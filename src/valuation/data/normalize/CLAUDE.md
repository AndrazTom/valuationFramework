# valuation/data/normalize

AI-only note for normalization contracts.

This subtree is one of the real backend contract layers.

Rules:

- keep output schemas stable; downstream modules should not need to know raw SEC or Yahoo payload shapes
- `CompanyFactQuery` is the main primitive for selecting latest facts and statement rows
- statement-period selection and quarter reconstruction semantics live here together with `company/statements.py`
- `recent_filings_to_table()` is responsible for:
  - preferred-form filtering
  - filing ordering/prioritization
  - keeping core company views focused on analysis-relevant filings rather than ownership-form noise
  - normalized filing metadata columns
  - filing URL construction when enough SEC metadata exists
- when changing normalization behavior, add or update focused tests before changing CLI expectations
