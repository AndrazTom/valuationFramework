# Working Progress Log

AI-maintained progress file. Updated continuously during long working sessions.

---

## Session: 2026-05-17 (continued)

### Context
Branch: `brk` (inherits all of `main`).

---

## Completed this session

### 731505f — BRK holdings change summary + SOTP segment history
- `./vf brk holdings --history` → Holdings Change Summary (new/increased/decreased/eliminated)
- `./vf brk sotp --details` → fetches 4 segment filings, showing real period history

### f34fac0 — Generic company (main-targeted)
- `./vf company` → Valuation Ratios section: P/E, P/B, P/S, P/FCF
- Cash flow statement → derived `free_cash_flow` row (OCF − capex)
- Works for both SEC and Yahoo paths

### 46fcc1b — EV ratios + formatting fixes
- EV/Revenue and EV/EBITDA in Valuation Ratios
- Fixed `share_change` scientific notation (broadened `"share"` match)
- Fixed `residual_to_pretax_earnings_multiple` rendering as `7.2x`

### 0169831 — TTM period support
- `./vf statements TICKER --period ttm` now sums last 4 quarterly filings per metric
- Balance sheet: returns latest quarterly snapshot (TTM not meaningful for instant items)
- Yahoo path gets matching `build_yahoo_statement_table_ttm`
- Year/quarter bounds rejected for TTM with clear error message

### 28dc070 — Owner earnings
- `owner_earnings = net_income + D&A - capex` derived row in Key Financials (both SEC and Yahoo)
- `price_to_owner_earnings` added to Valuation Ratios table

### eee0aa9 — Valuation ratios period label
- `as_of` column added to Valuation Ratios table (e.g. "FY 2024")
- Derived from `net_income` end date in SEC companyfacts or latest Yahoo frame column

### 6b892d6 — FCF in Key Financials
- `free_cash_flow` derived row added to Key Financials alongside `owner_earnings`
- Both SEC and Yahoo paths surfaced in `./vf company`

---

## Planned work (in order)

- [ ] Live QA: `./vf brk holdings --history --filings-limit 2` and `./vf brk sotp --details`
- [ ] Merge brk → main (all recent generic improvements are main-targeted)
- [ ] BRK EPS/shares filing-table fallback: explore SEC filing report names, implement brk-local parser
- [ ] SOTP: split fixed maturity securities more explicitly
- [ ] 13F: full issuer change context (not just top holdings)
- [ ] Yahoo statement hardening: European issuers

---

## Questions for user

- Merge timing: merge brk → main now? All 5 recent commits are generic and clean.
- BRK EPS: worth spending time on HTML filing parser, or is the Yahoo fallback sufficient?
- SOTP change summary: should it show filing-over-filing portfolio value change (not just issuer-level)?
- Distribution: any interest in open-sourcing to r/berkshirehathaway or Slovenian FIRE community?

---

## Issues / observations

- BRK `diluted_eps` and `diluted_shares` are confirmed absent from SEC companyfacts; only approach is parsing the 10-K/10-Q HTML report tables
- The `./vf brk sotp --details` now fetches 4 segment filings but SOTP context table still uses only the latest; this is intentional
- FCF derived row uses capex as a positive outflow (PaymentsToAcquirePropertyPlantAndEquipment is always positive in SEC GAAP); this is correct
- Valuation ratios use latest annual figures, not TTM quarterly aggregates; relevant for companies with strong quarterly seasonality
- TTM implementation sums 4 quarters from SEC quarterly reconstruction; if fewer than 4 are available, it sums what it has (partial year — may want to warn user)

---

## Needs improving

- TTM with fewer than 4 quarters available should ideally show a warning or note the number of quarters used
- SOTP change summary could show filing-over-filing portfolio value change (not just issuer-level)
- `./vf brk holdings --history` with filings-limit 2 should auto-include the change summary without requiring --history
- Valuation Ratios `as_of` column shows `None` for Yahoo path companies that have no annual frame columns (edge case with empty frames)
