"""Portfolio CLI: holdings snapshot, realized-gains tax, and dividend tax summary."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

from valuation.portfolio.ibkr import IbkrDividend, load_activity_statement
from valuation.portfolio.lots import Lot, RealizedGain, build_lots_and_realized, non_eur_currency_dates
from valuation.portfolio.tax_si import (
    next_si_cgt_threshold,
    si_cgt_rate,
    si_cgt_tax,
    si_dividend_tax,
)

_ENV_STATEMENT_PATH = "IBKR_STATEMENT_PATH"

# IBKR uses exchange-local symbols; Yahoo needs exchange suffixes for non-US listings.
# Add entries here when a symbol consistently fails Yahoo price lookup.
_IBKR_YAHOO_OVERRIDES: dict[str, str] = {
    "BNP": "BNP.PA",    # BNP Paribas — Euronext Paris
    "FWRA": "FWRA.L",   # Invesco FTSE All-World — London
    "VWCE": "VWCE.DE",  # Vanguard FTSE All-World — Xetra
    "PAH3": "PAH3.DE",  # Porsche Automobil Holding — Frankfurt
    "PAH3d": "PAH3.DE",
}


# ---------------------------------------------------------------------------
# Command runners
# ---------------------------------------------------------------------------

def run_portfolio_show(
    file: str | None,
    outdir: str,
    output_format: str,
    use_cache: bool = True,
    fx_auto: bool = False,
) -> int:
    """Show open positions with cost basis, unrealized P&L, and Slovenian tax tier."""
    paths = _resolve_statement_paths(file)
    if not paths:
        return 1

    trades, _dividends, meta = _load_combined_statement(paths)
    fx_rates = _maybe_fetch_fx(trades, fx_auto)
    open_lots, _ = build_lots_and_realized(trades, fx_rates=fx_rates)

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
    fx_auto: bool = False,
) -> int:
    """Show realized gains for a tax year and compute Slovenian CGT owed."""
    paths = _resolve_statement_paths(file)
    if not paths:
        return 1

    trades, _dividends, meta = _load_combined_statement(paths)
    fx_rates = _maybe_fetch_fx(trades, fx_auto)
    _, realized = build_lots_and_realized(trades, fx_rates=fx_rates)

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


def run_portfolio_dividends(
    file: str | None,
    year: int,
    outdir: str,
    output_format: str,
    fx_auto: bool = False,
) -> int:
    """Show dividend income for a tax year and compute Slovenian dividend tax owed."""
    paths = _resolve_statement_paths(file)
    if not paths:
        return 1

    _trades, dividends, meta = _load_combined_statement(paths)

    # Filter to the requested year
    year_divs = [d for d in dividends if d.payment_date.year == year]
    if not year_divs:
        print(f"No dividends found for {year}.")
        return 0

    # For non-EUR dividends we need FX rates; fetch if requested
    non_eur_pairs = [
        (d.currency, d.payment_date)
        for d in year_divs
        if d.currency != "EUR"
    ]
    fx_rates: dict = {}
    if fx_auto and non_eur_pairs:
        from valuation.portfolio.fx import EcbFxClient
        client = EcbFxClient()
        fx_rates = client.build_fx_rates_dict(non_eur_pairs)

    div_table = _build_dividend_table(year_divs, fx_rates)
    summary_table = _build_dividend_summary(year_divs, fx_rates, year)

    _print_and_save(
        [
            (f"Dividends {year}", div_table),
            ("Dividend Tax Summary", summary_table),
        ],
        outdir=outdir,
        output_format=output_format,
        slug=f"portfolio_dividends_{year}",
    )
    return 0


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

def _build_holdings_table(open_lots: list[Lot], *, use_cache: bool = True) -> pd.DataFrame:
    today = date.today()
    by_symbol: dict[str, list[Lot]] = {}
    for lot in open_lots:
        by_symbol.setdefault(lot.symbol, []).append(lot)

    prices = _fetch_prices(list(by_symbol.keys()), use_cache=use_cache)

    # Collect all currencies quoted in the snapshots (may differ from trade currency)
    quote_currencies: set[str] = set()
    for symbol in by_symbol:
        snap = prices.get(_ibkr_to_yahoo(symbol), {})
        qc = (snap.get("currency") or "").upper()
        if qc and qc != "EUR":
            quote_currencies.add(qc)
    # Also include trade currencies in case quote currency is missing from snapshot
    for lots in by_symbol.values():
        tc = (lots[0].currency or "").upper()
        if tc and tc != "EUR":
            quote_currencies.add(tc)
    live_fx = _fetch_live_fx_for_currencies(quote_currencies)

    rows = []
    for symbol, lots in sorted(by_symbol.items()):
        total_qty = sum(l.quantity for l in lots)
        total_cost_eur = _sum_optional(l.cost_basis_eur for l in lots)
        avg_cost_eur = (total_cost_eur / total_qty
                        if (total_cost_eur is not None and total_qty > 0)
                        else None)

        oldest = min(lots, key=lambda l: l.acquired)
        threshold = next_si_cgt_threshold(oldest.acquired, today)
        current_rate = si_cgt_rate(oldest.acquired, today)
        days_to_next = (threshold[0] - today).days if threshold else None

        snap = prices.get(_ibkr_to_yahoo(symbol), {})
        last_price_eur = _to_eur_price(snap, lots[0].currency, live_fx=live_fx)
        value_eur = last_price_eur * total_qty if last_price_eur is not None else None
        unrealized_eur = (
            (value_eur - total_cost_eur)
            if (value_eur is not None and total_cost_eur is not None)
            else None
        )

        rows.append(
            {
                "symbol": symbol,
                "lots": len(lots),
                "shares": _fmt_qty(total_qty),
                "avg_cost_eur": _fmt_eur(avg_cost_eur),
                "last_eur": _fmt_eur(last_price_eur),
                "value_eur": _fmt_eur(value_eur),
                "unrealized_eur": _fmt_signed_eur(unrealized_eur),
                "oldest_lot": oldest.acquired.isoformat(),
                "cgt_rate": f"{current_rate * 100:.0f}%",
                "days_to_next_tier": (
                    str(days_to_next) if days_to_next is not None else "exempt"
                ),
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
    all_eur = [r.gain_eur for r in realized if r.gain_eur is not None]
    gains_eur = [g for g in all_eur if g > 0]
    losses_eur = [g for g in all_eur if g < 0]

    total_gains = sum(gains_eur) if gains_eur else None
    total_losses = sum(losses_eur) if losses_eur else None
    net_gain = sum(all_eur) if all_eur else None

    # Gross tax: sum per-disposal tax (each disposal may have a different rate)
    gross_tax = sum(
        si_cgt_tax(r.gain_eur, r.acquired, r.sold)
        for r in realized
        if r.gain_eur is not None
    )
    needs_fx = any(r.needs_fx for r in realized)

    rows = [
        {"metric": "Tax year", "value": str(year)},
        {"metric": "Gross realized gains", "value": _fmt_eur(total_gains)},
        {"metric": "Gross realized losses", "value": _fmt_signed_eur(total_losses)},
        {"metric": "Net gain / loss", "value": _fmt_signed_eur(net_gain)},
        {"metric": "Gross CGT due", "value": _fmt_eur(gross_tax)},
        {
            "metric": "Note",
            "value": (
                "Some EUR amounts missing (non-EUR trades, no FX rates). "
                "Re-run with --fx-auto or provide ECB rates. Tax figures are partial."
                if needs_fx
                else "Losses may offset gains; carry-forward rules apply. Verify with FURS."
            ),
        },
    ]
    return pd.DataFrame(rows)


def _build_dividend_table(
    dividends: list[IbkrDividend],
    fx_rates: dict,
) -> pd.DataFrame:
    rows = []
    for d in dividends:
        eur_rate = fx_rates.get((d.currency, d.payment_date.isoformat()), 1.0 if d.currency == "EUR" else None)
        gross_eur = d.amount * eur_rate if eur_rate is not None else None
        wht_eur = d.withholding_tax * eur_rate if eur_rate is not None else None
        top_up = (
            si_dividend_tax(gross_eur, wht_eur)
            if (gross_eur is not None and wht_eur is not None)
            else None
        )
        rows.append(
            {
                "symbol": d.symbol,
                "date": d.payment_date.isoformat(),
                "currency": d.currency,
                "gross_native": _fmt_currency(d.amount, d.currency),
                "wht_native": _fmt_currency(d.withholding_tax, d.currency),
                "gross_eur": _fmt_eur(gross_eur),
                "wht_eur": _fmt_eur(wht_eur),
                "si_topup_eur": _fmt_eur(top_up),
                "needs_fx": eur_rate is None,
            }
        )
    return pd.DataFrame(rows)


def _build_dividend_summary(
    dividends: list[IbkrDividend],
    fx_rates: dict,
    year: int,
) -> pd.DataFrame:
    gross_eur_total = 0.0
    wht_eur_total = 0.0
    topup_total = 0.0
    partial = False

    for d in dividends:
        eur_rate = fx_rates.get((d.currency, d.payment_date.isoformat()), 1.0 if d.currency == "EUR" else None)
        if eur_rate is None:
            partial = True
            continue
        gross_eur = d.amount * eur_rate
        wht_eur = d.withholding_tax * eur_rate
        gross_eur_total += gross_eur
        wht_eur_total += wht_eur
        topup_total += si_dividend_tax(gross_eur, wht_eur)

    rows = [
        {"metric": "Tax year", "value": str(year)},
        {"metric": "Gross dividend income (EUR)", "value": _fmt_eur(gross_eur_total)},
        {"metric": "Foreign WHT already paid (EUR)", "value": _fmt_eur(wht_eur_total)},
        {"metric": "Additional SI dividend tax due (EUR)", "value": _fmt_eur(topup_total)},
        {
            "metric": "Note",
            "value": (
                "Some EUR amounts missing — re-run with --fx-auto for full totals."
                if partial
                else "Verify with FURS before filing (DOHDSP-2 form)."
            ),
        },
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# FX helpers
# ---------------------------------------------------------------------------

def _maybe_fetch_fx(trades, fx_auto: bool) -> dict | None:
    if not fx_auto:
        return None
    pairs = non_eur_currency_dates(trades)
    if not pairs:
        return None
    from valuation.portfolio.fx import EcbFxClient
    client = EcbFxClient()
    return client.build_fx_rates_dict(pairs)


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------

def _fetch_prices(symbols: list[str], *, use_cache: bool) -> dict[str, dict]:
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


def _to_eur_price(
    snap: dict,
    trade_currency: str,
    *,
    live_fx: dict[str, float] | None = None,
) -> float | None:
    if not snap:
        return None
    last = snap.get("last_price")
    if last is None:
        return None
    currency = (snap.get("currency") or trade_currency or "").upper()
    if currency == "EUR":
        return float(last)
    if live_fx:
        rate = live_fx.get(currency)
        if rate is not None:
            return float(last) * rate
    return None


def _fetch_live_fx_for_currencies(currencies: set[str]) -> dict[str, float]:
    """Fetch today's ECB spot rate for each non-EUR currency."""
    if not currencies:
        return {}
    from valuation.portfolio.fx import EcbFxClient
    client = EcbFxClient()
    today = date.today()
    result: dict[str, float] = {}
    for cur in currencies:
        if cur == "EUR":
            continue
        rate = client.eur_per_unit(cur, today)
        if rate is not None:
            result[cur] = rate
    return result


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _resolve_statement_paths(file: str | None) -> list[Path]:
    """Resolve one or more statement paths from --file arg or env var.

    --file accepts comma-separated paths for combining multi-year exports.
    """
    raw = file or os.environ.get(_ENV_STATEMENT_PATH)
    if raw is None:
        print(
            f"Error: no IBKR statement file specified. "
            f"Use --file <path>[,<path>...] or set {_ENV_STATEMENT_PATH} in .env.",
            file=sys.stderr,
        )
        return []
    paths: list[Path] = []
    for part in raw.split(","):
        p = Path(part.strip()).expanduser()
        if not p.is_file():
            print(f"Error: statement file not found: {p}", file=sys.stderr)
            return []
        paths.append(p)
    return paths


def _load_combined_statement(
    paths: list[Path],
    fx_auto: bool = False,
):
    """Load and merge trades/dividends from one or more statement files.

    Deduplicates trades by (symbol, trade_date, quantity, price) so overlapping
    date ranges in adjacent year exports don't double-count.
    Returns (trades, dividends, meta) where meta is from the last file.
    """
    from valuation.portfolio.ibkr import IbkrTrade, IbkrDividend, IbkrStatementMeta

    all_trades: list[IbkrTrade] = []
    all_dividends: list[IbkrDividend] = []
    meta: IbkrStatementMeta | None = None

    for path in sorted(paths):  # chronological by filename
        trades, dividends, m = load_activity_statement(path)
        all_trades.extend(trades)
        all_dividends.extend(dividends)
        meta = m

    # Deduplicate trades: same symbol + date + quantity + price = same trade
    seen_trades: set[tuple] = set()
    deduped_trades: list[IbkrTrade] = []
    for t in all_trades:
        key = (t.symbol, t.trade_date, t.quantity, t.price)
        if key not in seen_trades:
            seen_trades.add(key)
            deduped_trades.append(t)

    # Deduplicate dividends: same symbol + date + amount
    seen_divs: set[tuple] = set()
    deduped_divs: list[IbkrDividend] = []
    for d in all_dividends:
        key = (d.symbol, d.payment_date, d.amount)
        if key not in seen_divs:
            seen_divs.add(key)
            deduped_divs.append(d)

    if meta is None:
        from valuation.portfolio.ibkr import IbkrStatementMeta
        meta = IbkrStatementMeta(base_currency="EUR", account_id="", from_date=None, to_date=None)

    return deduped_trades, deduped_divs, meta


def _ibkr_to_yahoo(symbol: str) -> str:
    """Normalize IBKR symbol format to Yahoo Finance format."""
    if symbol in _IBKR_YAHOO_OVERRIDES:
        return _IBKR_YAHOO_OVERRIDES[symbol]
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


def _fmt_currency(value: float, currency: str) -> str:
    symbol = "€" if currency == "EUR" else ("$" if currency == "USD" else currency + " ")
    return f"{symbol}{value:,.2f}"


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
            "(non-EUR trades). Re-run with --fx-auto to fetch ECB historical rates.",
            file=sys.stderr,
        )


def _warn_needs_fx_realized(realized: list[RealizedGain]) -> None:
    non_eur = {r.symbol for r in realized if r.needs_fx}
    if non_eur:
        print(
            f"\nNote: EUR amounts incomplete for {', '.join(sorted(non_eur))}. "
            "Re-run with --fx-auto for full tax calculation.",
            file=sys.stderr,
        )
