"""Generic company tables."""

from __future__ import annotations

from datetime import date, datetime
from typing import Mapping

import pandas as pd

from valuation.company.statements import build_statement_table
from valuation.company.statements import STATEMENT_DEFINITIONS
from valuation.company.yahoo_statements import build_yahoo_key_financials_table
from valuation.company.yahoo_statements import build_yahoo_statement_table
from valuation.company.yahoo_statements import YAHOO_STATEMENT_LABELS
from valuation.company.service import CompanyResolution
from valuation.data.normalize.tables import CompanyFactQuery, company_facts_to_table

OVERVIEW_MARKET_METRICS = (
    ("last_price", "currency"),
    ("market_cap", "currency"),
    ("shares", "shares"),
)

OVERVIEW_FINANCIAL_METRICS = (
    "revenue",
    "net_income",
    "operating_cash_flow",
    "cash_and_equivalents",
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
)

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
    CompanyFactQuery(
        "stockholders_equity",
        (
            ("us-gaap", "StockholdersEquity"),
            ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        ),
    ),
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
        "operating_income",
        (("us-gaap", "OperatingIncomeLoss"),),
    ),
    CompanyFactQuery(
        "long_term_debt",
        (
            ("us-gaap", "LongTermDebtAndCapitalLeaseObligations"),
            ("us-gaap", "LongTermDebtAndFinanceLeaseObligations"),
            ("us-gaap", "LongTermDebtNoncurrent"),
            ("us-gaap", "LongTermDebt"),
        ),
    ),
    CompanyFactQuery(
        "depreciation_amortization",
        (
            ("us-gaap", "DepreciationDepletionAndAmortization"),
            ("us-gaap", "DepreciationAndAmortization"),
            ("us-gaap", "Depreciation"),
        ),
    ),
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

MARKET_SNAPSHOT_STALE_AFTER_DAYS = 7

OVERVIEW_STATEMENT_BY_METRIC = {
    "revenue": "income",
    "net_income": "income",
    "operating_cash_flow": "cashflow",
    "cash_and_equivalents": "balance",
    "total_assets": "balance",
    "total_liabilities": "balance",
    "stockholders_equity": "balance",
}

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
    """Return selected generic SEC facts for one company, with derived FCF and owner earnings rows."""
    table = company_facts_to_table(company_facts, COMMON_FACT_DEFINITIONS)
    return _append_derived_rows(table)


def _append_derived_rows(table: pd.DataFrame) -> pd.DataFrame:
    """Append EBITDA, free_cash_flow, and owner_earnings rows when inputs are present."""
    if table.empty:
        return table
    metric_values = {str(row["metric"]): _to_float(row.get("value")) for _, row in table.iterrows()}
    ocf = metric_values.get("operating_cash_flow")
    capex = metric_values.get("capex")
    net_income = metric_values.get("net_income")
    da = metric_values.get("depreciation_amortization")
    op_income = metric_values.get("operating_income")

    # Infer unit from operating_cash_flow or net_income
    def _unit_for(primary: str, fallback: str = "USD") -> str:
        for m in (primary, "net_income", "operating_cash_flow", "operating_income"):
            rows = table[table["metric"] == m]
            if not rows.empty:
                u = rows.iloc[0].get("unit")
                if u is not None:
                    return str(u)
        return fallback

    new_rows = []
    if op_income is not None and da is not None:
        new_rows.append({
            "metric": "ebitda",
            "taxonomy": "derived",
            "concept": "operating_income + depreciation_amortization",
            "unit": _unit_for("operating_income"),
            "value": op_income + da,
            "end": None,
            "filed": None,
            "form": None,
            "frame": None,
        })
    if ocf is not None and capex is not None:
        new_rows.append({
            "metric": "free_cash_flow",
            "taxonomy": "derived",
            "concept": "operating_cash_flow - capex",
            "unit": _unit_for("operating_cash_flow"),
            "value": ocf - capex,
            "end": None,
            "filed": None,
            "form": None,
            "frame": None,
        })
    if net_income is not None and da is not None and capex is not None:
        new_rows.append({
            "metric": "owner_earnings",
            "taxonomy": "derived",
            "concept": "net_income + depreciation_amortization - capex",
            "unit": _unit_for("net_income"),
            "value": net_income + da - capex,
            "end": None,
            "filed": None,
            "form": None,
            "frame": None,
        })
    if not new_rows:
        return table
    return pd.concat([table, pd.DataFrame(new_rows)], ignore_index=True)


def build_sec_overview_table(
    *,
    market_snapshot: Mapping[str, object],
    company_facts: Mapping[str, object],
    currency: str = "USD",
) -> pd.DataFrame:
    """Return a compact machine-friendly overview from market snapshot + SEC facts."""
    rows = _market_overview_rows(market_snapshot, currency=currency, source="yfinance")
    facts_table = company_facts_to_table(company_facts, COMMON_FACT_DEFINITIONS)
    fact_rows = {
        str(row["metric"]): row
        for row in facts_table.to_dict(orient="records")
    }
    latest_as_of_by_statement = _latest_as_of_by_statement(fact_rows)
    for metric in OVERVIEW_FINANCIAL_METRICS:
        fact_row = fact_rows.get(metric)
        if fact_row and _has_value(fact_row.get("value")):
            statement = OVERVIEW_STATEMENT_BY_METRIC.get(metric)
            as_of = fact_row.get("end")
            rows.append(
                {
                    "metric": metric,
                    "value": fact_row.get("value"),
                    "unit": fact_row.get("unit"),
                    "source": "sec",
                    "source_table": "companyfacts",
                    "statement": statement,
                    "period_type": _sec_period_type(fact_row.get("form")),
                    "as_of": as_of,
                    "status": "available",
                    "completeness": _completeness_for_as_of(
                        as_of=as_of,
                        latest_as_of=latest_as_of_by_statement.get(statement),
                    ),
                    "taxonomy": fact_row.get("taxonomy"),
                    "concept": fact_row.get("concept"),
                    "matched_label": None,
                    "form": fact_row.get("form"),
                    "filed": fact_row.get("filed"),
                    "reason": None,
                }
            )
            continue
        rows.append(
            {
                "metric": metric,
                "value": None,
                "unit": _overview_default_unit(metric, currency=currency),
                "source": "sec",
                "source_table": "companyfacts",
                "statement": OVERVIEW_STATEMENT_BY_METRIC.get(metric),
                "period_type": None,
                "as_of": None,
                "status": "unavailable",
                "completeness": "missing",
                "taxonomy": None,
                "concept": None,
                "matched_label": None,
                "form": None,
                "filed": None,
                "reason": _sec_metric_unavailable_reason(
                    metric,
                    company_facts=company_facts,
                ),
            }
        )
    return pd.DataFrame(rows)


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


def build_yahoo_overview_table(
    *,
    market_snapshot: Mapping[str, object],
    income_frame: pd.DataFrame,
    balance_frame: pd.DataFrame,
    cashflow_frame: pd.DataFrame,
    currency: str = "USD",
) -> pd.DataFrame:
    """Return a compact machine-friendly overview from market snapshot + Yahoo annual statements."""
    rows = _market_overview_rows(market_snapshot, currency=currency, source="yfinance")
    yahoo_rows = _build_yahoo_overview_financial_rows(
        income_frame=income_frame,
        balance_frame=balance_frame,
        cashflow_frame=cashflow_frame,
        currency=currency,
    )
    for metric in OVERVIEW_FINANCIAL_METRICS:
        financial_row = yahoo_rows.get(metric)
        if financial_row and _has_value(financial_row.get("value")):
            rows.append(financial_row)
            continue
        statement = OVERVIEW_STATEMENT_BY_METRIC.get(metric)
        frame = {
            "income": income_frame,
            "balance": balance_frame,
            "cashflow": cashflow_frame,
        }.get(statement, pd.DataFrame())
        if frame is None or frame.empty:
            reason = f"Yahoo returned no annual {statement} statement frame"
        else:
            reason = _yahoo_metric_unavailable_reason(
                metric=metric,
                statement=statement,
                frame=frame,
            )
        rows.append(
            {
                "metric": metric,
                "value": None,
                "unit": _overview_default_unit(metric, currency=currency),
                "source": "yahoo",
                "source_table": f"{statement}_statement" if statement else "yahoo_statement_frame",
                "statement": statement,
                "period_type": "annual",
                "as_of": None,
                "status": "unavailable",
                "completeness": "missing",
                "taxonomy": "yahoo",
                "concept": metric,
                "matched_label": None,
                "form": None,
                "filed": None,
                "reason": reason,
            }
        )
    return pd.DataFrame(rows)


def build_valuation_ratios_table(
    market_snapshot: Mapping[str, object],
    financials: Mapping[str, float | None],
    *,
    period_label: str | None = None,
) -> pd.DataFrame:
    """Return standard market valuation ratios from market snapshot + financial metric values.

    ``financials`` should map metric names (e.g. ``net_income``, ``revenue``,
    ``stockholders_equity``, ``operating_cash_flow``, ``capex``, ``long_term_debt``,
    ``operating_income``, ``depreciation_amortization``) to their latest annual values
    in the reporting currency.  Missing or zero denominators produce no row for that ratio.
    ``period_label`` is displayed in the ``as_of`` column when provided (e.g. ``"FY 2024"``).
    """
    shares = _to_float(market_snapshot.get("shares"))
    market_cap = _to_float(market_snapshot.get("market_cap"))
    if market_cap is None:
        price = _to_float(market_snapshot.get("last_price"))
        if price and shares:
            market_cap = price * shares

    net_income = _to_float(financials.get("net_income"))
    revenue = _to_float(financials.get("revenue"))
    equity = _to_float(financials.get("stockholders_equity"))
    ocf = _to_float(financials.get("operating_cash_flow"))
    capex = _to_float(financials.get("capex"))
    fcf = (ocf - capex) if ocf is not None and capex is not None else None
    cash = _to_float(financials.get("cash_and_equivalents"))
    long_term_debt = _to_float(financials.get("long_term_debt"))
    op_income = _to_float(financials.get("operating_income"))
    da = _to_float(financials.get("depreciation_amortization"))
    owner_earnings = (
        (net_income + da - capex)
        if net_income is not None and da is not None and capex is not None
        else None
    )

    ev: float | None = None
    if market_cap is not None and long_term_debt is not None and cash is not None:
        ev = market_cap + long_term_debt - cash
    ebitda: float | None = None
    if op_income is not None and da is not None:
        ebitda = op_income + da

    def _ratio(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator is None or denominator == 0.0:
            return None
        return numerator / denominator

    candidates = [
        ("pe_ratio", _ratio(market_cap, net_income), "Market cap / Net income (LTM)"),
        ("earnings_yield", _ratio(net_income, market_cap), "Net income / Market cap"),
        ("ps_ratio", _ratio(market_cap, revenue), "Market cap / Revenue (LTM)"),
        ("pb_ratio", _ratio(market_cap, equity), "Market cap / Stockholders equity"),
        ("price_to_fcf", _ratio(market_cap, fcf), "Market cap / (OCF - Capex)"),
        ("fcf_yield", _ratio(fcf, market_cap), "FCF / Market cap"),
        ("price_to_owner_earnings", _ratio(market_cap, owner_earnings), "Market cap / (Net income + D&A - Capex)"),
        ("owner_earnings_yield", _ratio(owner_earnings, market_cap), "Owner earnings / Market cap"),
        ("per_share_owner_earnings", _ratio(owner_earnings, shares), "Owner earnings / Shares outstanding"),
        ("ev_to_revenue", _ratio(ev, revenue), "EV / Revenue (EV = mkt cap + LT debt - cash)"),
        ("ev_to_ebitda", _ratio(ev, ebitda), "EV / EBITDA (EBITDA = op income + D&A)"),
    ]
    rows = [
        {"ratio": name, "value": value, "as_of": period_label, "note": note}
        for name, value, note in candidates
        if value is not None
    ]
    return pd.DataFrame(rows)


def extract_financials_from_company_facts(company_facts: Mapping[str, object]) -> dict[str, float | None]:
    """Extract a flat metric→value dict from SEC companyfacts for ratio calculation."""
    facts_table = company_facts_to_table(company_facts, COMMON_FACT_DEFINITIONS)
    return {
        str(row["metric"]): _to_float(row.get("value"))
        for row in facts_table.to_dict(orient="records")
    }


def extract_financials_ttm_from_company_facts(company_facts: Mapping[str, object]) -> tuple[dict[str, float | None], str | None]:
    """Extract TTM financials from SEC companyfacts by summing 4 quarters.

    Returns (financials_dict, ttm_label) where ttm_label is e.g. 'TTM' or '3Q TTM'
    if fewer than 4 quarters were available. Balance-sheet metrics come from the
    latest quarterly snapshot.

    Falls back to annual values when quarterly data is unavailable.
    """
    from valuation.company.statements import build_statement_table_ttm, build_statement_table

    result: dict[str, float | None] = {}

    # Income statement: TTM from quarterly reconstruction
    income_ttm = build_statement_table_ttm(company_facts, statement="income")
    _ttm_col = next((c for c in income_ttm.columns if c not in {"metric", "unit"}), None)
    ttm_label: str | None = _ttm_col  # e.g. "TTM" or "3Q TTM"
    if _ttm_col:
        for _, row in income_ttm.iterrows():
            result[str(row["metric"])] = _to_float(row.get(_ttm_col))

    # Cashflow: TTM
    cashflow_ttm = build_statement_table_ttm(company_facts, statement="cashflow")
    cf_col = next((c for c in cashflow_ttm.columns if c not in {"metric", "unit"}), None)
    if cf_col:
        for _, row in cashflow_ttm.iterrows():
            m = str(row["metric"])
            if m not in result:
                result[m] = _to_float(row.get(cf_col))

    # Balance sheet: latest quarterly snapshot (instant, TTM doesn't apply)
    balance_latest = build_statement_table(company_facts, statement="balance", period="quarterly", limit=1)
    bal_cols = [c for c in balance_latest.columns if c not in {"metric", "unit"}]
    if bal_cols:
        for _, row in balance_latest.iterrows():
            m = str(row["metric"])
            if m not in result:
                result[m] = _to_float(row.get(bal_cols[0]))

    # Fall back to annual for any metric that's still missing
    annual = extract_financials_from_company_facts(company_facts)
    for metric, value in annual.items():
        if metric not in result or result[metric] is None:
            result[metric] = value

    return result, ttm_label


def extract_period_label_from_company_facts(company_facts: Mapping[str, object]) -> str | None:
    """Return a human-readable label for the latest annual period in the company facts (e.g. 'FY 2024')."""
    facts_table = company_facts_to_table(company_facts, COMMON_FACT_DEFINITIONS)
    # Use net_income end date as the representative period marker
    for metric in ("net_income", "revenue", "operating_cash_flow"):
        rows = facts_table[facts_table["metric"] == metric]
        if rows.empty:
            continue
        end_val = rows.iloc[0].get("end")
        if end_val is None:
            continue
        try:
            end_str = str(end_val)
            year = end_str[:4]
            return f"FY {year}"
        except Exception:
            continue
    return None


def extract_financials_from_yahoo_frames(
    income_frame: pd.DataFrame,
    balance_frame: pd.DataFrame,
    cashflow_frame: pd.DataFrame,
) -> dict[str, float | None]:
    """Extract a flat metric→value dict from Yahoo annual statement frames for ratio calculation."""
    result: dict[str, float | None] = {}
    frames = {
        "income": income_frame,
        "balance": balance_frame,
        "cashflow": cashflow_frame,
    }
    for statement, frame in frames.items():
        if frame is None or frame.empty:
            continue
        transposed = frame.transpose().copy()
        transposed.index = pd.to_datetime(transposed.index, errors="coerce")
        transposed = transposed.sort_index(ascending=False)
        for metric, candidates in YAHOO_STATEMENT_LABELS[statement].items():
            if metric in result:
                continue
            for timestamp, row in transposed.iterrows():
                _, value = _resolve_yahoo_value_with_label(row, candidates=candidates)
                if value is not None:
                    result[metric] = value
                    break
    return result


def extract_financials_ttm_from_yahoo_frames(
    income_annual: pd.DataFrame,
    balance_annual: pd.DataFrame,
    cashflow_annual: pd.DataFrame,
    income_quarterly: pd.DataFrame,
    balance_quarterly: pd.DataFrame,
    cashflow_quarterly: pd.DataFrame,
    *,
    currency: str = "USD",
) -> tuple[dict[str, float | None], str | None]:
    """Extract TTM financials from Yahoo quarterly frames when available, else fall back to annual.

    Returns (financials_dict, ttm_label) where ttm_label is 'TTM', 'NQ TTM', or
    'FY YYYY' (from the annual frame) when quarterly data is unavailable.
    """
    from valuation.company.yahoo_statements import build_yahoo_statement_table_ttm

    result: dict[str, float | None] = {}
    ttm_label: str | None = None

    # Income: TTM from quarterly
    income_ttm_frame = build_yahoo_statement_table_ttm(income_quarterly, statement="income", currency=currency)
    income_ttm_col = next((c for c in income_ttm_frame.columns if c not in {"metric", "unit"}), None)
    if income_ttm_col and not income_ttm_frame.empty:
        ttm_label = income_ttm_col
        for _, row in income_ttm_frame.iterrows():
            result[str(row["metric"])] = _to_float(row.get(income_ttm_col))

    # Cashflow: TTM from quarterly
    cf_ttm_frame = build_yahoo_statement_table_ttm(cashflow_quarterly, statement="cashflow", currency=currency)
    cf_ttm_col = next((c for c in cf_ttm_frame.columns if c not in {"metric", "unit"}), None)
    if cf_ttm_col and not cf_ttm_frame.empty:
        if ttm_label is None:
            ttm_label = cf_ttm_col
        for _, row in cf_ttm_frame.iterrows():
            m = str(row["metric"])
            if m not in result:
                result[m] = _to_float(row.get(cf_ttm_col))

    # Balance: latest quarterly snapshot (instant items, TTM not meaningful)
    from valuation.company.yahoo_statements import build_yahoo_statement_table
    balance_q_frame = build_yahoo_statement_table(
        balance_quarterly, statement="balance", period="quarterly", currency=currency, limit=1
    )
    bal_col = next((c for c in balance_q_frame.columns if c not in {"metric", "unit"}), None)
    if bal_col:
        for _, row in balance_q_frame.iterrows():
            m = str(row["metric"])
            if m not in result:
                result[m] = _to_float(row.get(bal_col))

    # Fall back to annual for anything still missing
    annual = extract_financials_from_yahoo_frames(income_annual, balance_annual, cashflow_annual)
    for metric, value in annual.items():
        if metric not in result or result[metric] is None:
            result[metric] = value
    if ttm_label is None:
        ttm_label = _latest_yahoo_period_label(income_annual)

    return result, ttm_label


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
                expected_metrics=_expected_sec_metrics(statement),
                empty_reason="No matching concepts found in SEC companyfacts",
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
            "Yahoo returned no statement frame"
            if frame is None or frame.empty
            else "Statement frame present but no mapped metrics"
        )
        rows.append(
            _statement_availability_row(
                statement=statement,
                period=period,
                source="yahoo",
                table=table,
                expected_metrics=tuple(YAHOO_STATEMENT_LABELS[statement].keys()),
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
    expected_metrics: tuple[str, ...],
    empty_reason: str,
) -> dict[str, object]:
    period_columns = [column for column in table.columns if column not in {"metric", "unit"}]
    expected_metric_count = len(expected_metrics)
    if period_columns and not table.empty:
        present_metrics = tuple(str(metric) for metric in table["metric"].tolist())
        metric_count = int(len(table))
        coverage_ratio = (
            float(metric_count) / float(expected_metric_count)
            if expected_metric_count > 0
            else None
        )
        is_partial = expected_metric_count > 0 and metric_count < expected_metric_count
        return {
            "statement": statement,
            "period": period,
            "source": source,
            "status": "partial" if is_partial else "available",
            "period_count": len(period_columns),
            "metric_count": metric_count,
            "expected_metric_count": expected_metric_count,
            "coverage_ratio": coverage_ratio,
            "latest_period": period_columns[0],
            "reason": (
                _partial_statement_reason(
                    present_metrics=present_metrics,
                    expected_metrics=expected_metrics,
                )
                if is_partial
                else None
            ),
        }
    return {
        "statement": statement,
        "period": period,
        "source": source,
        "status": "unavailable",
        "period_count": 0,
        "metric_count": 0,
        "expected_metric_count": expected_metric_count,
        "coverage_ratio": 0.0 if expected_metric_count > 0 else None,
        "latest_period": None,
        "reason": empty_reason,
    }


def _expected_sec_metrics(statement: str) -> tuple[str, ...]:
    return tuple(
        str(query.metric)
        for query in STATEMENT_DEFINITIONS[statement]
        if not str(query.metric).startswith("_")
    )


def _sec_metric_unavailable_reason(
    metric: str,
    *,
    company_facts: Mapping[str, object],
) -> str:
    query = None
    for query in COMMON_FACT_DEFINITIONS:
        if query.metric == metric:
            break
    else:
        return "No matching concepts found in SEC companyfacts"

    facts = company_facts.get("facts", {})
    expected_concepts = [concept for _, concept in query.candidates]
    concepts_without_unit = []
    concepts_without_values = []
    concepts_found = []
    for taxonomy, concept in query.candidates:
        concept_payload = facts.get(taxonomy, {}).get(concept)
        if not concept_payload:
            continue
        concepts_found.append(concept)
        units = concept_payload.get("units", {})
        selected_unit = query.unit
        if selected_unit is None:
            selected_unit = next(iter(units.keys()), None)
        if selected_unit is None or selected_unit not in units:
            concepts_without_unit.append(concept)
            continue
        values = units.get(selected_unit, [])
        if not any(_has_value(entry.get("val")) for entry in values):
            concepts_without_values.append(concept)

    if not concepts_found:
        return f"No SEC companyfacts concepts found: {_compact_list(expected_concepts)}"
    if concepts_without_unit and len(concepts_without_unit) == len(concepts_found):
        return (
            f"SEC companyfacts concepts found but no {query.unit or 'usable'} units: "
            f"{_compact_list(concepts_without_unit)}"
        )
    if concepts_without_values and len(concepts_without_values) == len(concepts_found):
        return (
            f"SEC companyfacts concepts found but no usable {query.unit or 'unit'} values: "
            f"{_compact_list(concepts_without_values)}"
        )
    return f"No usable SEC companyfacts facts for: {_compact_list(concepts_found)}"


def _yahoo_metric_unavailable_reason(
    *,
    metric: str,
    statement: str | None,
    frame: pd.DataFrame,
) -> str:
    if statement is None:
        return "Metric unavailable in Yahoo annual statements"
    candidates = tuple(YAHOO_STATEMENT_LABELS.get(statement, {}).get(metric, ()))
    if not candidates:
        return "Metric unavailable in Yahoo annual statements"
    present_labels = [label for label in candidates if label in frame.index]
    if present_labels:
        return (
            f"Yahoo annual {statement} labels present but values blank: "
            f"{_compact_list(present_labels)}"
        )
    return (
        f"No Yahoo annual {statement} labels matched for {metric}; "
        f"tried {_compact_list(candidates)}"
    )


def _partial_statement_reason(
    *,
    present_metrics: tuple[str, ...],
    expected_metrics: tuple[str, ...],
) -> str:
    present = set(present_metrics)
    missing = [metric for metric in expected_metrics if metric not in present]
    return (
        f"Partial metric coverage: {len(present_metrics)}/{len(expected_metrics)} "
        f"metrics available; missing {_compact_list(missing)}"
    )


def _compact_list(values: list[str] | tuple[str, ...], *, limit: int = 4) -> str:
    text = ", ".join(values[:limit])
    if len(values) > limit:
        text = f"{text}, +{len(values) - limit} more"
    return text or "unknown"


def _market_overview_rows(
    market_snapshot: Mapping[str, object],
    *,
    currency: str,
    source: str,
) -> list[dict[str, object]]:
    rows = []
    as_of = market_snapshot.get("latest_price_date")
    completeness = _market_snapshot_completeness(as_of)
    for metric, unit_kind in OVERVIEW_MARKET_METRICS:
        value = market_snapshot.get(metric)
        matched_label = _market_snapshot_matched_label(market_snapshot, metric=metric)
        has_value = _has_value(value)
        rows.append(
            {
                "metric": metric,
                "value": value,
                "unit": currency if unit_kind == "currency" else "shares",
                "source": source,
                "source_table": "market_snapshot",
                "statement": None,
                "period_type": "market",
                "as_of": as_of,
                "status": "available" if has_value else "unavailable",
                "completeness": completeness if has_value else "missing",
                "taxonomy": source,
                "concept": metric,
                "matched_label": matched_label,
                "form": None,
                "filed": None,
                "reason": _market_snapshot_reason(
                    has_value=has_value,
                    as_of=as_of,
                    completeness=completeness,
                ),
            }
        )
    return rows


def _market_snapshot_completeness(as_of: object) -> str:
    quote_date = _parse_date(as_of)
    if quote_date is None:
        return "missing"
    age_days = (date.today() - quote_date).days
    if age_days > MARKET_SNAPSHOT_STALE_AFTER_DAYS:
        return "stale"
    return "current"


def _market_snapshot_reason(
    *,
    has_value: bool,
    as_of: object,
    completeness: str,
) -> str | None:
    if not has_value:
        return "Unavailable in market snapshot"
    if completeness == "missing":
        return "Market snapshot date unavailable"
    if completeness == "stale":
        return f"Market snapshot date older than {MARKET_SNAPSHOT_STALE_AFTER_DAYS} days: {as_of}"
    return None


def _parse_date(value: object) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _overview_default_unit(metric: str, *, currency: str) -> str:
    if metric == "shares":
        return "shares"
    return currency


def _market_snapshot_matched_label(
    market_snapshot: Mapping[str, object],
    *,
    metric: str,
) -> str:
    if metric == "market_cap":
        source = market_snapshot.get("market_cap_source")
        if source:
            return str(source)
    return metric


def _has_value(value: object) -> bool:
    return value is not None and not pd.isna(value)


def _latest_as_of_by_statement(
    fact_rows: Mapping[str, Mapping[str, object]],
) -> dict[str, str]:
    latest: dict[str, str] = {}
    for metric, row in fact_rows.items():
        statement = OVERVIEW_STATEMENT_BY_METRIC.get(metric)
        as_of = row.get("end")
        if statement is None or not _has_value(row.get("value")) or not as_of:
            continue
        as_of_text = str(as_of)
        current = latest.get(statement)
        if current is None or as_of_text > current:
            latest[statement] = as_of_text
    return latest


def _completeness_for_as_of(*, as_of: object, latest_as_of: str | None) -> str:
    if not as_of:
        return "missing"
    if latest_as_of is None:
        return "current"
    return "current" if str(as_of) == str(latest_as_of) else "stale"


def _sec_period_type(form: object) -> str | None:
    normalized = str(form or "").upper()
    if normalized in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}:
        return "annual"
    if normalized in {"10-Q", "10-Q/A", "6-K"}:
        return "quarterly"
    if normalized:
        return "reported"
    return None


def _build_yahoo_overview_financial_rows(
    *,
    income_frame: pd.DataFrame,
    balance_frame: pd.DataFrame,
    cashflow_frame: pd.DataFrame,
    currency: str,
) -> dict[str, dict[str, object]]:
    frames = {
        "income": income_frame,
        "balance": balance_frame,
        "cashflow": cashflow_frame,
    }
    latest_period_by_statement = {
        statement: _latest_yahoo_period_label(frame)
        for statement, frame in frames.items()
    }
    rows: dict[str, dict[str, object]] = {}
    for statement, frame in frames.items():
        if frame is None or frame.empty:
            continue
        transposed = frame.transpose().copy()
        transposed.index = pd.to_datetime(transposed.index)
        transposed = transposed.sort_index(ascending=False)
        for metric, candidates in YAHOO_STATEMENT_LABELS[statement].items():
            if metric not in OVERVIEW_FINANCIAL_METRICS:
                continue
            resolved = _resolve_yahoo_overview_metric(
                transposed=transposed,
                statement=statement,
                metric=metric,
                candidates=candidates,
                currency=currency,
                latest_period_label=latest_period_by_statement.get(statement),
            )
            if resolved is not None:
                rows[metric] = resolved
    return rows


def _latest_yahoo_period_label(frame: pd.DataFrame) -> str | None:
    if frame is None or frame.empty:
        return None
    timestamps = sorted(pd.to_datetime(frame.columns), reverse=True)
    if not timestamps:
        return None
    return f"FY {timestamps[0].year}"


def _resolve_yahoo_overview_metric(
    *,
    transposed: pd.DataFrame,
    statement: str,
    metric: str,
    candidates: tuple[str, ...],
    currency: str,
    latest_period_label: str | None,
) -> dict[str, object] | None:
    for timestamp, row in transposed.iterrows():
        matched_label, value = _resolve_yahoo_value_with_label(
            row,
            candidates=candidates,
        )
        if not _has_value(value):
            continue
        as_of = f"FY {timestamp.year}"
        return {
            "metric": metric,
            "value": value,
            "unit": _overview_default_unit(metric, currency=currency),
            "source": "yahoo",
            "source_table": f"{statement}_statement",
            "statement": statement,
            "period_type": "annual",
            "as_of": as_of,
            "status": "available",
            "completeness": _completeness_for_as_of(
                as_of=as_of,
                latest_as_of=latest_period_label,
            ),
            "taxonomy": "yahoo",
            "concept": metric,
            "matched_label": matched_label,
            "form": None,
            "filed": None,
            "reason": None,
        }
    return None


def _resolve_yahoo_value_with_label(
    row: pd.Series,
    *,
    candidates: tuple[str, ...],
) -> tuple[str | None, float | None]:
    for candidate in candidates:
        if candidate not in row.index:
            continue
        value = row[candidate]
        if pd.isna(value):
            continue
        try:
            return candidate, float(value)
        except (TypeError, ValueError):
            return candidate, None
    return None, None
