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
        "short_term_investments": (
            "Other Short Term Investments",
            "Short Term Investments",
            "Marketable Securities",
            "Available For Sale Securities",
        ),
        "current_assets": ("Current Assets",),
        "total_assets": ("Total Assets",),
        "current_liabilities": ("Current Liabilities",),
        "long_term_debt": (
            "Long Term Debt And Capital Lease Obligation",
            "Long Term Debt",
            "Long Term Capital Lease Obligation",
        ),
        "total_liabilities": ("Total Liabilities Net Minority Interest", "Total Liabilities"),
        "stockholders_equity": ("Stockholders Equity", "Total Equity Gross Minority Interest"),
    },
    "cashflow": {
        "operating_cash_flow": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
        "capex": ("Capital Expenditure",),
        "depreciation_amortization": (
            "Depreciation Amortization Depletion",
            "Depreciation And Amortization",
            "Depreciation",
        ),
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
    "depreciation_amortization": "USD",
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
    result = pd.DataFrame(rows)
    if statement == "cashflow":
        result = _add_yahoo_free_cash_flow_row(result)
    return result


def _add_yahoo_free_cash_flow_row(frame: pd.DataFrame) -> pd.DataFrame:
    """Append free_cash_flow = operating_cash_flow - capex for each period."""
    if frame.empty or "metric" not in frame.columns:
        return frame
    period_cols = [c for c in frame.columns if c not in {"metric", "unit"}]
    if not period_cols:
        return frame
    ocf_rows = frame[frame["metric"] == "operating_cash_flow"]
    capex_rows = frame[frame["metric"] == "capex"]
    if ocf_rows.empty or capex_rows.empty:
        return frame
    ocf_row = ocf_rows.iloc[0]
    capex_row = capex_rows.iloc[0]
    fcf_values: dict[str, object] = {}
    any_value = False
    for col in period_cols:
        ocf = ocf_row[col]
        capex = capex_row[col]
        if not pd.isna(ocf) and not pd.isna(capex):
            try:
                fcf_values[col] = float(ocf) - float(capex)
                any_value = True
            except (TypeError, ValueError):
                fcf_values[col] = None
        else:
            fcf_values[col] = None
    if not any_value:
        return frame
    unit = ocf_row.get("unit", "USD")
    new_row = {"metric": "free_cash_flow", "unit": unit, **fcf_values}
    return pd.concat([frame, pd.DataFrame([new_row])], ignore_index=True)


def build_yahoo_statement_table_ttm(
    frame: pd.DataFrame,
    *,
    statement: str,
    currency: str = "USD",
) -> pd.DataFrame:
    """Return a TTM view of a Yahoo statement.

    Balance sheet: returns the latest quarterly snapshot.
    Income / cashflow: sums the last 4 quarterly values per metric; share counts
    are averaged instead of summed.
    """
    _SHARE_METRICS = {"diluted_shares"}

    if statement == "balance":
        return build_yahoo_statement_table(
            frame,
            statement="balance",
            period="quarterly",
            currency=currency,
            limit=1,
        )

    quarterly = build_yahoo_statement_table(
        frame,
        statement=statement,
        period="quarterly",
        currency=currency,
        limit=4,
    )

    if quarterly.empty:
        return pd.DataFrame(columns=["metric", "unit", "TTM"])

    period_cols = [c for c in quarterly.columns if c not in {"metric", "unit"}]
    if not period_cols:
        return pd.DataFrame(columns=["metric", "unit", "TTM"])

    num_quarters = len(period_cols)
    ttm_label = "TTM" if num_quarters == 4 else f"{num_quarters}Q TTM"

    rows = []
    for _, row in quarterly.iterrows():
        metric = row["metric"]
        values = [row[c] for c in period_cols if not pd.isna(row[c])]
        if not values:
            ttm_val = None
        elif metric in _SHARE_METRICS:
            ttm_val = sum(float(v) for v in values) / len(values)
        else:
            ttm_val = sum(float(v) for v in values)
        rows.append({"metric": metric, "unit": row["unit"], ttm_label: ttm_val})

    result = pd.DataFrame(rows, columns=["metric", "unit", ttm_label])
    # Drop rows that ended up with no TTM value
    return result[result[ttm_label].notna()].reset_index(drop=True)


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
    result = pd.DataFrame(rows)
    return _append_yahoo_owner_earnings_row(result)


def _append_yahoo_owner_earnings_row(table: pd.DataFrame) -> pd.DataFrame:
    """Append free_cash_flow and owner_earnings derived rows when inputs are present."""
    if table.empty or "metric" not in table.columns:
        return table
    metric_values: dict[str, float | None] = {}
    metric_meta: dict[str, dict] = {}
    for _, row in table.iterrows():
        metric = str(row["metric"])
        val = row.get("value")
        try:
            metric_values[metric] = float(val) if val is not None and not pd.isna(val) else None
        except (TypeError, ValueError):
            metric_values[metric] = None
        metric_meta[metric] = {"unit": row.get("unit", "USD"), "end": row.get("end")}

    def _unit(primary: str) -> str:
        for m in (primary, "net_income", "operating_cash_flow"):
            meta = metric_meta.get(m)
            if meta and meta.get("unit"):
                return str(meta["unit"])
        return "USD"

    def _end(primary: str) -> str | None:
        meta = metric_meta.get(primary)
        return str(meta["end"]) if meta and meta.get("end") is not None else None

    ocf = metric_values.get("operating_cash_flow")
    capex = metric_values.get("capex")
    net_income = metric_values.get("net_income")
    da = metric_values.get("depreciation_amortization")

    new_rows = []
    if ocf is not None and capex is not None:
        new_rows.append({
            "metric": "free_cash_flow",
            "taxonomy": "derived",
            "concept": "operating_cash_flow - capex",
            "unit": _unit("operating_cash_flow"),
            "value": ocf - capex,
            "end": _end("operating_cash_flow"),
            "filed": None,
            "form": None,
            "frame": None,
        })
    if net_income is not None and da is not None and capex is not None:
        new_rows.append({
            "metric": "owner_earnings",
            "taxonomy": "derived",
            "concept": "net_income + depreciation_amortization - capex",
            "unit": _unit("net_income"),
            "value": net_income + da - capex,
            "end": _end("net_income"),
            "filed": None,
            "form": None,
            "frame": None,
        })
    if not new_rows:
        return table
    return pd.concat([table, pd.DataFrame(new_rows)], ignore_index=True)


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
