import pandas as pd

from valuation.brk.statements import supplement_brk_income_statement_eps_shares
from valuation.data.providers.sec import SecCompany, SecFilingReport


class FakeSecClient:
    def __init__(self, tables):
        self.tables = tables

    def fetch_submissions(self, cik):
        assert cik == "0001067983"
        return {
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "10-Q"],
                    "filingDate": ["2026-03-02", "2025-11-03", "2025-08-04"],
                    "reportDate": ["2025-12-31", "2025-09-30", "2025-06-30"],
                    "accessionNumber": ["annual", "q3", "q2"],
                    "primaryDocument": ["brka.htm", "brka-q3.htm", "brka-q2.htm"],
                }
            }
        }

    def fetch_filing_summary_reports(self, cik, accession_number):
        assert cik == "0001067983"
        return [
            SecFilingReport(
                html_file_name=f"{accession_number}.htm",
                short_name="Consolidated Statements of Earnings",
                long_name="Consolidated Statements of Earnings",
            )
        ]

    def fetch_report_table(self, cik, accession_number, filename):
        assert cik == "0001067983"
        assert filename == f"{accession_number}.htm"
        return self.tables[accession_number]


def test_supplement_brk_income_statement_adds_annual_class_b_eps_and_shares():
    base = pd.DataFrame(
        [
            {"metric": "revenue", "unit": "USD", "FY 2025": 371.0, "FY 2024": 370.0},
            {"metric": "net_income", "unit": "USD", "FY 2025": 67.0, "FY 2024": 89.0},
        ]
    )
    annual = pd.DataFrame(
        [
            ["Equivalent Class B [Member]", "", "", ""],
            ["Net earnings per average equivalent", "[1]", "$ 31.04", "$ 41.27"],
            ["Average equivalent shares outstanding", "", "2,157,335,139", "2,156,580,296"],
        ],
        columns=[
            "Consolidated Statements of Earnings",
            "Consolidated Statements of Earnings",
            "12 Months Ended Dec. 31, 2025",
            "12 Months Ended Dec. 31, 2024",
        ],
    )

    result = supplement_brk_income_statement_eps_shares(
        base,
        sec_client=FakeSecClient({"annual": annual}),
        company=_brk_company(),
        submissions=None,
        period="annual",
    )

    assert list(result["metric"]) == ["revenue", "net_income", "diluted_eps", "diluted_shares"]
    eps = result[result["metric"] == "diluted_eps"].iloc[0]
    shares = result[result["metric"] == "diluted_shares"].iloc[0]
    assert eps["FY 2025"] == 31.04
    assert eps["FY 2024"] == 41.27
    assert shares["FY 2025"] == 2_157_335_139.0
    assert shares["FY 2024"] == 2_156_580_296.0


def test_supplement_brk_income_statement_uses_only_three_month_quarter_columns():
    base = pd.DataFrame(
        [
            {
                "metric": "net_income",
                "unit": "USD",
                "2025 Q4": 19.2,
                "2025 Q3": 30.8,
                "2025 Q2": 12.37,
            }
        ]
    )
    q3 = pd.DataFrame(
        [
            ["Equivalent Class B [Member]", "", "", "", "", ""],
            ["Net earnings per average equivalent", "[1]", "$ 14.28", "$ 12.18", "$ 22.14", "$ 32.14"],
            ["Average equivalent shares outstanding", "", "2,157,335,139", "2,155,058,383", "2,157,335,139", "2,156,427,917"],
        ],
        columns=[
            "Consolidated Statements of Earnings",
            "Consolidated Statements of Earnings",
            "3 Months Ended Sep. 30, 2025",
            "3 Months Ended Sep. 30, 2024",
            "9 Months Ended Sep. 30, 2025",
            "9 Months Ended Sep. 30, 2024",
        ],
    )
    q2 = pd.DataFrame(
        [
            ["Equivalent Class B [Member]", "", "", "", "", ""],
            ["Net earnings per average equivalent", "[1]", "$ 5.73", "$ 14.08", "$ 7.87", "$ 19.96"],
            ["Average equivalent shares outstanding", "", "2,157,335,139", "2,155,185,283", "2,157,335,139", "2,157,120,209"],
        ],
        columns=[
            "Consolidated Statements of Earnings",
            "Consolidated Statements of Earnings",
            "3 Months Ended Jun. 30, 2025",
            "3 Months Ended Jun. 30, 2024",
            "6 Months Ended Jun. 30, 2025",
            "6 Months Ended Jun. 30, 2024",
        ],
    )

    result = supplement_brk_income_statement_eps_shares(
        base,
        sec_client=FakeSecClient({"q3": q3, "q2": q2}),
        company=_brk_company(),
        submissions=None,
        period="quarterly",
    )

    eps = result[result["metric"] == "diluted_eps"].iloc[0]
    shares = result[result["metric"] == "diluted_shares"].iloc[0]
    assert pd.isna(eps["2025 Q4"])
    assert eps["2025 Q3"] == 14.28
    assert eps["2025 Q2"] == 5.73
    assert shares["2025 Q3"] == 2_157_335_139.0
    assert shares["2025 Q2"] == 2_157_335_139.0


def _brk_company():
    return SecCompany(
        ticker="BRK-B",
        cik="0001067983",
        name="BERKSHIRE HATHAWAY INC",
        exchange="NYSE",
    )
