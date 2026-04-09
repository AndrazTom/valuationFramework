"""Berkshire-specific service orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

import pandas as pd

from valuation.brk.holdings import parse_13f_infotable
from valuation.data.providers.sec import SecClient, SecCompany
from valuation.data.providers.yahoo import YahooFinanceClient

BRK_B_TICKER = "BRK-B"
BRK_A_TICKER = "BRK-A"
BRK_A_TO_B_CONVERSION = 1500


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
class BrkLiquidityBundle:
    """Berkshire company facts bundle for liquidity analysis."""

    company: SecCompany
    company_facts: Mapping[str, Any]


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


def fetch_brk_liquidity(sec_client: Optional[SecClient] = None) -> BrkLiquidityBundle:
    """Fetch the Berkshire facts needed for the liquidity bridge."""
    sec = sec_client or SecClient()
    company_bundle = sec.fetch_company_bundle(
        BRK_B_TICKER,
        include_company_facts=True,
    )
    return BrkLiquidityBundle(
        company=company_bundle["company"],
        company_facts=company_bundle["company_facts"],
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


def find_brk_13f_filings(
    submissions: Mapping[str, Any],
    limit: int = 1,
) -> list[dict[str, str]]:
    """Return recent Berkshire 13F filing rows from SEC submissions."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    matches = []
    for index, form in enumerate(forms):
        if form in ("13F-HR", "13F-HR/A"):
            matches.append(
                {
                    "filing_date": recent["filingDate"][index],
                    "accession_number": recent["accessionNumber"][index],
                    "form": form,
                }
            )
            if len(matches) >= limit:
                break
    if not matches:
        raise LookupError("No 13F filing found in recent submissions.")
    return matches


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
