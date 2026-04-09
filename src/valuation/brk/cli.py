"""CLI helpers for Berkshire-specific commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from valuation.brk.service import fetch_brk_overview
from valuation.brk.service import fetch_latest_brk_13f
from valuation.brk.tables import (
    build_13f_summary_table,
    build_key_facts_table,
    build_share_class_table,
    build_top_holdings_table,
    filter_core_filings_table,
)
from valuation.data.normalize.tables import (
    recent_filings_to_table,
    sec_company_to_table,
    snapshot_to_table,
)
from valuation.reports.tables import render_terminal_table, write_csv, write_markdown


def register_brk_parser(subparsers) -> None:
    """Register Berkshire-only CLI commands under the `brk` group."""
    brk_parser = subparsers.add_parser(
        "brk",
        help="Berkshire Hathaway-specific workflows.",
    )
    brk_subparsers = brk_parser.add_subparsers(dest="brk_command", required=True)

    overview_parser = brk_subparsers.add_parser(
        "overview",
        help="Fetch Berkshire-specific overview tables for valuation work.",
    )
    overview_parser.add_argument("--outdir", default="outputs/tables")
    overview_parser.add_argument(
        "--filings-limit",
        type=_non_negative_int,
        default=10,
        help="Number of Berkshire filings to show after filtering.",
    )

    holdings_parser = brk_subparsers.add_parser(
        "holdings",
        help="Fetch Berkshire's latest 13F holdings tables.",
    )
    holdings_parser.add_argument("--outdir", default="outputs/tables")
    holdings_parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=20,
        help="Number of top holdings rows to show.",
    )


def run_brk_command(args: argparse.Namespace) -> int:
    """Dispatch Berkshire subcommands."""
    if args.brk_command == "overview":
        return run_brk_overview(
            outdir=args.outdir,
            filings_limit=args.filings_limit,
        )
    if args.brk_command == "holdings":
        return run_brk_holdings(
            outdir=args.outdir,
            limit=args.limit,
        )
    raise ValueError(f"Unknown Berkshire command: {args.brk_command}")


def run_brk_overview(outdir: str, filings_limit: int) -> int:
    """Build Berkshire-oriented tables that are useful before full valuation exists."""
    bundle = fetch_brk_overview()

    sections = [
        ("Company", sec_company_to_table(bundle.company)),
        ("Share Classes", build_share_class_table(bundle.market_snapshot)),
        ("Market Snapshot", snapshot_to_table(bundle.market_snapshot)),
        ("Key SEC Facts", build_key_facts_table(bundle.company_facts)),
        (
            "Core Filings",
            filter_core_filings_table(
                recent_filings_to_table(bundle.submissions, limit=50),
                limit=filings_limit,
            ),
        ),
    ]

    _emit_sections(sections, Path(outdir) / "BRK")
    return 0


def run_brk_holdings(outdir: str, limit: int) -> int:
    """Build table outputs for Berkshire's latest 13F holdings."""
    bundle = fetch_latest_brk_13f()
    sections = [
        (
            "13F Summary",
            build_13f_summary_table(
                filing_date=bundle.filing_date,
                accession_number=bundle.accession_number,
                information_table_filename=bundle.information_table_filename,
                holdings=bundle.holdings,
            ),
        ),
        ("Top Holdings", build_top_holdings_table(bundle.holdings, limit=limit)),
    ]
    _emit_sections(sections, Path(outdir) / "BRK_13F")
    return 0


def _emit_sections(sections: Iterable[tuple[str, object]], output_dir: Path) -> None:
    for title, frame in sections:
        print(f"\n## {title}\n")
        print(render_terminal_table(frame))

    for name, frame in _named_tables(sections):
        write_csv(frame, output_dir / f"{name}.csv")
        write_markdown(frame, output_dir / f"{name}.md")

    print(f"\nWrote tables to {output_dir}")


def _named_tables(sections: Iterable[tuple[str, object]]):
    for title, frame in sections:
        slug = title.lower().replace(" ", "_")
        yield slug, frame


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed
