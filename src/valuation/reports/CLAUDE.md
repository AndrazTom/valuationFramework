# valuation/reports

AI-only note for rendering and export layers.

This package should stay thin and generic.

## Rules

- render from stable backend tables or objects; do not invent business logic here
- keep exact raw values intact in JSON output
- apply display aliases and human-readable formatting only for terminal / markdown / csv presentation
- terminal rendering may drop low-value metadata columns to fit normal terminal widths, but must not drop requested period/history columns
- when period/history columns make a terminal table too wide, split them into repeated period blocks; Markdown/CSV/JSON should remain complete
- keep security identity columns such as `issuer` readable on one terminal row where practical; wrapping them into continuation lines can look like extra rows
- use display aliases for long field/metric labels when terminal readability is the only concern; do not rename backend columns just to shorten table output
- BRK selected/reported/live 13F labels are display aliases only; backend fields stay explicit (`reported_13f_value_usd`, `selected_13f_value_usd`, `blended_13f_value_usd`, `live_value_delta_usd`)
- when adding a new `company` section, keep JSON bundle naming stable and make the section export alongside the table outputs
- prefer small generic helpers over command-specific formatting branches
- current export pattern is one `bundle.json` plus one file per section slug
- empty tables are valid inputs and should stay explicit rather than triggering command-specific render branches

## reports/tables.py Key Helpers

- `humanize_frame(df)` — applies `_prepare_display_frame` (alias column labels + drop terminal secondary columns) then `_format_values` per row
- `_infer_format_kind(row, col)` — decides formatting for a cell based on field name tokens and `unit` sentinel
- `DISPLAY_COLUMN_ALIASES` — column header aliases (e.g. `issuer_name` → `issuer`)
- `DISPLAY_VALUE_ALIASES` — metric/field name aliases (e.g. `net_income` → `Net Income`)
- `TERMINAL_SECONDARY_COLUMNS` — columns dropped first when terminal width is tight
- `render_terminal_table`, `render_markdown_table`, `write_csv`, `write_markdown` — export helpers

## Number Formatting Rules

- `_multiple` column suffix → `Nx` format (e.g. `5.0x`)
- `_yield` or `_pct` suffix → percent format
- `_change_pct` / `_yoy_change_pct` suffix → signed percent (`+12.5%` / `-3.2%`)
- `per_share_` prefix → currency format (respects `unit` column for non-USD)
- `unit="USD"` row sentinel → currency for period columns
- `unit="PCT"` row sentinel → percent for period columns
- `unit="SHARES"` or `"COUNT"` row sentinel → quantity format
- `"unit"` column always dropped from display output (it is a formatting hint, not a display field)
