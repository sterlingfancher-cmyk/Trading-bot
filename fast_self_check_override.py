from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict

VERSION = "fast-self-check-override-2026-08-03-v5-all-in-one"
_PATCHED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "portfolio"):
            return module
    return None


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _performance(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    return _dict(portfolio.get("performance"))


def _time_key(value: Any) -> float:
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return 0.0
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return dt.datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        try:
            return float(text)
        except Exception:
            return 0.0


def _error_freshness(last_error: Any, last_attempt: Any, last_run: Any, last_success: Any) -> Dict[str, Any]:
    error_present = bool(last_error)
    attempt_key = _time_key(last_attempt)
    run_key = _time_key(last_run)
    success_key = _time_key(last_success)
    recovery_key = max(run_key, success_key)
    superseded = bool(error_present and attempt_key > 0.0 and recovery_key >= attempt_key)
    active = bool(error_present and not superseded)
    return {
        "present": error_present,
        "active": active,
        "stale": superseded,
        "state": "active" if active else "historical_superseded" if superseded else "none",
        "superseding_run_or_success": bool(superseded),
    }


def _check_result(name: str, payload: Dict[str, Any], passed: bool, details: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": name,
        "overall": "pass" if passed else "warn",
        "version": payload.get("version"),
        **details,
    }


def _component_error(name: str, exc: Exception) -> Dict[str, Any]:
    return {
        "name": name,
        "overall": "warn",
        "error": f"{type(exc).__name__}: {exc}",
    }


def _component_checks(core: Any) -> Dict[str, Dict[str, Any]]:
    checks: Dict[str, Dict[str, Any]] = {}

    try:
        import scanner_runtime_contract as scanner_contract

        row = _dict(scanner_contract.status_payload(core))
        after = _dict(row.get("after"))
        passed = bool(
            row.get("overall") == "pass"
            and after.get("ordered")
            and not after.get("cycle_detected")
            and not after.get("truncated")
            and int(after.get("opening_surge_count") or 0) == 1
            and int(after.get("breakout_count") or 0) == 1
            and int(after.get("market_participation_count") or 0) == 1
        )
        checks["scanner_stack"] = _check_result(
            "scanner_stack",
            row,
            passed,
            {
                "ordered": bool(after.get("ordered")),
                "cycle_detected": bool(after.get("cycle_detected")),
                "truncated": bool(after.get("truncated")),
                "opening_surge_count": after.get("opening_surge_count"),
                "breakout_count": after.get("breakout_count"),
                "market_participation_count": after.get("market_participation_count"),
                "rebuild_changed": bool(_dict(row.get("rebuild")).get("changed")),
            },
        )
    except Exception as exc:
        checks["scanner_stack"] = _component_error("scanner_stack", exc)

    try:
        import entry_pipeline_xray_bear_ownership_guard as atomic_guard

        row = _dict(atomic_guard.status_payload(core))
        stack = _dict(row.get("stack_contract"))
        counts = _dict(stack.get("wrapper_counts")) or _dict(_dict(row.get("last_install")).get("wrapper_counts"))
        passed = bool(
            row.get("overall") == "pass"
            and row.get("owned")
            and row.get("valid_xray_below_bear")
            and int(counts.get("bear_wrapper_count") or 0) == 1
            and int(counts.get("xray_wrapper_count") or 0) == 1
        )
        checks["entry_stack_ownership"] = _check_result(
            "entry_stack_ownership",
            row,
            passed,
            {
                "owned": bool(row.get("owned")),
                "valid_xray_below_bear": bool(row.get("valid_xray_below_bear")),
                "bear_wrapper_count": counts.get("bear_wrapper_count"),
                "xray_wrapper_count": counts.get("xray_wrapper_count"),
                "entry_guard_active": bool(stack.get("entry_guard_active")),
                "atomic_repair_reason": _dict(_dict(row.get("last_install")).get("atomic_repair")).get("reason"),
            },
        )
    except Exception as exc:
        checks["entry_stack_ownership"] = _component_error("entry_stack_ownership", exc)

    try:
        import entry_pipeline_composition_guard as composition_guard

        row = _dict(composition_guard.status_payload(core))
        passed = bool(
            row.get("overall") == "pass"
            and row.get("stack_stable")
            and row.get("recursion_safe")
            and row.get("participation_valve_chain_cycle_free")
            and row.get("direct_core_base")
        )
        callable_row = _dict(row.get("participation_valve_callable"))
        checks["entry_composition"] = _check_result(
            "entry_composition",
            row,
            passed,
            {
                "stack_stable": bool(row.get("stack_stable")),
                "recursion_safe": bool(row.get("recursion_safe")),
                "direct_core_base": bool(row.get("direct_core_base")),
                "participation_chain_cycle_free": bool(row.get("participation_valve_chain_cycle_free")),
                "participation_valve_module": callable_row.get("module"),
                "participation_valve_name": callable_row.get("name"),
            },
        )
    except Exception as exc:
        checks["entry_composition"] = _component_error("entry_composition", exc)

    try:
        import bear_recovery_stack_contract as bear_contract

        row = _dict(bear_contract.status_payload(core))
        counts = _dict(row.get("wrapper_counts"))
        passed = bool(
            row.get("overall") == "pass"
            and row.get("owned")
            and row.get("entry_guard_active")
            and int(counts.get("bear_wrapper_count") or 0) == 1
            and int(counts.get("xray_wrapper_count") or 0) == 1
        )
        checks["bear_recovery_stack"] = _check_result(
            "bear_recovery_stack",
            row,
            passed,
            {
                "owned": bool(row.get("owned")),
                "entry_guard_active": bool(row.get("entry_guard_active")),
                "bear_wrapper_count": counts.get("bear_wrapper_count"),
                "xray_wrapper_count": counts.get("xray_wrapper_count"),
            },
        )
    except Exception as exc:
        checks["bear_recovery_stack"] = _component_error("bear_recovery_stack", exc)

    try:
        import neutral_momentum_starter_extension as neutral_starter

        row = _dict(neutral_starter.status_payload(core))
        settings = _dict(row.get("settings"))
        authority = _dict(row.get("authority"))
        last = _dict(row.get("last_evaluation"))
        staged = _dict(last.get("staged_gate"))
        passed = bool(row.get("overall") == "pass" and row.get("active"))
        checks["neutral_starter"] = _check_result(
            "neutral_starter",
            row,
            passed,
            {
                "active": bool(row.get("active")),
                "max_entries_per_day": settings.get("max_entries_per_day"),
                "max_entries_per_cycle": settings.get("max_entries_per_cycle"),
                "max_open_positions": settings.get("max_open_positions"),
                "minimum_seconds_between_entries": settings.get("minimum_seconds_between_entries"),
                "maximum_combined_exposure_pct": settings.get("maximum_combined_exposure_pct"),
                "neutral_only_staging": bool(authority.get("neutral_stage_applies_only_in_neutral_mode")),
                "last_gate_status": staged.get("status"),
                "last_gate_reason": staged.get("reason"),
            },
        )
    except Exception as exc:
        checks["neutral_starter"] = _component_error("neutral_starter", exc)

    return checks


def build_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    portfolio = _dict(getattr(core, "portfolio", {})) if core is not None else {}
    auto = _dict(portfolio.get("auto_runner"))
    perf = _performance(portfolio)
    risk = _dict(portfolio.get("risk_controls"))
    feedback = _dict(portfolio.get("feedback_loop"))
    positions = _dict(portfolio.get("positions"))
    trades = portfolio.get("trades")
    scanner = _dict(portfolio.get("scanner_audit"))
    decision = _dict(portfolio.get("decision_audit"))
    last_error = auto.get("last_error")

    last_attempt = auto.get("last_attempt_local") or auto.get("last_attempt_ts")
    last_run = auto.get("last_run_local") or auto.get("last_run_ts")
    last_success = auto.get("last_successful_run_local") or auto.get("last_successful_run_ts")
    last_skip = auto.get("last_skip_local") or auto.get("last_skip_ts")
    freshness = _error_freshness(last_error, last_attempt, last_run, last_success)
    recursion_text = "recursion" in str(last_error or "").lower()

    components = _component_checks(core) if core is not None else {}
    failing_components = [name for name, row in components.items() if row.get("overall") != "pass"]
    component_pass_count = sum(1 for row in components.values() if row.get("overall") == "pass")

    base_failures = []
    if core is None:
        base_failures.append("core_missing")
    if freshness["active"]:
        base_failures.append("active_auto_runner_error")
    if bool(risk.get("halted")):
        base_failures.append("risk_halted")
    if bool(risk.get("self_defense_active")):
        base_failures.append("self_defense_active")
    if auto.get("enabled") is False:
        base_failures.append("auto_runner_disabled")
    if auto.get("thread_started") is False:
        base_failures.append("auto_runner_thread_not_started")

    all_passed = bool(core is not None and not base_failures and not failing_components)

    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if all_passed else "warn" if core is not None else "pending",
        "type": "all_in_one_self_check",
        "version": VERSION,
        "generated_local": _now(core),
        "validation_mode": "bounded_runtime_component_validation",
        "one_test_complete": bool(core is not None),
        "summary": {
            "components_checked": len(components),
            "components_passed": component_pass_count,
            "components_warned": len(failing_components),
            "failing_components": failing_components,
            "base_failures": base_failures,
            "next_action": "none" if all_passed else "inspect_only_the_named_warning_component",
        },
        "account": {
            "cash": portfolio.get("cash"),
            "equity": portfolio.get("equity"),
            "positions": list(positions.keys()),
            "open_positions_count": len(positions),
            "realized_today": perf.get("realized_pnl_today"),
            "realized_total": perf.get("realized_pnl_total"),
            "unrealized_pnl": perf.get("unrealized_pnl"),
            "wins_total": perf.get("wins_total"),
            "losses_total": perf.get("losses_total"),
            "execution_rows": len(trades) if isinstance(trades, list) else None,
        },
        "auto_runner": {
            "enabled": auto.get("enabled"),
            "thread_started": auto.get("thread_started"),
            "interval_seconds": auto.get("interval_seconds"),
            "last_attempt": last_attempt,
            "last_attempt_source": auto.get("last_attempt_source"),
            "last_run": last_run,
            "last_run_source": auto.get("last_run_source"),
            "last_success": last_success,
            "last_success_source": auto.get("last_successful_run_source"),
            "last_skip": last_skip,
            "last_skip_reason": auto.get("last_skip_reason"),
            "market_open_now": auto.get("market_open_now"),
            "last_error": last_error,
            "last_error_present": freshness["present"],
            "last_error_active": freshness["active"],
            "last_error_stale": freshness["stale"],
            "last_error_state": freshness["state"],
            "last_error_superseded_by_success": freshness["superseding_run_or_success"],
            "last_recovered_error": auto.get("last_recovered_error"),
            "last_recovered_error_local": auto.get("last_recovered_error_local"),
        },
        "risk": {
            "halted": risk.get("halted"),
            "halt_reason": risk.get("halt_reason"),
            "self_defense_active": risk.get("self_defense_active"),
            "self_defense_reason": risk.get("self_defense_reason"),
            "daily_loss_pct": risk.get("daily_loss_pct"),
            "intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
            "realized_loss_pct": risk.get("realized_loss_pct"),
            "controlled_restart": feedback.get("controlled_restart", {}),
        },
        "scanner": {
            "signals_found": scanner.get("signals_found") or decision.get("signals_found"),
            "entries_count": decision.get("entries_count"),
            "last_updated_local": scanner.get("last_updated_local"),
            "last_cycle_source": scanner.get("last_cycle_source"),
        },
        "entry_pipeline": {
            "scanner_callable": getattr(getattr(core, "scan_signals", None), "__qualname__", None) if core is not None else None,
            "entry_callable": getattr(getattr(core, "try_entries_and_rotations", None), "__qualname__", None) if core is not None else None,
            "recursion_error_active": bool(recursion_text and freshness["active"]),
            "recursion_error_historical": bool(recursion_text and freshness["stale"]),
        },
        "component_checks": components,
        "links": {
            "routine_test": "/paper/self-check",
            "full_diagnostics": "/paper/full-self-check",
            "status": "/paper/status",
        },
        "authority": {
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_ml_authority": False,
            "changes_live_authority": False,
            "may_repair_runtime_composition_or_ownership": True,
            "trading_authority_unchanged": True,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    flask_app = getattr(core, "app", None) if core is not None else None
    if flask_app is None:
        return {"status": "pending", "version": VERSION}

    from flask import jsonify

    def fast_view():
        return jsonify(build_payload(core or _mod()))

    fast_view._fast_self_check_override_version = VERSION
    for endpoint in ("paper_self_check", "paper_smoke_test"):
        if endpoint in flask_app.view_functions:
            flask_app.view_functions[endpoint] = fast_view
    _PATCHED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "patched": True}


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    flask_app = getattr(core, "app", None) if core is not None else None
    view = getattr(flask_app, "view_functions", {}).get("paper_self_check") if flask_app is not None else None
    return {
        "status": "ok" if getattr(view, "_fast_self_check_override_version", None) == VERSION else "pending",
        "version": VERSION,
        "patched": getattr(view, "_fast_self_check_override_version", None) == VERSION,
        "routine_test": "/paper/self-check",
        "all_in_one": True,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/fast-self-check-status" not in existing:
        flask_app.add_url_rule(
            "/paper/fast-self-check-status",
            "fast_self_check_status",
            lambda: jsonify(status_payload(core or _mod())),
        )
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
