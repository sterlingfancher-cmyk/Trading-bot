"""Regime-flip entry and exposure guard.

Purpose:
- Prevent the bot from adding fresh long exposure when surface momentum is green
  but futures/regime are deteriorating.
- Reduce clustered ETF/leader losses by blocking risky fresh entries earlier and
  trimming the most vulnerable paper positions when futures flip hostile before
  the core market mode fully changes to risk_off.

This is a paper-only protection layer by default. It does not grant live trade
authority, does not change ML authority, does not raise max positions, and does
not lower entry thresholds.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Tuple

VERSION = "regime-flip-entry-guard-2026-06-17-v1"
ENABLED = os.environ.get("REGIME_FLIP_ENTRY_GUARD_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("REGIME_FLIP_ENTRY_GUARD_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
PREEMPTIVE_TRIM_ENABLED = os.environ.get("REGIME_FLIP_PREEMPTIVE_TRIM_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PREEMPTIVE_TRIM_FRACTION = float(os.environ.get("REGIME_FLIP_PREEMPTIVE_TRIM_FRACTION", "0.50"))
BENCHMARK_ETF_CAP_PCT = float(os.environ.get("REGIME_FLIP_BENCHMARK_ETF_CAP_PCT", "0.40"))
OVEREXTENDED_DAILY_PCT = float(os.environ.get("REGIME_FLIP_OVEREXTENDED_DAILY_PCT", "15.0"))
STARTER_MAX_ALLOC_FACTOR = float(os.environ.get("REGIME_FLIP_STARTER_MAX_ALLOC_FACTOR", "0.35"))

BENCHMARK_ETFS = {
    item.strip().upper()
    for item in os.environ.get("REGIME_FLIP_BENCHMARK_ETFS", "SPY,QQQ,IWM,SMH,DIA,RSP,ARKK").split(",")
    if item.strip()
}
HOSTILE_FUTURES_ACTIONS = {"block_opening_longs", "reduce_aggression", "tech_caution", "gap_chase_protection"}
HARD_BLOCK_FUTURES_ACTIONS = {"block_opening_longs"}
HOSTILE_MARKET_MODES = {"risk_off", "crash_warning", "defensive_rotation"}

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "entry_quality_check"):
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


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _symbol(signal_or_symbol: Any) -> str:
    if isinstance(signal_or_symbol, dict):
        value = signal_or_symbol.get("symbol") or signal_or_symbol.get("ticker") or ""
    else:
        value = signal_or_symbol
    return str(value or "").upper().strip()


def _side(signal: Dict[str, Any]) -> str:
    return str(signal.get("side") or "long").lower().strip() or "long"


def _bucket(core: Any, symbol: str, signal: Dict[str, Any] | None = None, pos: Dict[str, Any] | None = None) -> str:
    signal = signal or {}
    pos = pos or {}
    raw = signal.get("bucket") or signal.get("symbol_bucket") or pos.get("bucket")
    if raw:
        return str(raw)
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


def _sector(core: Any, symbol: str, signal: Dict[str, Any] | None = None, pos: Dict[str, Any] | None = None) -> str:
    signal = signal or {}
    pos = pos or {}
    raw = signal.get("sector") or pos.get("sector")
    if raw:
        return str(raw)
    try:
        sector_map = getattr(core, "SYMBOL_SECTOR", {}) or {}
        if isinstance(sector_map, dict):
            return str(sector_map.get(symbol, "UNKNOWN"))
    except Exception:
        pass
    return "UNKNOWN"


def _market(core: Any, market: Dict[str, Any] | None = None, market_mode: str | None = None) -> Dict[str, Any]:
    out = dict(market or {})
    if not out:
        try:
            out = dict(core.portfolio.get("last_market") or {})
        except Exception:
            out = {}
    if market_mode and not out.get("market_mode"):
        out["market_mode"] = market_mode
    return out


def _futures(market: Dict[str, Any]) -> Dict[str, Any]:
    value = market.get("futures_bias") or {}
    return value if isinstance(value, dict) else {}


def _extension_guard(market: Dict[str, Any]) -> Dict[str, Any]:
    value = market.get("market_extension_guard") or {}
    return value if isinstance(value, dict) else {}


def _is_benchmark_etf(core: Any, symbol: str, signal: Dict[str, Any] | None = None, pos: Dict[str, Any] | None = None) -> bool:
    bucket = _bucket(core, symbol, signal, pos)
    return bool(symbol in BENCHMARK_ETFS or bucket == "benchmark_etf")


def _multi_timeframe(signal: Dict[str, Any] | None = None, pos: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signal = signal or {}
    pos = pos or {}
    value = signal.get("multi_timeframe") or pos.get("multi_timeframe") or {}
    return value if isinstance(value, dict) else {}


def _is_overextended(signal: Dict[str, Any] | None = None, pos: Dict[str, Any] | None = None) -> Tuple[bool, Dict[str, Any]]:
    mtf = _multi_timeframe(signal, pos)
    if not mtf:
        return False, {"reason": "no_multi_timeframe_context"}
    extended_pct = _f(mtf.get("extended_from_20dma_pct"), 0.0)
    overextended = bool(mtf.get("overextended")) or extended_pct >= OVEREXTENDED_DAILY_PCT
    return overextended, {
        "reason": "multi_timeframe_overextended" if overextended else "multi_timeframe_not_overextended",
        "overextended": bool(overextended),
        "extended_from_20dma_pct": round(extended_pct, 2),
        "threshold_pct": OVEREXTENDED_DAILY_PCT,
        "classification": mtf.get("classification"),
    }


def _is_starter_or_reclaim(signal: Dict[str, Any]) -> bool:
    context = str(signal.get("entry_context") or "").lower()
    trade_class = str(signal.get("trade_class") or "").lower()
    alloc_factor = _f(signal.get("alloc_factor"), 1.0)
    if "pullback" in context or "reclaim" in context:
        return True
    if "theme_starter" in context or "theme_starter" in trade_class:
        return alloc_factor <= STARTER_MAX_ALLOC_FACTOR
    if bool(signal.get("theme_starter_exception")):
        return alloc_factor <= STARTER_MAX_ALLOC_FACTOR
    return False


def _hostile_futures(market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    futures = _futures(market)
    action = str(futures.get("action") or "").lower()
    bias = str(futures.get("bias") or "").lower()
    nq_trend = str(futures.get("nq_trend") or "").lower()
    es_trend = str(futures.get("es_trend") or "").lower()
    hard_block = action in HARD_BLOCK_FUTURES_ACTIONS
    hostile = bool(hard_block or action in HOSTILE_FUTURES_ACTIONS or bias in {"bearish", "mixed_bearish"} or nq_trend == "down" or es_trend == "down")
    return hostile, {
        "reason": "futures_hostile" if hostile else "futures_not_hostile",
        "hard_block": bool(hard_block),
        "action": action,
        "bias": bias,
        "nq_trend": nq_trend,
        "es_trend": es_trend,
        "raw": futures,
    }


def _regime_hostile(market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    mode = str(market.get("market_mode") or "").lower()
    bear_confirmed = bool(market.get("bear_confirmed"))
    hostile = bool(bear_confirmed or mode in HOSTILE_MARKET_MODES)
    return hostile, {"reason": "regime_hostile" if hostile else "regime_not_hostile", "market_mode": mode, "bear_confirmed": bear_confirmed}


def _benchmark_exposure_ok(core: Any, symbol: str, signal: Dict[str, Any], params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if not _is_benchmark_etf(core, symbol, signal):
        return True, {"reason": "not_benchmark_etf"}
    try:
        bucket_equity, bucket_values, _bucket_counts = getattr(core, "portfolio_bucket_stats")()
        proposed_alloc = _f(getattr(core, "estimated_trade_allocation")(signal, params or {}), 0.0)
        bucket_equity = max(_f(bucket_equity, 0.0), 0.01)
        current_value = _f((bucket_values or {}).get("benchmark_etf"), 0.0)
        projected_pct = (current_value + proposed_alloc) / bucket_equity
        if projected_pct > BENCHMARK_ETF_CAP_PCT:
            return False, {
                "reason": "benchmark_etf_regime_cap",
                "current_benchmark_etf_pct": round((current_value / bucket_equity) * 100, 2),
                "projected_benchmark_etf_pct": round(projected_pct * 100, 2),
                "cap_pct": round(BENCHMARK_ETF_CAP_PCT * 100, 2),
                "proposed_alloc": round(proposed_alloc, 2),
            }
    except Exception:
        pass
    return True, {"reason": "benchmark_etf_cap_ok"}


def _entry_guard(core: Any, signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if not (ENABLED and _paper_context()):
        return True, {"reason": "regime_flip_guard_disabled_or_not_paper"}
    if not isinstance(signal, dict):
        return True, {"reason": "not_a_signal"}
    symbol = _symbol(signal)
    side = _side(signal)
    if side != "long":
        return True, {"reason": "shorts_not_guarded_here"}

    market = _market(core, market)
    bucket = _bucket(core, symbol, signal)
    sector = _sector(core, symbol, signal)
    hostile_regime, regime_info = _regime_hostile(market)
    hostile_fut, futures_info = _hostile_futures(market)
    ext = _extension_guard(market)
    ext_action = str(ext.get("action") or "").lower()
    benchmark = _is_benchmark_etf(core, symbol, signal)
    overextended, overextended_info = _is_overextended(signal, None)

    if hostile_regime:
        return False, {
            "reason": "regime_flip_block_fresh_long",
            "symbol": symbol,
            "bucket": bucket,
            "sector": sector,
            "regime": regime_info,
            "futures": futures_info,
            "version": VERSION,
        }

    if futures_info.get("hard_block"):
        return False, {
            "reason": "futures_block_opening_longs_guard",
            "symbol": symbol,
            "bucket": bucket,
            "sector": sector,
            "regime": regime_info,
            "futures": futures_info,
            "version": VERSION,
        }

    if benchmark and hostile_fut:
        return False, {
            "reason": "benchmark_etf_futures_hostile_block",
            "symbol": symbol,
            "bucket": bucket,
            "sector": sector,
            "regime": regime_info,
            "futures": futures_info,
            "version": VERSION,
        }

    if benchmark and ext_action in {"reduce_aggression", "gap_chase_protection", "block_chase_longs"}:
        return False, {
            "reason": "benchmark_etf_market_extension_block",
            "symbol": symbol,
            "bucket": bucket,
            "sector": sector,
            "market_extension_guard": ext,
            "version": VERSION,
        }

    cap_ok, cap_info = _benchmark_exposure_ok(core, symbol, signal, params)
    if not cap_ok:
        return False, {"symbol": symbol, "bucket": bucket, "sector": sector, **cap_info, "version": VERSION}

    if overextended and not _is_starter_or_reclaim(signal):
        return False, {
            "reason": "overextended_leader_requires_starter_or_pullback_reclaim",
            "symbol": symbol,
            "bucket": bucket,
            "sector": sector,
            "overextended": overextended_info,
            "alloc_factor": _f(signal.get("alloc_factor"), 1.0),
            "starter_max_alloc_factor": STARTER_MAX_ALLOC_FACTOR,
            "entry_context": signal.get("entry_context"),
            "trade_class": signal.get("trade_class"),
            "version": VERSION,
        }

    return True, {
        "reason": "regime_flip_entry_guard_ok",
        "symbol": symbol,
        "bucket": bucket,
        "sector": sector,
        "regime": regime_info,
        "futures": futures_info,
        "market_extension_guard": ext,
        "overextended": overextended_info,
        "version": VERSION,
    }


def _patch_entry_quality_check(core: Any) -> bool:
    current = getattr(core, "entry_quality_check", None)
    if not callable(current) or getattr(current, "_regime_flip_entry_guard_patched", False):
        return False
    original = current

    def patched_entry_quality_check(signal, params, market, exclude_symbol=None):
        try:
            try:
                ok, info = original(signal, params, market, exclude_symbol=exclude_symbol)
            except TypeError:
                ok, info = original(signal, params, market)
            if not ok:
                return ok, info
            guard_ok, guard_info = _entry_guard(core, signal if isinstance(signal, dict) else {}, params or {}, market or {})
            if guard_ok:
                if isinstance(info, dict):
                    info.setdefault("regime_flip_entry_guard", guard_info)
                return ok, info
            return False, guard_info
        except Exception:
            return original(signal, params, market)

    patched_entry_quality_check._regime_flip_entry_guard_patched = True  # type: ignore[attr-defined]
    patched_entry_quality_check._regime_flip_entry_guard_original = original  # type: ignore[attr-defined]
    core.entry_quality_check = patched_entry_quality_check
    return True


def _patch_enter_position(core: Any) -> bool:
    current = getattr(core, "enter_position", None)
    if not callable(current) or getattr(current, "_regime_flip_entry_guard_entry_patched", False):
        return False
    original = current

    def patched_enter_position(signal, params, market_mode=None):
        try:
            market = _market(core, None, market_mode=market_mode)
            guard_ok, guard_info = _entry_guard(core, signal if isinstance(signal, dict) else {}, params or {}, market)
            if not guard_ok:
                return {
                    "blocked": True,
                    "symbol": _symbol(signal or {}),
                    "side": _side(signal or {}),
                    "reason": guard_info.get("reason", "regime_flip_entry_guard_block"),
                    "regime_flip_entry_guard": guard_info,
                }
            result = original(signal, params, market_mode=market_mode)
            if isinstance(result, dict) and not result.get("blocked"):
                result["regime_flip_entry_guard"] = guard_info
                try:
                    sym = _symbol(signal or result)
                    pos = (core.portfolio.get("positions", {}) or {}).get(sym)
                    if isinstance(pos, dict):
                        pos["regime_flip_entry_guard"] = guard_info
                    for row in reversed((core.portfolio.get("trades", []) or [])[-10:]):
                        if isinstance(row, dict) and row.get("action") == "entry" and _symbol(row) == sym:
                            row["regime_flip_entry_guard"] = guard_info
                            break
                except Exception:
                    pass
            return result
        except Exception:
            return original(signal, params, market_mode=market_mode)

    patched_enter_position._regime_flip_entry_guard_entry_patched = True  # type: ignore[attr-defined]
    patched_enter_position._regime_flip_entry_guard_entry_original = original  # type: ignore[attr-defined]
    core.enter_position = patched_enter_position
    return True


def _trim_reason_for_position(core: Any, symbol: str, pos: Dict[str, Any], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if not (ENABLED and PREEMPTIVE_TRIM_ENABLED and _paper_context()):
        return False, {"reason": "trim_disabled"}
    if str(pos.get("side", "long")).lower() != "long":
        return False, {"reason": "not_long"}
    hostile_regime, regime_info = _regime_hostile(market)
    hostile_fut, futures_info = _hostile_futures(market)
    # Full risk-off exits are already handled by core manage_exits. This trim is for
    # the earlier warning phase while the book may still appear risk_on/constructive.
    if hostile_regime:
        return False, {"reason": "core_market_regime_protection_handles_full_exit", "regime": regime_info}
    if not hostile_fut:
        return False, {"reason": "futures_not_hostile", "futures": futures_info}
    benchmark = _is_benchmark_etf(core, symbol, None, pos)
    overextended, overextended_info = _is_overextended(None, pos)
    if not (benchmark or overextended):
        return False, {"reason": "not_vulnerable_benchmark_or_overextended", "futures": futures_info}
    if bool(pos.get("regime_flip_preemptive_trim_taken")):
        return False, {"reason": "preemptive_trim_already_taken"}
    return True, {
        "reason": "regime_flip_preemptive_trim",
        "symbol": symbol,
        "benchmark_etf": bool(benchmark),
        "overextended": overextended_info,
        "futures": futures_info,
        "regime": regime_info,
        "trim_fraction": PREEMPTIVE_TRIM_FRACTION,
        "version": VERSION,
    }


def _patch_manage_exits(core: Any) -> bool:
    current = getattr(core, "manage_exits", None)
    if not callable(current) or getattr(current, "_regime_flip_entry_guard_exits_patched", False):
        return False
    original = current

    def patched_manage_exits(params, market):
        preemptive = []
        market_dict = _market(core, market)
        try:
            for symbol, pos in list((core.portfolio.get("positions", {}) or {}).items()):
                if not isinstance(pos, dict):
                    continue
                should_trim, trim_info = _trim_reason_for_position(core, str(symbol).upper(), pos, market_dict)
                if not should_trim:
                    continue
                px = None
                try:
                    px = getattr(core, "latest_price")(str(symbol).upper())
                except Exception:
                    px = None
                if px is None:
                    px = _f(pos.get("last_price") or pos.get("entry"), 0.0)
                if px <= 0:
                    continue
                try:
                    reducer = getattr(core, "reduce_position", None)
                    if callable(reducer):
                        result = reducer(
                            str(symbol).upper(),
                            float(px),
                            PREEMPTIVE_TRIM_FRACTION,
                            "regime_flip_preemptive_trim",
                            market_mode=market_dict.get("market_mode"),
                            extra={"regime_flip_entry_guard": trim_info},
                        )
                        if result:
                            pos["regime_flip_preemptive_trim_taken"] = True
                            pos["regime_flip_entry_guard"] = trim_info
                            preemptive.append(result)
                except Exception:
                    pass
        except Exception:
            pass
        exits = original(params, market)
        try:
            if preemptive:
                core.portfolio["regime_flip_entry_guard_latest"] = {
                    "status": "preemptive_trim_applied",
                    "generated_local": _now(core),
                    "preemptive_trims": preemptive[:10],
                    "market_mode": market_dict.get("market_mode"),
                    "version": VERSION,
                    "authority_changed": False,
                }
        except Exception:
            pass
        return list(preemptive) + list(exits or [])

    patched_manage_exits._regime_flip_entry_guard_exits_patched = True  # type: ignore[attr-defined]
    patched_manage_exits._regime_flip_entry_guard_exits_original = original  # type: ignore[attr-defined]
    core.manage_exits = patched_manage_exits
    return True


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    eq = getattr(core, "entry_quality_check", None) if core is not None else None
    ep = getattr(core, "enter_position", None) if core is not None else None
    me = getattr(core, "manage_exits", None) if core is not None else None
    latest = {}
    try:
        latest = (core.portfolio.get("regime_flip_entry_guard_latest") or {}) if core is not None else {}
    except Exception:
        latest = {}
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "regime_flip_entry_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "paper_context": bool(_paper_context()),
        "patched_entry_quality_check": bool(getattr(eq, "_regime_flip_entry_guard_patched", False)),
        "patched_enter_position": bool(getattr(ep, "_regime_flip_entry_guard_entry_patched", False)),
        "patched_manage_exits": bool(getattr(me, "_regime_flip_entry_guard_exits_patched", False)),
        "latest": latest,
        "policy": {
            "benchmark_etfs": sorted(BENCHMARK_ETFS),
            "benchmark_etf_cap_pct": round(BENCHMARK_ETF_CAP_PCT * 100, 2),
            "hostile_futures_actions": sorted(HOSTILE_FUTURES_ACTIONS),
            "hard_block_futures_actions": sorted(HARD_BLOCK_FUTURES_ACTIONS),
            "hostile_market_modes": sorted(HOSTILE_MARKET_MODES),
            "overextended_daily_pct": OVEREXTENDED_DAILY_PCT,
            "starter_max_alloc_factor": STARTER_MAX_ALLOC_FACTOR,
            "preemptive_trim_enabled": bool(PREEMPTIVE_TRIM_ENABLED),
            "preemptive_trim_fraction": PREEMPTIVE_TRIM_FRACTION,
            "does_not_raise_max_positions": True,
            "does_not_raise_max_entries_per_cycle": True,
            "does_not_lower_score_thresholds": True,
            "blocks_fresh_longs_in_hostile_regime": True,
            "blocks_benchmark_etf_entries_when_futures_hostile": True,
            "requires_starter_or_reclaim_for_overextended_leaders": True,
            "paper_only_by_default": True,
            "live_trade_authority": "none",
            "ml_authority": "shadow_only",
            "authority_changed": False,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return status_payload(core)
    patched_quality = _patch_entry_quality_check(core)
    patched_entry = _patch_enter_position(core)
    patched_exits = _patch_manage_exits(core)
    PATCHED_MODULE_IDS.add(id(core))
    payload = status_payload(core)
    payload["patched_this_call"] = {
        "entry_quality_check": bool(patched_quality),
        "enter_position": bool(patched_entry),
        "manage_exits": bool(patched_exits),
    }
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
    if "/paper/regime-flip-entry-guard-status" not in existing:
        flask_app.add_url_rule(
            "/paper/regime-flip-entry-guard-status",
            "regime_flip_entry_guard_status",
            lambda: jsonify(apply(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
