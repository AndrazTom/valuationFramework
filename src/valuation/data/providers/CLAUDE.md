# valuation/data/providers

AI-only note for external data wrappers.

Rules:

- keep these clients small and boring
- provider clients should normalize obvious field names but should not own product-level business rules
- SEC specifics:
  - `SecClient` requires a compliant user agent
  - surface a clear error when the placeholder `VALUATION_SEC_USER_AGENT` is rejected
  - keep ticker lookup, submissions, companyfacts, and filing fetches separate
  - filing report tables are now parsed from SEC HTML in-code
  - do not reintroduce a hard runtime dependency on `lxml` just to read SEC filing tables
  - persistent cache is enabled by default under `~/.cache/valuationFramework/sec` or `VALUATION_CACHE_DIR/sec`
  - ticker map, submissions, and companyfacts have TTLs; filing archive artifacts are immutable and cached indefinitely
  - `VALUATION_REFRESH_CACHE=1` or `./vf --refresh-cache ...` bypasses reads and overwrites cache entries for the run
  - to detect new filings after months or years, refresh submissions, compare latest accession numbers/report dates with the local index, then fetch only new filing artifacts
- Yahoo specifics:
  - use Yahoo for quote search, profile fallback, price snapshot convenience, and broad non-US statement coverage
  - accept that Yahoo data can be sparse, stale, or inconsistent by metric
  - do not hide provider gaps with heavy inference in this layer
  - persistent cache is enabled by default under `~/.cache/valuationFramework/yahoo` or `VALUATION_CACHE_DIR/yahoo`
  - price snapshots expire after 1h; history frames expire after 24h
  - `VALUATION_REFRESH_CACHE=1` or `./vf --refresh-cache ...` bypasses Yahoo cache reads and overwrites entries for the run
  - price snapshots may derive `market_cap` from `last_price * shares` when Yahoo omits direct `market_cap`
  - keep `market_cap_source` so derived current market cap is visible to backend consumers
