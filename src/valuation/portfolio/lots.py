"""FIFO lot engine: builds open positions and realized gain records from trade history."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from valuation.portfolio.ibkr import IbkrTrade

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Lot:
    """An open (unrealized) position lot."""
    symbol: str
    currency: str
    acquired: date
    quantity: float
    cost_per_share_native: float  # price in trade currency per share
    commission_native: float      # total commission allocated to this lot in trade currency
    cost_per_share_eur: float | None   # None when FX conversion not available
    commission_eur: float | None

    @property
    def cost_basis_native(self) -> float:
        return self.cost_per_share_native * self.quantity + self.commission_native

    @property
    def cost_basis_eur(self) -> float | None:
        if self.cost_per_share_eur is None:
            return None
        eur_comm = self.commission_eur or 0.0
        return self.cost_per_share_eur * self.quantity + eur_comm


@dataclass(frozen=True)
class RealizedGain:
    """One matched sell-lot pair from FIFO matching."""
    symbol: str
    currency: str
    acquired: date
    sold: date
    quantity: float
    cost_basis_native: float
    proceeds_native: float        # after commission deduction
    cost_basis_eur: float | None
    proceeds_eur: float | None
    needs_fx: bool                # True when EUR amounts could not be determined

    @property
    def gain_native(self) -> float:
        return self.proceeds_native - self.cost_basis_native

    @property
    def gain_eur(self) -> float | None:
        if self.cost_basis_eur is None or self.proceeds_eur is None:
            return None
        return self.proceeds_eur - self.cost_basis_eur


# ---------------------------------------------------------------------------
# Internal mutable lot (consumed during FIFO matching)
# ---------------------------------------------------------------------------

@dataclass
class _OpenLot:
    acquired: date
    currency: str
    quantity: float
    cost_per_share_native: float
    commission_native: float      # remaining commission (shrinks as lot is partially consumed)
    eur_rate_at_buy: float | None  # EUR per 1 unit of trade currency at acquisition


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_lots_and_realized(
    trades: Sequence[IbkrTrade],
    fx_rates: dict[tuple[str, str], float] | None = None,
) -> tuple[list[Lot], list[RealizedGain]]:
    """
    Process trades chronologically, returning (open_lots, realized_gains).

    fx_rates maps (currency, "YYYY-MM-DD") → EUR rate, e.g. ("USD", "2026-01-15") → 0.918.
    When fx_rates is None or a rate is missing, EUR amounts are left as None.
    For EUR-denominated trades the rate is always 1.0 and fx_rates is ignored.
    """
    open_lots: dict[str, list[_OpenLot]] = {}
    realized: list[RealizedGain] = []

    for trade in trades:
        eur_rate = _eur_rate(trade, fx_rates)

        if trade.quantity > 0:
            _process_buy(trade, eur_rate, open_lots)
        elif trade.quantity < 0:
            _process_sell(trade, eur_rate, open_lots, realized)

    # Convert remaining open lots into Lot records
    result_lots: list[Lot] = []
    for symbol, lots in open_lots.items():
        for lot in lots:
            cost_eur = (
                lot.cost_per_share_native * lot.eur_rate_at_buy
                if lot.eur_rate_at_buy is not None
                else None
            )
            comm_eur = (
                lot.commission_native * lot.eur_rate_at_buy
                if lot.eur_rate_at_buy is not None
                else None
            )
            result_lots.append(
                Lot(
                    symbol=symbol,
                    currency=lot.currency,
                    acquired=lot.acquired,
                    quantity=lot.quantity,
                    cost_per_share_native=lot.cost_per_share_native,
                    commission_native=lot.commission_native,
                    cost_per_share_eur=cost_eur,
                    commission_eur=comm_eur,
                )
            )

    return result_lots, realized


def _process_buy(
    trade: IbkrTrade,
    eur_rate: float | None,
    open_lots: dict[str, list[_OpenLot]],
) -> None:
    qty = trade.quantity
    # Effective price per share (accounts for any execution slippage vs T. Price)
    price_per_share = abs(trade.proceeds) / qty if qty > 0 else trade.price
    commission = abs(trade.commission)

    open_lots.setdefault(trade.symbol, []).append(
        _OpenLot(
            acquired=trade.trade_date,
            currency=trade.currency,
            quantity=qty,
            cost_per_share_native=price_per_share,
            commission_native=commission,
            eur_rate_at_buy=eur_rate,
        )
    )


def _process_sell(
    trade: IbkrTrade,
    sell_eur_rate: float | None,
    open_lots: dict[str, list[_OpenLot]],
    realized: list[RealizedGain],
) -> None:
    sell_qty = abs(trade.quantity)
    lots = open_lots.get(trade.symbol, [])

    proceeds_per_share_native = abs(trade.proceeds) / sell_qty if sell_qty > 0 else 0.0
    sell_commission_native = abs(trade.commission)

    remaining = sell_qty
    while remaining > 1e-9 and lots:
        lot = lots[0]
        matched = min(remaining, lot.quantity)
        lot_fraction = matched / lot.quantity

        # Cost side
        cost_native = lot.cost_per_share_native * matched + lot.commission_native * lot_fraction
        cost_eur = (
            cost_native * lot.eur_rate_at_buy
            if lot.eur_rate_at_buy is not None
            else None
        )

        # Proceeds side (proportional commission from the sell)
        sell_fraction_of_total = matched / sell_qty
        sell_comm_for_this_lot = sell_commission_native * sell_fraction_of_total
        proceeds_native = proceeds_per_share_native * matched - sell_comm_for_this_lot
        proceeds_eur = (
            proceeds_native * sell_eur_rate
            if sell_eur_rate is not None
            else None
        )

        realized.append(
            RealizedGain(
                symbol=trade.symbol,
                currency=trade.currency,
                acquired=lot.acquired,
                sold=trade.trade_date,
                quantity=matched,
                cost_basis_native=cost_native,
                proceeds_native=proceeds_native,
                cost_basis_eur=cost_eur,
                proceeds_eur=proceeds_eur,
                needs_fx=(lot.eur_rate_at_buy is None or sell_eur_rate is None),
            )
        )

        # Consume from the lot
        if matched >= lot.quantity - 1e-9:
            lots.pop(0)
        else:
            lot.quantity -= matched
            lot.commission_native -= lot.commission_native * lot_fraction

        remaining -= matched

    if remaining > 1e-9:
        _log.warning(
            "Sell %s on %s: %.4f shares unmatched (no open lots); "
            "possibly a short sale or missing buy records",
            trade.symbol,
            trade.trade_date,
            remaining,
        )


def _eur_rate(trade: IbkrTrade, fx_rates: dict[tuple[str, str], float] | None) -> float | None:
    if trade.currency == "EUR":
        return 1.0
    if fx_rates is None:
        return None
    return fx_rates.get((trade.currency, trade.trade_date.isoformat()))
