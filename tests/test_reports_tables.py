from pathlib import Path

import pandas as pd

from valuation.notation import B
from valuation.reports.tables import (
    frame_to_records,
    render_markdown_table,
    render_terminal_table,
    write_csv,
    write_markdown,
)


def test_render_terminal_table_for_empty_frame():
    assert render_terminal_table(pd.DataFrame()) == "(no rows)"


def test_render_markdown_table_for_non_empty_frame():
    frame = pd.DataFrame(
        [
            {"field": "ticker", "value": "BRK-B"},
            {"field": "reported_value_usd", "value": 274.160086701 * B},
        ]
    )

    rendered = render_markdown_table(frame)

    assert "| field" in rendered
    assert "BRK-B" in rendered
    assert "$274.16B" in rendered


def test_write_csv_and_markdown(tmp_path: Path):
    frame = pd.DataFrame([{"field": "ticker", "value": "BRK-B"}])
    csv_path = tmp_path / "tables" / "company.csv"
    md_path = tmp_path / "tables" / "company.md"

    write_csv(frame, csv_path)
    write_markdown(frame, md_path)

    assert csv_path.exists()
    assert md_path.exists()
    assert "BRK-B" in md_path.read_text(encoding="utf-8")


def test_render_terminal_table_formats_statement_period_values():
    frame = pd.DataFrame(
        [
            {
                "metric": "revenue",
                "unit": "USD",
                "FY 2025": 1500000000.0,
            }
        ]
    )

    rendered = render_terminal_table(frame, max_width=120)

    assert "1.5B" in rendered


def test_render_terminal_table_uses_statement_unit_for_non_us_currency():
    frame = pd.DataFrame(
        [
            {
                "metric": "revenue",
                "unit": "EUR",
                "FY 2025": 1500000000.0,
            }
        ]
    )

    rendered = render_terminal_table(frame, max_width=120)

    assert "EUR 1.5B" in rendered


def test_render_terminal_table_uses_snapshot_currency_hint():
    frame = pd.DataFrame(
        [
            {"field": "currency", "value": "EUR"},
            {"field": "last_price", "value": 89.49},
        ]
    )

    rendered = render_terminal_table(frame)

    assert "EUR 89.49" in rendered


def test_render_terminal_table_formats_snapshot_market_cap_after_label_humanizing():
    frame = pd.DataFrame(
        [
            {"field": "currency", "value": "USD"},
            {"field": "market_cap", "value": 4_409_585_053_240.112},
        ]
    )

    rendered = render_terminal_table(frame)

    assert "$4.41T" in rendered


def test_frame_to_records_converts_missing_values_to_none():
    frame = pd.DataFrame([{"field": "ticker", "value": "BRK-B", "note": None, "missing_number": float("nan")}])

    records = frame_to_records(frame)

    assert records == [
        {"field": "ticker", "value": "BRK-B", "note": None, "missing_number": None}
    ]


def test_render_terminal_table_uses_new_filing_and_availability_aliases():
    frame = pd.DataFrame(
        [
            {
                "report_date": "2025-12-31",
                "form_group": "annual_report",
                "period_count": 5,
                "metric_count": 7,
            }
        ]
    )

    rendered = render_terminal_table(frame)

    assert "report date" in rendered
    assert "category" in rendered
    assert "periods" in rendered
    assert "metrics" in rendered


def test_render_terminal_table_drops_secondary_columns_to_fit_width():
    frame = pd.DataFrame(
        [
            {
                "metric": "revenue",
                "value": 100.0,
                "status": "available",
                "source_table": "companyfacts",
                "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
            }
        ]
    )

    rendered = render_terminal_table(frame, max_width=80)

    assert "revenue" in rendered
    assert "available" in rendered
    assert "source table" not in rendered
    assert "concept" not in rendered

    markdown = render_markdown_table(frame)

    assert "source table" in markdown
    assert "concept" in markdown


def test_render_terminal_table_drops_old_period_columns_to_fit_width():
    frame = pd.DataFrame(
        [
            {
                "metric": "revenue",
                "unit": "USD",
                "FY 2025": 100.0,
                "FY 2024": 90.0,
                "FY 2023": 80.0,
                "FY 2022": 70.0,
                "FY 2021": 60.0,
            }
        ]
    )

    rendered = render_terminal_table(frame, max_width=72)

    assert "FY 2025" in rendered
    assert "FY 2024" in rendered
    assert "FY 2021" not in rendered
    assert max(len(line) for line in rendered.splitlines()) <= 72

    markdown = render_markdown_table(frame)

    assert "FY 2021" in markdown


def test_render_terminal_table_uses_compact_value_aliases():
    frame = pd.DataFrame(
        [
            {"field": "residual_to_segment_pretax_earnings", "value": 7.2},
            {"field": "short_term_us_treasury_bills", "value": 286_000_000_000.0},
        ]
    )

    rendered = render_terminal_table(frame)

    assert "residual / pretax earnings" in rendered
    assert "T-bills" in rendered
