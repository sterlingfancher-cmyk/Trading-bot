"""Best-of-cycle entry arbitration v2 — diagnostic safe mode.

The original v1 implementation wrapped try_entries_and_rotations so already-passing
entry candidates could be ranked before consuming limited cycle slots. Live runner
freshness checks later showed persistent `maximum recursion depth exceeded` errors
while wrapper-based overlays were active.

This safe-mode module intentionally does not patch try_entries_and_rotations by
default. It keeps the status route and policy documentation available while
removing this wrapper from the auto-runner execution path.

Future best-of-cycle ranking should be implemented inside the core entry pipeline
or as a non-wrapper pre-entry candidate selector.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict

VERSION = "best-of-cycle-entry-arbitration-2026-06-24-v2-disabled-safe-mode"
ENABLED = os.environ.get("BEST_OF_CYCLE_ENTRY_ARBITRATION_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
PAPER_ONLY = os.environ.get("BEST_OF_CYCLE_ENTRY_ARBITRATION_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
PATCH_ENABLED = os.environ.get("BEST_OF_CYCLE_ENTRY_ARBITRATION_PATCH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
MAX_REVIEWED = int(os.environ.get("BEST_OF_CYCLE_MAX_REVIEWED", "40"))
MAX_NOT_SELECTED_ROWS = int(os.environ.get("BEST_OF_CYCLE_MAX_NOT_SELECTED_ROWS", "15"))

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()

THEME_PRIORITY = {
    "space_stocks": 0.006,
    "bitcoin_ai_compute": 0.005,
    "semi_leaders": 0.0045,
    "data_center_infra": 0.004,
    "small_cap_momentum": 0.0035,
    "mega_cap_ai": 0.003,
    "cloud_cyber_software": 0.0025,
    "precious_metals": 0.0015,
}

PREFERRED_SYMBOLS = {
    "RKLB", "RDW", "LUNR", "ASTS", "SPCX", "SATL",
    "AMD", "AVGO", "MU", "LRCX", "NVTS", "NBIS", "GEV", "STX", "WDC", "DELL", "HPE",
    "CIFR", "CLSK", "RIOT", "HIVE", "HUT", "BTDR", "WULF", "CORZ", "IREN", "MARA",
}


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


def _currently_wrapped(core: Any = None) -> bool:
    try:
        current = getattr(core, "try_entries_and_rotations", None)
        return bool(getattr(current, "_best_of_cycle_arbitration_patched", False))
    except Exception:
        return False


def _latest(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {}
    try:
        latest = core.portfolio.get("best_of_cycle_entry_arbitration") or {}
        return latest if isinstance(latest, dict) else {}
    except Exception:
        return {}


def _policy() -> Dict[str, Any]:
    return {
        "enabled": bool(ENABLED),
        "patch_enabled": bool(PATCH_ENABLED),
        "safe_mode": True,
        "wrapper_disabled_by_default": True,
        "reason_disabled": "auto_runner_recursion_depth_failures_from_wrapper_chain",
        "future_fix_required": "implement_inside_core_entry_pipeline_or_non_wrapper_pre_entry_selector",
        "max_reviewed": MAX_REVIEWED,
        "max_not_selected_rows": MAX_NOT_SELECTED_ROWS,
        "theme_priority": THEME_PRIORITY,
        "preferred_symbols": sorted(PREFERRED_SYMBOLS),
        "does_not_patch_try_entries_by_default": True,
        "does_not_raise_max_positions": True,
        "does_not_bypass_risk_controls": True,
        "does_not_bypass_self_defense": True,
        "does_not_lower_score_thresholds": True,
        "normal_entry_quality_check_required": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "best_of_cycle_entry_arbitration_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "patch_enabled": bool(PATCH_ENABLED),
        "safe_mode": True,
        "paper_context": bool(_paper_context()),
        "patched_try_entries": bool(_currently_wrapped(core)),
        "patched_this_call": {"try_entries_and_rotations": False},
        "latest": _latest(core),
        "policy": _policy(),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    # Safe mode: intentionally no runtime patch. Do not revive this wrapper in
    # production; implement ranking inside the core entry pipeline instead.
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

    if "/paper/best-of-cycle-entry-arbitration-status" not in existing:
        flask_app.add_url_rule(
            "/paper/best-of-cycle-entry-arbitration-status",
            "best_of_cycle_entry_arbitration_status",
            status_route,
        )
    REGISTERED_APP_IDS.add(id(flask_app))


try:
    apply(_mod())
except Exception:
    pass
