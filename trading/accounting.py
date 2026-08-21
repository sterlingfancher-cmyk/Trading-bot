"""Shadow-only canonical ledger/accounting projection for Stable Paper Core v3 Stage E.

This module projects a deterministic portfolio from a verified baseline plus an
ordered append-only execution stream. It has no production runtime, persistence,
market-data, risk, strategy, sizing, live, or ML authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Tuple

from trading.state import AccountingEpochSnapshot, PortfolioSnapshot, PositionSnapshot

VERSION = "stable-paper-core-v3-stage-e-accounting-2026-08-20-v1"
AUTHORITY = "shadow_only"
ACCOUNTING_MODEL = "bidirectional_margin_v1"


class AccountingInvariantError(ValueError):
    """Raised when canonical execution evidence cannot be projected safely."""


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise AccountingInvariantError(f"{name} must be numeric")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise AccountingInvariantError(f"{name} must be numeric") from exc
    if not isfinite(out):
        raise AccountingInvariantError(f"{name} must be finite")
    return out


def _positive(value: Any, *, name: str) -> float:
    out = _finite(value, name=name)
    if out <= 0.0:
        raise AccountingInvariantError(f"{name} must be positive")
    return out


@dataclass(frozen=True)
class ExecutionSnapshot:
    sequence: int
    symbol: str
    event: str
    side: str
    quantity: float
    price: float
    timestamp: str
    execution_id: str

    def __post_init__(self) -> None:
        if int(self.sequence) <= 0:
            raise AccountingInvariantError("execution sequence must be positive")
        symbol = str(self.symbol or "").upper().strip()
        event = str(self.event or "").lower().strip()
        side = str(self.side or "").lower().strip()
        execution_id = str(self.execution_id or "").strip()
        if not symbol or not execution_id:
            raise AccountingInvariantError("symbol and execution_id are required")
        if event not in {"entry", "exit"}:
            raise AccountingInvariantError("event must be entry or exit")
        if side not in {"long", "short"}:
            raise AccountingInvariantError("side must be long or short")
        object.__setattr__(self, "sequence", int(self.sequence))
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "event", event)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "quantity", _positive(self.quantity, name="quantity"))
        object.__setattr__(self, "price", _positive(self.price, name="price"))
        object.__setattr__(self, "timestamp", str(self.timestamp or ""))
        object.__setattr__(self, "execution_id", execution_id)


@dataclass(frozen=True)
class BaselineSnapshot:
    cash: float
    positions: Tuple[PositionSnapshot, ...] = field(default_factory=tuple)
    realized_total: float = 0.0
    realized_today: float = 0.0
    accounting_epoch: AccountingEpochSnapshot | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cash", _finite(self.cash, name="cash"))
        object.__setattr__(self, "realized_total", _finite(self.realized_total, name="realized_total"))
        object.__setattr__(self, "realized_today", _finite(self.realized_today, name="realized_today"))
        positions = tuple(self.positions)
        symbols = [row.symbol for row in positions]
        if len(symbols) != len(set(symbols)):
            raise AccountingInvariantError("baseline cannot contain duplicate symbols")
        object.__setattr__(self, "positions", positions)


@dataclass(frozen=True)
class AccountingProjection:
    portfolio: PortfolioSnapshot
    execution_rows: int
    last_sequence: int
    execution_ids: Tuple[str, ...]
    authority: str = AUTHORITY
    accounting_model: str = ACCOUNTING_MODEL
    version: str = VERSION

    def __post_init__(self) -> None:
        if self.authority != AUTHORITY:
            raise AccountingInvariantError("Stage E projection must remain shadow-only")
        if self.accounting_model != ACCOUNTING_MODEL:
            raise AccountingInvariantError("unexpected accounting model")
        if self.execution_rows < 0 or self.last_sequence < 0:
            raise AccountingInvariantError("execution metadata cannot be negative")
        if len(self.execution_ids) != len(set(self.execution_ids)):
            raise AccountingInvariantError("duplicate execution ids in projection")

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "authority": self.authority,
            "accounting_model": self.accounting_model,
            "version": self.version,
            "execution_rows": self.execution_rows,
            "last_sequence": self.last_sequence,
            "execution_ids": self.execution_ids,
            "portfolio": self.portfolio,
        })


class CanonicalAccountingProjector:
    authority = AUTHORITY
    accounting_model = ACCOUNTING_MODEL
    reads_state_file = False
    writes_state_file = False
    fetches_market_data = False
    mutates_risk = False
    places_orders = False

    @classmethod
    def project(
        cls,
        *,
        baseline: BaselineSnapshot,
        executions: Iterable[ExecutionSnapshot],
        marks: Mapping[str, float] | None = None,
        today: str = "",
    ) -> AccountingProjection:
        rows = tuple(executions)
        sequences = [row.sequence for row in rows]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise AccountingInvariantError("execution sequence must be strictly ordered and unique")
        ids = [row.execution_id for row in rows]
        if len(ids) != len(set(ids)):
            raise AccountingInvariantError("duplicate execution_id")

        cash = baseline.cash
        realized_total = baseline.realized_total
        realized_today = baseline.realized_today
        books: dict[str, dict[str, list[list[float]]]] = {}
        for position in baseline.positions:
            books.setdefault(position.symbol, {"long": [], "short": []})[position.side].append(
                [position.quantity, position.entry_price]
            )

        for row in rows:
            side_books = books.setdefault(row.symbol, {"long": [], "short": []})
            opposite = "short" if row.side == "long" else "long"
            if row.event == "entry" and any(qty > 1e-12 for qty, _ in side_books[opposite]):
                raise AccountingInvariantError(f"opposing open book for {row.symbol}")

            book = side_books[row.side]
            if row.event == "entry":
                notional = row.quantity * row.price
                if notional > cash + max(2.0, abs(cash) * 0.0025):
                    raise AccountingInvariantError(f"entry exceeds available cash for {row.symbol}")
                cash -= notional
                book.append([row.quantity, row.price])
                continue

            remaining = row.quantity
            release = 0.0
            realized = 0.0
            while remaining > 1e-12 and book:
                lot_qty, lot_price = book[0]
                used = min(remaining, lot_qty)
                if row.side == "long":
                    release += used * row.price
                    realized += (row.price - lot_price) * used
                else:
                    pnl = (lot_price - row.price) * used
                    release += (lot_price * used) + pnl
                    realized += pnl
                lot_qty -= used
                remaining -= used
                if lot_qty <= 1e-12:
                    book.pop(0)
                else:
                    book[0][0] = lot_qty
            if remaining > 1e-9:
                raise AccountingInvariantError(f"unmatched exit for {row.symbol}")
            cash += release
            realized_total += realized
            if today and row.timestamp[:10] == today:
                realized_today += realized

        mark_map = {str(k).upper(): _positive(v, name=f"{k} mark") for k, v in dict(marks or {}).items()}
        positions: list[PositionSnapshot] = []
        unrealized_total = 0.0
        position_value_total = 0.0
        for symbol, side_books in books.items():
            open_sides = [side for side in ("long", "short") if sum(q for q, _ in side_books[side]) > 1e-12]
            if len(open_sides) > 1:
                raise AccountingInvariantError(f"opposing open books remain for {symbol}")
            if not open_sides:
                continue
            side = open_sides[0]
            lots = side_books[side]
            qty = sum(q for q, _ in lots)
            basis = sum(q * px for q, px in lots)
            entry = basis / qty
            mark = mark_map.get(symbol, entry)
            if side == "long":
                unrealized = (mark - entry) * qty
                position_value = qty * mark
            else:
                unrealized = (entry - mark) * qty
                position_value = basis + unrealized
            unrealized_total += unrealized
            position_value_total += position_value
            positions.append(PositionSnapshot(symbol=symbol, side=side, quantity=qty, entry_price=entry, mark_price=mark))

        equity = cash + position_value_total
        if equity <= 0.0:
            raise AccountingInvariantError("projected equity must remain positive")
        portfolio = PortfolioSnapshot(
            cash=cash,
            equity=equity,
            realized_total=realized_total,
            realized_today=realized_today,
            unrealized_pnl=unrealized_total,
            positions=tuple(sorted(positions, key=lambda row: row.symbol)),
            accounting_epoch=baseline.accounting_epoch,
        )
        return AccountingProjection(
            portfolio=portfolio,
            execution_rows=len(rows),
            last_sequence=sequences[-1] if sequences else 0,
            execution_ids=tuple(ids),
        )

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType({
            "target_interface": "trading.accounting.CanonicalAccountingProjector",
            "authority": cls.authority,
            "accounting_model": cls.accounting_model,
            "reads_state_file": cls.reads_state_file,
            "writes_state_file": cls.writes_state_file,
            "fetches_market_data": cls.fetches_market_data,
            "mutates_risk": cls.mutates_risk,
            "places_orders": cls.places_orders,
            "version": VERSION,
        })
