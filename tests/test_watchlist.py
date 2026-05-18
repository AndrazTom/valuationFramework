"""Tests for watchlist persistence helpers."""

import pytest

from valuation.watchlist import (
    add_ticker,
    load_tickers,
    remove_ticker,
    save_tickers,
    _parse_toml_simple,
)


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "wl.toml"
    save_tickers(["AAPL", "MSFT", "BRK-B"], path=path)
    result = load_tickers(path=path)
    assert result == ["AAPL", "MSFT", "BRK-B"]


def test_load_missing_file_returns_empty(tmp_path):
    path = tmp_path / "nonexistent.toml"
    assert load_tickers(path=path) == []


def test_add_ticker_appends(tmp_path):
    path = tmp_path / "wl.toml"
    add_ticker("AAPL", path=path)
    add_ticker("MSFT", path=path)
    assert load_tickers(path=path) == ["AAPL", "MSFT"]


def test_add_ticker_deduplicates_case_insensitive(tmp_path):
    path = tmp_path / "wl.toml"
    add_ticker("AAPL", path=path)
    add_ticker("aapl", path=path)
    assert load_tickers(path=path) == ["AAPL"]


def test_remove_ticker(tmp_path):
    path = tmp_path / "wl.toml"
    save_tickers(["AAPL", "MSFT", "GOOG"], path=path)
    remove_ticker("MSFT", path=path)
    assert load_tickers(path=path) == ["AAPL", "GOOG"]


def test_remove_missing_ticker_is_noop(tmp_path):
    path = tmp_path / "wl.toml"
    save_tickers(["AAPL"], path=path)
    result = remove_ticker("XYZ", path=path)
    assert result == ["AAPL"]
    assert load_tickers(path=path) == ["AAPL"]


def test_parse_toml_simple():
    text = '# comment\ntickers = [\n  "AAPL",\n  "MSFT",\n]\n'
    assert _parse_toml_simple(text) == ["AAPL", "MSFT"]


def test_parse_toml_simple_empty():
    assert _parse_toml_simple("tickers = [\n]\n") == []
