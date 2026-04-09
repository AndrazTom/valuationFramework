"""Table rendering helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from tabulate import tabulate

from valuation.utils.formatting import humanize_frame


def render_terminal_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "(no rows)"
    display = humanize_frame(frame)
    return tabulate(display.fillna(""), headers="keys", tablefmt="github", showindex=False)


def render_markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "(no rows)\n"
    display = humanize_frame(frame)
    return display.fillna("").to_markdown(index=False) + "\n"


def write_csv(frame: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def write_markdown(frame: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_markdown_table(frame), encoding="utf-8")
