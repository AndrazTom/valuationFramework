from valuation.company.service import (
    fetch_company_facts,
    fetch_company_snapshot,
    resolve_company_identifier,
)
from valuation.data.providers.sec import SecCompany
from valuation.data.providers.yahoo import YahooSearchQuote


class FakeSecClient:
    def lookup_company(self, ticker):
        normalized = ticker.upper()
        if normalized in {"BRK-B", "AAPL"}:
            return SecCompany(
                ticker=normalized,
                cik="0001067983" if normalized == "BRK-B" else "0000320193",
                name="BERKSHIRE HATHAWAY INC" if normalized == "BRK-B" else "APPLE INC",
                exchange="NYSE" if normalized == "BRK-B" else "NASDAQ",
            )
        raise LookupError(ticker)

    def lookup_company_by_cik(self, cik):
        if str(cik).zfill(10) == "0001067983":
            return SecCompany(
                ticker="BRK-B",
                cik="0001067983",
                name="BERKSHIRE HATHAWAY INC",
                exchange="NYSE",
            )
        raise LookupError(cik)

    def fetch_company_bundle(self, ticker, include_company_facts=False):
        company = self.lookup_company(ticker)
        bundle = {
            "company": company,
            "submissions": {"filings": {"recent": {}}},
        }
        if include_company_facts:
            bundle["company_facts"] = {"facts": {}}
        return bundle

    def fetch_company_facts(self, cik):
        if str(cik).zfill(10) in {"0001067983", "0000320193"}:
            return {"facts": {}}
        raise LookupError(cik)


class FakeYahooClient:
    def search_quotes(self, query, max_results=10):
        if query == "BRK":
            return [
                YahooSearchQuote(
                    symbol="BRK-B",
                    exchange="NYQ",
                    exchange_display="NYSE",
                    short_name="Berkshire Hathaway",
                    long_name="Berkshire Hathaway Inc.",
                    quote_type="EQUITY",
                )
            ]
        if query == "US0846707026":
            return [
                YahooSearchQuote(
                    symbol="BRK-B",
                    exchange="NYQ",
                    exchange_display="NYSE",
                    short_name="Berkshire Hathaway",
                    long_name="Berkshire Hathaway Inc.",
                    quote_type="EQUITY",
                )
            ]
        if query == "037833100":
            return [
                YahooSearchQuote(
                    symbol="AAPL",
                    exchange="NMS",
                    exchange_display="NASDAQ",
                    short_name="Apple",
                    long_name="Apple Inc.",
                    quote_type="EQUITY",
                )
            ]
        if query == "FR0000121014":
            return [
                YahooSearchQuote(
                    symbol="MC.PA",
                    exchange="PAR",
                    exchange_display="Paris",
                    short_name="LVMH",
                    long_name="LVMH Moet Hennessy Louis Vuitton SE",
                    quote_type="EQUITY",
                )
            ]
        return []

    def fetch_price_snapshot(self, ticker):
        return {"ticker": ticker.upper(), "last_price": 500.0}

    def fetch_company_profile(self, ticker):
        normalized = ticker.upper()
        if normalized == "BNP.PA":
            return {
                "ticker": "BNP.PA",
                "name": "BNP Paribas SA",
                "exchange": "PAR",
                "exchange_display": "PAR",
                "currency": "EUR",
                "quote_type": "EQUITY",
                "country": "France",
                "sector": "Financial Services",
                "industry": "Banks",
            }
        if normalized == "MC.PA":
            return {
                "ticker": "MC.PA",
                "name": "LVMH",
                "exchange": "PAR",
                "exchange_display": "Paris",
                "currency": "EUR",
                "quote_type": "EQUITY",
                "country": "France",
                "sector": "Consumer Cyclical",
                "industry": "Luxury Goods",
            }
        if normalized in {"BRK-B", "AAPL"}:
            return {
                "ticker": normalized,
                "name": "Known Company",
                "exchange": "NYSE" if normalized == "BRK-B" else "NASDAQ",
                "exchange_display": "NYSE" if normalized == "BRK-B" else "NASDAQ",
                "currency": "USD",
                "quote_type": "EQUITY",
            }
        return {"ticker": normalized}


def test_resolve_company_identifier_by_cik():
    resolution = resolve_company_identifier(
        "1067983",
        identifier_kind="cik",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert resolution.ticker == "BRK-B"
    assert resolution.security_id == "cik:0001067983"


def test_resolve_company_identifier_by_isin():
    resolution = resolve_company_identifier(
        "US0846707026",
        identifier_kind="auto",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert resolution.identifier_kind == "isin"
    assert resolution.ticker == "BRK-B"


def test_fetch_company_snapshot():
    bundle = fetch_company_snapshot(
        "BRK-B",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert bundle.resolution.ticker == "BRK-B"
    assert bundle.market_snapshot["last_price"] == 500.0


def test_fetch_company_snapshot_sec_includes_profile_enrichment():
    bundle = fetch_company_snapshot(
        "AAPL",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert bundle.company_profile is not None
    assert bundle.company_profile["currency"] == "USD"


def test_fetch_company_facts():
    bundle = fetch_company_facts(
        "BRK-B",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert bundle.resolution.ticker == "BRK-B"
    assert bundle.company_facts == {"facts": {}}


def test_resolve_company_identifier_non_us_ticker_uses_yahoo_fallback():
    resolution = resolve_company_identifier(
        "BNP.PA",
        identifier_kind="ticker",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert resolution.ticker == "BNP.PA"
    assert resolution.sec_company is None
    assert resolution.company_name == "BNP Paribas SA"
    assert resolution.security_id == "ticker:PAR:BNP.PA"


def test_fetch_company_facts_non_us_uses_yahoo_source():
    bundle = fetch_company_facts(
        "BNP.PA",
        identifier_kind="ticker",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert bundle.statement_source == "yahoo"
    assert bundle.company_facts is None


def test_resolve_alias_ticker_uses_sec_match_from_yahoo_quote():
    resolution = resolve_company_identifier(
        "BRK",
        identifier_kind="ticker",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert resolution.ticker == "BRK-B"
    assert resolution.sec_company is not None
    assert resolution.security_id == "cik:0001067983"


def test_fetch_company_facts_alias_ticker_prefers_sec_source():
    bundle = fetch_company_facts(
        "BRK",
        identifier_kind="ticker",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert bundle.statement_source == "sec"
    assert bundle.company_facts == {"facts": {}}


def test_resolve_non_us_isin_does_not_require_sec_lookup():
    resolution = resolve_company_identifier(
        "FR0000121014",
        identifier_kind="auto",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert resolution.ticker == "MC.PA"
    assert resolution.sec_company is None
