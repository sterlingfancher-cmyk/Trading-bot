"""Entry Pipeline X-Ray telemetry.

Diagnostic-only overlay around core_entry_pipeline._core_try_entries_and_rotations.
It records how many candidates enter the core pipeline, the final rejection/output
reasons, participation-valve reachability, and per-symbol paths. It does not
change candidates, thresholds, sizing, authority, or execution decisions.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from collections import Counter
from typing import Any, Dict, Iterable, List

VERSION = "entry-pipeline-xray-2026-07-10-v1"
ENABLED = os.environ.get("ENTRY_PIPELINE_XRAY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MAX_SYMBOL_ROWS = int(os.environ.get("ENTRY_PIPELINE_XRAY_MAX_SYMBOL_ROWS", "40"))
MAX_RECENT_CYCLES = int(os.environ.get("ENTRY_PIPELINE_XRAY_MAX_RECENT_CYCLES", "20"))
REGISTERED_APP_IDS: set[int] = set()
_PATCHED = False
_ORIGINAL = None


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "load_state"):
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "load_state"):
            return m
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item(), depth + 1)
        except Exception:
            return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v, depth + 1) for k, v in value.items() if not callable(v)}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, depth + 1) for v in list(value)[:100]]
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
        try:
            core.portfolio = state
        except Exception:
            pass
    except Exception:
        try:
            core.portfolio = state
        except Exception:
            pass


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def _reason(row: Dict[str, Any]) -> str:
    direct = row.get("reason")
    if direct:
        return str(direct)
    quality = _d(row.get("quality_info"))
    if quality.get("reason"):
        return f"entry_quality_block:{quality.get('reason')}"
    participation = _d(row.get("participation_valve"))
    if participation.get("reason"):
        return f"participation_valve:{participation.get('reason')}"
    return "reason_not_available"


def _prepared_candidates(core: Any, long_signals: Any, short_signals: Any, params: Dict[str, Any], market: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        import core_entry_pipeline as cep
        rows = cep._prepare_candidates(core, long_signals or [], short_signals or [], params or {}, market or {})
        return rows if isinstance(rows, list) else []
    except Exception:
        rows: List[Dict[str, Any]] = []
        for item in list(long_signals or []) + list(short_signals or []):
            if isinstance(item, dict):
                rows.append(dict(item))
        return rows


def _entry_symbols(entries: Iterable[Any]) -> set[str]:
    out: set[str] = set()
    for row in entries or []:
        if isinstance(row, dict):
            symbol = _symbol(row)
            if symbol:
                out.add(symbol)
    return out


def _build_cycle(core: Any, long_signals: Any, short_signals: Any, params: Dict[str, Any], market: Dict[str, Any], new_entries_allowed: bool, entry_block_reason: Any, prepared: List[Dict[str, Any]], result: Any) -> Dict[str, Any]:
    entries, rotations, blocked = (result if isinstance(result, tuple) and len(result) == 3 else ([], [], []))
    entries = _l(entries)
    rotations = _l(rotations)
    blocked = _l(blocked)
    entered = _entry_symbols(entries)
    blocked_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    reason_counts: Counter[str] = Counter()
    valve_reached = 0
    quality_blocked = 0
    for row in blocked:
        if not isinstance(row, dict):
            continue
        symbol = _symbol(row)
        reason = _reason(row)
        reason_counts[reason] += 1
        if symbol:
            blocked_by_symbol.setdefault(symbol, []).append(row)
        if isinstance(row.get("participation_valve"), dict):
            valve_reached += 1
        if reason.startswith("entry_quality_block") or row.get("reason") in {"entry_quality_block", "rotation_entry_quality_block"}:
            quality_blocked += 1

    symbol_paths: List[Dict[str, Any]] = []
    for rank, candidate in enumerate(prepared[:MAX_SYMBOL_ROWS], start=1):
        symbol = _symbol(candidate)
        rows = blocked_by_symbol.get(symbol, [])
        final_status = "entered" if symbol in entered else ("blocked" if rows else "not_returned")
        reasons = [_reason(r) for r in rows]
        path = ["input_signal", "prepared_candidate"]
        if rows:
            path.append("core_pipeline_reviewed")
            if any(isinstance(r.get("participation_valve"), dict) for r in rows):
                path.append("participation_valve_reached")
            path.append("blocked")
        elif symbol in entered:
            path.extend(["core_pipeline_reviewed", "entry_returned"])
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
            "final_reasons": reasons[:5],
            "path": path,
        })

    stage_counts = {
        "raw_long_signals": len(_l(long_signals)),
        "raw_short_signals": len(_l(short_signals)),
        "raw_total_signals": len(_l(long_signals)) + len(_l(short_signals)),
        "prepared_candidates": len(prepared),
        "core_entries_returned": len(entries),
        "core_rotations_returned": len(rotations),
        "core_blocked_rows_returned": len(blocked),
        "quality_blocked_rows": quality_blocked,
        "participation_valve_reached_rows": valve_reached,
        "candidates_without_final_row": sum(1 for row in symbol_paths if row.get("final_status") == "not_returned"),
    }
    bottleneck = "none"
    if not new_entries_allowed:
        bottleneck = "new_entries_not_allowed"
    elif len(prepared) == 0 and stage_counts["raw_total_signals"] > 0:
        bottleneck = "candidate_preparation"
    elif len(prepared) > 0 and not entries and not blocked:
        bottleneck = "core_pipeline_no_final_rows"
    elif valve_reached == 0 and quality_blocked == 0 and len(prepared) > 0:
        bottleneck = "before_entry_quality_or_valve"
    elif quality_blocked > 0 and valve_reached == 0:
        bottleneck = "quality_block_not_reaching_valve"
    elif valve_reached > 0 and not entries:
        bottleneck = "participation_valve_or_enter_position"
    elif entries:
        bottleneck = "entries_returned"

    return _json_safe({
        "generated_local": _now(core),
        "version": VERSION,
        "new_entries_allowed": bool(new_entries_allowed),
        "entry_block_reason": entry_block_reason,
        "market_mode": (market or {}).get("market_mode"),
        "allow_longs": bool((params or {}).get("allow_longs", False)),
        "allow_shorts": bool((params or {}).get("allow_shorts", False)),
        "stage_counts": stage_counts,
        "bottleneck": bottleneck,
        "top_rejection_reasons": [{"reason": reason, "count": count} for reason, count in reason_counts.most_common(15)],
        "symbol_paths": symbol_paths,
        "entries_preview": entries[:10],
        "rotations_preview": rotations[:5],
        "blocked_preview": blocked[:20],
        "authority_changed": False,
        "diagnostic_only": True,
    })


def _persist(core: Any, cycle: Dict[str, Any]) -> None:
    state = _state(core)
    xray = state.setdefault("entry_pipeline_xray", {})
    if not isinstance(xray, dict):
        xray = {}
        state["entry_pipeline_xray"] = xray
    xray.update({
        "version": VERSION,
        "updated_local": cycle.get("generated_local"),
        "last_cycle": cycle,
        "last_bottleneck": cycle.get("bottleneck"),
        "last_stage_counts": cycle.get("stage_counts"),
        "last_top_rejection_reasons": cycle.get("top_rejection_reasons"),
        "last_symbol_paths": cycle.get("symbol_paths"),
    })
    recent = xray.get("recent_cycles") if isinstance(xray.get("recent_cycles"), list) else []
    recent.append(cycle)
    xray["recent_cycles"] = recent[-max(1, MAX_RECENT_CYCLES):]
    counters = xray.setdefault("counters", {})
    if isinstance(counters, dict):
        counters["cycles_total"] = int(counters.get("cycles_total") or 0) + 1
        bottleneck = str(cycle.get("bottleneck") or "unknown")
        key = f"bottleneck_{bottleneck}_total"
        counters[key] = int(counters.get(key) or 0) + 1
    _save(core, state)


def _patch() -> bool:
    global _PATCHED, _ORIGINAL
    if not ENABLED:
        return False
    try:
        import core_entry_pipeline as cep
        current = getattr(cep, "_core_try_entries_and_rotations", None)
        if getattr(current, "_entry_pipeline_xray_version", None) == VERSION:
            _PATCHED = True
            return False
        if not callable(current):
            return False
        _ORIGINAL = current

        def wrapped(core: Any, long_signals: Any, short_signals: Any, params: Any, market: Any, new_entries_allowed: bool = True, entry_block_reason: Any = None):
            prepared = _prepared_candidates(core, long_signals, short_signals, dict(params or {}), dict(market or {}))
            result = _ORIGINAL(core, long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)
            try:
                cycle = _build_cycle(core, long_signals, short_signals, dict(params or {}), dict(market or {}), new_entries_allowed, entry_block_reason, prepared, result)
                _persist(core, cycle)
            except Exception:
                pass
            return result

        wrapped._entry_pipeline_xray_version = VERSION  # type: ignore[attr-defined]
        wrapped._entry_pipeline_xray_diagnostic_only = True  # type: ignore[attr-defined]
        cep._core_try_entries_and_rotations = wrapped
        _PATCHED = True
        return True
    except Exception:
        return False


def _telemetry(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    state = _state(core) if core is not None else {}
    row = state.get("entry_pipeline_xray") if isinstance(state, dict) else {}
    return row if isinstance(row, dict) else {}


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    telemetry = _telemetry(core)
    return {
        "status": "ok",
        "overall": "pass",
        "type": "entry_pipeline_xray_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "patched": bool(_PATCHED),
        "telemetry_persisted": bool(telemetry),
        "last_cycle": telemetry.get("last_cycle") or {},
        "last_bottleneck": telemetry.get("last_bottleneck"),
        "last_stage_counts": telemetry.get("last_stage_counts") or {},
        "last_top_rejection_reasons": telemetry.get("last_top_rejection_reasons") or [],
        "last_symbol_paths": telemetry.get("last_symbol_paths") or [],
        "counters": telemetry.get("counters") or {},
        "policy": {
            "diagnostic_only": True,
            "does_not_change_candidates": True,
            "does_not_change_thresholds": True,
            "does_not_change_sizing": True,
            "does_not_place_trades": True,
            "does_not_change_live_authority": True,
            "does_not_change_ml_authority": True,
            "max_symbol_rows": MAX_SYMBOL_ROWS,
            "max_recent_cycles": MAX_RECENT_CYCLES,
        },
    }


def _install_one_link_promotion() -> None:
    try:
        import one_link_check as olc
        endpoints = getattr(olc, "ONE_TEST_ENDPOINTS", None)
        if isinstance(endpoints, list) and not any(isinstance(e, dict) and e.get("path") == "/paper/entry-pipeline-xray-status" for e in endpoints):
            endpoints.append({"path": "/paper/entry-pipeline-xray-status", "category": "governance", "required": False, "after": "/paper/risk-on-starter-participation-status"})
        current = getattr(olc, "_postprocess_one_test_payload", None)
        if callable(current) and getattr(current, "_entry_pipeline_xray_version", None) != VERSION:
            def promoted(payload: Dict[str, Any], self_check_module: Any):
                payload = current(payload, self_check_module)
                xray = status_payload()
                compact = {
                    "status": xray.get("status"),
                    "version": xray.get("version"),
                    "patched": xray.get("patched"),
                    "telemetry_persisted": xray.get("telemetry_persisted"),
                    "last_bottleneck": xray.get("last_bottleneck"),
                    "last_stage_counts": xray.get("last_stage_counts"),
                    "last_top_rejection_reasons": xray.get("last_top_rejection_reasons"),
                    "last_symbol_paths": _l(xray.get("last_symbol_paths"))[:20],
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
                    "entry_pipeline_xray_telemetry_persisted": compact.get("telemetry_persisted"),
                    "entry_pipeline_xray_last_bottleneck": compact.get("last_bottleneck"),
                    "entry_pipeline_xray_last_stage_counts": compact.get("last_stage_counts"),
                    "entry_pipeline_xray_top_rejection_reasons": compact.get("last_top_rejection_reasons"),
                    "entry_pipeline_xray_symbol_paths": compact.get("last_symbol_paths"),
                })
                payload["operator_summary"] = operator
                return payload
            promoted._entry_pipeline_xray_version = VERSION  # type: ignore[attr-defined]
            olc._postprocess_one_test_payload = promoted
            olc.VERSION = "one-test-policy-2026-07-10-entry-pipeline-xray"
    except Exception:
        pass


def apply(core: Any = None) -> Dict[str, Any]:
    _patch()
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
        flask_app.add_url_rule("/paper/entry-pipeline-xray-status", "entry_pipeline_xray_status", lambda: jsonify(apply(core or _mod())))
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
