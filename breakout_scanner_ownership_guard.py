"""Deterministic ownership guard for the breakout scanner wrapper.

The breakout participation patcher historically checked only the public outermost
``scan_signals`` callable. When opening-surge or observability wrappers sat above
an existing breakout layer, repeated registration could add another breakout
wrapper. This guard makes the breakout patcher chain-aware and removes only
redundant outer breakout wrappers, preserving one breakout layer beneath the
opening-surge filter.

Paper-only composition repair. It does not change signal criteria, thresholds,
sizing, hard risk limits, order placement, ML authority, or live authority.
"""
from __future__ import annotations

import datetime as dt
import sys
import threading
import time
from typing import Any, Dict, List, Tuple

VERSION = "breakout-scanner-ownership-2026-07-30-v1"

_LOCK = threading.RLock()
_WATCHDOGS: set[int] = set()
_REGISTERED_APPS: set[int] = set()
_LAST: Dict[str, Any] = {}

_LINK_TOKENS = ("original", "prior", "wrapped", "base", "inner")
_KNOWN_LINK_ATTRS = (
    "_breakout_original",
    "_opening_surge_scan_prior",
    "_opening_surge_prior",
    "_shared_cycle_identity_original",
    "_scanner_v2_lifecycle_trace_original",
    "_dynamic_universe_builder_original",
    "_relative_strength_original",
    "_pattern_recognition_original",
    "_market_participation_original",
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


def _callable_label(fn: Any) -> Dict[str, Any]:
    return {
        "module": getattr(fn, "__module__", None),
        "name": getattr(fn, "__name__", None),
        "qualname": getattr(fn, "__qualname__", None),
        "id": id(fn) if callable(fn) else None,
        "breakout_marker": bool(getattr(fn, "_breakout_layer_patched", False)) if callable(fn) else False,
        "opening_surge_marker": bool(getattr(fn, "_opening_surge_scan_guard", False)) if callable(fn) else False,
    }


def _linked(fn: Any) -> List[Tuple[str, Any]]:
    if not callable(fn):
        return []
    found: List[Tuple[str, Any]] = []
    seen: set[int] = set()

    def add(name: str, candidate: Any) -> None:
        if callable(candidate) and id(candidate) not in seen:
            seen.add(id(candidate))
            found.append((name, candidate))

    for attr in _KNOWN_LINK_ATTRS:
        add(attr, getattr(fn, attr, None))
    try:
        attrs = vars(fn)
    except Exception:
        attrs = {}
    for name, candidate in attrs.items():
        lowered = str(name).lower()
        if any(token in lowered for token in _LINK_TOKENS):
            add(str(name), candidate)
    return found


def _inspect(fn: Any, limit: int = 96) -> Dict[str, Any]:
    queue: List[Tuple[Any, List[str], int]] = [(fn, [], 0)]
    seen: set[int] = set()
    rows: List[Dict[str, Any]] = []
    breakout_matches: List[Dict[str, Any]] = []
    opening_matches: List[Dict[str, Any]] = []
    cycle_detected = False

    while queue and len(rows) < limit:
        current, path, depth = queue.pop(0)
        if not callable(current):
            continue
        ident = id(current)
        if ident in seen:
            cycle_detected = True
            continue
        seen.add(ident)
        row = _callable_label(current)
        row.update({"depth": depth, "path": path})
        rows.append(row)
        if row["breakout_marker"]:
            breakout_matches.append(row)
        if row["opening_surge_marker"]:
            opening_matches.append(row)
        for attr, linked in _linked(current):
            queue.append((linked, path + [attr], depth + 1))

    def first_depth(matches: List[Dict[str, Any]]) -> int | None:
        return int(matches[0]["depth"]) if matches else None

    return {
        "current_callable": _callable_label(fn),
        "breakout_count": len(breakout_matches),
        "opening_surge_count": len(opening_matches),
        "breakout_first_depth": first_depth(breakout_matches),
        "opening_surge_first_depth": first_depth(opening_matches),
        "breakout_first_path": list(breakout_matches[0]["path"]) if breakout_matches else None,
        "opening_surge_first_path": list(opening_matches[0]["path"]) if opening_matches else None,
        "cycle_detected": cycle_detected,
        "nodes_inspected": len(rows),
        "truncated": bool(queue),
        "chain_preview": rows[:24],
    }


def _guard_breakout_patcher() -> Dict[str, Any]:
    try:
        import breakout_participation_layer as breakout
    except Exception as exc:
        return {"status": "pending", "reason": f"breakout_import_failed:{type(exc).__name__}"}

    current_patcher = getattr(breakout, "_patch_scan_signals", None)
    if not callable(current_patcher):
        return {"status": "pending", "reason": "breakout_patcher_missing"}
    if getattr(current_patcher, "_breakout_chain_ownership_guard", False):
        return {"status": "ok", "patched": False, "reason": "already_chain_guarded"}

    original_patcher = current_patcher

    def guarded_patch_scan_signals(runtime: Any) -> bool:
        current = getattr(runtime, "scan_signals", None) if runtime is not None else None
        if callable(current) and _inspect(current).get("breakout_count", 0) >= 1:
            return False
        return bool(original_patcher(runtime))

    guarded_patch_scan_signals._breakout_chain_ownership_guard = True  # type: ignore[attr-defined]
    guarded_patch_scan_signals._breakout_original_patcher = original_patcher  # type: ignore[attr-defined]
    breakout._patch_scan_signals = guarded_patch_scan_signals
    return {"status": "ok", "patched": True, "reason": "chain_aware_patcher_installed"}


def _remove_redundant_outer_breakouts(core: Any) -> Dict[str, Any]:
    removed: List[Dict[str, Any]] = []
    before = _inspect(getattr(core, "scan_signals", None))

    for _ in range(12):
        current = getattr(core, "scan_signals", None)
        snapshot = _inspect(current)
        if snapshot.get("breakout_count", 0) <= 1:
            break
        if not bool(getattr(current, "_breakout_layer_patched", False)):
            break
        prior = getattr(current, "_breakout_original", None)
        if not callable(prior):
            break
        removed.append(_callable_label(current))
        core.scan_signals = prior

    after = _inspect(getattr(core, "scan_signals", None))
    return {
        "removed_count": len(removed),
        "removed_outer_wrappers": removed,
        "before_breakout_count": before.get("breakout_count"),
        "after_breakout_count": after.get("breakout_count"),
        "before": before,
        "after": after,
    }


def _ensure_one_breakout(core: Any) -> Dict[str, Any]:
    snapshot = _inspect(getattr(core, "scan_signals", None))
    if snapshot.get("breakout_count", 0) >= 1:
        return {"patched": False, "reason": "breakout_already_present"}
    try:
        import breakout_participation_layer as breakout
        patcher = getattr(breakout, "_patch_scan_signals", None)
        patched = bool(patcher(core)) if callable(patcher) else False
        return {"patched": patched, "reason": "breakout_reapplied" if patched else "breakout_reapply_noop"}
    except Exception as exc:
        return {"patched": False, "reason": f"breakout_reapply_failed:{type(exc).__name__}:{exc}"}


def install(core: Any = None) -> Dict[str, Any]:
    global _LAST
    core = core or _mod()
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        patcher = _guard_breakout_patcher()
        normalization = _remove_redundant_outer_breakouts(core)
        ensure = _ensure_one_breakout(core)
        ownership = _inspect(getattr(core, "scan_signals", None))
        breakout_count = int(ownership.get("breakout_count") or 0)
        opening_count = int(ownership.get("opening_surge_count") or 0)
        breakout_depth = ownership.get("breakout_first_depth")
        opening_depth = ownership.get("opening_surge_first_depth")
        opening_above_breakout = bool(
            opening_count == 1
            and breakout_count == 1
            and opening_depth is not None
            and breakout_depth is not None
            and int(opening_depth) < int(breakout_depth)
        )
        healthy = bool(
            breakout_count == 1
            and opening_count == 1
            and opening_above_breakout
            and not ownership.get("cycle_detected")
            and not ownership.get("truncated")
        )
        _LAST = {
            "status": "ok" if healthy else "warn",
            "overall": "pass" if healthy else "warn",
            "type": "breakout_scanner_ownership_status",
            "version": VERSION,
            "generated_local": _now(core),
            "patcher_guard": patcher,
            "normalization": normalization,
            "ensure_breakout": ensure,
            "breakout_guard_count": breakout_count,
            "opening_surge_guard_count": opening_count,
            "breakout_guard_depth": breakout_depth,
            "opening_surge_guard_depth": opening_depth,
            "opening_surge_above_breakout": opening_above_breakout,
            "ownership": ownership,
            "authority": {
                "paper_only": True,
                "composition_and_ownership_only": True,
                "changes_signal_generation": False,
                "changes_thresholds": False,
                "changes_sizing": False,
                "changes_hard_risk_limits": False,
                "places_orders_directly": False,
                "changes_ml_authority": False,
                "changes_live_authority": False,
            },
        }
        setattr(core, "BREAKOUT_SCANNER_OWNERSHIP_VERSION", VERSION)
        return dict(_LAST)


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    return install(core)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    core = core or _mod()
    install(core)
    if id(flask_app) in _REGISTERED_APPS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    path = "/paper/breakout-scanner-ownership-status"
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if path not in existing:
        flask_app.add_url_rule(path, "breakout_scanner_ownership_status", lambda: jsonify(status_payload(core)))
    _REGISTERED_APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [path]}


def start_watchdog(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    install(core)
    if core is None or id(core) in _WATCHDOGS:
        return {"status": "ok", "version": VERSION, "watchdog_started": core is not None and id(core) in _WATCHDOGS}
    _WATCHDOGS.add(id(core))

    def watch() -> None:
        for iteration in range(1200):
            try:
                install(core)
            except Exception:
                pass
            time.sleep(0.5 if iteration < 60 else 30.0)

    threading.Thread(target=watch, daemon=True, name="breakout-scanner-ownership-watchdog").start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}


try:
    install(_mod())
except Exception:
    pass
