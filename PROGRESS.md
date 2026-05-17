# Working Progress Log

AI-maintained progress file. Updated continuously during long working sessions.

---

## Session: 2026-05-17 (full day)

### Context
Branch: `brk` (inherits all of `main`).
All non-BRK work is immediately merged to `main` via fast-forward.

---

## Completed this session

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

- [ ] Live QA sweep: `./vf brk holdings --history --filings-limit 2` and `./vf brk sotp --details`
- [ ] BRK EPS/shares filing-table fallback — requires live exploration of SEC report names
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

- BRK `diluted_eps` and `diluted_shares` absent from SEC companyfacts; only approach is HTML filing tables
- Valuation Ratios `as_of` shows "TTM" or "3Q TTM" — this is intentional and accurate
- FCF derived row in Key Financials uses positive capex (PaymentsToAcquirePropertyPlantAndEquipment is always positive in SEC GAAP); FCF = OCF - capex
- TTM financial extraction uses 4 quarters for income/cashflow, latest quarterly for balance; falls back to annual when quarterly unavailable
- Partial TTM (< 4 quarters) labeled "3Q TTM" etc. — users should note this in their analysis
- `build_brk_component_bridge_table` is dead code (CLI uses `build_market_implied_sotp_bridge_table` which already has the detailed breakdown)

---

## Test status (2026-05-17)
- 161 tests pass (pytest `tests/` excluding tabulate-dependent files)
- Tabulate-dependent tests (test_cli.py, test_reports_display.py, test_reports_tables.py) need `.venv` activated
