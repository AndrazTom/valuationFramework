from pathlib import Path
import json

import pandas as pd
import pytest

from valuation import cli
from valuation.brk import cli as brk_cli
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

    def fetch_company_profile(self, ticker):
        return {
            "ticker": ticker.upper(),
            "name": "Example Co",
            "exchange": "PAR",
            "exchange_display": "PAR",
            "currency": "EUR",
            "quote_type": "EQUITY",
            "country": "France",
        }

    def fetch_statement_frame(self, ticker, *, statement, period):
        if statement == "income":
            return pd.DataFrame(
                {
                    pd.Timestamp("2025-12-31"): {"Total Revenue": 100.0, "Net Income": 20.0},
                }
            )
        return pd.DataFrame()


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
                    "company_name": "BERKSHIRE HATHAWAY INC",
                    "country": "United States",
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
            "company_profile": None,
        },
    )())

    result = cli.main(["company", "BRK-B", "--outdir", str(tmp_path)])

    assert result == 0
    assert (tmp_path / "BRK-B" / "resolution.csv").exists()
    assert (tmp_path / "BRK-B" / "overview.md").exists()
    assert (tmp_path / "BRK-B" / "key_financials.md").exists()
    assert (tmp_path / "BRK-B" / "statement_availability.md").exists()


def test_company_cli_writes_files_for_yahoo_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli, "YahooFinanceClient", lambda: FakeYahooClient())
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
                    "security_id": "ticker:PAR:BNP.PA",
                    "ticker": "BNP.PA",
                    "exchange": "PAR",
                    "company_name": "BNP Paribas SA",
                    "country": "France",
                    "currency": "EUR",
                    "sec_company": None,
                },
            )(),
            "market_snapshot": {"ticker": "BNP.PA", "last_price": 89.0, "currency": "EUR"},
            "submissions": None,
            "company_facts": None,
            "company_profile": {
                "ticker": "BNP.PA",
                "name": "BNP Paribas SA",
                "exchange": "PAR",
                "currency": "EUR",
                "country": "France",
                "sector": "Financial Services",
                "industry": "Banks",
            },
        },
    )())

    result = cli.main(["company", "BNP.PA", "--outdir", str(tmp_path)])

    assert result == 0
    assert (tmp_path / "BNP-PA" / "overview.md").exists()
    assert (tmp_path / "BNP-PA" / "key_financials.md").exists()
    assert (tmp_path / "BNP-PA" / "statement_availability.md").exists()


def test_statements_cli_writes_files(monkeypatch, tmp_path: Path):
    captured = {}
    
    def fake_build_statement_table(company_facts, statement, period, limit=4, **kwargs):
        captured["limit"] = limit
        return pd.DataFrame([{"metric": "revenue", "unit": "USD", "FY 2025": 100.0}])

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
                        "company_name": "APPLE INC",
                        "country": "United States",
                        "sec_company": SecCompany(
                            ticker="AAPL",
                            cik="0000320193",
                            name="APPLE INC",
                            exchange="NASDAQ",
                        ),
                    },
                )(),
                "company_facts": {"facts": {}},
                "statement_source": "sec",
            },
        )(),
    )
    monkeypatch.setattr(
        cli,
        "build_statement_table",
        fake_build_statement_table,
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
    assert captured["limit"] == 4
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


def test_brk_liquidity_cli_accepts_period_and_limit(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_fetch(period="annual", limit=1, **kwargs):
        captured["period"] = period
        captured["limit"] = limit
        return type(
            "Bundle",
            (),
            {
                "filings": [],
            },
        )()

    monkeypatch.setattr(
        brk_cli,
        "fetch_brk_liquidity",
        fake_fetch,
    )
    monkeypatch.setattr(brk_cli, "build_liquidity_bridge_table", lambda filings: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_liquidity_summary_table", lambda bridge: pd.DataFrame())

    result = cli.main(
        [
            "brk",
            "liquidity",
            "--period",
            "quarterly",
            "--limit",
            "3",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured == {"period": "quarterly", "limit": 3}


def test_brk_liquidity_cli_uses_range_filters_and_widens_default_limit(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_fetch(
        period="annual",
        limit=1,
        start_year=None,
        end_year=None,
        start_quarter=None,
        end_quarter=None,
    ):
        captured["period"] = period
        captured["limit"] = limit
        captured["start_year"] = start_year
        captured["end_year"] = end_year
        captured["start_quarter"] = start_quarter
        captured["end_quarter"] = end_quarter
        return type("Bundle", (), {"filings": []})()

    monkeypatch.setattr(brk_cli, "fetch_brk_liquidity", fake_fetch)
    monkeypatch.setattr(brk_cli, "build_liquidity_bridge_table", lambda filings: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_liquidity_summary_table", lambda bridge: pd.DataFrame())

    result = cli.main(
        [
            "brk",
            "liquidity",
            "--period",
            "quarterly",
            "--start-year",
            "2019",
            "--start-quarter",
            "1",
            "--end-year",
            "2023",
            "--end-quarter",
            "3",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured == {
        "period": "quarterly",
        "limit": 99,
        "start_year": 2019,
        "end_year": 2023,
        "start_quarter": 1,
        "end_quarter": 3,
    }


def test_brk_segments_cli_accepts_period_and_limit(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_fetch(period="annual", limit=1, **kwargs):
        captured["period"] = period
        captured["limit"] = limit
        return type(
            "Bundle",
            (),
            {
                "filings": [],
            },
        )()

    monkeypatch.setattr(
        brk_cli,
        "fetch_brk_segments",
        fake_fetch,
    )
    monkeypatch.setattr(brk_cli, "build_segment_report_summary_table", lambda filings: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_segment_period_sections", lambda filings, period="annual": [])
    monkeypatch.setattr(brk_cli, "build_top_level_operating_segments_summary_table", lambda filings, period="annual": pd.DataFrame())

    result = cli.main(
        [
            "brk",
            "segments",
            "--period",
            "quarterly",
            "--limit",
            "2",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured == {"period": "quarterly", "limit": 2}


def test_brk_segments_cli_range_forces_limit_even_when_explicit(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_fetch(period="annual", limit=1, **kwargs):
        captured["period"] = period
        captured["limit"] = limit
        captured.update(kwargs)
        return type("Bundle", (), {"filings": []})()

    monkeypatch.setattr(brk_cli, "fetch_brk_segments", fake_fetch)
    monkeypatch.setattr(brk_cli, "build_segment_report_summary_table", lambda filings: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_segment_period_sections", lambda filings, period="annual": [])
    monkeypatch.setattr(brk_cli, "build_top_level_operating_segments_summary_table", lambda filings, period="annual": pd.DataFrame())

    result = cli.main(
        [
            "brk",
            "segments",
            "--period",
            "annual",
            "--limit",
            "2",
            "--start-year",
            "2022",
            "--end-year",
            "2024",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured["limit"] == 99


def test_brk_holdings_cli_price_change_enables_live_table(monkeypatch, tmp_path: Path):
    captured = {"sections": []}

    monkeypatch.setattr(
        brk_cli,
        "fetch_latest_brk_13f",
        lambda: type(
            "Bundle",
            (),
            {
                "filing_date": "2026-02-17",
                "accession_number": "0001",
                "information_table_filename": "info.xml",
                "holdings": pd.DataFrame([{"issuer": "APPLE INC", "value_usd": 1000}]),
            },
        )(),
    )
    monkeypatch.setattr(brk_cli, "build_13f_summary_table", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_top_holdings_table", lambda holdings, limit=20: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_brk_security_reference", lambda: pd.DataFrame())
    monkeypatch.setattr(
        brk_cli,
        "build_13f_live_price_summary_table",
        lambda holdings, reference, yahoo_client=None, price_change_window=None, enriched_holdings=None: pd.DataFrame(),
    )
    monkeypatch.setattr(
        brk_cli,
        "build_holdings_vs_brk_price_change_table",
        lambda holdings, reference, yahoo_client=None, price_change_window=None, limit=None, enriched_holdings=None, brk_snapshot=None: pd.DataFrame(),
    )

    def fake_live_table(holdings, reference, limit=20, yahoo_client=None, price_change_window=None, enriched_holdings=None):
        captured["window"] = price_change_window
        return pd.DataFrame()

    def fake_emit(sections, output_dir):
        captured["sections"] = [title for title, _ in sections]

    monkeypatch.setattr(brk_cli, "build_top_holdings_live_table", fake_live_table)
    monkeypatch.setattr(brk_cli, "_emit_sections", fake_emit)

    result = cli.main(
        [
            "brk",
            "holdings",
            "--price-change",
            "1M",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured["window"] == "1M"
    assert "Top Holdings Live (1M Change)" in captured["sections"]
    assert "BRK vs Holdings Price Change (1M)" in captured["sections"]


def test_brk_holdings_cli_history_fetches_multiple_filings(monkeypatch, tmp_path: Path):
    captured = {"sections": []}

    def fake_history(limit=4):
        captured["filings_limit"] = limit
        return type(
            "HistoryBundle",
            (),
            {
                "filings": [
                    type(
                        "Filing",
                        (),
                        {
                            "filing_date": "2026-02-14",
                            "accession_number": "0002",
                            "information_table_filename": "info.xml",
                            "holdings": pd.DataFrame([{"issuer": "APPLE INC", "value_usd": 1000}]),
                        },
                    )()
                ],
            },
        )()

    monkeypatch.setattr(brk_cli, "fetch_brk_13f_history", fake_history)
    monkeypatch.setattr(brk_cli, "build_13f_summary_table", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_top_holdings_table", lambda holdings, limit=20: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_13f_history_summary_table", lambda filings: pd.DataFrame())
    monkeypatch.setattr(
        brk_cli,
        "build_13f_holdings_history_table",
        lambda filings, limit=20: pd.DataFrame(),
    )
    monkeypatch.setattr(
        brk_cli,
        "_emit_sections",
        lambda sections, output_dir: captured.update({"sections": [title for title, _ in sections]}),
    )

    result = cli.main(
        [
            "brk",
            "holdings",
            "--history",
            "--filings-limit",
            "6",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured["filings_limit"] == 6
    assert captured["sections"] == [
        "13F Summary",
        "Top Holdings",
        "13F Filing History",
        "Top Holdings History",
    ]


def test_brk_sotp_cli_writes_expected_sections(monkeypatch, tmp_path: Path):
    captured = {"sections": []}

    monkeypatch.setattr(
        brk_cli,
        "fetch_brk_valuation_bundle",
        lambda period="annual", yahoo_client=None: type(
            "Bundle",
            (),
            {
                "overview": type("Overview", (), {"market_snapshot": {}})(),
                "holdings": type("Holdings", (), {"holdings": pd.DataFrame()})(),
                "liquidity": type("Liquidity", (), {"filings": []})(),
                "segments": type("Segments", (), {"filings": []})(),
            },
        )(),
    )
    monkeypatch.setattr(brk_cli, "build_brk_security_reference", lambda: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_brk_valuation_assumptions_table", lambda period="annual": pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_market_anchor_table", lambda market_snapshot: pd.DataFrame())
    monkeypatch.setattr(
        brk_cli,
        "build_public_equity_portfolio_summary_table",
        lambda holdings, reference, yahoo_client=None, enriched_holdings=None: pd.DataFrame(),
    )
    monkeypatch.setattr(
        brk_cli,
        "build_13f_live_price_summary_table",
        lambda holdings, reference, yahoo_client=None, price_change_window=None, enriched_holdings=None: pd.DataFrame(),
    )
    monkeypatch.setattr(brk_cli, "build_liquidity_bridge_table", lambda filings: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_liquidity_summary_table", lambda bridge: pd.DataFrame())
    monkeypatch.setattr(brk_cli, "build_latest_liquidity_snapshot_table", lambda bridge: pd.DataFrame())
    monkeypatch.setattr(
        brk_cli,
        "build_market_implied_sotp_bridge_table",
        lambda bundle, reference, yahoo_client=None, enriched_holdings=None: pd.DataFrame(),
    )
    monkeypatch.setattr(
        brk_cli,
        "build_operating_business_context_table",
        lambda bundle, reference, period="annual", yahoo_client=None, enriched_holdings=None: pd.DataFrame(),
    )
    monkeypatch.setattr(
        brk_cli,
        "build_holdings_vs_brk_price_change_table",
        lambda holdings, reference, yahoo_client=None, price_change_window=None, enriched_holdings=None, brk_snapshot=None: pd.DataFrame(),
    )
    monkeypatch.setattr(brk_cli, "build_segment_period_sections", lambda filings, period="annual": [])
    monkeypatch.setattr(
        brk_cli,
        "_emit_sections",
        lambda sections, output_dir: captured.update({"sections": [title for title, _ in sections]}),
    )

    result = cli.main(
        [
            "brk",
            "sotp",
            "--price-change",
            "1M",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured["sections"] == [
        "Valuation Assumptions",
        "Market Anchor",
        "Public Equity Portfolio Summary",
        "Quoted Holdings Summary",
        "Liquidity Snapshot",
        "Market-Implied SOTP Bridge",
        "Operating Business Context",
        "BRK vs Holdings Price Change (1M)",
    ]
    assert "BRK vs Holdings Price Change (1M)" in captured["sections"]


def test_brk_segments_cli_rejects_invalid_range(tmp_path: Path):
    result = cli.main(
        [
            "brk",
            "segments",
            "--period",
            "annual",
            "--start-quarter",
            "1",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 1


def test_statements_cli_writes_files_for_yahoo_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli, "YahooFinanceClient", lambda: FakeYahooClient())
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
                        "security_id": "ticker:PAR:BNP.PA",
                        "ticker": "BNP.PA",
                        "exchange": "PAR",
                        "company_name": "BNP Paribas SA",
                        "country": "France",
                        "currency": "EUR",
                        "sec_company": None,
                    },
                )(),
                "company_facts": None,
                "statement_source": "yahoo",
            },
        )(),
    )

    result = cli.main(
        [
            "statements",
            "BNP.PA",
            "--statement",
            "income",
            "--period",
            "annual",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert (tmp_path / "BNP-PA" / "income_statement_annual.csv").exists()


def test_statements_cli_uses_wide_default_limit_for_filtered_ranges(monkeypatch, tmp_path: Path):
    captured = {}
    
    def fake_build_statement_table(company_facts, statement, period, limit=4, **kwargs):
        captured["limit"] = limit
        return pd.DataFrame([{"metric": "revenue", "unit": "USD", "2025 Q4": 100.0}])

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
                        "company_name": "APPLE INC",
                        "country": "United States",
                        "sec_company": SecCompany(
                            ticker="AAPL",
                            cik="0000320193",
                            name="APPLE INC",
                            exchange="NASDAQ",
                        ),
                    },
                )(),
                "company_facts": {"facts": {}},
                "statement_source": "sec",
            },
        )(),
    )
    monkeypatch.setattr(
        cli,
        "build_statement_table",
        fake_build_statement_table,
    )

    result = cli.main(
        [
            "statements",
            "AAPL",
            "--statement",
            "cashflow",
            "--period",
            "quarterly",
            "--start-year",
            "2019",
            "--end-year",
            "2025",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured["limit"] == 99


def test_statements_cli_honors_explicit_limit_for_filtered_ranges(monkeypatch, tmp_path: Path):
    captured = {}
    
    def fake_build_statement_table(company_facts, statement, period, limit=4, **kwargs):
        captured["limit"] = limit
        return pd.DataFrame([{"metric": "revenue", "unit": "USD", "2025 Q4": 100.0}])

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
                        "company_name": "APPLE INC",
                        "country": "United States",
                        "sec_company": SecCompany(
                            ticker="AAPL",
                            cik="0000320193",
                            name="APPLE INC",
                            exchange="NASDAQ",
                        ),
                    },
                )(),
                "company_facts": {"facts": {}},
                "statement_source": "sec",
            },
        )(),
    )
    monkeypatch.setattr(
        cli,
        "build_statement_table",
        fake_build_statement_table,
    )

    result = cli.main(
        [
            "statements",
            "AAPL",
            "--statement",
            "cashflow",
            "--period",
            "quarterly",
            "--start-year",
            "2019",
            "--end-year",
            "2025",
            "--limit",
            "12",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured["limit"] == 12


def test_statements_cli_errors_when_no_statement_rows_are_available(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cli, "YahooFinanceClient", lambda: FakeYahooClient())
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
                        "security_id": "ticker:PAR:MC.PA",
                        "ticker": "MC.PA",
                        "exchange": "PAR",
                        "company_name": "LVMH",
                        "country": "France",
                        "currency": "EUR",
                        "sec_company": None,
                    },
                )(),
                "company_facts": None,
                "statement_source": "yahoo",
            },
        )(),
    )
    monkeypatch.setattr(
        FakeYahooClient,
        "fetch_statement_frame",
        lambda self, ticker, *, statement, period: pd.DataFrame(),
    )

    result = cli.main(
        [
            "statements",
            "MC.PA",
            "--statement",
            "income",
            "--period",
            "quarterly",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 1
    assert not (tmp_path / "MC-PA" / "income_statement_quarterly.csv").exists()


def test_company_cli_json_format_writes_bundle_and_section_files(monkeypatch, tmp_path: Path, capsys):
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
                    "company_name": "BERKSHIRE HATHAWAY INC",
                    "country": "United States",
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
            "company_profile": {
                "country": "United States",
                "currency": "USD",
                "sector": "Financials",
            },
        },
    )())

    result = cli.main(["company", "BRK-B", "--format", "json", "--outdir", str(tmp_path)])

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["command"] == "company"
    assert "company" in output["sections"]
    assert "overview" in output["sections"]
    assert (tmp_path / "BRK-B" / "bundle.json").exists()
    assert (tmp_path / "BRK-B" / "company.json").exists()
    assert (tmp_path / "BRK-B" / "overview.json").exists()
    assert not (tmp_path / "BRK-B" / "company.md").exists()


def test_statements_cli_json_format_prints_machine_readable_bundle(monkeypatch, tmp_path: Path, capsys):
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
                        "company_name": "APPLE INC",
                        "country": "United States",
                        "sec_company": SecCompany(
                            ticker="AAPL",
                            cik="0000320193",
                            name="APPLE INC",
                            exchange="NASDAQ",
                        ),
                    },
                )(),
                "company_facts": {"facts": {}},
                "statement_source": "sec",
            },
        )(),
    )
    monkeypatch.setattr(
        cli,
        "build_statement_table",
        lambda company_facts, statement, period, limit=4, **kwargs: pd.DataFrame(
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
            "--format",
            "json",
            "--outdir",
            str(tmp_path),
        ]
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["command"] == "statements"
    assert "income_statement_annual" in output["sections"]
    assert output["sections"]["income_statement_annual"][0]["metric"] == "revenue"
    assert (tmp_path / "AAPL" / "income_statement_annual.json").exists()
