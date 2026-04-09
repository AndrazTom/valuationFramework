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
- `yfinance` for market snapshot convenience and identifier search

## Local Setup

```bash
./setup
export VALUATION_SEC_USER_AGENT="valuationFramework/0.1 your-email@example.com"
./vf company BRK-B
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

Examples:

```bash
./vf company AAPL
./vf company 0000320193 --identifier-kind cik
./vf company US0378331005
./vf statements AAPL --statement income --period annual
./vf statements AAPL --statement balance --period quarterly
./vf statements AAPL --statement cashflow --period quarterly --start-year 2025 --start-quarter 1 --end-year 2025 --end-quarter 4
```

## Output Shape

The project defaults to structured outputs:

- terminal tables with compact human-readable values
- Markdown tables
- CSV
- later Parquet and API responses

Raw numeric precision stays in backend tables. Human-readable notation is applied in the render layer.

## Documentation

- `README.md` is human-facing
- `claude.md` and subtree `CLAUDE.md` files are AI-only notes
