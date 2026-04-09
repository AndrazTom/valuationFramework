"""Human-readable formatting for valuation tables."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from valuation.utils.scale import BILLION, MILLION, THOUSAND, TRILLION


def humanize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a display-friendly copy of a table while keeping raw data untouched."""
    if frame.empty:
        return frame.copy()

    display = frame.copy()
    for column in display.columns:
        display[column] = [
            _format_value_for_display(
                value=row[column],
                column=column,
                row=row,
            )
            for _, row in display.iterrows()
        ]
    return display


def format_currency(value: Any) -> Any:
    """Format a numeric value using valuation-friendly currency notation."""
    if not _is_number(value):
        return value
    return _format_scaled(value, prefix="$")


def format_quantity(value: Any) -> Any:
    """Format a numeric quantity such as shares or counts."""
    if not _is_number(value):
        return value
    return _format_quantity_scaled(value)


def format_percent(value: Any) -> Any:
    """Format percentages from 0-1 decimal values."""
    if not _is_number(value):
        return value
    return f"{float(value) * 100:.1f}%"


def _format_value_for_display(value: Any, column: str, row: pd.Series) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    kind = _infer_format_kind(column=column, row=row)
    if kind == "currency":
        return format_currency(value)
    if kind == "percent":
        return format_percent(value)
    if kind == "quantity":
        return format_quantity(value)
    return value


def _infer_format_kind(column: str, row: pd.Series) -> Optional[str]:
    column_name = column.lower()
    if column_name in {"portfolio_weight"} or "weight" in column_name:
        return "percent"
    if column_name.endswith("_usd") or column_name in {
        "last_price",
        "previous_close",
        "open",
        "day_high",
        "day_low",
        "market_cap",
        "fifty_day_average",
        "two_hundred_day_average",
    }:
        return "currency"
    if column_name in {
        "shares",
        "shares_or_principal",
        "holding_count",
        "voting_sole",
        "voting_shared",
        "voting_none",
    }:
        return "quantity"
    if column_name == "value" and "field" in row:
        return _infer_kind_from_field(str(row["field"]).lower())
    if column_name == "value" and "metric" in row:
        return _infer_kind_from_field(str(row["metric"]).lower())
    return None


def _infer_kind_from_field(field_name: str) -> Optional[str]:
    if "weight" in field_name:
        return "percent"
    if any(
        token in field_name
        for token in (
            "price",
            "open",
            "high",
            "low",
            "average",
            "cash",
            "asset",
            "liabil",
            "equity",
            "revenue",
            "income",
            "capex",
            "value",
            "market_cap",
        )
    ):
        return "currency"
    if any(token in field_name for token in ("share", "count")):
        return "quantity"
    return None


def _format_scaled(value: Any, prefix: str = "") -> str:
    numeric = float(value)
    negative = numeric < 0
    absolute = abs(numeric)

    if absolute >= TRILLION:
        rendered = f"{absolute / TRILLION:.2f}T"
    elif absolute >= BILLION:
        rendered = f"{absolute / BILLION:.2f}B"
    elif absolute >= MILLION:
        rendered = f"{absolute / MILLION:.2f}M"
    elif absolute >= THOUSAND:
        rendered = f"{absolute / THOUSAND:.2f}K"
    elif float(absolute).is_integer():
        rendered = f"{absolute:,.0f}"
    else:
        rendered = f"{absolute:,.2f}"

    rendered = rendered.rstrip("0").rstrip(".")
    if negative:
        return f"-{prefix}{rendered}"
    return f"{prefix}{rendered}"


def _format_quantity_scaled(value: Any) -> str:
    numeric = float(value)
    negative = numeric < 0
    absolute = abs(numeric)

    if absolute >= TRILLION:
        rendered = f"{absolute / TRILLION:.2f}T"
    elif absolute >= BILLION:
        rendered = f"{absolute / BILLION:.2f}B"
    elif absolute >= MILLION:
        rendered = f"{absolute / MILLION:.2f}M"
    elif float(absolute).is_integer():
        rendered = f"{absolute:,.0f}"
    else:
        rendered = f"{absolute:,.2f}"

    rendered = rendered.rstrip("0").rstrip(".")
    if negative:
        return f"-{rendered}"
    return rendered


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
