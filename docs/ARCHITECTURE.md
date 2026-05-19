# Architecture Direction

This project should be treated as one investing toolkit with two product areas:
portfolio operations and investment research. The current code already contains
both, but the user-facing direction is not clear enough yet.

## Product Areas

### Portfolio

Purpose: personal IBKR portfolio accounting and Slovenian tax reporting.

Primary jobs:
- import IBKR Activity Statement CSV and Flex Query XML exports
- track holdings, cost basis, realized gains, dividends, withholding tax, and FX
- reconcile outputs against filed private tax reports
- eventually generate FURS-ready `Doh-KDVP`, `Doh-Div`, and `Doh-Obr` XML

Correctness standard:
- outputs must be auditable from source broker rows
- tax reports should have reconciliation tables before any final XML generation
- private files stay under ignored paths such as `/portfolio/`, `outputs/`, or `.env`

Candidate CLI shape:

```bash
vf portfolio holdings
vf portfolio tax kdvp --year 2025
vf portfolio tax dividends --year 2025
vf portfolio tax interest --year 2025
vf portfolio reconcile --year 2025
vf portfolio doh --year 2025 --outdir ...
```

### Research

Purpose: company and security analysis.

Primary jobs:
- resolve identifiers such as ticker, CIK, ISIN, and CUSIP
- fetch SEC and Yahoo data
- build financial statement tables
- compute ratios, comps, reverse DCF, and watchlist views
- support specialized Berkshire Hathaway workflows

Candidate CLI shape:

```bash
vf research company AAPL
vf research statements AAPL --statement income
vf research ratios AAPL
vf research comps AAPL MSFT GOOGL
vf research watchlist show
vf research brk sotp
```

Existing top-level commands can remain as compatibility aliases while the
direction settles.

## One Repo Or Two

Recommendation: keep one repository for now.

Reasons:
- both areas share infrastructure: CLI, cache config, table rendering, FX, tests,
  and data-provider conventions
- portfolio and research workflows overlap in real use; portfolio holdings often
  lead to company research
- splitting too early would create package, release, and dependency overhead
  before the boundaries are proven

Use logical boundaries inside one repo:

```text
src/valuation/portfolio/   private-accounting and tax-reporting workflows
src/valuation/company/     generic company research
src/valuation/brk/         Berkshire-specific research
src/valuation/data/        provider integrations and normalization
src/valuation/reports/     shared table/output utilities
```

Consider two repositories only if one of these becomes true:
- portfolio code needs to be private while research code stays public
- portfolio logic becomes jurisdiction-specific enough to release separately
- the research toolkit becomes a reusable public package with a different audience
- dependencies, tests, or release cadence diverge materially

If that happens, a clean split would be:
- `valuation-research`: SEC/Yahoo research, statements, ratios, comps, BRK
- `portfolio-tax`: IBKR imports, Slovenian tax, FURS XML, private reconciliation

Until then, the right split is conceptual and CLI-level, not a physical repo split.

## Near-Term Hardening Plan

1. Make the README describe the two product areas clearly.
2. Add compatibility-safe command grouping:
   - keep current commands working
   - introduce `vf research ...` aliases gradually
   - refine `vf portfolio ...` names around holdings, tax, and reconciliation
3. Build `portfolio reconcile --year 2025` before any FURS XML generator.
4. Keep private brokerage and tax files out of Git with `.gitignore` and checks.
5. Add tests at the contract boundary: parser rows in, reconciled report rows out.

## Non-Goals For Now

- no large directory refactor just to make the tree look cleaner
- no FURS XML generator until reconciliation is boring and repeatable
- no second repository until privacy or release boundaries require it
