from valuation.data.providers.yahoo import YahooFinanceClient


def test_search_quotes_normalizes_results(monkeypatch):
    class FakeSearch:
        def __init__(self, query, max_results=10):
            self.quotes = [
                {
                    "symbol": "BRK-B",
                    "exchange": "NYQ",
                    "exchDisp": "NYSE",
                    "shortname": "Berkshire Hathaway",
                    "longname": "Berkshire Hathaway Inc.",
                    "quoteType": "EQUITY",
                }
            ]

    class FakeYahooModule:
        Search = FakeSearch

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    client = YahooFinanceClient()
    results = client.search_quotes("US0846707026")

    assert results[0].symbol == "BRK-B"
    assert results[0].exchange_display == "NYSE"


def test_fetch_price_snapshot_skips_history_when_fast_info_has_last_price(monkeypatch):
    class FakeTicker:
        def __init__(self, ticker):
            self.fast_info = {
                "currency": "USD",
                "exchange": "NMS",
                "last_price": 123.45,
            }

        def history(self, **kwargs):
            raise AssertionError("history() should not be called when fast_info has last_price")

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    client = YahooFinanceClient()
    snapshot = client.fetch_price_snapshot("AAPL")

    assert snapshot["ticker"] == "AAPL"
    assert snapshot["last_price"] == 123.45
