"""Generic company tables."""

from __future__ import annotations

import pandas as pd

from valuation.company.yahoo_statements import build_yahoo_key_financials_table
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
    if resolution.sec_company is not None:
        return pd.DataFrame(
            [
                {"field": "ticker", "value": resolution.sec_company.ticker},
                {"field": "cik", "value": resolution.sec_company.cik},
                {"field": "name", "value": resolution.sec_company.name},
                {"field": "exchange", "value": resolution.sec_company.exchange},
            ]
        )

    profile = company_profile or {}
    rows = [
        {"field": "ticker", "value": resolution.ticker},
        {"field": "name", "value": resolution.company_name},
        {"field": "exchange", "value": resolution.exchange},
        {"field": "country", "value": resolution.country},
        {"field": "currency", "value": profile.get("currency") or resolution.currency},
        {"field": "sector", "value": profile.get("sector")},
        {"field": "industry", "value": profile.get("industry")},
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
