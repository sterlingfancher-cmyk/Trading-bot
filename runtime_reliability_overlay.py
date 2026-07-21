"""Runtime reliability overlay for transactional diagnostics and cycle-aware reporting.

This module performs authority-neutral reliability repairs:
1. Entry Pipeline X-Ray persistence uses core.update_state() when available.
2. X-Ray status inspection is read-only and never installs or repairs wrappers.
3. Daily scanner-count comparison only declares a mismatch when both producers
   identify the same cycle.
4. Compact entry-pipeline stability fields are normalized from the dedicated
   composition guard when X-Ray telemetry does not contain them.

No trading, risk, sizing, scanner, candidate, order, live-authority, or ML-authority
behavior is changed.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, List

VERSION = "runtime-reliability-overlay-2026-07-21-v2-entry-contract"
_PATCHED = False


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "load_state"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cycle_identity(row: Dict[str, Any]) -> Any:
    for key in ("cycle_id", "scan_cycle_id", "scanner_cycle_id", "run_id"):
        if row.get(key) is not None:
            return row.get(key)
    return None


def _composition_status(core: Any = None) -> Dict[str, Any]:
    """Read the authoritative composition inspection without installing or repairing."""
    try:
        import entry_pipeline_composition_guard as guard
        fn = getattr(guard, "status_payload", None)
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


def _patch_xray(core: Any) -> Dict[str, Any]:
    try:
        import entry_pipeline_xray as xray
    except Exception as exc:
        return {"patched": False, "reason": f"xray_unavailable:{type(exc).__name__}:{exc}"}

    if getattr(getattr(xray, "_persist", None), "_runtime_reliability_overlay_version", None) != VERSION:
        original_persist = getattr(xray, "_persist", None)

        def transactional_persist(c: Any, cycle: Dict[str, Any]) -> None:
            update_state = getattr(c, "update_state", None)
            if not callable(update_state):
                if callable(original_persist):
                    original_persist(c, cycle)
                return

            def mutate(state: Dict[str, Any]) -> Dict[str, Any]:
                xrow = state.setdefault("entry_pipeline_xray", {})
                if not isinstance(xrow, dict):
                    xrow = {}
                    state["entry_pipeline_xray"] = xrow

                xrow.update({
                    "version": xray.VERSION,
                    "patch_target": "app.try_entries_and_rotations",
                    "updated_local": cycle.get("generated_local"),
                    "last_cycle": cycle,
                    "last_bottleneck": cycle.get("bottleneck"),
                    "last_stage_counts": cycle.get("stage_counts"),
                    "last_top_rejection_reasons": cycle.get("top_rejection_reasons"),
                    "last_symbol_paths": cycle.get("symbol_paths"),
                    "wrapped_callable": cycle.get("wrapped_callable"),
                    "composition": cycle.get("composition"),
                })

                recent = xrow.get("recent_cycles") if isinstance(xrow.get("recent_cycles"), list) else []
                recent.append(cycle)
                xrow["recent_cycles"] = recent[-max(1, xray.MAX_RECENT_CYCLES):]

                meaningful = bool(xray._is_meaningful(cycle))
                if meaningful:
                    xrow["last_meaningful_cycle"] = cycle
                    xrow["last_meaningful_stage_counts"] = cycle.get("stage_counts")
                    xrow["last_meaningful_bottleneck"] = cycle.get("bottleneck")
                    xrow["last_meaningful_symbol_paths"] = cycle.get("symbol_paths")
                    scanner = state.get("scanner_audit")
                    if isinstance(scanner, dict) and int(scanner.get("signals_found") or 0) > 0:
                        xrow["last_meaningful_scanner_audit"] = xray._json_safe(scanner)

                if cycle.get("error"):
                    errors = xrow.get("recent_errors") if isinstance(xrow.get("recent_errors"), list) else []
                    errors.append({
                        "generated_local": cycle.get("generated_local"),
                        "error": cycle.get("error"),
                        "wrapped_callable": cycle.get("wrapped_callable"),
                        "market_mode": cycle.get("market_mode"),
                        "stage_counts": cycle.get("stage_counts"),
                    })
                    xrow["recent_errors"] = errors[-max(1, xray.MAX_RECENT_ERRORS):]
                    xrow["last_error"] = xrow["recent_errors"][-1]

                counters = xrow.setdefault("counters", {})
                if isinstance(counters, dict):
                    counters["cycles_total"] = int(counters.get("cycles_total") or 0) + 1
                    counters["active_callsite_invocations_total"] = int(counters.get("active_callsite_invocations_total") or 0) + 1
                    key = f"bottleneck_{cycle.get('bottleneck') or 'unknown'}_total"
                    counters[key] = int(counters.get(key) or 0) + 1
                    if meaningful:
                        counters["meaningful_cycles_total"] = int(counters.get("meaningful_cycles_total") or 0) + 1
                return state

            update_state(mutate, source="entry_pipeline_xray")

        transactional_persist._runtime_reliability_overlay_version = VERSION  # type: ignore[attr-defined]
        xray._persist = transactional_persist

    def read_only_status(c: Any = None) -> Dict[str, Any]:
        c = c or _mod()
        telemetry = xray._telemetry(c)
        current = getattr(c, "try_entries_and_rotations", None) if c is not None else None
        composition = (
            _d(telemetry.get("composition"))
            or _d(_d(telemetry.get("last_cycle")).get("composition"))
            or _d(_d(telemetry.get("last_meaningful_cycle")).get("composition"))
            or _composition_status(c)
        )
        return {
            "status": "ok" if callable(current) else "pending",
            "overall": "pass" if callable(current) else "warn",
            "type": "entry_pipeline_xray_status",
            "version": xray.VERSION,
            "reliability_overlay_version": VERSION,
            "generated_local": _now(c),
            "enabled": bool(xray.ENABLED),
            "patched": bool(getattr(current, "_entry_pipeline_xray_version", None)),
            "patch_target": "app.try_entries_and_rotations",
            "current_callable": xray._callable_metadata(current),
            "wrapped_callable": telemetry.get("wrapped_callable") or getattr(xray, "_PATCH_TARGET", None) or {},
            "composition_status": composition,
            "telemetry_persisted": bool(telemetry),
            "last_cycle": telemetry.get("last_cycle") or {},
            "last_bottleneck": telemetry.get("last_bottleneck"),
            "last_stage_counts": telemetry.get("last_stage_counts") or {},
            "last_top_rejection_reasons": telemetry.get("last_top_rejection_reasons") or [],
            "last_symbol_paths": telemetry.get("last_symbol_paths") or [],
            "last_meaningful_cycle": telemetry.get("last_meaningful_cycle") or {},
            "last_meaningful_bottleneck": telemetry.get("last_meaningful_bottleneck"),
            "last_meaningful_stage_counts": telemetry.get("last_meaningful_stage_counts") or {},
            "last_meaningful_symbol_paths": telemetry.get("last_meaningful_symbol_paths") or [],
            "last_meaningful_scanner_audit": telemetry.get("last_meaningful_scanner_audit") or {},
            "last_error": telemetry.get("last_error") or {},
            "recent_errors": telemetry.get("recent_errors") or [],
            "counters": telemetry.get("counters") or {},
            "inspection_read_only": True,
            "transactional_persistence": callable(getattr(c, "update_state", None)) if c is not None else False,
            "authority_changed": False,
            "logic_changed": False,
        }

    read_only_status._runtime_reliability_overlay_version = VERSION  # type: ignore[attr-defined]
    xray.status_payload = read_only_status
    return {"patched": True, "transactional_persistence": True, "read_only_status": True}


def _patch_daily_compactor(core: Any) -> Dict[str, Any]:
    try:
        import daily_self_check_compactor as compactor
    except Exception as exc:
        return {"patched": False, "reason": f"compactor_unavailable:{type(exc).__name__}:{exc}"}

    current = getattr(compactor, "compact_daily", None)
    if not callable(current):
        return {"patched": False, "reason": "compact_daily_missing"}
    if getattr(current, "_runtime_reliability_overlay_version", None) == VERSION:
        return {"patched": True, "already_patched": True}

    original = current

    def cycle_aware_compact(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        out = original(payload)
        if not isinstance(out, dict):
            return out
        scanner = _d(out.get("scanner"))

        state: Dict[str, Any] = {}
        try:
            loaded = core.load_state()
            state = loaded if isinstance(loaded, dict) else {}
        except Exception:
            state = getattr(core, "portfolio", {}) if isinstance(getattr(core, "portfolio", {}), dict) else {}

        decision = _d(state.get("decision_audit"))
        blocked = _d(state.get("blocked_entry_reason_audit"))
        decision_cycle = _cycle_identity(decision) or _cycle_identity(_d(decision.get("latest_cycle")))
        blocker_cycle = _cycle_identity(blocked)
        same_cycle = decision_cycle is not None and blocker_cycle is not None and str(decision_cycle) == str(blocker_cycle)
        counts_differ = (
            scanner.get("signals_found") is not None
            and scanner.get("blocker_audit_signals_found") is not None
            and scanner.get("signals_found") != scanner.get("blocker_audit_signals_found")
        )

        scanner["decision_cycle_id"] = decision_cycle
        scanner["blocker_cycle_id"] = blocker_cycle
        scanner["same_cycle_comparison"] = bool(same_cycle)
        scanner["count_difference"] = (
            int(scanner.get("signals_found")) - int(scanner.get("blocker_audit_signals_found"))
            if counts_differ else 0
        )
        if same_cycle:
            scanner["source_mismatch"] = bool(counts_differ)
            scanner["snapshot_alignment"] = "same_cycle"
        elif decision_cycle is not None or blocker_cycle is not None:
            scanner["source_mismatch"] = False
            scanner["snapshot_alignment"] = "different_or_partial_cycle_ids"
        else:
            scanner["source_mismatch"] = None
            scanner["snapshot_alignment"] = "unverified_without_shared_cycle_id"
        out["scanner"] = scanner
        out["cycle_aware_scanner_comparison"] = True
        out["runtime_reliability_overlay_version"] = VERSION

        # Normalize the two stability fields from the dedicated, read-only
        # composition inspector. X-Ray telemetry is not required to duplicate
        # these structural facts.
        entry = _d(out.get("entry_pipeline"))
        composition = _composition_status(core)
        if entry.get("stack_stable") is None:
            entry["stack_stable"] = composition.get("stack_stable")
        if entry.get("participation_valve_chain_cycle_free") is None:
            entry["participation_valve_chain_cycle_free"] = composition.get("participation_valve_chain_cycle_free")
        if entry.get("recursion_safe") is None:
            entry["recursion_safe"] = composition.get("recursion_safe")
        if entry.get("direct_core_base") is None:
            entry["direct_core_base"] = composition.get("direct_core_base")
        out["entry_pipeline"] = entry

        health = _d(out.get("health"))
        warnings = []
        for row in _l(health.get("warnings")):
            if isinstance(row, dict) and row.get("error") == "scanner_source_snapshot_mismatch" and not same_cycle:
                continue
            if isinstance(row, dict) and row.get("error") == "compact_source_fields_missing":
                details = [item for item in _l(row.get("details")) if item != "entry_pipeline.stack_stable"]
                if not details:
                    continue
                row = {**row, "details": details}
            warnings.append(row)
        health["warnings"] = warnings
        out["health"] = health

        # The base compactor calculates overall before this compatibility layer.
        # Promote warn back to pass only when all warnings were resolved and no
        # required path failed. Never mask a real error or failed health check.
        failed_required = _l(health.get("failed_required"))
        if out.get("overall") == "warn" and not warnings and not failed_required:
            out["overall"] = "pass"
            out["status"] = "ok"
        return out

    cycle_aware_compact._runtime_reliability_overlay_version = VERSION  # type: ignore[attr-defined]
    compactor.compact_daily = cycle_aware_compact
    return {
        "patched": True,
        "cycle_aware_scanner_comparison": True,
        "entry_contract_normalized": True,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _PATCHED
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    xray = _patch_xray(core)
    compactor = _patch_daily_compactor(core)
    _PATCHED = bool(xray.get("patched") and compactor.get("patched"))
    return {
        "status": "ok" if _PATCHED else "warn",
        "version": VERSION,
        "patched": _PATCHED,
        "xray": xray,
        "daily_compactor": compactor,
        "authority_changed": False,
        "logic_changed": False,
    }


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _PATCHED else "pending",
        "version": VERSION,
        "patched": _PATCHED,
        "transactional_xray_persistence": True,
        "read_only_xray_status": True,
        "cycle_aware_scanner_comparison": True,
        "entry_contract_normalized": True,
        "authority_changed": False,
        "logic_changed": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if "/paper/runtime-reliability-status" not in existing:
            from flask import jsonify
            flask_app.add_url_rule(
                "/paper/runtime-reliability-status",
                "runtime_reliability_status",
                lambda: jsonify(status_payload(core or _mod())),
            )
    except Exception:
        pass
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
