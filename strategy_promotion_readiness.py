"""Phase 3A strategy-promotion readiness gate.

Advisory analytics only. Evaluates whether strategy scorecards have enough
sample size, validation, path telemetry, and quality evidence for future review.
It does not change orders, sizing, signals, stops, exits, or allocation.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "strategy-promotion-readiness-2026-05-16"
ENABLED = os.environ.get("STRATEGY_PROMOTION_READINESS_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()

MIN_EXIT_ROWS = int(os.environ.get("PROMOTION_MIN_EXIT_ROWS", "30"))
MIN_EXECUTION_ROWS = int(os.environ.get("PROMOTION_MIN_EXECUTION_ROWS", "30"))
MIN_WIN_RATE = float(os.environ.get("PROMOTION_MIN_WIN_RATE", "0.55"))
MIN_PROFIT_FACTOR = float(os.environ.get("PROMOTION_MIN_PROFIT_FACTOR", "1.25"))
MIN_QUALITY = float(os.environ.get("PROMOTION_MIN_AVG_QUALITY_SCORE", "60"))
MIN_REWARD = float(os.environ.get("PROMOTION_MIN_AVG_REWARD_SCORE", "0"))
MIN_PATH_ROWS = int(os.environ.get("PROMOTION_MIN_PATH_ROWS", "10"))


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


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        val = float(x)
        return default if math.isnan(val) or math.isinf(val) else val
    except Exception:
        return default


def _scorecards(state: Dict[str, Any], mod: Any = None) -> List[Dict[str, Any]]:
    try:
        import strategy_scorecard
        section = strategy_scorecard.build_scorecards(state, mod)
        return [c for c in _list(_dict(section).get("scorecards")) if isinstance(c, dict)]
    except Exception:
        return [c for c in _list(_dict(state.get("strategy_scorecard")).get("scorecards")) if isinstance(c, dict)]


def _validation_status(state: Dict[str, Any]) -> Dict[str, Any]:
    research = _dict(state.get("adaptive_ml_research"))
    walk = _dict(research.get("walk_forward"))
    status = str(walk.get("status") or "missing").lower()
    passed = bool(walk.get("formal_walk_forward_passed"))
    ready = passed and status not in {"missing", "insufficient_data", "failed", "error"}
    return {
        "status": status,
        "formal_walk_forward_passed": passed,
        "train_days": walk.get("train_days"),
        "test_days": walk.get("test_days"),
        "test_rows": walk.get("test_rows"),
        "proxy_test_win_rate": walk.get("proxy_test_win_rate"),
        "ready": ready,
    }


def _path_counts(state: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    rows: List[Dict[str, Any]] = []
    tq = _dict(state.get("trade_quality_telemetry"))
    for key in ("recent_quality_tail", "recent_quality_rows", "quality_rows"):
        rows.extend([r for r in _list(tq.get(key)) if isinstance(r, dict)])
    ml2 = _dict(state.get("ml_phase2"))
    rows.extend([r for r in _list(ml2.get("dataset")) if isinstance(r, dict)])
    research = _dict(state.get("adaptive_ml_research"))
    rows.extend([r for r in _list(research.get("reward_rows")) + _list(research.get("exit_reward_tail")) if isinstance(r, dict)])
    for row in rows:
        sid = str(row.get("strategy_id") or "").strip()
        if not sid:
            continue
        has_mae = row.get("mae") is not None or row.get("mae_pct") is not None or row.get("max_adverse_excursion") is not None
        has_mfe = row.get("mfe") is not None or row.get("mfe_pct") is not None or row.get("max_favorable_excursion") is not None
        if has_mae and has_mfe:
            counts[sid] = counts.get(sid, 0) + 1
    return counts


def _quality(card: Dict[str, Any]) -> Dict[str, Any]:
    exits = int(_f(card.get("exit_rows"), 0))
    executions = int(_f(card.get("execution_rows"), 0))
    win_rate = card.get("win_rate")
    profit_factor = card.get("profit_factor")
    avg_quality = card.get("avg_trade_quality_score")
    avg_reward = card.get("avg_reward_score")
    net_pnl = _f(card.get("net_pnl"), 0.0)
    checks = {
        "min_exit_rows": exits >= MIN_EXIT_ROWS,
        "min_execution_rows": executions >= MIN_EXECUTION_ROWS,
        "min_win_rate": win_rate is not None and _f(win_rate) >= MIN_WIN_RATE,
        "min_profit_factor": profit_factor is not None and _f(profit_factor) >= MIN_PROFIT_FACTOR,
        "positive_net_pnl": net_pnl > 0,
        "min_quality_score": avg_quality is None or _f(avg_quality) >= MIN_QUALITY,
        "min_reward_score": avg_reward is None or _f(avg_reward) >= MIN_REWARD,
    }
    sample_weight = min(exits / max(MIN_EXIT_ROWS, 1), 1.0)
    raw = 0.0
    raw += ((_f(win_rate, 0.0) - 0.50) * 100.0) if win_rate is not None else -25.0
    raw += min(max((_f(profit_factor, 0.0) - 1.0) * 25.0, -25.0), 50.0) if profit_factor is not None else -25.0
    raw += ((_f(avg_quality, 50.0) - 50.0) / 2.0) if avg_quality is not None else 0.0
    raw += _f(avg_reward, 0.0) * 10.0 if avg_reward is not None else 0.0
    raw += min(max(net_pnl, -25.0), 25.0)
    return {"checks": checks, "sample_weight": round(sample_weight, 4), "confidence_weighted_score": round(raw * sample_weight, 4)}


def evaluate(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    cards = _scorecards(state, mod)
    validation = _validation_status(state)
    path_by_strategy = _path_counts(state)
    total_path_rows = sum(path_by_strategy.values())
    global_path_ready = total_path_rows >= MIN_PATH_ROWS
    ranked: List[Dict[str, Any]] = []
    for card in cards:
        sid = str(card.get("strategy_id") or "unlabeled_strategy")
        quality = _quality(card)
        path_rows = int(path_by_strategy.get(sid, 0))
        checks = dict(quality["checks"])
        checks.update({
            "validation_passed": bool(validation.get("ready")),
            "path_rows_ready": path_rows >= MIN_PATH_ROWS,
            "global_path_ready": global_path_ready,
            "advisory_only": True,
        })
        failed = [k for k, v in checks.items() if not v]
        ready = not failed
        ranked.append({
            "strategy_id": sid,
            "setup_family": card.get("setup_family"),
            "entry_model": card.get("entry_model"),
            "exit_model": card.get("exit_model"),
            "risk_model": card.get("risk_model"),
            "execution_rows": card.get("execution_rows"),
            "exit_rows": card.get("exit_rows"),
            "win_rate": card.get("win_rate"),
            "profit_factor": card.get("profit_factor"),
            "net_pnl": card.get("net_pnl"),
            "avg_trade_quality_score": card.get("avg_trade_quality_score"),
            "avg_reward_score": card.get("avg_reward_score"),
            "path_rows_with_mae_mfe": path_rows,
            "sample_weight": quality["sample_weight"],
            "confidence_weighted_score": quality["confidence_weighted_score"],
            "promotion_ready": ready,
            "failed_checks": failed,
            "recommendation": "eligible_for_review" if ready else "blocked_from_promotion",
        })
    ranked.sort(key=lambda r: (_f(r.get("promotion_ready")), _f(r.get("confidence_weighted_score"))), reverse=True)
    ready_rows = [r for r in ranked if r.get("promotion_ready")]
    blocked_rows = [r for r in ranked if not r.get("promotion_ready")]
    gate_open = bool(ready_rows) and bool(validation.get("ready")) and global_path_ready
    section = state.setdefault("strategy_promotion_readiness", {}) if isinstance(state, dict) else {}
    section.update({
        "version": VERSION,
        "enabled": ENABLED,
        "last_updated_local": _now(mod),
        "gate_open": gate_open,
        "phase3a_promotion_ready": gate_open,
        "strategy_count": len(ranked),
        "ready_strategy_count": len(ready_rows),
        "blocked_strategy_count": len(blocked_rows),
        "validation": validation,
        "path_status": {"path_rows_with_mae_mfe": total_path_rows, "min_path_rows": MIN_PATH_ROWS, "ready": global_path_ready},
        "thresholds": {
            "min_exit_rows": MIN_EXIT_ROWS,
            "min_execution_rows": MIN_EXECUTION_ROWS,
            "min_win_rate": MIN_WIN_RATE,
            "min_profit_factor": MIN_PROFIT_FACTOR,
            "min_avg_quality_score": MIN_QUALITY,
            "min_avg_reward_score": MIN_REWARD,
            "min_path_rows": MIN_PATH_ROWS,
        },
        "top_ranked": ranked[:10],
        "ready_strategies": ready_rows[:25],
        "blocked_strategies": blocked_rows[:25],
        "recommendation": "Keep promotion closed until sample-size, validation, and path-data gates pass." if not gate_open else "Candidates are review-ready; keep advisory until explicitly approved.",
    })
    return section


def payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    section = evaluate(state, mod) if ENABLED and isinstance(state, dict) else _dict(state.get("strategy_promotion_readiness") if isinstance(state, dict) else {})
    return {
        "status": "ok",
        "type": "strategy_promotion_readiness_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "gate_open": section.get("gate_open", False),
        "phase3a_promotion_ready": section.get("phase3a_promotion_ready", False),
        "strategy_count": section.get("strategy_count", 0),
        "ready_strategy_count": section.get("ready_strategy_count", 0),
        "blocked_strategy_count": section.get("blocked_strategy_count", 0),
        "validation": section.get("validation", {}),
        "path_status": section.get("path_status", {}),
        "thresholds": section.get("thresholds", {}),
        "top_ranked": section.get("top_ranked", []),
        "ready_strategies": section.get("ready_strategies", []),
        "blocked_strategies": section.get("blocked_strategies", []),
        "recommendation": section.get("recommendation"),
    }


def apply(module: Any = None) -> Dict[str, Any]:
    module = module or _module()
    if module is None:
        return {"status": "not_applied", "version": VERSION, "reason": "module_missing"}
    if id(module) in PATCHED_MODULE_IDS:
        return {"status": "ok", "version": VERSION, "already_patched": True}
    try:
        original = getattr(module, "save_state", None)
        if callable(original):
            def patched_save_state(state):
                try:
                    if ENABLED and isinstance(state, dict):
                        evaluate(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("strategy_promotion_readiness", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                return original(state)
            patched_save_state._strategy_promotion_readiness_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "STRATEGY_PROMOTION_READINESS_VERSION", VERSION)
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(module))
    return {"status": "ok", "version": VERSION}


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
        ("/paper/strategy-promotion-readiness-status", "paper_strategy_promotion_readiness_status"),
        ("/paper/phase3a-promotion-gate-status", "paper_phase3a_promotion_gate_status"),
        ("/paper/strategy-promotion-gate-status", "paper_strategy_promotion_gate_status"),
    ):
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/strategy-promotion-readiness-status", "/paper/phase3a-promotion-gate-status", "/paper/strategy-promotion-gate-status"]}
