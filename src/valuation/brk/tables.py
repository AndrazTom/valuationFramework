"""Berkshire-only table shaping."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

import pandas as pd

from valuation.brk.service import (
    Brk13FBundle,
    BrkLiquidityFiling,
    BrkSegmentFiling,
    BrkTaxContextBundle,
    BrkValuationBundle,
)
from valuation.brk.service import BRK_A_TICKER, BRK_A_TO_B_CONVERSION, BRK_B_TICKER
from valuation.brk.segments import build_top_level_operating_segments_table
from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_table
from valuation.brk.holdings import aggregate_13f_holdings
from valuation.notation import MILLION
from valuation.securities.pricing import enrich_holdings_with_market_prices, fetch_price_change_snapshot

PUBLIC_EQUITY_VALUATION_BASES = ("reported", "live")
BRK_FEDERAL_CORPORATE_TAX_RATE = 0.21

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

BRK_BALANCE_SHEET_CONTEXT_LABELS = {
    "equity_securities": "Investments in equity securities",
    "equity_method_investments": "Equity method investments",
    "total_assets": "Total assets",
    "deferred_income_taxes": "Income taxes, principally deferred",
    "total_liabilities": "Total liabilities",
}

BRK_BALANCE_SHEET_CONTEXT_SUM_LABELS = {
    "notes_payable_and_other_borrowings": "Notes payable and other borrowings",
}

BRK_REPORT_LABEL_ALIASES = {
    "Payable for purchase of U.S. Treasury Bills": (
        "Payable for purchase of U.S. Treasury Bills",
        "Payable for purchases of U.S. Treasury Bills",
    ),
}

CORE_BRK_FORMS = ("10-K", "10-Q", "8-K", "DEF 14A", "13F-HR", "13F-HR/A")

BRK_13F_HISTORY_SUMMARY_COLUMNS = [
    "filing_date",
    "report_date",
    "accession_number",
    "information_table_filename",
    "holding_count",
    "reported_value_usd",
    "top_holding",
    "top_holding_value_usd",
    "top_holding_weight",
]

BRK_13F_HOLDINGS_HISTORY_COLUMNS = [
    "latest_rank",
    "filing_date",
    "report_date",
    "accession_number",
    "issuer",
    "class_title",
    "cusip",
    "value_usd",
    "value_change_from_prior_filing_usd",
    "shares_or_principal",
    "shares_change_from_prior_filing",
    "portfolio_weight",
]

BRK_13F_CHANGE_SUMMARY_COLUMNS = [
    "issuer",
    "cusip",
    "change_type",
    "prior_shares",
    "current_shares",
    "share_change",
    "share_change_pct",
    "prior_value_usd",
    "current_value_usd",
    "value_change_usd",
    "value_change_pct",
    "share_driven_value_change_usd",
    "price_driven_value_change_usd",
]

_CHANGE_TYPE_ORDER = {"new": 0, "increased": 1, "decreased": 2, "eliminated": 3, "unchanged": 4}


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
                    "label": _report_label_for_metric(metric),
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


def build_liquidity_detail_table(bridge: pd.DataFrame) -> pd.DataFrame:
    """Return only the rows that make up the liquidity subtotal."""
    if bridge.empty:
        return bridge
    return bridge[bridge["metric"].isin(BRK_LIQUIDITY_REPORT_LABELS)].reset_index(drop=True)


def build_balance_sheet_context_table(bridge: pd.DataFrame) -> pd.DataFrame:
    """Return latest selected Berkshire balance-sheet rows that remain SOTP context."""
    if bridge.empty:
        return pd.DataFrame(columns=["field", "value"])
    summary = _balance_sheet_context_summary_table(bridge)
    if summary.empty:
        return pd.DataFrame(columns=["field", "value"])
    latest = summary.iloc[0]
    fields = [
        "period_end",
        "equity_securities_usd",
        "equity_method_investments_usd",
        "total_assets_usd",
        "notes_payable_and_other_borrowings_usd",
        "deferred_income_taxes_usd",
        "total_liabilities_usd",
    ]
    rows = [
        {"field": field, "value": latest.get(field)}
        for field in fields
        if field in latest.index and latest.get(field) is not None and pd.notna(latest.get(field))
    ]
    if rows:
        rows.append(
            {
                "field": "context_note",
                "value": "Selected balance-sheet assets and liabilities remain inside the SOTP residual; they are shown for context, not added to the liquidity subtotal",
            }
        )
    return pd.DataFrame(rows)


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


def build_13f_history_summary_table(filings: Sequence[Brk13FBundle]) -> pd.DataFrame:
    """Summarize Berkshire 13F filings across time."""
    rows = []
    for filing in filings:
        aggregated = aggregate_13f_holdings(filing.holdings)
        reported_value = (
            aggregated["value_usd"].dropna().sum()
            if "value_usd" in aggregated
            else None
        )
        top_holding = aggregated.iloc[0] if not aggregated.empty else pd.Series(dtype=object)
        top_value = top_holding.get("value_usd")
        rows.append(
            {
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "accession_number": filing.accession_number,
                "information_table_filename": filing.information_table_filename,
                "holding_count": int(len(aggregated)),
                "reported_value_usd": reported_value,
                "top_holding": top_holding.get("issuer"),
                "top_holding_value_usd": top_value,
                "top_holding_weight": _ratio(top_value, reported_value),
            }
        )
    return pd.DataFrame(rows, columns=BRK_13F_HISTORY_SUMMARY_COLUMNS)


def build_13f_holdings_history_table(
    filings: Sequence[Brk13FBundle],
    *,
    limit: int = 20,
) -> pd.DataFrame:
    """Return a per-filing history for the latest filing's top holdings."""
    if not filings:
        return pd.DataFrame(columns=BRK_13F_HOLDINGS_HISTORY_COLUMNS)
    limit = max(0, limit)
    aggregated_by_filing = [_history_aggregate_for_filing(filing) for filing in filings]
    if aggregated_by_filing[0].empty:
        return pd.DataFrame(columns=BRK_13F_HOLDINGS_HISTORY_COLUMNS)

    latest = aggregated_by_filing[0].head(limit).copy()
    selected_keys = [_holding_history_key(row) for _, row in latest.iterrows()]
    selected_key_set = set(selected_keys)
    latest_rank_by_key = {
        key: rank
        for rank, key in enumerate(selected_keys, start=1)
    }

    rows = []
    for filing_index, (filing, aggregated) in enumerate(zip(filings, aggregated_by_filing)):
        if aggregated.empty:
            continue
        current_by_key = {}
        for _, current_row in aggregated.iterrows():
            current_key = _holding_history_key(current_row)
            if current_key in selected_key_set:
                current_by_key[current_key] = current_row
        older_by_key = {}
        if filing_index + 1 < len(aggregated_by_filing):
            older_by_key = {
                _holding_history_key(row): row
                for _, row in aggregated_by_filing[filing_index + 1].iterrows()
            }
        total_value = aggregated["value_usd"].dropna().sum()
        for key in selected_keys:
            row = current_by_key.get(key)
            if row is None:
                rows.append(
                    {
                        "latest_rank": latest_rank_by_key[key],
                        "filing_date": filing.filing_date,
                        "report_date": filing.report_date,
                        "accession_number": filing.accession_number,
                        "issuer": _history_key_display_value(key, "issuer"),
                        "class_title": _history_key_display_value(key, "class_title"),
                        "cusip": _history_key_display_value(key, "cusip"),
                        "value_usd": None,
                        "value_change_from_prior_filing_usd": None,
                        "shares_or_principal": None,
                        "shares_change_from_prior_filing": None,
                        "portfolio_weight": None,
                    }
                )
                continue
            older = older_by_key.get(key)
            value = row.get("value_usd")
            shares = row.get("shares_or_principal")
            rows.append(
                {
                    "latest_rank": latest_rank_by_key[key],
                    "filing_date": filing.filing_date,
                    "report_date": filing.report_date,
                    "accession_number": filing.accession_number,
                    "issuer": row.get("issuer"),
                    "class_title": row.get("class_title"),
                    "cusip": row.get("cusip"),
                    "value_usd": value,
                    "value_change_from_prior_filing_usd": _difference(
                        value,
                        older.get("value_usd") if older is not None else None,
                    ),
                    "shares_or_principal": shares,
                    "shares_change_from_prior_filing": _difference(
                        shares,
                        older.get("shares_or_principal") if older is not None else None,
                    ),
                    "portfolio_weight": _ratio(value, total_value),
                }
            )
    return pd.DataFrame(rows, columns=BRK_13F_HOLDINGS_HISTORY_COLUMNS)


def build_13f_issuer_change_summary_table(
    filings: Sequence[Brk13FBundle],
) -> pd.DataFrame:
    """Return a per-issuer change summary comparing the two most recent 13F filings.

    Separates share-count changes (Berkshire's active decisions) from value
    changes (which can also reflect market-price movement).  Change type is
    driven by the share-count direction: new, increased, decreased, eliminated,
    or unchanged.
    """
    if len(filings) < 2:
        return pd.DataFrame(columns=BRK_13F_CHANGE_SUMMARY_COLUMNS)
    current_agg = _history_aggregate_for_filing(filings[0])
    prior_agg = _history_aggregate_for_filing(filings[1])
    if current_agg.empty and prior_agg.empty:
        return pd.DataFrame(columns=BRK_13F_CHANGE_SUMMARY_COLUMNS)

    current_map = _agg_by_cusip(current_agg)
    prior_map = _agg_by_cusip(prior_agg)
    all_cusips = sorted(set(current_map) | set(prior_map))

    rows = []
    for cusip in all_cusips:
        current_row = current_map.get(cusip)
        prior_row = prior_map.get(cusip)

        current_shares = _none_if_nan_float(current_row.get("shares_or_principal") if current_row is not None else None)
        prior_shares = _none_if_nan_float(prior_row.get("shares_or_principal") if prior_row is not None else None)
        current_value = _none_if_nan_float(current_row.get("value_usd") if current_row is not None else None)
        prior_value = _none_if_nan_float(prior_row.get("value_usd") if prior_row is not None else None)

        if current_row is None:
            change_type = "eliminated"
        elif prior_row is None:
            change_type = "new"
        elif prior_shares is not None and current_shares is not None:
            if current_shares > prior_shares * 1.001:
                change_type = "increased"
            elif current_shares < prior_shares * 0.999:
                change_type = "decreased"
            else:
                change_type = "unchanged"
        else:
            change_type = "unchanged"

        share_change = _difference(current_shares, prior_shares)
        share_change_pct = _ratio(share_change, prior_shares)
        value_change = _difference(current_value, prior_value)
        value_change_pct = _ratio(value_change, prior_value)
        issuer = _none_if_nan((current_row if current_row is not None else prior_row).get("issuer"))

        share_driven: float | None = None
        price_driven: float | None = None
        if (
            prior_shares is not None and prior_shares > 0
            and current_shares is not None and current_shares > 0
            and prior_value is not None and current_value is not None
        ):
            prior_price = prior_value / prior_shares
            current_price = current_value / current_shares
            share_driven = (current_shares - prior_shares) * prior_price
            price_driven = prior_shares * (current_price - prior_price)

        rows.append(
            {
                "issuer": issuer,
                "cusip": cusip,
                "change_type": change_type,
                "prior_shares": prior_shares,
                "current_shares": current_shares,
                "share_change": share_change,
                "share_change_pct": share_change_pct,
                "prior_value_usd": prior_value,
                "current_value_usd": current_value,
                "value_change_usd": value_change,
                "value_change_pct": value_change_pct,
                "share_driven_value_change_usd": share_driven,
                "price_driven_value_change_usd": price_driven,
            }
        )

    frame = pd.DataFrame(rows, columns=BRK_13F_CHANGE_SUMMARY_COLUMNS)
    if not frame.empty:
        frame["_sort_type"] = frame["change_type"].map(lambda t: _CHANGE_TYPE_ORDER.get(t, 99))
        abs_share_change = frame["share_change"].apply(lambda x: abs(x) if x is not None and pd.notna(x) else 0.0)
        frame = frame.assign(_sort_abs=abs_share_change)
        frame = frame.sort_values(["_sort_type", "_sort_abs"], ascending=[True, False])
        frame = frame.drop(columns=["_sort_type", "_sort_abs"]).reset_index(drop=True)
    return frame


def build_13f_portfolio_change_summary_table(
    filings: Sequence[Brk13FBundle],
) -> pd.DataFrame:
    """Return a portfolio-level filing-over-filing change summary for the two most recent 13F filings.

    Aggregates reported value, position count, and new/eliminated/changed counts.
    """
    if len(filings) < 2:
        return pd.DataFrame(columns=["field", "value"])
    current_agg = _history_aggregate_for_filing(filings[0])
    prior_agg = _history_aggregate_for_filing(filings[1])
    if current_agg.empty and prior_agg.empty:
        return pd.DataFrame(columns=["field", "value"])

    current_map = _agg_by_cusip(current_agg)
    prior_map = _agg_by_cusip(prior_agg)
    all_cusips = set(current_map) | set(prior_map)

    current_value_total = sum(
        _none_if_nan_float(row.get("value_usd")) or 0.0
        for row in current_map.values()
    )
    prior_value_total = sum(
        _none_if_nan_float(row.get("value_usd")) or 0.0
        for row in prior_map.values()
    )
    value_change = current_value_total - prior_value_total
    value_change_pct = (value_change / prior_value_total) if prior_value_total else None

    new_count = sum(1 for cusip in all_cusips if cusip not in prior_map and cusip in current_map)
    eliminated_count = sum(1 for cusip in all_cusips if cusip in prior_map and cusip not in current_map)
    changed_count = sum(
        1 for cusip in all_cusips
        if cusip in current_map and cusip in prior_map
        and current_map[cusip].get("shares_or_principal") != prior_map[cusip].get("shares_or_principal")
    )

    filing_date_current = filings[0].filing_date
    filing_date_prior = filings[1].filing_date

    rows = [
        {"field": "current_filing_date", "value": filing_date_current},
        {"field": "prior_filing_date", "value": filing_date_prior},
        {"field": "current_positions", "value": len(current_map)},
        {"field": "prior_positions", "value": len(prior_map)},
        {"field": "new_positions", "value": new_count},
        {"field": "eliminated_positions", "value": eliminated_count},
        {"field": "changed_positions", "value": changed_count},
        {"field": "current_reported_value_usd", "value": current_value_total},
        {"field": "prior_reported_value_usd", "value": prior_value_total},
        {"field": "reported_value_change_usd", "value": value_change},
        {"field": "reported_value_change_pct", "value": value_change_pct},
    ]
    return pd.DataFrame(rows)


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
    if resolved_count == 0:
        rows.append(
            {
                "field": "live_price_status",
                "value": "No Yahoo prices resolved in current run",
            }
        )
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

    rows = [
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
    if brk_change is None and holdings_weighted_change is None:
        rows.append(
            {
                "field": "comparison_status",
                "value": "No BRK or holdings price-change data resolved in current run",
            }
        )
    return pd.DataFrame(rows)


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


def _balance_sheet_context_summary_table(bridge: pd.DataFrame) -> pd.DataFrame:
    if bridge.empty:
        return pd.DataFrame()
    context_metrics = set(BRK_BALANCE_SHEET_CONTEXT_LABELS) | set(BRK_BALANCE_SHEET_CONTEXT_SUM_LABELS)
    filtered = bridge[bridge["metric"].isin(context_metrics)]
    if filtered.empty:
        return pd.DataFrame()
    summary = (
        filtered.pivot_table(
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
            "equity_securities": "equity_securities_usd",
            "equity_method_investments": "equity_method_investments_usd",
            "total_assets": "total_assets_usd",
            "deferred_income_taxes": "deferred_income_taxes_usd",
            "total_liabilities": "total_liabilities_usd",
            "notes_payable_and_other_borrowings": "notes_payable_and_other_borrowings_usd",
        }
    )
    return summary.sort_values(
        by=["filing_date", "period_end"],
        ascending=False,
    ).reset_index(drop=True)


def build_public_equity_portfolio_summary_table(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
    equity_valuation_basis: str = "live",
    max_live_holdings: int | None = None,
) -> pd.DataFrame:
    """Summarize Berkshire's latest public-equity block for valuation work."""
    if holdings.empty:
        return pd.DataFrame(columns=["field", "value"])
    holdings_metrics = _live_holdings_metrics(
        holdings,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
        equity_valuation_basis=equity_valuation_basis,
        max_live_holdings=max_live_holdings,
    )
    reported_total = holdings_metrics["reported_value_usd"]
    live_resolved = holdings_metrics["live_value_usd"]
    unresolved_reported = holdings_metrics["unresolved_reported_value_usd"]
    blended_value = holdings_metrics["blended_value_usd"]
    rows = [
        {"field": "reported_13f_value_usd", "value": reported_total},
        {"field": "live_resolved_13f_value_usd", "value": live_resolved},
        {"field": "unresolved_13f_value_reported_usd", "value": unresolved_reported},
        {"field": "blended_13f_value_usd", "value": blended_value},
        {"field": "selected_13f_value_usd", "value": holdings_metrics["selected_value_usd"]},
        {"field": "selected_13f_basis", "value": holdings_metrics["selected_basis"]},
        {
            "field": "live_price_coverage_pct",
            "value": holdings_metrics["coverage_ratio"],
        },
        {"field": "positions_total", "value": holdings_metrics["positions_total"]},
        {"field": "positions_live_priced", "value": holdings_metrics["resolved_positions"]},
        {"field": "positions_unresolved", "value": holdings_metrics["unresolved_positions"]},
        {"field": "live_pricing_limit", "value": holdings_metrics["live_pricing_limit"]},
        {"field": "latest_price_date", "value": holdings_metrics["latest_price_date"]},
    ]
    if holdings_metrics["resolved_positions"] == 0 and holdings_metrics["selected_basis"] != "reported_13f":
        rows.append(
            {
                "field": "live_price_status",
                "value": "No Yahoo prices resolved in current run",
            }
        )
    return pd.DataFrame(rows)


def build_public_equity_revaluation_detail_table(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
    equity_valuation_basis: str = "live",
    max_live_holdings: int | None = None,
    limit: int = 20,
) -> pd.DataFrame:
    """Show which 13F holdings were replaced with live share-count based values."""
    if holdings.empty or normalize_public_equity_valuation_basis(equity_valuation_basis) != "live":
        return pd.DataFrame()
    enriched = _enriched_holdings_frame(
        holdings,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
        max_live_holdings=max_live_holdings,
    )
    if enriched.empty or "market_value_live_usd" not in enriched.columns:
        return pd.DataFrame()
    detail = enriched[
        enriched["market_value_live_usd"].notna() & enriched["value_usd"].notna()
    ].copy()
    if detail.empty:
        return pd.DataFrame()
    detail["live_value_delta_usd"] = detail["market_value_live_usd"] - detail["value_usd"]
    detail["live_value_delta_pct"] = detail.apply(
        lambda row: _ratio(row.get("live_value_delta_usd"), row.get("value_usd")),
        axis=1,
    )
    columns = [
        "issuer",
        "ticker",
        "cusip",
        "value_usd",
        "market_value_live_usd",
        "live_value_delta_usd",
        "live_value_delta_pct",
        "shares_or_principal",
        "last_price",
        "latest_price_date",
    ]
    selected = detail[[column for column in columns if column in detail.columns]].copy()
    selected = selected.rename(columns={"value_usd": "reported_value_usd"})
    return selected.head(max(0, limit)).reset_index(drop=True)


def build_public_equity_tax_context_table(
    tax_context: BrkTaxContextBundle | None,
    equity_portfolio: pd.DataFrame,
) -> pd.DataFrame:
    """Estimate embedded tax context for the selected public-equity value.

    The filing note gives cost/fair value for Berkshire's equity securities in
    aggregate, not cost basis for each 13F row. For live 13F values, scale that
    aggregate cost ratio onto the selected 13F value and treat the result as an
    approximation.
    """
    if tax_context is None:
        return pd.DataFrame(columns=["field", "value"])
    selected_value = _context_field_value(equity_portfolio, "selected_13f_value_usd")
    reported_value = _context_field_value(equity_portfolio, "reported_13f_value_usd")
    equity_note = _extract_equity_securities_tax_basis(tax_context.equity_securities)
    deferred_note = _extract_deferred_tax_context(tax_context.deferred_income_taxes)
    reconciliation = _extract_tax_reconciliation_rates(tax_context.income_tax_reconciliation)

    fair_value = equity_note.get("fair_value_usd")
    cost_basis = equity_note.get("cost_basis_usd")
    unrealized_gain = equity_note.get("unrealized_gain_usd")
    cost_ratio = _ratio(cost_basis, fair_value)
    unrealized_gain_ratio = _ratio(unrealized_gain, fair_value)

    estimated_cost_basis = None
    estimated_unrealized_gain = None
    if selected_value is not None and cost_ratio is not None:
        estimated_cost_basis = selected_value * cost_ratio
        estimated_unrealized_gain = max(0.0, selected_value - estimated_cost_basis)

    investment_deferred_tax = deferred_note.get("investment_deferred_tax_liability_usd")
    scaled_investment_deferred_tax = None
    if investment_deferred_tax is not None and selected_value is not None and fair_value:
        scaled_investment_deferred_tax = investment_deferred_tax * (selected_value / fair_value)

    rows = [
        {"field": "equity_note_filing_date", "value": tax_context.equity_filing_date},
        {"field": "equity_note_accession", "value": tax_context.equity_accession_number},
        {"field": "equity_note_fair_value_usd", "value": fair_value},
        {"field": "equity_note_cost_basis_usd", "value": cost_basis},
        {"field": "equity_note_unrealized_gain_usd", "value": unrealized_gain},
        {"field": "equity_note_unrealized_gain_ratio", "value": unrealized_gain_ratio},
        {"field": "selected_13f_value_usd", "value": selected_value},
        {"field": "reported_13f_value_usd", "value": reported_value},
        {"field": "estimated_selected_13f_cost_basis_usd", "value": estimated_cost_basis},
        {"field": "estimated_selected_13f_unrealized_gain_usd", "value": estimated_unrealized_gain},
        {"field": "federal_corporate_tax_rate", "value": BRK_FEDERAL_CORPORATE_TAX_RATE},
        {
            "field": "state_local_rate_net_federal_benefit",
            "value": reconciliation.get("state_local_rate_net_federal_benefit"),
        },
        {"field": "latest_effective_tax_rate", "value": reconciliation.get("latest_effective_tax_rate")},
        {"field": "tax_note_filing_date", "value": tax_context.tax_filing_date},
        {"field": "tax_note_accession", "value": tax_context.tax_accession_number},
        {"field": "investment_deferred_tax_liability_usd", "value": investment_deferred_tax},
        {"field": "scaled_investment_deferred_tax_liability_usd", "value": scaled_investment_deferred_tax},
        {
            "field": "tax_context_note",
            "value": "Estimated 13F cost basis scales Berkshire's aggregate equity-securities cost/fair-value ratio onto the selected 13F value; tax is a sensitivity, not a precise sale model",
        },
    ]
    return pd.DataFrame(rows)


def build_public_equity_tax_sensitivity_table(
    tax_context_table: pd.DataFrame,
) -> pd.DataFrame:
    """Return after-tax selected 13F sensitivity rows from filing-derived tax context."""
    if tax_context_table.empty:
        return pd.DataFrame()
    selected_value = _context_field_value(tax_context_table, "selected_13f_value_usd")
    estimated_gain = _context_field_value(tax_context_table, "estimated_selected_13f_unrealized_gain_usd")
    if selected_value is None or estimated_gain is None:
        return pd.DataFrame()
    rows = []

    def add_rate_case(scenario: str, tax_rate: float | None, note: str) -> None:
        if tax_rate is None:
            return
        tax = max(0.0, estimated_gain * tax_rate)
        rows.append(
            {
                "scenario": scenario,
                "tax_rate": tax_rate,
                "estimated_tax_usd": tax,
                "after_tax_selected_13f_value_usd": selected_value - tax,
                "tax_as_pct_of_selected_13f": _ratio(tax, selected_value),
                "note": note,
            }
        )

    federal_rate = _context_field_value(tax_context_table, "federal_corporate_tax_rate")
    state_rate = _context_field_value(tax_context_table, "state_local_rate_net_federal_benefit")
    effective_rate = _context_field_value(tax_context_table, "latest_effective_tax_rate")
    add_rate_case("federal_statutory", federal_rate, "21% U.S. federal C-corporation rate applied to estimated unrealized gain")
    add_rate_case(
        "federal_plus_state_local",
        (federal_rate or 0.0) + state_rate if state_rate is not None else None,
        "Federal statutory rate plus Berkshire's latest annual state/local reconciliation effect, net of federal benefit",
    )
    add_rate_case(
        "latest_effective_tax_rate",
        effective_rate,
        "Latest annual company-wide effective tax rate; included for context, not a pure capital-gains rate",
    )

    scaled_dtl = _context_field_value(tax_context_table, "scaled_investment_deferred_tax_liability_usd")
    if scaled_dtl is not None:
        rows.append(
            {
                "scenario": "scaled_reported_investment_deferred_tax",
                "tax_rate": _ratio(scaled_dtl, estimated_gain),
                "estimated_tax_usd": scaled_dtl,
                "after_tax_selected_13f_value_usd": selected_value - scaled_dtl,
                "tax_as_pct_of_selected_13f": _ratio(scaled_dtl, selected_value),
                "note": "Scales Berkshire's reported investment deferred-tax liability by selected 13F value / filing equity fair value",
            }
        )
    return pd.DataFrame(rows)


def build_market_anchor_table(market_snapshot: dict) -> pd.DataFrame:
    """Return the market anchor for Berkshire valuation work."""
    market_cap = _market_cap_from_snapshot(market_snapshot)
    rows = [
        {"field": "primary_valuation_unit", "value": BRK_B_TICKER},
        {"field": "last_price", "value": market_snapshot.get("last_price")},
        {"field": "latest_price_date", "value": market_snapshot.get("latest_price_date")},
        {"field": "shares_outstanding", "value": market_snapshot.get("shares")},
        {"field": "market_cap_usd", "value": market_cap},
    ]
    if all(row["value"] in {None, ""} for row in rows[1:]):
        rows.append(
            {
                "field": "market_snapshot_status",
                "value": "No Yahoo market snapshot values resolved in current run",
            }
        )
    return pd.DataFrame(rows)


def build_brk_valuation_assumptions_table(
    *,
    period: str,
    equity_valuation_basis: str = "live",
    max_live_holdings: int | None = None,
) -> pd.DataFrame:
    """Return the assumptions used in the first Berkshire bridge."""
    equity_basis = normalize_public_equity_valuation_basis(equity_valuation_basis)
    if equity_basis == "reported":
        public_equities_basis = "Latest 13F reported market values from the filing"
        residual_definition = "Market cap less reported 13F public equities less net cash/T-bills"
    else:
        limit_text = "all mapped holdings" if max_live_holdings is None else f"top {max_live_holdings} mapped holdings"
        public_equities_basis = (
            f"Latest 13F, revaluing {limit_text} at current prices where resolved "
            "and using reported values for unresolved positions"
        )
        residual_definition = "Market cap less selected 13F public equities less net cash/T-bills"
    return pd.DataFrame(
        [
            {"field": "valuation_unit", "value": BRK_B_TICKER},
            {"field": "selected_period_type", "value": period},
            {"field": "market_anchor", "value": "Yahoo market snapshot market cap"},
            {
                "field": "public_equities_basis",
                "value": public_equities_basis,
            },
            {"field": "equity_valuation_basis", "value": equity_basis},
            {"field": "equity_live_pricing_limit", "value": max_live_holdings if equity_basis == "live" else None},
            {
                "field": "public_equities_scope",
                "value": "13F positions only; excludes non-13F public equities and controlled subsidiaries",
            },
            {
                "field": "liquidity_basis",
                "value": "Latest filing cash and Treasury bills for deployable core liquidity; fixed maturity securities shown separately as insurance investment context",
            },
            {
                "field": "residual_definition",
                "value": residual_definition,
            },
            {
                "field": "residual_circularity_note",
                "value": "Residual is market-implied (circular): it reflects the market's current pricing, not an independent bottoms-up appraisal of operating business value",
            },
            {
                "field": "insurance_float_note",
                "value": "~$170B insurance float not separately valued in this bridge; float enables investment of policyholders' funds at near-zero cost and is implicitly reflected in the public-equity portfolio value",
            },
            {
                "field": "fixed_maturity_note",
                "value": "Fixed maturity securities are insurance-reserve-backed; not freely deployable excess capital",
            },
        ]
    )


def build_brk_component_bridge_table(
    market_snapshot: dict,
    public_equity_summary: pd.DataFrame,
    latest_liquidity_snapshot: pd.DataFrame,
) -> pd.DataFrame:
    """Return an explicit Berkshire SOTP component bridge.

    Splits the net liquidity into fixed maturity securities and net cash/T-bills
    so the residual more closely approximates the operating business value.
    """
    market_cap = _market_cap_from_snapshot(market_snapshot)
    shares = market_snapshot.get("shares")
    public_equities = _field_value(public_equity_summary, "selected_13f_value_usd")
    if public_equities is None:
        public_equities = _field_value(public_equity_summary, "blended_13f_value_usd")

    # Pull individual liquidity components for explicit breakdown
    fixed_maturity = _frame_row_value(latest_liquidity_snapshot, "fixed_maturity_securities_usd")
    cash = _frame_row_value(latest_liquidity_snapshot, "cash_and_equivalents_usd")
    tbills = _frame_row_value(latest_liquidity_snapshot, "short_term_us_treasury_bills_usd")
    tbill_payable = _frame_row_value(latest_liquidity_snapshot, "payable_for_purchase_of_us_treasury_bills_usd")

    # Net cash and T-bills = cash + T-bills - T-bill purchase payable
    net_cash_and_tbills: float | None = None
    if cash is not None or tbills is not None:
        base = _sum_defined(cash, tbills)
        if tbill_payable is not None:
            net_cash_and_tbills = _sum_defined(base, -float(tbill_payable))
        else:
            net_cash_and_tbills = base

    # Residual after all explicit components
    implied_other = None
    if market_cap is not None:
        implied_other = float(market_cap)
        for value in (public_equities, fixed_maturity, net_cash_and_tbills):
            if value is not None and pd.notna(value):
                implied_other -= float(value)

    def _share(value: float | None) -> float | None:
        if value is None or market_cap is None or market_cap == 0:
            return None
        return value / market_cap

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
            "share_of_market_cap_pct": _share(public_equities),
            "method": "Latest 13F using live prices where resolved and reported values otherwise",
        },
        {
            "component": "fixed_maturity_securities",
            "value_usd": fixed_maturity,
            "per_brk_b_share_usd": _per_share_value(fixed_maturity, shares),
            "share_of_market_cap_pct": _share(fixed_maturity),
            "method": "Insurance portfolio fixed maturity bonds (filing balance sheet)",
        },
        {
            "component": "net_cash_and_treasury_bills",
            "value_usd": net_cash_and_tbills,
            "per_brk_b_share_usd": _per_share_value(net_cash_and_tbills, shares),
            "share_of_market_cap_pct": _share(net_cash_and_tbills),
            "method": "Cash + T-bills net of T-bill purchase payable (filing balance sheet)",
        },
        {
            "component": "implied_operating_businesses",
            "value_usd": implied_other,
            "per_brk_b_share_usd": _per_share_value(implied_other, shares),
            "share_of_market_cap_pct": _share(implied_other),
            "method": "Residual: market cap minus 13F equities, fixed maturity, and net cash/T-bills",
        },
    ]
    return pd.DataFrame(rows)




def build_brk_valuation_context_table(
    bundle: BrkValuationBundle,
    reference: pd.DataFrame,
    *,
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
    equity_valuation_basis: str = "live",
    max_live_holdings: int | None = None,
) -> pd.DataFrame:
    """Return the key inputs behind Berkshire's current valuation bridge."""
    holdings_metrics = _live_holdings_metrics(
        bundle.holdings.holdings,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
        equity_valuation_basis=equity_valuation_basis,
        max_live_holdings=max_live_holdings,
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
            {"field": "13f_selected_value_usd", "value": holdings_metrics["selected_value_usd"]},
            {"field": "13f_selected_basis", "value": holdings_metrics["selected_basis"]},
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
    equity_valuation_basis: str = "live",
    max_live_holdings: int | None = None,
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
        equity_valuation_basis=equity_valuation_basis,
        max_live_holdings=max_live_holdings,
    )
    liquidity_bridge = build_liquidity_bridge_table(bundle.liquidity.filings)
    liquidity_snapshot = build_latest_liquidity_snapshot_table(liquidity_bridge)
    bs_context = _balance_sheet_context_summary_table(liquidity_bridge)
    deferred_tax = float(bs_context.iloc[0]["deferred_income_taxes_usd"]) if not bs_context.empty and "deferred_income_taxes_usd" in bs_context.columns and pd.notna(bs_context.iloc[0].get("deferred_income_taxes_usd")) else None

    cash_and_equivalents = _frame_row_value(liquidity_snapshot, "cash_and_equivalents_usd")
    short_term_t_bills = _frame_row_value(liquidity_snapshot, "short_term_us_treasury_bills_usd")
    fixed_maturity = _frame_row_value(liquidity_snapshot, "fixed_maturity_securities_usd")
    payable_raw = _frame_row_value(liquidity_snapshot, "payable_for_purchase_of_us_treasury_bills_usd")
    payable_component = -float(payable_raw) if payable_raw is not None and pd.notna(payable_raw) else None

    # Core deployable liquidity: cash + T-bills - payable only.
    # Fixed maturity securities are insurance-reserve-backed and sit inside the insurance
    # business; they are not freely deployable capital and must not be subtracted here.
    net_core_liquidity = _sum_defined(cash_and_equivalents, short_term_t_bills, payable_component)
    public_equities = holdings_metrics["selected_value_usd"]
    quoted_plus_core_liquidity = _sum_defined(public_equities, net_core_liquidity)
    residual = None
    if market_cap is not None and quoted_plus_core_liquidity is not None and pd.notna(market_cap):
        residual = float(market_cap) - float(quoted_plus_core_liquidity)

    coverage_text = _public_equity_note(holdings_metrics)

    rows = [
        {
            "metric": "public_equity_holdings_blended",
            "value_usd": public_equities,
            "per_brk_b_share_usd": _per_share_value(public_equities, share_count),
            "market_cap_weight": _ratio(public_equities, market_cap),
            "note": coverage_text,
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
            "metric": "payable_for_purchase_of_us_treasury_bills",
            "value_usd": payable_component,
            "per_brk_b_share_usd": _per_share_value(payable_component, share_count),
            "market_cap_weight": _ratio(payable_component, market_cap),
            "note": "Deducted from core liquidity when reported",
        },
        {
            "metric": "net_cash_and_treasury_bills",
            "value_usd": net_core_liquidity,
            "per_brk_b_share_usd": _per_share_value(net_core_liquidity, share_count),
            "market_cap_weight": _ratio(net_core_liquidity, market_cap),
            "note": "Cash + Treasury bills - payable (excludes fixed maturity; see context row below)",
        },
        {
            "metric": "quoted_holdings_plus_net_cash",
            "value_usd": quoted_plus_core_liquidity,
            "per_brk_b_share_usd": _per_share_value(quoted_plus_core_liquidity, share_count),
            "market_cap_weight": _ratio(quoted_plus_core_liquidity, market_cap),
            "note": "Selected 13F public equities plus net cash and T-bills",
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
            "note": "Market-implied plug (circular): market cap minus public equities and net cash/T-bills. Not an independent appraisal — reflects what the market already prices in for operating businesses, insurance portfolio (incl. fixed maturity), non-13F assets, debt, and deferred taxes",
        },
        {
            "metric": "fixed_maturity_securities_context",
            "value_usd": fixed_maturity,
            "per_brk_b_share_usd": _per_share_value(fixed_maturity, share_count),
            "market_cap_weight": _ratio(fixed_maturity, market_cap),
            "note": "Context only — included in residual above; insurance-reserve-backed bond portfolio, not freely deployable capital",
        },
        {
            "metric": "deferred_income_taxes_context",
            "value_usd": deferred_tax,
            "per_brk_b_share_usd": _per_share_value(deferred_tax, share_count),
            "market_cap_weight": _ratio(deferred_tax, market_cap),
            "note": "Context only — latest balance-sheet deferred income tax liability; not deducted from the bridge unless the residual definition changes. Use the public-equity tax sensitivity table for an embedded-gain estimate on selected 13F holdings",
        },
    ]
    return pd.DataFrame(rows)


def build_operating_business_context_table(
    bundle: BrkValuationBundle,
    reference: pd.DataFrame,
    *,
    period: str = "annual",
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
    equity_valuation_basis: str = "live",
    max_live_holdings: int | None = None,
) -> pd.DataFrame:
    """Put the SOTP residual next to latest reported operating segment earnings."""
    bridge = build_market_implied_sotp_bridge_table(
        bundle,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
        equity_valuation_basis=equity_valuation_basis,
        max_live_holdings=max_live_holdings,
    )
    residual = _metric_value(bridge, "residual_operating_and_other")
    market_cap = _metric_value(bridge, "market_cap")
    segments = _latest_segments_table(bundle.segments.filings, period=period)
    pretax_earnings = _segment_pretax_earnings_total(segments)
    period_end = segments.iloc[0].get("period_end") if not segments.empty else None
    return pd.DataFrame(
        [
            {"field": "segment_period_end", "value": period_end},
            {"field": "operating_segment_count", "value": int(len(segments)) if not segments.empty else 0},
            {"field": "operating_segment_pretax_earnings_usd", "value": pretax_earnings},
            {"field": "residual_operating_and_other_usd", "value": residual},
            {
                "field": "residual_to_pretax_earnings_multiple",
                "value": _ratio(residual, pretax_earnings),
            },
            {
                "field": "residual_market_cap_weight",
                "value": _ratio(residual, market_cap),
            },
            {
                "field": "context_note",
                "value": "Residual includes operating businesses plus non-13F assets, debt, taxes, and other items; segment earnings are pre-tax and not a standalone valuation",
            },
        ]
    )


_BRK_DEFAULT_REQUIRED_RETURNS = (0.08, 0.10, 0.12)


def _context_field_value(context: pd.DataFrame, field: str) -> float | None:
    if context.empty or "field" not in context.columns or "value" not in context.columns:
        return None
    rows = context[context["field"] == field]
    if rows.empty:
        return None
    v = rows.iloc[0]["value"]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_brk_operating_reverse_dcf_table(
    context_table: pd.DataFrame,
    market_snapshot: dict,
    *,
    required_returns: tuple[float, ...] | list[float] = _BRK_DEFAULT_REQUIRED_RETURNS,
) -> pd.DataFrame:
    """Return implied perpetual growth rates for Berkshire operating businesses.

    Uses the Gordon Growth model solved for g:
      residual = pretax_earnings / (r - g)  →  g = r - pretax_earnings / residual

    ``residual`` is the market-implied operating-and-other residual from the SOTP
    bridge (includes non-13F assets, debt, deferred taxes, and other items, so treat
    the implied growth as an approximation, not a precise business appraisal).
    ``pretax_earnings`` are the latest reported top-level segment pre-tax earnings.
    ``zero_growth_operating_value_usd`` is what the residual would be worth at that
    required return with zero growth assumed: pretax_earnings / r.

    Returns empty DataFrame when residual or pretax earnings are unavailable or ≤ 0.

    Columns: assumed_return, implied_growth, zero_growth_operating_value_usd,
             zero_growth_per_brk_b_usd
    ``assumed_return`` and ``implied_growth`` are 0-1 decimals.
    """
    residual = _context_field_value(context_table, "residual_operating_and_other_usd")
    pretax_earnings = _context_field_value(context_table, "operating_segment_pretax_earnings_usd")
    if residual is None or pretax_earnings is None or residual <= 0 or pretax_earnings <= 0:
        return pd.DataFrame()

    share_count = _implied_brk_b_equivalent_shares(market_snapshot)
    earnings_yield = pretax_earnings / residual
    rows = []
    for r in required_returns:
        implied_g = r - earnings_yield
        zero_growth_value = pretax_earnings / r
        rows.append(
            {
                "assumed_return": r,
                "implied_growth": implied_g,
                "zero_growth_operating_value_usd": zero_growth_value,
                "zero_growth_per_brk_b_usd": _per_share_value(zero_growth_value, share_count),
                "model_note": "Pre-tax earnings / pre-tax return; apply ~0.75 tax-rate factor for after-tax equivalent. Residual is market-implied (circular).",
            }
        )
    return pd.DataFrame(rows)


def build_brk_valuation_summary_table(
    market_snapshot: dict,
    sotp_bridge: pd.DataFrame,
    operating_context: pd.DataFrame,
    reverse_dcf: pd.DataFrame,
    equity_portfolio: pd.DataFrame,
) -> pd.DataFrame:
    """Return a compact key-numbers summary extracted from already-computed SOTP tables.

    Columns: field, value.  Values are raw numerics; humanize_frame formats them for display.
    Designed to be the first section of a valuation report — key findings at a glance.
    """
    price = market_snapshot.get("last_price")
    market_cap = _metric_value(sotp_bridge, "market_cap")
    blended_13f = _context_field_value(equity_portfolio, "blended_13f_value_usd")
    selected_13f = _context_field_value(equity_portfolio, "selected_13f_value_usd")
    selected_13f_basis = _field_value(equity_portfolio, "selected_13f_basis")
    reported_13f = _context_field_value(equity_portfolio, "reported_13f_value_usd")
    coverage = _context_field_value(equity_portfolio, "live_price_coverage_pct")
    net_liquidity = _metric_value(sotp_bridge, "net_cash_and_treasury_bills")
    residual = _metric_value(sotp_bridge, "residual_operating_and_other")
    residual_per_share = _metric_per_share(sotp_bridge, "residual_operating_and_other")
    residual_weight = _metric_weight(sotp_bridge, "residual_operating_and_other")
    pretax_earnings = _context_field_value(operating_context, "operating_segment_pretax_earnings_usd")
    earnings_multiple = _context_field_value(operating_context, "residual_to_pretax_earnings_multiple")

    implied_growth_10 = None
    zero_growth_per_share_10 = None
    if not reverse_dcf.empty and "assumed_return" in reverse_dcf.columns:
        row_10 = reverse_dcf[abs(reverse_dcf["assumed_return"] - 0.10) < 0.001]
        if not row_10.empty:
            v = row_10.iloc[0].get("implied_growth")
            implied_growth_10 = float(v) if v is not None and pd.notna(v) else None
            v = row_10.iloc[0].get("zero_growth_per_brk_b_usd")
            zero_growth_per_share_10 = float(v) if v is not None and pd.notna(v) else None

    rows = [
        {"field": "price_brk_b", "value": price},
        {"field": "market_cap_usd", "value": market_cap},
        {"field": "13f_reported_value_usd", "value": reported_13f},
        {"field": "13f_selected_basis", "value": selected_13f_basis},
        {"field": "13f_blended_value_usd", "value": blended_13f},
        {"field": "13f_selected_value_usd", "value": selected_13f if selected_13f is not None else blended_13f},
        {"field": "13f_live_coverage_pct", "value": coverage},
        {"field": "net_core_liquidity_usd", "value": net_liquidity},
        {"field": "residual_operating_and_other_usd", "value": residual},
        {"field": "residual_per_brk_b_usd", "value": residual_per_share},
        {"field": "residual_market_cap_weight", "value": residual_weight},
        {"field": "segment_pretax_earnings_usd", "value": pretax_earnings},
        {"field": "residual_to_pretax_earnings_multiple", "value": earnings_multiple},
        {"field": "implied_growth_at_10_pct", "value": implied_growth_10},
        {"field": "zero_growth_value_per_brk_b_usd", "value": zero_growth_per_share_10},
    ]
    return pd.DataFrame(rows)


def build_segment_metric_history_table(
    filings: Sequence[BrkSegmentFiling],
    *,
    metric: str,
    period: str = "annual",
    row_label: str | None = None,
) -> pd.DataFrame:
    """Generic pivot: segments as rows, period labels as columns, CAGR appended.

    Each cell is the raw USD value for that segment in that period.
    Returns empty DataFrame when no filings yield the requested metric.
    """
    records: list[dict] = []
    for filing in filings:
        table = build_top_level_operating_segments_table(filing.reports, period=period)
        if table.empty or metric not in table.columns:
            continue
        ts = table.iloc[0]["period_end"]
        try:
            t = pd.Timestamp(ts)
        except Exception:
            continue
        if period == "annual":
            col_label = f"FY {t.year}"
        else:
            q = ((t.month - 1) // 3) + 1
            col_label = f"{t.year} Q{q}"
        for _, row in table.iterrows():
            seg = row.get("segment")
            val = row.get(metric)
            if seg is None or val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            records.append({"segment": seg, "period_label": col_label, "value": float(val)})
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    pivot = (
        df.pivot_table(index="segment", columns="period_label", values="value", aggfunc="first")
        .rename_axis(columns=None)
        .reset_index()
    )
    # Sort period columns chronologically (oldest left → newest right for CAGR direction)
    period_cols = [c for c in pivot.columns if c != "segment"]
    period_cols_sorted = sorted(period_cols, key=_period_col_sort_key)
    pivot = pivot[["segment"] + period_cols_sorted]

    pivot["cagr_pct"] = pivot.apply(
        lambda row: _row_cagr([row.get(c) for c in period_cols_sorted]), axis=1
    )
    # Add Total row
    total_row: dict = {"segment": "Total"}
    for c in period_cols_sorted:
        col_vals = pd.to_numeric(pivot[c], errors="coerce")
        total_row[c] = col_vals.sum() if col_vals.notna().any() else None
    total_row["cagr_pct"] = _row_cagr([total_row.get(c) for c in period_cols_sorted])
    pivot = pd.concat([pivot, pd.DataFrame([total_row])], ignore_index=True)
    pivot["unit"] = "USD"
    return pivot


def build_segment_earnings_history_table(
    filings: Sequence[BrkSegmentFiling], *, period: str = "annual"
) -> pd.DataFrame:
    return build_segment_metric_history_table(filings, metric="earnings_before_income_taxes_usd", period=period)


def build_segment_revenues_history_table(
    filings: Sequence[BrkSegmentFiling], *, period: str = "annual"
) -> pd.DataFrame:
    return build_segment_metric_history_table(filings, metric="revenues_usd", period=period)


def build_segment_dna_history_table(
    filings: Sequence[BrkSegmentFiling], *, period: str = "annual"
) -> pd.DataFrame:
    return build_segment_metric_history_table(filings, metric="depreciation_and_amortization_usd", period=period)


def build_segment_capex_history_table(
    filings: Sequence[BrkSegmentFiling], *, period: str = "annual"
) -> pd.DataFrame:
    return build_segment_metric_history_table(filings, metric="capex_usd", period=period)


def build_segment_owner_earnings_history_table(
    filings: Sequence[BrkSegmentFiling], *, period: str = "annual"
) -> pd.DataFrame:
    """Pivot of owner earnings (pretax + D&A - capex) per segment per period."""
    records: list[dict] = []
    for filing in filings:
        table = build_top_level_operating_segments_table(filing.reports, period=period)
        if table.empty:
            continue
        required = {"earnings_before_income_taxes_usd", "depreciation_and_amortization_usd", "capex_usd"}
        if not required.issubset(table.columns):
            continue
        ts = table.iloc[0]["period_end"]
        try:
            t = pd.Timestamp(ts)
        except Exception:
            continue
        if period == "annual":
            col_label = f"FY {t.year}"
        else:
            q = ((t.month - 1) // 3) + 1
            col_label = f"{t.year} Q{q}"
        for _, row in table.iterrows():
            seg = row.get("segment")
            pretax = row.get("earnings_before_income_taxes_usd")
            dna = row.get("depreciation_and_amortization_usd")
            capex = row.get("capex_usd")
            if seg is None or any(v is None or (isinstance(v, float) and pd.isna(v)) for v in [pretax, dna, capex]):
                continue
            oe = float(pretax) + float(dna) - float(capex)
            records.append({"segment": seg, "period_label": col_label, "value": oe})
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    pivot = (
        df.pivot_table(index="segment", columns="period_label", values="value", aggfunc="first")
        .rename_axis(columns=None)
        .reset_index()
    )
    period_cols = sorted([c for c in pivot.columns if c != "segment"], key=_period_col_sort_key)
    pivot = pivot[["segment"] + period_cols]
    pivot["cagr_pct"] = pivot.apply(lambda row: _row_cagr([row.get(c) for c in period_cols]), axis=1)
    total_row: dict = {"segment": "Total"}
    for c in period_cols:
        col_vals = pd.to_numeric(pivot[c], errors="coerce")
        total_row[c] = col_vals.sum() if col_vals.notna().any() else None
    total_row["cagr_pct"] = _row_cagr([total_row.get(c) for c in period_cols])
    pivot = pd.concat([pivot, pd.DataFrame([total_row])], ignore_index=True)
    pivot["unit"] = "USD"
    return pivot


def build_segment_pretax_margin_history_table(
    filings: Sequence[BrkSegmentFiling], *, period: str = "annual"
) -> pd.DataFrame:
    """Pivot of pretax margin (pretax / revenue) per segment per period.

    Values stored as 0-1 ratios; unit='PCT' so humanize_frame renders as %.
    Includes Total row using aggregate pretax / aggregate revenue.
    """
    records: list[dict] = []
    for filing in filings:
        table = build_top_level_operating_segments_table(filing.reports, period=period)
        if table.empty:
            continue
        if "earnings_before_income_taxes_usd" not in table.columns or "revenues_usd" not in table.columns:
            continue
        ts = table.iloc[0]["period_end"]
        try:
            t = pd.Timestamp(ts)
        except Exception:
            continue
        col_label = f"FY {t.year}" if period == "annual" else f"{t.year} Q{((t.month - 1) // 3) + 1}"
        for _, row in table.iterrows():
            seg = row.get("segment")
            pretax = row.get("earnings_before_income_taxes_usd")
            rev = row.get("revenues_usd")
            if seg is None or any(v is None or (isinstance(v, float) and pd.isna(v)) for v in [pretax, rev]):
                continue
            if float(rev) == 0:
                continue
            records.append({"segment": seg, "period_label": col_label, "value": float(pretax) / float(rev)})
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    pivot = (
        df.pivot_table(index="segment", columns="period_label", values="value", aggfunc="first")
        .rename_axis(columns=None)
        .reset_index()
    )
    period_cols = sorted([c for c in pivot.columns if c != "segment"], key=_period_col_sort_key)
    pivot = pivot[["segment"] + period_cols]
    pivot["cagr_pct"] = pivot.apply(lambda row: _row_cagr([row.get(c) for c in period_cols]), axis=1)

    # Total row: aggregate pretax / aggregate revenue per period
    pretax_table = build_segment_earnings_history_table(filings, period=period)
    rev_table = build_segment_revenues_history_table(filings, period=period)
    total_row: dict = {"segment": "Total"}
    for c in period_cols:
        pretax_total = None
        rev_total = None
        if not pretax_table.empty and c in pretax_table.columns:
            seg_rows = pretax_table[pretax_table["segment"] != "Total"]
            vals = pd.to_numeric(seg_rows[c], errors="coerce")
            pretax_total = vals.sum() if vals.notna().any() else None
        if not rev_table.empty and c in rev_table.columns:
            seg_rows2 = rev_table[rev_table["segment"] != "Total"]
            vals2 = pd.to_numeric(seg_rows2[c], errors="coerce")
            rev_total = vals2.sum() if vals2.notna().any() else None
        if pretax_total is not None and rev_total is not None and rev_total != 0:
            total_row[c] = pretax_total / rev_total
        else:
            total_row[c] = None
    total_row["cagr_pct"] = _row_cagr([total_row.get(c) for c in period_cols])
    pivot = pd.concat([pivot, pd.DataFrame([total_row])], ignore_index=True)
    pivot["unit"] = "PCT"
    return pivot


def build_segment_implied_allocation_table(
    bundle: "BrkValuationBundle",
    reference: pd.DataFrame,
    *,
    period: str = "annual",
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
    equity_valuation_basis: str = "live",
    max_live_holdings: int | None = None,
) -> pd.DataFrame:
    """Allocate the SOTP residual proportionally to each segment's pre-tax earnings share.

    Shows segment, pretax earnings, % of total, implied value, and implied P/E.
    Also shows owner earnings columns when available.
    """
    bridge = build_market_implied_sotp_bridge_table(
        bundle,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
        equity_valuation_basis=equity_valuation_basis,
        max_live_holdings=max_live_holdings,
    )
    residual = _metric_value(bridge, "residual_operating_and_other")
    share_count = _implied_brk_b_equivalent_shares(bundle.overview.market_snapshot)
    if residual is None or residual <= 0:
        return pd.DataFrame()
    segments = _latest_segments_table(bundle.segments.filings, period=period)
    if segments.empty or "earnings_before_income_taxes_usd" not in segments.columns:
        return pd.DataFrame()
    valid_segs = segments[pd.to_numeric(segments["earnings_before_income_taxes_usd"], errors="coerce").notna()].copy()
    if valid_segs.empty:
        return pd.DataFrame()
    total_pretax = float(pd.to_numeric(valid_segs["earnings_before_income_taxes_usd"], errors="coerce").sum())
    if total_pretax <= 0:
        return pd.DataFrame()

    has_oe = (
        "earnings_before_income_taxes_usd" in segments.columns
        and "depreciation_and_amortization_usd" in segments.columns
        and "capex_usd" in segments.columns
    )
    rows = []
    for _, row in valid_segs.iterrows():
        pretax = float(row["earnings_before_income_taxes_usd"])
        share_pct = pretax / total_pretax
        implied_val = residual * share_pct
        implied_pe = implied_val / pretax if pretax != 0 else None
        rec: dict = {
            "segment": row.get("segment"),
            "pretax_earnings_usd": pretax,
            "pretax_share_pct": share_pct,
            "implied_value_usd": implied_val,
            "implied_pe_multiple": implied_pe,
        }
        if has_oe:
            dna = row.get("depreciation_and_amortization_usd")
            capex = row.get("capex_usd")
            if dna is not None and capex is not None and not any(
                isinstance(v, float) and pd.isna(v) for v in [dna, capex]
            ):
                oe = pretax + float(dna) - float(capex)
                rec["owner_earnings_usd"] = oe
                rec["implied_p_oe_multiple"] = implied_val / oe if oe != 0 else None
        rows.append(rec)
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    # Append totals row
    total: dict = {
        "segment": "Total",
        "pretax_earnings_usd": total_pretax,
        "pretax_share_pct": 1.0,
        "implied_value_usd": residual,
        "implied_pe_multiple": residual / total_pretax if total_pretax != 0 else None,
    }
    if has_oe and "owner_earnings_usd" in result.columns:
        total_oe = pd.to_numeric(result["owner_earnings_usd"], errors="coerce").sum()
        total["owner_earnings_usd"] = total_oe
        total["implied_p_oe_multiple"] = residual / total_oe if total_oe != 0 else None
    return pd.concat([result, pd.DataFrame([total])], ignore_index=True)


def build_opco_valuation_sensitivity_table(
    bundle: "BrkValuationBundle",
    reference: pd.DataFrame,
    *,
    period: str = "annual",
    pe_multiples: tuple[float, ...] = (6.0, 8.0, 10.0, 12.0, 15.0),
    yahoo_client=None,
    enriched_holdings: pd.DataFrame | None = None,
    equity_valuation_basis: str = "live",
    max_live_holdings: int | None = None,
) -> pd.DataFrame:
    """Show implied BRK.B price at various owner-earnings (or pretax-earnings) multiples.

    Total value = (13F blended + net liquidity) + (owner earnings × multiple).
    Falls back to pretax earnings when OE components are unavailable.
    """
    bridge = build_market_implied_sotp_bridge_table(
        bundle,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
        equity_valuation_basis=equity_valuation_basis,
        max_live_holdings=max_live_holdings,
    )
    known_assets = None
    pe_val = _metric_value(bridge, "public_equity_holdings_blended")
    liq_val = _metric_value(bridge, "net_cash_and_treasury_bills")
    if pe_val is not None and liq_val is not None:
        known_assets = pe_val + liq_val
    if known_assets is None:
        return pd.DataFrame()

    share_count = _implied_brk_b_equivalent_shares(bundle.overview.market_snapshot)
    last_price = bundle.overview.market_snapshot.get("last_price")
    if share_count is None or share_count <= 0:
        return pd.DataFrame()

    segments = _latest_segments_table(bundle.segments.filings, period=period)
    owner_earnings: float | None = None
    earnings_label = "pretax earnings"
    if not segments.empty:
        required_oe = {"earnings_before_income_taxes_usd", "depreciation_and_amortization_usd", "capex_usd"}
        if required_oe.issubset(segments.columns):
            pt_vals = pd.to_numeric(segments["earnings_before_income_taxes_usd"], errors="coerce")
            dna_vals = pd.to_numeric(segments["depreciation_and_amortization_usd"], errors="coerce")
            capex_vals = pd.to_numeric(segments["capex_usd"], errors="coerce")
            total_pt = pt_vals.sum() if pt_vals.notna().any() else None
            total_dna = dna_vals.sum() if dna_vals.notna().any() else None
            total_capex = capex_vals.sum() if capex_vals.notna().any() else None
            if all(v is not None for v in [total_pt, total_dna, total_capex]):
                oe = float(total_pt) + float(total_dna) - float(total_capex)
                if oe > 0:
                    owner_earnings = oe
                    earnings_label = "owner earnings"
        if owner_earnings is None and "earnings_before_income_taxes_usd" in segments.columns:
            pt_vals = pd.to_numeric(segments["earnings_before_income_taxes_usd"], errors="coerce")
            total_pt = float(pt_vals.sum()) if pt_vals.notna().any() else None
            if total_pt is not None and total_pt > 0:
                owner_earnings = total_pt
    if owner_earnings is None or owner_earnings <= 0:
        return pd.DataFrame()

    rows = []
    for multiple in pe_multiples:
        implied_opco = owner_earnings * multiple
        implied_total = known_assets + implied_opco
        implied_price = implied_total / share_count
        upside = ((implied_price / float(last_price)) - 1.0) if last_price and float(last_price) > 0 else None
        rows.append({
            "scenario": f"{multiple:.0f}× {earnings_label}",
            "implied_opco_value_usd": implied_opco,
            "implied_total_value_usd": implied_total,
            "implied_brk_b_price_usd": implied_price,
            "vs_current_price_pct": upside,
        })
    return pd.DataFrame(rows)


def build_book_value_history_table(
    company_facts: dict,
    share_count: float | None,
    *,
    limit: int = 5,
) -> pd.DataFrame:
    """Show stockholders' equity and optional book value per BRK.B across annual periods.

    Uses build_key_facts_table to find the latest equity value, and
    company_facts_to_table for the multi-year annual series.
    """
    from valuation.company.statements import build_statement_table

    balance = build_statement_table(company_facts, statement="balance", period="annual", limit=limit)
    if balance.empty:
        return pd.DataFrame()

    # Find stockholders_equity row
    eq_rows = balance[balance["metric"] == "stockholders_equity"]
    if eq_rows.empty:
        return pd.DataFrame()

    # period columns are all columns except 'metric', 'unit', and 'cagr_pct'
    non_period_cols = {"metric", "unit", "cagr_pct"}
    period_cols = [c for c in eq_rows.columns if c not in non_period_cols]
    if not period_cols:
        return pd.DataFrame()

    equity_row = eq_rows.iloc[0][period_cols].to_dict()
    rows = [{"metric": "stockholders_equity_usd", "unit": "USD", **equity_row}]

    if share_count is not None and share_count > 0:
        bvps = {}
        for col in period_cols:
            v = equity_row.get(col)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                bvps[col] = float(v) / share_count
            else:
                bvps[col] = None
        rows.append({"metric": "book_value_per_brk_b_usd", "unit": "USD", **bvps})

    result = pd.DataFrame(rows)
    # Compute CAGR on the equity row
    result["cagr_pct"] = result.apply(
        lambda row: _row_cagr([row.get(c) for c in period_cols]), axis=1
    )
    return result


def _period_col_sort_key(label: str) -> tuple[int, int]:
    """Sort period labels chronologically. FY YYYY → (year, 0); YYYY Qn → (year, quarter)."""
    import re as _re
    m_fy = _re.match(r"FY (\d{4})$", label)
    if m_fy:
        return (int(m_fy.group(1)), 0)
    m_q = _re.match(r"(\d{4}) Q(\d)$", label)
    if m_q:
        return (int(m_q.group(1)), int(m_q.group(2)))
    return (0, 0)


def _row_cagr(values: list) -> float | None:
    """Compute annualised CAGR from first to last positive value in the list."""
    clean = [float(v) for v in values if v is not None and not (isinstance(v, float) and pd.isna(v))]
    if len(clean) < 2 or clean[0] <= 0 or clean[-1] <= 0:
        return None
    periods = len(clean) - 1
    if periods == 0:
        return None
    return (clean[-1] / clean[0]) ** (1.0 / periods) - 1.0


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
        title = _segment_period_title(filing, table, period=period)
        table = table.drop(columns=["period_end", "period_type"], errors="ignore")
        sections.append((title, table))
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
    equity_valuation_basis: str = "live",
    max_live_holdings: int | None = None,
) -> dict[str, float | int | str | None]:
    if holdings.empty:
        return {
            "positions_total": 0,
            "resolved_positions": 0,
            "unresolved_positions": 0,
            "reported_value_usd": None,
            "resolved_reported_value_usd": None,
            "unresolved_reported_value_usd": None,
            "live_value_usd": None,
            "blended_value_usd": None,
            "selected_value_usd": None,
            "selected_basis": None,
            "live_pricing_limit": None,
            "latest_price_date": None,
            "coverage_ratio": None,
        }
    basis = normalize_public_equity_valuation_basis(equity_valuation_basis)
    aggregated = aggregate_13f_holdings(holdings)
    reported_value = aggregated["value_usd"].dropna().sum()
    if basis == "reported":
        return {
            "positions_total": int(len(aggregated)),
            "resolved_positions": 0,
            "unresolved_positions": int(len(aggregated)),
            "reported_value_usd": reported_value if pd.notna(reported_value) else None,
            "resolved_reported_value_usd": None,
            "unresolved_reported_value_usd": reported_value if pd.notna(reported_value) else None,
            "live_value_usd": None,
            "blended_value_usd": reported_value if pd.notna(reported_value) else None,
            "selected_value_usd": reported_value if pd.notna(reported_value) else None,
            "selected_basis": "reported_13f",
            "live_pricing_limit": None,
            "latest_price_date": None,
            "coverage_ratio": None,
        }
    enriched = _enriched_holdings_frame(
        aggregated,
        reference,
        yahoo_client=yahoo_client,
        enriched_holdings=enriched_holdings,
        max_live_holdings=max_live_holdings,
    )
    resolved = enriched[enriched["market_value_live_usd"].notna()].copy()
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
    latest_price_date = None
    if "latest_price_date" in enriched.columns:
        dates = [value for value in enriched["latest_price_date"].dropna().tolist() if value]
        if dates:
            latest_price_date = max(dates)
    return {
        "positions_total": int(len(enriched)),
        "resolved_positions": int(len(resolved)),
        "unresolved_positions": int(len(enriched) - len(resolved)),
        "reported_value_usd": reported_value if pd.notna(reported_value) else None,
        "resolved_reported_value_usd": resolved_reported_value if pd.notna(resolved_reported_value) else None,
        "unresolved_reported_value_usd": unresolved_reported_value if pd.notna(unresolved_reported_value) else None,
        "live_value_usd": live_value if pd.notna(live_value) else None,
        "blended_value_usd": blended_value if blended_value is not None and pd.notna(blended_value) else None,
        "selected_value_usd": blended_value if blended_value is not None and pd.notna(blended_value) else None,
        "selected_basis": "live_revalued_13f",
        "live_pricing_limit": max_live_holdings,
        "latest_price_date": latest_price_date,
        "coverage_ratio": coverage_ratio,
    }


def _enriched_holdings_frame(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    *,
    yahoo_client=None,
    price_change_window: str | None = None,
    enriched_holdings: pd.DataFrame | None = None,
    max_live_holdings: int | None = None,
) -> pd.DataFrame:
    if enriched_holdings is not None:
        return enriched_holdings.copy()
    aggregated = aggregate_13f_holdings(holdings)
    return enrich_holdings_with_market_prices(
        aggregated,
        reference,
        yahoo_client=yahoo_client,
        price_change_window=price_change_window,
        max_holdings=max_live_holdings,
    )


def normalize_public_equity_valuation_basis(value: str | None) -> str:
    normalized = str(value or "live").strip().lower()
    if normalized in {"current", "current_price", "market", "market_price"}:
        normalized = "live"
    if normalized not in PUBLIC_EQUITY_VALUATION_BASES:
        allowed = ", ".join(PUBLIC_EQUITY_VALUATION_BASES)
        raise ValueError(f"Unsupported public equity valuation basis '{value}'. Use one of: {allowed}")
    return normalized


def _extract_equity_securities_tax_basis(frame: pd.DataFrame) -> dict[str, float | None]:
    return {
        "cost_basis_usd": _first_report_value_for_label(frame, "Cost Basis"),
        "unrealized_gain_usd": _first_report_value_for_label(frame, "Net Unrealized Gains"),
        "fair_value_usd": _first_report_value_for_label(frame, "Fair Value"),
    }


def _extract_deferred_tax_context(frame: pd.DataFrame) -> dict[str, float | None]:
    return {
        "investment_deferred_tax_liability_usd": _first_report_value_for_label(
            frame,
            "Investments, including unrealized appreciation",
        ),
        "net_deferred_tax_liability_usd": _first_report_value_for_label(
            frame,
            "Net deferred income tax liability",
        ),
    }


def _extract_tax_reconciliation_rates(frame: pd.DataFrame) -> dict[str, float | None]:
    return {
        "state_local_rate_net_federal_benefit": _first_report_percent_for_label(
            frame,
            "State and local income taxes, net of U.S. federal effect, percentage",
        ),
        "latest_effective_tax_rate": _first_report_percent_for_label(
            frame,
            "Effective income tax rate percentage",
        ),
    }


def _first_report_value_for_label(frame: pd.DataFrame, label: str) -> float | None:
    if frame.empty:
        return None
    label_values = frame.iloc[:, 0].astype(str).str.strip()
    matches = frame[label_values == label]
    if matches.empty:
        return None
    for idx in range(1, len(frame.columns)):
        value = _parse_balance_sheet_value(matches.iloc[0, idx])
        if value is not None:
            return value
    return None


def _first_report_percent_for_label(frame: pd.DataFrame, label: str) -> float | None:
    if frame.empty:
        return None
    label_values = frame.iloc[:, 0].astype(str).str.strip()
    matches = frame[label_values == label]
    if matches.empty:
        return None
    for idx in range(1, len(frame.columns)):
        value = _parse_percent(matches.iloc[0, idx])
        if value is not None:
            return value
    return None


def _parse_percent(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace("\xa0", " ").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.replace("%", "").replace(",", "").replace("(", "").replace(")", "").strip()
    if cleaned in {"", "NaN", "nan"}:
        return None
    try:
        numeric = float(cleaned) / 100.0
    except ValueError:
        return None
    return -numeric if negative else numeric


def _public_equity_note(metrics: dict[str, object]) -> str:
    if metrics.get("selected_basis") == "reported_13f":
        return "Latest 13F reported market values from the filing"
    coverage = metrics.get("coverage_ratio")
    limit = metrics.get("live_pricing_limit")
    scope = "mapped holdings" if limit is None else f"top {limit} mapped holdings"
    if coverage is not None:
        return f"Current-price 13F estimate for {scope}; live price coverage {float(coverage) * 100:.1f}%"
    return f"Current-price 13F estimate for {scope}; reported values used where prices are unresolved"


def _latest_segments_table(
    filings: Sequence[BrkSegmentFiling],
    *,
    period: str = "annual",
) -> pd.DataFrame:
    if not filings:
        return pd.DataFrame()
    return build_top_level_operating_segments_table(filings[0].reports, period=period)


def _segment_pretax_earnings_total(segments: pd.DataFrame) -> float | None:
    if segments.empty or "earnings_before_income_taxes_usd" not in segments.columns:
        return None
    total = segments["earnings_before_income_taxes_usd"].dropna().sum()
    return float(total) if pd.notna(total) else None


def _metric_value(frame: pd.DataFrame, metric: str) -> float | None:
    if frame.empty or "metric" not in frame.columns or "value_usd" not in frame.columns:
        return None
    rows = frame[frame["metric"] == metric]
    if rows.empty:
        return None
    value = rows.iloc[0]["value_usd"]
    if value is None or pd.isna(value):
        return None
    return float(value)


def _metric_per_share(frame: pd.DataFrame, metric: str) -> float | None:
    if frame.empty or "metric" not in frame.columns or "per_brk_b_share_usd" not in frame.columns:
        return None
    rows = frame[frame["metric"] == metric]
    if rows.empty:
        return None
    value = rows.iloc[0]["per_brk_b_share_usd"]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)


def _metric_weight(frame: pd.DataFrame, metric: str) -> float | None:
    if frame.empty or "metric" not in frame.columns or "market_cap_weight" not in frame.columns:
        return None
    rows = frame[frame["metric"] == metric]
    if rows.empty:
        return None
    value = rows.iloc[0]["market_cap_weight"]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)


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


def _agg_by_cusip(agg: pd.DataFrame) -> dict:
    result = {}
    if agg.empty:
        return result
    for _, row in agg.iterrows():
        cusip = _none_if_nan(row.get("cusip"))
        if cusip and cusip not in result:
            result[cusip] = row
    return result


def _none_if_nan_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f


def _history_aggregate_for_filing(filing: Brk13FBundle) -> pd.DataFrame:
    aggregated = aggregate_13f_holdings(filing.holdings)
    if aggregated.empty:
        return aggregated
    return aggregated.sort_values(
        by=["value_usd", "issuer"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)


def _holding_history_key(row) -> tuple[str | None, str | None, str | None, str | None]:
    return (
        _none_if_nan(row.get("security_id")),
        _none_if_nan(row.get("issuer")),
        _none_if_nan(row.get("class_title")),
        _none_if_nan(row.get("cusip")),
    )


def _history_key_display_value(
    key: tuple[str | None, str | None, str | None, str | None],
    field: str,
) -> str | None:
    index_by_field = {
        "security_id": 0,
        "issuer": 1,
        "class_title": 2,
        "cusip": 3,
    }
    return key[index_by_field[field]]


def _difference(value, previous):
    if value is None or previous is None:
        return None
    if pd.isna(value) or pd.isna(previous):
        return None
    return float(value) - float(previous)


def _none_if_nan(value):
    if value is None:
        return None
    if pd.isna(value):
        return None
    return str(value)


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
    for metric, label in {
        **BRK_LIQUIDITY_REPORT_LABELS,
        **BRK_BALANCE_SHEET_CONTEXT_LABELS,
    }.items():
        matched = frame[labels.isin(_label_aliases(label))]
        if matched.empty:
            continue
        parsed_value = _parse_balance_sheet_value(matched.iloc[0, current_column_index])
        if parsed_value is None:
            continue
        values[metric] = parsed_value
    for metric, label in BRK_BALANCE_SHEET_CONTEXT_SUM_LABELS.items():
        matched = frame[labels.isin(_label_aliases(label))]
        if matched.empty:
            continue
        parsed_values = [
            parsed
            for parsed in (
                _parse_balance_sheet_value(value)
                for value in matched.iloc[:, current_column_index].tolist()
            )
            if parsed is not None
        ]
        if parsed_values:
            values[metric] = sum(parsed_values)
    return period_end, values


def _label_aliases(label: str) -> tuple[str, ...]:
    return BRK_REPORT_LABEL_ALIASES.get(label, (label,))


def _report_label_for_metric(metric: str) -> str:
    for labels in (
        BRK_LIQUIDITY_REPORT_LABELS,
        BRK_BALANCE_SHEET_CONTEXT_LABELS,
        BRK_BALANCE_SHEET_CONTEXT_SUM_LABELS,
    ):
        if metric in labels:
            return labels[metric]
    return metric


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
