# Working Progress Log

AI-maintained progress file. Updated continuously during long working sessions.

---

## Session: 2026-05-19

### Completed

- Added `./vf portfolio reconcile --year YYYY`
- Reconciliation emits input-file coverage, statement-year coverage, realized-gain totals, dividend/WHT totals, FX coverage, and warning tables
- JSON output includes stable reconciliation section keys
- Added filing-shaped portfolio rows:
  - `./vf portfolio tax --year YYYY` emits `KDVP Filing Rows`
  - `./vf portfolio dividends --year YYYY` emits `Dividend Filing Rows`
  - `./vf portfolio interest --year YYYY` emits broker-interest and `Interest Filing Rows` from Flex XML
- Targeted portfolio tests pass: 84 tests; full suite passes: 409 tests

---

## Session: 2026-05-17 (full day)

### Context
Branch: `brk` (inherits all of `main`).
All non-BRK work is immediately merged to `main` via fast-forward.

---

## Completed this session

### Persistent provider cache (current)
- `SecClient` now persists SEC JSON/text payloads under `~/.cache/valuationFramework/sec` by default, or `VALUATION_CACHE_DIR/sec` when configured
- Mutable SEC endpoints expire automatically: company ticker map 24h, submissions 12h, companyfacts 24h
- Immutable filing artifacts such as filing index JSON, `FilingSummary.xml`, report HTML, and 13F XML are cached indefinitely after first fetch
- `YahooFinanceClient` now persists price snapshots under `~/.cache/valuationFramework/yahoo/snapshots` for 1h and history frames under `~/.cache/valuationFramework/yahoo/history` for 24h
- `./vf --refresh-cache ...` bypasses cached SEC/Yahoo payloads for one run and overwrites cache entries
- This is the right foundation for later universe download/index commands; do not build top-500/top-1000 ingest until source/licensing and ranking definition are explicit
- Full test suite now passes: 272 tests

### BRK balance-sheet context for SOTP residual (current)
- `./vf brk sotp --details` now includes a `Balance Sheet Context` section sourced from the filing balance sheet
- Context rows include equity securities, equity-method investments, total assets, notes payable and other borrowings, deferred income taxes, and total liabilities
- These rows are shown for residual context only; they are not added to the net-liquidity subtotal or SOTP arithmetic
- `./vf brk liquidity --period quarterly --limit 1` now captures the latest 10-Q's plural `Payable for purchases of U.S. Treasury Bills` label and separates context rows from the `Liquidity Bridge`
- Full test suite now passes: 262 tests

### BRK EPS/share filing-table fallback (current)
- `./vf statements BRK --statement income --period annual --limit 3` now fills Class B EPS and equivalent-share rows from Berkshire's `Consolidated Statements of Earnings` filing report table when SEC companyfacts omits them
- `./vf statements BRK --statement income --period quarterly --limit 4` now fills available direct 3-month Class B EPS/share rows from recent 10-Q report tables
- The fallback lives in `src/valuation/brk/statements.py` and only runs for BRK income statements; generic companyfacts statement behavior stays unchanged
- Quarterly fallback intentionally uses only `3 Months Ended` columns and leaves Q4 blank rather than deriving per-share values from annual EPS/YTD columns
- Full test suite now passes: 260 tests

### BRK live QA sweep + terminal readability (current)
- `./vf brk holdings --history --filings-limit 2 --limit 10` exits 0 against live SEC data
- `./vf brk sotp --details` exits 0 and emits valuation assumptions, market anchor, 13F summaries, liquidity, SOTP bridge, operating context, reverse DCF, and segment sections
- `./vf brk sotp --price-change 1M` exits 0 and emits the BRK-vs-holdings comparison
- Fixed terminal rendering so security issuer names do not wrap into misleading continuation rows
- Added compact display aliases for BRK live/resolved 13F and price-change summary fields; backend field names and JSON/CSV contracts remain unchanged
- Full test suite now passes: 258 tests

### TTM period support (0169831, f739f26)
- `./vf statements TICKER --period ttm` sums last 4 quarterly filings per metric
- Balance sheet returns latest quarterly snapshot (TTM not meaningful for instant items)
- Yahoo path gets matching `build_yahoo_statement_table_ttm`
- Year/quarter bounds rejected for TTM with clear error message
- Partial TTM labeled as "3Q TTM" when fewer than 4 quarters available

### EV ratios + formatting fixes (46fcc1b, 0ae742f)
- EV/Revenue and EV/EBITDA in Valuation Ratios
- Fixed `share_change` scientific notation
- Fixed valuation multiple rendering as `7.2x`
- Valuation ratio fields (pe_ratio, ps_ratio etc.) now render as `Nx` not percent

### Owner earnings (28dc070)
- `owner_earnings = net_income + D&A - capex` in Key Financials (SEC and Yahoo)
- `price_to_owner_earnings` in Valuation Ratios table

### EBITDA derived row (e438ee1)
- `ebitda = operating_income + D&A` in Key Financials (SEC and Yahoo)
- Precedes FCF and owner earnings rows

### FCF in Key Financials (6b892d6)
- `free_cash_flow` derived row in Key Financials (was already in cashflow statement)
- Yahoo cashflow statement table also gets FCF derived row

### Valuation ratios period label (eee0aa9)
- `as_of` column in Valuation Ratios table (e.g. "FY 2024" or "TTM")
- SEC path uses TTM financials when quarterly data is available and more recent

### TTM financials for valuation ratios (ce6233c)
- `extract_financials_ttm_from_company_facts`: sums quarterly, falls back to annual
- `./vf company` SEC path uses TTM values for Valuation Ratios

### Number formatting improvements (decf9fe, current)
- EBITDA, FCF, owner_earnings, earnings tokens → currency format
- Valuation ratio fields explicitly mapped to `multiple` format (not percent)

### 13F portfolio change summary (8e79d0a)
- `build_13f_portfolio_change_summary_table`: position counts, value totals, % change
- Shown before per-issuer Holdings Change Summary in `./vf brk holdings --history`

### SOTP bridge improvement (7658934)
- `build_brk_component_bridge_table` now separates fixed maturity and net cash/T-bills
- Residual renamed to `implied_operating_businesses` (more precise)

---

## Planned work (in order)

- [x] Live QA sweep: `./vf brk holdings --history --filings-limit 2` and `./vf brk sotp --details`
- [x] BRK EPS/shares filing-table fallback — requires live exploration of SEC report names
- [x] BRK balance-sheet context for major residual assets/liabilities
- [ ] Yahoo statement hardening for European issuers (bank/insurance balance sheet shapes)
- [ ] Consider open-sourcing after BRK workflow is excellent

---

## Questions for user

- Merge timing: brk and main are in sync; all work has been merged already
- BRK EPS: worth spending time on HTML filing parser, or is Yahoo fallback sufficient?
- Yahoo Europe: which specific issuers have problems? Need a test case to validate fixes
- Distribution: any interest in open-sourcing to r/berkshirehathaway or Slovenia FIRE community?

---

## Issues / observations

- Terminal renderer should keep security identity columns such as `issuer` on one line; wrapping issuer names in Markdown-style terminal tables looks like false extra rows
- BRK `diluted_eps` and `diluted_shares` are absent from SEC companyfacts; `statements` now fills the available Class B rows from filing report tables for annual and direct quarterly income statements
- Valuation Ratios `as_of` shows "TTM" or "3Q TTM" — this is intentional and accurate
- FCF derived row in Key Financials uses positive capex (PaymentsToAcquirePropertyPlantAndEquipment is always positive in SEC GAAP); FCF = OCF - capex
- TTM financial extraction uses 4 quarters for income/cashflow, latest quarterly for balance; falls back to annual when quarterly unavailable
- Partial TTM (< 4 quarters) labeled "3Q TTM" etc. — users should note this in their analysis
- `build_brk_component_bridge_table` is dead code (CLI uses `build_market_implied_sotp_bridge_table` which already has the detailed breakdown)

---

## Test status (2026-05-17)
- 161 tests pass (pytest `tests/` excluding tabulate-dependent files)
- Tabulate-dependent tests (test_cli.py, test_reports_display.py, test_reports_tables.py) need `.venv` activated

## Test status (2026-05-18)
- 272 tests pass with `. .venv/bin/activate && PYTHONPATH=src pytest -q`
