"""Historical per-fiscal-year valuation ratio builder."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

import pandas as pd

from valuation.company.statements import build_statement_table


def build_historical_ratios_table(
    company_facts: Mapping[str, Any],
    price_history: pd.DataFrame,
    *,
    limit: int = 10,
) -> pd.DataFrame:
    """Return per-fiscal-year valuation ratios for a SEC-backed company.

    For each annual period in the company facts, the function:
      1. reads financial metrics from the annual income, balance, and cashflow tables
      2. looks up the stock price on (or near) the fiscal year end date
      3. computes P/E, P/OE, OE yield, P/B, and EV/EBITDA

    ``price_history`` should be a monthly OHLCV frame from
    ``YahooFinanceClient.fetch_history(..., period="max", interval="1mo")``.

    Columns: fiscal_year, end_date, price, market_cap, net_income, revenue,
             owner_earnings, pe_ratio, price_to_oe, oe_yield_pct, pb_ratio,
             ev_to_ebitda
    """
    income = build_statement_table(company_facts, statement="income", period="annual", limit=limit)
    balance = build_statement_table(company_facts, statement="balance", period="annual", limit=limit)
    cashflow = build_statement_table(company_facts, statement="cashflow", period="annual", limit=limit)

    period_cols = [c for c in income.columns if c not in {"metric", "unit"}]
    if not period_cols:
        return pd.DataFrame()

    period_end_dates = _annual_period_end_dates(company_facts, limit=limit)
    price_map = _price_by_month_map(price_history)

    # Build metric→value lookup for each period
    def _row_values(table: pd.DataFrame, metric: str) -> dict[str, float | None]:
        rows = table[table["metric"] == metric]
        if rows.empty:
            return {}
        row = rows.iloc[0]
        return {col: _f(row.get(col)) for col in period_cols}

    ni_by_period = _row_values(income, "net_income")
    rev_by_period = _row_values(income, "revenue")
    shares_by_period = _row_values(income, "diluted_shares")
    da_by_period = _row_values(cashflow, "depreciation_amortization")
    capex_by_period = _row_values(cashflow, "capex")
    ocf_by_period = _row_values(cashflow, "operating_cash_flow")
    equity_by_period = _row_values(balance, "stockholders_equity")
    cash_by_period = _row_values(balance, "cash_and_equivalents")
    ltd_by_period = _row_values(balance, "long_term_debt")
    op_income_by_period = _row_values(income, "operating_income")

    rows_out = []
    for period_col in period_cols:
        end_date_str = period_end_dates.get(period_col)
        end_date = _parse_date(end_date_str)
        price = _price_for_date(price_map, end_date) if end_date else None

        net_income = ni_by_period.get(period_col)
        revenue = rev_by_period.get(period_col)
        shares = shares_by_period.get(period_col)
        da = da_by_period.get(period_col)
        capex = capex_by_period.get(period_col)
        equity = equity_by_period.get(period_col)
        cash = cash_by_period.get(period_col)
        ltd = ltd_by_period.get(period_col)
        op_income = op_income_by_period.get(period_col)

        oe: float | None = None
        if net_income is not None and da is not None and capex is not None:
            raw = net_income + da - capex
            oe = raw if raw > 0 else None

        market_cap = (price * shares) if price and shares else None
        ev: float | None = None
        if market_cap is not None and ltd is not None and cash is not None:
            ev = market_cap + ltd - cash
        ebitda: float | None = None
        if op_income is not None and da is not None:
            ebitda = op_income + da

        rows_out.append({
            "fiscal_year": period_col,
            "end_date": end_date_str,
            "price": price,
            "market_cap": market_cap,
            "net_income": net_income,
            "revenue": revenue,
            "owner_earnings": oe,
            "pe_ratio": _r(market_cap, net_income),
            "price_to_oe": _r(market_cap, oe),
            "oe_yield_pct": _r(oe, market_cap),
            "pb_ratio": _r(market_cap, equity),
            "ev_to_ebitda": _r(ev, ebitda),
        })

    return pd.DataFrame(rows_out)


def build_historical_ratios_table_from_yahoo(
    income_annual: pd.DataFrame,
    balance_annual: pd.DataFrame,
    cashflow_annual: pd.DataFrame,
    price_history: pd.DataFrame,
    *,
    currency: str = "USD",
) -> pd.DataFrame:
    """Return per-fiscal-year valuation ratios from Yahoo annual statement frames.

    Yahoo frames have actual Timestamp column names, which are used directly to
    look up historical prices.

    Columns: same as ``build_historical_ratios_table``.
    """
    from valuation.company.yahoo_statements import YAHOO_STATEMENT_LABELS, _resolve_yahoo_value

    if income_annual is None or income_annual.empty:
        return pd.DataFrame()

    period_dates = sorted(
        [c for c in income_annual.columns if hasattr(c, "year")],
        reverse=True,
    )
    if not period_dates:
        return pd.DataFrame()

    price_map = _price_by_month_map(price_history)

    def _yahoo_value(frame: pd.DataFrame, statement: str, metric: str, ts) -> float | None:
        if frame is None or frame.empty:
            return None
        if ts not in frame.columns:
            return None
        col = frame[ts]
        candidates: list[str] = list(YAHOO_STATEMENT_LABELS.get(statement, {}).get(metric, []))
        return _resolve_yahoo_value(col, candidates=candidates)

    rows_out = []
    for ts in period_dates:
        end_date_str = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
        end_date = _parse_date(end_date_str)
        price = _price_for_date(price_map, end_date) if end_date else None

        net_income = _yahoo_value(income_annual, "income", "net_income", ts)
        revenue = _yahoo_value(income_annual, "income", "revenue", ts)
        da = _yahoo_value(cashflow_annual, "cashflow", "depreciation_amortization", ts)
        capex = _yahoo_value(cashflow_annual, "cashflow", "capex", ts)
        equity = _yahoo_value(balance_annual, "balance", "stockholders_equity", ts)
        cash = _yahoo_value(balance_annual, "balance", "cash_and_equivalents", ts)
        ltd = _yahoo_value(balance_annual, "balance", "long_term_debt", ts)
        op_income = _yahoo_value(income_annual, "income", "operating_income", ts)
        shares_snap = _yahoo_value(income_annual, "income", "diluted_shares", ts)

        oe: float | None = None
        if net_income is not None and da is not None and capex is not None:
            raw = net_income + da - capex
            oe = raw if raw > 0 else None

        fiscal_label = f"FY {ts.year}" if hasattr(ts, "year") else end_date_str[:4]
        # Derive shares from market cap if available
        market_cap = None
        if price and shares_snap:
            market_cap = price * shares_snap
        ev: float | None = None
        if market_cap is not None and ltd is not None and cash is not None:
            ev = market_cap + ltd - cash
        ebitda = (op_income + da) if op_income is not None and da is not None else None

        rows_out.append({
            "fiscal_year": fiscal_label,
            "end_date": end_date_str,
            "price": price,
            "market_cap": market_cap,
            "net_income": net_income,
            "revenue": revenue,
            "owner_earnings": oe,
            "pe_ratio": _r(market_cap, net_income),
            "price_to_oe": _r(market_cap, oe),
            "oe_yield_pct": _r(oe, market_cap),
            "pb_ratio": _r(market_cap, equity),
            "ev_to_ebitda": _r(ev, ebitda),
        })

    return pd.DataFrame(rows_out)


def _annual_period_end_dates(
    company_facts: Mapping[str, Any],
    *,
    limit: int = 10,
) -> dict[str, str]:
    """Return {period_label: end_date_str} for the most recent annual periods.

    Reads annual entries directly from companyfacts to recover the actual fiscal
    year end date, which is lost when the statement table converts it to a label.
    """
    facts = company_facts.get("facts", {})
    annual_forms = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}

    # Try common income + cashflow concepts until one has annual entries
    _probe_candidates = [
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "Revenues"),
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
    ]
    for taxonomy, concept in _probe_candidates:
        entries = facts.get(taxonomy, {}).get(concept, {}).get("units", {}).get("USD", [])
        year_to_end: dict[int, str] = {}
        for entry in entries:
            fp = entry.get("fp", "")
            form = entry.get("form", "")
            end = entry.get("end", "")
            if not end:
                continue
            if fp == "FY" or form in annual_forms:
                try:
                    y = int(end[:4])
                    existing = year_to_end.get(y, "")
                    if end > existing:
                        year_to_end[y] = end
                except (ValueError, IndexError):
                    pass
        if year_to_end:
            top_years = sorted(year_to_end.keys(), reverse=True)[:limit]
            return {f"FY {y}": year_to_end[y] for y in top_years}
    return {}


def _price_by_month_map(price_history: pd.DataFrame) -> dict[tuple[int, int], float]:
    """Build a {(year, month): close_price} lookup from a monthly price history frame."""
    if price_history is None or price_history.empty:
        return {}
    result: dict[tuple[int, int], float] = {}
    date_col = next((c for c in ("date", "Date", "index") if c in price_history.columns), None)
    close_col = next((c for c in ("close", "Close", "adj close", "Adj Close") if c in price_history.columns), None)
    if not date_col or not close_col:
        return {}
    for _, row in price_history.iterrows():
        ts = pd.to_datetime(row[date_col], errors="coerce")
        if pd.isna(ts):
            continue
        val = _f(row[close_col])
        if val is None:
            continue
        result[(ts.year, ts.month)] = val
    return result


def _price_for_date(
    price_map: dict[tuple[int, int], float],
    target: date | None,
    *,
    search_months: int = 3,
) -> float | None:
    """Return the closest monthly price bar to ``target``.

    Searches backward up to ``search_months`` months, then forward the same,
    to handle months with no bar (holiday gaps, data gaps, etc.).
    """
    if target is None or not price_map:
        return None
    y, m = target.year, target.month
    for delta in range(search_months + 1):
        for sign in (-1, 1):
            if delta == 0 and sign == 1:
                continue
            total_months = y * 12 + m - 1 + sign * delta
            yr, mo = divmod(total_months, 12)
            mo += 1
            v = price_map.get((yr, mo))
            if v is not None:
                return v
    return None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _r(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None
