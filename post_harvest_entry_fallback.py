"""Guarded fallback for post-harvest redeployment entries.

This module does not scan for trades and does not loosen risk policy. It only
runs after the post-harvest redeployment controller already selected a starter
candidate and the wrapped entry pipeline returned no entry and no blocked reason.

The fallback re-checks safety, calls the app's normal entry_quality_check, and
then calls the app's normal enter_position only if the candidate still qualifies.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, Tuple

VERSION = "post-harvest-entry-fallback-2026-06-03-v1"
REGISTERED_APP_IDS: set[int] = set()

ENABLED = os.environ.get("POST_HARVEST_ENTRY_FALLBACK_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("POST_HARVEST_ENTRY_FALLBACK_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
MAX_FALLBACK_ENTRIES_PER_CYCLE = int(os.environ.get("POST_HARVEST_ENTRY_FALLBACK_MAX_PER_CYCLE", "1"))
MAX_DAILY_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_ENTRY_FALLBACK_MAX_DD_PCT", "1.25"))
MAX_LOSSES_TODAY = int(os.environ.get("POST_HARVEST_ENTRY_FALLBACK_MAX_LOSSES_TODAY", "0"))
VALID_REDEPLOYMENT_STATUSES = {"passed_to_entry_pipeline", "passed_to_entry_pipeline_no_decision"}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "try_entries_and_rotations"):
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "try_entries_and_rotations"):
            return m
    return None


def _now(m: Any | None = None) -> str:
    try:
        return m.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        out = float(v)
        return default if math.isnan(out) or math.isinf(out) else out
    except Exception:
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _portfolio(m: Any | None) -> Dict[str, Any]:
    try:
        return getattr(m, "portfolio", {}) or {}
    except Exception:
        return {}


def _positions(m: Any | None) -> Dict[str, Any]:
    try:
        return dict((_portfolio(m).get("positions", {}) or {}))
    except Exception:
        return {}


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _risk_controls(m: Any | None) -> Dict[str, Any]:
    try:
        fn = getattr(m, "get_risk_controls", None)
        if callable(fn):
            rc = fn()
            if isinstance(rc, dict):
                return rc
    except Exception:
        pass
    try:
        rc = (_portfolio(m).get("risk_controls") or {})
        return dict(rc) if isinstance(rc, dict) else {}
    except Exception:
        return {}


def _risk_ok(m: Any | None) -> Tuple[bool, Dict[str, Any]]:
    rc = _risk_controls(m)
    perf = (_portfolio(m).get("performance") or {}) if isinstance(_portfolio(m).get("performance"), dict) else {}
    losses_today = _i(rc.get("losses_today", perf.get("losses_today", 0)), 0)
    daily_dd = max(_f(rc.get("daily_drawdown_pct"), 0.0), _f(rc.get("intraday_drawdown_pct"), 0.0))
    payload = {
        "halted": bool(rc.get("halted")),
        "self_defense_active": bool(rc.get("self_defense_active")),
        "losses_today": losses_today,
        "daily_drawdown_pct": round(daily_dd, 4),
        "halt_reason": str(rc.get("halt_reason") or rc.get("self_defense_reason") or ""),
    }
    if payload["halted"]:
        return False, {**payload, "reason": "risk_halt_active"}
    if payload["self_defense_active"]:
        return False, {**payload, "reason": "self_defense_active"}
    if losses_today > MAX_LOSSES_TODAY:
        return False, {**payload, "reason": "losses_today_not_clean"}
    if daily_dd >= MAX_DAILY_DRAWDOWN_PCT:
        return False, {**payload, "reason": "daily_drawdown_above_fallback_limit"}
    return True, {**payload, "reason": "risk_controls_clean"}


def _market_ok(market: Dict[str, Any] | None) -> Tuple[bool, str]:
    market = market or {}
    mode = str(market.get("market_mode", "neutral") or "neutral").lower()
    regime = str(market.get("regime", "") or "").lower()
    if bool(market.get("bear_confirmed")) or bool(market.get("broad_market_soft")):
        return False, "market_not_clean_for_fallback"
    if "risk_off" in mode or "defensive" in mode or "bear" in regime:
        return False, "fallback_blocked_by_market_mode"
    if mode != "risk_on":
        return False, "fallback_requires_risk_on"
    return True, "ok"


def _candidate_symbol(candidate: Dict[str, Any]) -> str:
    return str(candidate.get("symbol") or "").upper()


def _selected_candidates(m: Any | None) -> Tuple[list[Dict[str, Any]], Dict[str, Any]]:
    latest = {}
    try:
        latest = dict((_portfolio(m).get("post_harvest_redeployment") or {}))
    except Exception:
        latest = {}
    candidates = [c for c in (latest.get("candidates") or []) if isinstance(c, dict)]
    return candidates, latest


def _should_attempt(m: Any | None, entries: list, rotations: list, blocked_entries: list) -> Tuple[bool, Dict[str, Any]]:
    if not ENABLED:
        return False, {"reason": "post_harvest_entry_fallback_disabled", "version": VERSION}
    if not _paper_context():
        return False, {"reason": "not_paper_context", "version": VERSION}
    candidates, latest = _selected_candidates(m)
    if not latest or not bool(latest.get("allowed")):
        return False, {"reason": "no_allowed_post_harvest_selection", "version": VERSION}
    if str(latest.get("status") or "") not in VALID_REDEPLOYMENT_STATUSES:
        return False, {"reason": "redeployment_status_not_no_decision", "redeployment_status": latest.get("status"), "version": VERSION}
    syms = {_candidate_symbol(c) for c in candidates if _candidate_symbol(c)}
    if not syms:
        return False, {"reason": "no_candidate_symbols", "version": VERSION}
    if any(isinstance(e, dict) and str(e.get("symbol", "")).upper() in syms for e in (entries or [])):
        return False, {"reason": "entry_already_returned", "version": VERSION}
    if any(isinstance(r, dict) and str(r.get("in", "")).upper() in syms for r in (rotations or [])):
        return False, {"reason": "rotation_already_returned", "version": VERSION}
    if any(isinstance(b, dict) and str(b.get("symbol", "")).upper() in syms for b in (blocked_entries or [])):
        return False, {"reason": "blocked_reason_already_returned", "version": VERSION}
    return True, {"reason": "fallback_needed", "version": VERSION, "candidate_symbols": sorted(syms)}


def _bridge_params(params: Dict[str, Any] | None, candidate: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(params or {})
    side = str(candidate.get("side", "long")).lower()
    if side == "short":
        out["allow_shorts"] = True
    else:
        out["allow_longs"] = True
    return out


def _attempt_candidate(m: Any, candidate: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    symbol = _candidate_symbol(candidate)
    if not symbol:
        return False, {"reason": "missing_symbol"}
    positions = _positions(m)
    if symbol in positions:
        return False, {"symbol": symbol, "reason": "already_held"}
    max_positions = _i(params.get("max_positions"), 0)
    if max_positions <= 0:
        return False, {"symbol": symbol, "reason": "missing_effective_max_positions"}
    if len(positions) >= max_positions:
        return False, {"symbol": symbol, "reason": "max_positions_full", "open_positions_count": len(positions), "max_positions": max_positions}
    if _f(candidate.get("price"), 0.0) <= 0:
        return False, {"symbol": symbol, "reason": "missing_or_bad_candidate_price", "price": candidate.get("price")}
    try:
        cooldown_fn = getattr(m, "is_in_cooldown", None)
        if callable(cooldown_fn) and cooldown_fn(symbol):
            return False, {"symbol": symbol, "reason": "cooldown"}
    except Exception:
        pass

    quality_fn = getattr(m, "entry_quality_check", None)
    enter_fn = getattr(m, "enter_position", None)
    if not callable(quality_fn):
        return False, {"symbol": symbol, "reason": "entry_quality_check_unavailable"}
    if not callable(enter_fn):
        return False, {"symbol": symbol, "reason": "enter_position_unavailable"}

    try:
        ok, quality_info = quality_fn(candidate, params, market)
    except Exception as exc:
        return False, {"symbol": symbol, "reason": "entry_quality_check_error", "error": str(exc)}
    if not ok:
        return False, {"symbol": symbol, "reason": "entry_quality_block", "quality_info": quality_info}

    try:
        entry = enter_fn(candidate, params, market_mode=market.get("market_mode", "neutral"))
    except Exception as exc:
        return False, {"symbol": symbol, "reason": "enter_position_error", "error": str(exc), "quality_info": quality_info}
    if entry and not entry.get("blocked"):
        entry["quality_info"] = quality_info
        entry["post_harvest_entry_fallback"] = {"version": VERSION, "reason": "normal_pipeline_returned_no_decision"}
        return True, entry
    return False, entry or {"symbol": symbol, "reason": "enter_position_returned_empty", "quality_info": quality_info}


def _apply_fallback(m: Any, entries: list, rotations: list, blocked_entries: list, params: Dict[str, Any], market: Dict[str, Any]) -> Tuple[list, list, list, Dict[str, Any]]:
    entries = list(entries or [])
    rotations = list(rotations or [])
    blocked_entries = list(blocked_entries or [])

    should, info = _should_attempt(m, entries, rotations, blocked_entries)
    if not should:
        return entries, rotations, blocked_entries, {"attempted": False, **info}

    risk_ok, risk_info = _risk_ok(m)
    if not risk_ok:
        blocked = {"reason": risk_info.get("reason", "risk_controls_not_clean"), "risk_controls": risk_info, "version": VERSION}
        return entries, rotations, blocked_entries, {"attempted": False, **blocked}

    market_ok, market_reason = _market_ok(market)
    if not market_ok:
        return entries, rotations, blocked_entries, {"attempted": False, "reason": market_reason, "version": VERSION}

    candidates, latest = _selected_candidates(m)
    fallback_entries = []
    fallback_blocked = []
    for candidate in candidates[:MAX_FALLBACK_ENTRIES_PER_CYCLE]:
        call_params = _bridge_params(params, candidate)
        ok, result = _attempt_candidate(m, dict(candidate), call_params, market or {})
        if ok:
            fallback_entries.append(result)
            entries.append(result)
        else:
            fallback_blocked.append(result)
            if isinstance(result, dict):
                blocked_entries.append(result)

    status = "entered_via_guarded_fallback" if fallback_entries else "blocked_by_guarded_fallback"
    payload = {
        "attempted": True,
        "status": status,
        "version": VERSION,
        "fallback_entries": fallback_entries,
        "fallback_blocked": fallback_blocked[:10],
        "risk_controls": risk_info,
        "does_not_raise_max_positions": True,
        "entry_quality_check_called": True,
        "enter_position_called_only_after_quality_pass": True,
    }
    try:
        latest = dict((_portfolio(m).get("post_harvest_redeployment") or {}))
        latest["entry_fallback"] = payload
        latest["status"] = status
        latest["entries_from_post_harvest"] = list(latest.get("entries_from_post_harvest") or []) + fallback_entries
        latest["blocked_post_harvest_entries"] = list(latest.get("blocked_post_harvest_entries") or []) + fallback_blocked[:10]
        _portfolio(m)["post_harvest_redeployment"] = latest
        _portfolio(m)["post_harvest_entry_fallback"] = payload
    except Exception:
        pass
    return entries, rotations, blocked_entries, payload


def _chain_has_marker(fn: Any, marker: str, limit: int = 50) -> bool:
    seen: set[int] = set()
    cur = fn
    for _ in range(limit):
        if not callable(cur) or id(cur) in seen:
            return False
        seen.add(id(cur))
        if bool(getattr(cur, marker, False)):
            return True
        cur = next(
            (
                getattr(cur, attr, None)
                for attr in (
                    "_post_harvest_entry_fallback_original",
                    "_post_harvest_redeployment_original",
                    "_profit_maturity_rotation_original",
                    "_paper_breakout_rotation_original",
                    "_paper_exposure_debug_original",
                    "__wrapped__",
                )
                if callable(getattr(cur, attr, None))
            ),
            None,
        )
    return False


def _patch_try_entries(m: Any) -> bool:
    current = getattr(m, "try_entries_and_rotations", None)
    if not callable(current) or _chain_has_marker(current, "_post_harvest_entry_fallback_patched"):
        return False
    original = current

    def patched_try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        entries, rotations, blocked_entries = original(
            long_signals,
            short_signals,
            params,
            market,
            new_entries_allowed=new_entries_allowed,
            entry_block_reason=entry_block_reason,
        )
        entries, rotations, blocked_entries, payload = _apply_fallback(
            m,
            entries or [],
            rotations or [],
            blocked_entries or [],
            dict(params or {}),
            dict(market or {}),
        )
        try:
            _portfolio(m)["post_harvest_entry_fallback"] = payload
        except Exception:
            pass
        return entries, rotations, blocked_entries

    patched_try_entries_and_rotations._post_harvest_entry_fallback_patched = True  # type: ignore[attr-defined]
    patched_try_entries_and_rotations._post_harvest_entry_fallback_original = original  # type: ignore[attr-defined]
    m.try_entries_and_rotations = patched_try_entries_and_rotations
    return True


def status_payload(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "type": "post_harvest_entry_fallback_status", "version": VERSION, "reason": "app_module_not_ready"}
    try:
        latest = dict((_portfolio(m).get("post_harvest_entry_fallback") or {}))
    except Exception:
        latest = {}
    return {
        "status": "ok",
        "type": "post_harvest_entry_fallback_status",
        "version": VERSION,
        "generated_local": _now(m),
        "enabled": bool(ENABLED and _paper_context()),
        "patched_try_entries": _chain_has_marker(getattr(m, "try_entries_and_rotations", None), "_post_harvest_entry_fallback_patched"),
        "latest_fallback": latest,
    }


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "type": "post_harvest_entry_fallback_status", "version": VERSION, "reason": "app_module_not_ready"}
    patched = _patch_try_entries(m)
    payload = status_payload(m)
    payload["patched_this_call"] = {"try_entries_and_rotations": bool(patched)}
    return payload


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify

    def post_harvest_entry_fallback_status():
        return jsonify(apply_runtime_overrides(m or _mod()))

    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/post-harvest-entry-fallback-status" not in existing:
        flask_app.add_url_rule("/paper/post-harvest-entry-fallback-status", "post_harvest_entry_fallback_status", post_harvest_entry_fallback_status)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply_runtime_overrides(m or _mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
