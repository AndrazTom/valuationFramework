# valuation/tests

AI-only note for test expectations.

Rules:

- run tests against the repo source tree with `PYTHONPATH=src pytest -q`
- use `. .venv/bin/activate` first in this repo so runtime deps like `tabulate` are available
- env-loading coverage should verify both local `.env` support and exported-env precedence
- prefer targeted unit tests for normalization and table contracts before adding broader CLI coverage
- when adding a new `company` section, test both file outputs and JSON bundle keys
- CLI tests should stay offline and use monkeypatches or fixtures rather than live providers
- keep assertions focused on backend behavior and stable contracts, not incidental table formatting
- current full-suite baseline after hardening batch: `402 passed`

Coverage map:

- `test_brk_holdings.py`, `test_brk_service.py`, `test_brk_tables.py`, and `test_brk_segments.py` cover Berkshire-specific workflows on the `brk` branch
- `test_company_service.py` covers identifier resolution and SEC/Yahoo path selection
- `test_normalize_tables.py` covers latest-fact resolution and filing normalization
- `test_statement_matrix.py` covers the tricky quarterly statement semantics
- `test_company_tables.py` covers company-view tables such as overview and statement availability
- `test_company_tables.py` is also where overview provenance/completeness behavior is currently locked down
- `test_company_tables.py` also locks down statement-availability partial-coverage behavior
- `test_normalize_tables.py` locks down core filing filtering so noisy ownership forms do not leak into preferred company filing views
- `test_cli.py` covers section wiring and output artifacts
- `test_security_pricing.py` covers reusable price-change enrichment and graceful degradation on quote/history failures
- `test_security_pricing.py` also covers bounded live quote enrichment via `max_holdings`
- `test_brk_tables.py` covers reported vs live selected 13F equity values, live revaluation detail rows, and public-equity tax context/sensitivity tables for the BRK SOTP/report tables
- `test_brk_tables.py` also covers tax edge cases: None context, empty equity note, underwater portfolio, after-tax value invariant
- `test_yahoo_statement_tables.py` covers bank/insurance shapes (no gross_profit, no current items), Net Revenue fallback, TTM on partial quarters, Common Stock Equity fallback
- `test_ratios.py` now covers `build_historical_ratios_table` (SEC path) and `build_historical_ratios_table_from_yahoo` in addition to helpers
- `test_yahoo_provider.py` covers Yahoo provider fallbacks when fast-info or history calls fail
- `test_brk_holdings.py` covers `aggregate_13f_holdings`: empty input, duplicate issuer consolidation, distinct issuers stay separate, investment_discretion/other_manager text merge, sort order
- `test_brk_tables.py` also covers T-bill payable plural variant (`Payable for purchases of U.S. Treasury Bills`)
- `test_brk_tables.py` covers `build_buyback_history_table`: basic buyback row, CAGR direction (oldest→newest), implied price per share when shares-retired data present, per-current-share row, and empty return when concept absent
- `test_ratios.py` covers `oe_per_share` in both SEC and Yahoo paths
- `test_brk_tables.py` covers `build_insurance_float_table`: basic multi-component, positive CAGR direction, partial components (only losses), empty return when concepts absent
- `test_brk_tables.py` covers `build_book_value_history_table` CAGR direction: positive CAGR for growing equity (guards against newest-first bug)
- `test_company_service.py` covers SEC failure isolation: SEC bundle crash does not propagate when Yahoo market data succeeds
- `test_yahoo_provider.py` covers `latest_price_date` populated from fast-info path, and missing Close column safe degradation
- `test_ratios.py` Yahoo path `oe_per_share` uses correct capex sign (abs normalization)
- `test_brk_tables.py` covers `build_opco_segment_industry_multiples_table`: basic structure, correct multiples per segment, total sums, empty-on-no-segments
- `test_portfolio.py` covers IBKR parser (Order/Execution deduplication, BOM, thousand-separators, dividends+WHT, metadata/period), FIFO engine (single buy, full/partial sell, spanning lots, multi-symbol, gain calculation, non-EUR/FX flag, same-day buy-before-sell ordering), ECB FX client (cache, weekend lookback, missing rate, build_fx_rates_dict, CSV parser), Slovenian CGT (rates, thresholds, leap-day anniversary), and dividend tax (WHT credit, effective rate)
- `test_normalize_tables.py` covers `_derive_duration_entry` None-propagation: Q2 derived from (Q2_ytd - Q1) where Q1 val is None must yield None, not 0 or the YTD value
- `test_portfolio.py` covers `ibkr_flex.py`: FlexLot parsing (symbol/dates/cost/pnl), proceeds_native property, SELL-only filter, zero-quantity skip, dividend with explicit type + WHT match, metadata, datetime format parsing, per-share description regex, WHT rate arithmetic derivation (clean integer check + non-integer rejection), Lot-element fallback for pre-period buys, `parse_flex_interest` (basic records, WHT matching via CREDIT INT)
- `test_portfolio.py` also covers `portfolio reconcile`: table output artifacts, JSON bundle section names, and statement-gap detection for the audit workflow
- `test_portfolio.py` covers filing-shaped portfolio outputs: KDVP rows for `portfolio gains`, Doh-Div rows for `portfolio dividends`, and Doh-Obr rows for `portfolio interest`
