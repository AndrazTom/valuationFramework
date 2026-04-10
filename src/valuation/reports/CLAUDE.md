# valuation/reports

AI-only note for rendering and export layers.

This package should stay thin and generic.

Rules:

- render from stable backend tables or objects; do not invent business logic here
- keep exact raw values intact in JSON output
- apply display aliases and human-readable formatting only for terminal / markdown / csv presentation
- when adding a new `company` section, keep JSON bundle naming stable and make the section export alongside the table outputs
- prefer small generic helpers over command-specific formatting branches
- current export pattern is one `bundle.json` plus one file per section slug
- empty tables are valid inputs and should stay explicit rather than triggering command-specific render branches
