"""Shadow-only deterministic valuation for Stable Paper Core v3 Stage B.

This module defines the future canonical valuation boundary. It performs no
market-data fetches, state-file I/O, runtime registration, order placement, or
risk mutation. Upstream code must supply already-validated protected marks.

Accounting semantics intentionally match the existing bidirectional margin
model:

- long entry reserves entry notional; position value is quantity * mark;
- short entry reserves entry notional as margin; position value is reserved
  basis plus unrealized P&L.

Therefore total equity is always:

    cash + total_cost_basis + total_unrealized_pnl

for both long and short positions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Tuple

from trading.state import PositionSnapshot

VERSION = "stable-paper-core-v3-stage-b-valuation-2026-08-20-v1"
AUTHORITY = "shadow_only"
ACCOUNTING_MODEL = "bidirectional_margin_v1"


class ValuationInvariantError(ValueError):
    """Raised when a protected valuation cannot be produced safely."""


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValuationInvariantError(f"{name} must be numeric")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValuationInvariantError(f"{name} must be numeric") from exc
    if not isfinite(out):
        raise ValuationInvariantError(f"{name} must be finite")
    return out


def _positive(value: Any, *, name: str) -> float:
    out = _finite(value, name=name)
    if out <= 0.0:
        raise ValuationInvariantError(f"{name} must be positive")
    return out


@dataclass(frozen=True)
class ProtectedMarkSnapshot:
    """A mark whose freshness and plausibility were proven upstream."""

    symbol: str
    price: float
    source: str
    fresh: bool
    plausible: bool
    observed_at: str = ""

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").upper().strip()
        source = str(self.source or "").strip()
        if not symbol:
            raise ValuationInvariantError("mark symbol is required")
        if not source:
            raise ValuationInvariantError("mark source is required")
        price = _positive(self.price, name="mark price")
        if not bool(self.fresh):
            raise ValuationInvariantError(f"{symbol} mark is not fresh")
        if not bool(self.plausible):
            raise ValuationInvariantError(f"{symbol} mark is not plausible")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "fresh", True)
        object.__setattr__(self, "plausible", True)
        object.__setattr__(self, "observed_at", str(self.observed_at or ""))


@dataclass(frozen=True)
class PositionValuation:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    mark_price: float
    cost_basis: float
    market_notional: float
    position_value: float
    unrealized_pnl: float
    mark_source: str
    mark_observed_at: str = ""

    def __post_init__(self) -> None:
        for name in (
            "quantity",
            "entry_price",
            "mark_price",
            "cost_basis",
            "market_notional",
            "position_value",
            "unrealized_pnl",
        ):
            _finite(getattr(self, name), name=name)
        if self.quantity <= 0.0:
            raise ValuationInvariantError("quantity must be positive")
        if self.entry_price <= 0.0 or self.mark_price <= 0.0:
            raise ValuationInvariantError("position prices must be positive")
        if self.cost_basis <= 0.0 or self.market_notional <= 0.0:
            raise ValuationInvariantError("position basis/notional must be positive")
        if self.side not in {"long", "short"}:
            raise ValuationInvariantError("side must be long or short")


@dataclass(frozen=True)
class ValuationSnapshot:
    cash: float
    equity: float
    total_cost_basis: float
    total_position_value: float
    total_unrealized_pnl: float
    gross_market_exposure: float
    net_market_exposure: float
    positions: Tuple[PositionValuation, ...] = field(default_factory=tuple)
    accounting_model: str = ACCOUNTING_MODEL
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        cash = _finite(self.cash, name="cash")
        equity = _finite(self.equity, name="equity")
        basis = _finite(self.total_cost_basis, name="total_cost_basis")
        position_value = _finite(
            self.total_position_value, name="total_position_value"
        )
        unrealized = _finite(
            self.total_unrealized_pnl, name="total_unrealized_pnl"
        )
        gross = _finite(self.gross_market_exposure, name="gross_market_exposure")
        net = _finite(self.net_market_exposure, name="net_market_exposure")
        if equity <= 0.0:
            raise ValuationInvariantError(
                "protected equity must be positive; risk baseline is ineligible"
            )
        if basis < 0.0 or gross < 0.0:
            raise ValuationInvariantError("basis and gross exposure cannot be negative")
        if self.accounting_model != ACCOUNTING_MODEL:
            raise ValuationInvariantError("unexpected accounting model")
        if self.authority != AUTHORITY:
            raise ValuationInvariantError("Stage B valuation must remain shadow-only")
        positions = tuple(self.positions)
        symbols = [row.symbol for row in positions]
        if len(symbols) != len(set(symbols)):
            raise ValuationInvariantError("duplicate position valuation symbols")

        expected_position_value = basis + unrealized
        expected_equity = cash + expected_position_value
        tolerance = max(1e-9, abs(expected_equity) * 1e-12)
        if abs(position_value - expected_position_value) > tolerance:
            raise ValuationInvariantError(
                "position value must equal cost basis plus unrealized P&L"
            )
        if abs(equity - expected_equity) > tolerance:
            raise ValuationInvariantError(
                "equity must equal cash plus deterministic position value"
            )

        object.__setattr__(self, "cash", cash)
        object.__setattr__(self, "equity", equity)
        object.__setattr__(self, "total_cost_basis", basis)
        object.__setattr__(self, "total_position_value", position_value)
        object.__setattr__(self, "total_unrealized_pnl", unrealized)
        object.__setattr__(self, "gross_market_exposure", gross)
        object.__setattr__(self, "net_market_exposure", net)
        object.__setattr__(self, "positions", positions)

    @property
    def risk_baseline_eligible(self) -> bool:
        return self.equity > 0.0

    def to_dict(self) -> Mapping[str, Any]:
        rows = tuple(
            MappingProxyType(
                {
                    "symbol": row.symbol,
                    "side": row.side,
                    "quantity": row.quantity,
                    "entry_price": row.entry_price,
                    "mark_price": row.mark_price,
                    "cost_basis": row.cost_basis,
                    "market_notional": row.market_notional,
                    "position_value": row.position_value,
                    "unrealized_pnl": row.unrealized_pnl,
                    "mark_source": row.mark_source,
                    "mark_observed_at": row.mark_observed_at,
                }
            )
            for row in self.positions
        )
        return MappingProxyType(
            {
                "authority": self.authority,
                "version": self.version,
                "accounting_model": self.accounting_model,
                "cash": self.cash,
                "equity": self.equity,
                "total_cost_basis": self.total_cost_basis,
                "total_position_value": self.total_position_value,
                "total_unrealized_pnl": self.total_unrealized_pnl,
                "gross_market_exposure": self.gross_market_exposure,
                "net_market_exposure": self.net_market_exposure,
                "risk_baseline_eligible": self.risk_baseline_eligible,
                "positions": rows,
            }
        )


class DeterministicValuationService:
    """Pure Stage B valuation service with no external/runtime authority."""

    authority = AUTHORITY
    accounting_model = ACCOUNTING_MODEL
    fetches_market_data = False
    reads_state_file = False
    writes_state_file = False
    mutates_risk = False
    places_orders = False

    @classmethod
    def value(
        cls,
        *,
        cash: float,
        positions: Iterable[PositionSnapshot],
        marks: Iterable[ProtectedMarkSnapshot],
    ) -> ValuationSnapshot:
        cash_value = _finite(cash, name="cash")
        position_rows = tuple(positions)
        mark_rows = tuple(marks)

        position_symbols = [row.symbol for row in position_rows]
        if len(position_symbols) != len(set(position_symbols)):
            raise ValuationInvariantError("duplicate position symbols")

        mark_map: dict[str, ProtectedMarkSnapshot] = {}
        for mark in mark_rows:
            if mark.symbol in mark_map:
                raise ValuationInvariantError(
                    f"duplicate protected mark for {mark.symbol}"
                )
            mark_map[mark.symbol] = mark

        if set(mark_map) != set(position_symbols):
            missing = sorted(set(position_symbols) - set(mark_map))
            extra = sorted(set(mark_map) - set(position_symbols))
            raise ValuationInvariantError(
                f"protected mark coverage mismatch; missing={missing}; extra={extra}"
            )

        valued: list[PositionValuation] = []
        total_basis = 0.0
        total_position_value = 0.0
        total_unrealized = 0.0
        gross_exposure = 0.0
        net_exposure = 0.0

        for position in position_rows:
            mark = mark_map[position.symbol]
            quantity = _positive(position.quantity, name=f"{position.symbol} quantity")
            entry = _positive(position.entry_price, name=f"{position.symbol} entry")
            price = _positive(mark.price, name=f"{position.symbol} protected mark")
            basis = quantity * entry
            market_notional = quantity * price

            if position.side == "long":
                unrealized = (price - entry) * quantity
                position_value = market_notional
                signed_exposure = market_notional
            elif position.side == "short":
                unrealized = (entry - price) * quantity
                position_value = basis + unrealized
                signed_exposure = -market_notional
            else:
                raise ValuationInvariantError(
                    f"unsupported side for {position.symbol}: {position.side}"
                )

            valued.append(
                PositionValuation(
                    symbol=position.symbol,
                    side=position.side,
                    quantity=quantity,
                    entry_price=entry,
                    mark_price=price,
                    cost_basis=basis,
                    market_notional=market_notional,
                    position_value=position_value,
                    unrealized_pnl=unrealized,
                    mark_source=mark.source,
                    mark_observed_at=mark.observed_at,
                )
            )
            total_basis += basis
            total_position_value += position_value
            total_unrealized += unrealized
            gross_exposure += market_notional
            net_exposure += signed_exposure

        equity = cash_value + total_position_value
        return ValuationSnapshot(
            cash=cash_value,
            equity=equity,
            total_cost_basis=total_basis,
            total_position_value=total_position_value,
            total_unrealized_pnl=total_unrealized,
            gross_market_exposure=gross_exposure,
            net_market_exposure=net_exposure,
            positions=tuple(valued),
        )

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": "trading.valuation.DeterministicValuationService",
                "authority": cls.authority,
                "accounting_model": cls.accounting_model,
                "fetches_market_data": cls.fetches_market_data,
                "reads_state_file": cls.reads_state_file,
                "writes_state_file": cls.writes_state_file,
                "mutates_risk": cls.mutates_risk,
                "places_orders": cls.places_orders,
                "version": VERSION,
            }
        )
