from valuation.company.service import fetch_company_snapshot, resolve_company_identifier
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


class FakeYahooClient:
    def search_quotes(self, query, max_results=10):
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
        return []

    def fetch_price_snapshot(self, ticker):
        return {"ticker": ticker.upper(), "last_price": 500.0}


def test_resolve_company_identifier_by_cik():
    resolution = resolve_company_identifier(
        "1067983",
        identifier_kind="cik",
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert resolution.ticker == "BRK-B"
    assert resolution.security_id == "ticker:NYSE:BRK-B"


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
