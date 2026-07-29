"""Staged paper-trading risk ladder and plateau diagnostics.

Replaces the legacy 1% permanent self-defense halt with:
- 1.00% realized loss: controlled restart mode
- 2.50% realized loss or intraday drawdown: hard halt
- 3.00% daily equity loss: absolute ceiling

Controlled restart permits only high-score, half-sized long entries in confirmed
risk-on/constructive conditions, with no rotations and a bounded daily count.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, Iterable, List

VERSION = "performance-risk-calibration-2026-07-29-v1"

SOFT_REALIZED = float(os.environ.get("CALIBRATION_SOFT_REALIZED_LOSS_PCT", "0.010"))
HARD_REALIZED = float(os.environ.get("CALIBRATION_HARD_REALIZED_LOSS_PCT", "0.025"))
HARD_INTRADAY = float(os.environ.get("CALIBRATION_HARD_INTRADAY_DRAWDOWN_PCT", "0.025"))
ABSOLUTE_DAILY = float(os.environ.get("CALIBRATION_ABSOLUTE_DAILY_LOSS_PCT", "0.030"))
RESTART_ALLOC_FACTOR = float(os.environ.get("CONTROLLED_RESTART_ALLOC_FACTOR", "0.50"))
RESTART_SCORE_BUMP = float(os.environ.get("CONTROLLED_RESTART_SCORE_BUMP", "0.006"))
RESTART_MAX_ENTRIES = max(1, int(os.environ.get("CONTROLLED_RESTART_MAX_ENTRIES_PER_DAY", "2")))
RESTART_MODES = {
    x.strip() for x in os.environ.get("CONTROLLED_RESTART_MARKET_MODES", "risk_on,constructive").split(",") if x.strip()
}
STARTING_EQUITY = float(os.environ.get("PAPER_STARTING_EQUITY", "10000"))

_PATCHED: set[int] = set()
_REGISTERED: set[int] = set()


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "portfolio"):
            return mod
    return None


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return default if math.isnan(number) or math.isinf(number) else number
    except Exception:
        return default


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    try:
        return str(core.today_key())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _portfolio(core: Any) -> Dict[str, Any]:
    return _dict(getattr(core, "portfolio", {}))


def _realized_today(core: Any, state: Dict[str, Any]) -> float:
    try:
        row = core.get_realized_pnl()
        if isinstance(row, dict):
            return _f(row.get("today"))
    except Exception:
        pass
    return _f(_dict(state.get("performance")).get("realized_pnl_today"))


def _metrics(core: Any, risk: Dict[str, Any] | None = None) -> Dict[str, float]:
    state = _portfolio(core)
    risk = risk if isinstance(risk, dict) else _dict(state.get("risk_controls"))
    equity = max(_f(state.get("equity"), _f(state.get("cash"), STARTING_EQUITY)), 0.01)
    start = max(_f(risk.get("day_start_equity"), equity), 0.01)
    peak = max(_f(risk.get("day_peak_equity"), equity), equity, 0.01)
    realized = _realized_today(core, state)
    return {
        "equity": equity,
        "day_start_equity": start,
        "day_peak_equity": peak,
        "realized_today": realized,
        "daily_loss_fraction": max(0.0, (start - equity) / start),
        "intraday_drawdown_fraction": max(0.0, (peak - equity) / peak),
        "realized_loss_fraction": max(0.0, -realized / start),
    }


def _restart_state(core: Any) -> Dict[str, Any]:
    section = _portfolio(core).setdefault("performance_risk_calibration", {})
    today = _today(core)
    if section.get("restart_date") != today:
        section["restart_date"] = today
        section["controlled_restart_entries_used"] = 0
        section["controlled_restart_attempts"] = 0
    section.setdefault("controlled_restart_entries_used", 0)
    section.setdefault("controlled_restart_attempts", 0)
    return section


def _managed_halt(reason: Any) -> bool:
    text = str(reason or "").lower()
    return text.startswith("self-defense hard") or text.startswith("performance risk hard")


def _decorate_risk(core: Any, risk: Dict[str, Any]) -> Dict[str, Any]:
    m = _metrics(core, risk)
    daily = m["daily_loss_fraction"]
    intraday = m["intraday_drawdown_fraction"]
    realized = m["realized_loss_fraction"]

    risk["daily_loss_fraction"] = round(daily, 6)
    risk["intraday_drawdown_fraction"] = round(intraday, 6)
    risk["realized_loss_fraction"] = round(realized, 6)
    risk["daily_loss_pct"] = round(daily * 100.0, 3)
    risk["daily_drawdown_pct"] = round(daily * 100.0, 3)
    risk["intraday_drawdown_pct"] = round(intraday * 100.0, 3)
    risk["realized_loss_pct"] = round(realized * 100.0, 3)

    hard_reason = None
    if daily >= ABSOLUTE_DAILY:
        hard_reason = f"absolute daily equity loss halt ({ABSOLUTE_DAILY * 100:.2f}%)"
    elif intraday >= HARD_INTRADAY:
        hard_reason = f"performance risk hard intraday drawdown halt ({HARD_INTRADAY * 100:.2f}%)"
    elif realized >= HARD_REALIZED:
        hard_reason = f"performance risk hard realized loss halt ({HARD_REALIZED * 100:.2f}%)"

    if hard_reason:
        risk["halted"] = True
        risk["halt_reason"] = hard_reason
    elif bool(risk.get("halted")) and _managed_halt(risk.get("halt_reason")):
        risk["halted"] = False
        risk["halt_reason"] = ""

    restart = _restart_state(core)
    risk["risk_ladder"] = {
        "version": VERSION,
        "units": {"fraction": "0.01 equals 1%", "pct": "1.0 equals 1%"},
        "soft_realized_loss_fraction": SOFT_REALIZED,
        "soft_realized_loss_pct": round(SOFT_REALIZED * 100.0, 3),
        "hard_realized_loss_fraction": HARD_REALIZED,
        "hard_realized_loss_pct": round(HARD_REALIZED * 100.0, 3),
        "hard_intraday_drawdown_fraction": HARD_INTRADAY,
        "hard_intraday_drawdown_pct": round(HARD_INTRADAY * 100.0, 3),
        "absolute_daily_loss_fraction": ABSOLUTE_DAILY,
        "absolute_daily_loss_pct": round(ABSOLUTE_DAILY * 100.0, 3),
        "controlled_restart_alloc_factor": RESTART_ALLOC_FACTOR,
        "controlled_restart_score_bump": RESTART_SCORE_BUMP,
        "controlled_restart_max_entries_per_day": RESTART_MAX_ENTRIES,
        "controlled_restart_entries_used": int(restart.get("controlled_restart_entries_used") or 0),
    }
    return risk


def _base_score(core: Any, market: Dict[str, Any]) -> float:
    try:
        return _f(core.min_entry_score_for_market(market, "long"))
    except Exception:
        mode = str(market.get("market_mode") or "neutral")
        field = {
            "risk_on": "MIN_ENTRY_SCORE_RISK_ON",
            "constructive": "MIN_ENTRY_SCORE_CONSTRUCTIVE",
            "neutral": "MIN_ENTRY_SCORE_NEUTRAL",
        }.get(mode, "MIN_ENTRY_SCORE_DEFENSIVE")
        return _f(getattr(core, field, 0.0))


def _restart_payload(core: Any, market: Dict[str, Any], clock: Dict[str, Any], risk: Dict[str, Any], feedback: Dict[str, Any]) -> Dict[str, Any]:
    m = _metrics(core, risk)
    section = _restart_state(core)
    used = int(section.get("controlled_restart_entries_used") or 0)
    stop_limit = int(getattr(core, "SELF_DEFENSE_STOP_LOSS_LIMIT", 2) or 2)
    stops = int(feedback.get("stop_losses_today") or 0)
    soft_realized = m["realized_loss_fraction"] >= SOFT_REALIZED
    soft_stops = stops >= stop_limit
    soft = soft_realized or soft_stops
    hard = bool(
        m["realized_loss_fraction"] >= HARD_REALIZED
        or m["intraday_drawdown_fraction"] >= HARD_INTRADAY
        or m["daily_loss_fraction"] >= ABSOLUTE_DAILY
        or risk.get("halted")
    )
    mode = str(market.get("market_mode") or "neutral")
    late = bool(feedback.get("late_day_entry_cutoff"))
    active = bool(
        soft and not hard and bool(clock.get("is_open")) and not late
        and mode in RESTART_MODES and used < RESTART_MAX_ENTRIES
        and not risk.get("profit_guard_active")
    )
    return {
        "active": active,
        "soft_pause_active": bool(soft),
        "hard_halt_active": hard,
        "realized_soft_triggered": soft_realized,
        "loss_streak_soft_triggered": soft_stops,
        "market_mode": mode,
        "market_eligible": mode in RESTART_MODES,
        "market_open": bool(clock.get("is_open")),
        "late_day_block": late,
        "profit_guard_block": bool(risk.get("profit_guard_active")),
        "required_long_score": round(_base_score(core, market) + RESTART_SCORE_BUMP, 6),
        "score_bump": RESTART_SCORE_BUMP,
        "alloc_factor": RESTART_ALLOC_FACTOR,
        "max_entries_per_day": RESTART_MAX_ENTRIES,
        "entries_used": used,
        "entries_remaining": max(0, RESTART_MAX_ENTRIES - used),
        "allow_rotations": False,
        "allowed_market_modes": sorted(RESTART_MODES),
    }


def _rewrite_feedback(core: Any, feedback: Dict[str, Any], market: Dict[str, Any], clock: Dict[str, Any], risk: Dict[str, Any], persist: bool) -> Dict[str, Any]:
    _decorate_risk(core, risk)
    restart = _restart_payload(core, market, clock, risk, feedback)
    m = _metrics(core, risk)
    stops = int(feedback.get("stop_losses_today") or 0)
    reasons: List[str] = []
    actions: List[str] = []

    if restart["loss_streak_soft_triggered"]:
        reasons.append(f"{stops} stop-loss exits triggered controlled restart restrictions")
        actions.append("controlled_restart_after_loss_streak")
    if restart["realized_soft_triggered"]:
        reasons.append(
            f"realized daily loss {m['realized_loss_fraction'] * 100:.2f}% reached "
            f"{SOFT_REALIZED * 100:.2f}% soft pause"
        )
        actions.append("controlled_restart_after_soft_loss")
    if restart["hard_halt_active"]:
        reasons.append(str(risk.get("halt_reason") or "hard risk halt active"))
        actions.append("hard_halt_new_entries")
    if restart["late_day_block"]:
        reasons.append(f"inside final {int(getattr(core, 'LATE_DAY_ENTRY_CUTOFF_MINUTES', 30))} minutes before close")
        actions.append("late_day_manage_only")

    if restart["soft_pause_active"] and not restart["active"] and not restart["hard_halt_active"] and not restart["late_day_block"]:
        if not restart["market_open"]:
            reasons.append("controlled restart waits for the regular session")
        elif not restart["market_eligible"]:
            reasons.append(f"controlled restart is unavailable in {restart['market_mode']} mode")
        elif restart["profit_guard_block"]:
            reasons.append("profit guard blocks controlled restart")
        elif restart["entries_remaining"] <= 0:
            reasons.append("controlled restart daily entry allowance exhausted")
        actions.append("remain_manage_only_until_restart_eligible")

    if restart["active"]:
        reasons.append(
            f"controlled restart active: score >= {restart['required_long_score']:.4f}, "
            f"{restart['alloc_factor']:.0%} size, no rotations"
        )
        actions.extend(("allow_one_high_quality_long_candidate", "reduce_restart_position_size", "disable_rotations_during_restart"))

    for action in _list(feedback.get("actions")):
        text = str(action)
        if text.startswith(("futures_bias_", "breadth_", "precious_metals_", "raise_score_floor_", "reduce_aggression_")):
            actions.append(text)
    if not reasons:
        reasons.append("performance risk calibration clear")

    block = bool(restart["hard_halt_active"] or restart["late_day_block"] or (restart["soft_pause_active"] and not restart["active"]))
    feedback.update({
        "version": VERSION,
        "self_defense_mode": bool(restart["soft_pause_active"] or restart["hard_halt_active"]),
        "block_new_entries": block,
        "hard_halt": bool(restart["hard_halt_active"]),
        "reasons": list(dict.fromkeys(reasons)),
        "actions": list(dict.fromkeys(actions)),
        "realized_pnl_today": round(m["realized_today"], 2),
        "realized_loss_fraction": round(m["realized_loss_fraction"], 6),
        "realized_loss_pct": round(m["realized_loss_fraction"] * 100.0, 3),
        "controlled_restart": restart,
        "risk_ladder": risk.get("risk_ladder", {}),
    })
    if persist:
        state = _portfolio(core)
        state["feedback_loop"] = feedback
        risk["self_defense_active"] = bool(feedback["self_defense_mode"])
        risk["self_defense_reason"] = "; ".join(feedback["reasons"])
        section = _restart_state(core)
        section.update({
            "version": VERSION,
            "updated_local": _now(core),
            "risk_metrics": m,
            "controlled_restart": restart,
            "authority": {"paper_only": True, "changes_live_authority": False, "changes_ml_authority": False},
        })
    return feedback


def _exit_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in _list(state.get("trades")):
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or row.get("type") or "").lower()
        if action in {"exit", "sell", "close", "cover"} or row.get("pnl_dollars") is not None or row.get("realized_pnl") is not None:
            out.append(row)
    return out


def _pnl(row: Dict[str, Any]) -> float:
    if row.get("pnl_dollars") is not None:
        return _f(row.get("pnl_dollars"))
    if row.get("realized_pnl") is not None:
        return _f(row.get("realized_pnl"))
    return _f(row.get("pnl"))


def _stats(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    values = [_pnl(row) for row in rows]
    wins = [x for x in values if x > 0]
    losses = [x for x in values if x < 0]
    gp = sum(wins)
    gl = sum(losses)
    count = len(values)
    avg_win = gp / len(wins) if wins else None
    avg_loss = gl / len(losses) if losses else None
    pf = gp / abs(gl) if gl < 0 else (999.0 if gp > 0 else None)
    payoff = avg_win / abs(avg_loss) if avg_win is not None and avg_loss not in (None, 0.0) else None
    return {
        "closed_exits": count,
        "wins": len(wins),
        "losses": len(losses),
        "flats": count - len(wins) - len(losses),
        "win_rate": round(len(wins) / count, 4) if count else None,
        "gross_profit": round(gp, 2),
        "gross_loss": round(gl, 2),
        "net_pnl": round(sum(values), 2),
        "profit_factor": round(pf, 4) if pf is not None else None,
        "avg_winner": round(avg_win, 2) if avg_win is not None else None,
        "avg_loser": round(avg_loss, 2) if avg_loss is not None else None,
        "payoff_ratio": round(payoff, 4) if payoff is not None else None,
        "expectancy_per_exit": round(sum(values) / count, 2) if count else None,
    }


def _strategy_section(core: Any, state: Dict[str, Any]) -> Dict[str, Any]:
    stored = _dict(state.get("strategy_scorecard"))
    if stored.get("scorecards") or stored.get("strategy_id_scorecards"):
        return stored
    try:
        import strategy_scorecard
        return strategy_scorecard.build_scorecards(state, core)
    except Exception as exc:
        return {"last_error": f"{type(exc).__name__}: {exc}"}


def build_diagnostic(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    state = _portfolio(core)
    risk = _dict(state.get("risk_controls"))
    _decorate_risk(core, risk)
    exits = _exit_rows(state)
    lifetime = _stats(exits)
    recent = _stats(exits[-20:])
    equity = max(_f(state.get("equity"), _f(state.get("cash"), STARTING_EQUITY)), 0.01)
    cash = _f(state.get("cash"))
    start = max(_f(state.get("initial_equity"), _f(state.get("starting_equity"), STARTING_EQUITY)), 0.01)
    exposure = max(0.0, min(100.0, (equity - cash) / equity * 100.0))
    scanner = _dict(state.get("scanner_audit"))
    feedback = _dict(state.get("feedback_loop"))
    strategy = _strategy_section(core, state)
    cards = _list(strategy.get("strategy_id_scorecards") or strategy.get("scorecards"))

    positive = [c for c in cards if isinstance(c, dict) and int(c.get("exit_rows") or 0) >= 5 and _f(c.get("expectancy_per_exit")) > 0]
    negative = [c for c in cards if isinstance(c, dict) and int(c.get("exit_rows") or 0) >= 5 and _f(c.get("expectancy_per_exit")) < 0]
    positive.sort(key=lambda c: (_f(c.get("expectancy_per_exit")), _f(c.get("profit_factor"))), reverse=True)
    negative.sort(key=lambda c: (_f(c.get("expectancy_per_exit")), _f(c.get("net_pnl"))))

    drivers: List[Dict[str, Any]] = []
    if lifetime.get("win_rate") is not None and lifetime["win_rate"] >= 0.55 and lifetime.get("payoff_ratio") is not None and lifetime["payoff_ratio"] < 1.0:
        drivers.append({"driver": "payoff_imbalance", "severity": "high", "evidence": f"Win rate is {lifetime['win_rate'] * 100:.1f}% but payoff ratio is {lifetime['payoff_ratio']:.2f}."})
    if lifetime.get("profit_factor") is not None and lifetime["profit_factor"] < 1.25:
        drivers.append({"driver": "weak_profit_factor", "severity": "high", "evidence": f"Lifetime profit factor is {lifetime['profit_factor']:.2f}."})
    if recent.get("expectancy_per_exit") is not None and recent["expectancy_per_exit"] <= 0:
        drivers.append({"driver": "recent_negative_expectancy", "severity": "high", "evidence": f"Recent 20-exit expectancy is ${recent['expectancy_per_exit']:.2f}."})
    if exposure < 20 and int(scanner.get("signals_found") or 0) > 0:
        drivers.append({"driver": "underdeployment", "severity": "medium", "evidence": f"Exposure is {exposure:.1f}% with {int(scanner.get('signals_found') or 0)} scanner signals."})
    if negative:
        drivers.append({"driver": "negative_expectancy_strategies", "severity": "medium", "evidence": f"{len(negative)} strategy labels have negative expectancy with at least five exits."})

    last_result = _dict(_dict(state.get("auto_runner")).get("last_result"))
    controlled = _dict(feedback.get("controlled_restart"))
    return {
        "status": "ok",
        "overall": "warn" if drivers else "pass",
        "type": "performance_risk_calibration_status",
        "version": VERSION,
        "generated_local": _now(core),
        "account": {
            "cash": round(cash, 2), "equity": round(equity, 2),
            "starting_equity_reference": round(start, 2),
            "return_pct": round((equity - start) / start * 100.0, 2),
            "open_positions_count": len(_dict(state.get("positions"))),
            "exposure_pct": round(exposure, 2),
            "execution_rows": len(_list(state.get("trades"))),
        },
        "lifetime_performance": lifetime,
        "recent_20_exit_performance": recent,
        "risk": {
            "halted": bool(risk.get("halted")), "halt_reason": risk.get("halt_reason"),
            "daily_loss_fraction": risk.get("daily_loss_fraction"), "daily_loss_pct": risk.get("daily_loss_pct"),
            "intraday_drawdown_fraction": risk.get("intraday_drawdown_fraction"), "intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
            "realized_loss_fraction": risk.get("realized_loss_fraction"), "realized_loss_pct": risk.get("realized_loss_pct"),
            "risk_ladder": risk.get("risk_ladder", {}), "controlled_restart": controlled,
        },
        "capital_utilization": {
            "cash_pct": round(cash / equity * 100.0, 2), "exposure_pct": round(exposure, 2),
            "scanner_signals_found": int(scanner.get("signals_found") or 0),
            "latest_cycle_entries": len(_list(last_result.get("entries"))),
        },
        "plateau_drivers": drivers,
        "strategy_expectancy": {
            "positive_candidates": positive[:15], "negative_candidates": negative[:15],
            "setup_family_scorecards": _list(strategy.get("setup_family_scorecards"))[:20],
            "bucket_scorecards": _list(strategy.get("bucket_scorecards"))[:20],
            "automatic_strategy_disabling": False,
            "reason": "Demotion remains advisory until label quality and sample size are sufficient.",
        },
        "recommendations": [
            "Keep the 3.00% absolute daily equity-loss ceiling.",
            "Use half-sized, high-score controlled restart entries after the 1.00% soft pause.",
            "Hard halt new risk at 2.50% realized loss or intraday drawdown.",
            "Review negative-expectancy strategy labels before granting additional capital.",
            "Favor strategies with positive expectancy, profit factor above 1.25, and adequate sample size.",
        ],
        "authority": {
            "paper_only": True, "changes_thresholds": True, "changes_risk_or_sizing": True,
            "places_orders_directly": False, "changes_ml_authority": False, "changes_live_authority": False,
        },
    }


def install(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    if id(core) in _PATCHED:
        return {"status": "ok", "version": VERSION, "already_installed": True}

    patched: Dict[str, bool] = {}
    original_update = getattr(core, "update_daily_risk_controls", None)
    if callable(original_update) and not getattr(original_update, "_performance_risk_calibrated", False):
        def calibrated_update(equity, *args, **kwargs):
            result = original_update(equity, *args, **kwargs)
            risk = result if isinstance(result, dict) else _dict(_portfolio(core).get("risk_controls"))
            return _decorate_risk(core, risk)
        calibrated_update._performance_risk_calibrated = True
        calibrated_update._performance_risk_original = original_update
        core.update_daily_risk_controls = calibrated_update
        patched["update_daily_risk_controls"] = True

    original_feedback = getattr(core, "feedback_loop_status", None)
    if callable(original_feedback) and not getattr(original_feedback, "_performance_risk_calibrated", False):
        def calibrated_feedback(*args, **kwargs):
            row = original_feedback(*args, **kwargs)
            row = row if isinstance(row, dict) else {}
            market = kwargs.get("market") if isinstance(kwargs.get("market"), dict) else (args[0] if args and isinstance(args[0], dict) else _dict(_portfolio(core).get("last_market")))
            risk = kwargs.get("risk_controls") if isinstance(kwargs.get("risk_controls"), dict) else (args[2] if len(args) >= 3 and isinstance(args[2], dict) else _dict(_portfolio(core).get("risk_controls")))
            clock = kwargs.get("clock") if isinstance(kwargs.get("clock"), dict) else (args[3] if len(args) >= 4 and isinstance(args[3], dict) else None)
            if not isinstance(clock, dict):
                try:
                    clock = core.market_clock()
                except Exception:
                    clock = {}
            persist = kwargs.get("persist", args[4] if len(args) >= 5 else True)
            return _rewrite_feedback(core, row, market, clock, risk, bool(persist))
        calibrated_feedback._performance_risk_calibrated = True
        calibrated_feedback._performance_risk_original = original_feedback
        core.feedback_loop_status = calibrated_feedback
        patched["feedback_loop_status"] = True

    original_entries = getattr(core, "try_entries_and_rotations", None)
    if callable(original_entries) and not getattr(original_entries, "_performance_risk_calibrated", False):
        def calibrated_entries(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
            restart = _dict(_dict(_portfolio(core).get("feedback_loop")).get("controlled_restart"))
            if not restart.get("active") or not new_entries_allowed:
                return original_entries(long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

            section = _restart_state(core)
            used = int(section.get("controlled_restart_entries_used") or 0)
            candidates = sorted([x for x in _list(long_signals) if isinstance(x, dict)], key=lambda x: _f(x.get("score")), reverse=True)
            if used >= RESTART_MAX_ENTRIES:
                return [], [], [{"symbol": x.get("symbol"), "score": x.get("score"), "reason": "controlled_restart_daily_allowance_exhausted"} for x in candidates[:10]]
            required = _f(restart.get("required_long_score"))
            qualified = [x for x in candidates if _f(x.get("score")) >= required]
            if not qualified:
                return [], [], [{"symbol": x.get("symbol"), "score": x.get("score"), "reason": "controlled_restart_score_floor", "required_score": required} for x in candidates[:10]]

            positions = _dict(_portfolio(core).get("positions"))
            calibrated_params = dict(params or {})
            normal_max = int(calibrated_params.get("max_positions") or 0)
            if normal_max <= len(positions):
                x = qualified[0]
                return [], [], [{"symbol": x.get("symbol"), "score": x.get("score"), "reason": "controlled_restart_no_rotation", "allow_rotations": False}]

            signal = dict(qualified[0])
            signal["alloc_factor"] = min(_f(signal.get("alloc_factor"), 1.0), RESTART_ALLOC_FACTOR)
            signal["entry_context"] = f"{str(signal.get('entry_context') or 'scanner')}|controlled_restart"
            signal["controlled_restart"] = True
            calibrated_params["max_positions"] = min(normal_max, len(positions) + 1)
            section["controlled_restart_attempts"] = int(section.get("controlled_restart_attempts") or 0) + 1
            entries, _, blocked = original_entries([signal], [], calibrated_params, market, new_entries_allowed=True, entry_block_reason=None)
            if entries:
                new_used = used + len(entries)
                section["controlled_restart_entries_used"] = new_used
                section["last_controlled_restart_entry_local"] = _now(core)
                restart["entries_used"] = new_used
                restart["entries_remaining"] = max(0, RESTART_MAX_ENTRIES - new_used)
                _dict(_portfolio(core).get("feedback_loop"))["controlled_restart"] = restart
                for entry in entries:
                    if isinstance(entry, dict):
                        entry["controlled_restart"] = True
                        entry["controlled_restart_alloc_factor"] = RESTART_ALLOC_FACTOR
            section["last_controlled_restart_blocked"] = blocked
            return entries, [], blocked
        calibrated_entries._performance_risk_calibrated = True
        calibrated_entries._performance_risk_original = original_entries
        core.try_entries_and_rotations = calibrated_entries
        patched["try_entries_and_rotations"] = True

    try:
        setattr(core, "PERFORMANCE_RISK_CALIBRATION_VERSION", VERSION)
        risk = _dict(_portfolio(core).get("risk_controls"))
        if risk:
            _decorate_risk(core, risk)
    except Exception:
        pass
    _PATCHED.add(id(core))
    return {"status": "ok", "version": VERSION, "patched": patched, "paper_only": True, "changes_live_authority": False, "changes_ml_authority": False}


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    core = core or _module()
    install(core)
    if id(flask_app) in _REGISTERED:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    def view():
        return jsonify(build_diagnostic(core or _module()))
    routes = (
        ("/paper/performance-risk-calibration-status", "performance_risk_calibration_status"),
        ("/paper/plateau-diagnostic", "performance_plateau_diagnostic"),
        ("/paper/risk-ladder-status", "performance_risk_ladder_status"),
    )
    for path, endpoint in routes:
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, view)
    _REGISTERED.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [x[0] for x in routes], "paper_only": True}
