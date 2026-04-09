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


def _resolve_latest_company_fact(
    company_facts: Mapping[str, Any],
    candidates: Sequence[tuple[str, str]],
    unit: Optional[str],
) -> Optional[Mapping[str, Any]]:
    facts = company_facts.get("facts", {})
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
        return {
            "taxonomy": taxonomy,
            "concept": concept,
            "unit": selected_unit,
            "value": latest.get("val"),
            "end": latest.get("end"),
            "filed": latest.get("filed"),
            "form": latest.get("form"),
            "frame": latest.get("frame"),
        }
    return None


def _company_fact_sort_key(entry: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(entry.get("filed") or ""),
        str(entry.get("end") or ""),
    )


def _get_or_none(values: Sequence[Any], index: int) -> Any:
    if index >= len(values):
        return None
    return values[index]
