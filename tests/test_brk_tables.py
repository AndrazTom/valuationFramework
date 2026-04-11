import pandas as pd

from valuation.notation import B, M
from valuation.brk.service import BrkLiquidityFiling, BrkSegmentFiling
from valuation.brk.segments import BrkSegmentReportSet
from valuation.brk.tables import (
    build_13f_summary_table,
    build_13f_live_price_summary_table,
    build_key_facts_table,
    build_liquidity_bridge_table,
    build_liquidity_summary_table,
    build_top_level_operating_segments_summary_table,
    build_share_class_table,
    build_top_holdings_live_table,
    build_top_holdings_table,
    filter_core_filings_table,
)
from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_table


class FakeYahooClient:
    def fetch_price_snapshot(self, ticker):
        return {
            "ticker": ticker,
            "last_price": {"AAPL": 200.0, "AXP": 300.0}[ticker],
            "latest_price_date": "2026-04-09",
            "source": "yfinance",
        }


def test_build_share_class_table_derives_implied_brk_a_price():
    frame = build_share_class_table({"last_price": 500.0})

    assert frame.iloc[2]["value"] == 1500
    assert frame.iloc[4]["value"] == 750000.0


def test_company_facts_to_table_picks_latest_filed_value():
    company_facts = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "val": 100.0,
                                "filed": "2025-02-20",
                                "end": "2024-12-31",
                                "form": "10-K",
                            },
                            {
                                "val": 110.0,
                                "filed": "2025-05-05",
                                "end": "2025-03-31",
                                "form": "10-Q",
                            },
                        ]
                    }
                }
            }
        }
    }

    frame = company_facts_to_table(
        company_facts,
        [CompanyFactQuery(metric="assets", candidates=(("us-gaap", "Assets"),))],
    )

    assert frame.iloc[0]["value"] == 110.0
    assert frame.iloc[0]["form"] == "10-Q"


def test_build_key_facts_table_leaves_missing_metrics_blank():
    company_facts = {
        "facts": {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {
                        "USD": [
                            {
                                "val": 42.0,
                                "filed": "2025-05-05",
                                "end": "2025-03-31",
                                "form": "10-Q",
                            }
                        ]
                    }
                }
            }
        }
    }

    frame = build_key_facts_table(company_facts)

    assert "cash_and_equivalents" in set(frame["metric"])
    revenue_row = frame[frame["metric"] == "revenue"].iloc[0]
    assert pd.isna(revenue_row["value"])


def test_filter_core_filings_table_keeps_relevant_forms():
    frame = pd.DataFrame(
        [
            {"form": "4", "filing_date": "2026-01-01"},
            {"form": "10-Q", "filing_date": "2026-01-02"},
            {"form": "8-K", "filing_date": "2026-01-03"},
        ]
    )

    filtered = filter_core_filings_table(frame, limit=10)

    assert list(filtered["form"]) == ["10-Q", "8-K"]


def test_build_13f_summary_table():
    holdings = pd.DataFrame(
        [
            {"issuer": "A", "class_title": "COM", "cusip": "1", "value_usd": 1000},
            {"issuer": "A", "class_title": "COM", "cusip": "1", "value_usd": 500},
            {"issuer": "B", "class_title": "COM", "cusip": "2", "value_usd": 2500},
        ]
    )

    frame = build_13f_summary_table(
        filing_date="2026-02-17",
        accession_number="0001193125-26-054580",
        information_table_filename="50240.xml",
        holdings=holdings,
    )

    assert frame.iloc[3]["value"] == 2
    assert frame.iloc[4]["value"] == 4000


def test_build_top_holdings_table():
    holdings = pd.DataFrame(
        [
            {"issuer": "A", "value_usd": 1000},
            {"issuer": "B", "value_usd": 900},
            {"issuer": "C", "value_usd": 800},
        ]
    )

    frame = build_top_holdings_table(holdings, limit=2)

    assert list(frame["issuer"]) == ["A", "B"]


def test_build_top_holdings_live_table():
    holdings = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "class_title": "COM",
                "cusip": "037833100",
                "value_usd": 1000,
                "shares_or_principal": 10,
            },
            {
                "security_id": "cusip:025816109",
                "issuer": "AMERICAN EXPRESS CO",
                "class_title": "COM",
                "cusip": "025816109",
                "value_usd": 900,
                "shares_or_principal": 20,
            },
        ]
    )
    reference = pd.DataFrame(
        [
            {"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"},
            {"security_id": "cusip:025816109", "ticker": "AXP", "exchange": "NYSE"},
        ]
    )

    frame = build_top_holdings_live_table(
        holdings,
        reference,
        limit=2,
        yahoo_client=FakeYahooClient(),
    )

    assert list(frame["ticker"]) == ["AAPL", "AXP"]
    assert list(frame["reported_value_usd"]) == [1000, 900]


def test_build_13f_live_price_summary_table():
    holdings = pd.DataFrame(
        [
            {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 1000, "shares_or_principal": 10},
            {"security_id": "cusip:025816109", "issuer": "AMERICAN EXPRESS CO", "class_title": "COM", "cusip": "025816109", "value_usd": 900, "shares_or_principal": 20},
        ]
    )
    reference = pd.DataFrame(
        [{"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"}]
    )

    summary = build_13f_live_price_summary_table(
        holdings,
        reference,
        yahoo_client=FakeYahooClient(),
    )

    assert summary[summary["field"] == "positions_total"].iloc[0]["value"] == 2
    assert summary[summary["field"] == "positions_with_live_price"].iloc[0]["value"] == 1
    assert summary[summary["field"] == "market_value_live_resolved_usd"].iloc[0]["value"] == 2000.0


def test_build_liquidity_bridge_table():
    filings = [
        BrkLiquidityFiling(
            filing_date="2026-03-02",
            accession_number="0001",
            form="10-K",
            balance_sheet=pd.DataFrame(
                [
                    ["Cash and cash equivalents", "", "47,719", "44,333"],
                    ["Short-term investments in U.S. Treasury Bills", "", "321,434", "286,472"],
                    ["Investments in fixed maturity securities", "", "17,816", "15,364"],
                ],
                columns=[
                    "Consolidated Balance Sheets",
                    "Consolidated Balance Sheets",
                    "Dec. 31, 2025",
                    "Dec. 31, 2024",
                ],
            ),
        )
    ]

    frame = build_liquidity_bridge_table(filings)

    assert set(frame["metric"]) == {
        "cash_and_equivalents",
        "short_term_us_treasury_bills",
        "fixed_maturity_securities",
    }
    assert frame[frame["metric"] == "short_term_us_treasury_bills"].iloc[0]["value_usd"] == 321434 * M


def test_build_liquidity_summary_table():
    bridge = pd.DataFrame(
        [
            {"filing_date": "2026-03-02", "form": "10-K", "period_end": "2025-12-31", "accession_number": "0001", "metric": "cash_and_equivalents", "value_usd": 47.719 * B},
            {"filing_date": "2026-03-02", "form": "10-K", "period_end": "2025-12-31", "accession_number": "0001", "metric": "short_term_us_treasury_bills", "value_usd": 321.434 * B},
            {"filing_date": "2026-03-02", "form": "10-K", "period_end": "2025-12-31", "accession_number": "0001", "metric": "fixed_maturity_securities", "value_usd": 17.816 * B},
        ]
    )

    summary = build_liquidity_summary_table(bridge)

    assert summary.iloc[0]["core_liquidity_total_usd"] == 369.153 * B
    assert summary.iloc[0]["liquid_investments_total_usd"] == 386.969 * B


def test_build_top_level_operating_segments_summary_table_history():
    filings = [
        BrkSegmentFiling(
            filing_date="2026-03-02",
            accession_number="0001",
            form="10-K",
            reports=BrkSegmentReportSet(
                filing_date="2026-03-02",
                accession_number="0001",
                earnings_detail=pd.DataFrame(
                    [
                        {"report": "earnings", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Revenues", "duration_months": 12, "period_end": "2025-12-31", "value": 23 * M},
                    ]
                ),
                reconciliation_detail=pd.DataFrame(),
                additional_detail=pd.DataFrame(),
            ),
        )
    ]
    summary = build_top_level_operating_segments_summary_table(filings, period="annual")

    assert summary.iloc[0]["filing_date"] == "2026-03-02"
    assert summary.iloc[0]["period_end"] == "2025-12-31"
    assert summary.iloc[0]["revenues_usd"] == 23 * M
