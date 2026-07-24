"""Advisory-only trace for blocker rows that lack terminal reason detail.

The overlay augments the compact paper self-check with a bounded sample describing
which diagnostic producer/source emitted a placeholder. It never synthesizes a
trading reason and does not alter scanner results, entry decisions, thresholds,
risk controls, sizing, orders, executable universe, ML authority, or live authority.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, List

VERSION = "missing-reason-trace-2026-07-24-v1"
_PATCHED = False
_REGISTERED_APP_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "load_state"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _audit_payload(core: Any = None) -> Dict[str, Any]:
    try:
        import blocked_entry_reason_audit as audit
        value = audit.build_payload(core or _mod())
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        return {"trace_error": f"{type(exc).__name__}: {exc}"[:300]}


def _bounded_sample(audit: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    rows = audit.get("missing_reason_rows_sample")
    if not isinstance(rows, list):
        return out
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        out.append({
            "symbol": row.get("symbol"),
            "source": row.get("source"),
            "source_key": row.get("source_key"),
            "placeholder": row.get("reason"),
            "category": row.get("category"),
        })
    return out


def status_payload(core: Any = None) -> Dict[str, Any]:
    global _LAST
    audit = _audit_payload(core)
    sample = _bounded_sample(audit)
    missing_count = audit.get("missing_reason_detail_count")
    payload = {
        "status": "warn" if missing_count else "ok",
        "overall": "warn" if missing_count else "pass",
        "type": "missing_reason_trace_status",
        "version": VERSION,
        "generated_local": _now(),
        "missing_reason_rows": missing_count,
        "missing_reason_symbols": audit.get("missing_reason_detail_symbols") or [],
        "missing_reason_sample": sample,
        "trace_error": audit.get("trace_error"),
        "advisory_only": True,
        "reason_synthesized": False,
        "authority": {
            "changes_scanner_results": False,
            "changes_trading_logic": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_orders": False,
            "changes_executable_universe": False,
            "changes_ml_authority": False,
            "changes_live_authority": False,
        },
        "next_action": "Use symbol/source/source_key to repair the producer contract; do not infer or fabricate a blocker reason.",
    }
    _LAST = payload
    return payload


def install(core: Any = None) -> Dict[str, Any]:
    global _PATCHED
    try:
        import daily_self_check_compactor as compact
    except Exception as exc:
        return {"status": "pending", "version": VERSION, "reason": f"compactor_import_failed: {exc}"[:300]}

    current = getattr(compact, "compact_daily", None)
    if callable(current) and getattr(current, "_missing_reason_trace_version", None) != VERSION:
        original = current

        def wrapped_compact_daily(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
            result = original(payload)
            if not isinstance(result, dict):
                return result
            trace = status_payload(core or _mod())
            scanner = result.get("scanner")
            if isinstance(scanner, dict):
                scanner["missing_reason_symbols"] = trace.get("missing_reason_symbols")
                scanner["missing_reason_sample"] = trace.get("missing_reason_sample")
                scanner["missing_reason_trace_version"] = VERSION
            return result

        wrapped_compact_daily._missing_reason_trace_version = VERSION  # type: ignore[attr-defined]
        wrapped_compact_daily._missing_reason_trace_original = original  # type: ignore[attr-defined]
        compact.compact_daily = wrapped_compact_daily
    _PATCHED = True
    return {"status": "ok", "overall": "pass", "version": VERSION, "patched": True}


def apply(core: Any = None) -> Dict[str, Any]:
    return install(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return install(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/missing-reason-trace-status" not in existing:
        flask_app.add_url_rule(
            "/paper/missing-reason-trace-status",
            "missing_reason_trace_status",
            lambda: jsonify(status_payload(core or _mod())),
        )
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core or _mod())


try:
    install(_mod())
except Exception:
    pass
