"""Telemetry-only runtime adapter for Stage D shadow capture.

The adapter receives already-computed inputs and outputs from ``app.run_cycle``.
It does not import the trading runtime, call providers, replace callables, register
routes, write files, mutate portfolio state, or place orders.

V1 is intentionally a capture-parity baseline. It proves immutable translation
and comparison plumbing before any independent shadow policy is introduced.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from shadow_decision_comparison import compare_cycles
from shadow_decision_models import (
    CandidateDecision,
    CycleDecision,
    DecisionEffect,
    MarketSnapshot,
    PolicyDecision,
    PositionSnapshot,
    RiskSnapshot,
    Side,
    SignalSnapshot,
)

VERSION = "runtime-shadow-capture-2026-08-03-v1-parity-baseline"
MODE = "capture_parity_baseline"
DEFAULT_HISTORY_LIMIT = 30


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _symbol(row: Any) -> str:
    if isinstance(row, str):
        return row.strip().upper()
    if isinstance(row, Mapping):
        value = row.get("symbol") or row.get("ticker") or row.get("asset") or row.get("in")
        return str(value).strip().upper() if value else ""
    return ""


def _side(value: Any, fallback: Side) -> Side:
    text = str(value or "").strip().lower()
    if text in {"short", "sell", "bear", "bearish"}:
        return Side.SHORT
    if text in {"long", "buy", "bull", "bullish"}:
        return Side.LONG
    return fallback


def _first_float(row: Mapping[str, Any], keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        if row.get(key) is not None:
            return _float(row.get(key), default)
    return default


def _reason(row: Any, fallback: str = "") -> str:
    if not isinstance(row, Mapping):
        return fallback
    for key in (
        "reason",
        "entry_block_reason",
        "block_reason",
        "reject_reason",
        "terminal_reason",
        "status",
    ):
        if row.get(key) not in (None, ""):
            return str(row.get(key))
    for key in ("quality_info", "rotation_info", "entry_fallback"):
        nested = row.get(key)
        if isinstance(nested, Mapping):
            value = nested.get("reason") or nested.get("status")
            if value not in (None, ""):
                return str(value)
    return fallback


def _sector(row: Mapping[str, Any]) -> str:
    return str(row.get("sector") or "").strip().upper()


def _bucket(row: Mapping[str, Any]) -> str:
    return str(
        row.get("strategy_bucket")
        or row.get("bucket")
        or row.get("trade_class")
        or ""
    ).strip()


def _confirmations(row: Mapping[str, Any]) -> tuple[str, ...]:
    raw = row.get("confirmations") or row.get("confirmation") or ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, (list, tuple, set)):
        return tuple(str(item) for item in raw if item not in (None, ""))
    return ()


def _key(symbol: str, side: Side) -> tuple[str, str]:
    return symbol.upper(), side.value


def _signals(
    long_signals: Iterable[Any],
    short_signals: Iterable[Any],
    *extra_groups: Iterable[Any],
) -> tuple[SignalSnapshot, ...]:
    output: dict[tuple[str, str], SignalSnapshot] = {}
    groups = [(Side.LONG, long_signals), (Side.SHORT, short_signals)]
    groups.extend((Side.LONG, rows) for rows in extra_groups)
    for fallback_side, rows in groups:
        for raw in rows:
            symbol = _symbol(raw)
            if not symbol:
                continue
            row = raw if isinstance(raw, Mapping) else {"symbol": symbol}
            side = _side(row.get("side") or row.get("direction"), fallback_side)
            score = _first_float(row, ("final_score", "score", "signal_score"), 0.0)
            snapshot = SignalSnapshot(
                symbol=symbol,
                side=side,
                score=score,
                rank_score=_first_float(row, ("rank_score", "final_score", "score"), score),
                price=_first_float(row, ("price", "entry_price", "last_price", "close"), 0.0),
                sector=_sector(row),
                strategy_bucket=_bucket(row),
                confirmations=_confirmations(row),
            )
            key = _key(symbol, side)
            existing = output.get(key)
            if existing is None or abs(snapshot.score) >= abs(existing.score):
                output[key] = snapshot
    return tuple(output[key] for key in sorted(output))


def _index(
    rows: Iterable[Any],
    signal_sides: Mapping[str, Side],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    output: dict[tuple[str, str], Mapping[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        symbol = _symbol(raw)
        if not symbol:
            continue
        side = _side(
            raw.get("side") or raw.get("direction"),
            signal_sides.get(symbol, Side.LONG),
        )
        output[_key(symbol, side)] = raw
    return output


def _positions(positions: Mapping[str, Any], equity: float) -> tuple[PositionSnapshot, ...]:
    output: list[PositionSnapshot] = []
    safe_equity = max(_float(equity), 0.01)
    for symbol, raw in sorted(positions.items()):
        row = raw if isinstance(raw, Mapping) else {}
        side = _side(row.get("side"), Side.LONG)
        quantity = _first_float(row, ("qty", "quantity", "shares"), 0.0)
        price = _first_float(row, ("last_price", "price", "entry"), 0.0)
        entry = _first_float(row, ("entry", "entry_price"), 0.0)
        value = _first_float(row, ("market_value",), abs(quantity) * max(price, 0.0))
        if row.get("unrealized_return_fraction") is not None:
            unrealized = _float(row.get("unrealized_return_fraction"))
        elif entry > 0 and price > 0:
            move = (price - entry) / entry
            unrealized = move if side is Side.LONG else -move
        else:
            unrealized = 0.0
        output.append(
            PositionSnapshot(
                symbol=str(symbol).upper(),
                side=side,
                quantity=quantity,
                market_value_fraction=max(0.0, value / safe_equity),
                unrealized_return_fraction=unrealized,
                sector=_sector(row),
                strategy_bucket=_bucket(row),
            )
        )
    return tuple(output)


def _market(market: Mapping[str, Any], market_open: bool) -> MarketSnapshot:
    breadth = _dict(market.get("breadth"))
    breadth_raw = breadth.get("score", market.get("breadth_score"))
    volatility = market.get("volatility_fraction", market.get("vix_fraction"))
    return MarketSnapshot(
        mode=str(market.get("market_mode") or market.get("regime") or "unknown"),
        risk_score=_float(market.get("risk_score")),
        market_open=bool(market_open),
        breadth_score=None if breadth_raw is None else _float(breadth_raw),
        volatility_fraction=None if volatility is None else _float(volatility),
    )


def _risk(risk: Mapping[str, Any]) -> RiskSnapshot:
    return RiskSnapshot(
        halted=bool(risk.get("halted")),
        self_defense_active=bool(risk.get("self_defense_active")),
        daily_loss_fraction=_float(
            risk.get("daily_loss_fraction"),
            _float(risk.get("daily_loss_pct")) / 100.0,
        ),
        intraday_drawdown_fraction=_float(
            risk.get("intraday_drawdown_fraction"),
            _float(risk.get("intraday_drawdown_pct")) / 100.0,
        ),
        realized_loss_fraction=_float(
            risk.get("realized_loss_fraction"),
            _float(risk.get("realized_loss_pct")) / 100.0,
        ),
        portfolio_heat_fraction=_float(risk.get("portfolio_heat_fraction")),
    )


def _decisions(
    signals: tuple[SignalSnapshot, ...],
    *,
    entries: Iterable[Any],
    blocked_entries: Iterable[Any],
    rejected_signals: Iterable[Any],
    new_entries_allowed: bool,
    entry_block_reason: str | None,
) -> tuple[tuple[CandidateDecision, ...], tuple[str, ...]]:
    signal_sides = {signal.symbol.upper(): signal.side for signal in signals}
    entered = _index(entries, signal_sides)
    blocked = _index(blocked_entries, signal_sides)
    rejected = _index(rejected_signals, signal_sides)
    decisions: list[CandidateDecision] = []
    selected: set[str] = set()

    for signal in signals:
        key = _key(signal.symbol, signal.side)
        source: Mapping[str, Any] = {}
        if key in entered:
            source = entered[key]
            allowed, terminal = True, ""
            effect, reason_code = DecisionEffect.ALLOW, "selected_by_current_engine"
            selected.add(signal.symbol.upper())
        elif key in blocked:
            source = blocked[key]
            terminal = _reason(source, entry_block_reason or "blocked")
            allowed, effect, reason_code = False, DecisionEffect.HARD_BLOCK, terminal
        elif key in rejected:
            source = rejected[key]
            terminal = _reason(source, "rejected")
            allowed, effect, reason_code = False, DecisionEffect.HARD_BLOCK, terminal
        elif not new_entries_allowed:
            terminal = entry_block_reason or "cycle_entry_block"
            allowed, effect, reason_code = False, DecisionEffect.HARD_BLOCK, terminal
        else:
            allowed, terminal = True, ""
            effect, reason_code = DecisionEffect.TELEMETRY_ONLY, "eligible_not_selected"

        final_score = _first_float(source, ("final_score", "rank_score", "score"), signal.score)
        size = max(
            0.0,
            _first_float(source, ("final_size_multiplier", "size_multiplier", "alloc_factor"), 1.0),
        )
        decisions.append(
            CandidateDecision(
                signal=signal,
                policies=(
                    PolicyDecision(
                        policy_id="observed_current_engine",
                        effect=effect,
                        reason_code=reason_code,
                        terminal=not allowed,
                        score_adjustment=final_score - signal.score,
                        size_multiplier=size,
                    ),
                ),
                final_score=final_score,
                final_size_multiplier=size,
                allowed=allowed,
                terminal_reason=terminal,
            )
        )
    return tuple(decisions), tuple(sorted(selected))


def capture_cycle(
    *,
    cycle_id: str,
    generated_local: str,
    market: Mapping[str, Any],
    risk: Mapping[str, Any],
    positions: Mapping[str, Any],
    equity: float,
    long_signals: Iterable[Any],
    short_signals: Iterable[Any],
    entries: Iterable[Any],
    blocked_entries: Iterable[Any],
    rejected_signals: Iterable[Any],
    new_entries_allowed: bool,
    entry_block_reason: str | None,
    market_open: bool,
) -> dict[str, Any]:
    signals = _signals(
        long_signals,
        short_signals,
        entries,
        blocked_entries,
        rejected_signals,
    )
    candidates, selected = _decisions(
        signals,
        entries=entries,
        blocked_entries=blocked_entries,
        rejected_signals=rejected_signals,
        new_entries_allowed=new_entries_allowed,
        entry_block_reason=entry_block_reason,
    )
    current = CycleDecision(
        cycle_id=str(cycle_id),
        generated_local=str(generated_local),
        market=_market(market, market_open),
        risk=_risk(risk),
        positions=_positions(positions, equity),
        candidates=candidates,
        selected_symbols=selected,
        authority="paper_current_observed",
    )
    shadow = CycleDecision(
        cycle_id=current.cycle_id,
        generated_local=current.generated_local,
        market=current.market,
        risk=current.risk,
        positions=current.positions,
        candidates=current.candidates,
        selected_symbols=current.selected_symbols,
        authority="shadow_capture_baseline",
    )
    comparison = compare_cycles(current, shadow)
    selected_set = set(selected)
    return {
        "status": "pass" if comparison.parity else "warn",
        "overall": "pass" if comparison.parity else "warn",
        "type": "runtime_shadow_capture",
        "version": VERSION,
        "mode": MODE,
        "cycle_id": current.cycle_id,
        "generated_local": current.generated_local,
        "input_fingerprint": comparison.input_fingerprint,
        "parity": comparison.parity,
        "candidate_count": len(candidates),
        "eligible_candidate_count": sum(candidate.allowed for candidate in candidates),
        "blocked_candidate_count": sum(not candidate.allowed for candidate in candidates),
        "selected_symbols": list(selected),
        "divergence_counts": dict(comparison.divergence_counts),
        "current_authority": comparison.current_authority,
        "shadow_authority": comparison.shadow_authority,
        "comparison_authority": comparison.authority,
        "independent_policy_active": False,
        "forward_evidence_eligible": False,
        "candidate_sample": [
            {
                "symbol": candidate.signal.symbol,
                "side": candidate.signal.side.value,
                "allowed": candidate.allowed,
                "selected": candidate.signal.symbol.upper() in selected_set,
                "terminal_reason": candidate.terminal_reason,
                "final_score": candidate.final_score,
                "final_size_multiplier": candidate.final_size_multiplier,
            }
            for candidate in candidates[:12]
        ],
        "authority": {
            "observer_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "replaces_callables": False,
            "registers_routes": False,
            "reads_or_writes_files": False,
            "places_orders": False,
            "automatic_promotion": False,
        },
    }


def failure_record(*, cycle_id: str, generated_local: str, error: Exception) -> dict[str, Any]:
    return {
        "status": "warn",
        "overall": "warn",
        "type": "runtime_shadow_capture",
        "version": VERSION,
        "mode": MODE,
        "cycle_id": str(cycle_id),
        "generated_local": str(generated_local),
        "parity": None,
        "independent_policy_active": False,
        "forward_evidence_eligible": False,
        "error": f"{type(error).__name__}: {error}",
        "authority": {
            "observer_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "replaces_callables": False,
            "registers_routes": False,
            "reads_or_writes_files": False,
            "places_orders": False,
            "automatic_promotion": False,
        },
    }


def append_bounded(
    existing: Any,
    report: Mapping[str, Any],
    *,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    """Return bounded telemetry; the caller remains the state owner."""
    previous = _dict(existing)
    row = dict(report)
    if _dict(previous.get("latest")).get("cycle_id") == row.get("cycle_id"):
        return previous

    history = [dict(item) for item in _rows(previous.get("history")) if isinstance(item, Mapping)]
    history.append(
        {
            key: row.get(key)
            for key in (
                "status",
                "cycle_id",
                "generated_local",
                "input_fingerprint",
                "parity",
                "candidate_count",
                "eligible_candidate_count",
                "blocked_candidate_count",
                "selected_symbols",
                "divergence_counts",
            )
        }
    )
    limit = max(1, int(history_limit))
    history = history[-limit:]
    return {
        "status": "pass" if row.get("status") == "pass" else "warn",
        "overall": "pass" if row.get("status") == "pass" else "warn",
        "type": "runtime_shadow_capture_state",
        "version": VERSION,
        "mode": MODE,
        "latest": row,
        "history": history,
        "history_limit": limit,
        "history_count": len(history),
        "total_cycles": int(previous.get("total_cycles") or 0) + 1,
        "total_candidates": int(previous.get("total_candidates") or 0)
        + int(row.get("candidate_count") or 0),
        "parity_cycles": int(previous.get("parity_cycles") or 0) + int(row.get("parity") is True),
        "warning_cycles": int(previous.get("warning_cycles") or 0)
        + int(row.get("status") != "pass"),
        "independent_policy_active": False,
        "forward_evidence": {
            "eligible": False,
            "reason": "capture_parity_baseline_only",
            "minimum_forward_candidates": 30,
            "minimum_one_day_outcomes": 20,
            "observed_forward_candidates": 0,
            "observed_one_day_outcomes": 0,
        },
        "authority": row.get("authority", {}),
    }


def status_payload(portfolio: Any) -> dict[str, Any]:
    capture = _dict(_dict(portfolio).get("shadow_decision_comparison"))
    latest = _dict(capture.get("latest"))
    if not capture:
        return {
            "status": "ok",
            "overall": "pass",
            "type": "runtime_shadow_capture_status",
            "version": VERSION,
            "mode": MODE,
            "capture_state": "awaiting_first_market_cycle",
            "independent_policy_active": False,
            "forward_evidence_eligible": False,
            "authority": {
                "observer_only": True,
                "places_orders": False,
                "replaces_callables": False,
                "registers_routes": False,
            },
        }
    healthy = latest.get("status") == "pass" and latest.get("parity") is True
    return {
        "status": "ok" if healthy else "warn",
        "overall": "pass" if healthy else "warn",
        "type": "runtime_shadow_capture_status",
        "version": VERSION,
        "mode": capture.get("mode", MODE),
        "capture_state": "captured" if latest else "awaiting_first_market_cycle",
        "latest_cycle_id": latest.get("cycle_id"),
        "latest_generated_local": latest.get("generated_local"),
        "latest_parity": latest.get("parity"),
        "latest_candidate_count": latest.get("candidate_count"),
        "latest_selected_symbols": latest.get("selected_symbols"),
        "latest_divergence_counts": latest.get("divergence_counts"),
        "history_count": capture.get("history_count"),
        "total_cycles": capture.get("total_cycles"),
        "total_candidates": capture.get("total_candidates"),
        "parity_cycles": capture.get("parity_cycles"),
        "warning_cycles": capture.get("warning_cycles"),
        "independent_policy_active": False,
        "forward_evidence": capture.get("forward_evidence"),
        "authority": latest.get("authority") or capture.get("authority") or {},
    }
