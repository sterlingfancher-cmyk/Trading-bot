"""Terminal, allowlisted serializer for the routine paper self-check.

The daily route is reporting-only. It reads authoritative state and diagnostic
status producers, normalizes their different schemas, and returns a small stable
contract. Full diagnostics remain available at /paper/full-self-check.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

VERSION = "daily-self-check-compactor-2026-07-21-v4-source-contracts"
_PATCHED = False
_TERMINAL_ROUTE_APP_IDS: set[int] = set()


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
    state = getattr(core, "portfolio", {})
    return state if isinstance(state, dict) else {}


def _base_url() -> str:
    base = str(
        os.environ.get("PUBLIC_BASE_URL")
        or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or os.environ.get("BASE_URL")
        or "https://trading-bot-clean.up.railway.app"
    ).strip()
    if base and not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")


def _module_payload(module_name: str, function_names: tuple[str, ...]) -> Dict[str, Any]:
    """Read a status producer using either its no-arg or core-aware contract."""
    try:
        module = __import__(module_name)
    except Exception:
        return {}
    core = _mod()
    for name in function_names:
        fn = getattr(module, name, None)
        if not callable(fn):
            continue
        for args in ((), (core,)):
            try:
                value = fn(*args)
                if isinstance(value, dict):
                    return value
            except TypeError:
                continue
            except Exception:
                break
    return {}


def _mobile_base_payload() -> Dict[str, Any]:
    try:
        import self_check
        fn = getattr(self_check, "run_mobile_self_check", None)
        if callable(fn):
            value = fn()
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def _callable_name(value: Any) -> Any:
    row = _d(value)
    module = row.get("module")
    name = row.get("name")
    return f"{module}.{name}" if module and name else None


def _positions(state: Dict[str, Any], status: Dict[str, Any], performance: Dict[str, Any]) -> tuple[List[str], bool]:
    sources = [performance.get("open_positions"), state.get("positions"), status.get("positions"), _d(state.get("portfolio")).get("positions")]
    for value in sources:
        if isinstance(value, dict):
            return [str(key) for key in value.keys()], True
        if isinstance(value, list):
            return [str(item) for item in value], True
    return [], False


def _top_rows(rows: Any, limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in _l(rows):
        if not isinstance(row, dict):
            continue
        quality = _d(row.get("quality_info"))
        reason = row.get("top_reason") or row.get("reason")
        if quality.get("reason") and reason:
            reason = f"{reason};quality_info.reason={quality.get('reason')}"
        out.append({
            "symbol": row.get("symbol"),
            "category": row.get("top_category") or row.get("category"),
            "reason": reason,
            "score": _first(row.get("best_visible_score"), row.get("score")),
        })
        if len(out) >= limit:
            break
    return out


def _decision_payload(payload: Dict[str, Any], dashboard: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    decision = (
        _d(payload.get("decision_audit_summary"))
        or _d(dashboard.get("decision_audit"))
        or _d(state.get("decision_audit"))
        or _module_payload("decision_audit_consolidation", ("build_payload",))
    )
    cycle = _d(decision.get("latest_cycle"))
    post = _d(decision.get("post_harvest"))
    ml_shadow = _d(decision.get("ml_shadow"))
    return {
        **decision,
        "signals_found": _first(decision.get("signals_found"), cycle.get("signals_found")),
        "entries_count": _first(decision.get("entries_count"), cycle.get("entries_count")),
        "rejected_signals_count": _first(decision.get("rejected_signals_count"), cycle.get("rejected_signals_count")),
        "open_positions_count": _first(decision.get("open_positions_count"), _d(decision.get("risk_book")).get("open_positions_count")),
        "post_harvest_outcome": _first(decision.get("post_harvest_outcome"), post.get("outcome")),
        "post_harvest_reason": _first(decision.get("post_harvest_reason"), post.get("reason")),
        "advisory_only": _first(decision.get("advisory_only"), True if decision else None),
        "phase3a_ready": _first(decision.get("phase3a_ready"), ml_shadow.get("phase3a_ready")),
    }


def _xray_payload(payload: Dict[str, Any], dashboard: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    return (
        _d(payload.get("entry_pipeline_xray_summary"))
        or _d(dashboard.get("entry_pipeline_xray"))
        or _module_payload("entry_pipeline_xray", ("status_payload",))
        or _d(state.get("entry_pipeline_xray"))
    )


def compact_daily(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    state = _state_snapshot()
    dashboard = _d(payload.get("dashboard"))
    status = _d(dashboard.get("status"))
    performance = _d(status.get("performance")) or _d(state.get("performance"))
    risk = _d(status.get("risk_controls")) or _d(state.get("risk_controls"))
    journal = _d(_d(state.get("trade_journal")).get("journal_summary"))

    decision = _decision_payload(payload, dashboard, state)
    blocked = (
        _d(payload.get("blocked_entry_reason_audit_summary"))
        or _d(dashboard.get("blocked_entry_reason_audit"))
        or _module_payload("blocked_entry_reason_audit", ("status_payload", "build_payload"))
        or _d(state.get("blocked_entry_reason_audit"))
    )
    xray = _xray_payload(payload, dashboard, state)
    starter = (
        _d(payload.get("risk_on_starter_participation_summary"))
        or _d(dashboard.get("risk_on_starter_participation"))
        or _module_payload("risk_on_starter_participation_valve", ("status_payload",))
        or _d(state.get("risk_on_starter_participation"))
    )
    ml_gate = _module_payload("ml_phase3a_early_paper_gate", ("status_payload",)) or _d(state.get("ml_phase3a_early_paper_gate"))

    composition = (
        _d(xray.get("composition_status"))
        or _d(xray.get("composition"))
        or _d(_d(xray.get("last_cycle")).get("composition"))
        or _d(_d(xray.get("last_meaningful_cycle")).get("composition"))
    )
    current_callable = _d(composition.get("current_callable")) or _d(xray.get("current_callable"))
    inner_callable = _d(composition.get("inner_callable")) or _d(xray.get("wrapped_callable"))
    counters = _d(xray.get("counters"))
    last_error = _d(xray.get("last_error"))
    error = _d(last_error.get("error"))

    positions, positions_present = _positions(state, status, performance)
    trades = state.get("trades")
    account = {
        "cash": _first(status.get("cash"), state.get("cash"), _d(state.get("portfolio")).get("cash")),
        "equity": _first(status.get("equity"), state.get("equity"), _d(state.get("portfolio")).get("equity")),
        "positions": positions,
        "open_positions_count": _first(decision.get("open_positions_count"), journal.get("open_positions_count"), len(positions) if positions_present else None),
        "realized_today": _first(performance.get("realized_pnl_today"), journal.get("realized_today"), state.get("realized_pnl_today")),
        "realized_total": _first(performance.get("realized_pnl_total"), journal.get("realized_total"), state.get("realized_pnl_total")),
        "unrealized_pnl": _first(performance.get("unrealized_pnl"), journal.get("unrealized_pnl"), state.get("unrealized_pnl")),
        "wins_total": _first(performance.get("wins_total"), journal.get("wins_total"), state.get("wins_total")),
        "losses_total": _first(performance.get("losses_total"), journal.get("losses_total"), state.get("losses_total")),
        "execution_rows": _first(journal.get("execution_rows_count"), len(trades) if isinstance(trades, list) else None),
    }
    compact_risk = {
        "self_defense_active": _first(risk.get("self_defense_active"), state.get("self_defense_active")),
        "self_defense_reason": _first(risk.get("self_defense_reason"), state.get("self_defense_reason")),
        "daily_loss_pct": risk.get("daily_loss_pct"),
        "intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
    }

    reason_coverage = _d(blocked.get("reason_coverage"))
    decision_signals = decision.get("signals_found")
    blocker_signals = blocked.get("signals_found")
    scanner = {
        "signals_found": decision_signals,
        "signal_count_source": "decision_audit",
        "blocker_audit_signals_found": blocker_signals,
        "entries_count": decision.get("entries_count"),
        "rejected_signals_count": decision.get("rejected_signals_count"),
        "post_harvest_outcome": decision.get("post_harvest_outcome"),
        "post_harvest_reason": decision.get("post_harvest_reason"),
        "top_blockers": _top_rows(blocked.get("top_blocked_symbol_details") or blocked.get("symbol_reason_rollup"), 5),
        "reason_coverage_pct": _first(reason_coverage.get("actionable_reason_coverage_pct"), blocked.get("actionable_reason_coverage_pct")),
        "missing_reason_rows": _first(blocked.get("missing_reason_detail_count"), reason_coverage.get("rows_missing_reason_detail")),
        "source_mismatch": bool(decision_signals is not None and blocker_signals is not None and decision_signals != blocker_signals),
    }

    next_actions = _l(decision.get("next_actions"))
    ml = {
        "phase3a_ready": bool(_first(ml_gate.get("phase3a_ready"), decision.get("phase3a_ready"), False)),
        "live_authority": "none",
        "advisory_only": _first(decision.get("advisory_only"), True if ml_gate else None),
        "next_action": next_actions[0] if next_actions else ml_gate.get("recommendation"),
    }
    entry_pipeline = {
        "status": _first(composition.get("status"), xray.get("status")),
        "stack_stable": _first(composition.get("stack_stable"), _d(composition.get("latest")).get("stable_fast_path")),
        "recursion_safe": _first(composition.get("recursion_safe"), _d(composition.get("latest")).get("recursion_safe")),
        "direct_core_base": _first(composition.get("direct_core_base"), _d(composition.get("latest")).get("direct_core_base")),
        "participation_valve_chain_cycle_free": _first(composition.get("participation_valve_chain_cycle_free"), _d(_d(composition.get("latest")).get("participation_valve_chain")).get("cycle_free")),
        "current_callable": _callable_name(current_callable),
        "inner_callable": _callable_name(inner_callable),
        "active_callsite_invocations_total": counters.get("active_callsite_invocations_total"),
        "active_callsite_errors_total": counters.get("bottleneck_active_callsite_error_total"),
        "latest_error_timestamp": last_error.get("generated_local"),
        "latest_error_type": error.get("type"),
        "latest_error_message": error.get("message"),
    }
    starter_valve = {
        "status": starter.get("status"),
        "enabled": starter.get("enabled"),
        "patched": starter.get("patched"),
        "telemetry_persisted": starter.get("telemetry_persisted"),
        "last_status": starter.get("last_status"),
        "last_reason": starter.get("last_reason"),
        "last_symbol": starter.get("last_symbol"),
    }

    missing: List[str] = []
    contracts = (
        ("account", account, ("cash", "equity", "open_positions_count", "realized_total", "unrealized_pnl")),
        ("risk", compact_risk, ("self_defense_active", "intraday_drawdown_pct")),
        ("entry_pipeline", entry_pipeline, ("status", "stack_stable", "recursion_safe", "direct_core_base", "current_callable", "inner_callable")),
        ("starter_valve", starter_valve, ("status", "enabled", "patched")),
        ("ml", ml, ("advisory_only", "next_action")),
    )
    for section_name, section, keys in contracts:
        for key in keys:
            if section.get(key) is None:
                missing.append(f"{section_name}.{key}")

    warnings: List[Dict[str, Any]] = []
    for row in _l(payload.get("warnings"))[:3]:
        if isinstance(row, dict):
            warnings.append({"path": row.get("path"), "error": row.get("error"), "details": row.get("details")})
    if missing:
        warnings.append({"path": "/paper/self-check", "error": "compact_source_fields_missing", "details": missing})
    if scanner["source_mismatch"]:
        warnings.append({
            "path": "/paper/self-check",
            "error": "scanner_source_snapshot_mismatch",
            "details": {"decision_audit": decision_signals, "blocker_audit": blocker_signals},
        })

    failed_required = payload.get("failed_required") if isinstance(payload.get("failed_required"), list) else []
    overall = "fail" if failed_required else ("warn" if missing else "pass")
    status_value = "fail" if failed_required else ("warn" if missing else "ok")
    base = _base_url()
    checked_paths = payload.get("checked_paths")
    if not isinstance(checked_paths, list) or not checked_paths:
        checked_paths = ["/health", "/paper/status"]

    return {
        "status": status_value,
        "overall": overall,
        "type": "daily_self_check",
        "version": VERSION,
        "generated_local": payload.get("generated_local"),
        "daily_response_compact": True,
        "terminal_compaction_applied": True,
        "source_contracts_normalized": True,
        "source_fallbacks_used": bool(state),
        "full_diagnostics_url": f"{base}/paper/full-self-check",
        "routine_test_url": f"{base}/paper/self-check",
        "health": {"service": "running" if state else None, "failed_required": failed_required, "checked_paths": checked_paths, "warnings": warnings[:4]},
        "account": account,
        "risk": compact_risk,
        "scanner": scanner,
        "entry_pipeline": entry_pipeline,
        "starter_valve": starter_valve,
        "ml": ml,
        "note": "Use full_diagnostics_url only for fail, missing critical fields, or a newly timestamped runtime error.",
    }


def _terminal_daily_payload() -> Dict[str, Any]:
    return compact_daily(_mobile_base_payload())


def _install_terminal_routes(flask_app: Any) -> None:
    if flask_app is None:
        return
    try:
        from flask import jsonify
        def daily_view():
            return jsonify(_terminal_daily_payload())
        daily_view._daily_self_check_terminal_version = VERSION  # type: ignore[attr-defined]
        for endpoint in ("paper_self_check", "paper_smoke_test"):
            if endpoint in flask_app.view_functions:
                flask_app.view_functions[endpoint] = daily_view
        _TERMINAL_ROUTE_APP_IDS.add(id(flask_app))
    except Exception:
        pass


def apply(core: Any = None) -> Dict[str, Any]:
    global _PATCHED
    flask_app = getattr(core, "app", None) if core is not None else None
    if flask_app is None:
        runtime = _mod()
        flask_app = getattr(runtime, "app", None) if runtime is not None else None
    _install_terminal_routes(flask_app)
    _PATCHED = flask_app is not None
    return {
        "status": "ok" if _PATCHED else "pending",
        "version": VERSION,
        "patched": _PATCHED,
        "terminal_route_installed": bool(flask_app),
        "reporting_only": True,
        "authority_changed": False,
    }


def status_payload() -> Dict[str, Any]:
    return {
        "status": "ok" if _PATCHED else "pending",
        "version": VERSION,
        "patched": _PATCHED,
        "terminal_serializer": True,
        "explicit_allowlist": True,
        "source_contracts_normalized": True,
        "full_diagnostics_preserved": True,
        "authority_changed": False,
        "logic_changed": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
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
    _install_terminal_routes(flask_app)
    apply(core)


try:
    apply()
except Exception:
    pass
