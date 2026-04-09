"""SEC EDGAR provider helpers."""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd
import requests
import xml.etree.ElementTree as ET

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

    def _get_json(self, url: str) -> Mapping[str, Any]:
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

        payload = self._get_json(f"{SEC_FILES_BASE_URL}/company_tickers_exchange.json")
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

    def fetch_submissions(self, cik: int | str) -> Mapping[str, Any]:
        return self._get_json(
            f"{SEC_DATA_BASE_URL}/submissions/CIK{_format_cik(cik)}.json"
        )

    def fetch_company_facts(self, cik: int | str) -> Mapping[str, Any]:
        return self._get_json(
            f"{SEC_DATA_BASE_URL}/api/xbrl/companyfacts/CIK{_format_cik(cik)}.json"
        )

    def fetch_filing_index(self, cik: int | str, accession_number: str) -> Mapping[str, Any]:
        accession = accession_number.replace("-", "")
        cik_number = int(_format_cik(cik))
        return self._get_json(
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
        tables = pd.read_html(StringIO(text))
        if not tables:
            return pd.DataFrame()
        return tables[0]

    def fetch_company_bundle(
        self,
        ticker: str,
        include_company_facts: bool = False,
    ) -> Dict[str, Any]:
        """Return a small SEC payload bundle for downstream commands."""
        company = self.lookup_company(ticker)
        submissions = self.fetch_submissions(company.cik)
        bundle = {
            "company": company,
            "submissions": submissions,
        }
        if include_company_facts:
            bundle["company_facts"] = self.fetch_company_facts(company.cik)
        return bundle
