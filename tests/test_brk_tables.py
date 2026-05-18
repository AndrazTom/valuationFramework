import pandas as pd
import pytest

from valuation.notation import B, M
from valuation.brk.service import (
    Brk13FBundle,
    BrkLiquidityBundle,
    BrkLiquidityFiling,
    BrkOverviewBundle,
    BrkSegmentFiling,
    BrkSegmentsBundle,
    BrkValuationBundle,
)
from valuation.brk.segments import BrkSegmentReportSet
from valuation.brk.tables import (
    build_13f_summary_table,
    build_13f_history_summary_table,
    build_13f_holdings_history_table,
    build_13f_issuer_change_summary_table,
    build_13f_portfolio_change_summary_table,
    build_13f_live_price_summary_table,
    build_balance_sheet_context_table,
    build_brk_valuation_context_table,
    build_segment_period_sections,
    build_holdings_vs_brk_price_change_table,
    build_key_facts_table,
    build_liquidity_bridge_table,
    build_liquidity_detail_table,
    build_liquidity_summary_table,
    build_market_implied_sotp_bridge_table,
    build_market_anchor_table,
    build_brk_operating_reverse_dcf_table,
    build_operating_business_context_table,
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
            "last_price": {"AAPL": 200.0, "AXP": 300.0, "BRK-B": 500.0}[ticker],
            "previous_close": {"AAPL": 180.0, "AXP": 270.0, "BRK-B": 480.0}[ticker],
            "latest_price_date": "2026-04-09",
            "market_cap": {"AAPL": None, "AXP": None, "BRK-B": 1000.0}[ticker],
            "source": "yfinance",
        }

    def fetch_history(self, ticker, period="1mo", interval="1d"):
        return pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2026-01-02", "2026-02-02", "2026-03-02", "2026-04-09"]
                ),
                "close": {
                    "AAPL": [100.0, 120.0, 150.0, 200.0],
                    "AXP": [200.0, 220.0, 260.0, 300.0],
                    "BRK-B": [400.0, 430.0, 470.0, 500.0],
                }[ticker],
            }
        )


class EmptyYahooClient:
    def fetch_price_snapshot(self, ticker):
        return {"ticker": ticker, "last_price": None, "latest_price_date": None, "source": "yfinance"}

    def fetch_history(self, ticker, period="1mo", interval="1d"):
        return pd.DataFrame(columns=["date", "close"])


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


def test_build_13f_history_summary_table():
    filings = [
        Brk13FBundle(
            company=None,
            filing_date="2026-02-14",
            report_date="2025-12-31",
            accession_number="0002",
            information_table_filename="info.xml",
            holdings=pd.DataFrame(
                [
                    {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 1000, "shares_or_principal": 10},
                    {"security_id": "cusip:025816109", "issuer": "AMERICAN EXPRESS CO", "class_title": "COM", "cusip": "025816109", "value_usd": 900, "shares_or_principal": 20},
                ]
            ),
        ),
        Brk13FBundle(
            company=None,
            filing_date="2025-11-14",
            report_date="2025-09-30",
            accession_number="0004",
            information_table_filename="info.xml",
            holdings=pd.DataFrame(
                [
                    {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 800, "shares_or_principal": 8},
                ]
            ),
        ),
    ]

    frame = build_13f_history_summary_table(filings)

    assert list(frame["accession_number"]) == ["0002", "0004"]
    assert list(frame["holding_count"]) == [2, 1]
    assert frame.iloc[0]["reported_value_usd"] == 1900
    assert frame.iloc[0]["top_holding"] == "APPLE INC"
    assert frame.iloc[0]["top_holding_weight"] == pytest.approx(1000 / 1900)


def test_build_13f_holdings_history_table_tracks_latest_top_holdings():
    filings = [
        Brk13FBundle(
            company=None,
            filing_date="2026-02-14",
            report_date="2025-12-31",
            accession_number="0002",
            information_table_filename="info.xml",
            holdings=pd.DataFrame(
                [
                    {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 1000, "shares_or_principal": 10},
                    {"security_id": "cusip:025816109", "issuer": "AMERICAN EXPRESS CO", "class_title": "COM", "cusip": "025816109", "value_usd": 900, "shares_or_principal": 20},
                ]
            ),
        ),
        Brk13FBundle(
            company=None,
            filing_date="2025-11-14",
            report_date="2025-09-30",
            accession_number="0004",
            information_table_filename="info.xml",
            holdings=pd.DataFrame(
                [
                    {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 800, "shares_or_principal": 8},
                    {"security_id": "cusip:025816109", "issuer": "AMERICAN EXPRESS CO", "class_title": "COM", "cusip": "025816109", "value_usd": 950, "shares_or_principal": 22},
                ]
            ),
        ),
    ]

    frame = build_13f_holdings_history_table(filings, limit=2)
    apple_latest = frame[(frame["issuer"] == "APPLE INC") & (frame["filing_date"] == "2026-02-14")].iloc[0]
    axp_latest = frame[(frame["issuer"] == "AMERICAN EXPRESS CO") & (frame["filing_date"] == "2026-02-14")].iloc[0]

    assert list(frame["latest_rank"].drop_duplicates()) == [1, 2]
    assert apple_latest["value_change_from_prior_filing_usd"] == 200.0
    assert apple_latest["shares_change_from_prior_filing"] == 2.0
    assert axp_latest["value_change_from_prior_filing_usd"] == -50.0


def _make_filing(filing_date, report_date, accession, holdings_rows):
    return Brk13FBundle(
        company=None,
        filing_date=filing_date,
        report_date=report_date,
        accession_number=accession,
        information_table_filename="info.xml",
        holdings=pd.DataFrame(holdings_rows),
    )


def test_build_13f_issuer_change_summary_table_classifies_changes():
    current = _make_filing(
        "2026-02-14", "2025-12-31", "0002",
        [
            # Increased: more shares than prior
            {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 1200, "shares_or_principal": 15},
            # Decreased: fewer shares than prior
            {"security_id": "cusip:025816109", "issuer": "AMERICAN EXPRESS CO", "class_title": "COM", "cusip": "025816109", "value_usd": 700, "shares_or_principal": 15},
            # New: only in current
            {"security_id": "cusip:NEWCUSIP1", "issuer": "NEW CO", "class_title": "COM", "cusip": "NEWCUSIP1", "value_usd": 500, "shares_or_principal": 50},
        ],
    )
    prior = _make_filing(
        "2025-11-14", "2025-09-30", "0004",
        [
            {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 800, "shares_or_principal": 8},
            {"security_id": "cusip:025816109", "issuer": "AMERICAN EXPRESS CO", "class_title": "COM", "cusip": "025816109", "value_usd": 950, "shares_or_principal": 22},
            # Eliminated: only in prior
            {"security_id": "cusip:OLDCUSIP1", "issuer": "OLD CO", "class_title": "COM", "cusip": "OLDCUSIP1", "value_usd": 300, "shares_or_principal": 10},
        ],
    )

    frame = build_13f_issuer_change_summary_table([current, prior])

    assert set(frame["cusip"]) == {"037833100", "025816109", "NEWCUSIP1", "OLDCUSIP1"}
    assert frame[frame["cusip"] == "037833100"].iloc[0]["change_type"] == "increased"
    assert frame[frame["cusip"] == "025816109"].iloc[0]["change_type"] == "decreased"
    assert frame[frame["cusip"] == "NEWCUSIP1"].iloc[0]["change_type"] == "new"
    assert frame[frame["cusip"] == "OLDCUSIP1"].iloc[0]["change_type"] == "eliminated"


def test_build_13f_issuer_change_summary_table_share_and_value_columns():
    current = _make_filing(
        "2026-02-14", "2025-12-31", "0002",
        [{"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 1200, "shares_or_principal": 15}],
    )
    prior = _make_filing(
        "2025-11-14", "2025-09-30", "0004",
        [{"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 800, "shares_or_principal": 8}],
    )
    frame = build_13f_issuer_change_summary_table([current, prior])
    row = frame.iloc[0]

    assert row["prior_shares"] == pytest.approx(8.0)
    assert row["current_shares"] == pytest.approx(15.0)
    assert row["share_change"] == pytest.approx(7.0)
    assert row["share_change_pct"] == pytest.approx(7.0 / 8.0)
    assert row["prior_value_usd"] == pytest.approx(800.0)
    assert row["current_value_usd"] == pytest.approx(1200.0)
    assert row["value_change_usd"] == pytest.approx(400.0)
    assert row["value_change_pct"] == pytest.approx(400.0 / 800.0)


def test_build_13f_issuer_change_summary_table_sort_order():
    """New positions appear before increased before decreased before eliminated."""
    # NEW: C (only in current)
    # INCREASED: A (5 → 10)
    # DECREASED: B (100 → 50)
    # ELIMINATED: D (only in prior)
    current = _make_filing(
        "2026-02-14", "2025-12-31", "0002",
        [
            {"security_id": "c:A", "issuer": "A", "class_title": "COM", "cusip": "A", "value_usd": 100, "shares_or_principal": 10},
            {"security_id": "c:B", "issuer": "B", "class_title": "COM", "cusip": "B", "value_usd": 100, "shares_or_principal": 50},
            {"security_id": "c:C", "issuer": "C", "class_title": "COM", "cusip": "C", "value_usd": 100, "shares_or_principal": 5},
        ],
    )
    prior = _make_filing(
        "2025-11-14", "2025-09-30", "0004",
        [
            {"security_id": "c:A", "issuer": "A", "class_title": "COM", "cusip": "A", "value_usd": 90, "shares_or_principal": 5},
            {"security_id": "c:B", "issuer": "B", "class_title": "COM", "cusip": "B", "value_usd": 80, "shares_or_principal": 100},
            {"security_id": "c:D", "issuer": "D", "class_title": "COM", "cusip": "D", "value_usd": 50, "shares_or_principal": 20},
        ],
    )
    frame = build_13f_issuer_change_summary_table([current, prior])
    types = list(frame["change_type"])
    assert types.index("new") < types.index("increased")
    assert types.index("increased") < types.index("decreased")
    assert types.index("decreased") < types.index("eliminated")


def test_build_13f_issuer_change_summary_table_price_and_share_decomposition():
    """Value change decomposes into share-driven and price-driven components."""
    # prior: 8 shares at $100 each = $800
    # current: 15 shares at $80 each = $1200
    # prior_price = 800/8 = 100, current_price = 1200/15 = 80
    # share_driven = (15 - 8) * 100 = 700
    # price_driven = 8 * (80 - 100) = -160
    # sum = 540 ≈ value_change (400) + cross_term (7 * -20 = -140), so 700 - 160 = 540 != 400
    # Actually: share_driven + price_driven = 700 - 160 = 540; cross term = (15-8)*(80-100) = -140
    # So 540 - 140 = 400 which is the correct total value change
    current = _make_filing(
        "2026-02-14", "2025-12-31", "0002",
        [{"security_id": "cusip:A", "issuer": "ALPHA", "class_title": "COM", "cusip": "A", "value_usd": 1200, "shares_or_principal": 15}],
    )
    prior = _make_filing(
        "2025-11-14", "2025-09-30", "0004",
        [{"security_id": "cusip:A", "issuer": "ALPHA", "class_title": "COM", "cusip": "A", "value_usd": 800, "shares_or_principal": 8}],
    )
    frame = build_13f_issuer_change_summary_table([current, prior])
    row = frame.iloc[0]

    prior_price = 800.0 / 8.0   # = 100
    current_price = 1200.0 / 15.0  # = 80

    assert row["share_driven_value_change_usd"] == pytest.approx((15 - 8) * prior_price)
    assert row["price_driven_value_change_usd"] == pytest.approx(8 * (current_price - prior_price))


def test_build_13f_issuer_change_summary_table_decomposition_none_for_new_eliminated():
    """New and eliminated positions have no price/share decomposition."""
    current = _make_filing(
        "2026-02-14", "2025-12-31", "0002",
        [{"security_id": "c:NEW", "issuer": "NEW", "class_title": "COM", "cusip": "N", "value_usd": 100, "shares_or_principal": 10}],
    )
    prior = _make_filing(
        "2025-11-14", "2025-09-30", "0004",
        [{"security_id": "c:OLD", "issuer": "OLD", "class_title": "COM", "cusip": "O", "value_usd": 100, "shares_or_principal": 10}],
    )
    frame = build_13f_issuer_change_summary_table([current, prior])
    by_type = {row["change_type"]: row for _, row in frame.iterrows()}

    assert pd.isna(by_type["new"]["share_driven_value_change_usd"])
    assert pd.isna(by_type["new"]["price_driven_value_change_usd"])
    assert pd.isna(by_type["eliminated"]["share_driven_value_change_usd"])
    assert pd.isna(by_type["eliminated"]["price_driven_value_change_usd"])


def test_build_13f_issuer_change_summary_table_requires_two_filings():
    single = _make_filing(
        "2026-02-14", "2025-12-31", "0002",
        [{"security_id": "c:A", "issuer": "A", "class_title": "COM", "cusip": "A", "value_usd": 100, "shares_or_principal": 10}],
    )
    frame = build_13f_issuer_change_summary_table([single])
    assert frame.empty


def test_build_13f_portfolio_change_summary_table_aggregates_filing_totals():
    current = _make_filing(
        "2026-02-14", "2025-12-31", "0002",
        [
            {"security_id": "c:A", "issuer": "A", "class_title": "COM", "cusip": "A", "value_usd": 1200, "shares_or_principal": 15},
            {"security_id": "c:NEW", "issuer": "NEW CO", "class_title": "COM", "cusip": "NEW", "value_usd": 500, "shares_or_principal": 5},
        ],
    )
    prior = _make_filing(
        "2025-11-14", "2025-09-30", "0004",
        [
            {"security_id": "c:A", "issuer": "A", "class_title": "COM", "cusip": "A", "value_usd": 800, "shares_or_principal": 8},
            {"security_id": "c:OLD", "issuer": "OLD CO", "class_title": "COM", "cusip": "OLD", "value_usd": 300, "shares_or_principal": 10},
        ],
    )
    frame = build_13f_portfolio_change_summary_table([current, prior])
    assert not frame.empty
    fields = {row["field"]: row["value"] for _, row in frame.iterrows()}
    assert fields["current_positions"] == 2
    assert fields["prior_positions"] == 2
    assert fields["new_positions"] == 1  # NEW CO
    assert fields["eliminated_positions"] == 1  # OLD CO
    assert fields["current_reported_value_usd"] == pytest.approx(1700.0)  # 1200 + 500
    assert fields["prior_reported_value_usd"] == pytest.approx(1100.0)  # 800 + 300
    assert fields["reported_value_change_usd"] == pytest.approx(600.0)
    assert fields["reported_value_change_pct"] == pytest.approx(600.0 / 1100.0)


def test_build_13f_portfolio_change_summary_table_requires_two_filings():
    single = _make_filing(
        "2026-02-14", "2025-12-31", "0002",
        [{"security_id": "c:A", "issuer": "A", "class_title": "COM", "cusip": "A", "value_usd": 100, "shares_or_principal": 10}],
    )
    frame = build_13f_portfolio_change_summary_table([single])
    assert frame.empty


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


def test_build_top_holdings_live_table_adds_price_change_column():
    holdings = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "class_title": "COM",
                "cusip": "037833100",
                "value_usd": 1000,
                "shares_or_principal": 10,
            }
        ]
    )
    reference = pd.DataFrame(
        [{"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"}]
    )

    frame = build_top_holdings_live_table(
        holdings,
        reference,
        limit=1,
        yahoo_client=FakeYahooClient(),
        price_change_window="1M",
    )

    assert "price_change_pct" in frame.columns
    assert frame.iloc[0]["price_change_pct"] == pytest.approx((200.0 / 150.0) - 1.0)


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


def test_build_13f_live_price_summary_table_includes_price_change_window():
    holdings = pd.DataFrame(
        [
            {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 1000, "shares_or_principal": 10},
        ]
    )
    reference = pd.DataFrame(
        [{"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"}]
    )

    summary = build_13f_live_price_summary_table(
        holdings,
        reference,
        yahoo_client=FakeYahooClient(),
        price_change_window="1M",
    )

    assert summary[summary["field"] == "price_change_window"].iloc[0]["value"] == "1M"


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


def test_build_balance_sheet_context_table_shows_selected_residual_context():
    filings = [
        BrkLiquidityFiling(
            filing_date="2026-05-04",
            accession_number="0001",
            form="10-Q",
            balance_sheet=pd.DataFrame(
                [
                    ["Investments in equity securities", "", "288,034", "297,778"],
                    ["Equity method investments", "", "19,951", "19,978"],
                    ["Total assets", "", "1,252,271", "1,222,176"],
                    ["Income taxes, principally deferred", "", "88,685", "86,955"],
                    ["Total liabilities", "", "522,821", "502,473"],
                    ["Notes payable and other borrowings", "", "42,835", "45,763"],
                    ["Notes payable and other borrowings", "", "86,051", "83,318"],
                ],
                columns=[
                    "Consolidated Balance Sheets",
                    "Consolidated Balance Sheets",
                    "Mar. 31, 2026",
                    "Dec. 31, 2025",
                ],
            ),
        )
    ]

    bridge = build_liquidity_bridge_table(filings)
    context = build_balance_sheet_context_table(bridge)

    fields = dict(zip(context["field"], context["value"]))
    assert fields["period_end"] == "2026-03-31"
    assert fields["equity_securities_usd"] == 288_034 * M
    assert fields["equity_method_investments_usd"] == 19_951 * M
    assert fields["deferred_income_taxes_usd"] == 88_685 * M
    assert fields["total_liabilities_usd"] == 522_821 * M
    assert fields["notes_payable_and_other_borrowings_usd"] == (42_835 + 86_051) * M


def test_build_liquidity_detail_table_excludes_context_rows():
    bridge = pd.DataFrame(
        [
            {"metric": "cash_and_equivalents", "value_usd": 1.0},
            {"metric": "equity_securities", "value_usd": 2.0},
            {"metric": "notes_payable_and_other_borrowings", "value_usd": 3.0},
        ]
    )

    detail = build_liquidity_detail_table(bridge)

    assert list(detail["metric"]) == ["cash_and_equivalents"]


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


def test_build_holdings_vs_brk_price_change_table():
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

    frame = build_holdings_vs_brk_price_change_table(
        holdings,
        reference,
        price_change_window="1M",
        limit=1,
        yahoo_client=FakeYahooClient(),
    )

    assert frame[frame["field"] == "price_change_window"].iloc[0]["value"] == "1M"
    assert frame[frame["field"] == "brk_b_price_change_pct"].iloc[0]["value"] == pytest.approx((500.0 / 470.0) - 1.0)


def test_build_holdings_vs_brk_price_change_table_reports_missing_status():
    holdings = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "class_title": "COM",
                "cusip": "037833100",
                "value_usd": 1000,
                "shares_or_principal": 10,
            }
        ]
    )
    reference = pd.DataFrame(
        [{"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"}]
    )

    frame = build_holdings_vs_brk_price_change_table(
        holdings,
        reference,
        price_change_window="1M",
        yahoo_client=EmptyYahooClient(),
    )

    assert frame[frame["field"] == "comparison_status"].iloc[0]["value"] == "No BRK or holdings price-change data resolved in current run"
    assert frame[frame["field"] == "top_holdings_limit"].iloc[0]["value"] == 0
    assert pd.isna(frame[frame["field"] == "top_holdings_weighted_change_pct"].iloc[0]["value"])


def test_build_segment_period_sections_returns_one_table_per_period():
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
        ),
        BrkSegmentFiling(
            filing_date="2025-03-01",
            accession_number="0002",
            form="10-K",
            reports=BrkSegmentReportSet(
                filing_date="2025-03-01",
                accession_number="0002",
                earnings_detail=pd.DataFrame(
                    [
                        {"report": "earnings", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Revenues", "duration_months": 12, "period_end": "2024-12-31", "value": 5 * M},
                    ]
                ),
                reconciliation_detail=pd.DataFrame(),
                additional_detail=pd.DataFrame(),
            ),
        ),
    ]

    sections = build_segment_period_sections(filings, period="annual")

    assert [title for title, _ in sections] == [
        "Top-Level Operating Segments FY 2025 (2026-03-02)",
        "Top-Level Operating Segments FY 2024 (2025-03-01)",
    ]


def test_build_brk_valuation_context_table():
    reference = pd.DataFrame(
        [
            {"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"},
            {"security_id": "cusip:025816109", "ticker": "AXP", "exchange": "NYSE"},
        ]
    )
    bundle = BrkValuationBundle(
        overview=BrkOverviewBundle(
            company=None,
            market_snapshot={"ticker": "BRK-B", "last_price": 500.0, "market_cap": 1000.0 * M},
            submissions={},
            company_facts={},
        ),
        holdings=Brk13FBundle(
            company=None,
            filing_date="2026-02-17",
            accession_number="0001",
            information_table_filename="info.xml",
            holdings=pd.DataFrame(
                [
                    {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 100.0, "shares_or_principal": 0.2},
                    {"security_id": "cusip:025816109", "issuer": "AMERICAN EXPRESS CO", "class_title": "COM", "cusip": "025816109", "value_usd": 90.0, "shares_or_principal": 0.1},
                ]
            ),
        ),
        liquidity=BrkLiquidityBundle(
            company=None,
            filings=[
                BrkLiquidityFiling(
                    filing_date="2026-03-02",
                    accession_number="0002",
                    form="10-K",
                    balance_sheet=pd.DataFrame(
                        [
                            ["Cash and cash equivalents", "", "100", "90"],
                            ["Short-term investments in U.S. Treasury Bills", "", "200", "180"],
                            ["Investments in fixed maturity securities", "", "50", "40"],
                            ["Payable for purchase of U.S. Treasury Bills", "", "10", "5"],
                        ],
                        columns=[
                            "Consolidated Balance Sheets",
                            "Consolidated Balance Sheets",
                            "Dec. 31, 2025",
                            "Dec. 31, 2024",
                        ],
                    ),
                )
            ],
        ),
        segments=BrkSegmentsBundle(
            company=None,
            filings=[
                BrkSegmentFiling(
                    filing_date="2026-03-02",
                    accession_number="0003",
                    form="10-K",
                    reports=BrkSegmentReportSet(
                        filing_date="2026-03-02",
                        accession_number="0003",
                        earnings_detail=pd.DataFrame(
                            [
                                {"report": "earnings", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Revenues", "duration_months": 12, "period_end": "2025-12-31", "value": 23 * M},
                            ]
                        ),
                        reconciliation_detail=pd.DataFrame(),
                        additional_detail=pd.DataFrame(),
                    ),
                )
            ],
        ),
    )

    context = build_brk_valuation_context_table(bundle, reference, yahoo_client=FakeYahooClient())

    assert context[context["field"] == "13f_live_coverage_ratio"].iloc[0]["value"] == 1.0
    assert context[context["field"] == "net_liquidity_total_usd"].iloc[0]["value"] == 340.0 * M
    assert context[context["field"] == "segment_period_end"].iloc[0]["value"] == "2025-12-31"


def test_build_13f_live_price_summary_table_reports_missing_status():
    holdings = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "class_title": "COM",
                "cusip": "037833100",
                "value_usd": 1000,
                "shares_or_principal": 10,
            }
        ]
    )
    reference = pd.DataFrame(
        [{"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"}]
    )

    summary = build_13f_live_price_summary_table(
        holdings,
        reference,
        yahoo_client=EmptyYahooClient(),
        price_change_window="1M",
    )

    assert summary[summary["field"] == "live_price_status"].iloc[0]["value"] == "No Yahoo prices resolved in current run"


def test_build_market_anchor_table_reports_missing_snapshot_status():
    anchor = build_market_anchor_table({})

    assert anchor[anchor["field"] == "market_snapshot_status"].iloc[0]["value"] == "No Yahoo market snapshot values resolved in current run"


def test_build_market_implied_sotp_bridge_table():
    reference = pd.DataFrame(
        [
            {"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"},
            {"security_id": "cusip:025816109", "ticker": "AXP", "exchange": "NYSE"},
        ]
    )
    bundle = BrkValuationBundle(
        overview=BrkOverviewBundle(
            company=None,
            market_snapshot={"ticker": "BRK-B", "last_price": 500.0, "market_cap": 1000.0 * M},
            submissions={},
            company_facts={},
        ),
        holdings=Brk13FBundle(
            company=None,
            filing_date="2026-02-17",
            accession_number="0001",
            information_table_filename="info.xml",
            holdings=pd.DataFrame(
                [
                    {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 100.0, "shares_or_principal": 0.2},
                    {"security_id": "cusip:025816109", "issuer": "AMERICAN EXPRESS CO", "class_title": "COM", "cusip": "025816109", "value_usd": 90.0, "shares_or_principal": 0.1},
                ]
            ),
        ),
        liquidity=BrkLiquidityBundle(
            company=None,
            filings=[
                BrkLiquidityFiling(
                    filing_date="2026-03-02",
                    accession_number="0002",
                    form="10-K",
                    balance_sheet=pd.DataFrame(
                        [
                            ["Cash and cash equivalents", "", "100", "90"],
                            ["Short-term investments in U.S. Treasury Bills", "", "200", "180"],
                            ["Investments in fixed maturity securities", "", "50", "40"],
                            ["Payable for purchase of U.S. Treasury Bills", "", "10", "5"],
                        ],
                        columns=[
                            "Consolidated Balance Sheets",
                            "Consolidated Balance Sheets",
                            "Dec. 31, 2025",
                            "Dec. 31, 2024",
                        ],
                    ),
                )
            ],
        ),
        segments=BrkSegmentsBundle(company=None, filings=[]),
    )

    bridge = build_market_implied_sotp_bridge_table(bundle, reference, yahoo_client=FakeYahooClient())

    assert bridge[bridge["metric"] == "public_equity_holdings_blended"].iloc[0]["value_usd"] == 70.0
    assert bridge[bridge["metric"] == "net_liquidity_total"].iloc[0]["value_usd"] == 340.0 * M
    assert bridge[bridge["metric"] == "residual_operating_and_other"].iloc[0]["value_usd"] == pytest.approx((1000.0 * M) - (340.0 * M) - 70.0)


def test_build_operating_business_context_table_compares_residual_to_segment_earnings():
    reference = pd.DataFrame(
        [{"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"}]
    )
    bundle = BrkValuationBundle(
        overview=BrkOverviewBundle(
            company=None,
            market_snapshot={"ticker": "BRK-B", "last_price": 500.0, "market_cap": 1000.0 * M},
            submissions={},
            company_facts={},
        ),
        holdings=Brk13FBundle(
            company=None,
            filing_date="2026-02-17",
            accession_number="0001",
            information_table_filename="info.xml",
            holdings=pd.DataFrame(
                [
                    {"security_id": "cusip:037833100", "issuer": "APPLE INC", "class_title": "COM", "cusip": "037833100", "value_usd": 100.0, "shares_or_principal": 0.2},
                ]
            ),
        ),
        liquidity=BrkLiquidityBundle(
            company=None,
            filings=[
                BrkLiquidityFiling(
                    filing_date="2026-03-02",
                    accession_number="0002",
                    form="10-K",
                    balance_sheet=pd.DataFrame(
                        [
                            ["Cash and cash equivalents", "", "100"],
                            ["Short-term investments in U.S. Treasury Bills", "", "200"],
                        ],
                        columns=[
                            "Consolidated Balance Sheets",
                            "Consolidated Balance Sheets",
                            "Dec. 31, 2025",
                        ],
                    ),
                )
            ],
        ),
        segments=BrkSegmentsBundle(
            company=None,
            filings=[
                BrkSegmentFiling(
                    filing_date="2026-03-02",
                    accession_number="0003",
                    form="10-K",
                    reports=BrkSegmentReportSet(
                        filing_date="2026-03-02",
                        accession_number="0003",
                        earnings_detail=pd.DataFrame(
                            [
                                {"report": "earnings", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Earnings before income taxes", "duration_months": 12, "period_end": "2025-12-31", "value": 30 * M},
                                {"report": "earnings", "member_path": "Operating Businesses | BHE", "member_name": "BHE", "metric": "Earnings before income taxes", "duration_months": 12, "period_end": "2025-12-31", "value": 20 * M},
                            ]
                        ),
                        reconciliation_detail=pd.DataFrame(),
                        additional_detail=pd.DataFrame(),
                    ),
                )
            ],
        ),
    )

    context = build_operating_business_context_table(
        bundle,
        reference,
        yahoo_client=FakeYahooClient(),
    )

    residual = context[context["field"] == "residual_operating_and_other_usd"].iloc[0]["value"]
    pretax = context[context["field"] == "operating_segment_pretax_earnings_usd"].iloc[0]["value"]
    multiple = context[context["field"] == "residual_to_pretax_earnings_multiple"].iloc[0]["value"]

    assert context[context["field"] == "operating_segment_count"].iloc[0]["value"] == 2
    assert pretax == 50 * M
    assert residual == pytest.approx((1000.0 * M) - (300.0 * M) - 40.0)
    assert multiple == pytest.approx(residual / pretax)


def test_build_brk_operating_reverse_dcf_table_basic():
    # residual = 500M, pretax_earnings = 50M
    # oe_yield = 50/500 = 0.10
    # at r=0.10: implied_g = 0.10 - 0.10 = 0.00
    # zero_growth_value = 50M / 0.10 = 500M
    context = pd.DataFrame([
        {"field": "residual_operating_and_other_usd", "value": 500.0 * M},
        {"field": "operating_segment_pretax_earnings_usd", "value": 50.0 * M},
    ])
    snapshot = {"market_cap": 1000.0 * M, "last_price": 500.0}
    table = build_brk_operating_reverse_dcf_table(context, snapshot, required_returns=[0.10])
    assert len(table) == 1
    row = table.iloc[0]
    assert row["assumed_return"] == pytest.approx(0.10)
    assert row["implied_growth"] == pytest.approx(0.0)
    assert row["zero_growth_operating_value_usd"] == pytest.approx(500.0 * M)


def test_build_brk_operating_reverse_dcf_table_default_returns():
    context = pd.DataFrame([
        {"field": "residual_operating_and_other_usd", "value": 400.0 * M},
        {"field": "operating_segment_pretax_earnings_usd", "value": 20.0 * M},
    ])
    snapshot = {"market_cap": 800.0 * M, "last_price": 400.0}
    table = build_brk_operating_reverse_dcf_table(context, snapshot)
    assert list(table["assumed_return"]) == pytest.approx([0.08, 0.10, 0.12])


def test_build_brk_operating_reverse_dcf_table_computes_per_share():
    # residual=400M, pretax=40M, oe_yield=0.10
    # at r=0.10: implied_g=0, zero_growth=400M
    # market_cap=1000M, last_price=500 → shares=2M BRK-B equiv
    # zero_growth_per_brk_b = 400M / 2M = $200
    context = pd.DataFrame([
        {"field": "residual_operating_and_other_usd", "value": 400.0 * M},
        {"field": "operating_segment_pretax_earnings_usd", "value": 40.0 * M},
    ])
    snapshot = {"market_cap": 1000.0 * M, "last_price": 500.0}
    table = build_brk_operating_reverse_dcf_table(context, snapshot, required_returns=[0.10])
    row = table.iloc[0]
    assert row["zero_growth_per_brk_b_usd"] == pytest.approx(200.0)


def test_build_brk_operating_reverse_dcf_table_returns_empty_when_residual_zero():
    context = pd.DataFrame([
        {"field": "residual_operating_and_other_usd", "value": 0.0},
        {"field": "operating_segment_pretax_earnings_usd", "value": 50.0 * M},
    ])
    snapshot = {"market_cap": 1000.0 * M, "last_price": 500.0}
    table = build_brk_operating_reverse_dcf_table(context, snapshot)
    assert table.empty


def test_build_brk_operating_reverse_dcf_table_returns_empty_when_pretax_missing():
    context = pd.DataFrame([
        {"field": "residual_operating_and_other_usd", "value": 500.0 * M},
    ])
    snapshot = {"market_cap": 1000.0 * M, "last_price": 500.0}
    table = build_brk_operating_reverse_dcf_table(context, snapshot)
    assert table.empty
