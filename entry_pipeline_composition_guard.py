"""Deterministic runtime composition for the paper entry pipeline.

Intended call stack used by run_cycle():

    entry_pipeline_xray (outer diagnostic)
      -> paper_exposure_rotation (composable overlay)
        -> direct core_entry_pipeline implementation

The participation helper chain is also rebuilt deterministically:

    clean core participation valve
      -> extended-leader starter overlay
        -> risk-on starter overlay

No overlay is allowed to capture another overlay dynamically as its original
function. This prevents the extended/risk-on wrappers from pointing at each
other and causing RecursionError loops.

This module changes composition only. It does not change candidates,
thresholds, sizing, risk controls, broker authority, or ML authority.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, Tuple

VERSION = "entry-pipeline-composition-guard-2026-07-17-v4-valve-chain"
VALVE_CHAIN_VERSION = "participation-valve-chain-2026-07-17-v1"
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
        "direct_core_base": bool(getattr(fn, "_entry_pipeline_direct_core_base", False)),
        "participation_valve_chain_version": getattr(fn, "_participation_valve_chain_version", None),
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
        and getattr(inner, "_entry_pipeline_direct_core_base", False)
    )


def _direct_core_base(core: Any, core_pipeline: Any):
    """Return an immutable closure over the true internal core implementation."""
    internal = getattr(core_pipeline, "_core_try_entries_and_rotations", None)
    if not callable(internal):
        raise RuntimeError("core_internal_entry_callable_missing")

    def direct_core(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        return internal(
            core,
            long_signals,
            short_signals,
            params,
            market,
            new_entries_allowed=new_entries_allowed,
            entry_block_reason=entry_block_reason,
        )

    direct_core._core_entry_pipeline_non_wrapper_patched = True  # type: ignore[attr-defined]
    direct_core._core_entry_pipeline_version = getattr(core_pipeline, "VERSION", None)  # type: ignore[attr-defined]
    direct_core._entry_pipeline_direct_core_base = True  # type: ignore[attr-defined]
    direct_core._entry_pipeline_direct_core_target = "core_entry_pipeline._core_try_entries_and_rotations"  # type: ignore[attr-defined]
    return direct_core


def _clean_base_participation_valve(core_pipeline: Any):
    """Create a fresh base valve that never references overlay globals."""

    def clean_base(core: Any, signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any], quality_info: Any, rank_index: int, entries_this_cycle: int, valve_entries_this_cycle: int) -> Tuple[bool, Dict[str, Any]]:
        symbol = core_pipeline._symbol(signal)
        side = core_pipeline._side(signal)
        score = core_pipeline._safe_float(signal.get("score"), 0.0)
        rank_score = core_pipeline._safe_float(signal.get("core_entry_rank_score"), score)
        quality_reason = core_pipeline._quality_reason(quality_info)
        required_score = core_pipeline._safe_float(quality_info.get("required_score") if isinstance(quality_info, dict) else None, 0.0)
        if required_score <= 0:
            required_score = core_pipeline._normal_entry_floor(core, market, side, 0.0)
        score_gap = max(0.0, required_score - score) if required_score > 0 else 999.0

        base = {
            "version": getattr(core_pipeline, "VERSION", None),
            "symbol": symbol,
            "side": side,
            "rank_index": rank_index,
            "score": round(score, 6),
            "rank_score": round(rank_score, 6),
            "required_score": round(required_score, 6),
            "score_gap": round(score_gap, 6),
            "quality_reason": quality_reason,
            "participation_valve_chain_version": VALVE_CHAIN_VERSION,
        }
        if not (getattr(core_pipeline, "PARTICIPATION_VALVE_ENABLED", False) and core_pipeline._paper_context()):
            return False, {**base, "reason": "participation_valve_disabled_or_not_paper"}
        if side != "long":
            return False, {**base, "reason": "participation_valve_long_only"}
        if rank_index > core_pipeline.PARTICIPATION_VALVE_MAX_REVIEWED_RANK:
            return False, {**base, "reason": "participation_valve_rank_too_low", "max_rank": core_pipeline.PARTICIPATION_VALVE_MAX_REVIEWED_RANK}
        if valve_entries_this_cycle >= core_pipeline.PARTICIPATION_VALVE_MAX_ENTRIES_PER_CYCLE:
            return False, {**base, "reason": "participation_valve_cycle_limit", "max_entries_per_cycle": core_pipeline.PARTICIPATION_VALVE_MAX_ENTRIES_PER_CYCLE}
        if core_pipeline._participation_valve_entries_today(core) >= core_pipeline.PARTICIPATION_VALVE_MAX_ENTRIES_PER_DAY:
            return False, {**base, "reason": "participation_valve_daily_limit", "max_entries_per_day": core_pipeline.PARTICIPATION_VALVE_MAX_ENTRIES_PER_DAY}
        if quality_reason not in core_pipeline.PARTICIPATION_VALVE_ALLOWED_QUALITY_REASONS:
            return False, {**base, "reason": "participation_valve_quality_reason_not_allowed", "allowed_reasons": sorted(core_pipeline.PARTICIPATION_VALVE_ALLOWED_QUALITY_REASONS)}
        if score < core_pipeline.PARTICIPATION_VALVE_MIN_RAW_SCORE:
            return False, {**base, "reason": "participation_valve_raw_score_too_low", "min_raw_score": core_pipeline.PARTICIPATION_VALVE_MIN_RAW_SCORE}
        if rank_score < core_pipeline.PARTICIPATION_VALVE_MIN_RANK_SCORE:
            return False, {**base, "reason": "participation_valve_rank_score_too_low", "min_rank_score": core_pipeline.PARTICIPATION_VALVE_MIN_RANK_SCORE}
        if score_gap > core_pipeline.PARTICIPATION_VALVE_MAX_SCORE_GAP:
            return False, {**base, "reason": "participation_valve_score_gap_too_wide", "max_score_gap": core_pipeline.PARTICIPATION_VALVE_MAX_SCORE_GAP}
        if core_pipeline._has_extension_warning(signal, quality_info):
            return False, {**base, "reason": "participation_valve_extension_or_chase_block"}
        risk_ok, risk_info = core_pipeline._risk_clean_for_participation(core, market)
        if not risk_ok:
            return False, {**base, **risk_info}
        return True, {
            **base,
            "reason": "participation_valve_ok",
            "alloc_factor": core_pipeline.PARTICIPATION_VALVE_ALLOC_FACTOR,
            "risk": risk_info,
        }

    clean_base._participation_valve_chain_version = VALVE_CHAIN_VERSION  # type: ignore[attr-defined]
    clean_base._participation_valve_chain_role = "clean_base"  # type: ignore[attr-defined]
    return clean_base


def _repair_participation_valve_chain(core_pipeline: Any) -> Dict[str, Any]:
    """Install a fixed non-cyclic base -> extended -> risk-on helper chain."""
    current = getattr(core_pipeline, "_participation_valve_ok", None)
    if (
        callable(current)
        and getattr(current, "_participation_valve_chain_version", None) == VALVE_CHAIN_VERSION
        and getattr(current, "_participation_valve_chain_role", None) == "risk_on_outer"
    ):
        return {
            "status": "ok",
            "stable_fast_path": True,
            "version": VALVE_CHAIN_VERSION,
            "outer": _meta(current),
            "cycle_free": True,
        }

    import extended_leader_starter_valve as extended
    import risk_on_starter_participation_valve as risk_on

    clean_base = _clean_base_participation_valve(core_pipeline)
    extended._ORIGINAL_FN = clean_base
    extended_fn = extended._patched_participation_valve_ok
    extended_fn._extended_leader_starter_version = extended.VERSION  # type: ignore[attr-defined]
    extended_fn._participation_valve_chain_version = VALVE_CHAIN_VERSION  # type: ignore[attr-defined]
    extended_fn._participation_valve_chain_role = "extended_middle"  # type: ignore[attr-defined]
    extended._PATCHED = True

    risk_on._ORIGINAL_FN = extended_fn
    risk_on_fn = risk_on._patched_participation_valve_ok
    risk_on_fn._risk_on_starter_participation_version = risk_on.VERSION  # type: ignore[attr-defined]
    risk_on_fn._participation_valve_chain_version = VALVE_CHAIN_VERSION  # type: ignore[attr-defined]
    risk_on_fn._participation_valve_chain_role = "risk_on_outer"  # type: ignore[attr-defined]
    risk_on._PATCHED = True

    core_pipeline._participation_valve_ok = risk_on_fn
    return {
        "status": "ok",
        "stable_fast_path": False,
        "version": VALVE_CHAIN_VERSION,
        "cycle_free": True,
        "base_role": getattr(clean_base, "_participation_valve_chain_role", None),
        "extended_role": getattr(extended_fn, "_participation_valve_chain_role", None),
        "outer_role": getattr(risk_on_fn, "_participation_valve_chain_role", None),
        "outer": _meta(risk_on_fn),
    }


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
                "direct_core_base": True,
                "participation_valve_chain_version": VALVE_CHAIN_VERSION,
            }
        except Exception:
            pass
        return entries, rotations, blocked_entries

    composed._paper_exposure_composition_version = VERSION  # type: ignore[attr-defined]
    composed._paper_exposure_debug_patched = True  # type: ignore[attr-defined]
    composed._paper_exposure_debug_original = base_fn  # type: ignore[attr-defined]
    composed._core_entry_pipeline_version = getattr(base_fn, "_core_entry_pipeline_version", None)  # type: ignore[attr-defined]
    composed._core_entry_pipeline_non_wrapper_patched = bool(getattr(base_fn, "_core_entry_pipeline_non_wrapper_patched", False))  # type: ignore[attr-defined]
    composed._entry_pipeline_direct_core_base = True  # type: ignore[attr-defined]
    composed._entry_pipeline_direct_core_target = getattr(base_fn, "_entry_pipeline_direct_core_target", None)  # type: ignore[attr-defined]
    composed._participation_valve_chain_version = VALVE_CHAIN_VERSION  # type: ignore[attr-defined]
    return composed


def enforce(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}

    current = getattr(core, "try_entries_and_rotations", None)
    before = _meta(current)
    try:
        import core_entry_pipeline as core_pipeline
        valve_chain = _repair_participation_valve_chain(core_pipeline)
    except Exception as exc:
        payload = {
            "status": "error",
            "overall": "warn",
            "version": VERSION,
            "reason": f"participation_valve_chain_repair_failed:{type(exc).__name__}:{exc}",
            "before": before,
        }
        _save_payload(core, payload)
        return payload

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
            "direct_core_base": True,
            "recursion_safe": True,
            "participation_valve_chain": valve_chain,
            "stack": [
                "entry_pipeline_xray_outer",
                "paper_exposure_rotation_overlay",
                "direct_core_entry_pipeline_closure",
                "clean_base_participation_valve",
                "extended_leader_starter_overlay",
                "risk_on_starter_overlay",
            ],
            "authority_changed": False,
        }
        _save_payload(core, payload)
        return payload

    try:
        base = _direct_core_base(core, core_pipeline)
    except Exception as exc:
        payload = {
            "status": "error",
            "overall": "warn",
            "version": VERSION,
            "reason": f"direct_core_capture_failed:{type(exc).__name__}:{exc}",
            "before": before,
            "participation_valve_chain": valve_chain,
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
            "participation_valve_chain": valve_chain,
        }
        _save_payload(core, payload)
        return payload

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
        "participation_valve_chain": valve_chain,
        "stack": [
            "entry_pipeline_xray_outer",
            "paper_exposure_rotation_overlay",
            "direct_core_entry_pipeline_closure",
            "clean_base_participation_valve",
            "extended_leader_starter_overlay",
            "risk_on_starter_overlay",
        ],
        "core_authoritative": bool(after.get("core_entry_pipeline_patched")),
        "paper_exposure_composed": after.get("paper_exposure_version") == VERSION,
        "direct_core_base": bool(after.get("direct_core_base")),
        "recursion_safe": bool(after.get("direct_core_base") and valve_chain.get("cycle_free")),
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
    inner = _inner_callable(current)
    try:
        import core_entry_pipeline as core_pipeline
        valve_fn = getattr(core_pipeline, "_participation_valve_ok", None)
        valve_meta = _meta(valve_fn)
        valve_cycle_free = bool(
            getattr(valve_fn, "_participation_valve_chain_version", None) == VALVE_CHAIN_VERSION
            and getattr(valve_fn, "_participation_valve_chain_role", None) == "risk_on_outer"
        )
    except Exception:
        valve_meta = {}
        valve_cycle_free = False
    return {
        "status": "ok",
        "overall": "pass",
        "type": "entry_pipeline_composition_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "current_callable": _meta(current),
        "inner_callable": _meta(inner),
        "stack_stable": _is_stable(current),
        "direct_core_base": bool(getattr(inner, "_entry_pipeline_direct_core_base", False)),
        "recursion_safe": bool(getattr(inner, "_entry_pipeline_direct_core_base", False) and valve_cycle_free),
        "participation_valve_chain_version": VALVE_CHAIN_VERSION,
        "participation_valve_chain_cycle_free": valve_cycle_free,
        "participation_valve_callable": valve_meta,
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
