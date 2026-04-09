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
    CompanyFactQuery("net_income", (("us-gaap", "NetIncomeLoss"),)),
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
            ("us-gaap", "LongTermDebtAndFinanceLeaseObligations"),
            ("us-gaap", "LongTermDebtNoncurrent"),
            ("us-gaap", "LongTermDebt"),
        ),
    ),
    CompanyFactQuery("total_liabilities", (("us-gaap", "Liabilities"),)),
    CompanyFactQuery("stockholders_equity", (("us-gaap", "StockholdersEquity"),)),
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
    return frame


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
    if net_income_index is None or diluted_eps_index is None or diluted_shares_index is None:
        return filled

    for column in period_columns:
        net_income = filled.at[net_income_index, column]
        diluted_eps = filled.at[diluted_eps_index, column]
        diluted_shares = filled.at[diluted_shares_index, column]

        if pd.isna(diluted_eps) and _is_positive_number(net_income) and _is_positive_number(diluted_shares):
            filled.at[diluted_eps_index, column] = float(net_income) / float(diluted_shares)
            diluted_eps = filled.at[diluted_eps_index, column]

        if pd.isna(diluted_shares) and _is_positive_number(net_income) and _is_positive_number(diluted_eps):
            filled.at[diluted_shares_index, column] = float(net_income) / float(diluted_eps)

    return filled


def _is_positive_number(value) -> bool:
    return value is not None and not pd.isna(value) and float(value) > 0
