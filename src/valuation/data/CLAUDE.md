# valuation/data

AI-only note for provider and normalization layers.

Intent:

- keep transport access separate from normalization
- do not let provider-specific object shapes leak upward when a stable table or bundle can be returned instead

Rules:

- `providers/` should stay thin wrappers over external systems
- `normalize/` owns table contracts and light semantic cleanup
- filing prioritization and latest-fact selection belong in normalization, not in the CLI
- if a provider is incomplete, preserve that incompleteness clearly instead of inventing data
