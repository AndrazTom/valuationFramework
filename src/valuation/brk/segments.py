"""Berkshire segment extraction from SEC filing report tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from valuation.notation import MILLION

SEGMENT_REPORT_LABELS = {
    "earnings": "Business segment data - Earnings data (Detail)",
    "reconciliations": "Business segment data - Reconciliations of Revenues and Earnings before income taxes (Detail)",
    "additional": "Business segment data - Additional tabular disclosures (Detail)",
}

TOP_LEVEL_OPERATING_METRICS = (
    "Revenues",
    "Earnings before income taxes",
    "Interest expense",
    "Capital expenditures",
    "Depreciation and amortization",
    "Goodwill at year-end",
    "Identifiable assets at year-end",
)

SEGMENT_LABEL_ALIASES = {
    "Business Segments": "Operating Businesses",
    'Berkshire Hathaway Energy ("BHE")': "BHE",
    "Manufacturing Businesses": "Manufacturing",
}


@dataclass(frozen=True)
class BrkSegmentReportSet:
    """Normalized Berkshire segment tables from one filing."""

    filing_date: str
    accession_number: str
    earnings_detail: pd.DataFrame
    reconciliation_detail: pd.DataFrame
    additional_detail: pd.DataFrame


def normalize_segment_report_table(
    frame: pd.DataFrame,
    *,
    report_name: str,
    scale_multiplier: int = MILLION,
) -> pd.DataFrame:
    """Normalize a Berkshire SEC report table into long, typed rows."""
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "report",
                "member_path",
                "member_name",
                "metric",
                "period_end",
                "value",
            ]
        )

    flat = frame.copy()
    flat.columns = [_flatten_column_name(column) for column in flat.columns]
    label_column = flat.columns[0]
    value_columns = [
        column
        for column in flat.columns[1:]
        if "Dec." in column or "20" in column
    ]

    rows = []
    current_member_path: Optional[str] = None
    for _, row in flat.iterrows():
        label = _normalize_text(row[label_column])
        if not label:
            continue
        if "[Member]" in label:
            current_member_path = _clean_member_path(label)
            continue
        if _should_skip_metric_row(label):
            continue
        if current_member_path is None:
            continue

        member_name = current_member_path.split(" | ")[-1]
        for column in value_columns:
            period_end = _extract_period_end(column)
            parsed_value = _parse_report_value(row[column], scale_multiplier=scale_multiplier)
            if period_end is None or parsed_value is None:
                continue
            rows.append(
                {
                    "report": report_name,
                    "member_path": current_member_path,
                    "member_name": member_name,
                    "metric": label,
                    "period_end": period_end,
                    "value": parsed_value,
                }
            )
    return pd.DataFrame(rows)


def build_top_level_operating_segments_table(report_set: BrkSegmentReportSet) -> pd.DataFrame:
    """Return a practical Berkshire segment table for current-year operating analysis."""
    period_end = _latest_period_end(report_set.earnings_detail, report_set.additional_detail)
    if period_end is None:
        return pd.DataFrame()
    earnings = _select_top_level_period_rows(report_set.earnings_detail, period_end=period_end)
    additional = _select_top_level_period_rows(report_set.additional_detail, period_end=period_end)
    combined = pd.concat([earnings, additional], ignore_index=True)
    if combined.empty:
        return pd.DataFrame()

    combined = combined[combined["metric"].isin(TOP_LEVEL_OPERATING_METRICS)]
    pivoted = (
        combined.pivot_table(
            index=["member_path", "member_name"],
            columns="metric",
            values="value",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(columns=None)
    )
    rename_map = {
        "Revenues": "revenues_usd",
        "Earnings before income taxes": "earnings_before_income_taxes_usd",
        "Interest expense": "interest_expense_usd",
        "Capital expenditures": "capex_usd",
        "Depreciation and amortization": "depreciation_and_amortization_usd",
        "Goodwill at year-end": "goodwill_usd",
        "Identifiable assets at year-end": "identifiable_assets_usd",
    }
    result = pivoted.rename(columns=rename_map)
    if "member_path" in result.columns:
        result = result.drop(columns=["member_path"])
    result = result.rename(columns={"member_name": "segment"})
    return result.sort_values(by="revenues_usd", ascending=False, na_position="last").reset_index(drop=True)


def _select_top_level_period_rows(frame: pd.DataFrame, *, period_end: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    filtered = frame[frame["period_end"] == period_end].copy()
    filtered = filtered[
        filtered["member_path"].apply(_is_top_level_operating_path)
    ]
    return filtered.reset_index(drop=True)


def _latest_period_end(*frames: pd.DataFrame) -> Optional[str]:
    period_ends = []
    for frame in frames:
        if frame.empty or "period_end" not in frame.columns:
            continue
        period_ends.extend([value for value in frame["period_end"].dropna().tolist() if value])
    if not period_ends:
        return None
    return max(period_ends)


def _is_top_level_operating_path(path: object) -> bool:
    if path is None or pd.isna(path):
        return False
    text = str(path)
    if not text.startswith("Operating Businesses | "):
        return False
    return text.count(" | ") == 1


def _flatten_column_name(column: object) -> str:
    if isinstance(column, tuple):
        parts = [str(part).strip() for part in column if str(part).strip() and str(part) != "nan"]
        return " ".join(parts)
    return str(column).strip()


def _normalize_text(value: object) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace("\xa0", " ").strip()
    return text or None


def _clean_member_path(text: str) -> str:
    parts = [part.strip() for part in text.split("|")]
    cleaned_parts = []
    for part in parts:
        cleaned = part.replace("[Member]", "").strip()
        cleaned = SEGMENT_LABEL_ALIASES.get(cleaned, cleaned)
        if cleaned:
            cleaned_parts.append(cleaned)
    return " | ".join(cleaned_parts)


def _should_skip_metric_row(label: str) -> bool:
    return label in {
        "Segment Reporting Information [Line Items]",
        "Costs and Expenses:",
    }


def _extract_period_end(column_name: str) -> Optional[str]:
    if "2025" in column_name:
        return "2025-12-31"
    if "2024" in column_name:
        return "2024-12-31"
    if "2023" in column_name:
        return "2023-12-31"
    return None


def _parse_report_value(value: object, *, scale_multiplier: int) -> Optional[float]:
    text = _normalize_text(value)
    if text is None:
        return None
    if text.endswith("%"):
        return None
    cleaned = (
        text.replace("$", "")
        .replace(",", "")
        .replace("[1]", "")
        .replace("[2]", "")
        .strip()
    )
    if cleaned in {"", "NaN", "nan"}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.replace("(", "").replace(")", "").strip()
    try:
        numeric = float(cleaned)
    except ValueError:
        return None
    if negative:
        numeric *= -1
    return numeric * scale_multiplier
