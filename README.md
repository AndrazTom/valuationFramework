# valuationFramework

CLI-first investing toolkit for company research and personal portfolio/tax reporting.

The project currently has two product areas:
- research: statements, balance-sheet visibility, ratios, comps, and valuation from SEC EDGAR + Yahoo Finance
- portfolio: IBKR holdings, realized gains, dividends, withholding tax, FX, and Slovenian tax-report reconciliation

## What it produces

`./vf company AAPL` shows:
- company metadata and identifier resolution
- market snapshot (price, market cap, shares)
- key financials (revenue, net income, FCF, owner earnings, EBITDA)
- valuation ratios (P/E, P/B, P/S, P/FCF, P/OE, EV/EBITDA) using TTM financials
- implied value range at 10x–30x owner earnings
- reverse DCF: implied perpetual growth rate at 8%/10%/12% required return
- statement availability summary with explicit coverage reasons
- recent core filings (10-K, 10-Q, 8-K, DEF 14A)

`./vf brk sotp` produces a market-implied SOTP bridge for Berkshire Hathaway:
- public equity portfolio (13F with live prices where resolved)
- net liquidity (cash, T-bills, fixed maturity securities)
- market-implied residual for operating businesses
- operating context: segment pre-tax earnings vs. residual multiple
- operating reverse DCF: implied growth at 8–12% required return

## Prerequisites

- Python 3.10+
- A free SEC EDGAR user agent (just an email address — see Setup)

## Setup

```bash
git clone https://github.com/AndrazTom/valuationFramework
cd valuationFramework
./setup
```

Then add your SEC user agent to a `.env` in the repo root:

```
VALUATION_SEC_USER_AGENT=valuationFramework/0.1 your@email.com
```

Or export it in your shell:

```bash
export VALUATION_SEC_USER_AGENT="valuationFramework/0.1 your@email.com"
```

`./vf` runs the current source tree through the local virtualenv. No install step is needed beyond `./setup`.

## Commands

### Company view

```bash
./vf company AAPL
./vf company BNP.PA                          # non-US via Yahoo fallback
./vf company US0378331005                    # by ISIN
./vf company 0000320193 --identifier-kind cik
./vf snapshot BRK-B                          # lighter: price + recent filings
```

### Statements

```bash
./vf statements AAPL --statement income --period annual
./vf statements AAPL --statement income --period quarterly
./vf statements AAPL --statement balance --period quarterly
./vf statements AAPL --statement cashflow --period quarterly
./vf statements AAPL --statement income --period ttm
./vf statements AAPL --statement income --period quarterly --start-year 2022 --end-year 2024
./vf statements BRK --statement income --period quarterly --diagnostics
./vf statements BNP.PA --statement income --period annual
```

### Research tools

```bash
./vf comps AAPL MSFT GOOG                   # TTM side-by-side comparison table
./vf ratios AAPL --limit 5                  # annual P/E, P/B, P/OE, EV/EBITDA history
./vf ratios BNP.PA --limit 4
```

### Watchlist

```bash
./vf watchlist add AAPL MSFT BRK-B
./vf watchlist remove MSFT
./vf watchlist list
./vf watchlist show                          # runs comps across the full watchlist
```

### Portfolio

Private brokerage and tax files should stay under ignored paths such as `portfolio/`.

```bash
./vf portfolio show                               # open positions, cost basis, P&L, tax tier
./vf portfolio tax --year 2025                    # realized gains and Slovenian CGT view
./vf portfolio dividends --year 2025              # dividends, WHT, and Slovenian dividend tax view
./vf portfolio interest --year 2025               # broker interest, WHT, and Doh-Obr-shaped rows
./vf portfolio reconcile --year 2025              # audit source coverage, FX, gains, and dividend totals
./vf portfolio furs-xml --file flex.xml --year 2025   # generate Doh-KDVP, Doh-Div, Doh-Obr XML
```

See `docs/portfolio.md` for Flex Query setup, env vars, and FURS filing notes.

### Berkshire

```bash
./vf brk overview
./vf brk sotp                                # compact SOTP bridge + operating context
./vf brk sotp --details                      # full supporting tables
./vf brk sotp --price-change 1M             # BRK vs holdings price-change comparison
./vf brk valuation-report                    # self-contained Markdown valuation report
./vf brk holdings --limit 10
./vf brk holdings --history --filings-limit 4 --limit 10
./vf brk holdings --live-prices --limit 10
./vf brk holdings --price-change 1M --limit 10
./vf brk liquidity --period annual --limit 4
./vf brk liquidity --period quarterly --limit 4
./vf brk segments --period annual --limit 4
./vf brk segments --period quarterly --limit 4
./vf brk liquidity --period quarterly --start-year 2019 --start-quarter 1 --end-year 2023 --end-quarter 3
```

## Supported identifiers

US issuers use SEC EDGAR. Non-US issuers fall back to Yahoo Finance when usable data exists.

| Form | Example |
|------|---------|
| Ticker | `AAPL`, `BRK-B` |
| SEC CIK | `0000320193` (add `--identifier-kind cik`) |
| ISIN | `US0378331005` |
| CUSIP | `US02079K3059` |
| Non-US ticker | `BNP.PA`, `NESN.SW` |

Some smaller-market tickers require an exchange-qualified form or may not be reachable through Yahoo.

## Data sources

| Source | Used for |
|--------|----------|
| SEC EDGAR | Statements and filings for US issuers (preferred) |
| Yahoo Finance | Market snapshots, price history, non-US profile and statement fallback |

SEC company facts are the authoritative source for US financial statements. Yahoo is used for market prices and as a broad global fallback.

## Caching

Provider payloads are cached locally on first use.

| What | Default path | Expiry |
|------|-------------|--------|
| SEC companyfacts/submissions | `~/.cache/valuationFramework/sec` | 12–24h |
| SEC filing artifacts (HTML, XML) | same | indefinite |
| Yahoo snapshots | `~/.cache/valuationFramework/yahoo/snapshots` | 1h |
| Yahoo price history | `~/.cache/valuationFramework/yahoo/history` | 24h |

Override the root: `VALUATION_CACHE_DIR=/your/path`

Force a fresh pass: `./vf --refresh-cache <command> ...`

## Output

Default: terminal table + Markdown + CSV files written to `./outputs/`.

JSON output:

```bash
./vf company AAPL --format json
```

Prints a machine-readable bundle to stdout and writes per-section `.json` files alongside the table outputs.

## Data quality and methodology notes

- **SEC path preferred**: SEC EDGAR is the primary source for US issuers. Yahoo Finance handles market snapshots and non-US names.
- **Quarterly gaps**: Some European issuers have no Yahoo quarterly frames. These fail explicitly rather than returning silent empty tables.
- **Sector shape**: Banks and insurers have different statement structures. Rows like `gross_profit` or `current_assets` may be genuinely absent rather than a data gap.
- **BRK EPS/share**: `diluted_eps` and `diluted_shares` are absent from Berkshire's SEC companyfacts. The income statement fills these from Berkshire's own filing tables instead.
- **SOTP residual is market-implied (circular)**: The Berkshire operating-business residual is `market cap − public equities − net liquidity`. It reflects what the market is already pricing in, not an independent bottoms-up appraisal of the operating businesses.
- **Reverse DCF uses pre-tax segment earnings**: Implied growth rates are approximations. Applying a ~25% tax-rate haircut to the earnings yield gives a rough after-tax equivalent.
- **Owner earnings** = net income + D&A − capex. For capital-intensive businesses where capex substantially exceeds D&A (e.g. BNSF), this may overstate maintenance-adjusted owner earnings.

## Documentation

- `README.md` — this file
- `docs/portfolio.md` — portfolio commands, IBKR Flex Query setup, FURS filing guide
