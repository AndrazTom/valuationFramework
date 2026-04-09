"""Berkshire-only table shaping."""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from valuation.brk.service import BRK_A_TICKER, BRK_A_TO_B_CONVERSION, BRK_B_TICKER
from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_table
from valuation.brk.holdings import aggregate_13f_holdings

BRK_FACT_DEFINITIONS: Sequence[CompanyFactQuery] = (
    CompanyFactQuery(
        "cash_and_equivalents",
        (
            ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
            ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
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

CORE_BRK_FORMS = ("10-K", "10-Q", "8-K", "DEF 14A", "13F-HR", "13F-HR/A")


def build_share_class_table(market_snapshot: dict) -> pd.DataFrame:
    """Express Berkshire share classes in BRK.B-equivalent terms."""
    brk_b_price = market_snapshot.get("last_price")
    brk_a_implied = None
    if isinstance(brk_b_price, (int, float)):
        brk_a_implied = float(brk_b_price) * BRK_A_TO_B_CONVERSION

    return pd.DataFrame(
        [
            {"field": "primary_valuation_unit", "value": BRK_B_TICKER},
            {"field": "reference_share_class", "value": BRK_A_TICKER},
            {"field": "brk_a_to_brk_b_conversion", "value": BRK_A_TO_B_CONVERSION},
            {"field": "brk_b_last_price", "value": brk_b_price},
            {"field": "implied_brk_a_price", "value": brk_a_implied},
        ]
    )


def build_key_facts_table(company_facts: dict) -> pd.DataFrame:
    """Return the latest selected Berkshire-relevant SEC facts."""
    return company_facts_to_table(company_facts, BRK_FACT_DEFINITIONS)


def filter_core_filings_table(frame: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    """Keep the filing types that matter most for Berkshire valuation work."""
    if frame.empty:
        return frame
    filtered = frame[frame["form"].isin(CORE_BRK_FORMS)]
    return filtered.head(limit).reset_index(drop=True)


def build_13f_summary_table(
    filing_date: str,
    accession_number: str,
    information_table_filename: str,
    holdings: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize the latest Berkshire 13F at a glance."""
    total_value = None
    if not holdings.empty and "value_usd" in holdings:
        total_value = holdings["value_usd"].dropna().sum()

    return pd.DataFrame(
        [
            {"field": "filing_date", "value": filing_date},
            {"field": "accession_number", "value": accession_number},
            {"field": "information_table_filename", "value": information_table_filename},
            {"field": "holding_count", "value": len(holdings)},
            {"field": "reported_value_usd", "value": total_value},
        ]
    )


def build_top_holdings_table(holdings: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Return the largest Berkshire 13F positions."""
    if holdings.empty:
        return holdings
    limit = max(0, limit)
    aggregated = aggregate_13f_holdings(holdings)
    total_value = aggregated["value_usd"].dropna().sum()
    trimmed = aggregated[
        [
            "issuer",
            "class_title",
            "cusip",
            "value_usd",
            "shares_or_principal",
        ]
    ].copy()
    trimmed["portfolio_weight"] = trimmed["value_usd"].apply(
        lambda value: (value / total_value) if total_value else None
    )
    return trimmed.head(limit).reset_index(drop=True)
