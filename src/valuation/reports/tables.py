"""Table rendering helpers."""

from __future__ import annotations

import json
from pathlib import Path
import textwrap

import pandas as pd
from tabulate import tabulate

from valuation.utils.formatting import humanize_frame

DISPLAY_COLUMN_ALIASES = {
    "accession_number": "accession",
    "accepted_at": "accepted at",
    "as_of": "as of",
    "coverage_ratio": "coverage",
    "earnings_before_income_taxes_usd": "pre-tax earnings",
    "expected_metric_count": "expected metrics",
    "filing_url": "filing url",
    "form_group": "category",
    "goodwill_usd": "goodwill",
    "identifiable_assets_usd": "assets",
    "depreciation_and_amortization_usd": "depr & amort",
    "interest_expense_usd": "interest expense",
    "latest_price_date": "price date",
    "metric_count": "metrics",
    "period_count": "periods",
    "report_date": "report date",
    "security_id": "security id",
    "identifier_kind": "id kind",
    "query_used": "query",
}


def render_terminal_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "(no rows)"
    display = _prepare_display_frame(frame, target="terminal")
    return tabulate(display.fillna(""), headers="keys", tablefmt="github", showindex=False)


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
    display = display.rename(columns={column: _display_column_name(str(column), target=target) for column in display.columns})
    for column in display.columns:
        if target == "terminal":
            display[column] = [
                _wrap_terminal_cell(value, column=column)
                for value in display[column]
            ]
        if str(column).lower() in {"field", "metric"}:
            display[column] = [
                _humanize_label(value)
                for value in display[column]
            ]
    return display


def _display_column_name(column: str, *, target: str) -> str:
    return DISPLAY_COLUMN_ALIASES.get(column, column.replace("_usd", "").replace("_", " "))


def _wrap_terminal_cell(value, *, column: str):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    column_name = str(column).lower()
    width = 24
    if column_name in {"value", "segment"}:
        width = 30
    elif column_name in {"field", "metric"}:
        width = 24
    elif column_name in {"concept", "primary document", "description", "filing url", "reason", "website"}:
        width = 36
    elif column_name == "accession":
        width = 24
    if len(text) <= width or "\n" in text:
        return text
    return textwrap.fill(text, width=width, break_long_words=False)


def _humanize_label(value):
    if value is None:
        return value
    text = str(value).replace("_", " ").strip()
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
