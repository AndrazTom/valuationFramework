# valuationFramework

## Purpose

This repository is for building a practical stock valuation framework.

The scope is general: the code should support valuing many public companies.

The priority case is Berkshire Hathaway, where the goal is to estimate intrinsic value as precisely as reasonably possible without turning the repo into an overbuilt research platform.

This is also a hobby project. It does not need a rigid product end-state upfront. The repo should support exploration, with enough structure that experimental work can later be turned into reusable tooling.

## Project Philosophy

The right approach is to build by example:

- start with one hard case: Berkshire Hathaway
- use that case to discover what generic tooling is actually needed
- extract reusable pieces into `main` only after they prove useful
- allow the project to remain a research backend for a while before deciding whether it becomes an app

Possible end states are all acceptable:

- a strong personal valuation research backend
- a CLI tool that produces repeatable valuation tables
- a local API/backend that powers a UI later
- a small portfolio of company-specific valuation modules built on one common core

The project does not need a final product decision now. The immediate goal is to make it useful, inspectable, and extensible.

## Documentation Policy

Keep documentation short, current, and close to the code:

- `README.md` should stay concise and human-oriented
- `claude.md` is the longer-lived agent bootstrap and repo contract
- `claude.md` should be updated continuously so a new chat can resume work with clear context
- core modules should explain intent with docstrings
- use short comments only where behavior or design assumptions are non-obvious
- update docs whenever the repo shape, runtime baseline, or workflow changes
- prefer reusable notation helpers for large financial values instead of scattering raw 10- to 12-digit literals through code and tests

## Cross-Chat Continuity

Treat `claude.md` as persistent working memory for future chats.

Keep it current with:

- current branch strategy and active branch
- current collaboration style with the user
- current runtime assumptions
- what is already implemented
- what is intentionally deferred
- the next likely implementation steps
- any open steering questions that future chats should know about

## Collaboration Style

Current working mode:

- the user is steering conceptually, not doing code review at this stage
- keep working autonomously unless a decision is genuinely blocking
- ask short steering questions when useful, then continue on reasonable assumptions
- use parallel sub-agents for bounded side work when it speeds up execution
- keep `claude.md` current as the living agent contract

Near-term usability goal:

- keep usage relatively simple
- prefer a CLI-first interface over a heavier application surface
- optimize for "learnable by using it" rather than a large framework upfront
- preserve the option to add an API/UI later without forcing that now
- prefer repo-local commands that run the current source tree, not stale installed snapshots

## Collaboration Mode

Current expected working style:

- the user leads conceptually, not by reviewing implementation details line by line
- the agent should keep executing for extended stretches without waiting for constant approval
- the agent should ask focused steering questions when tradeoffs matter, but continue making progress on other safe work while waiting for answers
- parallel exploration is encouraged when it speeds up iteration and does not create branch chaos
- prioritize quality, maintainability, and simplicity over feature count

Review expectations at this stage:

- do not optimize for showing lots of code to the user
- do not add speculative features just to make the repo look complete
- prefer small, clean modules with obvious responsibilities
- keep the default interface simple enough that the user can learn it later through a small CLI

## Core Rules

- Default language is Python.
- Target modern Python, not the system Python.
- Use C++ only if a real bottleneck appears later.
- The repo must remain free to run.
- Favor simple scripts, clear modules, and reproducible outputs over notebook-only workflows.
- Default outputs should be tables: terminal tables, Markdown tables, CSV, and optionally Parquet.
- keep exact raw numeric values in backend tables; apply human-readable notation only in report/render layers
- Prefer official or primary-source fundamentals data when possible.
- Treat market quotes and fundamentals as separate concerns.
- Do not build a trading bot. This is a valuation repo.
- `main` is for general-purpose valuation infrastructure.
- `brk` is the working branch for Berkshire-specific valuation logic and experiments.
- Code copied or adapted from other projects is acceptable only if the license allows it and attribution is preserved.

## Branch Strategy

Use the branches with different responsibilities:

- `main`: generic data connectors, normalized financial tables, reusable valuation models, reporting, and later API/backend layers
- `brk`: Berkshire-specific data loaders, Berkshire tables, sum-of-the-parts logic, and any temporary exploratory code needed to refine the Berkshire approach

Rules for merging from `brk` back to `main`:

- only merge code that is genuinely reusable
- if a Berkshire implementation reveals a generic need, extract the reusable layer first
- keep Berkshire assumptions out of generic modules unless they are parameterized cleanly

This means Berkshire is the first example-driven implementation, not the permanent design center of `main`.

## What Exists Already

There are already several ways to get stock data in Python. The main distinction is not Python vs. C++; it is free-and-simple vs. licensed-and-reliable.

### Data Source Scan

| Option | Best for | Pros | Limits | Initial verdict |
| --- | --- | --- | --- | --- |
| SEC EDGAR APIs (`submissions`, `companyfacts`, filings) | Fundamentals, filings, share counts, segment data | Official, free, strong for audited data | Not a quote feed; requires respectful access and a proper `User-Agent` | Must use |
| `yfinance` | Fast prototype quotes and historical prices | Very easy, zero key, good enough for research prototypes | Not an official exchange feed; quote quality and availability can vary | Use first |
| Financial Modeling Prep | Unified market + fundamentals API | Broad coverage, easy integration | API key, commercial dependency, quality varies by endpoint/plan | Do not depend on it in core repo |
| Finnhub | Realtime quotes/news/fundamentals | Good API design, useful for live data | API key and plan limits | Do not depend on it in core repo |
| Polygon | Higher-grade market data | Better for serious realtime workflows | Paid, more infrastructure commitment | Out of scope for free-first repo |
| OpenBB | Unified research interface | Can speed up exploration across providers | Extra abstraction layer; may hide source-specific details | Optional, not core |

## Recommendation For Phase 1

Use a Python-first stack:

- `requests` or `httpx` for API calls
- `pandas` for tables
- `pyarrow` for Parquet when needed
- `tabulate` or `rich` for readable terminal tables
- SEC EDGAR as the primary fundamentals source
- `yfinance` as the initial price/market-data source

Runtime baseline:

- package metadata should target modern Python (`>=3.12`)
- local development can standardize on Python 3.14
- avoid bending core dependency choices around old machine-specific interpreters
- SEC access requires a proper `VALUATION_SEC_USER_AGENT` with contact information
- on Python 3.14, prefer normal installs over editable installs for now

This gives the fastest path to a working repo with no paid dependency on day one.

Free-first interpretation:

- no required paid APIs
- no required SaaS backend
- no hidden dependency on proprietary terminals or datasets
- optional adapters for paid providers can exist later, but the repo must work without them

Important: "realtime stock data in Python directly" usually means calling an HTTP or WebSocket API from Python. That is normal. True exchange-grade realtime data is usually paid. For a simple start, Python is enough.

## Berkshire Hathaway Focus

Do not treat Berkshire like a normal single-business DCF case.

The primary Berkshire model should be a sum-of-the-parts valuation:

1. Public equity portfolio marked to market
2. Cash, cash equivalents, and Treasury bills
3. Insurance operations and float
4. Railroad, utility/energy, manufacturing, service, and retail operating businesses
5. Debt, minority interests, and other balance-sheet adjustments
6. Per-share value for `BRK.B`, with `BRK.A` handled via the 1:1500 conversion

### Berkshire Notes

- `BRK.B` is the practical market ticker to anchor price comparisons.
- 13F data is useful, but it is only part of Berkshire's full economic value.
- The official annual report and quarterly filings matter more than market-screening APIs for Berkshire.
- We should expect a Berkshire-specific model module, not just reuse a generic DCF.

## Planned Outputs

Every important script should be able to produce tables in at least one of these forms:

- terminal table for quick inspection
- Markdown table for notes and agent summaries
- CSV for spreadsheet work
- Parquet for local storage and later analysis

Examples of outputs we want:

- current market snapshot
- historical valuation multiples table
- inputs table for a valuation run
- Berkshire sum-of-the-parts bridge table
- sensitivity table
- valuation summary table with bull/base/bear cases

## Architecture Direction

The repo should be backend-first.

Start with a library plus CLI/report layer. Add a web/API interface only after the data pipeline and valuation outputs are stable.

Preferred flow:

1. provider adapters fetch raw data
2. normalization layer converts raw inputs into clean tables
3. model layer consumes normalized tables
4. report layer emits terminal, Markdown, CSV, and Parquet outputs
5. later, an API layer can expose the same report/model functions

The important design rule is that table generation should be easy and consistent. Models should return structured tabular outputs, not only free-form text.

Frontend readiness rule:

- keep backend outputs structured and JSON-serializable so a thin frontend or API can be added later without rewriting model logic
- do not move business logic into a future UI layer
- prefer CLI first, but shape the backend as if a minimal local web UI may be added later

Notation rule:

- for valuation code and tests, prefer `valuation.notation` helpers such as `B`, `M`, `T`, and `parse_scaled_number("100B")`
- avoid raw large numeric literals unless the value is truly an identifier, accession number, CUSIP, CIK, or other exact code

Security identity rule:

- do not assume ticker is the only identifier
- use a canonical `security_id` for backend joins across providers
- prefer `cusip:<CUSIP>` when holdings data includes a CUSIP
- use ticker-based ids like `ticker:NYSE:BRK-B` when the workflow begins from a quoted market symbol
- treat ticker/exchange as market-data aliases that can change or require manual mapping

Interface expectations:

- the core should remain a Python package with importable modules
- the first user-facing interface should be a simple CLI
- any later API or UI should stay thin and call the same underlying library functions
- avoid machine-specific setup assumptions beyond a modern Python runtime
- prefer repo-local launcher scripts when they materially simplify usage

## Proposed Repo Shape

This is the intended direction, not a final structure:

```text
valuationFramework/
  claude.md
  src/
    valuation/
      brk/
      data/
        providers/
        normalize/
      models/
      reports/
      api/
      utils/
  tests/
  data/
    raw/
    processed/
    cache/
  outputs/
    tables/
    reports/
```

Suggested module intent:

- `brk/`: Berkshire-specific orchestration, table shaping, and CLI hooks that should not leak into generic modules
- `data/providers/`: source-specific fetchers such as SEC and `yfinance`
- `data/normalize/`: convert provider-specific payloads into common tables
- `models/`: DCF, multiples, owner-earnings, and later Berkshire sum-of-the-parts
- `reports/`: Markdown, terminal, CSV, and Parquet renderers
- `api/`: later FastAPI or similar backend layer, only after the core library is stable

## First Implementation Plan

### Phase 1: Bootstrap

- set up Python project basics
- add a small data client for SEC EDGAR
- add a small data client for `yfinance`
- add normalized table schemas for prices, shares, income statement, balance sheet, and cash flow
- add a table output utility
- prove a clean pipeline for one ticker

### Phase 2: Generic Valuation Framework

- normalized financial statement loader
- basic multiples valuation
- simple DCF / owner-earnings model
- report builder that emits Markdown and CSV tables
- ensure all generic models can run without Berkshire-specific assumptions

### Phase 3: Berkshire-Specific Valuation

- ingest Berkshire annual and quarterly filings
- build public holdings and cash/investments bridge
- estimate operating-business value by segment
- produce a Berkshire sum-of-the-parts table
- compare intrinsic value range vs. market price
- keep reusable pieces extractable back into `main`

### Phase 4: Interface Layer

- add a simple CLI entrypoint for repeatable runs
- optionally add FastAPI endpoints for tables and valuation summaries
- keep the interface as a thin layer over the core library

## Near-Term Decision

Unless there is a strong objection, the first code milestone should be:

1. bootstrap a small Python package
2. fetch `BRK-B` quote/history with `yfinance`
3. fetch Berkshire filing/fundamental data from SEC sources
4. render the first Markdown and terminal tables

Bootstrap status as of 2026-04-09:

- Python package scaffold exists
- CLI snapshot command exists
- installed CLI command is `valuation`
- repo-local launcher is `./vf` and should be the default way to run the current source tree
- `yfinance` snapshot pull works on modern Python
- SEC pull works only when `VALUATION_SEC_USER_AGENT` is explicitly set
- snapshot tables are written to `outputs/`, which should remain gitignored
- active implementation branch for Berkshire work is `brk`
- Berkshire logic now lives under `valuation.brk`
- `valuation brk overview` produces live Berkshire overview tables
- `valuation brk holdings` produces latest Berkshire 13F summary and top-holdings tables
- `valuation brk holdings --live-prices` can revalue the resolved portion of Berkshire's 13F at current Yahoo prices
- `valuation brk liquidity` produces a Berkshire liquidity bridge from SEC company facts
- tests cover normalization, CLI behavior, SEC ticker normalization, and Berkshire table/service helpers
- Berkshire 13F XML parsing lives in `valuation.brk.holdings`
- generic security identity helpers now live under `valuation.securities`
- Python 3.14 editable installs are currently avoided; normal installs are the default path

Current Berkshire implementation on `brk`:

- Berkshire-specific CLI group: `valuation brk ...`
- `valuation brk overview` fetches:
  - company metadata
  - share-class conversion table
  - market snapshot for `BRK-B`
  - selected SEC company facts
  - filtered Berkshire-relevant filings
- `valuation brk holdings` fetches:
  - latest Berkshire 13F accession
  - SEC information-table XML
  - parsed holdings rows
  - aggregated top-holdings table by issuer/CUSIP
  - 13F summary and top-holdings tables
- `valuation brk holdings --live-prices` additionally:
  - resolves a curated subset of Berkshire CUSIPs to ticker symbols
  - pulls current Yahoo prices for resolved positions
  - builds a resolved live-price summary and a live top-holdings table
- `valuation brk liquidity` fetches:
  - Berkshire cash and debt-security-related company facts
  - a liquidity summary table
  - a raw bridge table with source SEC concepts
- the current per-share convention is `BRK.B` as the primary valuation unit
- terminal and Markdown tables now default to human-readable numeric formatting
- CSV remains raw for machine-friendly downstream use
- backend tables retain precise numeric values; formatting is a presentation concern
- `valuation.notation` now provides reusable `K`, `M`, `B`, `T`, and `parse_scaled_number(...)` helpers for valuation code and tests

Current useful commands:

- `./vf snapshot BRK-B`
- `./vf brk overview`
- `./vf brk holdings`
- `./vf brk holdings --live-prices`
- `./vf brk liquidity`
- `./setup`

Intentionally deferred for later:

- public-equity portfolio decomposition
- insurance float-specific treatment
- private operating-business segment valuation
- intrinsic-value bridge and bull/base/bear ranges

Open steering question:

- keep using `BRK.B` as the primary valuation unit unless the user asks to flip to `BRK.A`

## Session Handoff

Last updated: 2026-04-09

Current branch:

- `brk`

Current working status:

- `main` has the initial bootstrap commit
- `brk` adds Berkshire-specific package structure under `valuation.brk`
- `valuation brk overview` works live
- `valuation brk holdings` works live
- latest live 13F holdings output is aggregated by issuer/CUSIP for a cleaner valuation input table
- tests were last green at `24 passed`

Important runtime note:

- on Python 3.14, prefer normal installs like `pip install .` or `pip install '.[dev]'`
- editable installs are currently avoided because Python 3.14 skipped the generated `__editable__...pth` file in this environment
- `./vf` should be preferred for local usage because it executes `python -m valuation.cli` against the current `src/` tree
- use `valuation.notation` for large financial values in code and tests instead of raw long literals

Current useful commands:

- `./vf snapshot BRK-B`
- `./vf brk overview`
- `./vf brk holdings`
- `./vf brk liquidity`

Most likely next implementation steps:

1. improve Berkshire liquidity and Treasury treatment
2. improve public-equity portfolio outputs
3. operating-business segment extraction
4. first Berkshire sum-of-the-parts bridge table

Questions to ask the user next:

1. After public holdings, should the next priority be `cash + treasuries` or `operating businesses by segment`?
2. Keep `BRK.B` as the primary valuation unit, or switch the repo convention to `BRK.A`?
3. For CLI output, prefer raw numeric values, rounded human-readable values, or both?
4. Should generated tables stay as Markdown/CSV only for now, or add Parquet next?
5. When the next checkpoint is stable, should `brk` be committed before continuing further?

## Current Decisions

User decisions now in force:

- primary valuation unit stays `BRK.B`
- CLI/report output should prefer human-readable values
- Markdown/CSV remain sufficient for now; Parquet is not currently required
- commit stable checkpoints on `brk` before continuing deeper work
- both `cash + treasuries` and `operating businesses by segment` matter; order can be chosen pragmatically

Current default execution order:

1. public holdings
2. cash + treasuries
3. operating businesses by segment
4. first Berkshire sum-of-the-parts bridge

Latest verified state:

- `./vf brk holdings --limit 5` works live and prints human-readable values like `$61.96B` and `400M`
- `./vf brk holdings --live-prices --limit 10` works live and revalues 24 currently resolved Berkshire positions using Yahoo prices
- `./vf brk liquidity` works live and prints human-readable Berkshire cash and debt-security tables
- tests last passed at `44 passed`

## Agent Guidance

- Keep the framework general, but let Berkshire drive the first serious design decisions.
- Prefer transparent calculations over black-box finance packages.
- When choosing between a simple direct implementation and a more abstract system, choose the simple direct implementation first.
- Preserve table-first outputs.
- Document data provenance in reports.
- If code is borrowed from elsewhere, verify license compatibility and keep attribution notes in the repo.
- Build generic abstractions only after one concrete implementation proves the shape.

## Reference Links To Revisit

These were the useful anchors for the initial scan on 2026-04-09:

- SEC EDGAR API documentation: https://api.edgarfiling.sec.gov/edgar-api.pdf
- Berkshire Hathaway 2024 annual report / 10-K: https://www.berkshirehathaway.com/2024ar/202410-k.pdf
- OpenBB docs: https://docs.openbb.co/
- Financial Modeling Prep quote docs: https://site.financialmodelingprep.com/developer/docs/quote-order-quote

Future updates to this file should keep the repo intent stable and refine the concrete implementation plan as the codebase appears.
