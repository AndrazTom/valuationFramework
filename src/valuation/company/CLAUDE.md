# valuation/company

AI-only note for generic single-company workflows.

This package is where `main` should become useful on its own.

Current intent:

- accept flexible identifiers such as ticker, CIK, CUSIP, and ISIN when the free data path supports them
- resolve them into one canonical company/ticker view
- produce a TradingView-like baseline focused on financials, filings, and balance-sheet visibility
- keep the workflow generic and reusable, not Berkshire-specific

Rules:

- keep the public entrypoint simple: one identifier in, several clean tables out
- prefer official SEC facts for financial statements
- use Yahoo only for search and market snapshot convenience
- if a metric is missing, leave it blank rather than inventing heuristics
- keep the compact `overview` layer stable before expanding deeper metric sets
- current `overview` rows should expose:
  - `metric`
  - `value`
  - `unit`
  - `source`
  - `source_table`
  - `statement`
  - `period_type`
  - `as_of`
  - `status`
  - `completeness`
  - `taxonomy`
  - `concept`
  - `matched_label`
  - `form`
  - `filed`
  - `reason`
- `company` should present overview before key financials and statement availability
- overview completeness should stay simple:
  - `current`
  - `stale`
  - `missing`
- SEC overview rows should carry real `companyfacts` provenance when available
- Yahoo overview rows should carry statement + matched-label provenance when available
- market overview rows should carry yfinance provenance in the existing columns:
  - `taxonomy=yfinance`
  - `concept` as the snapshot metric name
  - `matched_label` as the provider field or market-cap derivation source
- statement availability rows should distinguish:
  - `available`
  - `partial`
  - `unavailable`
- statement availability should expose expected metric counts and coverage, not just raw present counts

Module ownership:

- `service.py`
  - resolve identifiers
  - choose SEC-backed versus Yahoo-backed path
  - fetch provider bundles concurrently where useful
- `tables.py`
  - define compact company-facing tables and overview/availability summaries
- `statements.py`
  - own SEC statement concept sets and quarterly reconstruction rules
- `yahoo_statements.py`
  - own Yahoo label mapping for fallback statements and Yahoo key financials

Statement rules:

- SEC quarterly flows may derive quarter values from YTD/FY facts
- balance-sheet items should stay instant and avoid subtraction logic
- diluted EPS / diluted shares should prefer direct-quarter values
- helper heuristics are acceptable only when they are narrow and defensible
- Yahoo statement handling should stay explicit and shallow; do not build complex inference layers on vendor-standardized rows
- Yahoo Europe hardening notes from `fix/european-yahoo-statements`:
  - several European issuers have real Yahoo quarterly gaps; do not "fix" those with synthetic quarter inference in the Yahoo path
  - bank/insurance statement shapes differ materially from generic industrials; missing `gross_profit`, `current_assets`, or `current_liabilities` can be real
  - avoid semantic drift in label fallbacks:
    - do not map `Cash Cash Equivalents And Short Term Investments` to `short_term_investments`
    - do not map `Total Debt` to `long_term_debt`
  - after Yahoo-focused fixes, run targeted unit tests plus live README/basic-flow verification before calling the branch merge-ready
- Berkshire alias note:
  - plain `BRK` may resolve from Yahoo search to `BRK-B`
  - when that happens, retry SEC lookup on the resolved Yahoo symbol so `company` and `statements` stay on the SEC-backed path instead of degrading to Yahoo fallback tables
