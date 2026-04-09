import pandas as pd

from valuation.securities.pricing import enrich_holdings_with_market_prices


class FakeYahooClient:
    def fetch_price_snapshot(self, ticker):
        return {
            "ticker": ticker,
            "last_price": {"AAPL": 200.0, "AXP": 300.0}[ticker],
            "latest_price_date": "2026-04-09",
            "source": "yfinance",
        }


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
