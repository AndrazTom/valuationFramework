"""Portfolio CLI: show holdings and compute Slovenian realized-gains tax."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from valuation.portfolio.ibkr import load_activity_statement
from valuation.portfolio.lots import Lot, RealizedGain, build_lots_and_realized
from valuation.portfolio.tax_si import next_si_cgt_threshold, si_cgt_rate, si_cgt_tax

_ENV_STATEMENT_PATH = "IBKR_STATEMENT_PATH"


# ---------------------------------------------------------------------------
# Command runners
# ---------------------------------------------------------------------------

def run_portfolio_show(
    file: str | None,
    outdir: str,
    output_format: str,
    use_cache: bool = True,
) -> int:
    """Show open positions with cost basis, unrealized P&L, and Slovenian tax tier."""
    path = _resolve_statement_path(file)
    if path is None:
        print(
            "Error: specify an IBKR activity statement with --file <path> "
            f"or set {_ENV_STATEMENT_PATH}.",
            file=sys.stderr,
        )
        return 1

    trades = load_activity_statement(path)
    open_lots, _ = build_lots_and_realized(trades)

    if not open_lots:
        print("No open positions found in statement.")
        return 0

    holdings_table = _build_holdings_table(open_lots, use_cache=use_cache)
    _print_and_save(
        [("Holdings", holdings_table)],
        outdir=outdir,
        output_format=output_format,
        slug="portfolio_holdings",
    )
    _warn_needs_fx(open_lots)
    return 0


def run_portfolio_tax(
    file: str | None,
    year: int,
    outdir: str,
    output_format: str,
) -> int:
    """Show realized gains for a given tax year and compute Slovenian CGT owed."""
    path = _resolve_statement_path(file)
    if path is None:
        print(
            "Error: specify an IBKR activity statement with --file <path> "
            f"or set {_ENV_STATEMENT_PATH}.",
            file=sys.stderr,
        )
        return 1

    trades = load_activity_statement(path)
    _, realized = build_lots_and_realized(trades)

    year_gains = [r for r in realized if r.sold.year == year]
    if not year_gains:
        print(f"No realized gains/losses found for {year}.")
        return 0

    tax_table = _build_tax_table(year_gains)
    summary_table = _build_tax_summary(year_gains, year)

    _print_and_save(
        [
            (f"Realized Gains {year}", tax_table),
            ("Tax Summary", summary_table),
        ],
        outdir=outdir,
        output_format=output_format,
        slug=f"portfolio_tax_{year}",
    )
    _warn_needs_fx_realized(year_gains)
    return 0


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

def _build_holdings_table(open_lots: list[Lot], *, use_cache: bool = True) -> pd.DataFrame:
    """Aggregate open lots per symbol, enrich with live Yahoo prices."""
    today = date.today()

    # Group lots by symbol
    by_symbol: dict[str, list[Lot]] = {}
    for lot in open_lots:
        by_symbol.setdefault(lot.symbol, []).append(lot)

    # Fetch current prices in parallel
    yahoo_symbols = list(by_symbol.keys())
    prices = _fetch_prices(yahoo_symbols, use_cache=use_cache)

    rows = []
    for symbol, lots in sorted(by_symbol.items()):
        total_qty = sum(l.quantity for l in lots)
        total_cost_eur = _sum_optional(l.cost_basis_eur for l in lots)
        avg_cost_eur = total_cost_eur / total_qty if (total_cost_eur is not None and total_qty > 0) else None

        oldest_lot = min(lots, key=lambda l: l.acquired)
        threshold = next_si_cgt_threshold(oldest_lot.acquired, today)
        current_rate = si_cgt_rate(oldest_lot.acquired, today)
        days_to_next = (threshold[0] - today).days if threshold else None

        snap = prices.get(_ibkr_to_yahoo(symbol), {})
        last_price_eur = _to_eur_price(snap, lots[0].currency)
        value_eur = last_price_eur * total_qty if last_price_eur is not None else None
        unrealized_eur = (value_eur - total_cost_eur) if (value_eur is not None and total_cost_eur is not None) else None

        rows.append(
            {
                "symbol": symbol,
                "lots": len(lots),
                "shares": _fmt_qty(total_qty),
                "avg_cost_eur": _fmt_eur(avg_cost_eur),
                "last_eur": _fmt_eur(last_price_eur),
                "value_eur": _fmt_eur(value_eur),
                "unrealized_eur": _fmt_signed_eur(unrealized_eur),
                "oldest_lot": oldest_lot.acquired.isoformat(),
                "cgt_rate": f"{current_rate * 100:.0f}%",
                "days_to_next_tier": str(days_to_next) if days_to_next is not None else "exempt",
                "needs_fx": any(l.cost_basis_eur is None for l in lots),
            }
        )

    return pd.DataFrame(rows)


def _build_tax_table(realized: list[RealizedGain]) -> pd.DataFrame:
    rows = []
    for r in realized:
        rate = si_cgt_rate(r.acquired, r.sold)
        gain = r.gain_eur
        tax = si_cgt_tax(gain, r.acquired, r.sold) if gain is not None else None
        rows.append(
            {
                "symbol": r.symbol,
                "acquired": r.acquired.isoformat(),
                "sold": r.sold.isoformat(),
                "quantity": _fmt_qty(r.quantity),
                "cost_eur": _fmt_eur(r.cost_basis_eur),
                "proceeds_eur": _fmt_eur(r.proceeds_eur),
                "gain_eur": _fmt_signed_eur(gain),
                "years_held": f"{_years_held(r.acquired, r.sold):.1f}",
                "rate": f"{rate * 100:.0f}%",
                "tax_eur": _fmt_eur(tax),
                "needs_fx": r.needs_fx,
            }
        )
    return pd.DataFrame(rows)


def _build_tax_summary(realized: list[RealizedGain], year: int) -> pd.DataFrame:
    """Aggregate totals and net tax (gains offset losses within the year)."""
    eur_gains = [r.gain_eur for r in realized if r.gain_eur is not None and r.gain_eur > 0]
    eur_losses = [r.gain_eur for r in realized if r.gain_eur is not None and r.gain_eur < 0]
    all_eur = [r.gain_eur for r in realized if r.gain_eur is not None]

    total_gains = sum(eur_gains) if eur_gains else None
    total_losses = sum(eur_losses) if eur_losses else None
    net_gain = sum(all_eur) if all_eur else None

    # Tax is assessed on net gain (losses offset gains within the year)
    # Each gain row uses its own rate, but for a simple summary we compute gross tax per row
    gross_tax = sum(
        si_cgt_tax(r.gain_eur, r.acquired, r.sold)
        for r in realized
        if r.gain_eur is not None
    )

    needs_fx = any(r.needs_fx for r in realized)

    rows = [
        {"metric": "Tax year", "value": str(year)},
        {"metric": "Realized gains (gross)", "value": _fmt_eur(total_gains)},
        {"metric": "Realized losses (gross)", "value": _fmt_signed_eur(total_losses)},
        {"metric": "Net gain/loss", "value": _fmt_signed_eur(net_gain)},
        {"metric": "Gross tax due (before loss offset)", "value": _fmt_eur(gross_tax)},
        {
            "metric": "Note",
            "value": (
                "EUR amounts unavailable for some trades (FX conversion needed) — "
                "tax figures are partial. See --help for --fx-rates-file."
                if needs_fx
                else "All EUR amounts available. Verify with FURS before filing."
            ),
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------

def _fetch_prices(symbols: list[str], *, use_cache: bool) -> dict[str, dict]:
    """Fetch Yahoo price snapshots for a list of symbols in parallel."""
    from valuation.data.providers.yahoo import YahooFinanceClient

    client = YahooFinanceClient(use_cache=use_cache)
    yahoo_symbols = [_ibkr_to_yahoo(s) for s in symbols]

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(yahoo_symbols), 8)) as ex:
        futures = {s: ex.submit(_safe_fetch, client, s) for s in yahoo_symbols}
    for symbol, future in futures.items():
        snap = future.result()
        if snap:
            results[symbol] = snap
    return results


def _safe_fetch(client, symbol: str) -> dict | None:
    try:
        return client.fetch_price_snapshot(symbol)
    except Exception:
        return None


def _to_eur_price(snap: dict, trade_currency: str) -> float | None:
    """Extract last price in EUR from a Yahoo snapshot."""
    if not snap:
        return None
    last = snap.get("last_price")
    if last is None:
        return None
    currency = snap.get("currency") or trade_currency
    if currency == "EUR":
        return float(last)
    # For non-EUR quotes, we can't reliably convert without an FX rate
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_statement_path(file: str | None) -> Path | None:
    raw = file or os.environ.get(_ENV_STATEMENT_PATH)
    if raw is None:
        return None
    p = Path(raw).expanduser()
    if not p.is_file():
        print(f"Error: statement file not found: {p}", file=sys.stderr)
        return None
    return p


def _ibkr_to_yahoo(symbol: str) -> str:
    """Normalize IBKR symbol to Yahoo Finance format."""
    # IBKR uses "BRK B"; Yahoo uses "BRK-B"
    return symbol.replace(" ", "-")


def _sum_optional(values) -> float | None:
    total = 0.0
    any_value = False
    for v in values:
        if v is not None:
            total += v
            any_value = True
    return total if any_value else None


def _years_held(acquired: date, sold: date) -> float:
    return (sold - acquired).days / 365.25


def _fmt_eur(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"€{value:,.2f}"


def _fmt_signed_eur(value: float | None) -> str:
    if value is None:
        return "N/A"
    prefix = "+" if value > 0 else ""
    return f"{prefix}€{value:,.2f}"


def _fmt_qty(qty: float) -> str:
    if qty == int(qty):
        return str(int(qty))
    return f"{qty:.4f}"


def _print_and_save(
    sections: list[tuple[str, pd.DataFrame]],
    *,
    outdir: str,
    output_format: str,
    slug: str,
) -> None:
    import json

    from valuation.reports.tables import (
        frame_to_records,
        render_terminal_table,
        write_csv,
        write_json,
        write_markdown,
    )

    out_path = Path(outdir) / slug

    if output_format == "json":
        bundle = {
            "sections": {
                title.lower().replace(" ", "_"): frame_to_records(df)
                for title, df in sections
            }
        }
        print(json.dumps(bundle, indent=2))
        write_json(bundle, out_path / "bundle.json")
        return

    for title, df in sections:
        print(f"\n## {title}\n")
        print(render_terminal_table(df))

    out_path.mkdir(parents=True, exist_ok=True)
    for title, df in sections:
        name = title.lower().replace(" ", "_")
        write_csv(df, out_path / f"{name}.csv")
        write_markdown(df, out_path / f"{name}.md")

    print(f"\nWrote tables to {out_path}")


def _warn_needs_fx(open_lots: list[Lot]) -> None:
    non_eur = {l.symbol for l in open_lots if l.cost_basis_eur is None}
    if non_eur:
        print(
            f"\nNote: EUR cost basis unavailable for {', '.join(sorted(non_eur))} "
            "(non-EUR currency). Provide an FX rates file for full EUR P&L.",
            file=sys.stderr,
        )


def _warn_needs_fx_realized(realized: list[RealizedGain]) -> None:
    non_eur = {r.symbol for r in realized if r.needs_fx}
    if non_eur:
        print(
            f"\nNote: EUR amounts missing for {', '.join(sorted(non_eur))} — "
            "tax figures for these positions are incomplete.",
            file=sys.stderr,
        )
