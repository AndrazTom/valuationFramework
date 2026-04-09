"""Turn provider payloads into stable tables."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd

from valuation.data.providers.sec import SecCompany


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


def _get_or_none(values: Sequence[Any], index: int) -> Any:
    if index >= len(values):
        return None
    return values[index]
