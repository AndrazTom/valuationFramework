"""Generic financial statement definitions and table builders."""

from __future__ import annotations

import pandas as pd

from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_statement_table

INCOME_STATEMENT_DEFINITIONS = (
    CompanyFactQuery(
        "revenue",
        (
            ("us-gaap", "Revenues"),
            ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            ("us-gaap", "RevenuesNetOfInterestExpense"),
            ("us-gaap", "InterestIncomeOperating"),
            ("us-gaap", "InterestIncomeExpenseNet"),
            ("us-gaap", "NoninterestIncome"),
        ),
    ),
    CompanyFactQuery("gross_profit", (("us-gaap", "GrossProfit"),)),
    CompanyFactQuery("operating_income", (("us-gaap", "OperatingIncomeLoss"),)),
    CompanyFactQuery(
        "pretax_income",
        (
            ("us-gaap", "IncomeBeforeTaxExpenseBenefit"),
            (
                "us-gaap",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            ),
            (
                "us-gaap",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
            ),
        ),
    ),
    CompanyFactQuery(
        "net_income",
        (
            ("us-gaap", "NetIncomeLoss"),
            ("us-gaap", "NetIncomeLossAvailableToCommonStockholdersDiluted"),
            ("us-gaap", "NetIncomeLossAvailableToCommonStockholdersBasic"),
            ("us-gaap", "ProfitLoss"),
        ),
    ),
    CompanyFactQuery(
        "diluted_eps",
        (("us-gaap", "EarningsPerShareDiluted"),),
        unit="USD/shares",
        quarterly_value_kind="direct",
    ),
    CompanyFactQuery(
        "diluted_shares",
        (("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding"),),
        unit="shares",
        quarterly_value_kind="direct_or_annual",
    ),
    CompanyFactQuery(
        "_basic_eps",
        (("us-gaap", "EarningsPerShareBasic"),),
        unit="USD/shares",
        quarterly_value_kind="direct",
    ),
    CompanyFactQuery(
        "_basic_shares",
        (("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic"),),
        unit="shares",
        quarterly_value_kind="direct_or_annual",
    ),
)

BALANCE_SHEET_DEFINITIONS = (
    CompanyFactQuery(
        "cash_and_equivalents",
        (
            ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
            ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
        ),
    ),
    CompanyFactQuery(
        "short_term_investments",
        (
            ("us-gaap", "AvailableForSaleSecuritiesCurrent"),
            ("us-gaap", "MarketableSecuritiesCurrent"),
            ("us-gaap", "ShortTermInvestments"),
        ),
    ),
    CompanyFactQuery("current_assets", (("us-gaap", "AssetsCurrent"),)),
    CompanyFactQuery("total_assets", (("us-gaap", "Assets"),)),
    CompanyFactQuery("current_liabilities", (("us-gaap", "LiabilitiesCurrent"),)),
    CompanyFactQuery(
        "long_term_debt",
        (
            ("us-gaap", "LongTermDebtAndCapitalLeaseObligations"),
            ("us-gaap", "LongTermDebtAndFinanceLeaseObligations"),
            ("us-gaap", "LongTermDebtNoncurrent"),
            ("us-gaap", "LongTermDebt"),
        ),
    ),
    CompanyFactQuery("total_liabilities", (("us-gaap", "Liabilities"),)),
    CompanyFactQuery(
        "stockholders_equity",
        (
            ("us-gaap", "StockholdersEquity"),
            ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        ),
    ),
)

CASH_FLOW_DEFINITIONS = (
    CompanyFactQuery(
        "operating_cash_flow",
        (("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),),
    ),
    CompanyFactQuery(
        "capex",
        (("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),),
    ),
    CompanyFactQuery(
        "investing_cash_flow",
        (("us-gaap", "NetCashProvidedByUsedInInvestingActivities"),),
    ),
    CompanyFactQuery(
        "financing_cash_flow",
        (("us-gaap", "NetCashProvidedByUsedInFinancingActivities"),),
    ),
    CompanyFactQuery(
        "change_in_cash",
        (
            (
                "us-gaap",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            ),
            ("us-gaap", "CashAndCashEquivalentsPeriodIncreaseDecrease"),
        ),
    ),
)

STATEMENT_DEFINITIONS = {
    "income": INCOME_STATEMENT_DEFINITIONS,
    "balance": BALANCE_SHEET_DEFINITIONS,
    "cashflow": CASH_FLOW_DEFINITIONS,
}

STATEMENT_VALUE_KINDS = {
    "income": "duration",
    "balance": "instant",
    "cashflow": "duration",
}


def build_statement_table(
    company_facts: dict,
    *,
    statement: str,
    period: str,
    limit: int = 4,
    start_year: int | None = None,
    end_year: int | None = None,
    start_quarter: int | None = None,
    end_quarter: int | None = None,
) -> pd.DataFrame:
    """Return one generic statement table from SEC companyfacts."""
    definitions = STATEMENT_DEFINITIONS[statement]
    frame = company_facts_to_statement_table(
        company_facts,
        definitions,
        period=period,
        value_kind=STATEMENT_VALUE_KINDS[statement],
        limit=limit,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    if statement == "income" and period == "quarterly":
        frame = _fill_income_quarterly_gaps(frame)
    frame = _drop_helper_rows(frame)
    return _drop_all_missing_rows(frame)


def _fill_income_quarterly_gaps(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    period_columns = [column for column in frame.columns if column not in {"metric", "unit"}]
    if not period_columns:
        return frame

    filled = frame.copy()
    metric_index = {row["metric"]: index for index, row in filled.iterrows()}
    net_income_index = metric_index.get("net_income")
    diluted_eps_index = metric_index.get("diluted_eps")
    diluted_shares_index = metric_index.get("diluted_shares")
    basic_eps_index = metric_index.get("_basic_eps")
    basic_shares_index = metric_index.get("_basic_shares")
    if net_income_index is None or diluted_eps_index is None or diluted_shares_index is None:
        return filled

    use_basic_share_fallback = _can_use_basic_share_fallback(
        filled,
        period_columns,
        diluted_eps_index=diluted_eps_index,
        basic_eps_index=basic_eps_index,
    )

    for column in period_columns:
        net_income = filled.at[net_income_index, column]
        diluted_eps = filled.at[diluted_eps_index, column]
        diluted_shares = filled.at[diluted_shares_index, column]

        if (
            pd.isna(diluted_shares)
            and use_basic_share_fallback
            and basic_shares_index is not None
        ):
            basic_shares = filled.at[basic_shares_index, column]
            if _is_positive_number(basic_shares):
                filled.at[diluted_shares_index, column] = float(basic_shares)
                diluted_shares = filled.at[diluted_shares_index, column]

        if pd.isna(diluted_eps) and _is_positive_number(net_income) and _is_positive_number(diluted_shares):
            filled.at[diluted_eps_index, column] = float(net_income) / float(diluted_shares)
            diluted_eps = filled.at[diluted_eps_index, column]

        if pd.isna(diluted_shares) and _is_positive_number(net_income) and _is_positive_number(diluted_eps):
            filled.at[diluted_shares_index, column] = float(net_income) / float(diluted_eps)

    return filled


def _is_positive_number(value) -> bool:
    return value is not None and not pd.isna(value) and float(value) > 0


def _drop_all_missing_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    period_columns = [column for column in frame.columns if column not in {"metric", "unit"}]
    if not period_columns:
        return frame

    kept_rows = []
    for _, row in frame.iterrows():
        if any(not pd.isna(row[column]) for column in period_columns):
            kept_rows.append(row.to_dict())

    if not kept_rows:
        return frame.iloc[0:0].copy()

    return pd.DataFrame(kept_rows, columns=frame.columns)


def _drop_helper_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "metric" not in frame.columns:
        return frame
    return frame[~frame["metric"].astype(str).str.startswith("_")].reset_index(drop=True)


def _can_use_basic_share_fallback(
    frame: pd.DataFrame,
    period_columns: list[str],
    *,
    diluted_eps_index: int | None,
    basic_eps_index: int | None,
) -> bool:
    if diluted_eps_index is None or basic_eps_index is None:
        return False

    observed_matches = 0
    for column in period_columns:
        diluted_eps = frame.at[diluted_eps_index, column]
        basic_eps = frame.at[basic_eps_index, column]
        if pd.isna(diluted_eps) or pd.isna(basic_eps):
            continue
        if abs(float(diluted_eps) - float(basic_eps)) > 1e-9:
            return False
        observed_matches += 1

    return observed_matches > 0
