import pandas as pd

from valuation.brk.service import (
    BRK_B_TICKER,
    fetch_brk_segments,
    fetch_brk_13f_history,
    fetch_brk_liquidity,
    fetch_brk_overview,
    fetch_brk_valuation_bundle,
    find_recent_filings,
    find_brk_13f_filings,
)
from valuation.data.providers.sec import SecCompany


class FakeSecClient:
    def fetch_company_bundle(self, ticker, include_company_facts=False):
        assert ticker == BRK_B_TICKER
        bundle = {
            "company": SecCompany(
                ticker="BRK-B",
                cik="0001067983",
                name="BERKSHIRE HATHAWAY INC",
                exchange="NYSE",
            ),
            "submissions": {
                "filings": {
                    "recent": {
                        "form": ["10-K", "10-Q", "13F-HR", "13F-HR"],
                        "filingDate": ["2026-03-02", "2025-11-03", "2026-02-14", "2025-11-14"],
                        "reportDate": ["2025-12-31", "2025-09-30", "2025-12-31", "2025-09-30"],
                        "accessionNumber": ["0001", "0003", "0002", "0004"],
                        "primaryDocument": ["brka.htm", "brka-q3.htm", "13f.htm", "13f-q3.htm"],
                    }
                }
            },
        }
        if include_company_facts:
            bundle["company_facts"] = {"facts": {}}
        return bundle

    def fetch_filing_summary_reports(self, cik, accession_number):
        assert cik == "0001067983"
        assert accession_number in {"0001", "0003"}
        from valuation.data.providers.sec import SecFilingReport

        return [
            SecFilingReport(
                html_file_name="R2.htm",
                short_name="Consolidated Balance Sheets",
                long_name="Consolidated Balance Sheets",
            ),
            SecFilingReport(
                html_file_name="R136.htm",
                short_name="Business segment data - Earnings data (Detail)",
                long_name="Business segment data - Earnings data (Detail)",
            ),
            SecFilingReport(
                html_file_name="R137.htm",
                short_name="Business segment data - Reconciliations of Revenues and Earnings before income taxes (Detail)",
                long_name="Business segment data - Reconciliations of Revenues and Earnings before income taxes (Detail)",
            ),
            SecFilingReport(
                html_file_name="R138.htm",
                short_name="Business segment data - Additional tabular disclosures (Detail)",
                long_name="Business segment data - Additional tabular disclosures (Detail)",
            ),
        ]

    def fetch_report_table(self, cik, accession_number, filename):
        assert cik == "0001067983"
        if filename == "R2.htm":
            return pd.DataFrame(
                [
                    ["Cash and cash equivalents", "", "47,719", "44,333"],
                    ["Short-term investments in U.S. Treasury Bills", "", "321,434", "286,472"],
                    ["Investments in fixed maturity securities", "", "17,816", "15,364"],
                ],
                columns=[
                    "Consolidated Balance Sheets",
                    "Consolidated Balance Sheets",
                    "Dec. 31, 2025",
                    "Dec. 31, 2024",
                ],
            )
        if accession_number == "0001":
            return pd.DataFrame(
                [
                    ["Operating Businesses [Member] | BNSF [Member]", None, None, None],
                    ["Revenues", "23", "24", "25"],
                ],
                columns=[
                    ("stub", "label"),
                    ("12 Months Ended", "Dec. 31, 2023"),
                    ("12 Months Ended", "Dec. 31, 2024"),
                    ("12 Months Ended", "Dec. 31, 2025"),
                ],
            )
        return pd.DataFrame(
            [
                ["Operating Businesses [Member] | BNSF [Member]", None, None, None, None],
                ["Revenues", "20", "19", "60", "58"],
            ],
            columns=[
                ("stub", "label"),
                ("3 Months Ended", "Sep. 30, 2025"),
                ("3 Months Ended", "Sep. 30, 2024"),
                ("9 Months Ended", "Sep. 30, 2025"),
                ("9 Months Ended", "Sep. 30, 2024"),
            ],
        )

    def fetch_filing_index(self, cik, accession_number):
        assert cik == "0001067983"
        assert accession_number in {"0002", "0004"}
        return {"directory": {"item": [{"name": "info.xml"}]}}

    def fetch_filing_text(self, cik, accession_number, filename):
        assert cik == "0001067983"
        assert accession_number in {"0002", "0004"}
        assert filename == "info.xml"
        value = "100" if accession_number == "0002" else "80"
        shares = "10" if accession_number == "0002" else "9"
        return f"""
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>{value}</value>
    <shrsOrPrnAmt>
      <sshPrnamt>{shares}</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority>
      <Sole>10</Sole>
      <Shared>0</Shared>
      <None>0</None>
    </votingAuthority>
  </infoTable>
</informationTable>
"""


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
    assert bundle.filings[0].form == "10-K"
    assert not bundle.filings[0].balance_sheet.empty


def test_fetch_brk_liquidity_supports_quarterly_history():
    bundle = fetch_brk_liquidity(
        sec_client=FakeSecClient(),
        period="quarterly",
        limit=1,
    )

    assert len(bundle.filings) == 1
    assert bundle.filings[0].form == "10-Q"


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


def test_fetch_brk_13f_history_fetches_multiple_filings():
    bundle = fetch_brk_13f_history(sec_client=FakeSecClient(), limit=2)

    assert bundle.company.ticker == "BRK-B"
    assert [filing.accession_number for filing in bundle.filings] == ["0002", "0004"]
    assert [filing.report_date for filing in bundle.filings] == ["2025-12-31", "2025-09-30"]
    assert [filing.holdings.iloc[0]["value_usd"] for filing in bundle.filings] == [100, 80]


def test_find_recent_filings_finds_first_matching_form():
    submissions = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-K", "10-Q"],
                "filingDate": ["2026-01-01", "2026-02-14", "2026-02-15"],
                "reportDate": ["2025-12-15", "2025-12-31", "2025-09-30"],
                "accessionNumber": ["0001", "0002", "0003"],
                "primaryDocument": ["a.htm", "b.htm", "c.htm"],
            }
        }
    }

    metadata = find_recent_filings(submissions, forms=("10-K",), limit=1)

    assert metadata[0]["filing_date"] == "2026-02-14"
    assert metadata[0]["report_date"] == "2025-12-31"
    assert metadata[0]["accession_number"] == "0002"


def test_fetch_brk_liquidity_filters_by_report_date_range():
    bundle = fetch_brk_liquidity(
        sec_client=FakeSecClient(),
        period="quarterly",
        limit=99,
        start_year=2025,
        start_quarter=3,
        end_year=2025,
        end_quarter=3,
    )

    assert len(bundle.filings) == 1
    assert bundle.filings[0].accession_number == "0003"


def test_fetch_brk_segments_assembles_bundle():
    fake = FakeSecClient()
    bundle = fetch_brk_segments(sec_client=fake)

    assert bundle.company.ticker == "BRK-B"
    assert bundle.filings[0].filing_date == "2026-03-02"
    assert bundle.filings[0].accession_number == "0001"


def test_fetch_brk_segments_supports_quarterly_history():
    fake = FakeSecClient()
    bundle = fetch_brk_segments(
        sec_client=fake,
        period="quarterly",
        limit=1,
    )

    assert len(bundle.filings) == 1
    assert bundle.filings[0].form == "10-Q"


def test_fetch_brk_valuation_bundle_assembles_inputs():
    bundle = fetch_brk_valuation_bundle(
        sec_client=FakeSecClient(),
        yahoo_client=FakeYahooClient(),
    )

    assert bundle.overview.market_snapshot["last_price"] == 500.0
    assert bundle.holdings.filing_date == "2026-02-14"
    assert len(bundle.liquidity.filings) == 1
    assert len(bundle.segments.filings) == 1
