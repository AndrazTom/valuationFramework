# valuation/src

AI-only module note for future chats.

This subtree should stay generic unless a module is explicitly under `valuation.brk`.

Rules:

- prefer reusable primitives here
- keep raw values precise in backend tables
- keep human-readable formatting in `reports/`
- treat `security_id` as the canonical backend join key
- treat ticker as a market-data alias, not the only identity
- generic CLI workflows should accept flexible identifiers when the free data path supports them
- if a Berkshire-specific idea becomes reusable, extract it here before merging toward `main`
