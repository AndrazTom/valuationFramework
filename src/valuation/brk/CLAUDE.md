# valuation/brk

AI-only note for Berkshire-specific workflows.

This subtree is the proving ground for hard valuation problems that later reveal reusable infrastructure.

Current Berkshire stack:

- latest 13F holdings
- optional live-price revaluation for resolved holdings
- liquidity bridge from SEC company facts
- operating segment extraction from filing report tables

Next major output:

- a first Berkshire sum-of-the-parts bridge table

Rules:

- prefer explicit bridge tables over opaque model outputs
- separate reported values from live-revalued values
- keep `BRK.B` as the default share unit unless the user changes that
