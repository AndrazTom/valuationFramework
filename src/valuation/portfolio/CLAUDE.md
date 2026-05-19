# valuation/portfolio

AI-only notes for the IBKR portfolio module.

## Privacy

IBKR activity statement CSV files contain personal financial data and must NEVER be committed to the repo (which is public).

**Always store the statement path in `.env` (gitignored), not in code:**
```
IBKR_STATEMENT_PATH=/path/to/U1234567_activity.csv
```

The `.gitignore` already excludes `*.activity.csv`, `*_statement.csv`, `ibkr_*.csv`, and `ibkr_*.xml`.

## CLI usage

```bash
# Open positions with live prices and CGT tier
./vf portfolio show --file /path/to/statement.csv

# Realized gains + Slovenian CGT for a year
./vf portfolio tax --file /path/to/statement.csv --year 2026

# Dividend income + SI dividend tax (with WHT credit)
./vf portfolio dividends --file /path/to/statement.csv --year 2026

# Auto-fetch ECB historical FX rates for non-EUR trades
./vf portfolio tax --file /path/to/statement.csv --year 2026 --fx-auto
```

## Architecture

- `ibkr.py` — IBKR activity statement CSV parser
  - Handles multi-section IBKR CSV format (each section has its own Header + Data rows)
  - **Order vs Execution deduplication**: IBKR can export at "Order" or "Execution" granularity.
    If both appear in the same statement, Order rows aggregate Execution rows — use ONLY Order rows.
  - Parses: trades (Stocks only), dividends, withholding tax, statement metadata
  - Returns `(list[IbkrTrade], list[IbkrDividend], IbkrStatementMeta)`

- `lots.py` — FIFO lot engine
  - Input: list of `IbkrTrade`, optional `fx_rates` dict
  - Sorts by (date, buy_before_sell) internally — callers do NOT need to pre-sort
  - EUR trades: handled natively (rate = 1.0)
  - Non-EUR trades: EUR amounts set to None when fx_rates absent or incomplete
  - Returns: `(open_lots, realized_gains)`
  - `non_eur_currency_dates(trades)` — helper to collect currency/date pairs for FX lookup

- `fx.py` — ECB historical FX rate fetcher
  - Free ECB SDMX REST API, no auth required
  - ECB returns units-of-foreign-currency per EUR; we invert to EUR per unit
  - Weekend/holiday gaps: searches up to 7 days backwards for nearest available rate
  - Persistent JSON cache under `~/.cache/valuationFramework/ecb_fx/` (7-day TTL)
  - `EcbFxClient.build_fx_rates_dict(pairs)` returns the dict expected by `build_lots_and_realized`

- `tax_si.py` — Slovenian tax rules (ZDoh-2)
  - CGT: 25% → 20% → 15% → 0% at 5/10/15 complete years held
  - Dividends: 25% flat, crediting foreign WHT; `si_dividend_tax(gross, wht)` returns net additional tax
  - `next_si_cgt_threshold(acquired, as_of)` — when the next rate tier kicks in

## IBKR statement export

In IBKR Account Management:
1. Reports → Statements → Activity
2. Select date range (e.g. full year for tax, or year-to-date for current holdings)
3. Format: CSV
4. Download and keep the file OUTSIDE the repo directory, or in a gitignored location

## Slovenian tax notes

- CGT: reported on DOHDSP-1 form, due 28 Feb of following year (verify with FURS)
- Dividends: reported on DOHDSP-2 form; foreign WHT from 15% US treaty rate offsets 25% SI rate
- Losses offset gains within the same tax year only; no carry-forward under ZDoh-2
- Verify all rates and deadlines with FURS (https://www.fu.gov.si) before filing

## Flex Query vs Activity Statement

- Flex Query XML (`.xml`): preferred for CGT — IBKR pre-computes FIFO `<Lot>` elements with
  cost basis and acquisition date even for lots opened before the statement period.
  Eliminates "unmatched sell" warnings. Configure flex query to include Trades + Lots +
  CashTransactions (Dividends + Withholding Tax).
- Activity Statement CSV (`.csv`): suitable when flex query is unavailable; requires combining
  multiple year exports for full FIFO history.
- `--file` accepts comma-separated paths for combining multiple files of either format.
