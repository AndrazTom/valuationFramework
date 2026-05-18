# valuation/data/providers

AI-only note for external data wrappers.

## Rules

- keep these clients small and boring
- normalize obvious field names but do not own product-level business rules

## SEC Provider (`sec.py`)

- `SecClient` requires a compliant `VALUATION_SEC_USER_AGENT`; surfaces a clear error when the placeholder is rejected
- separate methods for: ticker lookup, submissions, companyfacts, filing fetches
- filing report tables are parsed from SEC HTML in-code; do not reintroduce a hard runtime dependency on `lxml`
- **Persistent cache** under `~/.cache/valuationFramework/sec` (or `VALUATION_CACHE_DIR/sec`):
  - mutable endpoints expire: ticker map 24h, submissions 12h, companyfacts 24h
  - immutable filing artifacts (filing index JSON, `FilingSummary.xml`, report HTML, 13F XML) cached indefinitely
  - `./vf --refresh-cache ...` or `VALUATION_REFRESH_CACHE=1` bypasses reads and overwrites for the run
- to detect new filings after a long gap: refresh submissions, compare latest accession numbers/report dates to local index, then fetch only new filing artifacts

## Yahoo Provider (`yahoo.py`)

- use for: quote search, profile fallback, price snapshot, broad non-US statement coverage
- accept that Yahoo data can be sparse, stale, or inconsistent by metric; do not hide gaps with heavy inference
- **Persistent cache** under `~/.cache/valuationFramework/yahoo` (or `VALUATION_CACHE_DIR/yahoo`):
  - price snapshots expire after 1h
  - history frames expire after 24h
  - `./vf --refresh-cache ...` or `VALUATION_REFRESH_CACHE=1` bypasses reads and overwrites for the run
- price snapshots may derive `market_cap` from `last_price * shares` when Yahoo omits a direct `market_cap`
- keep `market_cap_source` so derived current market cap is visible to backend consumers
