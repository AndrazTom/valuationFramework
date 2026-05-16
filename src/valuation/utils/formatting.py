"""Human-readable formatting for valuation tables."""

from __future__ import annotations

from numbers import Real
from typing import Any, Optional

import pandas as pd

from valuation.notation import format_scaled_currency, format_scaled_number


def humanize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a display-friendly copy of a table while keeping raw data untouched."""
    if frame.empty:
        return frame.copy()

    source = frame.copy()
    display = source.copy()
    table_currency = _frame_currency_hint(source)
    for column in display.columns:
        display[column] = [
            _format_value_for_display(
                value=row[column],
                column=column,
                row=row,
                table_currency=table_currency,
            )
            for _, row in source.iterrows()
        ]
    return display


def format_currency(value: Any, *, currency: str = "USD") -> Any:
    """Format a numeric value using valuation-friendly currency notation."""
    return format_scaled_currency(value, currency=currency)


def format_quantity(value: Any) -> Any:
    """Format a numeric quantity such as shares or counts."""
    return format_scaled_number(value)


def format_percent(value: Any) -> Any:
    """Format percentages from 0-1 decimal values."""
    if not _is_number(value):
        return value
    return f"{float(value) * 100:.1f}%"


def _format_value_for_display(value: Any, column: str, row: pd.Series, table_currency: str | None) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if column.lower() in {"field", "metric"} and isinstance(value, str):
        return value.replace("_", " ")
    kind = _infer_format_kind(column=column, row=row)
    if kind == "currency":
        return format_currency(value, currency=_row_currency(row, table_currency=table_currency))
    if kind == "percent":
        return format_percent(value)
    if kind == "quantity":
        return format_quantity(value)
    if kind == "multiple":
        return f"{float(value):.1f}x" if _is_number(value) else value
    return value


def _infer_format_kind(column: str, row: pd.Series) -> Optional[str]:
    column_name = column.lower()
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
    if column_name in {"coverage_ratio"} or column_name.endswith("_pct"):
        return "percent"
    if column_name in {"portfolio_weight"} or "weight" in column_name:
        return "percent"
    if column_name in {
        "shares",
        "shares_or_principal",
        "holding_count",
        "voting_sole",
        "voting_shared",
        "voting_none",
    } or "share" in column_name:
        return "quantity"
    if "metric" in row and column_name not in {"metric", "unit"}:
        return _infer_kind_from_field(str(row["metric"]).lower())
    if column_name == "value" and "field" in row:
        return _infer_kind_from_field(str(row["field"]).lower())
    if column_name == "value" and "metric" in row:
        return _infer_kind_from_field(str(row["metric"]).lower())
    return None


def _infer_kind_from_field(field_name: str) -> Optional[str]:
    normalized_field = field_name.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized_field.endswith("_pct") or normalized_field.endswith("_ratio"):
        return "percent"
    if normalized_field.endswith("_multiple"):
        return "multiple"
    if normalized_field.endswith("_usd"):
        return "currency"
    if "weight" in normalized_field:
        return "percent"
    if any(token in normalized_field for token in ("share", "count", "position")):
        return "quantity"
    if any(
        token in normalized_field
        for token in (
            "price",
            "open",
            "high",
            "low",
            "average",
            "debt",
            "liquidity",
            "cash",
            "investment",
            "asset",
            "liabil",
            "equity",
            "revenue",
            "profit",
            "income",
            "eps",
            "capex",
            "value",
            "market_cap",
        )
    ):
        return "currency"
    return None


def _row_currency(row: pd.Series, *, table_currency: str | None) -> str:
    unit = str(row.get("unit") or "").upper()
    if unit.endswith("/SHARES"):
        unit = unit.removesuffix("/SHARES")
    if unit and unit != "SHARES":
        return unit
    if table_currency:
        return table_currency
    return "USD"


def _frame_currency_hint(frame: pd.DataFrame) -> str | None:
    if "field" not in frame.columns or "value" not in frame.columns:
        return None
    currency_rows = frame[frame["field"] == "currency"]
    if currency_rows.empty:
        return None
    value = currency_rows.iloc[0]["value"]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value).upper()


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)
