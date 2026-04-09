"""Yahoo Finance provider helpers via yfinance."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import yfinance as yf


class YahooFinanceClient:
    """Thin wrapper over yfinance for a stable repo-level interface."""

    def fetch_price_snapshot(self, ticker: str) -> Dict[str, Any]:
        """Return a small, stable snapshot instead of exposing raw yfinance objects."""
        instrument = yf.Ticker(ticker)
        info = instrument.fast_info or {}
        history = instrument.history(period="5d", interval="1d", auto_adjust=False)
        latest_close = None
        latest_date = None
        if not history.empty:
            latest_row = history.tail(1).iloc[0]
            latest_close = float(latest_row.get("Close"))
            latest_date = history.tail(1).index[0]

        return {
            "ticker": ticker.upper(),
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "quote_type": info.get("quote_type"),
            "last_price": _coerce_float(info.get("last_price"), latest_close),
            "previous_close": _coerce_float(info.get("previous_close")),
            "open": _coerce_float(info.get("open")),
            "day_high": _coerce_float(info.get("day_high")),
            "day_low": _coerce_float(info.get("day_low")),
            "market_cap": _coerce_float(info.get("market_cap")),
            "shares": _coerce_float(info.get("shares")),
            "fifty_day_average": _coerce_float(info.get("fifty_day_average")),
            "two_hundred_day_average": _coerce_float(
                info.get("two_hundred_day_average")
            ),
            "latest_price_date": (
                latest_date.strftime("%Y-%m-%d") if latest_date is not None else None
            ),
            "source": "yfinance",
        }

    def fetch_history(
        self,
        ticker: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return normalized historical OHLCV rows for downstream tables."""
        instrument = yf.Ticker(ticker)
        history = instrument.history(
            period=period,
            interval=interval,
            auto_adjust=False,
        )
        if history.empty:
            return pd.DataFrame()
        normalized = history.reset_index()
        normalized.columns = [
            str(column).lower().replace(" ", "_") for column in normalized.columns
        ]
        normalized["ticker"] = ticker.upper()
        return normalized


def _coerce_float(primary: Any, fallback: Any = None) -> Any:
    value = primary if primary is not None else fallback
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value
