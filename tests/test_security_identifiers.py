import pandas as pd

from valuation.securities.identifiers import build_security_id, identify_security
from valuation.securities.identifiers import with_security_ids


def test_build_security_id_prefers_cusip():
    assert build_security_id(cusip="037833100", ticker="AAPL", exchange="NASDAQ") == "cusip:037833100"


def test_build_security_id_uses_exchange_and_ticker_when_needed():
    assert build_security_id(ticker="BRK-B", exchange="NYSE") == "ticker:NYSE:BRK-B"


def test_identify_security_normalizes_fields():
    identifier = identify_security(ticker=" brk-b ", exchange="nyse", issuer=" Berkshire Hathaway Inc ")

    assert identifier is not None
    assert identifier.security_id == "ticker:NYSE:BRK-B"
    assert identifier.ticker == "brk-b"
    assert identifier.exchange == "nyse"
    assert identifier.issuer == "Berkshire Hathaway Inc"


def test_with_security_ids_adds_canonical_id_column():
    frame = pd.DataFrame(
        [
            {"ticker": "BRK-B", "exchange": "NYSE"},
            {"cusip": "037833100", "issuer": "APPLE INC"},
        ]
    )

    enriched = with_security_ids(
        frame,
        ticker_column="ticker",
        exchange_column="exchange",
        cusip_column="cusip",
    )

    assert list(enriched["security_id"]) == [
        "ticker:NYSE:BRK-B",
        "cusip:037833100",
    ]
