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

# Disable ECB FX auto-fetch (on by default)
./vf portfolio tax --file /path/to/statement.csv --year 2026 --no-fx-auto
```

## Architecture

- `ibkr.py` — IBKR activity statement CSV parser
  - Handles multi-section IBKR CSV format (each section has its own Header + Data rows)
  - **Order vs Execution deduplication**: IBKR can export at "Order" or "Execution" granularity.
    If both appear in the same statement, Order rows aggregate Execution rows — use ONLY Order rows.
  - Parses: trades (Stocks only), dividends, withholding tax, statement metadata
  - Returns `(list[IbkrTrade], list[IbkrDividend], IbkrStatementMeta)`

- `ibkr_flex.py` — IBKR Flex Query XML parser (preferred for CGT and FURS reporting)
  - `load_flex_query(path)` → `(list[FlexLot], list[IbkrDividend], IbkrStatementMeta)`
    - `FlexLot`: IBKR-computed FIFO lot (`cost_native`, `pnl_native`, `proceeds_native = cost + pnl`)
    - Lot elements cover buys from before the statement period — no "unmatched sell" gaps
    - When the flex query includes `Dividends` CashTransaction type, dividends are parsed directly
    - When only `Withholding Tax` is present, gross is derived in two-step priority:
      1. **WHT arithmetic** (primary): parses `- XX% TAX` from description, computes
         `shares = WHT / (per_share × rate)` — accepts result when within 2% of an integer
      2. **Structural fallback**: counts shares from Trade elements (current period net position);
         if none, checks SELL Lot elements where `openDateTime ≤ div_date < dateTime`
         (handles buys from before the statement period that are sold after the dividend date)
  - `parse_flex_interest(path)` → `list[FlexInterest]`
    - Parses `Broker Interest Received` CashTransactions
    - Matches `Withholding Tax` entries containing `CREDIT INT` by (currency, date)
    - `FlexInterest` fields: `currency`, `payment_date`, `amount`, `withholding_tax`, `description`
  - **WHT net-signed accumulation**: IBKR emits reversal/re-entry pairs for some events
    (e.g. 3× debit + 2× credit = 1× net debit). All WHT amounts are summed with sign;
    `abs()` is applied at the lookup sites. Do NOT sum only negative amounts.

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
- Real estate capital losses (same year) also offset securities CGT — both fall under dohodek iz kapitala
- **Wash-sale rule**: 30-day window — selling at a loss and buying back the *same* instrument within
  30 days disallows the loss. Workaround: buy a *different* instrument for equivalent exposure, or
  wait 30 days. FIFO constraint means you cannot selectively sell a specific loss lot if earlier
  (gain) lots of the same symbol exist; use a different instrument to harvest the loss cleanly.
- Verify all rates and deadlines with FURS (https://www.fu.gov.si) before filing

## Flex Query vs Activity Statement

- Flex Query XML (`.xml`): preferred for CGT — IBKR pre-computes FIFO `<Lot>` elements with
  cost basis and acquisition date even for lots opened before the statement period.
  Eliminates "unmatched sell" warnings. Configure flex query to include Trades + Lots +
  CashTransactions (Dividends + Withholding Tax + Broker Interest Received).
- Activity Statement CSV (`.csv`): suitable when flex query is unavailable; requires combining
  multiple year exports for full FIFO history.
- `--file` accepts comma-separated paths for combining multiple files of either format.

## Fees-in-price (FURS requirement)

FURS requires trade commissions to be baked into F4 (buy price) and F9 (sell price); F5 (commission)
is reported as 0. The `_load_flex_as_trades` function in `cli.py` already implements this:

- `buy.proceeds = -lot.cost_native` (IBKR `Lot.cost` already includes buy commission)
- `sell.proceeds = lot.proceeds_native` (= `cost + fifoPnlRealized`, net of sell commission)
- `commission = 0.0` on both synthetic trades

`lot.cost_native / lot.quantity` gives the all-in F4 per-share price. Do not pass raw
`tradePrice` from the Lot element — that is the execution price before fees.

## Dividend derivation limitations

The WHT arithmetic approach (`shares = WHT / (per_share × rate)`) covers most positions,
including still-held shares that have no closed Lot in the current period. It fails when:
- The description has no `- XX% TAX` pattern (rare in practice for IBKR WHT entries)
- The inferred share count is not within 2% of an integer (indicates a non-standard WHT rate)
- WHT is 0% (e.g. Cayman Islands) — no WHT entry exists, so no derivation path at all

For 0%-WHT symbols (e.g. BABA), add `Dividends` CashTransaction type to the flex query
configuration; otherwise these dividends cannot be derived from WHT-only exports.
