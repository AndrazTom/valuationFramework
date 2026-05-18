"""Parse IBKR activity statement CSV exports into structured trade records."""

from __future__ import annotations

import csv
import io
import logging
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


def load_activity_statement(path: str | Path) -> list[IbkrTrade]:
    """Parse an IBKR activity statement CSV and return all stock trades sorted by date."""
    text = Path(path).read_text(encoding="utf-8-sig")  # utf-8-sig strips BOM if present
    sections = _parse_ibkr_sections(text)
    return _extract_stock_trades(sections)


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
            # Align lengths: IBKR sometimes adds trailing empty fields
            padded = (values + [""] * len(cols))[: len(cols)]
            sections.setdefault(section, []).append(dict(zip(cols, padded)))

    return sections


def _extract_stock_trades(sections: dict[str, list[dict[str, str]]]) -> list[IbkrTrade]:
    trades: list[IbkrTrade] = []

    for row in sections.get("Trades", []):
        disc = row.get("DataDiscriminator", "").strip()
        # Skip sub-totals, totals, and corporate-action rows
        if disc not in ("Order", "Execution"):
            continue
        asset_cat = row.get("Asset Category", "").strip()
        if "Stocks" not in asset_cat:
            continue

        symbol = row.get("Symbol", "").strip()
        currency = row.get("Currency", "").strip()
        dt_str = row.get("Date/Time", "").strip()
        qty_str = _clean_number(row.get("Quantity", "0"))
        price_str = _clean_number(row.get("T. Price", "0"))
        proceeds_str = _clean_number(row.get("Proceeds", "0"))
        comm_str = _clean_number(row.get("Comm/Fee", "0"))

        if not symbol:
            continue

        trade_date = _parse_ibkr_datetime(dt_str)
        if trade_date is None:
            _log.warning("Could not parse date %r for %s — skipping row", dt_str, symbol)
            continue

        quantity = _safe_float(qty_str)
        if quantity is None or abs(quantity) < 1e-9:
            continue

        trades.append(
            IbkrTrade(
                symbol=symbol,
                asset_category=asset_cat,
                currency=currency,
                trade_date=trade_date,
                quantity=quantity,
                price=_safe_float(price_str) or 0.0,
                proceeds=_safe_float(proceeds_str) or 0.0,
                commission=_safe_float(comm_str) or 0.0,
            )
        )

    return sorted(trades, key=lambda t: t.trade_date)


def _parse_ibkr_datetime(dt_str: str) -> date | None:
    """Handle formats: '2026-01-15, 10:30:00', '2026-01-15 10:30:00', '2026-01-15'."""
    for fmt in ("%Y-%m-%d, %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt).date()
        except ValueError:
            continue
    return None


def _clean_number(value: str) -> str:
    """Remove thousand-separator commas from numeric strings."""
    # IBKR uses commas as thousand separators: "1,850.00" → "1850.00"
    # But we must not strip decimal commas (European format), so only strip when a period also exists
    stripped = value.replace(",", "")
    return stripped


def _safe_float(value: str) -> float | None:
    if not value or value.strip() in ("", "--", "N/A"):
        return None
    try:
        return float(value)
    except ValueError:
        return None
