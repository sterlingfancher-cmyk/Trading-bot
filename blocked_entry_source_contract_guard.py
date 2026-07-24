from __future__ import annotations

import datetime as dt
import functools
import sys
from typing import Any, Dict, List

VERSION = "blocked-entry-source-contract-2026-07-24-v1"
_APPLIED: set[int] = set()
_LAST: Dict[str, Any] = {}

# These keys describe candidates that were reviewed or selected. They are not
# evidence that an entry was blocked and therefore must not be included in
# blocked-entry reason coverage calculations.
NON_BLOCKER_SOURCE_KEYS = {
    "top_candidates_reviewed",
    "candidates",
    "selected_candidate",
}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    try:
        import blocked_entry_reason_audit as audit
    except Exception as exc:
        return {"status": "not_applied", "version": VERSION, "reason": f"audit_import_failed:{type(exc).__name__}"}

    if id(audit) in _APPLIED:
        return {"status": "ok", "version": VERSION, "already_applied": True}

    original = getattr(audit, "_extract_rows_from_section", None)
    if not callable(original):
        return {"status": "not_applied", "version": VERSION, "reason": "extractor_missing"}
    if getattr(original, "_blocked_entry_source_contract_guard", False):
        _APPLIED.add(id(audit))
        return {"status": "ok", "version": VERSION, "already_wrapped": True}

    @functools.wraps(original)
    def wrapped_extract(source: str, section: Dict[str, Any]) -> List[Dict[str, Any]]:
        global _LAST
        rows = original(source, section)
        kept: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        for row in rows or []:
            source_key = str((row or {}).get("source_key") or "") if isinstance(row, dict) else ""
            if source_key in NON_BLOCKER_SOURCE_KEYS:
                if len(excluded) < 10:
                    excluded.append({
                        "symbol": str((row or {}).get("symbol") or "").upper(),
                        "source": (row or {}).get("source"),
                        "source_key": source_key,
                        "reason": "informational_candidate_row_not_blocker_evidence",
                    })
                continue
            kept.append(row)
        if excluded:
            _LAST = {
                "status": "ok",
                "version": VERSION,
                "generated_local": _now(core or _mod()),
                "source": source,
                "excluded_count": len(excluded),
                "excluded_sample": excluded,
                "trading_behavior_changed": False,
            }
        return kept

    wrapped_extract._blocked_entry_source_contract_guard = True
    wrapped_extract._blocked_entry_source_contract_guard_original = original
    audit._extract_rows_from_section = wrapped_extract
    try:
        audit.BLOCKED_ENTRY_SOURCE_CONTRACT_GUARD_VERSION = VERSION
    except Exception:
        pass
    _APPLIED.add(id(audit))
    return {
        "status": "ok",
        "version": VERSION,
        "patched": ["blocked_entry_reason_audit._extract_rows_from_section"],
        "excluded_source_keys": sorted(NON_BLOCKER_SOURCE_KEYS),
        "trading_behavior_changed": False,
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "blocked_entry_source_contract_guard_status",
        "version": VERSION,
        "generated_local": _now(core or _mod()),
        "installed": bool(_APPLIED),
        "excluded_source_keys": sorted(NON_BLOCKER_SOURCE_KEYS),
        "last_exclusion": dict(_LAST),
        "diagnostic_only": True,
        "scanner_results_changed": False,
        "strategy_changed": False,
        "risk_changed": False,
        "order_behavior_changed": False,
        "ml_authority_changed": False,
        "live_authority_changed": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/blocked-entry-source-contract-status" in existing:
        return
    from flask import jsonify
    flask_app.add_url_rule(
        "/paper/blocked-entry-source-contract-status",
        "blocked_entry_source_contract_status",
        lambda: jsonify(status_payload(core)),
    )
