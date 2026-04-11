"""Berkshire-only table shaping."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

import pandas as pd

from valuation.brk.service import BrkLiquidityFiling, BrkSegmentFiling, BrkValuationBundle
from valuation.brk.service import BRK_A_TICKER, BRK_A_TO_B_CONVERSION, BRK_B_TICKER
from valuation.brk.segments import build_top_level_operating_segments_table
from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_table
from valuation.brk.holdings import aggregate_13f_holdings
from valuation.notation import MILLION
from valuation.securities.pricing import enrich_holdings_with_market_prices, fetch_price_change_snapshot

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

BRK_LIQUIDITY_REPORT_LABELS = {
    "cash_and_equivalents": "Cash and cash equivalents",
    "short_term_us_treasury_bills": "Short-term investments in U.S. Treasury Bills",
    "fixed_maturity_securities": "Investments in fixed maturity securities",
    "payable_for_purchase_of_us_treasury_bills": "Payable for purchase of U.S. Treasury Bills",
}

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


def build_liquidity_bridge_table(filings: Sequence[BrkLiquidityFiling]) -> pd.DataFrame:
    """Return the Berkshire liquidity bridge from filing balance-sheet reports."""
    rows = []
    for filing in filings:
        period_end, values = _extract_liquidity_values(filing.balance_sheet)
        if period_end is None:
            continue
        for metric, value in values.items():
            rows.append(
                {
                    "filing_date": filing.filing_date,
                    "form": filing.form,
                    "period_end": period_end,
                    "accession_number": filing.accession_number,
                    "metric": metric,
                    "label": BRK_LIQUIDITY_REPORT_LABELS[metric],
                    "value_usd": value,
                }
            )
    return pd.DataFrame(rows)


def build_liquidity_summary_table(bridge: pd.DataFrame) -> pd.DataFrame:
    """Summarize Berkshire liquidity history from filing report rows."""
    if bridge.empty:
        return pd.DataFrame(
            columns=[
                "filing_date",
                "form",
                "period_end",
                "cash_and_equivalents_usd",
                "short_term_us_treasury_bills_usd",
                "core_liquidity_total_usd",
                "fixed_maturity_securities_usd",
                "liquid_investments_total_usd",
                "payable_for_purchase_of_us_treasury_bills_usd",
            ]
        )

    summary = (
        bridge.pivot_table(
            index=["filing_date", "form", "period_end", "accession_number"],
            columns="metric",
            values="value_usd",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(columns=None)
    )
    summary = summary.rename(
        columns={
            "cash_and_equivalents": "cash_and_equivalents_usd",
            "short_term_us_treasury_bills": "short_term_us_treasury_bills_usd",
            "fixed_maturity_securities": "fixed_maturity_securities_usd",
            "payable_for_purchase_of_us_treasury_bills": "payable_for_purchase_of_us_treasury_bills_usd",
        }
    )
    summary["core_liquidity_total_usd"] = summary.apply(
        lambda row: _sum_defined(
            row.get("cash_and_equivalents_usd"),
            row.get("short_term_us_treasury_bills_usd"),
        ),
        axis=1,
    )
    summary["liquid_investments_total_usd"] = summary.apply(
        lambda row: _sum_defined(
            row.get("core_liquidity_total_usd"),
            row.get("fixed_maturity_securities_usd"),
        ),
        axis=1,
    )
    preferred_order = [
        "filing_date",
        "form",
        "period_end",
        "accession_number",
        "cash_and_equivalents_usd",
        "short_term_us_treasury_bills_usd",
        "core_liquidity_total_usd",
        "fixed_maturity_securities_usd",
        "liquid_investments_total_usd",
        "payable_for_purchase_of_us_treasury_bills_usd",
    ]
    available_columns = [column for column in preferred_order if column in summary.columns]
    return summary[available_columns].sort_values(
        by=["filing_date", "period_end"],
        ascending=False,
    ).reset_index(drop=True)


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
    price_change_window: str | None = None,
    enriched_holdings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return Berkshire top holdings with current market-price enrichment."""
    if holdings.empty:
        return holdings
    limit = max(0, limit)
    enriched = _enriched_holdings_frame(
        holdings,
        reference,
        yahoo_client=yahoo_client,
        price_change_window=price_change_window,
        enriched_holdings=enriched_holdings,
    )
    total_live_value = enriched["market_value_live_usd"].dropna().sum()
    selected_columns = [
        "issuer",
        "ticker",
        "cusip",
        "value_usd",
        "last_price",
        "market_value_live_usd",
        "shares_or_principal",
        "latest_price_date",
    ]
    if price_change_window is not None:
        selected_columns.insert(5, "price_change_pct")
    trimmed = enriched[selected_columns].copy()
    trimmed["portfolio_weight_live"] = trimmed["market_value_live_usd"].apply(
        lambda value: (value / total_live_value) if total_live_value else None
    )
    trimmed = trimmed.rename(columns={"value_usd": "reported_value_usd"})
    return trimmed.head(limit).reset_index(drop=True)


def build_13f_live_price_summary_table(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    yahoo_client=None,
    price_change_window: str | None = None,
    enriched_holdings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarize live-price coverage for Berkshire's latest 13F positions."""
    if holdings.empty:
        return pd.DataFrame(columns=["field", "value"])

    enriched = _enriched_holdings_frame(
        holdings,
        reference,
        yahoo_client=yahoo_client,
        price_change_window=price_change_window,
        enriched_holdings=enriched_holdings,
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

    rows = [
        {"field": "positions_total", "value": len(enriched)},
        {"field": "positions_with_live_price", "value": resolved_count},
        {"field": "positions_without_live_price", "value": unresolved_count},
        {"field": "reported_value_usd", "value": reported_value},
        {"field": "reported_value_resolved_usd", "value": reported_value_resolved},
        {"field": "market_value_live_resolved_usd", "value": live_value},
        {"field": "latest_price_date", "value": latest_price_date},
    ]
    if price_change_window is not None:
        rows.append({"field": "price_change_window", "value": price_change_window})
    return pd.DataFrame(rows)


def build_holdings_vs_brk_price_change_table(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    price_change_window: str,
    limit: int | None = None,
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
    brk_snapshot: dict[str, object] | None = None,
) -> pd.DataFrame:
    """Compare Berkshire's own price change to a resolved public-holdings basket."""
    if holdings.empty:
        return pd.DataFrame(columns=["field", "value"])

    enriched = _enriched_holdings_frame(
        holdings,
        reference,
        yahoo_client=yahoo_client,
        price_change_window=price_change_window,
        enriched_holdings=enriched_holdings,
    )
    brk_snapshot = brk_snapshot or fetch_price_change_snapshot(
        BRK_B_TICKER,
        price_change_window=price_change_window,
        yahoo_client=yahoo_client,
    )

    resolved = enriched[
        enriched["price_change_pct"].notna() & enriched["value_usd"].notna()
    ].copy()
    resolved_reported_value = resolved["value_usd"].sum() if not resolved.empty else None
    resolved_live_value = resolved["market_value_live_usd"].dropna().sum() if not resolved.empty else None
    holdings_weighted_change = _weighted_price_change_from_frame(resolved)
    top_slice = resolved
    if limit is not None:
        top_slice = resolved.head(max(0, limit)).copy()
    top_slice_weighted_change = _weighted_price_change_from_frame(top_slice)
    top_slice_reported_value = top_slice["value_usd"].sum() if not top_slice.empty else None

    brk_change = brk_snapshot.get("price_change_pct")
    change_spread = None
    if brk_change is not None and holdings_weighted_change is not None:
        change_spread = holdings_weighted_change - brk_change
    top_slice_spread = None
    if brk_change is not None and top_slice_weighted_change is not None:
        top_slice_spread = top_slice_weighted_change - brk_change

    return pd.DataFrame(
        [
            {"field": "price_change_window", "value": price_change_window},
            {"field": "brk_b_price_change_pct", "value": brk_change},
            {"field": "resolved_holdings_weighted_change_pct", "value": holdings_weighted_change},
            {"field": "holdings_minus_brk_b_change_pct", "value": change_spread},
            {"field": "top_holdings_limit", "value": int(len(top_slice))},
            {"field": "top_holdings_reported_value_usd", "value": top_slice_reported_value},
            {"field": "top_holdings_weighted_change_pct", "value": top_slice_weighted_change},
            {"field": "top_holdings_minus_brk_b_change_pct", "value": top_slice_spread},
            {"field": "resolved_positions_count", "value": int(len(resolved))},
            {"field": "resolved_positions_reported_value_usd", "value": resolved_reported_value},
            {"field": "resolved_positions_live_value_usd", "value": resolved_live_value},
            {"field": "brk_b_last_price", "value": brk_snapshot.get("last_price")},
            {"field": "latest_price_date", "value": brk_snapshot.get("latest_price_date")},
        ]
    )


def build_latest_liquidity_snapshot_table(bridge: pd.DataFrame) -> pd.DataFrame:
    """Return the latest Berkshire liquidity row plus a net liquidity line."""
    summary = build_liquidity_summary_table(bridge)
    if summary.empty:
        return summary
    latest = summary.head(1).copy()
    latest["net_liquid_investments_usd"] = latest.apply(
        lambda row: _sum_defined(
            row.get("liquid_investments_total_usd"),
            -float(row["payable_for_purchase_of_us_treasury_bills_usd"])
            if row.get("payable_for_purchase_of_us_treasury_bills_usd") is not None
            and pd.notna(row.get("payable_for_purchase_of_us_treasury_bills_usd"))
            else None,
        ),
        axis=1,
    )
    ordered = [
        "filing_date",
        "form",
        "period_end",
        "accession_number",
        "cash_and_equivalents_usd",
        "short_term_us_treasury_bills_usd",
        "fixed_maturity_securities_usd",
        "liquid_investments_total_usd",
        "payable_for_purchase_of_us_treasury_bills_usd",
        "net_liquid_investments_usd",
    ]
    return latest[[column for column in ordered if column in latest.columns]].reset_index(drop=True)


def build_public_equity_portfolio_summary_table(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarize Berkshire's latest public-equity block for valuation work."""
    if holdings.empty:
        return pd.DataFrame(columns=["field", "value"])
    enriched = _enriched_holdings_frame(
        holdings,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
    )
    resolved = enriched["market_value_live_usd"].notna()
    reported_total = enriched["value_usd"].dropna().sum()
    live_resolved = enriched.loc[resolved, "market_value_live_usd"].dropna().sum()
    unresolved_reported = enriched.loc[~resolved, "value_usd"].dropna().sum()
    blended_value = _sum_defined(live_resolved, unresolved_reported)
    latest_price_date = None
    if "latest_price_date" in enriched.columns:
        dates = [value for value in enriched["latest_price_date"].dropna().tolist() if value]
        if dates:
            latest_price_date = max(dates)
    return pd.DataFrame(
        [
            {"field": "reported_13f_value_usd", "value": reported_total},
            {"field": "live_resolved_13f_value_usd", "value": live_resolved},
            {"field": "unresolved_13f_value_reported_usd", "value": unresolved_reported},
            {"field": "blended_13f_value_usd", "value": blended_value},
            {
                "field": "live_price_coverage_pct",
                "value": (live_resolved / reported_total) if reported_total else None,
            },
            {"field": "positions_total", "value": int(len(enriched))},
            {"field": "positions_live_priced", "value": int(resolved.sum())},
            {"field": "positions_unresolved", "value": int((~resolved).sum())},
            {"field": "latest_price_date", "value": latest_price_date},
        ]
    )


def build_market_anchor_table(market_snapshot: dict) -> pd.DataFrame:
    """Return the market anchor for Berkshire valuation work."""
    market_cap = _market_cap_from_snapshot(market_snapshot)
    return pd.DataFrame(
        [
            {"field": "primary_valuation_unit", "value": BRK_B_TICKER},
            {"field": "last_price", "value": market_snapshot.get("last_price")},
            {"field": "latest_price_date", "value": market_snapshot.get("latest_price_date")},
            {"field": "shares_outstanding", "value": market_snapshot.get("shares")},
            {"field": "market_cap_usd", "value": market_cap},
        ]
    )


def build_brk_valuation_assumptions_table(*, period: str) -> pd.DataFrame:
    """Return the assumptions used in the first Berkshire bridge."""
    return pd.DataFrame(
        [
            {"field": "valuation_unit", "value": BRK_B_TICKER},
            {"field": "selected_period_type", "value": period},
            {"field": "market_anchor", "value": "Yahoo market snapshot market cap"},
            {
                "field": "public_equities_basis",
                "value": "Latest 13F with live prices where resolved and reported values for unresolved positions",
            },
            {
                "field": "public_equities_scope",
                "value": "13F positions only; excludes non-13F public equities and controlled subsidiaries",
            },
            {
                "field": "liquidity_basis",
                "value": "Latest filing balance-sheet bridge including cash, Treasury Bills, and fixed maturity securities",
            },
            {
                "field": "residual_definition",
                "value": "Market cap less blended 13F public equities less net liquid investments",
            },
        ]
    )


def build_brk_component_bridge_table(
    market_snapshot: dict,
    public_equity_summary: pd.DataFrame,
    latest_liquidity_snapshot: pd.DataFrame,
) -> pd.DataFrame:
    """Return a first explicit Berkshire component bridge."""
    market_cap = _market_cap_from_snapshot(market_snapshot)
    shares = market_snapshot.get("shares")
    public_equities = _field_value(public_equity_summary, "blended_13f_value_usd")
    net_liquid = _frame_row_value(latest_liquidity_snapshot, "net_liquid_investments_usd")
    implied_other = None
    if market_cap is not None:
        implied_other = float(market_cap)
        for value in (public_equities, net_liquid):
            if value is not None and pd.notna(value):
                implied_other -= float(value)

    rows = [
        {
            "component": "market_cap",
            "value_usd": market_cap,
            "per_brk_b_share_usd": _per_share_value(market_cap, shares),
            "share_of_market_cap_pct": 1.0 if market_cap else None,
            "method": "Current Yahoo market cap anchor",
        },
        {
            "component": "public_equities_13f_blended",
            "value_usd": public_equities,
            "per_brk_b_share_usd": _per_share_value(public_equities, shares),
            "share_of_market_cap_pct": (public_equities / market_cap) if market_cap and public_equities is not None else None,
            "method": "Latest 13F using live prices where resolved and reported values otherwise",
        },
        {
            "component": "net_liquid_investments",
            "value_usd": net_liquid,
            "per_brk_b_share_usd": _per_share_value(net_liquid, shares),
            "share_of_market_cap_pct": (net_liquid / market_cap) if market_cap and net_liquid is not None else None,
            "method": "Latest filing liquid investments net of Treasury Bill purchase payable",
        },
        {
            "component": "implied_operating_businesses_and_non_13f_assets",
            "value_usd": implied_other,
            "per_brk_b_share_usd": _per_share_value(implied_other, shares),
            "share_of_market_cap_pct": (implied_other / market_cap) if market_cap and implied_other is not None else None,
            "method": "Residual after subtracting blended 13F public equities and net liquid investments",
        },
    ]
    return pd.DataFrame(rows)




def build_brk_valuation_context_table(
    bundle: BrkValuationBundle,
    reference: pd.DataFrame,
    *,
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return the key inputs behind Berkshire's current valuation bridge."""
    holdings_metrics = _live_holdings_metrics(
        bundle.holdings.holdings,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
    )
    liquidity_summary = build_liquidity_summary_table(
        build_liquidity_bridge_table(bundle.liquidity.filings)
    )
    latest_liquidity = liquidity_summary.iloc[0] if not liquidity_summary.empty else pd.Series(dtype=object)
    latest_segments = _latest_segments_table(bundle.segments.filings)
    segment_period_end = latest_segments.iloc[0]["period_end"] if not latest_segments.empty else None
    market_snapshot = bundle.overview.market_snapshot
    resolved_market_cap = _resolved_market_cap(market_snapshot)
    brk_b_equivalent_shares = _implied_brk_b_equivalent_shares(market_snapshot)

    return pd.DataFrame(
        [
            {"field": "brk_b_last_price", "value": market_snapshot.get("last_price")},
            {"field": "market_cap", "value": resolved_market_cap},
            {"field": "implied_brk_b_equivalent_shares", "value": brk_b_equivalent_shares},
            {"field": "latest_price_date", "value": market_snapshot.get("latest_price_date")},
            {"field": "13f_filing_date", "value": bundle.holdings.filing_date},
            {"field": "13f_reported_value_usd", "value": holdings_metrics["reported_value_usd"]},
            {"field": "13f_live_resolved_value_usd", "value": holdings_metrics["live_value_usd"]},
            {"field": "13f_live_coverage_ratio", "value": holdings_metrics["coverage_ratio"]},
            {"field": "liquidity_period_end", "value": latest_liquidity.get("period_end")},
            {"field": "net_liquidity_total_usd", "value": _net_liquidity_total(latest_liquidity)},
            {"field": "segment_period_end", "value": segment_period_end},
        ]
    )


def build_market_implied_sotp_bridge_table(
    bundle: BrkValuationBundle,
    reference: pd.DataFrame,
    *,
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return a first explicit Berkshire market-implied SOTP bridge."""
    market_snapshot = bundle.overview.market_snapshot
    market_cap = _resolved_market_cap(market_snapshot)
    share_count = _implied_brk_b_equivalent_shares(market_snapshot)
    holdings_metrics = _live_holdings_metrics(
        bundle.holdings.holdings,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
    )
    liquidity_snapshot = build_latest_liquidity_snapshot_table(
        build_liquidity_bridge_table(bundle.liquidity.filings)
    )

    cash_and_equivalents = _frame_row_value(liquidity_snapshot, "cash_and_equivalents_usd")
    short_term_t_bills = _frame_row_value(liquidity_snapshot, "short_term_us_treasury_bills_usd")
    fixed_maturity = _frame_row_value(liquidity_snapshot, "fixed_maturity_securities_usd")
    payable_component = _frame_row_value(
        liquidity_snapshot,
        "payable_for_purchase_of_us_treasury_bills_usd",
    )
    if payable_component is not None and pd.notna(payable_component):
        payable_component = -float(payable_component)
    net_liquidity = _frame_row_value(liquidity_snapshot, "net_liquid_investments_usd")
    public_equities = holdings_metrics["blended_value_usd"]
    quoted_plus_liquidity = _sum_defined(public_equities, net_liquidity)
    residual = None
    if market_cap is not None and quoted_plus_liquidity is not None and pd.notna(market_cap):
        residual = float(market_cap) - float(quoted_plus_liquidity)

    coverage_text = None
    if holdings_metrics["coverage_ratio"] is not None:
        coverage_text = f"Live 13F price coverage {holdings_metrics['coverage_ratio'] * 100:.1f}%"

    rows = [
        {
            "metric": "public_equity_holdings_blended",
            "value_usd": public_equities,
            "per_brk_b_share_usd": _per_share_value(public_equities, share_count),
            "market_cap_weight": _ratio(public_equities, market_cap),
            "note": coverage_text or "Latest 13F using live prices where resolved and reported values otherwise",
        },
        {
            "metric": "cash_and_equivalents",
            "value_usd": cash_and_equivalents,
            "per_brk_b_share_usd": _per_share_value(cash_and_equivalents, share_count),
            "market_cap_weight": _ratio(cash_and_equivalents, market_cap),
            "note": "Latest filing balance-sheet cash",
        },
        {
            "metric": "short_term_us_treasury_bills",
            "value_usd": short_term_t_bills,
            "per_brk_b_share_usd": _per_share_value(short_term_t_bills, share_count),
            "market_cap_weight": _ratio(short_term_t_bills, market_cap),
            "note": "Latest filing Treasury-bill position",
        },
        {
            "metric": "fixed_maturity_securities",
            "value_usd": fixed_maturity,
            "per_brk_b_share_usd": _per_share_value(fixed_maturity, share_count),
            "market_cap_weight": _ratio(fixed_maturity, market_cap),
            "note": "Latest filing fixed maturity securities",
        },
        {
            "metric": "payable_for_purchase_of_us_treasury_bills",
            "value_usd": payable_component,
            "per_brk_b_share_usd": _per_share_value(payable_component, share_count),
            "market_cap_weight": _ratio(payable_component, market_cap),
            "note": "Deducted from liquidity when reported",
        },
        {
            "metric": "net_liquidity_total",
            "value_usd": net_liquidity,
            "per_brk_b_share_usd": _per_share_value(net_liquidity, share_count),
            "market_cap_weight": _ratio(net_liquidity, market_cap),
            "note": "Cash + Treasury bills + fixed maturity securities - payable",
        },
        {
            "metric": "quoted_holdings_plus_net_liquidity",
            "value_usd": quoted_plus_liquidity,
            "per_brk_b_share_usd": _per_share_value(quoted_plus_liquidity, share_count),
            "market_cap_weight": _ratio(quoted_plus_liquidity, market_cap),
            "note": "Blended 13F public equities plus net liquidity subtotal",
        },
        {
            "metric": "market_cap",
            "value_usd": market_cap,
            "per_brk_b_share_usd": _per_share_value(market_cap, share_count),
            "market_cap_weight": 1.0 if market_cap is not None and pd.notna(market_cap) else None,
            "note": "Current Berkshire market capitalization",
        },
        {
            "metric": "residual_operating_and_other",
            "value_usd": residual,
            "per_brk_b_share_usd": _per_share_value(residual, share_count),
            "market_cap_weight": _ratio(residual, market_cap),
            "note": "Residual after blended 13F public equities and net liquidity; includes operating businesses, non-13F assets, debt, and other items",
        },
    ]
    return pd.DataFrame(rows)


def build_segment_report_summary_table(filings: Sequence[BrkSegmentFiling]) -> pd.DataFrame:
    """Summarize the Berkshire segment filings included in the current output."""
    return pd.DataFrame(
        [
            {
                "filing_date": filing.filing_date,
                "form": filing.form,
                "accession_number": filing.accession_number,
            }
            for filing in filings
        ]
    )


def build_top_level_operating_segments_summary_table(
    filings: Sequence[BrkSegmentFiling],
    *,
    period: str,
) -> pd.DataFrame:
    """Return Berkshire top-level operating segments across selected filings."""
    tables = []
    for filing in filings:
        table = build_top_level_operating_segments_table(filing.reports, period=period)
        if table.empty:
            continue
        table.insert(0, "accession_number", filing.accession_number)
        table.insert(0, "form", filing.form)
        table.insert(0, "filing_date", filing.filing_date)
        tables.append(table)
    if not tables:
        return pd.DataFrame()
    combined = pd.concat(tables, ignore_index=True)
    sort_columns = ["filing_date", "period_end"]
    ascending = [False, False]
    if "revenues_usd" in combined.columns:
        sort_columns.append("revenues_usd")
        ascending.append(False)
    return combined.sort_values(
        by=sort_columns,
        ascending=ascending,
        na_position="last",
    ).reset_index(drop=True)


def build_segment_period_sections(
    filings: Sequence[BrkSegmentFiling],
    *,
    period: str,
) -> list[tuple[str, pd.DataFrame]]:
    """Return one Berkshire segment table per selected filing period."""
    sections = []
    for filing in filings:
        table = build_top_level_operating_segments_table(filing.reports, period=period)
        if table.empty:
            continue
        sections.append((_segment_period_title(filing, table, period=period), table))
    return sections


def _segment_period_title(
    filing: BrkSegmentFiling,
    table: pd.DataFrame,
    *,
    period: str,
) -> str:
    if table.empty or "period_end" not in table.columns:
        return f"Top-Level Operating Segments ({filing.filing_date})"
    period_end = str(table.iloc[0]["period_end"])
    timestamp = pd.Timestamp(period_end)
    if period == "annual":
        label = f"FY {timestamp.year}"
    else:
        quarter = ((timestamp.month - 1) // 3) + 1
        label = f"Q{quarter} {timestamp.year}"
    return f"Top-Level Operating Segments {label} ({filing.filing_date})"


def _live_holdings_metrics(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
) -> dict[str, float | int | None]:
    if holdings.empty:
        return {
            "positions_total": 0,
            "resolved_positions": 0,
            "reported_value_usd": None,
            "resolved_reported_value_usd": None,
            "unresolved_reported_value_usd": None,
            "live_value_usd": None,
            "blended_value_usd": None,
            "coverage_ratio": None,
        }
    enriched = _enriched_holdings_frame(
        holdings,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
    )
    resolved = enriched[enriched["market_value_live_usd"].notna()].copy()
    reported_value = enriched["value_usd"].dropna().sum()
    resolved_reported_value = resolved["value_usd"].dropna().sum()
    live_value = resolved["market_value_live_usd"].dropna().sum()
    unresolved_reported_value = enriched.loc[
        enriched["market_value_live_usd"].isna(),
        "value_usd",
    ].dropna().sum()
    blended_value = _sum_defined(live_value, unresolved_reported_value)
    coverage_ratio = None
    if reported_value:
        coverage_ratio = resolved_reported_value / reported_value
    return {
        "positions_total": int(len(enriched)),
        "resolved_positions": int(len(resolved)),
        "reported_value_usd": reported_value if pd.notna(reported_value) else None,
        "resolved_reported_value_usd": resolved_reported_value if pd.notna(resolved_reported_value) else None,
        "unresolved_reported_value_usd": unresolved_reported_value if pd.notna(unresolved_reported_value) else None,
        "live_value_usd": live_value if pd.notna(live_value) else None,
        "blended_value_usd": blended_value if blended_value is not None and pd.notna(blended_value) else None,
        "coverage_ratio": coverage_ratio,
    }


def _enriched_holdings_frame(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    yahoo_client=None,
    price_change_window: str | None = None,
    enriched_holdings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if enriched_holdings is not None:
        return enriched_holdings.copy()
    aggregated = aggregate_13f_holdings(holdings)
    return enrich_holdings_with_market_prices(
        aggregated,
        reference,
        yahoo_client=yahoo_client,
        price_change_window=price_change_window,
    )


def _latest_segments_table(filings: Sequence[BrkSegmentFiling]) -> pd.DataFrame:
    if not filings:
        return pd.DataFrame()
    return build_top_level_operating_segments_table(filings[0].reports, period="annual")


def _implied_brk_b_equivalent_shares(market_snapshot: dict) -> float | None:
    market_cap = market_snapshot.get("market_cap")
    last_price = market_snapshot.get("last_price")
    if market_cap is not None and last_price not in {None, 0} and pd.notna(market_cap) and pd.notna(last_price):
        return float(market_cap) / float(last_price)
    shares = market_snapshot.get("shares")
    if shares is None or pd.isna(shares):
        return None
    return float(shares)


def _resolved_market_cap(market_snapshot: dict) -> float | None:
    market_cap = market_snapshot.get("market_cap")
    if market_cap is not None and pd.notna(market_cap):
        return float(market_cap)
    shares = market_snapshot.get("shares")
    last_price = market_snapshot.get("last_price")
    if shares is None or last_price in {None, 0}:
        return None
    if pd.isna(shares) or pd.isna(last_price):
        return None
    return float(shares) * float(last_price)


def _per_share_value(value: float | None, share_count: float | None) -> float | None:
    if value is None or share_count in {None, 0}:
        return None
    if pd.isna(value) or pd.isna(share_count):
        return None
    return float(value) / float(share_count)


def _ratio(value: float | None, total: float | None) -> float | None:
    if value is None or total in {None, 0}:
        return None
    if pd.isna(value) or pd.isna(total):
        return None
    return float(value) / float(total)


def _net_liquidity_total(row: pd.Series) -> float | None:
    if row.empty:
        return None
    payable = row.get("payable_for_purchase_of_us_treasury_bills_usd")
    payable_component = -float(payable) if payable is not None and pd.notna(payable) else None
    return _sum_defined(
        row.get("cash_and_equivalents_usd"),
        row.get("short_term_us_treasury_bills_usd"),
        row.get("fixed_maturity_securities_usd"),
        payable_component,
    )


def _sum_defined(*values):
    defined = [value for value in values if value is not None and pd.notna(value)]
    if not defined:
        return None
    return sum(defined)


def _weighted_price_change_from_frame(frame: pd.DataFrame) -> float | None:
    if frame.empty or "value_usd" not in frame.columns or "price_change_pct" not in frame.columns:
        return None
    total_weight = frame["value_usd"].dropna().sum()
    if not total_weight:
        return None
    return float((frame["value_usd"] * frame["price_change_pct"]).sum() / total_weight)


def _field_value(frame: pd.DataFrame, field: str):
    if frame.empty or "field" not in frame.columns or "value" not in frame.columns:
        return None
    matches = frame[frame["field"] == field]
    if matches.empty:
        return None
    return matches.iloc[0]["value"]


def _frame_row_value(frame: pd.DataFrame, column: str):
    if frame.empty or column not in frame.columns:
        return None
    return frame.iloc[0][column]


def _market_cap_from_snapshot(market_snapshot: dict) -> float | None:
    market_cap = market_snapshot.get("market_cap")
    if market_cap is not None and pd.notna(market_cap):
        return float(market_cap)
    last_price = market_snapshot.get("last_price")
    shares = market_snapshot.get("shares")
    if last_price is None or shares is None or pd.isna(last_price) or pd.isna(shares):
        return None
    return float(last_price) * float(shares)




def _extract_liquidity_values(frame: pd.DataFrame) -> tuple[str | None, dict[str, float]]:
    if frame.empty:
        return None, {}
    labels = frame.iloc[:, 0].astype(str).str.strip()
    current_column_index = _latest_date_column_index(frame.columns)
    if current_column_index is None:
        return None, {}
    current_column = frame.columns[current_column_index]
    period_end = _parse_report_date(str(current_column))
    if period_end is None:
        return None, {}
    values = {}
    for metric, label in BRK_LIQUIDITY_REPORT_LABELS.items():
        matched = frame[labels == label]
        if matched.empty:
            continue
        parsed_value = _parse_balance_sheet_value(matched.iloc[0, current_column_index])
        if parsed_value is None:
            continue
        values[metric] = parsed_value
    return period_end, values


def _latest_date_column_index(columns) -> int | None:
    dated_columns = []
    for index, column in enumerate(columns):
        parsed = _parse_report_date(str(column))
        if parsed is not None:
            dated_columns.append((parsed, index))
    if not dated_columns:
        return None
    return max(dated_columns, key=lambda item: item[0])[1]


def _parse_report_date(value: str) -> str | None:
    cleaned = value.replace(".", "")
    try:
        return datetime.strptime(cleaned, "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def _parse_balance_sheet_value(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace("\xa0", " ").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = (
        text.replace("$", "")
        .replace(",", "")
        .replace("[1]", "")
        .replace("[2]", "")
        .replace("[3]", "")
        .replace("(", "")
        .replace(")", "")
        .strip()
    )
    if cleaned in {"", "NaN", "nan"}:
        return None
    try:
        numeric = float(cleaned)
    except ValueError:
        return None
    if negative:
        numeric *= -1
    return numeric * MILLION
