"""Berkshire-only table shaping."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

import pandas as pd

from valuation.brk.service import BrkLiquidityFiling, BrkSegmentFiling
from valuation.brk.service import BRK_A_TICKER, BRK_A_TO_B_CONVERSION, BRK_B_TICKER
from valuation.brk.segments import build_top_level_operating_segments_table
from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_table
from valuation.brk.holdings import aggregate_13f_holdings
from valuation.notation import MILLION
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
    return combined.sort_values(
        by=["filing_date", "period_end", "revenues_usd"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)


def _sum_defined(*values):
    defined = [value for value in values if value is not None and pd.notna(value)]
    if not defined:
        return None
    return sum(defined)


def _extract_liquidity_values(frame: pd.DataFrame) -> tuple[str | None, dict[str, float]]:
    if frame.empty:
        return None, {}
    labels = frame.iloc[:, 0].astype(str).str.strip()
    current_column = _latest_date_column(frame.columns)
    if current_column is None:
        return None, {}
    period_end = _parse_report_date(str(current_column))
    if period_end is None:
        return None, {}
    values = {}
    for metric, label in BRK_LIQUIDITY_REPORT_LABELS.items():
        matched = frame[labels == label]
        if matched.empty:
            continue
        parsed_value = _parse_balance_sheet_value(matched.iloc[0][current_column])
        if parsed_value is None:
            continue
        values[metric] = parsed_value
    return period_end, values


def _latest_date_column(columns) -> object | None:
    dated_columns = []
    for column in columns:
        parsed = _parse_report_date(str(column))
        if parsed is not None:
            dated_columns.append((parsed, column))
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
