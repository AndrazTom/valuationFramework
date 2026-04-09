"""Turn provider payloads into stable tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

import pandas as pd

from valuation.data.providers.sec import SecCompany


@dataclass(frozen=True)
class CompanyFactQuery:
    """Definition for selecting a latest fact from SEC companyfacts payloads."""

    metric: str
    candidates: Sequence[tuple[str, str]]
    unit: Optional[str] = "USD"


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


def recent_filings_to_table(submissions: Mapping[str, Any], limit: int = 10) -> pd.DataFrame:
    limit = max(0, limit)
    recent = submissions.get("filings", {}).get("recent", {})
    if not recent:
        return pd.DataFrame(
            columns=[
                "filing_date",
                "form",
                "accession_number",
                "primary_document",
                "is_inline_xbrl",
            ]
        )

    accession_numbers: Sequence[Any] = recent.get("accessionNumber", [])
    filing_dates: Sequence[Any] = recent.get("filingDate", [])
    forms: Sequence[Any] = recent.get("form", [])
    primary_documents: Sequence[Any] = recent.get("primaryDocument", [])
    inline_xbrl_flags: Sequence[Any] = recent.get("isInlineXBRL", [])

    max_rows = min(limit, len(accession_numbers))
    rows = []
    for index in range(max_rows):
        rows.append(
            {
                "filing_date": _get_or_none(filing_dates, index),
                "form": _get_or_none(forms, index),
                "accession_number": _get_or_none(accession_numbers, index),
                "primary_document": _get_or_none(primary_documents, index),
                "is_inline_xbrl": _get_or_none(inline_xbrl_flags, index),
            }
        )
    return pd.DataFrame(rows)


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
    limit: int = 4,
) -> pd.DataFrame:
    """Return a statement-like table with one row per metric and one column per period."""
    definitions = tuple(queries)
    periods = _statement_periods(company_facts, definitions, period=period)
    selected_periods = periods[: max(0, limit)]

    rows = []
    for query in definitions:
        values_by_period = _statement_values_by_period(
            company_facts,
            query,
            period=period,
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
) -> list[Mapping[str, Any]]:
    periods_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for query in queries:
        values_by_period = _statement_values_by_period(
            company_facts,
            query,
            period=period,
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
) -> dict[tuple[str, str], Mapping[str, Any]]:
    facts = company_facts.get("facts", {})
    selected: dict[tuple[str, str], Mapping[str, Any]] = {}
    for candidate_index, (taxonomy, concept) in enumerate(query.candidates):
        units = facts.get(taxonomy, {}).get(concept, {}).get("units", {})
        if not units:
            continue

        selected_unit = query.unit
        if selected_unit is None:
            selected_unit = next(iter(units.keys()), None)
        if selected_unit is None or selected_unit not in units:
            continue

        for entry in units.get(selected_unit, []):
            period_key = _statement_period_key(entry, period=period)
            if period_key is None:
                continue
            period_label = _statement_period_label(entry, period=period)
            candidate = {
                "value": entry.get("val"),
                "unit": selected_unit,
                "end": entry.get("end"),
                "filed": entry.get("filed"),
                "form": entry.get("form"),
                "frame": entry.get("frame"),
                "key": period_key,
                "label": period_label,
                "sort_key": _statement_sort_key(entry, period=period),
                "candidate_priority": -candidate_index,
            }
            existing = selected.get(period_key)
            if existing is None or (
                candidate["sort_key"],
                candidate["candidate_priority"],
            ) > (
                existing["sort_key"],
                existing["candidate_priority"],
            ):
                selected[period_key] = candidate
    return selected


def _statement_period_key(
    entry: Mapping[str, Any],
    *,
    period: str,
) -> tuple[str, str] | None:
    fy = str(entry.get("fy") or "")
    fp = str(entry.get("fp") or "")
    end = str(entry.get("end") or "")
    if period == "annual":
        if fp == "FY":
            return ("annual", fy or end[:4])
        if _is_annual_form(entry):
            return ("annual", fy or end[:4])
        return None

    if fp.startswith("Q"):
        return ("quarterly", f"{fy}:{fp}")
    if _is_quarterly_form(entry) and end:
        return ("quarterly", end)
    return None


def _statement_period_label(
    entry: Mapping[str, Any],
    *,
    period: str,
) -> str:
    fy = str(entry.get("fy") or "").strip()
    fp = str(entry.get("fp") or "").strip()
    end = str(entry.get("end") or "").strip()
    if period == "annual":
        if fy:
            return f"FY {fy}"
        return end
    if fy and fp.startswith("Q"):
        return f"{fy} {fp}"
    return end


def _statement_sort_key(
    entry: Mapping[str, Any],
    *,
    period: str,
) -> tuple[str, str, str]:
    return (
        str(entry.get("fy") or ""),
        str(entry.get("end") or ""),
        str(entry.get("filed") or ""),
    )


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
