import pandas as pd

from valuation.company.tables import (
    build_sec_overview_table,
    build_sec_statement_availability_table,
    build_yahoo_overview_table,
    build_yahoo_statement_availability_table,
    company_summary_to_table,
)
from valuation.data.providers.sec import SecCompany


class Resolution:
    def __init__(
        self,
        *,
        sec_company=None,
        ticker="AAPL",
        exchange="NASDAQ",
        company_name="APPLE INC",
        country=None,
        currency=None,
    ):
        self.input_value = ticker
        self.identifier_kind = "ticker"
        self.query_used = ticker
        self.security_id = f"ticker:{exchange}:{ticker}"
        self.ticker = ticker
        self.exchange = exchange
        self.company_name = company_name
        self.country = country
        self.currency = currency
        self.sec_company = sec_company


def test_company_summary_to_table_uses_profile_enrichment_for_sec_issuer():
    resolution = Resolution(
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
            "website": "https://apple.com",
        },
    )

    assert "country" in list(table["field"])
    assert "currency" in list(table["field"])
    assert "website" in list(table["field"])


def test_build_sec_statement_availability_table_marks_missing_rows_with_reason():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 100.0,
                                "fy": 2025,
                                "fp": "FY",
                                "end": "2025-12-31",
                                "filed": "2026-01-31",
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
    assert income_annual["metric_count"] >= 1
    assert cashflow_quarterly["status"] == "unavailable"
    assert cashflow_quarterly["reason"] == "No matching concepts found in SEC companyfacts"


def test_build_yahoo_statement_availability_table_reports_empty_frame_reason():
    frames = {
        ("income", "annual"): pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): {"Total Revenue": 100.0, "Net Income": 20.0},
            }
        ),
        ("income", "quarterly"): pd.DataFrame(),
        ("balance", "annual"): pd.DataFrame(),
        ("balance", "quarterly"): pd.DataFrame(),
        ("cashflow", "annual"): pd.DataFrame(),
        ("cashflow", "quarterly"): pd.DataFrame(),
    }

    table = build_yahoo_statement_availability_table(frames, currency="EUR")

    income_annual = table[(table["statement"] == "income") & (table["period"] == "annual")].iloc[0]
    income_quarterly = table[(table["statement"] == "income") & (table["period"] == "quarterly")].iloc[0]

    assert income_annual["status"] == "available"
    assert income_annual["latest_period"] == "FY 2025"
    assert income_quarterly["status"] == "unavailable"
    assert income_quarterly["reason"] == "Yahoo returned no statement frame"


def test_build_sec_overview_table_includes_market_and_financial_rows():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 100.0,
                                "fy": 2025,
                                "fp": "FY",
                                "end": "2025-12-31",
                                "filed": "2026-01-31",
                                "form": "10-K",
                            }
                        ]
                    }
                }
            }
        }
    }

    table = build_sec_overview_table(
        market_snapshot={
            "last_price": 250.0,
            "market_cap": 4000000000.0,
            "shares": 16000000.0,
            "latest_price_date": "2026-04-10",
        },
        company_facts=company_facts,
        currency="USD",
    )

    last_price = table[table["metric"] == "last_price"].iloc[0]
    revenue = table[table["metric"] == "revenue"].iloc[0]
    net_income = table[table["metric"] == "net_income"].iloc[0]

    assert last_price["status"] == "available"
    assert last_price["source"] == "yfinance"
    assert revenue["status"] == "available"
    assert revenue["source"] == "sec"
    assert revenue["as_of"] == "2025-12-31"
    assert net_income["status"] == "unavailable"
    assert net_income["reason"] == "No matching concepts found in SEC companyfacts"


def test_build_yahoo_overview_table_marks_missing_financial_metrics():
    income = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Total Revenue": 100.0}})
    balance = pd.DataFrame()
    cashflow = pd.DataFrame()

    table = build_yahoo_overview_table(
        market_snapshot={
            "last_price": 90.0,
            "market_cap": None,
            "shares": 1000000.0,
            "latest_price_date": "2026-04-10",
        },
        income_frame=income,
        balance_frame=balance,
        cashflow_frame=cashflow,
        currency="EUR",
    )

    market_cap = table[table["metric"] == "market_cap"].iloc[0]
    revenue = table[table["metric"] == "revenue"].iloc[0]
    total_assets = table[table["metric"] == "total_assets"].iloc[0]

    assert market_cap["status"] == "unavailable"
    assert market_cap["reason"] == "Unavailable in market snapshot"
    assert revenue["status"] == "available"
    assert revenue["source"] == "yahoo"
    assert total_assets["status"] == "unavailable"
    assert total_assets["reason"] == "Metric unavailable in Yahoo annual statements"
