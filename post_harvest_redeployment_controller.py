"""Controlled post-harvest redeployment for paper trading.

This layer is intentionally narrow. It only wakes up after the bot has already
harvested profit and is sitting underdeployed with clean risk controls. It may
submit 1-2 high-quality unheld long candidates back through the normal entry
pipeline. It does not raise max positions, bypass halts, bypass stop losses,
bypass self-defense, bypass account risk controls, or force fills.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, Iterable, Tuple

VERSION = "post-harvest-redeployment-2026-06-03-v2"
REGISTERED_APP_IDS: set[int] = set()
_CYCLE_ENTRIES_USED = 0

ENABLED = os.environ.get("POST_HARVEST_REDEPLOYMENT_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("POST_HARVEST_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
MAX_OPEN_POSITIONS = int(os.environ.get("POST_HARVEST_MAX_OPEN_POSITIONS", "4"))
TARGET_OPEN_POSITIONS = int(os.environ.get("POST_HARVEST_TARGET_OPEN_POSITIONS", "6"))
MIN_CASH_PCT = float(os.environ.get("POST_HARVEST_MIN_CASH_PCT", "0.60"))
MIN_SCORE = float(os.environ.get("POST_HARVEST_MIN_SCORE", "0.034"))
EXCEPTIONAL_SCORE = float(os.environ.get("POST_HARVEST_EXCEPTIONAL_SCORE", "0.045"))
MAX_ENTRIES_PER_CYCLE = int(os.environ.get("POST_HARVEST_MAX_ENTRIES_PER_CYCLE", "2"))
EXIT_COOLDOWN_SECONDS = int(os.environ.get("POST_HARVEST_EXIT_COOLDOWN_SECONDS", "21600"))
MIN_SIGNAL_COUNT = int(os.environ.get("POST_HARVEST_MIN_SIGNAL_COUNT", "8"))
MIN_REALIZED_TODAY = float(os.environ.get("POST_HARVEST_MIN_REALIZED_TODAY", "25"))
MAX_LOSSES_TODAY = int(os.environ.get("POST_HARVEST_MAX_LOSSES_TODAY", "0"))
MAX_DAILY_DRAWDOWN_PCT = float(os.environ.get("POST_HARVEST_MAX_DAILY_DRAWDOWN_PCT", "1.25"))
NO_TIMESTAMP_EXIT_LOOKBACK = int(os.environ.get("POST_HARVEST_NO_TS_EXIT_LOOKBACK", "40"))

PREFERRED_CONTEXTS = {
    "breakout_participation_starter",
    "relative_strength_leader_exception",
    "pattern_recognition_ranked",
    "post_harvest_redeployment_starter",
}
PREFERRED_CLASSES = {"breakout_starter", "leader_hold", "swing_candidate", "intraday_trade"}
HARD_BLOCK_TOKENS = (
    "halt",
    "stop_loss",
    "stop loss",
    "daily_loss",
    "daily loss",
    "drawdown",
    "self_defense",
    "self defense",
    "market_not",
    "bear",
    "risk_off",
    "stale_runner",
    "runner_stale",
)
SOFT_BLOCK_TOKENS = ("profit_guard", "profit guard", "harvest", "maturity", "underdeploy", "underdeployed", "cash")
PROFIT_TOKENS = ("profit", "harvest", "maturity", "trim", "take_profit", "take profit", "winner")


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


def _now_ts(m: Any | None = None) -> int:
    try:
        fn = getattr(m, "now_ts", None)
        return int(fn()) if callable(fn) else int(dt.datetime.now().timestamp())
    except Exception:
        return int(dt.datetime.now().timestamp())


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


def _portfolio(m: Any | None) -> Dict[str, Any]:
    try:
        return dict(getattr(m, "portfolio", {}) or {})
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


def _portfolio_cash_equity(m: Any | None) -> Tuple[float, float, float]:
    portfolio = _portfolio(m)
    cash = _f(portfolio.get("cash"), 0.0)
    equity = _f(portfolio.get("equity"), 0.0)
    if equity <= 0:
        try:
            equity = _f((portfolio.get("performance") or {}).get("equity"), 0.0)
        except Exception:
            pass
    if equity <= 0:
        position_value = 0.0
        for pos in _positions(m).values():
            if isinstance(pos, dict):
                px = _f(pos.get("last_price", pos.get("entry", 0.0)), 0.0)
                shares = abs(_f(pos.get("shares", pos.get("qty", pos.get("quantity", 0.0))), 0.0))
                position_value += px * shares
        equity = cash + position_value
    return cash, equity, (cash / equity if equity > 0 else 0.0)


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


def _market_ok(market: Dict[str, Any] | None) -> Tuple[bool, str]:
    market = market or {}
    mode = str(market.get("market_mode", "neutral") or "neutral").lower()
    regime = str(market.get("regime", "") or "").lower()
    if bool(market.get("bear_confirmed")) or bool(market.get("broad_market_soft")):
        return False, "market_not_clean_for_post_harvest_redeploy"
    if "risk_off" in mode or "defensive" in mode or "bear" in regime:
        return False, "post_harvest_redeploy_blocked_by_market_mode"
    if mode != "risk_on":
        return False, "post_harvest_redeploy_requires_risk_on"
    return True, "ok"


def _risk_ok(m: Any | None) -> Tuple[bool, Dict[str, Any]]:
    rc = _risk_controls(m)
    reason = str(rc.get("halt_reason") or rc.get("self_defense_reason") or "")
    losses_today = _i(rc.get("losses_today", (_portfolio(m).get("performance") or {}).get("losses_today", 0)), 0)
    daily_dd = max(
        _f(rc.get("daily_drawdown_pct"), 0.0),
        _f(rc.get("intraday_drawdown_pct"), 0.0),
    )
    blocked = {
        "halted": bool(rc.get("halted")),
        "self_defense_active": bool(rc.get("self_defense_active")),
        "losses_today": losses_today,
        "daily_drawdown_pct": round(daily_dd, 4),
        "halt_reason": reason,
    }
    if blocked["halted"]:
        return False, {**blocked, "reason": "risk_halt_active"}
    if blocked["self_defense_active"]:
        return False, {**blocked, "reason": "self_defense_active"}
    if losses_today > MAX_LOSSES_TODAY:
        return False, {**blocked, "reason": "losses_today_not_clean"}
    if daily_dd >= MAX_DAILY_DRAWDOWN_PCT:
        return False, {**blocked, "reason": "daily_drawdown_above_post_harvest_limit"}
    return True, {**blocked, "reason": "risk_controls_clean"}


def _entry_block_safe(new_entries_allowed: bool, entry_block_reason: Any) -> Tuple[bool, str]:
    if bool(new_entries_allowed):
        return True, "entries_already_allowed"
    reason = str(entry_block_reason or "").lower()
    if any(token in reason for token in HARD_BLOCK_TOKENS):
        return False, "hard_entry_block_not_overridden"
    if any(token in reason for token in SOFT_BLOCK_TOKENS):
        return True, "post_harvest_soft_block_override"
    return False, "entry_block_reason_not_post_harvest_safe"


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
        or signal.get("breakout") is True
    )


def _is_relative_strength_signal(signal: Dict[str, Any] | None) -> bool:
    if not isinstance(signal, dict):
        return False
    text = " ".join(str(signal.get(k, "")).lower() for k in ("entry_context", "trade_class", "reason", "signal_type"))
    if "relative_strength" in text or "relative strength" in text or "leader" in text:
        return True
    for key in ("relative_strength", "relative_strength_score", "rs_score", "rs_rank", "momentum_rank"):
        value = signal.get(key)
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, (int, float)) and _f(value) > 0:
            return True
    return False


def _summary(m: Any | None, signal: Dict[str, Any]) -> Dict[str, Any]:
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
        "relative_strength": bool(_is_relative_strength_signal(signal)),
        "breakout_reason": ctx.get("reason"),
        "risk_tier": ctx.get("risk_tier"),
    }


def _trades(m: Any | None) -> list[Dict[str, Any]]:
    try:
        rows = list((_portfolio(m).get("trades", []) or []))
    except Exception:
        rows = []
    return [r for r in rows if isinstance(r, dict)]


def _is_exit_row(row: Dict[str, Any]) -> bool:
    text = " ".join(str(row.get(k, "")).lower() for k in ("action", "event", "type", "reason", "side"))
    return bool(row.get("exit_time") or row.get("closed_at")) or any(token in text for token in ("sell", "exit", "close", "trim", "harvest", "take_profit"))


def _row_ts(row: Dict[str, Any]) -> int:
    return _i(row.get("exit_time") or row.get("closed_at") or row.get("ts") or row.get("time") or row.get("timestamp"), 0)


def _row_pnl(row: Dict[str, Any]) -> float:
    for key in ("pnl", "profit", "realized_pnl", "pnl_dollars", "gain", "net_pnl"):
        if key in row:
            return _f(row.get(key), 0.0)
    return 0.0


def _recent_exit_symbols(m: Any | None) -> set[str]:
    if EXIT_COOLDOWN_SECONDS <= 0:
        return set()
    now_ts = _now_ts(m)
    out: set[str] = set()
    no_ts_scanned = 0
    for row in reversed(_trades(m)[-250:]):
        symbol = str(row.get("symbol") or row.get("ticker") or "").upper()
        if not symbol or not _is_exit_row(row):
            continue
        ts = _row_ts(row)
        if ts and 0 <= now_ts - ts <= EXIT_COOLDOWN_SECONDS:
            out.add(symbol)
        elif not ts and no_ts_scanned < NO_TIMESTAMP_EXIT_LOOKBACK:
            out.add(symbol)
            no_ts_scanned += 1
    return out


def _realized_value(portfolio: Dict[str, Any], key_names: Iterable[str]) -> float:
    perf = portfolio.get("performance") or {}
    sources = [portfolio, perf]
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in key_names:
            if key in source:
                return _f(source.get(key), 0.0)
    return 0.0


def _profit_harvest_ok(m: Any | None, entry_block_reason: Any) -> Tuple[bool, Dict[str, Any]]:
    portfolio = _portfolio(m)
    reason_text = str(entry_block_reason or "").lower()
    realized_today = _realized_value(
        portfolio,
        ("realized_today", "realized_pnl_today", "realized_profit_today", "day_realized_pnl", "realized_today_pnl"),
    )
    realized_total = _realized_value(
        portfolio,
        ("realized_total", "realized_pnl_total", "total_realized_pnl", "realized_pnl"),
    )
    recent_profit_exits: list[Dict[str, Any]] = []
    now_ts = _now_ts(m)
    for row in reversed(_trades(m)[-250:]):
        if not _is_exit_row(row):
            continue
        pnl = _row_pnl(row)
        ts = _row_ts(row)
        recent_enough = bool(ts and 0 <= now_ts - ts <= EXIT_COOLDOWN_SECONDS)
        if pnl > 0 and (recent_enough or len(recent_profit_exits) < 5):
            recent_profit_exits.append({"symbol": str(row.get("symbol") or row.get("ticker") or "").upper(), "pnl": round(pnl, 2), "ts": ts})
        if len(recent_profit_exits) >= 5:
            break
    token_evidence = any(token in reason_text for token in PROFIT_TOKENS)
    ok = bool(realized_today >= MIN_REALIZED_TODAY or recent_profit_exits or token_evidence)
    return ok, {
        "reason": "profit_harvest_confirmed" if ok else "profit_harvest_not_confirmed",
        "realized_today": round(realized_today, 2),
        "realized_total": round(realized_total, 2),
        "min_realized_today": MIN_REALIZED_TODAY,
        "entry_block_profit_token": token_evidence,
        "recent_profit_exits": recent_profit_exits[:5],
    }


def _quality_ok(signal: Dict[str, Any]) -> Tuple[bool, str]:
    if str(signal.get("side", "long")).lower() != "long":
        return False, "post_harvest_redeploy_long_only_in_risk_on"
    score = _f(signal.get("score"), 0.0)
    if score >= EXCEPTIONAL_SCORE:
        return True, "exceptional_score"
    if score < MIN_SCORE:
        return False, "score_below_post_harvest_floor"
    if _is_breakout_signal(signal):
        return True, "breakout_quality"
    if _is_relative_strength_signal(signal):
        return True, "relative_strength_quality"
    if str(signal.get("entry_context") or "") in PREFERRED_CONTEXTS:
        return True, "preferred_entry_context"
    if str(signal.get("trade_class") or "") in PREFERRED_CLASSES:
        return True, "preferred_trade_class"
    return False, "missing_breakout_or_relative_strength_quality"


def _priority(signal: Dict[str, Any]) -> float:
    return (
        _f(signal.get("score"), 0.0)
        + (0.006 if _is_breakout_signal(signal) else 0.0)
        + (0.004 if _is_relative_strength_signal(signal) else 0.0)
        + (0.002 if str(signal.get("trade_class") or "") in {"leader_hold", "breakout_starter"} else 0.0)
    )


def _signal_lists(signals: list[Dict[str, Any]]) -> Tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    longs, shorts = [], []
    for signal in signals:
        (shorts if str(signal.get("side", "long")).lower() == "short" else longs).append(signal)
    return longs, shorts


def _starter_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    copied = dict(signal)
    copied.setdefault("entry_context", "post_harvest_redeployment_starter")
    copied["post_harvest_redeployment"] = {
        "enabled": True,
        "scope": "starter_position_only",
        "max_entries_per_cycle": MAX_ENTRIES_PER_CYCLE,
        "version": VERSION,
    }
    return copied


def select_redeployment_candidates(
    m: Any | None,
    long_signals: Iterable[Dict[str, Any]] | None,
    short_signals: Iterable[Dict[str, Any]] | None,
    params: Dict[str, Any] | None,
    market: Dict[str, Any] | None,
    new_entries_allowed: bool,
    entry_block_reason: Any,
) -> Tuple[list[Dict[str, Any]], Dict[str, Any]]:
    if not ENABLED:
        return [], {"allowed": False, "reason": "post_harvest_redeployment_disabled", "version": VERSION}
    if not _paper_context():
        return [], {"allowed": False, "reason": "not_paper_context", "version": VERSION}
    if _CYCLE_ENTRIES_USED >= MAX_ENTRIES_PER_CYCLE:
        return [], {"allowed": False, "reason": "post_harvest_cycle_limit_reached", "max_per_cycle": MAX_ENTRIES_PER_CYCLE, "version": VERSION}

    risk_ok, risk_info = _risk_ok(m)
    if not risk_ok:
        return [], {"allowed": False, "reason": risk_info.get("reason", "risk_controls_not_clean"), "risk_controls": risk_info, "version": VERSION}

    ok, reason = _market_ok(market or {})
    if not ok:
        return [], {"allowed": False, "reason": reason, "version": VERSION}

    ok, reason = _entry_block_safe(new_entries_allowed, entry_block_reason)
    if not ok:
        return [], {"allowed": False, "reason": reason, "entry_block_reason": str(entry_block_reason or ""), "version": VERSION}

    profit_ok, profit_info = _profit_harvest_ok(m, entry_block_reason)
    if not profit_ok:
        return [], {"allowed": False, "reason": "profit_harvest_not_confirmed", "profit_harvest": profit_info, "version": VERSION}

    positions = _positions(m)
    max_positions = _i((params or {}).get("max_positions"), 0)
    if max_positions <= 0:
        return [], {"allowed": False, "reason": "missing_effective_max_positions", "version": VERSION}
    if len(positions) >= max_positions:
        return [], {"allowed": False, "reason": "book_not_underdeployed", "open_positions_count": len(positions), "max_positions": max_positions, "version": VERSION}
    if len(positions) > MAX_OPEN_POSITIONS:
        return [], {"allowed": False, "reason": "open_positions_above_post_harvest_threshold", "open_positions_count": len(positions), "threshold": MAX_OPEN_POSITIONS, "version": VERSION}

    cash, equity, cash_pct = _portfolio_cash_equity(m)
    if cash_pct < MIN_CASH_PCT:
        return [], {
            "allowed": False,
            "reason": "cash_pct_below_post_harvest_threshold",
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "cash_pct": round(cash_pct, 4),
            "required_cash_pct": MIN_CASH_PCT,
            "version": VERSION,
        }

    all_signals = list(long_signals or []) + list(short_signals or [])
    if len(all_signals) < MIN_SIGNAL_COUNT:
        return [], {"allowed": False, "reason": "scanner_signal_count_too_low_for_redeployment", "signals_found": len(all_signals), "min_signal_count": MIN_SIGNAL_COUNT, "version": VERSION}

    held, recent = {str(s).upper() for s in positions}, _recent_exit_symbols(m)
    candidates: list[Dict[str, Any]] = []
    rejected: list[Dict[str, Any]] = []
    for sig in all_signals:
        if not isinstance(sig, dict):
            continue
        symbol = str(sig.get("symbol", "")).upper()
        if not symbol:
            continue
        if symbol in held:
            continue
        if symbol in recent:
            rejected.append({"symbol": symbol, "reason": "recent_profit_harvest_cooldown"})
            continue
        sig_ok, sig_reason = _quality_ok(sig)
        if sig_ok:
            candidates.append(sig)
        elif len(rejected) < 12:
            item = _summary(m, sig)
            item["reason"] = sig_reason
            rejected.append(item)

    if not candidates:
        return [], {
            "allowed": False,
            "reason": "no_post_harvest_redeployment_candidate",
            "required_score": MIN_SCORE,
            "open_positions_count": len(positions),
            "max_positions": max_positions,
            "cash_pct": round(cash_pct, 4),
            "signals_found": len(all_signals),
            "rejected_top_candidates": rejected[:12],
            "profit_harvest": profit_info,
            "risk_controls": risk_info,
            "version": VERSION,
        }

    limit = max(0, min(MAX_ENTRIES_PER_CYCLE - _CYCLE_ENTRIES_USED, max_positions - len(positions), TARGET_OPEN_POSITIONS - len(positions)))
    if limit <= 0:
        return [], {"allowed": False, "reason": "post_harvest_target_slots_not_available", "open_positions_count": len(positions), "target_open_positions": TARGET_OPEN_POSITIONS, "max_positions": max_positions, "version": VERSION}

    ranked = sorted(candidates, key=_priority, reverse=True)
    selected = [_starter_signal(s) for s in ranked[:limit]]
    return selected, {
        "allowed": True,
        "reason": "post_harvest_controlled_redeployment_candidates",
        "version": VERSION,
        "entry_scope": "controlled_post_harvest_redeployment_ladder",
        "candidates": [_summary(m, s) for s in selected],
        "top_candidates_reviewed": [_summary(m, s) for s in ranked[:10]],
        "rejected_top_candidates": rejected[:12],
        "open_positions_count": len(positions),
        "target_open_positions": TARGET_OPEN_POSITIONS,
        "max_positions": max_positions,
        "cash": round(cash, 2),
        "equity": round(equity, 2),
        "cash_pct": round(cash_pct, 4),
        "signals_found": len(all_signals),
        "profit_harvest": profit_info,
        "risk_controls": risk_info,
        "max_entries_per_cycle": MAX_ENTRIES_PER_CYCLE,
        "does_not_raise_max_positions": True,
        "does_not_bypass_halts": True,
        "does_not_bypass_stop_losses": True,
        "does_not_bypass_self_defense": True,
        "does_not_force_entries": True,
        "entry_quality_check_still_required": True,
        "cooldown_seconds_after_harvest": EXIT_COOLDOWN_SECONDS,
    }


def _chain_has_marker(fn: Any, marker: str, limit: int = 40) -> bool:
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
                getattr(cur, a, None)
                for a in (
                    "_post_harvest_redeployment_original",
                    "_profit_maturity_rotation_original",
                    "_paper_breakout_rotation_original",
                    "_paper_exposure_debug_original",
                    "__wrapped__",
                )
                if callable(getattr(cur, a, None))
            ),
            None,
        )
    return False


def _patch_try_entries(m: Any) -> bool:
    current = getattr(m, "try_entries_and_rotations", None)
    if not callable(current) or _chain_has_marker(current, "_post_harvest_redeployment_patched"):
        return False
    original = current

    def patched_try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        global _CYCLE_ENTRIES_USED
        _CYCLE_ENTRIES_USED = 0
        selected, info = select_redeployment_candidates(
            m,
            long_signals,
            short_signals,
            params or {},
            market or {},
            bool(new_entries_allowed),
            entry_block_reason,
        )
        call_long_signals, call_short_signals = long_signals, short_signals
        call_new_entries_allowed, call_entry_block_reason = new_entries_allowed, entry_block_reason
        if selected:
            call_long_signals, call_short_signals = _signal_lists(selected)
            call_new_entries_allowed, call_entry_block_reason = True, None
            _CYCLE_ENTRIES_USED += len(selected)
        entries, rotations, blocked_entries = original(
            call_long_signals,
            call_short_signals,
            params,
            market,
            new_entries_allowed=call_new_entries_allowed,
            entry_block_reason=call_entry_block_reason,
        )
        try:
            if selected:
                syms = {str(s.get("symbol", "")).upper() for s in selected}
                info["entries_from_post_harvest"] = [e for e in (entries or []) if str(e.get("symbol", "")).upper() in syms][:10]
                info["blocked_post_harvest_entries"] = [b for b in (blocked_entries or []) if str(b.get("symbol", "")).upper() in syms][:10]
                info["status"] = "entered" if info["entries_from_post_harvest"] else "passed_to_entry_pipeline"
            else:
                info["status"] = "not_applicable"
            m.portfolio["post_harvest_redeployment"] = info
        except Exception:
            pass
        return entries, rotations, blocked_entries

    patched_try_entries_and_rotations._post_harvest_redeployment_patched = True  # type: ignore[attr-defined]
    patched_try_entries_and_rotations._post_harvest_redeployment_original = original  # type: ignore[attr-defined]
    m.try_entries_and_rotations = patched_try_entries_and_rotations
    return True


def status_payload(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "type": "post_harvest_redeployment_status", "version": VERSION, "reason": "app_module_not_ready"}
    try:
        latest = dict((m.portfolio or {}).get("post_harvest_redeployment") or {})
    except Exception:
        latest = {}
    positions = _positions(m)
    cash, equity, cash_pct = _portfolio_cash_equity(m)
    risk_ok, risk_info = _risk_ok(m)
    profit_ok, profit_info = _profit_harvest_ok(m, latest.get("entry_block_reason"))
    return {
        "status": "ok",
        "type": "post_harvest_redeployment_status",
        "version": VERSION,
        "generated_local": _now(m),
        "enabled": bool(ENABLED and _paper_context()),
        "patched_try_entries": _chain_has_marker(getattr(m, "try_entries_and_rotations", None), "_post_harvest_redeployment_patched"),
        "latest_redeployment": latest,
        "current_book": {
            "open_positions_count": len(positions),
            "cash": round(cash, 2),
            "equity": round(equity, 2),
            "cash_pct": round(cash_pct, 4),
            "underdeployed": bool(len(positions) <= MAX_OPEN_POSITIONS and cash_pct >= MIN_CASH_PCT),
        },
        "risk_controls_clean": bool(risk_ok),
        "risk_controls": risk_info,
        "profit_harvest_confirmed": bool(profit_ok),
        "profit_harvest": profit_info,
        "policy": {
            "does_not_raise_max_positions": True,
            "does_not_bypass_halts": True,
            "does_not_bypass_stop_losses": True,
            "does_not_bypass_self_defense": True,
            "does_not_force_entries": True,
            "entry_quality_check_still_required": True,
            "max_open_positions_threshold": MAX_OPEN_POSITIONS,
            "target_open_positions": TARGET_OPEN_POSITIONS,
            "min_cash_pct": MIN_CASH_PCT,
            "min_score": MIN_SCORE,
            "exceptional_score": EXCEPTIONAL_SCORE,
            "max_entries_per_cycle": MAX_ENTRIES_PER_CYCLE,
            "min_signal_count": MIN_SIGNAL_COUNT,
            "min_realized_today": MIN_REALIZED_TODAY,
            "max_losses_today": MAX_LOSSES_TODAY,
            "max_daily_drawdown_pct": MAX_DAILY_DRAWDOWN_PCT,
            "exit_cooldown_seconds": EXIT_COOLDOWN_SECONDS,
        },
    }


def apply_runtime_overrides(m: Any | None = None) -> Dict[str, Any]:
    m = m or _mod()
    if m is None:
        return {"status": "pending", "type": "post_harvest_redeployment_status", "version": VERSION, "reason": "app_module_not_ready"}
    patched = _patch_try_entries(m)
    payload = status_payload(m)
    payload["patched_this_call"] = {"try_entries_and_rotations": bool(patched)}
    return payload


def register_routes(flask_app: Any, m: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify

    def post_harvest_redeployment_status():
        return jsonify(apply_runtime_overrides(m or _mod()))

    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/post-harvest-redeployment-status" not in existing:
        flask_app.add_url_rule("/paper/post-harvest-redeployment-status", "post_harvest_redeployment_status", post_harvest_redeployment_status)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply_runtime_overrides(m or _mod())


try:
    apply_runtime_overrides(_mod())
except Exception:
    pass
