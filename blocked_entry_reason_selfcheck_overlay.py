"""Surface blocked-entry reason audit inside /paper/self-check.

This is a mobile-safe overlay. It wraps self_check.run_self_check and injects the
blocked-entry reason audit summary directly into dashboard/operator_summary.
It does not call heavy routes, place trades, lower thresholds, or alter authority.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, List

VERSION = "blocked-entry-reason-selfcheck-overlay-2026-06-30-v2-reason-coverage"
PATCHED_SELF_CHECK_IDS: set[int] = set()
REGISTERED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _list(obj: Any) -> List[Any]:
    return obj if isinstance(obj, list) else []


def _compact_audit(audit: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": audit.get("status"),
        "overall": audit.get("overall"),
        "type": audit.get("type"),
        "version": audit.get("version"),
        "generated_local": audit.get("generated_local"),
        "advisory_only": audit.get("advisory_only"),
        "authority_changed": audit.get("authority_changed"),
        "signals_found": audit.get("signals_found"),
        "blocked_entries_count": audit.get("blocked_entries_count"),
        "visible_blocked_rows_count": audit.get("visible_blocked_rows_count"),
        "reason_coverage": audit.get("reason_coverage") or {},
        "missing_reason_detail_count": audit.get("missing_reason_detail_count"),
        "missing_reason_detail_symbols": audit.get("missing_reason_detail_symbols") or [],
        "top_blocked_symbols": audit.get("top_blocked_symbols") or [],
        "top_categories": audit.get("top_categories") or [],
        "top_reasons": audit.get("top_reasons") or [],
        "top_buckets": audit.get("top_buckets") or [],
        "symbol_reason_rollup": audit.get("symbol_reason_rollup") or [],
        "watched_momentum_symbols_seen": audit.get("watched_momentum_symbols_seen") or [],
        "watched_momentum_symbols_blocked": audit.get("watched_momentum_symbols_blocked") or [],
        "no_trade_read": audit.get("no_trade_read"),
        "next_actions": audit.get("next_actions") or [],
    }


def _build_audit(core: Any = None) -> Dict[str, Any]:
    try:
        import blocked_entry_reason_audit
        fn = getattr(blocked_entry_reason_audit, "build_payload", None)
        if callable(fn):
            return _compact_audit(_dict(fn(core or _mod())))
    except Exception as exc:
        return {
            "status": "warn",
            "overall": "warn",
            "type": "blocked_entry_reason_audit_status",
            "version": VERSION,
            "generated_local": _now(core),
            "advisory_only": True,
            "authority_changed": False,
            "error": f"blocked_entry_reason_audit_unavailable:{type(exc).__name__}",
        }
    return {}


def inject(payload: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    audit = _build_audit(core)
    if not audit:
        return payload

    dashboard = _dict(payload.get("dashboard"))
    dashboard["blocked_entry_reason_audit"] = audit
    payload["dashboard"] = dashboard
    payload["blocked_entry_reason_audit_summary"] = audit

    coverage = _dict(audit.get("reason_coverage"))
    operator = _dict(payload.get("operator_summary"))
    operator.update({
        "blocked_entry_reason_audit_status": audit.get("status"),
        "blocked_entry_no_trade_read": audit.get("no_trade_read"),
        "blocked_entry_top_categories": audit.get("top_categories") or [],
        "blocked_entry_top_reasons": audit.get("top_reasons") or [],
        "blocked_entry_top_symbols": audit.get("top_blocked_symbols") or [],
        "blocked_entry_symbol_reason_rollup": audit.get("symbol_reason_rollup") or [],
        "blocked_entry_reason_coverage_pct": coverage.get("actionable_reason_coverage_pct"),
        "blocked_entry_rows_missing_reason_detail": coverage.get("rows_missing_reason_detail"),
        "blocked_entry_missing_reason_symbols": audit.get("missing_reason_detail_symbols") or [],
        "watched_momentum_symbols_seen": audit.get("watched_momentum_symbols_seen") or [],
        "watched_momentum_symbols_blocked": audit.get("watched_momentum_symbols_blocked") or [],
    })
    payload["operator_summary"] = operator

    # Keep overall pass if the audit is advisory-only and healthy. Only warn if the audit itself warns.
    if audit.get("overall") == "warn" or audit.get("status") == "warn":
        if payload.get("overall") != "fail":
            payload["overall"] = "warn"
        if payload.get("status") == "ok":
            payload["status"] = "warn"
        warnings = _list(payload.get("warnings"))
        warnings.append({
            "path": "/paper/blocked-entry-reason-audit-status",
            "status_code": 200,
            "error": "blocked entry reason audit warning",
            "details": audit.get("error"),
        })
        payload["warnings"] = warnings

    return payload


def apply(self_check_module: Any = None, core: Any = None) -> Dict[str, Any]:
    try:
        if self_check_module is None:
            import self_check as self_check_module  # type: ignore[no-redef]
        if id(self_check_module) in PATCHED_SELF_CHECK_IDS:
            return {"status": "ok", "version": VERSION, "already_patched": True, "advisory_only": True}

        original_run = getattr(self_check_module, "run_self_check", None)
        if not callable(original_run):
            return {"status": "not_applied", "version": VERSION, "reason": "run_self_check_missing"}

        def patched_run_self_check(flask_app: Any, mode: str = "light") -> Dict[str, Any]:
            result = original_run(flask_app, mode=mode)
            if isinstance(result, dict):
                return inject(result, core or _mod())
            return result

        patched_run_self_check._blocked_entry_reason_overlay_patched = True  # type: ignore[attr-defined]
        self_check_module.run_self_check = patched_run_self_check
        PATCHED_SELF_CHECK_IDS.add(id(self_check_module))
        return {
            "status": "ok",
            "version": VERSION,
            "advisory_only": True,
            "authority_changed": False,
            "self_check_injection_active": True,
            "dashboard_key": "blocked_entry_reason_audit",
            "operator_summary_keys": [
                "blocked_entry_no_trade_read",
                "blocked_entry_top_categories",
                "blocked_entry_top_reasons",
                "blocked_entry_top_symbols",
                "blocked_entry_symbol_reason_rollup",
                "blocked_entry_reason_coverage_pct",
                "blocked_entry_rows_missing_reason_detail",
                "blocked_entry_missing_reason_symbols",
                "watched_momentum_symbols_seen",
                "watched_momentum_symbols_blocked",
            ],
        }
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": str(exc)}


def register_routes(flask_app: Any = None, core: Any = None) -> Dict[str, Any]:
    try:
        import self_check
        result = apply(self_check, core or _mod())
    except Exception as exc:
        result = {"status": "error", "version": VERSION, "error": str(exc)}

    if flask_app is not None and id(flask_app) not in REGISTERED_APP_IDS:
        from flask import jsonify
        try:
            existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        except Exception:
            existing = set()
        if "/paper/blocked-entry-reason-selfcheck-overlay-status" not in existing:
            flask_app.add_url_rule(
                "/paper/blocked-entry-reason-selfcheck-overlay-status",
                "blocked_entry_reason_selfcheck_overlay_status",
                lambda: jsonify(apply(self_check, core or _mod())),
            )
        REGISTERED_APP_IDS.add(id(flask_app))
    return result
