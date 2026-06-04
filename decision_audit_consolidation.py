"""Compact decision audit consolidation.

Read-only advisory layer. Summarizes the latest scanner/result flow,
post-harvest redeployment, fallback state, news/catalyst availability, ML shadow
counts, and repo-native advisory coaches so the operator can keep using one
routine self-check link.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, List, Tuple

VERSION = "decision-audit-consolidation-2026-06-04-v5-advisory-coaches"
REGISTERED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None:
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "portfolio"):
            return m
    return None


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state(core: Any) -> Dict[str, Any]:
    return _d(getattr(core, "portfolio", {}))


def _json(core: Any, payload: Dict[str, Any], endpoint: str):
    try:
        return core.json_response(payload, endpoint=endpoint)
    except Exception:
        from flask import jsonify
        return jsonify(payload)


def _sym(item: Any) -> str:
    if isinstance(item, str):
        return item.upper().strip()
    if isinstance(item, dict):
        value = item.get("symbol") or item.get("ticker") or item.get("in") or item.get("out")
        return str(value).upper().strip() if value else ""
    return ""


def _syms(rows: Any, limit: int = 12) -> List[str]:
    out: List[str] = []
    seen = set()
    for row in _l(rows):
        sym = _sym(row)
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
        if len(out) >= limit:
            break
    return out


def _reason(row: Any) -> str:
    if not isinstance(row, dict):
        return "unknown"
    for key in ("reason", "entry_block_reason", "block_reason", "reject_reason", "exit_reason", "status"):
        if row.get(key):
            return str(row.get(key))
    for key in ("quality_info", "rotation_info", "entry_fallback"):
        nested = row.get(key)
        if isinstance(nested, dict) and (nested.get("reason") or nested.get("status")):
            return str(nested.get("reason") or nested.get("status"))
    return "unknown"


def _compact(rows: Any, limit: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in _l(rows)[:limit]:
        if isinstance(row, str):
            out.append({"symbol": row})
            continue
        if not isinstance(row, dict):
            continue
        item = {
            "symbol": _sym(row),
            "side": row.get("side") or row.get("direction"),
            "score": row.get("score"),
            "reason": _reason(row),
            "sector": row.get("sector"),
            "bucket": row.get("bucket"),
        }
        for key in ("entry_context", "trade_class", "price", "alloc_factor"):
            if row.get(key) is not None:
                item[key] = row.get(key)
        out.append(item)
    return out


def _reason_counts(*groups: Any) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for rows in groups:
        for row in _l(rows):
            reason = _reason(row)
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10])


def _cycle(core: Any) -> Dict[str, Any]:
    state = _state(core)
    auto = _d(state.get("auto_runner"))
    last = _d(auto.get("last_result"))
    scanner = _d(state.get("scanner_audit"))
    entries = _l(last.get("entries"))
    rotations = _l(last.get("rotations"))
    blocked = _l(last.get("blocked_entries"))
    rejected = _l(last.get("rejected_signals"))
    longs = _l(last.get("long_signals")) or _l(scanner.get("long_signals"))
    shorts = _l(last.get("short_signals")) or _l(scanner.get("short_signals"))
    found = _i(last.get("signals_found"), _i(scanner.get("signals_found"), len(longs) + len(shorts)))
    return {
        "last_run_local": auto.get("last_run_local") or auto.get("last_successful_run_local"),
        "last_run_source": auto.get("last_run_source") or auto.get("last_successful_run_source"),
        "market_mode": last.get("market_mode"),
        "regime": last.get("regime"),
        "new_entries_allowed": last.get("new_entries_allowed"),
        "entry_block_reason": last.get("entry_block_reason"),
        "signals_found": found,
        "entries_count": len(entries),
        "rotations_count": len(rotations),
        "blocked_entries_count": len(blocked),
        "rejected_signals_count": len(rejected),
        "entry_symbols": _syms(entries),
        "blocked_symbols": _syms(blocked),
        "rejected_symbols": _syms(rejected),
        "long_signal_symbols": _syms(longs),
        "short_signal_symbols": _syms(shorts),
        "top_blocked": _compact(blocked),
        "top_rejected": _compact(rejected),
        "reason_counts": _reason_counts(blocked, rejected),
    }


def _post_harvest(core: Any) -> Dict[str, Any]:
    state = _state(core)
    redeploy = _d(state.get("post_harvest_redeployment"))
    fallback = _d(state.get("post_harvest_entry_fallback"))
    candidates = _l(redeploy.get("candidates"))
    entries = _l(redeploy.get("entries_from_post_harvest"))
    blocked = _l(redeploy.get("blocked_post_harvest_entries"))
    status = str(redeploy.get("status") or "not_available")
    if not redeploy:
        outcome = "not_available"
    elif redeploy.get("allowed") is False:
        outcome = "no_candidate_qualified"
    elif entries:
        outcome = "entered"
    elif blocked:
        outcome = "blocked"
    elif "no_decision" in status or (redeploy.get("allowed") and candidates):
        outcome = "selected_without_final_decision"
    else:
        outcome = "not_applicable"
    return {
        "available": bool(redeploy),
        "outcome": outcome,
        "status": status,
        "allowed": redeploy.get("allowed"),
        "reason": redeploy.get("reason"),
        "candidate_symbols": _syms(candidates),
        "candidates": _compact(candidates, 6),
        "entries_from_post_harvest": _compact(entries, 6),
        "blocked_post_harvest_entries": _compact(blocked, 6),
        "fallback_status": fallback.get("status"),
        "fallback_attempted": fallback.get("attempted"),
        "fallback_blocked": _compact(fallback.get("fallback_blocked"), 4),
    }


def _news(core: Any) -> Dict[str, Any]:
    state = _state(core)
    rows = [_d(state.get(k)) for k in ("news_sentiment", "news_sentiment_status", "news_sentiment_research", "news_risk")]
    source = next((row for row in rows if row), {})
    if not source:
        return {"available": False, "status": "not_available", "advisory_only": True}
    diag = _d(source.get("diagnostics"))
    return {
        "available": True,
        "status": source.get("status") or source.get("status_detail") or diag.get("status_detail") or "available",
        "provider": source.get("provider") or diag.get("provider"),
        "provider_configured": source.get("provider_configured") or diag.get("provider_configured"),
        "symbols_reviewed": _syms(source.get("symbols") or diag.get("symbols_requested"), 12),
        "advisory_only": True,
    }


def _risk_book(core: Any) -> Dict[str, Any]:
    state = _state(core)
    risk = _d(state.get("risk_controls"))
    positions = _d(state.get("positions"))
    cash = _f(state.get("cash"), 0.0)
    equity = _f(state.get("equity"), 0.0)
    reason = str(risk.get("self_defense_reason") or risk.get("halt_reason") or "")
    final_lock = "final 30" in reason.lower() or "before close" in reason.lower()
    return {
        "cash": round(cash, 2),
        "equity": round(equity, 2),
        "cash_pct": round(cash / equity, 4) if equity > 0 else None,
        "open_positions_count": len(positions),
        "positions": sorted(list(positions.keys()))[:20],
        "halted": bool(risk.get("halted")),
        "self_defense_active": bool(risk.get("self_defense_active")),
        "self_defense_reason": reason,
        "expected_final_close_lock": bool(final_lock),
        "daily_drawdown_pct": risk.get("daily_drawdown_pct") or risk.get("intraday_drawdown_pct") or risk.get("daily_loss_pct"),
        "losses_today": risk.get("losses_today"),
    }


def _ml_shadow(core: Any) -> Dict[str, Any]:
    state = _state(core)
    ml2 = _d(state.get("ml_phase2"))
    model = _d(ml2.get("model"))
    phase25 = _d(state.get("ml_phase25"))
    dataset = _l(ml2.get("dataset"))
    return {
        "available": bool(ml2),
        "enabled": ml2.get("enabled"),
        "mode": "shadow",
        "rows_total": ml2.get("rows_total", len(dataset)),
        "labeled_outcome_rows": ml2.get("labeled_outcome_rows", model.get("labeled_outcome_rows")),
        "observed_outcomes": ml2.get("trade_outcomes", model.get("trade_outcomes")),
        "latest_predictions_count": len(_l(ml2.get("last_predictions"))),
        "readiness": ml2.get("readiness", model.get("readiness")),
        "baseline_win_rate": model.get("baseline_win_rate"),
        "phase3a_ready": bool(phase25.get("phase3a_ready")),
        "gates_passed": phase25.get("gates_passed"),
        "gates_failed": phase25.get("gates_failed"),
    }


def _is_exit_row(row: Dict[str, Any]) -> bool:
    text = " ".join(str(row.get(k, "")).lower() for k in ("action", "type", "reason", "exit_reason"))
    return bool(row.get("pnl_dollars") is not None or row.get("pnl_pct") is not None or "exit" in text or "sell" in text or "close" in text or "stop" in text)


def _trade_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [row for row in _l(state.get("trades")) if isinstance(row, dict)]


def _trade_quality_coach(core: Any) -> Dict[str, Any]:
    state = _state(core)
    trades = _trade_rows(state)
    exits = [row for row in trades if _is_exit_row(row)]
    performance = _d(state.get("performance"))
    wins = _i(performance.get("wins_total"), 0)
    losses = _i(performance.get("losses_total"), 0)
    gross_profit = 0.0
    gross_loss = 0.0
    exit_reasons: Dict[str, int] = {}
    symbol_pnl: Dict[str, float] = {}
    if wins + losses <= 0:
        wins = 0
        losses = 0
    for row in exits:
        pnl = _f(row.get("pnl_dollars"), _f(row.get("pnl"), 0.0))
        if pnl > 0:
            gross_profit += pnl
            if wins + losses <= 0:
                wins += 1
        elif pnl < 0:
            gross_loss += abs(pnl)
            if wins + losses <= 0:
                losses += 1
        reason = _reason(row)
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        sym = _sym(row)
        if sym:
            symbol_pnl[sym] = symbol_pnl.get(sym, 0.0) + pnl
    closed = wins + losses
    win_rate = round(wins / closed, 4) if closed else 0.0
    profit_factor = round((gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0), 3)
    top_symbols = sorted(symbol_pnl.items(), key=lambda kv: kv[1], reverse=True)[:5]
    weakest_symbols = sorted(symbol_pnl.items(), key=lambda kv: kv[1])[:5]
    if len(trades) < 150:
        posture = "collect_more_executions"
        recommendation = f"Trade Quality Coach: execution_rows={len(trades)}/150; continue collecting outcomes before changing ML authority."
    elif profit_factor >= 1.15 and win_rate >= 0.48:
        posture = "quality_positive"
        recommendation = f"Trade Quality Coach: realized quality is positive with win_rate={win_rate} and profit_factor={profit_factor}; continue validation."
    else:
        posture = "quality_review_needed"
        recommendation = f"Trade Quality Coach: review exits and setup quality; win_rate={win_rate}, profit_factor={profit_factor}."
    return {
        "status": "ok",
        "advisory_only": True,
        "authority_changed": False,
        "execution_rows": len(trades),
        "exit_rows": len(exits),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": profit_factor,
        "posture": posture,
        "top_symbols": [{"symbol": sym, "pnl": round(pnl, 2)} for sym, pnl in top_symbols],
        "weakest_symbols": [{"symbol": sym, "pnl": round(pnl, 2)} for sym, pnl in weakest_symbols],
        "top_exit_reasons": dict(sorted(exit_reasons.items(), key=lambda kv: kv[1], reverse=True)[:5]),
        "recommendation": recommendation,
    }


def _risk_coach(core: Any, risk: Dict[str, Any]) -> Dict[str, Any]:
    cash_pct = _f(risk.get("cash_pct"), 0.0)
    positions = _i(risk.get("open_positions_count"), 0)
    drawdown = _f(risk.get("daily_drawdown_pct"), 0.0)
    halted = bool(risk.get("halted"))
    self_defense = bool(risk.get("self_defense_active"))
    if halted or self_defense:
        posture = "protected"
        recommendation = "Risk Coach: protective controls are active; do not override entries."
    elif cash_pct >= 0.75 and positions <= 3:
        posture = "defensive_underdeployed"
        recommendation = f"Risk Coach: cash_pct={cash_pct:.2%} with {positions} positions; redeploy only through high-quality candidates."
    elif drawdown >= 1.0:
        posture = "drawdown_watch"
        recommendation = f"Risk Coach: drawdown={drawdown}% is elevated; keep new-entry discipline tight."
    else:
        posture = "clean"
        recommendation = f"Risk Coach: controls are clean; cash_pct={cash_pct:.2%}, positions={positions}, drawdown={drawdown}%."
    return {
        "status": "ok",
        "advisory_only": True,
        "authority_changed": False,
        "posture": posture,
        "cash_pct": cash_pct,
        "open_positions_count": positions,
        "daily_drawdown_pct": drawdown,
        "halted": halted,
        "self_defense_active": self_defense,
        "recommendation": recommendation,
    }


def _post_harvest_coach(core: Any, post: Dict[str, Any], risk: Dict[str, Any], cycle: Dict[str, Any]) -> Dict[str, Any]:
    cash_pct = _f(risk.get("cash_pct"), 0.0)
    positions = _i(risk.get("open_positions_count"), 0)
    outcome = str(post.get("outcome") or "not_available")
    signals = _i(cycle.get("signals_found"), 0)
    candidates = _l(post.get("candidates"))
    if outcome == "entered":
        posture = "redeployed"
        recommendation = "Post-Harvest Coach: redeployment entered through the controlled ladder; monitor follow-through rather than adding new risk."
    elif outcome == "selected_without_final_decision":
        posture = "decision_visibility_needed"
        recommendation = "Post-Harvest Coach: selected candidate lacks a final visible entry/block result; inspect fallback and entry-quality path."
    elif positions <= 3 and cash_pct >= 0.75 and signals >= 8:
        posture = "underdeployed_but_selective"
        recommendation = "Post-Harvest Coach: underdeployed with scanner activity; keep starter-only redeployment and do not lower thresholds blindly."
    elif outcome == "no_candidate_qualified":
        posture = "standing_down_correctly"
        recommendation = "Post-Harvest Coach: no candidate qualified; standing down is preferred to forcing a weak redeployment."
    else:
        posture = "not_applicable"
        recommendation = "Post-Harvest Coach: no active post-harvest action needed."
    return {
        "status": "ok",
        "advisory_only": True,
        "authority_changed": False,
        "posture": posture,
        "outcome": outcome,
        "reason": post.get("reason"),
        "candidate_symbols": post.get("candidate_symbols") or _syms(candidates),
        "cash_pct": cash_pct,
        "open_positions_count": positions,
        "signals_found": signals,
        "recommendation": recommendation,
    }


def _ml_counts_text(ml: Dict[str, Any]) -> str:
    return (
        "ML shadow counts: "
        f"rows={ml.get('rows_total')}, "
        f"labeled={ml.get('labeled_outcome_rows')}, "
        f"observed_outcomes={ml.get('observed_outcomes')}, "
        f"predictions={ml.get('latest_predictions_count')}, "
        f"phase3a_ready={ml.get('phase3a_ready')}."
    )


def build_payload(core: Any | None = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "type": "decision_audit_status", "version": VERSION, "reason": "app_module_not_ready"}

    cycle = _cycle(core)
    post = _post_harvest(core)
    risk = _risk_book(core)
    ml = _ml_shadow(core)
    trade_quality = _trade_quality_coach(core)
    risk_coach = _risk_coach(core, risk)
    post_harvest_coach = _post_harvest_coach(core, post, risk, cycle)
    warnings: List[Dict[str, Any]] = []
    next_actions: List[str] = []

    final_lock = bool(risk.get("expected_final_close_lock"))
    risk_issue = bool(risk.get("halted") or risk.get("self_defense_active"))
    if risk_issue and not final_lock:
        warnings.append({"code": "risk_controls_not_clean", "message": "Risk halt or self-defense is active."})
        next_actions.append("Respect risk controls; do not override entry blocks.")
    elif final_lock:
        next_actions.append("Expected final-30-minute entry lock is active; no new-entry override is needed.")

    if post.get("outcome") == "selected_without_final_decision":
        warnings.append({"code": "post_harvest_no_final_decision", "message": "A post-harvest candidate lacks a final visible entry/block result."})
        next_actions.append("Review fallback and entry-quality details before changing thresholds.")

    if cycle.get("signals_found", 0) > 0 and cycle.get("entries_count", 0) == 0 and cycle.get("blocked_entries_count", 0) == 0 and cycle.get("rejected_signals_count", 0) == 0:
        warnings.append({"code": "scanner_no_visible_decisions", "message": "Signals existed but no entry/block/rejection was recorded."})
        next_actions.append("Improve instrumentation before loosening risk settings.")

    if post.get("outcome") == "no_candidate_qualified":
        if final_lock or post.get("reason") == "self_defense_active":
            next_actions.append("Post-harvest redeployment is correctly standing down during the protective close lock.")
        else:
            next_actions.append("Post-harvest controller is standing down because no candidate cleared quality thresholds.")

    next_actions.append(trade_quality.get("recommendation"))
    next_actions.append(risk_coach.get("recommendation"))
    next_actions.append(post_harvest_coach.get("recommendation"))

    if ml.get("available"):
        next_actions.append(_ml_counts_text(ml))
        if not ml.get("phase3a_ready"):
            next_actions.append("ML remains shadow-only while rows and observed outcomes continue accumulating.")

    next_actions = [str(x) for x in next_actions if x]
    if not next_actions:
        next_actions.append("No decision-audit issue detected; continue using the one-link self-check workflow.")

    overall = "warn" if warnings else "pass"
    payload = {
        "status": "ok" if overall == "pass" else "warn",
        "overall": overall,
        "type": "decision_audit_status",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "authority_changed": False,
        "latest_cycle": cycle,
        "post_harvest": post,
        "news_catalyst": _news(core),
        "ml_shadow": ml,
        "trade_quality_coach": trade_quality,
        "risk_coach": risk_coach,
        "post_harvest_coach": post_harvest_coach,
        "risk_book": risk,
        "warnings": warnings,
        "next_actions": next_actions[:8],
        "single_test_policy": {
            "routine_test_url": "https://trading-bot-clean.up.railway.app/paper/self-check",
            "extra_links_required_after_push": False,
            "included_in_one_test": True,
        },
    }
    try:
        _state(core)["decision_audit"] = {
            "version": VERSION,
            "generated_local": payload["generated_local"],
            "overall": overall,
            "warnings": warnings[:6],
            "post_harvest_outcome": post.get("outcome"),
            "signals_found": cycle.get("signals_found"),
            "entries_count": cycle.get("entries_count"),
            "expected_final_close_lock": final_lock,
            "ml_shadow": ml,
            "trade_quality_coach": trade_quality,
            "risk_coach": risk_coach,
            "post_harvest_coach": post_harvest_coach,
        }
    except Exception:
        pass
    return payload


def apply(core: Any | None = None) -> Dict[str, Any]:
    return build_payload(core or _mod())


def apply_runtime_overrides(core: Any | None = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    def decision_audit_status():
        c = core or _mod()
        return _json(c, build_payload(c), endpoint="decision_audit_status")

    def candidate_decision_audit():
        c = core or _mod()
        return _json(c, build_payload(c), endpoint="candidate_decision_audit")

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/decision-audit-status" not in existing:
        flask_app.add_url_rule("/paper/decision-audit-status", "decision_audit_status", decision_audit_status)
    if "/paper/candidate-decision-audit" not in existing:
        flask_app.add_url_rule("/paper/candidate-decision-audit", "candidate_decision_audit", candidate_decision_audit)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
