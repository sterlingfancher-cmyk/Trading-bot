"""Profit-maturity rotation review and controlled capital recycling.

Conservative paper-mode layer: it does not raise max positions, force entries,
bypass halts, bypass stop losses, or bypass entry-quality checks. It only lets a
full book recycle a mature/fading winner into a materially stronger candidate,
and records a status payload for review.

v2 adds a narrow profit-guard redeployment exception: when profit guard blocks
new entries but the book is materially under max positions, one exceptional
breakout starter can be re-submitted through the normal entry pipeline. This
does not bypass technical entry quality checks, halts, stop losses, or
self-defense controls.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, Iterable, Tuple

VERSION = "profit-maturity-rotation-2026-06-02-v2"
REGISTERED_APP_IDS: set[int] = set()
_CYCLE_ROTATIONS_USED = 0
_CYCLE_REDEPLOY_ENTRIES_USED = 0

ENABLED = os.environ.get("PROFIT_MATURITY_ROTATION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("PROFIT_MATURITY_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
MIN_PNL = float(os.environ.get("PROFIT_MATURITY_MIN_PNL_PCT", "0.12"))
MIN_PEAK = float(os.environ.get("PROFIT_MATURITY_MIN_PEAK_PROFIT_PCT", "0.16"))
MIN_GIVEBACK = float(os.environ.get("PROFIT_MATURITY_MIN_GIVEBACK_PCT", "0.025"))
MIN_HOLD = int(os.environ.get("PROFIT_MATURITY_MIN_HOLD_SECONDS", "21600"))
MIN_NEW_SCORE = float(os.environ.get("PROFIT_MATURITY_MIN_NEW_SCORE", "0.034"))
MIN_SCORE_EDGE = float(os.environ.get("PROFIT_MATURITY_MIN_SCORE_EDGE", "0.012"))
EXCEPTIONAL_SCORE = float(os.environ.get("PROFIT_MATURITY_EXCEPTIONAL_NEW_SCORE", "0.045"))
STALE_WINNER_MAX_SCORE = float(os.environ.get("PROFIT_MATURITY_STALE_WINNER_MAX_SCORE", "0.028"))
MAX_ROTATIONS_PER_CYCLE = int(os.environ.get("PROFIT_MATURITY_MAX_ROTATIONS_PER_CYCLE", "2"))

PROFIT_GUARD_REDEPLOY_ENABLED = os.environ.get("PROFIT_GUARD_EXCEPTIONAL_REDEPLOY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PROFIT_GUARD_REDEPLOY_SCORE = float(os.environ.get("PROFIT_GUARD_EXCEPTIONAL_REDEPLOY_SCORE", str(EXCEPTIONAL_SCORE)))
PROFIT_GUARD_REDEPLOY_MAX_PER_CYCLE = int(os.environ.get("PROFIT_GUARD_EXCEPTIONAL_REDEPLOY_MAX_PER_CYCLE", "1"))


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "rotation_allowed"):
            return m
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "rotation_allowed"):
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


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _positions(m: Any | None) -> Dict[str, Any]:
    try:
        return dict((m.portfolio.get("positions", {}) or {}))
    except Exception:
        return {}


def _bucket(m: Any | None, symbol: str) -> str:
    try:
        fn = getattr(m, "symbol_bucket", None)
        if callable(fn):
            return str(fn(symbol))
    except Exception:
        pass
    try:
        return str((getattr(m, "SYMBOL_BUCKET", {}) or {}).get(symbol, "unknown"))
    except Exception:
        return "unknown"


def _sector(m: Any | None, symbol: str, fallback: str = "UNKNOWN") -> str:
    try:
        return str((getattr(m, "SYMBOL_SECTOR", {}) or {}).get(symbol, fallback))
    except Exception:
        return fallback


def _pnl_pct(m: Any | None, pos: Dict[str, Any], px: float) -> float:
    try:
        fn = getattr(m, "position_pnl_pct", None)
        if callable(fn):
            return _f(fn(pos, px), 0.0)
    except Exception:
        pass
    entry = max(_f(pos.get("entry"), px), 0.01)
    return (entry - px) / entry if str(pos.get("side", "long")).lower() == "short" else (px - entry) / entry


def _position_snapshot(m: Any | None, symbol: str, pos: Dict[str, Any] | None = None) -> Dict[str, Any]:
    pos = dict(pos or _positions(m).get(symbol) or {})
    px = _f(pos.get("last_price", pos.get("entry", 0.0)), 0.0)
    entry = max(_f(pos.get("entry", px), px), 0.01)
    side = str(pos.get("side", "long")).lower()
    pnl = _pnl_pct(m, pos, px) if pos else 0.0
    if side == "short":
        peak_profit = max(0.0, (entry - _f(pos.get("trough", px), px)) / entry)
    else:
        peak_profit = max(0.0, (_f(pos.get("peak", px), px) - entry) / entry)
    try:
        now_fn = getattr(m, "now_ts", None)
        now_ts = int(now_fn()) if callable(now_fn) else int(dt.datetime.now().timestamp())
        held = max(0, now_ts - _i(pos.get("entry_time"), now_ts))
    except Exception:
        held = 0
    return {
        "symbol": symbol,
        "side": side,
        "score": _f(pos.get("score"), 0.0),
        "pnl_pct": pnl,
        "pnl_pct_display": round(pnl * 100, 2),
        "peak_profit_pct": peak_profit,
        "peak_profit_pct_display": round(peak_profit * 100, 2),
        "giveback_pct": max(0.0, peak_profit - pnl),
        "giveback_pct_display": round(max(0.0, peak_profit - pnl) * 100, 2),
        "held_seconds": held,
        "held_hours": round(held / 3600.0, 2),
        "sector": str(pos.get("sector") or _sector(m, symbol)),
        "bucket": _bucket(m, symbol),
    }


def _market_ok(market: Dict[str, Any] | None) -> Tuple[bool, str]:
    market = market or {}
    mode = str(market.get("market_mode", "neutral") or "neutral").lower()
    if bool(market.get("bear_confirmed")) or mode in {"risk_off", "crash_warning", "defensive_rotation"}:
        return False, "market_not_risk_on_for_profit_maturity_rotation"
    if bool(market.get("broad_market_soft")) and mode not in {"risk_on", "constructive"}:
        return False, "broad_market_soft"
    return True, "ok"


def _market_ok_for_redeploy(market: Dict[str, Any] | None) -> Tuple[bool, str]:
    market = market or {}
    mode = str(market.get("market_mode", "neutral") or "neutral").lower()
    if bool(market.get("bear_confirmed")) or bool(market.get("broad_market_soft")):
        return False, "market_not_clean_for_profit_guard_redeploy"
    if mode != "risk_on":
        return False, "profit_guard_redeploy_requires_risk_on"
    return True, "ok"


def _self_defense_active(m: Any | None) -> Tuple[bool, str]:
    try:
        fn = getattr(m, "get_risk_controls", None)
        rc = fn() if callable(fn) else {}
        if isinstance(rc, dict) and bool(rc.get("self_defense_active")):
            return True, str(rc.get("self_defense_reason") or "self_defense_active")
    except Exception:
        pass
    try:
        rc = ((getattr(m, "portfolio", {}) or {}).get("risk_controls") or {})
        if isinstance(rc, dict) and bool(rc.get("self_defense_active")):
            return True, str(rc.get("self_defense_reason") or "self_defense_active")
    except Exception:
        pass
    return False, ""


def _is_profit_guard_block(new_entries_allowed: bool, entry_block_reason: Any) -> bool:
    reason = str(entry_block_reason or "").lower()
    return (not bool(new_entries_allowed)) and ("profit_guard" in reason or "profit guard" in reason)


def _is_breakout_signal(signal: Dict[str, Any] | None) -> bool:
    if not isinstance(signal, dict):
        return False
    ctx = signal.get("breakout_participation") or {}
    catalyst = signal.get("catalyst") or {}
    return bool(
        ctx.get("active")
        or signal.get("entry_context") == "breakout_participation_starter"
        or signal.get("trade_class") == "breakout_starter"
        or catalyst.get("reason") == "breakout_participation_layer"
    )


def _signal_summary(m: Any | None, signal: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(signal.get("symbol", "")).upper()
    ctx = signal.get("breakout_participation") or {}
    return {
        "symbol": symbol,
        "side": signal.get("side"),
        "score": round(_f(signal.get("score"), 0.0), 6),
        "sector": signal.get("sector") or _sector(m, symbol),
        "bucket": _bucket(m, symbol),
        "entry_context": signal.get("entry_context"),
        "trade_class": signal.get("trade_class"),
        "breakout": bool(_is_breakout_signal(signal)),
        "breakout_reason": ctx.get("reason"),
        "risk_tier": ctx.get("risk_tier"),
    }


def _best_exceptional_redeploy_signal(
    m: Any | None,
    long_signals: Iterable[Dict[str, Any]] | None,
    short_signals: Iterable[Dict[str, Any]] | None,
    params: Dict[str, Any] | None,
    market: Dict[str, Any] | None,
    new_entries_allowed: bool,
    entry_block_reason: Any,
) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
    if not PROFIT_GUARD_REDEPLOY_ENABLED:
        return None, {"allowed": False, "reason": "profit_guard_redeploy_disabled", "version": VERSION}
    if not _paper_context():
        return None, {"allowed": False, "reason": "not_paper_context", "version": VERSION}
    if _CYCLE_REDEPLOY_ENTRIES_USED >= PROFIT_GUARD_REDEPLOY_MAX_PER_CYCLE:
        return None, {"allowed": False, "reason": "profit_guard_redeploy_cycle_limit_reached", "max_per_cycle": PROFIT_GUARD_REDEPLOY_MAX_PER_CYCLE, "version": VERSION}
    if not _is_profit_guard_block(new_entries_allowed, entry_block_reason):
        return None, {"allowed": False, "reason": "entry_block_not_profit_guard", "entry_block_reason": str(entry_block_reason or ""), "version": VERSION}

    active, defense_reason = _self_defense_active(m)
    if active:
        return None, {"allowed": False, "reason": "self_defense_active", "self_defense_reason": defense_reason, "version": VERSION}

    ok, reason = _market_ok_for_redeploy(market or {})
    if not ok:
        return None, {"allowed": False, "reason": reason, "version": VERSION}

    positions = _positions(m)
    max_positions = _i((params or {}).get("max_positions"), 0)
    if max_positions <= 0:
        return None, {"allowed": False, "reason": "missing_effective_max_positions", "version": VERSION}
    if len(positions) >= max_positions:
        return None, {"allowed": False, "reason": "book_not_underdeployed", "open_positions_count": len(positions), "max_positions": max_positions, "version": VERSION}

    held = {str(s).upper() for s in positions}
    candidates = []
    for sig in list(long_signals or []) + list(short_signals or []):
        if not isinstance(sig, dict):
            continue
        symbol = str(sig.get("symbol", "")).upper()
        if not symbol or symbol in held:
            continue
        score = _f(sig.get("score"), 0.0)
        if score < PROFIT_GUARD_REDEPLOY_SCORE:
            continue
        if not _is_breakout_signal(sig):
            continue
        candidates.append(sig)

    if not candidates:
        return None, {
            "allowed": False,
            "reason": "no_exceptional_breakout_redeploy_candidate",
            "required_score": PROFIT_GUARD_REDEPLOY_SCORE,
            "open_positions_count": len(positions),
            "max_positions": max_positions,
            "version": VERSION,
        }

    best = sorted(candidates, key=lambda s: _f(s.get("score"), 0.0), reverse=True)[0]
    return best, {
        "allowed": True,
        "reason": "profit_guard_exceptional_redeploy_candidate",
        "version": VERSION,
        "candidate": _signal_summary(m, best),
        "required_score": PROFIT_GUARD_REDEPLOY_SCORE,
        "open_positions_count": len(positions),
        "max_positions": max_positions,
        "does_not_raise_max_positions": True,
        "does_not_bypass_halts": True,
        "does_not_bypass_stop_losses": True,
        "does_not_force_entries": False,
        "entry_quality_check_still_required": True,
        "max_redeploy_entries_per_cycle": PROFIT_GUARD_REDEPLOY_MAX_PER_CYCLE,
    }


def _single_signal_lists(signal: Dict[str, Any] | None) -> Tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    if not isinstance(signal, dict):
        return [], []
    if str(signal.get("side", "long")).lower() == "short":
        return [], [signal]
    return [signal], []


def profit_maturity_allowed(m: Any | None, new_signal: Dict[str, Any], weakest: Dict[str, Any], market: Dict[str, Any] | None) -> Tuple[bool, Dict[str, Any]]:
    if not ENABLED:
        return False, {"reason": "profit_maturity_rotation_disabled", "version": VERSION}
    if not _paper_context():
        return False, {"reason": "not_paper_context", "version": VERSION}
    if _CYCLE_ROTATIONS_USED >= MAX_ROTATIONS_PER_CYCLE:
        return False, {"reason": "profit_maturity_cycle_limit_reached", "max_rotations_per_cycle": MAX_ROTATIONS_PER_CYCLE, "version": VERSION}
    ok, reason = _market_ok(market)
    if not ok:
        return False, {"reason": reason, "version": VERSION}

    new_symbol = str(new_signal.get("symbol", "")).upper()
    weak_symbol = str(weakest.get("symbol", "")).upper()
    if not new_symbol or not weak_symbol or new_symbol == weak_symbol:
        return False, {"reason": "invalid_rotation_pair", "version": VERSION}
    if str(new_signal.get("side", "long")).lower() != str(weakest.get("side", "long")).lower():
        return False, {"reason": "profit_maturity_same_side_required", "version": VERSION, "weakest_symbol": weak_symbol}

    snap = _position_snapshot(m, weak_symbol)
    new_score = _f(new_signal.get("score"), 0.0)
    weak_score = _f(weakest.get("score", snap.get("score")), 0.0)
    score_edge = new_score - weak_score
    held = max(_i(weakest.get("held_seconds"), 0), _i(snap.get("held_seconds"), 0))
    pnl = _f(weakest.get("pnl_pct", snap.get("pnl_pct")), 0.0)
    peak = _f(snap.get("peak_profit_pct"), max(0.0, pnl))
    giveback = max(0.0, peak - pnl)

    if held < MIN_HOLD:
        return False, {"reason": "profit_maturity_min_hold_not_met", "held_seconds": held, "required_hold_seconds": MIN_HOLD, "weakest_symbol": weak_symbol, "version": VERSION}
    if pnl < MIN_PNL:
        return False, {"reason": "winner_not_mature_enough", "weakest_pnl_pct": round(pnl * 100, 2), "required_pnl_pct": round(MIN_PNL * 100, 2), "weakest_symbol": weak_symbol, "version": VERSION}
    if peak < MIN_PEAK:
        return False, {"reason": "peak_profit_not_mature_enough", "peak_profit_pct": round(peak * 100, 2), "required_peak_profit_pct": round(MIN_PEAK * 100, 2), "weakest_symbol": weak_symbol, "version": VERSION}
    if new_score < MIN_NEW_SCORE:
        return False, {"reason": "new_signal_below_profit_maturity_floor", "new_score": round(new_score, 6), "required_new_score": MIN_NEW_SCORE, "weakest_symbol": weak_symbol, "version": VERSION}
    if score_edge < MIN_SCORE_EDGE and new_score < EXCEPTIONAL_SCORE:
        return False, {"reason": "profit_maturity_score_edge_not_met", "new_score": round(new_score, 6), "weakest_score": round(weak_score, 6), "score_edge": round(score_edge, 6), "required_score_edge": MIN_SCORE_EDGE, "exceptional_new_score": EXCEPTIONAL_SCORE, "weakest_symbol": weak_symbol, "version": VERSION}

    fading = giveback >= MIN_GIVEBACK
    stale_exception = weak_score <= STALE_WINNER_MAX_SCORE and new_score >= EXCEPTIONAL_SCORE
    if not (fading or stale_exception):
        return False, {"reason": "mature_winner_still_working", "weakest_symbol": weak_symbol, "weakest_pnl_pct": round(pnl * 100, 2), "peak_profit_pct": round(peak * 100, 2), "giveback_pct": round(giveback * 100, 2), "required_giveback_pct": round(MIN_GIVEBACK * 100, 2), "new_score": round(new_score, 6), "weakest_score": round(weak_score, 6), "version": VERSION}

    return True, {
        "reason": "profit_maturity_rotation_to_stronger_signal",
        "version": VERSION,
        "weakest_symbol": weak_symbol,
        "new_symbol": new_symbol,
        "new_score": round(new_score, 6),
        "weakest_score": round(weak_score, 6),
        "score_edge": round(score_edge, 6),
        "weakest_pnl_pct": round(pnl * 100, 2),
        "peak_profit_pct": round(peak * 100, 2),
        "giveback_pct": round(giveback * 100, 2),
        "held_seconds": held,
        "held_hours": round(held / 3600.0, 2),
        "maturity_trigger": "giveback" if fading else "stale_low_score_exceptional_replacement",
        "sector_aligned": new_signal.get("sector") in ((market or {}).get("sector_leaders", []) or []),
        "does_not_raise_max_positions": True,
        "entry_quality_check_still_required": True,
    }


def _chain_has_marker(fn: Any, marker: str, limit: int = 30) -> bool:
    seen: set[int] = set()
    cur = fn
    for _ in range(limit):
        if not callable(cur) or id(cur) in seen:
            return False
        seen.add(id(cur))
        if bool(getattr(cur, marker, False)):
            return True
        cur = next((getattr(cur, a, None) for a in ("_profit_maturity_rotation_original", "_paper_breakout_rotation_original", "_paper_exposure_debug_original", "__wrapped__") if callable(getattr(cur, a, None))), None)
    return False


def _patch_rotation_allowed(m: Any) -> bool:
    current = getattr(m, "rotation_allowed", None)
    if not callable(current) or _chain_has_marker(current, "_profit_maturity_rotation_patched"):
        return False
    original = current

    def patched_rotation_allowed(new_signal, weakest, market):
        global _CYCLE_ROTATIONS_USED
        allowed, info = original(new_signal, weakest, market)
        if allowed:
            return allowed, info
        mature_ok, mature_info = profit_maturity_allowed(m, new_signal or {}, weakest or {}, market or {})
        if mature_ok:
            _CYCLE_ROTATIONS_USED += 1
            mature_info["standard_rotation_block"] = info
            return True, mature_info
        try:
            info = dict(info or {})
            info["profit_maturity_rotation_info"] = mature_info
        except Exception:
            pass
        return False, info

    patched_rotation_allowed._profit_maturity_rotation_patched = True  # type: ignore[attr-defined]
    patched_rotation_allowed._profit_maturity_rotation_original = original  # type: ignore[attr-defined]
    m.rotation_allowed = patched_rotation_allowed
    return True


def _review(m: Any, long_signals: Iterable[Dict[str, Any]] | None, short_signals: Iterable[Dict[str, Any]] | None, blocked_entries: Iterable[Dict[str, Any]] | None, params: Dict[str, Any] | None, market: Dict[str, Any] | None, rotations: Iterable[Dict[str, Any]] | None) -> Dict[str, Any]:
    positions = _positions(m)
    snaps = [_position_snapshot(m, s, p) for s, p in positions.items() if isinstance(p, dict)]
    mature = [p for p in snaps if p["pnl_pct"] >= MIN_PNL and p["peak_profit_pct"] >= MIN_PEAK and p["held_seconds"] >= MIN_HOLD]
    fading = [p for p in mature if p["giveback_pct"] >= MIN_GIVEBACK]
    held = {str(s).upper() for s in positions}
    signals = [s for s in list(long_signals or []) + list(short_signals or []) if isinstance(s, dict) and str(s.get("symbol", "")).upper() not in held]
    signals = sorted(signals, key=lambda x: _f(x.get("score"), 0.0), reverse=True)[:12]
    rotations_from_layer = [r for r in (rotations or []) if isinstance(r, dict) and str((r.get("info") or {}).get("reason", "")).startswith("profit_maturity_rotation")]
    blocked = [b for b in (blocked_entries or []) if isinstance(b, dict)]
    exceptional_redeploy_candidates = [
        _signal_summary(m, s)
        for s in signals
        if _is_breakout_signal(s) and _f(s.get("score"), 0.0) >= PROFIT_GUARD_REDEPLOY_SCORE
    ][:10]
    return {
        "status": "ok",
        "type": "profit_maturity_rotation_review",
        "version": VERSION,
        "generated_local": _now(m),
        "enabled": bool(ENABLED and _paper_context()),
        "does_not_raise_max_positions": True,
        "does_not_bypass_halts": True,
        "does_not_bypass_stop_losses": True,
        "does_not_force_entries": True,
        "entry_quality_check_still_required": True,
        "max_positions": int((params or {}).get("max_positions", 0) or 0),
        "open_positions_count": len(snaps),
        "mature_winners_count": len(mature),
        "fading_mature_winners_count": len(fading),
        "mature_winners": sorted(mature, key=lambda x: x["pnl_pct"], reverse=True)[:10],
        "fading_mature_winners": sorted(fading, key=lambda x: x["giveback_pct"], reverse=True)[:10],
        "top_unheld_signals": [_signal_summary(m, s) for s in signals],
        "exceptional_redeploy_candidates": exceptional_redeploy_candidates,
        "blocked_entries_count": len(blocked),
        "blocked_rotation_candidates": [b for b in blocked if "rotation" in str(b.get("reason", "")) or str(b.get("reason", "")).startswith("max_positions_full")][:12],
        "rotations_from_profit_maturity": rotations_from_layer[:10],
        "profit_guard_redeployment": (getattr(m, "portfolio", {}) or {}).get("profit_guard_redeployment") or {},
        "policy": {
            "min_pnl_pct": round(MIN_PNL * 100, 2),
            "min_peak_profit_pct": round(MIN_PEAK * 100, 2),
            "min_giveback_pct": round(MIN_GIVEBACK * 100, 2),
            "min_hold_hours": round(MIN_HOLD / 3600.0, 2),
            "min_new_score": MIN_NEW_SCORE,
            "min_score_edge": MIN_SCORE_EDGE,
            "exceptional_new_score": EXCEPTIONAL_SCORE,
            "max_rotations_per_cycle": MAX_ROTATIONS_PER_CYCLE,
            "profit_guard_redeploy_enabled": PROFIT_GUARD_REDEPLOY_ENABLED,
            "profit_guard_redeploy_score": PROFIT_GUARD_REDEPLOY_SCORE,
            "profit_guard_redeploy_max_per_cycle": PROFIT_GUARD_REDEPLOY_MAX_PER_CYCLE,
        },
    }


def _patch_try_entries(m: Any) -> bool:
    current = getattr(m, "try_entries_and_rotations", None)
    if not callable(current) or _chain_has_marker(current, "_profit_maturity_try_entries_patched"):
        return False
    original = current

    def patched_try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        global _CYCLE_ROTATIONS_USED, _CYCLE_REDEPLOY_ENTRIES_USED
        _CYCLE_ROTATIONS_USED = 0
        _CYCLE_REDEPLOY_ENTRIES_USED = 0

        redeploy_signal, redeploy_info = _best_exceptional_redeploy_signal(
            m,
            long_signals,
            short_signals,
            params or {},
            market or {},
            bool(new_entries_allowed),
            entry_block_reason,
        )
        call_long_signals = long_signals
        call_short_signals = short_signals
        call_new_entries_allowed = new_entries_allowed
        call_entry_block_reason = entry_block_reason

        if redeploy_signal is not None:
            call_long_signals, call_short_signals = _single_signal_lists(redeploy_signal)
            call_new_entries_allowed = True
            call_entry_block_reason = None
            _CYCLE_REDEPLOY_ENTRIES_USED += 1
            redeploy_info["entry_scope"] = "single_exceptional_breakout_candidate_only"

        entries, rotations, blocked_entries = original(
            call_long_signals,
            call_short_signals,
            params,
            market,
            new_entries_allowed=call_new_entries_allowed,
            entry_block_reason=call_entry_block_reason,
        )

        try:
            if redeploy_signal is not None:
                sym = str(redeploy_signal.get("symbol", "")).upper()
                redeploy_info["entries_from_redeploy"] = [e for e in (entries or []) if str(e.get("symbol", "")).upper() == sym][:5]
                redeploy_info["blocked_redeploy_entries"] = [b for b in (blocked_entries or []) if str(b.get("symbol", "")).upper() == sym][:5]
                redeploy_info["status"] = "entered" if redeploy_info["entries_from_redeploy"] else "passed_to_entry_pipeline"
            else:
                redeploy_info["status"] = "not_applicable"
            m.portfolio["profit_guard_redeployment"] = redeploy_info
        except Exception:
            pass

        try:
            m.portfolio["profit_maturity_rotation_review"] = _review(m, long_signals, short_signals, blocked_entries, params or {}, market or {}, rotations)
        except Exception as exc:
            try:
                m.portfolio["profit_maturity_rotation_review"] = {"status": "error", "type": "profit_maturity_rotation_review", "version": VERSION, "error": str(exc)}
            except Exception:
                pass
        return entries, rotations, blocked_entries

    patched_try_entries_and_rotations._profit_maturity_try_entries_patched = True  # type: ignore[attr-defined]
    patched_try_entries_and_rotations._profit_maturity_rotation_original = original  # type: ignore[attr-defined]
    m.try_entries_and_rotations = patched_try_entries_and_rotations
    return True


def status_payload(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "type": "profit_maturity_rotation_status", "version": VERSION, "reason": "app_module_not_ready"}
    try:
        latest = dict((m.portfolio or {}).get("profit_maturity_rotation_review") or {})
    except Exception:
        latest = {}
    try:
        redeployment = dict((m.portfolio or {}).get("profit_guard_redeployment") or {})
    except Exception:
        redeployment = {}
    return {
        "status": "ok",
        "type": "profit_maturity_rotation_status",
        "version": VERSION,
        "generated_local": _now(m),
        "enabled": bool(ENABLED and _paper_context()),
        "patched_rotation_allowed": _chain_has_marker(getattr(m, "rotation_allowed", None), "_profit_maturity_rotation_patched"),
        "patched_try_entries": _chain_has_marker(getattr(m, "try_entries_and_rotations", None), "_profit_maturity_try_entries_patched"),
        "latest_review": latest,
        "profit_guard_redeployment": redeployment,
    }


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "version": VERSION, "reason": "app_module_not_ready"}
    patched_rotation = _patch_rotation_allowed(m)
    patched_try_entries = _patch_try_entries(m)
    payload = status_payload(m)
    payload["patched_this_call"] = {"rotation_allowed": bool(patched_rotation), "try_entries_and_rotations": bool(patched_try_entries)}
    return payload


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify

    def profit_maturity_rotation_status():
        return jsonify(apply_runtime_overrides(m or _mod()))

    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/profit-maturity-rotation-status" not in existing:
        flask_app.add_url_rule("/paper/profit-maturity-rotation-status", "profit_maturity_rotation_status", profit_maturity_rotation_status)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply_runtime_overrides(m or _mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
