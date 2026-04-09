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
