"""Tests for the IBKR portfolio module: parser, FIFO engine, Slovenian CGT, FX, dividends."""

import textwrap
from datetime import date
from pathlib import Path

import pytest

from valuation.portfolio.ibkr import (
    _parse_ibkr_sections,
    _extract_stock_trades,
    _symbol_from_dividend_desc,
    load_open_positions,
    load_activity_statement,
    load_trades,
    IbkrTrade,
    IbkrDividend,
    IbkrOpenPosition,
)
from valuation.portfolio.cli import (
    _periods_cover_year,
    run_portfolio_dividends,
    run_portfolio_interest,
    run_portfolio_reconcile,
    run_portfolio_tax,
)
from valuation.portfolio.lots import build_lots_and_realized, non_eur_currency_dates
from valuation.portfolio.tax_si import (
    si_cgt_rate,
    si_cgt_tax,
    si_dividend_tax,
    si_dividend_effective_rate,
    si_interest_tax,
    next_si_cgt_threshold,
    _complete_years,
)


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
    trades, dividends, meta = load_activity_statement(csv_file)
    assert len(trades) == 4
    assert all(isinstance(t, IbkrTrade) for t in trades)


def test_load_trades_convenience_wrapper(tmp_path):
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text(_SAMPLE_CSV, encoding="utf-8")
    trades = load_trades(csv_file)
    assert len(trades) == 4


def test_load_open_positions_parses_stock_summaries(tmp_path):
    csv = textwrap.dedent("""\
        Statement,Header,Field Name,Field Value
        Statement,Data,Period,"January 1, 2026 - May 18, 2026"
        Account Information,Header,Field Name,Field Value
        Account Information,Data,Base Currency,EUR
        Open Positions,Header,DataDiscriminator,Asset Category,Currency,Symbol,Quantity,Mult,Cost Price,Cost Basis,Close Price,Value,Unrealized P/L,Code
        Open Positions,Data,Summary,Stocks,USD,GOOGL,17,1,154.891745529,2633.159674,396.94,6747.98,4114.820326,
        Open Positions,Total,,Stocks,USD,,,,,2633.159674,,6747.98,4114.820326,
    """)
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text(csv, encoding="utf-8")

    positions, meta = load_open_positions(csv_file)

    assert meta.to_date == date(2026, 5, 18)
    assert len(positions) == 1
    assert isinstance(positions[0], IbkrOpenPosition)
    assert positions[0].symbol == "GOOGL"
    assert positions[0].quantity == pytest.approx(17)
    assert positions[0].cost_basis == pytest.approx(2633.159674)


def test_load_activity_statement_with_bom(tmp_path):
    csv_file = tmp_path / "statement_bom.csv"
    csv_file.write_bytes(b"\xef\xbb\xbf" + _SAMPLE_CSV.encode("utf-8"))
    trades, _, _ = load_activity_statement(csv_file)
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


def test_next_si_cgt_threshold_between_10_and_15():
    acquired = date(2012, 3, 1)
    as_of = date(2024, 6, 1)   # 12 years held → next threshold at 15yr
    result = next_si_cgt_threshold(acquired, as_of)
    assert result is not None
    next_date, next_rate = result
    assert next_date == date(2027, 3, 1)
    assert next_rate == pytest.approx(0.0)


def test_next_si_cgt_threshold_feb29_acquired():
    """Leap-day acquisition: threshold date falls back to Feb 28 in non-leap target years."""
    acquired = date(2008, 2, 29)
    as_of = date(2012, 3, 1)
    result = next_si_cgt_threshold(acquired, as_of)
    assert result is not None
    next_date, _ = result
    assert next_date.month == 2 and next_date.day in (28, 29)


# ---------------------------------------------------------------------------
# Order vs Execution deduplication
# ---------------------------------------------------------------------------

_MIXED_ORDER_EXECUTION_CSV = textwrap.dedent("""\
    Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code
    Trades,Data,Execution,Stocks,EUR,AAPL,"2024-01-15, 10:30:01",3,185.00,185.00,-555.00,-0.50,555.50,0,0,O
    Trades,Data,Execution,Stocks,EUR,AAPL,"2024-01-15, 10:30:02",7,185.00,185.00,-1295.00,-1.00,1296.00,0,0,O
    Trades,Data,Order,Stocks,EUR,AAPL,"2024-01-15, 10:30:00",10,185.00,185.00,-1850.00,-1.50,1851.50,0,0,O
""")


def test_order_rows_take_precedence_over_execution_rows():
    """When both Order and Execution rows exist, only Order rows are used."""
    sections = _parse_ibkr_sections(_MIXED_ORDER_EXECUTION_CSV)
    trades = _extract_stock_trades(sections)
    # Should be exactly 1 trade (the Order row), not 3 (Order + 2 Executions)
    assert len(trades) == 1
    assert trades[0].quantity == pytest.approx(10.0)
    assert trades[0].price == pytest.approx(185.0)


_EXECUTION_ONLY_CSV = textwrap.dedent("""\
    Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code
    Trades,Data,Execution,Stocks,EUR,MSFT,"2024-02-01, 09:00:00",5,300.00,300.00,-1500.00,-1.00,1501.00,0,0,O
    Trades,Data,Execution,Stocks,EUR,MSFT,"2024-02-01, 09:00:01",5,300.00,300.00,-1500.00,-1.00,1501.00,0,0,O
""")


def test_execution_rows_used_when_no_order_rows():
    """When no Order rows exist, fall back to Execution rows."""
    sections = _parse_ibkr_sections(_EXECUTION_ONLY_CSV)
    trades = _extract_stock_trades(sections)
    assert len(trades) == 2
    assert all(t.quantity == pytest.approx(5.0) for t in trades)


# ---------------------------------------------------------------------------
# Same-day buy-before-sell ordering
# ---------------------------------------------------------------------------

def test_same_day_buy_processed_before_sell():
    """A buy and sell on the same calendar date: buy must open a lot before the sell matches it."""
    # If sell comes first in the list but buy is on the same day, FIFO engine
    # should still match them correctly (buy is sorted before sell).
    buy = IbkrTrade(
        symbol="X", asset_category="Stocks", currency="EUR",
        trade_date=date(2025, 6, 1), quantity=10, price=100.0,
        proceeds=-1000.0, commission=-1.0, _sort_key=(date(2025, 6, 1), 0),
    )
    sell = IbkrTrade(
        symbol="X", asset_category="Stocks", currency="EUR",
        trade_date=date(2025, 6, 1), quantity=-10, price=110.0,
        proceeds=1100.0, commission=-1.0, _sort_key=(date(2025, 6, 1), 1),
    )
    # Pass sell before buy to verify sort_key wins
    lots, realized = build_lots_and_realized([sell, buy])
    # Should have no open lots and one realized gain (not an unmatched sell)
    assert lots == []
    assert len(realized) == 1
    assert realized[0].gain_eur is not None
    assert realized[0].gain_eur > 0


# ---------------------------------------------------------------------------
# Dividend parsing
# ---------------------------------------------------------------------------

_DIVIDEND_CSV = textwrap.dedent("""\
    Dividends,Header,Currency,Date,Description,Amount
    Dividends,Data,USD,2024-03-15,AAPL (US0378331005) Cash Dividend USD 0.24 per Share (Ordinary Dividend),24.00
    Dividends,Data,EUR,2024-04-10,ASML (NL0010273215) Cash Dividend EUR 1.75 per Share,17.50
    Dividends,SubTotal,USD,,Total,24.00
    Withholding Tax,Header,Currency,Date,Description,Amount,Code
    Withholding Tax,Data,USD,2024-03-15,AAPL (US0378331005) Cash Dividend USD 0.24 per Share - US Tax,-3.60,R
""")


def test_dividend_section_parsed(tmp_path):
    csv_file = tmp_path / "stmt.csv"
    csv_file.write_text(_DIVIDEND_CSV, encoding="utf-8")
    _, dividends, _ = load_activity_statement(csv_file)
    assert len(dividends) == 2


def test_dividend_aapl_has_wht(tmp_path):
    csv_file = tmp_path / "stmt.csv"
    csv_file.write_text(_DIVIDEND_CSV, encoding="utf-8")
    _, dividends, _ = load_activity_statement(csv_file)
    aapl = next(d for d in dividends if d.symbol == "AAPL")
    assert aapl.amount == pytest.approx(24.0)
    assert aapl.withholding_tax == pytest.approx(3.6)
    assert aapl.currency == "USD"


def test_dividend_wht_reversal_pairs_net_correctly(tmp_path):
    csv = textwrap.dedent("""\
        Dividends,Header,Currency,Date,Description,Amount
        Dividends,Data,EUR,2025-05-21,BNP(FR0000131104) Cash Dividend EUR 4.79 per Share (Ordinary Dividend),153.28
        Withholding Tax,Header,Currency,Date,Description,Amount,Code
        Withholding Tax,Data,EUR,2025-05-21,BNP(FR0000131104) Cash Dividend EUR 4.79 per Share - FR Tax,-38.32,
        Withholding Tax,Data,EUR,2025-05-21,BNP(FR0000131104) Cash Dividend EUR 4.79 per Share - FR Tax,-38.32,
        Withholding Tax,Data,EUR,2025-05-21,BNP(FR0000131104) Cash Dividend EUR 4.79 per Share - FR Tax,-38.32,
        Withholding Tax,Data,EUR,2025-05-21,BNP(FR0000131104) Cash Dividend EUR 4.79 per Share - FR Tax,38.32,
        Withholding Tax,Data,EUR,2025-05-21,BNP(FR0000131104) Cash Dividend EUR 4.79 per Share - FR Tax,38.32,
    """)
    csv_file = tmp_path / "stmt.csv"
    csv_file.write_text(csv, encoding="utf-8")

    _, dividends, _ = load_activity_statement(csv_file)

    assert len(dividends) == 1
    assert dividends[0].withholding_tax == pytest.approx(38.32)


def test_dividend_eur_security_has_no_wht(tmp_path):
    csv_file = tmp_path / "stmt.csv"
    csv_file.write_text(_DIVIDEND_CSV, encoding="utf-8")
    _, dividends, _ = load_activity_statement(csv_file)
    asml = next(d for d in dividends if d.symbol == "ASML")
    assert asml.amount == pytest.approx(17.5)
    assert asml.withholding_tax == pytest.approx(0.0)


def test_symbol_from_dividend_desc_standard():
    assert _symbol_from_dividend_desc("AAPL (US0378331005) Cash Dividend USD 0.24 per Share") == "AAPL"


def test_symbol_from_dividend_desc_multiword():
    assert _symbol_from_dividend_desc("BRK B (US0846707026) Cash Dividend") == "BRK B"


def test_symbol_from_dividend_desc_empty():
    assert _symbol_from_dividend_desc("") == ""


# ---------------------------------------------------------------------------
# Statement metadata
# ---------------------------------------------------------------------------

_META_CSV = textwrap.dedent("""\
    Statement,Header,Field Name,Field Value
    Statement,Data,BrokerName,Interactive Brokers LLC
    Statement,Data,Period,"January 1, 2026 - December 31, 2026"
    Account Information,Header,Field Name,Field Value
    Account Information,Data,Base Currency,EUR
    Account Information,Data,Account,U1234567
""")


def test_statement_meta_base_currency(tmp_path):
    csv_file = tmp_path / "stmt.csv"
    csv_file.write_text(_META_CSV, encoding="utf-8")
    _, _, meta = load_activity_statement(csv_file)
    assert meta.base_currency == "EUR"


def test_statement_meta_account_id(tmp_path):
    csv_file = tmp_path / "stmt.csv"
    csv_file.write_text(_META_CSV, encoding="utf-8")
    _, _, meta = load_activity_statement(csv_file)
    assert meta.account_id == "U1234567"


def test_statement_meta_period_parsed(tmp_path):
    csv_file = tmp_path / "stmt.csv"
    csv_file.write_text(_META_CSV, encoding="utf-8")
    _, _, meta = load_activity_statement(csv_file)
    assert meta.from_date == date(2026, 1, 1)
    assert meta.to_date == date(2026, 12, 31)


# ---------------------------------------------------------------------------
# non_eur_currency_dates helper
# ---------------------------------------------------------------------------

def test_non_eur_currency_dates_extracts_usd():
    trades = [
        IbkrTrade("AAPL", "Stocks", "USD", date(2024, 1, 15), 10, 185.0, -1850.0, -1.5),
        IbkrTrade("ASML", "Stocks", "EUR", date(2024, 1, 20), 5, 700.0, -3500.0, -1.0),
    ]
    pairs = non_eur_currency_dates(trades)
    assert ("USD", date(2024, 1, 15)) in pairs
    assert ("EUR", date(2024, 1, 20)) not in pairs


def test_non_eur_currency_dates_deduplicates():
    trades = [
        IbkrTrade("AAPL", "Stocks", "USD", date(2024, 1, 15), 5, 185.0, -925.0, -1.0),
        IbkrTrade("MSFT", "Stocks", "USD", date(2024, 1, 15), 3, 300.0, -900.0, -1.0),
    ]
    pairs = non_eur_currency_dates(trades)
    # Same currency+date pair should appear only once
    assert pairs.count(("USD", date(2024, 1, 15))) == 1


# ---------------------------------------------------------------------------
# ECB FX client (mocked — no live network)
# ---------------------------------------------------------------------------

def test_ecb_client_eur_rate_is_one():
    from valuation.portfolio.fx import EcbFxClient
    client = EcbFxClient()
    assert client.eur_per_unit("EUR", date(2024, 1, 15)) == pytest.approx(1.0)


def test_ecb_client_uses_cache(tmp_path, monkeypatch):
    from valuation.portfolio.fx import EcbFxClient

    fetch_calls = {"count": 0}

    def fake_fetch(currency):
        fetch_calls["count"] += 1
        return {"2024-01-15": 1.0845, "2024-01-16": 1.0850}

    monkeypatch.setattr("valuation.portfolio.fx._fetch_ecb_series", fake_fetch)

    client1 = EcbFxClient(cache_root=tmp_path)
    r1 = client1.eur_per_unit("USD", date(2024, 1, 15))
    assert r1 == pytest.approx(1 / 1.0845)
    assert fetch_calls["count"] == 1

    # Second client with same cache root: should read from disk, not fetch again
    client2 = EcbFxClient(cache_root=tmp_path)
    r2 = client2.eur_per_unit("USD", date(2024, 1, 15))
    assert r2 == pytest.approx(1 / 1.0845)
    assert fetch_calls["count"] == 1  # still 1, no new fetch


def test_ecb_client_lookback_finds_nearest(tmp_path, monkeypatch):
    """If exact date missing (weekend), finds the most recent prior business day."""
    from valuation.portfolio.fx import EcbFxClient

    monkeypatch.setattr(
        "valuation.portfolio.fx._fetch_ecb_series",
        lambda _: {"2024-01-12": 1.10},  # Friday only
    )

    client = EcbFxClient(cache_root=tmp_path, refresh=True)
    # 2024-01-13 is Saturday, 2024-01-14 is Sunday, both missing → should use Jan 12
    rate = client.eur_per_unit("USD", date(2024, 1, 14))
    assert rate == pytest.approx(1 / 1.10)


def test_ecb_client_returns_none_when_no_rate_in_window(tmp_path, monkeypatch):
    from valuation.portfolio.fx import EcbFxClient

    monkeypatch.setattr("valuation.portfolio.fx._fetch_ecb_series", lambda _: {})

    client = EcbFxClient(cache_root=tmp_path, refresh=True)
    assert client.eur_per_unit("USD", date(2024, 1, 15)) is None


def test_ecb_build_fx_rates_dict(tmp_path, monkeypatch):
    from valuation.portfolio.fx import EcbFxClient

    monkeypatch.setattr(
        "valuation.portfolio.fx._fetch_ecb_series",
        lambda _: {"2024-01-15": 1.0845},
    )
    client = EcbFxClient(cache_root=tmp_path, refresh=True)
    result = client.build_fx_rates_dict([("USD", date(2024, 1, 15))])
    assert ("USD", "2024-01-15") in result
    assert result[("USD", "2024-01-15")] == pytest.approx(1 / 1.0845)


def test_ecb_build_fx_rates_dict_eur_skipped(tmp_path, monkeypatch):
    from valuation.portfolio.fx import EcbFxClient

    monkeypatch.setattr("valuation.portfolio.fx._fetch_ecb_series", lambda _: {})
    client = EcbFxClient(cache_root=tmp_path, refresh=True)
    result = client.build_fx_rates_dict([("EUR", date(2024, 1, 15))])
    assert result == {}


# ---------------------------------------------------------------------------
# ECB CSV parser
# ---------------------------------------------------------------------------

def test_ecb_parse_csv():
    from valuation.portfolio.fx import _parse_ecb_csv

    sample = textwrap.dedent("""\
        KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE
        EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2024-01-15,1.0845
        EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2024-01-16,1.0850
    """)
    rates = _parse_ecb_csv(sample)
    assert rates["2024-01-15"] == pytest.approx(1.0845)
    assert rates["2024-01-16"] == pytest.approx(1.0850)


def test_ecb_parse_csv_empty():
    from valuation.portfolio.fx import _parse_ecb_csv
    assert _parse_ecb_csv("") == {}


# ---------------------------------------------------------------------------
# Dividend tax rules
# ---------------------------------------------------------------------------

def test_si_dividend_tax_us_stock_15pct_wht():
    # US stock: 15% WHT under US-Slovenia tax treaty; SI rate = 25%
    # Net top-up = 25% - 15% = 10%
    gross = 100.0
    wht = 15.0
    assert si_dividend_tax(gross, wht) == pytest.approx(10.0)


def test_si_dividend_tax_no_wht():
    # No foreign WHT → full 25% due to SI
    assert si_dividend_tax(100.0, 0.0) == pytest.approx(25.0)


def test_si_dividend_tax_wht_exceeds_si_rate():
    # If WHT ≥ 25%, no additional SI tax
    assert si_dividend_tax(100.0, 30.0) == pytest.approx(0.0)


def test_si_dividend_tax_negative_gross():
    assert si_dividend_tax(-50.0, 0.0) == pytest.approx(0.0)


def test_si_dividend_effective_rate():
    # 100 EUR gross, 15 EUR WHT: effective = (15 + 10) / 100 = 25%
    rate = si_dividend_effective_rate(15.0, 100.0)
    assert rate == pytest.approx(0.25)


def test_si_dividend_effective_rate_zero_gross():
    assert si_dividend_effective_rate(0.0, 0.0) == pytest.approx(0.0)


def test_si_interest_tax_basic():
    assert si_interest_tax(100.0, 0.0) == pytest.approx(25.0)
    assert si_interest_tax(100.0, 5.0) == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# IBKR Flex Query XML parser
# ---------------------------------------------------------------------------

import textwrap as _textwrap
from valuation.portfolio.ibkr_flex import (
    FlexInterest,
    FlexLot,
    load_flex_query,
    parse_flex_interest,
    _parse_flex_datetime,
    _parse_per_share_from_desc,
)


_FLEX_XML_BASIC = _textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <FlexQueryResponse>
      <FlexStatements>
        <FlexStatement accountId="U1234567" fromDate="20250101" toDate="20251231">
          <AccountInformation currency="EUR" />
          <Trades>
            <Trade symbol="AAPL" assetCategory="STK" currency="USD"
                   tradeDate="20240601" dateTime="20240601;093000" quantity="10" />
            <Trade symbol="AAPL" assetCategory="STK" currency="USD"
                   tradeDate="20250601" dateTime="20250601;093000" quantity="-10" />
          </Trades>
          <Lots>
            <Lot symbol="AAPL" assetCategory="STK" currency="USD"
                 buySell="SELL"
                 openDateTime="20240601;093000"
                 dateTime="20250601;093000"
                 quantity="-10"
                 cost="-1500.00"
                 fifoPnlRealized="200.00" />
          </Lots>
          <CashTransactions>
            <CashTransaction type="Dividends" symbol="AAPL" currency="USD"
                             dateTime="20250315;000000" amount="25.00"
                             description="AAPL CASH DIVIDEND USD 0.25 PER SHARE" />
            <CashTransaction type="Withholding Tax" symbol="AAPL" currency="USD"
                             dateTime="20250315;000000" amount="-3.75"
                             description="AAPL(US0378331005) CASH DIVIDEND USD 0.25 PER SHARE - 15% TAX" />
          </CashTransactions>
        </FlexStatement>
      </FlexStatements>
    </FlexQueryResponse>
""")


def test_flex_lot_parsed():
    import io, tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(_FLEX_XML_BASIC)
        fname = f.name
    try:
        lots, dividends, meta = load_flex_query(fname)
    finally:
        os.unlink(fname)

    assert len(lots) == 1
    lot = lots[0]
    assert lot.symbol == "AAPL"
    assert lot.currency == "USD"
    assert lot.quantity == pytest.approx(10.0)
    assert lot.cost_native == pytest.approx(-1500.0)
    assert lot.pnl_native == pytest.approx(200.0)
    assert lot.proceeds_native == pytest.approx(-1300.0)


def test_flex_lot_acquired_and_sold_dates():
    import io, tempfile, os
    from datetime import date
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(_FLEX_XML_BASIC)
        fname = f.name
    try:
        lots, _, _ = load_flex_query(fname)
    finally:
        os.unlink(fname)

    assert lots[0].acquired == date(2024, 6, 1)
    assert lots[0].sold == date(2025, 6, 1)


def test_flex_dividend_parsed():
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(_FLEX_XML_BASIC)
        fname = f.name
    try:
        _, dividends, _ = load_flex_query(fname)
    finally:
        os.unlink(fname)

    assert len(dividends) == 1
    d = dividends[0]
    assert d.symbol == "AAPL"
    assert d.amount == pytest.approx(25.0)
    assert d.withholding_tax == pytest.approx(3.75)


def test_flex_meta_parsed():
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(_FLEX_XML_BASIC)
        fname = f.name
    try:
        _, _, meta = load_flex_query(fname)
    finally:
        os.unlink(fname)

    assert meta.account_id == "U1234567"
    assert meta.base_currency == "EUR"


def test_flex_skips_non_sell_lots():
    """BUY Lot rows (openDateTime == dateTime) should not be included."""
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="X" fromDate="20250101" toDate="20251231">
              <Lots>
                <Lot symbol="GOOG" assetCategory="STK" currency="USD"
                     buySell="BUY"
                     openDateTime="20240601;093000"
                     dateTime="20240601;093000"
                     quantity="5"
                     cost="-2000.00"
                     fifoPnlRealized="0.00" />
                <Lot symbol="GOOG" assetCategory="STK" currency="USD"
                     buySell="SELL"
                     openDateTime="20240601;093000"
                     dateTime="20250101;093000"
                     quantity="-5"
                     cost="-2000.00"
                     fifoPnlRealized="500.00" />
              </Lots>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        fname = f.name
    try:
        lots, _, _ = load_flex_query(fname)
    finally:
        os.unlink(fname)

    assert len(lots) == 1
    assert lots[0].symbol == "GOOG"


def test_flex_skips_zero_quantity_lots():
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="X" fromDate="20250101" toDate="20251231">
              <Lots>
                <Lot symbol="MSFT" assetCategory="STK" currency="USD"
                     buySell="SELL"
                     openDateTime="20240101;093000"
                     dateTime="20250101;093000"
                     quantity="0"
                     cost="0.00"
                     fifoPnlRealized="0.00" />
              </Lots>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        fname = f.name
    try:
        lots, _, _ = load_flex_query(fname)
    finally:
        os.unlink(fname)

    assert lots == []


def test_parse_flex_datetime_formats():
    from datetime import date
    assert _parse_flex_datetime("20250315;074110") == date(2025, 3, 15)
    assert _parse_flex_datetime("20250315") == date(2025, 3, 15)
    assert _parse_flex_datetime("") is None
    assert _parse_flex_datetime("bad") is None


def test_parse_per_share_from_desc():
    assert _parse_per_share_from_desc("AAPL(US0378331005) CASH DIVIDEND USD 0.25 PER SHARE") == pytest.approx(0.25)
    assert _parse_per_share_from_desc("CASH DIVIDEND EUR 1.50 PER SHARE") == pytest.approx(1.50)
    assert _parse_per_share_from_desc("no amount here") is None


def test_flex_wht_only_derives_gross_via_rate_arithmetic():
    """When WHT description contains '- XX% TAX', gross is derived even without Trade/Lot history."""
    # 6 shares × EUR 2.00/share × 15% = EUR 1.80 WHT exactly
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="X" fromDate="20250101" toDate="20251231">
              <CashTransactions>
                <CashTransaction type="Withholding Tax" symbol="TST" currency="USD"
                                 dateTime="20250310;000000" amount="-1.80"
                                 description="TST(US1234567890) CASH DIVIDEND USD 2.00 PER SHARE - 15% TAX" />
              </CashTransactions>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        fname = f.name
    try:
        _, dividends, _ = load_flex_query(fname)
    finally:
        os.unlink(fname)

    assert len(dividends) == 1
    assert dividends[0].symbol == "TST"
    assert dividends[0].amount == pytest.approx(12.00)  # 6 × 2.00
    assert dividends[0].withholding_tax == pytest.approx(1.80)


def test_flex_wht_debit_credit_pairs_net_correctly():
    """3 debit + 2 credit WHT entries should net to 1 debit, not triple."""
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="X" fromDate="20250101" toDate="20251231">
              <Trades>
                <Trade symbol="BNP" assetCategory="STK" currency="EUR"
                       tradeDate="20250101" dateTime="20250101;093000" quantity="32" />
              </Trades>
              <CashTransactions>
                <CashTransaction type="Dividends" symbol="BNP" currency="EUR"
                                 dateTime="20250521;000000" amount="153.28"
                                 description="BNP CASH DIVIDEND EUR 4.79 PER SHARE" />
                <CashTransaction type="Withholding Tax" symbol="BNP" currency="EUR"
                                 dateTime="20250521;000000" amount="-38.32"
                                 description="BNP(FR0000131104) CASH DIVIDEND EUR 4.79 PER SHARE - FR TAX" />
                <CashTransaction type="Withholding Tax" symbol="BNP" currency="EUR"
                                 dateTime="20250521;000000" amount="-38.32"
                                 description="BNP(FR0000131104) CASH DIVIDEND EUR 4.79 PER SHARE - FR TAX" />
                <CashTransaction type="Withholding Tax" symbol="BNP" currency="EUR"
                                 dateTime="20250521;000000" amount="-38.32"
                                 description="BNP(FR0000131104) CASH DIVIDEND EUR 4.79 PER SHARE - FR TAX" />
                <CashTransaction type="Withholding Tax" symbol="BNP" currency="EUR"
                                 dateTime="20250521;000000" amount="38.32"
                                 description="BNP(FR0000131104) CASH DIVIDEND EUR 4.79 PER SHARE - FR TAX" />
                <CashTransaction type="Withholding Tax" symbol="BNP" currency="EUR"
                                 dateTime="20250521;000000" amount="38.32"
                                 description="BNP(FR0000131104) CASH DIVIDEND EUR 4.79 PER SHARE - FR TAX" />
              </CashTransactions>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        fname = f.name
    try:
        _, dividends, _ = load_flex_query(fname)
    finally:
        os.unlink(fname)

    assert len(dividends) == 1
    assert dividends[0].withholding_tax == pytest.approx(38.32)


def test_flex_proceeds_native_property():
    from datetime import date
    lot = FlexLot(
        symbol="TST", currency="EUR",
        acquired=date(2024, 1, 1), sold=date(2025, 1, 1),
        quantity=10.0, cost_native=-1000.0, pnl_native=300.0,
    )
    assert lot.proceeds_native == pytest.approx(-700.0)


def test_flex_wht_rate_noninteger_inferred_shares_yields_empty():
    """When WHT arithmetic gives a non-integer share count, dividend is skipped."""
    # 1.00 WHT at 15% = 6.67 shares for 1.00/share — not near an integer, should be skipped
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="X" fromDate="20250101" toDate="20251231">
              <CashTransactions>
                <CashTransaction type="Withholding Tax" symbol="XYZ" currency="USD"
                                 dateTime="20250401;000000" amount="-1.00"
                                 description="XYZ(US0000000000) CASH DIVIDEND USD 1.00 PER SHARE - 15% TAX" />
              </CashTransactions>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        fname = f.name
    try:
        _, dividends, _ = load_flex_query(fname)
    finally:
        os.unlink(fname)

    # 1.00 / (1.00 × 0.15) = 6.67 → not within 2% of 7 → skip
    assert dividends == []


def test_flex_shares_from_lot_elements_when_no_trades():
    """Dividend gross is derived from Lot elements when buy predates the statement period."""
    # 5 shares bought in 2024, sold in Aug 2025. Dividend paid May 2025 while lot open.
    # No "% TAX" in description → forces Lot path.
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="X" fromDate="20250101" toDate="20251231">
              <Trades>
                <Trade symbol="OTHER" assetCategory="STK" currency="EUR"
                       tradeDate="20250101" dateTime="20250101;093000" quantity="1" />
              </Trades>
              <Lots>
                <Lot symbol="PAH" assetCategory="STK" currency="EUR"
                     buySell="SELL"
                     openDateTime="20240601;093000"
                     dateTime="20250801;093000"
                     quantity="-5"
                     cost="-1000.00"
                     fifoPnlRealized="200.00" />
              </Lots>
              <CashTransactions>
                <CashTransaction type="Withholding Tax" symbol="PAH" currency="EUR"
                                 dateTime="20250528;000000" amount="-13.19"
                                 description="PAH(DE0007100338) CASH DIVIDEND EUR 10.00 PER SHARE" />
              </CashTransactions>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        fname = f.name
    try:
        _, dividends, _ = load_flex_query(fname)
    finally:
        os.unlink(fname)

    # Lot was open on 2025-05-28 (openDateTime=2024-06-01 ≤ 2025-05-28 < 2025-08-01)
    # gross = 5 × 10.00 = 50.00
    assert len(dividends) == 1
    d = dividends[0]
    assert d.symbol == "PAH"
    assert d.amount == pytest.approx(50.00)
    assert d.withholding_tax == pytest.approx(13.19)


def test_flex_interest_parsed_basic():
    """Broker Interest Received entries are parsed into FlexInterest records."""
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="U1234567" fromDate="20250101" toDate="20251231">
              <CashTransactions>
                <CashTransaction type="Broker Interest Received" currency="EUR"
                                 dateTime="20251031;000000" amount="30.97"
                                 description="EUR CREDIT INT FOR OCT-01 TO OCT-31" />
                <CashTransaction type="Broker Interest Received" currency="EUR"
                                 dateTime="20251130;000000" amount="50.07"
                                 description="EUR CREDIT INT FOR NOV-01 TO NOV-30" />
              </CashTransactions>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        fname = f.name
    try:
        records = parse_flex_interest(fname)
    finally:
        os.unlink(fname)

    assert len(records) == 2
    assert all(isinstance(r, FlexInterest) for r in records)
    assert records[0].payment_date == date(2025, 10, 31)
    assert records[0].amount == pytest.approx(30.97)
    assert records[0].withholding_tax == pytest.approx(0.0)
    assert records[1].amount == pytest.approx(50.07)


def test_flex_interest_wht_matched():
    """Withholding Tax entries with CREDIT INT are matched to interest records."""
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="U1234567" fromDate="20250101" toDate="20251231">
              <CashTransactions>
                <CashTransaction type="Broker Interest Received" currency="EUR"
                                 dateTime="20251031;000000" amount="30.97"
                                 description="EUR CREDIT INT FOR OCT-01 TO OCT-31" />
                <CashTransaction type="Withholding Tax" currency="EUR"
                                 dateTime="20251031;000000" amount="-6.19"
                                 description="WITHHOLDING @ 20% ON CREDIT INT FOR OCT-01 TO OCT-31" />
              </CashTransactions>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        fname = f.name
    try:
        records = parse_flex_interest(fname)
    finally:
        os.unlink(fname)

    assert len(records) == 1
    r = records[0]
    assert r.currency == "EUR"
    assert r.amount == pytest.approx(30.97)
    assert r.withholding_tax == pytest.approx(6.19)


# ---------------------------------------------------------------------------
# Portfolio reconciliation command
# ---------------------------------------------------------------------------

_RECONCILE_CSV = textwrap.dedent("""\
    Statement,Header,Field Name,Field Value
    Statement,Data,Period,"January 1, 2024 - December 31, 2025"
    Account Information,Header,Field Name,Field Value
    Account Information,Data,Base Currency,EUR
    Account Information,Data,Account,U1234567
    Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code
    Trades,Data,Order,Stocks,EUR,AAPL,"2024-01-15, 10:30:00",10,100.00,100.00,-1000.00,-2.00,1002.00,0,0,O
    Trades,Data,Order,Stocks,EUR,AAPL,"2025-03-15, 11:00:00",-10,120.00,120.00,1200.00,-2.00,0,196.00,0,C
    Dividends,Header,Currency,Date,Description,Amount
    Dividends,Data,EUR,2025-04-10,AAPL (US0378331005) Cash Dividend EUR 1.00 per Share,10.00
    Withholding Tax,Header,Currency,Date,Description,Amount,Code
    Withholding Tax,Data,EUR,2025-04-10,AAPL (US0378331005) Cash Dividend EUR 1.00 per Share - US Tax,-1.50,R
""")


def test_portfolio_reconcile_writes_audit_tables(tmp_path):
    statement = tmp_path / "statement.csv"
    statement.write_text(_RECONCILE_CSV, encoding="utf-8")
    outdir = tmp_path / "outputs"

    code = run_portfolio_reconcile(
        file=str(statement),
        year=2025,
        outdir=str(outdir),
        output_format="table",
        fx_auto=True,
    )

    assert code == 0
    result_dir = outdir / "portfolio_reconcile_2025"
    assert (result_dir / "input_files.md").is_file()
    realized = (result_dir / "realized_reconciliation.md").read_text(encoding="utf-8")
    dividends = (result_dir / "dividend_reconciliation.md").read_text(encoding="utf-8")
    warnings = (result_dir / "warnings.md").read_text(encoding="utf-8")

    assert "Net gain / loss" in realized
    assert "+€196.00" in realized
    assert "Gross dividend income" in dividends
    assert "€10.00" in dividends
    assert "No reconciliation warnings" in warnings


def test_portfolio_reconcile_json_bundle_sections(tmp_path, capsys):
    statement = tmp_path / "statement.csv"
    statement.write_text(_RECONCILE_CSV, encoding="utf-8")

    code = run_portfolio_reconcile(
        file=str(statement),
        year=2025,
        outdir=str(tmp_path / "outputs"),
        output_format="json",
        fx_auto=True,
    )

    assert code == 0
    captured = capsys.readouterr()
    assert '"input_files"' in captured.out
    assert '"coverage_summary"' in captured.out
    assert '"realized_reconciliation"' in captured.out
    assert '"dividend_reconciliation"' in captured.out
    assert '"fx_coverage"' in captured.out


def test_reconcile_period_coverage_detects_statement_gaps():
    summaries = [
        {"period_start": date(2025, 1, 1), "period_end": date(2025, 3, 31)},
        {"period_start": date(2025, 5, 1), "period_end": date(2025, 12, 31)},
    ]

    assert _periods_cover_year(summaries, 2025) is False


def test_portfolio_tax_writes_kdvp_filing_rows(tmp_path):
    statement = tmp_path / "statement.csv"
    statement.write_text(_RECONCILE_CSV, encoding="utf-8")
    outdir = tmp_path / "outputs"

    code = run_portfolio_tax(
        file=str(statement),
        year=2025,
        outdir=str(outdir),
        output_format="table",
        fx_auto=True,
    )

    assert code == 0
    filing_rows = (
        outdir / "portfolio_tax_2025" / "kdvp_filing_rows_2025.md"
    ).read_text(encoding="utf-8")
    assert "Doh-KDVP" in filing_rows
    assert "f4 buy value eur" in filing_rows
    assert "IBKR fees included" in filing_rows


def test_portfolio_dividends_writes_filing_rows(tmp_path):
    statement = tmp_path / "statement.csv"
    statement.write_text(_RECONCILE_CSV, encoding="utf-8")
    outdir = tmp_path / "outputs"

    code = run_portfolio_dividends(
        file=str(statement),
        year=2025,
        outdir=str(outdir),
        output_format="table",
        fx_auto=True,
    )

    assert code == 0
    filing_rows = (
        outdir / "portfolio_dividends_2025" / "dividend_filing_rows_2025.md"
    ).read_text(encoding="utf-8")
    assert "Doh-Div" in filing_rows
    assert "estimated si topup eur" in filing_rows


def test_portfolio_interest_writes_filing_rows(tmp_path):
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="U1234567" fromDate="20250101" toDate="20251231">
              <AccountInformation currency="EUR" />
              <CashTransactions>
                <CashTransaction type="Broker Interest Received" currency="EUR"
                                 dateTime="20251031;000000" amount="30.00"
                                 description="EUR CREDIT INT FOR OCT-01 TO OCT-31" />
                <CashTransaction type="Withholding Tax" currency="EUR"
                                 dateTime="20251031;000000" amount="-6.00"
                                 description="WITHHOLDING @ 20% ON CREDIT INT FOR OCT-01 TO OCT-31" />
              </CashTransactions>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    statement = tmp_path / "flex.xml"
    statement.write_text(xml, encoding="utf-8")
    outdir = tmp_path / "outputs"

    code = run_portfolio_interest(
        file=str(statement),
        year=2025,
        outdir=str(outdir),
        output_format="table",
        fx_auto=True,
    )

    assert code == 0
    result_dir = outdir / "portfolio_interest_2025"
    interest_rows = (result_dir / "interest_2025.md").read_text(encoding="utf-8")
    filing_rows = (result_dir / "interest_filing_rows_2025.md").read_text(encoding="utf-8")
    summary = (result_dir / "interest_tax_summary.md").read_text(encoding="utf-8")
    assert "€30.00" in interest_rows
    assert "Doh-Obr" in filing_rows
    assert "€1.50" in summary


# ---------------------------------------------------------------------------
# FURS XML generator
# ---------------------------------------------------------------------------

def test_flex_lot_isin_and_description():
    """FlexLot parser populates isin and description from Lot XML attributes."""
    xml = _textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="X" fromDate="20250101" toDate="20251231">
              <Lots>
                <Lot symbol="ASML" description="ASML HOLDING NV" isin="NL0010273215"
                     assetCategory="STK" currency="EUR" buySell="SELL"
                     openDateTime="20250514;041538" dateTime="20250804;031250"
                     quantity="2" cost="1351.05" fifoPnlRealized="-149.26" />
              </Lots>
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
    """)
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(xml)
        fname = f.name
    try:
        lots, _, _ = load_flex_query(fname)
    finally:
        os.unlink(fname)

    assert lots[0].isin == "NL0010273215"
    assert lots[0].description == "ASML HOLDING NV"


def test_build_kdvp_xml_eur_security():
    """build_kdvp_xml produces correct KDVP elements for an EUR-denominated lot."""
    from valuation.portfolio.furs_xml import build_kdvp_xml

    lots = [
        FlexLot(
            symbol="ASML", currency="EUR",
            isin="NL0010273215", description="ASML HOLDING NV",
            acquired=date(2025, 5, 14), sold=date(2025, 8, 4),
            quantity=2.0, cost_native=1351.05, pnl_native=-149.26,
        )
    ]
    taxpayer = {"tax_number": "0", "name": "T", "email": "t@t.si", "phone": "0"}
    xml = build_kdvp_xml(lots, 2025, taxpayer)

    assert "Doh_KDVP_9" in xml
    assert "<ISIN>NL0010273215</ISIN>" in xml
    assert "<Code>ASML</Code>" in xml
    assert "<F2>B</F2>" in xml
    assert "<F5>0</F5>" in xml
    assert "<F8>2.0000</F8>" in xml   # balance after buy
    assert "<F8>0.0000</F8>" in xml   # balance after sell
    # F4 = 1351.05 / 2 = 675.525
    assert "<F4>675.5250</F4>" in xml
    # F9 = |1351.05 + (-149.26)| / 2 = 1201.79 / 2 = 600.895
    assert "<F9>600.8950</F9>" in xml


def test_build_kdvp_xml_non_eur_needs_fx():
    """build_kdvp_xml returns 0.0000 for F4/F9 when no FX rate available for non-EUR lot."""
    from valuation.portfolio.furs_xml import build_kdvp_xml

    lots = [
        FlexLot(
            symbol="GOOGL", currency="USD",
            isin="US02079K3059", description="ALPHABET INC-CL A",
            acquired=date(2024, 2, 1), sold=date(2025, 2, 4),
            quantity=10.0, cost_native=1409.53, pnl_native=642.0,
        )
    ]
    taxpayer = {"tax_number": "0", "name": "T", "email": "t@t.si", "phone": "0"}
    xml = build_kdvp_xml(lots, 2025, taxpayer, fx_rates=None)

    assert "<F4>0.0000</F4>" in xml
    assert "<F9>0.0000</F9>" in xml


def test_build_kdvp_xml_non_eur_with_fx():
    """build_kdvp_xml converts USD lot to EUR using provided FX rates."""
    from valuation.portfolio.furs_xml import build_kdvp_xml

    lots = [
        FlexLot(
            symbol="GOOGL", currency="USD",
            isin="US02079K3059", description="ALPHABET INC-CL A",
            acquired=date(2024, 2, 1), sold=date(2025, 2, 4),
            quantity=10.0, cost_native=1409.53, pnl_native=642.0,
        )
    ]
    taxpayer = {"tax_number": "0", "name": "T", "email": "t@t.si", "phone": "0"}
    fx_rates = {
        ("USD", "2024-02-01"): 0.9244,
        ("USD", "2025-02-04"): 0.9610,
    }
    xml = build_kdvp_xml(lots, 2025, taxpayer, fx_rates=fx_rates)

    # F4 = (1409.53 / 10) * 0.9244 = 140.953 * 0.9244 ≈ 130.27
    import re
    f4_match = re.search(r"<F4>([\d.]+)</F4>", xml)
    assert f4_match is not None
    assert abs(float(f4_match.group(1)) - 130.27) < 0.1


def test_build_div_xml_known_payer():
    """build_div_xml emits correct Dividend element with payer details from KNOWN_PAYERS."""
    from valuation.portfolio.furs_xml import build_div_xml
    from valuation.portfolio.ibkr import IbkrDividend

    divs = [
        IbkrDividend(
            symbol="GOOGL", currency="USD",
            payment_date=date(2025, 3, 17),
            amount=4.00, withholding_tax=0.60,
            description="GOOGL CASH DIVIDEND USD 0.20 PER SHARE - 15% TAX",
        )
    ]
    taxpayer = {"tax_number": "0", "name": "T", "email": "t@t.si", "phone": "0"}
    fx_rates = {("USD", "2025-03-17"): 0.92}
    xml = build_div_xml(divs, 2025, taxpayer, fx_rates)

    assert "Doh_Div_3" in xml
    assert "<Date>2025-03-17</Date>" in xml
    assert "<Type>1</Type>" in xml
    assert "Alphabet Inc." in xml
    assert "<Value>3.68</Value>" in xml   # 4.00 * 0.92 = 3.68
    assert "<ForeignTax>0.55</ForeignTax>" in xml  # 0.60 * 0.92 = 0.552 → 0.55


def test_build_obr_xml_ibkr_payer():
    """build_obr_xml emits correct Interest element with IBKR Ireland as payer."""
    from valuation.portfolio.furs_xml import build_obr_xml

    interest = [
        FlexInterest(
            currency="EUR",
            payment_date=date(2025, 3, 5),
            amount=30.97,
            withholding_tax=6.19,
            description="EUR CREDIT INT FOR FEB-2025",
        )
    ]
    taxpayer = {"tax_number": "0", "name": "T", "email": "t@t.si", "phone": "0"}
    xml = build_obr_xml(interest, 2025, taxpayer, {})

    assert "Doh_Obr_2" in xml
    assert "<Date>2025-03-05</Date>" in xml
    assert "<Type>2</Type>" in xml
    assert "Interactive Brokers Ireland Limited" in xml
    assert "<Value>30.97</Value>" in xml
    assert "<ForeignTax>6.19</ForeignTax>" in xml
    assert "<Country>IE</Country>" in xml
