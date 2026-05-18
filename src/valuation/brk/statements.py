"""Berkshire-specific statement fallbacks from SEC filing report tables."""

from __future__ import annotations

import math
import re
from typing import Mapping, Sequence

import pandas as pd

from valuation.brk.service import BRK_B_TICKER, find_recent_filings
from valuation.data.providers.sec import SecClient, SecCompany

EARNINGS_REPORT_SHORT_NAME = "Consolidated Statements of Earnings"
BRK_EPS_SHARE_METRICS = ("diluted_eps", "diluted_shares")

_MONTH_TO_QUARTER = {
    "Mar": 1,
    "Jun": 2,
    "Sep": 3,
    "Dec": 4,
}


def supplement_brk_income_statement_eps_shares(
    statement_table: pd.DataFrame,
    *,
    sec_client: SecClient,
    company: SecCompany | None,
    submissions: Mapping[str, object] | None,
    period: str,
) -> pd.DataFrame:
    """Fill BRK Class B EPS/share rows from filing report tables when companyfacts lacks them."""
    if company is None or company.ticker.upper() != BRK_B_TICKER:
        return statement_table
    if period not in {"annual", "quarterly"}:
        return statement_table
    if submissions is None:
        submissions = sec_client.fetch_submissions(company.cik)

    target_periods = _period_columns(statement_table)
    if not target_periods:
        return statement_table

    fallback = build_brk_eps_share_fallback_table(
        sec_client=sec_client,
        company=company,
        submissions=submissions,
        period=period,
        target_periods=target_periods,
    )
    return merge_brk_eps_share_rows(statement_table, fallback)


def build_brk_eps_share_fallback_table(
    *,
    sec_client: SecClient,
    company: SecCompany,
    submissions: Mapping[str, object],
    period: str,
    target_periods: Sequence[str],
) -> pd.DataFrame:
    """Return Class B EPS/share rows parsed from Berkshire earnings filing tables."""
    target_periods = [str(period) for period in target_periods]
    if not target_periods:
        return _empty_fallback_frame(target_periods)

    forms = ("10-K",) if period == "annual" else ("10-Q",)
    filing_limit = _filing_fetch_limit(period=period, target_periods=target_periods)
    try:
        filings = find_recent_filings(submissions, forms=forms, limit=filing_limit)
    except LookupError:
        return _empty_fallback_frame(target_periods)

    values = {
        "diluted_eps": {period_label: None for period_label in target_periods},
        "diluted_shares": {period_label: None for period_label in target_periods},
    }
    remaining = set(target_periods)
    for filing in filings:
        if not remaining:
            break
        try:
            reports = sec_client.fetch_filing_summary_reports(company.cik, filing["accession_number"])
            report = next(
                report
                for report in reports
                if report.short_name == EARNINGS_REPORT_SHORT_NAME
            )
        except (LookupError, StopIteration, KeyError):
            continue

        frame = sec_client.fetch_report_table(company.cik, filing["accession_number"], report.html_file_name)
        parsed = _extract_class_b_eps_share_values(frame, period=period)
        for metric in BRK_EPS_SHARE_METRICS:
            for period_label, value in parsed.get(metric, {}).items():
                if period_label in remaining and values[metric][period_label] is None:
                    values[metric][period_label] = value
        remaining = {
            period_label
            for period_label in remaining
            if any(values[metric][period_label] is None for metric in BRK_EPS_SHARE_METRICS)
        }

    rows = [
        {"metric": "diluted_eps", "unit": "USD/shares", **values["diluted_eps"]},
        {"metric": "diluted_shares", "unit": "shares", **values["diluted_shares"]},
    ]
    frame = pd.DataFrame(rows, columns=["metric", "unit", *target_periods])
    return frame if _has_any_period_value(frame) else _empty_fallback_frame(target_periods)


def merge_brk_eps_share_rows(statement_table: pd.DataFrame, fallback_table: pd.DataFrame) -> pd.DataFrame:
    """Overlay fallback EPS/share values onto an existing statement table."""
    if statement_table.empty or fallback_table.empty:
        return statement_table

    result = statement_table.copy()
    period_columns = _period_columns(result)
    fallback_by_metric = {
        str(row["metric"]): row
        for _, row in fallback_table.iterrows()
        if str(row.get("metric")) in BRK_EPS_SHARE_METRICS
    }
    if not fallback_by_metric:
        return result

    for metric, fallback_row in fallback_by_metric.items():
        existing = result.index[result["metric"] == metric].tolist()
        if existing:
            index = existing[0]
            if "unit" in result.columns and pd.isna(result.at[index, "unit"]):
                result.at[index, "unit"] = fallback_row.get("unit")
            for column in period_columns:
                value = fallback_row.get(column)
                if column in result.columns and pd.isna(result.at[index, column]) and not pd.isna(value):
                    result.at[index, column] = value
            continue
        row = {"metric": metric, "unit": fallback_row.get("unit")}
        row.update({column: fallback_row.get(column) for column in period_columns})
        result = _insert_statement_row(result, row)

    return result.reset_index(drop=True)


def _extract_class_b_eps_share_values(frame: pd.DataFrame, *, period: str) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {"diluted_eps": {}, "diluted_shares": {}}
    if frame.empty:
        return values

    period_columns = [
        column
        for column in frame.columns
        if _period_label_from_column(column, period=period) is not None
    ]
    in_class_b_section = False
    for _, row in frame.iterrows():
        label = _label_from_row(row)
        if not label:
            continue
        if "Equivalent Class B [Member]" in label:
            in_class_b_section = True
            continue
        if in_class_b_section and label.endswith("[Member]"):
            in_class_b_section = False
        if not in_class_b_section:
            continue

        metric = None
        if label.startswith("Net earnings per average equivalent"):
            metric = "diluted_eps"
        elif label.startswith("Average equivalent shares outstanding"):
            metric = "diluted_shares"
        if metric is None:
            continue

        for column in period_columns:
            period_label = _period_label_from_column(column, period=period)
            value = _parse_number(row.get(column))
            if period_label is not None and value is not None:
                values[metric][period_label] = value
    return values


def _period_label_from_column(column: object, *, period: str) -> str | None:
    text = " ".join(str(part) for part in column) if isinstance(column, tuple) else str(column)
    if period == "annual":
        match = re.search(r"12 Months Ended [A-Za-z]{3}\.? \d{1,2}, (\d{4})", text)
        return f"FY {match.group(1)}" if match else None
    match = re.search(r"3 Months Ended ([A-Za-z]{3})\.? \d{1,2}, (\d{4})", text)
    if not match:
        return None
    quarter = _MONTH_TO_QUARTER.get(match.group(1))
    return f"{match.group(2)} Q{quarter}" if quarter else None


def _label_from_row(row: pd.Series) -> str:
    for value in row.iloc[:2]:
        text = str(value).strip()
        if text and text.lower() not in {"none", "nan"}:
            return text
    return ""


def _parse_number(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan"}:
        return None
    negative = "(" in text and ")" in text
    cleaned = (
        text.replace("$", "")
        .replace(",", "")
        .replace("[1]", "")
        .replace("(", "")
        .replace(")", "")
        .strip()
    )
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return -parsed if negative else parsed


def _period_columns(frame: pd.DataFrame) -> list[str]:
    return [str(column) for column in frame.columns if column not in {"metric", "unit"}]


def _has_any_period_value(frame: pd.DataFrame) -> bool:
    period_columns = _period_columns(frame)
    return any(not pd.isna(row[column]) for _, row in frame.iterrows() for column in period_columns)


def _empty_fallback_frame(target_periods: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=["metric", "unit", *target_periods])


def _filing_fetch_limit(*, period: str, target_periods: Sequence[str]) -> int:
    if period == "annual":
        return max(1, len(target_periods))
    return max(1, len(target_periods) + 2)


def _insert_statement_row(frame: pd.DataFrame, row: dict) -> pd.DataFrame:
    metric = row["metric"]
    if metric == "diluted_eps":
        after_metric = "net_income"
    else:
        after_metric = "diluted_eps"

    records = frame.to_dict(orient="records")
    insert_at = next(
        (index + 1 for index, existing in enumerate(records) if existing.get("metric") == after_metric),
        len(records),
    )
    records.insert(insert_at, row)
    return pd.DataFrame(records, columns=frame.columns)
