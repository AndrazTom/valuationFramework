"""Portfolio CLI: holdings snapshot, realized-gains tax, and dividend tax summary."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from valuation.portfolio.ibkr import (
    IbkrDividend,
    IbkrStatementMeta,
    load_activity_statement,
)
from valuation.portfolio.ibkr_flex import FlexLot, load_flex_query
from valuation.portfolio.ibkr_flex import FlexInterest, parse_flex_interest
from valuation.portfolio.lots import Lot, RealizedGain, build_lots_and_realized, non_eur_currency_dates
from valuation.portfolio.tax_si import (
    next_si_cgt_threshold,
    si_cgt_rate,
    si_cgt_tax,
    si_dividend_tax,
    si_interest_tax,
)

_ENV_FLEX_PATH = "IBKR_FLEX_PATH"


# ---------------------------------------------------------------------------
# Command runners
# ---------------------------------------------------------------------------

def run_portfolio_gains(
    file: str | None,
    year: int,
    outdir: str,
    output_format: str,
    fx_auto: bool = True,
    show_fees: bool = False,
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

    lot_fees: dict[int, tuple[float, float]] = {}
    if show_fees:
        lot_fees = _extract_flex_fees(paths, year_gains, fx_rates)

    tax_table = _build_tax_table(year_gains, lot_fees=lot_fees, show_fees=show_fees)
    summary_table = _build_tax_summary(year_gains, year)

    note = _GAINS_FEE_NOTE_SHOW_FEES if show_fees else _GAINS_FEE_NOTE
    print(f"\nNote: {note}")
    _print_and_save(
        [
            (f"Realized Gains {year}", tax_table),
            ("Tax Summary", summary_table),
        ],
        outdir=outdir,
        output_format=output_format,
        slug=f"portfolio_gains_{year}",
    )
    _warn_needs_fx_realized(year_gains)
    return 0


def run_portfolio_dividends(
    file: str | None,
    year: int,
    outdir: str,
    output_format: str,
) -> int:
    """Show dividend income for a tax year and compute Slovenian dividend tax owed."""
    paths = _resolve_statement_paths(file)
    if not paths:
        return 1

    _trades, dividends, meta = _load_combined_statement(paths)

    year_divs = [d for d in dividends if d.payment_date.year == year]
    if not year_divs:
        print(f"No dividends found for {year}.")
        return 0

    fx_rates: dict = {}
    non_eur_pairs = [(d.currency, d.payment_date) for d in year_divs if d.currency != "EUR"]
    if non_eur_pairs:
        from valuation.portfolio.fx import EcbFxClient
        fx_rates = EcbFxClient().build_fx_rates_dict(non_eur_pairs)

    div_table = _build_dividend_table(year_divs, fx_rates)
    summary_table = _build_dividend_summary(year_divs, fx_rates, year)

    print(f"\nNote: {_DIVIDENDS_NOTE}")
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


def run_portfolio_interest(
    file: str | None,
    year: int,
    outdir: str,
    output_format: str,
    fx_auto: bool = True,
) -> int:
    """Show broker interest income for a tax year from IBKR Flex XML files."""
    paths = _resolve_statement_paths(file)
    if not paths:
        return 1

    interest = _load_interest_from_flex_paths(paths)
    year_interest = [row for row in interest if row.payment_date.year == year]
    if not year_interest:
        print(f"No broker interest found for {year}.")
        return 0

    fx_rates = _maybe_fetch_interest_fx(year_interest, fx_auto)
    interest_table = _build_interest_table(year_interest, fx_rates)
    summary_table = _build_interest_summary(year_interest, fx_rates, year)

    print(f"\nNote: {_INTEREST_NOTE}")
    _print_and_save(
        [
            (f"Interest {year}", interest_table),
            ("Interest Tax Summary", summary_table),
        ],
        outdir=outdir,
        output_format=output_format,
        slug=f"portfolio_interest_{year}",
    )
    return 0


def run_portfolio_furs_xml(
    file: str | None,
    year: int,
    outdir: str,
    forms: str = "all",
    fx_auto: bool = True,
) -> int:
    """Generate FURS eDavki XML forms (Doh-KDVP, Doh-Div, Doh-Obr) from IBKR Flex XML."""
    from valuation.portfolio.furs_xml import (
        build_div_xml,
        build_kdvp_xml,
        build_obr_xml,
        company_xml_snippet_for,
        load_taxpayer_from_env,
        lot_fx_pairs,
        missing_dividend_payers,
    )

    paths = _resolve_statement_paths(file)
    if not paths:
        return 1

    xml_paths = [p for p in paths if p.suffix.lower() == ".xml"]
    if not xml_paths:
        print("Error: furs-xml requires IBKR Flex XML (.xml) files.", file=sys.stderr)
        return 1

    taxpayer = load_taxpayer_from_env()
    if not taxpayer.get("tax_number"):
        print(
            "Warning: FURS_TAX_NUMBER not set. Add FURS_* vars to .env for a complete XML.",
            file=sys.stderr,
        )

    forms_set = {"kdvp", "div", "obr"} if forms == "all" else {forms}

    all_lots = []
    all_dividends = []
    all_interest = []
    for path in xml_paths:
        from valuation.portfolio.ibkr_flex import load_flex_query, parse_flex_interest
        lots, dividends, _meta = load_flex_query(path)
        interest = parse_flex_interest(path)
        all_lots.extend(lots)
        all_dividends.extend(dividends)
        all_interest.extend(interest)

    # Deduplicate dividends
    seen: set[tuple] = set()
    deduped_divs = []
    for d in all_dividends:
        key = (d.symbol, d.payment_date, d.amount)
        if key not in seen:
            seen.add(key)
            deduped_divs.append(d)

    fx_rates: dict = {}
    if fx_auto:
        from valuation.portfolio.fx import EcbFxClient
        pairs: list[tuple] = []
        pairs += lot_fx_pairs([l for l in all_lots if l.sold.year == year])
        pairs += _non_eur_dividend_currency_dates(
            [d for d in deduped_divs if d.payment_date.year == year]
        )
        pairs += _non_eur_interest_currency_dates(
            [r for r in all_interest if r.payment_date.year == year]
        )
        if pairs:
            fx_rates = EcbFxClient().build_fx_rates_dict(pairs)

    out_path = Path(outdir) / f"portfolio_furs_{year}"
    out_path.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    if "kdvp" in forms_set:
        xml_str = build_kdvp_xml(all_lots, year, taxpayer, fx_rates or None)
        p = out_path / "Doh-KDVP.xml"
        p.write_text(xml_str, encoding="utf-8")
        written.append(str(p))

    if "div" in forms_set:
        _warn_missing_dividend_payers(deduped_divs, year, missing_dividend_payers, company_xml_snippet_for)
        xml_str = build_div_xml(deduped_divs, year, taxpayer, fx_rates)
        p = out_path / "Doh-Div.xml"
        p.write_text(xml_str, encoding="utf-8")
        written.append(str(p))

    if "obr" in forms_set:
        xml_str = build_obr_xml(all_interest, year, taxpayer, fx_rates)
        p = out_path / "Doh-Obr.xml"
        p.write_text(xml_str, encoding="utf-8")
        written.append(str(p))

    print(f"\nWrote FURS XML to {out_path}:")
    for p in written:
        print(f"  {p}")
    sys.stdout.flush()
    _warn_missing_furs_taxpayer_fields(taxpayer)
    return 0


def _warn_missing_furs_taxpayer_fields(taxpayer: dict) -> None:
    fields = [
        ("FURS_NAME", "name"),
        ("FURS_ADDRESS", "address"),
        ("FURS_CITY", "city"),
        ("FURS_POST_NUMBER", "post_number"),
        ("FURS_POST_NAME", "post_name"),
        ("FURS_EMAIL", "email"),
        ("FURS_PHONE", "phone"),
    ]
    missing = [(env, key) for env, key in fields if not taxpayer.get(key)]
    if not missing:
        return

    print(
        "\nWarning: generated XML has blank taxpayer/contact fields. "
        "You can edit the generated XML manually, or set these and rerun:",
        file=sys.stderr,
    )
    for env, _ in missing:
        print(f'  export {env}="..."', file=sys.stderr)


def _warn_missing_dividend_payers(
    dividends: list[IbkrDividend],
    year: int,
    missing_func,
    snippet_func,
) -> None:
    missing = missing_func(dividends, year)
    if not missing:
        return

    print(
        "\nWarning: missing Doh-Div payer metadata in "
        "src/valuation/portfolio/data/companies.xml.",
        file=sys.stderr,
    )
    print(
        "Doh-Div.xml was still generated, but these rows have incomplete payer "
        "name/address/tax-number fields.",
        file=sys.stderr,
    )
    print(
        "Fix: add company entries like these to "
        "src/valuation/portfolio/data/companies.xml before the closing </companies> tag:",
        file=sys.stderr,
    )
    for dividend in missing:
        print("", file=sys.stderr)
        print(snippet_func(dividend), file=sys.stderr)


def run_portfolio_reconcile(
    file: str | None,
    year: int,
    outdir: str,
    output_format: str,
    fx_auto: bool = True,
) -> int:
    """Reconcile source IBKR rows to yearly tax and dividend summary totals."""
    paths = _resolve_statement_paths(file)
    if not paths:
        return 1

    file_summaries = _load_statement_file_summaries(paths)
    trades, dividends, _meta = _load_combined_statement(paths)

    trade_fx_rates = _maybe_fetch_fx(trades, fx_auto)
    _, realized = build_lots_and_realized(trades, fx_rates=trade_fx_rates)
    year_realized = [r for r in realized if r.sold.year == year]

    year_dividends = [d for d in dividends if d.payment_date.year == year]
    dividend_fx_rates = _maybe_fetch_dividend_fx(year_dividends, fx_auto)

    all_interest = _load_interest_from_flex_paths(paths)
    year_interest = [r for r in all_interest if r.payment_date.year == year]
    interest_fx_rates = _maybe_fetch_interest_fx(year_interest, fx_auto)

    trade_fx_pairs = non_eur_currency_dates(trades)
    dividend_fx_pairs = _non_eur_dividend_currency_dates(year_dividends)
    interest_fx_pairs = _non_eur_interest_currency_dates(year_interest)
    fx_table = _build_fx_coverage_table(
        trade_fx_pairs=trade_fx_pairs,
        trade_fx_rates=trade_fx_rates,
        dividend_fx_pairs=dividend_fx_pairs,
        dividend_fx_rates=dividend_fx_rates,
        interest_fx_pairs=interest_fx_pairs,
        interest_fx_rates=interest_fx_rates,
        fx_auto=fx_auto,
    )

    input_table = _build_reconcile_input_files_table(file_summaries)
    coverage_table = _build_reconcile_coverage_table(
        file_summaries=file_summaries,
        trades=trades,
        dividends=dividends,
        realized=realized,
        year_realized=year_realized,
        year_dividends=year_dividends,
        year_interest=year_interest,
        year=year,
        fx_table=fx_table,
    )
    realized_table = _build_realized_reconciliation_table(year_realized, year)
    dividend_table = _build_dividend_reconciliation_table(
        year_dividends,
        dividend_fx_rates,
        year,
    )
    interest_table = _build_interest_reconciliation_table(
        year_interest,
        interest_fx_rates,
        year,
    )
    warning_table = _build_reconcile_warnings_table(
        coverage_table=coverage_table,
        realized=year_realized,
        dividends=year_dividends,
        interest=year_interest,
        fx_table=fx_table,
        year=year,
    )

    _print_and_save(
        [
            ("Input Files", input_table),
            ("Coverage Summary", coverage_table),
            ("Realized Reconciliation", realized_table),
            ("Dividend Reconciliation", dividend_table),
            ("Interest Reconciliation", interest_table),
            ("FX Coverage", fx_table),
            ("Warnings", warning_table),
        ],
        outdir=outdir,
        output_format=output_format,
        slug=f"portfolio_reconcile_{year}",
        notes={
            "Dividend Reconciliation": _DIVIDENDS_NOTE,
            "Interest Reconciliation": _INTEREST_NOTE,
        },
    )
    return 0


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

_GAINS_FEE_NOTE = "Buy and sell commissions are included in cost and proceeds respectively (FURS requirement)."
_GAINS_FEE_NOTE_SHOW_FEES = (
    "Buy and sell commissions are included in cost and proceeds respectively (FURS requirement). "
    "The fee column shows the sell commission already deducted from proceeds — informational only."
)


def _build_tax_table(
    realized: list[RealizedGain],
    *,
    lot_fees: dict[int, tuple[float, float]] | None = None,
    show_fees: bool = False,
) -> pd.DataFrame:
    rows = []
    for idx, r in enumerate(realized, start=1):
        rate = si_cgt_rate(r.acquired, r.sold)
        gain_eur = r.gain_eur
        tax = si_cgt_tax(gain_eur, r.acquired, r.sold) if gain_eur is not None else None

        cost_val = _fmt_eur(r.cost_basis_eur) if r.cost_basis_eur is not None else _fmt_currency(r.cost_basis_native, r.currency)
        proceeds_val = _fmt_eur(r.proceeds_eur) if r.proceeds_eur is not None else _fmt_currency(r.proceeds_native, r.currency)
        gain_val = _fmt_signed_eur(gain_eur) if gain_eur is not None else _fmt_signed_currency(r.gain_native, r.currency)

        row: dict = {
            "id": idx,
            "symbol": r.symbol,
            "acquired": r.acquired.isoformat(),
            "sold": r.sold.isoformat(),
            "qty": _fmt_qty(r.quantity),
            "cost_eur": cost_val,
            "proceeds_eur": proceeds_val,
            "gain_eur": gain_val,
            "tax_rate": f"{rate * 100:.0f}%",
            "tax_eur": _fmt_eur(tax),
            "years_held": f"{_years_held(r.acquired, r.sold):.1f}",
        }
        if show_fees and lot_fees is not None:
            _, sell_fee = lot_fees.get(idx - 1, (0.0, 0.0))
            row["fee_eur"] = _fmt_eur(sell_fee) if sell_fee else "€0.00"
        rows.append(row)
    return pd.DataFrame(rows)



def _build_tax_summary(realized: list[RealizedGain], year: int) -> pd.DataFrame:
    all_eur = [r.gain_eur for r in realized if r.gain_eur is not None]
    gains_eur = [g for g in all_eur if g > 0]
    losses_eur = [g for g in all_eur if g < 0]

    total_gains = sum(gains_eur) if gains_eur else None
    total_losses = sum(losses_eur) if losses_eur else None
    net_gain = sum(all_eur) if all_eur else None

    needs_fx = any(r.needs_fx for r in realized)

    # Net CGT: Slovenian ZDoh-2 allows same-year loss offset; no carry-forward.
    # Tax is applied to max(0, net_gain). All disposals are at 25% (< 5 years held)
    # so we can simply apply the rate to the net. When multiple rates apply, we
    # show the net figure and advise FURS verification.
    net_cgt = max(0.0, net_gain) * 0.25 if net_gain is not None else None

    rows = [
        {"metric": "Tax year", "value": str(year)},
        {"metric": "Gross realized gains", "value": _fmt_eur(total_gains)},
        {"metric": "Gross realized losses", "value": _fmt_signed_eur(total_losses)},
        {"metric": "Net gain / loss", "value": _fmt_signed_eur(net_gain)},
        {"metric": "Net CGT due (25%)", "value": _fmt_eur(net_cgt)},
        {
            "metric": "Note",
            "value": (
                "Some EUR amounts missing (non-EUR trades, ECB FX fetch returned no data). "
                "Tax figures are partial."
                if needs_fx
                else "Losses offset gains within the same year (ZDoh-2). Verify with FURS."
            ),
        },
    ]
    return pd.DataFrame(rows)


_DIVIDENDS_NOTE = (
    "SI top-up estimate is informative only — assumes foreign WHT fully offsets the 25% SI rate "
    "(perfect DTA credit). Actual liability may differ."
)


def _build_dividend_table(
    dividends: list[IbkrDividend],
    fx_rates: dict,
) -> pd.DataFrame:
    rows = []
    for idx, d in enumerate(dividends, start=1):
        eur_rate = _dividend_eur_rate(d, fx_rates)
        gross_eur = d.amount * eur_rate if eur_rate is not None else None
        wht_eur = d.withholding_tax * eur_rate if eur_rate is not None else None
        top_up = (
            si_dividend_tax(gross_eur, wht_eur)
            if (gross_eur is not None and wht_eur is not None)
            else None
        )
        rows.append(
            {
                "id": idx,
                "symbol": d.symbol,
                "date": d.payment_date.isoformat(),
                "ccy": d.currency,
                "gross": _fmt_currency(d.amount, d.currency),
                "wht": _fmt_currency(d.withholding_tax, d.currency),
                "gross_eur": _fmt_eur(gross_eur),
                "wht_eur": _fmt_eur(wht_eur),
                "topup_eur": _fmt_eur(top_up),
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
                "Some EUR amounts missing — ECB FX fetch returned no data for these dates."
                if partial
                else "Verify with FURS before filing (DOHDSP-2 form)."
            ),
        },
    ]
    return pd.DataFrame(rows)


_INTEREST_NOTE = (
    "SI tax estimate is informative only — assumes foreign WHT fully offsets the 25% SI rate "
    "(perfect DTA credit). Actual liability may differ."
)


def _build_interest_table(
    interest: list[FlexInterest],
    fx_rates: dict,
) -> pd.DataFrame:
    rows = []
    for idx, row in enumerate(interest, start=1):
        eur_rate = _interest_eur_rate(row, fx_rates)
        gross_eur = row.amount * eur_rate if eur_rate is not None else None
        wht_eur = row.withholding_tax * eur_rate if eur_rate is not None else None
        tax = (
            si_interest_tax(gross_eur, wht_eur)
            if (gross_eur is not None and wht_eur is not None)
            else None
        )
        rows.append(
            {
                "id": idx,
                "date": row.payment_date.isoformat(),
                "ccy": row.currency,
                "gross": _fmt_currency(row.amount, row.currency),
                "wht": _fmt_currency(row.withholding_tax, row.currency),
                "gross_eur": _fmt_eur(gross_eur),
                "wht_eur": _fmt_eur(wht_eur),
                "topup_eur": _fmt_eur(tax),
            }
        )
    return pd.DataFrame(rows)


def _build_interest_summary(
    interest: list[FlexInterest],
    fx_rates: dict,
    year: int,
) -> pd.DataFrame:
    gross_total = 0.0
    wht_total = 0.0
    tax_total = 0.0
    partial = False
    for row in interest:
        eur_rate = _interest_eur_rate(row, fx_rates)
        if eur_rate is None:
            partial = True
            continue
        gross_eur = row.amount * eur_rate
        wht_eur = row.withholding_tax * eur_rate
        gross_total += gross_eur
        wht_total += wht_eur
        tax_total += si_interest_tax(gross_eur, wht_eur)

    return pd.DataFrame(
        [
            {"metric": "Tax year", "value": str(year)},
            {"metric": "Gross interest income (EUR)", "value": _fmt_eur(gross_total)},
            {"metric": "Foreign WHT already paid (EUR)", "value": _fmt_eur(wht_total)},
            {"metric": "Estimated SI interest tax due (EUR)", "value": _fmt_eur(tax_total)},
            {
                "metric": "Note",
                "value": (
                    "Some EUR amounts missing — ECB FX fetch returned no data for these dates."
                    if partial
                    else "Filing-shaped estimate for Doh-Obr; verify current treatment with FURS."
                ),
            },
        ]
    )


# ---------------------------------------------------------------------------
# Reconciliation table builders
# ---------------------------------------------------------------------------

def _load_statement_file_summaries(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(paths):
        if path.suffix.lower() == ".xml":
            lots, dividends, meta = load_flex_query(path)
            trades_count = len(lots)
            file_type = "flex_xml"
        else:
            trades, dividends, meta = load_activity_statement(path)
            trades_count = len(trades)
            file_type = "activity_csv"
        rows.append(
            {
                "file": path.name,
                "type": file_type,
                "account": _mask_account(meta.account_id),
                "base_currency": meta.base_currency,
                "period_start": meta.from_date,
                "period_end": meta.to_date,
                "trade_rows": trades_count,
                "dividend_rows": len(dividends),
            }
        )
    return rows


def _build_reconcile_input_files_table(file_summaries: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "file": row["file"],
                "type": row["type"],
                "account": row["account"],
                "base_currency": row["base_currency"],
                "period_start": _fmt_date(row["period_start"]),
                "period_end": _fmt_date(row["period_end"]),
                "trade_rows": row["trade_rows"],
                "dividend_rows": row["dividend_rows"],
            }
            for row in file_summaries
        ]
    )


def _build_reconcile_coverage_table(
    *,
    file_summaries: list[dict],
    trades: list,
    dividends: list[IbkrDividend],
    realized: list[RealizedGain],
    year_realized: list[RealizedGain],
    year_dividends: list[IbkrDividend],
    year_interest: list[FlexInterest],
    year: int,
    fx_table: pd.DataFrame,
) -> pd.DataFrame:
    starts = [row["period_start"] for row in file_summaries if row["period_start"] is not None]
    ends = [row["period_end"] for row in file_summaries if row["period_end"] is not None]
    coverage_start = min(starts) if starts else None
    coverage_end = max(ends) if ends else None
    covers_year = _periods_cover_year(file_summaries, year)
    missing_fx = _fx_status_count(fx_table, "missing")

    rows = [
        {"metric": "Tax year", "value": str(year)},
        {"metric": "Statement files", "value": str(len(file_summaries))},
        {"metric": "Coverage start", "value": _fmt_date(coverage_start)},
        {"metric": "Coverage end", "value": _fmt_date(coverage_end)},
        {"metric": "Full-year coverage", "value": "yes" if covers_year else "no"},
        {"metric": "Parsed trade rows", "value": str(len(trades))},
        {"metric": "Parsed dividend rows", "value": str(len(dividends))},
        {"metric": "Realized lot rows", "value": str(len(realized))},
        {"metric": f"Realized rows in {year}", "value": str(len(year_realized))},
        {"metric": f"Dividend rows in {year}", "value": str(len(year_dividends))},
        {"metric": f"Interest rows in {year}", "value": str(len(year_interest))},
        {"metric": "Missing FX pairs", "value": str(missing_fx)},
        {
            "metric": "Status",
            "value": "needs review" if (not covers_year or missing_fx > 0) else "reconciled",
        },
    ]
    return pd.DataFrame(rows)


def _build_realized_reconciliation_table(
    realized: list[RealizedGain],
    year: int,
) -> pd.DataFrame:
    complete = [r for r in realized if r.gain_eur is not None]
    proceeds = _sum_optional(r.proceeds_eur for r in realized)
    cost = _sum_optional(r.cost_basis_eur for r in realized)
    gains = [r.gain_eur for r in complete if r.gain_eur is not None and r.gain_eur > 0]
    losses = [r.gain_eur for r in complete if r.gain_eur is not None and r.gain_eur < 0]
    net_gain = _sum_optional(r.gain_eur for r in complete)
    missing_fx_rows = sum(1 for r in realized if r.needs_fx)
    taxable_gain = max(0.0, net_gain) if net_gain is not None else None
    net_cgt_due = taxable_gain * 0.25 if taxable_gain is not None else None

    return pd.DataFrame(
        [
            {"metric": "Tax year", "value": str(year)},
            {"metric": "Realized lot rows", "value": str(len(realized))},
            {"metric": "Symbols", "value": ", ".join(sorted({r.symbol for r in realized}))},
            {"metric": "Proceeds", "value": _fmt_eur(proceeds)},
            {"metric": "Cost basis", "value": _fmt_eur(cost)},
            {"metric": "Gross gains", "value": _fmt_eur(sum(gains) if gains else None)},
            {"metric": "Gross losses", "value": _fmt_signed_eur(sum(losses) if losses else None)},
            {"metric": "Net gain / loss", "value": _fmt_signed_eur(net_gain)},
            {"metric": "Taxable gain after same-year loss offset", "value": _fmt_eur(taxable_gain)},
            {"metric": "Estimated CGT due at 25%", "value": _fmt_eur(net_cgt_due)},
            {"metric": "Rows missing FX", "value": str(missing_fx_rows)},
        ]
    )


def _build_dividend_reconciliation_table(
    dividends: list[IbkrDividend],
    fx_rates: dict,
    year: int,
) -> pd.DataFrame:
    gross_total = 0.0
    wht_total = 0.0
    topup_total = 0.0
    missing_fx_rows = 0
    for d in dividends:
        eur_rate = _dividend_eur_rate(d, fx_rates)
        if eur_rate is None:
            missing_fx_rows += 1
            continue
        gross_eur = d.amount * eur_rate
        wht_eur = d.withholding_tax * eur_rate
        gross_total += gross_eur
        wht_total += wht_eur
        topup_total += si_dividend_tax(gross_eur, wht_eur)

    return pd.DataFrame(
        [
            {"metric": "Tax year", "value": str(year)},
            {"metric": "Dividend rows", "value": str(len(dividends))},
            {"metric": "Symbols", "value": ", ".join(sorted({d.symbol for d in dividends}))},
            {"metric": "Gross dividend income", "value": _fmt_eur(gross_total)},
            {"metric": "Foreign WHT already paid", "value": _fmt_eur(wht_total)},
            {"metric": "Additional SI dividend tax due", "value": _fmt_eur(topup_total)},
            {"metric": "Rows missing FX", "value": str(missing_fx_rows)},
        ]
    )


def _build_interest_reconciliation_table(
    interest: list[FlexInterest],
    fx_rates: dict,
    year: int,
) -> pd.DataFrame:
    gross_total = 0.0
    wht_total = 0.0
    topup_total = 0.0
    missing_fx_rows = 0
    for r in interest:
        eur_rate = _interest_eur_rate(r, fx_rates)
        if eur_rate is None:
            missing_fx_rows += 1
            continue
        gross_eur = r.amount * eur_rate
        wht_eur = r.withholding_tax * eur_rate
        gross_total += gross_eur
        wht_total += wht_eur
        topup_total += si_interest_tax(gross_eur, wht_eur)

    return pd.DataFrame(
        [
            {"metric": "Tax year", "value": str(year)},
            {"metric": "Interest rows", "value": str(len(interest))},
            {"metric": "Gross interest income", "value": _fmt_eur(gross_total)},
            {"metric": "Foreign WHT already paid", "value": _fmt_eur(wht_total)},
            {"metric": "Additional SI interest tax due", "value": _fmt_eur(topup_total)},
            {"metric": "Rows missing FX", "value": str(missing_fx_rows)},
        ]
    )


def _build_fx_coverage_table(
    *,
    trade_fx_pairs: list[tuple[str, date]],
    trade_fx_rates: dict | None,
    dividend_fx_pairs: list[tuple[str, date]],
    dividend_fx_rates: dict | None,
    interest_fx_pairs: list[tuple[str, date]],
    interest_fx_rates: dict | None,
    fx_auto: bool,
) -> pd.DataFrame:
    usage: dict[tuple[str, str], set[str]] = {}
    for currency, day in trade_fx_pairs:
        usage.setdefault((currency, day.isoformat()), set()).add("trades")
    for currency, day in dividend_fx_pairs:
        usage.setdefault((currency, day.isoformat()), set()).add("dividends")
    for currency, day in interest_fx_pairs:
        usage.setdefault((currency, day.isoformat()), set()).add("interest")

    rows = []
    for currency, day in sorted(usage):
        rate = None
        if trade_fx_rates:
            rate = trade_fx_rates.get((currency, day))
        if rate is None and dividend_fx_rates:
            rate = dividend_fx_rates.get((currency, day))
        if rate is None and interest_fx_rates:
            rate = interest_fx_rates.get((currency, day))
        if rate is not None:
            status = "available"
        elif fx_auto:
            status = "missing"
        else:
            status = "not fetched"
        rows.append(
            {
                "currency": currency,
                "date": day,
                "used_by": "+".join(sorted(usage[(currency, day)])),
                "eur_per_unit": f"{rate:.8f}" if rate is not None else "",
                "status": status,
            }
        )
    return pd.DataFrame(rows, columns=["currency", "date", "used_by", "eur_per_unit", "status"])


def _build_reconcile_warnings_table(
    *,
    coverage_table: pd.DataFrame,
    realized: list[RealizedGain],
    dividends: list[IbkrDividend],
    interest: list[FlexInterest],
    fx_table: pd.DataFrame,
    year: int,
) -> pd.DataFrame:
    warnings = []
    coverage = _coverage_value(coverage_table, "Full-year coverage")
    if coverage != "yes":
        warnings.append(
            {
                "severity": "review",
                "message": f"Input statements do not prove full calendar-year coverage for {year}.",
            }
        )
    missing_fx = _fx_status_count(fx_table, "missing")
    not_fetched_fx = _fx_status_count(fx_table, "not fetched")
    if missing_fx:
        warnings.append(
            {
                "severity": "review",
                "message": f"{missing_fx} non-EUR currency/date pair(s) are missing ECB FX rates.",
            }
        )
    if not_fetched_fx:
        warnings.append(
            {
                "severity": "info",
                "message": "FX auto-fetch was disabled; EUR tax totals are partial for non-EUR rows.",
            }
        )
    if not realized:
        warnings.append(
            {"severity": "info", "message": f"No realized sale lots were found for {year}."}
        )
    if not dividends:
        warnings.append(
            {"severity": "info", "message": f"No dividend rows were found for {year}."}
        )
    if not interest:
        warnings.append(
            {"severity": "info", "message": f"No broker interest rows were found for {year}."}
        )
    if not warnings:
        warnings.append(
            {
                "severity": "ok",
                "message": "No reconciliation warnings from parsed rows and FX coverage.",
            }
        )
    return pd.DataFrame(warnings)


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


def _maybe_fetch_dividend_fx(dividends: list[IbkrDividend], fx_auto: bool) -> dict:
    if not fx_auto:
        return {}
    pairs = _non_eur_dividend_currency_dates(dividends)
    if not pairs:
        return {}
    from valuation.portfolio.fx import EcbFxClient
    client = EcbFxClient()
    return client.build_fx_rates_dict(pairs)


def _maybe_fetch_interest_fx(interest: list[FlexInterest], fx_auto: bool) -> dict:
    if not fx_auto:
        return {}
    pairs = _non_eur_interest_currency_dates(interest)
    if not pairs:
        return {}
    from valuation.portfolio.fx import EcbFxClient
    client = EcbFxClient()
    return client.build_fx_rates_dict(pairs)


def _extract_flex_fees(
    paths: list[Path],
    year_gains: list[RealizedGain],
    fx_rates: dict | None,
) -> dict[int, tuple[float, float]]:
    """Return {year_gains_index: (buy_fee_eur, sell_fee_eur)} from Flex XML lots.

    Fees are in native currency; converted to EUR using fx_rates when available.
    Non-EUR lots without FX rate get 0.0 for both fees.
    """
    from collections import defaultdict

    all_lots = []
    for path in paths:
        if path.suffix.lower() == ".xml":
            lots, _, _ = load_flex_query(path)
            all_lots.extend(lots)

    # Build lookup: (symbol, acquired, sold) -> [(buy_comm, sell_comm, currency), ...]
    fee_by_key: dict = defaultdict(list)
    for lot in all_lots:
        fee_by_key[(lot.symbol, lot.acquired, lot.sold)].append(
            (lot.buy_commission, lot.sell_commission, lot.currency)
        )

    result: dict[int, tuple[float, float]] = {}
    counters: dict = defaultdict(int)
    for i, r in enumerate(year_gains):
        key = (r.symbol, r.acquired, r.sold)
        idx = counters[key]
        entries = fee_by_key.get(key, [])
        counters[key] += 1
        if idx >= len(entries):
            continue
        buy_comm, sell_comm, currency = entries[idx]
        if currency == "EUR":
            rate = 1.0
        else:
            rate = (fx_rates or {}).get((currency, r.acquired.isoformat())) if buy_comm else None
            sell_rate = (fx_rates or {}).get((currency, r.sold.isoformat())) if sell_comm else None
            buy_fee_eur = buy_comm * rate if rate is not None else 0.0
            sell_fee_eur = sell_comm * sell_rate if sell_rate is not None else 0.0
            result[i] = (buy_fee_eur, sell_fee_eur)
            continue
        result[i] = (buy_comm * rate, sell_comm * rate)

    return result


def _non_eur_dividend_currency_dates(dividends: list[IbkrDividend]) -> list[tuple[str, date]]:
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, date]] = []
    for dividend in dividends:
        if dividend.currency == "EUR":
            continue
        key = (dividend.currency, dividend.payment_date.isoformat())
        if key not in seen:
            seen.add(key)
            result.append((dividend.currency, dividend.payment_date))
    return result


def _non_eur_interest_currency_dates(interest: list[FlexInterest]) -> list[tuple[str, date]]:
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, date]] = []
    for row in interest:
        if row.currency == "EUR":
            continue
        key = (row.currency, row.payment_date.isoformat())
        if key not in seen:
            seen.add(key)
            result.append((row.currency, row.payment_date))
    return result


def _dividend_eur_rate(dividend: IbkrDividend, fx_rates: dict) -> float | None:
    if dividend.currency == "EUR":
        return 1.0
    return fx_rates.get((dividend.currency, dividend.payment_date.isoformat()))


def _interest_eur_rate(interest: FlexInterest, fx_rates: dict) -> float | None:
    if interest.currency == "EUR":
        return 1.0
    return fx_rates.get((interest.currency, interest.payment_date.isoformat()))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _resolve_statement_paths(file: str | None) -> list[Path]:
    """Resolve one or more statement paths from --file arg or env var.

    --file accepts comma-separated paths for combining multi-year exports.
    """
    raw = file or os.environ.get(_ENV_FLEX_PATH)
    if raw is None:
        print(
            f"Error: no IBKR Flex XML file specified. "
            f"Use --file <path>[,<path>...] or set {_ENV_FLEX_PATH} in .env.",
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


def _load_interest_from_flex_paths(paths: list[Path]) -> list[FlexInterest]:
    rows: list[FlexInterest] = []
    ignored_csv = []
    for path in sorted(paths):
        if path.suffix.lower() != ".xml":
            ignored_csv.append(path.name)
            continue
        rows.extend(parse_flex_interest(path))
    if ignored_csv:
        print(
            "Note: interest reporting uses Flex XML; ignored non-XML file(s): "
            + ", ".join(ignored_csv),
            file=sys.stderr,
        )
    return sorted(rows, key=lambda row: row.payment_date)


def _load_combined_statement(
    paths: list[Path],
    fx_auto: bool = True,
):
    """Load and merge trades/dividends from one or more statement files.

    Auto-detects format: .xml → Flex Query, .csv → Activity Statement.
    Deduplicates trades by (symbol, trade_date, quantity, price) so overlapping
    date ranges in adjacent year exports don't double-count.
    Returns (trades, dividends, meta) where meta is from the last file.
    """
    from valuation.portfolio.ibkr import IbkrTrade, IbkrDividend, IbkrStatementMeta

    all_trades: list[IbkrTrade] = []
    all_dividends: list[IbkrDividend] = []
    meta: IbkrStatementMeta | None = None

    for path in sorted(paths):
        if path.suffix.lower() == ".xml":
            trades, dividends, m = _load_flex_as_trades(path, fx_auto=fx_auto)
        else:
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
        meta = IbkrStatementMeta(base_currency="EUR", account_id="", from_date=None, to_date=None)

    return deduped_trades, deduped_divs, meta


def _load_flex_as_trades(path: Path, *, fx_auto: bool = True):
    """Load a Flex Query XML and return (trades, dividends, meta).

    The flex path uses IBKR's pre-computed FIFO <Lot> elements directly.
    Lots are converted to synthetic IbkrTrade pairs (one buy + one sell per lot)
    so the rest of the pipeline (FIFO engine, tax table) works unchanged.
    """
    from valuation.portfolio.ibkr import IbkrTrade, IbkrStatementMeta

    lots, dividends, meta = load_flex_query(path)

    trades: list[IbkrTrade] = []
    for lot in lots:
        # Synthetic buy: use cost_native as proceeds magnitude
        buy = IbkrTrade(
            symbol=lot.symbol,
            asset_category="Stocks",
            currency=lot.currency,
            trade_date=lot.acquired,
            quantity=lot.quantity,
            price=lot.cost_native / lot.quantity if lot.quantity > 0 else 0.0,
            proceeds=-lot.cost_native,  # buys have negative proceeds in IBKR convention
            commission=0.0,
            _sort_key=(lot.acquired, 0),
        )
        # Synthetic sell: proceeds = cost + pnl
        sell = IbkrTrade(
            symbol=lot.symbol,
            asset_category="Stocks",
            currency=lot.currency,
            trade_date=lot.sold,
            quantity=-lot.quantity,
            price=lot.proceeds_native / lot.quantity if lot.quantity > 0 else 0.0,
            proceeds=lot.proceeds_native,
            commission=0.0,
            _sort_key=(lot.sold, 1),
        )
        trades.append(buy)
        trades.append(sell)

    return trades, dividends, meta


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


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value is not None else ""


def _fmt_eur(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"€{value:,.2f}"


def _fmt_signed_eur(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"€{value:,.2f}"


def _fmt_signed_currency(value: float, currency: str) -> str:
    symbol = "€" if currency == "EUR" else ("$" if currency == "USD" else currency + " ")
    return f"{symbol}{value:,.2f}"


def _fmt_qty(qty: float) -> str:
    if qty == int(qty):
        return str(int(qty))
    return f"{qty:.4f}"


def _fmt_currency(value: float, currency: str) -> str:
    symbol = "€" if currency == "EUR" else ("$" if currency == "USD" else currency + " ")
    return f"{symbol}{value:,.2f}"


def _mask_account(account_id: str) -> str:
    if not account_id:
        return ""
    if len(account_id) <= 4:
        return "*" * len(account_id)
    return "*" * (len(account_id) - 4) + account_id[-4:]


def _periods_cover_year(file_summaries: list[dict], year: int) -> bool:
    intervals = sorted(
        (row["period_start"], row["period_end"])
        for row in file_summaries
        if row["period_start"] is not None and row["period_end"] is not None
    )
    if not intervals:
        return False

    cursor = date(year, 1, 1)
    year_end = date(year, 12, 31)
    for start, end in intervals:
        if end < cursor:
            continue
        if start > cursor:
            return False
        if end >= year_end:
            return True
        cursor = end + timedelta(days=1)
    return False


def _coverage_value(table: pd.DataFrame, metric: str) -> str | None:
    if table.empty:
        return None
    rows = table.loc[table["metric"] == metric, "value"]
    if rows.empty:
        return None
    return str(rows.iloc[0])


def _fx_status_count(table: pd.DataFrame, status: str) -> int:
    if table.empty or "status" not in table.columns:
        return 0
    return int((table["status"] == status).sum())


def _print_and_save(
    sections: list[tuple[str, pd.DataFrame]],
    *,
    outdir: str,
    output_format: str,
    slug: str,
    notes: dict[str, str] | None = None,
) -> None:
    import json

    from valuation.reports.tables import (
        frame_to_records,
        rename_for_display,
        render_terminal_table,
        write_csv,
        write_json,
        write_markdown,
    )

    out_path = Path(outdir) / slug

    if output_format == "json":
        bundle = {
            "sections": {
                title.lower().replace(" ", "_"): frame_to_records(rename_for_display(df))
                for title, df in sections
            }
        }
        print(json.dumps(bundle, indent=2))
        write_json(bundle, out_path / "bundle.json")
        return

    for title, df in sections:
        print(f"\n## {title}\n")
        if notes and title in notes:
            print(f"Note: {notes[title]}\n")
        print(render_terminal_table(df))

    out_path.mkdir(parents=True, exist_ok=True)
    for title, df in sections:
        name = title.lower().replace(" ", "_")
        write_csv(df, out_path / f"{name}.csv")
        write_markdown(df, out_path / f"{name}.md")

    print(f"\nWrote tables to {out_path}")


def _warn_needs_fx_realized(realized: list[RealizedGain]) -> None:
    non_eur = {r.symbol for r in realized if r.needs_fx}
    if non_eur:
        print(
            f"\nNote: EUR amounts incomplete for {', '.join(sorted(non_eur))}. "
            "ECB FX fetch failed or returned no data for these dates.",
            file=sys.stderr,
        )
