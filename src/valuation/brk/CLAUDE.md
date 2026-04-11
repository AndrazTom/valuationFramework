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
- latest 13F holdings
- optional live-price revaluation for resolved holdings
- liquidity history from SEC filing balance-sheet tables
- operating segment extraction from filing report tables
- liquidity and segments both support:
  - `--period annual|quarterly`
  - `--limit`
- SEC live checks should work with either:
  - repo-local `.env`
  - exported env vars, which should override `.env`

Next major output:

- a first Berkshire sum-of-the-parts bridge table

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
