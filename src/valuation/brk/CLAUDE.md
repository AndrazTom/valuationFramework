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
- `./vf brk sotp [--details] [--price-change WINDOW] [--equity-valuation-basis reported|live] [--equity-live-limit N]`
- `./vf brk valuation-report [--segment-filings N] [--equity-valuation-basis reported|live] [--equity-live-limit N] [--outdir DIR]`

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
- `build_public_equity_portfolio_summary_table` — reported 13F value, selected 13F value, and optional live-price coverage
- `build_public_equity_revaluation_detail_table` — live-priced holdings detail: reported value, live value, delta, shares, quote/date
- `build_public_equity_tax_context_table` — filing-derived equity-securities cost/fair-value context and selected-13F embedded-gain estimate
- `build_public_equity_tax_sensitivity_table` — after-tax selected-13F sensitivity using federal statutory, federal + state/local, effective-rate, and scaled reported investment DTL cases

**Liquidity and balance sheet:**
- `build_liquidity_bridge_table` — multi-filing liquidity bridge from balance-sheet tables
- `build_liquidity_summary_table` — net-liquidity summary rows
- `build_liquidity_detail_table` — all balance-sheet line items
- `build_latest_liquidity_snapshot_table` — latest-period snapshot
- `build_balance_sheet_context_table` — context rows (equity securities, equity-method, total assets, debt, deferred tax, total liabilities); for context only, not added to bridge arithmetic

**SOTP and valuation:**
- `build_market_anchor_table` — current market cap and price reference
- `build_brk_valuation_assumptions_table` — stated assumptions, including selected public-equity basis and live-pricing limit
- `build_market_implied_sotp_bridge_table` — main SOTP bridge: market cap − selected 13F value − net cash/T-bills = residual
- `build_brk_valuation_context_table` — bridge + residual context rows
- `build_operating_business_context_table` — residual vs segment pre-tax earnings, P/B, OE
- `build_brk_operating_reverse_dcf_table` — Gordon Growth implied growth at 8%/10%/12% required return
- `build_brk_valuation_summary_table` — compact key-numbers summary for valuation report front page
  - fields: price, market cap, 13F reported/selected basis/blended/selected, live coverage %, net cash/T-bills, residual + per-share + weight, pretax earnings, multiple, implied growth at 10%, zero-growth per-share

**Segments:**
- `build_segment_report_summary_table` — filing metadata for included segments
- `build_top_level_operating_segments_summary_table` — latest period segment data
- `build_segment_period_sections` — one section per period for `--details`

**Share class:**
- `build_share_class_table` — BRK.A and BRK.B equivalent share counts

## Valuation Report (`./vf brk valuation-report`)

Produces a self-contained Markdown artifact. Section order (findings-first):
1. **Key Valuation Summary** — compact numbers table printed to terminal before writing file
2. **Market-Implied SOTP Bridge** — market cap − selected 13F value − net cash/T-bills = residual
3. **Operating Business Context** — residual vs segment earnings
4. **Operating Business Reverse DCF** — implied growth scenarios (when positive earnings)
5. **Supporting Detail** — market anchor, public-equity portfolio, equity revaluation detail, cash/T-bills and fixed maturity context, balance-sheet context, public-equity tax context/sensitivity
6. **Segment History** — one section per period fetched plus history pivots
7. **Methodology Notes** — assumptions table, dynamic fixed-maturity figure, float explanation, deferred tax haircut, debt distinction

`--segment-filings N` controls segment history depth (default 4).
`--equity-valuation-basis live` is the default and revalues all mapped holdings as shares × current Yahoo quote, then blends unresolved holdings at reported value.
`--equity-live-limit N` bounds live pricing to the top N mapped holdings if runtime or provider behavior becomes a concern.
`--equity-valuation-basis reported` keeps the old report behavior: public equities equal latest reported 13F values from the filing.
The report methodology explicitly states the live formula: reported total minus reported value of live-priced holdings plus `shares held × current price`; it keeps both reported and selected 13F values in the key summary and public-equity portfolio tables.
Fixed maturities should be framed as insurance investment-portfolio context, not deployable liquidity. The SOTP bridge subtracts only cash + T-bills - T-bill purchase payable as core liquidity; fixed maturities remain inside the residual with insurance businesses and other non-13F items.
Public-equity tax sensitivity is included in the full valuation report only. It fetches Berkshire's equity-securities note from the latest 10-K/10-Q and deferred-tax / tax-reconciliation notes from the latest 10-K. The selected 13F cost basis is estimated by scaling Berkshire's aggregate equity-securities cost/fair-value ratio onto the selected 13F value. Tax is applied to estimated unrealized gain, not gross portfolio value; this is a sensitivity/stress test, not an exact liquidation model.
Accession numbers included in report header for 13F and liquidity filings.

## BRK EPS/Share Filing Fallback (`brk/statements.py`)

SEC companyfacts omits `EarningsPerShareDiluted` and `WeightedAverageNumberOfDilutedSharesOutstanding` for Berkshire. `brk/statements.py` fills:
- Annual income: Class B EPS and equivalent-share rows from `Consolidated Statements of Earnings`
- Quarterly income: direct 3-month Class B EPS/share rows from recent 10-Qs
- Quarterly fallback: uses only `3 Months Ended` columns; leaves Q4 blank (never derives from annual/YTD)

This fallback runs only for BRK income statements; generic SEC companyfacts path is unchanged.

## Balance Sheet Context Caveat

`build_balance_sheet_context_table` rows (equity securities, equity-method investments, deferred income taxes, notes payable, total liabilities, total assets) are **context only**. Do not add them to net liquidity or subtract them again from the SOTP bridge without redefining the residual — they are already priced into the market cap.

## Deferred Tax Context

The SOTP bridge shows balance-sheet deferred income taxes as a context row when the filing balance sheet exposes it. This broad liability is not deducted from the bridge unless the residual definition changes.

For public equities, use the valuation-report tax context/sensitivity tables instead of the broad balance-sheet deferred-tax row. Selling appreciated equities would tax unrealized gain rather than gross market value; the report approximates embedded gain from Berkshire's equity-securities cost/fair-value filing note and keeps federal statutory, federal + state/local, effective-rate, and scaled reported investment-DTL scenarios side by side.

## Rules

- prefer explicit bridge tables over opaque model outputs
- separate reported values from live-revalued values
- keep BRK SOTP and valuation report default on live current-price equity estimation for all mapped holdings; use `--equity-valuation-basis reported` for old filing-date 13F values
- keep public-equity tax as report context/sensitivity unless the user explicitly changes the SOTP residual definition; do not silently subtract it from selected 13F value
- keep `BRK.B` as the default share unit unless the user changes that
- keep Berkshire-specific logic in this subtree rather than leaking it into generic modules
- for liquidity / fixed maturities:
  - prefer the filing balance-sheet report over SEC companyfacts
  - keep the U.S. Treasury Bill line explicit
  - do not describe fixed maturity securities as freely deployable liquidity; they are insurance-reserve-backed investment-portfolio context unless the bridge definition changes
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
