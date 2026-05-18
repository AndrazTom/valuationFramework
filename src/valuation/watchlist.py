"""Persistent ticker watchlist backed by a plain TOML file."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

_DEFAULT_PATH = Path.home() / ".config" / "valuationFramework" / "watchlist.toml"


def watchlist_path() -> Path:
    return _DEFAULT_PATH


def load_tickers(path: Path | None = None) -> list[str]:
    """Return the current watchlist, preserving insertion order."""
    p = path or watchlist_path()
    if not p.exists():
        return []
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return _parse_toml_simple(p.read_text(encoding="utf-8"))
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return list(data.get("tickers", []))


def save_tickers(tickers: Sequence[str], path: Path | None = None) -> None:
    p = path or watchlist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# valuationFramework watchlist\n", "tickers = [\n"]
    for t in tickers:
        lines.append(f'  "{t}",\n')
    lines.append("]\n")
    p.write_text("".join(lines), encoding="utf-8")


def add_ticker(ticker: str, path: Path | None = None) -> list[str]:
    """Add ticker if not already present; return updated list."""
    tickers = load_tickers(path)
    upper = ticker.upper()
    if upper not in (t.upper() for t in tickers):
        tickers.append(ticker)
        save_tickers(tickers, path)
    return tickers


def remove_ticker(ticker: str, path: Path | None = None) -> list[str]:
    """Remove ticker (case-insensitive); return updated list."""
    tickers = load_tickers(path)
    updated = [t for t in tickers if t.upper() != ticker.upper()]
    if len(updated) != len(tickers):
        save_tickers(updated, path)
    return updated


def _parse_toml_simple(text: str) -> list[str]:
    """Minimal TOML list parser used when tomllib/tomli is unavailable."""
    tickers: list[str] = []
    in_list = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("tickers"):
            in_list = True
            continue
        if in_list:
            if stripped.startswith("]"):
                break
            val = stripped.strip('",').strip("'")
            if val:
                tickers.append(val)
    return tickers
