"""SEC EDGAR provider helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import pandas as pd
import requests

from valuation.config import get_sec_user_agent, using_default_sec_user_agent

SEC_FILES_BASE_URL = "https://www.sec.gov/files"
SEC_DATA_BASE_URL = "https://data.sec.gov"


def _format_cik(cik: int | str) -> str:
    """Normalize a CIK into the zero-padded format used by SEC endpoints."""
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    return digits.zfill(10)


@dataclass
class SecCompany:
    ticker: str
    cik: str
    name: str
    exchange: Optional[str] = None


@dataclass(frozen=True)
class SecFilingReport:
    html_file_name: str
    short_name: str
    long_name: str
    menu_category: Optional[str] = None
    position: Optional[int] = None


class SecClient:
    """Very small SEC client for ticker lookup and filing retrieval."""

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self._company_tickers_cache: Optional[List[SecCompany]] = None
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": get_sec_user_agent(),
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def _fetch_json_uncached(self, url: str) -> Mapping[str, Any]:
        """Fetch JSON and convert common SEC access failures into actionable errors."""
        response = self.session.get(url, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            if response.status_code == 403 and using_default_sec_user_agent():
                raise RuntimeError(
                    "SEC rejected the default user agent. Set "
                    "VALUATION_SEC_USER_AGENT to something like "
                    "'valuationFramework/0.1 your-email@example.com'."
                ) from exc
            raise
        return response.json()

    def _get_text(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            if response.status_code == 403 and using_default_sec_user_agent():
                raise RuntimeError(
                    "SEC rejected the default user agent. Set "
                    "VALUATION_SEC_USER_AGENT to something like "
                    "'valuationFramework/0.1 your-email@example.com'."
                ) from exc
            raise
        return response.text

    def fetch_company_tickers(self) -> List[SecCompany]:
        """Load the SEC ticker-to-CIK mapping once per call."""
        if self._company_tickers_cache is not None:
            return self._company_tickers_cache

        payload = self._fetch_json_uncached(
            f"{SEC_FILES_BASE_URL}/company_tickers_exchange.json"
        )
        fields = payload.get("fields", [])
        rows = payload.get("data", [])
        companies: List[SecCompany] = []
        for row in rows:
            item = dict(zip(fields, row))
            ticker = str(item.get("ticker", "")).upper()
            if not ticker:
                continue
            companies.append(
                SecCompany(
                    ticker=ticker,
                    cik=_format_cik(item.get("cik", "")),
                    name=str(item.get("name", "")).strip(),
                    exchange=item.get("exchange"),
                )
            )
        self._company_tickers_cache = companies
        return companies

    def lookup_company(self, ticker: str) -> SecCompany:
        """Resolve a public ticker into the SEC's canonical company metadata."""
        target = ticker.upper().replace(".", "-")
        for company in self.fetch_company_tickers():
            if company.ticker == target:
                return company
        raise LookupError("Ticker not found in SEC company mapping: %s" % ticker)

    def lookup_company_by_cik(self, cik: int | str) -> SecCompany:
        """Resolve a CIK into the SEC's canonical company metadata."""
        target = _format_cik(cik)
        for company in self.fetch_company_tickers():
            if company.cik == target:
                return company
        raise LookupError("CIK not found in SEC company mapping: %s" % cik)

    def fetch_submissions(self, cik: int | str) -> Mapping[str, Any]:
        return self._fetch_json_uncached(
            f"{SEC_DATA_BASE_URL}/submissions/CIK{_format_cik(cik)}.json"
        )

    def fetch_company_facts(self, cik: int | str) -> Mapping[str, Any]:
        return self._fetch_json_uncached(
            f"{SEC_DATA_BASE_URL}/api/xbrl/companyfacts/CIK{_format_cik(cik)}.json"
        )

    def fetch_filing_index(self, cik: int | str, accession_number: str) -> Mapping[str, Any]:
        accession = accession_number.replace("-", "")
        cik_number = int(_format_cik(cik))
        return self._fetch_json_uncached(
            f"https://www.sec.gov/Archives/edgar/data/{cik_number}/{accession}/index.json"
        )

    def fetch_filing_text(
        self,
        cik: int | str,
        accession_number: str,
        filename: str,
    ) -> str:
        accession = accession_number.replace("-", "")
        cik_number = int(_format_cik(cik))
        return self._get_text(
            f"https://www.sec.gov/Archives/edgar/data/{cik_number}/{accession}/{filename}"
        )

    def fetch_filing_summary_reports(
        self,
        cik: int | str,
        accession_number: str,
    ) -> List[SecFilingReport]:
        """Return report metadata from an SEC filing's FilingSummary.xml."""
        text = self.fetch_filing_text(cik, accession_number, "FilingSummary.xml")
        root = ET.fromstring(text)
        reports: List[SecFilingReport] = []
        for report in root.findall(".//Report"):
            html_file_name = (report.findtext("HtmlFileName") or "").strip()
            if not html_file_name:
                continue
            position_text = (report.findtext("Position") or "").strip()
            reports.append(
                SecFilingReport(
                    html_file_name=html_file_name,
                    short_name=(report.findtext("ShortName") or "").strip(),
                    long_name=(report.findtext("LongName") or "").strip(),
                    menu_category=(report.findtext("MenuCategory") or "").strip() or None,
                    position=int(position_text) if position_text.isdigit() else None,
                )
            )
        return reports

    def fetch_report_table(
        self,
        cik: int | str,
        accession_number: str,
        filename: str,
    ) -> pd.DataFrame:
        """Read the first HTML table from a filing report page."""
        text = self.fetch_filing_text(cik, accession_number, filename)
        return _parse_first_html_table(text)

    def fetch_company_bundle(
        self,
        ticker: str,
        include_company_facts: bool = False,
    ) -> Dict[str, Any]:
        """Return a small SEC payload bundle for downstream commands."""
        company = self.lookup_company(ticker)
        with ThreadPoolExecutor(max_workers=2) as executor:
            submissions_future = executor.submit(self.fetch_submissions, company.cik)
            company_facts_future = None
            if include_company_facts:
                company_facts_future = executor.submit(self.fetch_company_facts, company.cik)

            submissions = submissions_future.result()
        bundle = {
            "company": company,
            "submissions": submissions,
        }
        if company_facts_future is not None:
            bundle["company_facts"] = company_facts_future.result()
        return bundle


def _parse_first_html_table(text: str) -> pd.DataFrame:
    soup = BeautifulSoup(text, "html.parser")
    table = soup.find("table")
    if table is None:
        return pd.DataFrame()

    rows = _expand_html_table(table)
    if not rows:
        return pd.DataFrame()

    width = max(len(row) for row in rows)
    rows = [_pad_row(row, width) for row in rows]
    header_row_count = _count_header_rows(table)
    if header_row_count > len(rows):
        header_row_count = len(rows)

    if header_row_count:
        columns = _build_header_labels(rows[:header_row_count], width)
        body = rows[header_row_count:]
    else:
        columns = [f"column_{index + 1}" for index in range(width)]
        body = rows

    return pd.DataFrame(body, columns=columns)


def _expand_html_table(table) -> list[list[str]]:
    pending_spans: dict[int, tuple[str, int]] = {}
    rows: list[list[str]] = []

    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        row: list[str] = []
        column_index = 0

        def consume_pending() -> None:
            nonlocal column_index
            while column_index in pending_spans:
                text, remaining = pending_spans[column_index]
                row.append(text)
                if remaining <= 1:
                    del pending_spans[column_index]
                else:
                    pending_spans[column_index] = (text, remaining - 1)
                column_index += 1

        consume_pending()
        for cell in cells:
            consume_pending()
            text = " ".join(cell.get_text(" ", strip=True).replace("\xa0", " ").split())
            colspan = _parse_span_count(cell.get("colspan"))
            rowspan = _parse_span_count(cell.get("rowspan"))
            for offset in range(colspan):
                row.append(text)
                if rowspan > 1:
                    pending_spans[column_index + offset] = (text, rowspan - 1)
            column_index += colspan
        consume_pending()
        rows.append(row)

    return rows


def _count_header_rows(table) -> int:
    count = 0
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        if any(cell.name == "td" for cell in cells):
            break
        count += 1
    return count


def _build_header_labels(rows: list[list[str]], width: int) -> list[str]:
    labels: list[str] = []
    for column_index in range(width):
        parts: list[str] = []
        for row in rows:
            value = row[column_index].strip() if column_index < len(row) else ""
            if value and (not parts or parts[-1] != value):
                parts.append(value)
        labels.append(" ".join(parts) if parts else f"column_{column_index + 1}")
    return labels


def _pad_row(row: list[str], width: int) -> list[str]:
    if len(row) >= width:
        return row
    return row + [""] * (width - len(row))


def _parse_span_count(raw_value: object) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return 1
    return max(value, 1)
