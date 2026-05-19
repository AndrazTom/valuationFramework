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

Current repo-root launcher:

```bash
./vf portfolio show                              # open positions with live prices
./vf portfolio tax --year 2025                   # realized gains + KDVP filing rows
./vf portfolio dividends --year 2025             # dividend income + Doh-Div filing rows
./vf portfolio interest --year 2025              # broker interest + Doh-Obr filing rows
./vf portfolio reconcile --year 2025             # audit coverage before filing
./vf portfolio furs-xml --file flex.xml --year 2025   # generate eDavki XML
```

The `furs-xml` command produces `Doh-KDVP.xml`, `Doh-Div.xml`, and `Doh-Obr.xml`
under `outputs/tables/portfolio_furs_{year}/`. These can be uploaded directly to
eDavki. Taxpayer personal details are read from `FURS_*` env vars (set in `.env`
or exported). Flex Query XML is the required input format; Activity Statement CSV
is not sufficient for the XML generator.

### IBKR Flex Query setup

Configure an **Activity Flex Query** in IBKR (Performance & Reports → Flex Queries → "+"):

| Section | Options / Fields |
|---|---|
| Account Information | IB Entity, Account ID |
| Trades | Options: **Executions** + **Closed Lots**; then **Select All** fields |
| Corporate Actions | **Select All** fields |
| Cash Transactions | Options: **Dividends**, **Payment in Lieu of Dividends**, **Withholding Tax**, **Broker Fees**, **Broker Interest Received**; then **Select All** fields |
| Financial Instrument Information | **Select All** fields |

When running the report: Period → **Custom Date Range** → Jan 1–Dec 31 of the
target year. Generate one file per calendar year. Also run a report for the
current year when filing a past year — some WHT entries are reported retroactively.

**Multi-account**: on the Reports page use "Select Account(s)" and filter to show
Open + Closed + Migrated accounts to capture accounts from the IBUK → IBCE → IBIE
migrations.

Flex Query configuration instructions adapted from
[ib-edavki](https://github.com/ib-edavki/ib-edavki).

### Research

Purpose: company and security analysis.

Primary jobs:
- resolve identifiers such as ticker, CIK, ISIN, and CUSIP
- fetch SEC and Yahoo data
- build financial statement tables
- compute ratios, comps, reverse DCF, and watchlist views
- support specialized Berkshire Hathaway workflows

Possible future grouped CLI shape:

```bash
./vf research company AAPL
./vf research statements AAPL --statement income
./vf research ratios AAPL
./vf research comps AAPL MSFT GOOGL
./vf research watchlist show
./vf research brk sotp
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
   - introduce `./vf research ...` aliases gradually
   - refine `./vf portfolio ...` names around holdings, tax, and reconciliation
3. Keep hardening `./vf portfolio reconcile --year 2025` alongside the FURS XML generator.
4. Keep private brokerage and tax files out of Git with `.gitignore` and checks.
5. Add tests at the contract boundary: parser rows in, reconciled report rows out.

## Non-Goals For Now

- no large directory refactor just to make the tree look cleaner
- no FURS XML submission automation (manual eDavki upload is the intended workflow)
- no second repository until privacy or release boundaries require it
