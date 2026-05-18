"""Tests for multi-security comparison table builder."""

import pytest
import pandas as pd

from valuation.company.comps import (
    CompsEntry,
    build_comps_table,
    _ratio,
    _implied_growth,
)


def _entry(
    ticker="AAPL",
    name="Apple Inc",
    price=190.0,
    market_cap=3_000_000_000_000.0,
    shares=15_800_000_000.0,
    revenue=400_000_000_000.0,
    net_income=100_000_000_000.0,
    da=12_000_000_000.0,
    capex=11_000_000_000.0,
    op_income=120_000_000_000.0,
    ocf=110_000_000_000.0,
    cash=50_000_000_000.0,
    ltd=100_000_000_000.0,
) -> CompsEntry:
    return CompsEntry(
        ticker=ticker,
        name=name,
        market_snapshot={
            "last_price": price,
            "market_cap": market_cap,
            "shares": shares,
        },
        financials={
            "revenue": revenue,
            "net_income": net_income,
            "depreciation_amortization": da,
            "capex": capex,
            "operating_income": op_income,
            "operating_cash_flow": ocf,
            "cash_and_equivalents": cash,
            "long_term_debt": ltd,
        },
        period_label="TTM",
    )


def test_build_comps_table_basic():
    entries = [_entry("AAPL"), _entry("MSFT", name="Microsoft", price=420.0, market_cap=3_100_000_000_000.0)]
    df = build_comps_table(entries)
    assert len(df) == 2
    assert list(df["ticker"]) == ["AAPL", "MSFT"]


def test_build_comps_table_columns():
    df = build_comps_table([_entry()])
    expected = {
        "ticker", "name", "price", "market_cap", "revenue", "net_income",
        "owner_earnings", "oe_margin_pct", "pe_ratio", "price_to_oe",
        "oe_yield_pct", "ev_to_ebitda", "implied_growth_pct", "as_of", "error",
    }
    assert expected.issubset(set(df.columns))


def test_build_comps_table_owner_earnings():
    # OE = net_income + da - capex = 100 + 12 - 11 = 101
    df = build_comps_table([_entry()])
    assert abs(df.iloc[0]["owner_earnings"] - 101_000_000_000.0) < 1


def test_build_comps_table_negative_oe_suppressed():
    # capex larger than net_income + da → negative OE → suppressed
    e = _entry(net_income=5_000_000_000, da=2_000_000_000, capex=20_000_000_000)
    df = build_comps_table([e])
    assert df.iloc[0]["owner_earnings"] is None
    assert df.iloc[0]["price_to_oe"] is None
    assert df.iloc[0]["oe_yield_pct"] is None
    assert df.iloc[0]["implied_growth_pct"] is None


def test_build_comps_table_pe_ratio():
    # P/E = 3T / 100B = 30
    df = build_comps_table([_entry()])
    assert abs(df.iloc[0]["pe_ratio"] - 30.0) < 0.01


def test_build_comps_table_oe_margin():
    # OE = 101B, revenue = 400B → 101/400 ≈ 0.2525
    df = build_comps_table([_entry()])
    assert abs(df.iloc[0]["oe_margin_pct"] - 101 / 400) < 0.001


def test_build_comps_table_ev_ebitda():
    # EV = 3T + 100B - 50B = 3.05T; EBITDA = op_income + da = 120B + 12B = 132B
    # EV/EBITDA ≈ 23.1
    df = build_comps_table([_entry()])
    ev = 3_000_000_000_000 + 100_000_000_000 - 50_000_000_000
    ebitda = 120_000_000_000 + 12_000_000_000
    assert abs(df.iloc[0]["ev_to_ebitda"] - ev / ebitda) < 0.01


def test_build_comps_table_implied_growth():
    # OE = 101B, mkt_cap = 3T → oe_yield = 101/3000 ≈ 0.03367
    # implied_growth = 0.10 - 0.03367 ≈ 0.06633
    df = build_comps_table([_entry()])
    oe_yield = 101_000_000_000 / 3_000_000_000_000
    assert abs(df.iloc[0]["implied_growth_pct"] - (0.10 - oe_yield)) < 1e-6


def test_build_comps_table_market_cap_derived():
    # market_cap not provided → derives as price * shares
    e = CompsEntry(
        ticker="TEST",
        name="Test",
        market_snapshot={"last_price": 100.0, "shares": 1_000_000_000.0},
        financials={"net_income": 5_000_000_000.0},
        period_label="TTM",
    )
    df = build_comps_table([e])
    assert abs(df.iloc[0]["market_cap"] - 100_000_000_000.0) < 1


def test_build_comps_table_missing_inputs():
    # Empty financials → most ratios are None
    e = CompsEntry(
        ticker="EMPTY",
        name="Empty",
        market_snapshot={"last_price": 50.0, "market_cap": 1e10},
        financials={},
        period_label=None,
    )
    df = build_comps_table([e])
    row = df.iloc[0]
    assert row["owner_earnings"] is None
    assert row["pe_ratio"] is None
    assert row["ev_to_ebitda"] is None


def test_build_comps_table_error_entry():
    e = CompsEntry(
        ticker="BAD",
        name="Bad Co",
        market_snapshot={},
        financials={},
        period_label=None,
        error="network timeout",
    )
    df = build_comps_table([e])
    assert df.iloc[0]["error"] == "network timeout"
    assert df.iloc[0]["market_cap"] is None


def test_build_comps_table_preserves_order():
    tickers = ["MSFT", "AAPL", "GOOG"]
    entries = [_entry(t, name=t) for t in tickers]
    df = build_comps_table(entries)
    assert list(df["ticker"]) == tickers


def test_ratio_helper():
    assert _ratio(10.0, 2.0) == pytest.approx(5.0)
    assert _ratio(None, 2.0) is None
    assert _ratio(10.0, None) is None
    assert _ratio(10.0, 0.0) is None


def test_implied_growth_helper():
    # OE = 10, market_cap = 100 → oe_yield = 0.1 → implied_g = 0.10 - 0.1 = 0
    assert _implied_growth(10.0, 100.0, required_return=0.10) == pytest.approx(0.0)
    assert _implied_growth(None, 100.0, required_return=0.10) is None
    assert _implied_growth(10.0, 0.0, required_return=0.10) is None
