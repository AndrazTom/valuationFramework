"""CLI helpers for Berkshire-specific commands."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Iterable

from valuation.brk.holdings import aggregate_13f_holdings
from valuation.brk.service import (
    BRK_B_TICKER,
    fetch_brk_13f_history,
    fetch_brk_liquidity,
    fetch_brk_overview,
    fetch_brk_segments,
)
from valuation.brk.service import fetch_latest_brk_13f
from valuation.brk.service import fetch_brk_valuation_bundle
from valuation.brk.reference import build_brk_security_reference
from valuation.brk.tables import (
    build_13f_holdings_history_table,
    build_13f_history_summary_table,
    build_13f_issuer_change_summary_table,
    build_13f_portfolio_change_summary_table,
    build_13f_summary_table,
    build_13f_live_price_summary_table,
    build_brk_operating_reverse_dcf_table,
    build_brk_valuation_assumptions_table,
    build_key_facts_table,
    build_holdings_vs_brk_price_change_table,
    build_liquidity_bridge_table,
    build_liquidity_summary_table,
    build_latest_liquidity_snapshot_table,
    build_market_anchor_table,
    build_market_implied_sotp_bridge_table,
    build_operating_business_context_table,
    build_public_equity_portfolio_summary_table,
    build_segment_period_sections,
    build_segment_report_summary_table,
    build_share_class_table,
    build_top_level_operating_segments_summary_table,
    build_top_holdings_live_table,
    build_top_holdings_table,
    filter_core_filings_table,
)
from valuation.data.normalize.tables import (
    recent_filings_to_table,
    sec_company_to_table,
    snapshot_to_table,
)
from valuation.data.providers.yahoo import YahooFinanceClient
from valuation.reports.tables import render_terminal_table, write_csv, write_markdown
from valuation.securities.pricing import (
    enrich_holdings_with_market_prices,
    fetch_price_change_snapshot,
    normalize_price_change_window,
)


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
    holdings_parser.add_argument(
        "--history",
        action="store_true",
        help="Also fetch recent 13F filings and show holdings history tables.",
    )
    holdings_parser.add_argument(
        "--filings-limit",
        type=_non_negative_int,
        default=4,
        help="Number of 13F filings to include when --history is used.",
    )
    holdings_parser.add_argument(
        "--live-prices",
        action="store_true",
        help="Attempt to revalue holdings using current market prices where a ticker is known.",
    )
    holdings_parser.add_argument(
        "--price-change-window",
        "--price-change",
        dest="price_change_window",
        type=_price_change_window,
        help="Add a price-change column using one window: 1D, 5D, 1M, 3M, YTD, 1Y, 5Y, ALL.",
    )

    liquidity_parser = brk_subparsers.add_parser(
        "liquidity",
        help="Fetch Berkshire cash and debt-securities bridge tables.",
    )
    liquidity_parser.add_argument("--outdir", default="outputs/tables")
    liquidity_parser.add_argument(
        "--period",
        choices=("annual", "quarterly"),
        default="annual",
        help="Use annual 10-K or quarterly 10-Q filings.",
    )
    liquidity_parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=None,
        help="Number of filings to include.",
    )
    liquidity_parser.add_argument("--start-year", type=int)
    liquidity_parser.add_argument("--end-year", type=int)
    liquidity_parser.add_argument("--start-quarter", type=_quarter_int)
    liquidity_parser.add_argument("--end-quarter", type=_quarter_int)

    segments_parser = brk_subparsers.add_parser(
        "segments",
        help="Fetch Berkshire operating-segment tables from annual or quarterly filings.",
    )
    segments_parser.add_argument("--outdir", default="outputs/tables")
    segments_parser.add_argument(
        "--period",
        choices=("annual", "quarterly"),
        default="annual",
        help="Use annual 10-K or quarterly 10-Q filings.",
    )
    segments_parser.add_argument(
        "--limit",
        type=_non_negative_int,
        default=None,
        help="Number of filings to include.",
    )
    segments_parser.add_argument("--start-year", type=int)
    segments_parser.add_argument("--end-year", type=int)
    segments_parser.add_argument("--start-quarter", type=_quarter_int)
    segments_parser.add_argument("--end-quarter", type=_quarter_int)

    sotp_parser = brk_subparsers.add_parser(
        "sotp",
        aliases=["valuation"],
        help="Build a first Berkshire market-implied SOTP bridge.",
    )
    sotp_parser.add_argument("--outdir", default="outputs/tables")
    sotp_parser.add_argument(
        "--period",
        choices=("annual", "quarterly"),
        default="annual",
        help="Use annual 10-K or quarterly 10-Q inputs for liquidity and segment context.",
    )
    sotp_parser.add_argument(
        "--price-change-window",
        "--price-change",
        dest="price_change_window",
        type=_price_change_window,
        help="Optional comparison window for BRK.B versus resolved holdings basket.",
    )
    sotp_parser.add_argument(
        "--details",
        action="store_true",
        help="Include supporting assumptions, market anchor, liquidity, holdings, and segment tables.",
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
            live_prices=args.live_prices,
            price_change_window=args.price_change_window,
            history=args.history,
            filings_limit=args.filings_limit,
        )
    if args.brk_command == "liquidity":
        return run_brk_liquidity(
            outdir=args.outdir,
            period=args.period,
            limit=args.limit,
            start_year=args.start_year,
            end_year=args.end_year,
            start_quarter=args.start_quarter,
            end_quarter=args.end_quarter,
        )
    if args.brk_command == "segments":
        return run_brk_segments(
            outdir=args.outdir,
            period=args.period,
            limit=args.limit,
            start_year=args.start_year,
            end_year=args.end_year,
            start_quarter=args.start_quarter,
            end_quarter=args.end_quarter,
        )
    if args.brk_command in {"sotp", "valuation"}:
        return run_brk_sotp(
            outdir=args.outdir,
            period=args.period,
            price_change_window=args.price_change_window,
            details=args.details,
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


def run_brk_holdings(
    outdir: str,
    limit: int,
    live_prices: bool,
    price_change_window: str | None,
    history: bool = False,
    filings_limit: int = 4,
) -> int:
    """Build table outputs for Berkshire's latest 13F holdings."""
    history_bundle = fetch_brk_13f_history(limit=filings_limit) if history else None
    if history_bundle is not None and history_bundle.filings:
        bundle = history_bundle.filings[0]
    else:
        bundle = fetch_latest_brk_13f()
    yahoo = YahooFinanceClient()
    if price_change_window is not None:
        live_prices = True
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
    if history and history_bundle is not None:
        sections.extend(
            [
                (
                    "13F Filing History",
                    build_13f_history_summary_table(history_bundle.filings),
                ),
                (
                    "Top Holdings History",
                    build_13f_holdings_history_table(
                        history_bundle.filings,
                        limit=limit,
                    ),
                ),
            ]
        )
        if len(history_bundle.filings) >= 2:
            sections.append(
                (
                    "Portfolio Change Summary",
                    build_13f_portfolio_change_summary_table(history_bundle.filings),
                )
            )
            sections.append(
                (
                    "Holdings Change Summary",
                    build_13f_issuer_change_summary_table(history_bundle.filings),
                )
            )
    if live_prices:
        reference = build_brk_security_reference()
        enriched_holdings = enrich_holdings_with_market_prices(
            aggregate_13f_holdings(bundle.holdings),
            reference,
            yahoo_client=yahoo,
            price_change_window=price_change_window,
        )
        brk_snapshot = (
            fetch_price_change_snapshot(
                BRK_B_TICKER,
                price_change_window=price_change_window,
                yahoo_client=yahoo,
            )
            if price_change_window is not None
            else None
        )
        sections.extend(
            [
                (
                    "Live Price Summary",
                    build_13f_live_price_summary_table(
                        bundle.holdings,
                        reference,
                        yahoo_client=yahoo,
                        price_change_window=price_change_window,
                        enriched_holdings=enriched_holdings,
                    ),
                ),
                (
                    "Top Holdings Live",
                    build_top_holdings_live_table(
                        bundle.holdings,
                        reference,
                        limit=limit,
                        yahoo_client=yahoo,
                        price_change_window=price_change_window,
                        enriched_holdings=enriched_holdings,
                    ),
                ),
            ]
        )
        if price_change_window is not None:
            sections[-1] = (
                f"Top Holdings Live ({price_change_window} Change)",
                sections[-1][1],
            )
            sections.append(
                (
                    f"BRK vs Holdings Price Change ({price_change_window})",
                    build_holdings_vs_brk_price_change_table(
                        bundle.holdings,
                        reference,
                        yahoo_client=yahoo,
                        price_change_window=price_change_window,
                        limit=limit,
                        enriched_holdings=enriched_holdings,
                        brk_snapshot=brk_snapshot,
                    ),
                )
            )
    _emit_sections(sections, Path(outdir) / "BRK_13F")
    return 0


def run_brk_liquidity(
    outdir: str,
    period: str,
    limit: int | None,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> int:
    """Build Berkshire liquidity tables from filing balance sheets."""
    _validate_period_range(
        period=period,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    bundle = fetch_brk_liquidity(
        period=period,
        limit=_resolve_history_limit(
            limit=limit,
            start_year=start_year,
            end_year=end_year,
            start_quarter=start_quarter,
            end_quarter=end_quarter,
        ),
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    bridge = build_liquidity_bridge_table(bundle.filings)
    sections = [
        ("Liquidity History", build_liquidity_summary_table(bridge)),
        ("Liquidity Bridge", bridge),
    ]
    _emit_sections(sections, Path(outdir) / "BRK_LIQUIDITY")
    return 0


def run_brk_segments(
    outdir: str,
    period: str,
    limit: int | None,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> int:
    """Build Berkshire operating-segment tables from selected filings."""
    _validate_period_range(
        period=period,
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    bundle = fetch_brk_segments(
        period=period,
        limit=_resolve_history_limit(
            limit=limit,
            start_year=start_year,
            end_year=end_year,
            start_quarter=start_quarter,
            end_quarter=end_quarter,
        ),
        start_year=start_year,
        end_year=end_year,
        start_quarter=start_quarter,
        end_quarter=end_quarter,
    )
    sections = [
        (
            "Segment Filings",
            build_segment_report_summary_table(bundle.filings),
        ),
    ]
    sections.extend(build_segment_period_sections(bundle.filings, period=period))
    if len(bundle.filings) == 1 and len(sections) == 1:
        sections.append(
            (
                "Top-Level Operating Segments Summary",
                build_top_level_operating_segments_summary_table(
                    bundle.filings,
                    period=period,
                ),
            )
        )
    _emit_sections(sections, Path(outdir) / "BRK_SEGMENTS")
    return 0


def run_brk_sotp(
    outdir: str,
    period: str,
    price_change_window: str | None,
    details: bool = False,
) -> int:
    """Build a first Berkshire market-implied SOTP bridge."""
    yahoo = YahooFinanceClient()
    bundle = fetch_brk_valuation_bundle(period=period, yahoo_client=yahoo, segment_limit=4 if details else 1)
    reference = build_brk_security_reference()
    enriched_holdings = enrich_holdings_with_market_prices(
        aggregate_13f_holdings(bundle.holdings.holdings),
        reference,
        yahoo_client=yahoo,
        price_change_window=price_change_window,
    )
    brk_snapshot = (
        fetch_price_change_snapshot(
            BRK_B_TICKER,
            price_change_window=price_change_window,
            yahoo_client=yahoo,
        )
        if price_change_window is not None
        else None
    )
    operating_context = build_operating_business_context_table(
        bundle,
        reference,
        period=period,
        yahoo_client=yahoo,
        enriched_holdings=enriched_holdings,
    )
    reverse_dcf = build_brk_operating_reverse_dcf_table(
        operating_context, bundle.overview.market_snapshot
    )
    sections = [
        (
            "Market-Implied SOTP Bridge",
            build_market_implied_sotp_bridge_table(
                bundle,
                reference,
                yahoo_client=yahoo,
                enriched_holdings=enriched_holdings,
            ),
        ),
        ("Operating Business Context", operating_context),
    ]
    if not reverse_dcf.empty:
        sections.append(("Operating Business Reverse DCF", reverse_dcf))
    if details:
        liquidity_bridge = build_liquidity_bridge_table(bundle.liquidity.filings)
        sections[0:0] = [
            (
                "Valuation Assumptions",
                build_brk_valuation_assumptions_table(period=period),
            ),
            (
                "Market Anchor",
                build_market_anchor_table(bundle.overview.market_snapshot),
            ),
            (
                "Public Equity Portfolio Summary",
                build_public_equity_portfolio_summary_table(
                    bundle.holdings.holdings,
                    reference,
                    yahoo_client=yahoo,
                    enriched_holdings=enriched_holdings,
                ),
            ),
            (
                "Liquidity Snapshot",
                build_latest_liquidity_snapshot_table(liquidity_bridge),
            ),
        ]
    if price_change_window is not None:
        sections.append(
            (
                f"BRK vs Holdings Price Change ({price_change_window})",
                build_holdings_vs_brk_price_change_table(
                    bundle.holdings.holdings,
                    reference,
                    yahoo_client=yahoo,
                    price_change_window=price_change_window,
                    enriched_holdings=enriched_holdings,
                    brk_snapshot=brk_snapshot,
                ),
            )
        )
    if details:
        insert_at = 3
        if price_change_window is not None:
            sections.insert(
                insert_at,
                (
                    "Quoted Holdings Summary",
                    build_13f_live_price_summary_table(
                        bundle.holdings.holdings,
                        reference,
                        yahoo_client=yahoo,
                        price_change_window=price_change_window,
                        enriched_holdings=enriched_holdings,
                    ),
                ),
            )
        else:
            sections.insert(
                insert_at,
                (
                    "Quoted Holdings Summary",
                    build_13f_live_price_summary_table(
                        bundle.holdings.holdings,
                        reference,
                        yahoo_client=yahoo,
                        enriched_holdings=enriched_holdings,
                    ),
                ),
            )
        sections.extend(build_segment_period_sections(bundle.segments.filings, period=period))
    _emit_sections(sections, Path(outdir) / "BRK_SOTP")
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
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
        yield slug, frame


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


def _validate_period_range(
    *,
    period: str,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> None:
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


def _resolve_history_limit(
    *,
    limit: int | None,
    start_year: int | None,
    end_year: int | None,
    start_quarter: int | None,
    end_quarter: int | None,
) -> int:
    if any(value is not None for value in (start_year, end_year, start_quarter, end_quarter)):
        return 99
    if limit is not None:
        return limit
    return 1


def _price_change_window(value: str) -> str:
    try:
        return normalize_price_change_window(value) or ""
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
