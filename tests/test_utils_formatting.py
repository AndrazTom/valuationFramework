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


def test_humanize_frame_formats_pct_suffix_columns():
    frame = pd.DataFrame(
        [
            {
                "issuer": "APPLE INC",
                "price_change_pct": 0.125,
            }
        ]
    )

    display = humanize_frame(frame)

    assert display.iloc[0]["price_change_pct"] == "12.5%"


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


def test_humanize_frame_keeps_position_counts_as_quantities():
    frame = pd.DataFrame(
        [
            {"field": "positions_with_live_price", "value": 24},
            {"field": "market_value_live_resolved_usd", "value": 269.77 * B},
        ]
    )

    display = humanize_frame(frame)

    assert display.iloc[0]["value"] == "24"
    assert display.iloc[1]["value"] == "$269.77B"


def test_humanize_frame_formats_share_change_columns_as_quantities():
    frame = pd.DataFrame(
        [
            {
                "issuer": "APPLE INC",
                "shares_change_from_prior_filing": -10_295_000,
            }
        ]
    )

    display = humanize_frame(frame)

    assert display.iloc[0]["shares_change_from_prior_filing"] == "-10.29M"


def test_humanize_frame_formats_field_pct_ratio_and_usd_suffixes():
    frame = pd.DataFrame(
        [
            {"field": "brk_b_price_change_pct", "value": -0.032},
            {"field": "13f_live_coverage_ratio", "value": 0.983},
            {"field": "resolved_positions_reported_value_usd", "value": 269.51 * B},
        ]
    )

    display = humanize_frame(frame)

    assert display.iloc[0]["value"] == "-3.2%"
    assert display.iloc[1]["value"] == "98.3%"
    assert display.iloc[2]["value"] == "$269.51B"


def test_humanize_frame_prioritizes_usd_columns_over_metric_name():
    frame = pd.DataFrame(
        [
            {"metric": "short_term_us_treasury_bills", "value_usd": 305.367 * B},
            {"metric": "fixed_maturity_securities", "value_usd": 17.943 * B},
        ]
    )

    display = humanize_frame(frame)

    assert display.iloc[0]["value_usd"] == "$305.37B"
    assert display.iloc[1]["value_usd"] == "$17.94B"


def test_humanize_frame_prioritizes_weight_columns_over_metric_name():
    frame = pd.DataFrame(
        [
            {
                "metric": "short_term_us_treasury_bills",
                "market_cap_weight": 0.3105,
            }
        ]
    )

    display = humanize_frame(frame)

    assert display.iloc[0]["market_cap_weight"] == "31.1%"
