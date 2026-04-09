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
./vf brk liquidity
./vf brk holdings --live-prices --limit 10
```

Use a modern interpreter for local work. The current repo baseline is Python 3.12+, and local development is standardized on Python 3.14.

For development and tests:

```bash
./setup
./.venv/bin/python -m pytest -q
```

On Python 3.14, prefer a normal install over `pip install -e .` for now.

`./vf` runs the current source tree directly, so local commands do not depend on an older installed snapshot.

## Local Commands

Use the repo-local launcher:

```bash
./vf snapshot BRK-B
./vf brk overview
./vf brk holdings --limit 10
./vf brk liquidity
./vf brk holdings --live-prices --limit 10
```

If you keep `VALUATION_SEC_USER_AGENT` in a local `.env` file, `./vf` will load it automatically.

## Output Shape

The project should default to structured outputs:

- terminal tables with human-readable values
- Markdown tables with human-readable values
- CSV with raw machine-friendly values
- later Parquet and API responses

Raw numeric precision stays in the backend tables. Human-readable notation is applied only when rendering terminal or Markdown output.

## Number Notation

For valuation code and tests, avoid raw large literals when the value is conceptual rather than an identifier.

Use `valuation.notation` instead:

```python
from valuation.notation import B, M, parse_scaled_number

cash = 52.6 * B
shares = 400 * M
target_value = parse_scaled_number("100B")
```

## Security Identity

Treat ticker symbols as market-data aliases, not the only identity key.

- use a canonical `security_id` in backend tables
- prefer `CUSIP` when holdings data has it
- use `ticker + exchange` when the workflow starts from a market symbol
- resolve current prices through a separate alias layer

## Documentation Policy

- `README.md` stays short and human-oriented
- `claude.md` is the more detailed repo contract for AI agents
- important behavior should be documented in module docstrings and targeted comments near the code
