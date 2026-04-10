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
