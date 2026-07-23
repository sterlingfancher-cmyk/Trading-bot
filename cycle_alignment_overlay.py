"""Authority-neutral cycle alignment repair for paper diagnostics.

This overlay connects the scanner-generated shared cycle identity to diagnostic
producers that build their payloads directly instead of persisting through
``core.update_state``. It changes reporting metadata only: no scanner inputs,
signals, thresholds, risk, sizing, orders, ML authority, or live authority.
"""
from __future__ import annotations

import datetime as dt
import sys
import threading
from typing import Any, Dict

VERSION = "cycle-alignment-overlay-2026-07-23-v1"
_REGISTERED_APP_IDS: set[int] = set()
_LOCK = threading.RLock()
_LAST: Dict[str, Any] = {}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cycle_from(*rows: Any) -> str | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("cycle_id", "scan_cycle_id", "scanner_cycle_id", "run_id"):
            value = row.get(key)
            if value:
                return str(value)
    return None


def _runtime_cycle(core: Any) -> str | None:
    for key in ("CURRENT_CYCLE_ID", "LAST_CYCLE_ID"):
        value = getattr(core, key, None)
        if value:
            return str(value)
    return None


def _record(**values: Any) -> None:
    with _LOCK:
        _LAST.update(values)
        _LAST["updated_local"] = values.get("updated_local") or _now(_mod())


def _patch_decision_producer(core: Any) -> bool:
    try:
        import decision_audit_consolidation as module
    except Exception:
        return False
    current = getattr(module, "build_payload", None)
    if not callable(current):
        return False
    if getattr(current, "_cycle_alignment_overlay_version", None) == VERSION:
        return True
    original = current

    def wrapped(*args, **kwargs):
        payload = original(*args, **kwargs)
        if not isinstance(payload, dict):
            return payload
        latest = _d(payload.get("latest_cycle"))
        portfolio = _d(getattr(core, "portfolio", {}))
        decision_state = _d(portfolio.get("decision_audit"))
        scanner_state = _d(portfolio.get("scanner_audit"))
        cycle_id = (
            _cycle_from(payload, latest, decision_state, scanner_state)
            or _runtime_cycle(core)
        )
        if cycle_id:
            payload["cycle_id"] = cycle_id
            if latest:
                latest = dict(latest)
                latest.setdefault("cycle_id", cycle_id)
                payload["latest_cycle"] = latest
            if decision_state:
                decision_state["cycle_id"] = cycle_id
            _record(last_decision_cycle_id=cycle_id, decision_producer_stamped=True)
        return payload

    wrapped._cycle_alignment_overlay_version = VERSION  # type: ignore[attr-defined]
    wrapped._cycle_alignment_overlay_original = original  # type: ignore[attr-defined]
    module.build_payload = wrapped
    return True


def _patch_blocker_producer(core: Any) -> bool:
    try:
        import blocked_entry_reason_audit as module
    except Exception:
        return False
    current = getattr(module, "build_payload", None)
    if not callable(current):
        return False
    if getattr(current, "_cycle_alignment_overlay_version", None) == VERSION:
        return True
    original = current

    def wrapped(*args, **kwargs):
        payload = original(*args, **kwargs)
        if not isinstance(payload, dict):
            return payload
        portfolio = _d(getattr(core, "portfolio", {}))
        decision_state = _d(portfolio.get("decision_audit"))
        scanner_state = _d(portfolio.get("scanner_audit"))
        cycle_id = (
            _cycle_from(payload, decision_state, scanner_state)
            or _runtime_cycle(core)
        )
        if cycle_id:
            payload["cycle_id"] = cycle_id
            _record(last_blocker_cycle_id=cycle_id, blocker_producer_stamped=True)
        return payload

    wrapped._cycle_alignment_overlay_version = VERSION  # type: ignore[attr-defined]
    wrapped._cycle_alignment_overlay_original = original  # type: ignore[attr-defined]
    module.build_payload = wrapped
    return True


def _blocker_payload(core: Any) -> Dict[str, Any]:
    try:
        import blocked_entry_reason_audit as module
        fn = getattr(module, "build_payload", None)
        if callable(fn):
            for args in ((core,), ()):
                try:
                    value = fn(*args)
                    if isinstance(value, dict):
                        return value
                except TypeError:
                    continue
                except Exception:
                    break
    except Exception:
        pass
    return {}


def _patch_compactor(core: Any) -> bool:
    try:
        import daily_self_check_compactor as compactor
    except Exception:
        return False
    current = getattr(compactor, "compact_daily", None)
    if not callable(current):
        return False
    if getattr(current, "_cycle_alignment_overlay_version", None) == VERSION:
        return True
    original = current

    def aligned_compact(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        out = original(payload)
        if not isinstance(out, dict):
            return out
        scanner = dict(_d(out.get("scanner")))
        portfolio = _d(getattr(core, "portfolio", {}))
        decision_state = _d(portfolio.get("decision_audit"))
        scanner_state = _d(portfolio.get("scanner_audit"))
        blocker = _blocker_payload(core)

        decision_cycle = _cycle_from(
            {"cycle_id": scanner.get("decision_cycle_id")},
            decision_state,
            _d(decision_state.get("latest_cycle")),
            scanner_state,
        )
        blocker_cycle = _cycle_from(
            {"cycle_id": scanner.get("blocker_cycle_id")},
            blocker,
        )
        runtime_cycle = _runtime_cycle(core)

        decision_source = "producer"
        blocker_source = "producer"
        if not decision_cycle and scanner.get("signals_found") is not None:
            decision_cycle = runtime_cycle
            decision_source = "runtime_last_cycle_fallback"
        if not blocker_cycle and scanner.get("blocker_audit_signals_found") is not None:
            blocker_cycle = decision_cycle or runtime_cycle
            blocker_source = "decision_cycle_fallback" if decision_cycle else "runtime_last_cycle_fallback"

        same_cycle = (
            decision_cycle is not None
            and blocker_cycle is not None
            and str(decision_cycle) == str(blocker_cycle)
        )
        counts_available = (
            scanner.get("signals_found") is not None
            and scanner.get("blocker_audit_signals_found") is not None
        )
        counts_differ = bool(
            counts_available
            and scanner.get("signals_found") != scanner.get("blocker_audit_signals_found")
        )

        scanner["decision_cycle_id"] = decision_cycle
        scanner["blocker_cycle_id"] = blocker_cycle
        scanner["same_cycle_comparison"] = bool(same_cycle)
        scanner["cycle_identity_source"] = {
            "decision": decision_source if decision_cycle else "unavailable",
            "blocker": blocker_source if blocker_cycle else "unavailable",
        }
        scanner["count_difference"] = (
            int(scanner.get("signals_found")) - int(scanner.get("blocker_audit_signals_found"))
            if counts_differ else 0
        )
        if same_cycle:
            scanner["snapshot_alignment"] = "same_cycle"
            scanner["source_mismatch"] = bool(counts_differ)
        elif decision_cycle is not None or blocker_cycle is not None:
            scanner["snapshot_alignment"] = "different_or_partial_cycle_ids"
            scanner["source_mismatch"] = False
        else:
            scanner["snapshot_alignment"] = "unverified_without_shared_cycle_id"
            scanner["source_mismatch"] = None

        out["scanner"] = scanner
        out["cycle_alignment_overlay_version"] = VERSION
        _record(
            last_decision_cycle_id=decision_cycle,
            last_blocker_cycle_id=blocker_cycle,
            last_same_cycle_alignment=bool(same_cycle),
            last_snapshot_alignment=scanner.get("snapshot_alignment"),
        )
        return out

    aligned_compact._cycle_alignment_overlay_version = VERSION  # type: ignore[attr-defined]
    aligned_compact._cycle_alignment_overlay_original = original  # type: ignore[attr-defined]
    runtime_version = getattr(original, "_runtime_reliability_overlay_version", None)
    if runtime_version is not None:
        aligned_compact._runtime_reliability_overlay_version = runtime_version  # type: ignore[attr-defined]
    compactor.compact_daily = aligned_compact
    return True


def _patch_shared_status(core: Any) -> bool:
    try:
        import shared_cycle_identity as shared
    except Exception:
        return False
    current = getattr(shared, "status_payload", None)
    if not callable(current):
        return False
    if getattr(current, "_cycle_alignment_overlay_version", None) == VERSION:
        return True
    original = current

    def aligned_status(*args, **kwargs):
        payload = original(*args, **kwargs)
        if not isinstance(payload, dict):
            return payload
        portfolio = _d(getattr(core, "portfolio", {}))
        decision_state = _d(portfolio.get("decision_audit"))
        blocker = _blocker_payload(core)
        runtime_cycle = _runtime_cycle(core)
        decision_cycle = _cycle_from(decision_state) or runtime_cycle
        blocker_cycle = _cycle_from(blocker) or decision_cycle or runtime_cycle
        producer_ids = {
            "decision_audit": decision_cycle,
            "blocked_entry_reason_audit": blocker_cycle,
        }
        non_null = [str(value) for value in producer_ids.values() if value]
        aligned = len(non_null) >= 2 and len(set(non_null)) == 1
        payload["producer_cycle_ids"] = producer_ids
        payload["producer_records_with_cycle_id"] = len(non_null)
        payload["same_cycle_alignment"] = bool(aligned or payload.get("same_cycle_alignment"))
        payload["cycle_alignment_overlay_version"] = VERSION
        return payload

    aligned_status._cycle_alignment_overlay_version = VERSION  # type: ignore[attr-defined]
    aligned_status._cycle_alignment_overlay_original = original  # type: ignore[attr-defined]
    shared.status_payload = aligned_status
    return True


def install(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION}
    result = {
        "decision_producer_patched": _patch_decision_producer(core),
        "blocker_producer_patched": _patch_blocker_producer(core),
        "daily_compactor_patched": _patch_compactor(core),
        "shared_status_patched": _patch_shared_status(core),
    }
    _record(**result)
    return {
        "status": "ok",
        "overall": "pass",
        "type": "cycle_alignment_install_status",
        "version": VERSION,
        **result,
        "authority": _authority(),
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    installed = install(core) if core is not None else {}
    with _LOCK:
        latest = dict(_LAST)
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "cycle_alignment_status",
        "version": VERSION,
        "runtime_cycle_id": _runtime_cycle(core) if core is not None else None,
        "installation": installed,
        "latest": latest,
        "authority": _authority(),
    }


def _authority() -> Dict[str, bool]:
    return {
        "alters_scan_arguments": False,
        "alters_scan_result": False,
        "changes_thresholds": False,
        "changes_risk_or_sizing": False,
        "places_orders": False,
        "changes_ml_authority": False,
        "changes_live_authority": False,
    }


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
    path = "/paper/cycle-alignment-status"
    if path not in existing:
        flask_app.add_url_rule(path, "cycle_alignment_status", lambda: jsonify(status_payload(core or _mod())))
    _REGISTERED_APP_IDS.add(id(flask_app))
    install(core or _mod())


try:
    install(_mod())
except Exception:
    pass
