# valuationFramework

AI-only repo contract.

## Purpose

Build a practical stock-financials and valuation backbone.

Current branch priority:

- `main` should be useful on its own for generic company inspection
- `brk` is the Berkshire-specific proving ground
- `statement-debug` is the temporary correctness-hardening branch for statement extraction

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
- `./vf company US0846707026`
- `./vf snapshot BRK-B`
- `./vf statements AAPL --statement income --period annual`
- `./vf statements AAPL --statement balance --period quarterly`

## Next Main Priorities

- improve statement concept coverage and defaults
- prefer cleaner core-company filing views over noisy insider-form streams
- keep narrowing wide tables where possible
- add JSON output only after the table backbone is solid

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
