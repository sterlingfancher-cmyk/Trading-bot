"""Bounded neutral-tape starter with staged two-position controls.

The existing risk-on starter remains the final candidate-quality and execution
valve. This module adds a neutral context and, only while the market is neutral,
permits a staged second reduced-size starter after spacing, diversification,
position-health, and combined-exposure checks.

Non-neutral markets pass through to the pre-existing starter unchanged. This
module does not wrap the main entry loop, place orders directly, change hard
risk limits, enable live trading, or grant ML authority.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "neutral-momentum-starter-extension-2026-08-03-v3-neutral-only-staging"
ENABLED = os.environ.get("NEUTRAL_MOMENTUM_STARTER_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
START_MINUTES = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_START_MINUTES", "45"))
END_MINUTES = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_END_MINUTES", "180"))
MIN_RISK_SCORE = float(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MIN_RISK_SCORE", "40"))
MIN_SCANNER_SIGNALS = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MIN_SCANNER_SIGNALS", "15"))
MIN_LONG_SIGNALS = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MIN_LONG_SIGNALS", "4"))
MAX_NEUTRAL_STARTERS_PER_DAY = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MAX_ENTRIES_PER_DAY", "2"))
MAX_NEUTRAL_STARTERS_PER_CYCLE = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MAX_ENTRIES_PER_CYCLE", "1"))
MAX_NEUTRAL_OPEN_POSITIONS = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MAX_OPEN_POSITIONS", "2"))
MIN_SECONDS_BETWEEN_STARTERS = int(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MIN_SECONDS_BETWEEN", "900"))
FIRST_POSITION_MIN_PNL_PCT = float(os.environ.get("NEUTRAL_MOMENTUM_STARTER_FIRST_POSITION_MIN_PNL_PCT", "-0.50"))
MAX_COMBINED_EXPOSURE_PCT = float(os.environ.get("NEUTRAL_MOMENTUM_STARTER_MAX_COMBINED_EXPOSURE_PCT", "36.0"))

_EXTRA_SYMBOLS = {"RGIT", "APLD", "MP", "NBIS", "AMZN", "META", "BTQ", "NVTS", "KEEL", "CIFR"}
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
_LINK_ATTRS = (
    "_neutral_momentum_staged_prior",
    "_neutral_momentum_starter_extension_prior",
    "_risk_on_starter_participation_prior",
    "_participation_valve_prior",
    "__wrapped__",
)


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return int(float(value))
    except Exception:
        return default


def _paper() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker


def _portfolio(core: Any) -> Dict[str, Any]:
    return _d(getattr(core, "portfolio", {}))


def _positions(core: Any) -> Dict[str, Any]:
    return _d(_portfolio(core).get("positions"))


def _symbol(signal: Dict[str, Any]) -> str:
    return str(signal.get("symbol") or signal.get("ticker") or "").upper().strip()


def _sector(core: Any, symbol: str, row: Dict[str, Any]) -> str:
    value = row.get("sector") or row.get("sector_etf") or row.get("sector_symbol")
    if value:
        return str(value).upper().strip()
    try:
        return str((getattr(core, "SYMBOL_SECTOR", {}) or {}).get(symbol, "")).upper().strip()
    except Exception:
        return ""


def _bucket(core: Any, symbol: str, row: Dict[str, Any]) -> str:
    value = row.get("bucket") or row.get("symbol_bucket") or row.get("theme")
    if value:
        return str(value).lower().strip()
    try:
        return str((getattr(core, "SYMBOL_BUCKET", {}) or {}).get(symbol, "")).lower().strip()
    except Exception:
        return ""


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
    state = _portfolio(core)
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
    futures_text = " ".join(str(futures.get(k) or "").lower() for k in ("bias", "action", "reason"))
    breadth_text = " ".join(str(breadth.get(k) or "").lower() for k in ("state", "action", "reason"))
    growth = bool(market.get("growth_leadership") or market.get("tech_leadership") or market.get("risk_on_leadership"))
    sector_count = _i(market.get("risk_on_sector_count"))
    positive_tape = bool(
        growth
        or sector_count >= 2
        or any(token in futures_text for token in ("bullish", "gap_chase_protection", "risk_on"))
        or any(token in breadth_text for token in (
            "supportive", "narrow_mega_cap_led", "reduce_aggression",
            "tech_concentrated", "tech_caution",
        ))
    )

    reasons: List[str] = []
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


def _parse_time(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(value))
        except Exception:
            return None
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("T", " ").replace("Z", "").split(" CDT")[0].split(" CST")[0]
    for candidate in (text, text[:19]):
        try:
            return dt.datetime.fromisoformat(candidate)
        except Exception:
            pass
        try:
            return dt.datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return None


def _latest_entry_time(core: Any, positions: Dict[str, Any]) -> dt.datetime | None:
    times: List[dt.datetime] = []
    fields = ("entry_time", "opened_at", "opened_local", "entry_timestamp", "timestamp", "created_at")
    for row in positions.values():
        if not isinstance(row, dict):
            continue
        for field in fields:
            parsed = _parse_time(row.get(field))
            if parsed is not None:
                times.append(parsed)
                break
    for trade in list(_portfolio(core).get("trades") or [])[-100:]:
        if not isinstance(trade, dict):
            continue
        action = str(trade.get("action") or trade.get("type") or "").lower()
        if action and action not in {"buy", "entry", "open", "long", "short", "sell_short"}:
            continue
        for field in fields:
            parsed = _parse_time(trade.get(field))
            if parsed is not None:
                times.append(parsed)
                break
    return max(times) if times else None


def _position_mark(row: Dict[str, Any]) -> float:
    for field in ("current_price", "mark", "last_price", "price", "market_price", "entry_price", "avg_price", "average_price"):
        value = _f(row.get(field))
        if value > 0:
            return value
    return 0.0


def _position_entry(row: Dict[str, Any]) -> float:
    for field in ("entry_price", "avg_price", "average_price", "cost_basis_price", "price"):
        value = _f(row.get(field))
        if value > 0:
            return value
    return 0.0


def _position_qty(row: Dict[str, Any]) -> float:
    for field in ("qty", "quantity", "shares", "units", "position_size"):
        value = abs(_f(row.get(field)))
        if value > 0:
            return value
    return 0.0


def _position_value(row: Dict[str, Any]) -> float:
    for field in ("market_value", "position_value", "value", "notional", "cost_basis"):
        value = abs(_f(row.get(field)))
        if value > 0:
            return value
    return _position_qty(row) * _position_mark(row)


def _position_pnl_pct(row: Dict[str, Any]) -> float | None:
    for field in ("unrealized_pnl_pct", "pnl_pct", "return_pct", "gain_pct", "unrealized_pct"):
        if row.get(field) is not None:
            return _f(row.get(field))
    entry = _position_entry(row)
    mark = _position_mark(row)
    if entry > 0 and mark > 0:
        move = ((mark / entry) - 1.0) * 100.0
        return -move if str(row.get("side") or "long").lower() == "short" else move
    unrealized = row.get("unrealized_pnl")
    basis = row.get("cost_basis") or row.get("position_value")
    if unrealized is not None and _f(basis) > 0:
        return (_f(unrealized) / _f(basis)) * 100.0
    return None


def _entries_today(starter: Any, core: Any) -> int:
    try:
        return int(starter._entries_today(core))
    except Exception:
        return 0


def _stage_gate(core: Any, starter: Any, signal: Dict[str, Any], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    positions = _positions(core)
    starter_entries = _entries_today(starter, core)
    stage_count = max(starter_entries, len(positions))
    mode = str(_d(market).get("market_mode") or _d(market).get("regime") or "").lower()
    symbol = _symbol(signal)
    candidate_sector = _sector(core, symbol, signal)
    candidate_bucket = _bucket(core, symbol, signal)
    base = {
        "symbol": symbol,
        "candidate_sector": candidate_sector,
        "candidate_bucket": candidate_bucket,
        "market_mode": mode,
        "starter_entries_today": starter_entries,
        "open_positions_count": len(positions),
        "stage_count": stage_count,
        "max_entries_per_day": MAX_NEUTRAL_STARTERS_PER_DAY,
        "max_entries_per_cycle": MAX_NEUTRAL_STARTERS_PER_CYCLE,
        "max_open_positions": MAX_NEUTRAL_OPEN_POSITIONS,
    }

    if mode != "neutral":
        return True, {**base, "reason": "non_neutral_passthrough", "neutral_stage_applies": False}
    if stage_count <= 0:
        return True, {**base, "reason": "first_neutral_starter_stage_allowed", "stage": 1}
    if stage_count >= MAX_NEUTRAL_STARTERS_PER_DAY or len(positions) >= MAX_NEUTRAL_OPEN_POSITIONS:
        return False, {**base, "reason": "neutral_starter_daily_or_open_position_limit"}
    if len(positions) != 1:
        return False, {**base, "reason": "second_starter_requires_one_open_first_position"}

    latest = _latest_entry_time(core, positions)
    if latest is None:
        return False, {**base, "reason": "second_starter_entry_time_unknown"}
    try:
        current = core.now_local()
    except Exception:
        current = dt.datetime.now()
    if getattr(current, "tzinfo", None) is not None and getattr(latest, "tzinfo", None) is None:
        latest = latest.replace(tzinfo=current.tzinfo)
    age_seconds = max(0.0, (current - latest).total_seconds())
    if age_seconds < MIN_SECONDS_BETWEEN_STARTERS:
        return False, {
            **base,
            "reason": "second_starter_spacing_not_met",
            "seconds_since_first_entry": round(age_seconds, 1),
            "required_seconds_between_entries": MIN_SECONDS_BETWEEN_STARTERS,
        }

    existing_sectors: set[str] = set()
    existing_buckets: set[str] = set()
    pnl_rows: List[Dict[str, Any]] = []
    current_value = 0.0
    for existing_symbol, raw in positions.items():
        row = raw if isinstance(raw, dict) else {}
        existing_sector = _sector(core, str(existing_symbol).upper(), row)
        existing_bucket = _bucket(core, str(existing_symbol).upper(), row)
        if existing_sector:
            existing_sectors.add(existing_sector)
        if existing_bucket:
            existing_buckets.add(existing_bucket)
        pnl = _position_pnl_pct(row)
        pnl_rows.append({"symbol": str(existing_symbol).upper(), "pnl_pct": None if pnl is None else round(pnl, 4)})
        if pnl is None:
            return False, {**base, "reason": "first_position_pnl_unknown", "first_positions": pnl_rows}
        if pnl < FIRST_POSITION_MIN_PNL_PCT:
            return False, {
                **base,
                "reason": "first_position_materially_losing",
                "first_positions": pnl_rows,
                "minimum_first_position_pnl_pct": FIRST_POSITION_MIN_PNL_PCT,
            }
        current_value += _position_value(row)

    if not candidate_sector and not candidate_bucket:
        return False, {**base, "reason": "second_starter_diversification_metadata_missing"}
    same_sector = bool(candidate_sector and candidate_sector in existing_sectors)
    same_bucket = bool(candidate_bucket and candidate_bucket in existing_buckets)
    if same_sector and same_bucket:
        return False, {
            **base,
            "reason": "second_starter_not_diversified",
            "existing_sectors": sorted(existing_sectors),
            "existing_buckets": sorted(existing_buckets),
        }

    state = _portfolio(core)
    equity = max(_f(state.get("equity"), _f(state.get("cash"))), 0.0)
    starter_factor = max(0.0, _f(getattr(starter, "ALLOC_FACTOR", 0.18), 0.18))
    proposed_upper_bound = equity * starter_factor
    combined_pct = ((current_value + proposed_upper_bound) / equity) * 100.0 if equity > 0 else 999.0
    if combined_pct > MAX_COMBINED_EXPOSURE_PCT:
        return False, {
            **base,
            "reason": "second_starter_combined_exposure_cap",
            "current_open_value": round(current_value, 2),
            "proposed_starter_upper_bound": round(proposed_upper_bound, 2),
            "projected_combined_exposure_pct": round(combined_pct, 3),
            "maximum_combined_exposure_pct": MAX_COMBINED_EXPOSURE_PCT,
        }

    return True, {
        **base,
        "reason": "second_neutral_starter_stage_allowed",
        "stage": 2,
        "seconds_since_first_entry": round(age_seconds, 1),
        "required_seconds_between_entries": MIN_SECONDS_BETWEEN_STARTERS,
        "first_positions": pnl_rows,
        "minimum_first_position_pnl_pct": FIRST_POSITION_MIN_PNL_PCT,
        "existing_sectors": sorted(existing_sectors),
        "existing_buckets": sorted(existing_buckets),
        "different_sector_or_bucket": True,
        "current_open_value": round(current_value, 2),
        "proposed_starter_upper_bound": round(proposed_upper_bound, 2),
        "projected_combined_exposure_pct": round(combined_pct, 3),
        "maximum_combined_exposure_pct": MAX_COMBINED_EXPOSURE_PCT,
    }


def _linked(fn: Any) -> Iterable[Any]:
    if not callable(fn):
        return []
    out: List[Any] = []
    for attr in _LINK_ATTRS:
        try:
            value = getattr(fn, attr, None)
            if callable(value):
                out.append(value)
        except Exception:
            pass
    return out


def _has_exact_version(fn: Any, limit: int = 32) -> bool:
    queue = [fn]
    seen: set[int] = set()
    while queue and len(seen) < limit:
        current = queue.pop(0)
        if not callable(current) or id(current) in seen:
            continue
        seen.add(id(current))
        if getattr(current, "_neutral_momentum_starter_extension_version", None) == VERSION:
            return True
        queue.extend(_linked(current))
    return False


def _unwrap_old_neutral_stage(fn: Any) -> Any:
    current = fn
    seen: set[int] = set()
    for _ in range(16):
        if not callable(current) or id(current) in seen:
            break
        seen.add(id(current))
        version = getattr(current, "_neutral_momentum_starter_extension_version", None)
        prior = getattr(current, "_neutral_momentum_staged_prior", None)
        if version and callable(prior):
            current = prior
            continue
        break
    return current


def _unwrap_old_neutral_context(fn: Any) -> Any:
    current = fn
    seen: set[int] = set()
    for _ in range(16):
        if not callable(current) or id(current) in seen:
            break
        seen.add(id(current))
        prior = getattr(current, "_neutral_momentum_starter_extension_prior", None)
        if callable(prior):
            current = prior
            continue
        break
    return current


def _install_context(core: Any, starter: Any) -> bool:
    current = getattr(starter, "_risk_on_confirmed", None)
    if not callable(current):
        return False
    if getattr(current, "_neutral_momentum_context_version", None) == VERSION:
        return False
    prior = _unwrap_old_neutral_context(current)

    def extended_context(runtime: Any, market: Dict[str, Any], __prior=prior):
        global _LAST
        prior_ok, prior_info = __prior(runtime, market)
        if prior_ok:
            _LAST["context"] = {
                "generated_local": _now(runtime),
                "status": "passthrough",
                "reason": "existing_risk_on_or_constructive_context_allowed",
                "prior": prior_info,
            }
            return prior_ok, prior_info
        neutral_ok, neutral_info = _neutral_context(runtime, market)
        _LAST["context"] = {
            "generated_local": _now(runtime),
            "status": "allowed" if neutral_ok else "blocked",
            "reason": neutral_info.get("reason"),
            "neutral": neutral_info,
            "prior": prior_info,
        }
        return (True, neutral_info) if neutral_ok else (False, neutral_info)

    extended_context._neutral_momentum_context_version = VERSION
    extended_context._neutral_momentum_starter_extension_prior = prior
    extended_context.__wrapped__ = prior
    starter._risk_on_confirmed = extended_context
    return True


def _install_staged_valve(core: Any, starter: Any) -> bool:
    try:
        import core_entry_pipeline as cep
    except Exception:
        return False
    current = getattr(cep, "_participation_valve_ok", None)
    if not callable(current):
        return False
    if _has_exact_version(current):
        try:
            current._risk_on_starter_participation_version = starter.VERSION
        except Exception:
            pass
        return False

    prior = _unwrap_old_neutral_stage(current)

    def staged_valve(
        runtime: Any,
        signal: Dict[str, Any],
        params: Dict[str, Any],
        market: Dict[str, Any],
        quality_info: Any,
        rank_index: int,
        entries_this_cycle: int,
        valve_entries_this_cycle: int,
        __prior=prior,
    ):
        global _LAST
        signal_row = signal if isinstance(signal, dict) else {}
        market_row = market if isinstance(market, dict) else {}
        mode = str(market_row.get("market_mode") or market_row.get("regime") or "").lower()

        if mode != "neutral":
            ok, raw_info = __prior(
                runtime, signal, params, market, quality_info,
                rank_index, entries_this_cycle, valve_entries_this_cycle,
            )
            info = raw_info if isinstance(raw_info, dict) else {"reason": str(raw_info)}
            _LAST["staged_gate"] = {
                "generated_local": _now(runtime),
                "status": "non_neutral_passthrough_allowed" if ok else "non_neutral_passthrough_blocked",
                "reason": "non_neutral_passthrough",
                "market_mode": mode,
                "prior_result": info,
            }
            return ok, info

        gate_ok, gate = _stage_gate(runtime, starter, signal_row, market_row)
        if not gate_ok:
            payload = {
                "reason": gate.get("reason", "neutral_staged_second_entry_block"),
                "neutral_staged_second_entry": gate,
                "paper_only": True,
                "authority_changed": False,
            }
            _LAST["staged_gate"] = {"generated_local": _now(runtime), "status": "blocked", **payload}
            return False, payload

        ok, raw_info = __prior(
            runtime, signal, params, market, quality_info,
            rank_index, entries_this_cycle, valve_entries_this_cycle,
        )
        info = raw_info if isinstance(raw_info, dict) else {"reason": str(raw_info)}
        _LAST["staged_gate"] = {
            "generated_local": _now(runtime),
            "status": "allowed_by_prior" if ok else "blocked_by_prior",
            "stage_gate": gate,
            "prior_result": info,
        }
        if ok:
            info = dict(info)
            info["neutral_staged_second_entry"] = gate
        return ok, info

    staged_valve._neutral_momentum_starter_extension_version = VERSION
    staged_valve._neutral_momentum_staged_prior = prior
    staged_valve._risk_on_starter_participation_version = getattr(starter, "VERSION", None)
    staged_valve.__wrapped__ = prior
    cep._participation_valve_ok = staged_valve
    return True


def install(core: Any = None) -> Dict[str, Any]:
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
            import core_entry_pipeline as cep
        except Exception as exc:
            return {
                "status": "warn",
                "overall": "warn",
                "version": VERSION,
                "reason": f"starter_or_core_import_failed:{type(exc).__name__}:{exc}",
            }

        _extend_universe(core, starter)
        starter.MAX_ENTRIES_PER_DAY = MAX_NEUTRAL_STARTERS_PER_DAY
        starter.MAX_ENTRIES_PER_CYCLE = MAX_NEUTRAL_STARTERS_PER_CYCLE
        starter.MAX_OPEN_POSITIONS = MAX_NEUTRAL_OPEN_POSITIONS

        context_patched = _install_context(core, starter)
        valve_patched = _install_staged_valve(core, starter)
        active = _has_exact_version(getattr(cep, "_participation_valve_ok", None))
        setattr(core, "NEUTRAL_MOMENTUM_STARTER_EXTENSION_VERSION", VERSION)
        return {
            "status": "ok" if active else "warn",
            "overall": "pass" if active else "warn",
            "type": "neutral_momentum_starter_extension_status",
            "version": VERSION,
            "generated_local": _now(core),
            "active": active,
            "context_patched_this_call": context_patched,
            "staged_valve_patched_this_call": valve_patched,
            "last_evaluation": dict(_LAST),
            "settings": {
                "window_start_minutes": START_MINUTES,
                "window_end_minutes": END_MINUTES,
                "minimum_risk_score": MIN_RISK_SCORE,
                "minimum_scanner_signals": MIN_SCANNER_SIGNALS,
                "minimum_long_signals_when_available": MIN_LONG_SIGNALS,
                "starter_alloc_factor": getattr(starter, "ALLOC_FACTOR", None),
                "max_entries_per_day": getattr(starter, "MAX_ENTRIES_PER_DAY", None),
                "max_entries_per_cycle": getattr(starter, "MAX_ENTRIES_PER_CYCLE", None),
                "max_open_positions": getattr(starter, "MAX_OPEN_POSITIONS", None),
                "minimum_seconds_between_entries": MIN_SECONDS_BETWEEN_STARTERS,
                "first_position_minimum_pnl_pct": FIRST_POSITION_MIN_PNL_PCT,
                "maximum_combined_exposure_pct": MAX_COMBINED_EXPOSURE_PCT,
                "requires_different_sector_or_bucket_for_second": True,
                "non_neutral_passthrough_unchanged": True,
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
                "changes_normal_portfolio_position_cap": False,
                "changes_existing_starter_sizing": False,
                "changes_market_context_permission": True,
                "changes_neutral_starter_daily_limit": True,
                "bounded_staged_second_neutral_starter": True,
                "neutral_stage_applies_only_in_neutral_mode": True,
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
