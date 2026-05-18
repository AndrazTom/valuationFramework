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

    client = YahooFinanceClient(use_cache=False)
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
                "market_cap": None,
                "shares": 1_000_000,
            }

        def history(self, **kwargs):
            raise AssertionError("history() should not be called when fast_info has last_price")

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    client = YahooFinanceClient(use_cache=False)
    snapshot = client.fetch_price_snapshot("AAPL")

    assert snapshot["ticker"] == "AAPL"
    assert snapshot["last_price"] == 123.45
    assert snapshot["market_cap"] == 123_450_000.0
    assert snapshot["market_cap_source"] == "last_price_x_shares"


def test_fetch_price_snapshot_prefers_reported_market_cap(monkeypatch):
    class FakeTicker:
        def __init__(self, ticker):
            self.fast_info = {
                "currency": "USD",
                "exchange": "NMS",
                "last_price": 123.45,
                "market_cap": 120_000_000.0,
                "shares": 1_000_000,
            }

        def history(self, **kwargs):
            raise AssertionError("history() should not be called when fast_info has last_price")

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    client = YahooFinanceClient(use_cache=False)
    snapshot = client.fetch_price_snapshot("AAPL")

    assert snapshot["market_cap"] == 120_000_000.0
    assert snapshot["market_cap_source"] == "yfinance_fast_info"


def test_fetch_price_snapshot_handles_fast_info_rate_limit(monkeypatch):
    class ExplodingInfo:
        def get(self, key, default=None):
            raise RuntimeError("rate limited")

    class FakeTicker:
        def __init__(self, ticker):
            self.fast_info = ExplodingInfo()

        def history(self, **kwargs):
            raise RuntimeError("rate limited")

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    client = YahooFinanceClient(use_cache=False)
    snapshot = client.fetch_price_snapshot("AAPL")

    assert snapshot["ticker"] == "AAPL"
    assert snapshot["last_price"] is None
    assert snapshot["exchange"] is None


def test_fetch_history_returns_empty_frame_on_provider_error(monkeypatch):
    class FakeTicker:
        def __init__(self, ticker):
            self.fast_info = {}

        def history(self, **kwargs):
            raise RuntimeError("rate limited")

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    client = YahooFinanceClient(use_cache=False)
    history = client.fetch_history("AAPL")

    assert history.empty


def test_fetch_price_snapshot_uses_persistent_cache(monkeypatch, tmp_path):
    calls = {"count": 0}

    class FakeTicker:
        def __init__(self, ticker):
            calls["count"] += 1
            self.fast_info = {
                "currency": "USD",
                "exchange": "NMS",
                "last_price": 100.0,
                "market_cap": 1_000_000.0,
            }

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    first = YahooFinanceClient(cache_root=tmp_path)
    assert first.fetch_price_snapshot("AAPL")["last_price"] == 100.0

    class ExplodingTicker:
        def __init__(self, ticker):
            raise AssertionError("provider should not be called for a warm cache hit")

    class ExplodingYahooModule:
        Ticker = ExplodingTicker

    monkeypatch.setattr(
        "valuation.data.providers.yahoo._load_yfinance",
        lambda: ExplodingYahooModule,
    )

    second = YahooFinanceClient(cache_root=tmp_path)
    assert second.fetch_price_snapshot("AAPL")["last_price"] == 100.0
    assert calls["count"] == 1


def test_fetch_price_snapshot_refresh_cache_bypasses_persistent_cache(monkeypatch, tmp_path):
    prices = [100.0, 200.0]

    class FakeTicker:
        def __init__(self, ticker):
            self.fast_info = {
                "currency": "USD",
                "exchange": "NMS",
                "last_price": prices.pop(0),
                "market_cap": 1_000_000.0,
            }

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    first = YahooFinanceClient(cache_root=tmp_path)
    assert first.fetch_price_snapshot("AAPL")["last_price"] == 100.0

    refreshed = YahooFinanceClient(cache_root=tmp_path, refresh_cache=True)
    assert refreshed.fetch_price_snapshot("AAPL")["last_price"] == 200.0


def test_fetch_history_uses_persistent_cache(monkeypatch, tmp_path):
    import pandas as pd

    calls = {"count": 0}

    class FakeTicker:
        def __init__(self, ticker):
            calls["count"] += 1

        def history(self, **kwargs):
            return pd.DataFrame(
                [{"Date": pd.Timestamp("2026-01-02"), "Close": 10.0, "Volume": 100}]
            ).set_index("Date")

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    first = YahooFinanceClient(cache_root=tmp_path)
    first_history = first.fetch_history("AAPL")
    assert first_history.iloc[0]["close"] == 10.0

    class ExplodingTicker:
        def __init__(self, ticker):
            raise AssertionError("provider should not be called for a warm history cache hit")

    class ExplodingYahooModule:
        Ticker = ExplodingTicker

    monkeypatch.setattr(
        "valuation.data.providers.yahoo._load_yfinance",
        lambda: ExplodingYahooModule,
    )

    second = YahooFinanceClient(cache_root=tmp_path)
    second_history = second.fetch_history("AAPL")

    assert second_history.iloc[0]["close"] == 10.0
    assert second_history.iloc[0]["date"] == "2026-01-02T00:00:00"
    assert calls["count"] == 1


def test_fetch_price_snapshot_latest_price_date_populated_from_fast_info(monkeypatch):
    """latest_price_date must not be None when fast_info provides last_price."""
    import datetime

    class FakeTicker:
        def __init__(self, ticker):
            self.fast_info = {"last_price": 200.0, "market_cap": None, "shares": 1_000}

        def history(self, **kwargs):
            raise AssertionError("history() should not be called")

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    client = YahooFinanceClient(use_cache=False)
    snapshot = client.fetch_price_snapshot("AAPL")

    assert snapshot["last_price"] == 200.0
    assert snapshot["latest_price_date"] is not None
    assert snapshot["latest_price_date"] == datetime.date.today().isoformat()


def test_fetch_price_snapshot_missing_close_column_does_not_crash(monkeypatch):
    """When history() returns a frame without 'Close', latest_close should be None (not crash)."""
    import pandas as pd

    class FakeTicker:
        def __init__(self, ticker):
            self.fast_info = {"last_price": None, "market_cap": None, "shares": None}

        def history(self, **kwargs):
            return pd.DataFrame([{"Volume": 1000}])

    class FakeYahooModule:
        Ticker = FakeTicker

    monkeypatch.setattr("valuation.data.providers.yahoo._load_yfinance", lambda: FakeYahooModule)

    client = YahooFinanceClient(use_cache=False)
    snapshot = client.fetch_price_snapshot("AAPL")

    assert snapshot["last_price"] is None
    assert snapshot["latest_price_date"] is None
