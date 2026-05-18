# valuation/brk

AI-only note for Berkshire-specific workflows.

This subtree is the proving ground for hard valuation problems that later reveal reusable infrastructure.

This branch inherits the generic backend from `main`; Berkshire logic belongs here only when it is genuinely Berkshire-specific.

## Current Berkshire Stack

Inherited generic commands:
- `./vf company`, `./vf snapshot`, `./vf statements`, `./vf comps`, `./vf ratios`, `./vf watchlist`

Berkshire-specific commands:
- `./vf brk overview`
- `./vf brk holdings [--live-prices] [--history --filings-limit N] [--price-change WINDOW] [--limit N]`
- `./vf brk liquidity [--period annual|quarterly] [--limit N]`
- `./vf brk segments [--period annual|quarterly] [--limit N]`
- `./vf brk sotp [--details] [--price-change WINDOW]`
- `./vf brk valuation-report [--segment-filings N] [--outdir DIR]`

## Module Ownership

- `brk/service.py` — fetches and bundles all BRK data into `BrkValuationBundle`
- `brk/tables.py` — all BRK-specific table builders (see key functions below)
- `brk/cli.py` — command wiring, never does data logic
- `brk/holdings.py` — 13F data fetch and enrichment
- `brk/segments.py` — segment filing extraction
- `brk/statements.py` — BRK-only income statement fallback for Class B EPS/share rows

## Key Table Functions (brk/tables.py)

**Holdings:**
- `build_13f_summary_table` — latest 13F filing metadata
- `build_top_holdings_table` — top N holdings by portfolio weight + cumulative weight
- `build_top_holdings_live_table` — live-enriched version with today's prices
- `build_13f_live_price_summary_table` — live-price coverage summary
- `build_13f_history_summary_table` — one row per filing period across history
- `build_13f_holdings_history_table` — wide holding history across filings
- `build_13f_issuer_change_summary_table` — new/increased/decreased/eliminated categorisation
- `build_13f_portfolio_change_summary_table` — portfolio-level value and count changes
- `build_holdings_vs_brk_price_change_table` — BRK-B price vs holdings weighted return
- `build_public_equity_portfolio_summary_table` — blended 13F value with live-price coverage

**Liquidity and balance sheet:**
- `build_liquidity_bridge_table` — multi-filing liquidity bridge from balance-sheet tables
- `build_liquidity_summary_table` — net-liquidity summary rows
- `build_liquidity_detail_table` — all balance-sheet line items
- `build_latest_liquidity_snapshot_table` — latest-period snapshot
- `build_balance_sheet_context_table` — context rows (equity securities, equity-method, total assets, debt, deferred tax, total liabilities); for context only, not added to bridge arithmetic

**SOTP and valuation:**
- `build_market_anchor_table` — current market cap and price reference
- `build_brk_valuation_assumptions_table` — stated assumptions (insurance float, float cost, etc.)
- `build_market_implied_sotp_bridge_table` — main SOTP bridge: market cap − 13F − net liquidity = residual
- `build_brk_valuation_context_table` — bridge + residual context rows
- `build_operating_business_context_table` — residual vs segment pre-tax earnings, P/B, OE
- `build_brk_operating_reverse_dcf_table` — Gordon Growth implied growth at 8%/10%/12% required return
- `build_brk_valuation_summary_table` — compact key-numbers summary for valuation report front page
  - fields: price, market cap, 13F reported/blended, live coverage %, net liquidity, residual + per-share + weight, pretax earnings, multiple, implied growth at 10%, zero-growth per-share

**Segments:**
- `build_segment_report_summary_table` — filing metadata for included segments
- `build_top_level_operating_segments_summary_table` — latest period segment data
- `build_segment_period_sections` — one section per period for `--details`

**Share class:**
- `build_share_class_table` — BRK.A and BRK.B equivalent share counts

## Valuation Report (`./vf brk valuation-report`)

Produces a self-contained Markdown artifact. Section order (findings-first):
1. **Key Valuation Summary** — compact numbers table printed to terminal before writing file
2. **Valuation Assumptions** — stated methodology assumptions
3. **Market Anchor** — current price and market cap
4. **Public Equity Portfolio** — 13F blended value with live-price coverage
5. **Liquidity Snapshot** — net liquidity from balance-sheet filing
6. **Balance Sheet Context** — residual-context rows (not deducted from bridge)
7. **Market-Implied SOTP Bridge** — market cap − 13F − net liquidity = residual
8. **Operating Business Context** — residual vs segment earnings
9. **Operating Business Reverse DCF** — implied growth scenarios (when positive earnings)
10. **Segment periods** — one section per period fetched
11. **Methodology Notes** — dynamic fixed-maturity figure, float explanation, deferred tax haircut, debt distinction

`--segment-filings N` controls segment history depth (default 4).
Accession numbers included in report header for 13F and liquidity filings.

## BRK EPS/Share Filing Fallback (`brk/statements.py`)

SEC companyfacts omits `EarningsPerShareDiluted` and `WeightedAverageNumberOfDilutedSharesOutstanding` for Berkshire. `brk/statements.py` fills:
- Annual income: Class B EPS and equivalent-share rows from `Consolidated Statements of Earnings`
- Quarterly income: direct 3-month Class B EPS/share rows from recent 10-Qs
- Quarterly fallback: uses only `3 Months Ended` columns; leaves Q4 blank (never derives from annual/YTD)

This fallback runs only for BRK income statements; generic SEC companyfacts path is unchanged.

## Balance Sheet Context Caveat

`build_balance_sheet_context_table` rows (equity securities, equity-method investments, deferred income taxes, notes payable, total liabilities, total assets) are **context only**. Do not add them to net liquidity or subtract them again from the SOTP bridge without redefining the residual — they are already priced into the market cap.

## Deferred Tax Context (Planned)

The SOTP bridge does not explicitly show the deferred tax liability on unrealized equity gains (~$35B). Selling the equity portfolio triggers ~21% capital gains tax. This is a real contingent liability. Planned: add `deferred_tax_haircut_on_equity` as a context row sourced from `DeferredIncomeTaxLiabilitiesNet` or `DeferredTaxLiabilitiesInvestments`.

## Rules

- prefer explicit bridge tables over opaque model outputs
- separate reported values from live-revalued values
- keep `BRK.B` as the default share unit unless the user changes that
- keep Berkshire-specific logic in this subtree rather than leaking it into generic modules
- for liquidity:
  - prefer the filing balance-sheet report over SEC companyfacts
  - keep the U.S. Treasury Bill line explicit
  - filing parser accepts both `Payable for purchase of U.S. Treasury Bills` and `Payable for purchases of U.S. Treasury Bills`
- for quarterly segments:
  - prefer the 3-month columns over 6/9-month YTD columns when the command asks for quarterly history
  - normalize alternate SEC member paths for the same operating segment into one row
  - when multiple filings are selected, emit one output table per filing period instead of one large combined history table
- for annual segments:
  - some older filings only expose `Total revenues` in the earnings report; blank cells in older tables can be real upstream report-table coverage limits
- default SOTP output stays compact; supporting assumptions, quoted holdings, liquidity, and segment tables stay behind `--details`
- Yahoo live-price paths should degrade to partial coverage instead of crashing on rate limits
- SEC live checks should work with either repo-local `.env` or exported env vars (exported vars override `.env`)
