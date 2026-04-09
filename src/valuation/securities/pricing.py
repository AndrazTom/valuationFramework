"""Security price enrichment helpers."""

from __future__ import annotations

from typing import Mapping, Optional

import pandas as pd

from valuation.data.providers.yahoo import YahooFinanceClient


def enrich_holdings_with_market_prices(
    holdings: pd.DataFrame,
    reference: pd.DataFrame,
    yahoo_client: Optional[YahooFinanceClient] = None,
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
    snapshots_by_ticker = {
        ticker: yahoo.fetch_price_snapshot(ticker)
        for ticker in sorted(set(enriched["ticker"].dropna()))
    }

    enriched["last_price"] = enriched["ticker"].map(
        lambda ticker: _snapshot_value(snapshots_by_ticker, ticker, "last_price")
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
    return enriched


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
