import pandas as pd

from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_statement_table
from valuation.company.statements import build_statement_table


def test_statement_matrix_flow_ytd_only_derives_quarters_and_q4():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 400.0,
                                "fy": 2025,
                                "fp": "FY",
                                "start": "2024-10-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-K",
                            },
                            {
                                "val": 270.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2024-10-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 170.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2024-10-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 80.0,
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
        [CompanyFactQuery("revenue", (("us-gaap", "Revenues"),))],
        period="quarterly",
        value_kind="duration",
        limit=4,
    )

    assert list(frame.columns) == ["metric", "unit", "2025 Q3", "2025 Q2", "2025 Q1", "2024 Q4"]
    assert frame.iloc[0]["2025 Q3"] == 130.0
    assert frame.iloc[0]["2025 Q2"] == 100.0
    assert frame.iloc[0]["2025 Q1"] == 90.0
    assert frame.iloc[0]["2024 Q4"] == 80.0


def test_statement_matrix_direct_quarter_only_ratio_and_average_preserve_values():
    company_facts = {
        "facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [
                            {
                                "val": 6.2,
                                "fy": 2025,
                                "fp": "FY",
                                "start": "2024-10-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-K",
                            },
                            {
                                "val": 1.7,
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
                },
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "val": 1000.0,
                                "fy": 2025,
                                "fp": "FY",
                                "start": "2024-10-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-K",
                            },
                            {
                                "val": 990.0,
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
                },
            }
        }
    }

    eps_frame = company_facts_to_statement_table(
        company_facts,
        [
            CompanyFactQuery(
                "diluted_eps",
                (("us-gaap", "EarningsPerShareDiluted"),),
                unit="USD/shares",
                quarterly_value_kind="direct",
            )
        ],
        period="quarterly",
        value_kind="duration",
        limit=4,
    )
    shares_frame = company_facts_to_statement_table(
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

    assert eps_frame.iloc[0]["2025 Q1"] == 1.7
    assert shares_frame.iloc[0]["2025 Q1"] == 990.0
    assert "2025 Q4" not in eps_frame.columns
    assert "2025 Q4" not in shares_frame.columns


def test_statement_matrix_instant_balance_sheet_uses_period_end_snapshots():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "val": 310.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 300.0,
                                "fy": 2025,
                                "fp": "Q1",
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
        [CompanyFactQuery("total_assets", (("us-gaap", "Assets"),))],
        period="quarterly",
        value_kind="instant",
        limit=2,
    )

    assert list(frame.columns) == ["metric", "unit", "2025 Q1", "2024 Q4"]
    assert frame.iloc[0]["2025 Q1"] == 310.0
    assert frame.iloc[0]["2024 Q4"] == 300.0


def test_statement_matrix_berkshire_sparse_income_stays_blank_without_guessing():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 95.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                            }
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 12.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
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
            CompanyFactQuery("operating_income", (("us-gaap", "OperatingIncomeLoss"),)),
            CompanyFactQuery(
                "diluted_shares",
                (("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),),
                unit="shares",
                quarterly_value_kind="direct",
            ),
            CompanyFactQuery("net_income", (("us-gaap", "NetIncomeLoss"),)),
        ],
        period="quarterly",
        value_kind="duration",
        limit=1,
    )

    assert list(frame.columns) == ["metric", "unit", "2025 Q1"]
    assert frame.iloc[0]["2025 Q1"] == 95.0
    assert pd.isna(frame.iloc[1]["2025 Q1"])
    assert pd.isna(frame.iloc[2]["2025 Q1"])
    assert frame.iloc[3]["2025 Q1"] == 12.0


def test_statement_matrix_financial_institution_uses_bank_style_revenue_and_pretax():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 180.0,
                                "fy": 2025,
                                "fp": "FY",
                                "start": "2025-01-01",
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
                                "val": 130.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-01-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 45.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-07-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-Q",
                                "frame": "CY2025Q3",
                            },
                            {
                                "val": 85.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-01-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 40.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-04-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                                "frame": "CY2025Q2",
                            },
                            {
                                "val": 45.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1",
                            },
                        ]
                    }
                },
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": {
                    "units": {
                        "USD": [
                            {
                                "val": 60.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-01-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 20.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-07-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-Q",
                                "frame": "CY2025Q3",
                            },
                            {
                                "val": 38.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-01-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 18.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-04-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                                "frame": "CY2025Q2",
                            },
                            {
                                "val": 20.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1",
                            },
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 15.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-07-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-Q",
                                "frame": "CY2025Q3",
                            }
                        ]
                    }
                },
            }
        }
    }

    frame = build_statement_table(
        company_facts,
        statement="income",
        period="quarterly",
        limit=3,
    )

    revenue_row = frame[frame["metric"] == "revenue"].iloc[0]
    pretax_row = frame[frame["metric"] == "pretax_income"].iloc[0]
    net_income_row = frame[frame["metric"] == "net_income"].iloc[0]

    assert revenue_row["2025 Q3"] == 45.0
    assert revenue_row["2025 Q2"] == 40.0
    assert revenue_row["2025 Q1"] == 45.0
    assert pretax_row["2025 Q3"] == 20.0
    assert pretax_row["2025 Q2"] == 18.0
    assert pretax_row["2025 Q1"] == 20.0
    assert net_income_row["2025 Q3"] == 15.0


def test_statement_matrix_build_statement_table_drops_all_missing_rows():
    company_facts = {
        "facts": {
            "us-gaap": {
                "RevenuesNetOfInterestExpense": {
                    "units": {
                        "USD": [
                            {
                                "val": 45.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1",
                            }
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 15.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1",
                            }
                        ]
                    }
                },
            }
        }
    }

    frame = build_statement_table(
        company_facts,
        statement="income",
        period="quarterly",
        limit=1,
    )

    assert "gross_profit" not in set(frame["metric"])
    assert "operating_income" not in set(frame["metric"])
    assert "revenue" in set(frame["metric"])
    assert "net_income" in set(frame["metric"])


def test_statement_matrix_industrial_uses_alternate_net_income_concepts():
    company_facts = {
        "facts": {
            "us-gaap": {
                "ProfitLoss": {
                    "units": {
                        "USD": [
                            {
                                "val": 60.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-01-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 22.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-07-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-Q",
                                "frame": "CY2025Q3",
                            },
                            {
                                "val": 38.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-01-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 18.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-04-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                                "frame": "CY2025Q2",
                            },
                            {
                                "val": 20.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1",
                            },
                        ]
                    }
                },
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 100.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-01-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 35.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2025-07-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-Q",
                                "frame": "CY2025Q3",
                            },
                            {
                                "val": 65.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-01-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                            },
                            {
                                "val": 30.0,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-04-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                                "frame": "CY2025Q2",
                            },
                            {
                                "val": 35.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1",
                            },
                        ]
                    }
                },
            }
        }
    }

    frame = build_statement_table(
        company_facts,
        statement="income",
        period="quarterly",
        limit=3,
    )

    net_income_row = frame[frame["metric"] == "net_income"].iloc[0]
    assert net_income_row["2025 Q3"] == 22.0
    assert net_income_row["2025 Q2"] == 18.0
    assert net_income_row["2025 Q1"] == 20.0


def test_statement_matrix_balance_uses_alternate_equity_and_debt_concepts():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "val": 500.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1I",
                            }
                        ]
                    }
                },
                "Liabilities": {
                    "units": {
                        "USD": [
                            {
                                "val": 300.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1I",
                            }
                        ]
                    }
                },
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {
                        "USD": [
                            {
                                "val": 200.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1I",
                            }
                        ]
                    }
                },
                "LongTermDebtAndCapitalLeaseObligations": {
                    "units": {
                        "USD": [
                            {
                                "val": 120.0,
                                "fy": 2025,
                                "fp": "Q1",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1I",
                            }
                        ]
                    }
                },
            }
        }
    }

    frame = build_statement_table(
        company_facts,
        statement="balance",
        period="quarterly",
        limit=1,
    )

    stockholders_equity_row = frame[frame["metric"] == "stockholders_equity"].iloc[0]
    long_term_debt_row = frame[frame["metric"] == "long_term_debt"].iloc[0]

    assert stockholders_equity_row["2025 Q1"] == 200.0
    assert long_term_debt_row["2025 Q1"] == 120.0


def test_statement_matrix_income_fills_year_end_diluted_share_and_eps_gaps():
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
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
                                "val": 75.0,
                                "fy": 2025,
                                "fp": "Q3",
                                "start": "2024-10-01",
                                "end": "2025-06-30",
                                "filed": "2025-08-01",
                                "form": "10-Q",
                            },
                        ]
                    }
                },
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [
                            {
                                "val": 1.5,
                                "fy": 2025,
                                "fp": "Q2",
                                "start": "2025-01-01",
                                "end": "2025-03-31",
                                "filed": "2025-05-01",
                                "form": "10-Q",
                                "frame": "CY2025Q1",
                            }
                        ]
                    }
                },
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "val": 25.0,
                                "fy": 2025,
                                "fp": "FY",
                                "start": "2024-10-01",
                                "end": "2025-09-30",
                                "filed": "2025-11-01",
                                "form": "10-K",
                            }
                        ]
                    }
                },
            }
        }
    }

    frame = build_statement_table(
        company_facts,
        statement="income",
        period="quarterly",
        limit=4,
    )

    diluted_eps_row = frame[frame["metric"] == "diluted_eps"].iloc[0]
    diluted_shares_row = frame[frame["metric"] == "diluted_shares"].iloc[0]

    assert diluted_shares_row["2025 Q3"] == 25.0
    assert diluted_eps_row["2025 Q3"] == 1.8
