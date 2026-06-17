"""Controlled theme-starter exception for paper entries.

Purpose:
- Speed up participation in confirmed momentum themes without broadly lowering the
  normal entry floor.
- Allow a tiny starter when a symbol is close below the normal entry threshold,
  theme/catalyst is confirmed, and the normal risk/exposure gates remain clean.

This module is paper-only by default. It does not grant live authority, does not
change ML authority, does not raise max positions, does not raise max entries per
cycle, and does not bypass self-defense/risk controls.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Tuple

VERSION = "theme-starter-exception-2026-06-17-v1"
ENABLED = os.environ.get("THEME_STARTER_EXCEPTION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("THEME_STARTER_EXCEPTION_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
STARTER_ALLOC_FACTOR = float(os.environ.get("THEME_STARTER_ALLOC_FACTOR", "0.30"))
MAX_PER_CYCLE = int(os.environ.get("THEME_STARTER_MAX_PER_CYCLE", "1"))
MIN_SCORE = float(os.environ.get("THEME_STARTER_MIN_SCORE", "0.013"))
MAX_SCORE_GAP = float(os.environ.get("THEME_STARTER_MAX_SCORE_GAP", "0.010"))
MAX_SCORE_GAP_PRECIOUS = float(os.environ.get("THEME_STARTER_MAX_SCORE_GAP_PRECIOUS", "0.0075"))

ALLOWED_BUCKETS = {
    item.strip()
    for item in os.environ.get(
        "THEME_STARTER_ALLOWED_BUCKETS",
        "space_stocks,bitcoin_ai_compute,semi_leaders,data_center_infra,small_cap_momentum,precious_metals",
    ).split(",")
    if item.strip()
}
ALLOWED_MARKET_MODES = {
    item.strip()
    for item in os.environ.get("THEME_STARTER_ALLOWED_MARKET_MODES", "risk_on,constructive").split(",")
    if item.strip()
}

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
_CYCLE_THEME_STARTERS_USED = 0


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


def _symbol(signal: Dict[str, Any]) -> str:
    return str(signal.get("symbol") or signal.get("ticker") or "").upper().strip()


def _side(signal: Dict[str, Any]) -> str:
    return str(signal.get("side") or "long").lower().strip() or "long"


def _bucket(core: Any, symbol: str, signal: Dict[str, Any]) -> str:
    raw = signal.get("bucket") or signal.get("symbol_bucket")
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


def _sector(core: Any, symbol: str, signal: Dict[str, Any]) -> str:
    raw = signal.get("sector")
    if raw:
        return str(raw)
    try:
        sector_map = getattr(core, "SYMBOL_SECTOR", {}) or {}
        if isinstance(sector_map, dict):
            return str(sector_map.get(symbol, "UNKNOWN"))
    except Exception:
        pass
    return "UNKNOWN"


def _risk_clean(core: Any) -> Tuple[bool, Dict[str, Any]]:
    try:
        fn = getattr(core, "get_risk_controls", None)
        rc = fn() if callable(fn) else (core.portfolio.get("risk_controls", {}) or {})
        rc = rc if isinstance(rc, dict) else {}
    except Exception:
        rc = {}
    if bool(rc.get("halted")):
        return False, {"reason": "risk_halt_active", "risk_controls": rc}
    if bool(rc.get("self_defense_active")):
        return False, {"reason": "self_defense_active", "risk_controls": rc}
    return True, {"reason": "risk_controls_clean", "risk_controls": rc}


def _theme_confirmed(signal: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    theme = signal.get("theme_confirmation") if isinstance(signal.get("theme_confirmation"), dict) else {}
    catalyst = signal.get("catalyst") if isinstance(signal.get("catalyst"), dict) else {}
    active = bool(theme.get("active") or catalyst.get("active"))
    reason = theme.get("reason") or catalyst.get("reason") or "theme_or_catalyst_not_confirmed"
    return active, {"theme_confirmation": theme, "catalyst": catalyst, "reason": reason}


def _quality_reason(info: Any) -> str:
    if isinstance(info, dict):
        if info.get("reason"):
            return str(info.get("reason"))
        controlled = info.get("controlled_pullback_info")
        if isinstance(controlled, dict) and controlled.get("reason"):
            return str(controlled.get("reason"))
    return str(info or "unknown")


def _normal_floor(core: Any, market: Dict[str, Any], side: str, fallback: float = 0.0) -> float:
    try:
        fn = getattr(core, "min_entry_score_for_market", None)
        if callable(fn):
            return _f(fn(market or {}, side), fallback)
    except Exception:
        pass
    return fallback


def _has_extension_warning(signal: Dict[str, Any], info: Dict[str, Any]) -> bool:
    text_bits = []
    for obj in (signal, info):
        if isinstance(obj, dict):
            for key in ("reason", "entry_context", "pullback_reclaim_status", "quality_reason"):
                if obj.get(key):
                    text_bits.append(str(obj.get(key)).lower())
    text = " ".join(text_bits)
    return any(token in text for token in ("extended_above", "too_close_to_intraday_high", "chase", "overstretched"))


def _exposure_ok(core: Any, signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    symbol = _symbol(signal)
    sector = _sector(core, symbol, signal)
    bucket = _bucket(core, symbol, signal)
    try:
        proposed_alloc = _f(getattr(core, "estimated_trade_allocation")(signal, params or {}), 0.0)
    except Exception:
        proposed_alloc = 0.0

    try:
        equity, sector_values, sector_counts = getattr(core, "portfolio_sector_stats")()
        sector_count = int((sector_counts or {}).get(sector, 0))
        max_sector_positions = int(getattr(core, "effective_max_positions_per_sector")(market or {}, sector))
        if sector not in {None, "", "UNKNOWN"} and sector_count >= max_sector_positions:
            return False, {"reason": "theme_starter_sector_position_limit", "sector": sector, "current_sector_positions": sector_count, "max_positions_per_sector": max_sector_positions}
        projected_sector_value = _f((sector_values or {}).get(sector), 0.0) + proposed_alloc
        equity = max(_f(equity, 0.0), 0.01)
        sector_cap = _f(getattr(core, "effective_sector_exposure_cap")(market or {}, sector), 1.0)
        if sector not in {None, "", "UNKNOWN"} and projected_sector_value / equity > sector_cap:
            return False, {"reason": "theme_starter_sector_exposure_cap", "sector": sector, "projected_sector_pct": round((projected_sector_value / equity) * 100, 2), "max_sector_exposure_pct": round(sector_cap * 100, 2)}
    except Exception:
        pass

    try:
        bucket_equity, bucket_values, bucket_counts = getattr(core, "portfolio_bucket_stats")()
        cfg_fn = getattr(core, "bucket_config", None)
        cfg = cfg_fn(bucket) if callable(cfg_fn) else {}
        cfg = cfg if isinstance(cfg, dict) else {}
        bucket_count = int((bucket_counts or {}).get(bucket, 0))
        max_bucket_positions = int(cfg.get("max_positions", 99))
        if bucket_count >= max_bucket_positions:
            return False, {"reason": "theme_starter_bucket_position_limit", "bucket": bucket, "current_bucket_positions": bucket_count, "max_bucket_positions": max_bucket_positions}
        projected_bucket_value = _f((bucket_values or {}).get(bucket), 0.0) + proposed_alloc
        bucket_equity = max(_f(bucket_equity, 0.0), 0.01)
        max_bucket_exposure = _f(cfg.get("max_exposure_pct"), 1.0)
        if projected_bucket_value / bucket_equity > max_bucket_exposure:
            return False, {"reason": "theme_starter_bucket_exposure_cap", "bucket": bucket, "projected_bucket_pct": round((projected_bucket_value / bucket_equity) * 100, 2), "max_bucket_exposure_pct": round(max_bucket_exposure * 100, 2)}
    except Exception:
        pass

    return True, {"reason": "theme_starter_exposure_ok", "sector": sector, "bucket": bucket, "proposed_alloc": round(proposed_alloc, 2)}


def _theme_starter_ok(core: Any, signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any], original_info: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if not (ENABLED and _paper_context()):
        return False, {"reason": "theme_starter_disabled_or_not_paper"}
    symbol = _symbol(signal)
    side = _side(signal)
    bucket = _bucket(core, symbol, signal)
    score = _f(signal.get("score"), 0.0)
    floor = _f(original_info.get("required_score"), 0.0) or _normal_floor(core, market, side, 0.0)
    market_mode = str((market or {}).get("market_mode") or "").lower()

    if side != "long":
        return False, {"reason": "theme_starter_long_only"}
    if not symbol:
        return False, {"reason": "theme_starter_missing_symbol"}
    if bucket not in ALLOWED_BUCKETS:
        return False, {"reason": "theme_starter_bucket_not_allowed", "bucket": bucket, "allowed_buckets": sorted(ALLOWED_BUCKETS)}
    if market_mode not in ALLOWED_MARKET_MODES:
        return False, {"reason": "theme_starter_market_mode_not_allowed", "market_mode": market_mode, "allowed_market_modes": sorted(ALLOWED_MARKET_MODES)}
    if score < MIN_SCORE:
        return False, {"reason": "theme_starter_score_below_minimum", "score": round(score, 6), "min_score": MIN_SCORE}
    if floor <= 0:
        return False, {"reason": "theme_starter_missing_entry_floor", "score": round(score, 6)}

    gap = max(0.0, floor - score)
    max_gap = MAX_SCORE_GAP_PRECIOUS if bucket == "precious_metals" else MAX_SCORE_GAP
    if gap > max_gap:
        return False, {"reason": "theme_starter_too_far_below_entry_floor", "score": round(score, 6), "required_score": round(floor, 6), "gap": round(gap, 6), "max_gap": max_gap}

    theme_ok, theme_info = _theme_confirmed(signal)
    if not theme_ok:
        return False, {"reason": "theme_starter_theme_not_confirmed", "theme": theme_info}
    if _has_extension_warning(signal, original_info):
        return False, {"reason": "theme_starter_extension_warning_block"}

    risk_ok, risk_info = _risk_clean(core)
    if not risk_ok:
        return False, risk_info

    exposure_ok, exposure_info = _exposure_ok(core, signal, params, market)
    if not exposure_ok:
        return False, exposure_info

    return True, {
        "reason": "theme_starter_exception_ok",
        "symbol": symbol,
        "score": round(score, 6),
        "required_score": round(floor, 6),
        "score_gap": round(gap, 6),
        "max_score_gap": max_gap,
        "bucket": bucket,
        "sector": _sector(core, symbol, signal),
        "market_mode": market_mode,
        "theme": theme_info,
        "risk_controls": risk_info,
        "exposure": exposure_info,
        "alloc_factor": STARTER_ALLOC_FACTOR,
        "max_per_cycle": MAX_PER_CYCLE,
        "version": VERSION,
    }


def _patch_entry_quality_check(core: Any) -> bool:
    current = getattr(core, "entry_quality_check", None)
    if not callable(current) or getattr(current, "_theme_starter_exception_patched", False):
        return False
    original = current

    def patched_entry_quality_check(signal, params, market, exclude_symbol=None):
        try:
            try:
                ok, info = original(signal, params, market, exclude_symbol=exclude_symbol)
            except TypeError:
                ok, info = original(signal, params, market)
            if ok:
                return ok, info
            info_dict = info if isinstance(info, dict) else {"reason": str(info)}
            if _quality_reason(info_dict) != "entry_score_below_minimum":
                return ok, info
            if not isinstance(signal, dict):
                return ok, info
            allowed, theme_info = _theme_starter_ok(core, signal, params or {}, market or {}, info_dict)
            if not allowed:
                return ok, info
            signal["entry_context"] = "theme_starter_exception"
            signal["trade_class"] = signal.get("trade_class") or "theme_starter"
            signal["alloc_factor"] = min(_f(signal.get("alloc_factor"), 1.0), STARTER_ALLOC_FACTOR)
            signal["theme_starter_exception"] = theme_info
            return True, theme_info
        except Exception:
            return original(signal, params, market)

    patched_entry_quality_check._theme_starter_exception_patched = True  # type: ignore[attr-defined]
    patched_entry_quality_check._theme_starter_exception_original = original  # type: ignore[attr-defined]
    core.entry_quality_check = patched_entry_quality_check
    return True


def _patch_enter_position(core: Any) -> bool:
    current = getattr(core, "enter_position", None)
    if not callable(current) or getattr(current, "_theme_starter_exception_entry_patched", False):
        return False
    original = current

    def patched_enter_position(signal, params, market_mode=None):
        global _CYCLE_THEME_STARTERS_USED
        try:
            marker = (signal or {}).get("theme_starter_exception") if isinstance(signal, dict) else None
            if isinstance(marker, dict):
                symbol = _symbol(signal)
                if _CYCLE_THEME_STARTERS_USED >= MAX_PER_CYCLE:
                    return {
                        "blocked": True,
                        "symbol": symbol,
                        "side": _side(signal),
                        "reason": "theme_starter_max_per_cycle",
                        "max_per_cycle": MAX_PER_CYCLE,
                        "version": VERSION,
                    }
                result = original(signal, params, market_mode=market_mode)
                if isinstance(result, dict) and not result.get("blocked"):
                    _CYCLE_THEME_STARTERS_USED += 1
                    result["theme_starter_exception"] = marker
                    try:
                        pos = (core.portfolio.get("positions", {}) or {}).get(symbol)
                        if isinstance(pos, dict):
                            pos["theme_starter_exception"] = marker
                            pos["entry_context"] = "theme_starter_exception"
                        for row in reversed((core.portfolio.get("trades", []) or [])[-10:]):
                            if isinstance(row, dict) and row.get("action") == "entry" and str(row.get("symbol", "")).upper() == symbol:
                                row["theme_starter_exception"] = marker
                                row["entry_context"] = "theme_starter_exception"
                                break
                    except Exception:
                        pass
                return result
        except Exception:
            pass
        return original(signal, params, market_mode=market_mode)

    patched_enter_position._theme_starter_exception_entry_patched = True  # type: ignore[attr-defined]
    patched_enter_position._theme_starter_exception_entry_original = original  # type: ignore[attr-defined]
    core.enter_position = patched_enter_position
    return True


def _patch_try_entries(core: Any) -> bool:
    current = getattr(core, "try_entries_and_rotations", None)
    if not callable(current) or getattr(current, "_theme_starter_exception_cycle_patched", False):
        return False
    original = current

    def patched_try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        global _CYCLE_THEME_STARTERS_USED
        _CYCLE_THEME_STARTERS_USED = 0
        return original(long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

    patched_try_entries_and_rotations._theme_starter_exception_cycle_patched = True  # type: ignore[attr-defined]
    patched_try_entries_and_rotations._theme_starter_exception_cycle_original = original  # type: ignore[attr-defined]
    core.try_entries_and_rotations = patched_try_entries_and_rotations
    return True


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    eq = getattr(core, "entry_quality_check", None) if core is not None else None
    ep = getattr(core, "enter_position", None) if core is not None else None
    te = getattr(core, "try_entries_and_rotations", None) if core is not None else None
    latest = {}
    try:
        latest = (core.portfolio.get("theme_starter_exception") or {}) if core is not None else {}
    except Exception:
        latest = {}
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "theme_starter_exception_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "paper_context": bool(_paper_context()),
        "patched_entry_quality_check": bool(getattr(eq, "_theme_starter_exception_patched", False)),
        "patched_enter_position": bool(getattr(ep, "_theme_starter_exception_entry_patched", False)),
        "patched_try_entries": bool(getattr(te, "_theme_starter_exception_cycle_patched", False)),
        "theme_starters_used_this_cycle": _CYCLE_THEME_STARTERS_USED,
        "latest": latest,
        "policy": {
            "allowed_buckets": sorted(ALLOWED_BUCKETS),
            "allowed_market_modes": sorted(ALLOWED_MARKET_MODES),
            "min_score": MIN_SCORE,
            "max_score_gap": MAX_SCORE_GAP,
            "max_score_gap_precious": MAX_SCORE_GAP_PRECIOUS,
            "starter_alloc_factor": STARTER_ALLOC_FACTOR,
            "max_per_cycle": MAX_PER_CYCLE,
            "does_not_raise_max_positions": True,
            "does_not_raise_max_entries_per_cycle": True,
            "does_not_bypass_risk_controls": True,
            "does_not_bypass_self_defense": True,
            "does_not_bypass_exposure_caps": True,
            "does_not_bypass_cooldown": True,
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
    patched_try = _patch_try_entries(core)
    try:
        core.portfolio["theme_starter_exception"] = {
            "version": VERSION,
            "enabled": bool(ENABLED),
            "paper_context": bool(_paper_context()),
            "last_apply_local": _now(core),
            "authority_changed": False,
            "ml_authority": "shadow_only",
            "live_trade_authority": "none",
        }
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(core))
    payload = status_payload(core)
    payload["patched_this_call"] = {
        "entry_quality_check": bool(patched_quality),
        "enter_position": bool(patched_entry),
        "try_entries_and_rotations": bool(patched_try),
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
    if "/paper/theme-starter-exception-status" not in existing:
        flask_app.add_url_rule(
            "/paper/theme-starter-exception-status",
            "theme_starter_exception_status",
            lambda: jsonify(apply(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
