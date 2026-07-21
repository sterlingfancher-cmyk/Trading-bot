"""Compact the routine paper self-check without removing full diagnostics.

/paper/self-check remains the single daily URL, but its light-mode response is
reduced to operator-critical health, account, risk, pipeline, scanner, and ML
fields. /paper/full-self-check remains unchanged for intentional debugging.

This module changes reporting only. It does not change trading logic, risk,
orders, sizing, candidates, live authority, or ML authority.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

VERSION = "daily-self-check-compactor-2026-07-21-v2-authoritative-fallbacks"
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


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "load_state"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _state_snapshot() -> Dict[str, Any]:
    core = _mod()
    if core is None:
        return {}
    try:
        state = core.load_state()
        if isinstance(state, dict):
            return state
    except Exception:
        pass
    try:
        state = getattr(core, "portfolio", {})
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _base_url() -> str:
    base = str(os.environ.get("RAILWAY_PUBLIC_DOMAIN") or os.environ.get("BASE_URL") or "https://trading-bot-clean.up.railway.app").strip()
    if base and not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")


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


def _positions_from_sources(status: Dict[str, Any], state: Dict[str, Any], performance: Dict[str, Any]) -> tuple[List[str], Dict[str, Any], bool]:
    status_positions = status.get("positions")
    state_positions = state.get("positions")
    performance_positions = performance.get("open_positions")

    positions_map: Dict[str, Any] = {}
    positions_list: List[str] = []
    source_present = False

    if isinstance(performance_positions, dict):
        positions_map = performance_positions
        positions_list = list(performance_positions.keys())
        source_present = True
    elif isinstance(state_positions, dict):
        positions_map = state_positions
        positions_list = list(state_positions.keys())
        source_present = True
    elif isinstance(status_positions, dict):
        positions_map = status_positions
        positions_list = list(status_positions.keys())
        source_present = True
    elif isinstance(status_positions, list):
        positions_list = [str(item) for item in status_positions]
        source_present = True

    return positions_list, positions_map, source_present


def compact_daily(payload: Dict[str, Any]) -> Dict[str, Any]:
    state = _state_snapshot()
    dashboard = _d(payload.get("dashboard"))
    status = _d(dashboard.get("status"))
    health_snapshot = _d(dashboard.get("health"))
    performance = _d(status.get("performance"))
    risk = _d(status.get("risk_controls"))
    operator = _d(payload.get("operator_summary"))
    truth = _d(payload.get("truth_summary"))
    decision = _d(payload.get("decision_audit_summary")) or _d(dashboard.get("decision_audit")) or _d(state.get("decision_audit"))
    blocked = _d(payload.get("blocked_entry_reason_audit_summary")) or _d(dashboard.get("blocked_entry_reason_audit")) or _d(state.get("blocked_entry_reason_audit"))
    xray = _d(payload.get("entry_pipeline_xray_summary")) or _d(dashboard.get("entry_pipeline_xray")) or _d(state.get("entry_pipeline_xray"))
    composition = _d(xray.get("composition_status"))
    current_callable = _d(composition.get("current_callable"))
    inner_callable = _d(composition.get("inner_callable"))
    counters = _d(xray.get("counters"))
    last_error = _d(xray.get("last_error"))
    error = _d(last_error.get("error"))
    starter = _d(payload.get("risk_on_starter_participation_summary")) or _d(dashboard.get("risk_on_starter_participation")) or _d(state.get("risk_on_starter_participation"))

    state_performance = _d(state.get("performance"))
    state_risk = _d(state.get("risk_controls"))
    state_trade_journal = _d(state.get("trade_journal"))
    state_journal_summary = _d(state_trade_journal.get("journal_summary"))
    state_scanner = _d(state.get("scanner_audit"))

    positions, open_positions, positions_source_present = _positions_from_sources(status, state, performance)

    warnings = _l(payload.get("warnings"))
    compact_warnings: List[Dict[str, Any]] = []
    for row in warnings[:3]:
        if isinstance(row, dict):
            compact_warnings.append({
                "path": row.get("path"),
                "error": row.get("error"),
                "details": row.get("details"),
            })

    account = {
        "equity": _first(status.get("equity"), state.get("equity")),
        "cash": _first(status.get("cash"), state.get("cash")),
        "positions": positions,
        "open_positions_count": _first(
            truth.get("open_positions_count"),
            operator.get("open_positions_count"),
            state_journal_summary.get("open_positions_count"),
            len(open_positions) if open_positions else (len(positions) if positions_source_present else None),
        ),
        "realized_today": _first(
            truth.get("realized_today"),
            performance.get("realized_pnl_today"),
            state_performance.get("realized_pnl_today"),
            state_journal_summary.get("realized_today"),
            state.get("realized_pnl_today"),
        ),
        "realized_total": _first(
            truth.get("realized_total"),
            performance.get("realized_pnl_total"),
            state_performance.get("realized_pnl_total"),
            state_journal_summary.get("realized_total"),
            state.get("realized_pnl_total"),
        ),
        "unrealized_pnl": _first(
            truth.get("unrealized_pnl"),
            performance.get("unrealized_pnl"),
            state_performance.get("unrealized_pnl"),
            state_journal_summary.get("unrealized_pnl"),
            state.get("unrealized_pnl"),
        ),
        "wins_total": _first(truth.get("wins_total"), performance.get("wins_total"), state_performance.get("wins_total"), state.get("wins_total")),
        "losses_total": _first(truth.get("losses_total"), performance.get("losses_total"), state_performance.get("losses_total"), state.get("losses_total")),
        "execution_rows": _first(truth.get("execution_rows_count"), state_journal_summary.get("execution_rows_count"), len(_l(state.get("trades"))) if isinstance(state.get("trades"), list) else None),
    }

    compact_risk = {
        "self_defense_active": _first(risk.get("self_defense_active"), state_risk.get("self_defense_active"), state.get("self_defense_active")),
        "self_defense_reason": _first(risk.get("self_defense_reason"), state_risk.get("self_defense_reason"), state.get("self_defense_reason")),
        "daily_loss_pct": _first(risk.get("daily_loss_pct"), state_risk.get("daily_loss_pct")),
        "intraday_drawdown_pct": _first(risk.get("intraday_drawdown_pct"), state_risk.get("intraday_drawdown_pct")),
    }

    reason_coverage = _d(blocked.get("reason_coverage"))
    scanner = {
        "signals_found": _first(decision.get("signals_found"), _d(status.get("scanner_audit")).get("signals_found"), state_scanner.get("signals_found")),
        "entries_count": decision.get("entries_count"),
        "rejected_signals_count": _first(decision.get("rejected_signals_count"), len(_l(state_scanner.get("rejected_signals"))) if isinstance(state_scanner.get("rejected_signals"), list) else None),
        "post_harvest_outcome": decision.get("post_harvest_outcome"),
        "post_harvest_reason": decision.get("post_harvest_reason"),
        "top_blockers": _top_rows(blocked.get("top_blocked_symbol_details") or blocked.get("symbol_reason_rollup"), 5),
        "reason_coverage_pct": _first(reason_coverage.get("actionable_reason_coverage_pct"), blocked.get("actionable_reason_coverage_pct")),
        "missing_reason_rows": _first(blocked.get("missing_reason_detail_count"), reason_coverage.get("rows_missing_reason_detail")),
    }

    missing_sources: List[str] = []
    for key in ("equity", "cash", "open_positions_count", "realized_total", "unrealized_pnl"):
        if account.get(key) is None:
            missing_sources.append(f"account.{key}")
    for key in ("self_defense_active", "intraday_drawdown_pct"):
        if compact_risk.get(key) is None:
            missing_sources.append(f"risk.{key}")
    if scanner.get("signals_found") is None:
        missing_sources.append("scanner.signals_found")

    if missing_sources:
        compact_warnings.append({
            "path": "/paper/self-check",
            "error": "compact_source_fields_missing",
            "details": missing_sources,
        })

    base = _base_url()
    full_diagnostics_url = payload.get("full_self_check") or (f"{base}/paper/full-self-check" if base else "/paper/full-self-check")
    routine_url = payload.get("single_best_link") or payload.get("normal_test_link") or (f"{base}/paper/self-check" if base else "/paper/self-check")

    checked_paths = payload.get("checked_paths")
    if not isinstance(checked_paths, list):
        checked_paths = [row.get("path") for row in _l(payload.get("results")) if isinstance(row, dict) and row.get("path")]

    service_status = _first(health_snapshot.get("status"), status.get("status"), "running" if state else None)
    overall = payload.get("overall") or payload.get("status") or "unknown"
    compact_status = payload.get("status") or ("warn" if missing_sources else "ok")

    return {
        "status": compact_status,
        "overall": overall,
        "type": "daily_self_check",
        "version": VERSION,
        "generated_local": payload.get("generated_local"),
        "daily_response_compact": True,
        "source_fallbacks_used": bool(state),
        "full_diagnostics_url": full_diagnostics_url,
        "routine_test_url": routine_url,
        "health": {
            "service": service_status,
            "failed_required": payload.get("failed_required") or [],
            "checked_paths": checked_paths,
            "warnings": compact_warnings[:4],
        },
        "account": account,
        "risk": compact_risk,
        "scanner": scanner,
        "entry_pipeline": {
            "status": composition.get("status") or xray.get("status"),
            "stack_stable": composition.get("stack_stable"),
            "recursion_safe": composition.get("recursion_safe"),
            "direct_core_base": composition.get("direct_core_base"),
            "participation_valve_chain_cycle_free": composition.get("participation_valve_chain_cycle_free"),
            "current_callable": f"{current_callable.get('module')}.{current_callable.get('name')}" if current_callable else None,
            "inner_callable": f"{inner_callable.get('module')}.{inner_callable.get('name')}" if inner_callable else None,
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
    while callable(original) and getattr(original, "_daily_self_check_compactor_original", None) is not None:
        original = getattr(original, "_daily_self_check_compactor_original")

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
        "authoritative_state_fallbacks": True,
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
