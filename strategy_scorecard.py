"""Strategy-level scorecards built from canonical strategy labels.

Advisory analytics only. Uses canonical strategy_id/setup labels to summarize
performance by strategy so future promotion/demotion can be based on stable
statistics instead of ad-hoc reason strings.

Routes:
- /paper/strategy-scorecard-status
- /paper/strategy-id-scorecards
- /paper/strategy-promotion-candidates
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "strategy-scorecard-2026-05-16"
ENABLED = os.environ.get("STRATEGY_SCORECARD_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_AUTHORITY = False
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()


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


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        value = float(x)
        return default if math.isnan(value) or math.isinf(value) else value
    except Exception:
        return default


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _ensure_labels(state: Dict[str, Any]) -> None:
    try:
        import strategy_label_propagation
        if hasattr(strategy_label_propagation, "propagate"):
            strategy_label_propagation.propagate(state)
    except Exception:
        pass


def _is_execution(row: Dict[str, Any]) -> bool:
    action = str(row.get("action") or row.get("type") or "").lower()
    if action in {"entry", "buy", "short", "sell_short", "exit", "sell", "close", "cover"}:
        return True
    if row.get("pnl_dollars") is not None or row.get("pnl_pct") is not None:
        return True
    return False


def _is_exit(row: Dict[str, Any]) -> bool:
    action = str(row.get("action") or row.get("type") or "").lower()
    reason = str(row.get("exit_reason") or row.get("reason") or "").lower()
    return action in {"exit", "sell", "close", "cover"} or "exit" in reason or "stop" in reason or row.get("pnl_dollars") is not None


def _trade_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = [row for row in _list(state.get("trades")) if isinstance(row, dict) and _is_execution(row)]
    return rows


def _quality_by_strategy(state: Dict[str, Any]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    tq = _dict(state.get("trade_quality_telemetry"))
    candidates: List[Dict[str, Any]] = []
    for key in ("recent_quality_tail", "recent_quality_rows", "quality_rows"):
        candidates.extend([row for row in _list(tq.get(key)) if isinstance(row, dict)])
    for row in candidates:
        sid = str(row.get("strategy_id") or "").strip()
        if not sid:
            continue
        score = row.get("quality_score") or row.get("trade_quality_score") or row.get("score")
        if score is not None:
            out.setdefault(sid, []).append(_f(score, 0.0))
    return out


def _reward_by_strategy(state: Dict[str, Any]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    research = _dict(state.get("adaptive_ml_research"))
    for row in _list(research.get("exit_reward_tail")) + _list(research.get("reward_rows")):
        if not isinstance(row, dict):
            continue
        sid = str(row.get("strategy_id") or "").strip()
        if not sid:
            continue
        reward = row.get("reward_score") or row.get("reward") or row.get("exit_reward")
        if reward is not None:
            out.setdefault(sid, []).append(_f(reward, 0.0))
    return out


def _empty_card(strategy_id: str) -> Dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "setup_family": None,
        "entry_model": None,
        "exit_model": None,
        "risk_model": None,
        "side": None,
        "execution_rows": 0,
        "exit_rows": 0,
        "wins": 0,
        "losses": 0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "best_trade": None,
        "worst_trade": None,
        "quality_scores": [],
        "reward_scores": [],
        "symbols": {},
        "recent_results": [],
    }


def _finalize_card(card: Dict[str, Any]) -> Dict[str, Any]:
    gross_loss_abs = abs(_f(card.get("gross_loss"), 0.0))
    gross_profit = _f(card.get("gross_profit"), 0.0)
    exits = int(card.get("exit_rows") or 0)
    wins = int(card.get("wins") or 0)
    losses = int(card.get("losses") or 0)
    quality_scores = [_f(x, 0.0) for x in _list(card.pop("quality_scores", []))]
    reward_scores = [_f(x, 0.0) for x in _list(card.pop("reward_scores", []))]
    win_rate = round(wins / exits, 4) if exits else None
    profit_factor = round(gross_profit / gross_loss_abs, 4) if gross_loss_abs > 0 else (None if gross_profit == 0 else 999.0)
    avg_quality = round(sum(quality_scores) / len(quality_scores), 4) if quality_scores else None
    avg_reward = round(sum(reward_scores) / len(reward_scores), 4) if reward_scores else None
    net_pnl = round(_f(card.get("net_pnl"), 0.0), 4)

    if exits < 5:
        confidence = "very_low_sample"
    elif exits < 15:
        confidence = "low_sample"
    elif exits < 30:
        confidence = "medium_sample"
    else:
        confidence = "higher_sample"

    if exits < 10:
        action = "collect_more_data"
    elif win_rate is not None and profit_factor is not None and win_rate >= 0.55 and profit_factor >= 1.25 and net_pnl > 0:
        action = "promote_candidate_advisory"
    elif win_rate is not None and profit_factor is not None and (win_rate <= 0.40 or profit_factor < 0.85) and net_pnl < 0:
        action = "demote_candidate_advisory"
    else:
        action = "maintain_observation"

    symbols = _dict(card.get("symbols"))
    top_symbols = sorted(symbols.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {
        "strategy_id": card.get("strategy_id"),
        "setup_family": card.get("setup_family"),
        "entry_model": card.get("entry_model"),
        "exit_model": card.get("exit_model"),
        "risk_model": card.get("risk_model"),
        "side": card.get("side"),
        "execution_rows": int(card.get("execution_rows") or 0),
        "exit_rows": exits,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "gross_profit": round(gross_profit, 4),
        "gross_loss": round(_f(card.get("gross_loss"), 0.0), 4),
        "profit_factor": profit_factor,
        "net_pnl": net_pnl,
        "best_trade": card.get("best_trade"),
        "worst_trade": card.get("worst_trade"),
        "avg_trade_quality_score": avg_quality,
        "avg_reward_score": avg_reward,
        "sample_confidence": confidence,
        "rotation_action": action,
        "top_symbols": [{"symbol": k, "rows": v} for k, v in top_symbols],
        "recent_results": _list(card.get("recent_results"))[-12:],
        "live_authority": False,
    }


def build_scorecards(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    if isinstance(state, dict):
        _ensure_labels(state)
    cards: Dict[str, Dict[str, Any]] = {}
    q = _quality_by_strategy(state)
    r = _reward_by_strategy(state)
    for row in _trade_rows(state):
        sid = str(row.get("strategy_id") or "unlabeled_strategy").strip() or "unlabeled_strategy"
        card = cards.setdefault(sid, _empty_card(sid))
        for key in ("setup_family", "entry_model", "exit_model", "risk_model", "side"):
            if not card.get(key) and row.get(key):
                card[key] = row.get(key)
        card["execution_rows"] += 1
        sym = str(row.get("symbol") or "UNKNOWN").upper()
        card["symbols"][sym] = int(card["symbols"].get(sym, 0)) + 1
        if _is_exit(row):
            card["exit_rows"] += 1
            pnl = _f(row.get("pnl_dollars"), _f(row.get("pnl_pct"), 0.0))
            card["net_pnl"] += pnl
            if pnl > 0:
                card["wins"] += 1
                card["gross_profit"] += pnl
                card["recent_results"].append("W")
            elif pnl < 0:
                card["losses"] += 1
                card["gross_loss"] += pnl
                card["recent_results"].append("L")
            else:
                card["recent_results"].append("F")
            if card["best_trade"] is None or pnl > _f(card["best_trade"].get("pnl"), -10**9):
                card["best_trade"] = {"symbol": sym, "pnl": round(pnl, 4), "reason": row.get("exit_reason") or row.get("reason")}
            if card["worst_trade"] is None or pnl < _f(card["worst_trade"].get("pnl"), 10**9):
                card["worst_trade"] = {"symbol": sym, "pnl": round(pnl, 4), "reason": row.get("exit_reason") or row.get("reason")}
    for sid, scores in q.items():
        cards.setdefault(sid, _empty_card(sid))["quality_scores"].extend(scores)
    for sid, scores in r.items():
        cards.setdefault(sid, _empty_card(sid))["reward_scores"].extend(scores)

    finalized = [_finalize_card(card) for card in cards.values()]
    finalized.sort(key=lambda c: (_f(c.get("net_pnl"), 0.0), _f(c.get("profit_factor"), 0.0) if c.get("profit_factor") is not None else 0.0), reverse=True)
    promotions = [c for c in finalized if c.get("rotation_action") == "promote_candidate_advisory"]
    demotions = [c for c in finalized if c.get("rotation_action") == "demote_candidate_advisory"]
    collect = [c for c in finalized if c.get("rotation_action") == "collect_more_data"]
    section = state.setdefault("strategy_scorecard", {}) if isinstance(state, dict) else {}
    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": _now(mod),
        "strategy_count": len(finalized),
        "promotion_candidates_count": len(promotions),
        "demotion_candidates_count": len(demotions),
        "collect_more_data_count": len(collect),
        "scorecards": finalized[:100],
        "top_scorecards": finalized[:10],
        "promotion_candidates": promotions[:25],
        "demotion_candidates": demotions[:25],
        "recommendation": "Use scorecards for advisory review only until Phase 3A sample-size and walk-forward gates pass.",
    })
    return section


def payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    section = build_scorecards(state, mod) if ENABLED and isinstance(state, dict) else _dict(state.get("strategy_scorecard") if isinstance(state, dict) else {})
    return {
        "status": "ok",
        "type": "strategy_scorecard_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_authority": False,
        "strategy_count": section.get("strategy_count", 0),
        "promotion_candidates_count": section.get("promotion_candidates_count", 0),
        "demotion_candidates_count": section.get("demotion_candidates_count", 0),
        "collect_more_data_count": section.get("collect_more_data_count", 0),
        "top_scorecards": section.get("top_scorecards", []),
        "promotion_candidates": section.get("promotion_candidates", []),
        "demotion_candidates": section.get("demotion_candidates", []),
        "recommendation": section.get("recommendation"),
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
                        build_scorecards(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("strategy_scorecard", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                return original(state)
            patched_save_state._strategy_scorecard_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "STRATEGY_SCORECARD_VERSION", VERSION)
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
        ("/paper/strategy-scorecard-status", "paper_strategy_scorecard_status"),
        ("/paper/strategy-id-scorecards", "paper_strategy_id_scorecards"),
        ("/paper/strategy-promotion-candidates", "paper_strategy_promotion_candidates"),
    ):
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/strategy-scorecard-status", "/paper/strategy-id-scorecards", "/paper/strategy-promotion-candidates"], "live_authority": False}
