"""Multi-security comparison table builder."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import pandas as pd

from valuation.company.service import fetch_company_snapshot
from valuation.company.tables import (
    extract_financials_ttm_from_company_facts,
    extract_financials_ttm_from_yahoo_frames,
    extract_period_label_from_company_facts,
)
from valuation.data.providers.yahoo import YahooFinanceClient


@dataclass
class CompsEntry:
    ticker: str
    name: str | None
    market_snapshot: Mapping[str, Any]
    financials: dict[str, float | None]
    period_label: str | None
    error: str | None = None


def fetch_comps_entries(
    tickers: Sequence[str],
    *,
    max_workers: int = 8,
) -> list[CompsEntry]:
    """Fetch snapshot + TTM financials for multiple tickers in parallel.

    Errors per ticker are captured in ``CompsEntry.error`` rather than raised,
    so a single bad ticker does not abort the whole set.
    """

    def _fetch_one(ticker: str) -> CompsEntry:
        try:
            bundle = fetch_company_snapshot(ticker)
            name = (
                (bundle.company_profile or {}).get("name")
                or getattr(bundle.resolution, "company_name", None)
                or ticker
            )
            yahoo = YahooFinanceClient()
            if bundle.company_facts:
                financials, ttm_label = extract_financials_ttm_from_company_facts(bundle.company_facts)
                period_label = ttm_label or extract_period_label_from_company_facts(bundle.company_facts)
            elif bundle.company_profile:
                requests = [
                    ("income", "annual"),
                    ("income", "quarterly"),
                    ("balance", "annual"),
                    ("balance", "quarterly"),
                    ("cashflow", "annual"),
                    ("cashflow", "quarterly"),
                ]
                with ThreadPoolExecutor(max_workers=len(requests)) as ex:
                    ff = {
                        r: ex.submit(
                            yahoo.fetch_statement_frame,
                            bundle.resolution.ticker,
                            statement=r[0],
                            period=r[1],
                        )
                        for r in requests
                    }
                frames = {r: f.result() for r, f in ff.items()}
                currency = (bundle.company_profile or {}).get("currency", "USD")
                financials, period_label = extract_financials_ttm_from_yahoo_frames(
                    income_annual=frames[("income", "annual")],
                    balance_annual=frames[("balance", "annual")],
                    cashflow_annual=frames[("cashflow", "annual")],
                    income_quarterly=frames[("income", "quarterly")],
                    balance_quarterly=frames[("balance", "quarterly")],
                    cashflow_quarterly=frames[("cashflow", "quarterly")],
                    currency=currency,
                )
            else:
                financials, period_label = {}, None
            return CompsEntry(
                ticker=bundle.resolution.ticker,
                name=str(name).strip().replace("\n", " ")[:40] if name else ticker,
                market_snapshot=bundle.market_snapshot,
                financials=financials,
                period_label=period_label,
            )
        except Exception as exc:
            return CompsEntry(
                ticker=ticker,
                name=ticker,
                market_snapshot={},
                financials={},
                period_label=None,
                error=str(exc)[:120],
            )

    results: dict[str, CompsEntry] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        for fut in as_completed(futures):
            entry = fut.result()
            results[futures[fut]] = entry

    return [
        results.get(t, CompsEntry(ticker=t, name=t, market_snapshot={}, financials={}, period_label=None, error="not fetched"))
        for t in tickers
    ]


def build_comps_table(entries: Sequence[CompsEntry]) -> pd.DataFrame:
    """Return a multi-security comparison table with one row per security.

    Columns:
      ticker, name, price, market_cap,
      revenue, net_income, owner_earnings, oe_margin_pct,
      pe_ratio, price_to_oe, oe_yield_pct, ev_to_ebitda,
      implied_growth_pct (at 10% required return), as_of

    All ratio / yield / growth columns are 0-1 decimals so ``humanize_frame``
    renders them as percent or multiple automatically.
    """
    rows = []
    for e in entries:
        ms = e.market_snapshot
        fin = e.financials

        price = _f(ms.get("last_price"))
        market_cap = _f(ms.get("market_cap"))
        shares = _f(ms.get("shares"))
        if market_cap is None and price and shares:
            market_cap = price * shares

        revenue = _f(fin.get("revenue"))
        net_income = _f(fin.get("net_income"))
        da = _f(fin.get("depreciation_amortization"))
        capex = _f(fin.get("capex"))
        ocf = _f(fin.get("operating_cash_flow"))
        op_income = _f(fin.get("operating_income"))
        cash = _f(fin.get("cash_and_equivalents"))
        ltd = _f(fin.get("long_term_debt"))

        oe: float | None = None
        if net_income is not None and da is not None and capex is not None:
            oe_raw = net_income + da - capex
            oe = oe_raw if oe_raw > 0 else None

        ev: float | None = None
        if market_cap is not None and ltd is not None and cash is not None:
            ev = market_cap + ltd - cash

        ebitda: float | None = None
        if op_income is not None and da is not None:
            ebitda = op_income + da

        rows.append({
            "ticker": e.ticker,
            "name": e.name,
            "price": price,
            "market_cap": market_cap,
            "revenue": revenue,
            "net_income": net_income,
            "owner_earnings": oe,
            "oe_margin_pct": _ratio(oe, revenue),
            "pe_ratio": _ratio(market_cap, net_income),
            "price_to_oe": _ratio(market_cap, oe),
            "oe_yield_pct": _ratio(oe, market_cap),
            "ev_to_ebitda": _ratio(ev, ebitda),
            "implied_growth_pct": _implied_growth(oe, market_cap, required_return=0.10),
            "as_of": e.period_label,
            "error": e.error,
        })
    return pd.DataFrame(rows)


def _ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _implied_growth(oe: float | None, market_cap: float | None, *, required_return: float) -> float | None:
    oe_yield = _ratio(oe, market_cap)
    if oe_yield is None:
        return None
    return required_return - oe_yield


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
