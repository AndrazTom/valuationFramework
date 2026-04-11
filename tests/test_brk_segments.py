import pandas as pd

from valuation.brk.segments import BrkSegmentReportSet, build_top_level_operating_segments_table
from valuation.brk.segments import normalize_segment_report_table
from valuation.notation import MILLION


def test_normalize_segment_report_table():
    frame = pd.DataFrame(
        [
            ["Operating Businesses [Member] | BNSF [Member]", None, None, None],
            ["Revenues", "23", "24", "25"],
            ["Earnings before income taxes", "5", "6", "7"],
        ],
        columns=[
            ("stub", "label"),
            ("12 Months Ended", "Dec. 31, 2023"),
            ("12 Months Ended", "Dec. 31, 2024"),
            ("12 Months Ended", "Dec. 31, 2025"),
        ],
    )

    normalized = normalize_segment_report_table(frame, report_name="test")

    assert set(normalized["member_path"]) == {"Operating Businesses | BNSF"}
    assert set(normalized["metric"]) == {"Revenues", "Earnings before income taxes"}
    assert normalized[normalized["period_end"] == "2025-12-31"].iloc[0]["value"] == 25 * MILLION
    assert normalized[normalized["period_end"] == "2025-12-31"].iloc[0]["duration_months"] == 12


def test_normalize_segment_report_table_parses_quarterly_columns():
    frame = pd.DataFrame(
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

    normalized = normalize_segment_report_table(frame, report_name="test")

    three_month_row = normalized[normalized["duration_months"] == 3].iloc[0]
    nine_month_row = normalized[normalized["duration_months"] == 9].iloc[0]
    assert three_month_row["period_end"] == "2025-09-30"
    assert nine_month_row["period_end"] == "2025-09-30"


def test_build_top_level_operating_segments_table():
    report_set = BrkSegmentReportSet(
        filing_date="2025-12-31",
        accession_number="0001",
        earnings_detail=pd.DataFrame(
            [
                {"report": "earnings", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Revenues", "period_end": "2025-12-31", "value": 23 * MILLION},
                {"report": "earnings", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Earnings before income taxes", "period_end": "2025-12-31", "value": 7 * MILLION},
                {"report": "earnings", "member_path": "Operating Businesses | Insurance Group | Underwriting", "member_name": "Underwriting", "metric": "Revenues", "period_end": "2025-12-31", "value": 88 * MILLION},
            ]
        ),
        reconciliation_detail=pd.DataFrame(),
        additional_detail=pd.DataFrame(
            [
                {"report": "additional", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Identifiable assets at year-end", "period_end": "2025-12-31", "value": 100 * MILLION},
                {"report": "additional", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Capital expenditures", "period_end": "2025-12-31", "value": 2 * MILLION},
            ]
        ),
    )

    summary = build_top_level_operating_segments_table(report_set)

    assert list(summary["segment"]) == ["BNSF"]
    assert summary.iloc[0]["period_type"] == "annual"
    assert summary.iloc[0]["period_end"] == "2025-12-31"
    assert summary.iloc[0]["revenues_usd"] == 23 * MILLION
    assert summary.iloc[0]["identifiable_assets_usd"] == 100 * MILLION


def test_build_top_level_operating_segments_table_uses_three_month_quarterly_data():
    report_set = BrkSegmentReportSet(
        filing_date="2025-11-03",
        accession_number="0003",
        earnings_detail=pd.DataFrame(
            [
                {"report": "earnings", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Revenues", "duration_months": 3, "period_end": "2025-09-30", "value": 20 * MILLION},
                {"report": "earnings", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Revenues", "duration_months": 9, "period_end": "2025-09-30", "value": 60 * MILLION},
                {"report": "earnings", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Earnings before income taxes", "duration_months": 3, "period_end": "2025-09-30", "value": 5 * MILLION},
            ]
        ),
        reconciliation_detail=pd.DataFrame(),
        additional_detail=pd.DataFrame(
            [
                {"report": "additional", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Capital expenditures", "duration_months": 3, "period_end": "2025-09-30", "value": 2 * MILLION},
                {"report": "additional", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Capital expenditures", "duration_months": 9, "period_end": "2025-09-30", "value": 6 * MILLION},
                {"report": "additional", "member_path": "Operating Businesses | BNSF", "member_name": "BNSF", "metric": "Goodwill", "duration_months": 3, "period_end": "2025-09-30", "value": 100 * MILLION},
            ]
        ),
    )

    summary = build_top_level_operating_segments_table(report_set, period="quarterly")

    assert summary.iloc[0]["period_type"] == "quarterly"
    assert summary.iloc[0]["period_end"] == "2025-09-30"
    assert summary.iloc[0]["revenues_usd"] == 20 * MILLION
    assert summary.iloc[0]["capex_usd"] == 2 * MILLION
    assert summary.iloc[0]["goodwill_usd"] == 100 * MILLION
