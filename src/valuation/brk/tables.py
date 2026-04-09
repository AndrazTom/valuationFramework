"""Berkshire-only table shaping."""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from valuation.brk.service import BRK_A_TICKER, BRK_A_TO_B_CONVERSION, BRK_B_TICKER
from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_table
from valuation.brk.holdings import aggregate_13f_holdings
from valuation.securities.pricing import enrich_holdings_with_market_prices

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

BRK_LIQUIDITY_FACT_DEFINITIONS: Sequence[CompanyFactQuery] = (
    CompanyFactQuery(
        "cash_and_equivalents",
        (
            ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
            ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ),
    ),
    CompanyFactQuery(
        "cash_equivalents_component",
        (("us-gaap", "CashEquivalentsAtCarryingValue"),),
    ),
    CompanyFactQuery(
        "available_for_sale_debt_amortized_cost",
        (("us-gaap", "AvailableForSaleDebtSecuritiesAmortizedCostBasis"),),
    ),
    CompanyFactQuery(
        "available_for_sale_debt_fair_value",
        (
            ("us-gaap", "AvailableForSaleSecuritiesDebtSecurities"),
            ("us-gaap", "AvailableForSaleDebtSecurities"),
        ),
    ),
    CompanyFactQuery(
        "debt_maturing_within_1y",
        (("us-gaap", "AvailableForSaleSecuritiesDebtMaturitiesNextRollingTwelveMonthsFairValue"),),
    ),
    CompanyFactQuery(
        "debt_maturing_2_to_5y",
        (("us-gaap", "AvailableForSaleSecuritiesDebtMaturitiesRollingYearTwoThroughFiveFairValue"),),
    ),
    CompanyFactQuery(
        "debt_maturing_6_to_10y",
        (("us-gaap", "AvailableForSaleSecuritiesDebtMaturitiesRollingYearSixThroughTenFairValue"),),
    ),
    CompanyFactQuery(
        "debt_maturing_after_10y",
        (("us-gaap", "AvailableForSaleSecuritiesDebtMaturitiesRollingAfterYearTenFairValue"),),
    ),
    CompanyFactQuery(
        "debt_without_single_maturity",
        (("us-gaap", "AvailableForSaleSecuritiesDebtMaturitiesWithoutSingleMaturityDateFairValue"),),
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


def build_liquidity_bridge_table(company_facts: dict) -> pd.DataFrame:
    """Return the raw SEC fact bridge used for Berkshire liquidity estimates."""
    return company_facts_to_table(company_facts, BRK_LIQUIDITY_FACT_DEFINITIONS)


def build_liquidity_summary_table(bridge: pd.DataFrame) -> pd.DataFrame:
    """Summarize Berkshire liquidity buckets from the bridge facts."""
    if bridge.empty:
        return pd.DataFrame(columns=["field", "value"])

    values = {
        row["metric"]: row["value"]
        for _, row in bridge.iterrows()
        if pd.notna(row["value"])
    }
    debt_current = values.get("debt_maturing_within_1y")
    debt_noncurrent = _sum_defined(
        values.get("debt_maturing_2_to_5y"),
        values.get("debt_maturing_6_to_10y"),
        values.get("debt_maturing_after_10y"),
        values.get("debt_without_single_maturity"),
    )
    all_debt_securities = values.get("available_for_sale_debt_fair_value")
    liquidity_total = _sum_defined(
        values.get("cash_and_equivalents"),
        all_debt_securities,
    )

    return pd.DataFrame(
        [
            {"field": "cash_and_equivalents", "value": values.get("cash_and_equivalents")},
            {"field": "cash_equivalents_component", "value": values.get("cash_equivalents_component")},
            {"field": "debt_securities_total", "value": all_debt_securities},
            {"field": "debt_securities_current", "value": debt_current},
            {"field": "debt_securities_noncurrent", "value": debt_noncurrent},
            {"field": "liquidity_total_estimate", "value": liquidity_total},
        ]
    )


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
    holding_count = len(holdings)
    if not holdings.empty and {"issuer", "class_title", "cusip"}.issubset(holdings.columns):
        holding_count = len(aggregate_13f_holdings(holdings))

    total_value = None
    if not holdings.empty and "value_usd" in holdings:
        total_value = holdings["value_usd"].dropna().sum()

    return pd.DataFrame(
        [
            {"field": "filing_date", "value": filing_date},
            {"field": "accession_number", "value": accession_number},
            {"field": "information_table_filename", "value": information_table_filename},
            {"field": "holding_count", "value": holding_count},
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


def build_top_holdings_live_table(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    limit: int = 20,
    yahoo_client=None,
) -> pd.DataFrame:
    """Return Berkshire top holdings with current market-price enrichment."""
    if holdings.empty:
        return holdings
    limit = max(0, limit)
    aggregated = aggregate_13f_holdings(holdings)
    enriched = enrich_holdings_with_market_prices(
        aggregated,
        reference,
        yahoo_client=yahoo_client,
    )
    total_live_value = enriched["market_value_live_usd"].dropna().sum()
    trimmed = enriched[
        [
            "issuer",
            "ticker",
            "cusip",
            "value_usd",
            "last_price",
            "market_value_live_usd",
            "shares_or_principal",
            "latest_price_date",
        ]
    ].copy()
    trimmed["portfolio_weight_live"] = trimmed["market_value_live_usd"].apply(
        lambda value: (value / total_live_value) if total_live_value else None
    )
    trimmed = trimmed.rename(columns={"value_usd": "reported_value_usd"})
    return trimmed.head(limit).reset_index(drop=True)


def build_13f_live_price_summary_table(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    yahoo_client=None,
) -> pd.DataFrame:
    """Summarize live-price coverage for Berkshire's latest 13F positions."""
    if holdings.empty:
        return pd.DataFrame(columns=["field", "value"])

    aggregated = aggregate_13f_holdings(holdings)
    enriched = enrich_holdings_with_market_prices(
        aggregated,
        reference,
        yahoo_client=yahoo_client,
    )
    resolved = enriched["market_value_live_usd"].notna()
    resolved_count = int(resolved.sum())
    unresolved_count = int((~resolved).sum())
    reported_value = enriched["value_usd"].dropna().sum()
    reported_value_resolved = enriched.loc[resolved, "value_usd"].dropna().sum()
    live_value = enriched["market_value_live_usd"].dropna().sum()
    latest_price_date = None
    if "latest_price_date" in enriched.columns:
        dates = [value for value in enriched["latest_price_date"].dropna().tolist() if value]
        if dates:
            latest_price_date = max(dates)

    return pd.DataFrame(
        [
            {"field": "positions_total", "value": len(enriched)},
            {"field": "positions_with_live_price", "value": resolved_count},
            {"field": "positions_without_live_price", "value": unresolved_count},
            {"field": "reported_value_usd", "value": reported_value},
            {"field": "reported_value_resolved_usd", "value": reported_value_resolved},
            {"field": "market_value_live_resolved_usd", "value": live_value},
            {"field": "latest_price_date", "value": latest_price_date},
        ]
    )


def _sum_defined(*values):
    defined = [value for value in values if value is not None and pd.notna(value)]
    if not defined:
        return None
    return sum(defined)
