from pathlib import Path

import pandas as pd

from valuation.reports.tables import (
    render_markdown_table,
    render_terminal_table,
    write_csv,
    write_markdown,
)


def test_render_terminal_table_for_empty_frame():
    assert render_terminal_table(pd.DataFrame()) == "(no rows)"


def test_render_markdown_table_for_non_empty_frame():
    frame = pd.DataFrame([{"field": "ticker", "value": "BRK-B"}])

    rendered = render_markdown_table(frame)

    assert "| field" in rendered
    assert "BRK-B" in rendered


def test_write_csv_and_markdown(tmp_path: Path):
    frame = pd.DataFrame([{"field": "ticker", "value": "BRK-B"}])
    csv_path = tmp_path / "tables" / "company.csv"
    md_path = tmp_path / "tables" / "company.md"

    write_csv(frame, csv_path)
    write_markdown(frame, md_path)

    assert csv_path.exists()
    assert md_path.exists()
    assert "BRK-B" in md_path.read_text(encoding="utf-8")
