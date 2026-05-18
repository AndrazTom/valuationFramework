import pandas as pd

from valuation.company.yahoo_statements import (
    build_yahoo_key_financials_table,
    build_yahoo_statement_table,
    build_yahoo_statement_table_ttm,
)


def test_build_yahoo_statement_table_maps_income_rows():
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Total Revenue": 100.0,
                "Operating Income": 20.0,
                "Pretax Income": 18.0,
                "Net Income": 14.0,
                "Diluted EPS": 1.4,
                "Diluted Average Shares": 10.0,
            },
            pd.Timestamp("2024-12-31"): {
                "Total Revenue": 90.0,
                "Operating Income": 18.0,
                "Pretax Income": 16.0,
                "Net Income": 12.0,
                "Diluted EPS": 1.2,
                "Diluted Average Shares": 10.0,
            },
        }
    )

    table = build_yahoo_statement_table(
        frame,
        statement="income",
        period="annual",
        limit=2,
    )

    revenue_row = table[table["metric"] == "revenue"].iloc[0]
    diluted_shares_row = table[table["metric"] == "diluted_shares"].iloc[0]

    assert list(table.columns) == ["metric", "unit", "FY 2025", "FY 2024"]
    assert revenue_row["FY 2025"] == 100.0
    assert diluted_shares_row["FY 2025"] == 10.0


def test_build_yahoo_statement_table_filters_quarter_range():
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {"Total Revenue": 100.0},
            pd.Timestamp("2025-09-30"): {"Total Revenue": 90.0},
            pd.Timestamp("2025-06-30"): {"Total Revenue": 80.0},
        }
    )

    table = build_yahoo_statement_table(
        frame,
        statement="income",
        period="quarterly",
        limit=3,
        start_year=2025,
        start_quarter=3,
        end_year=2025,
        end_quarter=4,
    )

    assert list(table.columns) == ["metric", "unit", "2025 Q4", "2025 Q3"]


def test_build_yahoo_key_financials_table_uses_latest_annual_values():
    income = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Total Revenue": 100.0, "Net Income": 14.0}})
    balance = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Total Assets": 250.0}})
    cashflow = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Operating Cash Flow": 30.0}})

    table = build_yahoo_key_financials_table(
        income_frame=income,
        balance_frame=balance,
        cashflow_frame=cashflow,
    )

    assert set(table["metric"]) == {"revenue", "net_income", "total_assets", "operating_cash_flow"}


def test_build_yahoo_statement_table_avoids_combined_cash_for_short_term_investments():
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Cash And Cash Equivalents": 10.0,
                "Cash Cash Equivalents And Short Term Investments": 16.0,
                "Other Short Term Investments": 6.0,
            },
        }
    )

    table = build_yahoo_statement_table(
        frame,
        statement="balance",
        period="annual",
        limit=1,
    )

    short_term_row = table[table["metric"] == "short_term_investments"].iloc[0]

    assert short_term_row["FY 2025"] == 6.0


def test_build_yahoo_statement_table_uses_available_for_sale_securities_as_short_term_investment_fallback():
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Available For Sale Securities": 25.0,
            },
        }
    )

    table = build_yahoo_statement_table(
        frame,
        statement="balance",
        period="annual",
        limit=1,
    )

    short_term_row = table[table["metric"] == "short_term_investments"].iloc[0]

    assert short_term_row["FY 2025"] == 25.0


def test_build_yahoo_statement_table_avoids_total_debt_as_long_term_debt_fallback():
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Total Debt": 50.0,
            },
        }
    )

    table = build_yahoo_statement_table(
        frame,
        statement="balance",
        period="annual",
        limit=1,
    )

    assert "long_term_debt" not in set(table["metric"])


def test_build_yahoo_statement_table_uses_long_term_debt_and_capital_lease_obligation():
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Long Term Debt And Capital Lease Obligation": 42.0,
                "Total Debt": 50.0,
            },
        }
    )

    table = build_yahoo_statement_table(
        frame,
        statement="balance",
        period="annual",
        limit=1,
    )

    long_term_debt_row = table[table["metric"] == "long_term_debt"].iloc[0]

    assert long_term_debt_row["FY 2025"] == 42.0


def test_build_yahoo_statement_table_does_not_treat_end_cash_position_as_change_in_cash():
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Operating Cash Flow": 30.0,
                "End Cash Position": 500.0,
            },
        }
    )

    table = build_yahoo_statement_table(
        frame,
        statement="cashflow",
        period="annual",
        limit=1,
    )

    assert set(table["metric"]) == {"operating_cash_flow"}


def test_build_yahoo_statement_table_bank_income_no_gross_profit():
    """Bank income frame with no gross_profit emits revenue/operating_income/net_income only."""
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Total Revenue": 10_000.0,
                "Operating Income": 3_000.0,
                "Pretax Income": 2_800.0,
                "Net Income": 2_100.0,
            }
        }
    )
    table = build_yahoo_statement_table(frame, statement="income", period="annual", limit=1)
    metrics = set(table["metric"])
    assert "revenue" in metrics
    assert "gross_profit" not in metrics
    assert "net_income" in metrics


def test_build_yahoo_statement_table_net_revenue_fallback():
    """Net Revenue label maps to revenue when Total Revenue is absent."""
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Net Revenue": 8_500.0,
                "Net Income": 1_200.0,
            }
        }
    )
    table = build_yahoo_statement_table(frame, statement="income", period="annual", limit=1)
    revenue_row = table[table["metric"] == "revenue"].iloc[0]
    assert revenue_row["FY 2025"] == 8_500.0


def test_build_yahoo_statement_table_bank_balance_no_current_items():
    """Bank balance sheet with no current_assets or current_liabilities emits correctly."""
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Cash And Cash Equivalents": 50.0,
                "Total Assets": 1_200.0,
                "Total Liabilities Net Minority Interest": 1_000.0,
                "Common Stock Equity": 200.0,
            }
        }
    )
    table = build_yahoo_statement_table(frame, statement="balance", period="annual", limit=1)
    metrics = set(table["metric"])
    assert "total_assets" in metrics
    assert "stockholders_equity" in metrics
    assert "current_assets" not in metrics
    assert "current_liabilities" not in metrics


def test_build_yahoo_statement_table_ttm_partial_quarters_does_not_crash():
    """TTM sums correctly when some quarters are missing some metrics."""
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {"Total Revenue": 300.0, "Net Income": 30.0},
            pd.Timestamp("2025-09-30"): {"Total Revenue": 280.0},
            pd.Timestamp("2025-06-30"): {"Total Revenue": 260.0, "Net Income": 25.0},
            pd.Timestamp("2025-03-31"): {"Total Revenue": 250.0, "Net Income": 22.0},
        }
    )
    table = build_yahoo_statement_table_ttm(frame, statement="income")
    assert not table.empty
    revenue_row = table[table["metric"] == "revenue"].iloc[0]
    assert revenue_row.iloc[2] == 300.0 + 280.0 + 260.0 + 250.0


def test_build_yahoo_key_financials_table_common_stock_equity_fallback():
    """stockholders_equity maps from Common Stock Equity when Stockholders Equity is absent."""
    income = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Total Revenue": 100.0, "Net Income": 14.0}})
    balance = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Total Assets": 400.0, "Common Stock Equity": 120.0}})
    cashflow = pd.DataFrame({pd.Timestamp("2025-12-31"): {"Operating Cash Flow": 25.0}})
    table = build_yahoo_key_financials_table(
        income_frame=income,
        balance_frame=balance,
        cashflow_frame=cashflow,
    )
    assert "stockholders_equity" in set(table["metric"])
