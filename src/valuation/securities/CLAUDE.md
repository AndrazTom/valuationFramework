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
