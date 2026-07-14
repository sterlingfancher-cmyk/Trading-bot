"""Stable runtime composition for the paper entry pipeline.

Intended call stack used by run_cycle():

    entry_pipeline_xray (outer diagnostic)
      -> paper_exposure_rotation (composable overlay)
        -> core_entry_pipeline (authoritative implementation)

The risk-on starter valve patches core_entry_pipeline's internal participation
helper. This module changes composition only; it does not change candidates,
thresholds, sizing, risk controls, broker authority, or ML authority.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict

VERSION = "entry-pipeline-composition-guard-2026-07-14-v2-stable-stack"
REGISTERED_APP_IDS: set[int] = set()


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


def _meta(fn: Any) -> Dict[str, Any]:
    return {
        "name": getattr(fn, "__name__", None),
        "module": getattr(fn, "__module__", None),
        "core_entry_pipeline_version": getattr(fn, "_core_entry_pipeline_version", None),
        "core_entry_pipeline_patched": bool(getattr(fn, "_core_entry_pipeline_non_wrapper_patched", False)),
        "paper_exposure_version": getattr(fn, "_paper_exposure_composition_version", None),
        "xray_version": getattr(fn, "_entry_pipeline_xray_version", None),
    }


def _inner_callable(fn: Any) -> Any:
    original = getattr(fn, "_entry_pipeline_xray_original", None)
    return original if callable(original) else fn


def _save_payload(core: Any, payload: Dict[str, Any]) -> None:
    try:
        state = core.load_state()
        if not isinstance(state, dict):
            state = getattr(core, "portfolio", {}) or {}
    except Exception:
        state = getattr(core, "portfolio", {}) or {}
    if not isinstance(state, dict):
        return
    state["entry_pipeline_composition_guard"] = payload
    try:
        core.save_state(state)
        core.portfolio = state
    except Exception:
        try:
            core.portfolio = state
        except Exception:
            pass


def _is_stable(fn: Any) -> bool:
    inner = _inner_callable(fn)
    return bool(
        callable(inner)
        and getattr(inner, "_paper_exposure_composition_version", None) == VERSION
        and getattr(inner, "_core_entry_pipeline_non_wrapper_patched", False)
        and getattr(inner, "_core_entry_pipeline_version", None)
    )


def _breakout_overlay(core: Any, base_fn: Any):
    import paper_exposure_rotation as per

    def composed(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        breakout_candidates: Dict[str, Dict[str, Any]] = {}
        for signal in list(long_signals or []) + list(short_signals or []):
            if isinstance(signal, dict) and per._is_breakout_signal(signal):
                symbol = str(signal.get("symbol") or "").upper()
                breakout_candidates[symbol] = {
                    "symbol": signal.get("symbol"),
                    "side": signal.get("side"),
                    "score": signal.get("score"),
                    "entry_context": signal.get("entry_context"),
                    "trade_class": signal.get("trade_class"),
                    "breakout_participation": signal.get("breakout_participation"),
                }

        entries, rotations, blocked_entries = base_fn(
            long_signals,
            short_signals,
            params,
            market,
            new_entries_allowed=new_entries_allowed,
            entry_block_reason=entry_block_reason,
        )

        blocked_breakouts = []
        for item in blocked_entries or []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            if symbol in breakout_candidates:
                row = dict(item)
                row["breakout_candidate"] = breakout_candidates[symbol]
                blocked_breakouts.append(row)

        try:
            core.portfolio["breakout_rotation_authority"] = {
                "status": "ok",
                "type": "breakout_rotation_authority",
                "version": per.VERSION,
                "composition_version": VERSION,
                "generated_local": _now(core),
                "enabled": bool(per.BREAKOUT_ROTATION_ENABLED and per.PAPER_EXPOSURE_EXPANSION_ENABLED and per._is_paper_context(core)),
                "breakout_candidates_count": len(breakout_candidates),
                "blocked_breakout_candidates_count": len(blocked_breakouts),
                "blocked_breakout_candidates": blocked_breakouts[:20],
                "entries_from_breakouts": [row for row in (entries or []) if str(row.get("symbol") or "").upper() in breakout_candidates][:20],
                "rotations_from_breakouts": [row for row in (rotations or []) if str(row.get("in") or "").upper() in breakout_candidates][:20],
                "positions_count": len((core.portfolio.get("positions", {}) or {})),
                "max_positions": int((params or {}).get("max_positions", 0) or 0),
                "max_new_entries_per_cycle": int(getattr(core, "MAX_NEW_ENTRIES_PER_CYCLE", 0)),
            }
        except Exception:
            pass
        return entries, rotations, blocked_entries

    composed._paper_exposure_composition_version = VERSION  # type: ignore[attr-defined]
    composed._paper_exposure_debug_patched = True  # type: ignore[attr-defined]
    composed._paper_exposure_debug_original = base_fn  # type: ignore[attr-defined]
    composed._core_entry_pipeline_version = getattr(base_fn, "_core_entry_pipeline_version", None)  # type: ignore[attr-defined]
    composed._core_entry_pipeline_non_wrapper_patched = bool(getattr(base_fn, "_core_entry_pipeline_non_wrapper_patched", False))  # type: ignore[attr-defined]
    return composed


def enforce(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}

    current = getattr(core, "try_entries_and_rotations", None)
    before = _meta(current)
    if _is_stable(current):
        inner = _inner_callable(current)
        payload = {
            "status": "ok",
            "overall": "pass",
            "type": "entry_pipeline_composition_guard_status",
            "version": VERSION,
            "generated_local": _now(core),
            "before": before,
            "after": _meta(inner),
            "stable_fast_path": True,
            "core_authoritative": True,
            "paper_exposure_composed": True,
            "stack": [
                "entry_pipeline_xray_outer",
                "paper_exposure_rotation_overlay",
                "core_entry_pipeline_authoritative",
                "risk_on_starter_valve_internal",
            ],
            "authority_changed": False,
        }
        _save_payload(core, payload)
        return payload

    try:
        import core_entry_pipeline as core_pipeline
        core_pipeline.apply(core)
        base = getattr(core, "try_entries_and_rotations", None)
        if not callable(base) or not getattr(base, "_core_entry_pipeline_non_wrapper_patched", False):
            raise RuntimeError("core_entry_pipeline_not_authoritative_after_apply")
    except Exception as exc:
        payload = {
            "status": "error",
            "overall": "warn",
            "version": VERSION,
            "reason": f"core_apply_failed:{type(exc).__name__}:{exc}",
            "before": before,
        }
        _save_payload(core, payload)
        return payload

    try:
        import paper_exposure_rotation as exposure
        exposure._patch_bucket_and_sector_limits(core)
        exposure._patch_aggression(core)
        exposure._patch_rotation_allowed(core)
        composed = _breakout_overlay(core, base)
        core.try_entries_and_rotations = composed
    except Exception as exc:
        payload = {
            "status": "error",
            "overall": "warn",
            "version": VERSION,
            "reason": f"paper_exposure_compose_failed:{type(exc).__name__}:{exc}",
            "before": before,
            "base": _meta(base),
        }
        _save_payload(core, payload)
        return payload

    try:
        import risk_on_starter_participation_valve as starter_valve
        starter_valve.apply(core)
    except Exception:
        pass

    after = _meta(getattr(core, "try_entries_and_rotations", None))
    payload = {
        "status": "ok",
        "overall": "pass",
        "type": "entry_pipeline_composition_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "before": before,
        "after": after,
        "stable_fast_path": False,
        "stack": [
            "entry_pipeline_xray_outer",
            "paper_exposure_rotation_overlay",
            "core_entry_pipeline_authoritative",
            "risk_on_starter_valve_internal",
        ],
        "core_authoritative": bool(after.get("core_entry_pipeline_patched")),
        "paper_exposure_composed": after.get("paper_exposure_version") == VERSION,
        "authority_changed": False,
        "diagnostic_and_composition_only": True,
        "does_not_change_thresholds": True,
        "does_not_change_sizing": True,
        "does_not_change_live_authority": True,
        "does_not_change_ml_authority": True,
    }
    _save_payload(core, payload)
    return payload


def apply(core: Any = None) -> Dict[str, Any]:
    return enforce(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return enforce(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION}
    try:
        state = core.load_state()
    except Exception:
        state = getattr(core, "portfolio", {}) or {}
    latest = state.get("entry_pipeline_composition_guard") if isinstance(state, dict) else {}
    current = getattr(core, "try_entries_and_rotations", None)
    return {
        "status": "ok",
        "overall": "pass",
        "type": "entry_pipeline_composition_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "current_callable": _meta(current),
        "inner_callable": _meta(_inner_callable(current)),
        "stack_stable": _is_stable(current),
        "latest": latest if isinstance(latest, dict) else {},
        "authority_changed": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/entry-pipeline-composition-status" not in existing:
        flask_app.add_url_rule(
            "/paper/entry-pipeline-composition-status",
            "entry_pipeline_composition_status",
            lambda: jsonify(status_payload(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    enforce(core or _mod())


try:
    enforce(_mod())
except Exception:
    pass
