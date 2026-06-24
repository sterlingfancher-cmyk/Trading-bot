"""Profit Guard Redeployment Sleeve v4 — disabled safe mode.

The earlier sleeve used a try_entries_and_rotations wrapper. Live runner tests showed
that even with recursion guards, the wrapper chain could still trigger
`maximum recursion depth exceeded` in the auto-runner.

This safe-mode module intentionally does not patch the entry pipeline by default.
It keeps the diagnostic route and policy documentation available, but removes the
runtime wrapper from normal auto-runner flow.

Future profit-guard participation should be implemented inside the core entry
pipeline or a non-wrapper hook, not by wrapping try_entries_and_rotations again.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict

VERSION = "profit-guard-redeployment-sleeve-2026-06-24-v4-disabled-safe-mode"
PAPER_ONLY = os.environ.get("PROFIT_GUARD_REDEPLOYMENT_SLEEVE_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
# Critical safe-mode default: do not patch try_entries_and_rotations.
PATCH_ENABLED = os.environ.get("PROFIT_GUARD_REDEPLOYMENT_SLEEVE_PATCH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
MAX_REVIEWED = int(os.environ.get("PROFIT_GUARD_SLEEVE_MAX_REVIEWED", "30"))
MAX_ENTRIES_PER_DAY = int(os.environ.get("PROFIT_GUARD_SLEEVE_MAX_ENTRIES_PER_DAY", "1"))
ALLOC_FACTOR = float(os.environ.get("PROFIT_GUARD_SLEEVE_ALLOC_FACTOR", "0.35"))
MIN_SCORE = float(os.environ.get("PROFIT_GUARD_SLEEVE_MIN_SCORE", "0.018"))
ALLOWED_MARKET_MODES = sorted({s.strip().lower() for s in os.environ.get("PROFIT_GUARD_SLEEVE_ALLOWED_MARKET_MODES", "risk_on,constructive").split(",") if s.strip()})
REGISTERED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _current_latest(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {}
    try:
        latest = core.portfolio.get("profit_guard_redeployment_sleeve") or {}
        return latest if isinstance(latest, dict) else {}
    except Exception:
        return {}


def _is_currently_wrapped(core: Any = None) -> bool:
    try:
        current = getattr(core, "try_entries_and_rotations", None)
        return bool(getattr(current, "_profit_guard_redeployment_sleeve_patched", False))
    except Exception:
        return False


def _policy() -> Dict[str, Any]:
    return {
        "patch_enabled": bool(PATCH_ENABLED),
        "safe_mode": True,
        "wrapper_disabled_by_default": True,
        "reason_disabled": "auto_runner_recursion_depth_failures_from_wrapper_chain",
        "future_fix_required": "implement_inside_core_entry_pipeline_or_non_wrapper_hook",
        "max_reviewed": MAX_REVIEWED,
        "max_entries_per_day": MAX_ENTRIES_PER_DAY,
        "alloc_factor": ALLOC_FACTOR,
        "min_score": MIN_SCORE,
        "allowed_market_modes": ALLOWED_MARKET_MODES,
        "does_not_patch_try_entries_by_default": True,
        "does_not_raise_max_positions": True,
        "does_not_bypass_entry_quality_check": True,
        "does_not_bypass_regime_flip_guard": True,
        "does_not_bypass_self_defense": True,
        "does_not_bypass_cooldowns": True,
        "does_not_lower_score_thresholds": True,
        "hard_profit_lock_still_blocks": True,
        "giveback_lock_still_blocks": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "profit_guard_redeployment_sleeve_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": False,
        "patch_enabled": bool(PATCH_ENABLED),
        "safe_mode": True,
        "paper_context": bool(_paper_context()),
        "patched_try_entries": bool(_is_currently_wrapped(core)),
        "patched_this_call": {"try_entries_and_rotations": False},
        "latest": _current_latest(core),
        "policy": _policy(),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    # Safe mode: intentionally no runtime patch. If this ever needs to be turned
    # back on, build a non-wrapper implementation first.
    return status_payload(core or _mod())


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

    def status_route():
        return jsonify(status_payload(core or _mod()))

    if "/paper/profit-guard-redeployment-sleeve-status" not in existing:
        flask_app.add_url_rule("/paper/profit-guard-redeployment-sleeve-status", "profit_guard_redeployment_sleeve_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))


try:
    apply(_mod())
except Exception:
    pass
