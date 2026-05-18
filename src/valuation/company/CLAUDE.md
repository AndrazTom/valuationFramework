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
- SEC overview concept coverage should stay aligned with statement coverage where concepts are semantically reusable:
  - bank-style revenue concepts such as `RevenuesNetOfInterestExpense`
  - alternate net-income concepts such as common-stockholder net income and `ProfitLoss`
  - equity including noncontrolling interest when plain `StockholdersEquity` is absent or stale
- Yahoo overview rows should carry statement + matched-label provenance when available
- market overview rows should carry yfinance provenance in the existing columns:
  - `taxonomy=yfinance`
  - `concept` as the snapshot metric name
  - `matched_label` as the provider field or market-cap derivation source
- market overview completeness uses `latest_price_date`:
  - `current` within 7 days
  - `stale` when older
  - `missing` when values exist without a quote date
- unavailable overview reasons should stay metric-specific:
  - SEC missing rows should distinguish absent concepts, missing requested units, and present-but-blank values
  - Yahoo missing rows with non-empty frames should distinguish missing labels from labels present with blank values
- statement availability rows should distinguish:
  - `available`
  - `partial`
  - `unavailable`
- statement availability should expose expected metric counts and coverage, not just raw present counts
- partial statement-availability reasons should name the available/expected count and the first missing metrics, capped with `+N more` when needed

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
- BRK is the one current generic `statements` special case: `valuation.brk.statements` supplements annual/direct-quarterly Class B EPS and equivalent-share rows from filing report tables because SEC companyfacts omits those concepts for Berkshire
- missing statement rows should be explainable through an explicit diagnostic path; do not make users infer whether a row is absent because the concept is missing, stale, wrong-unit, or has no usable period
- `./vf statements ... --diagnostics` / `--include-missing` emits `Statement Diagnostics` for SEC-backed statements; keep default statement output clean
- cash flow statement appends a derived `free_cash_flow = operating_cash_flow - capex` row when both are present; capex is `PaymentsToAcquirePropertyPlantAndEquipment`, a positive outflow
- `./vf company` emits a `Valuation Ratios` section with P/E, P/B, P/S, P/FCF, P/OE, owner earnings yield, FCF yield, EV/Revenue, EV/EBITDA, and per-share owner earnings using TTM financials; works for both SEC and Yahoo paths; rows are omitted silently when a denominator is unavailable
- `./vf company` emits an `Implied Value Range` section after Valuation Ratios when owner earnings are positive: shows implied price per share at 10x/15x/20x/25x/30x owner earnings multiples with upside_pct vs current price (0-1 decimal)
- `./vf company` emits a `Reverse DCF` section when owner earnings are positive: uses Gordon Growth model to show implied perpetual growth rate at 8%/10%/12% required return, plus zero-growth fair value per share at each rate
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
