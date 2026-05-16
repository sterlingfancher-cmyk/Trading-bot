"""Adaptive ML research layer.

Shadow/advisory only. This module adds research outputs for:
- walk-forward ML validation scaffolding
- probabilistic trade confidence scoring
- regime-specific MAE/MFE profiles
- symbol personality modeling
- adaptive position sizing recommendations based on path quality
- reinforcement-style reward scoring for exits

No live trading authority. It does not place orders, modify stops, resize
positions, or override risk controls.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "adaptive-ml-research-2026-05-16"
ENABLED = os.environ.get("ADAPTIVE_ML_RESEARCH_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_AUTHORITY = False
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        value = float(x)
        return default if math.isnan(value) or math.isinf(value) else value
    except Exception:
        return default


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
            return mod
    return None


def _now(mod: Any = None) -> str:
    try:
        return mod.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return (state if isinstance(state, dict) else {}), mod


def _trade_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [row for row in _list(state.get("trades")) if isinstance(row, dict)]


def _exit_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _trade_rows(state):
        action = str(row.get("action") or row.get("type") or "").lower()
        reason = str(row.get("exit_reason") or row.get("reason") or "").lower()
        if action in {"exit", "sell", "close", "cover"} or "exit" in reason or "stop" in reason or row.get("pnl_dollars") is not None:
            rows.append(row)
    return rows


def _path_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    path = _dict(state.get("intratrade_path_capture"))
    rows = [row for row in _dict(path.get("paths")).values() if isinstance(row, dict)]
    rows.extend([row for row in _list(path.get("closed_path_archive")) if isinstance(row, dict)])
    return rows


def _regime(row: Dict[str, Any], state: Dict[str, Any]) -> str:
    return str(row.get("regime") or row.get("market_mode") or _dict(state.get("last_market")).get("regime") or _dict(state.get("last_market")).get("market_mode") or "unknown")


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper()


def _side(row: Dict[str, Any]) -> str:
    return str(row.get("side") or row.get("direction") or "long").lower()


def _group_profile(rows: List[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = str(key_fn(row) or "unknown")
        mae = _f(row.get("mae_pct"), 0.0)
        mfe = _f(row.get("mfe_pct"), 0.0)
        pnl = _f(row.get("pnl_pct"), _f(row.get("pnl_dollars"), 0.0))
        g = out.setdefault(key, {"rows": 0, "wins": 0, "mae_sum": 0.0, "mfe_sum": 0.0, "pnl_sum": 0.0, "eff_sum": 0.0, "eff_rows": 0})
        g["rows"] += 1
        g["wins"] += 1 if pnl > 0 else 0
        g["mae_sum"] += mae
        g["mfe_sum"] += mfe
        g["pnl_sum"] += pnl
        if mae != 0.0 or mfe != 0.0:
            g["eff_sum"] += mfe / max(0.01, abs(mae))
            g["eff_rows"] += 1
    for g in out.values():
        n = max(1, int(g.get("rows", 1)))
        eff_n = max(1, int(g.get("eff_rows", 1)))
        g.update({
            "win_rate": round(g["wins"] / n, 4),
            "avg_mae_pct": round(g["mae_sum"] / n, 4),
            "avg_mfe_pct": round(g["mfe_sum"] / n, 4),
            "avg_pnl_metric": round(g["pnl_sum"] / n, 4),
            "avg_path_efficiency": round(g["eff_sum"] / eff_n, 4) if g.get("eff_rows") else None,
        })
        for k in ["mae_sum", "mfe_sum", "pnl_sum", "eff_sum", "eff_rows"]:
            g.pop(k, None)
    return out


def _reward_score(row: Dict[str, Any]) -> float:
    pnl = _f(row.get("pnl_pct"), _f(row.get("pnl_dollars"), 0.0))
    mae = _f(row.get("mae_pct"), 0.0)
    mfe = _f(row.get("mfe_pct"), 0.0)
    duration = _f(row.get("duration_seconds"), 0.0)
    score = 50.0 + max(-25.0, min(25.0, pnl * 8.0))
    score += max(-12.0, min(12.0, mfe * 4.0))
    score -= max(0.0, min(15.0, abs(mae) * 5.0))
    if duration > 0 and pnl <= 0 and duration > 7200:
        score -= 5.0
    return round(max(0.0, min(100.0, score)), 2)


def _confidence_for_path(row: Dict[str, Any], regime_profiles: Dict[str, Any], symbol_profiles: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row)
    regime = _regime(row, state)
    mae = _f(row.get("mae_pct"), 0.0)
    mfe = _f(row.get("mfe_pct"), 0.0)
    eff = mfe / max(0.01, abs(mae)) if (mfe != 0.0 or mae != 0.0) else 1.0
    regime_wr = _f(_dict(regime_profiles.get(regime)).get("win_rate"), 0.5)
    symbol_wr = _f(_dict(symbol_profiles.get(symbol)).get("win_rate"), 0.5)
    p = 0.50 + (regime_wr - 0.50) * 0.30 + (symbol_wr - 0.50) * 0.40
    p += max(-0.08, min(0.10, (eff - 1.0) * 0.04))
    p += max(-0.06, min(0.08, mfe * 0.015))
    p -= max(0.0, min(0.08, abs(mae) * 0.015))
    p = max(0.05, min(0.95, p))
    if _dict(symbol_profiles.get(symbol)).get("rows", 0) < 3:
        confidence_label = "low_data_symbol"
        p = 0.50 + (p - 0.50) * 0.45
    elif _dict(regime_profiles.get(regime)).get("rows", 0) < 5:
        confidence_label = "low_data_regime"
        p = 0.50 + (p - 0.50) * 0.60
    else:
        confidence_label = "research_confidence_only"
    return {
        "symbol": symbol,
        "side": _side(row),
        "regime": regime,
        "probabilistic_trade_confidence": round(p, 4),
        "confidence_edge": round(p - 0.50, 4),
        "confidence_label": confidence_label,
        "path_efficiency": round(eff, 4),
        "adaptive_position_size_multiplier": round(max(0.25, min(1.5, 1.0 + (p - 0.50) * 1.5)), 3),
        "live_authority": False,
    }


def _walk_forward(state: Dict[str, Any], scored_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for row in _exit_rows(state):
        date = str(row.get("date") or row.get("local_date") or "")[:10]
        if not date and row.get("time"):
            try:
                date = dt.datetime.fromtimestamp(float(row.get("time"))).strftime("%Y-%m-%d")
            except Exception:
                date = "unknown"
        by_date.setdefault(date or "unknown", []).append(row)
    dates = sorted([d for d in by_date.keys() if d != "unknown"])
    test_days = dates[-max(1, min(5, len(dates))):]
    train_days = [d for d in dates if d not in test_days]
    test_rows = [row for d in test_days for row in by_date.get(d, [])]
    wins = sum(1 for row in test_rows if _f(row.get("pnl_dollars"), _f(row.get("pnl_pct"), 0.0)) > 0)
    n = len(test_rows)
    return {
        "status": "insufficient_data" if n < 10 or len(train_days) < 5 else "research_proxy_ready",
        "formal_walk_forward_passed": False,
        "train_days": len(train_days),
        "test_days": len(test_days),
        "test_rows": n,
        "proxy_test_win_rate": round(wins / max(1, n), 4),
        "note": "Proxy only. Formal walk-forward remains disabled until execution/outcome sample size is larger.",
    }


def research_payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    path_rows = _path_rows(state)
    exit_rows = _exit_rows(state)
    combined = path_rows + exit_rows
    regime_profiles = _group_profile(combined, lambda row: _regime(row, state))
    symbol_profiles = _group_profile(combined, _symbol)
    active_confidence = [_confidence_for_path(row, regime_profiles, symbol_profiles, state) for row in path_rows if _symbol(row)]
    rewards = []
    for row in combined[-200:]:
        sym = _symbol(row)
        if not sym:
            continue
        rewards.append({"symbol": sym, "side": _side(row), "regime": _regime(row, state), "reward_score": _reward_score(row), "pnl_pct": row.get("pnl_pct"), "mae_pct": row.get("mae_pct"), "mfe_pct": row.get("mfe_pct"), "live_authority": False})
    walk = _walk_forward(state, rewards)

    section = state.setdefault("adaptive_ml_research", {})
    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": _now(mod),
        "walk_forward": walk,
        "regime_profiles": regime_profiles,
        "symbol_profiles": symbol_profiles,
        "active_confidence": active_confidence[-50:],
        "exit_reward_tail": rewards[-50:],
        "summary": {
            "path_rows": len(path_rows),
            "exit_rows": len(exit_rows),
            "regime_profile_count": len(regime_profiles),
            "symbol_profile_count": len(symbol_profiles),
            "active_confidence_count": len(active_confidence),
            "reward_rows": len(rewards),
        },
        "recommended_actions": [
            "Keep adaptive position sizing advisory until Phase 3A gates and formal walk-forward pass.",
            "Use symbol personality profiles to identify instruments with poor path efficiency before increasing exposure.",
            "Use reward scores to compare exit policies before enabling dynamic exit authority.",
        ],
    })
    return section


def payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    section = research_payload(state, mod) if ENABLED else _dict(state.get("adaptive_ml_research"))
    return {
        "status": "ok",
        "type": "adaptive_ml_research_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_authority": False,
        "summary": section.get("summary"),
        "walk_forward": section.get("walk_forward"),
        "active_confidence_tail": _list(section.get("active_confidence"))[-10:],
        "exit_reward_tail": _list(section.get("exit_reward_tail"))[-10:],
        "recommended_actions": section.get("recommended_actions", []),
    }


def apply(module: Any = None) -> Dict[str, Any]:
    module = module or _module()
    if module is None:
        return {"status": "not_applied", "version": VERSION, "reason": "module_missing"}
    if id(module) in PATCHED_MODULE_IDS:
        return {"status": "ok", "version": VERSION, "already_patched": True, "live_authority": False}
    try:
        original = getattr(module, "save_state", None)
        if callable(original):
            def patched_save_state(state):
                try:
                    if ENABLED and isinstance(state, dict):
                        research_payload(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("adaptive_ml_research", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                return original(state)
            patched_save_state._adaptive_ml_research_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "ADAPTIVE_ML_RESEARCH_VERSION", VERSION)
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(module))
    return {"status": "ok", "version": VERSION, "live_authority": False}


def register_routes(flask_app: Any, module: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    module = module or _module()
    apply(module)
    if id(flask_app) in REGISTERED_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        state, mod = _load_state(module)
        return jsonify(payload(state, mod))

    for path, endpoint in (
        ("/paper/adaptive-ml-status", "paper_adaptive_ml_status"),
        ("/paper/walk-forward-ml-status", "paper_walk_forward_ml_status"),
        ("/paper/symbol-personality-status", "paper_symbol_personality_status"),
        ("/paper/exit-reward-status", "paper_exit_reward_status"),
    ):
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, status_route)

    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/adaptive-ml-status", "/paper/walk-forward-ml-status", "/paper/symbol-personality-status", "/paper/exit-reward-status"], "live_authority": False}
