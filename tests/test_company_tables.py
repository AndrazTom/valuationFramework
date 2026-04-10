import pandas as pd

from valuation.company.service import CompanyResolution
from valuation.company.tables import (
    build_sec_statement_availability_table,
    build_yahoo_statement_availability_table,
    company_summary_to_table,
)
from valuation.data.providers.sec import SecCompany


def test_company_summary_to_table_enriches_sec_company_with_profile_fields():
    resolution = CompanyResolution(
        input_value="AAPL",
        identifier_kind="ticker",
        query_used="AAPL",
        ticker="AAPL",
        exchange="NASDAQ",
        security_id="cik:0000320193",
        company_name="APPLE INC",
        sec_company=SecCompany(
            ticker="AAPL",
            cik="0000320193",
            name="APPLE INC",
            exchange="NASDAQ",
        ),
    )

    table = company_summary_to_table(
        resolution,
        company_profile={
            "country": "United States",
            "currency": "USD",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "website": "https://www.apple.com",
        },
    )

    fields = set(table["field"])

    assert {"ticker", "cik", "name", "exchange", "country", "currency", "sector", "industry", "website"} <= fields


def test_build_sec_statement_availability_table_marks_available_and_missing_rows():
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
                            }
                        ]
                    }
                }
            }
        }
    }

    table = build_sec_statement_availability_table(company_facts)

    income_annual = table[(table["statement"] == "income") & (table["period"] == "annual")].iloc[0]
    cashflow_quarterly = table[(table["statement"] == "cashflow") & (table["period"] == "quarterly")].iloc[0]

    assert income_annual["status"] == "available"
    assert income_annual["period_count"] == 1
    assert income_annual["latest_period"] == "FY 2024"
    assert cashflow_quarterly["status"] == "unavailable"
    assert cashflow_quarterly["reason"] == "no_companyfacts_rows"


def test_build_yahoo_statement_availability_table_marks_provider_gaps():
    frames = {
        ("income", "annual"): pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): {
                    "Total Revenue": 100.0,
                    "Net Income": 20.0,
                }
            }
        ),
        ("income", "quarterly"): pd.DataFrame(),
    }

    table = build_yahoo_statement_availability_table(frames, currency="EUR")

    income_annual = table[(table["statement"] == "income") & (table["period"] == "annual")].iloc[0]
    income_quarterly = table[(table["statement"] == "income") & (table["period"] == "quarterly")].iloc[0]

    assert income_annual["status"] == "available"
    assert income_annual["latest_period"] == "FY 2025"
    assert income_quarterly["status"] == "unavailable"
    assert income_quarterly["reason"] == "provider_returned_no_data"
