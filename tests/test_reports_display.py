import pandas as pd

from valuation.reports.tables import render_terminal_table


def test_render_terminal_table_uses_compact_headers():
    frame = pd.DataFrame(
        [
            {
                "segment": "Insurance Group",
                "earnings_before_income_taxes_usd": 24_720_000_000,
                "depreciation_and_amortization_usd": 438_000_000,
            }
        ]
    )

    rendered = render_terminal_table(frame)

    assert "pre-tax earnings" in rendered
    assert "depr & amort" in rendered
