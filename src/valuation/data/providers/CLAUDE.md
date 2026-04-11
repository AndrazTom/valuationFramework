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
- Yahoo specifics:
  - use Yahoo for quote search, profile fallback, price snapshot convenience, and broad non-US statement coverage
  - accept that Yahoo data can be sparse, stale, or inconsistent by metric
  - do not hide provider gaps with heavy inference in this layer
