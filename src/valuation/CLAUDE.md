# valuation/src

AI-only module note for future chats.

This subtree should stay generic unless a module is explicitly under `valuation.brk`.

Rules:

- prefer reusable primitives here
- keep raw values precise in backend tables
- keep human-readable formatting in `reports/`
- keep subtree `CLAUDE.md` files current when module-local behavior changes
- treat `security_id` as the canonical backend join key
- treat ticker as a market-data alias, not the only identity
- generic CLI workflows should accept flexible identifiers when the free data path supports them
- if a Berkshire-specific idea becomes reusable, extract it here before merging toward `main`
- keep the layering explicit:
  - `data/providers` fetch transport payloads
  - `data/normalize` turns them into stable tables
  - `company` assembles generic single-security views
  - `reports` renders or exports those views
- avoid pushing rendering concerns back into `company` or `data`
