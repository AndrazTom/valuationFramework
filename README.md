# valuationFramework

Backend-first stock valuation tooling.

The repo is meant to stay general on `main`, while Berkshire Hathaway can be explored in a dedicated `brk` branch and later folded back into generic pieces where appropriate.

## Current Scope

- free-first data stack
- Python package, not machine-specific scripts
- table-oriented outputs
- CLI first, API later

## Current Data Sources

- SEC EDGAR for filings and fundamentals
- `yfinance` for simple market data prototyping

## Local Setup

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -e .
export VALUATION_SEC_USER_AGENT="valuationFramework/0.1 your-email@example.com"
.venv/bin/python -m valuation.cli snapshot BRK-B
```

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
