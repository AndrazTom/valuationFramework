# valuation/tests

AI-only note for test expectations.

Rules:

- run tests against the repo source tree with `PYTHONPATH=src pytest -q`
- use `. .venv/bin/activate` first in this repo so runtime deps like `tabulate` are available
- prefer targeted unit tests for normalization and table contracts before adding broader CLI coverage
- when adding a new `company` section, test both file outputs and JSON bundle keys
- CLI tests should stay offline and use monkeypatches or fixtures rather than live providers
- keep assertions focused on backend behavior and stable contracts, not incidental table formatting

Coverage map:

- `test_brk_holdings.py`, `test_brk_service.py`, `test_brk_tables.py`, and `test_brk_segments.py` cover Berkshire-specific workflows on the `brk` branch
- `test_company_service.py` covers identifier resolution and SEC/Yahoo path selection
- `test_normalize_tables.py` covers latest-fact resolution and filing normalization
- `test_statement_matrix.py` covers the tricky quarterly statement semantics
- `test_company_tables.py` covers company-view tables such as overview and statement availability
- `test_company_tables.py` is also where overview provenance/completeness behavior is currently locked down
- `test_company_tables.py` also locks down statement-availability partial-coverage behavior
- `test_cli.py` covers section wiring and output artifacts
