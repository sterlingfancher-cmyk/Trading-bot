"""Compact the routine paper self-check without removing full diagnostics.

/paper/self-check remains the single daily URL, but its light-mode response is
reduced to operator-critical health, account, risk, pipeline, scanner, and ML
fields. /paper/full-self-check remains unchanged for intentional debugging.

This module changes reporting only. It does not change trading logic, risk,
orders, sizing, candidates, live authority, or ML authority.
"""
from __future__ import annotations

from typing import Any, Dict, List

VERSION = "daily-self-check-compactor-2026-07-21-v1"
_PATCHED = False


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _top_rows(rows: Any, limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in _l(rows):
        if not isinstance(row, dict):
            continue
        out.append({
            "symbol": row.get("symbol"),
            "category": row.get("top_category") or row.get("category"),
            "reason": row.get("top_reason") or row.get("reason"),
            "score": row.get("best_visible_score") if row.get("best_visible_score") is not None else row.get("score"),
        })
        if len(out) >= limit:
            break
    return out


def compact_daily(payload: Dict[str, Any]) -> Dict[str, Any]:
    dashboard = _d(payload.get("dashboard"))
    status = _d(dashboard.get("status"))
    performance = _d(status.get("performance"))
    risk = _d(status.get("risk_controls"))
    operator = _d(payload.get("operator_summary"))
    truth = _d(payload.get("truth_summary"))
    decision = _d(payload.get("decision_audit_summary")) or _d(dashboard.get("decision_audit"))
    blocked = _d(payload.get("blocked_entry_reason_audit_summary")) or _d(dashboard.get("blocked_entry_reason_audit"))
    xray = _d(payload.get("entry_pipeline_xray_summary")) or _d(dashboard.get("entry_pipeline_xray"))
    composition = _d(xray.get("composition_status"))
    current_callable = _d(composition.get("current_callable"))
    inner_callable = _d(composition.get("inner_callable"))
    counters = _d(xray.get("counters"))
    last_error = _d(xray.get("last_error"))
    error = _d(last_error.get("error"))
    starter = _d(payload.get("risk_on_starter_participation_summary")) or _d(dashboard.get("risk_on_starter_participation"))

    warnings = _l(payload.get("warnings"))
    compact_warnings: List[Dict[str, Any]] = []
    for row in warnings[:3]:
        if isinstance(row, dict):
            compact_warnings.append({
                "path": row.get("path"),
                "error": row.get("error"),
                "details": row.get("details"),
            })

    positions = status.get("positions") or operator.get("positions") or []
    open_positions = _d(performance.get("open_positions"))

    return {
        "status": payload.get("status"),
        "overall": payload.get("overall"),
        "type": "daily_self_check",
        "version": VERSION,
        "generated_local": payload.get("generated_local"),
        "daily_response_compact": True,
        "full_diagnostics_url": payload.get("full_self_check"),
        "routine_test_url": payload.get("single_best_link") or payload.get("normal_test_link"),
        "health": {
            "service": _d(dashboard.get("health")).get("status") or status.get("status"),
            "failed_required": payload.get("failed_required") or [],
            "checked_paths": payload.get("checked_paths") or [],
            "warnings": compact_warnings,
        },
        "account": {
            "equity": status.get("equity"),
            "cash": status.get("cash"),
            "positions": positions,
            "open_positions_count": _first(truth.get("open_positions_count"), operator.get("open_positions_count"), len(open_positions)),
            "realized_today": _first(truth.get("realized_today"), performance.get("realized_pnl_today")),
            "realized_total": _first(truth.get("realized_total"), performance.get("realized_pnl_total")),
            "unrealized_pnl": _first(truth.get("unrealized_pnl"), performance.get("unrealized_pnl")),
            "wins_total": _first(truth.get("wins_total"), performance.get("wins_total")),
            "losses_total": _first(truth.get("losses_total"), performance.get("losses_total")),
            "execution_rows": truth.get("execution_rows_count"),
        },
        "risk": {
            "self_defense_active": risk.get("self_defense_active"),
            "self_defense_reason": risk.get("self_defense_reason"),
            "daily_loss_pct": risk.get("daily_loss_pct"),
            "intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
        },
        "scanner": {
            "signals_found": _first(decision.get("signals_found"), _d(status.get("scanner_audit")).get("signals_found")),
            "entries_count": decision.get("entries_count"),
            "rejected_signals_count": decision.get("rejected_signals_count"),
            "post_harvest_outcome": decision.get("post_harvest_outcome"),
            "post_harvest_reason": decision.get("post_harvest_reason"),
            "top_blockers": _top_rows(blocked.get("top_blocked_symbol_details") or blocked.get("symbol_reason_rollup"), 5),
            "reason_coverage_pct": _d(blocked.get("reason_coverage")).get("actionable_reason_coverage_pct"),
            "missing_reason_rows": blocked.get("missing_reason_detail_count"),
        },
        "entry_pipeline": {
            "status": composition.get("status") or xray.get("status"),
            "stack_stable": composition.get("stack_stable"),
            "recursion_safe": composition.get("recursion_safe"),
            "direct_core_base": composition.get("direct_core_base"),
            "participation_valve_chain_cycle_free": composition.get("participation_valve_chain_cycle_free"),
            "current_callable": f"{current_callable.get('module')}.{current_callable.get('name')}",
            "inner_callable": f"{inner_callable.get('module')}.{inner_callable.get('name')}",
            "active_callsite_invocations_total": counters.get("active_callsite_invocations_total"),
            "active_callsite_errors_total": counters.get("bottleneck_active_callsite_error_total"),
            "latest_error_timestamp": last_error.get("generated_local"),
            "latest_error_type": error.get("type"),
            "latest_error_message": error.get("message"),
        },
        "starter_valve": {
            "status": starter.get("status"),
            "enabled": starter.get("enabled"),
            "patched": starter.get("patched"),
            "telemetry_persisted": starter.get("telemetry_persisted"),
            "last_status": starter.get("last_status"),
            "last_reason": starter.get("last_reason"),
            "last_symbol": starter.get("last_symbol"),
        },
        "ml": {
            "phase3a_ready": any("phase3a_ready=True" in str(item) for item in _l(decision.get("next_actions"))),
            "live_authority": "none",
            "advisory_only": decision.get("advisory_only"),
            "next_action": (_l(decision.get("next_actions")) or [None])[0],
        },
        "note": "Use full_diagnostics_url only when this compact response reports warn/fail or a new error timestamp.",
    }


def apply(_core: Any = None) -> Dict[str, Any]:
    global _PATCHED
    try:
        import self_check
    except Exception as exc:
        return {"status": "pending", "version": VERSION, "reason": str(exc)}

    current = getattr(self_check, "run_self_check", None)
    if not callable(current):
        return {"status": "pending", "version": VERSION, "reason": "run_self_check_not_ready"}
    if getattr(current, "_daily_self_check_compactor_version", None) == VERSION:
        _PATCHED = True
        return {"status": "ok", "version": VERSION, "patched": True, "stable_fast_path": True}

    original = current

    def run_self_check(flask_app: Any, mode: str = "light") -> Dict[str, Any]:
        payload = original(flask_app, mode=mode)
        if not isinstance(payload, dict):
            return payload
        if str(mode).lower() not in {"light", "mobile_safe", "daily"}:
            return payload
        return compact_daily(payload)

    run_self_check._daily_self_check_compactor_version = VERSION  # type: ignore[attr-defined]
    run_self_check._daily_self_check_compactor_original = original  # type: ignore[attr-defined]
    self_check.run_self_check = run_self_check
    _PATCHED = True
    return {
        "status": "ok",
        "version": VERSION,
        "patched": True,
        "daily_route": "/paper/self-check",
        "full_route": "/paper/full-self-check",
        "reporting_only": True,
        "authority_changed": False,
    }


def status_payload() -> Dict[str, Any]:
    return {
        "status": "ok" if _PATCHED else "pending",
        "version": VERSION,
        "patched": _PATCHED,
        "daily_response_compact": True,
        "full_diagnostics_preserved": True,
        "authority_changed": False,
        "logic_changed": False,
    }


def register_routes(flask_app: Any, _core: Any = None) -> None:
    if flask_app is None:
        return
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if "/paper/daily-self-check-compactor-status" not in existing:
            from flask import jsonify
            flask_app.add_url_rule(
                "/paper/daily-self-check-compactor-status",
                "daily_self_check_compactor_status",
                lambda: jsonify(status_payload()),
            )
    except Exception:
        pass
    apply()


try:
    apply()
except Exception:
    pass
