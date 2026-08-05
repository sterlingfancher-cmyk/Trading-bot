"""Canonical scanner-stack recovery, recursion telemetry, and universe boundary.

Maintains the validated paper scanner order:
    universe boundary -> opening surge -> breakout participation ->
    market participation -> core scanner

If callable ownership drifts, duplicates, or forms a cycle, the module restores the
known core scanner and deterministically reapplies the approved layers. The broad
momentum module supplies the bounded universe data, but this canonical scanner
owner remains the only module that wraps ``scan_signals`` for that boundary.

Composition/reliability only. No signal criteria, thresholds, sizing, hard-risk,
order placement, ML authority, or live authority changes.
"""
from __future__ import annotations

import datetime as dt
import functools
import sys
import threading
import time
from typing import Any, Dict, List, Tuple

VERSION = "scanner-runtime-contract-2026-08-05-v2-broad-boundary"

_LOCK = threading.RLock()
_WATCHDOGS: set[int] = set()
_REGISTERED_APPS: set[int] = set()
_LAST: Dict[str, Any] = {}

_LINK_TOKENS = ("original", "prior", "wrapped", "base", "inner")
_KNOWN_LINK_ATTRS = (
    "_scanner_runtime_contract_prior",
    "_scanner_universe_boundary_prior",
    "_opening_surge_scan_prior",
    "_opening_surge_prior",
    "_breakout_original",
    "_market_participation_original",
    "_shared_cycle_identity_original",
    "_scanner_v2_lifecycle_trace_original",
    "_dynamic_universe_builder_original",
    "_relative_strength_original",
    "_pattern_recognition_original",
    "_loss_streak_original",
    "__wrapped__",
)


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "scan_signals"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "scan_signals"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _label(fn: Any) -> Dict[str, Any]:
    return {
        "module": getattr(fn, "__module__", None),
        "name": getattr(fn, "__name__", None),
        "qualname": getattr(fn, "__qualname__", None),
        "id": id(fn) if callable(fn) else None,
        "universe_boundary": bool(getattr(fn, "_scanner_universe_boundary", False)) if callable(fn) else False,
        "opening_surge": bool(getattr(fn, "_opening_surge_scan_guard", False)) if callable(fn) else False,
        "breakout": bool(getattr(fn, "_breakout_layer_patched", False)) if callable(fn) else False,
        "market_participation": str(getattr(fn, "__module__", "")) == "market_participation_accelerator" if callable(fn) else False,
    }


def _linked(fn: Any) -> List[Tuple[str, Any]]:
    if not callable(fn):
        return []
    out: List[Tuple[str, Any]] = []
    seen: set[int] = set()

    def add(name: str, value: Any) -> None:
        if callable(value) and id(value) not in seen:
            seen.add(id(value))
            out.append((name, value))

    for attr in _KNOWN_LINK_ATTRS:
        try:
            add(attr, getattr(fn, attr, None))
        except Exception:
            pass
    try:
        attrs = vars(fn)
    except Exception:
        attrs = {}
    for name, value in attrs.items():
        lowered = str(name).lower()
        if any(token in lowered for token in _LINK_TOKENS):
            add(str(name), value)
    return out


def _inspect(fn: Any, core: Any = None, limit: int = 128) -> Dict[str, Any]:
    queue: List[Tuple[Any, List[str], int]] = [(fn, [], 0)]
    seen: set[int] = set()
    rows: List[Dict[str, Any]] = []
    cycle = False

    while queue and len(rows) < limit:
        current, path, depth = queue.pop(0)
        if not callable(current):
            continue
        ident = id(current)
        if ident in seen:
            cycle = True
            continue
        seen.add(ident)
        row = _label(current)
        row.update({"path": path, "depth": depth})
        rows.append(row)
        for attr, linked in _linked(current):
            queue.append((linked, path + [attr], depth + 1))

    base_candidates: List[Any] = []
    if core is not None:
        for attr in ("_participation_original_scan_signals", "CORE_SCAN_SIGNALS_BASE"):
            candidate = getattr(core, attr, None)
            if callable(candidate):
                base_candidates.append(candidate)

    boundary = [row for row in rows if row.get("universe_boundary")]
    opening = [row for row in rows if row.get("opening_surge")]
    breakout = [row for row in rows if row.get("breakout")]
    market = [row for row in rows if row.get("market_participation")]
    boundary_depth = boundary[0]["depth"] if boundary else None
    opening_depth = opening[0]["depth"] if opening else None
    breakout_depth = breakout[0]["depth"] if breakout else None
    market_depth = market[0]["depth"] if market else None
    ordered = bool(
        len(opening) == 1
        and len(breakout) == 1
        and len(market) == 1
        and opening_depth is not None
        and breakout_depth is not None
        and market_depth is not None
        and int(opening_depth) < int(breakout_depth) < int(market_depth)
    )
    boundary_ordered = bool(
        len(boundary) == 1
        and boundary_depth is not None
        and opening_depth is not None
        and int(boundary_depth) < int(opening_depth)
    )
    return {
        "current": _label(fn),
        "nodes": rows,
        "chain_preview": rows[:24],
        "cycle_detected": cycle,
        "truncated": bool(queue),
        "universe_boundary_count": len(boundary),
        "universe_boundary_depth": boundary_depth,
        "universe_boundary_ordered": boundary_ordered,
        "opening_surge_count": len(opening),
        "breakout_count": len(breakout),
        "market_participation_count": len(market),
        "opening_surge_depth": opening_depth,
        "breakout_depth": breakout_depth,
        "market_participation_depth": market_depth,
        "ordered": ordered,
        "base_candidates": base_candidates,
    }


def _choose_base(core: Any, inspection: Dict[str, Any]) -> Any | None:
    explicit = getattr(core, "_participation_original_scan_signals", None)
    if callable(explicit):
        return explicit
    explicit = getattr(core, "CORE_SCAN_SIGNALS_BASE", None)
    if callable(explicit):
        return explicit
    for candidate in inspection.get("base_candidates", []):
        if callable(candidate):
            return candidate
    return None


def _rebuild(core: Any, before: Dict[str, Any]) -> Dict[str, Any]:
    base = _choose_base(core, before)
    if not callable(base):
        return {"changed": False, "reason": "core_scanner_base_not_found"}

    core.scan_signals = base
    setattr(core, "CORE_SCAN_SIGNALS_BASE", base)
    steps: List[Dict[str, Any]] = [{"step": "restore_core", "callable": _label(base)}]

    try:
        import market_participation_accelerator as market_participation
        flag = str(getattr(market_participation, "PATCH_FLAG", "_market_participation_accelerator_v1"))
        setattr(core, flag, False)
        result = market_participation.apply(core)
        steps.append({"step": "market_participation", "result": result})
    except Exception as exc:
        steps.append({"step": "market_participation", "error": f"{type(exc).__name__}: {exc}"})

    try:
        import breakout_participation_layer as breakout
        patcher = getattr(breakout, "_patch_scan_signals", None)
        result = bool(patcher(core)) if callable(patcher) else False
        steps.append({"step": "breakout", "patched": result})
    except Exception as exc:
        steps.append({"step": "breakout", "error": f"{type(exc).__name__}: {exc}"})

    try:
        import opening_surge_participation as opening
        result = opening.install(core)
        steps.append({"step": "opening_surge", "result": result})
    except Exception as exc:
        steps.append({"step": "opening_surge", "error": f"{type(exc).__name__}: {exc}"})

    try:
        import opening_surge_score_calibration as calibration
        result = calibration.install(core)
        steps.append({"step": "score_calibration", "result": result})
    except Exception as exc:
        steps.append({"step": "score_calibration", "error": f"{type(exc).__name__}: {exc}"})

    return {"changed": True, "reason": "canonical_scanner_stack_rebuilt", "steps": steps}


def _chain_has_boundary(fn: Any) -> bool:
    return bool(_inspect(fn).get("universe_boundary_count"))


def _apply_broad_boundary(core: Any) -> Dict[str, Any]:
    try:
        import broad_momentum_discovery as broad
        result = broad.enforce_scanner_boundary(core)
        setattr(core, "SCANNER_UNIVERSE_BOUNDARY_VERSION", broad.VERSION)
        return {
            "status": "ok",
            "version": broad.VERSION,
            "final_universe_count": result.get("post_boundary_universe_count"),
            "within_policy_cap": result.get("within_policy_cap"),
        }
    except Exception as exc:
        return {
            "status": "warn",
            "error": f"{type(exc).__name__}: {exc}",
            "fallback": "existing_scanner_universe_preserved",
        }


def _patch_universe_boundary(core: Any) -> bool:
    current = getattr(core, "scan_signals", None)
    if not callable(current) or _chain_has_boundary(current):
        return False

    @functools.wraps(current)
    def bounded_scan(*args, __prior=current, **kwargs):
        boundary = _apply_broad_boundary(core)
        try:
            state = getattr(core, "portfolio", {})
            if isinstance(state, dict):
                contract = state.setdefault("scanner_runtime_contract", {})
                if isinstance(contract, dict):
                    contract["last_universe_boundary"] = boundary
                    contract["last_universe_boundary_local"] = _now(core)
        except Exception:
            pass
        return __prior(*args, **kwargs)

    bounded_scan._scanner_universe_boundary = True
    bounded_scan._scanner_runtime_contract_version = VERSION
    bounded_scan._scanner_universe_boundary_prior = current
    bounded_scan._scanner_runtime_contract_prior = current
    bounded_scan.__wrapped__ = current
    core.scan_signals = bounded_scan
    return True


def _clear_stale_recursion_error(core: Any) -> Dict[str, Any]:
    try:
        state = getattr(core, "portfolio", {})
        auto = state.setdefault("auto_runner", {}) if isinstance(state, dict) else {}
        error = str(auto.get("last_error") or "")
        if "recursion" not in error.lower():
            return {"cleared": False, "reason": "no_recursion_error"}
        last_success = str(auto.get("last_successful_run_local") or auto.get("last_successful_run_ts") or "")
        last_attempt = str(auto.get("last_attempt_local") or auto.get("last_attempt_ts") or "")
        if last_success and last_attempt and last_success >= last_attempt:
            auto["last_recovered_error"] = error
            auto["last_recovered_error_trace"] = auto.get("last_error_trace")
            auto["last_recovered_error_local"] = _now(core)
            auto["last_error"] = None
            auto["last_error_trace"] = None
            return {"cleared": True, "reason": "later_success_superseded_recursion_error"}
        return {"cleared": False, "reason": "no_later_success_confirmed"}
    except Exception as exc:
        return {"cleared": False, "reason": f"telemetry_clear_failed:{type(exc).__name__}:{exc}"}


def _patch_success(core: Any) -> bool:
    current = getattr(core, "set_auto_success", None)
    if not callable(current):
        return False
    if getattr(current, "_scanner_runtime_contract_version", None) == VERSION:
        return False

    def wrapped_success(source: Any, result: Any, clock: Any, __prior=current):
        output = __prior(source, result, clock)
        try:
            state = getattr(core, "portfolio", {})
            auto = state.setdefault("auto_runner", {}) if isinstance(state, dict) else {}
            previous = auto.get("last_error")
            if previous:
                auto["last_recovered_error"] = previous
                auto["last_recovered_error_trace"] = auto.get("last_error_trace")
                auto["last_recovered_error_local"] = _now(core)
            auto["last_error"] = None
            auto["last_error_trace"] = None
        except Exception:
            pass
        return output

    wrapped_success._scanner_runtime_contract_version = VERSION
    wrapped_success._scanner_runtime_contract_prior = current
    wrapped_success.__wrapped__ = current
    core.set_auto_success = wrapped_success
    return True


def install(core: Any = None) -> Dict[str, Any]:
    global _LAST
    core = core or _mod()
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        before = _inspect(getattr(core, "scan_signals", None), core)
        auto = getattr(core, "portfolio", {}).get("auto_runner", {}) if isinstance(getattr(core, "portfolio", {}), dict) else {}
        recursion_error = "recursion" in str(auto.get("last_error") or "").lower()
        unhealthy = bool(
            before.get("cycle_detected")
            or before.get("truncated")
            or not before.get("ordered")
            or before.get("opening_surge_count") != 1
            or before.get("breakout_count") != 1
            or before.get("market_participation_count") != 1
        )
        rebuild = _rebuild(core, before) if unhealthy else {"changed": False, "reason": "canonical_stack_already_healthy"}
        boundary_patched = _patch_universe_boundary(core)
        after = _inspect(getattr(core, "scan_signals", None), core)
        success_patched = _patch_success(core)
        telemetry = _clear_stale_recursion_error(core)
        healthy = bool(
            after.get("ordered")
            and after.get("universe_boundary_ordered")
            and after.get("universe_boundary_count") == 1
            and not after.get("cycle_detected")
            and not after.get("truncated")
        )
        _LAST = {
            "status": "ok" if healthy else "warn",
            "overall": "pass" if healthy else "warn",
            "type": "scanner_runtime_contract_status",
            "version": VERSION,
            "generated_local": _now(core),
            "recursion_error_seen_before_install": recursion_error,
            "before": {key: value for key, value in before.items() if key != "base_candidates"},
            "rebuild": rebuild,
            "universe_boundary_patched_this_call": boundary_patched,
            "universe_boundary_active": after.get("universe_boundary_count") == 1,
            "universe_boundary_ordered": after.get("universe_boundary_ordered"),
            "after": {key: value for key, value in after.items() if key != "base_candidates"},
            "set_auto_success_patched_this_call": success_patched,
            "telemetry_recovery": telemetry,
            "authority": {
                "paper_only": True,
                "composition_and_reliability_only": True,
                "changes_signal_generation": False,
                "changes_thresholds": False,
                "changes_sizing": False,
                "changes_hard_risk_limits": False,
                "places_orders_directly": False,
                "changes_ml_authority": False,
                "changes_live_authority": False,
            },
        }
        try:
            state = getattr(core, "portfolio", {})
            if isinstance(state, dict):
                state["scanner_runtime_contract"] = dict(_LAST)
        except Exception:
            pass
        setattr(core, "SCANNER_RUNTIME_CONTRACT_VERSION", VERSION)
        return dict(_LAST)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return install(core or _mod())


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    core = core or _mod()
    install(core)
    if id(flask_app) in _REGISTERED_APPS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    path = "/paper/scanner-runtime-contract-status"
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if path not in existing:
        flask_app.add_url_rule(path, "scanner_runtime_contract_status", lambda: jsonify(status_payload(core)))
    _REGISTERED_APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [path]}


def start_watchdog(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    install(core)
    if core is None or id(core) in _WATCHDOGS:
        return {"status": "ok", "version": VERSION, "watchdog_started": core is not None and id(core) in _WATCHDOGS}
    _WATCHDOGS.add(id(core))

    def watch() -> None:
        for iteration in range(1800):
            try:
                install(core)
            except Exception:
                pass
            time.sleep(0.5 if iteration < 60 else 15.0)

    threading.Thread(target=watch, daemon=True, name="scanner-runtime-contract-watchdog").start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}


try:
    install(_mod())
except Exception:
    pass
