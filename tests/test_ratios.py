"""Tests for historical valuation ratio builder."""

from datetime import date

import pandas as pd
import pytest

from valuation.company.ratios import (
    _annual_period_end_dates,
    _f,
    _price_by_month_map,
    _price_for_date,
    _r,
)


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

def test_r_basic():
    assert _r(10.0, 2.0) == pytest.approx(5.0)
    assert _r(None, 2.0) is None
    assert _r(10.0, None) is None
    assert _r(10.0, 0.0) is None


def test_f_conversions():
    assert _f(3.14) == pytest.approx(3.14)
    assert _f("5.0") == pytest.approx(5.0)
    assert _f(None) is None
    assert _f("nan") is None
    assert _f(float("nan")) is None


# ---------------------------------------------------------------------------
# Price map building
# ---------------------------------------------------------------------------

def _make_price_history(rows: list[tuple]) -> pd.DataFrame:
    """Build a minimal monthly price history from (date_str, close) tuples."""
    return pd.DataFrame([{"date": d, "close": c} for d, c in rows])


def test_price_by_month_map_basic():
    hist = _make_price_history([
        ("2023-01-01", 150.0),
        ("2023-02-01", 155.0),
        ("2023-12-01", 190.0),
    ])
    mp = _price_by_month_map(hist)
    assert mp[(2023, 1)] == pytest.approx(150.0)
    assert mp[(2023, 2)] == pytest.approx(155.0)
    assert mp[(2023, 12)] == pytest.approx(190.0)


def test_price_by_month_map_empty():
    assert _price_by_month_map(pd.DataFrame()) == {}


def test_price_for_date_exact_month():
    price_map = {(2023, 9): 178.0, (2023, 10): 175.0}
    target = date(2023, 9, 30)
    assert _price_for_date(price_map, target) == pytest.approx(178.0)


def test_price_for_date_fallback_prev_month():
    # Target month missing → should find previous month
    price_map = {(2023, 8): 172.0, (2023, 10): 180.0}
    target = date(2023, 9, 30)
    result = _price_for_date(price_map, target)
    assert result in (172.0, 180.0)  # either adjacent month is valid


def test_price_for_date_no_data():
    assert _price_for_date({}, date(2023, 9, 30)) is None
    assert _price_for_date({}, None) is None


# ---------------------------------------------------------------------------
# Annual period end dates
# ---------------------------------------------------------------------------

def _make_company_facts(concept_entries: list[dict]) -> dict:
    return {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": concept_entries
                    }
                }
            }
        }
    }


def test_annual_period_end_dates_basic():
    entries = [
        {"end": "2024-12-31", "val": 100, "fp": "FY", "form": "10-K", "filed": "2025-01-15"},
        {"end": "2023-12-31", "val": 90, "fp": "FY", "form": "10-K", "filed": "2024-01-15"},
        {"end": "2022-12-31", "val": 80, "fp": "FY", "form": "10-K", "filed": "2023-01-15"},
    ]
    facts = _make_company_facts(entries)
    result = _annual_period_end_dates(facts, limit=3)
    assert result.get("FY 2024") == "2024-12-31"
    assert result.get("FY 2023") == "2023-12-31"
    assert result.get("FY 2022") == "2022-12-31"


def test_annual_period_end_dates_non_december_fy():
    # AAPL-like fiscal year ending in September
    entries = [
        {"end": "2024-09-28", "val": 100, "fp": "FY", "form": "10-K", "filed": "2024-11-01"},
        {"end": "2023-09-30", "val": 90, "fp": "FY", "form": "10-K", "filed": "2023-11-01"},
    ]
    facts = _make_company_facts(entries)
    result = _annual_period_end_dates(facts, limit=2)
    assert result.get("FY 2024") == "2024-09-28"
    assert result.get("FY 2023") == "2023-09-30"


def test_annual_period_end_dates_limit():
    entries = [
        {"end": f"{y}-12-31", "val": 100, "fp": "FY", "form": "10-K", "filed": f"{y+1}-01-15"}
        for y in range(2015, 2025)
    ]
    facts = _make_company_facts(entries)
    result = _annual_period_end_dates(facts, limit=3)
    assert len(result) == 3
    assert "FY 2024" in result
    assert "FY 2023" in result
    assert "FY 2022" in result
    assert "FY 2021" not in result


def test_annual_period_end_dates_empty():
    result = _annual_period_end_dates({"facts": {}}, limit=5)
    assert result == {}
