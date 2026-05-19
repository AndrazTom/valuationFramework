# Portfolio & Tax Reporting

This module imports IBKR data and produces Slovenian tax filings
(`Doh-KDVP`, `Doh-Div`, `Doh-Obr`) ready for upload to eDavki.

## Quick start

```bash
# 1. Export a Flex Query XML from IBKR (see setup below)
# 2. Add personal details to .env (see env vars below)
# 3. Generate XML for all three forms
./vf portfolio furs-xml --file ~/ibkr/2025.xml --year 2025
# → outputs/tables/portfolio_furs_2025/Doh-KDVP.xml
# → outputs/tables/portfolio_furs_2025/Doh-Div.xml
# → outputs/tables/portfolio_furs_2025/Doh-Obr.xml
# 4. Upload each file at https://edavki.durs.si
```

## All portfolio commands

```bash
./vf portfolio show                               # open positions, cost basis, CGT tier
./vf portfolio gains --year 2025                  # realized gains + KDVP filing rows
./vf portfolio dividends --year 2025              # dividends, WHT, Doh-Div filing rows
./vf portfolio interest --year 2025               # broker interest, Doh-Obr filing rows
./vf portfolio reconcile --year 2025              # audit coverage before filing
./vf portfolio furs-xml --file flex.xml --year 2025          # all three XML forms
./vf portfolio furs-xml --file flex.xml --year 2025 --forms kdvp  # one form only
```

`--file` falls back to `IBKR_FLEX_PATH` in `.env` when omitted.
`--file` accepts comma-separated paths to combine multiple years or accounts.

---

## IBKR Flex Query setup

The `furs-xml` and `reconcile` commands require a Flex Query XML export.
Activity Statement CSV is not sufficient (it lacks IBKR-computed FIFO lots).

### Configure the query (one-time)

In IBKR: **Performance & Reports → Flex Queries → "+"** (next to Activity Flex Query)

| Section | What to enable |
|---|---|
| Account Information | IB Entity, Account ID |
| Trades | Options: **Executions** + **Closed Lots** → then **Select All** fields |
| Corporate Actions | **Select All** fields |
| Cash Transactions | Options: **Dividends**, **Payment in Lieu of Dividends**, **Withholding Tax**, **Broker Fees**, **Broker Interest Received** → then **Select All** fields |
| Financial Instrument Information | **Select All** fields |

Leave date settings at default when saving.

> **Important — include Dividends:** without the `Dividends` CashTransaction type,
> dividends for 0%-WHT issuers (e.g. BABA/Alibaba, Cayman Islands domicile) cannot
> be derived and will be missing from the output. Always include it.

### Export for a tax year

1. In Flex Queries, click the run arrow next to your query
2. Period → **Custom Date Range** → Jan 1 – Dec 31 of the target year
3. Download the XML file — keep it **outside the repo** (gitignored by default)
4. Repeat for each year you need. Also export the current year when filing a past
   year — some WHT entries are reported retroactively by IBKR

### Multi-account (IBUK → IBCE → IBIE migrations)

On the Reports page, click **Select Account(s)** → filter to show
**Open + Closed + Migrated** → select all accounts. This captures data from
all IBKR entity migrations under the same login.

*Flex Query configuration adapted from [ib-edavki](https://github.com/ib-edavki/ib-edavki).*

---

## Environment variables

Set these in `.env` at the repo root (gitignored). Shell exports take precedence.

```bash
# Path to your IBKR Flex Query XML (used as default --file)
IBKR_FLEX_PATH=/home/you/ibkr/2025.xml

# Your personal details for the XML header
FURS_TAX_NUMBER=12345678        # davčna številka — required
FURS_NAME=Ime Priimek           # required
FURS_EMAIL=your@email.com       # appears in form body
FURS_PHONE=+38641000000         # appears in form body
```

Address fields (`<edp:address1>`, `<edp:city>`, etc.) are left blank — eDavki
populates them from the tax register when you're logged in.

---

## FURS filing notes

### Capital gains (Doh-KDVP)

- Filed on **Doh-KDVP** form, due **28 Feb** of the following year
- This tool uses IBKR's FIFO lot cost basis with commissions baked into the
  per-share buy/sell price (F5 = 0), as required by FURS
- CGT rates under ZDoh-2: **25% → 20% → 15% → 0%** at 5 / 10 / 15 complete years held
- Losses offset gains within the same tax year only; no carry-forward
- Real estate capital losses (same year) also offset securities CGT

### Dividends (Doh-Div)

- Filed on **Doh-Div** form
- Foreign WHT offsets the 25% Slovenian dividend tax (e.g. 15% US treaty rate → 10% top-up)
- Payer details (name, address, tax ID) come from the `KNOWN_PAYERS` table in
  `src/valuation/portfolio/furs_xml.py` — add any missing symbols there before filing

### Interest (Doh-Obr)

- Broker interest from IBKR Ireland is filed on **Doh-Obr** (Type 2)
- Requires the Flex Query to include **Broker Interest Received** CashTransactions

### Wash-sale rule

30-day window: selling at a loss and re-buying the same instrument within 30 days
disallows the loss. FIFO constraint means you cannot selectively pick a loss lot
if earlier (gain) lots exist for the same symbol. Use a different instrument for
equivalent exposure to harvest the loss cleanly.

### Verify with FURS

Rates, deadlines, and treaty details at [fu.gov.si](https://www.fu.gov.si).
This tool is a calculation aid — always verify before filing.

---

## Known limitations

| Issue | Cause | Workaround |
|---|---|---|
| 0%-WHT dividends missing (e.g. BABA) | No WHT entry exists to derive gross from | Add `Dividends` CashTransaction type to Flex Query |
| Payer details missing for a symbol | Symbol not in `KNOWN_PAYERS` | Add entry to `furs_xml.py` before filing |
| FX values 0.0000 for non-EUR stocks | ECB rate fetch failed or `--no-fx-auto` used | Check network, or remove `--no-fx-auto` |
| Small price differences vs ib-edavki | ECB vs IBKR FX rates differ slightly | Both are acceptable to FURS |

---

## Privacy

IBKR statement files contain personal financial data. **Never commit them.**

The `.gitignore` already excludes `*.activity.csv`, `*_statement.csv`,
`ibkr_*.csv`, `ibkr_*.xml`. Store all statement paths in `.env` (also gitignored).
