from datetime import date

import pytest
import pandas as pd

from valuation.company.tables import (
    build_sec_overview_table,
    build_sec_statement_availability_table,
    build_valuation_ratios_table,
    build_yahoo_overview_table,
    build_yahoo_statement_availability_table,
    company_summary_to_table,
)
from valuation.company.statements import build_statement_diagnostics_table, build_statement_table_ttm
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


def test_build_statement_diagnostics_table_explains_missing_income_rows():
    table = build_statement_diagnostics_table(
        {"facts": {}},
        statement="income",
        period="quarterly",
    )

    diluted_shares = table[table["metric"] == "diluted_shares"].iloc[0]

    assert diluted_shares["status"] == "missing"
    assert diluted_shares["diagnostic"] == "concept not present in SEC companyfacts"


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
    assert net_income["reason"] == (
        "No SEC companyfacts concepts found: NetIncomeLoss, "
        "NetIncomeLossAvailableToCommonStockholdersDiluted, "
        "NetIncomeLossAvailableToCommonStockholdersBasic, ProfitLoss"
    )


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


def test_build_sec_overview_table_uses_bank_style_revenue_concepts():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 1000.0,
                                "end": "2025-12-31",
                                "filed": "2026-02-01",
                                "form": "10-K",
                            }
                        ]
                    }
                },
                "RevenuesNetOfInterestExpense": {
                    "units": {
                        "USD": [
                            {
                                "val": 300.0,
                                "end": "2026-03-31",
                                "filed": "2026-05-01",
                                "form": "10-Q",
                            }
                        ]
                    }
                },
            }
        }
    }

    table = build_sec_overview_table(
        market_snapshot={},
        company_facts=company_facts,
        currency="USD",
    )

    revenue = table[table["metric"] == "revenue"].iloc[0]

    assert revenue["value"] == 300.0
    assert revenue["concept"] == "RevenuesNetOfInterestExpense"
    assert revenue["as_of"] == "2026-03-31"
    assert revenue["completeness"] == "current"


def test_build_sec_overview_table_uses_equity_including_noncontrolling_interest():
    company_facts = {
        "facts": {
            "us-gaap": {
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {
                        "USD": [
                            {
                                "val": 400.0,
                                "end": "2026-03-31",
                                "filed": "2026-05-01",
                                "form": "10-Q",
                            }
                        ]
                    }
                },
            }
        }
    }

    table = build_sec_overview_table(
        market_snapshot={},
        company_facts=company_facts,
        currency="USD",
    )

    equity = table[table["metric"] == "stockholders_equity"].iloc[0]

    assert equity["status"] == "available"
    assert equity["value"] == 400.0
    assert equity["concept"] == "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"


def test_build_sec_overview_table_uses_alternate_current_net_income_concepts():
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 1000.0,
                                "end": "2025-12-31",
                                "filed": "2026-04-30",
                                "form": "DEF 14A",
                            }
                        ]
                    }
                },
                "NetIncomeLossAvailableToCommonStockholdersBasic": {
                    "units": {
                        "USD": [
                            {
                                "val": 300.0,
                                "end": "2026-03-31",
                                "filed": "2026-05-06",
                                "form": "10-Q",
                            }
                        ]
                    }
                },
            }
        }
    }

    table = build_sec_overview_table(
        market_snapshot={},
        company_facts=company_facts,
        currency="USD",
    )

    net_income = table[table["metric"] == "net_income"].iloc[0]

    assert net_income["value"] == 300.0
    assert net_income["concept"] == "NetIncomeLossAvailableToCommonStockholdersBasic"
    assert net_income["as_of"] == "2026-03-31"
    assert net_income["period_type"] == "quarterly"


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


def test_build_valuation_ratios_table_computes_pe_pb_ps_pfcf():
    snapshot = {"market_cap": 1_000.0, "last_price": 100.0, "shares": 10.0, "latest_price_date": "2026-05-01"}
    financials = {
        "net_income": 50.0,
        "revenue": 200.0,
        "stockholders_equity": 250.0,
        "operating_cash_flow": 80.0,
        "capex": 20.0,
    }
    table = build_valuation_ratios_table(snapshot, financials)
    ratios = {row["ratio"]: row["value"] for _, row in table.iterrows()}

    assert ratios["pe_ratio"] == pytest.approx(1_000.0 / 50.0)
    assert ratios["ps_ratio"] == pytest.approx(1_000.0 / 200.0)
    assert ratios["pb_ratio"] == pytest.approx(1_000.0 / 250.0)
    assert ratios["price_to_fcf"] == pytest.approx(1_000.0 / 60.0)


def test_build_valuation_ratios_table_omits_ratio_when_denominator_unavailable():
    snapshot = {"market_cap": 1_000.0}
    financials = {"net_income": 50.0}  # no equity, revenue, or fcf inputs
    table = build_valuation_ratios_table(snapshot, financials)
    assert set(table["ratio"]) == {"pe_ratio"}


def test_build_valuation_ratios_table_derives_market_cap_from_price_and_shares():
    snapshot = {"last_price": 100.0, "shares": 10.0}
    financials = {"net_income": 50.0}
    table = build_valuation_ratios_table(snapshot, financials)
    assert not table.empty
    assert table.iloc[0]["ratio"] == "pe_ratio"
    assert table.iloc[0]["value"] == pytest.approx(1_000.0 / 50.0)


def test_build_valuation_ratios_table_computes_ev_and_ev_to_revenue():
    snapshot = {"market_cap": 1_000.0}
    financials = {
        "long_term_debt": 200.0,
        "cash_and_equivalents": 50.0,
        "revenue": 400.0,
        "operating_income": 80.0,
        "depreciation_amortization": 20.0,
    }
    table = build_valuation_ratios_table(snapshot, financials)
    ratios = {row["ratio"]: row["value"] for _, row in table.iterrows()}
    # EV = 1000 + 200 - 50 = 1150
    assert ratios["ev_to_revenue"] == pytest.approx(1_150.0 / 400.0)
    # EBITDA = 80 + 20 = 100
    assert ratios["ev_to_ebitda"] == pytest.approx(1_150.0 / 100.0)


def test_build_valuation_ratios_table_omits_ev_when_debt_or_cash_missing():
    snapshot = {"market_cap": 1_000.0}
    financials = {"revenue": 400.0, "long_term_debt": 200.0}  # no cash → no EV
    table = build_valuation_ratios_table(snapshot, financials)
    assert "ev_to_revenue" not in set(table["ratio"])


def _make_income_company_facts_sec() -> dict:
    """Build SEC companyfacts with realistic YTD quarterly + annual Revenues entries.

    Q1=100, Q2_ytd=220 (so Q2=120), Q3_ytd=330 (so Q3=110), FY=460 (so Q4=130).
    Net income follows the same pattern.
    """
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            # Direct Q1
                            {"val": 100.0, "fy": 2025, "fp": "Q1", "start": "2025-01-01", "end": "2025-03-31", "filed": "2025-04-30", "form": "10-Q"},
                            # YTD Q2 (cumulative Jan-Jun = 220)
                            {"val": 220.0, "fy": 2025, "fp": "Q2", "start": "2025-01-01", "end": "2025-06-30", "filed": "2025-07-31", "form": "10-Q"},
                            # YTD Q3 (cumulative Jan-Sep = 330)
                            {"val": 330.0, "fy": 2025, "fp": "Q3", "start": "2025-01-01", "end": "2025-09-30", "filed": "2025-10-31", "form": "10-Q"},
                            # Annual FY (Jan-Dec = 460)
                            {"val": 460.0, "fy": 2025, "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-01-31", "form": "10-K"},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"val": 10.0, "fy": 2025, "fp": "Q1", "start": "2025-01-01", "end": "2025-03-31", "filed": "2025-04-30", "form": "10-Q"},
                            {"val": 22.0, "fy": 2025, "fp": "Q2", "start": "2025-01-01", "end": "2025-06-30", "filed": "2025-07-31", "form": "10-Q"},
                            {"val": 33.0, "fy": 2025, "fp": "Q3", "start": "2025-01-01", "end": "2025-09-30", "filed": "2025-10-31", "form": "10-Q"},
                            {"val": 46.0, "fy": 2025, "fp": "FY", "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-01-31", "form": "10-K"},
                        ]
                    }
                },
            }
        }
    }


def test_build_statement_table_ttm_sums_four_quarters():
    facts = _make_income_company_facts_sec()
    table = build_statement_table_ttm(facts, statement="income")

    assert "TTM" in table.columns
    revenue_row = table[table["metric"] == "revenue"].iloc[0]
    # Q1=100, Q2=120, Q3=110, Q4=130 → TTM=460
    assert revenue_row["TTM"] == pytest.approx(460.0)
    net_income_row = table[table["metric"] == "net_income"].iloc[0]
    # Q1=10, Q2=12, Q3=11, Q4=13 → TTM=46
    assert net_income_row["TTM"] == pytest.approx(46.0)


def test_build_statement_table_ttm_balance_returns_latest_quarterly():
    facts = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {"val": 500.0, "fy": 2025, "fp": "Q3", "end": "2025-09-30", "filed": "2025-10-01", "form": "10-Q"},
                            {"val": 600.0, "fy": 2025, "fp": "Q2", "end": "2025-06-30", "filed": "2025-07-01", "form": "10-Q"},
                        ]
                    }
                }
            }
        }
    }
    table = build_statement_table_ttm(facts, statement="balance")
    assert table.columns.tolist()[2] != "TTM"  # balance returns quarterly label, not TTM
    total_assets = table[table["metric"] == "total_assets"].iloc[0]
    value_col = [c for c in table.columns if c not in {"metric", "unit"}][0]
    assert total_assets[value_col] == pytest.approx(500.0)  # latest quarter


def test_build_statement_table_ttm_empty_on_no_data():
    facts = {"facts": {}}
    table = build_statement_table_ttm(facts, statement="income")
    assert table.empty or len([c for c in table.columns if c not in {"metric", "unit"}]) == 0


def test_build_key_financials_table_includes_derived_rows():
    from valuation.company.tables import build_key_financials_table

    facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {"USD": [{"val": 100.0, "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-01-31", "form": "10-K"}]}
                },
                "DepreciationDepletionAndAmortization": {
                    "units": {"USD": [{"val": 30.0, "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-01-31", "form": "10-K"}]}
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {"USD": [{"val": 20.0, "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-01-31", "form": "10-K"}]}
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": [{"val": 80.0, "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-01-31", "form": "10-K"}]}
                },
                "OperatingIncomeLoss": {
                    "units": {"USD": [{"val": 60.0, "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-01-31", "form": "10-K"}]}
                },
            }
        }
    }
    table = build_key_financials_table(facts)

    ebitda_row = table[table["metric"] == "ebitda"]
    assert not ebitda_row.empty
    assert ebitda_row.iloc[0]["value"] == pytest.approx(60.0 + 30.0)  # op_income + D&A = 90
    assert ebitda_row.iloc[0]["taxonomy"] == "derived"

    fcf_row = table[table["metric"] == "free_cash_flow"]
    assert not fcf_row.empty
    assert fcf_row.iloc[0]["value"] == pytest.approx(80.0 - 20.0)  # OCF - capex = 60
    assert fcf_row.iloc[0]["taxonomy"] == "derived"

    oe_row = table[table["metric"] == "owner_earnings"]
    assert not oe_row.empty
    assert oe_row.iloc[0]["value"] == pytest.approx(100.0 + 30.0 - 20.0)  # 110.0
    assert oe_row.iloc[0]["taxonomy"] == "derived"


def test_build_key_financials_table_omits_owner_earnings_when_inputs_missing():
    from valuation.company.tables import build_key_financials_table

    facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {"USD": [{"val": 100.0, "fy": 2025, "fp": "FY", "end": "2025-12-31", "filed": "2026-01-31", "form": "10-K"}]}
                },
                # D&A absent, capex absent → owner earnings should not appear
            }
        }
    }
    table = build_key_financials_table(facts)
    assert table[table["metric"] == "owner_earnings"].empty


def test_build_valuation_ratios_table_includes_price_to_owner_earnings():
    snapshot = {"market_cap": 1_000.0}
    financials = {
        "net_income": 50.0,
        "depreciation_amortization": 20.0,
        "capex": 10.0,  # owner earnings = 50 + 20 - 10 = 60
    }
    table = build_valuation_ratios_table(snapshot, financials)
    ratios = {row["ratio"]: row["value"] for _, row in table.iterrows()}
    assert "price_to_owner_earnings" in ratios
    assert ratios["price_to_owner_earnings"] == pytest.approx(1_000.0 / 60.0)


def test_extract_financials_ttm_from_company_facts_sums_quarterly_income():
    from valuation.company.tables import extract_financials_ttm_from_company_facts

    facts = _make_income_company_facts_sec()
    financials, ttm_label = extract_financials_ttm_from_company_facts(facts)

    assert ttm_label == "TTM"  # all 4 quarters available
    # Revenue TTM = Q1(100) + Q2(120) + Q3(110) + Q4(130) = 460
    assert financials.get("revenue") == pytest.approx(460.0)
    # Net income TTM = Q1(10) + Q2(12) + Q3(11) + Q4(13) = 46
    assert financials.get("net_income") == pytest.approx(46.0)


def test_extract_financials_ttm_from_company_facts_falls_back_to_annual():
    from valuation.company.tables import extract_financials_ttm_from_company_facts

    # No quarterly data → should fall back to annual
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [{"val": 200.0, "fy": 2024, "fp": "FY", "end": "2024-12-31", "filed": "2025-01-31", "form": "10-K"}]
                    }
                }
            }
        }
    }
    financials, ttm_label = extract_financials_ttm_from_company_facts(facts)
    # No quarterly quarters → label would be e.g. "0Q TTM" or None; falls back to annual
    assert financials.get("revenue") == pytest.approx(200.0)
