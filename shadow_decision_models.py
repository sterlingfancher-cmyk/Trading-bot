"""Immutable models for a future read-only shadow decision engine.

The module defines data contracts only. It does not import the trading runtime,
read provider data, mutate portfolio state, or expose order-placement methods.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class DecisionEffect(str, Enum):
    ALLOW = "allow"
    HARD_BLOCK = "hard_block"
    SIZE_REDUCTION = "size_reduction"
    SCORE_ADJUSTMENT = "score_adjustment"
    RANKING_PREFERENCE = "ranking_preference"
    TELEMETRY_ONLY = "telemetry_only"


@dataclass(frozen=True, slots=True)
class SignalSnapshot:
    symbol: str
    side: Side
    score: float
    rank_score: float
    price: float
    sector: str = ""
    strategy_bucket: str = ""
    confirmations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    mode: str
    risk_score: float
    market_open: bool
    breadth_score: float | None = None
    volatility_fraction: float | None = None


@dataclass(frozen=True, slots=True)
class RiskSnapshot:
    halted: bool
    self_defense_active: bool
    daily_loss_fraction: float
    intraday_drawdown_fraction: float
    realized_loss_fraction: float
    portfolio_heat_fraction: float


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    symbol: str
    side: Side
    quantity: float
    market_value_fraction: float
    unrealized_return_fraction: float
    sector: str = ""
    strategy_bucket: str = ""


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    policy_id: str
    effect: DecisionEffect
    reason_code: str
    terminal: bool = False
    score_adjustment: float = 0.0
    size_multiplier: float = 1.0
    metadata: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    signal: SignalSnapshot
    policies: tuple[PolicyDecision, ...]
    final_score: float
    final_size_multiplier: float
    allowed: bool
    terminal_reason: str = ""


@dataclass(frozen=True, slots=True)
class CycleDecision:
    cycle_id: str
    generated_local: str
    market: MarketSnapshot
    risk: RiskSnapshot
    positions: tuple[PositionSnapshot, ...]
    candidates: tuple[CandidateDecision, ...]
    selected_symbols: tuple[str, ...]
    authority: str = "shadow_only"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
