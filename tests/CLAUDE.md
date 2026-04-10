# valuation/tests

AI-only note for test expectations.

Rules:

- run tests against the repo source tree with `PYTHONPATH=src pytest -q`
- prefer targeted unit tests for normalization and table contracts before adding broader CLI coverage
- when adding a new `company` section, test both file outputs and JSON bundle keys
- CLI tests should stay offline and use monkeypatches or fixtures rather than live providers
- keep assertions focused on backend behavior and stable contracts, not incidental table formatting
