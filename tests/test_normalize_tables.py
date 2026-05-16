import pandas as pd

from valuation.data.normalize.tables import (
    CompanyFactQuery,
    CORE_COMPANY_FILING_FORMS,
    company_facts_to_table,
    company_facts_to_statement_table,
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
    assert frame.shape == (2, 10)
    assert frame.iloc[0]["report_date"] is None
    assert frame.iloc[0]["accepted_at"] is None
    assert frame.iloc[0]["form_group"] == "annual"
    assert frame.iloc[0]["description"] is None
    assert frame.iloc[0]["filing_url"] is None
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


def test_recent_filings_to_table_filters_to_preferred_forms():
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001", "0002", "0003"],
                "filingDate": ["2026-01-03", "2026-01-02", "2026-01-01"],
                "reportDate": ["2025-12-31", "2025-12-15", "2025-09-30"],
                "acceptanceDateTime": ["20260103100000", "20260102100000", "20260101100000"],
                "form": ["4", "8-K", "10-Q"],
                "primaryDocDescription": [
                    "Statement of changes in beneficial ownership",
                    "Current report",
                    "Quarterly report",
                ],
                "primaryDocument": ["form4.xml", "current.htm", "quarterly.htm"],
            }
        }
    }

    frame = recent_filings_to_table(
        submissions,
        limit=5,
        preferred_forms=("10-Q", "8-K"),
    )

    assert list(frame["form"]) == ["10-Q", "8-K"]
    assert frame.iloc[0]["form_group"] == "quarterly"
    assert frame.iloc[1]["report_date"] == "2025-12-15"


def test_recent_filings_to_table_core_forms_exclude_ownership_noise_but_keep_proxy():
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0001", "0002", "0003", "0004"],
                "filingDate": ["2026-01-04", "2026-01-03", "2026-01-02", "2026-01-01"],
                "reportDate": ["2026-01-04", "2026-01-03", "2025-12-31", "2025-12-31"],
                "acceptanceDateTime": [
                    "20260104100000",
                    "20260103100000",
                    "20260102100000",
                    "20260101100000",
                ],
                "form": ["4", "144", "DEF 14A", "10-K"],
                "primaryDocDescription": [
                    "Statement of changes in beneficial ownership",
                    "Proposed sale of securities",
                    "Definitive proxy statement",
                    "Annual report",
                ],
                "primaryDocument": ["form4.xml", "form144.htm", "proxy.htm", "annual.htm"],
            }
        }
    }

    frame = recent_filings_to_table(
        submissions,
        limit=10,
        preferred_forms=CORE_COMPANY_FILING_FORMS,
    )

    assert list(frame["form"]) == ["10-K", "DEF 14A"]
    assert list(frame["form_group"]) == ["annual", "proxy"]


def test_recent_filings_to_table_builds_filing_urls_when_cik_present():
    submissions = {
        "cik": "0000320193",
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000001"],
                "filingDate": ["2026-01-30"],
                "form": ["10-Q"],
                "primaryDocument": ["q1.htm"],
            }
        }
    }

    frame = recent_filings_to_table(submissions, limit=1)

    assert frame.iloc[0]["filing_url"] == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/q1.htm"


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


def test_company_facts_to_statement_table_builds_annual_period_columns():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 100.0,
                                "fy": 2024,
                                "fp": "FY",
                                "end": "2024-12-31",
                                "filed": "2025-02-01",
                                "form": "10-K",
                            },
                            {
                                "val": 90.0,
                                "fy": 2023,
                                "fp": "FY",
                                "end": "2023-12-31",
                                "filed": "2024-02-01",
                                "form": "10-K",
                            },
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 25.0,
                                "fy": 2024,
                                "fp": "FY",
                                "end": "2024-12-31",
                                "filed": "2025-02-01",
                                "form": "10-K",
                            }
                        ]
                    }
                },
            }
        }
    }

    frame = company_facts_to_statement_table(
        company_facts,
        [
            CompanyFactQuery("revenue", (("us-gaap", "Revenues"),)),
            CompanyFactQuery("net_income", (("us-gaap", "NetIncomeLoss"),)),
        ],
        period="annual",
        value_kind="duration",
        limit=2,
    )

    assert list(frame.columns) == ["metric", "unit", "FY 2024", "FY 2023"]
    assert frame.iloc[0]["FY 2024"] == 100.0
    assert frame.iloc[1]["FY 2024"] == 25.0


def test_company_facts_to_statement_table_builds_quarterly_labels():
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 7.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 6.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                            },
                        ]
                    }
                }
            }
        }
    }

    frame = company_facts_to_statement_table(
        company_facts,
        [CompanyFactQuery("net_income", (("us-gaap", "NetIncomeLoss"),))],
        period="quarterly",
        value_kind="duration",
        limit=2,
    )

    assert list(frame.columns) == ["metric", "unit", "2025 Q2", "2025 Q1"]
    assert frame.iloc[0]["2025 Q2"] == 7.0


def test_company_facts_to_statement_table_derives_missing_q4_from_ytd_and_fy():
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {
                                "val": 120.0,
                                "fy": 2025,
                                "fp": "FY",
                                "start": "2024-10-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-K",
                            },
                            {
                                "val": 90.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2024-10-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 50.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2024-10-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 20.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "start": "2024-10-01",
                                "end": "2024-12-31",
                                "filed": "2025-02-01",
                                "form": "10-Q",
                            },
                        ]
                    }
                }
            }
        }
    }

    frame = company_facts_to_statement_table(
        company_facts,
        [
            CompanyFactQuery(
                "operating_cash_flow",
                (("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),),
            )
        ],
        period="quarterly",
        value_kind="duration",
        limit=4,
    )

    assert list(frame.columns) == ["metric", "unit", "2025 Q3", "2025 Q2", "2025 Q1", "2024 Q4"]
    assert frame.iloc[0]["2025 Q3"] == 30.0
    assert frame.iloc[0]["2025 Q2"] == 40.0
    assert frame.iloc[0]["2025 Q1"] == 30.0
    assert frame.iloc[0]["2024 Q4"] == 20.0


def test_company_facts_to_statement_table_filters_by_year_and_quarter_range():
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 11.0,
                                "fy": 2026,
                                "fp": "Q1",
                                "start": "2025-10-01",
                                "end": "2025-12-31",
                                "filed": "2026-02-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 10.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-04-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                                "frame": "CY2025Q2",
                            },
                            {
                                "val": 9.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1",
                            },
                        ]
                    }
                }
            }
        }
    }

    frame = company_facts_to_statement_table(
        company_facts,
        [CompanyFactQuery("net_income", (("us-gaap", "NetIncomeLoss"),))],
        period="quarterly",
        value_kind="duration",
        limit=10,
        start_year=2025,
        start_quarter=1,
        end_year=2025,
        end_quarter=2,
    )

    assert list(frame.columns) == ["metric", "unit", "2025 Q2", "2025 Q1"]


def test_company_facts_to_statement_table_direct_quarter_metrics_do_not_subtract_ytd():
    company_facts = {
        "facts": {
            "us-gaap": {
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "val": 150.0,
                                "fy": 2025,
                                "fp": "FY",
                                "start": "2024-10-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-K",
                            },
                            {
                                "val": 152.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2024-10-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 149.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-04-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                                "frame": "CY2025Q2",
                            },
                            {
                                "val": 151.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1",
                            },
                        ]
                    }
                }
            }
        }
    }

    frame = company_facts_to_statement_table(
        company_facts,
        [
            CompanyFactQuery(
                "diluted_shares",
                (("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),),
                unit="shares",
                quarterly_value_kind="direct",
            )
        ],
        period="quarterly",
        value_kind="duration",
        limit=4,
    )

    assert frame.iloc[0]["2025 Q2"] == 149.0
    assert frame.iloc[0]["2025 Q1"] == 151.0
    assert "2025 Q3" not in frame.columns
