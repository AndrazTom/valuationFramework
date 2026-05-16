# valuationFramework

Backend-first stock financials and valuation tooling.

Longer term, the project is meant to become a small personal alternative to the financial-data side of TradingView, with more emphasis on statements, balance sheets, and cash flows.

This branch, `brk`, inherits the current generic company/statement backend from `main` and adds Berkshire Hathaway-specific workflows on top.

## Current Scope

- free-first data stack
- Python package, not machine-specific scripts
- generic single-security workflows
- table-oriented outputs with JSON export support
- CLI first, API later

## Current Data Sources

- SEC EDGAR for filings and fundamentals
- `yfinance` for market snapshots, identifier search, and global fallback financial statements when available

## Local Setup

```bash
./setup
./vf company AAPL
./vf company BNP.PA
./vf company US0846707026
./vf brk overview
./vf brk holdings --limit 10
```

`./vf` runs the current source tree through the local virtualenv.

For SEC-backed commands, use either:

- a repo-local `.env` with `VALUATION_SEC_USER_AGENT=valuationFramework/0.1 your-email@example.com`
- or an exported shell variable such as `export VALUATION_SEC_USER_AGENT="valuationFramework/0.1 your-email@example.com"`

The code now loads `.env` directly as well, so both `./vf ...` and `python -m valuation.cli ...` pick up the same local configuration. An exported environment variable still overrides `.env`.

## Main Workflow

The generic entrypoint is:

```bash
./vf company <identifier>
```

Supported identifier paths today:

- ticker
- CIK
- CUSIP
- ISIN

Current backend behavior:

- US issuers use SEC first for filings and statements
- non-US issuers fall back to Yahoo profile + statement data when available
- smaller markets may require explicit identifiers or cross-listings until market-specific filing adapters exist
- `company` is the main single-security view and currently shows:
  - resolution
  - company/profile metadata
  - market snapshot
  - overview
  - key financials
  - statement availability
  - recent core filings

Examples:

```bash
./vf company AAPL
./vf company BNP.PA
./vf company SI0031102120
./vf company 0000320193 --identifier-kind cik
./vf company US0378331005
./vf company AAPL --format json
./vf statements AAPL --statement income --period annual
./vf statements BNP.PA --statement income --period annual
./vf statements AAPL --statement balance --period quarterly
./vf statements AAPL --statement cashflow --period quarterly --start-year 2025 --start-quarter 1 --end-year 2025 --end-quarter 4
```

## Output Shape

The project supports two output modes:

- `--format table` (default)
  - terminal tables with compact human-readable values
  - Markdown files
  - CSV files
- `--format json`
  - a machine-readable JSON bundle on stdout
  - per-section `.json` files plus `bundle.json` in the output directory

Raw numeric precision stays in backend tables. Human-readable notation is applied in the render layer.

## Current Commands

The repo currently revolves around three generic commands:

- `./vf company <identifier>`
  - the main single-security backend view
  - works with ticker, CIK, CUSIP, and ISIN where the free data path supports them
- `./vf snapshot <ticker>`
  - a lighter market snapshot plus recent SEC filing view
- `./vf statements <identifier>`
  - generic income, balance sheet, and cash flow tables
  - annual and quarterly
  - optional year and quarter range filters

If you pass statement range filters such as `--start-year` / `--end-year`, the command widens the default internal period limit so the range filter controls the output instead of a small default cut-off.

On `brk`, there is also a Berkshire-only command group:

- `./vf brk overview`
- `./vf brk holdings`
- `./vf brk holdings --live-prices --limit 10`
- `./vf brk holdings --price-change 1M --limit 10`
- `./vf brk sotp`
- `./vf brk sotp --price-change 1M`
- `./vf brk liquidity --period annual --limit 4`
- `./vf brk liquidity --period quarterly --limit 4`
- `./vf brk segments --period annual --limit 4`
- `./vf brk segments --period quarterly --limit 4`
- both commands also support explicit period ranges such as:
  - `--start-year 2019 --start-quarter 1 --end-year 2023 --end-quarter 3`

For Berkshire history commands, explicit start/end period filters force the internal history limit wide enough that the period range drives the result instead of a small manual `--limit`.

Those commands are branch-specific research workflows layered on top of the generic backend.

## Current Company View

`./vf company <identifier>` currently tries to behave like the backend equivalent of a TradingView company page:

- flexible identifier resolution
- enriched company metadata even for SEC-backed issuers when Yahoo profile data is available
- compact overview rows that combine market data with the best available financial backbone
- market snapshot
- key financials
- statement availability by statement and period
- recent analysis-relevant filings

The compact `overview` section is intentionally small. It combines:

- market metrics such as `last_price`, `market_cap`, and `shares`
  - `market_cap` is derived from current price times shares when Yahoo omits a direct market-cap value
- latest core financial metrics such as `revenue`, `net_income`, `operating_cash_flow`, `cash_and_equivalents`, `total_assets`, `total_liabilities`, and `stockholders_equity`

The goal is to keep one stable, backend-friendly summary layer before the deeper tables.

Overview rows also carry lightweight backend metadata such as source, statement group, period type, `as_of`, and a simple completeness signal (`current`, `stale`, or `missing`) so downstream consumers can reason about data quality without parsing the full raw provider payloads.

Statement availability rows also try to distinguish between fully available statements and partial provider coverage. The current backend reports statement status together with present metric counts, expected metric counts, and a simple coverage ratio.

For SEC-backed issuers, recent filings are filtered toward core company forms such as `10-K`, `10-Q`, `8-K`, `20-F`, `6-K`, `40-F`, and `DEF 14A` so the view is less noisy.

## Current Statement Behavior

`./vf statements <identifier>` is generic across:

- `--statement income`
- `--statement balance`
- `--statement cashflow`
- `--period annual`
- `--period quarterly`

Current statement behavior includes:

- SEC-first statements for US issuers
- Yahoo-backed statement fallback for non-US issuers when Yahoo has usable data
- clearer failures when a provider returns no usable rows
- explicit separation between:
  - additive flow metrics
  - instant balance-sheet metrics
  - direct-quarter metrics such as diluted EPS and diluted shares
- statement tables prefer dropping rows that are empty across the selected periods instead of keeping noisy all-blank rows

For Yahoo-backed names, empty quarterly frames are treated as upstream provider gaps rather than silent success.

## Current JSON Path

`--format json` is supported on:

- `./vf company`
- `./vf snapshot`
- `./vf statements`

The JSON path is intentionally minimal and backend-oriented:

- one JSON bundle is printed to stdout
- one JSON file is written per section in the output directory
- raw numeric values are preserved
- the table/markdown path remains available for human inspection

## Berkshire Branch Workflow

`brk` keeps the generic `company`, `snapshot`, and `statements` commands, but adds Berkshire-focused commands under:

```bash
./vf brk <subcommand>
```

Current Berkshire workflows include:

- `overview`
  - Berkshire market snapshot
  - share-class bridge
  - selected SEC facts
  - filtered core filings
- `holdings`
  - latest 13F holdings
  - optional live-price enrichment where ticker mappings exist
  - optional `--price-change` / `--price-change-window` column for windows such as `1D`, `1M`, `YTD`, and `1Y`
  - Berkshire-vs-holdings change comparison when a price-change window is selected
  - if Yahoo rate-limits live pricing, the command now degrades to partial/empty live coverage instead of crashing
- `sotp`
  - first Berkshire market-implied SOTP bridge
  - explicit valuation assumptions, market anchor, public-equity summary, liquidity snapshot, and residual operating-and-other bridge
  - optional `--price-change` comparison between BRK and the resolved holdings basket
- `liquidity`
  - Berkshire liquidity history from filing balance sheets, not just companyfacts
  - includes cash, short-term U.S. Treasury Bills, fixed maturity securities, and explicit core liquidity totals
  - supports `--period annual|quarterly`, `--limit`, and explicit start/end period filters
- `segments`
  - top-level operating segment history from SEC filing report tables
  - supports `--period annual|quarterly`, `--limit`, and explicit start/end period filters
  - quarterly segment output prefers 3-month columns instead of mixing in 9-month YTD values
  - segment history is split into separate filing-period tables so multi-year output stays readable
  - current command is intentionally a top-level segment summary, not the full raw note disclosure
  - older annual filings can legitimately leave some top-level fields blank because the reusable SEC report tables often only expose `Total revenues` plus the additional-disclosure metrics

The intent on this branch is to use Berkshire as the hard valuation case while still inheriting the reusable generic infrastructure from `main`.

## Documentation

- `README.md` is human-facing
- `claude.md` and subtree `CLAUDE.md` files are AI-only notes
