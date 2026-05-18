"""Entry decision visibility and no-entry diagnostics.

Advisory-only: this module explains why entries did or did not happen. It does
not place trades, resize positions, enable live shorts, or override app.py trade
authority.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter
from typing import Any, Dict, List, Tuple

VERSION = "entry-decision-visibility-2026-05-18-risk-on-weak"


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


def _symbol(item: Any) -> str:
    if isinstance(item, str):
        return item.upper()
    if isinstance(item, dict):
        value = item.get("symbol") or item.get("ticker")
        return str(value).upper() if value else ""
    return ""


def _unique_symbols(rows: Any) -> List[str]:
    out, seen = [], set()
    for item in _safe_list(rows):
        symbol = _symbol(item)
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _reason_from_item(item: Any) -> str:
    if not isinstance(item, dict):
        return "unknown"
    for key in ("reason", "entry_block_reason", "block_reason", "reject_reason", "exit_reason"):
        if item.get(key):
            return str(item.get(key))
    for nested_key in ("quality_info", "rotation_info"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            value = nested.get("reason") or nested.get("block_reason")
            if value:
                return str(value)
    return "unknown"


def _side(item: Any) -> str:
    if isinstance(item, dict):
        value = item.get("side") or item.get("direction")
        return str(value).lower() if value else ""
    return ""


def _reason_counts(*collections: Any) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for rows in collections:
        for item in _safe_list(rows):
            counts[_reason_from_item(item)] += 1
    return dict(counts.most_common(12))


def _top_rows(rows: Any, limit: int = 10, floor: float | None = None) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    for item in _safe_list(rows)[:limit]:
        if isinstance(item, str):
            compact.append({"symbol": item})
            continue
        if not isinstance(item, dict):
            continue
        row = {
            "symbol": _symbol(item),
            "side": item.get("side") or item.get("direction"),
            "score": item.get("score"),
            "reason": _reason_from_item(item),
            "sector": item.get("sector"),
            "bucket": item.get("bucket"),
        }
        if floor is not None:
            score = _safe_float(item.get("score"), default=float("nan"))
            if math.isnan(score) or floor <= 0:
                row["score_gap_to_required"] = None
                row["score_pct_of_required"] = None
            else:
                row["score_gap_to_required"] = round(score - floor, 6)
                row["score_pct_of_required"] = round(score / floor, 4)
        compact.append(row)
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


def _feedback(core: Any, market: Dict[str, Any], risk: Dict[str, Any], clock: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _safe_dict(core.feedback_loop_status(market=market, risk_controls=risk, clock=clock, persist=False))
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
    return auto, _safe_dict(auto.get("last_result"))


def _entry_floor(core: Any, market: Dict[str, Any], feedback: Dict[str, Any]) -> float:
    if feedback.get("dynamic_min_long_score") is not None:
        return _safe_float(feedback.get("dynamic_min_long_score"), 0.0)
    try:
        return _safe_float(core.min_entry_score_for_market(market, "long"), 0.0)
    except Exception:
        return 0.0


def _split_rows(blocked: Any, rejected: Any) -> Dict[str, List[Dict[str, Any]]]:
    out = {"blocked_long": [], "blocked_short": [], "rejected_long": [], "rejected_short": [], "blocked_unknown": [], "rejected_unknown": []}
    for source, rows in (("blocked", blocked), ("rejected", rejected)):
        for item in _safe_list(rows):
            if not isinstance(item, dict):
                continue
            side = _side(item)
            key = f"{source}_{side}" if side in {"long", "short"} else f"{source}_unknown"
            out.setdefault(key, []).append(item)
    return out


def _weak_breadth(market: Dict[str, Any]) -> bool:
    breadth = _safe_dict(market.get("breadth"))
    state = str(breadth.get("state") or "").lower()
    action = str(breadth.get("action") or "").lower()
    reason = str(breadth.get("reason") or "").lower()
    positive_count = _safe_float(breadth.get("positive_breadth_count"), 999)
    return state in {"weak", "risk_off", "negative", "poor"} or "risk_off" in action or "weak" in reason or positive_count <= 1


def _bearish_futures(market: Dict[str, Any]) -> bool:
    futures = _safe_dict(market.get("futures_bias"))
    bias = str(futures.get("bias") or "").lower()
    action = str(futures.get("action") or "").lower()
    reason = str(futures.get("reason") or "").lower()
    nq_pct = _safe_float(futures.get("nq_pct"), 0.0)
    es_pct = _safe_float(futures.get("es_pct"), 0.0)
    return bias == "bearish" or "block_opening_longs" in action or "weak" in reason or (nq_pct < 0 and es_pct < 0)


def _market_sub_mode(market: Dict[str, Any], feedback: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(market.get("market_mode") or "").lower()
    regime = str(market.get("regime") or "").lower()
    actions = [str(x) for x in _safe_list(feedback.get("actions"))]
    weak = _weak_breadth(market)
    bearish = _bearish_futures(market)
    caution_actions = [a for a in actions if any(t in a for t in ("risk_off", "rising_vix", "rising_rates", "market_extension", "futures_bias"))]
    if mode == "risk_on" and (weak or bearish or caution_actions):
        sub_mode = "risk_on_but_weak"
        summary = "Risk-on regime remains active, but current breadth/futures/feedback are weak enough to require stricter longs and advisory-only short observation."
    elif mode == "risk_on":
        sub_mode = "clean_risk_on"
        summary = "Risk-on regime is active without major intraday caution flags in this diagnostic."
    elif regime in {"bull", "constructive"} and (weak or bearish):
        sub_mode = "constructive_but_weak"
        summary = "Broader regime is constructive, but current breadth/futures are weak."
    else:
        sub_mode = mode or regime or "unknown"
        summary = "No special risk-on weakness sub-mode was detected."
    return {"sub_mode": sub_mode, "weak_breadth": weak, "bearish_futures": bearish, "caution_actions": caution_actions, "summary": summary}


def _long_analysis(long_signals: List[str], long_rows: List[Dict[str, Any]], floor: float) -> Dict[str, Any]:
    best_score = None
    best_symbol = None
    for item in long_rows:
        score = _safe_float(item.get("score"), default=float("nan"))
        if math.isnan(score):
            continue
        if best_score is None or score > best_score:
            best_score = score
            best_symbol = _symbol(item)
    gap = round(best_score - floor, 6) if best_score is not None and floor > 0 else None
    pct = round(best_score / floor, 4) if best_score is not None and floor > 0 else None
    failed = best_score is not None and floor > 0 and best_score < floor
    return {
        "long_signals_count": len(long_signals),
        "blocked_or_rejected_long_count": len(long_rows),
        "required_score": floor,
        "best_long_symbol": best_symbol,
        "best_long_score": best_score,
        "best_long_score_gap_to_required": gap,
        "best_long_score_pct_of_required": pct,
        "long_quality_failed": failed,
        "top_failed_longs": _top_rows(long_rows, 12, floor=floor),
        "plain_english": (
            f"Longs are allowed, but the best visible long score ({best_score:.6f}) is below the active floor ({floor:.6f})."
            if failed else "No clear long-quality failure was visible in the stored cycle."
        ),
    }


def _short_waitlist(short_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out, seen = [], set()
    for item in short_rows:
        symbol = _symbol(item)
        reason = _reason_from_item(item)
        if not symbol or symbol in seen:
            continue
        if "extended_below" not in reason and reason not in {"extended_downside", "extension_guard"}:
            continue
        seen.add(symbol)
        out.append({
            "symbol": symbol,
            "score": item.get("score"),
            "bucket": item.get("bucket"),
            "reason": reason,
            "status": "wait_for_bounce_then_failure",
            "required_confirmation": [
                "bounce or reclaim toward 5m MA20/VWAP",
                "renewed failure without being extended below 5m MA20",
                "short score remains above tactical threshold",
            ],
        })
    return out[:20]


def _tactical_short_advisory(sub_mode: Dict[str, Any], params: Dict[str, Any], long_analysis: Dict[str, Any], short_signals: List[str], short_rows: List[Dict[str, Any]], entries: List[Any], global_blockers: List[Dict[str, Any]]) -> Dict[str, Any]:
    waitlist = _short_waitlist(short_rows)
    waitlisted = {row["symbol"] for row in waitlist}
    paper_candidates = [s for s in short_signals if s not in waitlisted][:12]
    non_short_blockers = [b for b in global_blockers if b.get("code") != "shorts_disabled_by_regime"]
    ready = (
        sub_mode.get("sub_mode") == "risk_on_but_weak"
        and len(entries) == 0
        and bool(long_analysis.get("long_quality_failed"))
        and bool(short_signals)
        and not non_short_blockers
    )
    allow_shorts = bool(params.get("allow_shorts", False))
    gate_reason = []
    if sub_mode.get("sub_mode") != "risk_on_but_weak":
        gate_reason.append("market_sub_mode_not_risk_on_but_weak")
    if entries:
        gate_reason.append("entries_already_taken")
    if not long_analysis.get("long_quality_failed"):
        gate_reason.append("long_quality_failure_not_confirmed")
    if not short_signals:
        gate_reason.append("no_short_signals")
    if non_short_blockers:
        gate_reason.append("higher_level_non_short_blocker_active")
    if not allow_shorts:
        gate_reason.append("live_shorts_disabled_by_regime")
    return {
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "risk_on_but_weak_detected": sub_mode.get("sub_mode") == "risk_on_but_weak",
        "advisory_ready_if_paper_short_pilot_enabled": ready,
        "allow_shorts_currently": allow_shorts,
        "live_short_authority_allowed_now": False,
        "gate_open": False,
        "gate_reason": gate_reason,
        "paper_only_candidate_symbols": paper_candidates,
        "reclaim_waitlist": waitlist,
        "pilot_rules": {
            "max_tactical_short_positions": 2,
            "allocation_mode": "reduced_size_only",
            "requires_no_qualified_longs": True,
            "requires_weak_breadth": True,
            "requires_bearish_futures": True,
            "requires_not_extended_below_5m_ma20": True,
            "requires_reclaim_then_failure_for_extended_names": True,
        },
        "plain_english": "Weak risk-on conditions support tracking tactical shorts, but this remains advisory-only and does not enable live shorting.",
    }


def _primary_driver(entries: List[Any], clock: Dict[str, Any], blockers: List[Dict[str, Any]], long_analysis: Dict[str, Any], tactical: Dict[str, Any], blocked_count: int, rejected_count: int) -> Dict[str, Any]:
    if entries:
        return {"code": "entries_taken", "detail": f"{len(entries)} entry/entries opened last cycle"}
    if not clock.get("is_open"):
        return {"code": "market_closed", "detail": clock.get("reason") or "market_not_open"}
    non_short = [b for b in blockers if b.get("code") != "shorts_disabled_by_regime"]
    if non_short:
        return non_short[0]
    if long_analysis.get("long_quality_failed"):
        return {
            "code": "long_quality_below_floor",
            "detail": f"best visible long score {long_analysis.get('best_long_score'):.6f} is below required {long_analysis.get('required_score'):.6f}",
        }
    if tactical.get("allow_shorts_currently") is False and tactical.get("paper_only_candidate_symbols"):
        return {"code": "shorts_disabled_by_regime", "detail": "short signals exist, but live shorts remain disabled; tactical short list is advisory-only"}
    if blocked_count or rejected_count:
        return {"code": "entry_guards_blocked_signals", "detail": f"{blocked_count} blocked and {rejected_count} rejected by timing/quality/extension guards"}
    return {"code": "no_qualified_candidates", "detail": "scanner found no candidate that cleared entry controls"}


def _plain_summary(verdict: str, primary: Dict[str, Any], signal_count: int, scanner_signals_found: int, blocked_count: int, rejected_count: int, entries_count: int, blockers: List[Dict[str, Any]]) -> str:
    if entries_count:
        return f"The latest cycle did open {entries_count} entry/entries; the system is not stuck flat."
    code, detail = primary.get("code"), primary.get("detail")
    if code == "long_quality_below_floor":
        return f"No entries because long candidates failed quality: {detail}. Short signals remain advisory-only while live shorts are disabled."
    if code == "shorts_disabled_by_regime":
        return f"No entries because shorts are advisory-only right now: {detail}."
    if code in {"market_closed", "risk_halted", "profit_guard", "self_defense", "feedback_blocks_entries", "max_positions_full", "opening_warmup"}:
        return f"No entries because a higher-level gate is active: {code} ({detail})."
    if blockers:
        first = ([b for b in blockers if b.get("code") != "shorts_disabled_by_regime"] or blockers)[0]
        return f"No entries because a higher-level gate is active: {first.get('code')} ({first.get('detail')})."
    if blocked_count or rejected_count:
        return f"Signals were present, but entry guards blocked or rejected them: {blocked_count} blocked and {rejected_count} rejected."
    if signal_count or scanner_signals_found:
        return f"The scanner found {scanner_signals_found or signal_count} opportunity/opportunities, but no entry was selected by timing/allocation controls."
    if verdict == "market_closed_or_pre_session":
        return "No entries because the market is closed or the cycle is outside regular-session trade authority."
    return "No qualified entry candidates were visible in the latest stored cycle."


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

    split = _split_rows(blocked, rejected)
    long_rows = split.get("blocked_long", []) + split.get("rejected_long", [])
    short_rows = split.get("blocked_short", []) + split.get("rejected_short", [])
    floor = _entry_floor(core, market, feedback)
    long_info = _long_analysis(long_signals, long_rows, floor)
    sub_mode = _market_sub_mode(market, feedback)
    tactical = _tactical_short_advisory(sub_mode, params, long_info, short_signals, short_rows, entries, global_blockers)
    primary = _primary_driver(entries, clock, global_blockers, long_info, tactical, len(blocked), len(rejected))

    if entries:
        verdict = "entries_taken_last_cycle"
    elif not clock.get("is_open"):
        verdict = "market_closed_or_pre_session"
    elif primary.get("code") == "long_quality_below_floor":
        verdict = "long_quality_failed_and_shorts_advisory_only"
    elif global_blockers:
        verdict = "globally_blocked_or_paused"
    elif blocked or rejected:
        verdict = "signals_present_but_entry_guards_blocked"
    elif signal_count or scanner_signals_found:
        verdict = "signals_present_but_allocation_or_timing_waited"
    else:
        verdict = "scanner_found_no_qualified_entries"

    recommendations: List[str] = []
    if primary.get("code") == "long_quality_below_floor":
        recommendations.append("Keep the long floor intact; do not lower quality just to force a trade.")
    if tactical.get("advisory_ready_if_paper_short_pilot_enabled"):
        recommendations.append("Track tactical short candidates in paper/advisory mode only; require reclaim-then-failure before any future short pilot.")
    if tactical.get("reclaim_waitlist"):
        recommendations.append("Keep extended short candidates on a reclaim watchlist instead of chasing downside extension.")
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
        "primary_no_entry_driver": primary,
        "plain_english": {
            "summary": _plain_summary(verdict, primary, signal_count, scanner_signals_found, len(blocked), len(rejected), len(entries), global_blockers),
            "next_best_action": recommendations[0],
        },
        "market_clock": clock,
        "market_context": {
            "market_mode": market.get("market_mode"),
            "market_sub_mode": sub_mode,
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
            "active_min_long_score": floor,
            "opening_warmup": warmup,
        },
        "long_entry_analysis": long_info,
        "short_entry_analysis": {
            "short_signals_count": len(short_signals),
            "blocked_or_rejected_short_count": len(short_rows),
            "top_failed_shorts": _top_rows(short_rows, 12),
            "live_shorts_disabled_by_regime": bool(short_signals and not bool(params.get("allow_shorts", False))),
        },
        "tactical_short_advisory": tactical,
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


def build_tactical_short_advisory_status(core: Any) -> Dict[str, Any]:
    diagnostic = build_no_entry_diagnostic(core, force_market=False)
    return {
        "status": "ok",
        "type": "tactical_short_advisory_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "market_sub_mode": _safe_dict(_safe_dict(diagnostic.get("market_context")).get("market_sub_mode")).get("sub_mode"),
        "long_entry_analysis": diagnostic.get("long_entry_analysis"),
        "short_entry_analysis": diagnostic.get("short_entry_analysis"),
        "tactical_short_advisory": diagnostic.get("tactical_short_advisory"),
        "recommended_actions": diagnostic.get("recommended_actions", []),
    }


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
            "/paper/tactical-short-advisory-status",
        ],
        "latest_verdict": diagnostic.get("verdict"),
        "primary_no_entry_driver": diagnostic.get("primary_no_entry_driver"),
        "market_sub_mode": _safe_dict(_safe_dict(diagnostic.get("market_context")).get("market_sub_mode")).get("sub_mode"),
        "latest_plain_english": diagnostic.get("plain_english"),
        "long_entry_analysis": diagnostic.get("long_entry_analysis"),
        "tactical_short_advisory": diagnostic.get("tactical_short_advisory"),
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

    if "/paper/tactical-short-advisory-status" not in existing:
        def tactical_short_advisory_status():
            return _json_response(core, build_tactical_short_advisory_status(core), endpoint="paper_tactical_short_advisory_status")
        flask_app.add_url_rule("/paper/tactical-short-advisory-status", "paper_tactical_short_advisory_status", tactical_short_advisory_status)

    return {
        "status": "ok",
        "type": "entry_decision_visibility_register_routes",
        "version": VERSION,
        "routes_installed": True,
        "advisory_only": True,
        "live_trade_authority_changed": False,
    }
