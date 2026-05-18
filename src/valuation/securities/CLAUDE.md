# valuation/securities

AI-only note for canonical identifier logic.

Rules:

- `security_id` is a backend join key, not a display field
- prefer:
  - `cusip:*` when available
  - then `cik:*`
  - then exchange-qualified ticker IDs
- unqualified tickers are weaker identifiers and should be treated as such
- keep identifier building deterministic and side-effect free

## Pricing Helpers

- `pricing.py` enriches holding rows by joining `security_id` to a reference table with market tickers, then applying Yahoo quote/history snapshots
- `enrich_holdings_with_market_prices(..., max_holdings=N)` limits live quote/history fetches to the first N holdings after upstream sorting; unpriced rows remain in the returned frame with null live values
- quote and history fetches run in a bounded thread pool (`max_workers <= 8`) and must continue to degrade gracefully on provider/rate-limit failures
