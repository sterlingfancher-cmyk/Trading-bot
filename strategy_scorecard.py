"""Strategy, setup-family, and bucket scorecards.

Advisory analytics only. Uses canonical strategy/setup/bucket labels to summarize
performance so future promotion/demotion can be based on stable statistics
instead of ad-hoc reason strings.

Routes:
- /paper/strategy-scorecard-status
- /paper/strategy-id-scorecards
- /paper/strategy-promotion-candidates
- /paper/setup-family-scorecards
- /paper/bucket-scorecards

No live authority is granted here. This module never places trades, never changes
ML authority, and never bypasses risk controls.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "strategy-scorecard-2026-06-16-v2-setup-bucket"
ENABLED = os.environ.get("STRATEGY_SCORECARD_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_AUTHORITY = False
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()

DIMENSION_CONFIG = {
    "strategy_id": {
        "key": "strategy_id",
        "unknown": "unlabeled_strategy",
        "label": "strategy_id",
    },
    "setup_family": {
        "key": "setup_family",
        "unknown": "unlabeled_setup_family",
        "label": "setup_family",
    },
    "bucket": {
        "key": "bucket",
        "unknown": "unlabeled_bucket",
        "label": "bucket",
    },
}

WATCHED_SETUP_FAMILIES = [
    "market_surge_stock_leader",
    "hybrid_market_surge_stock_leader",
    "market_surge_etf_anchor",
    "hybrid_market_surge_etf_anchor",
    "post_harvest_redeployment",
    "controlled_post_harvest_redeployment_ladder",
    "pullback_reclaim",
    "relative_strength_leader",
    "space_stocks",
    "bitcoin_ai_compute",
    "small_cap_momentum",
]

WATCHED_BUCKETS = [
    "space_stocks",
    "bitcoin_ai_compute",
    "small_cap_momentum",
    "semi_leaders",
    "mega_cap_ai",
    "cloud_cyber_software",
    "data_center_infra",
    "precious_metals",
    "energy_leaders",
    "benchmark_etf",
]


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
        if hasattr(x, "item"):
            x = x.item()
        value = float(x)
        return default if math.isnan(value) or math.isinf(value) else value
    except Exception:
        return default


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _safe_text(value: Any, default: str = "") -> str:
    try:
        text = str(value or "").strip()
        return text or default
    except Exception:
        return default


def _ensure_labels(state: Dict[str, Any]) -> None:
    try:
        import strategy_label_propagation
        if hasattr(strategy_label_propagation, "propagate"):
            strategy_label_propagation.propagate(state)
    except Exception:
        pass


def _is_execution(row: Dict[str, Any]) -> bool:
    action = str(row.get("action") or row.get("type") or "").lower()
    if action in {"entry", "buy", "short", "sell_short", "exit", "sell", "close", "cover", "paper_market_surge_deployment"}:
        return True
    if row.get("pnl_dollars") is not None or row.get("pnl_pct") is not None:
        return True
    if row.get("symbol") and (row.get("entry") is not None or row.get("entry_price") is not None):
        return True
    return False


def _is_exit(row: Dict[str, Any]) -> bool:
    action = str(row.get("action") or row.get("type") or "").lower()
    reason = str(row.get("exit_reason") or row.get("reason") or "").lower()
    return action in {"exit", "sell", "close", "cover"} or "exit" in reason or "stop" in reason or row.get("pnl_dollars") is not None


def _trade_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [row for row in _list(state.get("trades")) if isinstance(row, dict) and _is_execution(row)]


def _positions(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    positions = state.get("positions")
    if isinstance(positions, dict):
        for symbol, pos in positions.items():
            if isinstance(pos, dict):
                out[str(symbol).upper()] = pos
    perf = _dict(state.get("performance"))
    perf_positions = perf.get("open_positions")
    if isinstance(perf_positions, dict):
        for symbol, pos in perf_positions.items():
            if isinstance(pos, dict) and str(symbol).upper() not in out:
                out[str(symbol).upper()] = pos
    return out


def _symbol_bucket(symbol: str, row: Dict[str, Any], mod: Any = None) -> str:
    for key in ("bucket", "symbol_bucket", "theme_bucket", "strategy_bucket"):
        value = _safe_text(row.get(key))
        if value:
            return value
    try:
        bucket_map = getattr(mod or _module(), "SYMBOL_BUCKET", {})
        if isinstance(bucket_map, dict):
            value = _safe_text(bucket_map.get(symbol.upper()))
            if value:
                return value
    except Exception:
        pass
    return "unlabeled_bucket"


def _setup_family(row: Dict[str, Any], bucket: str = "") -> str:
    for key in ("setup_family", "entry_context", "entry_tag", "selection_reason", "type", "source"):
        value = _safe_text(row.get(key))
        if value:
            # Normalize known market surge labels into stable scorecard families.
            lower = value.lower()
            if "stock_leader" in lower or "scanner_leader" in lower:
                return "market_surge_stock_leader"
            if "etf_anchor" in lower or "etf_fallback" in lower:
                return "market_surge_etf_anchor"
            if "post_harvest" in lower or "redeployment" in lower:
                return "post_harvest_redeployment"
            return value
    if bucket == "space_stocks":
        return "space_stocks"
    if bucket == "bitcoin_ai_compute":
        return "bitcoin_ai_compute"
    if bucket == "small_cap_momentum":
        return "small_cap_momentum"
    return "unlabeled_setup_family"


def _strategy_id(row: Dict[str, Any], setup_family: str, bucket: str) -> str:
    for key in ("strategy_id", "strategy", "entry_model"):
        value = _safe_text(row.get(key))
        if value:
            return value
    if setup_family and setup_family != "unlabeled_setup_family":
        return setup_family
    if bucket and bucket != "unlabeled_bucket":
        return bucket
    return "unlabeled_strategy"


def _quality_by_strategy(state: Dict[str, Any]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    tq = _dict(state.get("trade_quality_telemetry"))
    candidates: List[Dict[str, Any]] = []
    for key in ("recent_quality_tail", "recent_quality_rows", "quality_rows"):
        candidates.extend([row for row in _list(tq.get(key)) if isinstance(row, dict)])
    for row in candidates:
        sid = _safe_text(row.get("strategy_id"))
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
        sid = _safe_text(row.get("strategy_id"))
        if not sid:
            continue
        reward = row.get("reward_score") or row.get("reward") or row.get("exit_reward")
        if reward is not None:
            out.setdefault(sid, []).append(_f(reward, 0.0))
    return out


def _empty_card(label: str, dimension: str) -> Dict[str, Any]:
    return {
        "dimension": dimension,
        "label": label,
        "strategy_id": label if dimension == "strategy_id" else None,
        "setup_family": label if dimension == "setup_family" else None,
        "bucket": label if dimension == "bucket" else None,
        "entry_model": None,
        "exit_model": None,
        "risk_model": None,
        "side": None,
        "execution_rows": 0,
        "entry_rows": 0,
        "exit_rows": 0,
        "wins": 0,
        "losses": 0,
        "flats": 0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "best_trade": None,
        "worst_trade": None,
        "quality_scores": [],
        "reward_scores": [],
        "symbols": {},
        "recent_results": [],
        "open_positions_count": 0,
        "open_market_value": 0.0,
        "open_unrealized_pnl": 0.0,
        "open_symbols": {},
    }


def _card_action(exits: int, win_rate: float | None, profit_factor: float | None, net_pnl: float, expectancy: float | None) -> str:
    if exits < 10:
        return "collect_more_data"
    if win_rate is not None and profit_factor is not None and expectancy is not None:
        if win_rate >= 0.55 and profit_factor >= 1.25 and expectancy > 0.0 and net_pnl > 0.0:
            return "promote_candidate_advisory"
        if (win_rate <= 0.40 or profit_factor < 0.85 or expectancy < 0.0) and net_pnl < 0.0:
            return "demote_candidate_advisory"
    return "maintain_observation"


def _finalize_card(card: Dict[str, Any]) -> Dict[str, Any]:
    gross_loss_abs = abs(_f(card.get("gross_loss"), 0.0))
    gross_profit = _f(card.get("gross_profit"), 0.0)
    exits = int(card.get("exit_rows") or 0)
    wins = int(card.get("wins") or 0)
    losses = int(card.get("losses") or 0)
    flats = int(card.get("flats") or 0)
    quality_scores = [_f(x, 0.0) for x in _list(card.pop("quality_scores", []))]
    reward_scores = [_f(x, 0.0) for x in _list(card.pop("reward_scores", []))]
    win_rate = round(wins / exits, 4) if exits else None
    loss_rate = round(losses / exits, 4) if exits else None
    profit_factor = round(gross_profit / gross_loss_abs, 4) if gross_loss_abs > 0 else (None if gross_profit == 0 else 999.0)
    avg_quality = round(sum(quality_scores) / len(quality_scores), 4) if quality_scores else None
    avg_reward = round(sum(reward_scores) / len(reward_scores), 4) if reward_scores else None
    net_pnl = round(_f(card.get("net_pnl"), 0.0), 4)
    expectancy = round(net_pnl / exits, 4) if exits else None
    avg_win = round(gross_profit / wins, 4) if wins else None
    avg_loss = round(_f(card.get("gross_loss"), 0.0) / losses, 4) if losses else None

    if exits < 5:
        confidence = "very_low_sample"
    elif exits < 15:
        confidence = "low_sample"
    elif exits < 30:
        confidence = "medium_sample"
    else:
        confidence = "higher_sample"

    action = _card_action(exits, win_rate, profit_factor, net_pnl, expectancy)

    symbols = _dict(card.get("symbols"))
    top_symbols = sorted(symbols.items(), key=lambda kv: kv[1], reverse=True)[:10]
    open_symbols = _dict(card.get("open_symbols"))
    active_symbols = sorted(open_symbols.keys())[:20]

    return {
        "dimension": card.get("dimension"),
        "label": card.get("label"),
        "strategy_id": card.get("strategy_id"),
        "setup_family": card.get("setup_family"),
        "bucket": card.get("bucket"),
        "entry_model": card.get("entry_model"),
        "exit_model": card.get("exit_model"),
        "risk_model": card.get("risk_model"),
        "side": card.get("side"),
        "execution_rows": int(card.get("execution_rows") or 0),
        "entry_rows": int(card.get("entry_rows") or 0),
        "exit_rows": exits,
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "gross_profit": round(gross_profit, 4),
        "gross_loss": round(_f(card.get("gross_loss"), 0.0), 4),
        "profit_factor": profit_factor,
        "net_pnl": net_pnl,
        "expectancy_per_exit": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "best_trade": card.get("best_trade"),
        "worst_trade": card.get("worst_trade"),
        "avg_trade_quality_score": avg_quality,
        "avg_reward_score": avg_reward,
        "sample_confidence": confidence,
        "rotation_action": action,
        "top_symbols": [{"symbol": k, "rows": v} for k, v in top_symbols],
        "recent_results": _list(card.get("recent_results"))[-12:],
        "open_positions_count": int(card.get("open_positions_count") or 0),
        "open_market_value": round(_f(card.get("open_market_value"), 0.0), 4),
        "open_unrealized_pnl": round(_f(card.get("open_unrealized_pnl"), 0.0), 4),
        "active_symbols": active_symbols,
        "live_authority": False,
        "advisory_only": True,
    }


def _row_labels(row: Dict[str, Any], mod: Any = None) -> Dict[str, str]:
    symbol = _safe_text(row.get("symbol"), "UNKNOWN").upper()
    bucket = _symbol_bucket(symbol, row, mod)
    setup = _setup_family(row, bucket)
    strategy = _strategy_id(row, setup, bucket)
    return {
        "strategy_id": strategy,
        "setup_family": setup,
        "bucket": bucket,
        "symbol": symbol,
    }


def _update_card_from_row(card: Dict[str, Any], row: Dict[str, Any], labels: Dict[str, str]) -> None:
    for key in ("entry_model", "exit_model", "risk_model", "side"):
        if not card.get(key) and row.get(key):
            card[key] = row.get(key)
    card["execution_rows"] += 1
    if not _is_exit(row):
        card["entry_rows"] += 1
    sym = labels.get("symbol", "UNKNOWN")
    card["symbols"][sym] = int(card["symbols"].get(sym, 0)) + 1
    if _is_exit(row):
        card["exit_rows"] += 1
        pnl = _f(row.get("pnl_dollars"), _f(row.get("realized_pnl"), _f(row.get("pnl_pct"), 0.0)))
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
            card["flats"] += 1
            card["recent_results"].append("F")
        if card["best_trade"] is None or pnl > _f(card["best_trade"].get("pnl"), -10**9):
            card["best_trade"] = {"symbol": sym, "pnl": round(pnl, 4), "reason": row.get("exit_reason") or row.get("reason")}
        if card["worst_trade"] is None or pnl < _f(card["worst_trade"].get("pnl"), 10**9):
            card["worst_trade"] = {"symbol": sym, "pnl": round(pnl, 4), "reason": row.get("exit_reason") or row.get("reason")}


def _update_card_from_open_position(card: Dict[str, Any], symbol: str, pos: Dict[str, Any]) -> None:
    card["open_positions_count"] += 1
    shares = _f(pos.get("shares"), _f(pos.get("qty"), 0.0))
    last_price = _f(pos.get("last_price"), _f(pos.get("entry"), _f(pos.get("entry_price"), 0.0)))
    market_value = _f(pos.get("market_value"), shares * last_price if shares > 0.0 and last_price > 0.0 else 0.0)
    unrealized = _f(pos.get("unrealized_pnl"), _f(pos.get("pnl_dollars"), 0.0))
    card["open_market_value"] += market_value
    card["open_unrealized_pnl"] += unrealized
    card["open_symbols"][symbol] = True


def _build_dimension_cards(state: Dict[str, Any], mod: Any, dimension: str) -> List[Dict[str, Any]]:
    config = DIMENSION_CONFIG[dimension]
    cards: Dict[str, Dict[str, Any]] = {}

    for row in _trade_rows(state):
        labels = _row_labels(row, mod)
        label = labels.get(dimension) or config["unknown"]
        card = cards.setdefault(label, _empty_card(label, dimension))
        _update_card_from_row(card, row, labels)

    # Attach open-position context so scorecards show current exposure by setup/bucket.
    for symbol, pos in _positions(state).items():
        labels = _row_labels({"symbol": symbol, **pos}, mod)
        label = labels.get(dimension) or config["unknown"]
        card = cards.setdefault(label, _empty_card(label, dimension))
        _update_card_from_open_position(card, symbol, pos)

    if dimension == "strategy_id":
        quality = _quality_by_strategy(state)
        reward = _reward_by_strategy(state)
        for label, scores in quality.items():
            cards.setdefault(label, _empty_card(label, dimension))["quality_scores"].extend(scores)
        for label, scores in reward.items():
            cards.setdefault(label, _empty_card(label, dimension))["reward_scores"].extend(scores)

    if dimension == "setup_family":
        for label in WATCHED_SETUP_FAMILIES:
            cards.setdefault(label, _empty_card(label, dimension))
    if dimension == "bucket":
        for label in WATCHED_BUCKETS:
            cards.setdefault(label, _empty_card(label, dimension))

    finalized = [_finalize_card(card) for card in cards.values()]
    finalized.sort(
        key=lambda c: (
            _f(c.get("net_pnl"), 0.0),
            _f(c.get("expectancy_per_exit"), 0.0) if c.get("expectancy_per_exit") is not None else 0.0,
            _f(c.get("profit_factor"), 0.0) if c.get("profit_factor") is not None else 0.0,
            _f(c.get("open_unrealized_pnl"), 0.0),
        ),
        reverse=True,
    )
    return finalized


def build_scorecards(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    mod = mod or _module()
    if isinstance(state, dict):
        _ensure_labels(state)

    strategy_cards = _build_dimension_cards(state, mod, "strategy_id")
    setup_cards = _build_dimension_cards(state, mod, "setup_family")
    bucket_cards = _build_dimension_cards(state, mod, "bucket")

    promotions = [c for c in strategy_cards if c.get("rotation_action") == "promote_candidate_advisory"]
    demotions = [c for c in strategy_cards if c.get("rotation_action") == "demote_candidate_advisory"]
    collect = [c for c in strategy_cards if c.get("rotation_action") == "collect_more_data"]

    setup_promotions = [c for c in setup_cards if c.get("rotation_action") == "promote_candidate_advisory"]
    setup_demotions = [c for c in setup_cards if c.get("rotation_action") == "demote_candidate_advisory"]
    bucket_promotions = [c for c in bucket_cards if c.get("rotation_action") == "promote_candidate_advisory"]
    bucket_demotions = [c for c in bucket_cards if c.get("rotation_action") == "demote_candidate_advisory"]

    section = state.setdefault("strategy_scorecard", {}) if isinstance(state, dict) else {}
    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "advisory_only": True,
        "last_updated_local": _now(mod),
        "strategy_count": len(strategy_cards),
        "setup_family_count": len(setup_cards),
        "bucket_count": len(bucket_cards),
        "promotion_candidates_count": len(promotions),
        "demotion_candidates_count": len(demotions),
        "collect_more_data_count": len(collect),
        "scorecards": strategy_cards[:100],
        "top_scorecards": strategy_cards[:10],
        "strategy_id_scorecards": strategy_cards[:100],
        "setup_family_scorecards": setup_cards[:100],
        "top_setup_family_scorecards": setup_cards[:20],
        "bucket_scorecards": bucket_cards[:100],
        "top_bucket_scorecards": bucket_cards[:20],
        "promotion_candidates": promotions[:25],
        "demotion_candidates": demotions[:25],
        "setup_family_promotion_candidates": setup_promotions[:25],
        "setup_family_demotion_candidates": setup_demotions[:25],
        "bucket_promotion_candidates": bucket_promotions[:25],
        "bucket_demotion_candidates": bucket_demotions[:25],
        "watched_setup_families": WATCHED_SETUP_FAMILIES,
        "watched_buckets": WATCHED_BUCKETS,
        "recommendation": "Use scorecards for advisory review only until Phase 3A sample-size and walk-forward gates pass.",
        "guardrails": {
            "paper_only": True,
            "live_trade_authority": "none",
            "ml_authority": "shadow_only",
            "authority_changed": False,
            "does_not_place_trades": True,
            "does_not_bypass_risk_controls": True,
        },
    })
    return section


def payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    section = build_scorecards(state, mod) if ENABLED and isinstance(state, dict) else _dict(state.get("strategy_scorecard") if isinstance(state, dict) else {})
    return {
        "status": "ok",
        "overall": "pass",
        "type": "strategy_scorecard_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "advisory_only": True,
        "live_authority": False,
        "ml_authority": "shadow_only",
        "strategy_count": section.get("strategy_count", 0),
        "setup_family_count": section.get("setup_family_count", 0),
        "bucket_count": section.get("bucket_count", 0),
        "promotion_candidates_count": section.get("promotion_candidates_count", 0),
        "demotion_candidates_count": section.get("demotion_candidates_count", 0),
        "collect_more_data_count": section.get("collect_more_data_count", 0),
        "top_scorecards": section.get("top_scorecards", []),
        "top_setup_family_scorecards": section.get("top_setup_family_scorecards", []),
        "top_bucket_scorecards": section.get("top_bucket_scorecards", []),
        "promotion_candidates": section.get("promotion_candidates", []),
        "demotion_candidates": section.get("demotion_candidates", []),
        "setup_family_promotion_candidates": section.get("setup_family_promotion_candidates", []),
        "setup_family_demotion_candidates": section.get("setup_family_demotion_candidates", []),
        "bucket_promotion_candidates": section.get("bucket_promotion_candidates", []),
        "bucket_demotion_candidates": section.get("bucket_demotion_candidates", []),
        "watched_setup_families": section.get("watched_setup_families", WATCHED_SETUP_FAMILIES),
        "watched_buckets": section.get("watched_buckets", WATCHED_BUCKETS),
        "recommendation": section.get("recommendation"),
        "guardrails": section.get("guardrails", {}),
    }


def setup_family_payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    section = build_scorecards(state, mod) if ENABLED and isinstance(state, dict) else _dict(state.get("strategy_scorecard") if isinstance(state, dict) else {})
    return {
        "status": "ok",
        "overall": "pass",
        "type": "setup_family_scorecards",
        "version": VERSION,
        "generated_local": _now(mod),
        "advisory_only": True,
        "live_authority": False,
        "scorecards": section.get("setup_family_scorecards", []),
        "promotion_candidates": section.get("setup_family_promotion_candidates", []),
        "demotion_candidates": section.get("setup_family_demotion_candidates", []),
        "watched_setup_families": section.get("watched_setup_families", WATCHED_SETUP_FAMILIES),
    }


def bucket_payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    section = build_scorecards(state, mod) if ENABLED and isinstance(state, dict) else _dict(state.get("strategy_scorecard") if isinstance(state, dict) else {})
    return {
        "status": "ok",
        "overall": "pass",
        "type": "bucket_scorecards",
        "version": VERSION,
        "generated_local": _now(mod),
        "advisory_only": True,
        "live_authority": False,
        "scorecards": section.get("bucket_scorecards", []),
        "promotion_candidates": section.get("bucket_promotion_candidates", []),
        "demotion_candidates": section.get("bucket_demotion_candidates", []),
        "watched_buckets": section.get("watched_buckets", WATCHED_BUCKETS),
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
            def patched_save_state(state, *args, **kwargs):
                try:
                    if ENABLED and isinstance(state, dict):
                        build_scorecards(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("strategy_scorecard", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                return original(state, *args, **kwargs)
            patched_save_state._strategy_scorecard_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "STRATEGY_SCORECARD_VERSION", VERSION)
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(module))
    return {"status": "ok", "version": VERSION, "live_authority": False, "advisory_only": True}


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

    def setup_route():
        state, mod = _load_state(module)
        return jsonify(setup_family_payload(state, mod))

    def bucket_route():
        state, mod = _load_state(module)
        return jsonify(bucket_payload(state, mod))

    route_specs = (
        ("/paper/strategy-scorecard-status", "paper_strategy_scorecard_status", status_route),
        ("/paper/strategy-id-scorecards", "paper_strategy_id_scorecards", status_route),
        ("/paper/strategy-promotion-candidates", "paper_strategy_promotion_candidates", status_route),
        ("/paper/setup-family-scorecards", "paper_setup_family_scorecards", setup_route),
        ("/paper/bucket-scorecards", "paper_bucket_scorecards", bucket_route),
    )
    for path, endpoint, handler in route_specs:
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, handler)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {
        "status": "ok",
        "version": VERSION,
        "routes": [path for path, _, _ in route_specs],
        "live_authority": False,
        "advisory_only": True,
    }
