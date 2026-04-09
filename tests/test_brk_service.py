from valuation.brk.service import (
    BRK_B_TICKER,
    fetch_brk_liquidity,
    fetch_brk_overview,
    find_brk_13f_filings,
)
from valuation.data.providers.sec import SecCompany


class FakeSecClient:
    def fetch_company_bundle(self, ticker, include_company_facts=False):
        assert ticker == BRK_B_TICKER
        assert include_company_facts is True
        return {
            "company": SecCompany(
                ticker="BRK-B",
                cik="0001067983",
                name="BERKSHIRE HATHAWAY INC",
                exchange="NYSE",
            ),
            "submissions": {"filings": {"recent": {}}},
            "company_facts": {"facts": {}},
        }


class FakeYahooClient:
    def fetch_price_snapshot(self, ticker):
        assert ticker == BRK_B_TICKER
        return {"ticker": "BRK-B", "last_price": 500.0}


def test_fetch_brk_overview_assembles_bundle():
    bundle = fetch_brk_overview(
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert bundle.company.ticker == "BRK-B"
    assert bundle.market_snapshot["last_price"] == 500.0


def test_fetch_brk_liquidity_assembles_bundle():
    bundle = fetch_brk_liquidity(sec_client=FakeSecClient())

    assert bundle.company.ticker == "BRK-B"
    assert bundle.company_facts == {"facts": {}}


def test_find_brk_13f_filings_finds_first_matching_form():
    submissions = {
        "filings": {
            "recent": {
                "form": ["8-K", "13F-HR", "10-Q"],
                "filingDate": ["2026-01-01", "2026-02-14", "2026-02-15"],
                "accessionNumber": ["0001", "0002", "0003"],
            }
        }
    }

    metadata = find_brk_13f_filings(submissions, limit=1)

    assert metadata[0]["filing_date"] == "2026-02-14"
    assert metadata[0]["accession_number"] == "0002"
