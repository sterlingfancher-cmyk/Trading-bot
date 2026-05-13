"""Benchmark comparison + guarded risk-on participation mode."""
from __future__ import annotations

import copy
import functools
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Tuple

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

VERSION = "benchmark-participation-2026-05-13"
_REGISTERED: set[int] = set()
_APPLIED: set[int] = set()
_CACHE: Dict[str, Any] = {"ts": 0.0, "snapshot": None}

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(os.environ.get("STATE_FILE", "state.json"))) if STATE_DIR else os.environ.get("STATE_FILE", "state.json")

ENABLED = os.environ.get("RISK_ON_PARTICIPATION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
NEAR_HIGH_PCT = float(os.environ.get("RISK_ON_NEAR_HIGH_PCT", "0.0035"))
MAX_DRAWDOWN = float(os.environ.get("RISK_ON_MAX_DRAWDOWN_PCT", "0.0015"))
MAX_DAILY_LOSS = float(os.environ.get("RISK_ON_MAX_DAILY_LOSS_PCT", "0.0015"))
TARGET_POSITIONS = int(os.environ.get("RISK_ON_TARGET_LONG_POSITIONS", "3"))
MIN_TARGET_POSITIONS = int(os.environ.get("RISK_ON_MIN_TARGET_LONG_POSITIONS", "2"))
NEW_ENTRIES_PER_CYCLE = int(os.environ.get("RISK_ON_NEW_ENTRIES_PER_CYCLE", "2"))
ENTRY_SCORE_FLOOR = float(os.environ.get("RISK_ON_ENTRY_SCORE_FLOOR", "0.024"))
CORE_ALLOC_FACTOR = float(os.environ.get("RISK_ON_CORE_ALLOC_FACTOR", "1.35"))
HIGH_BETA_ALLOC_FACTOR = float(os.environ.get("RISK_ON_HIGH_BETA_ALLOC_FACTOR", "0.80"))
BENCHMARK_ALLOC_FACTOR = float(os.environ.get("RISK_ON_BENCHMARK_ALLOC_FACTOR", "1.00"))
CACHE_TTL = int(os.environ.get("RISK_ON_CACHE_TTL_SECONDS", "75"))

CORE_BUCKETS = {"mega_cap_ai", "semi_leaders", "cloud_cyber_software", "data_center_infra"}
HIGH_BETA_BUCKETS = {"small_cap_momentum", "bitcoin_ai_compute"}
HARD_BLOCKS = ("self_defense", "halt", "cooldown", "late_day", "after_hours", "stop_loss", "max_loss", "sector_exposure", "bucket_exposure", "extended_above", "extended_below")
SOFT_BLOCKS = ("entry_score_below_minimum", "controlled_pullback_empty_book_only", "score_below", "below_minimum", "position_limit", "max_positions")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default


def _now_text() -> str:
    try:
        import datetime as dt, pytz
        tz = pytz.timezone(os.environ.get("MARKET_TZ", "America/Chicago"))
        return dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        import datetime as dt
        return dt.datetime.now().isoformat(timespec="seconds")


def _load_state(core: Any | None = None) -> Dict[str, Any]:
    try:
        if core is not None and hasattr(core, "load_state"):
            s = core.load_state()
            return s if isinstance(s, dict) else {}
    except Exception:
        pass
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            s = json.load(f)
            return s if isinstance(s, dict) else {}
    except Exception:
        return {}


def _series(df: Any, name: str) -> List[float]:
    if df is None:
        return []
    try:
        if name in df:
            return [float(x) for x in df[name].dropna().tolist()]
    except Exception:
        pass
    try:
        for col in getattr(df, "columns", []):
            if (isinstance(col, tuple) and str(col[-1]).lower() == name.lower()) or str(col).lower() == name.lower():
                return [float(x) for x in df[col].dropna().tolist()]
    except Exception:
        pass
    return []


def _intraday(core: Any | None, symbol: str):
    try:
        if core is not None and hasattr(core, "download_prices"):
            return core.download_prices(symbol, period="1d", interval="5m")
    except Exception:
        pass
    if yf is None:
        return None
    try:
        return yf.download(symbol, period="1d", interval="5m", progress=False, auto_adjust=True, threads=False)
    except Exception:
        return None


def _bench(core: Any | None, symbol: str) -> Dict[str, Any]:
    df = _intraday(core, symbol)
    closes, highs, opens = _series(df, "Close"), _series(df, "High"), _series(df, "Open")
    if not closes:
        return {"symbol": symbol, "status": "missing", "positive": False, "near_day_high": False, "day_return_pct": 0.0, "distance_from_high_pct": None}
    last = closes[-1]
    first = opens[0] if opens else closes[0]
    high = max(highs) if highs else max(closes)
    ret = (last / first - 1.0) if first > 0 else 0.0
    dist = (high - last) / high if high > 0 else 1.0
    return {"symbol": symbol, "status": "ok", "positive": ret > 0, "near_day_high": dist <= NEAR_HIGH_PCT, "day_return_pct": round(ret * 100, 3), "distance_from_high_pct": round(dist * 100, 3), "last_price": round(last, 4), "day_high": round(high, 4), "near_high_threshold_pct": round(NEAR_HIGH_PCT * 100, 3)}


def _positions(state: Dict[str, Any]) -> Dict[str, Any]:
    raw = ((state.get("performance") or {}).get("open_positions") or state.get("positions") or {})
    if not isinstance(raw, dict):
        raw = {}
    rows, long_count, any_profit = [], 0, False
    for sym, p in raw.items():
        if not isinstance(p, dict):
            continue
        side = str(p.get("side", "long")).lower()
        pnl_pct_raw = _f(p.get("pnl_pct"), 0.0)
        pnl_pct = pnl_pct_raw / 100.0 if abs(pnl_pct_raw) > 1.5 else pnl_pct_raw
        if side == "long":
            long_count += 1
            any_profit = any_profit or pnl_pct >= 0
        rows.append({"symbol": str(sym).upper(), "side": side, "pnl_pct": round(pnl_pct * 100, 3), "pnl_dollars": round(_f(p.get("pnl_dollars"), 0), 2), "score": p.get("score"), "sector": p.get("sector")})
    return {"count": len(rows), "long_count": long_count, "flat_book": len(rows) == 0, "any_profitable_long": any_profit, "positions": rows}


def build_snapshot(core: Any | None = None, force: bool = False) -> Dict[str, Any]:
    if not force and _CACHE["snapshot"] and time.time() - _CACHE["ts"] <= CACHE_TTL:
        return copy.deepcopy(_CACHE["snapshot"])
    state = _load_state(core)
    spy, qqq = _bench(core, "SPY"), _bench(core, "QQQ")
    perf, risk = state.get("performance") or {}, state.get("risk_controls") or {}
    pos = _positions(state)
    equity = _f(state.get("equity"), 0.0)
    start = _f(risk.get("day_start_equity"), 0.0)
    bot_ret = (equity / start - 1.0) * 100.0 if equity > 0 and start > 0 else 0.0
    checks = {
        "spy_positive_near_high": bool(spy.get("positive") and spy.get("near_day_high")),
        "qqq_positive_near_high": bool(qqq.get("positive") and qqq.get("near_day_high")),
        "self_defense_clear": not bool(risk.get("self_defense_active")),
        "drawdown_near_zero": _f(risk.get("intraday_drawdown_pct"), 0.0) <= MAX_DRAWDOWN,
        "daily_loss_near_zero": _f(risk.get("daily_loss_pct"), 0.0) <= MAX_DAILY_LOSS,
        "book_flat_or_profitable": bool(pos["flat_book"] or pos["any_profitable_long"]),
    }
    active = bool(ENABLED and all(checks.values()))
    target = max(MIN_TARGET_POSITIONS, min(TARGET_POSITIONS, 3)) if active else pos["long_count"]
    alpha_spy = round(bot_ret - _f(spy.get("day_return_pct"), 0.0), 3)
    alpha_qqq = round(bot_ret - _f(qqq.get("day_return_pct"), 0.0), 3)
    cash = _f(state.get("cash"), 0.0)
    cash_pct = cash / equity if equity > 0 else 0.0
    score = "good"
    if active and pos["long_count"] < MIN_TARGET_POSITIONS:
        score = "too_low"
    elif active and pos["long_count"] < target:
        score = "moderate_underexposure"
    elif cash_pct > 0.4 and (spy.get("positive") or qqq.get("positive")):
        score = "cash_drag"
    recs = []
    if active:
        recs += ["Risk-on participation mode active: allow 2-3 active long positions.", "Modestly raise confirmed setup exposure toward the 3%-5% target band.", "Keep stops, but prefer profit-locks and partial exits over blocking all follow-up entries."]
    else:
        recs.append("Keep standard controls until SPY/QQQ are both positive and near highs with self-defense clear and minimal drawdown.")
    if score != "good":
        recs.append("Bot is under-participating versus SPY/QQQ; look for the next qualified long setup instead of staying at one position.")
    snap = {"status": "ok", "type": "benchmark_comparison", "version": VERSION, "generated_local": _now_text(), "benchmarks": {"SPY": spy, "QQQ": qqq}, "bot": {"equity": round(equity, 2), "cash": round(cash, 2), "bot_day_return_pct": round(bot_ret, 3), "realized_pnl_today": round(_f(perf.get("realized_pnl_today"), 0), 2), "realized_pnl_total": round(_f(perf.get("realized_pnl_total"), 0), 2), "unrealized_pnl": round(_f(perf.get("unrealized_pnl"), 0), 2), "daily_loss_pct": _f(risk.get("daily_loss_pct"), 0), "intraday_drawdown_pct": _f(risk.get("intraday_drawdown_pct"), 0), "self_defense_active": bool(risk.get("self_defense_active")), "self_defense_reason": risk.get("self_defense_reason", "")}, "positions": pos, "alpha": {"bot_vs_spy_alpha_pct": alpha_spy, "bot_vs_qqq_alpha_pct": alpha_qqq, "cash_pct": round(cash_pct * 100, 2), "cash_drag_detected": cash_pct > 0.4 and (spy.get("positive") or qqq.get("positive")), "participation_score": score}, "risk_on_participation": {"enabled": ENABLED, "active": active, "target_long_positions": target, "new_entries_per_cycle": NEW_ENTRIES_PER_CYCLE if active else None, "per_position_exposure_target_pct": "3-5% on confirmed setups while active", "checks": checks, "thresholds": {"near_high_pct": round(NEAR_HIGH_PCT * 100, 3), "max_intraday_drawdown_pct": round(MAX_DRAWDOWN * 100, 3), "max_daily_loss_pct": round(MAX_DAILY_LOSS * 100, 3), "entry_override_score_floor": ENTRY_SCORE_FLOOR}}, "recommended_actions": recs}
    _CACHE.update({"ts": time.time(), "snapshot": copy.deepcopy(snap)})
    return snap


def _save_runtime(core: Any) -> Dict[str, Any]:
    names = ["MAX_NEW_ENTRIES_PER_CYCLE", "MAX_POSITIONS_PER_SECTOR", "TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", "CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY", "CONTROLLED_PULLBACK_MIN_SCORE", "CONTROLLED_PULLBACK_SCORE_DISCOUNT"]
    saved = {n: getattr(core, n, None) for n in names}
    if isinstance(getattr(core, "BUCKET_CONFIG", None), dict):
        saved["BUCKET_CONFIG"] = copy.deepcopy(core.BUCKET_CONFIG)
    return saved


def _restore_runtime(core: Any, saved: Dict[str, Any]) -> None:
    for k, v in saved.items():
        try:
            if k == "BUCKET_CONFIG" and isinstance(getattr(core, "BUCKET_CONFIG", None), dict):
                core.BUCKET_CONFIG.clear(); core.BUCKET_CONFIG.update(v)
            elif v is not None:
                setattr(core, k, v)
        except Exception:
            pass


def _apply_runtime(core: Any, snap: Dict[str, Any]) -> Dict[str, Any]:
    if not (snap.get("risk_on_participation") or {}).get("active"):
        return {"applied": False, "reason": "risk_on_participation_not_active"}
    changes: Dict[str, Any] = {}
    def setmax(name: str, value: Any):
        old = getattr(core, name, None)
        try:
            new = max(old, value) if old is not None else value
            setattr(core, name, new)
            changes[name] = {"old": old, "new": new}
        except Exception as exc:
            changes[name] = {"old": old, "new": value, "error": str(exc)}
    def setmin(name: str, value: Any):
        old = getattr(core, name, None)
        try:
            new = min(old, value) if old is not None else value
            setattr(core, name, new)
            changes[name] = {"old": old, "new": new}
        except Exception as exc:
            changes[name] = {"old": old, "new": value, "error": str(exc)}
    setmax("MAX_NEW_ENTRIES_PER_CYCLE", NEW_ENTRIES_PER_CYCLE)
    setmax("MAX_POSITIONS_PER_SECTOR", 3)
    setmax("TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", 4)
    setmax("CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY", 2)
    setmin("CONTROLLED_PULLBACK_MIN_SCORE", ENTRY_SCORE_FLOOR)
    setmax("CONTROLLED_PULLBACK_SCORE_DISCOUNT", 0.006)
    cfg = getattr(core, "BUCKET_CONFIG", None)
    bchanges = {}
    if isinstance(cfg, dict):
        for bucket, row in cfg.items():
            if not isinstance(row, dict):
                continue
            old = _f(row.get("alloc_factor"), 1.0)
            if bucket in CORE_BUCKETS:
                new = max(old, CORE_ALLOC_FACTOR)
                row["max_positions"] = max(int(_f(row.get("max_positions"), 2)), 3)
            elif bucket in HIGH_BETA_BUCKETS:
                new = max(old, HIGH_BETA_ALLOC_FACTOR)
            elif bucket == "benchmark_etf":
                new = max(old, BENCHMARK_ALLOC_FACTOR)
            else:
                continue
            row["alloc_factor"] = round(new, 4)
            bchanges[bucket] = {"old_alloc_factor": old, "new_alloc_factor": row["alloc_factor"], "max_positions": row.get("max_positions")}
    changes["bucket_config"] = bchanges
    return {"applied": True, "version": VERSION, "changes": changes}


def _score(signal: Any) -> float:
    return _f(signal.get("score"), 0.0) if isinstance(signal, dict) else 0.0


def _side(signal: Any) -> str:
    return str(signal.get("side") or signal.get("direction") or "long").lower() if isinstance(signal, dict) else "long"


def _reason(info: Any) -> str:
    if not isinstance(info, dict):
        return str(info or "").lower()
    parts = [str(info.get("reason") or ""), str(info.get("entry_block_reason") or "")]
    cpi = info.get("controlled_pullback_info")
    if isinstance(cpi, dict):
        parts.append(str(cpi.get("reason") or ""))
    return " ".join(parts).lower()


def _quality_override_ok(signal: Any, info: Any, snap: Dict[str, Any]) -> Tuple[bool, str]:
    if not (snap.get("risk_on_participation") or {}).get("active"):
        return False, "participation_not_active"
    if _side(signal) != "long":
        return False, "only_long_overrides_allowed"
    if int((snap.get("positions") or {}).get("long_count", 0)) >= int((snap.get("risk_on_participation") or {}).get("target_long_positions", 1)):
        return False, "target_positions_met"
    reason = _reason(info)
    if any(x in reason for x in HARD_BLOCKS):
        return False, f"hard_block:{reason[:80]}"
    if reason and not any(x in reason for x in SOFT_BLOCKS):
        return False, f"not_soft_block:{reason[:80]}"
    if _score(signal) < ENTRY_SCORE_FLOOR:
        return False, f"score_too_low:{_score(signal):.6f}"
    return True, "risk_on_participation_soft_override"


def apply(core: Any | None = None) -> Dict[str, Any]:
    if core is None:
        for m in list(sys.modules.values()):
            if getattr(m, "app", None) is not None and hasattr(m, "load_state"):
                core = m; break
    if core is None:
        return {"status": "not_applied", "version": VERSION, "reason": "core_module_not_found"}
    if id(core) in _APPLIED:
        return {"status": "ok", "version": VERSION, "already_applied": True}
    patched = []
    if hasattr(core, "run_cycle") and not getattr(core.run_cycle, "_benchmark_participation_wrapped", False):
        original = core.run_cycle
        @functools.wraps(original)
        def run_cycle_wrapper(*args, **kwargs):
            snap = build_snapshot(core, force=True)
            saved = _save_runtime(core)
            runtime = _apply_runtime(core, snap)
            try:
                result = original(*args, **kwargs)
                if isinstance(result, dict):
                    result["benchmark_comparison"] = build_snapshot(core, force=True)
                    result["risk_on_participation_runtime"] = runtime
                return result
            finally:
                _restore_runtime(core, saved)
        run_cycle_wrapper._benchmark_participation_wrapped = True  # type: ignore[attr-defined]
        core.run_cycle = run_cycle_wrapper
        patched.append("run_cycle")
    if hasattr(core, "entry_quality_check") and not getattr(core.entry_quality_check, "_benchmark_participation_wrapped", False):
        original_q = core.entry_quality_check
        @functools.wraps(original_q)
        def entry_quality_check_wrapper(signal, params=None, market=None, *args, **kwargs):
            result = original_q(signal, params, market, *args, **kwargs)
            try:
                ok = bool(result[0]) if isinstance(result, tuple) and result else bool(result)
                info = result[1] if isinstance(result, tuple) and len(result) > 1 else {}
                if ok:
                    return result
                eligible, why = _quality_override_ok(signal, info, build_snapshot(core, force=False))
                if not eligible:
                    return result
                if not isinstance(info, dict):
                    info = {"original_quality_info": str(info)}
                info = dict(info)
                info.update({"risk_on_participation_override": True, "risk_on_participation_reason": why, "risk_on_participation_version": VERSION})
                return True, info
            except Exception:
                return result
        entry_quality_check_wrapper._benchmark_participation_wrapped = True  # type: ignore[attr-defined]
        core.entry_quality_check = entry_quality_check_wrapper
        patched.append("entry_quality_check")
    try:
        core.BENCHMARK_PARTICIPATION_VERSION = VERSION
    except Exception:
        pass
    _APPLIED.add(id(core))
    return {"status": "ok", "version": VERSION, "patched": patched}


def register_routes(flask_app: Any, core: Any | None = None) -> Dict[str, Any]:
    from flask import jsonify
    if core is None:
        for m in list(sys.modules.values()):
            if getattr(m, "app", None) is flask_app or (getattr(m, "app", None) is not None and hasattr(m, "load_state")):
                core = m; break
    applied = apply(core)
    if id(flask_app) in _REGISTERED:
        return {"status": "ok", "version": VERSION, "already_registered": True, "apply": applied}
    existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    if "/paper/benchmark-comparison" not in existing:
        flask_app.add_url_rule("/paper/benchmark-comparison", "benchmark_comparison", lambda: jsonify(build_snapshot(core, force=True)))
    if "/paper/market-participation-status" not in existing:
        def market_participation_status():
            s = build_snapshot(core, force=True)
            return jsonify({"status": "ok", "type": "market_participation_status", "version": VERSION, "generated_local": s.get("generated_local"), "benchmark_summary": s.get("benchmarks"), "bot_alpha": s.get("alpha"), "risk_on_participation": s.get("risk_on_participation"), "positions": s.get("positions"), "recommended_actions": s.get("recommended_actions")})
        flask_app.add_url_rule("/paper/market-participation-status", "market_participation_status", market_participation_status)
    _REGISTERED.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "registered": True, "apply": applied}
