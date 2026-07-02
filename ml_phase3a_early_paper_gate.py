"""Early paper-only ML Phase 3A gate.

Purpose:
- Allow the project to move from pure pre-3A shadow posture into an early,
  paper-only Phase 3A advisory posture before the stricter 150-execution-row
  benchmark is reached.
- Keep live authority off.
- Keep risk controls, self-defense, cooldowns, entry-quality gates, and existing
  sizing rules authoritative.
- Make the decision audit stop treating 150 rows as the only possible transition
  point when the current paper dataset is already sufficient for a guarded
  feedback-loop experiment.

This module does not place trades, does not change broker/live authority, does
not lower thresholds, and does not bypass risk controls.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List

VERSION = "ml-phase3a-early-paper-gate-2026-07-02-v1"
ENABLED = os.environ.get("ML3A_EARLY_PAPER_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MIN_EXECUTION_ROWS = int(os.environ.get("ML3A_EARLY_MIN_EXECUTION_ROWS", "75"))
MIN_OBSERVED_OUTCOMES = int(os.environ.get("ML3A_EARLY_MIN_OBSERVED_OUTCOMES", "50"))
MIN_LABELED_ROWS = int(os.environ.get("ML3A_EARLY_MIN_LABELED_ROWS", "100"))
MIN_PREDICTIONS = int(os.environ.get("ML3A_EARLY_MIN_PREDICTIONS", "10"))
MAX_DAILY_LOSS_PCT = float(os.environ.get("ML3A_EARLY_MAX_DAILY_LOSS_PCT", "1.00"))
STRICT_EXECUTION_ROWS = int(os.environ.get("ML_PRE3A_MIN_EXECUTION_ROWS", "150"))
STRICT_OBSERVED_OUTCOMES = int(os.environ.get("ML_PRE3A_MIN_OBSERVED_OUTCOMES", "100"))

REGISTERED_APP_IDS: set[int] = set()
PATCHED_DECISION_AUDIT_IDS: set[int] = set()
_LAST_STATUS: Dict[str, Any] = {}


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
            return mod
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _state(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is not None:
        try:
            state = getattr(core, "portfolio", None)
            if isinstance(state, dict):
                return state
        except Exception:
            pass
        try:
            if hasattr(core, "load_state"):
                state = core.load_state()
                if isinstance(state, dict):
                    return state
        except Exception:
            pass
    return {}


def _paper_context() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _is_exit(row: Dict[str, Any]) -> bool:
    text = " ".join(str(row.get(k, "")).lower() for k in ("action", "type", "reason", "exit_reason"))
    return bool(row.get("pnl_dollars") is not None or row.get("pnl_pct") is not None or "exit" in text or "sell" in text or "close" in text or "stop" in text)


def _counts(state: Dict[str, Any]) -> Dict[str, Any]:
    trades = [row for row in _l(state.get("trades")) if isinstance(row, dict)]
    exits = [row for row in trades if _is_exit(row)]
    ml2 = _d(state.get("ml_phase2"))
    model = _d(ml2.get("model"))
    dataset = _l(ml2.get("dataset"))
    labeled = _i(ml2.get("labeled_outcome_rows"), _i(model.get("labeled_outcome_rows"), 0))
    observed = _i(ml2.get("trade_outcomes"), _i(model.get("trade_outcomes"), len(exits)))
    predictions = len(_l(ml2.get("last_predictions")))
    return {
        "execution_rows": len(trades),
        "observed_outcomes": observed,
        "exit_rows": len(exits),
        "ml_rows_total": _i(ml2.get("rows_total"), len(dataset)),
        "labeled_rows": labeled,
        "predictions": predictions,
    }


def _risk_clean(state: Dict[str, Any]) -> Dict[str, Any]:
    risk = _d(state.get("risk_controls"))
    halted = bool(risk.get("halted"))
    self_defense = bool(risk.get("self_defense_active"))
    daily_loss = _f(risk.get("daily_loss_pct"), _f(risk.get("daily_drawdown_pct"), 0.0))
    return {
        "risk_clean": bool(not halted and not self_defense and daily_loss <= MAX_DAILY_LOSS_PCT),
        "halted": halted,
        "self_defense_active": self_defense,
        "daily_loss_pct": daily_loss,
        "max_daily_loss_pct": MAX_DAILY_LOSS_PCT,
    }


def _gate_status(core: Any = None) -> Dict[str, Any]:
    state = _state(core)
    counts = _counts(state)
    risk = _risk_clean(state)
    gates = [
        {"name": "paper_context", "current": _paper_context(), "required": True, "passed": bool(_paper_context())},
        {"name": "execution_rows", "current": counts["execution_rows"], "required": MIN_EXECUTION_ROWS, "passed": counts["execution_rows"] >= MIN_EXECUTION_ROWS},
        {"name": "observed_outcomes", "current": counts["observed_outcomes"], "required": MIN_OBSERVED_OUTCOMES, "passed": counts["observed_outcomes"] >= MIN_OBSERVED_OUTCOMES},
        {"name": "labeled_rows", "current": counts["labeled_rows"], "required": MIN_LABELED_ROWS, "passed": counts["labeled_rows"] >= MIN_LABELED_ROWS},
        {"name": "predictions", "current": counts["predictions"], "required": MIN_PREDICTIONS, "passed": counts["predictions"] >= MIN_PREDICTIONS},
        {"name": "risk_clean", "current": risk["risk_clean"], "required": True, "passed": bool(risk["risk_clean"])},
    ]
    failed = [g for g in gates if not g.get("passed")]
    early_ready = bool(ENABLED and not failed)
    strict_ready = bool(counts["execution_rows"] >= STRICT_EXECUTION_ROWS and counts["observed_outcomes"] >= STRICT_OBSERVED_OUTCOMES)
    return {
        "status": "ok",
        "overall": "pass" if early_ready else "warn",
        "type": "ml_phase3a_early_paper_gate_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "paper_context": bool(_paper_context()),
        "phase3a_ready": early_ready,
        "phase3a_paper_early_ready": early_ready,
        "strict_phase3a_ready": strict_ready,
        "phase3a_live_authority_allowed": False,
        "ml_authority": "paper_phase3a_guarded_advisory" if early_ready else "shadow_only",
        "execution_authority": False,
        "live_trade_decider": False,
        "risk_control_authority": False,
        "sizing_authority": False,
        "does_not_place_trades": True,
        "does_not_lower_thresholds": True,
        "does_not_bypass_risk_controls": True,
        "counts": counts,
        "risk": risk,
        "gates": gates,
        "gates_passed": len(gates) - len(failed),
        "gates_failed": len(failed),
        "failed_gates": failed,
        "strict_reference": {
            "execution_rows_required": STRICT_EXECUTION_ROWS,
            "observed_outcomes_required": STRICT_OBSERVED_OUTCOMES,
            "reason_for_not_waiting": "Paper-only feedback-loop experiment can begin earlier because no real-money execution authority is granted; strict 150/100 remains the benchmark before stronger or live authority.",
        },
        "recommendation": (
            "Early paper Phase 3A gate is open: allow guarded ML advisory influence in paper diagnostics while keeping risk controls and rule thresholds authoritative."
            if early_ready else
            "Keep ML shadow-only until the early paper gates pass."
        ),
    }


def _store_status(core: Any, status: Dict[str, Any]) -> None:
    try:
        state = _state(core)
        if not isinstance(state, dict):
            return
        state["ml_phase3a_early_paper_gate"] = dict(status)
        phase25 = state.setdefault("ml_phase25", {})
        if isinstance(phase25, dict):
            phase25.update({
                "version": VERSION,
                "phase3a_ready": bool(status.get("phase3a_ready")),
                "phase3a_paper_early_ready": bool(status.get("phase3a_paper_early_ready")),
                "strict_phase3a_ready": bool(status.get("strict_phase3a_ready")),
                "phase3a_live_authority_allowed": False,
                "ml_authority": status.get("ml_authority"),
                "gates_passed": status.get("gates_passed"),
                "gates_failed": status.get("gates_failed"),
                "counts": status.get("counts"),
                "updated_local": status.get("generated_local"),
            })
    except Exception:
        pass


def _patch_decision_audit(core: Any = None) -> Dict[str, Any]:
    try:
        import decision_audit_consolidation as dac
    except Exception as exc:
        return {"decision_audit_patched": False, "reason": f"decision_audit_unavailable:{type(exc).__name__}"}
    module_id = id(dac)
    if module_id in PATCHED_DECISION_AUDIT_IDS:
        return {"decision_audit_patched": True, "already_patched": True}

    original_ml_shadow = getattr(dac, "_ml_shadow", None)
    original_trade_quality = getattr(dac, "_trade_quality_coach", None)
    original_chief = getattr(dac, "_chief_advisory_coach", None)

    if callable(original_ml_shadow):
        def patched_ml_shadow(c: Any) -> Dict[str, Any]:
            row = original_ml_shadow(c)
            gate = _gate_status(c)
            row.update({
                "phase3a_ready": bool(gate.get("phase3a_ready")),
                "phase3a_paper_early_ready": bool(gate.get("phase3a_paper_early_ready")),
                "strict_phase3a_ready": bool(gate.get("strict_phase3a_ready")),
                "phase3a_live_authority_allowed": False,
                "ml_authority": gate.get("ml_authority"),
                "early_gate_version": VERSION,
                "early_gate_counts": gate.get("counts"),
                "early_gate_failed_gates": gate.get("failed_gates"),
            })
            return row
        patched_ml_shadow._ml3a_early_paper_gate_patched = True  # type: ignore[attr-defined]
        setattr(dac, "_ml_shadow", patched_ml_shadow)

    if callable(original_trade_quality):
        def patched_trade_quality(c: Any) -> Dict[str, Any]:
            row = original_trade_quality(c)
            gate = _gate_status(c)
            counts = gate.get("counts") if isinstance(gate.get("counts"), dict) else {}
            if gate.get("phase3a_paper_early_ready"):
                row["posture"] = "early_paper_3a_eligible"
                row["recommendation"] = (
                    f"Trade Quality Coach: execution_rows={counts.get('execution_rows')}/{STRICT_EXECUTION_ROWS}; "
                    "early paper Phase 3A gate is open with live authority off. Continue collecting rows for the strict benchmark."
                )
                row["phase3a_paper_early_ready"] = True
                row["strict_execution_rows_required"] = STRICT_EXECUTION_ROWS
            return row
        patched_trade_quality._ml3a_early_paper_gate_patched = True  # type: ignore[attr-defined]
        setattr(dac, "_trade_quality_coach", patched_trade_quality)

    if callable(original_chief):
        def patched_chief(trade_quality: Dict[str, Any], risk_coach: Dict[str, Any], post_harvest_coach: Dict[str, Any], ml: Dict[str, Any], news: Dict[str, Any]) -> Dict[str, Any]:
            row = original_chief(trade_quality, risk_coach, post_harvest_coach, ml, news)
            if ml.get("phase3a_paper_early_ready"):
                priority = {
                    "priority": "medium",
                    "category": "ml_early_paper_3a",
                    "recommended_action": "Run early paper Phase 3A as guarded ML advisory influence while keeping risk controls authoritative.",
                    "reason": "Early paper gates passed before the strict 150-row benchmark; live authority remains disabled.",
                    "authority_impact": "paper_advisory_only",
                }
                stack = [priority]
                for item in _l(row.get("priority_stack")):
                    if isinstance(item, dict) and item.get("category") not in {"trade_quality", "ml_readiness"}:
                        stack.append(item)
                row.update({
                    "top_priority": priority,
                    "priority_stack": stack[:6],
                    "recommendation": "Chief Advisory Coach: highest priority is run early paper Phase 3A guarded-advisory mode; do not grant live authority.",
                    "ml_authority": "paper_advisory_only",
                    "execution_authority": False,
                    "risk_control_authority": False,
                    "authority_changed": False,
                })
            return row
        patched_chief._ml3a_early_paper_gate_patched = True  # type: ignore[attr-defined]
        setattr(dac, "_chief_advisory_coach", patched_chief)

    PATCHED_DECISION_AUDIT_IDS.add(module_id)
    return {"decision_audit_patched": True, "already_patched": False}


def status_payload(core: Any = None) -> Dict[str, Any]:
    global _LAST_STATUS
    core = core or _module()
    status = _gate_status(core)
    patch_status = _patch_decision_audit(core)
    status.update(patch_status)
    _store_status(core, status)
    _LAST_STATUS = dict(status)
    return status


def apply(core: Any = None) -> Dict[str, Any]:
    return status_payload(core or _module())


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        return jsonify(status_payload(core or _module()))

    if "/paper/ml3a-early-paper-status" not in existing:
        flask_app.add_url_rule("/paper/ml3a-early-paper-status", "paper_ml3a_early_paper_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _module())


try:
    apply(_module())
except Exception:
    pass
