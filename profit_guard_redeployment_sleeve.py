"""Profit Guard Redeployment Sleeve v3.

Purpose:
- Convert a normal day-profit pause from a global entry shutdown into one small,
  high-quality participation sleeve.
- Stay completely inert during normal entry cycles and whenever profit guard is
  not the active blocker.
- Avoid wrapper-order recursion with best-of-cycle arbitration.

Guardrails:
- Paper-only by default.
- Does not place trades by itself.
- Does not lower score floors.
- Does not bypass entry_quality_check, regime_flip_entry_guard, cooldowns,
  exposure caps, self-defense, late-day cutoff, or hard profit locks.
- Does not change ML authority or grant live authority.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "profit-guard-redeployment-sleeve-2026-06-24-v3-inert-unless-active"
ENABLED = os.environ.get("PROFIT_GUARD_REDEPLOYMENT_SLEEVE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("PROFIT_GUARD_REDEPLOYMENT_SLEEVE_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
MAX_REVIEWED = int(os.environ.get("PROFIT_GUARD_SLEEVE_MAX_REVIEWED", "30"))
MAX_ENTRIES_PER_DAY = int(os.environ.get("PROFIT_GUARD_SLEEVE_MAX_ENTRIES_PER_DAY", "1"))
ALLOC_FACTOR = float(os.environ.get("PROFIT_GUARD_SLEEVE_ALLOC_FACTOR", "0.35"))
MIN_SCORE = float(os.environ.get("PROFIT_GUARD_SLEEVE_MIN_SCORE", "0.018"))
ALLOWED_MARKET_MODES = {s.strip().lower() for s in os.environ.get("PROFIT_GUARD_SLEEVE_ALLOWED_MARKET_MODES", "risk_on,constructive").split(",") if s.strip()}
ALLOW_SHORTS = os.environ.get("PROFIT_GUARD_SLEEVE_ALLOW_SHORTS", "false").lower() in {"1", "true", "yes", "on"}
ALLOW_LEVERAGED_ETFS = os.environ.get("PROFIT_GUARD_SLEEVE_ALLOW_LEVERAGED_ETFS", "false").lower() in {"1", "true", "yes", "on"}
LEVERAGED_MIN_SCORE = float(os.environ.get("PROFIT_GUARD_SLEEVE_LEVERAGED_MIN_SCORE", "0.040"))
MAX_DAILY_LOSS_PCT = float(os.environ.get("PROFIT_GUARD_SLEEVE_MAX_DAILY_LOSS_PCT", "0.15"))
MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("PROFIT_GUARD_SLEEVE_MAX_INTRADAY_DRAWDOWN_PCT", "0.35"))
MAX_REALIZED_LOSS_TODAY = float(os.environ.get("PROFIT_GUARD_SLEEVE_MAX_REALIZED_LOSS_TODAY", "0.0"))

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
HARD_PROFIT_GUARD_MARKERS = {"hard lock", "giveback", "lock triggered"}
LEVERAGED_BUCKETS = {"leveraged_etf", "leveraged_etf_watch", "leveraged"}
ORIGINAL_ATTRS = ("_profit_guard_redeployment_sleeve_original", "_best_of_cycle_original")

THEME_PRIORITY = {
    "semi_leaders": 0.006,
    "memory_storage": 0.0055,
    "data_center_infra": 0.005,
    "power_grid_data_center": 0.005,
    "bitcoin_ai_compute": 0.0045,
    "small_cap_momentum": 0.0035,
    "space_stocks": 0.003,
    "cloud_cyber_software": 0.0025,
    "mega_cap_ai": 0.002,
}
PREFERRED_SYMBOLS = {"MU", "MRVL", "LRCX", "QCOM", "WDC", "GEV", "BE", "CIFR", "HIVE", "HUT", "WULF", "IREN", "CORZ", "ASTS", "RKLB", "PL", "DELL", "GLW", "SNDK", "TSM", "TXN", "ALAB", "ARM", "AMD", "AVGO"}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _symbol(signal: Any) -> str:
    if isinstance(signal, dict):
        value = signal.get("symbol") or signal.get("ticker") or ""
    else:
        value = signal or ""
    return str(value).upper().strip()


def _side(signal: Dict[str, Any]) -> str:
    return str(signal.get("side") or "long").lower().strip() or "long"


def _positions(core: Any) -> Dict[str, Any]:
    try:
        positions = core.portfolio.get("positions", {}) or {}
        return positions if isinstance(positions, dict) else {}
    except Exception:
        return {}


def _risk_controls(core: Any) -> Dict[str, Any]:
    try:
        fn = getattr(core, "get_risk_controls", None)
        if callable(fn):
            rc = fn()
            return rc if isinstance(rc, dict) else {}
    except Exception:
        pass
    try:
        rc = core.portfolio.get("risk_controls", {}) or {}
        return rc if isinstance(rc, dict) else {}
    except Exception:
        return {}


def _realized_today(core: Any) -> float:
    try:
        fn = getattr(core, "get_realized_pnl", None)
        if callable(fn):
            return _safe_float((fn() or {}).get("today"), 0.0)
    except Exception:
        pass
    try:
        return _safe_float((core.portfolio.get("realized_pnl", {}) or {}).get("today"), 0.0)
    except Exception:
        return 0.0


def _today_trades(core: Any) -> List[Dict[str, Any]]:
    try:
        fn = getattr(core, "trades_for_date", None)
        today = getattr(core, "today_key", lambda: "")()
        if callable(fn):
            rows = fn(today)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
    except Exception:
        pass
    try:
        return [r for r in (core.portfolio.get("trades", []) or []) if isinstance(r, dict)]
    except Exception:
        return []


def _sleeve_entries_today(core: Any) -> int:
    count = 0
    for trade in _today_trades(core):
        if str(trade.get("action") or "") != "entry":
            continue
        text = " ".join(str(trade.get(k) or "") for k in ("entry_context", "trade_class", "reason")).lower()
        if "profit_guard_redeployment_sleeve" in text:
            count += 1
    return count


def _bucket(core: Any, symbol: str, signal: Dict[str, Any]) -> str:
    value = signal.get("bucket") or signal.get("symbol_bucket")
    if value:
        return str(value)
    try:
        fn = getattr(core, "symbol_bucket", None)
        if callable(fn):
            return str(fn(symbol))
    except Exception:
        pass
    try:
        bucket_map = getattr(core, "SYMBOL_BUCKET", {}) or {}
        if isinstance(bucket_map, dict):
            return str(bucket_map.get(symbol, "unknown"))
    except Exception:
        pass
    return "unknown"


def _sector(core: Any, symbol: str, signal: Dict[str, Any]) -> str:
    value = signal.get("sector")
    if value:
        return str(value)
    try:
        sector_map = getattr(core, "SYMBOL_SECTOR", {}) or {}
        if isinstance(sector_map, dict):
            return str(sector_map.get(symbol, "UNKNOWN"))
    except Exception:
        pass
    return "UNKNOWN"


def _entry_blockers(entry_block_reason: Any) -> set[str]:
    return {part.strip() for part in str(entry_block_reason or "").split(",") if part.strip()}


def _profit_guard_state(core: Any) -> Dict[str, Any]:
    rc = _risk_controls(core)
    active = bool(rc.get("profit_guard_active", False))
    reason = str(rc.get("profit_guard_reason") or "")
    lower = reason.lower()
    if not active:
        state = "inactive"
    elif any(marker in lower for marker in HARD_PROFIT_GUARD_MARKERS):
        state = "hard_block"
    elif "day profit pause" in lower or "pause reached" in lower:
        state = "soft_pause"
    else:
        state = "active_unknown"
    return {"active": active, "state": state, "reason": reason, "risk_controls": rc}


def _market_ok(market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    mode = str((market or {}).get("market_mode") or "").lower()
    futures = (market or {}).get("futures_bias", {}) or {}
    futures_action = str(futures.get("action") or "").lower()
    bear = bool((market or {}).get("bear_confirmed", False))
    if bear or mode in {"risk_off", "crash_warning", "defensive_rotation", "bear"}:
        return False, {"reason": "market_regime_not_allowed", "market_mode": mode, "bear_confirmed": bear, "futures_action": futures_action}
    if mode not in ALLOWED_MARKET_MODES:
        return False, {"reason": "market_mode_not_allowed_for_profit_guard_sleeve", "market_mode": mode, "allowed_modes": sorted(ALLOWED_MARKET_MODES), "futures_action": futures_action}
    if futures_action == "block_opening_longs":
        return False, {"reason": "futures_block_opening_longs", "market_mode": mode, "futures_action": futures_action, "futures_bias": futures}
    return True, {"reason": "market_context_ok", "market_mode": mode, "futures_action": futures_action, "futures_bias": futures}


def _hard_risk_ok(core: Any, entry_block_reason: Any, market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    blockers = _entry_blockers(entry_block_reason)
    extra_blockers = sorted(blockers - {"profit_guard_active"})
    if extra_blockers:
        return False, {"reason": "non_profit_guard_entry_blocker_present", "blockers": sorted(blockers), "extra_blockers": extra_blockers}
    rc = _risk_controls(core)
    if bool(rc.get("halted", False)):
        return False, {"reason": "risk_halted", "risk_controls": rc}
    daily_loss = _safe_float(rc.get("daily_loss_pct"), 0.0)
    intraday_dd = _safe_float(rc.get("intraday_drawdown_pct"), 0.0)
    if daily_loss > MAX_DAILY_LOSS_PCT:
        return False, {"reason": "daily_loss_too_high_for_profit_guard_sleeve", "daily_loss_pct": daily_loss, "max_daily_loss_pct": MAX_DAILY_LOSS_PCT}
    if intraday_dd > MAX_INTRADAY_DRAWDOWN_PCT:
        return False, {"reason": "intraday_drawdown_too_high_for_profit_guard_sleeve", "intraday_drawdown_pct": intraday_dd, "max_intraday_drawdown_pct": MAX_INTRADAY_DRAWDOWN_PCT}
    realized = _realized_today(core)
    if realized < -abs(MAX_REALIZED_LOSS_TODAY):
        return False, {"reason": "realized_loss_today_blocks_profit_guard_sleeve", "realized_today": realized, "max_realized_loss_today": MAX_REALIZED_LOSS_TODAY}
    market_ok, market_info = _market_ok(market or {})
    if not market_ok:
        return False, market_info
    return True, {"reason": "hard_risk_context_ok", "risk_controls": rc, "market": market_info}


def _signal_text(signal: Dict[str, Any], quality_info: Dict[str, Any] | None = None) -> str:
    parts: List[str] = []
    for obj in (signal, quality_info or {}):
        if isinstance(obj, dict):
            for key in ("entry_context", "trade_class", "reason", "signal_type", "selection_reason"):
                if obj.get(key):
                    parts.append(str(obj.get(key)).lower())
    return " ".join(parts)


def _theme_confirmed(signal: Dict[str, Any]) -> bool:
    for key in ("theme_confirmation", "catalyst"):
        value = signal.get(key)
        if isinstance(value, dict) and value.get("active"):
            return True
    return False


def _is_relative_strength(signal: Dict[str, Any]) -> bool:
    text = _signal_text(signal)
    if "relative_strength" in text or "relative strength" in text or "leader" in text:
        return True
    for key in ("relative_strength", "relative_strength_score", "rs_score", "rs_rank", "momentum_rank"):
        value = signal.get(key)
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, (int, float)) and _safe_float(value) > 0:
            return True
    return False


def _is_breakout(signal: Dict[str, Any]) -> bool:
    text = _signal_text(signal)
    if "breakout" in text or "reclaim" in text:
        return True
    return any(bool(signal.get(k)) for k in ("breakout", "is_breakout", "breakout_signal"))


def _quality_preview(core: Any, signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    symbol = _symbol(signal)
    preview = dict(signal)
    preview.setdefault("bucket", _bucket(core, symbol, preview))
    preview.setdefault("sector", _sector(core, symbol, preview))
    preview["alloc_factor"] = min(_safe_float(preview.get("alloc_factor"), 1.0), ALLOC_FACTOR)
    preview.setdefault("entry_context", "profit_guard_redeployment_sleeve")
    preview.setdefault("trade_class", "profit_guard_redeployment_sleeve")
    try:
        quality_fn = getattr(core, "entry_quality_check", None)
        if callable(quality_fn):
            ok, info = quality_fn(preview, params or {}, market or {})
            return bool(ok), info if isinstance(info, dict) else {"reason": str(info)}, preview
    except RecursionError:
        return False, {"reason": "entry_quality_preview_recursion_guard"}, preview
    except Exception as exc:
        return False, {"reason": f"entry_quality_preview_error:{type(exc).__name__}"}, preview
    return False, {"reason": "entry_quality_check_unavailable"}, preview


def _candidate_score(core: Any, signal: Dict[str, Any], quality_info: Dict[str, Any], market: Dict[str, Any]) -> float:
    symbol = _symbol(signal)
    bucket = _bucket(core, symbol, signal)
    score = _safe_float(signal.get("score"), 0.0)
    score += THEME_PRIORITY.get(bucket, 0.0)
    if symbol in PREFERRED_SYMBOLS:
        score += 0.002
    if _is_relative_strength(signal):
        score += 0.004
    if _is_breakout(signal):
        score += 0.004
    if _theme_confirmed(signal):
        score += 0.003
    if str((quality_info or {}).get("reason") or "") == "entry_quality_ok":
        score += 0.006
    text = _signal_text(signal, quality_info)
    if "extended" in text or "chase" in text or "near_high" in text:
        score -= 0.006
    return round(float(score), 8)


def _is_leveraged(core: Any, symbol: str, signal: Dict[str, Any]) -> bool:
    bucket = _bucket(core, symbol, signal).lower()
    sector = _sector(core, symbol, signal).lower()
    if bucket in LEVERAGED_BUCKETS or sector == "leveraged_etf":
        return True
    return symbol in {"SOXL", "TQQQ", "QLD", "USD", "TECL", "FNGU", "SQQQ", "SOXS"}


def _review_candidates(core: Any, long_signals: Iterable[Any], short_signals: Iterable[Any], params: Dict[str, Any], market: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    raw: List[Dict[str, Any]] = []
    if (params or {}).get("allow_longs", False):
        raw.extend([s for s in (long_signals or []) if isinstance(s, dict)])
    if ALLOW_SHORTS and (params or {}).get("allow_shorts", False):
        raw.extend([s for s in (short_signals or []) if isinstance(s, dict)])
    raw = sorted(raw, key=lambda s: _safe_float(s.get("score"), 0.0), reverse=True)[:MAX_REVIEWED]

    reviewed: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    positions = _positions(core)

    for signal in raw:
        symbol = _symbol(signal)
        side = _side(signal)
        row = {"symbol": symbol, "side": side, "score": round(_safe_float(signal.get("score"), 0.0), 6), "bucket": _bucket(core, symbol, signal), "sector": _sector(core, symbol, signal), "reason": "reviewed"}
        if not symbol:
            row["reason"] = "missing_symbol"; rejected.append(row); reviewed.append(row); continue
        if symbol in positions:
            row["reason"] = "already_held"; rejected.append(row); reviewed.append(row); continue
        if side != "long" and not ALLOW_SHORTS:
            row["reason"] = "shorts_disabled_for_profit_guard_sleeve"; rejected.append(row); reviewed.append(row); continue
        try:
            cooldown_fn = getattr(core, "is_in_cooldown", None)
            if callable(cooldown_fn) and cooldown_fn(symbol):
                row["reason"] = "cooldown"; rejected.append(row); reviewed.append(row); continue
        except Exception:
            pass
        raw_score = _safe_float(signal.get("score"), 0.0)
        leveraged = _is_leveraged(core, symbol, signal)
        if leveraged and not ALLOW_LEVERAGED_ETFS:
            row["reason"] = "leveraged_etf_disabled_for_profit_guard_sleeve"; rejected.append(row); reviewed.append(row); continue
        if leveraged and raw_score < LEVERAGED_MIN_SCORE:
            row["reason"] = "leveraged_etf_score_below_exceptional_floor"; row["required_score"] = LEVERAGED_MIN_SCORE; rejected.append(row); reviewed.append(row); continue
        if raw_score < MIN_SCORE:
            row["reason"] = "score_below_profit_guard_sleeve_floor"; row["required_score"] = MIN_SCORE; rejected.append(row); reviewed.append(row); continue

        ok, quality_info, preview = _quality_preview(core, signal, params, market)
        row["quality_reason"] = str((quality_info or {}).get("reason") or "unknown")
        row["quality_passed"] = bool(ok)
        row["relative_strength"] = _is_relative_strength(preview)
        row["breakout"] = _is_breakout(preview)
        row["theme_confirmed"] = _theme_confirmed(preview)
        if not ok:
            row["reason"] = "entry_quality_block"; row["quality_info"] = quality_info; rejected.append(row); reviewed.append(row); continue
        rank = _candidate_score(core, preview, quality_info, market)
        preview["profit_guard_redeployment_sleeve"] = {"version": VERSION, "rank_score": rank, "alloc_factor": ALLOC_FACTOR, "profit_guard_state": "soft_pause", "quality_reason": row["quality_reason"]}
        row["reason"] = "eligible_profit_guard_redeployment_sleeve"
        row["rank_score"] = rank
        eligible.append({"signal": preview, "summary": row, "rank_score": rank})
        reviewed.append(row)
    return reviewed, sorted(eligible, key=lambda r: _safe_float(r.get("rank_score"), 0.0), reverse=True), rejected


def _split_selected(signals: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    longs: List[Dict[str, Any]] = []
    shorts: List[Dict[str, Any]] = []
    for signal in signals:
        if _side(signal) == "short":
            shorts.append(signal)
        else:
            longs.append(signal)
    return longs, shorts


def _record(core: Any, payload: Dict[str, Any]) -> None:
    try:
        core.portfolio["profit_guard_redeployment_sleeve"] = payload
    except Exception:
        pass


def _blocked_response(long_signals: Iterable[Any], short_signals: Iterable[Any], reason: str, max_rows: int = 10):
    rows: List[Dict[str, Any]] = []
    for signal in list(long_signals or []) + list(short_signals or []):
        if not isinstance(signal, dict):
            continue
        rows.append({"symbol": _symbol(signal), "side": _side(signal), "score": signal.get("score"), "reason": reason, "version": VERSION})
        if len(rows) >= max_rows:
            break
    return [], [], rows


def _chain_has_attr(fn: Any, attr: str, max_depth: int = 8) -> bool:
    seen: set[int] = set()
    cur = fn
    for _ in range(max_depth):
        if cur is None or id(cur) in seen:
            return False
        seen.add(id(cur))
        if getattr(cur, attr, False):
            return True
        nxt = None
        for original_attr in ORIGINAL_ATTRS:
            candidate = getattr(cur, original_attr, None)
            if candidate is not None:
                nxt = candidate
                break
        cur = nxt
    return False


def _patch_try_entries(core: Any) -> bool:
    current = getattr(core, "try_entries_and_rotations", None)
    if not callable(current):
        return False
    if _chain_has_attr(current, "_profit_guard_redeployment_sleeve_patched"):
        return False
    original = current

    def patched_try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        # Critical v3 behavior: this overlay is completely inert unless profit guard
        # is the active reason normal entries were blocked. Normal cycles are passed
        # through without setting recursion flags or generating blocked rows.
        blockers = _entry_blockers(entry_block_reason)
        profit_guard_is_active_blocker = (not bool(new_entries_allowed)) and ("profit_guard_active" in blockers)
        if not (ENABLED and _paper_context() and profit_guard_is_active_blocker):
            return original(long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

        if getattr(patched_try_entries_and_rotations, "_profit_guard_sleeve_attempt_in_progress", False):
            return _blocked_response(long_signals, short_signals, "profit_guard_sleeve_recursion_guard")

        profit_state = _profit_guard_state(core)
        base_payload = {"status": "checked", "version": VERSION, "generated_local": _now(core), "entry_block_reason": entry_block_reason, "entry_blockers": sorted(blockers), "profit_guard": {k: v for k, v in profit_state.items() if k != "risk_controls"}, "authority_changed": False, "live_trade_authority": "none", "ml_authority": "shadow_only"}

        def finish_block(status: str, reason: str, extra: Dict[str, Any] | None = None):
            payload = {**base_payload, "status": status, "reason": reason}
            if extra:
                payload.update(extra)
            _record(core, payload)
            return _blocked_response(long_signals, short_signals, reason)

        if not profit_state.get("active"):
            return original(long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)
        if profit_state.get("state") != "soft_pause":
            return finish_block("hard_block", "profit_guard_state_not_soft_pause")
        risk_ok, risk_info = _hard_risk_ok(core, entry_block_reason, market or {})
        if not risk_ok:
            return finish_block("blocked", str(risk_info.get("reason") or "profit_guard_sleeve_risk_context_block"), {"risk_context": risk_info})
        used_today = _sleeve_entries_today(core)
        if used_today >= MAX_ENTRIES_PER_DAY:
            return finish_block("blocked", "profit_guard_sleeve_daily_limit", {"entries_today": used_today, "max_entries_per_day": MAX_ENTRIES_PER_DAY})

        params_dict = dict(params or {})
        params_dict["long_alloc_pct"] = _safe_float(params_dict.get("long_alloc_pct"), 0.0)
        params_dict["short_alloc_pct"] = _safe_float(params_dict.get("short_alloc_pct"), 0.0)
        reviewed, eligible, rejected = _review_candidates(core, long_signals or [], short_signals or [], params_dict, market or {})
        if not eligible:
            return finish_block("no_eligible_candidate", "profit_guard_sleeve_no_candidate_passed_quality", {"reviewed_count": len(reviewed), "eligible_count": 0, "rejected_preview": rejected[:15], "risk_context": risk_info})

        selected = eligible[:1]
        selected_signals = [row["signal"] for row in selected]
        call_longs, call_shorts = _split_selected(selected_signals)
        try:
            patched_try_entries_and_rotations._profit_guard_sleeve_attempt_in_progress = True  # type: ignore[attr-defined]
            entries, rotations, blocked_entries = original(call_longs, call_shorts, params_dict, market, new_entries_allowed=True, entry_block_reason=None)
        except RecursionError:
            payload = {**base_payload, "status": "recursion_guard", "reason": "recursion_during_profit_guard_sleeve_attempt", "reviewed_count": len(reviewed), "eligible_count": len(eligible), "selected_candidates": [row.get("summary") for row in selected], "authority_changed": False}
            _record(core, payload)
            return _blocked_response(call_longs, call_shorts, "profit_guard_sleeve_recursion_guard")
        finally:
            patched_try_entries_and_rotations._profit_guard_sleeve_attempt_in_progress = False  # type: ignore[attr-defined]

        extra_blocked = []
        for row in eligible[1:11]:
            summary = dict(row.get("summary") or {})
            summary.update({"reason": "profit_guard_sleeve_not_selected", "selected_symbols": [_symbol(s) for s in selected_signals], "version": VERSION})
            extra_blocked.append(summary)
        try:
            if isinstance(blocked_entries, list):
                blocked_entries.extend(extra_blocked)
        except Exception:
            pass

        payload = {**base_payload, "status": "allowed" if entries or rotations else "attempted_no_entry", "reason": "profit_guard_soft_pause_sleeve_opened", "risk_context": risk_info, "reviewed_count": len(reviewed), "eligible_count": len(eligible), "selected_candidates": [row.get("summary") for row in selected], "not_selected_count": max(0, len(eligible) - len(selected)), "rejected_preview": rejected[:15], "entries_returned_count": len(entries or []), "rotations_returned_count": len(rotations or []), "policy": _policy()}
        _record(core, payload)
        return entries, rotations, blocked_entries

    patched_try_entries_and_rotations._profit_guard_redeployment_sleeve_patched = True  # type: ignore[attr-defined]
    patched_try_entries_and_rotations._profit_guard_redeployment_sleeve_original = original  # type: ignore[attr-defined]
    if getattr(original, "_best_of_cycle_arbitration_patched", False):
        patched_try_entries_and_rotations._best_of_cycle_arbitration_patched = True  # type: ignore[attr-defined]
    core.try_entries_and_rotations = patched_try_entries_and_rotations
    return True


def _policy() -> Dict[str, Any]:
    return {"max_reviewed": MAX_REVIEWED, "max_entries_per_day": MAX_ENTRIES_PER_DAY, "alloc_factor": ALLOC_FACTOR, "min_score": MIN_SCORE, "allowed_market_modes": sorted(ALLOWED_MARKET_MODES), "allow_shorts": bool(ALLOW_SHORTS), "allow_leveraged_etfs": bool(ALLOW_LEVERAGED_ETFS), "leveraged_min_score": LEVERAGED_MIN_SCORE, "max_daily_loss_pct": MAX_DAILY_LOSS_PCT, "max_intraday_drawdown_pct": MAX_INTRADAY_DRAWDOWN_PCT, "does_not_raise_max_positions": True, "does_not_bypass_entry_quality_check": True, "does_not_bypass_regime_flip_guard": True, "does_not_bypass_self_defense": True, "does_not_bypass_cooldowns": True, "does_not_lower_score_thresholds": True, "hard_profit_lock_still_blocks": True, "giveback_lock_still_blocks": True, "inert_unless_profit_guard_active_blocker": True, "normal_cycles_passthrough_without_recursion_flag": True, "live_trade_authority": "none", "ml_authority": "shadow_only", "authority_changed": False}


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    latest = {}
    if core is not None:
        try:
            latest = core.portfolio.get("profit_guard_redeployment_sleeve") or {}
        except Exception:
            latest = {}
    current = getattr(core, "try_entries_and_rotations", None) if core is not None else None
    return {"status": "ok" if core is not None else "pending", "overall": "pass" if core is not None else "pending", "type": "profit_guard_redeployment_sleeve_status", "version": VERSION, "generated_local": _now(core), "enabled": bool(ENABLED), "paper_context": bool(_paper_context()), "patched_try_entries": bool(_chain_has_attr(current, "_profit_guard_redeployment_sleeve_patched")), "latest": latest, "policy": _policy()}


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return status_payload(core)
    patched = _patch_try_entries(core)
    PATCHED_MODULE_IDS.add(id(core))
    payload = status_payload(core)
    payload["patched_this_call"] = {"try_entries_and_rotations": bool(patched)}
    return payload


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        return jsonify(apply(core or _mod()))

    if "/paper/profit-guard-redeployment-sleeve-status" not in existing:
        flask_app.add_url_rule("/paper/profit-guard-redeployment-sleeve-status", "profit_guard_redeployment_sleeve_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
