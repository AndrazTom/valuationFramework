import pandas as pd

from valuation.securities.pricing import enrich_holdings_with_market_prices, normalize_price_change_window


class FakeYahooClient:
    def fetch_price_snapshot(self, ticker):
        return {
            "ticker": ticker,
            "last_price": {"AAPL": 200.0, "AXP": 300.0}[ticker],
            "previous_close": {"AAPL": 180.0, "AXP": 270.0}[ticker],
            "latest_price_date": "2026-04-09",
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
                }[ticker],
            }
        )


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


def test_normalize_price_change_window_uppercases_value():
    assert normalize_price_change_window("all") == "ALL"
