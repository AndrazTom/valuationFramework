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

    def search_quotes(self, query, max_results=10):
        return []


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


def test_company_cli_writes_files(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli, "fetch_company_snapshot", lambda identifier, identifier_kind="auto": type(
        "Bundle",
        (),
        {
            "resolution": type(
                "Resolution",
                (),
                {
                    "input_value": identifier,
                    "identifier_kind": identifier_kind,
                    "query_used": identifier,
                    "security_id": "ticker:NYSE:BRK-B",
                    "ticker": "BRK-B",
                    "exchange": "NYSE",
                    "sec_company": SecCompany(
                        ticker="BRK-B",
                        cik="0001067983",
                        name="BERKSHIRE HATHAWAY INC",
                        exchange="NYSE",
                    ),
                },
            )(),
            "market_snapshot": {"ticker": "BRK-B", "last_price": 500.0},
            "submissions": {"filings": {"recent": {}}},
            "company_facts": {"facts": {}},
        },
    )())

    result = cli.main(["company", "BRK-B", "--outdir", str(tmp_path)])

    assert result == 0
    assert (tmp_path / "BRK-B" / "resolution.csv").exists()
    assert (tmp_path / "BRK-B" / "key_financials.md").exists()


def test_statements_cli_writes_files(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        cli,
        "fetch_company_facts",
        lambda identifier, identifier_kind="auto": type(
            "Bundle",
            (),
            {
                "resolution": type(
                    "Resolution",
                    (),
                    {
                        "input_value": identifier,
                        "identifier_kind": identifier_kind,
                        "query_used": identifier,
                        "security_id": "ticker:NASDAQ:AAPL",
                        "ticker": "AAPL",
                        "exchange": "NASDAQ",
                        "sec_company": SecCompany(
                            ticker="AAPL",
                            cik="0000320193",
                            name="APPLE INC",
                            exchange="NASDAQ",
                        ),
                    },
                )(),
                "company_facts": {"facts": {}},
            },
        )(),
    )
    monkeypatch.setattr(
        cli,
        "build_statement_table",
        lambda company_facts, statement, period, limit=4, **kwargs: __import__("pandas").DataFrame(
            [{"metric": "revenue", "unit": "USD", "FY 2025": 100.0}]
        ),
    )

    result = cli.main(
        [
            "statements",
            "AAPL",
            "--statement",
            "income",
            "--period",
            "annual",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert (tmp_path / "AAPL" / "income_statement_annual.csv").exists()
    assert (tmp_path / "AAPL" / "company.md").exists()


def test_statements_cli_rejects_invalid_quarter():
    with pytest.raises(SystemExit):
        cli.main(["statements", "AAPL", "--start-quarter", "5"])


def test_statements_cli_rejects_quarter_without_year():
    result = cli.main(["statements", "AAPL", "--start-quarter", "2"])

    assert result == 1


def test_statements_cli_rejects_reversed_range():
    result = cli.main(
        [
            "statements",
            "AAPL",
            "--start-year",
            "2025",
            "--start-quarter",
            "4",
            "--end-year",
            "2025",
            "--end-quarter",
            "2",
        ]
    )

    assert result == 1
