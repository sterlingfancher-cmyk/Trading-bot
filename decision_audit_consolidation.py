"""Compact decision audit consolidation.

Read-only advisory layer. Summarizes the latest scanner/result flow,
post-harvest redeployment, fallback state, news/catalyst availability, and ML
shadow counts so the operator can keep using one routine self-check link.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, List

VERSION = "decision-audit-consolidation-2026-06-03-v4-ml-counts-visible"
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
    for key in ("reason", "entry_block_reason", "block_reason", "reject_reason", "status"):
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

    if ml.get("available"):
        next_actions.append(_ml_counts_text(ml))
        if not ml.get("phase3a_ready"):
            next_actions.append("ML remains shadow-only while rows and observed outcomes continue accumulating.")

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
        "risk_book": risk,
        "warnings": warnings,
        "next_actions": next_actions[:6],
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
