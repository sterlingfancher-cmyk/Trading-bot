"""Bounded neutral-tape extension for the existing paper starter valve.

The existing risk-on starter already enforces candidate rank/score, preferred
leadership buckets, quality-block allowlists, clean risk, cash, position, cycle,
and daily limits. This extension changes only its market-context confirmation so
one 18%-factor starter can be considered during a broad, strong neutral tape after
the opening-surge window.

It does not wrap the main entry loop, place orders directly, change hard-risk
limits, enable live trading, or grant ML authority.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from typing import Any, Dict, Tuple

VERSION = "neutral-momentum-starter-extension-2026-08-03-v1"
ENABLED = os.environ.get("NEUTRAL_MOMENTUM_STARTER_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
START_MINUTES = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_START_MINUTES", "45"))
END_MINUTES = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_END_MINUTES", "180"))
MIN_RISK_SCORE = float(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MIN_RISK_SCORE", "40"))
MIN_SCANNER_SIGNALS = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MIN_SCANNER_SIGNALS", "15"))
MIN_LONG_SIGNALS = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MIN_LONG_SIGNALS", "4"))

_EXTRA_SYMBOLS = {
    "RGIT", "APLD", "MP", "NBIS", "AMZN", "META", "BTQ", "NVTS", "KEEL", "CIFR",
}
_EXTRA_BUCKETS = {
    "semi_leaders", "mega_cap_ai", "ai_cloud_breakout", "cloud_cyber_software",
    "data_center_infra", "bitcoin_ai_compute", "space_stocks", "small_cap_momentum",
    "memory_storage", "power_grid_data_center", "critical_materials", "industrial_growth",
}
_SECTORS = {
    "RGIT": "XLK", "APLD": "XLK", "MP": "XLB", "NBIS": "XLK", "AMZN": "XLY",
    "META": "XLC", "BTQ": "XLK", "NVTS": "XLK", "KEEL": "XLI", "CIFR": "XLK",
}
_BUCKETS = {
    "RGIT": "small_cap_momentum", "APLD": "data_center_infra", "MP": "critical_materials",
    "NBIS": "ai_cloud_breakout", "AMZN": "mega_cap_ai", "META": "mega_cap_ai",
    "BTQ": "bitcoin_ai_compute", "NVTS": "semi_leaders", "KEEL": "industrial_growth",
    "CIFR": "bitcoin_ai_compute",
}

_LOCK = threading.RLock()
_WATCHDOGS: set[int] = set()
_REGISTERED_APPS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _paper() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker


def _minutes(core: Any) -> Tuple[float, Dict[str, Any]]:
    try:
        clock = _d(core.market_clock())
    except Exception:
        clock = {}
    if clock.get("minutes_since_open") is not None:
        return max(0.0, _f(clock.get("minutes_since_open"))), clock
    try:
        current = core.now_local()
        opening = core.regular_open_datetime(current)
        return max(0.0, (current - opening).total_seconds() / 60.0), clock
    except Exception:
        return 9999.0, clock


def _state_counts(core: Any) -> Dict[str, int]:
    state = _d(getattr(core, "portfolio", {}))
    scanner = _d(state.get("scanner_audit"))
    decision = _d(state.get("decision_audit"))
    auto_result = _d(_d(state.get("auto_runner")).get("last_result"))
    signals = max(
        _i(scanner.get("signals_found")),
        _i(decision.get("signals_found")),
        _i(auto_result.get("signals_found")),
        _i(auto_result.get("scanner_signals_found")),
    )
    longs = max(
        _i(decision.get("long_signals_count")),
        _i(auto_result.get("long_signals_count")),
        len(auto_result.get("long_signals") or []) if isinstance(auto_result.get("long_signals"), list) else 0,
    )
    return {"signals_found": signals, "long_signals_count": longs}


def _extend_universe(core: Any, starter: Any) -> None:
    try:
        starter.PREFERRED_SYMBOLS.update(_EXTRA_SYMBOLS)
        starter.PREFERRED_BUCKETS.update(_EXTRA_BUCKETS)
    except Exception:
        pass
    try:
        universe = list(getattr(core, "UNIVERSE", []) or [])
        for symbol in sorted(_EXTRA_SYMBOLS):
            if symbol not in universe:
                universe.append(symbol)
        core.UNIVERSE = universe
    except Exception:
        pass
    try:
        sectors = getattr(core, "SYMBOL_SECTOR", {})
        buckets = getattr(core, "SYMBOL_BUCKET", {})
        for symbol, sector in _SECTORS.items():
            sectors.setdefault(symbol, sector)
        for symbol, bucket in _BUCKETS.items():
            buckets.setdefault(symbol, bucket)
    except Exception:
        pass


def _neutral_context(core: Any, market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    market = _d(market)
    mode = str(market.get("market_mode") or market.get("regime") or "").lower()
    minutes, clock = _minutes(core)
    counts = _state_counts(core)
    risk_score = _f(market.get("risk_score"))
    futures = _d(market.get("futures_bias"))
    breadth = _d(market.get("breadth"))
    futures_text = " ".join(
        str(futures.get(key) or "").lower() for key in ("bias", "action", "reason")
    )
    breadth_text = " ".join(
        str(breadth.get(key) or "").lower() for key in ("state", "action", "reason")
    )
    growth = bool(market.get("growth_leadership") or market.get("tech_leadership") or market.get("risk_on_leadership"))
    sector_count = _i(market.get("risk_on_sector_count"))
    positive_tape = bool(
        growth
        or sector_count >= 2
        or any(token in futures_text for token in ("bullish", "gap_chase_protection", "risk_on"))
        or any(token in breadth_text for token in ("supportive", "narrow_mega_cap_led", "reduce_aggression"))
    )

    reasons = []
    if not ENABLED:
        reasons.append("neutral_momentum_extension_disabled")
    if not _paper():
        reasons.append("not_paper_context")
    if mode != "neutral":
        reasons.append("market_mode_not_neutral")
    if not bool(clock.get("is_open", True)):
        reasons.append("market_closed")
    if minutes < START_MINUTES:
        reasons.append("before_neutral_momentum_window")
    if minutes > END_MINUTES:
        reasons.append("after_neutral_momentum_window")
    if bool(market.get("bear_confirmed")):
        reasons.append("bear_confirmed")
    if bool(market.get("defensive_rotation")):
        reasons.append("defensive_rotation")
    if risk_score < MIN_RISK_SCORE:
        reasons.append("risk_score_below_neutral_floor")
    if any(token in futures_text for token in ("bearish", "block_opening_longs", "mixed_bearish")):
        reasons.append("futures_not_supportive")
    if "risk_off_confirmation" in breadth_text:
        reasons.append("breadth_risk_off_confirmation")
    if counts["signals_found"] < MIN_SCANNER_SIGNALS:
        reasons.append("scanner_cluster_too_small")
    if counts["long_signals_count"] and counts["long_signals_count"] < MIN_LONG_SIGNALS:
        reasons.append("long_signal_cluster_too_small")
    if not positive_tape:
        reasons.append("positive_tape_not_confirmed")

    return not reasons, {
        "reason": "neutral_momentum_context_confirmed" if not reasons else "neutral_momentum_context_blocked",
        "reasons": reasons,
        "market_mode": mode,
        "minutes_since_open": round(minutes, 2),
        "window_start_minutes": START_MINUTES,
        "window_end_minutes": END_MINUTES,
        "risk_score": risk_score,
        "minimum_risk_score": MIN_RISK_SCORE,
        "signals_found": counts["signals_found"],
        "minimum_scanner_signals": MIN_SCANNER_SIGNALS,
        "long_signals_count": counts["long_signals_count"],
        "minimum_long_signals": MIN_LONG_SIGNALS,
        "growth_leadership": growth,
        "risk_on_sector_count": sector_count,
        "futures_bias": futures,
        "breadth": breadth,
        "positive_tape": positive_tape,
    }


def install(core: Any = None) -> Dict[str, Any]:
    global _LAST
    if core is None:
        try:
            import app as core
        except Exception:
            core = None
    if core is None:
        return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        try:
            import risk_on_starter_participation_valve as starter
        except Exception as exc:
            return {"status": "warn", "overall": "warn", "version": VERSION, "reason": f"starter_import_failed:{type(exc).__name__}:{exc}"}

        _extend_universe(core, starter)
        current = getattr(starter, "_risk_on_confirmed", None)
        if not callable(current):
            return {"status": "warn", "overall": "warn", "version": VERSION, "reason": "starter_context_function_missing"}

        active = getattr(current, "_neutral_momentum_starter_extension_version", None) == VERSION
        patched = False
        if not active:
            prior = getattr(current, "_neutral_momentum_starter_extension_prior", current)

            def extended_context(runtime: Any, market: Dict[str, Any], __prior=prior):
                global _LAST
                prior_ok, prior_info = __prior(runtime, market)
                if prior_ok:
                    _LAST = {
                        "generated_local": _now(runtime),
                        "status": "passthrough",
                        "reason": "existing_risk_on_or_constructive_context_allowed",
                        "prior": prior_info,
                    }
                    return prior_ok, prior_info
                neutral_ok, neutral_info = _neutral_context(runtime, market)
                _LAST = {
                    "generated_local": _now(runtime),
                    "status": "allowed" if neutral_ok else "blocked",
                    "reason": neutral_info.get("reason"),
                    "neutral": neutral_info,
                    "prior": prior_info,
                }
                return (True, neutral_info) if neutral_ok else (False, neutral_info)

            extended_context._neutral_momentum_starter_extension_version = VERSION
            extended_context._neutral_momentum_starter_extension_prior = prior
            extended_context.__wrapped__ = prior
            starter._risk_on_confirmed = extended_context
            patched = True

        active = getattr(getattr(starter, "_risk_on_confirmed", None), "_neutral_momentum_starter_extension_version", None) == VERSION
        setattr(core, "NEUTRAL_MOMENTUM_STARTER_EXTENSION_VERSION", VERSION)
        return {
            "status": "ok" if active else "warn",
            "overall": "pass" if active else "warn",
            "type": "neutral_momentum_starter_extension_status",
            "version": VERSION,
            "generated_local": _now(core),
            "active": active,
            "patched_this_call": patched,
            "last_evaluation": dict(_LAST),
            "settings": {
                "window_start_minutes": START_MINUTES,
                "window_end_minutes": END_MINUTES,
                "minimum_risk_score": MIN_RISK_SCORE,
                "minimum_scanner_signals": MIN_SCANNER_SIGNALS,
                "minimum_long_signals_when_available": MIN_LONG_SIGNALS,
                "existing_starter_alloc_factor": getattr(starter, "ALLOC_FACTOR", None),
                "existing_starter_max_entries_per_day": getattr(starter, "MAX_ENTRIES_PER_DAY", None),
                "existing_starter_min_raw_score": getattr(starter, "MIN_RAW_SCORE", None),
                "existing_starter_min_rank_score": getattr(starter, "MIN_RANK_SCORE", None),
                "extra_symbols": sorted(_EXTRA_SYMBOLS),
            },
            "authority": {
                "paper_only": True,
                "places_orders_directly": False,
                "patches_main_entry_loop": False,
                "changes_hard_risk_limits": False,
                "changes_live_authority": False,
                "changes_ml_authority": False,
                "changes_position_limits": False,
                "changes_existing_starter_sizing": False,
                "changes_market_context_permission": True,
                "bounded_neutral_starter_only": True,
            },
        }


def status_payload(core: Any = None) -> Dict[str, Any]:
    return install(core)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    install(core)
    if id(flask_app) in _REGISTERED_APPS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    path = "/paper/neutral-momentum-starter-status"
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if path not in existing:
        flask_app.add_url_rule(path, "neutral_momentum_starter_status", lambda: jsonify(status_payload(core)))
    _REGISTERED_APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [path]}


def start_watchdog(core: Any = None) -> Dict[str, Any]:
    install(core)
    if core is None or id(core) in _WATCHDOGS:
        return {"status": "ok", "version": VERSION, "watchdog_started": core is not None and id(core) in _WATCHDOGS}
    _WATCHDOGS.add(id(core))

    def watch() -> None:
        for iteration in range(1200):
            try:
                install(core)
            except Exception:
                pass
            time.sleep(0.5 if iteration < 60 else 30.0)

    threading.Thread(target=watch, daemon=True, name="neutral-momentum-starter-watchdog").start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}


try:
    import app as _core
    install(_core)
except Exception:
    pass
