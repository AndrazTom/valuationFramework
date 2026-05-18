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
    company_name: str | None = None
    country: str | None = None
    currency: str | None = None
    sec_company: SecCompany | None = None
    yahoo_quote: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CompanySnapshotBundle:
    """Generic company snapshot bundle for CLI/report output."""

    resolution: CompanyResolution
    market_snapshot: Mapping[str, Any]
    submissions: Mapping[str, Any] | None
    company_facts: Mapping[str, Any] | None
    company_profile: Mapping[str, Any] | None


@dataclass(frozen=True)
class CompanyFactsBundle:
    """Resolved company identity plus SEC companyfacts for statement workflows."""

    resolution: CompanyResolution
    company_facts: Mapping[str, Any] | None
    statement_source: str = "sec"


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
    with ThreadPoolExecutor(max_workers=3) as executor:
        market_snapshot_future = executor.submit(
            yahoo.fetch_price_snapshot,
            resolution.ticker,
        )
        company_profile_future = executor.submit(
            yahoo.fetch_company_profile,
            resolution.ticker,
        )
        if resolution.sec_company is not None:
            company_bundle_future = executor.submit(
                sec.fetch_company_bundle,
                resolution.ticker,
                include_company_facts=True,
            )
        else:
            company_bundle_future = None

        market_snapshot = market_snapshot_future.result()
        try:
            company_profile = company_profile_future.result()
        except Exception:
            company_profile = None
        if not _is_viable_yahoo_profile(company_profile):
            company_profile = None
        if company_bundle_future is not None:
            try:
                company_bundle = company_bundle_future.result()
                submissions = company_bundle["submissions"]
                company_facts = company_bundle.get("company_facts")
            except Exception:
                submissions = None
                company_facts = None
        else:
            submissions = None
            company_facts = None
    return CompanySnapshotBundle(
        resolution=resolution,
        market_snapshot=market_snapshot,
        submissions=submissions,
        company_facts=company_facts,
        company_profile=company_profile,
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
    if resolution.sec_company is None:
        return CompanyFactsBundle(
            resolution=resolution,
            company_facts=None,
            statement_source="yahoo",
        )
    return CompanyFactsBundle(
        resolution=resolution,
        company_facts=sec.fetch_company_facts(resolution.sec_company.cik),
        statement_source="sec",
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
        if _looks_like_exchange_ticker(query):
            yahoo_quote = _select_matching_equity_quote(
                yahoo.search_quotes(query, max_results=10),
                query=query,
            )
            if yahoo_quote is not None:
                company_profile = yahoo.fetch_company_profile(yahoo_quote.symbol)
                return _build_resolution(
                    input_value=identifier,
                    identifier_kind=kind,
                    query_used=query,
                    sec_company=None,
                    yahoo_quote=yahoo_quote.as_dict(),
                    company_profile=company_profile,
                )
            company_profile = yahoo.fetch_company_profile(query)
            if not _is_viable_yahoo_profile(company_profile):
                raise LookupError(f"Could not resolve identifier: {identifier}")
            return _build_resolution(
                input_value=identifier,
                identifier_kind=kind,
                query_used=query,
                sec_company=None,
                yahoo_quote=None,
                company_profile=company_profile,
            )
        try:
            sec_company = sec.lookup_company(query)
            return _build_resolution(
                input_value=identifier,
                identifier_kind=kind,
                query_used=query,
                sec_company=sec_company,
                yahoo_quote=None,
                company_profile=None,
            )
        except LookupError:
            yahoo_quote = _select_matching_equity_quote(
                yahoo.search_quotes(query, max_results=10),
                query=query,
            )
            if yahoo_quote is not None:
                company_profile = yahoo.fetch_company_profile(yahoo_quote.symbol)
                sec_company = None
                normalized_symbol = yahoo_quote.symbol.upper()
                if "." not in normalized_symbol:
                    try:
                        sec_company = sec.lookup_company(normalized_symbol)
                    except LookupError:
                        sec_company = None
                return _build_resolution(
                    input_value=identifier,
                    identifier_kind=kind,
                    query_used=query,
                    sec_company=sec_company,
                    yahoo_quote=yahoo_quote.as_dict(),
                    company_profile=company_profile,
                )
            company_profile = yahoo.fetch_company_profile(query)
            if not _is_viable_yahoo_profile(company_profile):
                raise
            return _build_resolution(
                input_value=identifier,
                identifier_kind=kind,
                query_used=query,
                sec_company=None,
                yahoo_quote=None,
                company_profile=company_profile,
            )

    if kind == "cik":
        sec_company = sec.lookup_company_by_cik(query)
        return _build_resolution(
            input_value=identifier,
            identifier_kind=kind,
            query_used=query,
            sec_company=sec_company,
            yahoo_quote=None,
            company_profile=None,
        )

    if kind in {"isin", "cusip"}:
        yahoo_quote = _select_equity_quote(yahoo.search_quotes(query, max_results=10))
        if yahoo_quote is None:
            raise LookupError(f"No equity match found for {kind}: {identifier}")
        company_profile = yahoo.fetch_company_profile(yahoo_quote.symbol)
        sec_company = None
        normalized_symbol = yahoo_quote.symbol.upper()
        if "." not in normalized_symbol:
            try:
                sec_company = sec.lookup_company(normalized_symbol)
            except LookupError:
                sec_company = None
        return _build_resolution(
            input_value=identifier,
            identifier_kind=kind,
            query_used=query,
            sec_company=sec_company,
            yahoo_quote=yahoo_quote.as_dict(),
            company_profile=company_profile,
        )

    try:
        sec_company = sec.lookup_company(query)
        return _build_resolution(
            input_value=identifier,
            identifier_kind="ticker",
            query_used=query,
            sec_company=sec_company,
            yahoo_quote=None,
            company_profile=None,
        )
    except LookupError:
        yahoo_quote = _select_matching_equity_quote(
            yahoo.search_quotes(query, max_results=10),
            query=query,
        )
        if yahoo_quote is None:
            company_profile = yahoo.fetch_company_profile(query)
            if not _is_viable_yahoo_profile(company_profile):
                raise LookupError(f"Could not resolve identifier: {identifier}")
            return _build_resolution(
                input_value=identifier,
                identifier_kind=_normalize_identifier_kind(query, "auto"),
                query_used=query,
                sec_company=None,
                yahoo_quote=None,
                company_profile=company_profile,
            )
        company_profile = yahoo.fetch_company_profile(yahoo_quote.symbol)
        try:
            sec_company = sec.lookup_company(yahoo_quote.symbol)
        except LookupError:
            sec_company = None
        return _build_resolution(
            input_value=identifier,
            identifier_kind=_normalize_identifier_kind(query, "auto"),
            query_used=query,
            sec_company=sec_company,
            yahoo_quote=yahoo_quote.as_dict(),
            company_profile=company_profile,
        )


def _build_resolution(
    *,
    input_value: str,
    identifier_kind: str,
    query_used: str,
    sec_company: SecCompany | None,
    yahoo_quote: Mapping[str, Any] | None,
    company_profile: Mapping[str, Any] | None,
) -> CompanyResolution:
    if sec_company is not None:
        ticker = sec_company.ticker
        exchange = sec_company.exchange or (str(yahoo_quote.get("exchange")) if yahoo_quote else None)
        company_name = sec_company.name
        country = str(company_profile.get("country")) if company_profile else None
        currency = str(company_profile.get("currency")) if company_profile and company_profile.get("currency") else None
        cik = sec_company.cik
    else:
        ticker = str(company_profile.get("ticker") or query_used).upper()
        exchange = (
            str(company_profile.get("exchange_display") or company_profile.get("exchange"))
            if company_profile
            else None
        )
        company_name = str(company_profile.get("name")) if company_profile else None
        country = str(company_profile.get("country")) if company_profile else None
        currency = str(company_profile.get("currency")) if company_profile and company_profile.get("currency") else None
        cik = None
    return CompanyResolution(
        input_value=input_value,
        identifier_kind=identifier_kind,
        query_used=query_used,
        ticker=ticker,
        exchange=exchange,
        security_id=build_security_id(ticker=ticker, exchange=exchange, cik=cik),
        company_name=company_name,
        country=country,
        currency=currency,
        sec_company=sec_company,
        yahoo_quote=yahoo_quote,
    )


def _select_equity_quote(quotes: list[YahooSearchQuote]) -> YahooSearchQuote | None:
    for quote in quotes:
        if quote.quote_type == "EQUITY":
            return quote
    return None


def _select_matching_equity_quote(quotes: list[YahooSearchQuote], *, query: str) -> YahooSearchQuote | None:
    upper_query = query.strip().upper()
    exact_matches = [
        quote
        for quote in quotes
        if quote.quote_type == "EQUITY" and quote.symbol.upper() == upper_query
    ]
    if exact_matches:
        return exact_matches[0]
    return _select_equity_quote(quotes)


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


def _looks_like_exchange_ticker(value: str) -> bool:
    return "." in value.strip().upper()


def _is_viable_yahoo_profile(profile: Mapping[str, Any] | None) -> bool:
    if not profile:
        return False
    return bool(
        profile.get("ticker")
        and (
            profile.get("name")
            and profile.get("exchange")
        )
    )
