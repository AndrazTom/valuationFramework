"""Security price enrichment helpers."""

from __future__ import annotations

from typing import Mapping, Optional

import pandas as pd

from valuation.data.providers.yahoo import YahooFinanceClient

PRICE_CHANGE_WINDOWS = ("1D", "5D", "1M", "3M", "YTD", "1Y", "5Y", "ALL")


def fetch_price_change_snapshot(
    ticker: str,
    *,
    price_change_window: str,
    yahoo_client: Optional[YahooFinanceClient] = None,
) -> dict[str, object]:
    """Return a current price snapshot augmented with one normalized change window."""
    normalized_window = normalize_price_change_window(price_change_window)
    yahoo = yahoo_client or YahooFinanceClient()
    snapshot = _safe_fetch_price_snapshot(yahoo, ticker)
    history = _safe_fetch_history(
        yahoo,
        ticker,
        period=_history_period_for_change_window(normalized_window),
    )
    price_change_pct = _compute_price_change_pct(
        snapshots_by_ticker={ticker: snapshot},
        histories_by_ticker={ticker: history},
        ticker=ticker,
        window=normalized_window,
    )
    return {
        **snapshot,
        "ticker": str(snapshot.get("ticker") or ticker).upper(),
        "price_change_window": normalized_window,
        "price_change_pct": price_change_pct,
    }


def enrich_holdings_with_market_prices(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    yahoo_client: Optional[YahooFinanceClient] = None,
    price_change_window: str | None = None,
) -> pd.DataFrame:
    """Attach current price snapshots to holdings when a market symbol is known."""
    if holdings.empty:
        return holdings.copy()

    enriched = holdings.copy()
    reference_columns = ["security_id", "ticker", "exchange"]
    available_reference = reference.reindex(columns=reference_columns).drop_duplicates(
        subset=["security_id"],
        keep="first",
    )
    enriched = enriched.merge(available_reference, on="security_id", how="left")

    yahoo = yahoo_client or YahooFinanceClient()
    normalized_window = normalize_price_change_window(price_change_window)
    snapshots_by_ticker = {
        ticker: _safe_fetch_price_snapshot(yahoo, ticker)
        for ticker in sorted(set(enriched["ticker"].dropna()))
    }
    histories_by_ticker = {}
    if normalized_window is not None:
        histories_by_ticker = {
            ticker: _safe_fetch_history(
                yahoo,
                ticker,
                period=_history_period_for_change_window(normalized_window),
            )
            for ticker in sorted(set(enriched["ticker"].dropna()))
        }

    enriched["last_price"] = enriched["ticker"].map(
        lambda ticker: _snapshot_value(snapshots_by_ticker, ticker, "last_price")
    )
    enriched["previous_close"] = enriched["ticker"].map(
        lambda ticker: _snapshot_value(snapshots_by_ticker, ticker, "previous_close")
    )
    enriched["latest_price_date"] = enriched["ticker"].map(
        lambda ticker: _snapshot_value(snapshots_by_ticker, ticker, "latest_price_date")
    )
    enriched["price_source"] = enriched["ticker"].map(
        lambda ticker: _snapshot_value(snapshots_by_ticker, ticker, "source")
    )
    enriched["market_value_live_usd"] = enriched.apply(
        _compute_market_value_live,
        axis=1,
    )
    if normalized_window is not None:
        enriched["price_change_pct"] = enriched["ticker"].map(
            lambda ticker: _compute_price_change_pct(
                snapshots_by_ticker=snapshots_by_ticker,
                histories_by_ticker=histories_by_ticker,
                ticker=ticker,
                window=normalized_window,
            )
        )
    return enriched


def normalize_price_change_window(value: str | None) -> str | None:
    """Return a canonical change-window label or raise for invalid input."""
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if normalized not in PRICE_CHANGE_WINDOWS:
        allowed = ", ".join(PRICE_CHANGE_WINDOWS)
        raise ValueError(f"Unsupported price change window '{value}'. Use one of: {allowed}")
    return normalized


def fetch_ticker_price_change(
    ticker: str,
    *,
    window: str,
    yahoo_client: Optional[YahooFinanceClient] = None,
) -> dict[str, object]:
    """Return a small reusable price-change snapshot for one ticker."""
    normalized_window = normalize_price_change_window(window)
    if normalized_window is None:
        raise ValueError("price change window is required")
    yahoo = yahoo_client or YahooFinanceClient()
    snapshot = _safe_fetch_price_snapshot(yahoo, ticker)
    history = _safe_fetch_history(
        yahoo,
        ticker,
        period=_history_period_for_change_window(normalized_window),
    )
    price_change_pct = calculate_price_change_pct(
        snapshot=snapshot,
        history=history,
        window=normalized_window,
    )
    return {
        "ticker": str(snapshot.get("ticker") or ticker).upper(),
        "last_price": snapshot.get("last_price"),
        "latest_price_date": snapshot.get("latest_price_date"),
        "price_change_window": normalized_window,
        "price_change_pct": price_change_pct,
        "source": snapshot.get("source"),
    }


def calculate_price_change_pct(
    *,
    snapshot: Mapping[str, object],
    history: pd.DataFrame,
    window: str,
) -> float | None:
    """Compute a change percentage from one quote snapshot and history frame."""
    normalized_window = normalize_price_change_window(window)
    if normalized_window is None:
        return None
    latest_price = snapshot.get("last_price")
    if latest_price is None:
        latest_price = _latest_history_close(history)
    baseline = _baseline_close_for_window(
        window=normalized_window,
        snapshot=snapshot,
        history=history,
    )
    if latest_price is None or baseline in {None, 0}:
        return None
    return (float(latest_price) / float(baseline)) - 1.0


def _snapshot_value(
    snapshots_by_ticker: Mapping[str, Mapping[str, object]],
    ticker: object,
    field: str,
):
    if ticker is None or pd.isna(ticker):
        return None
    snapshot = snapshots_by_ticker.get(str(ticker))
    if snapshot is None:
        return None
    return snapshot.get(field)


def _compute_market_value_live(row: pd.Series):
    shares = row.get("shares_or_principal")
    last_price = row.get("last_price")
    if shares is None or last_price is None:
        return None
    if pd.isna(shares) or pd.isna(last_price):
        return None
    return float(shares) * float(last_price)


def _compute_price_change_pct(
    *,
    snapshots_by_ticker: Mapping[str, Mapping[str, object]],
    histories_by_ticker: Mapping[str, pd.DataFrame],
    ticker: object,
    window: str,
) -> float | None:
    if ticker is None or pd.isna(ticker):
        return None
    ticker_text = str(ticker)
    snapshot = snapshots_by_ticker.get(ticker_text) or {}
    history = histories_by_ticker.get(ticker_text, pd.DataFrame())
    return calculate_price_change_pct(snapshot=snapshot, history=history, window=window)


def _baseline_close_for_window(
    *,
    window: str,
    snapshot: Mapping[str, object],
    history: pd.DataFrame,
) -> float | None:
    if window == "1D":
        previous_close = snapshot.get("previous_close")
        if previous_close is not None:
            return float(previous_close)
        normalized = _normalize_history_frame(history)
        if len(normalized) >= 2:
            return float(normalized.iloc[-2]["close"])
        return None

    normalized = _normalize_history_frame(history)
    if normalized.empty:
        return None
    if window == "5D":
        if len(normalized) < 6:
            return None
        return float(normalized.iloc[-6]["close"])
    if window == "ALL":
        return float(normalized.iloc[0]["close"])
    latest_date = normalized.iloc[-1]["price_date"]
    if window == "YTD":
        baseline_rows = normalized[normalized["price_date"].dt.year == latest_date.year]
        if baseline_rows.empty:
            return None
        return float(baseline_rows.iloc[0]["close"])

    offset = {
        "1M": pd.DateOffset(months=1),
        "3M": pd.DateOffset(months=3),
        "1Y": pd.DateOffset(years=1),
        "5Y": pd.DateOffset(years=5),
    }[window]
    target_date = latest_date - offset
    on_or_before = normalized[normalized["price_date"] <= target_date]
    if not on_or_before.empty:
        return float(on_or_before.iloc[-1]["close"])
    on_or_after = normalized[normalized["price_date"] >= target_date]
    if on_or_after.empty:
        return None
    return float(on_or_after.iloc[0]["close"])


def _latest_history_close(history: pd.DataFrame) -> float | None:
    normalized = _normalize_history_frame(history)
    if normalized.empty:
        return None
    return float(normalized.iloc[-1]["close"])


def _normalize_history_frame(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=["price_date", "close"])
    date_column = "date" if "date" in history.columns else "datetime" if "datetime" in history.columns else None
    if date_column is None or "close" not in history.columns:
        return pd.DataFrame(columns=["price_date", "close"])
    normalized = history[[date_column, "close"]].copy()
    normalized["price_date"] = pd.to_datetime(
        normalized[date_column],
        errors="coerce",
        utc=True,
    )
    normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
    normalized = normalized.dropna(subset=["price_date", "close"]).sort_values("price_date")
    return normalized.reset_index(drop=True)


def _history_period_for_change_window(window: str) -> str:
    return {
        "1D": "5d",
        "5D": "1mo",
        "1M": "6mo",
        "3M": "1y",
        "YTD": "ytd",
        "1Y": "2y",
        "5Y": "10y",
        "ALL": "max",
    }[window]


def _safe_fetch_price_snapshot(yahoo: YahooFinanceClient, ticker: str) -> dict[str, object]:
    try:
        return yahoo.fetch_price_snapshot(ticker)
    except Exception:
        return {"ticker": str(ticker).upper(), "source": "yfinance"}


def _safe_fetch_history(
    yahoo: YahooFinanceClient,
    ticker: str,
    *,
    period: str,
) -> pd.DataFrame:
    try:
        return yahoo.fetch_history(
            ticker,
            period=period,
            interval="1d",
        )
    except Exception:
        return pd.DataFrame()
