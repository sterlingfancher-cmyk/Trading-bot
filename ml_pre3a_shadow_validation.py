"""Pre-3A shadow ML validation.

Advisory only. This module reads state and produces ML readiness diagnostics,
scorecards, MAE/MFE coverage, and chronological validation summaries. It does
not patch trading functions, place trades, change sizing, override risk, or grant
ML live authority.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "ml-pre3a-shadow-validation-2026-06-26-v1"
PHASE = "phase_2_5_pre_3a_shadow_validation"
ENABLED = os.environ.get("ML_PRE3A_SHADOW_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MIN_EXECUTION_ROWS = int(os.environ.get("ML_PRE3A_MIN_EXECUTION_ROWS", "150"))
MIN_OBSERVED_OUTCOMES = int(os.environ.get("ML_PRE3A_MIN_OBSERVED_OUTCOMES", "100"))
MIN_LABELED_ROWS = int(os.environ.get("ML_PRE3A_MIN_LABELED_ROWS", "150"))
MIN_WALK_FORWARD_EXITS = int(os.environ.get("ML_PRE3A_MIN_WALK_FORWARD_EXITS", "30"))
MIN_WALK_FORWARD_DAYS = int(os.environ.get("ML_PRE3A_MIN_WALK_FORWARD_DAYS", "10"))
MIN_REGIME_COUNT = int(os.environ.get("ML_PRE3A_MIN_REGIME_COUNT", "3"))
MIN_SCORECARD_ROWS = int(os.environ.get("ML_PRE3A_MIN_SCORECARD_ROWS", "3"))
MAX_SCORECARD_ITEMS = int(os.environ.get("ML_PRE3A_MAX_SCORECARD_ITEMS", "15"))

REGISTERED_APP_IDS: set[int] = set()


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
        return str(mod.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any | None]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return state if isinstance(state, dict) else {}, mod


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        v = float(value)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return int(float(value))
    except Exception:
        return default


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def _side(row: Dict[str, Any]) -> str:
    return str(row.get("side") or row.get("direction") or "long").lower().strip() or "long"


def _date_from_row(row: Dict[str, Any]) -> str | None:
    for key in ("date", "local_date", "day"):
        if row.get(key):
            return str(row.get(key))[:10]
    for key in ("exit_time", "entry_time", "time", "timestamp", "ts"):
        if row.get(key) is not None:
            try:
                return dt.datetime.fromtimestamp(float(row.get(key))).strftime("%Y-%m-%d")
            except Exception:
                pass
    return None


def _trades(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in _l(state.get("trades")) if isinstance(r, dict)]


def _exit_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for row in _trades(state):
        action = str(row.get("action") or row.get("type") or "").lower()
        reason = str(row.get("exit_reason") or row.get("reason") or "").lower()
        has_pnl = row.get("pnl_dollars") is not None or row.get("pnl_pct") is not None or row.get("pnl") is not None
        if action in {"exit", "sell", "close"} or "exit" in reason or "stop" in reason or has_pnl:
            rows.append(row)
    return rows


def _pnl(row: Dict[str, Any]) -> float:
    return _f(row.get("pnl_dollars"), _f(row.get("pnl"), 0.0))


def _pnl_pct(row: Dict[str, Any]) -> float:
    return _f(row.get("pnl_pct"), 0.0)


def _win(row: Dict[str, Any]) -> bool:
    return _pnl(row) > 0 or _pnl_pct(row) > 0


def _trade_metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [r for r in rows if isinstance(r, dict)]
    wins = sum(1 for r in rows if _win(r))
    losses = sum(1 for r in rows if not _win(r))
    gross_profit = sum(max(0.0, _pnl(r)) for r in rows)
    gross_loss = sum(abs(min(0.0, _pnl(r))) for r in rows)
    total = wins + losses
    pf = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    return {
        "rows": len(rows),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total, 4) if total else 0.0,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(pf, 3),
        "avg_pnl_dollars": round(sum(_pnl(r) for r in rows) / max(1, len(rows)), 4),
        "avg_pnl_pct": round(sum(_pnl_pct(r) for r in rows) / max(1, len(rows)), 5),
    }


def _ml_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    ml2 = _d(state.get("ml_phase2"))
    rows = [r for r in _l(ml2.get("dataset")) if isinstance(r, dict)]
    legacy = [r for r in _l(_d(state.get("ml_shadow")).get("feature_log")) if isinstance(r, dict)]
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in legacy + rows:
        key = str(row.get("row_id") or row.get("source_hash") or f"{row.get('date')}:{_symbol(row)}:{row.get('decision')}:{row.get('rule_score')}")
        by_key[key] = row
    return list(by_key.values())


def _labeled_ml_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for row in _ml_rows(state):
        pending = row.get("future_outcome_pending")
        if pending is False or row.get("future_win") is not None or row.get("future_pnl_pct") is not None or row.get("future_pnl_dollars") is not None:
            out.append(row)
    return out


def _candidate_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    scanner = _d(state.get("scanner_audit"))
    core = _d(state.get("core_entry_pipeline"))
    for key, decision in (("accepted_entries", "accepted"), ("blocked_entries", "blocked"), ("rejected_signals", "rejected")):
        for row in _l(scanner.get(key)):
            if isinstance(row, dict):
                r = dict(row)
                r.setdefault("decision", decision)
                rows.append(r)
    for row in _l(core.get("top_candidates")):
        if isinstance(row, dict):
            r = dict(row)
            r.setdefault("decision", "top_candidate")
            r.setdefault("source", "core_entry_pipeline")
            rows.append(r)
    for row in _l(core.get("participation_valve_attempts")):
        if isinstance(row, dict):
            r = dict(row)
            r.setdefault("decision", "participation_valve_review")
            r.setdefault("source", "core_entry_pipeline")
            rows.append(r)
    return [r for r in rows if _symbol(r)]


def _group_key(row: Dict[str, Any], field: str) -> str:
    if field == "symbol":
        return _symbol(row) or "unknown"
    if field == "side":
        return _side(row)
    value = row.get(field)
    if value is None and field == "regime":
        value = row.get("market_regime")
    if value is None and field == "bucket":
        value = row.get("symbol_bucket")
    return str(value or "unknown")


def _row_outcome(row: Dict[str, Any]) -> Tuple[bool, float, float] | None:
    if row.get("future_win") is None and row.get("future_pnl_pct") is None and row.get("future_pnl_dollars") is None:
        return None
    win = bool(row.get("future_win")) if row.get("future_win") is not None else (_f(row.get("future_pnl_dollars"), 0.0) > 0 or _f(row.get("future_pnl_pct"), 0.0) > 0)
    return win, _f(row.get("future_pnl_dollars"), 0.0), _f(row.get("future_pnl_pct"), 0.0)


def _scorecard(rows: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = _group_key(row, field)
        outcome = _row_outcome(row)
        if outcome is None:
            continue
        win, dollars, pct = outcome
        g = groups.setdefault(key, {"name": key, "rows": 0, "wins": 0, "pnl_dollars": 0.0, "pnl_pct": 0.0})
        g["rows"] += 1
        g["wins"] += 1 if win else 0
        g["pnl_dollars"] += dollars
        g["pnl_pct"] += pct
    cards = []
    for g in groups.values():
        rows_count = max(1, _i(g.get("rows"), 1))
        cards.append({
            "name": g.get("name"),
            "rows": g.get("rows"),
            "wins": g.get("wins"),
            "win_rate": round(_f(g.get("wins")) / rows_count, 4),
            "avg_pnl_dollars": round(_f(g.get("pnl_dollars")) / rows_count, 4),
            "avg_pnl_pct": round(_f(g.get("pnl_pct")) / rows_count, 5),
            "usable_for_weighting": bool(_i(g.get("rows"), 0) >= MIN_SCORECARD_ROWS),
        })
    cards.sort(key=lambda x: (_i(x.get("rows"), 0), _f(x.get("win_rate"), 0.0), _f(x.get("avg_pnl_pct"), 0.0)), reverse=True)
    return cards[:MAX_SCORECARD_ITEMS]


def _scorecards(state: Dict[str, Any]) -> Dict[str, Any]:
    labeled = _labeled_ml_rows(state)
    return {
        "labeled_rows_used": len(labeled),
        "min_rows_for_weighting": MIN_SCORECARD_ROWS,
        "by_symbol": _scorecard(labeled, "symbol"),
        "by_bucket": _scorecard(labeled, "bucket"),
        "by_sector": _scorecard(labeled, "sector"),
        "by_regime": _scorecard(labeled, "regime"),
        "by_decision": _scorecard(labeled, "decision"),
    }


def _mae_mfe_coverage(state: Dict[str, Any]) -> Dict[str, Any]:
    rows = _ml_rows(state)
    trades = _trades(state)
    path_section = _d(state.get("intratrade_path_capture"))
    active_paths = [p for p in _d(path_section.get("paths")).values() if isinstance(p, dict)]
    closed_paths = [p for p in _l(path_section.get("closed_path_archive")) if isinstance(p, dict)]
    def has_mae(row: Dict[str, Any]) -> bool:
        features = _d(row.get("mae_mfe_features"))
        return row.get("mae_pct") is not None or row.get("future_mae_pct") is not None or features.get("mae_pct") is not None
    def has_mfe(row: Dict[str, Any]) -> bool:
        features = _d(row.get("mae_mfe_features"))
        return row.get("mfe_pct") is not None or row.get("future_mfe_pct") is not None or features.get("mfe_pct") is not None
    rows_with_mae = sum(1 for r in rows if has_mae(r))
    rows_with_mfe = sum(1 for r in rows if has_mfe(r))
    trades_with_mae = sum(1 for r in trades if r.get("mae_pct") is not None)
    trades_with_mfe = sum(1 for r in trades if r.get("mfe_pct") is not None)
    paths_with_both = sum(1 for r in active_paths + closed_paths if r.get("mae_pct") is not None and r.get("mfe_pct") is not None)
    telemetry_rows = max(rows_with_mae, rows_with_mfe, trades_with_mae, trades_with_mfe, paths_with_both)
    return {
        "ml_rows_total": len(rows),
        "ml_rows_with_mae": rows_with_mae,
        "ml_rows_with_mfe": rows_with_mfe,
        "trade_rows_with_mae": trades_with_mae,
        "trade_rows_with_mfe": trades_with_mfe,
        "intratrade_paths_with_mae_mfe": paths_with_both,
        "telemetry_rows_available": telemetry_rows,
        "coverage_ready": bool(telemetry_rows > 0),
        "note": "Coverage uses recorded MAE/MFE/path fields only; no synthetic path values are created.",
    }


def _walk_forward(state: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    dates = set()
    for trade in _exit_rows(state):
        date_value = _date_from_row(trade)
        if not date_value:
            continue
        row = {"date": date_value, "pnl_dollars": _pnl(trade), "pnl_pct": _pnl_pct(trade), "symbol": _symbol(trade)}
        rows.append(row)
        dates.add(date_value)
    rows.sort(key=lambda r: r.get("date") or "")
    distinct = sorted(dates)
    if not rows:
        return {"formal_walk_forward_passed": False, "reason": "no_realized_exit_rows", "exit_rows": 0, "trade_days": 0}
    split = max(1, int(len(distinct) * 0.6))
    split = min(split, len(distinct) - 1) if len(distinct) > 1 else 1
    train_dates = set(distinct[:split])
    test_dates = set(distinct[split:]) or ({distinct[-1]} if distinct else set())
    train = [r for r in rows if r.get("date") in train_dates]
    test = [r for r in rows if r.get("date") in test_dates]
    train_metrics = _trade_metrics(train)
    test_metrics = _trade_metrics(test)
    enough_days = len(distinct) >= MIN_WALK_FORWARD_DAYS
    enough_exits = len(rows) >= MIN_WALK_FORWARD_EXITS
    enough_test = len(test) >= max(5, min(10, int(len(rows) * 0.2)))
    passed = bool(enough_days and enough_exits and enough_test and _f(test_metrics.get("profit_factor"), 0.0) >= 1.05 and _f(test_metrics.get("win_rate"), 0.0) >= 0.45)
    return {
        "formal_walk_forward_passed": passed,
        "reason": "formal_walk_forward_passed" if passed else "formal_walk_forward_incomplete_or_failed",
        "exit_rows": len(rows),
        "trade_days": len(distinct),
        "required_exit_rows": MIN_WALK_FORWARD_EXITS,
        "required_trade_days": MIN_WALK_FORWARD_DAYS,
        "gate_checks": {"enough_days": enough_days, "enough_exits": enough_exits, "enough_forward_test_rows": enough_test},
        "train": {"date_count": len(train_dates), **train_metrics},
        "forward_test": {"date_count": len(test_dates), **test_metrics},
    }


def _regimes_seen(state: Dict[str, Any]) -> List[str]:
    regimes = set()
    market = _d(state.get("last_market"))
    if market.get("regime"):
        regimes.add(str(market.get("regime")))
    for row in _ml_rows(state):
        if isinstance(row, dict) and row.get("regime"):
            regimes.add(str(row.get("regime")))
    return sorted(regimes)


def _prediction_review(state: Dict[str, Any]) -> Dict[str, Any]:
    ml2 = _d(state.get("ml_phase2"))
    predictions = [p for p in _l(ml2.get("last_predictions")) if isinstance(p, dict)]
    candidates = _candidate_rows(state)
    candidate_symbols = {_symbol(r) for r in candidates if _symbol(r)}
    predicted_symbols = {_symbol(p) for p in predictions if _symbol(p)}
    overlap = sorted(candidate_symbols & predicted_symbols)
    return {
        "predictions_available": len(predictions),
        "current_candidate_rows": len(candidates),
        "candidate_prediction_overlap_count": len(overlap),
        "candidate_prediction_overlap_symbols": overlap[:25],
        "top_predictions": predictions[:10],
        "top_current_candidates": candidates[:10],
    }


def _gate(name: str, current: Any, required: Any, passed: bool, detail: str) -> Dict[str, Any]:
    return {"name": name, "current": current, "required": required, "passed": bool(passed), "detail": detail}


def payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    trades = _trades(state)
    exits = _exit_rows(state)
    ml_rows = _ml_rows(state)
    labeled = _labeled_ml_rows(state)
    observed_outcomes = len(exits)
    scorecards = _scorecards(state)
    mae_mfe = _mae_mfe_coverage(state)
    wf = _walk_forward(state)
    regimes = _regimes_seen(state)
    predictions = _prediction_review(state)
    gates = [
        _gate("execution_rows", len(trades), MIN_EXECUTION_ROWS, len(trades) >= MIN_EXECUTION_ROWS, "Actual state.trades rows."),
        _gate("observed_exit_outcomes", observed_outcomes, MIN_OBSERVED_OUTCOMES, observed_outcomes >= MIN_OBSERVED_OUTCOMES, "Realized exits with outcome data."),
        _gate("labeled_ml_rows", len(labeled), MIN_LABELED_ROWS, len(labeled) >= MIN_LABELED_ROWS, "ML dataset rows with attached outcome labels."),
        _gate("mae_mfe_coverage", mae_mfe.get("coverage_ready"), True, bool(mae_mfe.get("coverage_ready")), "MAE/MFE or path telemetry exists."),
        _gate("regime_coverage", len(regimes), MIN_REGIME_COUNT, len(regimes) >= MIN_REGIME_COUNT, "Distinct regimes in state/ML rows."),
        _gate("walk_forward_validation", wf.get("formal_walk_forward_passed"), True, bool(wf.get("formal_walk_forward_passed")), "Chronological realized train/test validation."),
    ]
    failed = [g for g in gates if not g.get("passed")]
    phase3a_ready = len(failed) == 0
    next_actions = [
        "Keep ML shadow-only; do not let it place trades or override risk controls.",
        "Use the scorecards to observe which symbols, buckets, sectors, and regimes repeatedly outperform before changing weighting.",
        "Use MAE/MFE coverage and walk-forward results as gating evidence before Phase 3A.",
    ]
    if len(trades) < MIN_EXECUTION_ROWS:
        next_actions.append(f"Collect {MIN_EXECUTION_ROWS - len(trades)} more execution rows before Phase 3A review.")
    if observed_outcomes < MIN_OBSERVED_OUTCOMES:
        next_actions.append(f"Collect {MIN_OBSERVED_OUTCOMES - observed_outcomes} more observed exit outcomes for stronger labels.")
    return {
        "status": "ok",
        "type": "ml_pre3a_shadow_validation_status",
        "version": VERSION,
        "phase": PHASE,
        "generated_local": _now(mod),
        "enabled": bool(ENABLED),
        "live_trade_decider": False,
        "ml_authority": "shadow_only",
        "phase3a_ready": bool(phase3a_ready),
        "phase3a_live_authority_allowed": False,
        "gates_passed": len(gates) - len(failed),
        "gates_failed": len(failed),
        "gates": gates,
        "execution_summary": {"execution_rows": len(trades), "observed_exit_outcomes": observed_outcomes, **_trade_metrics(exits)},
        "ml_dataset_summary": {"rows_total": len(ml_rows), "labeled_rows": len(labeled), "pending_rows": max(0, len(ml_rows) - len(labeled)), "stored_predictions": len(_l(_d(state.get("ml_phase2")).get("last_predictions")))},
        "mae_mfe": mae_mfe,
        "walk_forward": wf,
        "regime_summary": {"count": len(regimes), "regimes_seen": regimes},
        "scorecards": scorecards,
        "prediction_review": predictions,
        "next_actions": next_actions,
        "policy": {"advisory_only": True, "does_not_patch_runtime_functions": True, "does_not_place_trades": True, "does_not_change_sizing": True, "does_not_override_risk_controls": True, "live_trade_authority": "none", "ml_authority": "shadow_only"},
    }


def status_payload(mod: Any = None) -> Dict[str, Any]:
    state, mod = _load_state(mod)
    if not ENABLED:
        return {"status": "disabled", "type": "ml_pre3a_shadow_validation_status", "version": VERSION, "enabled": False, "live_trade_decider": False}
    return payload(state, mod)


def apply(mod: Any = None) -> Dict[str, Any]:
    return {"status": "ok", "version": VERSION, "enabled": bool(ENABLED), "advisory_only": True, "does_not_patch_runtime_functions": True, "live_trade_decider": False}


def apply_runtime_overrides(mod: Any = None) -> Dict[str, Any]:
    return apply(mod)


def register_routes(flask_app: Any, mod: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        return jsonify(status_payload(mod or _module()))

    def scorecards_route():
        state, module = _load_state(mod or _module())
        return jsonify({"status": "ok", "type": "ml_shadow_scorecards", "version": VERSION, "generated_local": _now(module), "scorecards": _scorecards(state)})

    def validation_route():
        state, module = _load_state(mod or _module())
        return jsonify({"status": "ok", "type": "ml_shadow_validation", "version": VERSION, "generated_local": _now(module), "walk_forward": _walk_forward(state), "mae_mfe": _mae_mfe_coverage(state), "prediction_review": _prediction_review(state)})

    if "/paper/ml-pre3a-shadow-status" not in existing:
        flask_app.add_url_rule("/paper/ml-pre3a-shadow-status", "paper_ml_pre3a_shadow_status", status_route)
    if "/paper/ml-shadow-scorecards" not in existing:
        flask_app.add_url_rule("/paper/ml-shadow-scorecards", "paper_ml_shadow_scorecards", scorecards_route)
    if "/paper/ml-shadow-validation" not in existing:
        flask_app.add_url_rule("/paper/ml-shadow-validation", "paper_ml_shadow_validation", validation_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/ml-pre3a-shadow-status", "/paper/ml-shadow-scorecards", "/paper/ml-shadow-validation"], "live_trade_decider": False}


try:
    apply(_module())
except Exception:
    pass
