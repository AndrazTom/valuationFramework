"""Table rendering helpers."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import textwrap

import pandas as pd
from tabulate import tabulate

from valuation.utils.formatting import humanize_frame

DISPLAY_COLUMN_ALIASES = {
    "accession_number": "accession",
    "accepted_at": "accepted at",
    "as_of": "as of",
    "cash_and_equivalents_usd": "cash",
    "deferred_income_taxes_usd": "deferred taxes",
    "equity_method_investments_usd": "equity method",
    "equity_securities_usd": "equity securities",
    "coverage_ratio": "coverage",
    "earnings_before_income_taxes_usd": "pre-tax earnings",
    "expected_metric_count": "expected metrics",
    "filing_date": "filed",
    "filing_url": "filing url",
    "fixed_maturity_securities_usd": "fixed maturities",
    "form_group": "category",
    "goodwill_usd": "goodwill",
    "identifiable_assets_usd": "assets",
    "depreciation_and_amortization_usd": "depr & amort",
    "interest_expense_usd": "interest expense",
    "latest_price_date": "price date",
    "liquid_investments_total_usd": "cash/T-bills + fixed mat.",
    "live_value_delta_pct": "live delta %",
    "live_value_delta_usd": "live delta",
    "metric_count": "metrics",
    "net_liquid_investments_usd": "net incl fixed mat.",
    "notes_payable_and_other_borrowings_usd": "notes & borrowings",
    "payable_for_purchase_of_us_treasury_bills_usd": "T-bill payable",
    "period_count": "periods",
    "period_end": "as of",
    "price_change_pct": "price change",
    "per_brk_b_share_usd": "/BRK.B",
    "market_cap_weight": "% mkt cap",
    "share_of_market_cap_pct": "% mkt cap",
    "report_date": "report date",
    "security_id": "security id",
    "identifier_kind": "id kind",
    "query_used": "query",
    "short_term_us_treasury_bills_usd": "T-bills",
    # Segment history and implied allocation
    "revenues_usd": "revenues",
    "capex_usd": "capex",
    "after_tax_selected_13f_value_usd": "after-tax selected 13F",
    "estimated_tax_usd": "estimated tax",
    "pretax_earnings_usd": "pre-tax earnings",
    "owner_earnings_usd": "owner earnings",
    "pretax_share_pct": "% of total",
    "implied_value_usd": "implied value",
    "oe_multiple": "P/OE multiple",
    "implied_pe_multiple": "implied P/E",
    "implied_p_oe_multiple": "implied P/OE",
    # Book value and OpCo sensitivity
    "stockholders_equity_usd": "stockholders equity",
    "book_value_per_brk_b_usd": "BV/BRK.B",
    "implied_opco_value_usd": "implied opco value",
    "implied_total_value_usd": "implied total value",
    "implied_brk_b_price_usd": "implied BRK.B price",
    "vs_current_price_pct": "vs current price",
    "scenario": "scenario",
    "tax_as_pct_of_selected_13f": "tax / selected 13F",
    "tax_rate": "tax rate",
    "cagr_pct": "CAGR",
    "portfolio_weight": "weight",
    "portfolio_weight_live": "live weight",
}

DISPLAY_VALUE_ALIASES = {
    "operating_segment_pretax_earnings_usd": "segment pretax earnings",
    "residual_operating_and_other_usd": "residual opco + other",
    "residual_to_aftertax_earnings_multiple": "residual / after-tax earnings",
    "residual_market_cap_weight": "residual % mkt cap",
    "public_equity_holdings_blended": "selected 13F equities",
    "quoted_holdings_plus_net_cash": "13F + net cash/T-bills",
    "net_cash_and_treasury_bills": "net cash + T-bills",
    "fixed_maturity_securities_context": "fixed maturity (context)",
    "deferred_income_taxes_context": "deferred taxes (context)",
    "residual_operating_and_other": "residual opco + other",
    "deferred_income_taxes_usd": "deferred taxes",
    "equity_method_investments_usd": "equity method",
    "equity_securities_usd": "equity securities",
    "payable_for_purchase_of_us_treasury_bills": "T-bill payable",
    "notes_payable_and_other_borrowings": "notes & borrowings",
    "notes_payable_and_other_borrowings_usd": "notes & borrowings",
    "short_term_us_treasury_bills": "T-bills",
    "total_assets_usd": "total assets",
    "total_liabilities_usd": "total liabilities",
    "fixed_maturity_securities": "fixed maturities",
    "cash_and_equivalents": "cash",
    "13f_live_resolved_value_usd": "13F live resolved",
    "13f_reported_value_usd": "13F reported value",
    "13f_blended_value_usd": "13F blended value",
    "13f_live_coverage_pct": "13F live coverage",
    "13f_selected_basis": "13F basis",
    "13f_selected_value_usd": "13F selected value",
    "after_tax_selected_13f_value_usd": "after-tax selected 13F",
    "blended_13f_value_usd": "13F blended value",
    "brk_b_last_price": "BRK.B last price",
    "brk_b_price_change_pct": "BRK.B change",
    "holdings_minus_brk_b_change_pct": "holdings vs BRK.B",
    "live_price_coverage_pct": "live price coverage",
    "live_resolved_13f_value_usd": "live 13F value",
    "market_cap_usd": "market cap",
    "market_value_live_resolved_usd": "live resolved value",
    "net_core_liquidity_usd": "net cash + T-bills",
    "positions_without_live_price": "without live price",
    "price_brk_b": "BRK.B price",
    "reported_13f_value_usd": "13F reported value",
    "reported_value_resolved_usd": "reported resolved value",
    "resolved_holdings_weighted_change_pct": "holdings change",
    "residual_per_brk_b_usd": "residual / BRK.B",
    "implied_growth_at_10_pct": "implied growth @ 10%",
    "resolved_positions_count": "resolved positions",
    "resolved_positions_live_value_usd": "resolved live value",
    "resolved_positions_reported_value_usd": "resolved reported value",
    "segment_pretax_earnings_usd": "segment pre-tax earnings",
    "top_holdings_minus_brk_b_change_pct": "top holdings vs BRK.B",
    "top_holdings_reported_value_usd": "top holdings reported",
    "top_holdings_weighted_change_pct": "top holdings change",
    "unresolved_13f_value_reported_usd": "unresolved 13F reported",
    "zero_growth_value_per_brk_b_usd": "zero-growth value / BRK.B",
    "selected_13f_basis": "13F basis",
    "selected_13f_value_usd": "selected 13F value",
    "equity_valuation_basis": "equity basis",
    "equity_live_pricing_limit": "live pricing limit",
    "estimated_selected_13f_cost_basis_usd": "est. selected 13F cost",
    "estimated_selected_13f_unrealized_gain_usd": "est. selected 13F gain",
    "estimated_tax_usd": "estimated tax",
    "equity_note_cost_basis_usd": "equity note cost",
    "equity_note_fair_value_usd": "equity note fair value",
    "equity_note_unrealized_gain_ratio": "equity note gain %",
    "equity_note_unrealized_gain_usd": "equity note gain",
    "federal_corporate_tax_rate": "federal corporate tax rate",
    "investment_deferred_tax_liability_usd": "investment deferred tax",
    "latest_effective_tax_rate": "latest effective tax rate",
    "scaled_investment_deferred_tax_liability_usd": "scaled investment deferred tax",
    "state_local_rate_net_federal_benefit": "state/local tax rate",
    "tax_as_pct_of_selected_13f": "tax / selected 13F",
    "tax_rate": "tax rate",
}

TERMINAL_SECONDARY_COLUMNS = [
    "filing url",
    "primary document",
    "description",
    "is inline xbrl",
    "source table",
    "taxonomy",
    "concept",
    "matched label",
    "form",
    "filed",
    "accession",
    "report date",
    "accepted at",
    "reason",
    "expected metrics",
    "metrics",
    "as of",
    "period type",
    "cash/T-bills + fixed mat.",
    "goodwill",
    "assets",
    "interest expense",
]

TERMINAL_PERIOD_COLUMN_PATTERN = re.compile(r"^(FY \d{4}|\d{4} Q[1-4]|\d{4})$")


def render_terminal_table(frame: pd.DataFrame, *, max_width: int | None = None) -> str:
    if frame.empty:
        return "(no rows)"
    display = _prepare_display_frame(frame, target="terminal")
    width = max_width or _terminal_width()
    display = _fit_terminal_frame(display, max_width=width)
    if width > 0 and _rendered_width(display) > width:
        if _terminal_period_columns(display):
            return _tabulate_terminal_period_blocks(display, max_width=width)
        if len(display.columns) > 2:
            return _tabulate_terminal_column_blocks(display, max_width=width)
    return _tabulate_terminal(display)


def render_markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "(no rows)\n"
    display = _prepare_display_frame(frame, target="markdown")
    return display.fillna("").to_markdown(index=False) + "\n"


def write_csv(frame: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def write_markdown(frame: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_markdown_table(frame), encoding="utf-8")


def frame_to_records(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    records = []
    for row in frame.to_dict(orient="records"):
        records.append({str(key): _json_safe_value(value) for key, value in row.items()})
    return records


def write_json(data: object, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _prepare_display_frame(frame: pd.DataFrame, *, target: str) -> pd.DataFrame:
    display = humanize_frame(frame)
    # "unit" is a formatting-hint column; always drop it from any rendered output
    display = display.drop(columns=["unit"], errors="ignore")
    display = display.rename(columns={column: _display_column_name(str(column), target=target) for column in display.columns})
    for column in display.columns:
        if str(column).lower() in {"field", "metric"}:
            display[column] = [
                _humanize_label(value)
                for value in display[column]
            ]
        if target == "terminal":
            display[column] = [
                _wrap_terminal_cell(value, column=column)
                for value in display[column]
            ]
    return display


def _fit_terminal_frame(frame: pd.DataFrame, *, max_width: int | None) -> pd.DataFrame:
    width = max_width or _terminal_width()
    if width <= 0:
        return frame
    fitted = frame.copy()
    if _rendered_width(fitted) <= width:
        return fitted
    for column in TERMINAL_SECONDARY_COLUMNS:
        if column not in fitted.columns:
            continue
        if len(fitted.columns) <= 3:
            break
        candidate = fitted.drop(columns=[column])
        fitted = candidate
        if _rendered_width(fitted) <= width:
            return fitted
    return fitted


def _tabulate_terminal(frame: pd.DataFrame) -> str:
    return tabulate(frame.fillna(""), headers="keys", tablefmt="github", showindex=False)


def _tabulate_terminal_period_blocks(frame: pd.DataFrame, *, max_width: int) -> str:
    period_columns = _terminal_period_columns(frame)
    non_period_columns = [
        column
        for column in frame.columns
        if column not in period_columns
    ]
    chunks = _terminal_period_column_chunks(
        frame,
        non_period_columns=non_period_columns,
        period_columns=period_columns,
        max_width=max_width,
    )
    if len(chunks) <= 1:
        return _tabulate_terminal(frame)

    blocks = []
    for index, chunk in enumerate(chunks, start=1):
        columns = non_period_columns + chunk
        blocks.append(f"Period block {index}/{len(chunks)}")
        blocks.append(_tabulate_terminal(frame.loc[:, columns]))
    return "\n\n".join(blocks)


def _tabulate_terminal_column_blocks(frame: pd.DataFrame, *, max_width: int) -> str:
    """Split a wide non-period table into column blocks, repeating anchor columns in each block."""
    all_cols = list(frame.columns)
    # Use first 2 columns as anchors (ticker+name for comps, fiscal_year+end_date for ratios)
    anchor = all_cols[:2] if len(all_cols) > 2 else all_cols[:1]
    remaining = all_cols[len(anchor):]
    blocks: list[str] = []
    current: list[str] = []
    for col in remaining:
        candidate = frame[anchor + current + [col]]
        if current and _rendered_width(candidate) > max_width:
            blocks.append(_tabulate_terminal(frame[anchor + current]))
            current = [col]
        else:
            current.append(col)
    if current:
        blocks.append(_tabulate_terminal(frame[anchor + current]))
    if len(blocks) <= 1:
        return _tabulate_terminal(frame)
    return "\n\n".join(
        f"Column block {i + 1}/{len(blocks)}\n{b}" for i, b in enumerate(blocks)
    )


def _terminal_period_column_chunks(
    frame: pd.DataFrame,
    *,
    non_period_columns: list[object],
    period_columns: list[object],
    max_width: int,
) -> list[list[object]]:
    chunks: list[list[object]] = []
    current: list[object] = []
    for column in period_columns:
        candidate = current + [column]
        candidate_frame = frame.loc[:, non_period_columns + candidate]
        if current and _rendered_width(candidate_frame) > max_width:
            chunks.append(current)
            current = [column]
            continue
        current = candidate
    if current:
        chunks.append(current)
    return chunks


def _rendered_width(frame: pd.DataFrame) -> int:
    rendered = _tabulate_terminal(frame)
    return max((len(line) for line in rendered.splitlines()), default=0)


def _terminal_width() -> int:
    return shutil.get_terminal_size(fallback=(120, 24)).columns


def _terminal_period_columns(frame: pd.DataFrame) -> list[object]:
    return [
        column
        for column in frame.columns
        if _is_terminal_period_column(column)
    ]


def _is_terminal_period_column(column: object) -> bool:
    return bool(TERMINAL_PERIOD_COLUMN_PATTERN.match(str(column)))


def _display_column_name(column: str, *, target: str) -> str:
    return DISPLAY_COLUMN_ALIASES.get(column, column.replace("_usd", "").replace("_", " "))


def _wrap_terminal_cell(value, *, column: str):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    column_name = str(column).lower()
    width = 24
    if column_name in {"value", "segment", "note", "method", "context note"}:
        width = 26
    elif column_name in {"field", "metric"}:
        width = 26
    elif column_name in {"name", "issuer", "top holding"}:
        width = 36
    elif column_name in {"concept", "primary document", "description", "filing url", "reason", "website"}:
        width = 30
    elif column_name == "accession":
        width = 24
    if len(text) <= width or "\n" in text:
        return text
    return textwrap.fill(text, width=width, break_long_words=False)


def _humanize_label(value):
    if value is None:
        return value
    raw = str(value).strip()
    text = (
        DISPLAY_VALUE_ALIASES.get(raw)
        or DISPLAY_VALUE_ALIASES.get(raw.replace(" ", "_"))
        or raw
    ).replace("_", " ").strip()
    return text


def _json_safe_value(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            return value
    return value
