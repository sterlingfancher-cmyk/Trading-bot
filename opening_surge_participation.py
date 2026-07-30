"""Bounded paper-only opening-surge participation valve.

Allows one reduced-size opening-range breakout long when a defensive macro label
conflicts with a strongly bullish NQ open and a cluster of individual leaders.
It never permits longs during confirmed bear conditions and does not bypass the
core quality, timing, cooldown, stop, or hard-risk controls.

Version 2 makes scanner/risk ownership chain-aware. Metadata and diagnostic
wrappers may remain outside this valve without causing false displacement
warnings or repeated rewrapping.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import threading
import time
from typing import Any, Dict, List, Tuple

import numpy as np

VERSION = "opening-surge-participation-2026-07-30-v2-chain-aware"
ENABLED = os.getenv("OPENING_SURGE_PARTICIPATION_ENABLED", "true").lower() not in {
    "0", "false", "no", "off"
}
START_MIN = int(os.getenv("OPENING_SURGE_START_MINUTES_AFTER_OPEN", "15"))
END_MIN = int(os.getenv("OPENING_SURGE_END_MINUTES_AFTER_OPEN", "45"))
MAX_DAILY = int(os.getenv("OPENING_SURGE_MAX_ENTRIES_PER_DAY", "1"))
MAX_CANDIDATES = int(os.getenv("OPENING_SURGE_MAX_CANDIDATES_PER_CYCLE", "3"))
MIN_CLUSTER = int(os.getenv("OPENING_SURGE_MIN_CLUSTER_CANDIDATES", "2"))
MIN_SCORE = float(os.getenv("OPENING_SURGE_MIN_SCORE", "0.045"))
MIN_DAY_MOVE = float(os.getenv("OPENING_SURGE_MIN_DAY_MOVE", "0.080"))
MAX_DAY_MOVE = float(os.getenv("OPENING_SURGE_MAX_DAY_MOVE", "0.200"))
MIN_SESSION_MOVE = float(os.getenv("OPENING_SURGE_MIN_SESSION_MOVE", "0.040"))
MAX_SESSION_MOVE = float(os.getenv("OPENING_SURGE_MAX_SESSION_MOVE", "0.080"))
MIN_RANGE_BREAK = float(os.getenv("OPENING_SURGE_MIN_OPENING_RANGE_BREAK", "0.002"))
NEAR_HIGH = float(os.getenv("OPENING_SURGE_NEAR_SESSION_HIGH_FACTOR", "0.985"))
MIN_RVOL = float(os.getenv("OPENING_SURGE_MIN_RELATIVE_VOLUME", "1.25"))
STRONG_MOVE_RVOL_EXCEPTION = float(
    os.getenv("OPENING_SURGE_STRONG_MOVE_VOLUME_EXCEPTION", "0.080")
)
MIN_NQ_PCT = float(os.getenv("OPENING_SURGE_MIN_NQ_FUTURES_PCT", "0.80"))
MAX_LONG_ALLOC = float(os.getenv("OPENING_SURGE_MAX_LONG_ALLOC_PCT", "0.05"))
MAX_SIGNAL_FACTOR = float(
    os.getenv("OPENING_SURGE_MAX_SIGNAL_ALLOC_FACTOR", "1.00")
)
MAX_LOSS = float(os.getenv("OPENING_SURGE_MAX_DAILY_LOSS_FRACTION", "0.005"))
MODES = {
    item.strip()
    for item in os.getenv(
        "OPENING_SURGE_ALLOWED_MARKET_MODES", "crash_warning,risk_off"
    ).split(",")
    if item.strip()
}
BUCKETS = {
    item.strip()
    for item in os.getenv(
        "OPENING_SURGE_ALLOWED_BUCKETS",
        "semi_leaders,mega_cap_ai,ai_cloud_breakout,data_center_infra,"
        "bitcoin_ai_compute,power_grid_data_center,small_cap_momentum,"
        "cloud_cyber_software,space_stocks,dynamic_discovery",
    ).split(",")
    if item.strip()
}
EXTRA = [
    item.strip().upper()
    for item in os.getenv(
        "OPENING_SURGE_EXTRA_SYMBOLS",
        "WDC,CORZ,CRWV,LRCX,NBIS,SNDK,RIOT,AMD,BE,PWR",
    ).split(",")
    if item.strip()
]

_LOCK = threading.RLock()
_WATCHDOG: set[int] = set()
_APPS: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}
_LAST_PERMISSION: Dict[str, Any] = {}
_LAST_SCAN: Dict[str, Any] = {}

_LINK_NAME_TOKENS = ("original", "prior", "wrapped", "base", "inner")
_KNOWN_LINK_ATTRS = (
    "_opening_surge_scan_prior",
    "_opening_surge_risk_prior",
    "_opening_surge_prior",
    "_breakout_original",
    "_shared_cycle_identity_original",
    "_scanner_v2_lifecycle_trace_original",
    "_dynamic_universe_builder_original",
    "_relative_strength_original",
    "_pattern_recognition_original",
    "_market_participation_original",
    "_loss_streak_original",
    "__wrapped__",
)


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return default if math.isnan(number) or math.isinf(number) else number
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    try:
        return str(core.today_key())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _state(core: Any) -> Dict[str, Any]:
    return _d(getattr(core, "portfolio", {}))


def _paper() -> bool:
    live = os.getenv("LIVE_TRADING_ENABLED", "false").lower() in {
        "1", "true", "yes", "on"
    }
    broker_live = os.getenv("BROKER_MODE", "").lower() in {
        "live", "real", "production"
    }
    return not live and not broker_live


def _clock(core: Any) -> Dict[str, Any]:
    try:
        return _d(core.market_clock())
    except Exception:
        return {}


def _minutes(core: Any, clock: Dict[str, Any]) -> float:
    if clock.get("minutes_since_open") is not None:
        return max(0.0, _f(clock.get("minutes_since_open")))
    try:
        now = core.now_local()
        opening = core.regular_open_datetime(now)
        return max(0.0, (now - opening).total_seconds() / 60.0)
    except Exception:
        return 9999.0


def _entries_today(core: Any) -> int:
    try:
        trades = core.trades_for_date(_today(core))
    except Exception:
        trades = _l(_state(core).get("trades"))
    return sum(
        1
        for trade in _l(trades)
        if isinstance(trade, dict)
        and trade.get("action") == "entry"
        and (
            "opening_surge" in str(trade.get("entry_context") or "")
            or trade.get("trade_class") == "opening_surge_breakout_starter"
        )
    )


def _callable_label(fn: Any) -> Dict[str, Any]:
    return {
        "module": getattr(fn, "__module__", None),
        "name": getattr(fn, "__name__", None),
        "qualname": getattr(fn, "__qualname__", None),
        "id": id(fn) if callable(fn) else None,
    }


def _linked_callables(fn: Any) -> List[Tuple[str, Any]]:
    if not callable(fn):
        return []

    linked: List[Tuple[str, Any]] = []
    seen_ids: set[int] = set()

    def add(attr: str, candidate: Any) -> None:
        if callable(candidate) and id(candidate) not in seen_ids:
            seen_ids.add(id(candidate))
            linked.append((attr, candidate))

    for attr in _KNOWN_LINK_ATTRS:
        try:
            add(attr, getattr(fn, attr, None))
        except Exception:
            pass

    try:
        attributes = vars(fn)
    except Exception:
        attributes = {}

    for key in sorted(attributes):
        lower = str(key).lower()
        if not any(token in lower for token in _LINK_NAME_TOKENS):
            continue
        try:
            add(str(key), attributes.get(key))
        except Exception:
            pass

    return linked


def _inspect_callable_chain(
    fn: Any,
    marker: str,
    *,
    expected_version: str | None = None,
    limit: int = 100,
) -> Dict[str, Any]:
    queue: List[Tuple[Any, List[str], int]] = [(fn, [], 0)]
    seen: set[int] = set()
    nodes: List[Dict[str, Any]] = []
    matches: List[Dict[str, Any]] = []
    cycle_detected = False

    while queue and len(nodes) < limit:
        current, path, depth = queue.pop(0)
        if not callable(current):
            continue
        ident = id(current)
        if ident in seen:
            cycle_detected = True
            continue
        seen.add(ident)

        value = getattr(current, marker, None)
        version = getattr(current, "_opening_surge_version", None)
        matched = bool(value) and (
            expected_version is None or str(version) == str(expected_version)
        )
        row = {
            **_callable_label(current),
            "depth": depth,
            "path": path,
            "opening_surge_marker": bool(value),
            "opening_surge_version": version,
            "matched": matched,
        }
        nodes.append(row)
        if matched:
            matches.append(row)

        for attr, linked in _linked_callables(current):
            queue.append((linked, path + [attr], depth + 1))

    return {
        "active": bool(matches),
        "marker_count": len(matches),
        "outermost": bool(
            callable(fn)
            and bool(getattr(fn, marker, False))
            and (
                expected_version is None
                or str(getattr(fn, "_opening_surge_version", None))
                == str(expected_version)
            )
        ),
        "first_match_depth": matches[0]["depth"] if matches else None,
        "first_match_path": matches[0]["path"] if matches else None,
        "cycle_detected": cycle_detected,
        "nodes_inspected": len(nodes),
        "truncated": bool(queue),
        "current_callable": _callable_label(fn),
        "chain_preview": nodes[:20],
    }


def _permission(core: Any, market: Dict[str, Any]) -> Dict[str, Any]:
    global _LAST_PERMISSION

    market = _d(market)
    state = _state(core)
    clock = _clock(core)
    minutes = _minutes(core, clock)
    try:
        risk = _d(core.get_risk_controls())
    except Exception:
        risk = _d(state.get("risk_controls"))

    feedback = _d(state.get("feedback_loop"))
    warmup: Dict[str, Any] = {}
    try:
        warmup = _d(core.opening_warmup_status(clock))
    except Exception:
        pass

    futures = _d(market.get("futures_bias"))
    nq = _f(futures.get("nq_pct"))
    futures_ok = (
        nq >= MIN_NQ_PCT
        and str(futures.get("nq_trend") or "").lower() == "up"
        and (
            str(futures.get("bias") or "").lower()
            in {"bullish", "bullish_but_extended"}
            or str(futures.get("action") or "").lower() == "gap_chase_protection"
        )
    )

    daily = max(
        _f(risk.get("daily_loss_fraction")),
        _f(risk.get("realized_loss_fraction")),
        _f(risk.get("daily_loss_pct")) / 100.0,
    )
    intraday = max(
        _f(risk.get("intraday_drawdown_fraction")),
        _f(risk.get("intraday_drawdown_pct")) / 100.0,
    )
    used = _entries_today(core)
    positions = _d(state.get("positions"))
    mode = str(market.get("market_mode") or "").lower()

    checks = [
        (not ENABLED, "opening_surge_disabled"),
        (not _paper(), "not_paper_context"),
        (not bool(clock.get("is_open")), "market_closed"),
        (bool(warmup.get("active")), "opening_warmup_active"),
        (minutes < START_MIN, "before_opening_surge_window"),
        (minutes > END_MIN, "after_opening_surge_window"),
        (mode not in MODES, "market_mode_not_defensive_dislocation"),
        (bool(market.get("bear_confirmed")), "bear_confirmed_blocks_opening_long"),
        (not futures_ok, "bullish_nq_open_not_confirmed"),
        (bool(risk.get("halted")), "risk_halted"),
        (bool(risk.get("profit_guard_active")), "profit_guard_active"),
        (bool(risk.get("self_defense_active")), "self_defense_active"),
        (bool(feedback.get("hard_halt")), "feedback_hard_halt"),
        (bool(feedback.get("block_new_entries")), "feedback_blocks_entries"),
        (daily >= MAX_LOSS, "daily_loss_above_opening_surge_limit"),
        (intraday >= MAX_LOSS, "intraday_drawdown_above_opening_surge_limit"),
        (bool(positions), "opening_surge_requires_empty_book"),
        (used >= MAX_DAILY, "opening_surge_daily_allowance_used"),
    ]
    reasons = [reason for failed, reason in checks if failed]

    _LAST_PERMISSION = {
        "active": not reasons,
        "reasons": reasons,
        "market_mode": mode,
        "regime": market.get("regime"),
        "bear_confirmed": bool(market.get("bear_confirmed")),
        "market_open": bool(clock.get("is_open")),
        "opening_warmup": warmup,
        "minutes_since_open": round(minutes, 2),
        "window_start_minutes": START_MIN,
        "window_end_minutes": END_MIN,
        "futures_bullish": futures_ok,
        "futures_bias": futures,
        "minimum_nq_pct": MIN_NQ_PCT,
        "daily_loss_fraction": round(daily, 6),
        "intraday_drawdown_fraction": round(intraday, 6),
        "max_loss_fraction": MAX_LOSS,
        "open_positions_count": len(positions),
        "entries_used": used,
        "entries_remaining": max(0, MAX_DAILY - used),
    }
    return dict(_LAST_PERMISSION)


def _clean(value: Any) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=float).reshape(-1)
        return array[np.isfinite(array)]
    except Exception:
        return np.array([])


def _rvol(volumes: Any, bars: int) -> float:
    volumes = _clean(volumes)
    if bars <= 0 or len(volumes) < bars:
        return 0.0
    current = float(np.sum(volumes[-bars:]))
    end = len(volumes) - bars
    samples: List[float] = []
    for offset in range(1, 5):
        start = end - 78 * offset
        if start < 0:
            break
        chunk = volumes[start : start + bars]
        if len(chunk) == bars and float(np.sum(chunk)) > 0:
            samples.append(float(np.sum(chunk)))
    baseline = float(np.mean(samples)) if samples else 0.0
    return current / baseline if baseline > 0 else 0.0


def _bucket(core: Any, symbol: str, row: Dict[str, Any]) -> str:
    if row.get("bucket"):
        return str(row.get("bucket"))
    try:
        return str(core.symbol_bucket(symbol) or "default")
    except Exception:
        return str(_d(getattr(core, "SYMBOL_BUCKET", {})).get(symbol, "default"))


def _profile(
    core: Any,
    row: Dict[str, Any],
    minutes: float,
) -> Dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper().strip()
    score = _f(row.get("score"))
    base = {"symbol": symbol, "score": round(score, 6), "qualified": False}
    if not symbol:
        return {**base, "reason": "missing_symbol"}
    if score < MIN_SCORE:
        return {**base, "reason": "score_below_opening_surge_floor"}

    try:
        data = core.fetch_intraday(symbol)
        arrays = core.intraday_arrays(data)
    except Exception as exc:
        return {
            **base,
            "reason": "intraday_fetch_error",
            "error": f"{type(exc).__name__}: {exc}",
        }

    arrays = _d(arrays)
    closes = _clean(arrays.get("close"))
    opens = _clean(arrays.get("open"))
    highs = _clean(arrays.get("high"))
    lows = _clean(arrays.get("low"))
    volumes = _clean(arrays.get("volume"))

    bars = max(1, min(len(closes), int(minutes // 5) + 1))
    if bars < 4 or len(opens) < bars or len(highs) < bars:
        return {
            **base,
            "reason": "not_enough_opening_session_bars",
            "session_bars": bars,
        }

    c = closes[-bars:]
    o = opens[-bars:]
    h = highs[-bars:]
    l = lows[-bars:] if len(lows) >= bars else c
    price = float(c[-1])
    session_open = float(o[0])
    previous_close = float(closes[-bars - 1]) if len(closes) > bars else session_open
    if price <= 0 or session_open <= 0 or previous_close <= 0:
        return {**base, "reason": "bad_price"}

    day_move = price / previous_close - 1.0
    session_move = price / session_open - 1.0
    opening_range_high = float(np.max(h[: min(3, bars - 1)]))
    session_high = float(np.max(h))
    session_low = float(np.min(l))
    broke_range = price >= opening_range_high * (1.0 + MIN_RANGE_BREAK)
    holding_near_high = price >= session_high * NEAR_HIGH
    fast_hold = price >= float(np.mean(c[-min(3, len(c)) :])) * 0.998
    relative_volume = _rvol(volumes, bars)
    volume_ok = (
        relative_volume >= MIN_RVOL
        or session_move >= STRONG_MOVE_RVOL_EXCEPTION
    )
    bucket = _bucket(core, symbol, row)

    tests = [
        (day_move < MIN_DAY_MOVE, "total_day_move_below_gap_surge_minimum"),
        (day_move > MAX_DAY_MOVE, "total_day_move_too_extended"),
        (
            session_move < MIN_SESSION_MOVE,
            "opening_session_follow_through_below_minimum",
        ),
        (
            session_move > MAX_SESSION_MOVE,
            "opening_session_follow_through_too_extended",
        ),
        (not broke_range, "opening_range_not_broken"),
        (not holding_near_high, "not_holding_near_session_high"),
        (not fast_hold, "fast_momentum_not_holding"),
        (not volume_ok, "relative_volume_not_confirmed"),
        (bucket not in BUCKETS, "bucket_not_opening_surge_eligible"),
    ]
    failures = [reason for failed, reason in tests if failed]

    return {
        **base,
        "qualified": not failures,
        "reason": (
            "opening_surge_breakout_confirmed"
            if not failures
            else ",".join(failures)
        ),
        "price": round(price, 4),
        "session_bars": bars,
        "previous_close": round(previous_close, 4),
        "day_move_pct": round(day_move * 100, 3),
        "session_move_pct": round(session_move * 100, 3),
        "opening_range_high": round(opening_range_high, 4),
        "session_high": round(session_high, 4),
        "session_low": round(session_low, 4),
        "broke_opening_range": broke_range,
        "holding_near_high": holding_near_high,
        "fast_momentum_hold": fast_hold,
        "relative_volume_ratio": round(relative_volume, 3),
        "volume_confirmed": volume_ok,
        "bucket": bucket,
        "sector": row.get("sector")
        or _d(getattr(core, "SYMBOL_SECTOR", {})).get(symbol, "UNKNOWN"),
        "source_reason": row.get("reason"),
    }


def _patch_universe(core: Any) -> None:
    try:
        universe = list(getattr(core, "UNIVERSE", []) or [])
        for symbol in EXTRA:
            if symbol not in universe:
                universe.append(symbol)
        core.UNIVERSE = universe
    except Exception:
        pass

    sectors = {
        "WDC": "XLK",
        "CORZ": "XLK",
        "CRWV": "XLK",
        "LRCX": "XLK",
        "NBIS": "XLK",
        "SNDK": "XLK",
        "RIOT": "XLK",
        "AMD": "XLK",
        "BE": "XLI",
        "PWR": "XLI",
    }
    buckets = {
        "WDC": "data_center_infra",
        "CORZ": "bitcoin_ai_compute",
        "CRWV": "ai_cloud_breakout",
        "LRCX": "semi_leaders",
        "NBIS": "ai_cloud_breakout",
        "SNDK": "data_center_infra",
        "RIOT": "bitcoin_ai_compute",
        "AMD": "semi_leaders",
        "BE": "power_grid_data_center",
        "PWR": "power_grid_data_center",
    }
    try:
        sector_map = getattr(core, "SYMBOL_SECTOR", {})
        bucket_map = getattr(core, "SYMBOL_BUCKET", {})
        for symbol, value in sectors.items():
            sector_map.setdefault(symbol, value)
        for symbol, value in buckets.items():
            bucket_map.setdefault(symbol, value)
    except Exception:
        pass


def _wrap_risk(core: Any) -> bool:
    current = getattr(core, "risk_parameters", None)
    if not callable(current):
        return False

    inspection = _inspect_callable_chain(
        current,
        "_opening_surge_permission_guard",
        expected_version=VERSION,
    )
    if inspection.get("active"):
        return False

    def wrapped(market: Dict[str, Any], __prior=current):
        params = dict(__prior(market) or {})
        permission = _permission(core, market)
        if permission.get("active"):
            positions = _d(_state(core).get("positions"))
            normal_max = max(1, _i(params.get("max_positions"), 1))
            params.update(
                {
                    "allow_longs": True,
                    "max_positions": min(normal_max, len(positions) + 1),
                    "long_alloc_pct": min(
                        max(0.0, _f(params.get("long_alloc_pct"))),
                        MAX_LONG_ALLOC,
                    ),
                    "opening_surge_permission": permission,
                    "opening_surge_only": True,
                }
            )
        return params

    wrapped._opening_surge_permission_guard = True
    wrapped._opening_surge_version = VERSION
    wrapped._opening_surge_risk_prior = current
    wrapped._opening_surge_prior = current
    wrapped.__wrapped__ = current
    core.risk_parameters = wrapped
    return True


def _wrap_scan(core: Any) -> bool:
    current = getattr(core, "scan_signals", None)
    if not callable(current):
        return False

    inspection = _inspect_callable_chain(
        current,
        "_opening_surge_scan_guard",
        expected_version=VERSION,
    )
    if inspection.get("active"):
        return False

    def wrapped(market: Dict[str, Any], __prior=current):
        global _LAST_SCAN

        long_signals, short_signals, rejected = __prior(market)
        permission = _permission(core, market)
        if not permission.get("active"):
            return long_signals, short_signals, rejected

        by_symbol: Dict[str, Dict[str, Any]] = {}
        candidate_rows = list(_l(long_signals)) + [
            row
            for row in _l(rejected)
            if isinstance(row, dict)
            and str(row.get("side") or "long").lower() == "long"
            and _f(row.get("score")) >= MIN_SCORE
        ]
        for row in candidate_rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            if symbol not in by_symbol or _f(row.get("score")) > _f(
                by_symbol[symbol].get("score")
            ):
                by_symbol[symbol] = dict(row)

        profiles = [
            _profile(core, row, _f(permission.get("minutes_since_open")))
            for row in by_symbol.values()
        ]
        qualified = sorted(
            [profile for profile in profiles if profile.get("qualified")],
            key=lambda profile: (
                _f(profile.get("score")),
                _f(profile.get("relative_volume_ratio")),
            ),
            reverse=True,
        )

        promoted: List[Dict[str, Any]] = []
        if len(qualified) >= MIN_CLUSTER:
            for profile in qualified[:MAX_CANDIDATES]:
                symbol = str(profile.get("symbol") or "")
                row = dict(by_symbol.get(symbol, {}))
                row.update(
                    {
                        "symbol": profile.get("symbol"),
                        "side": "long",
                        "score": profile.get("score"),
                        "price": profile.get("price"),
                        "sector": profile.get("sector"),
                        "bucket": profile.get("bucket"),
                        "entry_context": "opening_surge_breakout_starter",
                        "trade_class": "opening_surge_breakout_starter",
                        "alloc_factor": min(
                            max(0.0, _f(row.get("alloc_factor"), 1.0)),
                            MAX_SIGNAL_FACTOR,
                        ),
                        "opening_surge_participation": profile,
                    }
                )
                promoted.append(row)

        _LAST_SCAN = {
            "version": VERSION,
            "updated_local": _now(core),
            "permission": permission,
            "cluster_confirmed": len(qualified) >= MIN_CLUSTER,
            "minimum_cluster_candidates": MIN_CLUSTER,
            "qualified_count": len(qualified),
            "qualified_symbols": [
                profile.get("symbol") for profile in qualified
            ],
            "promoted_symbols": [row.get("symbol") for row in promoted],
            "profiles": profiles[:20],
        }
        _state(core)["opening_surge_participation"] = dict(_LAST_SCAN)
        return promoted, short_signals, rejected

    wrapped._opening_surge_scan_guard = True
    wrapped._opening_surge_version = VERSION
    wrapped._opening_surge_scan_prior = current
    wrapped._opening_surge_prior = current
    wrapped.__wrapped__ = current
    core.scan_signals = wrapped
    return True


def _ownership(core: Any) -> Dict[str, Any]:
    risk_fn = getattr(core, "risk_parameters", None)
    scan_fn = getattr(core, "scan_signals", None)
    risk = _inspect_callable_chain(
        risk_fn,
        "_opening_surge_permission_guard",
        expected_version=VERSION,
    )
    scan = _inspect_callable_chain(
        scan_fn,
        "_opening_surge_scan_guard",
        expected_version=VERSION,
    )

    def classification(row: Dict[str, Any]) -> str:
        count = _i(row.get("marker_count"))
        if count == 0:
            return "missing"
        if count > 1:
            return "duplicate"
        if row.get("outermost"):
            return "outermost"
        return "nested_but_active"

    return {
        "risk": risk,
        "scan": scan,
        "risk_classification": classification(risk),
        "scan_classification": classification(scan),
        "risk_owned": _i(risk.get("marker_count")) == 1,
        "scan_owned": _i(scan.get("marker_count")) == 1,
    }


def install(core: Any) -> Dict[str, Any]:
    global _LAST_INSTALL

    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    with _LOCK:
        _patch_universe(core)
        risk_patched = _wrap_risk(core)
        scan_patched = _wrap_scan(core)
        ownership = _ownership(core)
        healthy = bool(ownership.get("risk_owned") and ownership.get("scan_owned"))
        _LAST_INSTALL = {
            "status": "ok" if healthy else "warn",
            "overall": "pass" if healthy else "warn",
            "version": VERSION,
            "generated_local": _now(core),
            "risk_parameters_patched_this_call": risk_patched,
            "scan_signals_patched_this_call": scan_patched,
            "risk_guard_active": bool(
                ownership.get("risk", {}).get("active")
            ),
            "scan_guard_active": bool(
                ownership.get("scan", {}).get("active")
            ),
            "risk_guard_outermost": bool(
                ownership.get("risk", {}).get("outermost")
            ),
            "scan_guard_outermost": bool(
                ownership.get("scan", {}).get("outermost")
            ),
            "risk_guard_count": ownership.get("risk", {}).get("marker_count"),
            "scan_guard_count": ownership.get("scan", {}).get("marker_count"),
            "risk_guard_depth": ownership.get("risk", {}).get(
                "first_match_depth"
            ),
            "scan_guard_depth": ownership.get("scan", {}).get(
                "first_match_depth"
            ),
            "risk_classification": ownership.get("risk_classification"),
            "scan_classification": ownership.get("scan_classification"),
            "risk_callable": ownership.get("risk", {}).get(
                "current_callable", {}
            ).get("qualname"),
            "scan_callable": ownership.get("scan", {}).get(
                "current_callable", {}
            ).get("qualname"),
        }
        setattr(core, "OPENING_SURGE_PARTICIPATION_VERSION", VERSION)
        return dict(_LAST_INSTALL)


def status_payload(core: Any) -> Dict[str, Any]:
    market = _d(_state(core).get("last_market")) if core else {}
    permission = _permission(core, market) if core else {}
    ownership = _ownership(core) if core else {}
    risk = _d(ownership.get("risk"))
    scan = _d(ownership.get("scan"))
    risk_owned = bool(ownership.get("risk_owned"))
    scan_owned = bool(ownership.get("scan_owned"))
    healthy = bool(core is not None and risk_owned and scan_owned)

    return {
        "status": "ok" if healthy else "warn",
        "overall": "pass" if healthy else "warn",
        "type": "opening_surge_participation_status",
        "version": VERSION,
        "generated_local": _now(core),
        "risk_guard_active": bool(risk.get("active")),
        "scan_guard_active": bool(scan.get("active")),
        "risk_guard_outermost": bool(risk.get("outermost")),
        "scan_guard_outermost": bool(scan.get("outermost")),
        "risk_guard_count": risk.get("marker_count"),
        "scan_guard_count": scan.get("marker_count"),
        "risk_guard_depth": risk.get("first_match_depth"),
        "scan_guard_depth": scan.get("first_match_depth"),
        "risk_classification": ownership.get("risk_classification"),
        "scan_classification": ownership.get("scan_classification"),
        "ownership": ownership,
        "permission_live": permission,
        "last_scan": dict(_LAST_SCAN),
        "stored_state": (
            _d(_state(core).get("opening_surge_participation"))
            if core
            else {}
        ),
        "last_install": dict(_LAST_INSTALL),
        "settings": {
            "start_minutes_after_open": START_MIN,
            "end_minutes_after_open": END_MIN,
            "max_entries_per_day": MAX_DAILY,
            "max_candidates_per_cycle": MAX_CANDIDATES,
            "minimum_cluster_candidates": MIN_CLUSTER,
            "minimum_score": MIN_SCORE,
            "minimum_day_move_pct": MIN_DAY_MOVE * 100,
            "maximum_day_move_pct": MAX_DAY_MOVE * 100,
            "minimum_session_follow_through_pct": MIN_SESSION_MOVE * 100,
            "maximum_session_follow_through_pct": MAX_SESSION_MOVE * 100,
            "minimum_relative_volume": MIN_RVOL,
            "minimum_nq_futures_pct": MIN_NQ_PCT,
            "allowed_market_modes": sorted(MODES),
        },
        "authority": {
            "paper_only": True,
            "places_orders_directly": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "changes_hard_risk_limits": False,
            "changes_signal_generation": True,
            "changes_strategy_permission": True,
            "changes_sizing": True,
            "bounded_opening_long_exception": True,
            "bear_confirmed_long_exception": False,
            "ownership_inspection_only": True,
        },
    }


def register_routes(flask_app: Any, core: Any) -> Dict[str, Any]:
    if flask_app is None:
        return {
            "status": "pending",
            "version": VERSION,
            "reason": "flask_app_missing",
        }
    install(core)
    if id(flask_app) in _APPS:
        return {"status": "ok", "version": VERSION, "already_registered": True}

    from flask import jsonify

    path = "/paper/opening-surge-participation-status"
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if path not in existing:
        flask_app.add_url_rule(
            path,
            "opening_surge_participation_status",
            lambda: jsonify(status_payload(core)),
        )
    _APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [path]}


def start_watchdog(core: Any) -> Dict[str, Any]:
    install(core)
    flask_app = getattr(core, "app", None)
    if flask_app is not None:
        register_routes(flask_app, core)

    if core is None or id(core) in _WATCHDOG:
        return {
            "status": "ok",
            "version": VERSION,
            "watchdog_started": core is not None and id(core) in _WATCHDOG,
        }

    _WATCHDOG.add(id(core))

    def watch() -> None:
        for iteration in range(1200):
            try:
                install(core)
            except Exception:
                pass
            time.sleep(0.5 if iteration < 60 else 30.0)

    threading.Thread(
        target=watch,
        daemon=True,
        name="opening-surge-participation-watchdog",
    ).start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}
