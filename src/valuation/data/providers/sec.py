"""SEC EDGAR provider helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

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


class SecClient:
    """Very small SEC client for ticker lookup and filing retrieval."""

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
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

    def fetch_company_tickers(self) -> List[SecCompany]:
        """Load the SEC ticker-to-CIK mapping once per call."""
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

    def fetch_company_bundle(self, ticker: str) -> Dict[str, Any]:
        """Return the minimum SEC payload currently needed by the CLI."""
        company = self.lookup_company(ticker)
        submissions = self.fetch_submissions(company.cik)
        return {
            "company": company,
            "submissions": submissions,
        }
