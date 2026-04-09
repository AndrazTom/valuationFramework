"""CLI entrypoints for quick valuation data pulls."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from valuation.data.normalize.tables import (
    recent_filings_to_table,
    sec_company_to_table,
    snapshot_to_table,
)
from valuation.data.providers.sec import SecClient
from valuation.data.providers.yahoo import YahooFinanceClient
from valuation.reports.tables import (
    render_terminal_table,
    write_csv,
    write_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="valuation framework CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Fetch a market snapshot and SEC metadata for one ticker.",
    )
    snapshot_parser.add_argument("ticker")
    snapshot_parser.add_argument("--outdir", default="outputs/tables")
    snapshot_parser.add_argument(
        "--filings-limit",
        type=int,
        default=10,
        help="Number of recent SEC filings to show.",
    )
    return parser


def run_snapshot(ticker: str, outdir: str, filings_limit: int) -> int:
    """Fetch one ticker, print quick tables, and persist the same tables to disk."""
    yahoo = YahooFinanceClient()
    sec = SecClient()

    market_snapshot = yahoo.fetch_price_snapshot(ticker)
    company_bundle = sec.fetch_company_bundle(ticker)

    company_table = sec_company_to_table(company_bundle["company"])
    snapshot_table = snapshot_to_table(market_snapshot)
    filings_table = recent_filings_to_table(
        company_bundle["submissions"],
        limit=filings_limit,
    )

    sections = [
        ("Company", company_table),
        ("Market Snapshot", snapshot_table),
        ("Recent Filings", filings_table),
    ]

    for title, frame in sections:
        print(f"\n## {title}\n")
        print(render_terminal_table(frame))

    output_dir = Path(outdir) / ticker.upper().replace(".", "-")
    # Keep filenames deterministic so later tooling can read generated tables.
    for name, frame in _named_tables(sections):
        write_csv(frame, output_dir / f"{name}.csv")
        write_markdown(frame, output_dir / f"{name}.md")

    print(f"\nWrote tables to {output_dir}")
    return 0


def _named_tables(sections: Iterable[tuple[str, object]]):
    """Yield stable file-friendly names for output sections."""
    for title, frame in sections:
        slug = title.lower().replace(" ", "_")
        yield slug, frame


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "snapshot":
            return run_snapshot(
                ticker=args.ticker,
                outdir=args.outdir,
                filings_limit=args.filings_limit,
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
