"""Generic company tables."""

from __future__ import annotations

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

STATEMENT_AVAILABILITY_REQUESTS = (
    ("income", "annual"),
    ("income", "quarterly"),
    ("balance", "annual"),
    ("balance", "quarterly"),
    ("cashflow", "annual"),
    ("cashflow", "quarterly"),
)

OVERVIEW_STATEMENT_BY_METRIC = {
    "revenue": "income",
    "net_income": "income",
    "operating_cash_flow": "cashflow",
    "cash_and_equivalents": "balance",
    "total_assets": "balance",
    "total_liabilities": "balance",
    "stockholders_equity": "balance",
}

EXPECTED_VISIBLE_SEC_METRIC_COUNTS = {
    statement: len(
        [
            query.metric
            for query in definitions
            if not str(query.metric).startswith("_")
        ]
    )
    for statement, definitions in STATEMENT_DEFINITIONS.items()
}

EXPECTED_YAHOO_METRIC_COUNTS = {
    statement: len(metrics)
    for statement, metrics in YAHOO_STATEMENT_LABELS.items()
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
    """Return selected generic SEC facts for one company."""
    return company_facts_to_table(company_facts, COMMON_FACT_DEFINITIONS)


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
                "reason": "No matching concepts found in SEC companyfacts",
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
            reason = "Metric unavailable in Yahoo annual statements"
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
                expected_metric_count=EXPECTED_VISIBLE_SEC_METRIC_COUNTS[statement],
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
                expected_metric_count=EXPECTED_YAHOO_METRIC_COUNTS[statement],
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
    expected_metric_count: int,
    empty_reason: str,
) -> dict[str, object]:
    period_columns = [column for column in table.columns if column not in {"metric", "unit"}]
    if period_columns and not table.empty:
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
            "reason": "Statement available with partial metric coverage" if is_partial else None,
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


def _market_overview_rows(
    market_snapshot: Mapping[str, object],
    *,
    currency: str,
    source: str,
) -> list[dict[str, object]]:
    rows = []
    as_of = market_snapshot.get("latest_price_date")
    for metric, unit_kind in OVERVIEW_MARKET_METRICS:
        value = market_snapshot.get(metric)
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
                "status": "available" if _has_value(value) else "unavailable",
                "completeness": "current" if _has_value(value) else "missing",
                "taxonomy": None,
                "concept": None,
                "matched_label": None,
                "form": None,
                "filed": None,
                "reason": None if _has_value(value) else "Unavailable in market snapshot",
            }
        )
    return rows


def _overview_default_unit(metric: str, *, currency: str) -> str:
    if metric == "shares":
        return "shares"
    return currency


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
