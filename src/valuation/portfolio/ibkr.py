"""Parse IBKR activity statement CSV exports into structured trade and dividend records."""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IbkrTrade:
    symbol: str
    asset_category: str
    currency: str          # native trade currency, e.g. "USD" or "EUR"
    trade_date: date
    quantity: float        # positive = buy, negative = sell
    price: float           # price per share in trade currency
    proceeds: float        # gross proceeds in trade currency (negative for buys)
    commission: float      # commission in trade currency (negative or zero)
    # Secondary sort key: 0 = buys before sells on the same calendar day
    _sort_key: tuple = (0,)


@dataclass(frozen=True)
class IbkrDividend:
    symbol: str
    currency: str
    payment_date: date
    amount: float              # gross dividend in trade currency (positive)
    withholding_tax: float     # foreign WHT already deducted by broker (positive = tax paid)
    description: str
    isin: str = ""
    issuer_country: str = ""


@dataclass(frozen=True)
class IbkrOpenPosition:
    symbol: str
    asset_category: str
    currency: str
    quantity: float
    cost_price: float
    cost_basis: float
    close_price: float
    value: float
    unrealized_pnl: float


@dataclass(frozen=True)
class IbkrStatementMeta:
    base_currency: str
    account_id: str
    from_date: date | None
    to_date: date | None


def load_activity_statement(
    path: str | Path,
) -> tuple[list[IbkrTrade], list[IbkrDividend], IbkrStatementMeta]:
    """
    Parse an IBKR activity statement CSV.

    Returns (trades, dividends, meta).
    Trades are sorted chronologically with buys before sells on the same day.
    """
    text = Path(path).read_text(encoding="utf-8-sig")  # utf-8-sig strips BOM if present
    sections = _parse_ibkr_sections(text)
    meta = _extract_meta(sections)
    trades = _extract_stock_trades(sections)
    dividends = _extract_dividends(sections)
    return trades, dividends, meta


def load_trades(path: str | Path) -> list[IbkrTrade]:
    """Convenience wrapper — returns only trades (backwards-compat with old callers)."""
    trades, _, _ = load_activity_statement(path)
    return trades


def load_open_positions(path: str | Path) -> tuple[list[IbkrOpenPosition], IbkrStatementMeta]:
    """Parse the explicit Open Positions snapshot from an IBKR activity statement CSV."""
    text = Path(path).read_text(encoding="utf-8-sig")
    sections = _parse_ibkr_sections(text)
    meta = _extract_meta(sections)
    return _extract_open_positions(sections), meta


# ---------------------------------------------------------------------------
# Section parser
# ---------------------------------------------------------------------------

def _parse_ibkr_sections(csv_text: str) -> dict[str, list[dict[str, str]]]:
    """Split the IBKR multi-section CSV into {section_name: [row_dict, ...]}."""
    sections: dict[str, list[dict[str, str]]] = {}
    headers: dict[str, list[str]] = {}

    reader = csv.reader(io.StringIO(csv_text))
    for row in reader:
        if len(row) < 2:
            continue
        section = row[0].strip()
        row_type = row[1].strip()
        values = [v.strip() for v in row[2:]]

        if row_type == "Header":
            headers[section] = values
        elif row_type == "Data" and section in headers:
            cols = headers[section]
            padded = (values + [""] * len(cols))[: len(cols)]
            sections.setdefault(section, []).append(dict(zip(cols, padded)))

    return sections


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def _extract_meta(sections: dict[str, list[dict[str, str]]]) -> IbkrStatementMeta:
    field_map: dict[str, str] = {}
    for row in sections.get("Statement", []):
        name = row.get("Field Name", "").strip()
        value = row.get("Field Value", "").strip()
        if name:
            field_map[name] = value
    for row in sections.get("Account Information", []):
        name = row.get("Field Name", "").strip()
        value = row.get("Field Value", "").strip()
        if name:
            field_map[name] = value

    base_currency = field_map.get("Base Currency", "EUR")
    account_id = field_map.get("Account", field_map.get("AccountID", ""))
    from_str = field_map.get("Period", "")
    from_date = to_date = None

    # Period format: "January 1, 2026 - December 31, 2026"
    m = re.search(r"(\w+ \d+, \d+)\s*-\s*(\w+ \d+, \d+)", from_str)
    if m:
        for fmt in ("%B %d, %Y",):
            try:
                from_date = datetime.strptime(m.group(1), fmt).date()
                to_date = datetime.strptime(m.group(2), fmt).date()
                break
            except ValueError:
                pass

    return IbkrStatementMeta(
        base_currency=base_currency,
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
    )


# ---------------------------------------------------------------------------
# Trade extraction
# ---------------------------------------------------------------------------

def _extract_stock_trades(sections: dict[str, list[dict[str, str]]]) -> list[IbkrTrade]:
    """
    Extract stock trades.

    IBKR can export in "Order" granularity (one row per completed order, aggregating
    partial fills) or "Execution" granularity (one row per partial fill). If both
    discriminators appear in the same section, "Order" rows aggregate "Execution" rows,
    so we must use one or the other — never both.

    Strategy: if ANY "Order" row is present → use ONLY "Order" rows.
              otherwise → use "Execution" rows.
    This matches IBKR's standard CSV export where Order rows are the summary.
    """
    all_rows = sections.get("Trades", [])
    stock_rows = [
        r for r in all_rows
        if "Stocks" in r.get("Asset Category", "")
        and r.get("DataDiscriminator", "").strip() in ("Order", "Execution")
    ]

    has_order_rows = any(r.get("DataDiscriminator", "").strip() == "Order" for r in stock_rows)
    use_disc = "Order" if has_order_rows else "Execution"

    trades: list[IbkrTrade] = []
    for row in stock_rows:
        if row.get("DataDiscriminator", "").strip() != use_disc:
            continue

        symbol = row.get("Symbol", "").strip()
        currency = row.get("Currency", "").strip()
        dt_str = row.get("Date/Time", "").strip()

        if not symbol or not currency:
            continue

        trade_dt = _parse_ibkr_datetime(dt_str)
        if trade_dt is None:
            _log.warning("Unparseable Date/Time %r for %s — skipping", dt_str, symbol)
            continue

        quantity = _safe_float(_clean_number(row.get("Quantity", "0")))
        if quantity is None or abs(quantity) < 1e-9:
            continue

        price = _safe_float(_clean_number(row.get("T. Price", "0"))) or 0.0
        proceeds = _safe_float(_clean_number(row.get("Proceeds", "0"))) or 0.0
        commission = _safe_float(_clean_number(row.get("Comm/Fee", "0"))) or 0.0

        # Sort key: on the same calendar date, buys (quantity>0) sort before sells.
        sort_key = (trade_dt.date() if isinstance(trade_dt, datetime) else trade_dt,
                    0 if quantity > 0 else 1)

        trades.append(
            IbkrTrade(
                symbol=symbol,
                asset_category=row.get("Asset Category", "Stocks").strip(),
                currency=currency,
                trade_date=trade_dt.date() if isinstance(trade_dt, datetime) else trade_dt,
                quantity=quantity,
                price=price,
                proceeds=proceeds,
                commission=commission,
                _sort_key=sort_key,
            )
        )

    return sorted(trades, key=lambda t: t._sort_key)


# ---------------------------------------------------------------------------
# Open position extraction
# ---------------------------------------------------------------------------

def _extract_open_positions(sections: dict[str, list[dict[str, str]]]) -> list[IbkrOpenPosition]:
    positions: list[IbkrOpenPosition] = []
    for row in sections.get("Open Positions", []):
        if row.get("DataDiscriminator", "").strip() != "Summary":
            continue
        if "Stocks" not in row.get("Asset Category", ""):
            continue

        symbol = row.get("Symbol", "").strip()
        currency = row.get("Currency", "").strip()
        if not symbol or not currency:
            continue

        quantity = _safe_float(_clean_number(row.get("Quantity", "0")))
        cost_price = _safe_float(_clean_number(row.get("Cost Price", "0")))
        cost_basis = _safe_float(_clean_number(row.get("Cost Basis", "0")))
        close_price = _safe_float(_clean_number(row.get("Close Price", "0")))
        value = _safe_float(_clean_number(row.get("Value", "0")))
        unrealized = _safe_float(_clean_number(row.get("Unrealized P/L", "0")))

        if (
            quantity is None
            or cost_price is None
            or cost_basis is None
            or close_price is None
            or value is None
            or unrealized is None
        ):
            continue
        if abs(quantity) < 1e-9:
            continue

        positions.append(
            IbkrOpenPosition(
                symbol=symbol,
                asset_category=row.get("Asset Category", "Stocks").strip(),
                currency=currency,
                quantity=quantity,
                cost_price=cost_price,
                cost_basis=cost_basis,
                close_price=close_price,
                value=value,
                unrealized_pnl=unrealized,
            )
        )

    return sorted(positions, key=lambda p: p.symbol)


# ---------------------------------------------------------------------------
# Dividend extraction
# ---------------------------------------------------------------------------

def _extract_dividends(sections: dict[str, list[dict[str, str]]]) -> list[IbkrDividend]:
    """
    Parse the Dividends section and match each payment against Withholding Tax rows.

    IBKR dividend row format (Currency, Date, Description, Amount):
      "AAPL (US0378331005) Cash Dividend USD 0.24 per Share (Ordinary Dividend)"

    Withholding tax row format (Currency, Date, Description, Amount, Code):
      "AAPL (US0378331005) Cash Dividend USD 0.24 per Share - US Tax"
    """
    # Build withholding tax index: (symbol, date) -> tax amount (net signed).
    # IBKR can emit reversal/re-entry pairs; summing absolute debits inflates WHT.
    wht_index: dict[tuple[str, date], float] = {}
    for row in sections.get("Withholding Tax", []):
        wht_date = _parse_date_field(row.get("Date", ""))
        if wht_date is None:
            continue
        raw_symbol = _symbol_from_dividend_desc(row.get("Description", ""))
        if not raw_symbol:
            continue
        amount = _safe_float(_clean_number(row.get("Amount", "0"))) or 0.0
        key = (raw_symbol, wht_date)
        wht_index[key] = wht_index.get(key, 0.0) + amount

    dividends: list[IbkrDividend] = []
    for row in sections.get("Dividends", []):
        currency = row.get("Currency", "").strip()
        div_date = _parse_date_field(row.get("Date", ""))
        if div_date is None:
            continue
        desc = row.get("Description", "").strip()
        symbol = _symbol_from_dividend_desc(desc)
        if not symbol:
            continue
        amount = _safe_float(_clean_number(row.get("Amount", "0"))) or 0.0
        if amount <= 0:
            continue  # skip subtotals and reversals

        wht = abs(wht_index.get((symbol, div_date), 0.0))
        dividends.append(
            IbkrDividend(
                symbol=symbol,
                currency=currency,
                payment_date=div_date,
                amount=amount,
                withholding_tax=wht,
                description=desc,
            )
        )

    return sorted(dividends, key=lambda d: d.payment_date)


def _symbol_from_dividend_desc(description: str) -> str:
    """Extract ticker symbol from IBKR dividend description string."""
    # Format: "AAPL (US0378331005) Cash Dividend ..."
    m = re.match(r"^([A-Z0-9. -]+?)\s*\(", description.strip())
    if m:
        return m.group(1).strip()
    # Fallback: first whitespace-delimited token
    parts = description.strip().split()
    return parts[0] if parts else ""


# ---------------------------------------------------------------------------
# Date / number helpers
# ---------------------------------------------------------------------------

def _parse_ibkr_datetime(dt_str: str) -> datetime | date | None:
    """Handle IBKR Date/Time formats including '2026-01-15, 10:30:00'."""
    for fmt in ("%Y-%m-%d, %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            pass
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d").date()
    except ValueError:
        pass
    return None


def _parse_date_field(value: str) -> date | None:
    """Parse a plain date field from IBKR sections like Dividends."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    return None


def _clean_number(value: str) -> str:
    """Remove IBKR thousand-separator commas: '1,850.00' → '1850.00'."""
    return value.replace(",", "")


def _safe_float(value: str) -> float | None:
    if not value or value.strip() in ("", "--", "N/A"):
        return None
    try:
        return float(value)
    except ValueError:
        return None
