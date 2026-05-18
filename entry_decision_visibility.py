"""Entry decision visibility and no-entry diagnostics.

This module is advisory-only. It does not place trades, size positions, promote ML,
or override any live risk/entry authority in app.py. Its purpose is to explain why
the system stayed flat or did not open new entries during the latest cycle.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from typing import Any, Dict, List, Tuple

VERSION = "entry-decision-visibility-2026-05-18"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except Exception:
        return default


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _now_text(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    try:
        return core.today_key()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _json_response(core: Any, payload: Dict[str, Any], endpoint: str):
    try:
        return core.json_response(payload, endpoint=endpoint)
    except Exception:
        from flask import jsonify
        return jsonify(payload)


def _unique_symbols(rows: Any) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in _safe_list(rows):
        symbol = None
        if isinstance(item, str):
            symbol = item
        elif isinstance(item, dict):
            symbol = item.get("symbol") or item.get("ticker")
        if symbol:
            symbol = str(symbol).upper()
            if symbol not in seen:
                seen.add(symbol)
                out.append(symbol)
    return out


def _reason_from_item(item: Any) -> str:
    if not isinstance(item, dict):
        return "unknown"
    for key in ("reason", "entry_block_reason", "block_reason", "reject_reason", "exit_reason"):
        value = item.get(key)
        if value:
            return str(value)
    quality = item.get("quality_info")
    if isinstance(quality, dict):
        value = quality.get("reason") or quality.get("block_reason")
        if value:
            return str(value)
    rotation = item.get("rotation_info")
    if isinstance(rotation, dict):
        value = rotation.get("reason")
        if value:
            return str(value)
    return "unknown"


def _reason_counts(*collections: Any) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for rows in collections:
        for item in _safe_list(rows):
            counts[_reason_from_item(item)] += 1
    return dict(counts.most_common(12))


def _top_rows(rows: Any, limit: int = 10) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    for item in _safe_list(rows)[:limit]:
        if isinstance(item, str):
            compact.append({"symbol": item})
            continue
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol") or item.get("ticker")
        compact.append({
            "symbol": symbol,
            "side": item.get("side") or item.get("direction"),
            "score": item.get("score"),
            "reason": _reason_from_item(item),
            "sector": item.get("sector"),
            "bucket": item.get("bucket"),
        })
    return compact


def _active_market(core: Any, force_market: bool = False) -> Dict[str, Any]:
    state = _safe_dict(getattr(core, "portfolio", {}))
    if force_market:
        try:
            market = core.market_status(force=True)
            if isinstance(market, dict):
                state["last_market"] = market
                return market
        except Exception:
            pass
    return _safe_dict(state.get("last_market"))


def _clock(core: Any) -> Dict[str, Any]:
    try:
        return _safe_dict(core.market_clock())
    except Exception:
        return {"is_open": False, "reason": "clock_unavailable"}


def _risk_controls(core: Any) -> Dict[str, Any]:
    try:
        return _safe_dict(core.get_risk_controls())
    except Exception:
        return _safe_dict(_safe_dict(getattr(core, "portfolio", {})).get("risk_controls"))


def _feedback(core: Any, market: Dict[str, Any], risk_controls: Dict[str, Any], clock: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _safe_dict(core.feedback_loop_status(market=market, risk_controls=risk_controls, clock=clock, persist=False))
    except Exception:
        return _safe_dict(_safe_dict(getattr(core, "portfolio", {})).get("feedback_loop"))


def _params(core: Any, market: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _safe_dict(core.apply_aggression_adjustments(core.risk_parameters(market), market))
    except Exception:
        try:
            return _safe_dict(core.risk_parameters(market))
        except Exception:
            return {}


def _opening_warmup(core: Any, clock: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _safe_dict(core.opening_warmup_status(clock))
    except Exception:
        return {"active": False}


def _scanner_log(core: Any) -> Dict[str, Any]:
    try:
        return _safe_dict(core.scanner_result_log())
    except Exception:
        return _safe_dict(_safe_dict(getattr(core, "portfolio", {})).get("scanner_audit"))


def _last_cycle(core: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    state = _safe_dict(getattr(core, "portfolio", {}))
    auto = _safe_dict(state.setdefault("auto_runner", {}))
    last = _safe_dict(auto.get("last_result"))
    return auto, last


def _entry_floor(core: Any, market: Dict[str, Any], feedback: Dict[str, Any]) -> float:
    floor = feedback.get("dynamic_min_long_score")
    if floor is not None:
        return _safe_float(floor, 0.0)
    try:
        return _safe_float(core.min_entry_score_for_market(market, "long"), 0.0)
    except Exception:
        return 0.0


def build_no_entry_diagnostic(core: Any, force_market: bool = False) -> Dict[str, Any]:
    state = _safe_dict(getattr(core, "portfolio", {}))
    try:
        if hasattr(core, "calculate_equity"):
            core.calculate_equity(refresh_prices=False)
    except Exception:
        pass

    market = _active_market(core, force_market=force_market)
    clock = _clock(core)
    risk = _risk_controls(core)
    feedback = _feedback(core, market, risk, clock)
    params = _params(core, market)
    scanner = _scanner_log(core)
    auto, last = _last_cycle(core)
    warmup = _opening_warmup(core, clock)

    positions = _safe_dict(state.get("positions"))
    max_positions = int(_safe_float(params.get("max_positions"), _safe_float(scanner.get("max_positions"), len(positions))))
    open_positions = len(positions)

    long_signals = _unique_symbols(last.get("long_signals") or scanner.get("long_signals"))
    short_signals = _unique_symbols(last.get("short_signals") or scanner.get("short_signals"))
    entries = _safe_list(last.get("entries"))
    exits = _safe_list(last.get("exits"))
    rotations = _safe_list(last.get("rotations"))
    blocked = _safe_list(last.get("blocked_entries")) or _safe_list(scanner.get("blocked_entries"))
    rejected = _safe_list(last.get("rejected_signals")) or _safe_list(scanner.get("rejected_signals"))

    signal_count = len(long_signals) + len(short_signals)
    scanner_signals_found = int(_safe_float(scanner.get("signals_found"), signal_count))

    global_blockers: List[Dict[str, Any]] = []
    if not clock.get("is_open"):
        global_blockers.append({"code": "market_closed", "detail": clock.get("reason") or "market_not_open"})
    if risk.get("halted"):
        global_blockers.append({"code": "risk_halted", "detail": risk.get("halt_reason") or "risk_controls_halted"})
    if risk.get("profit_guard_active"):
        global_blockers.append({"code": "profit_guard", "detail": risk.get("profit_guard_reason") or "profit_guard_active"})
    if feedback.get("self_defense_mode") or risk.get("self_defense_active"):
        global_blockers.append({"code": "self_defense", "detail": feedback.get("self_defense_reason") or risk.get("self_defense_reason") or "feedback_loop_self_defense"})
    if feedback.get("block_new_entries"):
        global_blockers.append({"code": "feedback_blocks_entries", "detail": "; ".join(_safe_list(feedback.get("reasons"))) or "feedback_loop_block_new_entries"})
    if last and last.get("new_entries_allowed") is False:
        global_blockers.append({"code": "last_cycle_new_entries_false", "detail": last.get("entry_block_reason") or "new_entries_allowed_false"})
    if open_positions >= max_positions and max_positions > 0:
        global_blockers.append({"code": "max_positions_full", "detail": f"{open_positions}/{max_positions} positions open"})
    if warmup.get("active"):
        global_blockers.append({"code": "opening_warmup", "detail": warmup.get("reason") or "opening_warmup_active"})
    if not bool(params.get("allow_longs", True)) and long_signals:
        global_blockers.append({"code": "longs_disabled_by_regime", "detail": "allow_longs is false"})
    if short_signals and not bool(params.get("allow_shorts", False)):
        global_blockers.append({"code": "shorts_disabled_by_regime", "detail": "short signals present but allow_shorts is false"})

    if entries:
        verdict = "entries_taken_last_cycle"
    elif not clock.get("is_open"):
        verdict = "market_closed_or_pre_session"
    elif global_blockers:
        verdict = "globally_blocked_or_paused"
    elif blocked or rejected:
        verdict = "signals_present_but_entry_guards_blocked"
    elif signal_count or scanner_signals_found:
        verdict = "signals_present_but_allocation_or_timing_waited"
    else:
        verdict = "scanner_found_no_qualified_entries"

    recommendations: List[str] = []
    if not clock.get("is_open"):
        recommendations.append("No action needed; wait for regular-session cycles before judging entries.")
    if verdict == "signals_present_but_entry_guards_blocked":
        recommendations.append("Review top blocked/rejected reasons; most likely gate is score floor, extension/chase guard, sector/bucket cap, or timing guard.")
    if open_positions >= max_positions and max_positions > 0:
        recommendations.append("Book is at max positions; only rotation can create space unless max_positions is raised by regime tier.")
    if not entries and signal_count and not global_blockers:
        recommendations.append("Use /paper/risk-on-entry-diagnostic and /paper/intraday-timing-status to see whether timing or score floors blocked the scan.")
    if not recommendations:
        recommendations.append("Keep collecting scanner decisions; no authority change recommended from this diagnostic alone.")

    return {
        "status": "ok",
        "type": "no_entry_diagnostic",
        "version": VERSION,
        "generated_local": _now_text(core),
        "date": _today(core),
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "verdict": verdict,
        "plain_english": {
            "summary": _plain_summary(verdict, signal_count, scanner_signals_found, len(blocked), len(rejected), len(entries), global_blockers),
            "next_best_action": recommendations[0] if recommendations else "Keep collecting data.",
        },
        "market_clock": clock,
        "market_context": {
            "market_mode": market.get("market_mode"),
            "regime": market.get("regime"),
            "risk_score": market.get("risk_score"),
            "futures_bias": market.get("futures_bias", {}),
            "breadth": market.get("breadth", {}),
            "precious_metals": market.get("precious_metals", {}),
        },
        "permission_snapshot": {
            "allow_longs": bool(params.get("allow_longs", False)),
            "allow_shorts": bool(params.get("allow_shorts", False)),
            "max_positions": max_positions,
            "open_positions": open_positions,
            "new_entries_allowed_last_cycle": last.get("new_entries_allowed"),
            "entry_block_reason_last_cycle": last.get("entry_block_reason"),
            "active_min_long_score": _entry_floor(core, market, feedback),
            "opening_warmup": warmup,
        },
        "global_blockers": global_blockers,
        "last_cycle_summary": {
            "last_run_local": auto.get("last_run_local"),
            "last_successful_run_local": auto.get("last_successful_run_local"),
            "last_skip_reason": auto.get("last_skip_reason"),
            "long_signals_count": len(long_signals),
            "short_signals_count": len(short_signals),
            "scanner_signals_found": scanner_signals_found,
            "entries_count": len(entries),
            "exits_count": len(exits),
            "rotations_count": len(rotations),
            "blocked_entries_count": len(blocked),
            "rejected_signals_count": len(rejected),
            "top_long_signals": long_signals[:12],
            "top_short_signals": short_signals[:12],
            "top_blocked": _top_rows(blocked, 12),
            "top_rejected": _top_rows(rejected, 12),
            "block_reason_counts": _reason_counts(blocked, rejected),
        },
        "risk_controls": {
            "halted": risk.get("halted"),
            "halt_reason": risk.get("halt_reason"),
            "profit_guard_active": risk.get("profit_guard_active"),
            "profit_guard_reason": risk.get("profit_guard_reason"),
            "daily_loss_pct": risk.get("daily_loss_pct"),
            "intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
            "self_defense_active": risk.get("self_defense_active"),
            "self_defense_reason": risk.get("self_defense_reason"),
        },
        "scanner_audit_summary": {
            "signals_found": scanner.get("signals_found"),
            "blocked_entries_count": scanner.get("blocked_entries_count"),
            "top_blocked_symbols": scanner.get("top_blocked_symbols"),
            "bucket_summary": scanner.get("bucket_summary"),
            "last_updated_local": scanner.get("last_updated_local"),
        },
        "recommended_actions": recommendations,
    }


def _plain_summary(verdict: str, signal_count: int, scanner_signals_found: int, blocked_count: int, rejected_count: int, entries_count: int, blockers: List[Dict[str, Any]]) -> str:
    if entries_count:
        return f"The latest cycle did open {entries_count} entry/entries; the system is not stuck flat."
    if blockers:
        first = blockers[0]
        return f"No entries because a higher-level gate is active: {first.get('code')} ({first.get('detail')})."
    if blocked_count or rejected_count:
        return f"Signals were present, but entry guards blocked or rejected them: {blocked_count} blocked and {rejected_count} rejected."
    if signal_count or scanner_signals_found:
        return f"The scanner found {scanner_signals_found or signal_count} opportunity/opportunities, but no entry was selected by timing/allocation controls."
    if verdict == "market_closed_or_pre_session":
        return "No entries because the market is closed or the cycle is outside regular-session trade authority."
    return "No qualified entry candidates were visible in the latest stored cycle."


def build_decision_visibility_status(core: Any) -> Dict[str, Any]:
    diagnostic = build_no_entry_diagnostic(core, force_market=False)
    return {
        "status": "ok",
        "type": "decision_visibility_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "routes_installed": [
            "/paper/no-entry-diagnostic",
            "/paper/why-no-entries",
            "/paper/decision-visibility-status",
        ],
        "latest_verdict": diagnostic.get("verdict"),
        "latest_plain_english": diagnostic.get("plain_english"),
        "last_cycle_counts": diagnostic.get("last_cycle_summary", {}),
        "recommended_actions": diagnostic.get("recommended_actions", []),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "entry_decision_visibility_apply",
        "version": VERSION,
        "advisory_only": True,
        "live_trade_authority_changed": False,
    }


def register_routes(flask_app: Any = None, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    if core is None:
        try:
            import app as core  # type: ignore[no-redef]
        except Exception:
            core = None
    if core is None:
        return {"status": "error", "version": VERSION, "error": "core_module_missing"}

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/no-entry-diagnostic" not in existing:
        def no_entry_diagnostic():
            try:
                from flask import request
                force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes", "on"}
            except Exception:
                force = False
            return _json_response(core, build_no_entry_diagnostic(core, force_market=force), endpoint="paper_no_entry_diagnostic")
        flask_app.add_url_rule("/paper/no-entry-diagnostic", "paper_no_entry_diagnostic", no_entry_diagnostic)

    if "/paper/why-no-entries" not in existing:
        def why_no_entries():
            return _json_response(core, build_no_entry_diagnostic(core, force_market=False), endpoint="paper_why_no_entries")
        flask_app.add_url_rule("/paper/why-no-entries", "paper_why_no_entries", why_no_entries)

    if "/paper/decision-visibility-status" not in existing:
        def decision_visibility_status():
            return _json_response(core, build_decision_visibility_status(core), endpoint="paper_decision_visibility_status")
        flask_app.add_url_rule("/paper/decision-visibility-status", "paper_decision_visibility_status", decision_visibility_status)

    return {
        "status": "ok",
        "type": "entry_decision_visibility_register_routes",
        "version": VERSION,
        "routes_installed": True,
        "advisory_only": True,
        "live_trade_authority_changed": False,
    }
