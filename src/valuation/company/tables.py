"""Generic company tables."""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from valuation.company.statements import build_statement_table
from valuation.company.yahoo_statements import build_yahoo_key_financials_table
from valuation.company.yahoo_statements import build_yahoo_statement_table
from valuation.company.service import CompanyResolution
from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_table

OVERVIEW_MARKET_METRICS = (
    ("last_price", "currency"),
    ("market_cap", "currency"),
    ("shares", "shares"),
)

OVERVIEW_FINANCIAL_METRICS = (
    "revenue",
    "net_income",
    "operating_cash_flow",
    "cash_and_equivalents",
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
)

COMMON_FACT_DEFINITIONS = (
    CompanyFactQuery(
        "cash_and_equivalents",
        (
            ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
            ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
        ),
    ),
    CompanyFactQuery("total_assets", (("us-gaap", "Assets"),)),
    CompanyFactQuery("total_liabilities", (("us-gaap", "Liabilities"),)),
    CompanyFactQuery("stockholders_equity", (("us-gaap", "StockholdersEquity"),)),
    CompanyFactQuery(
        "revenue",
        (
            ("us-gaap", "Revenues"),
            ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ),
    ),
    CompanyFactQuery("net_income", (("us-gaap", "NetIncomeLoss"),)),
    CompanyFactQuery(
        "operating_cash_flow",
        (("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),),
    ),
    CompanyFactQuery(
        "capex",
        (("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),),
    ),
)

STATEMENT_AVAILABILITY_REQUESTS = (
    ("income", "annual"),
    ("income", "quarterly"),
    ("balance", "annual"),
    ("balance", "quarterly"),
    ("cashflow", "annual"),
    ("cashflow", "quarterly"),
)


def resolution_to_table(resolution: CompanyResolution) -> pd.DataFrame:
    """Return the identifier-resolution step as a table."""
    return pd.DataFrame(
        [
            {"field": "input", "value": resolution.input_value},
            {"field": "identifier_kind", "value": resolution.identifier_kind},
            {"field": "query_used", "value": resolution.query_used},
            {"field": "security_id", "value": resolution.security_id},
            {"field": "ticker", "value": resolution.ticker},
            {"field": "exchange", "value": resolution.exchange},
        ]
    )


def company_summary_to_table(
    resolution: CompanyResolution,
    *,
    company_profile: dict | None = None,
) -> pd.DataFrame:
    """Return a generic company identity table for SEC-backed or Yahoo-backed issuers."""
    profile = company_profile or {}
    resolution_country = getattr(resolution, "country", None)
    resolution_currency = getattr(resolution, "currency", None)
    if resolution.sec_company is not None:
        rows = [
            {"field": "ticker", "value": resolution.sec_company.ticker},
            {"field": "cik", "value": resolution.sec_company.cik},
            {"field": "name", "value": resolution.sec_company.name},
            {"field": "exchange", "value": resolution.sec_company.exchange},
            {"field": "country", "value": profile.get("country") or resolution_country},
            {"field": "currency", "value": profile.get("currency") or resolution_currency},
            {"field": "sector", "value": profile.get("sector")},
            {"field": "industry", "value": profile.get("industry")},
            {"field": "website", "value": profile.get("website")},
        ]
    else:
        rows = [
            {"field": "ticker", "value": resolution.ticker},
            {"field": "name", "value": resolution.company_name},
            {"field": "exchange", "value": resolution.exchange},
            {"field": "country", "value": resolution_country},
            {"field": "currency", "value": profile.get("currency") or resolution_currency},
            {"field": "sector", "value": profile.get("sector")},
            {"field": "industry", "value": profile.get("industry")},
            {"field": "website", "value": profile.get("website")},
        ]
    filtered = [row for row in rows if row["value"] is not None]
    return pd.DataFrame(filtered)


def build_key_financials_table(company_facts: dict) -> pd.DataFrame:
    """Return selected generic SEC facts for one company."""
    return company_facts_to_table(company_facts, COMMON_FACT_DEFINITIONS)


def build_sec_overview_table(
    *,
    market_snapshot: Mapping[str, object],
    company_facts: Mapping[str, object],
    currency: str = "USD",
) -> pd.DataFrame:
    """Return a compact machine-friendly overview from market snapshot + SEC facts."""
    rows = _market_overview_rows(market_snapshot, currency=currency, source="yfinance")
    facts_table = company_facts_to_table(company_facts, COMMON_FACT_DEFINITIONS)
    fact_rows = {
        str(row["metric"]): row
        for row in facts_table.to_dict(orient="records")
    }
    for metric in OVERVIEW_FINANCIAL_METRICS:
        fact_row = fact_rows.get(metric)
        if fact_row and _has_value(fact_row.get("value")):
            rows.append(
                {
                    "metric": metric,
                    "value": fact_row.get("value"),
                    "unit": fact_row.get("unit"),
                    "source": "sec",
                    "as_of": fact_row.get("end"),
                    "status": "available",
                    "reason": None,
                }
            )
            continue
        rows.append(
            {
                "metric": metric,
                "value": None,
                "unit": _overview_default_unit(metric, currency=currency),
                "source": "sec",
                "as_of": None,
                "status": "unavailable",
                "reason": "No matching concepts found in SEC companyfacts",
            }
        )
    return pd.DataFrame(rows)


def build_yahoo_snapshot_key_financials_table(
    *,
    income_frame: pd.DataFrame,
    balance_frame: pd.DataFrame,
    cashflow_frame: pd.DataFrame,
    currency: str = "USD",
) -> pd.DataFrame:
    """Return selected generic financials from Yahoo annual statement frames."""
    return build_yahoo_key_financials_table(
        income_frame=income_frame,
        balance_frame=balance_frame,
        cashflow_frame=cashflow_frame,
        currency=currency,
    )


def build_yahoo_overview_table(
    *,
    market_snapshot: Mapping[str, object],
    income_frame: pd.DataFrame,
    balance_frame: pd.DataFrame,
    cashflow_frame: pd.DataFrame,
    currency: str = "USD",
) -> pd.DataFrame:
    """Return a compact machine-friendly overview from market snapshot + Yahoo annual statements."""
    rows = _market_overview_rows(market_snapshot, currency=currency, source="yfinance")
    financials_table = build_yahoo_key_financials_table(
        income_frame=income_frame,
        balance_frame=balance_frame,
        cashflow_frame=cashflow_frame,
        currency=currency,
    )
    financial_rows = {
        str(row["metric"]): row
        for row in financials_table.to_dict(orient="records")
    }
    for metric in OVERVIEW_FINANCIAL_METRICS:
        financial_row = financial_rows.get(metric)
        if financial_row and _has_value(financial_row.get("value")):
            rows.append(
                {
                    "metric": metric,
                    "value": financial_row.get("value"),
                    "unit": financial_row.get("unit"),
                    "source": "yahoo",
                    "as_of": financial_row.get("end"),
                    "status": "available",
                    "reason": None,
                }
            )
            continue
        rows.append(
            {
                "metric": metric,
                "value": None,
                "unit": _overview_default_unit(metric, currency=currency),
                "source": "yahoo",
                "as_of": None,
                "status": "unavailable",
                "reason": "Metric unavailable in Yahoo annual statements",
            }
        )
    return pd.DataFrame(rows)


def build_sec_statement_availability_table(company_facts: dict) -> pd.DataFrame:
    """Summarize generic statement availability from SEC companyfacts."""
    rows = []
    for statement, period in STATEMENT_AVAILABILITY_REQUESTS:
        table = build_statement_table(
            company_facts,
            statement=statement,
            period=period,
            limit=99,
        )
        rows.append(
            _statement_availability_row(
                statement=statement,
                period=period,
                source="sec",
                table=table,
                empty_reason="No matching concepts found in SEC companyfacts",
            )
        )
    return pd.DataFrame(rows)


def build_yahoo_statement_availability_table(
    frames: dict[tuple[str, str], pd.DataFrame],
    *,
    currency: str = "USD",
) -> pd.DataFrame:
    """Summarize generic statement availability from Yahoo statement frames."""
    rows = []
    for statement, period in STATEMENT_AVAILABILITY_REQUESTS:
        frame = frames.get((statement, period), pd.DataFrame())
        table = build_yahoo_statement_table(
            frame,
            statement=statement,
            period=period,
            currency=currency,
            limit=99,
        )
        empty_reason = (
            "Yahoo returned no statement frame"
            if frame is None or frame.empty
            else "Statement frame present but no mapped metrics"
        )
        rows.append(
            _statement_availability_row(
                statement=statement,
                period=period,
                source="yahoo",
                table=table,
                empty_reason=empty_reason,
            )
        )
    return pd.DataFrame(rows)


def _statement_availability_row(
    *,
    statement: str,
    period: str,
    source: str,
    table: pd.DataFrame,
    empty_reason: str,
) -> dict[str, object]:
    period_columns = [column for column in table.columns if column not in {"metric", "unit"}]
    if period_columns and not table.empty:
        return {
            "statement": statement,
            "period": period,
            "source": source,
            "status": "available",
            "period_count": len(period_columns),
            "metric_count": int(len(table)),
            "latest_period": period_columns[0],
            "reason": None,
        }
    return {
        "statement": statement,
        "period": period,
        "source": source,
        "status": "unavailable",
        "period_count": 0,
        "metric_count": 0,
        "latest_period": None,
        "reason": empty_reason,
    }


def _market_overview_rows(
    market_snapshot: Mapping[str, object],
    *,
    currency: str,
    source: str,
) -> list[dict[str, object]]:
    rows = []
    as_of = market_snapshot.get("latest_price_date")
    for metric, unit_kind in OVERVIEW_MARKET_METRICS:
        value = market_snapshot.get(metric)
        rows.append(
            {
                "metric": metric,
                "value": value,
                "unit": currency if unit_kind == "currency" else "shares",
                "source": source,
                "as_of": as_of,
                "status": "available" if _has_value(value) else "unavailable",
                "reason": None if _has_value(value) else "Unavailable in market snapshot",
            }
        )
    return rows


def _overview_default_unit(metric: str, *, currency: str) -> str:
    if metric == "shares":
        return "shares"
    return currency


def _has_value(value: object) -> bool:
    return value is not None and not pd.isna(value)
