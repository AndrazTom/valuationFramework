"""
Slovenian tax rules for securities income (ZDoh-2).

Capital gains (Article 93–100) — rates as of 2025:
  - Basic rate: 25 %
  - After 5 complete years: 20 %
  - After 10 complete years: 15 %
  - After 15 complete years:  0 % (exempt)

Dividends (Article 90–92):
  - 25 % flat withholding on gross dividend
  - Foreign WHT already paid to the source country credits against Slovenian tax
  - Net additional Slovenian tax = max(0, 25 % × gross − foreign WHT paid)

Losses on capital gains can offset gains in the same year and carry forward up
to 5 years.  This module computes per-disposal/per-dividend gross tax; loss
offsetting is handled at the summary level in the CLI.

Verify rates and rules with FURS (https://www.fu.gov.si) before filing.
"""

from __future__ import annotations

from datetime import date


# ---------------------------------------------------------------------------
# Capital gains
# ---------------------------------------------------------------------------

_SI_CGT_RATE = 0.25
_SI_CGT_THRESHOLDS = [
    (15, 0.00),
    (10, 0.15),
    (5,  0.20),
]


def si_cgt_rate(acquired: date, sold: date) -> float:
    """Return the Slovenian CGT rate for the given holding period."""
    years = _complete_years(acquired, sold)
    for min_years, rate in _SI_CGT_THRESHOLDS:
        if years >= min_years:
            return rate
    return _SI_CGT_RATE


def si_cgt_tax(gain_eur: float, acquired: date, sold: date) -> float:
    """Slovenian CGT on one disposal. Returns 0 for losses or exempt positions."""
    if gain_eur <= 0:
        return 0.0
    return round(gain_eur * si_cgt_rate(acquired, sold), 2)


def next_si_cgt_threshold(acquired: date, as_of: date) -> tuple[date, float] | None:
    """
    Return (next_rate_change_date, new_rate) for the holding.
    Returns None if already exempt (≥ 15 complete years).
    """
    thresholds_asc = [(5, 0.20), (10, 0.15), (15, 0.0)]
    current_years = _complete_years(acquired, as_of)
    for min_years, rate in thresholds_asc:
        if current_years < min_years:
            try:
                next_date = date(acquired.year + min_years, acquired.month, acquired.day)
            except ValueError:
                if acquired.month != 2 or acquired.day != 29:
                    raise
                # Feb 29 in a non-leap target year → Feb 28
                next_date = date(acquired.year + min_years, 2, 28)
            return next_date, rate
    return None


# ---------------------------------------------------------------------------
# Dividends
# ---------------------------------------------------------------------------

_SI_DIVIDEND_RATE = 0.25


def si_dividend_tax(
    gross_eur: float,
    foreign_wht_eur: float,
) -> float:
    """
    Net Slovenian dividend tax after crediting foreign withholding tax.

    gross_eur       – gross dividend in EUR before any WHT
    foreign_wht_eur – withholding tax already deducted by the foreign broker (positive)

    Returns additional tax due to FURS (can be 0 if WHT ≥ Slovenian rate).
    """
    if gross_eur <= 0:
        return 0.0
    si_gross_tax = round(gross_eur * _SI_DIVIDEND_RATE, 2)
    return max(0.0, round(si_gross_tax - foreign_wht_eur, 2))


def si_dividend_effective_rate(foreign_wht_eur: float, gross_eur: float) -> float:
    """Effective total tax rate (WHT + SI top-up) as a fraction of gross dividend."""
    if gross_eur <= 0:
        return 0.0
    top_up = si_dividend_tax(gross_eur, foreign_wht_eur)
    return (foreign_wht_eur + top_up) / gross_eur


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _complete_years(start: date, end: date) -> int:
    """Number of complete calendar years elapsed from start to end."""
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return max(0, years)
