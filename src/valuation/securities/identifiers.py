"""Canonical security identifiers for cross-provider joins.

Ticker symbols are useful market-data aliases, but they should not be treated as
the only identity key. For holdings data, CUSIP is usually the strongest free
identifier we have. For direct quote workflows, ticker plus exchange is often
good enough.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class SecurityIdentifier:
    """Normalized identifier bundle for one security."""

    security_id: str
    ticker: str | None = None
    exchange: str | None = None
    cusip: str | None = None
    cik: str | None = None
    issuer: str | None = None


def build_security_id(
    *,
    ticker: str | None = None,
    exchange: str | None = None,
    cusip: str | None = None,
    cik: str | None = None,
) -> str | None:
    """Return a canonical repo-level security identifier."""
    normalized_cusip = _normalized_or_none(cusip)
    if normalized_cusip is not None:
        return f"cusip:{normalized_cusip}"

    normalized_cik = _normalized_or_none(cik)
    if normalized_cik is not None:
        return f"cik:{normalized_cik.zfill(10)}"

    normalized_ticker = _normalized_or_none(ticker)
    normalized_exchange = _normalized_or_none(exchange)
    if normalized_ticker is not None and normalized_exchange is not None:
        return f"ticker:{normalized_exchange.upper()}:{normalized_ticker.upper()}"
    if normalized_ticker is not None:
        return f"ticker:{normalized_ticker.upper()}"
    return None


def identify_security(
    *,
    ticker: str | None = None,
    exchange: str | None = None,
    cusip: str | None = None,
    cik: str | None = None,
    issuer: str | None = None,
) -> SecurityIdentifier | None:
    """Build a normalized identifier bundle when enough fields are available."""
    security_id = build_security_id(
        ticker=ticker,
        exchange=exchange,
        cusip=cusip,
        cik=cik,
    )
    if security_id is None:
        return None
    return SecurityIdentifier(
        security_id=security_id,
        ticker=_normalized_or_none(ticker),
        exchange=_normalized_or_none(exchange),
        cusip=_normalized_or_none(cusip),
        cik=_normalized_or_none(cik),
        issuer=_normalized_or_none(issuer),
    )


def with_security_ids(
    frame: pd.DataFrame,
    *,
    ticker_column: str | None = None,
    exchange_column: str | None = None,
    cusip_column: str | None = None,
    cik_column: str | None = None,
) -> pd.DataFrame:
    """Return a copy of a table with a canonical `security_id` column."""
    enriched = frame.copy()
    if enriched.empty:
        if "security_id" not in enriched.columns:
            enriched["security_id"] = pd.Series(dtype="object")
        return enriched

    enriched["security_id"] = [
        build_security_id(
            ticker=_value_from_row(row, ticker_column),
            exchange=_value_from_row(row, exchange_column),
            cusip=_value_from_row(row, cusip_column),
            cik=_value_from_row(row, cik_column),
        )
        for _, row in enriched.iterrows()
    ]
    return enriched


def _value_from_row(row: pd.Series, column: str | None) -> Any:
    if column is None or column not in row:
        return None
    return row[column]


def _normalized_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text
