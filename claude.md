# valuationFramework

AI-only repo contract.

## Purpose

Build a practical stock-financials and valuation backbone.

Current branch priority:

- `main` should be useful on its own for generic company inspection
- `brk` is the Berkshire-specific proving ground
- temporary hardening branches should be merged back quickly, then deleted

Long-term direction:

- a smaller personal alternative to the financial-data side of TradingView
- more emphasis on statements, balance sheets, and cash flows
- free-first where practical
- CLI first, thin API/UI later

## Documentation Rules

- `README.md` is for humans
- `claude.md` and subtree `CLAUDE.md` files are AI-only readmes
- keep `claude.md` current so a new chat can resume work quickly
- add subtree `CLAUDE.md` files only when module-specific context is genuinely useful

## Current Architecture

Preferred flow:

1. provider adapters fetch raw data
2. normalization turns provider payloads into stable tables
3. report/render layer emits terminal, Markdown, CSV, later API responses
4. model layer should stay separate from rendering

Rules:

- keep exact raw numeric values in backend tables
- apply human-readable formatting only in report/render layers
- treat `security_id` as the canonical backend identifier
- treat ticker as a market-data alias, not the only identity
- prefer official SEC facts for financial statements
- use Yahoo mainly for market snapshot convenience and identifier search
- for non-US coverage, use Yahoo as the first broad fallback for profile + statements when it actually has data
- do not pretend Yahoo is universal; small markets may need explicit market-specific adapters later

## Main Branch Goal

`main` should provide a clean generic company workflow:

- accept flexible identifiers such as ticker, CIK, CUSIP, and ISIN when the free path supports them
- resolve them into one company/ticker view
- output a simple baseline similar to a financials-first TradingView page:
  - resolution
  - company metadata
  - market snapshot
  - key financial facts
  - recent filings

Keep `main` generic. Do not leak Berkshire assumptions into generic modules.

## Berkshire Branch Goal

`brk` is for:

- latest 13F holdings
- optional live-price revaluation
- liquidity bridge
- operating segment extraction
- later Berkshire sum-of-the-parts logic

Reusable pieces discovered there should be extracted back into `main`.

## Current Main Features

As of 2026-04-09, `main` should contain or move toward:

- repo-local launcher via `./vf`
- generic `valuation company <identifier>` CLI
- ticker / CIK / CUSIP / ISIN resolution through SEC + Yahoo
- initial non-US fallback path through Yahoo-backed company/profile/statement workflows
- compact terminal tables with shorter headers
- selected generic SEC financial facts
- generic statements command backed by SEC companyfacts:
  - income
  - balance
  - cashflow
  - annual and quarterly
  - optional start/end year filters
  - optional start/end quarter filters for quarterly views
  - quarterly handling is metric-aware:
    - additive flows may derive from YTD/FY
    - balance-sheet items stay instant
    - diluted EPS / diluted shares should prefer direct-quarter facts and avoid subtraction

## Current Commands

- `./setup`
- `./vf company BRK-B`
- `./vf company BNP.PA`
- `./vf company SI0031102120`
- `./vf company US0846707026`
- `./vf snapshot BRK-B`
- `./vf statements AAPL --statement income --period annual`
- `./vf statements BNP.PA --statement income --period annual`
- `./vf statements AAPL --statement balance --period quarterly`

## Next Main Priorities

- improve statement concept coverage and defaults
- prefer cleaner core-company filing views over noisy insider-form streams
- keep narrowing wide tables where possible
- add JSON output only after the table backbone is solid
- decide where Yahoo fallback is sufficient versus where market-specific filing adapters are worth building
- for Europe, prefer:
  - Yahoo fallback for broad coverage
  - then exchange / OAM / issuer-report adapters only where Yahoo coverage is missing or misleading

## Statement Debug Notes

- Berkshire currently has real SEC `companyfacts` sparsity for some standard income metrics
- As of 2026-04-09 inspection:
  - `EarningsPerShareDiluted` is absent for BRK in SEC companyfacts
  - `WeightedAverageNumberOfDilutedSharesOutstanding` is absent for BRK in SEC companyfacts
  - `GrossProfit` is absent for BRK in SEC companyfacts
  - `OperatingIncomeLoss` exists for BRK but recent-period coverage is sparse/stale
- Blank cells for those BRK rows are currently expected from the upstream data, not necessarily extraction bugs
- Quarterly statement logic now distinguishes:
  - additive flows
  - instant balance-sheet facts
  - direct-quarter-only metrics such as diluted EPS / diluted shares
- Debug branch note:
  - for some issuers like AAPL, fiscal year-end quarter diluted shares may be absent as direct quarter facts
  - current debug behavior allows diluted shares to fall back to the FY average share count for that year-end quarter
  - current debug behavior can then backfill diluted EPS from `quarter net income / diluted shares`
  - this is a pragmatic fallback, not a perfect ground-truth replacement for a missing direct-quarter disclosure
- Financial-institution note:
  - banks like JPM often do not populate industrial-style quarterly income concepts in the way industrial issuers do
  - generic revenue / pretax coverage should include bank-style concepts such as:
    - `RevenuesNetOfInterestExpense`
    - `InterestIncomeOperating`
    - `InterestIncomeExpenseNet`
    - `NoninterestIncome`
    - `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
- Cross-sector sweep note:
  - AAPL now looks broadly healthy on income, balance, and cashflow
  - JPM income improved after bank-style revenue / pretax concept coverage
  - CAT net income required alternate concepts such as `NetIncomeLossAvailableToCommonStockholdersBasic` / `ProfitLoss`
  - BRK still has real upstream sparsity for diluted-share / diluted-EPS fields
  - some rows like `gross_profit` remain sector-dependent and should not always be forced into existence
  - user-facing statement tables should prefer dropping rows that are entirely empty across the selected periods rather than showing sector-inappropriate blanks
  - generic balance sheet fallbacks now need to include broader equity and debt concepts where they are semantically close enough
  - external QA against StockAnalysis quarterly pages on 2026-04-10:
    - AAPL and JPM currently line up well on the main displayed income rows
    - XOM had a real year-end diluted-share gap; current fallback now uses basic-share data when observed basic and diluted EPS match
    - PGR operating income exists in vendor-standardized views but is not safely reconstructible from SEC companyfacts alone right now
    - UNH has small vendor-vs-companyfacts differences on net income; treat current `NetIncomeLoss` selection as shareholder-oriented SEC output unless a better generic rule is proven

## International Notes

- As of 2026-04-10, non-US support does not require a total rewrite
- current workable split:
  - SEC-backed path for US issuers
  - Yahoo-backed fallback for non-US issuers when Yahoo has usable profile + statement coverage
- live proof points:
  - `BNP.PA` works directly as a non-US large-cap fallback case
  - `KRKG` and ISIN `SI0031102120` can resolve through non-US fallback paths, but exchange/ticker quality should be treated carefully
  - direct `KRKG.LJ` is not usable through Yahoo and should fail cleanly rather than inventing a fake company
- likely medium-term structure:
  - keep Yahoo as the broad global baseline
  - add country / market specific adapters only for markets where Yahoo fails and where official filings are realistically parseable
  - Europe is unlikely to be one simple unified free API; expect exchange / OAM / issuer-specific work for deeper coverage
- display note:
  - non-USD company views should render market snapshot prices with the table currency hint instead of defaulting to USD
  - example target behavior: `EUR 236.5`, not `$236.5`

## Branch State

- `main`
  - should hold the reusable generic backbone, including the merged statement QA work and the first non-US Yahoo fallback path
- `brk`
  - remains the Berkshire-specific proving ground

## Quality Bar

- prioritize code quality over feature count
- prefer fewer, clearer modules over many thin wrappers
- delete code that is not pulling its weight
- keep tests that protect real behavior; skip decorative or low-signal tests
- preserve a clean path for later API/UI work without adding that surface too early

## Git / Publication

- repo remote: `https://github.com/AndrazTom/valuationFramework`
- keep the GitHub repo private unless the user explicitly changes that
- keep commits organized by reusable concern
- push stable `brk` checkpoints freely
- when generic work is ready, port it cleanly to `main`
