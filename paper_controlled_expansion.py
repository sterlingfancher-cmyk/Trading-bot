"""Paper-only controlled expansion overlay.

Purpose:
- Slightly increase paper-mode execution opportunity for ML learning.
- Raise effective risk-on max positions from 14 to 16.
- Raise post-harvest target open positions from 6 to 8.
- Keep max new entries per cycle controlled at 2.
- Label new paper entries for ML learning/audit separation.

This module is intentionally non-authoritative. It does not bypass halts,
self-defense, final-close locks, stop losses, score floors, cooldowns, or normal
entry quality checks. It does not grant ML trade authority.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict

VERSION = "paper-controlled-expansion-2026-06-04-v1"
ENABLED = os.environ.get("PAPER_CONTROLLED_EXPANSION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("PAPER_CONTROLLED_EXPANSION_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}

MAX_POSITIONS = int(os.environ.get("PAPER_CONTROLLED_EXPANSION_MAX_POSITIONS", "16"))
TARGET_OPEN_POSITIONS = int(os.environ.get("PAPER_CONTROLLED_EXPANSION_TARGET_OPEN_POSITIONS", "8"))
MAX_NEW_ENTRIES_PER_CYCLE = int(os.environ.get("PAPER_CONTROLLED_EXPANSION_MAX_NEW_ENTRIES_PER_CYCLE", "2"))
POST_HARVEST_MAX_OPEN_THRESHOLD = int(os.environ.get("PAPER_CONTROLLED_EXPANSION_POST_HARVEST_THRESHOLD", "6"))
STARTER_ALLOC_FACTOR = float(os.environ.get("PAPER_CONTROLLED_EXPANSION_STARTER_ALLOC_FACTOR", "0.45"))
RESEARCH_SLOT_MAX_ACTIVE = int(os.environ.get("PAPER_CONTROLLED_EXPANSION_RESEARCH_SLOT_MAX_ACTIVE", "2"))

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None:
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "portfolio"):
            return m
    return None


def _now_text(m: Any | None = None) -> str:
    try:
        return m.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _market_clean(market: Dict[str, Any] | None) -> bool:
    market = market or {}
    mode = str(market.get("market_mode", "") or "").lower()
    futures = market.get("futures_bias", {}) or {}
    breadth = market.get("breadth", {}) or {}
    return bool(
        mode == "risk_on"
        and not market.get("bear_confirmed")
        and not market.get("broad_market_soft")
        and str(market.get("regime", "")).lower() not in {"bear", "defensive"}
        and futures.get("action") not in {"block_opening_longs"}
        and breadth.get("action") not in {"risk_off_confirmation", "block_opening_longs"}
    )


def _positions_count(m: Any | None) -> int:
    try:
        return len((m.portfolio.get("positions", {}) or {}))
    except Exception:
        return 0


def _active_research_slots(m: Any | None) -> int:
    try:
        positions = (m.portfolio.get("positions", {}) or {})
        return sum(1 for pos in positions.values() if isinstance(pos, dict) and (pos.get("paper_learning") or {}).get("research_slot"))
    except Exception:
        return 0


def _learning_context(m: Any | None, symbol: str = "", market_mode: str | None = None) -> Dict[str, Any]:
    slots = _active_research_slots(m)
    research_slot = bool(slots < RESEARCH_SLOT_MAX_ACTIVE)
    return {
        "enabled": True,
        "paper_only": bool(PAPER_ONLY),
        "mode": "paper_only_controlled_expansion",
        "learning_mode": "paper_research" if research_slot else "paper_core_expansion",
        "research_slot": research_slot,
        "research_slot_max_active": RESEARCH_SLOT_MAX_ACTIVE,
        "trade_authority": "rules_based",
        "ml_authority": "shadow_only",
        "excluded_from_core_strategy_score": bool(research_slot),
        "included_in_ml_observation_data": True,
        "symbol": str(symbol or "").upper(),
        "market_mode": market_mode,
        "version": VERSION,
    }


def _patch_post_harvest_module() -> Dict[str, Any]:
    try:
        import post_harvest_redeployment_controller as ph
    except Exception as exc:
        return {"patched": False, "reason": f"import_failed:{type(exc).__name__}"}
    changed: Dict[str, Any] = {}
    for name, value in (
        ("TARGET_OPEN_POSITIONS", TARGET_OPEN_POSITIONS),
        ("MAX_OPEN_POSITIONS", POST_HARVEST_MAX_OPEN_THRESHOLD),
        ("MAX_ENTRIES_PER_CYCLE", MAX_NEW_ENTRIES_PER_CYCLE),
        ("STARTER_ALLOC_FACTOR", STARTER_ALLOC_FACTOR),
    ):
        try:
            old = getattr(ph, name, None)
            setattr(ph, name, value)
            changed[name] = {"old": old, "new": value}
        except Exception:
            pass
    return {"patched": bool(changed), "changed": changed}


def _patch_apply_aggression(m: Any) -> bool:
    current = getattr(m, "apply_aggression_adjustments", None)
    if not callable(current) or getattr(current, "_paper_controlled_expansion_patched", False):
        return False
    original = current

    def patched_apply_aggression_adjustments(params, market):
        out = original(params, market)
        try:
            active = bool(ENABLED and _paper_context() and _market_clean(market or {}))
            current_positions = _positions_count(m)
            if active:
                out["max_positions"] = max(int(out.get("max_positions", 0) or 0), MAX_POSITIONS, current_positions)
                try:
                    setattr(m, "MAX_NEW_ENTRIES_PER_CYCLE", MAX_NEW_ENTRIES_PER_CYCLE)
                except Exception:
                    pass
            out["paper_controlled_expansion"] = {
                "enabled": bool(ENABLED),
                "active": bool(active),
                "paper_context": bool(_paper_context()),
                "market_clean": bool(_market_clean(market or {})),
                "effective_max_positions": int(out.get("max_positions", 0) or 0),
                "target_open_positions": TARGET_OPEN_POSITIONS,
                "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE,
                "starter_alloc_factor": STARTER_ALLOC_FACTOR,
                "research_slot_max_active": RESEARCH_SLOT_MAX_ACTIVE,
                "ml_authority": "shadow_only",
                "trade_authority": "rules_based",
                "guardrails": [
                    "paper_only_by_default",
                    "does_not_bypass_halts",
                    "does_not_bypass_self_defense",
                    "does_not_bypass_final_close_lock",
                    "does_not_bypass_stop_losses",
                    "does_not_bypass_score_floors",
                    "normal_entry_quality_still_required",
                    "ml_shadow_only",
                ],
                "version": VERSION,
            }
            try:
                m.portfolio["paper_controlled_expansion"] = out["paper_controlled_expansion"]
            except Exception:
                pass
        except Exception:
            pass
        return out

    patched_apply_aggression_adjustments._paper_controlled_expansion_patched = True  # type: ignore[attr-defined]
    patched_apply_aggression_adjustments._paper_controlled_expansion_original = original  # type: ignore[attr-defined]
    m.apply_aggression_adjustments = patched_apply_aggression_adjustments
    return True


def _patch_enter_position(m: Any) -> bool:
    current = getattr(m, "enter_position", None)
    if not callable(current) or getattr(current, "_paper_controlled_expansion_entry_patched", False):
        return False
    original = current

    def patched_enter_position(signal, params, market_mode=None):
        result = original(signal, params, market_mode=market_mode)
        try:
            if not (ENABLED and _paper_context() and isinstance(result, dict) and not result.get("blocked")):
                return result
            symbol = str(result.get("symbol") or (signal or {}).get("symbol") or "").upper()
            context = _learning_context(m, symbol=symbol, market_mode=market_mode)
            pos = (m.portfolio.get("positions", {}) or {}).get(symbol)
            if isinstance(pos, dict):
                pos["paper_learning"] = context
                pos["paper_controlled_expansion"] = {
                    "max_positions": MAX_POSITIONS,
                    "target_open_positions": TARGET_OPEN_POSITIONS,
                    "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE,
                    "starter_alloc_factor": STARTER_ALLOC_FACTOR,
                    "version": VERSION,
                }
            trades = m.portfolio.get("trades", []) or []
            for row in reversed(trades[-10:]):
                if isinstance(row, dict) and row.get("action") == "entry" and str(row.get("symbol", "")).upper() == symbol:
                    row["paper_learning"] = context
                    row["paper_controlled_expansion"] = {
                        "max_positions": MAX_POSITIONS,
                        "target_open_positions": TARGET_OPEN_POSITIONS,
                        "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE,
                        "version": VERSION,
                    }
                    break
            result["paper_learning"] = context
        except Exception:
            pass
        return result

    patched_enter_position._paper_controlled_expansion_entry_patched = True  # type: ignore[attr-defined]
    patched_enter_position._paper_controlled_expansion_entry_original = original  # type: ignore[attr-defined]
    m.enter_position = patched_enter_position
    return True


def status_payload(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    latest = {}
    if m is not None:
        try:
            latest = (m.portfolio.get("paper_controlled_expansion") or {})
        except Exception:
            latest = {}
    ph = _patch_post_harvest_module() if m is not None else {"patched": False, "reason": "module_pending"}
    return {
        "status": "ok" if m is not None else "pending",
        "type": "paper_controlled_expansion_status",
        "version": VERSION,
        "generated_local": _now_text(m),
        "enabled": bool(ENABLED),
        "paper_context": bool(_paper_context()),
        "current_open_positions": _positions_count(m),
        "policy": {
            "max_positions": MAX_POSITIONS,
            "target_open_positions": TARGET_OPEN_POSITIONS,
            "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE,
            "post_harvest_max_open_threshold": POST_HARVEST_MAX_OPEN_THRESHOLD,
            "starter_alloc_factor": STARTER_ALLOC_FACTOR,
            "research_slot_max_active": RESEARCH_SLOT_MAX_ACTIVE,
            "ml_authority": "shadow_only",
            "trade_authority": "rules_based",
            "authority_changed": False,
        },
        "post_harvest_patch": ph,
        "latest": latest,
        "guardrails": [
            "paper_only_by_default",
            "does_not_bypass_risk_controls",
            "does_not_bypass_self_defense",
            "does_not_bypass_final_close_lock",
            "does_not_lower_score_thresholds",
            "does_not_change_ml_authority",
            "normal_entry_quality_still_required",
        ],
    }


def apply(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return status_payload(m)
    patched_aggression = _patch_apply_aggression(m)
    patched_entry = _patch_enter_position(m)
    ph = _patch_post_harvest_module()
    PATCHED_MODULE_IDS.add(id(m))
    payload = status_payload(m)
    payload["patched"] = {"apply_aggression_adjustments": bool(patched_aggression), "enter_position": bool(patched_entry), "post_harvest": ph}
    return payload


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    return apply(m)


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def paper_controlled_expansion_status():
        return jsonify(apply(m or _mod()))

    if "/paper/paper-controlled-expansion-status" not in existing:
        flask_app.add_url_rule("/paper/paper-controlled-expansion-status", "paper_controlled_expansion_status", paper_controlled_expansion_status)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(m or _mod())


try:
    apply(_mod())
except Exception:
    pass
