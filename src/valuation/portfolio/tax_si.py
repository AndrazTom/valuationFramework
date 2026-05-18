"""
Slovenian capital gains tax rules (ZDoh-2, Article 93–100).

Rates as of 2025 (verify with FURS or a tax advisor before filing):
  - Basic rate: 25 %
  - After 5 complete years: 20 %
  - After 10 complete years: 15 %
  - After 15 complete years: 0 % (exempt)

Losses can offset gains in the same year and are carried forward up to 5 years.
This module computes gross tax per disposal; loss-offsetting is handled at the
summary level in the CLI.
"""

from __future__ import annotations

from datetime import date


def si_cgt_rate(acquired: date, sold: date) -> float:
    """Return the Slovenian capital gains tax rate based on the holding period."""
    years = _complete_years(acquired, sold)
    if years >= 15:
        return 0.0
    if years >= 10:
        return 0.15
    if years >= 5:
        return 0.20
    return 0.25


def si_cgt_tax(gain_eur: float, acquired: date, sold: date) -> float:
    """Compute Slovenian CGT on one realized gain. Returns 0 for losses."""
    if gain_eur <= 0:
        return 0.0
    return round(gain_eur * si_cgt_rate(acquired, sold), 2)


def next_si_cgt_threshold(acquired: date, as_of: date) -> tuple[date, float] | None:
    """
    Return (next_threshold_date, new_rate) for the next tax rate reduction.
    Returns None if the position is already exempt (≥ 20 years held).
    """
    thresholds = [(5, 0.20), (10, 0.15), (15, 0.0)]
    current_years = _complete_years(acquired, as_of)
    for years, rate in thresholds:
        if current_years < years:
            # Anniversary is the same month/day, just years later
            try:
                next_date = date(acquired.year + years, acquired.month, acquired.day)
            except ValueError:
                # Handles Feb 29 in leap years: fall back to Feb 28
                next_date = date(acquired.year + years, acquired.month, acquired.day - 1)
            return next_date, rate
    return None


def _complete_years(start: date, end: date) -> int:
    """Number of complete calendar years between start and end (inclusive of anniversary day)."""
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return max(0, years)
