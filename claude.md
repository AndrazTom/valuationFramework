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

- `brk` is the Berkshire-specific proving ground layered on top of the generic base from `main`
- as of 2026-05-18, `brk` is mature; all prior hardening complete (liquidity, segments, SOTP, holdings history, price windows, diagnostics, valuation tables, valuation report)
- 2026-05-18 live QA sweep passed for `./vf brk holdings --history --filings-limit 2 --limit 10`, `./vf brk sotp --details`, and `./vf brk sotp --price-change 1M`
- `./vf brk valuation-report` now functional: self-contained Markdown artifact, findings-first order, terminal key-numbers preview, dynamic methodology notes, `--segment-filings` arg
- 275 tests passing as of 2026-05-18
- temporary hardening branches should be merged back quickly, then deleted

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
- **this is a constant, non-negotiable instruction**: every code change must be accompanied by updates to all affected subtree `CLAUDE.md` files; do not close a task without doing this
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
- cache note:
  - SEC provider payloads persist under `~/.cache/valuationFramework/sec` by default, or `VALUATION_CACHE_DIR/sec`
  - mutable SEC endpoints auto-expire: company ticker map 24h, submissions 12h, companyfacts 24h
  - immutable filing artifacts such as filing indexes, `FilingSummary.xml`, report HTML, and 13F XML cache indefinitely
  - Yahoo price snapshots persist under `~/.cache/valuationFramework/yahoo/snapshots` for 1h
  - Yahoo history frames persist under `~/.cache/valuationFramework/yahoo/history` for 24h
  - use `./vf --refresh-cache ...` to force provider refresh for one run

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
- broad universe downloads should be built on a persisted cache/index layer, not by repeatedly hitting providers in ad hoc command loops
- for a future top-500 US or top-1000 global command, define the universe source, ranking date, and licensing/data-source assumptions before implementation

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
  - also contains `build_implied_value_range_table` and `build_reverse_dcf_table` (owner-earnings valuation)
- `src/valuation/company/comps.py`
  - multi-security comparison table builder: `fetch_comps_entries` (parallel TTM fetch) + `build_comps_table`
  - columns: ticker, name, price, market_cap, revenue, net_income, owner_earnings, oe_margin_pct, pe_ratio, price_to_oe, oe_yield_pct, ev_to_ebitda, implied_growth_pct
- `src/valuation/company/ratios.py`
  - historical per-fiscal-year valuation ratio builder
  - SEC path: `build_historical_ratios_table` (annual companyfacts + monthly Yahoo price history)
  - Yahoo path: `build_historical_ratios_table_from_yahoo` (Yahoo annual frames)
  - `_annual_period_end_dates` reads raw companyfacts to recover actual fiscal year end dates (lost when statements convert to period labels)
- `src/valuation/watchlist.py`
  - persistent ticker watchlist backed by `~/.config/valuationFramework/watchlist.toml`
  - add/remove/load/save with case-insensitive deduplication
  - `./vf watchlist show` delegates to `run_comps` on the full watchlist
- `src/valuation/data/normalize/tables.py`
  - core normalization contract layer
  - latest-fact selection, filing normalization, statement period matrix logic
- `src/valuation/data/providers/`
  - thin wrappers over SEC and Yahoo
  - SEC filing report tables are now parsed in-code from HTML rather than relying on `pandas.read_html` + `lxml`
- `src/valuation/reports/tables.py`
  - rendering and export helpers
  - terminal display aliases keep BRK live/resolved 13F and price-change field labels compact without changing backend table keys
  - security identity columns such as `issuer` should stay on one terminal row; wrapping them can look like false extra holdings
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

`brk` contains:

- latest 13F holdings with live-price revaluation and price-change windows
- 13F holdings history across recent filings with portfolio-level change summaries
- liquidity bridge from filing balance-sheet tables
- operating segment history
- market-implied SOTP bridge with operating business context
- operating business reverse DCF (Gordon Growth implied growth at 8%/10%/12% required return)
- valuation tables (implied value range, reverse DCF) inherited from generic company workflow

As of 2026-05-18, `brk` is ahead of `main`; the live QA sweep and EPS/share fallback are complete before merging back.

- inherit the generic company/snapshot/statements stack from `main`
- keep Berkshire-specific logic in `src/valuation/brk/`
- `src/valuation/brk/statements.py` fills BRK Class B EPS/equivalent-share rows from filing report tables for annual and direct quarterly income statements when companyfacts omits them
- SOTP `--details` emits balance-sheet context rows for major assets/liabilities that remain inside the residual; these rows are context only and should not be added to net liquidity without redefining the bridge
- keep Berkshire assumptions out of generic modules unless they are reusable and parameterized cleanly

Reusable pieces discovered there should be extracted back into `main`.

## Current Main Features

As of 2026-05-18, `main` contains (on `brk`, pending merge):

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
  - cashflow (now includes `depreciation_amortization` row via `DepreciationDepletionAndAmortization`)
  - annual and quarterly
  - optional start/end year filters
  - optional start/end quarter filters for quarterly views
  - when any statement range filter is provided, the CLI default limit should widen enough that the range filter, not the default `--limit`, controls the output
  - quarterly handling is metric-aware:
    - additive flows may derive from YTD/FY
    - balance-sheet items stay instant
    - diluted EPS / diluted shares should prefer direct-quarter facts and avoid subtraction
  - BRK income statements add a Berkshire-only filing-table fallback for Class B EPS/share rows from `Consolidated Statements of Earnings`; quarterly fallback uses only `3 Months Ended` columns and leaves Q4 blank rather than deriving per-share values from annual/YTD disclosures
- multi-security comps table: `./vf comps AAPL MSFT GOOG` fetches TTM metrics in parallel and renders side-by-side
- historical valuation ratios: `./vf ratios AAPL --limit 5` shows annual P/E, P/OE, OE yield, P/B, EV/EBITDA with price from Yahoo monthly history
- persistent watchlist: `./vf watchlist add/remove/list/show` backed by `~/.config/valuationFramework/watchlist.toml`

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
- `./vf statements BRK --statement income --period quarterly --diagnostics`
- `./vf ratios AAPL --limit 5`
- `./vf ratios BNP.PA --limit 4`
- `./vf comps AAPL MSFT GOOG`
- `./vf watchlist add AAPL MSFT BRK-B`
- `./vf watchlist remove MSFT`
- `./vf watchlist list`
- `./vf watchlist show`
- `./vf brk overview`
- `./vf brk holdings --limit 10`
- `./vf brk holdings --history --filings-limit 4 --limit 10`
- `./vf brk holdings --live-prices --limit 10`
- `./vf brk holdings --price-change 1M --limit 10`
- `./vf brk sotp`
- `./vf brk sotp --details`
- `./vf brk sotp --price-change 1M`
- `./vf brk valuation-report`
- `./vf brk valuation-report --segment-filings 4`
- `./vf brk liquidity --period annual --limit 4`
- `./vf brk liquidity --period quarterly --limit 4`
- `./vf brk segments --period annual --limit 4`
- `./vf brk segments --period quarterly --limit 4`
- `./vf brk liquidity --period quarterly --start-year 2019 --start-quarter 1 --end-year 2023 --end-quarter 3`
- `./vf brk segments --period quarterly --start-year 2019 --start-quarter 1 --end-year 2023 --end-quarter 3`

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

## Berkshire Priorities

Steps 1-4 done. Next hardening pass:

1. ~~keep `./vf brk ...` workflows healthy after mainline sync~~ ✓
2. ~~improve Berkshire SOTP~~ ✓ (operating context + reverse DCF shipped 2026-05-18)
3. ~~tighten Berkshire-specific filing/report extraction quality (EPS/share fallback from filing tables)~~ ✓
4. ~~`./vf brk valuation-report` command~~ ✓ (shipped 2026-05-18: findings-first MD report, terminal summary, dynamic methodology notes)

### Next SOTP / Valuation Hardening Tasks

These are the highest-value next steps for improving the quality and trust of the BRK valuation output:

**Liability awareness in the SOTP bridge (highest priority conceptual improvement):**
- The current bridge does not explicitly show the deferred tax liability on unrealized equity gains (~$35B as of latest balance sheet)
  - This is a real contingent liability: selling the equity portfolio triggers ~21% capital gains tax on the unrealized gain
  - The 13F portfolio is valued at current market prices (pre-tax), so the "true" after-tax value is lower
  - Add a `deferred_tax_haircut_on_equity` context row to the SOTP bridge (shown as a context row, not deducted from the bridge, so the user can apply their own judgment)
  - This would require fetching `DeferredIncomeTaxLiabilitiesNet` or `DeferredTaxLiabilitiesInvestments` from SEC companyfacts
- Insurance float treatment: the methodology notes now explain this correctly; no code change needed unless a separate float-funded investment yield table becomes worthwhile
- Holding-company debt vs subsidiary debt: balance sheet context already shows `notes_payable_and_other_borrowings`; consider splitting into holding-company debt (Senior notes issued by BRK parent) vs consolidated debt in a future pass

**Valuation report quality:**
- Run `./vf brk valuation-report` live and QA the output Markdown for:
  - Fixed maturity figure is pulled from actual data (not hardcoded ~$25B)
  - All sections render without empty tables
  - Methodology notes are factually accurate with actual balance sheet context values
- Consider adding a `--price-change` flag to the valuation report so holdings can be revalued with a window (e.g. 1M price change context)

**Independent operating business valuation (medium-term):**
- The SOTP residual is market-implied (circular). A higher-quality report would also include a bottoms-up range estimate for the operating businesses
- BNSF: could use rail-industry EV/EBITDA multiples applied to BNSF segment EBITDA
- BHE: similar approach with utility multiples, noting the ongoing BHE utility wildfire liability
- Insurance / other: harder to value independently; keep as residual
- This is a larger project but the segment data + reverse DCF are already in place to support it

**Merge readiness:**
- after next live QA sweep, port `brk` clean to `main`
- keep pushing reusable pieces back into `main` when genuinely generic

Latest Berkshire live check on 2026-05-16:

- `./vf brk holdings --history --filings-limit 2 --limit 5` exited 0 and emitted filing history plus top-holdings history
- `./vf brk sotp` exited 0 and emitted the new `Operating Business Context` table
- latest live SOTP context showed:
  - residual operating-and-other value around $371.3B
  - latest segment pre-tax earnings around $51.7B
  - residual-to-segment-pre-tax-earnings around 7.2x

Current CLI hardening pass:

- default `./vf brk sotp` should stay compact: market-implied bridge, operating-business context, and optional price-change comparison only
- use `./vf brk sotp --details` for assumptions, market anchor, quoted holdings, liquidity snapshot, and segment-period support tables
- terminal rendering now fits normal terminal widths by dropping secondary metadata columns only; requested period/history columns are split into repeated terminal blocks instead of being removed
- CSV/Markdown/JSON exports remain complete
- live checks at `COLUMNS=100` stayed within width for:
  - `./vf brk sotp`
  - `./vf brk sotp --details`
  - `./vf statements AAPL --statement income --period quarterly --start-year 2024 --end-year 2025`
  - `./vf company AAPL`
  - `./vf statements BRK --statement income --period quarterly --limit 20`

Completed on 2026-05-17:

- `./vf statements ... --diagnostics` / `--include-missing` now emits a `Statement Diagnostics` section for SEC-backed statements
- diagnostics explain expected rows as available, concept absent, requested-unit missing, empty-unit, stale/outside selected output, or no usable period
- live BRK quarterly income diagnostic confirmed:
  - `diluted_eps` and `diluted_shares` are absent from BRK SEC companyfacts
  - `operating_income` has only stale usable quarterly coverage, latest shown as 2013 Q1

Completed before 2026-05-18:

- EBITDA and free_cash_flow derived rows added to Key Financials for both SEC and Yahoo paths
- TTM financials used for valuation ratios in `./vf company` (SEC path)
- TTM financials used for valuation ratios in Yahoo-backed path using quarterly frames when available
- TTM NQ label applied when fewer than 4 quarters are available
- earnings/FCF/owner-earnings yield ratios and per-share owner earnings added to Valuation Ratios section
- portfolio-level 13F change summary added: categorises every issuer as new/increased/decreased/eliminated/unchanged
- price/share decomposition added to 13F issuer change summary
- fixed maturity securities split explicitly in SOTP component bridge table
- segment earnings history in `./vf brk sotp --details` now fetches 4 filings (not 1)

Completed on 2026-05-18 (valuation):

- `build_implied_value_range_table` added to `company/tables.py`
  - pure function over market snapshot + TTM financials
  - computes owner earnings = net income + D&A - capex; returns empty when negative
  - shows implied price per share at 10x/15x/20x/25x/30x owner earnings multiples
  - shows `upside_pct` (0-1 decimal) as (implied - current) / current
  - `multiple` column formatted as "Nx" by `humanize_frame` via new `_infer_format_kind` case
- `build_reverse_dcf_table` added to `company/tables.py`
  - Gordon Growth model solved for g: implied_growth = required_return - (owner_earnings / market_cap)
  - shows implied perpetual growth at 8%/10%/12% required return assumptions
  - shows `zero_growth_price` = per_share_OE / r (what you'd pay for zero-growth OE)
  - `assumed_return` and `implied_growth` formatted as percent by `humanize_frame`
  - returns empty when owner earnings negative or market cap unavailable
- both `Implied Value Range` and `Reverse DCF` sections wired into `./vf company` for both SEC and Yahoo paths
  - sections only emit when owner earnings are positive and inputs are available
  - rendered to CSV/MD/JSON with slugs `implied_value_range` and `reverse_dcf`
- 13 new tests in `test_company_tables.py`; full suite now 219 tests, all passing

Completed on 2026-05-18 (Berkshire SOTP):

- `build_brk_operating_reverse_dcf_table` added to `brk/tables.py`
  - uses Gordon Growth solved for g: implied_g = r - (pretax_earnings / residual)
  - extracts residual and pretax_earnings from the already-built operating context table
  - shows implied perpetual growth at 8%/10%/12% required return, plus zero-growth value in USD and per BRK-B share
  - returns empty when residual or pretax earnings are zero/negative/missing
  - note: residual includes non-13F assets, debt, deferred taxes — implied growth is an approximation
- `Operating Business Reverse DCF` section added to default `./vf brk sotp` output (after Operating Business Context)
  - only emits when operating context has positive residual and pretax earnings
- 5 new tests in `test_brk_tables.py`; full suite now 224 tests, all passing

Completed on 2026-05-18 (generic company research tools):

- `src/valuation/company/comps.py` added: multi-ticker TTM comps via parallel `fetch_comps_entries` + `build_comps_table`
  - columns: ticker, name, price, market_cap, revenue, net_income, owner_earnings, oe_margin_pct, pe_ratio, price_to_oe, oe_yield_pct, ev_to_ebitda, implied_growth_pct
  - implied_growth_pct = 0.10 - (owner_earnings / market_cap), shown when owner earnings positive
- `src/valuation/company/ratios.py` added: historical per-fiscal-year valuation ratios
  - `build_historical_ratios_table`: SEC path using annual companyfacts + Yahoo monthly price history
  - `build_historical_ratios_table_from_yahoo`: Yahoo annual frames path
  - `_annual_period_end_dates`: recovers actual FY end dates from raw companyfacts (period labels lose the date)
  - `_price_for_date`: searches ±3 months in monthly price map for closest bar
  - columns: fiscal_year, end_date, price, market_cap, net_income, revenue, owner_earnings, pe_ratio, price_to_oe, oe_yield_pct, pb_ratio, ev_to_ebitda
- `src/valuation/watchlist.py` added: persistent ticker watchlist at `~/.config/valuationFramework/watchlist.toml`
  - `./vf watchlist add/remove/list/show` subcommands; `show` delegates to `run_comps` on full watchlist
- `depreciation_amortization` added to `CASH_FLOW_DEFINITIONS` (`DepreciationDepletionAndAmortization` / `DepreciationAndAmortization`)
  - unlocks owner earnings in historical ratios for all issuers with SEC cashflow D&A data
  - D&A now also surfaces in Key Financials section of `./vf company` with proper `$X.XXB` formatting
- `humanize_frame` formatting extended: `depreciation` and `amortization` token → currency format
- full test suite at 257 tests (was 224 before this session)

## First Task for Next Session

**CLAUDE.md audit — do this before any other work:**

- scan the entire repo for all existing `CLAUDE.md` files and identify every module that has meaningful local context but no `CLAUDE.md` yet
- update all existing subtree `CLAUDE.md` files to reflect the current state of the code (many were last updated before the valuation report, summary table, and liability-context work)
- add new subtree `CLAUDE.md` files where missing and genuinely useful (candidates: `src/valuation/company/`, `src/valuation/data/providers/`, `src/valuation/reports/`, `src/valuation/securities/`)
- cross-check every `CLAUDE.md` against the actual code: remove stale claims, add anything a new chat would need to avoid rediscovering

This is required before any feature work so the repo is fully navigable from a cold start.

---

Completed on 2026-05-18 (valuation report):

- `./vf brk valuation-report` now fully functional
  - findings-first section order: Key Valuation Summary → SOTP Bridge → Operating Context → Reverse DCF → Supporting Detail → Segment History → Methodology
  - terminal key-numbers preview (prints `Key Valuation Summary` table before writing file)
  - `build_brk_valuation_summary_table` added to `brk/tables.py`: compact summary over already-computed tables (price, mktcap, 13F blended, net liquidity, residual + per-share + weight, pretax earnings, multiple, implied growth at 10%, zero-growth per-share)
  - dynamic methodology notes: fixed maturity note pulled from actual liquidity data
  - improved liability context in methodology notes: float explained correctly (not a simple deduction), deferred tax haircut on equity flagged, subsidiary vs holdco debt distinction made explicit
  - `--segment-filings` arg (default 4) controls segment history depth
  - accession numbers included in report header for both 13F and liquidity filings
  - 275 tests passing (was 257)
- `_metric_per_share()` and `_metric_weight()` helpers added to `brk/tables.py` for SOTP bridge row extraction

Next concrete tasks:

1. Deferred tax context row in SOTP bridge (see Berkshire Priorities → Next SOTP/Valuation Hardening Tasks)
2. Cached universe/index layer:
   - build a small security/filer index before any top-500/top-1000 downloader
   - for updated SEC filings after long gaps, refresh submissions first, compare latest accession/report dates to local index, then fetch only new immutable filing artifacts
3. Yahoo Europe hardening:
   - collect specific issuer failures before changing mappings; bank/insurance statement shapes can be legitimately sparse
4. Generic company improvements:
   - statement concept coverage: consider sector-specific concept additions for energy/utility/insurance companies
   - filing quality: ensure `8-K` and proxy filings are surfaced cleanly in the company view
4. QA sweep completed on 2026-05-18:
   - `./vf brk sotp`, `./vf brk sotp --price-change 1M`, `./vf brk holdings --history --filings-limit 2`, `./vf company AAPL`, `./vf company BRK-B`, `./vf company BNP.PA` all exited 0
   - `Operating Business Reverse DCF` confirmed present in SOTP output
   - `Implied Value Range` and `Reverse DCF` confirmed for both AAPL and BRK-B
   - note: BRK-B owner earnings ARE available from SEC TTM (D&A + capex + net income all in Q1 2026 10-Q); earlier assumption of suppression was incorrect
   - BRK quarterly diagnostics confirmed: diluted_eps and diluted_shares absent from SEC companyfacts; operating_income stale since 2013

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
- `brk` contains all new work, pending final QA sweep before merge to `main`:
  - stronger `company` backbone with statement availability
  - richer prioritized filing rows + human-facing README refresh
  - `.codex` ignored in Git + minimal `--format json` bundle path
  - statement diagnostics (`--diagnostics` / `--include-missing`)
  - TTM financials for valuation ratios (SEC + Yahoo paths)
  - `Implied Value Range` and `Reverse DCF` sections in `./vf company`
  - `Operating Business Reverse DCF` in `./vf brk sotp`
  - portfolio-level and issuer-level 13F change summaries
  - 224 tests passing

## Quality Bar

- prioritize code quality over feature count
- prefer fewer, clearer modules over many thin wrappers
- delete code that is not pulling its weight
- keep tests that protect real behavior; skip decorative or low-signal tests
- preserve a clean path for later API/UI work without adding that surface too early

## Commit Authorship

- Do NOT add `Co-Authored-By: Claude` or any AI co-author trailers to commits
- Do NOT add `Generated with [Claude Code]` or any AI attribution lines to commit messages
- Commits should appear authored solely by the human user

## Git / Publication

- repo remote: `https://github.com/AndrazTom/valuationFramework`
- keep the GitHub repo private unless the user explicitly changes that
- keep commits organized by reusable concern
- push stable `brk` checkpoints freely
- when generic work is ready, port it cleanly to `main`
