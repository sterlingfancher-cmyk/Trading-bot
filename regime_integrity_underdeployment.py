"""Regime-integrity repair and underdeployment X-ray for paper trading.

Repairs:
- expands macro daily history when the legacy market engine requests 30 calendar days;
- recomputes the final regime after futures/breadth/metals score adjustments;
- exposes auditable risk-score and entry-floor ledgers;
- identifies long/short permission dead zones without granting new authority.

Paper-safe: this module does not place orders, change live/ML authority, lower entry
thresholds, or add a risk-off long exception.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import threading
import time
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "regime-integrity-underdeployment-2026-07-29-v1"
MACRO_DAILY_PERIOD = os.environ.get("REGIME_INTEGRITY_MACRO_DAILY_PERIOD", "100d")
MIN_TREND_BARS = max(30, int(os.environ.get("REGIME_INTEGRITY_MIN_TREND_BARS", "30")))
WATCHDOG_FAST_ITERATIONS = max(1, int(os.environ.get("REGIME_INTEGRITY_FAST_WATCHDOG_ITERATIONS", "60")))
WATCHDOG_MAX_ITERATIONS = max(WATCHDOG_FAST_ITERATIONS, int(os.environ.get("REGIME_INTEGRITY_WATCHDOG_ITERATIONS", "1200")))

_MARKET_LOCK = threading.RLock()
_INSTALL_LOCK = threading.RLock()
_ORIGINAL_MARKET_STATUS: Any = None
_REGISTERED_APPS: set[int] = set()
_WATCHDOG_STARTED: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}
_LAST_MARKET_REPAIR: Dict[str, Any] = {}


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


def _state(core: Any) -> Dict[str, Any]:
    value = getattr(core, "portfolio", {})
    return value if isinstance(value, dict) else {}


def _trend_from_prices(core: Any, prices: Any) -> str:
    try:
        if len(prices) < MIN_TREND_BARS:
            return "unknown"
        return str(core.trend_state(prices))
    except Exception:
        return "unknown"


def _pct_change(core: Any, prices: Any, bars: int) -> float:
    try:
        return _f(core.pct_change(prices, bars))
    except Exception:
        return 0.0


def _mode_for_score(score: int, spy_trend: str) -> Tuple[str, str, str]:
    if score >= 70:
        return "risk_on", "aggressive", "bull"
    if score >= 55:
        return "constructive", "normal", "bull" if spy_trend == "up" else "neutral"
    if score >= 40:
        return "neutral", "reduced", "neutral"
    if score >= 25:
        return "risk_off", "defensive", "bear"
    return "crash_warning", "protective", "bear"


def _score_ledger(result: Dict[str, Any]) -> Tuple[int, List[Dict[str, Any]]]:
    score = 50
    rows: List[Dict[str, Any]] = [{"component": "starting_score", "delta": 50, "running_score": 50}]

    def add(component: str, delta: int, detail: str) -> None:
        nonlocal score
        score += int(delta)
        rows.append({
            "component": component,
            "delta": int(delta),
            "detail": detail,
            "running_score": int(max(0, min(100, score))),
        })

    spy_trend = str(result.get("spy_trend") or "unknown")
    qqq_trend = str(result.get("qqq_trend") or "unknown")
    vix_5d = _f(result.get("vix_5d_pct")) / 100.0
    rates_5d = _f(result.get("rates_5d_pct")) / 100.0
    spy_5d = _f(result.get("spy_5d_pct")) / 100.0
    qqq_5d = _f(result.get("qqq_5d_pct")) / 100.0

    if spy_trend == "up":
        add("spy_trend", 15, "SPY trend up")
    elif spy_trend == "down":
        add("spy_trend", -18, "SPY trend down")
    else:
        add("spy_trend", 0, f"SPY trend {spy_trend}")

    if qqq_trend == "up":
        add("qqq_trend", 12, "QQQ trend up")
    elif qqq_trend == "down":
        add("qqq_trend", -15, "QQQ trend down")
    else:
        add("qqq_trend", 0, f"QQQ trend {qqq_trend}")

    if vix_5d < -0.05:
        add("vix_5d", 10, f"VIX 5d {vix_5d * 100:.2f}%")
    elif vix_5d > 0.08:
        add("vix_5d", -15, f"VIX 5d {vix_5d * 100:.2f}%")
    else:
        add("vix_5d", 0, f"VIX 5d {vix_5d * 100:.2f}%")

    if qqq_5d > spy_5d:
        add("qqq_relative_to_spy", 5, "QQQ outperformed SPY over 5d")
    else:
        add("qqq_relative_to_spy", -3, "QQQ did not outperform SPY over 5d")

    if rates_5d > 0.05 and qqq_5d < 0:
        add("rates_and_tech", -6, f"rates 5d {rates_5d * 100:.2f}% with QQQ negative")
    else:
        add("rates_and_tech", 0, f"rates 5d {rates_5d * 100:.2f}%")

    if bool(result.get("growth_leadership")):
        add("growth_leadership", 5, "at least one risk-on sector among top leaders")
    else:
        add("growth_leadership", 0, "growth leadership not confirmed")

    if bool(result.get("defensive_leadership")):
        add("defensive_leadership", -5, "at least two defensive sectors among top leaders")
    else:
        add("defensive_leadership", 0, "defensive leadership not confirmed")

    futures = _d(result.get("futures_bias"))
    if futures.get("action") in {"block_opening_longs", "tech_caution"}:
        add("futures_confirmation", -5, str(futures.get("action")))
    elif futures.get("bias") == "bullish":
        add("futures_confirmation", 3, "bullish futures")
    else:
        add("futures_confirmation", 0, str(futures.get("action") or futures.get("bias") or "neutral"))

    breadth = _d(result.get("breadth"))
    if breadth.get("action") in {"reduce_aggression", "tech_caution"}:
        add("breadth_confirmation", -3, str(breadth.get("action")))
    elif breadth.get("state") == "supportive":
        add("breadth_confirmation", 2, "supportive breadth")
    else:
        add("breadth_confirmation", 0, str(breadth.get("action") or breadth.get("state") or "neutral"))

    metals = _d(result.get("precious_metals"))
    if metals.get("action") == "allow_defensive_metals" and bool(result.get("broad_market_soft")):
        add("defensive_metals_confirmation", -2, "defensive metals bid with soft broad market")
    else:
        add("defensive_metals_confirmation", 0, str(metals.get("action") or "neutral"))

    return int(max(0, min(100, score))), rows


def _repair_market_result(core: Any, result: Dict[str, Any], capture: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    global _LAST_MARKET_REPAIR
    out = dict(result or {})

    for symbol, field in (("SPY", "spy_trend"), ("QQQ", "qqq_trend")):
        prices = capture.get(symbol, {}).get("prices")
        repaired = _trend_from_prices(core, prices) if prices is not None else "unknown"
        if repaired != "unknown":
            out[field] = repaired

    for symbol, field in (("SPY", "spy_5d_pct"), ("QQQ", "qqq_5d_pct"), ("^VIX", "vix_5d_pct"), ("^TNX", "rates_5d_pct")):
        prices = capture.get(symbol, {}).get("prices")
        if prices is not None and len(prices) > 5:
            out[field] = round(_pct_change(core, prices, 5) * 100.0, 2)

    spy_5d = _f(out.get("spy_5d_pct")) / 100.0
    qqq_5d = _f(out.get("qqq_5d_pct")) / 100.0
    vix_5d = _f(out.get("vix_5d_pct")) / 100.0
    spy_trend = str(out.get("spy_trend") or "unknown")
    qqq_trend = str(out.get("qqq_trend") or "unknown")

    broad_market_soft = spy_5d <= 0 or qqq_5d <= 0
    defensive_rotation = bool(
        _i(out.get("defensive_count")) >= 2
        and not bool(out.get("growth_leadership"))
        and broad_market_soft
    )
    bear_tests = {
        "spy_trend_down": spy_trend == "down",
        "qqq_trend_down": qqq_trend == "down",
        "spy_5d_negative": spy_5d < 0,
        "qqq_5d_negative": qqq_5d < 0,
        "vix_5d_positive": vix_5d > 0,
    }
    bear_confirmed = all(bear_tests.values())

    out["broad_market_soft"] = broad_market_soft
    out["defensive_rotation"] = defensive_rotation
    out["bear_confirmed"] = bear_confirmed

    preliminary_mode = str(out.get("market_mode") or "unknown")
    preliminary_score = _i(out.get("risk_score"), 0)
    final_score, ledger = _score_ledger(out)
    final_mode, trade_permission, regime = _mode_for_score(final_score, spy_trend)

    if bear_confirmed:
        final_mode, trade_permission, regime = "risk_off", "short_bias", "bear"
    elif defensive_rotation:
        final_mode, trade_permission, regime = "defensive_rotation", "defensive_pause", "defensive"

    out["risk_score"] = final_score
    out["market_mode"] = final_mode
    out["trade_permission"] = trade_permission
    out["regime"] = regime

    counts = {
        symbol: {
            "bar_count": _i(row.get("bar_count")),
            "trend_ready": _i(row.get("bar_count")) >= MIN_TREND_BARS,
            "requested_period": row.get("requested_period"),
            "effective_period": row.get("effective_period"),
        }
        for symbol, row in capture.items()
    }
    integrity = {
        "version": VERSION,
        "generated_local": _now(core),
        "macro_daily_period": MACRO_DAILY_PERIOD,
        "minimum_trend_bars": MIN_TREND_BARS,
        "macro_data_coverage": counts,
        "preliminary_risk_score": preliminary_score,
        "final_risk_score": final_score,
        "preliminary_market_mode": preliminary_mode,
        "final_market_mode": final_mode,
        "final_trade_permission": trade_permission,
        "final_regime": regime,
        "risk_score_components": ledger,
        "bear_confirmation_tests": bear_tests,
        "bear_confirmed": bear_confirmed,
        "defensive_rotation": defensive_rotation,
        "permission_dead_zone_expected": bool(final_mode == "risk_off" and not bear_confirmed),
        "notes": [
            "Final market mode is recomputed after futures, breadth, and precious-metals adjustments.",
            "Risk-off shorts require genuine bear confirmation; no risk-off long exception was added.",
        ],
    }
    out["regime_integrity"] = integrity
    _LAST_MARKET_REPAIR = integrity

    try:
        state = _state(core)
        state["last_market"] = out
        state["regime_integrity"] = integrity
    except Exception:
        pass
    return out


def _make_market_wrapper(core: Any, prior: Any):
    def wrapped_market_status(force: bool = False):
        with _MARKET_LOCK:
            capture: Dict[str, Dict[str, Any]] = {}
            original_download = getattr(core, "download_prices", None)

            def extended_download(symbol: str, period: str = "5d", interval: str = "5m"):
                effective_period = MACRO_DAILY_PERIOD if interval == "1d" and period == "30d" else period
                df = original_download(symbol, period=effective_period, interval=interval)
                if interval == "1d" and symbol in set(getattr(core, "MACRO_SYMBOLS", []) or []):
                    try:
                        prices = core.price_series(df, "Close")
                        capture[str(symbol)] = {
                            "prices": prices,
                            "bar_count": len(prices),
                            "requested_period": period,
                            "effective_period": effective_period,
                        }
                    except Exception:
                        capture[str(symbol)] = {
                            "prices": [],
                            "bar_count": 0,
                            "requested_period": period,
                            "effective_period": effective_period,
                        }
                return df

            try:
                if callable(original_download):
                    core.download_prices = extended_download
                result = prior(force=True)
            finally:
                if callable(original_download):
                    core.download_prices = original_download

            repaired = _repair_market_result(core, _d(result), capture)
            try:
                cache = getattr(core, "_market_cache", None)
                if isinstance(cache, dict):
                    cache["ts"] = time.time()
                    cache["data"] = repaired
            except Exception:
                pass
            return repaired

    wrapped_market_status._regime_integrity_guard = True
    wrapped_market_status._regime_integrity_version = VERSION
    wrapped_market_status._regime_integrity_prior = prior
    return wrapped_market_status


def _stop_losses_today(core: Any) -> int:
    try:
        rows = core.trades_for_date(core.today_key())
        return sum(
            1 for row in rows
            if isinstance(row, dict)
            and str(row.get("action") or "").lower() == "exit"
            and str(row.get("exit_reason") or row.get("reason") or "").lower() == "stop_loss"
        )
    except Exception:
        return 0


def entry_floor_ledger(core: Any, market: Dict[str, Any], side: str = "long") -> Dict[str, Any]:
    side = str(side or "long").lower()
    mode = str(market.get("market_mode") or "neutral")
    if side == "short":
        base = _f(getattr(core, "MIN_SHORT_ENTRY_SCORE", 0.0))
    elif mode == "risk_on":
        base = _f(getattr(core, "MIN_ENTRY_SCORE_RISK_ON", 0.0))
    elif mode == "constructive":
        base = _f(getattr(core, "MIN_ENTRY_SCORE_CONSTRUCTIVE", 0.0))
    elif mode == "neutral":
        base = _f(getattr(core, "MIN_ENTRY_SCORE_NEUTRAL", 0.0))
    else:
        base = _f(getattr(core, "MIN_ENTRY_SCORE_DEFENSIVE", 0.0))

    rows: List[Dict[str, Any]] = [{"component": "base", "delta": round(base, 6), "running_floor": round(base, 6)}]
    running = base

    def add(component: str, delta: float, detail: str) -> None:
        nonlocal running
        running += delta
        rows.append({
            "component": component,
            "delta": round(delta, 6),
            "detail": detail,
            "running_floor": round(running, 6),
        })

    if side != "short":
        try:
            rp = core.get_realized_pnl()
        except Exception:
            rp = {}
        losses_today = _i(_d(rp).get("losses_today"))
        loss_delta = min(losses_today, 1) * _f(getattr(core, "ENTRY_SCORE_LOSS_STEP", 0.0))
        add("losses_today", loss_delta, f"{losses_today} losing exits today")

        stops = _stop_losses_today(core)
        stop_delta = _f(getattr(core, "POST_STOP_SCORE_BUMP", 0.0)) if stops >= 1 else 0.0
        add("post_stop", stop_delta, f"{stops} stop-loss exits today")

        vix_delta = _f(getattr(core, "VIX_RISING_SCORE_BUMP", 0.0)) if _f(market.get("vix_5d_pct")) > 0 else 0.0
        add("vix_rising", vix_delta, f"VIX 5d {_f(market.get('vix_5d_pct')):.2f}%")

        rates_delta = _f(getattr(core, "RATES_RISING_SCORE_BUMP", 0.0)) if _f(market.get("rates_5d_pct")) > 1.0 else 0.0
        add("rates_rising", rates_delta, f"rates 5d {_f(market.get('rates_5d_pct')):.2f}%")

        futures = _d(market.get("futures_bias"))
        if futures.get("action") in {"reduce_aggression", "tech_caution", "gap_chase_protection"}:
            futures_delta = _f(getattr(core, "FUTURES_SCORE_BUMP_CAUTION", 0.0))
        elif futures.get("action") == "block_opening_longs":
            futures_delta = _f(getattr(core, "FUTURES_SCORE_BUMP_BEARISH", 0.0))
        else:
            futures_delta = 0.0
        add("futures", futures_delta, str(futures.get("action") or futures.get("bias") or "neutral"))

        breadth = _d(market.get("breadth"))
        try:
            tech = _d(core.tech_leadership_status(market))
        except Exception:
            tech = {}
        if breadth.get("action") in {"reduce_aggression", "tech_caution"}:
            breadth_delta = (
                _f(getattr(core, "TECH_LEADERSHIP_BREADTH_SCORE_BUMP", 0.0))
                if tech.get("active")
                else _f(getattr(core, "BREADTH_SCORE_BUMP_NARROW", 0.0))
            )
        else:
            breadth_delta = 0.0
        add("breadth", breadth_delta, str(breadth.get("action") or breadth.get("state") or "neutral"))

        relief = -_f(getattr(core, "TECH_LEADERSHIP_SCORE_RELIEF", 0.0)) if tech.get("active") else 0.0
        prior = running
        running = max(base, running + relief)
        rows.append({
            "component": "tech_leadership_relief",
            "delta": round(running - prior, 6),
            "detail": str(tech.get("state") or "inactive"),
            "running_floor": round(running, 6),
        })

    observed = None
    try:
        observed = _f(core.min_entry_score_for_market(market, side))
    except Exception:
        observed = None

    reconstructed = round(running, 6)
    external_delta = round((observed - reconstructed), 6) if observed is not None else None
    if external_delta is not None and abs(external_delta) > 0.0000005:
        rows.append({
            "component": "external_or_wrapper_adjustment",
            "delta": external_delta,
            "detail": "difference between reconstructed core floor and active observed floor",
            "running_floor": round(observed, 6),
        })

    feedback = _d(_state(core).get("feedback_loop"))
    restart = _d(feedback.get("controlled_restart"))
    restart_bump = _f(restart.get("score_bump"))
    restart_required = restart.get("required_long_score")
    return {
        "side": side,
        "market_mode": mode,
        "base_floor": round(base, 6),
        "core_reconstructed_floor": reconstructed,
        "active_observed_floor": round(observed, 6) if observed is not None else None,
        "external_or_wrapper_adjustment": external_delta,
        "controlled_restart_score_bump": round(restart_bump, 6),
        "controlled_restart_required_long_score": restart_required,
        "components": rows,
    }


def _symbol(row: Any) -> str:
    if isinstance(row, str):
        return row.upper().strip()
    if isinstance(row, dict):
        return str(row.get("symbol") or row.get("ticker") or "").upper().strip()
    return ""


def _candidate_rows(rows: Iterable[Any], blocked: List[Dict[str, Any]], rejected: List[Dict[str, Any]], permission_reason: str) -> List[Dict[str, Any]]:
    by_symbol: Dict[str, Dict[str, Any]] = {}
    for source in blocked + rejected:
        if not isinstance(source, dict):
            continue
        sym = _symbol(source)
        if sym and sym not in by_symbol:
            by_symbol[sym] = source

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        sym = _symbol(raw)
        if not sym or sym in seen:
            continue
        seen.add(sym)
        base = dict(raw) if isinstance(raw, dict) else {"symbol": sym}
        evidence = by_symbol.get(sym, {})
        reason = (
            evidence.get("reason")
            or evidence.get("quality_reason")
            or evidence.get("entry_block_reason")
            or permission_reason
            or "no stored candidate-specific blocker"
        )
        out.append({
            "symbol": sym,
            "side": base.get("side"),
            "score": base.get("score"),
            "rank_score": base.get("core_entry_rank_score") or base.get("rank_score"),
            "bucket": base.get("bucket"),
            "entry_context": base.get("entry_context"),
            "definitive_blocker": reason,
            "blocker_evidence": evidence,
        })
        if len(out) >= 12:
            break
    return out


def build_underdeployment_xray(core: Any, force_market: bool = False) -> Dict[str, Any]:
    state = _state(core)
    market = _d(core.market_status(force=force_market))
    try:
        params = _d(core.apply_aggression_adjustments(core.risk_parameters(market), market))
    except Exception:
        params = _d(core.risk_parameters(market))
    risk = _d(state.get("risk_controls"))
    feedback = _d(state.get("feedback_loop"))
    auto = _d(state.get("auto_runner"))
    last = _d(auto.get("last_result"))
    scanner = _d(state.get("scanner_audit"))
    blocked = [row for row in (_l(last.get("blocked_entries")) or _l(scanner.get("blocked_entries"))) if isinstance(row, dict)]
    rejected = [row for row in (_l(last.get("rejected_signals")) or _l(scanner.get("rejected_signals"))) if isinstance(row, dict)]

    long_signals = _l(last.get("long_signals")) or _l(scanner.get("long_signals"))
    short_signals = _l(last.get("short_signals")) or _l(scanner.get("short_signals"))
    allow_longs = bool(params.get("allow_longs"))
    allow_shorts = bool(params.get("allow_shorts"))

    global_blockers: List[Dict[str, Any]] = []
    if risk.get("halted"):
        global_blockers.append({"code": "risk_halted", "detail": risk.get("halt_reason")})
    if feedback.get("block_new_entries"):
        global_blockers.append({"code": "feedback_blocks_entries", "detail": feedback.get("reasons")})
    if not allow_longs:
        global_blockers.append({"code": "longs_disabled_by_regime", "detail": market.get("market_mode")})
    if not allow_shorts:
        global_blockers.append({
            "code": "shorts_disabled_by_regime",
            "detail": "bear confirmation required" if market.get("market_mode") == "risk_off" else market.get("market_mode"),
        })

    long_reason = "longs_disabled_by_regime" if not allow_longs else ""
    short_reason = "shorts_disabled_until_bear_confirmed" if not allow_shorts else ""
    dead_zone = not allow_longs and not allow_shorts

    integrity = _d(market.get("regime_integrity"))
    return {
        "status": "ok",
        "overall": "warn" if dead_zone or global_blockers else "pass",
        "type": "underdeployment_xray",
        "version": VERSION,
        "generated_local": _now(core),
        "authority": {
            "paper_only": True,
            "places_orders_directly": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "lowers_entry_thresholds": False,
            "adds_risk_off_long_exception": False,
        },
        "account": {
            "cash": round(_f(state.get("cash")), 2),
            "equity": round(_f(state.get("equity")), 2),
            "open_positions_count": len(_d(state.get("positions"))),
            "scanner_signals_found": _i(scanner.get("signals_found")),
            "latest_cycle_entries": len(_l(last.get("entries"))),
        },
        "market_integrity": integrity,
        "market": {
            "market_mode": market.get("market_mode"),
            "regime": market.get("regime"),
            "trade_permission": market.get("trade_permission"),
            "risk_score": market.get("risk_score"),
            "spy_trend": market.get("spy_trend"),
            "qqq_trend": market.get("qqq_trend"),
            "spy_5d_pct": market.get("spy_5d_pct"),
            "qqq_5d_pct": market.get("qqq_5d_pct"),
            "vix_5d_pct": market.get("vix_5d_pct"),
            "rates_5d_pct": market.get("rates_5d_pct"),
            "sector_leaders": market.get("sector_leaders"),
            "bear_confirmed": market.get("bear_confirmed"),
            "defensive_rotation": market.get("defensive_rotation"),
            "breadth": market.get("breadth"),
            "futures_bias": market.get("futures_bias"),
        },
        "permission_snapshot": {
            "allow_longs": allow_longs,
            "allow_shorts": allow_shorts,
            "max_positions": params.get("max_positions"),
            "long_alloc_pct": params.get("long_alloc_pct"),
            "short_alloc_pct": params.get("short_alloc_pct"),
            "permission_dead_zone": dead_zone,
            "dead_zone_classification": (
                "deliberate_defensive_pause_unconfirmed_bear"
                if dead_zone and market.get("market_mode") == "risk_off" and not market.get("bear_confirmed")
                else "none"
            ),
        },
        "entry_floor_ledger": {
            "long": entry_floor_ledger(core, market, "long"),
            "short": entry_floor_ledger(core, market, "short"),
        },
        "top_long_candidates": _candidate_rows(long_signals, blocked, rejected, long_reason),
        "top_short_candidates": _candidate_rows(short_signals, blocked, rejected, short_reason),
        "global_blockers": global_blockers,
        "diagnosis": {
            "primary_driver": (
                "risk_off_permission_dead_zone"
                if dead_zone
                else "stored_entry_guards_or_score_floor"
                if blocked or rejected
                else "no_current_global_permission_block"
            ),
            "macro_history_repaired": bool(integrity.get("macro_data_coverage")),
            "final_mode_recomputed_after_confirmation_layers": integrity.get("final_market_mode") == market.get("market_mode"),
            "bear_short_permission_expected": bool(market.get("bear_confirmed") and market.get("market_mode") == "risk_off"),
        },
    }


def status_payload(core: Any) -> Dict[str, Any]:
    fn = getattr(core, "market_status", None)
    active = bool(getattr(fn, "_regime_integrity_guard", False))
    market = _d(_state(core).get("last_market"))
    return {
        "status": "ok" if active else "warn",
        "overall": "pass" if active else "warn",
        "type": "regime_integrity_status",
        "version": VERSION,
        "generated_local": _now(core),
        "market_guard_active": active,
        "market_callable": getattr(fn, "__qualname__", None),
        "last_install": dict(_LAST_INSTALL),
        "last_market_repair": _d(market.get("regime_integrity")) or dict(_LAST_MARKET_REPAIR),
        "authority": {
            "paper_only": True,
            "places_orders_directly": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "lowers_thresholds": False,
        },
    }


def install(core: Any) -> Dict[str, Any]:
    global _ORIGINAL_MARKET_STATUS, _LAST_INSTALL
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}

    with _INSTALL_LOCK:
        current = getattr(core, "market_status", None)
        patched = False
        if callable(current) and not getattr(current, "_regime_integrity_guard", False):
            _ORIGINAL_MARKET_STATUS = current
            core.market_status = _make_market_wrapper(core, current)
            patched = True
            try:
                cache = getattr(core, "_market_cache", None)
                if isinstance(cache, dict):
                    cache["ts"] = 0
                    cache["data"] = None
            except Exception:
                pass

        try:
            setattr(core, "REGIME_INTEGRITY_UNDERDEPLOYMENT_VERSION", VERSION)
        except Exception:
            pass

        active_fn = getattr(core, "market_status", None)
        _LAST_INSTALL = {
            "status": "ok",
            "version": VERSION,
            "generated_local": _now(core),
            "patched_this_call": patched,
            "market_guard_active": bool(getattr(active_fn, "_regime_integrity_guard", False)),
            "market_callable": getattr(active_fn, "__qualname__", None),
            "macro_daily_period": MACRO_DAILY_PERIOD,
            "minimum_trend_bars": MIN_TREND_BARS,
        }
        return dict(_LAST_INSTALL)


def register_routes(flask_app: Any, core: Any) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    install(core)
    if id(flask_app) in _REGISTERED_APPS:
        return {"status": "ok", "version": VERSION, "already_registered": True}

    from flask import jsonify, request

    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    routes: List[str] = []
    if "/paper/regime-integrity-status" not in existing:
        flask_app.add_url_rule(
            "/paper/regime-integrity-status",
            "regime_integrity_status",
            lambda: jsonify(status_payload(core)),
        )
        routes.append("/paper/regime-integrity-status")
    if "/paper/underdeployment-xray" not in existing:
        flask_app.add_url_rule(
            "/paper/underdeployment-xray",
            "underdeployment_xray",
            lambda: jsonify(build_underdeployment_xray(
                core,
                force_market=str(request.args.get("force", "0")).lower() in {"1", "true", "yes", "on"},
            )),
        )
        routes.append("/paper/underdeployment-xray")

    _REGISTERED_APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": routes}


def start_watchdog(core: Any) -> Dict[str, Any]:
    install(core)
    flask_app = getattr(core, "app", None)
    if flask_app is not None:
        register_routes(flask_app, core)
    if core is None or id(core) in _WATCHDOG_STARTED:
        return {
            "status": "ok",
            "version": VERSION,
            "watchdog_started": core is not None and id(core) in _WATCHDOG_STARTED,
        }

    _WATCHDOG_STARTED.add(id(core))

    def watch() -> None:
        for iteration in range(WATCHDOG_MAX_ITERATIONS):
            try:
                install(core)
            except Exception as exc:
                try:
                    import runtime_diagnostics
                    runtime_diagnostics.record_exception(
                        exc,
                        source="regime_integrity_underdeployment.watchdog",
                        module=__name__,
                    )
                except Exception:
                    pass
            time.sleep(0.5 if iteration < WATCHDOG_FAST_ITERATIONS else 30.0)

    threading.Thread(
        target=watch,
        daemon=True,
        name="regime-integrity-underdeployment-watchdog",
    ).start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}
