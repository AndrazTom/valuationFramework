"""Parse IBKR Flex Query XML exports into structured lot and dividend records.

Flex Query XML is preferred over Activity Statement CSV for CGT because IBKR
pre-computes FIFO lot matching (<Lot> elements) including lots opened before
the statement period — eliminating "unmatched sell" warnings.

Dividend gross amounts are NOT present in a standard WHT-only flex query;
configure the flex query to include the "Dividends" CashTransaction type, or
use the Activity Statement CSV path for dividend reporting.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from valuation.portfolio.ibkr import IbkrDividend, IbkrStatementMeta

_log = logging.getLogger(__name__)

_FLEX_DATE_FMTS = ("%Y%m%d;%H%M%S", "%Y%m%d")


@dataclass(frozen=True)
class FlexLot:
    """A closed FIFO lot as reported by IBKR in <Lot> elements."""
    symbol: str
    currency: str
    acquired: date
    sold: date
    quantity: float
    cost_native: float       # IBKR FIFO cost basis in trade currency
    pnl_native: float        # fifoPnlRealized in trade currency

    @property
    def proceeds_native(self) -> float:
        return self.cost_native + self.pnl_native


def load_flex_query(
    path: str | Path,
) -> tuple[list[FlexLot], list[IbkrDividend], IbkrStatementMeta]:
    """Parse an IBKR Flex Query XML file.

    Returns (lots, dividends, meta).
    - lots: closed FIFO lots with IBKR-computed cost basis and P&L
    - dividends: gross + WHT pairs when both types are in the query
    - meta: account/period metadata
    """
    tree = ET.parse(str(path))
    root = tree.getroot()

    stmt = root.find(".//FlexStatement")
    meta = _parse_meta(stmt, root)
    lots = _parse_lots(root)
    dividends = _parse_dividends(root)

    return lots, dividends, meta


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def _parse_meta(stmt, root) -> IbkrStatementMeta:
    account_id = ""
    base_currency = "EUR"
    from_date = to_date = None

    if stmt is not None:
        account_id = stmt.get("accountId", "")
        from_str = stmt.get("fromDate", "")
        to_str = stmt.get("toDate", "")
        from_date = _parse_date_str(from_str)
        to_date = _parse_date_str(to_str)

    ai = root.find(".//AccountInformation")
    if ai is not None:
        base_currency = ai.get("currency", base_currency) or base_currency

    return IbkrStatementMeta(
        base_currency=base_currency,
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
    )


# ---------------------------------------------------------------------------
# Lot parsing (CGT core)
# ---------------------------------------------------------------------------

def _parse_lots(root) -> list[FlexLot]:
    lots: list[FlexLot] = []
    for elem in root.iter("Lot"):
        if elem.get("buySell", "").upper() != "SELL":
            continue
        if elem.get("assetCategory", "STK") not in ("STK", ""):
            continue

        symbol = elem.get("symbol", "").strip()
        currency = elem.get("currency", "").strip()
        if not symbol or not currency:
            continue

        acquired = _parse_flex_datetime(elem.get("openDateTime", ""))
        sold = _parse_flex_datetime(elem.get("dateTime", ""))
        if acquired is None or sold is None:
            _log.warning("Skipping Lot for %s: could not parse dates", symbol)
            continue

        qty = _f(elem.get("quantity"))
        cost = _f(elem.get("cost"))
        pnl = _f(elem.get("fifoPnlRealized"))
        if qty is None or cost is None or pnl is None:
            continue
        if abs(qty) < 1e-9:
            continue

        lots.append(FlexLot(
            symbol=symbol,
            currency=currency,
            acquired=acquired,
            sold=sold,
            quantity=abs(qty),
            cost_native=cost,
            pnl_native=pnl,
        ))

    return sorted(lots, key=lambda l: l.sold)


# ---------------------------------------------------------------------------
# Dividend parsing
# ---------------------------------------------------------------------------

def _parse_dividends(root) -> list[IbkrDividend]:
    """Parse CashTransaction elements into gross dividends with WHT.

    When the flex query includes both 'Dividends' and 'Withholding Tax' types,
    we match them by (symbol, date) to produce IbkrDividend records.

    When only 'Withholding Tax' is present, we attempt to derive gross from
    the description ("X.XX PER SHARE") combined with inferred share count, but
    this is approximate. Configure the flex query to include 'Dividends' type
    for authoritative gross amounts.
    """
    div_rows: list[dict] = []
    wht_index: dict[tuple[str, date], float] = {}

    for elem in root.iter("CashTransaction"):
        tx_type = elem.get("type", "")
        symbol = elem.get("symbol", "").strip()
        desc = elem.get("description", "").strip()
        currency = elem.get("currency", "").strip()
        amount = _f(elem.get("amount"))
        dt = _parse_flex_datetime(elem.get("dateTime", ""))
        if dt is None or amount is None:
            continue

        if tx_type == "Dividends" and symbol and amount > 0:
            div_rows.append({
                "symbol": symbol,
                "currency": currency,
                "date": dt,
                "amount": amount,
                "description": desc,
            })
        elif tx_type == "Withholding Tax" and symbol and "CASH DIVIDEND" in desc:
            # Accumulate signed amounts: IBKR sometimes emits reversal/re-entry pairs
            # (e.g. 3× debit + 2× credit = 1× net debit). Summing only debits triples
            # the WHT when this happens. Net signed sum gives the correct deduction.
            key = (symbol, dt)
            wht_index[key] = wht_index.get(key, 0.0) + amount  # keep sign

    # If no explicit Dividends transactions, attempt to derive from WHT + description
    if not div_rows and wht_index:
        div_rows = _derive_dividends_from_wht(root, wht_index)

    dividends: list[IbkrDividend] = []
    for row in div_rows:
        symbol = row["symbol"]
        dt = row["date"]
        wht = abs(wht_index.get((symbol, dt), 0.0))
        dividends.append(IbkrDividend(
            symbol=symbol,
            currency=row["currency"],
            payment_date=dt,
            amount=row["amount"],
            withholding_tax=wht,
            description=row["description"],
        ))

    return sorted(dividends, key=lambda d: d.payment_date)


def _derive_dividends_from_wht(root, wht_index: dict) -> list[dict]:
    """Derive gross dividend amount from WHT CashTransaction description.

    Description format: "SYMBOL(ISIN) CASH DIVIDEND CCY X.XX PER SHARE - XX TAX"
    Gross = per_share_amount × shares_at_exdate.
    Shares are estimated from all WHT transactions for the same (symbol, date).
    """
    rows = []
    seen: set[tuple[str, date]] = set()

    for elem in root.iter("CashTransaction"):
        if elem.get("type", "") != "Withholding Tax":
            continue
        symbol = elem.get("symbol", "").strip()
        desc = elem.get("description", "").strip()
        currency = elem.get("currency", "").strip()
        amount = _f(elem.get("amount"))
        dt = _parse_flex_datetime(elem.get("dateTime", ""))

        if not symbol or "CASH DIVIDEND" not in desc or amount is None or dt is None:
            continue
        if (symbol, dt) in seen:
            continue
        seen.add((symbol, dt))

        per_share = _parse_per_share_from_desc(desc)
        div_currency = _parse_currency_from_desc(desc) or currency
        total_wht = abs(wht_index.get((symbol, dt), 0.0))

        if per_share is None or per_share <= 0 or total_wht <= 0:
            continue

        # Infer share count from the magnitude of the first negative transaction
        # (WHT = per_share × shares × rate; but we don't know rate precisely).
        # Use total_wht / per_share as a lower bound proxy only when it yields a
        # plausible integer share count (within 20% rounding tolerance).
        # If ambiguous, skip and let the caller handle missing gross.
        gross = _infer_gross_from_wht_description(
            total_wht=total_wht,
            per_share=per_share,
            desc=desc,
            symbol=symbol,
            root=root,
            dt=dt,
        )
        if gross is None:
            _log.debug("Cannot derive gross dividend for %s on %s from WHT only", symbol, dt)
            continue

        rows.append({
            "symbol": symbol,
            "currency": div_currency,
            "date": dt,
            "amount": gross,
            "description": desc,
        })

    return rows


def _infer_gross_from_wht_description(
    *,
    total_wht: float,
    per_share: float,
    desc: str,
    symbol: str,
    root,
    dt: date,
) -> float | None:
    """Estimate gross = per_share × shares by inferring shares from trade history.

    Looks at <Trade> and <Lot> elements to find how many shares were held
    on the dividend payment date. Falls back to None when ambiguous.
    """
    shares = _shares_held_at(root, symbol, dt)
    if shares is None or shares <= 0:
        return None
    return round(per_share * shares, 6)


def _shares_held_at(root, symbol: str, as_of: date) -> float | None:
    """Estimate shares held as of a date from Trade open/close indicators."""
    held = 0.0
    found = False
    for elem in root.iter("Trade"):
        if elem.get("symbol", "") != symbol:
            continue
        if elem.get("assetCategory", "STK") not in ("STK", ""):
            continue
        td = _parse_flex_datetime(elem.get("tradeDate", "") or elem.get("dateTime", ""))
        if td is None or td > as_of:
            continue
        qty = _f(elem.get("quantity"))
        if qty is None:
            continue
        held += qty
        found = True
    return held if found else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_flex_datetime(s: str) -> date | None:
    if not s:
        return None
    for fmt in _FLEX_DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # Try plain YYYYMMDD
    if len(s) >= 8 and s[:8].isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            pass
    return None


def _parse_date_str(s: str) -> date | None:
    """Parse IBKR flex date strings like '20250101' or '2025-01-01'."""
    if not s:
        return None
    s = s.replace("-", "")
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, IndexError):
        return None


def _parse_per_share_from_desc(desc: str) -> float | None:
    """Extract per-share dividend amount from description like 'USD 0.20 PER SHARE'."""
    m = re.search(r"(?:USD|EUR|GBP|NOK|CHF|SEK|DKK|JPY|AUD|CAD)\s+([\d.]+)\s+PER\s+SHARE", desc, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _parse_currency_from_desc(desc: str) -> str | None:
    """Extract dividend currency from description."""
    m = re.search(r"\bCASH DIVIDEND\s+(USD|EUR|GBP|NOK|CHF|SEK|DKK|JPY|AUD|CAD)\b", desc, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None


def _f(s: str | None) -> float | None:
    if s is None or s.strip() in ("", "--", "N/A"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None
