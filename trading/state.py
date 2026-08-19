"""Shadow-only canonical state models for Stable Paper Core v3 Stage A.

No object in this module has runtime, persistence, market-data, or order authority.
The models define the future ownership boundary and deterministic invariants only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping, Tuple

VERSION = "stable-paper-core-v3-stage-a-2026-08-19-v1"
AUTHORITY = "shadow_only"


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _non_negative(value: Any, *, name: str) -> float:
    result = _finite(value, name=name)
    if result < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return result


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    mark_price: float

    def __post_init__(self) -> None:
        symbol = str(self.symbol or "").upper().strip()
        side = str(self.side or "").lower().strip()
        if not symbol:
            raise ValueError("symbol is required")
        if side not in {"long", "short"}:
            raise ValueError("side must be long or short")
        quantity = _non_negative(self.quantity, name="quantity")
        if quantity <= 0.0:
            raise ValueError("quantity must be positive")
        entry_price = _non_negative(self.entry_price, name="entry_price")
        mark_price = _non_negative(self.mark_price, name="mark_price")
        if entry_price <= 0.0 or mark_price <= 0.0:
            raise ValueError("position prices must be positive")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "entry_price", entry_price)
        object.__setattr__(self, "mark_price", mark_price)

    @property
    def signed_market_value(self) -> float:
        notional = self.quantity * self.mark_price
        return notional if self.side == "long" else -notional


@dataclass(frozen=True)
class AccountingEpochSnapshot:
    epoch_id: str
    baseline_type: str
    historical_evidence_archived: bool
    validation_hold: bool

    def __post_init__(self) -> None:
        if not str(self.epoch_id or "").strip():
            raise ValueError("epoch_id is required")
        if not str(self.baseline_type or "").strip():
            raise ValueError("baseline_type is required")


@dataclass(frozen=True)
class PortfolioSnapshot:
    cash: float
    equity: float
    realized_total: float
    realized_today: float
    unrealized_pnl: float
    positions: Tuple[PositionSnapshot, ...] = field(default_factory=tuple)
    accounting_epoch: AccountingEpochSnapshot | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cash", _finite(self.cash, name="cash"))
        equity = _finite(self.equity, name="equity")
        if equity <= 0.0:
            raise ValueError("equity must be positive for a canonical protected snapshot")
        object.__setattr__(self, "equity", equity)
        object.__setattr__(self, "realized_total", _finite(self.realized_total, name="realized_total"))
        object.__setattr__(self, "realized_today", _finite(self.realized_today, name="realized_today"))
        object.__setattr__(self, "unrealized_pnl", _finite(self.unrealized_pnl, name="unrealized_pnl"))
        object.__setattr__(self, "positions", tuple(self.positions))
        symbols = [position.symbol for position in self.positions]
        if len(symbols) != len(set(symbols)):
            raise ValueError("canonical portfolio cannot contain duplicate position symbols")


@dataclass(frozen=True)
class RiskStateSnapshot:
    date: str
    day_start_equity: float
    day_peak_equity: float
    daily_loss_fraction: float
    intraday_drawdown_fraction: float
    halted: bool
    halt_reason: str = ""

    def __post_init__(self) -> None:
        if not str(self.date or "").strip():
            raise ValueError("risk date is required")
        start = _finite(self.day_start_equity, name="day_start_equity")
        peak = _finite(self.day_peak_equity, name="day_peak_equity")
        if start <= 0.0 or peak <= 0.0:
            raise ValueError("risk baselines must be positive")
        if peak < start:
            raise ValueError("day_peak_equity cannot be below day_start_equity at snapshot validation")
        daily = _non_negative(self.daily_loss_fraction, name="daily_loss_fraction")
        drawdown = _non_negative(self.intraday_drawdown_fraction, name="intraday_drawdown_fraction")
        object.__setattr__(self, "day_start_equity", start)
        object.__setattr__(self, "day_peak_equity", peak)
        object.__setattr__(self, "daily_loss_fraction", daily)
        object.__setattr__(self, "intraday_drawdown_fraction", drawdown)
        object.__setattr__(self, "halt_reason", str(self.halt_reason or ""))


@dataclass(frozen=True)
class CanonicalStateSnapshot:
    portfolio: PortfolioSnapshot
    risk: RiskStateSnapshot
    execution_ledger_rows: int
    execution_chain_valid: bool
    source_version: str = VERSION
    authority: str = AUTHORITY

    def __post_init__(self) -> None:
        if int(self.execution_ledger_rows) < 0:
            raise ValueError("execution_ledger_rows must be non-negative")
        object.__setattr__(self, "execution_ledger_rows", int(self.execution_ledger_rows))
        if self.authority != AUTHORITY:
            raise ValueError("Stage A snapshots are shadow-only")

    def to_dict(self) -> Mapping[str, Any]:
        positions = tuple(
            MappingProxyType(
                {
                    "symbol": row.symbol,
                    "side": row.side,
                    "quantity": row.quantity,
                    "entry_price": row.entry_price,
                    "mark_price": row.mark_price,
                }
            )
            for row in self.portfolio.positions
        )
        return MappingProxyType(
            {
                "authority": self.authority,
                "source_version": self.source_version,
                "portfolio": MappingProxyType(
                    {
                        "cash": self.portfolio.cash,
                        "equity": self.portfolio.equity,
                        "realized_total": self.portfolio.realized_total,
                        "realized_today": self.portfolio.realized_today,
                        "unrealized_pnl": self.portfolio.unrealized_pnl,
                        "positions": positions,
                    }
                ),
                "risk": MappingProxyType(
                    {
                        "date": self.risk.date,
                        "day_start_equity": self.risk.day_start_equity,
                        "day_peak_equity": self.risk.day_peak_equity,
                        "daily_loss_fraction": self.risk.daily_loss_fraction,
                        "intraday_drawdown_fraction": self.risk.intraday_drawdown_fraction,
                        "halted": self.risk.halted,
                        "halt_reason": self.risk.halt_reason,
                    }
                ),
                "execution_ledger_rows": self.execution_ledger_rows,
                "execution_chain_valid": bool(self.execution_chain_valid),
            }
        )


class StateStore:
    """Stage A future interface descriptor; deliberately has no persistence authority."""

    authority = AUTHORITY
    write_enabled = False
    reads_state_file = False
    writes_state_file = False

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": "trading.state.StateStore",
                "authority": cls.authority,
                "write_enabled": cls.write_enabled,
                "reads_state_file": cls.reads_state_file,
                "writes_state_file": cls.writes_state_file,
                "version": VERSION,
            }
        )
