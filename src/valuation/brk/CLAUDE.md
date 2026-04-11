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
- optional live-price revaluation for resolved holdings
- optional live price-change windows on holdings via `--price-change` / `--price-change-window`
- BRK-vs-holdings price-change comparison when a change window is selected
- liquidity history from SEC filing balance-sheet tables
- top-level operating segment extraction from filing report tables
- first Berkshire market-implied SOTP bridge
- liquidity and segments both support:
  - `--period annual|quarterly`
  - `--limit`
  - explicit start/end period filters
  - when any explicit range filter is present, internal history fetch should widen to `99` even if a small `--limit` was passed
- SEC live checks should work with either:
  - repo-local `.env`
  - exported env vars, which should override `.env`
- Yahoo live-price paths should degrade to partial coverage instead of crashing when quote/history fetches are rate-limited

Next major output:

- Berkshire holdings history across filings

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
