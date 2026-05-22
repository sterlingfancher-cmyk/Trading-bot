"""Runtime stability hotfix for paper runner patch stacking.

This module is loaded by sitecustomize after the paper expansion modules. It is
intentionally non-strategic: it does not change signal scores, entry criteria,
stops, or risk rules. It only keeps runtime wrappers from stacking, avoids
valuation helpers triggering trade-journal file writes, and exposes a compact
status route for mobile/Railway diagnostics.
"""
from __future__ import annotations

import datetime as dt
import functools
import math
import os
import sys
from typing import Any, Callable, Dict, List, Tuple

VERSION = "runtime-stability-hotfix-2026-05-22-v1"
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
_LAST_STATUS: Dict[str, Any] = {}

ENABLED = os.environ.get("RUNTIME_STABILITY_HOTFIX_ENABLED", "true").lower() not in {"0", "false", "no", "off"}

PAPER_ORIGINAL_ATTRS = (
    "_paper_participation_original",
    "_paper_exposure_original",
)
PAPER_PATCH_MARKERS = (
    "_paper_participation_patched",
    "_paper_exposure_patched",
)

TRADE_JOURNAL_EXCLUDED_FUNCTION_NAMES = {
    "position_value",
    "estimated_trade_allocation",
    "apply_aggression_adjustments",
    "risk_parameters",
    "bucket_alloc_factor",
    "deployed_status",
    "participation_plan",
    "position_target",
    "effective_position_target",
    "exposure_status",
    "status",
}
TRADE_JOURNAL_EXCLUDED_KEYWORDS = (
    "deployed",
    "participation",
    "allocator",
    "allocation",
    "aggression",
    "exposure",
    "target",
    "plan",
    "value",
)
TRADE_JOURNAL_UNWRAP_HELPERS = {
    "position_value",
    "estimated_trade_allocation",
    "bucket_alloc_factor",
    "risk_parameters",
}


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None:
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "load_state"):
            return m
    return None


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _next_paper_original(fn: Any) -> Any | None:
    for attr in PAPER_ORIGINAL_ATTRS:
        nxt = getattr(fn, attr, None)
        if callable(nxt):
            return nxt
    return None


def _paper_chain(fn: Any, limit: int = 30) -> Tuple[List[Dict[str, Any]], Any | None, bool]:
    nodes: List[Dict[str, Any]] = []
    seen: set[int] = set()
    cur = fn
    cycle = False
    while callable(cur) and id(cur) not in seen and len(nodes) < limit:
        seen.add(id(cur))
        markers = [marker for marker in PAPER_PATCH_MARKERS if bool(getattr(cur, marker, False))]
        nodes.append({
            "name": getattr(cur, "__name__", str(cur)),
            "module": getattr(cur, "__module__", ""),
            "markers": markers,
        })
        nxt = _next_paper_original(cur)
        if not callable(nxt):
            return nodes, cur, cycle
        cur = nxt
    if callable(cur) and id(cur) in seen:
        cycle = True
    return nodes, cur if callable(cur) else None, cycle


def _chain_has_marker(fn: Any, marker: str) -> bool:
    nodes, _base, _cycle = _paper_chain(fn)
    return any(marker in (node.get("markers") or []) for node in nodes)


def _paper_marker_counts(nodes: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {marker: 0 for marker in PAPER_PATCH_MARKERS}
    for node in nodes:
        for marker in node.get("markers") or []:
            counts[marker] = counts.get(marker, 0) + 1
    return counts


def _import_module(name: str) -> Any | None:
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    try:
        return __import__(name)
    except Exception:
        return None


def _patch_aggression_patchers() -> Dict[str, Any]:
    """Make paper wrapper installers chain-aware so repeated bootstrap calls are idempotent."""
    result: Dict[str, Any] = {"patched": [], "already_guarded": [], "errors": []}
    targets = [
        ("paper_exposure_rotation", "_paper_exposure_patched"),
        ("paper_participation_allocator", "_paper_participation_patched"),
    ]
    for module_name, marker in targets:
        mod = _import_module(module_name)
        if mod is None:
            result["errors"].append({"module": module_name, "error": "module_not_available"})
            continue
        original_patcher = getattr(mod, "_patch_aggression", None)
        if not callable(original_patcher):
            result["errors"].append({"module": module_name, "error": "patcher_not_available"})
            continue
        if getattr(original_patcher, "_runtime_stability_chain_guarded", False):
            result["already_guarded"].append(module_name)
            continue

        @functools.wraps(original_patcher)
        def guarded_patch_aggression(m: Any, __orig: Callable[..., Any] = original_patcher, __marker: str = marker) -> bool:
            try:
                current = getattr(m, "apply_aggression_adjustments", None)
                if _chain_has_marker(current, __marker):
                    return False
            except Exception:
                pass
            return bool(__orig(m))

        guarded_patch_aggression._runtime_stability_chain_guarded = True  # type: ignore[attr-defined]
        guarded_patch_aggression._runtime_stability_original = original_patcher  # type: ignore[attr-defined]
        try:
            setattr(mod, "_patch_aggression", guarded_patch_aggression)
            result["patched"].append(module_name)
        except Exception as exc:
            result["errors"].append({"module": module_name, "error": str(exc)})
    return result


def _normalize_aggression_chain(m: Any | None = None) -> Dict[str, Any]:
    """Collapse duplicate paper wrappers and reapply one exposure + one participation layer."""
    if m is None or not hasattr(m, "apply_aggression_adjustments"):
        return {"status": "skipped", "reason": "module_or_function_missing"}
    current = getattr(m, "apply_aggression_adjustments", None)
    before_nodes, base, cycle = _paper_chain(current)
    counts = _paper_marker_counts(before_nodes)
    needs_normalize = bool(cycle or len(before_nodes) > 3 or any(v > 1 for v in counts.values()))
    if not needs_normalize:
        return {
            "status": "ok",
            "normalized": False,
            "before_depth": len(before_nodes),
            "after_depth": len(before_nodes),
            "marker_counts": counts,
            "cycle_detected": cycle,
        }
    if not callable(base):
        return {
            "status": "error",
            "normalized": False,
            "reason": "base_function_not_found",
            "before_depth": len(before_nodes),
            "marker_counts": counts,
        }

    try:
        setattr(m, "apply_aggression_adjustments", base)
    except Exception as exc:
        return {
            "status": "error",
            "normalized": False,
            "reason": f"restore_base_failed: {exc}",
            "before_depth": len(before_nodes),
            "marker_counts": counts,
        }

    reapplied: List[str] = []
    for module_name in ("paper_exposure_rotation", "paper_participation_allocator"):
        mod = _import_module(module_name)
        patcher = getattr(mod, "_patch_aggression", None) if mod is not None else None
        if callable(patcher):
            try:
                if patcher(m):
                    reapplied.append(module_name)
            except Exception:
                pass
    after_nodes, _after_base, after_cycle = _paper_chain(getattr(m, "apply_aggression_adjustments", None))
    return {
        "status": "ok",
        "normalized": True,
        "before_depth": len(before_nodes),
        "after_depth": len(after_nodes),
        "before_marker_counts": counts,
        "after_marker_counts": _paper_marker_counts(after_nodes),
        "cycle_detected_before": cycle,
        "cycle_detected_after": after_cycle,
        "reapplied": reapplied,
    }


def _direct_position_market_value(_m: Any, _symbol: str, pos: Dict[str, Any]) -> float:
    """Safe valuation helper that never calls app.position_value or journal-wrapped functions."""
    if not isinstance(pos, dict):
        return 0.0
    shares = abs(_f(pos.get("shares", 0.0), 0.0))
    px = _f(pos.get("last_price", pos.get("entry", 0.0)), 0.0)
    if px <= 0:
        px = _f(pos.get("entry", 0.0), 0.0)
    explicit_value = _f(pos.get("market_value", pos.get("value", 0.0)), 0.0)
    if explicit_value > 0:
        return abs(explicit_value)
    if str(pos.get("side", "long")).lower() == "short":
        margin = _f(pos.get("margin", 0.0), 0.0)
        return abs(margin) if margin > 0 else shares * px
    return shares * px


def _patch_participation_valuation() -> Dict[str, Any]:
    mod = _import_module("paper_participation_allocator")
    if mod is None:
        return {"status": "skipped", "reason": "paper_participation_allocator_not_available"}
    current = getattr(mod, "_position_market_value", None)
    if getattr(current, "_runtime_stability_direct_value", False):
        return {"status": "ok", "patched": False, "reason": "already_patched"}
    try:
        _direct_position_market_value._runtime_stability_direct_value = True  # type: ignore[attr-defined]
        setattr(mod, "_position_market_value", _direct_position_market_value)
        return {"status": "ok", "patched": True}
    except Exception as exc:
        return {"status": "error", "patched": False, "error": str(exc)}


def _patch_trade_journal_hook_filter() -> Dict[str, Any]:
    mod = _import_module("trade_journal")
    if mod is None:
        return {"status": "skipped", "reason": "trade_journal_not_available"}
    original = getattr(mod, "_function_should_be_hooked", None)
    if not callable(original):
        return {"status": "skipped", "reason": "hook_filter_not_available"}
    if getattr(original, "_runtime_stability_guarded", False):
        return {"status": "ok", "patched": False, "reason": "already_guarded"}

    @functools.wraps(original)
    def guarded_function_should_be_hooked(name: str, fn: Any) -> bool:
        low_name = str(name or "").lower()
        if low_name in TRADE_JOURNAL_EXCLUDED_FUNCTION_NAMES:
            return False
        if any(keyword in low_name for keyword in TRADE_JOURNAL_EXCLUDED_KEYWORDS):
            return False
        return bool(original(name, fn))

    guarded_function_should_be_hooked._runtime_stability_guarded = True  # type: ignore[attr-defined]
    guarded_function_should_be_hooked._runtime_stability_original = original  # type: ignore[attr-defined]
    try:
        setattr(mod, "_function_should_be_hooked", guarded_function_should_be_hooked)
        return {"status": "ok", "patched": True}
    except Exception as exc:
        return {"status": "error", "patched": False, "error": str(exc)}


def _unwrap_trade_journal_helpers(m: Any | None = None) -> Dict[str, Any]:
    if m is None:
        return {"status": "skipped", "reason": "module_not_available", "unwrapped": []}
    unwrapped: List[str] = []
    for name in sorted(TRADE_JOURNAL_UNWRAP_HELPERS):
        fn = getattr(m, name, None)
        if getattr(fn, "_trade_journal_event_wrapped", False) and callable(getattr(fn, "__wrapped__", None)):
            try:
                setattr(m, name, getattr(fn, "__wrapped__"))
                unwrapped.append(name)
            except Exception:
                pass
    return {"status": "ok", "unwrapped": unwrapped}


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    global _LAST_STATUS
    m = m or _mod()
    if not ENABLED:
        _LAST_STATUS = {"status": "disabled", "version": VERSION, "generated_local": _now_text()}
        return _LAST_STATUS
    patchers = _patch_aggression_patchers()
    valuation = _patch_participation_valuation()
    journal_filter = _patch_trade_journal_hook_filter()
    unwrapped = _unwrap_trade_journal_helpers(m)
    normalized = _normalize_aggression_chain(m)
    chain_nodes, _base, chain_cycle = _paper_chain(getattr(m, "apply_aggression_adjustments", None) if m is not None else None)
    payload = {
        "status": "ok",
        "type": "runtime_stability_hotfix_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "enabled": True,
        "module_found": bool(m is not None),
        "aggression_chain_depth": len(chain_nodes),
        "aggression_chain_cycle_detected": bool(chain_cycle),
        "aggression_marker_counts": _paper_marker_counts(chain_nodes),
        "aggression_chain": chain_nodes[:10],
        "patchers": patchers,
        "participation_valuation_patch": valuation,
        "trade_journal_hook_filter": journal_filter,
        "trade_journal_helpers_unwrapped": unwrapped,
        "aggression_chain_normalization": normalized,
    }
    try:
        if m is not None and hasattr(m, "portfolio"):
            m.portfolio["runtime_stability_hotfix"] = payload
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(m)) if m is not None else None
    _LAST_STATUS = payload
    return payload


def status(m: Any | None = None) -> Dict[str, Any]:
    try:
        return apply_runtime_overrides(m or _mod())
    except Exception as exc:
        return {
            "status": "error",
            "type": "runtime_stability_hotfix_status",
            "version": VERSION,
            "generated_local": _now_text(),
            "error": str(exc),
            "last_status": _LAST_STATUS,
        }


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify

    def runtime_stability_hotfix_status():
        return jsonify(status(m or _mod()))

    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/runtime-stability-hotfix-status" not in existing:
        flask_app.add_url_rule(
            "/paper/runtime-stability-hotfix-status",
            "runtime_stability_hotfix_status",
            runtime_stability_hotfix_status,
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    apply_runtime_overrides(m or _mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
