# valuationFramework

AI-only repo contract.

## Purpose

Build a practical stock-financials and valuation backbone.

Project posture:

- this is a serious personal investing project first
- optimize first for your own research edge, workflow quality, and trust in the numbers
- treat commercial use as optional future upside, not the present objective
- do not aim to become a generic broad-market terminal competing head-on with Koyfin, TIKR, Fiscal.ai, or BamSEC
- if the project becomes commercial later, the likely path is through a narrow wedge, specialized workflow, premium research, or an agent/API layer rather than a mass-market terminal

Current branch priority:

- `main` should be useful on its own for generic company inspection
- `brk` is the Berkshire-specific proving ground
- temporary hardening branches should be merged back quickly, then deleted
- current hardening branch `fix/european-yahoo-statements` is focused on Yahoo-backed European statement correctness

Long-term direction:

- a smaller personal alternative to the financial-data side of TradingView
- more emphasis on statements, balance sheets, and cash flows
- free-first where practical
- CLI first, thin API/UI later
- keep it personal-first until repeated real use proves a sharper product wedge

## Documentation Rules

- `README.md` is for humans
- `claude.md` and subtree `CLAUDE.md` files are AI-only readmes
- keep `claude.md` current so a new chat can resume work quickly
- coding agents should update root `claude.md` whenever meaningful backend behavior, priorities, branch state, or workflow assumptions change
- coding agents should also update relevant subtree `CLAUDE.md` files regularly when module-local contracts or workflow expectations change
- create a new subtree `CLAUDE.md` when a module has enough local context that future chats would otherwise have to rediscover it
- add subtree `CLAUDE.md` files only when module-specific context is genuinely useful
- after implementation work is complete, a separate Codex/Claude review pass should inspect the patch, run tests, and verify the basic README-listed workflows before the branch is considered ready to merge

## Working Notes

- run commands from the repo root
- use the repo venv when verifying behavior:
  - `. .venv/bin/activate`
  - `PYTHONPATH=src pytest -q`
- bare `pytest` can import the wrong package tree if `src/` is not on `PYTHONPATH`
- the shell environment may not always have `rg`; standard tools like `find`, `sed`, and `grep` are acceptable fallbacks
- SEC env note:
  - support both a repo-local `.env` and explicit exported variables
  - code should load `.env` without relying only on the `vf` shell wrapper
  - exported env vars should keep precedence over `.env`

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
- prefer adding stable backend tables/objects before adding more CLI surface area
- keep module boundaries explicit:
  - `data/providers` fetch
  - `data/normalize` stabilizes
  - `company` assembles product-facing tables
  - `reports` renders and exports

## Repo Map

- `src/valuation/cli.py`
  - command parsing and top-level orchestration
  - should stay thin
- `src/valuation/company/service.py`
  - identifier resolution and provider orchestration
  - decides SEC-backed versus Yahoo-backed company paths
- `src/valuation/company/statements.py`
  - generic SEC statement metric definitions
  - quarterly reconstruction heuristics and sparse-data handling
- `src/valuation/company/yahoo_statements.py`
  - explicit Yahoo label mapping
  - fallback path only, not a deep modeling layer
- `src/valuation/company/tables.py`
  - compact backend-facing company tables such as summary, overview, and statement availability
- `src/valuation/data/normalize/tables.py`
  - core normalization contract layer
  - latest-fact selection, filing normalization, statement period matrix logic
- `src/valuation/data/providers/`
  - thin wrappers over SEC and Yahoo
- `src/valuation/reports/tables.py`
  - rendering and export helpers
- `src/valuation/securities/identifiers.py`
  - canonical `security_id` rules
- `tests/`
  - statement matrix and normalization tests are the main behavioral guardrails

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
- `company` is moving toward the primary single-security backend view:
  - resolution
  - company/profile metadata
  - market snapshot
  - overview
  - key financials
  - statement availability
  - recent analysis-relevant filings
- compact terminal tables with shorter headers
- minimal CLI JSON output path for machine-readable backend bundles
- compact `overview` rows that combine market data with latest core financial metrics
- overview rows now carry lightweight provenance/completeness metadata for backend use
- selected generic SEC financial facts
- generic statements command backed by SEC companyfacts:
  - income
  - balance
  - cashflow
  - annual and quarterly
  - optional start/end year filters
  - optional start/end quarter filters for quarterly views
  - when any statement range filter is provided, the CLI default limit should widen enough that the range filter, not the default `--limit`, controls the output
  - quarterly handling is metric-aware:
    - additive flows may derive from YTD/FY
    - balance-sheet items stay instant
    - diluted EPS / diluted shares should prefer direct-quarter facts and avoid subtraction

## Current Commands

- `./setup`
- create a local `.env` with `VALUATION_SEC_USER_AGENT=...` or export it in shell for SEC access
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
- keep strengthening `company` as the main reusable backend object before adding API/UI surface
- keep the compact `overview` layer stable and increase trust/provenance before expanding metric count
- keep statement availability metadata honest about partial coverage, not just all-or-nothing availability
- prefer cleaner core-company filing views over noisy insider-form streams
- keep narrowing wide tables where possible
- keep the new JSON path minimal and backend-oriented rather than turning it into an API surface too early
- decide where Yahoo fallback is sufficient versus where market-specific filing adapters are worth building
- for Europe, prefer:
  - Yahoo fallback for broad coverage
  - then exchange / OAM / issuer-report adapters only where Yahoo coverage is missing or misleading
- live sweep note for `fix/european-yahoo-statements`:
  - broad annual Yahoo statement coverage across large-cap European industrial names is mostly healthy
  - some issuers have genuine Yahoo quarterly gaps, especially quarterly income/cashflow for several UK/Swiss/French names and quarterly cashflow for some banks/insurers
  - banks and insurers often lack generic rows like `gross_profit`, `current_assets`, and `current_liabilities`; treat that as sector-shape reality, not automatically as a mapper bug
  - two Yahoo mapping correctness issues were confirmed from live data:
    - `short_term_investments` must not use `Cash Cash Equivalents And Short Term Investments`, because that double-counts cash
    - `long_term_debt` must not fall back to `Total Debt`, because that can include current debt and overstate the non-current line
  - Berkshire ticker-alias note from 2026-05-03:
    - `BRK` can resolve through Yahoo to `BRK-B`
    - ticker resolution must still retry SEC lookup on the resolved Yahoo symbol so statement commands stay on the SEC-backed path
    - as of 2026-05-03, Berkshire's SEC submissions feed did not yet show a Q1 2026 `10-Q`; do not treat the absence of a `2026 Q1` statement on that date as a statement-builder bug
- product strategy note:
  - default assumption is personal-project utility, not startup theater
  - the right near-term test is whether the code improves your investing decisions, speed, and confidence
  - postpone broad commercialization until there is a clear differentiated wedge proven by real repeated use
  - likely future monetization paths, if they become justified:
    - niche research workflow
    - specialized holding-company / SOTP tooling
    - filing-audit and provenance tooling
    - agent-ready financial research API

## Resume Plan

When resuming work after the current overview hardening, keep the next steps in this order:

1. strengthen overview quality and provenance
   - keep `company` backend-first
   - add clearer provenance and completeness signals for overview metrics
   - prefer compact trustworthy metadata over adding many new metrics
2. improve the compact security overview model
   - make `overview` the stable summary backbone for one security
   - keep `key financials` as the deeper supporting table
   - avoid overcomplicating the schema too early
3. keep improving statement metadata and availability reasons
   - surface why a metric or statement is unavailable
   - keep provider gaps explicit, especially for Yahoo-backed non-US names
4. keep filing quality high
   - continue prioritizing analysis-relevant forms over noisy filing streams
   - preserve useful filing metadata for backend consumers
5. postpone broader expansion until the core backend is stronger
   - no urgent need to add more countries right now
   - no urgent need to add ETF or real index support right now
   - only expand market coverage after the core single-security workflow is more trustworthy

Immediate next implementation target:

- add provenance/completeness fields to the compact overview layer in a minimal way
- keep the table output, but move toward a more canonical machine-friendly overview contract underneath if needed

## Statement Debug Notes

- Berkshire currently has real SEC `companyfacts` sparsity for some standard income metrics
- the trickiest generic statement logic currently lives in:
  - `src/valuation/company/statements.py`
  - `src/valuation/data/normalize/tables.py`
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
  - CLI behavior note:
    - if a statement fetch normalizes to no rows, fail cleanly instead of writing a successful `(no rows)` table
    - `change_in_cash` should never fall back to `End Cash Position`; that is semantically a balance, not a flow
  - test coverage note:
    - `tests/test_statement_matrix.py` protects SEC quarterly matrix semantics
    - `tests/test_yahoo_statement_tables.py` protects Yahoo label mapping and period filtering
  - company-view note:
    - `company` should expose statement availability with explicit source + availability reason codes
    - statement availability should distinguish:
      - `available`
      - `partial`
      - `unavailable`
    - for Yahoo-backed names, empty quarterly frames should surface as provider gaps, not silent blanks

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
- European Yahoo QA note from 20-company sweep on 2026-04-10:
  - broad annual statement coverage looks workable across major EU/UK large caps
  - some issuers such as `MC.PA`, `OR.PA`, `NESN.SW`, and `SU.PA` have no Yahoo quarterly income/cashflow frames
  - those empty quarterly cases should error clearly rather than pretending the command succeeded

## Company View Notes

- As of 2026-04-10 hardening:
  - SEC-backed `company` views should enrich identity rows with Yahoo profile metadata when available
  - `company` should expose a compact `overview` layer before the deeper financial tables
  - overview rows should stay stable and backend-friendly:
    - `metric`
    - `value`
    - `unit`
    - `source`
    - `source_table`
    - `statement`
    - `period_type`
    - `as_of`
    - `status`
    - `completeness`
    - `taxonomy`
    - `concept`
    - `matched_label`
    - `form`
    - `filed`
    - `reason`
  - overview should combine:
    - market snapshot metrics from `yfinance`
    - latest core financial metrics from SEC or Yahoo
  - current implementation note:
    - overview is still built as a table in `company/tables.py`
    - later work can promote it to a more canonical machine object if the backend needs that
  - completeness should stay simple:
    - `current`
    - `stale`
    - `missing`
  - current completeness behavior:
    - market rows are `current` when the market snapshot has a value
    - SEC rows compare each metric to the latest available `as_of` within its statement group
    - Yahoo rows compare each metric to the latest available annual period within its statement frame
  - current overview metric set should stay compact:
    - `last_price`
    - `market_cap`
    - `shares`
    - `revenue`
    - `net_income`
    - `operating_cash_flow`
    - `cash_and_equivalents`
    - `total_assets`
    - `total_liabilities`
    - `stockholders_equity`
  - market snapshot behavior:
    - Yahoo may return `last_price` and `shares` while leaving `market_cap` blank
    - when that happens, the snapshot should derive current `market_cap` as `last_price * shares`
    - keep `market_cap_source` so downstream users can tell direct Yahoo market cap from derived current market cap
    - overview market rows should carry `taxonomy=yfinance`, `concept=<metric>`, and `matched_label` for the provider field or derived market-cap source
    - overview market rows should mark quote completeness as:
      - `current` when `latest_price_date` is within 7 days
      - `stale` when older than 7 days
      - `missing` when a value exists but the quote date is absent
  - `company` should show a statement-availability table with:
    - `statement`
    - `period`
    - `source`
    - `status`
    - `period_count`
    - `metric_count`
    - `expected_metric_count`
    - `coverage_ratio`
    - `latest_period`
    - `reason`
  - statement availability status should mean:
    - `available`: mapped all expected visible metrics for that statement
    - `partial`: statement exists but metric coverage is incomplete
    - `unavailable`: no usable rows after normalization
  - partial statement-availability reasons should include:
    - present/expected metric counts
    - the first few missing metric names
    - a `+N more` suffix when needed to keep the table compact
  - preferred unavailable reasons currently include:
    - `No matching SEC companyfacts concepts: ...`
    - `Yahoo returned no statement frame`
    - `Statement frame present but no mapped metrics`
  - overview unavailable reasons should be metric-specific where possible:
    - SEC rows should distinguish absent candidate concepts, present concepts with missing requested units, and present concepts with no usable values
    - Yahoo rows with a non-empty frame should distinguish absent candidate labels from present-but-blank labels
  - for SEC issuers, recent filings in `company` should prefer analysis-relevant forms like:
    - `10-K`
    - `10-Q`
    - `8-K`
    - `20-F`
    - `6-K`
    - `40-F`
    - `DEF 14A`
  - filing rows should preserve backend-useful metadata where available:
    - `filing_date`
    - `report_date`
    - `accepted_at`
    - `form_group`
    - `accession_number`
    - `description`
    - `primary_document`
    - `filing_url`
  - `company` command order should remain:
    - resolution
    - company
    - market snapshot
    - overview
    - key financials
    - statement availability
    - recent filings
  - live smoke sweep on 2026-05-16 after overview/availability hardening:
    - commands checked for `AAPL`, `BRK-B`, `JPM`, `BNP.PA`, and `NESN.SW`
    - `company`, `statements --statement income --period annual`, and `statements --statement balance --period quarterly` all exited 0
    - market overview rows showed current `latest_price_date=2026-05-15` for all five names
    - SEC-backed `AAPL` had full statement availability in company view
    - `BRK-B` and `JPM` correctly surfaced sector/company-shape partial coverage reasons
    - Yahoo-backed `BNP.PA` and `NESN.SW` worked through company and statements paths, with provider gaps explicit for missing quarterly frames
    - observed follow-up at the time: JPM overview `revenue` was stale while net income and balance rows were current
  - follow-up hardening pass on 2026-05-16:
    - README examples all exited 0, including `BRK` resolving to SEC-backed `BRK-B`
    - broader sample checked `JPM`, `XOM`, `PGR`, `UNH`, `CAT`, `MSFT`, `NESN.SW`, `MC.PA`, `OR.PA`, `SU.PA`, and `ASML.AS`
    - fixed compact SEC overview coverage by reusing statement-grade concepts:
      - bank-style revenue concepts fixed stale JPM overview revenue after raw concept inspection confirmed current `RevenuesNetOfInterestExpense`
      - alternate stockholders-equity concept fixed missing/stale CAT and UNH overview equity
      - alternate net-income concepts fixed CAT overview choosing stale proxy `NetIncomeLoss`
    - European Yahoo quarterly gaps for `NESN.SW`, `MC.PA`, `OR.PA`, and `SU.PA` remained genuine missing-provider-frame cases and should continue to fail/surface clearly rather than be synthesized

## Test Notes

- `tests/test_company_service.py`
  - identifier resolution and provider-path selection
- `tests/test_normalize_tables.py`
  - latest-fact resolution, filing normalization, and table contracts
- `tests/test_statement_matrix.py`
  - quarterly duration/direct/instant semantics and sparse-data behavior
- `tests/test_company_tables.py`
  - company summary, overview provenance/completeness, and statement-availability contracts
- `tests/test_cli.py`
  - section wiring, file outputs, and JSON bundle coverage

## Output Notes

- As of 2026-04-10 hardening:
  - CLI commands support `--format json`
  - JSON mode should:
    - print one pure JSON bundle to stdout
    - preserve raw numeric values instead of display-formatted strings
    - write per-section `.json` files plus `bundle.json`
  - current intended use is backend contract hardening, not public API design yet

## Repo Hygiene Notes

- local `.codex` workspace artifacts are tooling noise and should stay ignored in Git

## Branch State

- `main`
  - should hold the reusable generic backbone, including:
    - statement QA hardening
    - first non-US Yahoo fallback path
    - stronger `company` backbone
    - filing-quality improvements
    - minimal CLI JSON bundle support
- `brk`
  - remains the Berkshire-specific proving ground
- current hardening branch work now proven and ready to merge:
  - stronger `company` backbone with statement availability
  - richer prioritized filing rows
  - human-facing README refresh
  - `.codex` ignored in Git
  - minimal `--format json` backend bundle path

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
