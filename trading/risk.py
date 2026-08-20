"""Shadow-only deterministic risk lifecycle for Stable Paper Core v3 Stage C.

This module defines the future canonical daily-risk boundary. It consumes a
Stage B protected valuation snapshot and produces an immutable risk evaluation.
It performs no market-data fetches, state-file I/O, runtime registration, order
placement, or mutation of the legacy paper runtime.

Hard-risk semantics intentionally mirror the current app owner:
- absolute daily loss ceiling;
- intraday drawdown halt;
- hard realized-loss halt;
- same-day halt latching;
- normal fresh-day reset from the current protected valuation.

Threshold values are supplied explicitly by the caller. This module does not read
environment variables or become a second configuration owner.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping

from trading.state import RiskStateSnapshot
from trading.valuation import ValuationSnapshot

VERSION = "stable-paper-core-v3-stage-c-risk-2026-08-20-v1"
AUTHORITY = "shadow_only"


class RiskInvariantError(ValueError):
    """Raised when a deterministic risk transition cannot be evaluated safely."""


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise RiskInvariantError(f"{name} must be numeric")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise RiskInvariantError(f"{name} must be numeric") from exc
    if not isfinite(out):
        raise RiskInvariantError(f"{name} must be finite")
    return out


def _positive(value: Any, *, name: str) -> float:
    out = _finite(value, name=name)
    if out <= 0.0:
        raise RiskInvariantError(f"{name} must be positive")
    return out


def _risk_fraction(value: Any, *, name: str) -> float:
    out = _finite(value, name=name)
    if out <= 0.0 or out > 1.0:
        raise RiskInvariantError(f"{name} must be a fraction in (0, 1]")
    return out


@dataclass(frozen=True)
class RiskLimits:
    max_daily_loss_fraction: float
    max_intraday_drawdown_fraction: float
    hard_realized_loss_fraction: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_daily_loss_fraction",
            _risk_fraction(
                self.max_daily_loss_fraction, name="max_daily_loss_fraction"
            ),
        )
        object.__setattr__(
            self,
            "max_intraday_drawdown_fraction",
            _risk_fraction(
                self.max_intraday_drawdown_fraction,
                name="max_intraday_drawdown_fraction",
            ),
        )
        object.__setattr__(
            self,
            "hard_realized_loss_fraction",
            _risk_fraction(
                self.hard_realized_loss_fraction, name="hard_realized_loss_fraction"
            ),
        )


@dataclass(frozen=True)
class RiskEvaluation:
    state: RiskStateSnapshot
    day_pnl_fraction: float
    realized_loss_fraction: float
    daily_loss_triggered: bool
    intraday_drawdown_triggered: bool
    realized_loss_triggered: bool
    fresh_day: bool
    valuation_version: str
    authority: str = AUTHORITY
    version: str = VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "day_pnl_fraction", _finite(self.day_pnl_fraction, name="day_pnl_fraction")
        )
        realized = _finite(self.realized_loss_fraction, name="realized_loss_fraction")
        if realized < 0.0:
            raise RiskInvariantError("realized_loss_fraction cannot be negative")
        object.__setattr__(self, "realized_loss_fraction", realized)
        if self.authority != AUTHORITY:
            raise RiskInvariantError("Stage C risk evaluation must remain shadow-only")
        if not str(self.valuation_version or "").strip():
            raise RiskInvariantError("valuation_version is required")

    def to_dict(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "authority": self.authority,
                "version": self.version,
                "valuation_version": self.valuation_version,
                "fresh_day": self.fresh_day,
                "date": self.state.date,
                "day_start_equity": self.state.day_start_equity,
                "day_peak_equity": self.state.day_peak_equity,
                "day_pnl_fraction": self.day_pnl_fraction,
                "daily_loss_fraction": self.state.daily_loss_fraction,
                "intraday_drawdown_fraction": self.state.intraday_drawdown_fraction,
                "realized_loss_fraction": self.realized_loss_fraction,
                "halted": self.state.halted,
                "halt_reason": self.state.halt_reason,
                "daily_loss_triggered": self.daily_loss_triggered,
                "intraday_drawdown_triggered": self.intraday_drawdown_triggered,
                "realized_loss_triggered": self.realized_loss_triggered,
            }
        )


class ShadowRiskEngine:
    """Pure Stage C risk engine with no runtime mutation authority."""

    authority = AUTHORITY
    fetches_market_data = False
    reads_environment = False
    reads_state_file = False
    writes_state_file = False
    mutates_legacy_risk = False
    places_orders = False

    @classmethod
    def evaluate(
        cls,
        *,
        date: str,
        valuation: ValuationSnapshot,
        realized_today: float,
        limits: RiskLimits,
        previous: RiskStateSnapshot | None = None,
    ) -> RiskEvaluation:
        risk_date = str(date or "").strip()
        if not risk_date:
            raise RiskInvariantError("risk date is required")
        if not isinstance(valuation, ValuationSnapshot):
            raise RiskInvariantError("valuation must be a Stage B ValuationSnapshot")
        if not valuation.risk_baseline_eligible:
            raise RiskInvariantError("valuation is not eligible to seed risk state")

        equity = _positive(valuation.equity, name="protected equity")
        realized = _finite(realized_today, name="realized_today")
        fresh_day = previous is None or previous.date != risk_date

        if fresh_day:
            start = equity
            old_peak = equity
            prior_halted = False
            prior_reason = ""
        else:
            start = _positive(previous.day_start_equity, name="day_start_equity")
            old_peak = _positive(previous.day_peak_equity, name="day_peak_equity")
            prior_halted = bool(previous.halted)
            prior_reason = str(previous.halt_reason or "")

        peak = max(old_peak, equity)
        day_pnl = (equity - start) / start
        daily_loss = max(0.0, (start - equity) / start)
        intraday_drawdown = max(0.0, (peak - equity) / peak)
        realized_loss = max(0.0, -realized / start)

        daily_triggered = daily_loss >= limits.max_daily_loss_fraction
        intraday_triggered = (
            intraday_drawdown >= limits.max_intraday_drawdown_fraction
        )
        realized_triggered = realized_loss >= limits.hard_realized_loss_fraction

        halted = False
        halt_reason = ""
        if daily_triggered:
            halted = True
            halt_reason = (
                "daily loss limit hit "
                f"({limits.max_daily_loss_fraction * 100:.1f}%)"
            )
        elif intraday_triggered:
            halted = True
            halt_reason = (
                "intraday drawdown limit hit "
                f"({limits.max_intraday_drawdown_fraction * 100:.1f}%)"
            )
        elif realized_triggered:
            halted = True
            halt_reason = (
                "self-defense hard realized loss hit "
                f"({limits.hard_realized_loss_fraction * 100:.2f}%)"
            )
        elif not fresh_day and prior_halted:
            halted = True
            halt_reason = prior_reason

        state = RiskStateSnapshot(
            date=risk_date,
            day_start_equity=start,
            day_peak_equity=peak,
            daily_loss_fraction=daily_loss,
            intraday_drawdown_fraction=intraday_drawdown,
            halted=halted,
            halt_reason=halt_reason,
        )
        return RiskEvaluation(
            state=state,
            day_pnl_fraction=day_pnl,
            realized_loss_fraction=realized_loss,
            daily_loss_triggered=daily_triggered,
            intraday_drawdown_triggered=intraday_triggered,
            realized_loss_triggered=realized_triggered,
            fresh_day=fresh_day,
            valuation_version=valuation.version,
        )

    @classmethod
    def compare_legacy(
        cls,
        *,
        evaluation: RiskEvaluation,
        legacy: Mapping[str, Any],
        tolerance: float = 1e-9,
    ) -> Mapping[str, Any]:
        """Compare canonical fields against legacy percentage-point telemetry."""
        tol = _finite(tolerance, name="tolerance")
        if tol < 0.0:
            raise RiskInvariantError("tolerance cannot be negative")

        def legacy_number(name: str, *, percentage_points: bool = False) -> float:
            value = _finite(legacy.get(name), name=f"legacy.{name}")
            return value / 100.0 if percentage_points else value

        checks = {
            "day_start_equity": abs(
                evaluation.state.day_start_equity - legacy_number("day_start_equity")
            )
            <= tol,
            "day_peak_equity": abs(
                evaluation.state.day_peak_equity - legacy_number("day_peak_equity")
            )
            <= tol,
            "daily_loss_fraction": abs(
                evaluation.state.daily_loss_fraction
                - legacy_number("daily_loss_pct", percentage_points=True)
            )
            <= tol,
            "intraday_drawdown_fraction": abs(
                evaluation.state.intraday_drawdown_fraction
                - legacy_number("intraday_drawdown_pct", percentage_points=True)
            )
            <= tol,
            "halted": evaluation.state.halted == bool(legacy.get("halted")),
            "halt_reason": evaluation.state.halt_reason
            == str(legacy.get("halt_reason") or ""),
        }
        return MappingProxyType(
            {
                "authority": AUTHORITY,
                "overall": "pass" if all(checks.values()) else "fail",
                "checks": MappingProxyType(checks),
            }
        )

    @classmethod
    def descriptor(cls) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "target_interface": "trading.risk.ShadowRiskEngine",
                "authority": cls.authority,
                "fetches_market_data": cls.fetches_market_data,
                "reads_environment": cls.reads_environment,
                "reads_state_file": cls.reads_state_file,
                "writes_state_file": cls.writes_state_file,
                "mutates_legacy_risk": cls.mutates_legacy_risk,
                "places_orders": cls.places_orders,
                "version": VERSION,
            }
        )
