"""Berkshire-specific service orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

import pandas as pd

from valuation.brk.holdings import parse_13f_infotable
from valuation.brk.segments import BrkSegmentReportSet, SEGMENT_REPORT_LABELS
from valuation.brk.segments import normalize_segment_report_table
from valuation.data.providers.sec import SecClient, SecCompany
from valuation.data.providers.yahoo import YahooFinanceClient

BRK_B_TICKER = "BRK-B"
BRK_A_TICKER = "BRK-A"
BRK_A_TO_B_CONVERSION = 1500
BALANCE_SHEET_REPORT_SHORT_NAME = "Consolidated Balance Sheets"
SEGMENT_REVENUES_REPORT_SHORT_NAME = "Business segment data - Revenues (Detail)"
SEGMENT_PRETAX_REPORT_SHORT_NAME = "Business segment data - Earnings before income taxes (Detail)"


@dataclass
class BrkOverviewBundle:
    """Minimal Berkshire data bundle for reports and later valuation logic."""

    company: SecCompany
    market_snapshot: Mapping[str, Any]
    submissions: Mapping[str, Any]
    company_facts: Mapping[str, Any]


@dataclass
class Brk13FBundle:
    """Latest Berkshire 13F filing plus parsed holdings table."""

    company: SecCompany
    filing_date: str
    accession_number: str
    information_table_filename: str
    holdings: pd.DataFrame


@dataclass
class BrkLiquidityFiling:
    """One Berkshire filing with a parsed balance-sheet report table."""

    filing_date: str
    accession_number: str
    form: str
    balance_sheet: pd.DataFrame


@dataclass
class BrkLiquidityBundle:
    """Berkshire filing bundle for liquidity analysis."""

    company: SecCompany
    filings: list[BrkLiquidityFiling]


@dataclass
class BrkSegmentFiling:
    """One Berkshire filing with normalized segment report tables."""

    filing_date: str
    accession_number: str
    form: str
    reports: BrkSegmentReportSet


@dataclass
class BrkSegmentsBundle:
    """Berkshire segment report bundles across filings."""

    company: SecCompany
    filings: list[BrkSegmentFiling]


@dataclass
class BrkValuationBundle:
    """Core Berkshire inputs for a first transparent SOTP bridge."""

    overview: BrkOverviewBundle
    holdings: Brk13FBundle
    liquidity: BrkLiquidityBundle
    segments: BrkSegmentsBundle


def fetch_brk_overview(
    sec_client: Optional[SecClient] = None,
    yahoo_client: Optional[YahooFinanceClient] = None,
) -> BrkOverviewBundle:
    """Fetch the current Berkshire data needed for overview tables."""
    sec = sec_client or SecClient()
    yahoo = yahoo_client or YahooFinanceClient()

    market_snapshot = yahoo.fetch_price_snapshot(BRK_B_TICKER)
    company_bundle = sec.fetch_company_bundle(
        BRK_B_TICKER,
        include_company_facts=True,
    )

    return BrkOverviewBundle(
        company=company_bundle["company"],
        market_snapshot=market_snapshot,
        submissions=company_bundle["submissions"],
        company_facts=company_bundle["company_facts"],
    )


def fetch_brk_liquidity(
    sec_client: Optional[SecClient] = None,
    *,
    period: str = "annual",
    limit: int | None = 1,
    start_year: int | None = None,
    end_year: int | None = None,
    start_quarter: int | None = None,
    end_quarter: int | None = None,
) -> BrkLiquidityBundle:
    """Fetch Berkshire balance-sheet reports for liquidity analysis."""
    sec = sec_client or SecClient()
    company_bundle = sec.fetch_company_bundle(BRK_B_TICKER)
    if limit == 0:
        return BrkLiquidityBundle(
            company=company_bundle["company"],
            filings=[],
        )
    filings = find_recent_filings(
        company_bundle["submissions"],
        forms=_forms_for_period(period),
        limit=None,
    )
    filings = _filter_filings_by_period_range(
        filings,
        period=period,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    if limit is not None:
        filings = filings[:limit]
    if not filings:
        raise LookupError("No Berkshire filings found for the selected period range")
    liquidity_filings = []
    for filing in filings:
        reports = sec.fetch_filing_summary_reports(
            company_bundle["company"].cik,
            filing["accession_number"],
        )
        report = _find_report(reports, BALANCE_SHEET_REPORT_SHORT_NAME)
        liquidity_filings.append(
            BrkLiquidityFiling(
                filing_date=filing["filing_date"],
                accession_number=filing["accession_number"],
                form=filing["form"],
                balance_sheet=sec.fetch_report_table(
                    company_bundle["company"].cik,
                    filing["accession_number"],
                    report.html_file_name,
                ),
            )
        )
    return BrkLiquidityBundle(
        company=company_bundle["company"],
        filings=liquidity_filings,
    )


def fetch_latest_brk_13f(sec_client: Optional[SecClient] = None) -> Brk13FBundle:
    """Fetch Berkshire's latest reported 13F holdings from the SEC."""
    sec = sec_client or SecClient()
    company_bundle = sec.fetch_company_bundle(BRK_B_TICKER)
    company = company_bundle["company"]
    submissions = company_bundle["submissions"]
    filing = find_brk_13f_filings(submissions, limit=1)[0]
    filing_index = sec.fetch_filing_index(company.cik, filing["accession_number"])
    information_table_filename = _find_information_table_filename(
        sec,
        company.cik,
        filing["accession_number"],
        filing_index,
    )
    xml_text = sec.fetch_filing_text(
        company.cik,
        filing["accession_number"],
        information_table_filename,
    )
    holdings = parse_13f_infotable(xml_text)
    return Brk13FBundle(
        company=company,
        filing_date=filing["filing_date"],
        accession_number=filing["accession_number"],
        information_table_filename=information_table_filename,
        holdings=holdings,
    )


def fetch_brk_segments(
    sec_client: Optional[SecClient] = None,
    *,
    period: str = "annual",
    limit: int | None = 1,
    start_year: int | None = None,
    end_year: int | None = None,
    start_quarter: int | None = None,
    end_quarter: int | None = None,
) -> BrkSegmentsBundle:
    """Fetch Berkshire segment-report tables across annual or quarterly filings."""
    sec = sec_client or SecClient()
    company_bundle = sec.fetch_company_bundle(BRK_B_TICKER)
    company = company_bundle["company"]
    submissions = company_bundle["submissions"]
    if limit == 0:
        return BrkSegmentsBundle(company=company, filings=[])
    filings = find_recent_filings(
        submissions,
        forms=_forms_for_period(period),
        limit=None,
    )
    filings = _filter_filings_by_period_range(
        filings,
        period=period,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    if limit is not None:
        filings = filings[:limit]
    if not filings:
        raise LookupError("No Berkshire filings found for the selected period range")
    segment_filings = []
    for filing in filings:
        reports = sec.fetch_filing_summary_reports(company.cik, filing["accession_number"])
        report_map = {report.short_name: report for report in reports}

        def load_report(short_name: str) -> pd.DataFrame:
            report = report_map[short_name]
            frame = sec.fetch_report_table(
                company.cik,
                filing["accession_number"],
                report.html_file_name,
            )
            return normalize_segment_report_table(frame, report_name=short_name)

        report_set = BrkSegmentReportSet(
            filing_date=filing["filing_date"],
            accession_number=filing["accession_number"],
            earnings_detail=_load_segment_earnings_detail(
                report_map,
                load_report,
            ),
            reconciliation_detail=_load_optional_segment_report(
                report_map,
                load_report,
                SEGMENT_REPORT_LABELS["reconciliations"],
            ),
            additional_detail=_load_optional_segment_report(
                report_map,
                load_report,
                SEGMENT_REPORT_LABELS["additional"],
            ),
        )
        segment_filings.append(
            BrkSegmentFiling(
                filing_date=filing["filing_date"],
                accession_number=filing["accession_number"],
                form=filing["form"],
                reports=report_set,
            )
        )
    return BrkSegmentsBundle(
        company=company,
        filings=segment_filings,
    )


def fetch_brk_valuation_bundle(
    sec_client: Optional[SecClient] = None,
    yahoo_client: Optional[YahooFinanceClient] = None,
    *,
    period: str = "annual",
) -> BrkValuationBundle:
    """Fetch the current Berkshire inputs needed for a first SOTP bridge."""
    sec = sec_client or SecClient()
    yahoo = yahoo_client or YahooFinanceClient()
    return BrkValuationBundle(
        overview=fetch_brk_overview(sec_client=sec, yahoo_client=yahoo),
        holdings=fetch_latest_brk_13f(sec_client=sec),
        liquidity=fetch_brk_liquidity(sec_client=sec, period=period, limit=1),
        segments=fetch_brk_segments(sec_client=sec, period=period, limit=1),
    )


def find_recent_filings(
    submissions: Mapping[str, Any],
    forms: tuple[str, ...],
    limit: int | None = 1,
) -> list[dict[str, str]]:
    """Return recent SEC filing rows filtered by form type."""
    recent = submissions.get("filings", {}).get("recent", {})
    form_rows = recent.get("form", [])
    matches = []
    for index, form in enumerate(form_rows):
        if form in forms:
            matches.append(
                {
                    "filing_date": recent["filingDate"][index],
                    "report_date": recent.get("reportDate", [None] * len(form_rows))[index],
                    "accession_number": recent["accessionNumber"][index],
                    "form": form,
                    "primary_document": recent.get("primaryDocument", [None] * len(form_rows))[index],
                }
            )
            if limit is not None and len(matches) >= limit:
                break
    if not matches:
        raise LookupError(f"No filing found for forms: {forms}")
    return matches


def find_brk_13f_filings(
    submissions: Mapping[str, Any],
    limit: int = 1,
) -> list[dict[str, str]]:
    """Return recent Berkshire 13F filing rows from SEC submissions."""
    return find_recent_filings(submissions, forms=("13F-HR", "13F-HR/A"), limit=limit)


def _find_information_table_filename(
    sec_client: SecClient,
    cik: str,
    accession_number: str,
    filing_index: Mapping[str, Any],
) -> str:
    items = filing_index.get("directory", {}).get("item", [])
    xml_candidates = [
        item["name"]
        for item in items
        if item.get("name", "").lower().endswith(".xml")
        and item.get("name") != "primary_doc.xml"
    ]
    for filename in xml_candidates:
        text = sec_client.fetch_filing_text(cik, accession_number, filename)
        if "<informationTable" in text:
            return filename
    raise LookupError("Could not locate a 13F information table XML file.")


def _forms_for_period(period: str) -> tuple[str, ...]:
    if period == "annual":
        return ("10-K",)
    if period == "quarterly":
        return ("10-Q",)
    raise ValueError(f"Unsupported Berkshire period: {period}")


def _find_report(reports: list, short_name: str):
    for report in reports:
        if report.short_name == short_name:
            return report
    raise LookupError(f"Could not find filing report: {short_name}")


def _load_segment_earnings_detail(report_map, load_report) -> pd.DataFrame:
    if SEGMENT_REPORT_LABELS["earnings"] in report_map:
        return load_report(SEGMENT_REPORT_LABELS["earnings"])
    split_tables = []
    for short_name in (
        SEGMENT_REVENUES_REPORT_SHORT_NAME,
        SEGMENT_PRETAX_REPORT_SHORT_NAME,
    ):
        if short_name in report_map:
            split_tables.append(load_report(short_name))
    if split_tables:
        return pd.concat(split_tables, ignore_index=True)
    raise LookupError(f"Could not find filing report: {SEGMENT_REPORT_LABELS['earnings']}")


def _load_optional_segment_report(report_map, load_report, short_name: str) -> pd.DataFrame:
    if short_name not in report_map:
        return pd.DataFrame()
    return load_report(short_name)


def _filter_filings_by_period_range(
    filings: list[dict[str, str]],
    *,
    period: str,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> list[dict[str, str]]:
    if not any(
        value is not None
        for value in (start_year, end_year, start_quarter, end_quarter)
    ):
        return filings
    filtered = []
    for filing in filings:
        period_key = _filing_period_key(filing, period=period)
        if period_key is None:
            continue
        if start_year is not None and period_key < _start_period_key(
            period=period,
            year=start_year,
            quarter=start_quarter,
        ):
            continue
        if end_year is not None and period_key > _end_period_key(
            period=period,
            year=end_year,
            quarter=end_quarter,
        ):
            continue
        filtered.append(filing)
    return filtered


def _filing_period_key(filing: Mapping[str, str], *, period: str) -> tuple[int, int] | None:
    report_date = filing.get("report_date") or filing.get("filing_date")
    if not report_date:
        return None
    try:
        year_text, month_text, day_text = report_date.split("-")
        year = int(year_text)
        month = int(month_text)
        day = int(day_text)
    except (ValueError, AttributeError):
        return None
    if period == "annual":
        return (year, 0)
    quarter = ((month - 1) // 3) + 1
    if month == 12 and day == 31 and filing.get("form") == "10-K":
        quarter = 4
    return (year, quarter)


def _start_period_key(*, period: str, year: int, quarter: int | None) -> tuple[int, int]:
    if period == "annual":
        return (year, 0)
    return (year, quarter or 1)


def _end_period_key(*, period: str, year: int, quarter: int | None) -> tuple[int, int]:
    if period == "annual":
        return (year, 0)
    return (year, quarter or 4)
