"""ML Phase 2.5 readiness and outcome-telemetry layer.

This module is shadow/advisory only. It does not place trades, change orders,
override risk controls, or authorize execution. Its job is to make the move to
Phase 3A measurable by tracking whether the bot has enough usable outcome data.

Routes:
- /paper/ml-readiness-status
- /paper/ml-phase25-status

Design goals:
- Surface Phase 3A readiness gates clearly.
- Track execution rows, labeled outcomes, blocked/rejected decisions, and review rows.
- Prepare MAE/MFE fields as telemetry placeholders without inventing data.
- Keep ML live_trade_decider false until thresholds are met and manually enabled later.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "ml-phase25-readiness-2026-05-16"
PHASE = "phase_2_5_readiness_governance"
LIVE_DECIDER = False
ENABLED = os.environ.get("ML25_READINESS_ENABLED", "true").lower() not in {"0", "false", "no", "off"}

MIN_EXECUTIONS_PHASE3A = int(os.environ.get("ML25_MIN_EXECUTIONS_PHASE3A", "150"))
MIN_LABELED_OUTCOMES_PHASE3A = int(os.environ.get("ML25_MIN_LABELED_OUTCOMES_PHASE3A", "150"))
MIN_SCANNER_DECISIONS_PHASE3A = int(os.environ.get("ML25_MIN_SCANNER_DECISIONS_PHASE3A", "5000"))
MIN_PROFIT_FACTOR_PHASE3A = float(os.environ.get("ML25_MIN_PROFIT_FACTOR_PHASE3A", "1.15"))
MIN_WIN_RATE_PHASE3A = float(os.environ.get("ML25_MIN_WIN_RATE_PHASE3A", "0.48"))
MIN_REGIME_COUNT_PHASE3A = int(os.environ.get("ML25_MIN_REGIME_COUNT_PHASE3A", "3"))
MIN_WALK_FORWARD_DAYS_PHASE3A = int(os.environ.get("ML25_MIN_WALK_FORWARD_DAYS_PHASE3A", "10"))

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        value = float(x)
        return default if math.isnan(value) or math.isinf(value) else value
    except Exception:
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
            return mod
    return None


def _now(mod: Any = None) -> str:
    try:
        return mod.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return (state if isinstance(state, dict) else {}), mod


def _execution_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _list(state.get("trades")):
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _actual_exit_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    exits = []
    for row in _execution_rows(state):
        action = str(row.get("action") or row.get("type") or "").lower()
        reason = str(row.get("exit_reason") or row.get("reason") or "").lower()
        has_pnl = row.get("pnl_dollars") is not None or row.get("pnl_pct") is not None
        if action in {"exit", "sell", "close"} or "exit" in reason or "stop" in reason or has_pnl:
            exits.append(row)
    return exits


def _scanner_counts(state: Dict[str, Any]) -> Dict[str, int]:
    audit = _dict(state.get("scanner_audit"))
    blocked = _list(audit.get("blocked_entries"))
    rejected = _list(audit.get("rejected_signals"))
    accepted = _list(audit.get("accepted_entries"))
    long_signals = _list(audit.get("long_signals"))
    short_signals = _list(audit.get("short_signals"))
    ml_shadow_rows = _list(_dict(state.get("ml_shadow")).get("feature_log"))
    ml2_rows = _list(_dict(state.get("ml_phase2")).get("dataset"))
    return {
        "accepted_entries": len(accepted),
        "blocked_entries": len(blocked),
        "rejected_signals": len(rejected),
        "long_signals": len(long_signals),
        "short_signals": len(short_signals),
        "ml_shadow_rows": len(ml_shadow_rows),
        "ml2_dataset_rows": len(ml2_rows),
        "estimated_total_decisions": max(
            len(ml2_rows),
            len(ml_shadow_rows),
            len(accepted) + len(blocked) + len(rejected) + len(long_signals) + len(short_signals),
        ),
    }


def _profit_metrics(exit_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    gross_profit = 0.0
    gross_loss = 0.0
    wins = 0
    losses = 0
    for row in exit_rows:
        pnl = _f(row.get("pnl_dollars"), 0.0)
        if pnl > 0:
            gross_profit += pnl
            wins += 1
        elif pnl < 0:
            gross_loss += abs(pnl)
            losses += 1
    total = wins + losses
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    return {
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 3),
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) if total else 0.0, 4),
    }


def _regime_count(state: Dict[str, Any]) -> Dict[str, Any]:
    regimes = set()
    market = _dict(state.get("last_market"))
    if market.get("regime"):
        regimes.add(str(market.get("regime")))
    for row in _list(_dict(state.get("ml_phase2")).get("dataset")):
        if isinstance(row, dict) and row.get("regime"):
            regimes.add(str(row.get("regime")))
    return {"count": len(regimes), "regimes_seen": sorted(regimes)}


def _walk_forward_proxy(state: Dict[str, Any]) -> Dict[str, Any]:
    # This is intentionally conservative. Until a dedicated walk-forward runner
    # exists, count distinct trade dates as a proxy and mark formal validation false.
    dates = set()
    for row in _execution_rows(state):
        if not isinstance(row, dict):
            continue
        date_value = row.get("date") or row.get("local_date") or row.get("day")
        if not date_value and row.get("time"):
            try:
                date_value = dt.datetime.fromtimestamp(float(row.get("time"))).strftime("%Y-%m-%d")
            except Exception:
                date_value = None
        if date_value:
            dates.add(str(date_value)[:10])
    return {
        "formal_walk_forward_passed": False,
        "proxy_trade_days": len(dates),
        "distinct_trade_dates": sorted(dates)[-20:],
        "required_walk_forward_days": MIN_WALK_FORWARD_DAYS_PHASE3A,
        "note": "Formal walk-forward validation is not yet authoritative; this proxy only tracks trade-day coverage.",
    }


def _mae_mfe_status(state: Dict[str, Any]) -> Dict[str, Any]:
    ml2_rows = _list(_dict(state.get("ml_phase2")).get("dataset"))
    rows_with_mae = 0
    rows_with_mfe = 0
    for row in ml2_rows:
        if isinstance(row, dict):
            rows_with_mae += 1 if row.get("mae_pct") is not None or row.get("future_mae_pct") is not None else 0
            rows_with_mfe += 1 if row.get("mfe_pct") is not None or row.get("future_mfe_pct") is not None else 0
    return {
        "enabled": True,
        "rows_with_mae": rows_with_mae,
        "rows_with_mfe": rows_with_mfe,
        "mae_mfe_complete": bool(rows_with_mae > 0 and rows_with_mfe > 0),
        "note": "MAE/MFE fields are ready for telemetry; no synthetic MAE/MFE values are invented.",
    }


def _gate(name: str, current: Any, required: Any, passed: bool, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "current": current, "required": required, "passed": bool(passed), "detail": detail}


def readiness_payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    exits = _actual_exit_rows(state)
    scanner = _scanner_counts(state)
    metrics = _profit_metrics(exits)
    regimes = _regime_count(state)
    walk_forward = _walk_forward_proxy(state)
    mae_mfe = _mae_mfe_status(state)
    ml2 = _dict(state.get("ml_phase2"))
    labeled = _i(ml2.get("labeled_outcome_rows"), len([r for r in _list(ml2.get("dataset")) if isinstance(r, dict) and not r.get("future_outcome_pending")]))
    executions = len(_execution_rows(state))
    scanner_decisions = scanner.get("estimated_total_decisions", 0)

    gates = [
        _gate("execution_rows", executions, MIN_EXECUTIONS_PHASE3A, executions >= MIN_EXECUTIONS_PHASE3A, "Actual entries/exits in state.trades."),
        _gate("labeled_outcome_rows", labeled, MIN_LABELED_OUTCOMES_PHASE3A, labeled >= MIN_LABELED_OUTCOMES_PHASE3A, "Rows with realized or labeled outcome data."),
        _gate("scanner_decisions", scanner_decisions, MIN_SCANNER_DECISIONS_PHASE3A, scanner_decisions >= MIN_SCANNER_DECISIONS_PHASE3A, "Scanner/rejected/blocked/ML dataset coverage."),
        _gate("profit_factor", metrics.get("profit_factor"), MIN_PROFIT_FACTOR_PHASE3A, _f(metrics.get("profit_factor")) >= MIN_PROFIT_FACTOR_PHASE3A, "Execution-only realized profit factor."),
        _gate("win_rate", metrics.get("win_rate"), MIN_WIN_RATE_PHASE3A, _f(metrics.get("win_rate")) >= MIN_WIN_RATE_PHASE3A, "Execution-only realized win rate."),
        _gate("regime_coverage", regimes.get("count"), MIN_REGIME_COUNT_PHASE3A, regimes.get("count", 0) >= MIN_REGIME_COUNT_PHASE3A, "Distinct regimes represented in ML2 dataset."),
        _gate("walk_forward_days_proxy", walk_forward.get("proxy_trade_days"), MIN_WALK_FORWARD_DAYS_PHASE3A, walk_forward.get("proxy_trade_days", 0) >= MIN_WALK_FORWARD_DAYS_PHASE3A, "Proxy only; formal validation still required."),
        _gate("formal_walk_forward_validation", walk_forward.get("formal_walk_forward_passed"), True, bool(walk_forward.get("formal_walk_forward_passed")), "Must be true before Phase 3A live weighting."),
        _gate("mae_mfe_telemetry", mae_mfe.get("mae_mfe_complete"), True, bool(mae_mfe.get("mae_mfe_complete")), "Needed for quality labels and stop-efficiency learning."),
    ]
    passed = [g for g in gates if g.get("passed")]
    failed = [g for g in gates if not g.get("passed")]
    phase3a_ready = len(failed) == 0

    if phase3a_ready:
        phase = "phase_3a_ready_for_manual_enablement"
        recommendation = "All gates pass; ML may be considered for tiny shadow-to-weighting experiments only after manual review."
    elif executions >= 50 or labeled >= 50 or scanner_decisions >= 2500:
        phase = "phase_2_5_collecting_validating"
        recommendation = "Continue shadow collection; start formal walk-forward tooling before live ML weighting."
    else:
        phase = "phase_2_5_early_data_collection"
        recommendation = "Keep ML shadow-only; focus on outcome volume and MAE/MFE labeling before Phase 3A."

    return {
        "status": "ok",
        "type": "ml_readiness_status",
        "version": VERSION,
        "phase": phase,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_trade_decider": False,
        "phase3a_ready": bool(phase3a_ready),
        "phase3a_live_authority_allowed": False,
        "recommendation": recommendation,
        "gates_passed": len(passed),
        "gates_failed": len(failed),
        "gates": gates,
        "execution_summary": {
            "execution_rows": executions,
            "exit_rows": len(exits),
            **metrics,
        },
        "scanner_summary": scanner,
        "ml2_summary": {
            "rows_total": ml2.get("rows_total", len(_list(ml2.get("dataset")))),
            "labeled_outcome_rows": labeled,
            "readiness": ml2.get("readiness"),
            "latest_predictions_count": len(_list(ml2.get("last_predictions"))),
        },
        "regime_summary": regimes,
        "walk_forward": walk_forward,
        "mae_mfe": mae_mfe,
        "thresholds": {
            "min_executions_phase3a": MIN_EXECUTIONS_PHASE3A,
            "min_labeled_outcomes_phase3a": MIN_LABELED_OUTCOMES_PHASE3A,
            "min_scanner_decisions_phase3a": MIN_SCANNER_DECISIONS_PHASE3A,
            "min_profit_factor_phase3a": MIN_PROFIT_FACTOR_PHASE3A,
            "min_win_rate_phase3a": MIN_WIN_RATE_PHASE3A,
            "min_regime_count_phase3a": MIN_REGIME_COUNT_PHASE3A,
            "min_walk_forward_days_phase3a": MIN_WALK_FORWARD_DAYS_PHASE3A,
        },
    }


def _ensure_state_section(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    section = state.setdefault("ml_phase25", {})
    section.update({
        "version": VERSION,
        "phase": payload.get("phase"),
        "enabled": ENABLED,
        "live_trade_decider": False,
        "phase3a_ready": payload.get("phase3a_ready"),
        "gates_passed": payload.get("gates_passed"),
        "gates_failed": payload.get("gates_failed"),
        "last_updated_local": payload.get("generated_local"),
        "recommendation": payload.get("recommendation"),
        "mae_mfe": payload.get("mae_mfe"),
    })


def apply(module: Any = None) -> Dict[str, Any]:
    module = module or _module()
    if module is None:
        return {"status": "not_applied", "version": VERSION, "reason": "module_missing"}
    if id(module) in PATCHED_MODULE_IDS:
        return {"status": "ok", "version": VERSION, "already_patched": True, "live_trade_decider": False}

    try:
        original = getattr(module, "save_state", None)
        if callable(original):
            def patched_save_state(state):
                try:
                    payload = readiness_payload(state, module)
                    _ensure_state_section(state, payload)
                except Exception as exc:
                    try:
                        state.setdefault("ml_phase25", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                return original(state)
            patched_save_state._ml25_readiness_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass

    try:
        setattr(module, "ML_PHASE25_READINESS_VERSION", VERSION)
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(module))
    return {"status": "ok", "version": VERSION, "phase": PHASE, "live_trade_decider": False}


def register_routes(flask_app: Any, module: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    module = module or _module()
    apply(module)
    if id(flask_app) in REGISTERED_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        state, mod = _load_state(module)
        payload = readiness_payload(state, mod)
        return jsonify(payload)

    if "/paper/ml-readiness-status" not in existing:
        flask_app.add_url_rule("/paper/ml-readiness-status", "paper_ml_readiness_status", status_route)
    if "/paper/ml-phase25-status" not in existing:
        flask_app.add_url_rule("/paper/ml-phase25-status", "paper_ml_phase25_status", status_route)

    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/ml-readiness-status", "/paper/ml-phase25-status"], "live_trade_decider": False}
