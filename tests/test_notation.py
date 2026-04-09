from valuation.notation import B, M, format_scaled_currency, format_scaled_number
from valuation.notation import parse_scaled_number


def test_parse_scaled_number():
    assert parse_scaled_number("100B") == 100 * B
    assert parse_scaled_number("2.5M") == 2.5 * M


def test_format_scaled_currency_uses_trimmed_suffixes():
    assert format_scaled_currency(61.961735283 * B) == "$61.96B"
    assert format_scaled_currency(-1.25 * B) == "-$1.25B"


def test_format_scaled_number_uses_trimmed_suffixes():
    assert format_scaled_number(400 * M) == "400M"
    assert format_scaled_number(227.917808 * M) == "227.92M"
