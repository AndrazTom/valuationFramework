"""
ECB historical FX rate fetcher for EUR base-currency portfolios.

Uses the ECB's free SDMX REST API (no key required):
  https://data-api.ecb.europa.eu/service/data/EXR/D.{CURRENCY}.EUR.SP00.A

The API returns daily spot rates as units of foreign currency per 1 EUR
(e.g. OBS_VALUE=1.0845 means 1 EUR = 1.0845 USD).

To convert X units of foreign currency to EUR: X / rate
We expose: eur_per_unit(currency, date) → float

Weekends/holidays have no rate. We search up to LOOKBACK_DAYS backwards for the
most recent available rate.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from valuation.config import cache_dir

_log = logging.getLogger(__name__)

_ECB_BASE = "https://data-api.ecb.europa.eu/service/data/EXR"
_LOOKBACK_DAYS = 7          # search this many days back for nearest rate
_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 1 week; historical rates don't change


class EcbFxClient:
    """Fetch and cache ECB daily FX rates for EUR-base portfolios."""

    def __init__(
        self,
        *,
        cache_root: str | Path | None = None,
        refresh: bool = False,
    ) -> None:
        self.cache_root = (
            Path(cache_root).expanduser()
            if cache_root is not None
            else cache_dir() / "ecb_fx"
        )
        self.refresh = refresh
        # In-memory: {currency: {date_str: rate}}
        self._cache: dict[str, dict[str, float]] = {}

    def eur_per_unit(self, currency: str, on: date) -> float | None:
        """
        Return how many EUR equal 1 unit of `currency` on `on`.

        Searches up to LOOKBACK_DAYS backwards if no rate is available for
        the exact date (weekends / public holidays).
        Returns None if no rate found within the lookback window.
        """
        if currency == "EUR":
            return 1.0
        rates = self._rates_for_currency(currency)
        for delta in range(_LOOKBACK_DAYS + 1):
            d = on - timedelta(days=delta)
            rate = rates.get(d.isoformat())
            if rate is not None:
                return 1.0 / rate  # API gives foreign-per-EUR; we want EUR-per-foreign
        return None

    def build_fx_rates_dict(
        self,
        currency_dates: list[tuple[str, date]],
    ) -> dict[tuple[str, str], float]:
        """
        Build the fx_rates dict expected by the FIFO engine.

        Input: list of (currency, date) pairs observed in the statement.
        Output: {(currency, "YYYY-MM-DD"): eur_per_unit, ...}
        """
        result: dict[tuple[str, str], float] = {}
        for currency, d in currency_dates:
            if currency == "EUR":
                continue
            rate = self.eur_per_unit(currency, d)
            if rate is not None:
                result[(currency, d.isoformat())] = rate
            else:
                _log.warning("No ECB rate for %s on %s (±%d days)", currency, d, _LOOKBACK_DAYS)
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rates_for_currency(self, currency: str) -> dict[str, float]:
        """Return the full date→rate map for a currency (from cache or ECB)."""
        if currency in self._cache:
            return self._cache[currency]

        if not self.refresh:
            persistent = self._read_persistent(currency)
            if persistent is not None:
                self._cache[currency] = persistent
                return persistent

        fetched = _fetch_ecb_series(currency)
        self._cache[currency] = fetched
        self._write_persistent(currency, fetched)
        return fetched

    def _persistent_path(self, currency: str) -> Path:
        return self.cache_root / f"ecb_{currency}_EUR.json"

    def _read_persistent(self, currency: str) -> dict[str, float] | None:
        path = self._persistent_path(currency)
        if not path.is_file():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - float(entry.get("fetched_at", 0))
            if age > _CACHE_TTL_SECONDS:
                return None
            return entry.get("rates", {})
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def _write_persistent(self, currency: str, rates: dict[str, float]) -> None:
        self.cache_root.mkdir(parents=True, exist_ok=True)
        path = self._persistent_path(currency)
        payload = {"fetched_at": time.time(), "rates": rates}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)


def _fetch_ecb_series(currency: str) -> dict[str, float]:
    """
    Download the full history of daily ECB spot rates for currency/EUR.

    Returns {date_str: rate} where rate is foreign-currency units per 1 EUR.
    """
    import urllib.request

    url = f"{_ECB_BASE}/D.{currency}.EUR.SP00.A?format=csvdata"
    _log.info("Fetching ECB rates for %s: %s", currency, url)
    try:
        req = urllib.request.Request(url, headers={"Accept": "text/csv"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    except Exception as exc:
        _log.warning("ECB fetch failed for %s: %s", currency, exc)
        return {}

    return _parse_ecb_csv(text)


def _parse_ecb_csv(csv_text: str) -> dict[str, float]:
    """Parse ECB SDMX CSV into {date_str: rate}."""
    import csv as csv_module

    rates: dict[str, float] = {}
    reader = csv_module.reader(csv_text.splitlines())
    header = None
    for row in reader:
        if not row:
            continue
        if header is None:
            header = [c.strip() for c in row]
            continue
        row_dict = dict(zip(header, [v.strip() for v in row]))
        date_str = row_dict.get("TIME_PERIOD", "").strip()
        obs_str = row_dict.get("OBS_VALUE", "").strip()
        if not date_str or not obs_str:
            continue
        try:
            rates[date_str] = float(obs_str)
        except ValueError:
            pass

    return rates
