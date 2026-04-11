"""Turn provider payloads into stable tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

import pandas as pd

from valuation.data.providers.sec import SecCompany

CORE_COMPANY_FILING_FORMS = (
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "8-K",
    "20-F",
    "20-F/A",
    "6-K",
    "40-F",
    "40-F/A",
    "DEF 14A",
    "DEF 14A/A",
)


@dataclass(frozen=True)
class CompanyFactQuery:
    """Definition for selecting a latest fact from SEC companyfacts payloads."""

    metric: str
    candidates: Sequence[tuple[str, str]]
    unit: Optional[str] = "USD"
    quarterly_value_kind: Optional[str] = None


def snapshot_to_table(snapshot: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for field, value in snapshot.items():
        rows.append({"field": field, "value": value})
    return pd.DataFrame(rows)


def sec_company_to_table(company: SecCompany) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"field": "ticker", "value": company.ticker},
            {"field": "cik", "value": company.cik},
            {"field": "name", "value": company.name},
            {"field": "exchange", "value": company.exchange},
        ]
    )


def recent_filings_to_table(
    submissions: Mapping[str, Any],
    limit: int = 10,
    *,
    preferred_forms: Sequence[str] | None = None,
) -> pd.DataFrame:
    limit = max(0, limit)
    recent = submissions.get("filings", {}).get("recent", {})
    columns = [
        "filing_date",
        "report_date",
        "accepted_at",
        "form",
        "form_group",
        "description",
        "accession_number",
        "primary_document",
        "filing_url",
        "is_inline_xbrl",
    ]
    if not recent:
        return pd.DataFrame(columns=columns)
    if limit == 0:
        return pd.DataFrame(columns=columns)

    accession_numbers: Sequence[Any] = recent.get("accessionNumber", [])
    filing_dates: Sequence[Any] = recent.get("filingDate", [])
    report_dates: Sequence[Any] = recent.get("reportDate", [])
    acceptance_datetimes: Sequence[Any] = recent.get("acceptanceDateTime", [])
    forms: Sequence[Any] = recent.get("form", [])
    descriptions: Sequence[Any] = recent.get("primaryDocDescription", [])
    primary_documents: Sequence[Any] = recent.get("primaryDocument", [])
    inline_xbrl_flags: Sequence[Any] = recent.get("isInlineXBRL", [])
    cik = submissions.get("cik")

    preferred_form_set = None
    if preferred_forms is not None:
        preferred_form_set = {str(form).upper() for form in preferred_forms}

    rows = []
    for index in range(len(accession_numbers)):
        form = _get_or_none(forms, index)
        if preferred_form_set is not None and str(form or "").upper() not in preferred_form_set:
            continue
        rows.append(
            {
                "filing_date": _get_or_none(filing_dates, index),
                "report_date": _get_or_none(report_dates, index),
                "accepted_at": _get_or_none(acceptance_datetimes, index),
                "form": form,
                "form_group": _filing_form_group(form),
                "description": _get_or_none(descriptions, index),
                "accession_number": _get_or_none(accession_numbers, index),
                "primary_document": _get_or_none(primary_documents, index),
                "filing_url": _build_filing_url(
                    cik=cik,
                    accession_number=_get_or_none(accession_numbers, index),
                    primary_document=_get_or_none(primary_documents, index),
                ),
                "is_inline_xbrl": _get_or_none(inline_xbrl_flags, index),
                "_priority": _filing_priority(form),
                "_row_index": index,
            }
        )
    rows = sorted(
        rows,
        key=lambda row: (
            row["_priority"],
            str(row.get("filing_date") or ""),
            str(row.get("accepted_at") or ""),
            -int(row["_row_index"]),
        ),
        reverse=True,
    )[:limit]
    normalized_rows = []
    for row in rows:
        normalized_rows.append({column: row.get(column) for column in columns})
    return pd.DataFrame(normalized_rows, columns=columns)


def company_facts_to_table(
    company_facts: Mapping[str, Any],
    queries: Iterable[CompanyFactQuery],
) -> pd.DataFrame:
    """Resolve a small set of companyfacts into a flat latest-facts table."""
    rows = []
    for query in queries:
        fact = _resolve_latest_company_fact(
            company_facts,
            candidates=query.candidates,
            unit=query.unit,
        )
        rows.append(
            {
                "metric": query.metric,
                "taxonomy": fact.get("taxonomy") if fact else None,
                "concept": fact.get("concept") if fact else None,
                "unit": fact.get("unit") if fact else query.unit,
                "value": fact.get("value") if fact else None,
                "end": fact.get("end") if fact else None,
                "filed": fact.get("filed") if fact else None,
                "form": fact.get("form") if fact else None,
                "frame": fact.get("frame") if fact else None,
            }
        )
    return pd.DataFrame(rows)


def company_facts_to_statement_table(
    company_facts: Mapping[str, Any],
    queries: Iterable[CompanyFactQuery],
    *,
    period: str,
    value_kind: str,
    limit: int = 4,
    start_year: int | None = None,
    end_year: int | None = None,
    start_quarter: int | None = None,
    end_quarter: int | None = None,
) -> pd.DataFrame:
    """Return a statement-like table with one row per metric and one column per period."""
    definitions = tuple(queries)
    periods = _statement_periods(
        company_facts,
        definitions,
        period=period,
        value_kind=value_kind,
    )
    periods = _filter_statement_periods(
        periods,
        period=period,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    selected_periods = periods[: max(0, limit)]

    rows = []
    for query in definitions:
        query_value_kind = query.quarterly_value_kind or value_kind
        values_by_period = _statement_values_by_period(
            company_facts,
            query,
            period=period,
            value_kind=query_value_kind,
        )
        row = {
            "metric": query.metric,
            "unit": _statement_unit(values_by_period, default=query.unit),
        }
        for period_info in selected_periods:
            row[period_info["label"]] = values_by_period.get(period_info["key"], {}).get("value")
        rows.append(row)
    return pd.DataFrame(rows)


def _resolve_latest_company_fact(
    company_facts: Mapping[str, Any],
    candidates: Sequence[tuple[str, str]],
    unit: Optional[str],
) -> Optional[Mapping[str, Any]]:
    facts = company_facts.get("facts", {})
    best_fact = None
    best_key = None
    for taxonomy, concept in candidates:
        units = facts.get(taxonomy, {}).get(concept, {}).get("units", {})
        if not units:
            continue

        selected_unit = unit
        if selected_unit is None:
            selected_unit = next(iter(units.keys()), None)
        if selected_unit is None or selected_unit not in units:
            continue

        values = units.get(selected_unit, [])
        if not values:
            continue

        latest = max(values, key=_company_fact_sort_key)
        candidate_fact = {
            "taxonomy": taxonomy,
            "concept": concept,
            "unit": selected_unit,
            "value": latest.get("val"),
            "end": latest.get("end"),
            "filed": latest.get("filed"),
            "form": latest.get("form"),
            "frame": latest.get("frame"),
        }
        candidate_key = _company_fact_sort_key(latest)
        if best_key is None or candidate_key > best_key:
            best_key = candidate_key
            best_fact = candidate_fact
    return best_fact


def _statement_periods(
    company_facts: Mapping[str, Any],
    queries: Sequence[CompanyFactQuery],
    *,
    period: str,
    value_kind: str,
) -> list[Mapping[str, Any]]:
    periods_by_key: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for query in queries:
        query_value_kind = query.quarterly_value_kind or value_kind
        values_by_period = _statement_values_by_period(
            company_facts,
            query,
            period=period,
            value_kind=query_value_kind,
        )
        for key, value in values_by_period.items():
            existing = periods_by_key.get(key)
            if existing is None or value["sort_key"] > existing["sort_key"]:
                periods_by_key[key] = value
    return sorted(
        periods_by_key.values(),
        key=lambda item: item["sort_key"],
        reverse=True,
    )


def _statement_values_by_period(
    company_facts: Mapping[str, Any],
    query: CompanyFactQuery,
    *,
    period: str,
    value_kind: str,
) -> dict[tuple[Any, ...], Mapping[str, Any]]:
    facts = company_facts.get("facts", {})
    selected: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for candidate_index, (taxonomy, concept) in enumerate(query.candidates):
        units = facts.get(taxonomy, {}).get(concept, {}).get("units", {})
        if not units:
            continue

        selected_unit = query.unit
        if selected_unit is None:
            selected_unit = next(iter(units.keys()), None)
        if selected_unit is None or selected_unit not in units:
            continue

        if period == "annual":
            candidates = _annual_statement_candidates(
                units.get(selected_unit, []),
                unit=selected_unit,
            )
        elif value_kind == "duration":
            candidates = _quarterly_duration_statement_candidates(
                units.get(selected_unit, []),
                unit=selected_unit,
            )
        elif value_kind == "direct":
            candidates = _quarterly_direct_statement_candidates(
                units.get(selected_unit, []),
                unit=selected_unit,
                include_annual_fallback=False,
            )
        elif value_kind == "direct_or_annual":
            candidates = _quarterly_direct_statement_candidates(
                units.get(selected_unit, []),
                unit=selected_unit,
                include_annual_fallback=True,
            )
        else:
            candidates = _quarterly_instant_statement_candidates(
                units.get(selected_unit, []),
                unit=selected_unit,
            )

        for candidate in candidates:
            candidate = {
                **candidate,
                "candidate_priority": -candidate_index,
            }
            existing = selected.get(candidate["key"])
            if existing is None or (
                candidate["sort_key"],
                candidate["candidate_priority"],
            ) > (
                existing["sort_key"],
                existing["candidate_priority"],
            ):
                selected[candidate["key"]] = candidate
    return selected


def _annual_statement_candidates(
    entries: Sequence[Mapping[str, Any]],
    *,
    unit: str,
) -> list[Mapping[str, Any]]:
    candidates = []
    for entry in entries:
        year = _annual_year(entry)
        if year is None:
            continue
        candidates.append(
            {
                "value": entry.get("val"),
                "unit": unit,
                "end": entry.get("end"),
                "filed": entry.get("filed"),
                "form": entry.get("form"),
                "frame": entry.get("frame"),
                "key": ("annual", year),
                "label": f"FY {year}",
                "sort_key": (year, str(entry.get("end") or ""), str(entry.get("filed") or "")),
                "year": year,
            }
        )
    return candidates


def _quarterly_instant_statement_candidates(
    entries: Sequence[Mapping[str, Any]],
    *,
    unit: str,
) -> list[Mapping[str, Any]]:
    candidates = []
    for entry in entries:
        quarter_key = _calendar_quarter_key(entry)
        if quarter_key is None:
            continue
        year, quarter = quarter_key
        candidates.append(
            {
                "value": entry.get("val"),
                "unit": unit,
                "end": entry.get("end"),
                "filed": entry.get("filed"),
                "form": entry.get("form"),
                "frame": entry.get("frame"),
                "key": ("quarterly", year, quarter),
                "label": f"{year} Q{quarter}",
                "sort_key": (year, quarter, str(entry.get("end") or ""), str(entry.get("filed") or "")),
                "year": year,
                "quarter": quarter,
            }
        )
    return candidates


def _quarterly_direct_statement_candidates(
    entries: Sequence[Mapping[str, Any]],
    *,
    unit: str,
    include_annual_fallback: bool,
) -> list[Mapping[str, Any]]:
    candidates = []
    for entry in entries:
        if _is_single_quarter_duration_entry(entry):
            quarter_key = _calendar_quarter_key(entry)
            if quarter_key is None:
                continue
            year, quarter = quarter_key
            candidates.append(
                {
                    "value": entry.get("val"),
                    "unit": unit,
                    "end": entry.get("end"),
                    "filed": entry.get("filed"),
                    "form": entry.get("form"),
                    "frame": entry.get("frame"),
                    "key": ("quarterly", year, quarter),
                    "label": f"{year} Q{quarter}",
                    "sort_key": (
                        year,
                        quarter,
                        str(entry.get("end") or ""),
                        str(entry.get("filed") or ""),
                        1,
                    ),
                    "year": year,
                    "quarter": quarter,
                }
            )
            continue

        if include_annual_fallback and _is_annual_form(entry):
            quarter_key = _calendar_quarter_key(entry)
            if quarter_key is None:
                continue
            year, quarter = quarter_key
            candidates.append(
                {
                    "value": entry.get("val"),
                    "unit": unit,
                    "end": entry.get("end"),
                    "filed": entry.get("filed"),
                    "form": entry.get("form"),
                    "frame": entry.get("frame"),
                    "key": ("quarterly", year, quarter),
                    "label": f"{year} Q{quarter}",
                    "sort_key": (
                        year,
                        quarter,
                        str(entry.get("end") or ""),
                        str(entry.get("filed") or ""),
                        0,
                    ),
                    "year": year,
                    "quarter": quarter,
                }
            )
    return candidates


def _quarterly_duration_statement_candidates(
    entries: Sequence[Mapping[str, Any]],
    *,
    unit: str,
) -> list[Mapping[str, Any]]:
    grouped: dict[int, dict[str, Mapping[str, Any]]] = {}
    for entry in entries:
        fy = _fiscal_year(entry)
        if fy is None:
            continue
        fp = str(entry.get("fp") or "").upper()
        bucket = grouped.setdefault(fy, {})

        if fp in {"Q1", "Q2", "Q3"}:
            if _is_single_quarter_duration_entry(entry):
                key = f"{fp}_direct"
            else:
                key = f"{fp}_ytd"
        elif fp == "FY" or _is_annual_form(entry):
            key = "FY"
        else:
            continue

        existing = bucket.get(key)
        if existing is None or _company_fact_sort_key(entry) > _company_fact_sort_key(existing):
            bucket[key] = entry

    candidates = []
    for fy, bucket in grouped.items():
        q1_entry = bucket.get("Q1_direct") or bucket.get("Q1_ytd")
        q2_entry = bucket.get("Q2_direct")
        if q2_entry is None and bucket.get("Q2_ytd") is not None and q1_entry is not None:
            q2_entry = _derive_duration_entry(bucket["Q2_ytd"], q1_entry)

        q3_entry = bucket.get("Q3_direct")
        if q3_entry is None and bucket.get("Q3_ytd") is not None:
            base = bucket.get("Q2_ytd") or q2_entry
            if base is not None:
                q3_entry = _derive_duration_entry(bucket["Q3_ytd"], base)

        q4_entry = None
        if bucket.get("FY") is not None and bucket.get("Q3_ytd") is not None:
            q4_entry = _derive_duration_entry(bucket["FY"], bucket["Q3_ytd"])

        for entry in (q1_entry, q2_entry, q3_entry, q4_entry):
            if entry is None:
                continue
            quarter_key = _calendar_quarter_key(entry)
            if quarter_key is None:
                continue
            year, quarter = quarter_key
            candidates.append(
                {
                    "value": entry.get("val"),
                    "unit": unit,
                    "end": entry.get("end"),
                    "filed": entry.get("filed"),
                    "form": entry.get("form"),
                    "frame": entry.get("frame"),
                    "key": ("quarterly", year, quarter),
                    "label": f"{year} Q{quarter}",
                    "sort_key": (
                        year,
                        quarter,
                        str(entry.get("end") or ""),
                        str(entry.get("filed") or ""),
                    ),
                    "year": year,
                    "quarter": quarter,
                }
            )
    return candidates


def _annual_year(entry: Mapping[str, Any]) -> int | None:
    fp = str(entry.get("fp") or "").upper()
    fy = entry.get("fy")
    if fy is not None and (fp == "FY" or _is_annual_form(entry)):
        try:
            return int(fy)
        except (TypeError, ValueError):
            pass
    if _is_annual_form(entry):
        timestamp = _entry_end_timestamp(entry)
        if timestamp is not None:
            return int(timestamp.year)
    return None


def _fiscal_year(entry: Mapping[str, Any]) -> int | None:
    fy = entry.get("fy")
    if fy is None:
        return None
    try:
        return int(fy)
    except (TypeError, ValueError):
        return None


def _calendar_quarter_key(entry: Mapping[str, Any]) -> tuple[int, int] | None:
    timestamp = _entry_end_timestamp(entry)
    if timestamp is None:
        return None
    quarter = ((int(timestamp.month) - 1) // 3) + 1
    return int(timestamp.year), quarter


def _entry_end_timestamp(entry: Mapping[str, Any]) -> pd.Timestamp | None:
    end = entry.get("end")
    if not end:
        return None
    timestamp = pd.to_datetime(end, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp


def _duration_days(entry: Mapping[str, Any]) -> int | None:
    start = entry.get("start")
    end = entry.get("end")
    if not start or not end:
        return None
    start_ts = pd.to_datetime(start, errors="coerce")
    end_ts = pd.to_datetime(end, errors="coerce")
    if pd.isna(start_ts) or pd.isna(end_ts):
        return None
    return int((end_ts - start_ts).days) + 1


def _is_single_quarter_duration_entry(entry: Mapping[str, Any]) -> bool:
    fp = str(entry.get("fp") or "").upper()
    if fp == "Q1":
        return True
    days = _duration_days(entry)
    if days is None:
        return True
    return days is not None and days <= 120


def _derive_duration_entry(
    total_entry: Mapping[str, Any],
    base_entry: Mapping[str, Any],
) -> Mapping[str, Any]:
    return {
        "val": (total_entry.get("val") or 0) - (base_entry.get("val") or 0),
        "end": total_entry.get("end"),
        "filed": total_entry.get("filed"),
        "form": total_entry.get("form"),
        "frame": total_entry.get("frame"),
    }


def _filter_statement_periods(
    periods: Sequence[Mapping[str, Any]],
    *,
    period: str,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> list[Mapping[str, Any]]:
    if (
        start_year is None
        and end_year is None
        and start_quarter is None
        and end_quarter is None
    ):
        return list(periods)

    filtered = []
    for item in periods:
        year = item.get("year")
        quarter = item.get("quarter")
        if start_year is not None:
            if year is None or year < start_year:
                continue
            if (
                period == "quarterly"
                and year == start_year
                and start_quarter is not None
                and quarter is not None
                and quarter < start_quarter
            ):
                continue
        if end_year is not None:
            if year is None or year > end_year:
                continue
            if (
                period == "quarterly"
                and year == end_year
                and end_quarter is not None
                and quarter is not None
                and quarter > end_quarter
            ):
                continue
        filtered.append(item)
    return filtered


def _statement_unit(
    values_by_period: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    default: str | None,
) -> str | None:
    if values_by_period:
        first = next(iter(values_by_period.values()))
        return first.get("unit")
    return default


def _is_annual_form(entry: Mapping[str, Any]) -> bool:
    form = str(entry.get("form") or "").upper()
    return form in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


def _is_quarterly_form(entry: Mapping[str, Any]) -> bool:
    form = str(entry.get("form") or "").upper()
    return form in {"10-Q", "10-Q/A"}


def _company_fact_sort_key(entry: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(entry.get("filed") or ""),
        str(entry.get("end") or ""),
    )


def _get_or_none(values: Sequence[Any], index: int) -> Any:
    if index >= len(values):
        return None
    return values[index]


def _filing_form_group(form: Any) -> str:
    normalized = str(form or "").upper()
    if normalized in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}:
        return "annual"
    if normalized in {"10-Q", "10-Q/A"}:
        return "quarterly"
    if normalized in {"6-K", "6-K/A"}:
        return "foreign_current"
    if normalized in {"8-K", "8-K/A"}:
        return "current"
    if normalized.startswith("DEF "):
        return "proxy"
    if normalized in {"3", "4", "5", "144", "SCHEDULE 13G", "SCHEDULE 13G/A", "SCHEDULE 13D", "SCHEDULE 13D/A"}:
        return "ownership"
    return "other"


def _filing_priority(form: Any) -> int:
    priorities = {
        "annual": 5,
        "quarterly": 5,
        "foreign_current": 4,
        "current": 3,
        "proxy": 1,
        "ownership": 0,
        "other": 0,
    }
    return priorities[_filing_form_group(form)]


def _build_filing_url(cik: Any, accession_number: Any, primary_document: Any) -> str | None:
    if cik in {None, ""} or accession_number in {None, ""} or primary_document in {None, ""}:
        return None
    cik_digits = "".join(ch for ch in str(cik) if ch.isdigit())
    if not cik_digits:
        return None
    accession = str(accession_number).replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik_digits)}/{accession}/{primary_document}"
