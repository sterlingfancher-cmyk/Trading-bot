"""Risk-on starter participation valve.

Purpose:
- Let a flat/underdeployed paper account participate with one small starter on
  broad risk-on mornings instead of waiting for a perfect FVG/VWAP/EMA reclaim.
- Keep this as a narrow overlay on top of the existing core participation valve
  and extended-leader starter valve.
- Preserve all hard safety controls: no live authority, no self-defense bypass,
  no risk-halt bypass, no cooldown bypass, and no broad threshold lowering.

This module patches only core_entry_pipeline._participation_valve_ok. It does
not wrap the main entry loop, does not place trades by itself, and does not
modify broker/live authority.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Iterable, Tuple

VERSION = "risk-on-starter-participation-valve-2026-07-09-v3-telemetry"
ENABLED = os.environ.get("RISK_ON_STARTER_VALVE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MAX_REVIEWED_RANK = int(os.environ.get("RISK_ON_STARTER_MAX_REVIEWED_RANK", "8"))
MAX_ENTRIES_PER_DAY = int(os.environ.get("RISK_ON_STARTER_MAX_ENTRIES_PER_DAY", "1"))
MAX_ENTRIES_PER_CYCLE = int(os.environ.get("RISK_ON_STARTER_MAX_ENTRIES_PER_CYCLE", "1"))
MIN_CASH_PCT = float(os.environ.get("RISK_ON_STARTER_MIN_CASH_PCT", "85.0"))
MAX_OPEN_POSITIONS = int(os.environ.get("RISK_ON_STARTER_MAX_OPEN_POSITIONS", "2"))
MIN_RAW_SCORE = float(os.environ.get("RISK_ON_STARTER_MIN_RAW_SCORE", "0.0080"))
MIN_RANK_SCORE = float(os.environ.get("RISK_ON_STARTER_MIN_RANK_SCORE", "0.0120"))
ALLOC_FACTOR = float(os.environ.get("RISK_ON_STARTER_ALLOC_FACTOR", "0.18"))
MAX_DAILY_LOSS_PCT = float(os.environ.get("RISK_ON_STARTER_MAX_DAILY_LOSS_PCT", "0.00"))
MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("RISK_ON_STARTER_MAX_INTRADAY_DRAWDOWN_PCT", "0.10"))
MIN_RISK_SCORE = float(os.environ.get("RISK_ON_STARTER_MIN_RISK_SCORE", "62"))
TELEMETRY_MAX_ROWS = int(os.environ.get("RISK_ON_STARTER_TELEMETRY_MAX_ROWS", "40"))
ALLOWED_MODES = {s.strip().lower() for s in os.environ.get("RISK_ON_STARTER_ALLOWED_MODES", "risk_on,constructive").split(",") if s.strip()}
PREFERRED_BUCKETS = {s.strip() for s in os.environ.get(
    "RISK_ON_STARTER_PREFERRED_BUCKETS",
    "semi_leaders,mega_cap_ai,ai_cloud_breakout,cloud_cyber_software,data_center_infra,bitcoin_ai_compute,space_stocks,small_cap_momentum,memory_storage,power_grid_data_center",
).split(",") if s.strip()}
PREFERRED_SYMBOLS = {s.strip().upper() for s in os.environ.get(
    "RISK_ON_STARTER_PREFERRED_SYMBOLS",
    "NVDA,AMD,AVGO,MU,LRCX,DELL,HPE,STX,WDC,SNDK,GEV,GLW,ON,NBIS,NVTS,ASTS,RKLB,RDW,LUNR,SPCE,BKSY,PL,CIFR,CLSK,CORZ,HUT,IREN,MARA,RIOT,WULF,HIVE,BTDR,SNOW,DUOL,PLTR",
).split(",") if s.strip()}
ALLOWED_BLOCK_TOKENS = tuple(s.strip().lower() for s in os.environ.get(
    "RISK_ON_STARTER_ALLOWED_BLOCK_TOKENS",
    "opening_warmup_active,early_entry_requires_fvg_reclaim_vwap_ema_confirmation,extended_above_5m_ma20,extension_chase,entry_score_below_minimum,score_below_post_harvest_floor,extended_starter_rank_too_low,extended_starter_raw_score_too_low,extended_starter_rank_score_too_low,participation_valve_extension_or_chase_block,relative_strength_leader_exception_block",
).split(",") if s.strip())
HARD_BLOCK_TOKENS = tuple(s.strip().lower() for s in os.environ.get(
    "RISK_ON_STARTER_HARD_BLOCK_TOKENS",
    "self_defense,risk_halted,halted,daily_loss,intraday_drawdown,cooldown,already_held,daily_limit,cycle_limit,missing_price,no_price,market_regime_block,bear,crash,risk_off,futures_block_opening_longs,futures_bias_block_opening_longs,volume_not_confirmed,trend_not_confirmed,stock_not_green_enough,relative_edge_too_small",
).split(",") if s.strip())

REGISTERED_APP_IDS: set[int] = set()
_PATCHED = False
_ORIGINAL_FN = None
_LAST_STATUS: Dict[str, Any] = {}


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return int(float(value))
    except Exception:
        return default


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _portfolio(core: Any) -> Dict[str, Any]:
    try:
        return getattr(core, "portfolio", {}) or {}
    except Exception:
        return {}


def _state(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is not None:
        try:
            fn = getattr(core, "load_state", None)
            if callable(fn):
                row = fn()
                return row if isinstance(row, dict) else {}
        except Exception:
            pass
    return _portfolio(core)


def _save_state(core: Any, state: Dict[str, Any]) -> bool:
    if not isinstance(state, dict):
        return False
    core = core or _mod()
    if core is not None:
        try:
            fn = getattr(core, "save_state", None)
            if callable(fn):
                fn(state)
                try:
                    setattr(core, "portfolio", state)
                except Exception:
                    pass
                return True
        except Exception:
            pass
    try:
        if core is not None and hasattr(core, "portfolio"):
            setattr(core, "portfolio", state)
            return True
    except Exception:
        pass
    return False


def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item(), depth + 1)
        except Exception:
            return str(value)
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            if callable(item):
                continue
            out[str(key)] = _json_safe(item, depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, depth + 1) for item in list(value)[:80]]
    return str(value)


def _positions(core: Any) -> Dict[str, Any]:
    positions = _portfolio(core).get("positions", {}) or {}
    return positions if isinstance(positions, dict) else {}


def _cash_pct(core: Any) -> float:
    pf = _portfolio(core)
    cash = _safe_float(pf.get("cash"), 0.0)
    equity = _safe_float(pf.get("equity"), cash)
    if equity <= 0:
        return 0.0
    return round((cash / equity) * 100.0, 4)


def _risk_controls(core: Any) -> Dict[str, Any]:
    try:
        fn = getattr(core, "get_risk_controls", None)
        if callable(fn):
            row = fn()
            return row if isinstance(row, dict) else {}
    except Exception:
        pass
    return _d(_portfolio(core).get("risk_controls"))


def _paper_context() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _symbol(signal: Dict[str, Any]) -> str:
    return str(signal.get("symbol") or signal.get("ticker") or "").upper().strip()


def _side(signal: Dict[str, Any]) -> str:
    return str(signal.get("side") or "long").lower().strip() or "long"


def _bucket(core: Any, symbol: str, signal: Dict[str, Any]) -> str:
    value = signal.get("bucket") or signal.get("symbol_bucket")
    if value:
        return str(value)
    try:
        return str((getattr(core, "SYMBOL_BUCKET", {}) or {}).get(symbol, "unknown"))
    except Exception:
        return "unknown"


def _quality_reason(info: Any) -> str:
    if isinstance(info, dict):
        for key in ("reason", "quality_reason", "status"):
            if info.get(key):
                return str(info.get(key))
        controlled = info.get("controlled_pullback_info")
        if isinstance(controlled, dict) and controlled.get("reason"):
            return str(controlled.get("reason"))
    return str(info or "unknown")


def _walk_text(obj: Any, depth: int = 0) -> Iterable[str]:
    if depth > 4:
        return []
    out: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"reason", "entry_context", "trade_class", "signal_type", "selection_reason", "quality_reason", "status", "base_participation_result", "participation_valve"} and value:
                out.append(str(value).lower())
            out.extend(_walk_text(value, depth + 1))
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            out.extend(_walk_text(value, depth + 1))
    elif isinstance(obj, str):
        out.append(obj.lower())
    return out


def _combined_text(*items: Any) -> str:
    parts: list[str] = []
    for item in items:
        parts.extend(_walk_text(item))
    return " ".join(parts).lower()


def _latest_market(core: Any, market: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(market or {})
    state = _portfolio(core)
    for source in (_d(state.get("last_market")), _d(_d(state.get("auto_runner")).get("last_result"))):
        for key, value in source.items():
            out.setdefault(key, value)
    return out


def _risk_on_confirmed(core: Any, market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    m = _latest_market(core, market)
    mode = str(m.get("market_mode") or m.get("regime") or "").lower()
    risk_score = _safe_float(m.get("risk_score"), 0.0)
    futures = _d(m.get("futures_bias"))
    futures_bias = str(futures.get("bias") or futures.get("action") or "").lower()
    risk_on_sector_count = _safe_int(m.get("risk_on_sector_count"), 0)
    growth_leadership = bool(m.get("growth_leadership") or m.get("tech_leadership") or m.get("risk_on_leadership"))
    broad_soft = bool(m.get("broad_market_soft"))
    defensive = bool(m.get("defensive_rotation"))
    bear = bool(m.get("bear_confirmed")) or mode in {"risk_off", "crash_warning", "defensive_rotation", "bear"}
    allowed = (
        mode in ALLOWED_MODES
        and not bear
        and not defensive
        and not broad_soft
        and (
            risk_score >= MIN_RISK_SCORE
            or growth_leadership
            or risk_on_sector_count >= 2
            or futures_bias in {"bullish", "risk_on", "constructive"}
        )
    )
    return allowed, {
        "reason": "risk_on_context_confirmed" if allowed else "risk_on_context_not_confirmed",
        "market_mode": mode,
        "risk_score": risk_score,
        "risk_on_sector_count": risk_on_sector_count,
        "growth_leadership": growth_leadership,
        "futures_bias": futures_bias,
        "broad_market_soft": broad_soft,
        "defensive_rotation": defensive,
        "bear_confirmed": bear,
    }


def _risk_ok(core: Any, market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    rc = _risk_controls(core)
    if not _paper_context():
        return False, {"reason": "not_paper_context"}
    if bool(rc.get("halted", False)):
        return False, {"reason": "risk_on_starter_risk_halted", "risk_controls": rc}
    if bool(rc.get("self_defense_active", False)):
        return False, {"reason": "risk_on_starter_self_defense_active", "risk_controls": rc}
    daily_loss = _safe_float(rc.get("daily_loss_pct"), 0.0)
    intraday_dd = _safe_float(rc.get("intraday_drawdown_pct"), 0.0)
    if daily_loss > MAX_DAILY_LOSS_PCT:
        return False, {"reason": "risk_on_starter_daily_loss_not_clean", "daily_loss_pct": daily_loss, "max_daily_loss_pct": MAX_DAILY_LOSS_PCT}
    if intraday_dd > MAX_INTRADAY_DRAWDOWN_PCT:
        return False, {"reason": "risk_on_starter_intraday_drawdown_too_high", "intraday_drawdown_pct": intraday_dd, "max_intraday_drawdown_pct": MAX_INTRADAY_DRAWDOWN_PCT}
    ok, info = _risk_on_confirmed(core, market)
    if not ok:
        return False, info
    return True, {"reason": "risk_on_starter_risk_clean", "risk_controls": rc, "market": info}


def _entries_today(core: Any) -> int:
    try:
        cep = __import__("core_entry_pipeline")
        fn = getattr(cep, "_entries_today_with_context")
        return int(fn(core, "risk_on_starter_participation"))
    except Exception:
        return 0


def _quality_block_allowed(signal: Dict[str, Any], quality_info: Any, base_info: Any) -> Tuple[bool, Dict[str, Any]]:
    text = _combined_text(signal, quality_info, base_info)
    hard_hits = [token for token in HARD_BLOCK_TOKENS if token and token in text]
    if hard_hits:
        return False, {"reason": "risk_on_starter_hard_block_present", "hard_block_tokens": hard_hits[:8]}
    allowed_hits = [token for token in ALLOWED_BLOCK_TOKENS if token and token in text]
    if not allowed_hits:
        return False, {"reason": "risk_on_starter_block_reason_not_allowed", "allowed_tokens": list(ALLOWED_BLOCK_TOKENS)[:12]}
    return True, {"reason": "risk_on_starter_block_reason_allowed", "matched_tokens": allowed_hits[:8]}


def _state_telemetry(core: Any = None) -> Dict[str, Any]:
    state = _state(core)
    telemetry = state.get("risk_on_starter_participation_valve") if isinstance(state, dict) else {}
    return telemetry if isinstance(telemetry, dict) else {}


def _persist_evaluation(core: Any, status: str, payload: Dict[str, Any]) -> None:
    global _LAST_STATUS
    payload = _json_safe(payload)
    now_text = _now(core)
    reason = payload.get("reason") if isinstance(payload, dict) else None
    row = {
        "generated_local": now_text,
        "version": VERSION,
        "status": status,
        "reason": reason,
        "symbol": payload.get("symbol"),
        "bucket": payload.get("bucket"),
        "side": payload.get("side"),
        "rank_index": payload.get("rank_index"),
        "score": payload.get("score"),
        "rank_score": payload.get("rank_score"),
        "cash_pct": payload.get("cash_pct"),
        "open_positions_count": payload.get("open_positions_count"),
        "quality_reason": payload.get("quality_reason"),
        "prior_reason": _d(payload.get("prior_participation_result")).get("reason"),
        "quality_block": payload.get("quality_block"),
        "risk": payload.get("risk"),
        "hard_block_tokens": payload.get("hard_block_tokens"),
        "matched_tokens": payload.get("matched_tokens") or _d(payload.get("quality_block")).get("matched_tokens"),
        "allowed_tokens": payload.get("allowed_tokens"),
    }
    row = _json_safe(row)
    latest = {"status": status, "updated_local": now_text, "latest": payload}
    _LAST_STATUS = latest

    state = _state(core)
    if not isinstance(state, dict):
        return
    telemetry = state.setdefault("risk_on_starter_participation_valve", {})
    if not isinstance(telemetry, dict):
        telemetry = {}
        state["risk_on_starter_participation_valve"] = telemetry
    telemetry["version"] = VERSION
    telemetry["enabled"] = bool(ENABLED)
    telemetry["patched"] = bool(_PATCHED)
    telemetry["updated_local"] = now_text
    telemetry["last_status"] = status
    telemetry["last_reason"] = reason
    telemetry["last_symbol"] = row.get("symbol")
    telemetry["last_bucket"] = row.get("bucket")
    telemetry["last_evaluation"] = row
    telemetry["last"] = latest
    telemetry["policy_snapshot"] = {
        "max_entries_per_day": MAX_ENTRIES_PER_DAY,
        "max_entries_per_cycle": MAX_ENTRIES_PER_CYCLE,
        "alloc_factor": ALLOC_FACTOR,
        "min_cash_pct": MIN_CASH_PCT,
        "min_raw_score": MIN_RAW_SCORE,
        "min_rank_score": MIN_RANK_SCORE,
        "min_risk_score": MIN_RISK_SCORE,
        "allowed_modes": sorted(ALLOWED_MODES),
        "preferred_buckets": sorted(PREFERRED_BUCKETS),
        "hard_block_tokens": list(HARD_BLOCK_TOKENS),
        "allowed_block_tokens": list(ALLOWED_BLOCK_TOKENS),
    }
    counters = telemetry.setdefault("counters", {})
    if isinstance(counters, dict):
        counters["evaluations_total"] = _safe_int(counters.get("evaluations_total"), 0) + 1
        counters[f"{status}_total"] = _safe_int(counters.get(f"{status}_total"), 0) + 1
    recent = telemetry.setdefault("recent_evaluations", [])
    if not isinstance(recent, list):
        recent = []
    recent.append(row)
    telemetry["recent_evaluations"] = recent[-max(1, TELEMETRY_MAX_ROWS):]
    _save_state(core, state)


def _latest_status(core: Any = None) -> Dict[str, Any]:
    if _LAST_STATUS:
        return dict(_LAST_STATUS)
    telemetry = _state_telemetry(core)
    if telemetry.get("last"):
        return _d(telemetry.get("last"))
    if telemetry.get("last_evaluation"):
        return {
            "status": telemetry.get("last_status"),
            "updated_local": telemetry.get("updated_local"),
            "latest": telemetry.get("last_evaluation"),
        }
    return {}


def _base_row(core: Any, signal: Dict[str, Any], quality_info: Any, rank_index: int, info: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(signal)
    score = _safe_float(signal.get("score"), 0.0)
    rank_score = _safe_float(signal.get("core_entry_rank_score"), score)
    return {
        "version": VERSION,
        "symbol": symbol,
        "side": _side(signal),
        "bucket": _bucket(core, symbol, signal),
        "rank_index": rank_index,
        "score": round(score, 6),
        "rank_score": round(rank_score, 6),
        "quality_reason": _quality_reason(quality_info),
        "cash_pct": _cash_pct(core),
        "open_positions_count": len(_positions(core)),
        "prior_participation_result": info,
    }


def _patched_participation_valve_ok(core: Any, signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any], quality_info: Any, rank_index: int, entries_this_cycle: int, valve_entries_this_cycle: int):
    original = _ORIGINAL_FN
    info: Dict[str, Any] = {"reason": "prior_participation_valve_missing"}
    if callable(original):
        ok, raw_info = original(core, signal, params, market, quality_info, rank_index, entries_this_cycle, valve_entries_this_cycle)
        info = raw_info if isinstance(raw_info, dict) else {"reason": str(raw_info)}
        if ok:
            payload = {
                **_base_row(core, signal, quality_info, rank_index, info),
                "reason": "prior_participation_valve_allowed",
                "prior_allowed": True,
            }
            _persist_evaluation(core, "passthrough_allowed", payload)
            return ok, info

    base = _base_row(core, signal, quality_info, rank_index, info)

    def blocked(reason: str, **extra: Any):
        payload = {**base, "reason": reason, **extra}
        _persist_evaluation(core, "blocked", payload)
        return False, payload

    if not ENABLED:
        return blocked("risk_on_starter_disabled")
    if base.get("side") != "long":
        return blocked("risk_on_starter_long_only")
    if rank_index > MAX_REVIEWED_RANK:
        return blocked("risk_on_starter_rank_too_low", max_rank=MAX_REVIEWED_RANK)
    if valve_entries_this_cycle >= MAX_ENTRIES_PER_CYCLE:
        return blocked("risk_on_starter_cycle_limit", max_entries_per_cycle=MAX_ENTRIES_PER_CYCLE)
    if _entries_today(core) >= MAX_ENTRIES_PER_DAY:
        return blocked("risk_on_starter_daily_limit", max_entries_per_day=MAX_ENTRIES_PER_DAY)
    if _safe_float(base.get("cash_pct"), 0.0) < MIN_CASH_PCT:
        return blocked("risk_on_starter_cash_not_high_enough", min_cash_pct=MIN_CASH_PCT)
    if len(_positions(core)) > MAX_OPEN_POSITIONS:
        return blocked("risk_on_starter_too_many_open_positions", max_open_positions=MAX_OPEN_POSITIONS)
    if _safe_float(base.get("score"), 0.0) < MIN_RAW_SCORE:
        return blocked("risk_on_starter_raw_score_too_low", min_raw_score=MIN_RAW_SCORE)
    if _safe_float(base.get("rank_score"), 0.0) < MIN_RANK_SCORE:
        return blocked("risk_on_starter_rank_score_too_low", min_rank_score=MIN_RANK_SCORE)
    if base.get("bucket") not in PREFERRED_BUCKETS and str(base.get("symbol") or "").upper() not in PREFERRED_SYMBOLS:
        return blocked("risk_on_starter_not_preferred_leadership_bucket_or_symbol", preferred_buckets=sorted(PREFERRED_BUCKETS))
    reason_ok, reason_info = _quality_block_allowed(signal, quality_info, info)
    if not reason_ok:
        return blocked(reason_info.get("reason", "risk_on_starter_reason_block"), **reason_info)
    risk_ok, risk_info = _risk_ok(core, market or {})
    if not risk_ok:
        return blocked(risk_info.get("reason", "risk_on_starter_risk_block"), **risk_info)

    try:
        cep = __import__("core_entry_pipeline")
        cep.PARTICIPATION_VALVE_ALLOC_FACTOR = min(float(getattr(cep, "PARTICIPATION_VALVE_ALLOC_FACTOR", 1.0)), ALLOC_FACTOR)
    except Exception:
        pass
    payload = {
        **base,
        "reason": "risk_on_starter_participation_ok",
        "alloc_factor": ALLOC_FACTOR,
        "risk": risk_info,
        "quality_block": reason_info,
        "paper_only": True,
        "authority_changed": False,
        "live_trade_authority": "none",
        "ml_authority": "paper_phase3a_guarded_advisory",
    }
    _persist_evaluation(core, "allowed", payload)
    return True, payload


def apply(core: Any = None) -> Dict[str, Any]:
    global _PATCHED, _ORIGINAL_FN
    if not ENABLED:
        return status_payload(core)
    try:
        import core_entry_pipeline as cep
        current = getattr(cep, "_participation_valve_ok", None)
        if getattr(current, "_risk_on_starter_participation_version", None) == VERSION:
            _PATCHED = True
        else:
            _ORIGINAL_FN = current
            _patched_participation_valve_ok._risk_on_starter_participation_version = VERSION  # type: ignore[attr-defined]
            cep._participation_valve_ok = _patched_participation_valve_ok
            _PATCHED = True
    except Exception as exc:
        _LAST_STATUS["apply_error"] = f"{type(exc).__name__}: {exc}"
    return status_payload(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def policy() -> Dict[str, Any]:
    return {
        "enabled": bool(ENABLED),
        "patch_target": "core_entry_pipeline._participation_valve_ok",
        "does_not_wrap_main_entry_loop": True,
        "does_not_place_trades_directly": True,
        "paper_only": True,
        "max_entries_per_day": MAX_ENTRIES_PER_DAY,
        "max_entries_per_cycle": MAX_ENTRIES_PER_CYCLE,
        "max_reviewed_rank": MAX_REVIEWED_RANK,
        "min_cash_pct": MIN_CASH_PCT,
        "max_open_positions": MAX_OPEN_POSITIONS,
        "min_raw_score": MIN_RAW_SCORE,
        "min_rank_score": MIN_RANK_SCORE,
        "alloc_factor": ALLOC_FACTOR,
        "min_risk_score": MIN_RISK_SCORE,
        "telemetry_max_rows": TELEMETRY_MAX_ROWS,
        "allowed_modes": sorted(ALLOWED_MODES),
        "preferred_buckets": sorted(PREFERRED_BUCKETS),
        "preferred_symbols_sample": sorted(PREFERRED_SYMBOLS)[:30],
        "allowed_block_tokens": list(ALLOWED_BLOCK_TOKENS),
        "hard_block_tokens": list(HARD_BLOCK_TOKENS),
        "does_not_bypass_cooldowns": True,
        "does_not_bypass_self_defense": True,
        "does_not_bypass_risk_halts": True,
        "does_not_change_live_authority": True,
        "does_not_change_ml_authority": True,
        "authority_changed": False,
        "live_trade_authority": "none",
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    telemetry = _state_telemetry(core)
    latest = _latest_status(core)
    return {
        "status": "ok",
        "overall": "pass",
        "type": "risk_on_starter_participation_valve_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "patched": bool(_PATCHED),
        "latest": latest,
        "state_telemetry": telemetry,
        "last_evaluation": telemetry.get("last_evaluation") or _d(latest.get("latest")),
        "last_status": telemetry.get("last_status") or latest.get("status"),
        "last_reason": telemetry.get("last_reason") or _d(latest.get("latest")).get("reason"),
        "recent_evaluations": telemetry.get("recent_evaluations") or [],
        "counters": telemetry.get("counters") or {},
        "telemetry_persisted": bool(telemetry),
        "policy": policy(),
    }


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

    if "/paper/risk-on-starter-participation-status" not in existing:
        flask_app.add_url_rule("/paper/risk-on-starter-participation-status", "risk_on_starter_participation_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
