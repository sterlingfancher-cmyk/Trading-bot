"""One-link check patch.

Keeps the user's daily testing flow to one URL: /paper/self-check.
Adds journal truth, state/journal reconciliation guard, classic signal mode,
intraday timing, position-quality, benchmark comparison, market participation
status, and risk-on entry diagnostics into the light self-check set without
requiring Sterling to manually test more endpoints after each deploy.

This patch also promotes the state/journal guard into the operator summary so a
repaired or mismatched state is obvious from the one-link check instead of being
hidden in the raw result rows.
"""
from __future__ import annotations

from typing import Any, Dict, List

VERSION = "one-link-state-journal-guard-truth-2026-05-13"


def _safe_dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _safe_list(obj: Any) -> List[Any]:
    return obj if isinstance(obj, list) else []


def _add_endpoint(light, endpoint, after_path=None):
    if not isinstance(light, list):
        return
    if any(isinstance(item, dict) and item.get("path") == endpoint["path"] for item in light):
        return
    insert_at = len(light)
    if after_path:
        for idx, item in enumerate(light):
            if isinstance(item, dict) and item.get("path") == after_path:
                insert_at = idx + 1
                break
    light.insert(insert_at, endpoint)


def _compact_state_journal_guard(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": payload.get("status"),
        "type": payload.get("type"),
        "version": payload.get("version"),
        "repair_version": payload.get("repair_version"),
        "generated_local": payload.get("generated_local"),
        "active": payload.get("active"),
        "reconciliation_status": payload.get("reconciliation_status"),
        "safe_to_trade_guarded_symbols": payload.get("safe_to_trade_guarded_symbols"),
        "blocked_symbols": payload.get("blocked_symbols"),
        "repairable_symbols": payload.get("repairable_symbols"),
        "mismatch_count": payload.get("mismatch_count"),
        "operator_message": payload.get("operator_message"),
        "recommended_actions": payload.get("recommended_actions"),
        "repair_endpoint": payload.get("repair_endpoint"),
    }


def _extract_guard_from_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in results:
        if row.get("path") == "/paper/state-journal-guard-status":
            compact = _safe_dict(row.get("compact"))
            if compact:
                return compact
    return {}


def _postprocess_guard_truth(payload: Dict[str, Any]) -> Dict[str, Any]:
    results = _safe_list(payload.get("results"))
    guard = _extract_guard_from_results(results)
    if not guard:
        return payload

    dashboard = _safe_dict(payload.get("dashboard"))
    dashboard["state_journal_guard"] = guard
    payload["dashboard"] = dashboard
    payload["state_journal_guard_summary"] = guard

    operator = _safe_dict(payload.get("operator_summary"))
    operator.update({
        "state_journal_guard_active": bool(guard.get("active")),
        "state_journal_guard_status": guard.get("reconciliation_status"),
        "guarded_blocked_symbols": guard.get("blocked_symbols") or [],
        "safe_to_trade_guarded_symbols": guard.get("safe_to_trade_guarded_symbols"),
        "state_journal_guard_message": guard.get("operator_message"),
    })
    payload["operator_summary"] = operator

    if guard.get("active"):
        payload["overall"] = "warn"
        if payload.get("status") == "ok":
            payload["status"] = "warn"
        warnings = _safe_list(payload.get("warnings"))
        warnings.append({
            "path": "/paper/state-journal-guard-status",
            "status_code": 200,
            "error": "state/journal mismatch guard active; same-symbol trading is blocked until repaired",
            "blocked_symbols": guard.get("blocked_symbols") or [],
        })
        payload["warnings"] = warnings
    return payload


def _patch_self_check_guard_truth(self_check_module: Any) -> None:
    if getattr(self_check_module, "_one_link_guard_truth_patched", False):
        return

    original_compact = getattr(self_check_module, "_compact_payload", None)
    original_run = getattr(self_check_module, "run_self_check", None)
    if not callable(original_compact) or not callable(original_run):
        return

    def compact_payload(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        compact = original_compact(path, payload)
        if str(path) == "/paper/state-journal-guard-status":
            compact.update(_compact_state_journal_guard(_safe_dict(payload)))
        return compact

    def run_self_check(flask_app: Any, mode: str = "light") -> Dict[str, Any]:
        payload = original_run(flask_app, mode=mode)
        if isinstance(payload, dict):
            return _postprocess_guard_truth(payload)
        return payload

    self_check_module._compact_payload = compact_payload
    self_check_module.run_self_check = run_self_check
    self_check_module._one_link_guard_truth_patched = True


def apply(self_check_module=None):
    try:
        if self_check_module is None:
            import self_check as self_check_module  # type: ignore[no-redef]
        light = getattr(self_check_module, "LIGHT_ENDPOINTS", None)
        _add_endpoint(light, {"path": "/paper/journal-truth-status", "category": "journal", "required": True}, after_path="/paper/trade-event-hook-status")
        _add_endpoint(light, {"path": "/paper/state-journal-guard-status", "category": "journal", "required": True}, after_path="/paper/journal-truth-status")
        _add_endpoint(light, {"path": "/paper/classic-signal-status", "category": "risk", "required": True}, after_path="/paper/risk-improvement-status")
        _add_endpoint(light, {"path": "/paper/intraday-timing-status", "category": "risk", "required": True}, after_path="/paper/classic-signal-status")
        _add_endpoint(light, {"path": "/paper/position-quality-status", "category": "risk", "required": True}, after_path="/paper/intraday-timing-status")
        _add_endpoint(light, {"path": "/paper/benchmark-comparison", "category": "benchmark", "required": True}, after_path="/paper/position-quality-status")
        _add_endpoint(light, {"path": "/paper/market-participation-status", "category": "benchmark", "required": True}, after_path="/paper/benchmark-comparison")
        _add_endpoint(light, {"path": "/paper/risk-on-entry-diagnostic", "category": "benchmark", "required": True}, after_path="/paper/market-participation-status")
        _patch_self_check_guard_truth(self_check_module)
        return {
            "status": "ok",
            "version": VERSION,
            "journal_truth_in_self_check": True,
            "state_journal_guard_in_self_check": True,
            "state_journal_guard_truth_in_operator_summary": True,
            "classic_signal_in_self_check": True,
            "intraday_timing_in_self_check": True,
            "position_quality_in_self_check": True,
            "benchmark_comparison_in_self_check": True,
            "market_participation_in_self_check": True,
            "risk_on_entry_diagnostic_in_self_check": True,
            "single_best_link": "/paper/self-check",
        }
    except Exception as exc:
        return {
            "status": "error",
            "version": VERSION,
            "journal_truth_in_self_check": False,
            "state_journal_guard_in_self_check": False,
            "state_journal_guard_truth_in_operator_summary": False,
            "classic_signal_in_self_check": False,
            "intraday_timing_in_self_check": False,
            "position_quality_in_self_check": False,
            "benchmark_comparison_in_self_check": False,
            "market_participation_in_self_check": False,
            "risk_on_entry_diagnostic_in_self_check": False,
            "error": str(exc),
        }


def register_routes(flask_app=None, module=None):
    # Nothing new to register. This module patches self_check's existing route list.
    try:
        import self_check
        return apply(self_check)
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": str(exc)}
