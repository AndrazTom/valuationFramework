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
./setup
export VALUATION_SEC_USER_AGENT="valuationFramework/0.1 your-email@example.com"
./vf snapshot BRK-B
./vf brk overview
./vf brk holdings
```

Use a modern interpreter for local work. The current repo baseline is Python 3.12+, and local development is standardized on Python 3.14.

For development and tests:

```bash
./setup
./.venv/bin/python -m pytest -q
```

On Python 3.14, prefer a normal install over `pip install -e .` for now.

## Local Commands

Use the repo-local launcher:

```bash
./vf snapshot BRK-B
./vf brk overview
./vf brk holdings --limit 10
```

If you keep `VALUATION_SEC_USER_AGENT` in a local `.env` file, `./vf` will load it automatically.

## Output Shape

The project should default to structured outputs:

- terminal tables with human-readable values
- Markdown tables with human-readable values
- CSV with raw machine-friendly values
- later Parquet and API responses

## Documentation Policy

- `README.md` stays short and human-oriented
- `claude.md` is the more detailed repo contract for AI agents
- important behavior should be documented in module docstrings and targeted comments near the code
