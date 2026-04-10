"""Generic company tables."""

from __future__ import annotations

import pandas as pd

from valuation.company.statements import build_statement_table
from valuation.company.yahoo_statements import build_yahoo_key_financials_table
from valuation.company.yahoo_statements import build_yahoo_statement_table
from valuation.company.service import CompanyResolution
from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_table

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
                empty_reason="no_companyfacts_rows",
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
            "provider_returned_no_data"
            if frame is None or frame.empty
            else "no_supported_rows"
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
