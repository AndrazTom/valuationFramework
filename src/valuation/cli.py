"""CLI entrypoints for quick valuation data pulls."""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Optional, Sequence

from valuation.brk.cli import register_brk_parser, run_brk_command
from valuation.brk.statements import supplement_brk_income_statement_eps_shares
from valuation.portfolio.cli import (
    run_portfolio_dividends,
    run_portfolio_furs_xml,
    run_portfolio_gains,
    run_portfolio_interest,
    run_portfolio_reconcile,
)
from valuation.company.service import fetch_company_facts, fetch_company_snapshot
from valuation.company.statements import build_statement_diagnostics_table, build_statement_table, build_statement_table_ttm
from valuation.company.tables import (
    build_implied_value_range_table,
    build_key_financials_table,
    build_reverse_dcf_table,
    build_sec_overview_table,
    build_sec_statement_availability_table,
    build_valuation_ratios_table,
    build_yahoo_overview_table,
    build_yahoo_snapshot_key_financials_table,
    build_yahoo_statement_availability_table,
    company_summary_to_table,
    extract_financials_from_company_facts,
    extract_financials_from_yahoo_frames,
    extract_financials_ttm_from_company_facts,
    extract_financials_ttm_from_yahoo_frames,
    extract_period_label_from_company_facts,
    resolution_to_table,
)
from valuation.company.comps import build_comps_table, fetch_comps_entries
from valuation.company.ratios import (
    build_historical_ratios_table,
    build_historical_ratios_table_from_yahoo,
)
from valuation.watchlist import add_ticker, load_tickers, remove_ticker, watchlist_path
from valuation.company.yahoo_statements import build_yahoo_statement_table
from valuation.data.normalize.tables import (
    CORE_COMPANY_FILING_FORMS,
    recent_filings_to_table,
    sec_company_to_table,
    snapshot_to_table,
)
from valuation.config import load_project_env
from valuation.data.providers.sec import SecClient
from valuation.data.providers.yahoo import YahooFinanceClient
from valuation.reports.tables import (
    frame_to_records,
    render_terminal_table,
    write_csv,
    write_json,
    write_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="valuation framework CLI")
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Bypass provider cache for this run and overwrite cached SEC/Yahoo payloads.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Fetch a market snapshot and SEC metadata for one ticker.",
    )
    snapshot_parser.add_argument("ticker")
    snapshot_parser.add_argument("--outdir", default="outputs/tables")
    snapshot_parser.add_argument("--format", choices=("table", "json"), default="table")
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
    company_parser.add_argument("--format", choices=("table", "json"), default="table")
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
        choices=("annual", "quarterly", "ttm"),
        default="annual",
    )
    statements_parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=None,
        help="Number of periods to show.",
    )
    statements_parser.add_argument("--start-year", type=int)
    statements_parser.add_argument("--end-year", type=int)
    statements_parser.add_argument("--start-quarter", type=_quarter_int)
    statements_parser.add_argument("--end-quarter", type=_quarter_int)
    statements_parser.add_argument("--outdir", default="outputs/tables")
    statements_parser.add_argument("--format", choices=("table", "json"), default="table")
    statements_parser.add_argument(
        "--diagnostics",
        "--include-missing",
        action="store_true",
        help="Include a diagnostic table explaining expected statement rows that are missing or stale.",
    )

    ratios_parser = subparsers.add_parser(
        "ratios",
        help="Show historical per-fiscal-year valuation ratios (P/E, P/OE, EV/EBITDA, ...).",
    )
    ratios_parser.add_argument("identifier")
    ratios_parser.add_argument(
        "--identifier-kind",
        choices=("auto", "ticker", "cik", "cusip", "isin"),
        default="auto",
    )
    ratios_parser.add_argument("--limit", type=_non_negative_int, default=10)
    ratios_parser.add_argument("--outdir", default="outputs/tables")
    ratios_parser.add_argument("--format", choices=("table", "json"), default="table")

    comps_parser = subparsers.add_parser(
        "comps",
        help="Compare multiple securities side-by-side on TTM valuation metrics.",
    )
    comps_parser.add_argument("tickers", nargs="+", help="Two or more tickers to compare.")
    comps_parser.add_argument("--outdir", default="outputs/tables")
    comps_parser.add_argument("--format", choices=("table", "json"), default="table")

    watchlist_parser = subparsers.add_parser(
        "watchlist",
        help="Manage a persistent ticker watchlist and compare all tickers side-by-side.",
    )
    watchlist_sub = watchlist_parser.add_subparsers(dest="watchlist_command", required=True)
    wl_add = watchlist_sub.add_parser("add", help="Add one or more tickers to the watchlist.")
    wl_add.add_argument("tickers", nargs="+")
    wl_remove = watchlist_sub.add_parser("remove", help="Remove one or more tickers from the watchlist.")
    wl_remove.add_argument("tickers", nargs="+")
    watchlist_sub.add_parser("list", help="Print the current watchlist.")
    wl_show = watchlist_sub.add_parser("show", help="Run comps on all watchlist tickers.")
    wl_show.add_argument("--outdir", default="outputs/tables")
    wl_show.add_argument("--format", choices=("table", "json"), default="table")

    register_brk_parser(subparsers)
    _register_portfolio_parser(subparsers)
    return parser


def _register_portfolio_parser(subparsers) -> None:
    portfolio_parser = subparsers.add_parser(
        "portfolio",
        help="IBKR portfolio: open positions, unrealized P&L, and Slovenian CGT.",
    )
    portfolio_sub = portfolio_parser.add_subparsers(dest="portfolio_command", required=True)

    _flex_file_help = "Path to IBKR Flex Query XML. Falls back to IBKR_FLEX_PATH env var."

    gains_parser = portfolio_sub.add_parser(
        "gains",
        help="Show realized gains for a year and compute Slovenian CGT owed.",
    )
    gains_parser.add_argument("--file", metavar="PATH", help=_flex_file_help)
    gains_parser.add_argument(
        "--year", type=int, default=None,
        help="Tax year to report (default: current calendar year).",
    )
    gains_parser.add_argument("--outdir", default="outputs/tables")
    gains_parser.add_argument("--format", choices=("table", "json"), default="table")
    gains_parser.add_argument(
        "--no-fx-auto", action="store_false", dest="fx_auto", default=True,
        help="Disable automatic ECB historical FX rate fetching (on by default).",
    )
    gains_parser.add_argument(
        "--show-fees", action="store_true", default=False,
        help="Add buy_fee and sell_fee columns showing commissions separately (requires ibCommission in Flex Query).",
    )

    div_parser = portfolio_sub.add_parser(
        "dividends",
        help="Show dividend income for a year and compute Slovenian dividend tax.",
    )
    div_parser.add_argument("--file", metavar="PATH", help=_flex_file_help)
    div_parser.add_argument(
        "--year", type=int, default=None,
        help="Tax year to report (default: current calendar year).",
    )
    div_parser.add_argument("--outdir", default="outputs/tables")
    div_parser.add_argument("--format", choices=("table", "json"), default="table")

    interest_parser = portfolio_sub.add_parser(
        "interest",
        help="Show broker interest income for a year.",
    )
    interest_parser.add_argument("--file", metavar="PATH", help=_flex_file_help)
    interest_parser.add_argument(
        "--year", type=int, default=None,
        help="Tax year to report (default: current calendar year).",
    )
    interest_parser.add_argument("--outdir", default="outputs/tables")
    interest_parser.add_argument("--format", choices=("table", "json"), default="table")
    interest_parser.add_argument(
        "--no-fx-auto", action="store_false", dest="fx_auto", default=True,
        help="Disable automatic ECB historical FX rate fetching (on by default).",
    )

    reconcile_parser = portfolio_sub.add_parser(
        "reconcile",
        help="Reconcile Flex Query rows to yearly gains/dividend/interest totals.",
    )
    reconcile_parser.add_argument("--file", metavar="PATH", help=_flex_file_help)
    reconcile_parser.add_argument(
        "--year", type=int, default=None,
        help="Tax year to reconcile (default: current calendar year).",
    )
    reconcile_parser.add_argument("--outdir", default="outputs/tables")
    reconcile_parser.add_argument("--format", choices=("table", "json"), default="table")
    reconcile_parser.add_argument(
        "--no-fx-auto", action="store_false", dest="fx_auto", default=True,
        help="Disable automatic ECB historical FX rate fetching (on by default).",
    )

    furs_parser = portfolio_sub.add_parser(
        "furs-xml",
        help="Generate FURS eDavki XML forms (Doh-KDVP, Doh-Div, Doh-Obr).",
    )
    furs_parser.add_argument("--file", metavar="PATH", help=_flex_file_help)
    furs_parser.add_argument(
        "--year", type=int, default=None,
        help="Tax year (default: current calendar year).",
    )
    furs_parser.add_argument(
        "--forms", choices=("all", "kdvp", "div", "obr"), default="all",
        help="Which forms to generate (default: all).",
    )
    furs_parser.add_argument("--outdir", default="outputs/tables")
    furs_parser.add_argument(
        "--no-fx-auto", action="store_false", dest="fx_auto", default=True,
        help="Disable automatic ECB historical FX rate fetching (on by default).",
    )


def run_snapshot(ticker: str, outdir: str, filings_limit: int, output_format: str) -> int:
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
        output_format=output_format,
        command="snapshot",
    )
    return 0


def run_company(identifier: str, identifier_kind: str, outdir: str, filings_limit: int, output_format: str) -> int:
    """Fetch a generic company view from a flexible identifier input."""
    bundle = fetch_company_snapshot(
        identifier,
        identifier_kind=identifier_kind,
    )
    company_currency = str(
        getattr(bundle.resolution, "currency", None)
        or (bundle.company_profile or {}).get("currency")
        or "USD"
    )
    sections = [
        ("Resolution", resolution_to_table(bundle.resolution)),
        ("Company", company_summary_to_table(bundle.resolution, company_profile=bundle.company_profile)),
        ("Market Snapshot", snapshot_to_table(bundle.market_snapshot)),
    ]
    if bundle.company_facts:
        sections.append(
            (
                "Overview",
                build_sec_overview_table(
                    market_snapshot=bundle.market_snapshot,
                    company_facts=bundle.company_facts,
                    currency=company_currency,
                ),
            )
        )
        sections.append(("Key Financials", build_key_financials_table(bundle.company_facts)))
        _ttm_financials, _ttm_label = extract_financials_ttm_from_company_facts(bundle.company_facts)
        _ratio_label = _ttm_label or extract_period_label_from_company_facts(bundle.company_facts)
        sections.append(
            (
                "Valuation Ratios",
                build_valuation_ratios_table(
                    bundle.market_snapshot,
                    _ttm_financials,
                    period_label=_ratio_label,
                ),
            )
        )
        _oe_range = build_implied_value_range_table(
            bundle.market_snapshot, _ttm_financials, period_label=_ratio_label
        )
        if not _oe_range.empty:
            sections.append(("Implied Value Range (P/OE)", _oe_range))
        _rdcf = build_reverse_dcf_table(
            bundle.market_snapshot, _ttm_financials, period_label=_ratio_label
        )
        if not _rdcf.empty:
            sections.append(("Reverse DCF", _rdcf))
        sections.append(("Statement Availability", build_sec_statement_availability_table(bundle.company_facts)))
    elif bundle.company_profile:
        yahoo = YahooFinanceClient()
        requests = [
            ("income", "annual"),
            ("income", "quarterly"),
            ("balance", "annual"),
            ("balance", "quarterly"),
            ("cashflow", "annual"),
            ("cashflow", "quarterly"),
        ]
        with ThreadPoolExecutor(max_workers=len(requests)) as executor:
            futures = {
                request: executor.submit(
                    yahoo.fetch_statement_frame,
                    bundle.resolution.ticker,
                    statement=request[0],
                    period=request[1],
                )
                for request in requests
            }
        frames = {request: future.result() for request, future in futures.items()}
        sections.append(
            (
                "Overview",
                build_yahoo_overview_table(
                    market_snapshot=bundle.market_snapshot,
                    income_frame=frames[("income", "annual")],
                    balance_frame=frames[("balance", "annual")],
                    cashflow_frame=frames[("cashflow", "annual")],
                    currency=company_currency,
                ),
            )
        )
        sections.append(
            (
                "Key Financials",
                build_yahoo_snapshot_key_financials_table(
                    income_frame=frames[("income", "annual")],
                    balance_frame=frames[("balance", "annual")],
                    cashflow_frame=frames[("cashflow", "annual")],
                    currency=company_currency,
                ),
            )
        )
        _yahoo_ttm_financials, _yahoo_ttm_label = extract_financials_ttm_from_yahoo_frames(
            income_annual=frames[("income", "annual")],
            balance_annual=frames[("balance", "annual")],
            cashflow_annual=frames[("cashflow", "annual")],
            income_quarterly=frames[("income", "quarterly")],
            balance_quarterly=frames[("balance", "quarterly")],
            cashflow_quarterly=frames[("cashflow", "quarterly")],
            currency=company_currency,
        )
        sections.append(
            (
                "Valuation Ratios",
                build_valuation_ratios_table(
                    bundle.market_snapshot,
                    _yahoo_ttm_financials,
                    period_label=_yahoo_ttm_label,
                ),
            )
        )
        _yahoo_oe_range = build_implied_value_range_table(
            bundle.market_snapshot, _yahoo_ttm_financials, period_label=_yahoo_ttm_label
        )
        if not _yahoo_oe_range.empty:
            sections.append(("Implied Value Range", _yahoo_oe_range))
        _yahoo_rdcf = build_reverse_dcf_table(
            bundle.market_snapshot, _yahoo_ttm_financials, period_label=_yahoo_ttm_label
        )
        if not _yahoo_rdcf.empty:
            sections.append(("Reverse DCF", _yahoo_rdcf))
        sections.append(
            (
                "Statement Availability",
                build_yahoo_statement_availability_table(
                    frames,
                    currency=company_currency,
                ),
            )
        )
    if bundle.submissions:
        sections.append(
            (
                "Recent Filings",
                recent_filings_to_table(
                    bundle.submissions,
                    limit=filings_limit,
                    preferred_forms=CORE_COMPANY_FILING_FORMS,
                ),
            )
        )
    _emit_sections(
        sections,
        Path(outdir) / bundle.resolution.ticker.upper().replace(".", "-"),
        output_format=output_format,
        command="company",
    )
    return 0


def run_ratios(
    identifier: str,
    identifier_kind: str,
    limit: int,
    outdir: str,
    output_format: str,
) -> int:
    """Fetch historical annual financials + price history and render per-year valuation ratios."""
    bundle = fetch_company_snapshot(identifier, identifier_kind=identifier_kind)
    ticker = bundle.resolution.ticker
    yahoo = YahooFinanceClient()

    price_history = yahoo.fetch_history(ticker, period="max", interval="1mo")

    if bundle.company_facts:
        table = build_historical_ratios_table(bundle.company_facts, price_history, limit=limit)
    elif bundle.company_profile:
        requests = [
            ("income", "annual"),
            ("balance", "annual"),
            ("cashflow", "annual"),
        ]
        with ThreadPoolExecutor(max_workers=len(requests)) as executor:
            futures = {
                r: executor.submit(yahoo.fetch_statement_frame, ticker, statement=r[0], period=r[1])
                for r in requests
            }
        frames = {r: f.result() for r, f in futures.items()}
        table = build_historical_ratios_table_from_yahoo(
            income_annual=frames[("income", "annual")],
            balance_annual=frames[("balance", "annual")],
            cashflow_annual=frames[("cashflow", "annual")],
            price_history=price_history,
            limit=limit,
        )
    else:
        print(f"Error: could not resolve {identifier!r}", file=sys.stderr)
        return 1

    if table.empty:
        print("Error: no historical ratio data available", file=sys.stderr)
        return 1

    slug = ticker.upper().replace(".", "-")
    _emit_sections(
        [("Historical Ratios", table)],
        Path(outdir) / slug,
        output_format=output_format,
        command="ratios",
    )
    return 0


def run_comps(tickers: list[str], outdir: str, output_format: str) -> int:
    """Fetch TTM valuation metrics for multiple tickers and render a side-by-side table."""
    entries = fetch_comps_entries(tickers)
    table = build_comps_table(entries)

    # Surface any per-ticker errors to stderr; drop the error column from display
    error_rows = table[table["error"].notna()] if "error" in table.columns else table.iloc[:0]
    for _, row in error_rows.iterrows():
        print(f"Warning: {row['ticker']}: {row['error']}", file=sys.stderr)

    display = table.drop(columns=["error"], errors="ignore")
    slug = "COMPS_" + "_".join(t.upper().replace(".", "-") for t in tickers[:6])
    out_path = Path(outdir) / slug
    _emit_sections(
        [("Comps", display)],
        out_path,
        output_format=output_format,
        command="comps",
    )
    return 0


def run_watchlist(args: argparse.Namespace, outdir: str = "outputs/tables", output_format: str = "table") -> int:
    """Manage the watchlist or run comps on all watchlist tickers."""
    cmd = args.watchlist_command
    if cmd == "add":
        for t in args.tickers:
            add_ticker(t)
        tickers = load_tickers()
        print(f"Watchlist ({len(tickers)}): {', '.join(tickers)}")
        return 0
    if cmd == "remove":
        for t in args.tickers:
            remove_ticker(t)
        tickers = load_tickers()
        print(f"Watchlist ({len(tickers)}): {', '.join(tickers) or '(empty)'}")
        return 0
    if cmd == "list":
        tickers = load_tickers()
        if not tickers:
            print(f"Watchlist is empty. Add tickers with: ./vf watchlist add AAPL MSFT")
            print(f"Stored at: {watchlist_path()}")
        else:
            print(f"Watchlist ({len(tickers)}):")
            for t in tickers:
                print(f"  {t}")
        return 0
    if cmd == "show":
        tickers = load_tickers()
        if not tickers:
            print("Watchlist is empty. Add tickers with: ./vf watchlist add AAPL MSFT", file=sys.stderr)
            return 1
        return run_comps(tickers=tickers, outdir=outdir, output_format=output_format)
    return 1


def run_statements(
    identifier: str,
    identifier_kind: str,
    statement: str,
    period: str,
    limit: int | None,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
    outdir: str,
    output_format: str,
    diagnostics: bool = False,
) -> int:
    """Fetch one generic statement table from SEC companyfacts."""
    _validate_statement_range(
        period=period,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    limit = _resolve_statement_limit(
        limit=limit,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    bundle = fetch_company_facts(
        identifier,
        identifier_kind=identifier_kind,
    )
    diagnostics_table = None
    if bundle.statement_source == "sec":
        if period == "ttm":
            statement_table = build_statement_table_ttm(
                bundle.company_facts,
                statement=statement,
            )
        else:
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
            if (
                statement == "income"
                and bundle.resolution.sec_company is not None
                and bundle.resolution.sec_company.ticker.upper() == "BRK-B"
            ):
                statement_table = supplement_brk_income_statement_eps_shares(
                    statement_table,
                    sec_client=SecClient(),
                    company=bundle.resolution.sec_company,
                    submissions=None,
                    period=period,
                )
        if diagnostics and period != "ttm":
            diagnostics_table = build_statement_diagnostics_table(
                bundle.company_facts,
                statement=statement,
                period=period,
                limit=limit,
                start_year=start_year,
                end_year=end_year,
                start_quarter=start_quarter,
                end_quarter=end_quarter,
            )
    else:
        yahoo = YahooFinanceClient()
        yahoo_period = "quarterly" if period == "ttm" else period
        raw_frame = yahoo.fetch_statement_frame(bundle.resolution.ticker, statement=statement, period=yahoo_period)
        if period == "ttm":
            from valuation.company.yahoo_statements import build_yahoo_statement_table_ttm
            statement_table = build_yahoo_statement_table_ttm(
                raw_frame,
                statement=statement,
                currency=str(bundle.resolution.currency or "USD"),
            )
        else:
            statement_table = build_yahoo_statement_table(
                raw_frame,
                statement=statement,
                period=period,
                currency=str(bundle.resolution.currency or "USD"),
                limit=limit,
                start_year=start_year,
                end_year=end_year,
                start_quarter=start_quarter,
                end_quarter=end_quarter,
            )
    _require_statement_rows(
        statement_table,
        identifier=bundle.resolution.ticker,
        statement=statement,
        period=period,
    )
    title = f"{statement.title()} Statement {'TTM' if period == 'ttm' else period.title()}"
    sections = [
        ("Resolution", resolution_to_table(bundle.resolution)),
        ("Company", company_summary_to_table(bundle.resolution)),
        (title, statement_table),
    ]
    if diagnostics_table is not None:
        sections.append(("Statement Diagnostics", diagnostics_table))
    _emit_sections(
        sections,
        Path(outdir) / bundle.resolution.ticker.upper().replace(".", "-"),
        output_format=output_format,
        command="statements",
    )
    return 0


def _named_tables(sections: Iterable[tuple[str, object]]):
    """Yield stable file-friendly names for output sections."""
    for title, frame in sections:
        slug = title.lower().replace(" ", "_")
        yield slug, frame


def _emit_sections(
    sections: Iterable[tuple[str, object]],
    output_dir: Path,
    *,
    output_format: str,
    command: str,
) -> None:
    section_list = list(sections)
    if output_format == "json":
        bundle = {
            "command": command,
            "output_dir": str(output_dir),
            "sections": {
                name: frame_to_records(frame)
                for name, frame in _named_tables(section_list)
            },
        }
        print(json.dumps(bundle, indent=2))
        for name, frame in _named_tables(section_list):
            write_json(frame_to_records(frame), output_dir / f"{name}.json")
        write_json(bundle, output_dir / "bundle.json")
        return
    for title, frame in section_list:
        print(f"\n## {title}\n")
        print(render_terminal_table(frame))

    for name, frame in _named_tables(section_list):
        write_csv(frame, output_dir / f"{name}.csv")
        write_markdown(frame, output_dir / f"{name}.md")

    print(f"\nWrote tables to {output_dir}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    load_project_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    previous_refresh_cache = os.environ.get("VALUATION_REFRESH_CACHE")
    if args.refresh_cache:
        os.environ["VALUATION_REFRESH_CACHE"] = "1"

    try:
        if args.command == "snapshot":
            return run_snapshot(
                ticker=args.ticker,
                outdir=args.outdir,
                filings_limit=args.filings_limit,
                output_format=args.format,
            )
        if args.command == "company":
            return run_company(
                identifier=args.identifier,
                identifier_kind=args.identifier_kind,
                outdir=args.outdir,
                filings_limit=args.filings_limit,
                output_format=args.format,
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
                output_format=args.format,
                diagnostics=args.diagnostics,
            )
        if args.command == "ratios":
            return run_ratios(
                identifier=args.identifier,
                identifier_kind=args.identifier_kind,
                limit=args.limit,
                outdir=args.outdir,
                output_format=args.format,
            )
        if args.command == "comps":
            return run_comps(
                tickers=args.tickers,
                outdir=args.outdir,
                output_format=args.format,
            )
        if args.command == "watchlist":
            outdir = getattr(args, "outdir", "outputs/tables")
            output_format = getattr(args, "format", "table")
            return run_watchlist(args, outdir=outdir, output_format=output_format)
        if args.command == "brk":
            return run_brk_command(args)
        if args.command == "portfolio":
            import datetime as _dt
            year = getattr(args, "year", None) or _dt.date.today().year
            fx_auto = getattr(args, "fx_auto", True)
            if args.portfolio_command == "gains":
                return run_portfolio_gains(
                    file=getattr(args, "file", None),
                    year=year,
                    outdir=args.outdir,
                    output_format=args.format,
                    fx_auto=fx_auto,
                    show_fees=getattr(args, "show_fees", False),
                )
            if args.portfolio_command == "dividends":
                return run_portfolio_dividends(
                    file=getattr(args, "file", None),
                    year=year,
                    outdir=args.outdir,
                    output_format=args.format,
                )
            if args.portfolio_command == "interest":
                return run_portfolio_interest(
                    file=getattr(args, "file", None),
                    year=year,
                    outdir=args.outdir,
                    output_format=args.format,
                    fx_auto=fx_auto,
                )
            if args.portfolio_command == "reconcile":
                return run_portfolio_reconcile(
                    file=getattr(args, "file", None),
                    year=year,
                    outdir=args.outdir,
                    output_format=args.format,
                    fx_auto=fx_auto,
                )
            if args.portfolio_command == "furs-xml":
                return run_portfolio_furs_xml(
                    file=getattr(args, "file", None),
                    year=year,
                    outdir=args.outdir,
                    forms=getattr(args, "forms", "all"),
                    fx_auto=fx_auto,
                )
    except (LookupError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if args.refresh_cache:
            if previous_refresh_cache is None:
                os.environ.pop("VALUATION_REFRESH_CACHE", None)
            else:
                os.environ["VALUATION_REFRESH_CACHE"] = previous_refresh_cache
    return 1


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def _quarter_int(value: str) -> int:
    parsed = int(value)
    if parsed not in {1, 2, 3, 4}:
        raise argparse.ArgumentTypeError("quarter must be one of 1, 2, 3, 4")
    return parsed


def _validate_statement_range(
    *,
    period: str,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> None:
    if period == "ttm" and any(v is not None for v in (start_year, end_year, start_quarter, end_quarter)):
        raise ValueError("year/quarter bounds are not supported for --period ttm")
    if period != "quarterly" and (start_quarter is not None or end_quarter is not None):
        raise ValueError("quarter bounds are only valid when --period quarterly is used")
    if (start_quarter is not None and start_year is None) or (
        end_quarter is not None and end_year is None
    ):
        raise ValueError("quarter bounds require matching year bounds")
    if start_year is not None and end_year is not None:
        if start_year > end_year:
            raise ValueError("start year must be less than or equal to end year")
        if (
            period == "quarterly"
            and start_year == end_year
            and start_quarter is not None
            and end_quarter is not None
            and start_quarter > end_quarter
        ):
            raise ValueError("start quarter must be less than or equal to end quarter")


def _resolve_statement_limit(
    *,
    limit: int | None,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> int:
    if limit is not None:
        return limit
    if any(value is not None for value in (start_year, end_year, start_quarter, end_quarter)):
        return 99
    return 4


def _require_statement_rows(
    frame,
    *,
    identifier: str,
    statement: str,
    period: str,
) -> None:
    period_columns = [column for column in frame.columns if column not in {"metric", "unit"}]
    if period_columns and not frame.empty:
        return
    raise ValueError(f"No {period} {statement} statement data available for {identifier}")


def _yahoo_period_label(income_frame) -> str | None:
    """Extract a period label like 'FY 2024' from the most recent Yahoo annual income frame column."""
    import pandas as pd

    if income_frame is None or income_frame.empty:
        return None
    try:
        timestamps = sorted(pd.to_datetime(income_frame.columns, errors="coerce"), reverse=True)
        for ts in timestamps:
            if not pd.isna(ts):
                return f"FY {ts.year}"
    except Exception:
        pass
    return None


if __name__ == "__main__":
    raise SystemExit(main())
