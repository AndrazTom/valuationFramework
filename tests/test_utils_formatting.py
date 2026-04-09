import pandas as pd

from valuation.notation import B, M
from valuation.utils.formatting import format_currency, format_percent, humanize_frame
from valuation.utils.scale import parse_scaled_number


def test_parse_scaled_number():
    assert parse_scaled_number("100B") == 100 * B
    assert parse_scaled_number("2.5M") == 2_500_000


def test_format_currency_uses_scaled_notation():
    assert format_currency(1_250_000_000) == "$1.25B"
    assert format_currency(479.75) == "$479.75"


def test_format_percent():
    assert format_percent(0.226006) == "22.6%"


def test_humanize_frame_formats_currency_and_percent_columns():
    frame = pd.DataFrame(
        [
            {
                "issuer": "APPLE INC",
                "value_usd": 61.961735283 * B,
                "portfolio_weight": 0.226006,
            }
        ]
    )

    display = humanize_frame(frame)

    assert display.iloc[0]["value_usd"] == "$61.96B"
    assert display.iloc[0]["portfolio_weight"] == "22.6%"


def test_humanize_frame_formats_metric_value_rows():
    frame = pd.DataFrame(
        [
            {"metric": "cash_and_equivalents", "value": 52.569 * B},
            {"metric": "portfolio_weight", "value": 0.226006},
            {"metric": "shares_outstanding", "value": 400 * M},
        ]
    )

    display = humanize_frame(frame)

    assert display.iloc[0]["value"] == "$52.57B"
    assert display.iloc[1]["value"] == "22.6%"
    assert display.iloc[2]["value"] == "400M"


def test_humanize_frame_formats_pandas_integer_scalars():
    frame = pd.DataFrame([{"field": "reported_value_usd", "value": pd.Series([274.160086701 * B], dtype="int64").iloc[0]}])

    display = humanize_frame(frame)

    assert display.iloc[0]["value"] == "$274.16B"
