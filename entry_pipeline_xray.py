"""Entry Pipeline X-Ray v3 — stable active-callsite telemetry.

This diagnostic wrapper observes the exact app.try_entries_and_rotations callable
used by run_cycle(). Before wrapping, it asks entry_pipeline_composition_guard to
ensure the intended stack:

    X-Ray -> paper exposure overlay -> authoritative core entry pipeline

It records stage counts, symbol paths, recent errors, the latest cycle, and the
latest meaningful non-empty cycle. It does not change arguments, candidates,
thresholds, sizing, return values, risk controls, or authority.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from collections import Counter
from typing import Any, Dict, Iterable, List

VERSION = "entry-pipeline-xray-2026-07-14-v3-composition-errors"
ENABLED = os.environ.get("ENTRY_PIPELINE_XRAY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MAX_SYMBOL_ROWS = int(os.environ.get("ENTRY_PIPELINE_XRAY_MAX_SYMBOL_ROWS", "50"))
MAX_RECENT_CYCLES = int(os.environ.get("ENTRY_PIPELINE_XRAY_MAX_RECENT_CYCLES", "25"))
MAX_RECENT_ERRORS = int(os.environ.get("ENTRY_PIPELINE_XRAY_MAX_RECENT_ERRORS", "20"))
REGISTERED_APP_IDS: set[int] = set()
_PATCHED = False
_PATCH_TARGET: Dict[str, Any] | None = None


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 7:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item(), depth + 1)
        except Exception:
            return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item, depth + 1) for key, item in value.items() if not callable(item)}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, depth + 1) for item in list(value)[:120]]
    return str(value)


def _state(core: Any) -> Dict[str, Any]:
    try:
        state = core.load_state()
        return state if isinstance(state, dict) else {}
    except Exception:
        try:
            return getattr(core, "portfolio", {}) or {}
        except Exception:
            return {}


def _save(core: Any, state: Dict[str, Any]) -> None:
    try:
        core.save_state(state)
        core.portfolio = state
    except Exception:
        try:
            core.portfolio = state
        except Exception:
            pass


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def _reason(row: Dict[str, Any]) -> str:
    direct = row.get("reason")
    quality = _d(row.get("quality_info"))
    participation = _d(row.get("participation_valve"))
    if direct == "entry_quality_block" and quality.get("reason"):
        return f"entry_quality_block:{quality.get('reason')}"
    if direct:
        return str(direct)
    if quality.get("reason"):
        return f"entry_quality_block:{quality.get('reason')}"
    if participation.get("reason"):
        return f"participation_valve:{participation.get('reason')}"
    return "reason_not_available"


def _prepare_candidates(core: Any, longs: Any, shorts: Any, params: Dict[str, Any], market: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        import core_entry_pipeline as pipeline
        rows = pipeline._prepare_candidates(core, longs or [], shorts or [], params or {}, market or {})
        return rows if isinstance(rows, list) else []
    except Exception:
        rows: List[Dict[str, Any]] = []
        if params.get("allow_longs", False):
            rows.extend(dict(item) for item in _l(longs) if isinstance(item, dict))
        if params.get("allow_shorts", False):
            rows.extend(dict(item) for item in _l(shorts) if isinstance(item, dict))
        return rows


def _entry_symbols(rows: Iterable[Any]) -> set[str]:
    symbols: set[str] = set()
    for row in rows or []:
        if isinstance(row, dict):
            symbol = _symbol(row)
            if symbol:
                symbols.add(symbol)
    return symbols


def _callable_metadata(fn: Any) -> Dict[str, Any]:
    return {
        "name": getattr(fn, "__name__", None),
        "module": getattr(fn, "__module__", None),
        "core_entry_pipeline_version": getattr(fn, "_core_entry_pipeline_version", None),
        "core_entry_pipeline_patched": bool(getattr(fn, "_core_entry_pipeline_non_wrapper_patched", False)),
        "paper_exposure_version": getattr(fn, "_paper_exposure_composition_version", None),
        "xray_version": getattr(fn, "_entry_pipeline_xray_version", None),
    }


def _ensure_composition(core: Any) -> Dict[str, Any]:
    try:
        import entry_pipeline_composition_guard as guard
        payload = guard.enforce(core)
        return payload if isinstance(payload, dict) else {"status": "unknown"}
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"composition_guard_error:{type(exc).__name__}:{exc}",
        }


def _build_cycle(
    core: Any,
    longs: Any,
    shorts: Any,
    params: Dict[str, Any],
    market: Dict[str, Any],
    new_entries_allowed: bool,
    entry_block_reason: Any,
    prepared: List[Dict[str, Any]],
    result: Any,
    target_meta: Dict[str, Any],
    composition: Dict[str, Any],
    error: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    entries, rotations, blocked = result if isinstance(result, tuple) and len(result) == 3 else ([], [], [])
    entries = _l(entries)
    rotations = _l(rotations)
    blocked = _l(blocked)
    entered = _entry_symbols(entries)
    blocked_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    reasons: Counter[str] = Counter()
    participation_reached = 0
    quality_blocked = 0

    for row in blocked:
        if not isinstance(row, dict):
            continue
        symbol = _symbol(row)
        reason = _reason(row)
        reasons[reason] += 1
        if symbol:
            blocked_by_symbol.setdefault(symbol, []).append(row)
        if isinstance(row.get("participation_valve"), dict):
            participation_reached += 1
        if row.get("reason") in {"entry_quality_block", "rotation_entry_quality_block"} or reason.startswith("entry_quality_block"):
            quality_blocked += 1

    symbol_paths: List[Dict[str, Any]] = []
    for rank, candidate in enumerate(prepared[:MAX_SYMBOL_ROWS], start=1):
        symbol = _symbol(candidate)
        rows = blocked_by_symbol.get(symbol, [])
        final_status = "entered" if symbol in entered else ("blocked" if rows else "not_returned")
        path = ["scanner_signal", "run_cycle_handoff", "active_try_entries_call", "prepared_candidate"]
        if rows:
            path.append("entry_pipeline_reviewed")
            if any(isinstance(row.get("participation_valve"), dict) for row in rows):
                path.append("participation_valve_reached")
            path.append("blocked")
        elif symbol in entered:
            path.extend(["entry_pipeline_reviewed", "entry_returned"])
        else:
            path.append("no_final_row_visible")
        symbol_paths.append({
            "symbol": symbol,
            "rank": rank,
            "side": candidate.get("side"),
            "bucket": candidate.get("bucket"),
            "score": candidate.get("score"),
            "rank_score": candidate.get("core_entry_rank_score"),
            "final_status": final_status,
            "final_reasons": [_reason(row) for row in rows[:5]],
            "path": path,
        })

    raw_long = len(_l(longs))
    raw_short = len(_l(shorts))
    counts = {
        "raw_long_signals": raw_long,
        "raw_short_signals": raw_short,
        "raw_total_signals": raw_long + raw_short,
        "active_callsite_invocations": 1,
        "prepared_candidates": len(prepared),
        "entries_returned": len(entries),
        "rotations_returned": len(rotations),
        "blocked_rows_returned": len(blocked),
        "quality_blocked_rows": quality_blocked,
        "participation_valve_reached_rows": participation_reached,
        "candidates_without_final_row": sum(1 for row in symbol_paths if row.get("final_status") == "not_returned"),
    }

    if error:
        bottleneck = "active_callsite_error"
    elif not new_entries_allowed:
        bottleneck = "new_entries_not_allowed"
    elif counts["raw_total_signals"] > 0 and not prepared:
        bottleneck = "candidate_preparation"
    elif prepared and not entries and not blocked:
        bottleneck = "active_pipeline_no_final_rows"
    elif participation_reached == 0 and quality_blocked == 0 and prepared:
        bottleneck = "before_quality_or_participation_valve"
    elif quality_blocked > 0 and participation_reached == 0:
        bottleneck = "quality_block_not_reaching_participation_valve"
    elif participation_reached > 0 and not entries:
        bottleneck = "participation_valve_or_enter_position"
    elif entries:
        bottleneck = "entries_returned"
    else:
        bottleneck = "no_candidates_or_no_action"

    return _json_safe({
        "generated_local": _now(core),
        "version": VERSION,
        "patch_target": "app.try_entries_and_rotations",
        "wrapped_callable": target_meta,
        "composition": composition,
        "new_entries_allowed": bool(new_entries_allowed),
        "entry_block_reason": entry_block_reason,
        "market_mode": market.get("market_mode"),
        "allow_longs": bool(params.get("allow_longs", False)),
        "allow_shorts": bool(params.get("allow_shorts", False)),
        "stage_counts": counts,
        "bottleneck": bottleneck,
        "top_rejection_reasons": [{"reason": reason, "count": count} for reason, count in reasons.most_common(20)],
        "symbol_paths": symbol_paths,
        "entries_preview": entries[:10],
        "rotations_preview": rotations[:5],
        "blocked_preview": blocked[:25],
        "error": error,
        "authority_changed": False,
        "diagnostic_only": True,
    })


def _is_meaningful(cycle: Dict[str, Any]) -> bool:
    counts = _d(cycle.get("stage_counts"))
    return bool(
        int(counts.get("raw_total_signals") or 0) > 0
        or int(counts.get("entries_returned") or 0) > 0
        or int(counts.get("rotations_returned") or 0) > 0
        or int(counts.get("blocked_rows_returned") or 0) > 0
        or cycle.get("error")
    )


def _persist(core: Any, cycle: Dict[str, Any]) -> None:
    state = _state(core)
    xray = state.setdefault("entry_pipeline_xray", {})
    if not isinstance(xray, dict):
        xray = {}
        state["entry_pipeline_xray"] = xray

    xray.update({
        "version": VERSION,
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

    recent = xray.get("recent_cycles") if isinstance(xray.get("recent_cycles"), list) else []
    recent.append(cycle)
    xray["recent_cycles"] = recent[-max(1, MAX_RECENT_CYCLES):]

    if _is_meaningful(cycle):
        xray["last_meaningful_cycle"] = cycle
        xray["last_meaningful_stage_counts"] = cycle.get("stage_counts")
        xray["last_meaningful_bottleneck"] = cycle.get("bottleneck")
        xray["last_meaningful_symbol_paths"] = cycle.get("symbol_paths")
        scanner = state.get("scanner_audit")
        if isinstance(scanner, dict) and int(scanner.get("signals_found") or 0) > 0:
            xray["last_meaningful_scanner_audit"] = _json_safe(scanner)

    if cycle.get("error"):
        recent_errors = xray.get("recent_errors") if isinstance(xray.get("recent_errors"), list) else []
        recent_errors.append({
            "generated_local": cycle.get("generated_local"),
            "error": cycle.get("error"),
            "wrapped_callable": cycle.get("wrapped_callable"),
            "market_mode": cycle.get("market_mode"),
            "stage_counts": cycle.get("stage_counts"),
        })
        xray["recent_errors"] = recent_errors[-max(1, MAX_RECENT_ERRORS):]
        xray["last_error"] = recent_errors[-1]

    counters = xray.setdefault("counters", {})
    if isinstance(counters, dict):
        counters["cycles_total"] = int(counters.get("cycles_total") or 0) + 1
        counters["active_callsite_invocations_total"] = int(counters.get("active_callsite_invocations_total") or 0) + 1
        key = f"bottleneck_{cycle.get('bottleneck') or 'unknown'}_total"
        counters[key] = int(counters.get(key) or 0) + 1
        if _is_meaningful(cycle):
            counters["meaningful_cycles_total"] = int(counters.get("meaningful_cycles_total") or 0) + 1

    _save(core, state)


def _patch(core: Any = None) -> bool:
    global _PATCHED, _PATCH_TARGET
    if not ENABLED:
        return False
    core = core or _mod()
    if core is None:
        return False

    composition = _ensure_composition(core)
    current = getattr(core, "try_entries_and_rotations", None)
    if not callable(current):
        return False
    if getattr(current, "_entry_pipeline_xray_version", None) == VERSION:
        _PATCHED = True
        _PATCH_TARGET = _callable_metadata(getattr(current, "_entry_pipeline_xray_original", None))
        return False

    original = current
    original_meta = _callable_metadata(original)

    def wrapped(long_signals: Any, short_signals: Any, params: Any, market: Any, new_entries_allowed: bool = True, entry_block_reason: Any = None):
        params_dict = dict(params or {})
        market_dict = dict(market or {})
        prepared = _prepare_candidates(core, long_signals, short_signals, params_dict, market_dict)
        result = None
        error_row = None
        try:
            result = original(
                long_signals,
                short_signals,
                params,
                market,
                new_entries_allowed=new_entries_allowed,
                entry_block_reason=entry_block_reason,
            )
            return result
        except Exception as exc:
            error_row = {
                "type": type(exc).__name__,
                "message": str(exc),
                "wrapped_callable": original_meta,
            }
            raise
        finally:
            try:
                cycle = _build_cycle(
                    core,
                    long_signals,
                    short_signals,
                    params_dict,
                    market_dict,
                    new_entries_allowed,
                    entry_block_reason,
                    prepared,
                    result,
                    original_meta,
                    composition,
                    error=error_row,
                )
                _persist(core, cycle)
            except Exception:
                pass

    wrapped._entry_pipeline_xray_version = VERSION  # type: ignore[attr-defined]
    wrapped._entry_pipeline_xray_diagnostic_only = True  # type: ignore[attr-defined]
    wrapped._entry_pipeline_xray_wrapped_callable = original_meta  # type: ignore[attr-defined]
    wrapped._entry_pipeline_xray_original = original  # type: ignore[attr-defined]
    core.try_entries_and_rotations = wrapped
    _PATCHED = True
    _PATCH_TARGET = original_meta
    return True


def _telemetry(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    state = _state(core) if core is not None else {}
    row = state.get("entry_pipeline_xray") if isinstance(state, dict) else {}
    return row if isinstance(row, dict) else {}


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    _patch(core)
    telemetry = _telemetry(core)
    current = getattr(core, "try_entries_and_rotations", None) if core is not None else None
    try:
        import entry_pipeline_composition_guard as guard
        composition_status = guard.status_payload(core)
    except Exception as exc:
        composition_status = {"status": "error", "reason": str(exc)}
    return {
        "status": "ok",
        "overall": "pass",
        "type": "entry_pipeline_xray_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "patched": bool(_PATCHED),
        "patch_target": "app.try_entries_and_rotations",
        "current_callable": _callable_metadata(current),
        "wrapped_callable": telemetry.get("wrapped_callable") or _PATCH_TARGET or {},
        "composition_status": composition_status,
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
        "policy": {
            "diagnostic_only": True,
            "does_not_change_candidates": True,
            "does_not_change_thresholds": True,
            "does_not_change_sizing": True,
            "does_not_place_trades": True,
            "does_not_change_return_value": True,
            "does_not_change_live_authority": True,
            "does_not_change_ml_authority": True,
            "preserves_last_meaningful_cycle": True,
            "captures_recent_errors": True,
            "max_symbol_rows": MAX_SYMBOL_ROWS,
            "max_recent_cycles": MAX_RECENT_CYCLES,
            "max_recent_errors": MAX_RECENT_ERRORS,
        },
    }


def _install_one_link_promotion() -> None:
    try:
        import one_link_check as one_link
        endpoints = getattr(one_link, "ONE_TEST_ENDPOINTS", None)
        wanted = [
            {"path": "/paper/entry-pipeline-composition-status", "category": "governance", "required": False},
            {"path": "/paper/entry-pipeline-xray-status", "category": "governance", "required": False},
        ]
        if isinstance(endpoints, list):
            existing = {item.get("path") for item in endpoints if isinstance(item, dict)}
            for endpoint in wanted:
                if endpoint["path"] not in existing:
                    endpoints.append(endpoint)
        current = getattr(one_link, "_postprocess_one_test_payload", None)
        if callable(current) and getattr(current, "_entry_pipeline_xray_version", None) != VERSION:
            def promoted(payload: Dict[str, Any], self_check_module: Any):
                payload = current(payload, self_check_module)
                xray = status_payload()
                compact = {
                    "status": xray.get("status"),
                    "version": xray.get("version"),
                    "patched": xray.get("patched"),
                    "patch_target": xray.get("patch_target"),
                    "current_callable": xray.get("current_callable"),
                    "wrapped_callable": xray.get("wrapped_callable"),
                    "composition_status": xray.get("composition_status"),
                    "telemetry_persisted": xray.get("telemetry_persisted"),
                    "last_bottleneck": xray.get("last_bottleneck"),
                    "last_stage_counts": xray.get("last_stage_counts"),
                    "last_meaningful_bottleneck": xray.get("last_meaningful_bottleneck"),
                    "last_meaningful_stage_counts": xray.get("last_meaningful_stage_counts"),
                    "last_meaningful_scanner_audit": xray.get("last_meaningful_scanner_audit"),
                    "last_top_rejection_reasons": xray.get("last_top_rejection_reasons"),
                    "last_symbol_paths": _l(xray.get("last_symbol_paths"))[:25],
                    "last_meaningful_symbol_paths": _l(xray.get("last_meaningful_symbol_paths"))[:25],
                    "last_error": xray.get("last_error"),
                    "recent_errors": _l(xray.get("recent_errors"))[-10:],
                    "counters": xray.get("counters"),
                }
                dashboard = _d(payload.get("dashboard"))
                dashboard["entry_pipeline_xray"] = compact
                payload["dashboard"] = dashboard
                payload["entry_pipeline_xray_summary"] = compact
                operator = _d(payload.get("operator_summary"))
                operator.update({
                    "entry_pipeline_xray_status": compact.get("status"),
                    "entry_pipeline_xray_version": compact.get("version"),
                    "entry_pipeline_xray_patched": compact.get("patched"),
                    "entry_pipeline_xray_patch_target": compact.get("patch_target"),
                    "entry_pipeline_xray_current_callable": compact.get("current_callable"),
                    "entry_pipeline_xray_wrapped_callable": compact.get("wrapped_callable"),
                    "entry_pipeline_xray_composition_status": compact.get("composition_status"),
                    "entry_pipeline_xray_telemetry_persisted": compact.get("telemetry_persisted"),
                    "entry_pipeline_xray_last_bottleneck": compact.get("last_bottleneck"),
                    "entry_pipeline_xray_last_stage_counts": compact.get("last_stage_counts"),
                    "entry_pipeline_xray_last_meaningful_bottleneck": compact.get("last_meaningful_bottleneck"),
                    "entry_pipeline_xray_last_meaningful_stage_counts": compact.get("last_meaningful_stage_counts"),
                    "entry_pipeline_xray_last_meaningful_scanner_audit": compact.get("last_meaningful_scanner_audit"),
                    "entry_pipeline_xray_top_rejection_reasons": compact.get("last_top_rejection_reasons"),
                    "entry_pipeline_xray_symbol_paths": compact.get("last_symbol_paths"),
                    "entry_pipeline_xray_last_error": compact.get("last_error"),
                    "entry_pipeline_xray_recent_errors": compact.get("recent_errors"),
                })
                payload["operator_summary"] = operator
                return payload
            promoted._entry_pipeline_xray_version = VERSION  # type: ignore[attr-defined]
            one_link._postprocess_one_test_payload = promoted
            one_link.VERSION = "one-test-policy-2026-07-14-entry-pipeline-composition-v3"
    except Exception:
        pass


def apply(core: Any = None) -> Dict[str, Any]:
    _patch(core or _mod())
    _install_one_link_promotion()
    return status_payload(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/entry-pipeline-xray-status" not in existing:
        flask_app.add_url_rule(
            "/paper/entry-pipeline-xray-status",
            "entry_pipeline_xray_status",
            lambda: jsonify(apply(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
