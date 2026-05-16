"""Adaptive portfolio intelligence research layer.

Shadow/advisory only. This module adds higher-order research signals:
- Bayesian confidence updating
- rolling regime clustering
- volatility-state classification
- portfolio correlation governor
- adaptive capital allocator recommendations
- ML ensemble voting engine
- reinforcement reward decay learning
- trade-sequence behavioral memory
- dynamic strategy rotation
- autonomous strategy promotion/demotion scaffolding

No live authority. It does not place orders, modify allocation, change risk
controls, move stops, or suppress trades.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "adaptive-portfolio-intelligence-2026-05-16"
ENABLED = os.environ.get("ADAPTIVE_PORTFOLIO_INTELLIGENCE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
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


def _positions(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    positions = state.get("positions")
    return positions if isinstance(positions, dict) else {}


def _exit_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _list(state.get("trades")):
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or row.get("type") or "").lower()
        reason = str(row.get("exit_reason") or row.get("reason") or "").lower()
        if action in {"exit", "sell", "close", "cover"} or "exit" in reason or "stop" in reason or row.get("pnl_dollars") is not None:
            rows.append(row)
    return rows


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper()


def _regime(state: Dict[str, Any]) -> str:
    market = _dict(state.get("last_market"))
    return str(market.get("regime") or market.get("market_mode") or state.get("regime") or state.get("market_mode") or "unknown")


def _bayesian_confidence(state: Dict[str, Any]) -> Dict[str, Any]:
    alpha = 1.0
    beta = 1.0
    by_symbol: Dict[str, Dict[str, float]] = {}
    by_strategy: Dict[str, Dict[str, float]] = {}
    for row in _exit_rows(state):
        pnl = _f(row.get("pnl_dollars"), _f(row.get("pnl_pct"), 0.0))
        win = pnl > 0
        alpha += 1.0 if win else 0.0
        beta += 0.0 if win else 1.0
        sym = _symbol(row) or "UNKNOWN"
        strat = str(row.get("setup_family") or row.get("strategy") or row.get("exit_reason") or "unknown")
        by_symbol.setdefault(sym, {"alpha": 1.0, "beta": 1.0, "rows": 0})
        by_strategy.setdefault(strat, {"alpha": 1.0, "beta": 1.0, "rows": 0})
        by_symbol[sym]["alpha"] += 1.0 if win else 0.0
        by_symbol[sym]["beta"] += 0.0 if win else 1.0
        by_symbol[sym]["rows"] += 1
        by_strategy[strat]["alpha"] += 1.0 if win else 0.0
        by_strategy[strat]["beta"] += 0.0 if win else 1.0
        by_strategy[strat]["rows"] += 1
    def finalize(obj: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, Any]]:
        return {k: {"rows": int(v["rows"]), "posterior_win_prob": round(v["alpha"] / max(1.0, v["alpha"] + v["beta"]), 4), "alpha": round(v["alpha"], 2), "beta": round(v["beta"], 2)} for k, v in obj.items()}
    return {
        "overall_posterior_win_prob": round(alpha / max(1.0, alpha + beta), 4),
        "alpha": round(alpha, 2),
        "beta": round(beta, 2),
        "by_symbol": finalize(by_symbol),
        "by_strategy": finalize(by_strategy),
    }


def _rolling_regime_cluster(state: Dict[str, Any]) -> Dict[str, Any]:
    market = _dict(state.get("last_market"))
    risk_score = _f(market.get("risk_score"), 50.0)
    breadth = _dict(market.get("breadth"))
    breadth_state = str(breadth.get("state") or "unknown")
    mode = str(market.get("market_mode") or state.get("market_mode") or "neutral")
    if risk_score >= 75 and breadth_state == "supportive":
        cluster = "trend_expansion"
    elif risk_score >= 60:
        cluster = "constructive_risk_on"
    elif risk_score <= 35:
        cluster = "defensive_or_risk_off"
    elif mode in {"neutral", "mixed"}:
        cluster = "chop_or_transition"
    else:
        cluster = "unclassified_transition"
    return {"cluster": cluster, "risk_score": risk_score, "breadth_state": breadth_state, "market_mode": mode, "live_authority": False}


def _volatility_state(state: Dict[str, Any]) -> Dict[str, Any]:
    market = _dict(state.get("last_market"))
    vol = _f(market.get("volatility_score"), _f(_dict(state.get("risk_controls")).get("intraday_drawdown_pct"), 0.0) * 10.0)
    dd = _f(_dict(state.get("risk_controls")).get("intraday_drawdown_pct"), 0.0)
    if vol >= 75 or dd >= 2.0:
        state_name = "high_volatility_defensive"
    elif vol >= 45 or dd >= 0.75:
        state_name = "moderate_volatility"
    else:
        state_name = "low_to_normal_volatility"
    return {"volatility_state": state_name, "volatility_score": round(vol, 4), "intraday_drawdown_pct": round(dd, 4), "live_authority": False}


def _correlation_governor(state: Dict[str, Any]) -> Dict[str, Any]:
    positions = _positions(state)
    sector_counts: Dict[str, int] = {}
    bucket_counts: Dict[str, int] = {}
    symbols = []
    for sym, pos in positions.items():
        symbols.append(str(sym).upper())
        sector = str(_dict(pos).get("sector") or "unknown")
        bucket = str(_dict(pos).get("bucket") or "unknown")
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    concentration = max(sector_counts.values()) if sector_counts else 0
    risk = "elevated_concentration" if concentration >= 3 else "normal"
    return {"status": risk, "symbols": symbols, "sector_counts": sector_counts, "bucket_counts": bucket_counts, "max_sector_concentration": concentration, "recommendation": "reduce_new_same-sector_entries" if risk != "normal" else "no_correlation_action", "live_authority": False}


def _capital_allocator(state: Dict[str, Any], bayes: Dict[str, Any], vol: Dict[str, Any]) -> Dict[str, Any]:
    p = _f(bayes.get("overall_posterior_win_prob"), 0.5)
    vol_state = str(vol.get("volatility_state") or "")
    base = 1.0 + (p - 0.5) * 1.5
    if "high" in vol_state:
        base *= 0.55
    elif "moderate" in vol_state:
        base *= 0.8
    multiplier = max(0.25, min(1.5, base))
    return {"recommended_capital_multiplier": round(multiplier, 3), "reason": "bayesian_confidence_adjusted_for_volatility", "live_authority": False}


def _ensemble_vote(state: Dict[str, Any], bayes: Dict[str, Any], regime: Dict[str, Any], vol: Dict[str, Any]) -> Dict[str, Any]:
    votes = []
    votes.append({"model": "bayesian_confidence", "vote": "bullish" if _f(bayes.get("overall_posterior_win_prob"), 0.5) >= 0.53 else "neutral"})
    votes.append({"model": "regime_cluster", "vote": "bullish" if regime.get("cluster") in {"trend_expansion", "constructive_risk_on"} else "defensive"})
    votes.append({"model": "volatility_state", "vote": "defensive" if str(vol.get("volatility_state", "")).startswith("high") else "neutral"})
    score = sum(1 if v["vote"] == "bullish" else -1 if v["vote"] == "defensive" else 0 for v in votes)
    consensus = "risk_on_bias" if score > 0 else "defensive_bias" if score < 0 else "neutral_bias"
    return {"consensus": consensus, "score": score, "votes": votes, "live_authority": False}


def _reward_decay(state: Dict[str, Any]) -> Dict[str, Any]:
    rows = _exit_rows(state)[-25:]
    decay = 0.92
    weighted = 0.0
    weight_sum = 0.0
    for idx, row in enumerate(reversed(rows)):
        w = decay ** idx
        pnl = _f(row.get("pnl_pct"), _f(row.get("pnl_dollars"), 0.0))
        reward = 1.0 if pnl > 0 else -1.0 if pnl < 0 else 0.0
        weighted += reward * w
        weight_sum += w
    return {"decay_factor": decay, "recent_reward_score": round(weighted / max(1e-9, weight_sum), 4) if rows else 0.0, "rows": len(rows), "live_authority": False}


def _sequence_memory(state: Dict[str, Any]) -> Dict[str, Any]:
    rows = _exit_rows(state)[-12:]
    sequence = []
    for row in rows:
        pnl = _f(row.get("pnl_dollars"), _f(row.get("pnl_pct"), 0.0))
        sequence.append("W" if pnl > 0 else "L" if pnl < 0 else "F")
    streak = 0
    last = sequence[-1] if sequence else ""
    for x in reversed(sequence):
        if x == last:
            streak += 1
        else:
            break
    behavior = "loss_streak_caution" if last == "L" and streak >= 2 else "win_streak_confidence" if last == "W" and streak >= 2 else "mixed_sequence"
    return {"recent_sequence": sequence, "last_result": last, "streak": streak, "behavioral_state": behavior, "live_authority": False}


def _strategy_rotation(state: Dict[str, Any], bayes: Dict[str, Any]) -> Dict[str, Any]:
    strategies = _dict(bayes.get("by_strategy"))
    decisions = []
    for name, data in strategies.items():
        rows = int(_f(_dict(data).get("rows"), 0.0))
        p = _f(_dict(data).get("posterior_win_prob"), 0.5)
        if rows < 3:
            action = "insufficient_data"
        elif p >= 0.58:
            action = "promote_candidate"
        elif p <= 0.42:
            action = "demote_candidate"
        else:
            action = "maintain"
        decisions.append({"strategy": name, "rows": rows, "posterior_win_prob": p, "rotation_action": action, "live_authority": False})
    return {"strategy_decisions": decisions, "promotion_count": sum(1 for d in decisions if d.get("rotation_action") == "promote_candidate"), "demotion_count": sum(1 for d in decisions if d.get("rotation_action") == "demote_candidate"), "live_authority": False}


def build_payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    bayes = _bayesian_confidence(state)
    regime = _rolling_regime_cluster(state)
    vol = _volatility_state(state)
    corr = _correlation_governor(state)
    allocator = _capital_allocator(state, bayes, vol)
    ensemble = _ensemble_vote(state, bayes, regime, vol)
    reward = _reward_decay(state)
    sequence = _sequence_memory(state)
    rotation = _strategy_rotation(state, bayes)
    section = state.setdefault("adaptive_portfolio_intelligence", {})
    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": _now(mod),
        "bayesian_confidence": bayes,
        "rolling_regime_cluster": regime,
        "volatility_state": vol,
        "portfolio_correlation_governor": corr,
        "adaptive_capital_allocator": allocator,
        "ml_ensemble_vote": ensemble,
        "reinforcement_reward_decay": reward,
        "trade_sequence_memory": sequence,
        "dynamic_strategy_rotation": rotation,
        "autonomous_strategy_promotion_demotion": {"enabled": False, "mode": "advisory_candidates_only", "promotion_count": rotation.get("promotion_count"), "demotion_count": rotation.get("demotion_count")},
        "recommended_actions": [
            "Keep promotion/demotion advisory until walk-forward validation passes.",
            "Use Bayesian confidence and ensemble votes for research scoring only.",
            "Do not enable adaptive capital allocation until execution sample size and regime coverage improve.",
        ],
    })
    return section


def payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    section = build_payload(state, mod) if ENABLED else _dict(state.get("adaptive_portfolio_intelligence"))
    return {
        "status": "ok",
        "type": "adaptive_portfolio_intelligence_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_authority": False,
        "bayesian_confidence": section.get("bayesian_confidence"),
        "rolling_regime_cluster": section.get("rolling_regime_cluster"),
        "volatility_state": section.get("volatility_state"),
        "portfolio_correlation_governor": section.get("portfolio_correlation_governor"),
        "adaptive_capital_allocator": section.get("adaptive_capital_allocator"),
        "ml_ensemble_vote": section.get("ml_ensemble_vote"),
        "reinforcement_reward_decay": section.get("reinforcement_reward_decay"),
        "trade_sequence_memory": section.get("trade_sequence_memory"),
        "dynamic_strategy_rotation": section.get("dynamic_strategy_rotation"),
        "autonomous_strategy_promotion_demotion": section.get("autonomous_strategy_promotion_demotion"),
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
                        build_payload(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("adaptive_portfolio_intelligence", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                return original(state)
            patched_save_state._adaptive_portfolio_intelligence_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "ADAPTIVE_PORTFOLIO_INTELLIGENCE_VERSION", VERSION)
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
        ("/paper/adaptive-portfolio-status", "paper_adaptive_portfolio_status"),
        ("/paper/bayesian-confidence-status", "paper_bayesian_confidence_status"),
        ("/paper/regime-cluster-status", "paper_regime_cluster_status"),
        ("/paper/volatility-state-status", "paper_volatility_state_status"),
        ("/paper/correlation-governor-status", "paper_correlation_governor_status"),
        ("/paper/capital-allocator-status", "paper_capital_allocator_status"),
        ("/paper/ml-ensemble-status", "paper_ml_ensemble_status"),
        ("/paper/reward-decay-status", "paper_reward_decay_status"),
        ("/paper/strategy-rotation-status", "paper_strategy_rotation_status"),
    ):
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, status_route)

    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "live_authority": False}
