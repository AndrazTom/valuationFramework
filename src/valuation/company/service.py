"""Generic company snapshot workflow."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import re
from typing import Any, Mapping, Optional

from valuation.data.providers.sec import SecClient, SecCompany
from valuation.data.providers.yahoo import YahooFinanceClient, YahooSearchQuote
from valuation.securities.identifiers import build_security_id


@dataclass(frozen=True)
class CompanyResolution:
    """Resolved company identity for generic CLI workflows."""

    input_value: str
    identifier_kind: str
    query_used: str
    ticker: str
    exchange: str | None
    security_id: str | None
    sec_company: SecCompany
    yahoo_quote: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CompanySnapshotBundle:
    """Generic company snapshot bundle for CLI/report output."""

    resolution: CompanyResolution
    market_snapshot: Mapping[str, Any]
    submissions: Mapping[str, Any]
    company_facts: Mapping[str, Any]


@dataclass(frozen=True)
class CompanyFactsBundle:
    """Resolved company identity plus SEC companyfacts for statement workflows."""

    resolution: CompanyResolution
    company_facts: Mapping[str, Any]


def fetch_company_snapshot(
    identifier: str,
    *,
    identifier_kind: str = "auto",
    sec_client: Optional[SecClient] = None,
    yahoo_client: Optional[YahooFinanceClient] = None,
) -> CompanySnapshotBundle:
    """Resolve a company identifier and fetch general market + SEC tables."""
    sec = sec_client or SecClient()
    yahoo = yahoo_client or YahooFinanceClient()
    resolution = resolve_company_identifier(
        identifier,
        identifier_kind=identifier_kind,
        sec_client=sec,
        yahoo_client=yahoo,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        company_bundle_future = executor.submit(
            sec.fetch_company_bundle,
            resolution.ticker,
            include_company_facts=True,
        )
        market_snapshot_future = executor.submit(
            yahoo.fetch_price_snapshot,
            resolution.ticker,
        )

        company_bundle = company_bundle_future.result()
        market_snapshot = market_snapshot_future.result()
    return CompanySnapshotBundle(
        resolution=resolution,
        market_snapshot=market_snapshot,
        submissions=company_bundle["submissions"],
        company_facts=company_bundle["company_facts"],
    )


def fetch_company_facts(
    identifier: str,
    *,
    identifier_kind: str = "auto",
    sec_client: Optional[SecClient] = None,
    yahoo_client: Optional[YahooFinanceClient] = None,
) -> CompanyFactsBundle:
    """Resolve a company identifier and fetch only SEC companyfacts."""
    sec = sec_client or SecClient()
    yahoo = yahoo_client or YahooFinanceClient()
    resolution = resolve_company_identifier(
        identifier,
        identifier_kind=identifier_kind,
        sec_client=sec,
        yahoo_client=yahoo,
    )
    return CompanyFactsBundle(
        resolution=resolution,
        company_facts=sec.fetch_company_facts(resolution.sec_company.cik),
    )


def resolve_company_identifier(
    identifier: str,
    *,
    identifier_kind: str = "auto",
    sec_client: Optional[SecClient] = None,
    yahoo_client: Optional[YahooFinanceClient] = None,
) -> CompanyResolution:
    """Resolve ticker, CIK, CUSIP, or ISIN into one quoted company."""
    sec = sec_client or SecClient()
    yahoo = yahoo_client or YahooFinanceClient()
    query = identifier.strip()
    kind = _normalize_identifier_kind(query, identifier_kind)

    if kind == "ticker":
        sec_company = sec.lookup_company(query)
        return _build_resolution(
            input_value=identifier,
            identifier_kind=kind,
            query_used=query,
            sec_company=sec_company,
            yahoo_quote=None,
        )

    if kind == "cik":
        sec_company = sec.lookup_company_by_cik(query)
        return _build_resolution(
            input_value=identifier,
            identifier_kind=kind,
            query_used=query,
            sec_company=sec_company,
            yahoo_quote=None,
        )

    if kind in {"isin", "cusip"}:
        yahoo_quote = _select_equity_quote(yahoo.search_quotes(query, max_results=10))
        if yahoo_quote is None:
            raise LookupError(f"No equity match found for {kind}: {identifier}")
        sec_company = sec.lookup_company(yahoo_quote.symbol)
        return _build_resolution(
            input_value=identifier,
            identifier_kind=kind,
            query_used=query,
            sec_company=sec_company,
            yahoo_quote=yahoo_quote.as_dict(),
        )

    try:
        sec_company = sec.lookup_company(query)
        return _build_resolution(
            input_value=identifier,
            identifier_kind="ticker",
            query_used=query,
            sec_company=sec_company,
            yahoo_quote=None,
        )
    except LookupError:
        yahoo_quote = _select_equity_quote(yahoo.search_quotes(query, max_results=10))
        if yahoo_quote is None:
            raise LookupError(f"Could not resolve identifier: {identifier}")
        sec_company = sec.lookup_company(yahoo_quote.symbol)
        return _build_resolution(
            input_value=identifier,
            identifier_kind=_normalize_identifier_kind(query, "auto"),
            query_used=query,
            sec_company=sec_company,
            yahoo_quote=yahoo_quote.as_dict(),
        )


def _build_resolution(
    *,
    input_value: str,
    identifier_kind: str,
    query_used: str,
    sec_company: SecCompany,
    yahoo_quote: Mapping[str, Any] | None,
) -> CompanyResolution:
    exchange = sec_company.exchange or (str(yahoo_quote.get("exchange")) if yahoo_quote else None)
    return CompanyResolution(
        input_value=input_value,
        identifier_kind=identifier_kind,
        query_used=query_used,
        ticker=sec_company.ticker,
        exchange=exchange,
        security_id=build_security_id(ticker=sec_company.ticker, exchange=exchange),
        sec_company=sec_company,
        yahoo_quote=yahoo_quote,
    )


def _select_equity_quote(quotes: list[YahooSearchQuote]) -> YahooSearchQuote | None:
    for quote in quotes:
        if quote.quote_type == "EQUITY":
            return quote
    return None


def _normalize_identifier_kind(
    identifier: str,
    requested_kind: str,
) -> str:
    requested = requested_kind.lower()
    if requested != "auto":
        return requested
    upper = identifier.strip().upper()
    if _looks_like_isin(upper):
        return "isin"
    if _looks_like_cusip(upper):
        return "cusip"
    if upper.isdigit():
        return "cik"
    return "ticker"


def _looks_like_isin(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value))


def _looks_like_cusip(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{9}", value))
