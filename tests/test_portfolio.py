"""Tests for the IBKR portfolio module: parser, FIFO engine, and Slovenian CGT."""

import textwrap
from datetime import date
from pathlib import Path

import pytest

from valuation.portfolio.ibkr import _parse_ibkr_sections, _extract_stock_trades, load_activity_statement, IbkrTrade
from valuation.portfolio.lots import build_lots_and_realized
from valuation.portfolio.tax_si import si_cgt_rate, si_cgt_tax, next_si_cgt_threshold, _complete_years


# ---------------------------------------------------------------------------
# IBKR CSV parser
# ---------------------------------------------------------------------------

_SAMPLE_CSV = textwrap.dedent("""\
    Statement,Header,Field Name,Field Value
    Statement,Data,BrokerName,Interactive Brokers LLC
    Account Information,Header,Field Name,Field Value
    Account Information,Data,Base Currency,EUR
    Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code
    Trades,Data,Order,Stocks,EUR,AAPL,"2024-01-15, 10:30:00",10,185.00,185.00,-1850.00,-1.50,1851.50,0,0,O
    Trades,Data,Order,Stocks,EUR,AAPL,"2024-06-01, 14:20:00",5,195.00,195.00,-975.00,-1.00,976.00,0,0,O
    Trades,Data,Order,Stocks,EUR,AAPL,"2025-03-15, 11:00:00",-8,210.00,210.00,1680.00,-1.50,0,238.50,0,C
    Trades,Data,Order,Stocks,EUR,MSFT,"2023-05-10, 09:00:00",3,300.00,300.00,-900.00,-1.00,901.00,0,0,O
    Trades,SubTotal,,Stocks,,,,,,,,,,,,
    Trades,Total,,,,,,,,,,,,,,,
""")


def test_parse_ibkr_sections_extracts_trades():
    sections = _parse_ibkr_sections(_SAMPLE_CSV)
    assert "Trades" in sections
    trade_rows = [r for r in sections["Trades"] if r.get("DataDiscriminator") in ("Order", "Execution")]
    assert len(trade_rows) == 4


def test_parse_ibkr_sections_excludes_subtotals():
    sections = _parse_ibkr_sections(_SAMPLE_CSV)
    # SubTotal and Total rows have empty DataDiscriminator or "SubTotal"/"Total"
    for row in sections.get("Trades", []):
        assert row.get("DataDiscriminator") not in ("SubTotal", "Total")


def test_extract_stock_trades_parses_dates_and_quantities():
    sections = _parse_ibkr_sections(_SAMPLE_CSV)
    trades = _extract_stock_trades(sections)
    assert len(trades) == 4
    # Sorted by date
    assert trades[0].trade_date == date(2023, 5, 10)
    assert trades[-1].trade_date == date(2025, 3, 15)


def test_extract_stock_trades_buy_positive_sell_negative():
    sections = _parse_ibkr_sections(_SAMPLE_CSV)
    trades = _extract_stock_trades(sections)
    buys = [t for t in trades if t.quantity > 0]
    sells = [t for t in trades if t.quantity < 0]
    assert len(buys) == 3
    assert len(sells) == 1


def test_extract_stock_trades_price_and_proceeds():
    sections = _parse_ibkr_sections(_SAMPLE_CSV)
    trades = _extract_stock_trades(sections)
    buy = next(t for t in trades if t.symbol == "AAPL" and t.quantity == 10)
    assert buy.price == pytest.approx(185.0)
    assert buy.proceeds == pytest.approx(-1850.0)
    assert buy.commission == pytest.approx(-1.5)


def test_load_activity_statement_from_file(tmp_path):
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text(_SAMPLE_CSV, encoding="utf-8")
    trades = load_activity_statement(csv_file)
    assert len(trades) == 4
    assert all(isinstance(t, IbkrTrade) for t in trades)


def test_load_activity_statement_with_bom(tmp_path):
    csv_file = tmp_path / "statement_bom.csv"
    csv_file.write_bytes(b"\xef\xbb\xbf" + _SAMPLE_CSV.encode("utf-8"))
    trades = load_activity_statement(csv_file)
    assert len(trades) == 4


def test_csv_with_thousand_separator_numbers():
    csv = textwrap.dedent("""\
        Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code
        Trades,Data,Order,Stocks,EUR,TSLA,"2024-01-10, 09:00:00","1,000",250.00,250.00,"-250,000.00",-10.00,250010.00,0,0,O
    """)
    sections = _parse_ibkr_sections(csv)
    trades = _extract_stock_trades(sections)
    assert len(trades) == 1
    assert trades[0].quantity == pytest.approx(1000.0)
    assert trades[0].proceeds == pytest.approx(-250000.0)


# ---------------------------------------------------------------------------
# FIFO lot engine
# ---------------------------------------------------------------------------

def _make_trades(*specs) -> list[IbkrTrade]:
    """Create IbkrTrade objects from (symbol, date_str, qty, price, commission) tuples."""
    trades = []
    for symbol, dt_str, qty, price, commission in specs:
        proceeds = -(abs(price) * abs(qty)) if qty > 0 else abs(price) * abs(qty)
        trades.append(
            IbkrTrade(
                symbol=symbol,
                asset_category="Stocks",
                currency="EUR",
                trade_date=date.fromisoformat(dt_str),
                quantity=qty,
                price=abs(price),
                proceeds=proceeds,
                commission=commission,
            )
        )
    return trades


def test_fifo_single_buy_creates_one_lot():
    trades = _make_trades(("AAPL", "2024-01-15", 10, 185.0, -1.5))
    lots, realized = build_lots_and_realized(trades)
    assert len(lots) == 1
    assert lots[0].symbol == "AAPL"
    assert lots[0].quantity == pytest.approx(10.0)
    assert lots[0].cost_per_share_eur == pytest.approx(185.0)
    assert realized == []


def test_fifo_buy_then_full_sell():
    trades = _make_trades(
        ("AAPL", "2024-01-15", 10, 185.0, -1.5),
        ("AAPL", "2025-03-01", -10, 210.0, -1.5),
    )
    lots, realized = build_lots_and_realized(trades)
    assert lots == []
    assert len(realized) == 1
    r = realized[0]
    assert r.quantity == pytest.approx(10.0)
    assert r.acquired == date(2024, 1, 15)
    assert r.sold == date(2025, 3, 1)
    assert r.gain_eur is not None
    assert r.gain_eur > 0


def test_fifo_partial_sell_leaves_remaining_lot():
    trades = _make_trades(
        ("AAPL", "2024-01-15", 10, 185.0, -1.5),
        ("AAPL", "2025-03-01", -4, 210.0, -1.0),
    )
    lots, realized = build_lots_and_realized(trades)
    assert len(lots) == 1
    assert lots[0].quantity == pytest.approx(6.0)
    assert len(realized) == 1
    assert realized[0].quantity == pytest.approx(4.0)


def test_fifo_sell_spans_two_lots():
    trades = _make_trades(
        ("AAPL", "2024-01-15", 10, 185.0, -1.0),
        ("AAPL", "2024-06-01", 5, 195.0, -1.0),
        ("AAPL", "2025-03-15", -12, 210.0, -1.5),
    )
    lots, realized = build_lots_and_realized(trades)
    # 10 from first lot + 2 from second lot → 3 shares remain from second lot
    assert len(lots) == 1
    assert lots[0].quantity == pytest.approx(3.0)
    assert lots[0].cost_per_share_eur == pytest.approx(195.0)
    assert len(realized) == 2
    assert realized[0].acquired == date(2024, 1, 15)
    assert realized[0].quantity == pytest.approx(10.0)
    assert realized[1].acquired == date(2024, 6, 1)
    assert realized[1].quantity == pytest.approx(2.0)


def test_fifo_multiple_symbols_tracked_independently():
    trades = _make_trades(
        ("AAPL", "2024-01-01", 10, 185.0, -1.0),
        ("MSFT", "2024-01-01", 5, 300.0, -1.0),
        ("AAPL", "2025-01-01", -5, 200.0, -1.0),
    )
    lots, realized = build_lots_and_realized(trades)
    aapl_lots = [l for l in lots if l.symbol == "AAPL"]
    msft_lots = [l for l in lots if l.symbol == "MSFT"]
    assert len(aapl_lots) == 1
    assert aapl_lots[0].quantity == pytest.approx(5.0)
    assert len(msft_lots) == 1
    assert msft_lots[0].quantity == pytest.approx(5.0)
    assert len(realized) == 1
    assert realized[0].symbol == "AAPL"


def test_fifo_gain_calculation_is_correct():
    # Buy 10 at €100, commission €2. Sell 10 at €120, commission €2.
    # Cost basis = 10 * 100 + 2 = 1002 EUR
    # Proceeds = 10 * 120 - 2 = 1198 EUR
    # Gain = 1198 - 1002 = 196 EUR
    trades = _make_trades(
        ("TEST", "2024-01-01", 10, 100.0, -2.0),
        ("TEST", "2025-01-01", -10, 120.0, -2.0),
    )
    _, realized = build_lots_and_realized(trades)
    assert len(realized) == 1
    assert realized[0].gain_eur == pytest.approx(196.0)


def test_fifo_non_eur_trade_has_no_eur_amounts_by_default():
    trades = [
        IbkrTrade(
            symbol="AAPL",
            asset_category="Stocks",
            currency="USD",
            trade_date=date(2024, 1, 15),
            quantity=10,
            price=185.0,
            proceeds=-1850.0,
            commission=-1.5,
        )
    ]
    lots, _ = build_lots_and_realized(trades)
    assert lots[0].cost_per_share_eur is None
    assert lots[0].cost_basis_eur is None


def test_fifo_non_eur_trade_with_fx_rate():
    trades = [
        IbkrTrade(
            symbol="AAPL",
            asset_category="Stocks",
            currency="USD",
            trade_date=date(2024, 1, 15),
            quantity=10,
            price=185.0,
            proceeds=-1850.0,
            commission=-1.5,
        )
    ]
    fx_rates = {("USD", "2024-01-15"): 0.92}
    lots, _ = build_lots_and_realized(trades, fx_rates=fx_rates)
    assert lots[0].cost_per_share_eur == pytest.approx(185.0 * 0.92)


def test_fifo_empty_input():
    lots, realized = build_lots_and_realized([])
    assert lots == []
    assert realized == []


# ---------------------------------------------------------------------------
# Slovenian CGT rules
# ---------------------------------------------------------------------------

def test_complete_years_exact():
    assert _complete_years(date(2019, 3, 15), date(2024, 3, 15)) == 5
    assert _complete_years(date(2019, 3, 15), date(2024, 3, 14)) == 4


def test_si_cgt_rate_basic():
    # < 5 years
    assert si_cgt_rate(date(2022, 1, 1), date(2025, 1, 1)) == pytest.approx(0.25)


def test_si_cgt_rate_after_5_years():
    assert si_cgt_rate(date(2015, 1, 1), date(2020, 1, 1)) == pytest.approx(0.20)


def test_si_cgt_rate_after_10_years():
    assert si_cgt_rate(date(2010, 1, 1), date(2020, 1, 1)) == pytest.approx(0.15)


def test_si_cgt_rate_after_15_years():
    assert si_cgt_rate(date(2000, 1, 1), date(2015, 1, 1)) == pytest.approx(0.0)


def test_si_cgt_rate_exempt_after_15():
    assert si_cgt_rate(date(2005, 6, 1), date(2025, 6, 1)) == pytest.approx(0.0)


def test_si_cgt_tax_positive_gain():
    # 3 years held → 25% rate
    tax = si_cgt_tax(1000.0, date(2022, 1, 1), date(2025, 1, 1))
    assert tax == pytest.approx(250.0)


def test_si_cgt_tax_loss_returns_zero():
    tax = si_cgt_tax(-500.0, date(2023, 1, 1), date(2025, 1, 1))
    assert tax == pytest.approx(0.0)


def test_si_cgt_tax_exempt_position():
    tax = si_cgt_tax(5000.0, date(2005, 1, 1), date(2025, 1, 1))
    assert tax == pytest.approx(0.0)


def test_next_si_cgt_threshold_before_5_years():
    acquired = date(2023, 6, 15)
    as_of = date(2025, 1, 1)
    result = next_si_cgt_threshold(acquired, as_of)
    assert result is not None
    next_date, next_rate = result
    assert next_date == date(2028, 6, 15)
    assert next_rate == pytest.approx(0.20)


def test_next_si_cgt_threshold_between_5_and_10():
    acquired = date(2015, 1, 1)
    as_of = date(2022, 1, 1)
    result = next_si_cgt_threshold(acquired, as_of)
    assert result is not None
    next_date, next_rate = result
    assert next_date == date(2025, 1, 1)
    assert next_rate == pytest.approx(0.15)


def test_next_si_cgt_threshold_exempt_returns_none():
    acquired = date(2005, 1, 1)
    as_of = date(2025, 1, 1)
    assert next_si_cgt_threshold(acquired, as_of) is None
