from datetime import date

import pytest
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

    assert income_annual["status"] == "partial"
    assert income_annual["metric_count"] == 1
    assert income_annual["expected_metric_count"] == 7
    assert income_annual["coverage_ratio"] == pytest.approx(1 / 7)
    assert income_annual["reason"] == (
        "Partial metric coverage: 1/7 metrics available; "
        "missing gross_profit, operating_income, pretax_income, net_income, +2 more"
    )
    assert cashflow_quarterly["status"] == "unavailable"
    assert cashflow_quarterly["expected_metric_count"] == 5
    assert cashflow_quarterly["coverage_ratio"] == 0.0
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

    assert income_annual["status"] == "partial"
    assert income_annual["latest_period"] == "FY 2025"
    assert income_annual["metric_count"] == 2
    assert income_annual["expected_metric_count"] == 7
    assert income_annual["coverage_ratio"] == pytest.approx(2 / 7)
    assert income_annual["reason"] == (
        "Partial metric coverage: 2/7 metrics available; "
        "missing gross_profit, operating_income, pretax_income, diluted_eps, +1 more"
    )
    assert income_quarterly["status"] == "unavailable"
    assert income_quarterly["expected_metric_count"] == 7
    assert income_quarterly["coverage_ratio"] == 0.0
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
            "market_cap_source": "last_price_x_shares",
            "shares": 16000000.0,
            "latest_price_date": date.today().isoformat(),
        },
        company_facts=company_facts,
        currency="USD",
    )

    last_price = table[table["metric"] == "last_price"].iloc[0]
    market_cap = table[table["metric"] == "market_cap"].iloc[0]
    revenue = table[table["metric"] == "revenue"].iloc[0]
    net_income = table[table["metric"] == "net_income"].iloc[0]

    assert last_price["status"] == "available"
    assert last_price["source"] == "yfinance"
    assert last_price["source_table"] == "market_snapshot"
    assert last_price["period_type"] == "market"
    assert last_price["completeness"] == "current"
    assert last_price["taxonomy"] == "yfinance"
    assert last_price["concept"] == "last_price"
    assert last_price["matched_label"] == "last_price"
    assert market_cap["taxonomy"] == "yfinance"
    assert market_cap["concept"] == "market_cap"
    assert market_cap["matched_label"] == "last_price_x_shares"
    assert revenue["status"] == "available"
    assert revenue["source"] == "sec"
    assert revenue["source_table"] == "companyfacts"
    assert revenue["statement"] == "income"
    assert revenue["period_type"] == "annual"
    assert revenue["as_of"] == "2025-12-31"
    assert revenue["completeness"] == "current"
    assert revenue["concept"] == "Revenues"
    assert revenue["form"] == "10-K"
    assert net_income["status"] == "unavailable"
    assert net_income["completeness"] == "missing"
    assert net_income["reason"] == "No SEC companyfacts concepts found: NetIncomeLoss"


def test_build_sec_overview_table_marks_market_snapshot_stale_when_quote_date_is_old():
    table = build_sec_overview_table(
        market_snapshot={
            "last_price": 250.0,
            "market_cap": 4000000000.0,
            "shares": 16000000.0,
            "latest_price_date": "2000-01-01",
        },
        company_facts={"facts": {}},
        currency="USD",
    )

    last_price = table[table["metric"] == "last_price"].iloc[0]

    assert last_price["status"] == "available"
    assert last_price["completeness"] == "stale"
    assert last_price["reason"] == "Market snapshot date older than 7 days: 2000-01-01"


def test_build_sec_overview_table_marks_market_snapshot_missing_when_quote_date_is_absent():
    table = build_sec_overview_table(
        market_snapshot={
            "last_price": 250.0,
            "market_cap": 4000000000.0,
            "shares": 16000000.0,
        },
        company_facts={"facts": {}},
        currency="USD",
    )

    last_price = table[table["metric"] == "last_price"].iloc[0]

    assert last_price["status"] == "available"
    assert last_price["completeness"] == "missing"
    assert last_price["reason"] == "Market snapshot date unavailable"


def test_build_sec_overview_table_distinguishes_sec_concept_with_wrong_unit():
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "EUR": [
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
        market_snapshot={},
        company_facts=company_facts,
        currency="USD",
    )

    net_income = table[table["metric"] == "net_income"].iloc[0]

    assert net_income["status"] == "unavailable"
    assert net_income["reason"] == (
        "SEC companyfacts concepts found but no USD units: NetIncomeLoss"
    )


def test_build_sec_overview_table_distinguishes_sec_concept_with_blank_values():
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": None,
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
        market_snapshot={},
        company_facts=company_facts,
        currency="USD",
    )

    net_income = table[table["metric"] == "net_income"].iloc[0]

    assert net_income["status"] == "unavailable"
    assert net_income["reason"] == (
        "SEC companyfacts concepts found but no usable USD values: NetIncomeLoss"
    )


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
    net_income = table[table["metric"] == "net_income"].iloc[0]
    total_assets = table[table["metric"] == "total_assets"].iloc[0]

    assert market_cap["status"] == "unavailable"
    assert market_cap["completeness"] == "missing"
    assert market_cap["reason"] == "Unavailable in market snapshot"
    assert revenue["status"] == "available"
    assert revenue["source"] == "yahoo"
    assert revenue["source_table"] == "income_statement"
    assert revenue["statement"] == "income"
    assert revenue["period_type"] == "annual"
    assert revenue["completeness"] == "current"
    assert revenue["matched_label"] == "Total Revenue"
    assert net_income["reason"] == (
        "No Yahoo annual income labels matched for net_income; "
        "tried Net Income Common Stockholders, Net Income, "
        "Net Income From Continuing Operation Net Minority Interest"
    )
    assert total_assets["status"] == "unavailable"
    assert total_assets["completeness"] == "missing"
    assert total_assets["reason"] == "Yahoo returned no annual balance statement frame"


def test_build_yahoo_overview_table_distinguishes_blank_candidate_labels():
    income = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Total Revenue": 100.0,
                "Net Income": float("nan"),
            }
        }
    )

    table = build_yahoo_overview_table(
        market_snapshot={},
        income_frame=income,
        balance_frame=pd.DataFrame(),
        cashflow_frame=pd.DataFrame(),
        currency="EUR",
    )

    net_income = table[table["metric"] == "net_income"].iloc[0]

    assert net_income["status"] == "unavailable"
    assert net_income["reason"] == (
        "Yahoo annual income labels present but values blank: Net Income"
    )


def test_build_sec_overview_table_marks_stale_metric_when_older_than_latest_statement_period():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 120.0,
                                "fy": 2025,
                                "fp": "FY",
                                "end": "2025-12-31",
                                "filed": "2026-01-31",
                                "form": "10-K",
                            }
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 40.0,
                                "fy": 2024,
                                "fp": "FY",
                                "end": "2024-12-31",
                                "filed": "2025-01-31",
                                "form": "10-K",
                            }
                        ]
                    }
                },
            }
        }
    }

    table = build_sec_overview_table(
        market_snapshot={"latest_price_date": "2026-04-10"},
        company_facts=company_facts,
        currency="USD",
    )

    revenue = table[table["metric"] == "revenue"].iloc[0]
    net_income = table[table["metric"] == "net_income"].iloc[0]

    assert revenue["completeness"] == "current"
    assert net_income["status"] == "available"
    assert net_income["as_of"] == "2024-12-31"
    assert net_income["completeness"] == "stale"


def test_build_yahoo_overview_table_marks_stale_metric_when_only_older_annual_period_has_value():
    income = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {"Total Revenue": float("nan")},
            pd.Timestamp("2024-12-31"): {"Total Revenue": 100.0},
        }
    )

    table = build_yahoo_overview_table(
        market_snapshot={"latest_price_date": "2026-04-10"},
        income_frame=income,
        balance_frame=pd.DataFrame(),
        cashflow_frame=pd.DataFrame(),
        currency="EUR",
    )

    revenue = table[table["metric"] == "revenue"].iloc[0]

    assert revenue["status"] == "available"
    assert revenue["as_of"] == "FY 2024"
    assert revenue["matched_label"] == "Total Revenue"
    assert revenue["completeness"] == "stale"
