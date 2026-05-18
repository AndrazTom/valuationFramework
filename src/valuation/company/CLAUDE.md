# valuation/company

AI-only note for generic single-company workflows.

This package is where `main` provides standalone value for any issuer.

## Purpose

- accept flexible identifiers (ticker, CIK, CUSIP, ISIN) when the free data path supports them
- resolve them into one canonical company/ticker view
- produce a TradingView-like baseline focused on financials, filings, and balance-sheet visibility
- keep the workflow generic and reusable; no Berkshire assumptions

## Module Ownership

- `service.py` — resolve identifiers; choose SEC-backed vs Yahoo-backed path; fetch provider bundles
- `tables.py` — company-facing tables: summary, overview, statement availability, valuation ratios, implied value range, reverse DCF
- `statements.py` — SEC statement concept sets and quarterly reconstruction rules
- `yahoo_statements.py` — Yahoo label mapping for fallback statements and key financials
- `comps.py` — multi-ticker TTM comparison table (see below)
- `ratios.py` — historical per-fiscal-year valuation ratios (see below)

## Commands

- `./vf company <identifier>` — company overview, key financials, statement availability, recent filings, valuation ratios, implied value range, reverse DCF
- `./vf comps AAPL MSFT GOOG` — side-by-side TTM comparison across multiple tickers
- `./vf ratios AAPL --limit 5` — annual historical valuation ratios going back N years

## comps.py

`fetch_comps_entries(tickers, ...)` fetches TTM financials in parallel; `build_comps_table(entries)` renders the comparison.

Columns: ticker, name, price, market_cap, revenue, net_income, owner_earnings, oe_margin_pct, pe_ratio, price_to_oe, oe_yield_pct, ev_to_ebitda, implied_growth_pct

`implied_growth_pct = 0.10 − (owner_earnings / market_cap)` (Gordon Growth at 10% required return); shown only when owner earnings are positive.

## ratios.py

- `build_historical_ratios_table(ticker, company_facts, price_history, limit)` — SEC path using annual companyfacts + Yahoo monthly price history
- `build_historical_ratios_table_from_yahoo(ticker, frames, price_history, limit)` — Yahoo annual frames path
- `_annual_period_end_dates(company_facts)` — recovers actual FY end dates from raw companyfacts (period labels lose the date)
- `_price_for_date(date, month_map)` — searches ±3 months in monthly price map for closest bar

Columns: fiscal_year, end_date, price, market_cap, net_income, revenue, owner_earnings, pe_ratio, price_to_oe, oe_yield_pct, pb_ratio, ev_to_ebitda

## Overview Schema

Current `overview` rows expose:
- `metric`, `value`, `unit`, `source`, `source_table`, `statement`, `period_type`, `as_of`
- `status`, `completeness`, `taxonomy`, `concept`, `matched_label`, `form`, `filed`, `reason`

Completeness states: `current`, `stale`, `missing`.

Market rows: `current` within 7 days of `latest_price_date`, `stale` otherwise, `missing` when date absent.

SEC rows: `current` when metric is from the latest available period in its statement group; `stale` otherwise.

## Valuation Sections (./vf company)

- **Valuation Ratios**: P/E, P/B, P/S, P/FCF, P/OE, earnings/FCF/OE yields, EV/Revenue, EV/EBITDA, per-share OE — uses TTM financials; rows omitted silently when denominator unavailable
- **Implied Value Range**: implied price per share at 10x/15x/20x/25x/30x owner earnings multiples; `upside_pct` vs current price (0-1 decimal); only shown when owner earnings are positive
- **Reverse DCF**: Gordon Growth implied perpetual growth rate at 8%/10%/12% required return; `zero_growth_price` = per-share OE / r; only shown when owner earnings are positive

Both sections work for SEC and Yahoo paths.

## Statement Rules

- SEC quarterly flows may derive quarter values from YTD/FY facts
- balance-sheet items stay instant; no subtraction logic
- diluted EPS / diluted shares prefer direct-quarter values
- BRK is the one current `statements` special case: `valuation.brk.statements` supplements Class B EPS/share rows for annual and direct-quarterly income statements when companyfacts omits them
- missing statement rows are explainable via `--diagnostics` / `--include-missing`; default output stays clean
- cash flow statement appends `free_cash_flow = operating_cash_flow − capex`; capex = `PaymentsToAcquirePropertyPlantAndEquipment` (always positive in SEC GAAP)
- SEC concept coverage extends to bank-style revenues (`RevenuesNetOfInterestExpense`) and alternate net-income/equity concepts so industrial defaults do not silently miss financial-institution issuers

## Yahoo Statement Constraints

- label mapping should stay explicit and shallow; no complex inference
- revenue fallbacks: `"Total Revenue"` → `"Net Revenue"` → `"Total Net Revenue"` (covers banks where top line is net interest + fees)
- stockholders_equity fallback: `"Common Stock Equity"` (covers European issuers where Yahoo omits `"Stockholders Equity"`)
- do not map `Cash Cash Equivalents And Short Term Investments` to `short_term_investments` (double-counts cash)
- do not map `Total Debt` to `long_term_debt` (includes current debt)
- European issuers may have genuine Yahoo quarterly gaps; do not synthesize quarters
- bank/insurance shapes can legitimately lack `gross_profit`, `current_assets`, `current_liabilities`

## Berkshire Alias Note

Plain `BRK` may resolve via Yahoo search to `BRK-B`. When that happens, retry the SEC lookup on the resolved symbol so `company` and `statements` stay on the SEC-backed path.

## Output Order (./vf company)

resolution → company → market snapshot → overview → key financials → statement availability → recent filings → valuation ratios → implied value range → reverse DCF
