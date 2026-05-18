"""Berkshire segment extraction from SEC filing report tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
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
    "Total revenues",
    "Earnings before income taxes",
    "Earnings (loss) before income taxes",
    "Earnings (Loss) Before Income Taxes of Operating Businesses",
    "Interest expense",
    "Capital expenditures",
    "Depreciation and amortization",
    "Depreciation of tangible assets",
    "Goodwill at year-end",
    "Goodwill",
    "Identifiable assets at year-end",
    "Assets",
)

TOP_LEVEL_OPERATING_MEMBER_NAMES = {
    "BNSF",
    "BHE",
    "Manufacturing",
    "Service and Retailing",
    "Pilot",
    "McLane",
    "Insurance Group",
}

FLOW_METRIC_RENAMES = {
    "Revenues": "revenues_usd",
    "Total revenues": "revenues_usd",
    "Earnings before income taxes": "earnings_before_income_taxes_usd",
    "Earnings (loss) before income taxes": "earnings_before_income_taxes_usd",
    "Earnings (Loss) Before Income Taxes of Operating Businesses": "earnings_before_income_taxes_usd",
    "Interest expense": "interest_expense_usd",
    "Capital expenditures": "capex_usd",
    "Depreciation and amortization": "depreciation_and_amortization_usd",
    "Depreciation of tangible assets": "depreciation_and_amortization_usd",
}

STOCK_METRIC_RENAMES = {
    "Goodwill at year-end": "goodwill_usd",
    "Goodwill": "goodwill_usd",
    "Identifiable assets at year-end": "identifiable_assets_usd",
    "Assets": "identifiable_assets_usd",
}

SEGMENT_LABEL_ALIASES = {
    "Business Segments": "Operating Businesses",
    'Berkshire Hathaway Energy ("BHE")': "BHE",
    "Berkshire Hathaway Energy": "BHE",
    "Manufacturing Businesses": "Manufacturing",
    'Pilot Travel Centers ("PTC")': "Pilot",
    'Pilot Travel Centers ("Pilot")': "Pilot",
    "PTC": "Pilot",
    "McLane Company": "McLane",
    "Service and Retailing Businesses": "Service and Retailing",
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
                "column_label",
                "duration_label",
                "duration_months",
                "period_end",
                "value",
            ]
        )

    flat = frame.copy()
    flat.columns = [_flatten_column_name(column) for column in flat.columns]
    value_column_positions = [
        index
        for index, column in enumerate(flat.columns[1:], start=1)
        if "Dec." in column or "20" in column or "Sep." in column or "Jun." in column or "Mar." in column
    ]

    rows = []
    current_member_path: Optional[str] = None
    for row_index in range(len(flat)):
        label = _normalize_text(flat.iat[row_index, 0])
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
        for column_index in value_column_positions:
            column = flat.columns[column_index]
            period = _extract_period_metadata(column)
            parsed_value = _parse_report_value(
                flat.iat[row_index, column_index],
                scale_multiplier=scale_multiplier,
            )
            if period is None or parsed_value is None:
                continue
            rows.append(
                {
                    "report": report_name,
                    "member_path": current_member_path,
                    "member_name": member_name,
                    "metric": label,
                    "column_label": period["column_label"],
                    "duration_label": period["duration_label"],
                    "duration_months": period["duration_months"],
                    "period_end": period["period_end"],
                    "value": parsed_value,
                }
            )
    return pd.DataFrame(rows)


def build_top_level_operating_segments_table(
    report_set: BrkSegmentReportSet,
    *,
    period: str = "annual",
) -> pd.DataFrame:
    """Return Berkshire top-level segments for annual or quarterly reporting periods."""
    flow_duration_months = _flow_duration_months(period)
    period_end = _latest_period_end(
        report_set.earnings_detail,
        duration_months=flow_duration_months,
    )
    if period_end is None:
        return pd.DataFrame()
    flow_rows = pd.concat(
        [
            _select_top_level_period_rows(
                report_set.earnings_detail,
                period_end=period_end,
                duration_months=flow_duration_months,
            ),
            _select_top_level_period_rows(
                report_set.additional_detail,
                period_end=period_end,
                duration_months=flow_duration_months,
            ),
        ],
        ignore_index=True,
    )
    stock_rows = _select_top_level_period_rows(
        report_set.additional_detail,
        period_end=period_end,
    )
    combined = pd.concat([flow_rows, stock_rows], ignore_index=True)
    if combined.empty:
        return pd.DataFrame()

    combined = combined[combined["metric"].isin(TOP_LEVEL_OPERATING_METRICS)].copy()
    combined["canonical_metric"] = combined["metric"].map(
        {
            **FLOW_METRIC_RENAMES,
            **STOCK_METRIC_RENAMES,
        }
    )
    combined["segment"] = combined["member_name"].map(
        lambda value: SEGMENT_LABEL_ALIASES.get(value, value)
    )
    combined = combined[combined["canonical_metric"].notna()]
    combined = combined.drop_duplicates(
        subset=["segment", "canonical_metric", "period_end"],
        keep="first",
    )
    pivoted = (
        combined.pivot_table(
            index=["segment"],
            columns="canonical_metric",
            values="value",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(columns=None)
    )
    result = pivoted
    result.insert(0, "period_type", period)
    result.insert(0, "period_end", period_end)
    sort_column = "revenues_usd" if "revenues_usd" in result.columns else "segment"
    ascending = sort_column != "revenues_usd"
    return result.sort_values(by=sort_column, ascending=ascending, na_position="last").reset_index(drop=True)


def _select_top_level_period_rows(
    frame: pd.DataFrame,
    *,
    period_end: str,
    duration_months: int | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    filtered = frame[frame["period_end"] == period_end].copy()
    if duration_months is not None and "duration_months" in filtered.columns:
        filtered = filtered[filtered["duration_months"] == duration_months]
    filtered = filtered[
        filtered["member_path"].apply(_is_top_level_operating_path)
    ]
    return filtered.reset_index(drop=True)


def _latest_period_end(
    frame: pd.DataFrame,
    *,
    duration_months: int | None = None,
) -> Optional[str]:
    if frame.empty or "period_end" not in frame.columns:
        return None
    working = frame
    if duration_months is not None and "duration_months" in working.columns:
        working = working[working["duration_months"] == duration_months]
    period_ends = []
    period_ends.extend([value for value in working["period_end"].dropna().tolist() if value])
    if not period_ends:
        return None
    return max(period_ends)


def _is_top_level_operating_path(path: object) -> bool:
    if path is None or pd.isna(path):
        return False
    text = str(path)
    if text in TOP_LEVEL_OPERATING_MEMBER_NAMES:
        return True
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


def _extract_period_metadata(column_name: str) -> Optional[dict[str, object]]:
    date_match = re.search(r"([A-Z][a-z]{2}\.?\s+\d{1,2},\s+\d{4})", column_name)
    if date_match is None:
        return None
    period_end = _parse_date(date_match.group(1))
    if period_end is None:
        return None
    duration_match = re.search(r"(\d+)\s+Months?\s+Ended", column_name)
    duration_label = duration_match.group(0) if duration_match else None
    duration_months = int(duration_match.group(1)) if duration_match else None
    return {
        "column_label": column_name,
        "duration_label": duration_label,
        "duration_months": duration_months,
        "period_end": period_end,
    }


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


def _parse_date(value: str) -> Optional[str]:
    cleaned = value.replace(".", "")
    try:
        return datetime.strptime(cleaned, "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def _flow_duration_months(period: str) -> int:
    if period == "annual":
        return 12
    if period == "quarterly":
        return 3
    raise ValueError(f"Unsupported Berkshire segment period: {period}")
