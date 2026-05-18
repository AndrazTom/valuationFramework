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
        "depreciation_amortization",
        (
            ("us-gaap", "DepreciationDepletionAndAmortization"),
            ("us-gaap", "DepreciationAndAmortization"),
        ),
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
    frame = _raw_statement_frame(
        company_facts,
        statement=statement,
        period=period,
        limit=limit,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    frame = _drop_helper_rows(frame)
    if statement == "cashflow":
        frame = _add_free_cash_flow_row(frame)
    return _drop_all_missing_rows(frame)


def build_statement_table_ttm(
    company_facts: dict,
    *,
    statement: str,
) -> pd.DataFrame:
    """Return a TTM view of a statement.

    Balance sheet: returns the latest quarterly snapshot (TTM is not meaningful
    for instant-type items).
    Income / cashflow: sums the last 4 quarterly values per metric; share counts
    are averaged instead of summed.
    """
    if statement == "balance":
        return build_statement_table(company_facts, statement="balance", period="quarterly", limit=1)

    quarterly = _raw_statement_frame(company_facts, statement=statement, period="quarterly", limit=4)
    quarterly = _drop_helper_rows(quarterly)
    if statement == "cashflow":
        quarterly = _add_free_cash_flow_row(quarterly)

    period_cols = [c for c in quarterly.columns if c not in {"metric", "unit"}]
    if not period_cols or quarterly.empty:
        return _drop_all_missing_rows(quarterly)

    _SHARE_METRICS = {"diluted_shares", "_basic_shares"}
    num_quarters = len(period_cols)
    # Label the column to reflect partial coverage when fewer than 4 quarters are available
    ttm_label = "TTM" if num_quarters == 4 else f"{num_quarters}Q TTM"

    rows = []
    for _, row in quarterly.iterrows():
        metric = row["metric"]
        values = [row[c] for c in period_cols if not pd.isna(row[c])]
        if not values:
            ttm_val = None
        elif metric in _SHARE_METRICS:
            ttm_val = sum(values) / len(values)
        else:
            ttm_val = sum(float(v) for v in values)
        rows.append({"metric": metric, "unit": row["unit"], ttm_label: ttm_val})

    result = pd.DataFrame(rows, columns=["metric", "unit", ttm_label])
    return _drop_all_missing_rows(result)


def build_statement_diagnostics_table(
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
    """Return availability diagnostics for expected statement rows."""
    definitions = STATEMENT_DEFINITIONS[statement]
    selected_frame = _raw_statement_frame(
        company_facts,
        statement=statement,
        period=period,
        limit=limit,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    all_period_frame = _raw_statement_frame(
        company_facts,
        statement=statement,
        period=period,
        limit=99,
    )
    rows = []
    for query in definitions:
        if query.metric.startswith("_"):
            continue
        selected_row = _metric_row(selected_frame, query.metric)
        all_period_row = _metric_row(all_period_frame, query.metric)
        selected_periods = _period_columns(selected_frame)
        all_periods = _period_columns(all_period_frame)
        status = "available" if _row_has_value(selected_row, selected_periods) else "missing"
        latest_usable_period = _latest_value_period(all_period_row, all_periods)
        rows.append(
            {
                "metric": query.metric,
                "status": status,
                "requested_unit": query.unit,
                "latest_usable_period": latest_usable_period,
                "diagnostic": _diagnostic_reason(
                    company_facts,
                    query,
                    period=period,
                    status=status,
                    latest_usable_period=latest_usable_period,
                ),
            }
        )
    return pd.DataFrame(rows)


def _raw_statement_frame(
    company_facts: dict,
    *,
    statement: str,
    period: str,
    limit: int,
    start_year: int | None = None,
    end_year: int | None = None,
    start_quarter: int | None = None,
    end_quarter: int | None = None,
) -> pd.DataFrame:
    frame = company_facts_to_statement_table(
        company_facts,
        STATEMENT_DEFINITIONS[statement],
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


def _metric_row(frame: pd.DataFrame, metric: str) -> pd.Series | None:
    if frame.empty or "metric" not in frame.columns:
        return None
    rows = frame[frame["metric"] == metric]
    if rows.empty:
        return None
    return rows.iloc[0]


def _period_columns(frame: pd.DataFrame) -> list[str]:
    return [str(column) for column in frame.columns if column not in {"metric", "unit"}]


def _row_has_value(row: pd.Series | None, period_columns: list[str]) -> bool:
    if row is None:
        return False
    return any(not pd.isna(row[column]) for column in period_columns)


def _latest_value_period(row: pd.Series | None, period_columns: list[str]) -> str | None:
    if row is None:
        return None
    for column in period_columns:
        if not pd.isna(row[column]):
            return column
    return None


def _diagnostic_reason(
    company_facts: dict,
    query: CompanyFactQuery,
    *,
    period: str,
    status: str,
    latest_usable_period: str | None,
) -> str:
    if status == "available":
        return "available in selected periods"
    state = _company_fact_query_state(company_facts, query)
    if state["status"] == "absent":
        return "concept not present in SEC companyfacts"
    if state["status"] == "unit_missing":
        return f"requested unit missing; available units: {state['available_units']}"
    if state["status"] == "empty_unit":
        return "requested unit present but contains no fact entries"
    if latest_usable_period is not None:
        return f"latest usable {period} period is {latest_usable_period}, outside selected output"
    return f"concept present but no usable {period} periods"


def _company_fact_query_state(company_facts: dict, query: CompanyFactQuery) -> dict[str, str]:
    facts = company_facts.get("facts", {})
    concept_seen = False
    requested_unit_seen = False
    available_units: list[str] = []
    for taxonomy, concept in query.candidates:
        units = facts.get(taxonomy, {}).get(concept, {}).get("units", {})
        if not units:
            continue
        concept_seen = True
        available_units.extend(str(unit) for unit in units)
        selected_unit = query.unit or next(iter(units.keys()), None)
        if selected_unit is None or selected_unit not in units:
            continue
        requested_unit_seen = True
        if units.get(selected_unit):
            return {"status": "present", "available_units": ", ".join(sorted(set(available_units)))}
    if requested_unit_seen:
        return {"status": "empty_unit", "available_units": ", ".join(sorted(set(available_units)))}
    if concept_seen:
        return {"status": "unit_missing", "available_units": ", ".join(sorted(set(available_units)))}
    return {"status": "absent", "available_units": ""}


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


def _add_free_cash_flow_row(frame: pd.DataFrame) -> pd.DataFrame:
    """Append free_cash_flow = operating_cash_flow - capex for periods where both are present.

    Capex is PaymentsToAcquirePropertyPlantAndEquipment, reported as a positive outflow,
    so FCF = operating_cash_flow - capex.
    """
    if frame.empty or "metric" not in frame.columns:
        return frame
    period_columns = [col for col in frame.columns if col not in {"metric", "unit"}]
    if not period_columns:
        return frame
    ocf_rows = frame[frame["metric"] == "operating_cash_flow"]
    capex_rows = frame[frame["metric"] == "capex"]
    if ocf_rows.empty or capex_rows.empty:
        return frame
    ocf_row = ocf_rows.iloc[0]
    capex_row = capex_rows.iloc[0]
    fcf_values: dict[str, object] = {}
    any_value = False
    for col in period_columns:
        ocf = ocf_row[col]
        capex = capex_row[col]
        if _is_positive_number(ocf) and _is_positive_number(capex):
            fcf_values[col] = float(ocf) - float(capex)
            any_value = True
        else:
            fcf_values[col] = None
    if not any_value:
        return frame
    unit = ocf_row.get("unit", "USD")
    new_row = {"metric": "free_cash_flow", "unit": unit, **fcf_values}
    return pd.concat([frame, pd.DataFrame([new_row])], ignore_index=True)


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
