"""CLI entrypoints for quick valuation data pulls."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

from valuation.company.service import fetch_company_snapshot
from valuation.company.tables import build_key_financials_table, resolution_to_table
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
        type=_non_negative_int,
        default=10,
        help="Number of recent SEC filings to show.",
    )

    company_parser = subparsers.add_parser(
        "company",
        help="Fetch a generic company snapshot from ticker, CIK, CUSIP, or ISIN.",
    )
    company_parser.add_argument("identifier")
    company_parser.add_argument(
        "--identifier-kind",
        choices=("auto", "ticker", "cik", "cusip", "isin"),
        default="auto",
    )
    company_parser.add_argument("--outdir", default="outputs/tables")
    company_parser.add_argument(
        "--filings-limit",
        type=_non_negative_int,
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

    _emit_sections(
        [
            ("Company", company_table),
            ("Market Snapshot", snapshot_table),
            ("Recent Filings", filings_table),
        ],
        Path(outdir) / ticker.upper().replace(".", "-"),
    )
    return 0


def run_company(identifier: str, identifier_kind: str, outdir: str, filings_limit: int) -> int:
    """Fetch a generic company view from a flexible identifier input."""
    bundle = fetch_company_snapshot(
        identifier,
        identifier_kind=identifier_kind,
    )
    _emit_sections(
        [
            ("Resolution", resolution_to_table(bundle.resolution)),
            ("Company", sec_company_to_table(bundle.resolution.sec_company)),
            ("Market Snapshot", snapshot_to_table(bundle.market_snapshot)),
            ("Key Financials", build_key_financials_table(bundle.company_facts)),
            ("Recent Filings", recent_filings_to_table(bundle.submissions, limit=filings_limit)),
        ],
        Path(outdir) / bundle.resolution.ticker.upper().replace(".", "-"),
    )
    return 0


def _named_tables(sections: Iterable[tuple[str, object]]):
    """Yield stable file-friendly names for output sections."""
    for title, frame in sections:
        slug = title.lower().replace(" ", "_")
        yield slug, frame


def _emit_sections(sections: Iterable[tuple[str, object]], output_dir: Path) -> None:
    for title, frame in sections:
        print(f"\n## {title}\n")
        print(render_terminal_table(frame))

    for name, frame in _named_tables(sections):
        write_csv(frame, output_dir / f"{name}.csv")
        write_markdown(frame, output_dir / f"{name}.md")

    print(f"\nWrote tables to {output_dir}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "snapshot":
            return run_snapshot(
                ticker=args.ticker,
                outdir=args.outdir,
                filings_limit=args.filings_limit,
            )
        if args.command == "company":
            return run_company(
                identifier=args.identifier,
                identifier_kind=args.identifier_kind,
                outdir=args.outdir,
                filings_limit=args.filings_limit,
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.error("Unknown command")
    return 2


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
