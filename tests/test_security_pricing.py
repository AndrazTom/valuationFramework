import pandas as pd
import pytest

from valuation.securities.pricing import (
    calculate_price_change_pct,
    enrich_holdings_with_market_prices,
    fetch_price_change_snapshot,
    normalize_price_change_window,
)


class FakeYahooClient:
    def __init__(self):
        self.snapshot_calls = []
        self.history_calls = []

    def fetch_price_snapshot(self, ticker):
        self.snapshot_calls.append(ticker)
        return {
            "ticker": ticker,
            "last_price": {"AAPL": 200.0, "AXP": 300.0}[ticker],
            "previous_close": {"AAPL": 180.0, "AXP": 270.0}[ticker],
            "latest_price_date": "2026-04-09",
            "source": "yfinance",
        }

    def fetch_history(self, ticker, period="1mo", interval="1d"):
        self.history_calls.append(ticker)
        return pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2026-01-02", "2026-02-02", "2026-03-02", "2026-04-09"]
                ),
                "close": {
                    "AAPL": [100.0, 120.0, 150.0, 200.0],
                    "AXP": [200.0, 220.0, 260.0, 300.0],
                }[ticker],
            }
        )


class RaisingYahooClient:
    def fetch_price_snapshot(self, ticker):
        raise RuntimeError("rate limited")

    def fetch_history(self, ticker, period="1mo", interval="1d"):
        raise RuntimeError("rate limited")


def test_enrich_holdings_with_market_prices():
    holdings = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "shares_or_principal": 10,
            },
            {
                "security_id": "cusip:025816109",
                "issuer": "AMERICAN EXPRESS CO",
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

    enriched = enrich_holdings_with_market_prices(
        holdings,
        reference,
        yahoo_client=FakeYahooClient(),
    )

    assert list(enriched["ticker"]) == ["AAPL", "AXP"]
    assert list(enriched["market_value_live_usd"]) == [2000.0, 6000.0]


def test_enrich_holdings_with_market_prices_adds_price_change_pct():
    holdings = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "shares_or_principal": 10,
            }
        ]
    )
    reference = pd.DataFrame(
        [
            {"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"},
        ]
    )

    enriched = enrich_holdings_with_market_prices(
        holdings,
        reference,
        yahoo_client=FakeYahooClient(),
        price_change_window="1M",
    )

    assert enriched.iloc[0]["price_change_pct"] == (200.0 / 150.0) - 1.0


def test_enrich_holdings_with_market_prices_can_limit_live_fetches():
    holdings = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "shares_or_principal": 10,
            },
            {
                "security_id": "cusip:025816109",
                "issuer": "AMERICAN EXPRESS CO",
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
    yahoo = FakeYahooClient()

    enriched = enrich_holdings_with_market_prices(
        holdings,
        reference,
        yahoo_client=yahoo,
        max_holdings=1,
    )

    assert sorted(yahoo.snapshot_calls) == ["AAPL"]
    assert enriched.iloc[0]["market_value_live_usd"] == 2000.0
    assert enriched.iloc[1]["market_value_live_usd"] is None or pd.isna(enriched.iloc[1]["market_value_live_usd"])


def test_normalize_price_change_window_uppercases_value():
    assert normalize_price_change_window("all") == "ALL"


def test_fetch_price_change_snapshot_adds_change_fields():
    snapshot = fetch_price_change_snapshot(
        "AAPL",
        price_change_window="1M",
        yahoo_client=FakeYahooClient(),
    )

    assert snapshot["ticker"] == "AAPL"
    assert snapshot["price_change_window"] == "1M"
    assert snapshot["price_change_pct"] == pytest.approx((200.0 / 150.0) - 1.0)


def test_calculate_price_change_handles_mixed_timezone_history_without_warning(recwarn):
    history = pd.DataFrame(
        {
            "date": [
                "2026-03-01T00:00:00-05:00",
                "2026-04-09T00:00:00-04:00",
            ],
            "close": [150.0, 200.0],
        }
    )

    change = calculate_price_change_pct(
        snapshot={"last_price": 200.0},
        history=history,
        window="1M",
    )

    assert change == pytest.approx((200.0 / 150.0) - 1.0)
    assert not [warning for warning in recwarn if issubclass(warning.category, FutureWarning)]


def test_pricing_helpers_degrade_gracefully_when_quote_fetch_fails():
    holdings = pd.DataFrame(
        [
            {
                "security_id": "cusip:037833100",
                "issuer": "APPLE INC",
                "shares_or_principal": 10,
            }
        ]
    )
    reference = pd.DataFrame(
        [
            {"security_id": "cusip:037833100", "ticker": "AAPL", "exchange": "NASDAQ"},
        ]
    )

    enriched = enrich_holdings_with_market_prices(
        holdings,
        reference,
        yahoo_client=RaisingYahooClient(),
        price_change_window="1M",
    )
    snapshot = fetch_price_change_snapshot(
        "AAPL",
        price_change_window="1M",
        yahoo_client=RaisingYahooClient(),
    )

    assert enriched.iloc[0]["market_value_live_usd"] is None or pd.isna(enriched.iloc[0]["market_value_live_usd"])
    assert enriched.iloc[0]["price_change_pct"] is None or pd.isna(enriched.iloc[0]["price_change_pct"])
    assert snapshot["ticker"] == "AAPL"
    assert snapshot["price_change_pct"] is None
