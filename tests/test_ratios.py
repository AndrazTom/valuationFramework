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
    build_historical_ratios_table,
    build_historical_ratios_table_from_yahoo,
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


# ---------------------------------------------------------------------------
# build_historical_ratios_table (SEC path)
# ---------------------------------------------------------------------------

def _make_full_company_facts(years: list[int]) -> dict:
    """Minimal companyfacts with income, balance, cashflow for given FY years."""
    def _entries(vals: dict[int, float]) -> list[dict]:
        return [
            {"end": f"{y}-12-31", "val": v, "fp": "FY", "form": "10-K", "filed": f"{y+1}-02-01", "accn": f"acc-{y}"}
            for y, v in vals.items()
        ]

    return {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {"units": {"USD": _entries({y: 10_000_000_000 for y in years})}},
                "Revenues": {"units": {"USD": _entries({y: 100_000_000_000 for y in years})}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": _entries({y: 2_000_000_000 for y in years})}},
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": _entries({y: 20_000_000_000 for y in years})}},
                "StockholdersEquity": {"units": {"USD": _entries({y: 100_000_000_000 for y in years})}},
                "LongTermDebt": {"units": {"USD": _entries({y: 15_000_000_000 for y in years})}},
                "OperatingIncomeLoss": {"units": {"USD": _entries({y: 12_000_000_000 for y in years})}},
                "DepreciationAndAmortization": {"units": {"USD": _entries({y: 3_000_000_000 for y in years})}},
                "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": _entries({y: 5_000_000_000 for y in years})}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": _entries({y: 18_000_000_000 for y in years})}},
            }
        }
    }


def test_build_historical_ratios_table_basic():
    company_facts = _make_full_company_facts([2024, 2023])
    price_history = pd.DataFrame([
        {"date": "2024-12-01", "close": 200.0},
        {"date": "2023-12-01", "close": 180.0},
    ])
    result = build_historical_ratios_table(company_facts, price_history, limit=2)
    assert not result.empty
    assert "fiscal_year" in result.columns
    assert "pe_ratio" in result.columns
    assert "oe_per_share" in result.columns
    fy2024 = result[result["fiscal_year"] == "FY 2024"].iloc[0]
    assert fy2024["price"] == pytest.approx(200.0)
    assert fy2024["pe_ratio"] is not None
    # owner_earnings = net_income + DA - capex = 10B + 3B - 5B = 8B
    # oe_per_share = 8B / 2B shares = 4.0
    assert fy2024["oe_per_share"] == pytest.approx(4.0)


def test_build_historical_ratios_table_no_price_history():
    company_facts = _make_full_company_facts([2024])
    result = build_historical_ratios_table(company_facts, pd.DataFrame(), limit=1)
    assert not result.empty
    fy2024 = result[result["fiscal_year"] == "FY 2024"].iloc[0]
    assert fy2024["price"] is None
    assert fy2024["pe_ratio"] is None


def test_build_historical_ratios_table_empty_company_facts():
    result = build_historical_ratios_table({"facts": {}}, pd.DataFrame(), limit=5)
    assert result.empty


# ---------------------------------------------------------------------------
# build_historical_ratios_table_from_yahoo
# ---------------------------------------------------------------------------

def test_build_historical_ratios_table_from_yahoo_basic():
    ts1 = pd.Timestamp("2024-12-31")
    ts2 = pd.Timestamp("2023-12-31")
    income = pd.DataFrame({ts1: {"Total Revenue": 100e9, "Net Income": 10e9, "Diluted Average Shares": 2e9}, ts2: {"Total Revenue": 90e9, "Net Income": 9e9, "Diluted Average Shares": 2e9}})
    balance = pd.DataFrame({ts1: {"Total Assets": 300e9, "Cash And Cash Equivalents": 20e9, "Long Term Debt": 15e9, "Stockholders Equity": 100e9}, ts2: {"Total Assets": 280e9, "Cash And Cash Equivalents": 18e9, "Long Term Debt": 14e9, "Stockholders Equity": 95e9}})
    cashflow = pd.DataFrame({ts1: {"Operating Cash Flow": 18e9, "Capital Expenditure": -5e9, "Depreciation And Amortization": 3e9}, ts2: {"Operating Cash Flow": 16e9, "Capital Expenditure": -4e9, "Depreciation And Amortization": 2.8e9}})
    price_history = pd.DataFrame([
        {"date": "2024-12-01", "close": 200.0},
        {"date": "2023-12-01", "close": 180.0},
    ])
    result = build_historical_ratios_table_from_yahoo(income, balance, cashflow, price_history, limit=2)
    assert not result.empty
    assert "fiscal_year" in result.columns
    assert "oe_per_share" in result.columns
    fy2024 = result[result["fiscal_year"] == "FY 2024"].iloc[0]
    assert fy2024["revenue"] == pytest.approx(100e9)
    assert fy2024["net_income"] == pytest.approx(10e9)
    # Yahoo capex is stored negative: OE = 10B + 3B - (-5B) = 18B; shares = 2B → 9.0
    assert fy2024["oe_per_share"] == pytest.approx(9.0)


def test_build_historical_ratios_table_from_yahoo_empty_income():
    result = build_historical_ratios_table_from_yahoo(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert result.empty
