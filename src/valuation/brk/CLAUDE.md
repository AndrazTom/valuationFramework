# valuation/brk

AI-only note for Berkshire-specific workflows.

This subtree is the proving ground for hard valuation problems that later reveal reusable infrastructure.

This branch should now inherit the current generic backend from `main`; Berkshire logic belongs here only when it is genuinely Berkshire-specific.

Current Berkshire stack:

- inherited generic commands:
  - `./vf company`
  - `./vf snapshot`
  - `./vf statements`
- Berkshire-specific commands:
  - `./vf brk overview`
  - `./vf brk holdings`
  - `./vf brk liquidity`
- `./vf brk segments`
- `./vf brk sotp`
- latest 13F holdings
- recent 13F holdings history via `./vf brk holdings --history`
- optional live-price revaluation for resolved holdings
- optional live price-change windows on holdings via `--price-change` / `--price-change-window`
- BRK-vs-holdings price-change comparison when a change window is selected
- live-price tables should explain when Yahoo resolved nothing in the current run instead of silently showing blank comparisons
- liquidity history from SEC filing balance-sheet tables
- top-level operating segment extraction from filing report tables
- first Berkshire market-implied SOTP bridge
- SOTP now includes operating-business context that compares the residual to latest reported segment pre-tax earnings
- liquidity and segments both support:
  - `--period annual|quarterly`
  - `--limit`
  - explicit start/end period filters
  - when any explicit range filter is present, internal history fetch should widen to `99` even if a small `--limit` was passed
- SEC live checks should work with either:
  - repo-local `.env`
  - exported env vars, which should override `.env`
- Yahoo live-price paths should degrade to partial coverage instead of crashing when quote/history fetches are rate-limited

Recent completed output:

- Berkshire holdings history across filings:
  - `./vf brk holdings --history --filings-limit N`
  - emits filing-level 13F history plus a latest-top-holdings history table
  - keeps live-price enrichment scoped to the latest filing path
- Berkshire SOTP operating-business context:
  - emits an `Operating Business Context` table from `./vf brk sotp`
  - compares residual operating-and-other value to latest top-level segment pre-tax earnings
  - treats the residual as a market-implied context bridge, not a standalone appraisal
- live branch check on 2026-05-16:
  - `./vf brk holdings --history --filings-limit 2 --limit 5` exited 0
  - latest parsed 13F filings were 2026-05-15 / 2026-03-31 and 2026-02-17 / 2025-12-31
  - `./vf brk sotp` exited 0 and emitted `Operating Business Context`
  - live SOTP context showed residual operating-and-other of about $371.3B versus $51.7B latest segment pre-tax earnings, or about 7.2x

Next major output:

- improve Berkshire SOTP by separating more non-13F assets/liabilities and making segment earnings history more valuation-ready

Rules:

- prefer explicit bridge tables over opaque model outputs
- separate reported values from live-revalued values
- keep `BRK.B` as the default share unit unless the user changes that
- keep Berkshire-specific logic in this subtree rather than leaking it into generic modules
- for liquidity:
  - prefer the filing balance-sheet report over SEC companyfacts
  - keep the U.S. Treasury Bill line explicit
- for quarterly segments:
  - prefer the 3-month columns over 6/9-month YTD columns when the command asks for quarterly history
  - normalize alternate SEC member paths for the same operating segment into one row
  - when multiple filings are selected, emit one output table per filing period instead of one large combined history table
  - keep the command framed as a top-level segment summary, not a raw dump of every note row
- for annual segments:
  - some older Berkshire filings only expose `Total revenues` in the earnings report plus the additional-disclosure metrics
  - blank cells in older annual segment tables can therefore be real upstream report-table coverage limits, not necessarily parser bugs
