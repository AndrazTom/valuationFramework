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

    monkeypatch.setattr("valuation.data.providers.yahoo.yf.Search", FakeSearch)

    client = YahooFinanceClient()
    results = client.search_quotes("US0846707026")

    assert results[0].symbol == "BRK-B"
    assert results[0].exchange_display == "NYSE"
