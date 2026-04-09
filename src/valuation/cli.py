"""CLI entrypoints for quick valuation data pulls."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

from valuation.company.service import fetch_company_facts, fetch_company_snapshot
from valuation.company.statements import build_statement_table
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

    statements_parser = subparsers.add_parser(
        "statements",
        help="Fetch generic financial statement tables from SEC companyfacts.",
    )
    statements_parser.add_argument("identifier")
    statements_parser.add_argument(
        "--identifier-kind",
        choices=("auto", "ticker", "cik", "cusip", "isin"),
        default="auto",
    )
    statements_parser.add_argument(
        "--statement",
        choices=("income", "balance", "cashflow"),
        default="income",
    )
    statements_parser.add_argument(
        "--period",
        choices=("annual", "quarterly"),
        default="annual",
    )
    statements_parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=4,
        help="Number of periods to show.",
    )
    statements_parser.add_argument("--start-year", type=int)
    statements_parser.add_argument("--end-year", type=int)
    statements_parser.add_argument("--start-quarter", type=_quarter_int)
    statements_parser.add_argument("--end-quarter", type=_quarter_int)
    statements_parser.add_argument("--outdir", default="outputs/tables")
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


def run_statements(
    identifier: str,
    identifier_kind: str,
    statement: str,
    period: str,
    limit: int,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
    outdir: str,
) -> int:
    """Fetch one generic statement table from SEC companyfacts."""
    _validate_statement_range(
        period=period,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    bundle = fetch_company_facts(
        identifier,
        identifier_kind=identifier_kind,
    )
    statement_table = build_statement_table(
        bundle.company_facts,
        statement=statement,
        period=period,
        limit=limit,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    title = f"{statement.title()} Statement {period.title()}"
    _emit_sections(
        [
            ("Resolution", resolution_to_table(bundle.resolution)),
            ("Company", sec_company_to_table(bundle.resolution.sec_company)),
            (title, statement_table),
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
        if args.command == "statements":
            return run_statements(
                identifier=args.identifier,
                identifier_kind=args.identifier_kind,
                statement=args.statement,
                period=args.period,
                limit=args.limit,
                start_year=args.start_year,
                end_year=args.end_year,
                start_quarter=args.start_quarter,
                end_quarter=args.end_quarter,
                outdir=args.outdir,
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


def _quarter_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1 or parsed > 4:
        raise argparse.ArgumentTypeError("quarter must be between 1 and 4")
    return parsed


def _validate_statement_range(
    *,
    period: str,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> None:
    if period != "quarterly" and (start_quarter is not None or end_quarter is not None):
        raise ValueError("quarter bounds are only valid with --period quarterly")
    if start_quarter is not None and start_year is None:
        raise ValueError("--start-quarter requires --start-year")
    if end_quarter is not None and end_year is None:
        raise ValueError("--end-quarter requires --end-year")
    if start_year is not None and end_year is not None:
        start_boundary = (start_year, start_quarter or 1)
        end_boundary = (end_year, end_quarter or 4)
        if start_boundary > end_boundary:
            raise ValueError("statement range start must be before or equal to range end")


if __name__ == "__main__":
    raise SystemExit(main())
