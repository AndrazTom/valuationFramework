"""Normalize Yahoo Finance statement tables into repo-level metric tables."""

from __future__ import annotations

from typing import Sequence

import pandas as pd


YAHOO_STATEMENT_LABELS = {
    "income": {
        "revenue": ("Total Revenue",),
        "gross_profit": ("Gross Profit",),
        "operating_income": ("Operating Income", "EBIT"),
        "pretax_income": ("Pretax Income",),
        "net_income": (
            "Net Income Common Stockholders",
            "Net Income",
            "Net Income From Continuing Operation Net Minority Interest",
        ),
        "diluted_eps": ("Diluted EPS",),
        "diluted_shares": ("Diluted Average Shares", "Basic Average Shares"),
    },
    "balance": {
        "cash_and_equivalents": ("Cash And Cash Equivalents",),
        "short_term_investments": ("Cash Cash Equivalents And Short Term Investments", "Available For Sale Securities"),
        "current_assets": ("Current Assets",),
        "total_assets": ("Total Assets",),
        "current_liabilities": ("Current Liabilities",),
        "long_term_debt": ("Long Term Debt", "Total Debt"),
        "total_liabilities": ("Total Liabilities Net Minority Interest", "Total Liabilities"),
        "stockholders_equity": ("Stockholders Equity", "Total Equity Gross Minority Interest"),
    },
    "cashflow": {
        "operating_cash_flow": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
        "capex": ("Capital Expenditure",),
        "investing_cash_flow": ("Investing Cash Flow", "Cash Flow From Continuing Investing Activities"),
        "financing_cash_flow": ("Financing Cash Flow", "Cash Flow From Continuing Financing Activities"),
        "change_in_cash": ("Changes In Cash",),
    },
}

YAHOO_STATEMENT_UNITS = {
    "revenue": "USD",
    "gross_profit": "USD",
    "operating_income": "USD",
    "pretax_income": "USD",
    "net_income": "USD",
    "diluted_eps": "USD/shares",
    "diluted_shares": "shares",
    "cash_and_equivalents": "USD",
    "short_term_investments": "USD",
    "current_assets": "USD",
    "total_assets": "USD",
    "current_liabilities": "USD",
    "long_term_debt": "USD",
    "total_liabilities": "USD",
    "stockholders_equity": "USD",
    "operating_cash_flow": "USD",
    "capex": "USD",
    "investing_cash_flow": "USD",
    "financing_cash_flow": "USD",
    "change_in_cash": "USD",
}


def build_yahoo_statement_table(
    frame: pd.DataFrame,
    *,
    statement: str,
    period: str,
    currency: str = "USD",
    limit: int = 4,
    start_year: int | None = None,
    end_year: int | None = None,
    start_quarter: int | None = None,
    end_quarter: int | None = None,
) -> pd.DataFrame:
    """Return a repo-style statement table from a raw yfinance statement frame."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["metric", "unit"])

    transposed = frame.transpose().copy()
    transposed.index = pd.to_datetime(transposed.index)
    transposed = transposed.sort_index(ascending=False)

    periods = []
    for timestamp in transposed.index:
        period_info = _period_info(timestamp, period=period)
        if period_info is None:
            continue
        periods.append(period_info)

    periods = _filter_periods(
        periods,
        period=period,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )[: max(0, limit)]

    rows = []
    labels = YAHOO_STATEMENT_LABELS[statement]
    for metric, candidates in labels.items():
        row = {"metric": metric, "unit": _metric_unit(metric, currency=currency)}
        matched_any = False
        for period_info in periods:
            value = _resolve_yahoo_value(
                transposed.loc[period_info["timestamp"]],
                candidates=candidates,
            )
            row[period_info["label"]] = value
            matched_any = matched_any or not pd.isna(value)
        if matched_any:
            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=["metric", "unit", *[period_info["label"] for period_info in periods]])
    return pd.DataFrame(rows)


def build_yahoo_key_financials_table(
    *,
    income_frame: pd.DataFrame,
    balance_frame: pd.DataFrame,
    cashflow_frame: pd.DataFrame,
    currency: str = "USD",
) -> pd.DataFrame:
    """Return a latest-period key financials table from Yahoo annual statements."""
    annual_frames = {
        "income": build_yahoo_statement_table(
            income_frame,
            statement="income",
            period="annual",
            currency=currency,
            limit=1,
        ),
        "balance": build_yahoo_statement_table(
            balance_frame,
            statement="balance",
            period="annual",
            currency=currency,
            limit=1,
        ),
        "cashflow": build_yahoo_statement_table(
            cashflow_frame,
            statement="cashflow",
            period="annual",
            currency=currency,
            limit=1,
        ),
    }

    rows = []
    for frame in annual_frames.values():
        if frame.empty:
            continue
        value_columns = [column for column in frame.columns if column not in {"metric", "unit"}]
        if not value_columns:
            continue
        latest_column = value_columns[0]
        for _, row in frame.iterrows():
            rows.append(
                {
                    "metric": row["metric"],
                    "taxonomy": "yahoo",
                    "concept": row["metric"],
                    "unit": row["unit"],
                    "value": row[latest_column],
                    "end": latest_column,
                    "filed": None,
                    "form": None,
                    "frame": None,
                }
            )
    return pd.DataFrame(rows)


def _resolve_yahoo_value(row: pd.Series, *, candidates: Sequence[str]) -> float | None:
    for candidate in candidates:
        if candidate not in row.index:
            continue
        value = row[candidate]
        if pd.isna(value):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _metric_unit(metric: str, *, currency: str) -> str:
    if metric in {"diluted_eps"}:
        return f"{currency}/shares"
    if metric in {"diluted_shares"}:
        return "shares"
    return currency


def _period_info(timestamp: pd.Timestamp, *, period: str) -> dict | None:
    if period == "annual":
        return {
            "timestamp": timestamp,
            "label": f"FY {timestamp.year}",
            "year": timestamp.year,
        }
    quarter = ((timestamp.month - 1) // 3) + 1
    return {
        "timestamp": timestamp,
        "label": f"{timestamp.year} Q{quarter}",
        "year": timestamp.year,
        "quarter": quarter,
    }


def _filter_periods(
    periods: list[dict],
    *,
    period: str,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> list[dict]:
    filtered = []
    for period_info in periods:
        year = period_info["year"]
        quarter = period_info.get("quarter")
        if start_year is not None and year < start_year:
            continue
        if end_year is not None and year > end_year:
            continue
        if period == "quarterly" and start_year is not None and year == start_year and start_quarter is not None:
            if quarter is not None and quarter < start_quarter:
                continue
        if period == "quarterly" and end_year is not None and year == end_year and end_quarter is not None:
            if quarter is not None and quarter > end_quarter:
                continue
        filtered.append(period_info)
    return filtered
