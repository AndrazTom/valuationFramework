# valuation/src

AI-only module note for future chats.

This subtree should stay generic unless a module is explicitly under `valuation.brk`.

## Rules

- prefer reusable primitives here
- keep raw values precise in backend tables
- keep human-readable formatting in `reports/`
- keep subtree `CLAUDE.md` files current when module-local behavior changes
- treat `security_id` as the canonical backend join key
- treat ticker as a market-data alias, not the only identity
- generic CLI workflows should accept flexible identifiers when the free data path supports them
- if a Berkshire-specific idea becomes reusable, extract it here before merging toward `main`
- SEC-backed flows should support both:
  - repo-local `.env`
  - exported env vars
- never make `.env` the only supported path
- keep the layering explicit:
  - `data/providers` fetch transport payloads
  - `data/normalize` turns them into stable tables
  - `company` assembles generic single-security views
  - `reports` renders or exports those views
- avoid pushing rendering concerns back into `company` or `data`

## Current Top-Level Modules

- `cli.py` — top-level command routing; stays thin
- `company/` — generic single-security backend (see `company/CLAUDE.md`)
- `brk/` — Berkshire-specific proving ground (see `brk/CLAUDE.md`)
- `data/providers/` — SEC and Yahoo transport wrappers (see `data/providers/CLAUDE.md`)
- `data/normalize/` — table contracts and latest-fact selection (see `data/normalize/CLAUDE.md`)
- `reports/` — rendering, formatting, export helpers (see `reports/CLAUDE.md`)
- `securities/` — canonical identifier logic (see `securities/CLAUDE.md`)
- `watchlist.py` — persistent ticker watchlist at `~/.config/valuationFramework/watchlist.toml`
  - `./vf watchlist add/remove/list/show` subcommands
  - `show` delegates to `run_comps` on the full watchlist
  - case-insensitive deduplication
- `portfolio/` — IBKR portfolio, Slovenian tax, and reconciliation workflows
  - `./vf portfolio show/tax/dividends/interest/reconcile`
  - tax/dividend/interest commands emit filing-shaped rows before any future FURS XML generator
