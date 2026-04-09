from pathlib import Path

import pytest

from valuation import cli
from valuation.data.providers.sec import SecCompany


class FakeSecClient:
    def fetch_company_bundle(self, ticker, include_company_facts=False):
        company = SecCompany(
            ticker=ticker.upper(),
            cik="0001067983",
            name="BERKSHIRE HATHAWAY INC",
            exchange="NYSE",
        )
        bundle = {
            "company": company,
            "submissions": {
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001"],
                        "filingDate": ["2026-01-01"],
                        "form": ["10-K"],
                        "primaryDocument": ["doc.htm"],
                        "isInlineXBRL": [1],
                    }
                }
            },
        }
        if include_company_facts:
            bundle["company_facts"] = {"facts": {}}
        return bundle


class FakeYahooClient:
    def fetch_price_snapshot(self, ticker):
        return {"ticker": ticker.upper(), "last_price": 500.0}


def test_cli_rejects_negative_filings_limit():
    with pytest.raises(SystemExit):
        cli.main(["snapshot", "BRK-B", "--filings-limit", "-1"])


def test_snapshot_cli_writes_files(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli, "SecClient", lambda: FakeSecClient())
    monkeypatch.setattr(cli, "YahooFinanceClient", lambda: FakeYahooClient())

    result = cli.main(["snapshot", "BRK-B", "--outdir", str(tmp_path)])

    assert result == 0
    assert (tmp_path / "BRK-B" / "company.csv").exists()
    assert (tmp_path / "BRK-B" / "market_snapshot.md").exists()
