# valuationFramework

Backend-first stock financials and valuation tooling.

`main` is for reusable company-level infrastructure. `brk` is the Berkshire Hathaway proving ground.

Longer term, the project is meant to become a small personal alternative to the financial-data side of TradingView, with more emphasis on statements, balance sheets, and cash flows.

## Current Scope

- free-first data stack
- Python package, not machine-specific scripts
- table-oriented outputs
- CLI first, API later

## Current Data Sources

- SEC EDGAR for filings and fundamentals
- `yfinance` for market snapshots, identifier search, and global fallback financial statements when available

## Local Setup

```bash
./setup
export VALUATION_SEC_USER_AGENT="valuationFramework/0.1 your-email@example.com"
./vf company BRK-B
./vf company BNP.PA
./vf company US0846707026
```

`./vf` runs the current source tree through the local virtualenv.

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
- `company` is the main single-security view and now aims to show:
  - resolution
  - company/profile metadata
  - market snapshot
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

## Current Company View

`./vf company <identifier>` currently tries to behave like the backend equivalent of a TradingView company page:

- flexible identifier resolution
- enriched company metadata even for SEC-backed issuers when Yahoo profile data is available
- market snapshot
- key financials
- statement availability by statement and period
- recent analysis-relevant filings

For SEC-backed issuers, recent filings are filtered toward core company forms such as `10-K`, `10-Q`, `8-K`, `20-F`, `6-K`, `40-F`, and `DEF 14A` so the view is less noisy.

## Documentation

- `README.md` is human-facing
- `claude.md` and subtree `CLAUDE.md` files are AI-only notes
