# valuation/data/normalize

AI-only note for normalization contracts.

This subtree is one of the real backend contract layers.

## Rules

- keep output schemas stable; downstream modules should not need to know raw SEC or Yahoo payload shapes
- `CompanyFactQuery` is the main primitive for selecting latest facts and statement rows
- statement-period selection and quarter reconstruction semantics live here together with `company/statements.py`
- `recent_filings_to_table()` is responsible for:
  - preferred-form filtering (`10-K`, `10-Q`, `8-K`, `20-F`, `6-K`, `40-F`, `DEF 14A`)
  - filing ordering/prioritization
  - keeping core company views focused on analysis-relevant filings rather than ownership-form noise
  - normalized filing metadata columns including `filing_url` when SEC metadata is sufficient
- when changing normalization behavior, add or update focused tests before changing CLI expectations
- filing metadata columns used by `company` views:
  - `filing_date`, `report_date`, `accepted_at`, `form_group`, `accession_number`, `description`, `primary_document`, `filing_url`
