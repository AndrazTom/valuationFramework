import pandas as pd

from valuation.data.normalize.tables import (
    CompanyFactQuery,
    company_facts_to_table,
    recent_filings_to_table,
    sec_company_to_table,
    snapshot_to_table,
)
from valuation.data.providers.sec import SecCompany


def test_snapshot_to_table_preserves_fields():
    frame = snapshot_to_table({"ticker": "BRK-B", "last_price": 479.75})

    assert list(frame["field"]) == ["ticker", "last_price"]
    assert list(frame["value"]) == ["BRK-B", 479.75]


def test_sec_company_to_table():
    company = SecCompany(
        ticker="BRK-B",
        cik="0001067983",
        name="BERKSHIRE HATHAWAY INC",
        exchange="NYSE",
    )

    frame = sec_company_to_table(company)

    assert list(frame["field"]) == ["ticker", "cik", "name", "exchange"]
    assert frame.iloc[2]["value"] == "BERKSHIRE HATHAWAY INC"


def test_recent_filings_to_table_handles_missing_columns():
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001", "0002"],
                "filingDate": ["2026-01-01", "2026-01-02"],
                "form": ["10-K", "8-K"],
            }
        }
    }

    frame = recent_filings_to_table(submissions, limit=5)

    assert isinstance(frame, pd.DataFrame)
    assert frame.shape == (2, 5)
    assert frame.iloc[0]["primary_document"] is None
    assert frame.iloc[1]["is_inline_xbrl"] is None


def test_recent_filings_to_table_clamps_negative_limit():
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001"],
                "filingDate": ["2026-01-01"],
                "form": ["10-K"],
            }
        }
    }

    frame = recent_filings_to_table(submissions, limit=-5)

    assert frame.empty


def test_company_facts_to_table_picks_latest_across_candidate_concepts():
    company_facts = {
        "facts": {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {
                        "USD": [
                            {
                                "val": 42.0,
                                "filed": "2024-02-20",
                                "end": "2023-12-31",
                                "form": "10-K",
                            }
                        ]
                    }
                },
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {
                    "units": {
                        "USD": [
                            {
                                "val": 84.0,
                                "filed": "2025-05-05",
                                "end": "2025-03-31",
                                "form": "10-Q",
                            }
                        ]
                    }
                },
            }
        }
    }

    frame = company_facts_to_table(
        company_facts,
        [
            CompanyFactQuery(
                metric="cash_and_equivalents",
                candidates=(
                    ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
                    ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
                ),
            )
        ],
    )

    assert frame.iloc[0]["value"] == 84.0
    assert frame.iloc[0]["concept"] == "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"
