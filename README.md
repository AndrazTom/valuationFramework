# valuationFramework

Backend-first stock valuation tooling.

The repo is meant to stay general on `main`, while Berkshire Hathaway can be explored in a dedicated `brk` branch and later folded back into generic pieces where appropriate.

## Current Scope

- free-first data stack
- Python package, not machine-specific scripts
- table-oriented outputs
- CLI first, API later
- Berkshire work can advance on `brk` while `main` stays reusable

## Current Data Sources

- SEC EDGAR for filings and fundamentals
- `yfinance` for simple market data prototyping

## Local Setup

```bash
python -m venv .venv
.venv/bin/python -m pip install .
export VALUATION_SEC_USER_AGENT="valuationFramework/0.1 your-email@example.com"
.venv/bin/valuation snapshot BRK-B
.venv/bin/valuation brk overview
.venv/bin/valuation brk holdings
```

Use a modern interpreter for local work. The current repo baseline is Python 3.12+, and local development is standardized on Python 3.14.

For development and tests:

```bash
.venv/bin/python -m pip install '.[dev]'
.venv/bin/python -m pytest -q
```

On Python 3.14, prefer a normal install over `pip install -e .` for now.

## Output Shape

The project should default to structured outputs:

- terminal tables
- Markdown tables
- CSV
- later Parquet and API responses

## Documentation Policy

- `README.md` stays short and human-oriented
- `claude.md` is the more detailed repo contract for AI agents
- important behavior should be documented in module docstrings and targeted comments near the code
