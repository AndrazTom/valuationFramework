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

# Broker interest income from Flex XML (Doh-Obr-shaped output)
./vf portfolio interest --file /path/to/flex.xml --year 2026

# Audit source coverage, FX, realized gains, and dividend totals
./vf portfolio reconcile --file /path/to/flex.xml --year 2026

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
  - Interest: 25% flat estimate, crediting foreign WHT; `si_interest_tax(gross, wht)` returns estimated top-up
  - `next_si_cgt_threshold(acquired, as_of)` — when the next rate tier kicks in

## Filing-shaped rows

- `./vf portfolio tax --year YYYY` now emits:
  - `Realized Gains YYYY` — current readable realized-lot table
  - `KDVP Filing Rows YYYY` — Doh-KDVP-shaped rows with F4/F5/F8/F9-like columns
  - `Tax Summary`
- `./vf portfolio dividends --year YYYY` now emits:
  - `Dividends YYYY`
  - `Dividend Filing Rows YYYY` — Doh-Div-shaped gross/WHT/top-up rows
  - `Dividend Tax Summary`
- `./vf portfolio interest --year YYYY` emits:
  - `Interest YYYY`
  - `Interest Filing Rows YYYY` — Doh-Obr-shaped gross/WHT/tax rows
  - `Interest Tax Summary`
- FURS XML is still intentionally deferred. The next durable milestone is stable filing row contracts, not XML formatting.
- Activity CSV can support trade/dividend rows when exported with enough history, but Flex XML remains preferred for tax-grade lots and broker interest.

## Reconciliation workflow

- `./vf portfolio reconcile --year YYYY` is the audit step before any future FURS XML generator.
- It reuses the existing CSV/Flex loaders and FIFO/tax helpers; do not add separate parser logic just for reconciliation.
- Output sections:
  - `Input Files`: source filename, type, masked account, period, parsed row counts
  - `Coverage Summary`: calendar-year coverage, parsed trade/dividend rows, realized/dividend rows in year, missing FX count
  - `Realized Reconciliation`: proceeds, cost basis, gross gains/losses, net gain, 25% same-year-offset CGT estimate
  - `Dividend Reconciliation`: gross dividends, foreign WHT, Slovenian top-up tax
  - `FX Coverage`: non-EUR currency/date pairs, ECB rate status
  - `Warnings`: full-year coverage, FX, and no-row review flags
- Keep account IDs masked in generated reconciliation tables; private source files are still the audit authority.
- The 25% CGT estimate mirrors the current portfolio tax summary convention; a later pass should refine mixed-rate disposal years before official XML generation.

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
  Eliminates "unmatched sell" warnings. See "Flex Query setup" below for required sections.
- Activity Statement CSV (`.csv`): suitable when flex query is unavailable; requires combining
  multiple year exports for full FIFO history.
- `--file` accepts comma-separated paths for combining multiple files of either format.

## Flex Query setup

Configure an **Activity Flex Query** in IBKR (Performance & Reports → Flex Queries → "+"):

| Section | Options / Fields |
|---|---|
| Account Information | IB Entity, Account ID |
| Trades | Options: **Executions** + **Closed Lots**; then **Select All** fields |
| Corporate Actions | **Select All** fields |
| Cash Transactions | Options: **Dividends**, **Payment in Lieu of Dividends**, **Withholding Tax**, **Broker Fees**, **Broker Interest Received**; then **Select All** fields |
| Financial Instrument Information | **Select All** fields |

Leave date settings at default when saving. When running the report, set Period → **Custom Date
Range** → Jan 1–Dec 31 of the target year. Generate one file per calendar year. Also generate
a report for the current year even when filing a past year, because some WHT entries are reported
retroactively.

**Multi-account note**: On the Reports page use "Select Account(s)" and filter to show
Open + Closed + Migrated accounts to capture accounts from the IBUK→IBCE→IBIE migrations.

Credit: Flex Query configuration instructions adapted from
[ib-edavki](https://github.com/ib-edavki/ib-edavki) (see also `furs_xml.py` attribution).

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
