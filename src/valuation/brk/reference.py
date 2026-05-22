"""Manually curated Berkshire security aliases.

This is the free first-step registry that lets the repo revalue Berkshire's
major public holdings at current market prices. The generic identifier and
pricing layers stay reusable; this mapping is Berkshire-specific.
"""

from __future__ import annotations

import pandas as pd

from valuation.securities.identifiers import build_security_id

BRK_SECURITY_REFERENCE_ROWS = [
    {"cusip": "037833100", "ticker": "AAPL", "exchange": "NASDAQ"},
    {"cusip": "025816109", "ticker": "AXP", "exchange": "NYSE"},
    {"cusip": "060505104", "ticker": "BAC", "exchange": "NYSE"},
    {"cusip": "191216100", "ticker": "KO", "exchange": "NYSE"},
    {"cusip": "166764100", "ticker": "CVX", "exchange": "NYSE"},
    {"cusip": "615369105", "ticker": "MCO", "exchange": "NYSE"},
    {"cusip": "674599105", "ticker": "OXY", "exchange": "NYSE"},
    {"cusip": "H1467J104", "ticker": "CB", "exchange": "NYSE"},
    {"cusip": "500754106", "ticker": "KHC", "exchange": "NASDAQ"},
    {"cusip": "02079K305", "ticker": "GOOGL", "exchange": "NASDAQ"},
    {"cusip": "02079K107", "ticker": "GOOG", "exchange": "NASDAQ"},
    {"cusip": "23918K108", "ticker": "DVA", "exchange": "NYSE"},
    {"cusip": "501044101", "ticker": "KR", "exchange": "NYSE"},
    {"cusip": "92826C839", "ticker": "V", "exchange": "NYSE"},
    {"cusip": "829933100", "ticker": "SIRI", "exchange": "NASDAQ"},
    {"cusip": "57636Q104", "ticker": "MA", "exchange": "NYSE"},
    {"cusip": "92343E102", "ticker": "VRSN", "exchange": "NASDAQ"},
    {"cusip": "21036P108", "ticker": "STZ", "exchange": "NYSE"},
    {"cusip": "14040H105", "ticker": "COF", "exchange": "NYSE"},
    {"cusip": "91324P102", "ticker": "UNH", "exchange": "NYSE"},
    {"cusip": "25754A201", "ticker": "DPZ", "exchange": "NASDAQ"},
    {"cusip": "02005N100", "ticker": "ALLY", "exchange": "NYSE"},
    {"cusip": "G0403H108", "ticker": "AON", "exchange": "NYSE"},
    {"cusip": "670346105", "ticker": "NUE", "exchange": "NYSE"},
    {"cusip": "526057104", "ticker": "LEN", "exchange": "NYSE"},
    {"cusip": "526057302", "ticker": "LEN-B", "exchange": "NYSE"},
    {"cusip": "247361702", "ticker": "DAL", "exchange": "NYSE"},
    {"cusip": "650111107", "ticker": "NYT", "exchange": "NYSE"},
    {"cusip": "55616P104", "ticker": "M", "exchange": "NYSE"},
    {"cusip": "546347105", "ticker": "LPX", "exchange": "NYSE"},
    {"cusip": "62944T105", "ticker": "NVR", "exchange": "NYSE"},
    {"cusip": "47233W109", "ticker": "JEF", "exchange": "NYSE"},
    {"cusip": "530909100", "ticker": "LLYVA", "exchange": "NASDAQ"},
    {"cusip": "530909308", "ticker": "LLYVK", "exchange": "NASDAQ"},
]


def build_brk_security_reference() -> pd.DataFrame:
    """Return Berkshire's current manual market-symbol reference table."""
    rows = []
    for row in BRK_SECURITY_REFERENCE_ROWS:
        rows.append(
            {
                "security_id": build_security_id(cusip=row["cusip"]),
                "cusip": row["cusip"],
                "ticker": row["ticker"],
                "exchange": row["exchange"],
            }
        )
    return pd.DataFrame(rows)
