"""Performance audit laboratory for the paper trading system.

This module restores evidence-based evaluation without granting trading authority.
It provides:
- a runtime audit of every material threshold, timing gate, capacity limit, sizing
  reduction, and wrapper layer that can suppress performance;
- historical policy-proxy backtests for current, balanced, and permissive profiles;
- rolling walk-forward optimization/evaluation using out-of-sample folds;
- a forward shadow test that records what the current, balanced, and permissive
  policies would have accepted, then measures subsequent price outcomes;
- automated after-hours refreshes and compact diagnostic routes.

The historical simulations are policy proxies, not a claim of exact intraday fill
replay. They are designed to answer whether the system is losing too much
participation through compounded restrictions before any production thresholds
are changed.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except Exception:  # pragma: no cover
    np = None
    pd = None
    yf = None

VERSION = "performance-audit-lab-2026-09-03-v2-forward-integrity"
ENABLED = os.environ.get("PERFORMANCE_AUDIT_LAB_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
AUTO_BACKTEST = os.environ.get("PERFORMANCE_AUDIT_AUTO_BACKTEST_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
AUTO_BACKTEST_STALE_HOURS = float(os.environ.get("PERFORMANCE_AUDIT_BACKTEST_STALE_HOURS", "24"))
AUTO_BACKTEST_MAX_SYMBOLS = int(os.environ.get("PERFORMANCE_AUDIT_BACKTEST_MAX_SYMBOLS", "35"))
AUTO_BACKTEST_PERIOD = os.environ.get("PERFORMANCE_AUDIT_BACKTEST_PERIOD", "2y")
FORWARD_MAX_ROWS = int(os.environ.get("PERFORMANCE_AUDIT_FORWARD_MAX_ROWS", "1200"))
FORWARD_MAX_NEW_PER_CYCLE = int(os.environ.get("PERFORMANCE_AUDIT_FORWARD_MAX_NEW_PER_CYCLE", "12"))
FORWARD_RESOLVE_PER_CYCLE = int(os.environ.get("PERFORMANCE_AUDIT_FORWARD_RESOLVE_PER_CYCLE", "24"))
WATCHDOG_SECONDS = int(os.environ.get("PERFORMANCE_AUDIT_WATCHDOG_SECONDS", "300"))
TRANSACTION_COST_BPS = float(os.environ.get("PERFORMANCE_AUDIT_TRANSACTION_COST_BPS", "8"))
INITIAL_CAPITAL = float(os.environ.get("PERFORMANCE_AUDIT_INITIAL_CAPITAL", "10000"))

try:
    from paper_exit_price_integrity_guard import (
        SOURCE_MAX_PRICE_RATIO as FORWARD_MAX_PRICE_RATIO,
        SOURCE_MIN_PRICE_RATIO as FORWARD_MIN_PRICE_RATIO,
    )
except Exception:  # pragma: no cover - the runtime guard is a required dependency
    FORWARD_MIN_PRICE_RATIO = 0.40
    FORWARD_MAX_PRICE_RATIO = 2.50

_LOCK = threading.RLock()
_BACKTEST_LOCK = threading.Lock()
_REGISTERED: set[int] = set()
_WATCHDOGS: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}

HARD_BLOCK_TOKENS = (
    "risk_halted", "halted", "hard_halt", "self_defense", "daily_loss",
    "intraday_drawdown", "cooldown", "already_held", "missing_price", "no_price",
    "futures_block_opening_longs", "futures_bias_block_opening_longs", "bear",
    "crash", "risk_off", "market_closed", "late_day_entry_cutoff",
)
SOFT_BLOCK_TOKENS = (
    "entry_score_below_minimum", "opening_warmup", "fvg", "reclaim", "vwap",
    "ema", "extension", "extended", "chase", "rank", "relative_strength",
    "volume_not_confirmed", "trend_not_confirmed", "sector_alignment",
)

AUDIT_MODULES = (
    "app", "core_entry_pipeline", "risk_on_starter_participation_valve",
    "neutral_momentum_starter_extension", "neutral_late_session_participation",
    "performance_risk_calibration", "paper_participation_allocator",
    "paper_underdeployment_repair", "market_extension_guard", "risk_reward_structure",
    "paper_controlled_expansion", "market_surge_aggression",
    "market_surge_deployment_mode", "market_participation_accelerator",
    "breakout_participation_layer", "opening_surge_participation",
    "opening_surge_score_calibration", "intraday_timing", "live_volatility",
    "position_quality_governor", "loss_streak_defensive_governor",
    "relative_strength_leader_exception", "fundamental_valuation_risk_layer",
    "research_advisory_engine", "news_sentiment_engine", "pattern_recognition_layer",
    "multi_timeframe_swing", "benchmark_participation", "eod_hybrid",
)

AUDIT_NAME_TOKENS = (
    "MIN_", "MAX_", "SCORE", "THRESHOLD", "FLOOR", "LIMIT", "CUTOFF",
    "WARMUP", "COOLDOWN", "ALLOC", "EXPOSURE", "POSITION", "ENTRIES",
    "DRAWNDOWN", "DRAWDOWN", "LOSS", "PROFIT", "RISK", "WINDOW",
    "SPACING", "REDUCTION", "FACTOR", "REQUIRE", "BLOCK", "ENABLED",
)

PROFILES: Dict[str, Dict[str, Any]] = {
    "current_proxy": {
        "score_floor": 0.0140,
        "score_candidates": [0.0120, 0.0140, 0.0160, 0.0180],
        "min_confirmations": 5,
        "min_volume_ratio": 1.00,
        "min_relative_strength": 0.000,
        "require_ma50": True,
        "max_positions": 2,
        "target_allocation": 0.18,
        "stop_loss": 0.012,
        "max_hold_days": 7,
        "rebalance_days": 2,
        "description": "Tight policy proxy approximating compounded current entry requirements.",
    },
    "balanced": {
        "score_floor": 0.0090,
        "score_candidates": [0.0070, 0.0090, 0.0110, 0.0130],
        "min_confirmations": 3,
        "min_volume_ratio": 0.75,
        "min_relative_strength": -0.010,
        "require_ma50": False,
        "max_positions": 4,
        "target_allocation": 0.16,
        "stop_loss": 0.015,
        "max_hold_days": 10,
        "rebalance_days": 2,
        "description": "Moderate-aggressive participation profile that keeps trend and risk controls.",
    },
    "permissive": {
        "score_floor": 0.0060,
        "score_candidates": [0.0040, 0.0060, 0.0080, 0.0100],
        "min_confirmations": 2,
        "min_volume_ratio": 0.55,
        "min_relative_strength": -0.025,
        "require_ma50": False,
        "max_positions": 6,
        "target_allocation": 0.12,
        "stop_loss": 0.018,
        "max_hold_days": 12,
        "rebalance_days": 1,
        "description": "High-participation research profile used to quantify opportunity cost.",
    },
}

HORIZONS = {
    "one_hour": 3600,
    "same_session": int(6.5 * 3600),
    "one_day": 86400,
    "three_days": 3 * 86400,
    "five_days": 5 * 86400,
}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        out = float(value)
        return default if math.isnan(out) or math.isinf(out) else out
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _b(value: Any) -> bool:
    return bool(value)


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "portfolio"):
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "portfolio"):
            return mod
    return None


def _now_dt(core: Any = None) -> dt.datetime:
    try:
        value = core.now_local()
        if isinstance(value, dt.datetime):
            return value
    except Exception:
        pass
    return dt.datetime.now()


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return _now_dt(core).strftime("%Y-%m-%d %H:%M:%S")


def _portfolio(core: Any) -> Dict[str, Any]:
    return _d(getattr(core, "portfolio", {}))


def _section(core: Any) -> Dict[str, Any]:
    section = _portfolio(core).setdefault("performance_audit_lab", {})
    if not isinstance(section, dict):
        section = {}
        _portfolio(core)["performance_audit_lab"] = section
    section["version"] = VERSION
    return section


def _save(core: Any) -> None:
    try:
        fn = getattr(core, "save_state", None)
        if callable(fn):
            fn(_portfolio(core))
    except Exception:
        pass


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
        return {str(k): _json_safe(v, depth + 1) for k, v in list(value.items())[:150] if not callable(v)}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, depth + 1) for v in list(value)[:150]]
    return str(value)


def _callable_chain(fn: Any) -> List[Dict[str, Any]]:
    attrs = (
        "__wrapped__", "_paper_underdeployment_prior", "_paper_participation_original",
        "_neutral_momentum_staged_prior", "_neutral_momentum_starter_extension_prior",
        "_risk_on_starter_participation_prior", "_participation_valve_prior",
        "_entry_pipeline_xray_prior", "_bear_recovery_prior", "_original",
    )
    queue = [fn]
    seen: set[int] = set()
    rows: List[Dict[str, Any]] = []
    while queue and len(rows) < 40:
        item = queue.pop(0)
        if not callable(item) or id(item) in seen:
            continue
        seen.add(id(item))
        rows.append({
            "module": getattr(item, "__module__", None),
            "name": getattr(item, "__name__", None),
            "qualname": getattr(item, "__qualname__", None),
            "version_markers": {
                key: _json_safe(getattr(item, key))
                for key in dir(item)
                if key.startswith("_") and key.endswith("version") and not callable(getattr(item, key, None))
            },
        })
        for attr in attrs:
            linked = getattr(item, attr, None)
            if callable(linked):
                queue.append(linked)
    return rows


def _restriction_kind(name: str, value: Any) -> str:
    upper = name.upper()
    if "ALLOC" in upper or "REDUCTION" in upper or upper.endswith("FACTOR"):
        return "sizing"
    if any(token in upper for token in ("WINDOW", "MINUTES", "CUTOFF", "WARMUP", "COOLDOWN", "SPACING")):
        return "timing"
    if any(token in upper for token in ("MAX_POSITION", "MAX_ENTRIES", "EXPOSURE", "CASH_PCT")):
        return "capacity"
    if any(token in upper for token in ("SCORE", "FLOOR", "THRESHOLD", "MIN_RISK", "MIN_VOLUME", "MIN_RELATIVE")):
        return "quality_threshold"
    if any(token in upper for token in ("HALT", "BLOCK", "LOSS", "DRAWDOWN", "PROFIT_GUARD")):
        return "risk_gate"
    if isinstance(value, bool):
        return "feature_toggle"
    return "other"


def _restriction_direction(name: str, value: Any) -> str:
    upper = name.upper()
    if isinstance(value, bool):
        return "enabled" if value else "disabled"
    if "MAX_" in upper or "CUTOFF" in upper or "LIMIT" in upper:
        return "upper_bound"
    if "MIN_" in upper or "FLOOR" in upper or "THRESHOLD" in upper:
        return "lower_bound"
    if "REDUCTION" in upper or "FACTOR" in upper or "ALLOC" in upper:
        return "multiplier_or_target"
    return "configured"


def _restriction_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for module_name in AUDIT_MODULES:
        try:
            mod = __import__(module_name)
        except Exception:
            continue
        for name in sorted(dir(mod)):
            if name.startswith("_") or not name.isupper() or not any(token in name for token in AUDIT_NAME_TOKENS):
                continue
            try:
                value = getattr(mod, name)
            except Exception:
                continue
            if callable(value) or isinstance(value, (dict, list, tuple, set)) and len(value) > 40:
                continue
            if isinstance(value, (str, int, float, bool, type(None), tuple, list, set)):
                rows.append({
                    "module": module_name,
                    "name": name,
                    "value": _json_safe(value),
                    "kind": _restriction_kind(name, value),
                    "direction": _restriction_direction(name, value),
                })
    return rows


def _factor_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    factors: List[Dict[str, Any]] = []
    for row in rows:
        name = str(row.get("name") or "")
        value = row.get("value")
        if not isinstance(value, (int, float)):
            continue
        number = float(value)
        if 0 < number < 1 and any(token in name for token in ("FACTOR", "REDUCTION", "ALLOC_FACTOR")):
            factors.append({**row, "numeric_value": number})
    return sorted(factors, key=lambda r: r["numeric_value"])


def _rejection_history(core: Any) -> Dict[str, Any]:
    state = _portfolio(core)
    counts: Counter[str] = Counter()
    examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def add(row: Any) -> None:
        if not isinstance(row, dict):
            return
        nested = _d(row.get("quality_info"))
        valve = _d(row.get("participation_valve"))
        repair = _d(row.get("paper_underdeployment_repair"))
        reason = str(
            repair.get("reason") or row.get("final_reason") or row.get("reason")
            or nested.get("reason") or valve.get("reason") or "unknown"
        )
        counts[reason] += 1
        if len(examples[reason]) < 3:
            examples[reason].append({
                "symbol": row.get("symbol"), "score": row.get("score"),
                "rank_score": row.get("rank_score") or row.get("core_entry_rank_score"),
                "reason": reason,
            })

    for key in ("blocked_entries", "recent_blocked_entries", "entry_rejections", "rejected_candidates"):
        for row in _l(_d(state.get("decision_audit")).get(key)):
            add(row)
    for row in _l(_d(state.get("blocked_entry_reason_audit")).get("recent")):
        add(row)
    for row in _l(_d(_d(state.get("paper_underdeployment_repair")).get("last_candidate_cycle")).get("top_rejected_candidates")):
        add(row)
    for row in _l(_d(state.get("core_entry_pipeline")).get("participation_valve_attempts")):
        add(row)
    return {
        "total_observations": sum(counts.values()),
        "reason_counts": dict(counts.most_common(30)),
        "examples": {k: v for k, v in list(examples.items())[:30]},
    }


def _active_market(core: Any) -> Dict[str, Any]:
    state = _portfolio(core)
    market: Dict[str, Any] = {}
    for source in (_d(_d(state.get("auto_runner")).get("last_result")), _d(state.get("last_market"))):
        for key, value in source.items():
            market.setdefault(key, value)
    return market


def restriction_audit(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is None:
        return {"status": "pending", "type": "performance_restriction_audit", "version": VERSION, "reason": "core_missing"}
    rows = _restriction_rows()
    factors = _factor_rows(rows)
    factor_product = 1.0
    for row in factors[:12]:
        factor_product *= float(row["numeric_value"])
    wrappers: Dict[str, Any] = {}
    for name in (
        "scan_signals", "try_entries_and_rotations", "entry_quality_check", "enter_position",
        "min_entry_score_for_market", "apply_aggression_adjustments", "manage_exits",
    ):
        fn = getattr(core, name, None)
        chain = _callable_chain(fn) if callable(fn) else []
        wrappers[name] = {"depth": len(chain), "chain": chain}

    by_kind = Counter(str(row.get("kind")) for row in rows)
    toggles_enabled = sum(1 for row in rows if row.get("kind") == "feature_toggle" and row.get("value") is True)
    history = _rejection_history(core)
    market = _active_market(core)
    risk = _d(_portfolio(core).get("risk_controls"))
    feedback = _d(_portfolio(core).get("feedback_loop"))
    findings: List[Dict[str, Any]] = []

    max_depth_name, max_depth = max(
        ((name, _i(row.get("depth"))) for name, row in wrappers.items()),
        key=lambda pair: pair[1], default=("none", 0),
    )
    if max_depth >= 5:
        findings.append({
            "severity": "high", "finding": "deep_runtime_composition",
            "detail": f"{max_depth_name} has {max_depth} callable layers; interaction effects can suppress entries even when each layer passes independently.",
        })
    if len(factors) >= 5:
        findings.append({
            "severity": "high", "finding": "compounded_sizing_reductions",
            "detail": f"Detected {len(factors)} configured sub-1.0 sizing factors. Multiplying only the 12 smallest would leave {factor_product:.6f} of nominal size; actual paths use subsets, but the compounding risk is material.",
        })
    if _i(history.get("total_observations")) > 0:
        top_reason = next(iter(_d(history.get("reason_counts"))), None)
        findings.append({
            "severity": "high" if top_reason else "medium", "finding": "observed_entry_rejections",
            "detail": f"Runtime history contains {history['total_observations']} rejection observations; the most common recorded reason is {top_reason or 'unknown'}.",
        })
    if toggles_enabled >= 12:
        findings.append({
            "severity": "medium", "finding": "large_active_overlay_count",
            "detail": f"At least {toggles_enabled} restriction-related feature toggles are enabled across the audited modules.",
        })
    if bool(risk.get("self_defense_active")) or bool(feedback.get("block_new_entries")):
        findings.append({
            "severity": "current", "finding": "state_level_entry_block_active",
            "detail": str(risk.get("self_defense_reason") or feedback.get("reasons") or "entry block active"),
        })

    result = {
        "status": "ok", "type": "performance_restriction_audit", "version": VERSION,
        "generated_local": _now(core),
        "summary": {
            "audited_modules": len({row["module"] for row in rows}),
            "restriction_constants": len(rows),
            "sub_one_sizing_factors": len(factors),
            "enabled_feature_toggles": toggles_enabled,
            "maximum_callable_depth": max_depth,
            "maximum_callable_depth_function": max_depth_name,
            "historical_rejection_observations": history.get("total_observations"),
        },
        "market": {
            "market_mode": market.get("market_mode"), "risk_score": market.get("risk_score"),
            "signals_found": market.get("signals_found") or _d(_portfolio(core).get("scanner_audit")).get("signals_found"),
        },
        "risk_state": {
            "halted": risk.get("halted"), "self_defense_active": risk.get("self_defense_active"),
            "self_defense_reason": risk.get("self_defense_reason"),
            "profit_guard_active": risk.get("profit_guard_active"),
            "feedback_blocks_entries": feedback.get("block_new_entries"),
        },
        "restriction_counts_by_kind": dict(by_kind),
        "findings": findings,
        "wrapper_composition": wrappers,
        "smallest_sizing_factors": factors[:30],
        "rejection_history": history,
        "restriction_inventory": rows,
        "interpretation": {
            "exact_execution_replay": False,
            "why": "Several gates depend on intraday state, provider data, wrapper order, and portfolio history. The audit inventories them exactly; the historical tests below use policy proxies to quantify opportunity cost.",
        },
        "authority": {
            "advisory_only": True, "changes_strategy": False, "changes_thresholds": False,
            "changes_sizing": False, "places_orders": False, "changes_live_authority": False,
        },
    }
    _section(core)["last_restriction_audit"] = result
    _save(core)
    return result


# ---------------------------------------------------------------------------
# Historical policy-proxy backtest and rolling walk-forward evaluation
# ---------------------------------------------------------------------------

def _universe(core: Any, max_symbols: int) -> List[str]:
    symbols: List[str] = []
    for attr in ("UNIVERSE", "WATCHLIST", "STOCK_UNIVERSE", "DEFAULT_UNIVERSE"):
        value = getattr(core, attr, None)
        if isinstance(value, (list, tuple, set)):
            symbols.extend(str(x).upper().strip() for x in value if str(x).strip())
    try:
        import eod_hybrid
        symbols.extend(str(x).upper().strip() for x in getattr(eod_hybrid, "CORE_SYMBOLS", []) if str(x).strip())
    except Exception:
        pass
    preferred = [
        "SPY", "QQQ", "NVDA", "AMD", "AVGO", "MU", "MSFT", "AMZN", "META", "GOOGL",
        "PLTR", "DELL", "HPE", "ANET", "VRT", "GEV", "PWR", "STX", "WDC", "CIEN",
        "RKLB", "ASTS", "CIFR", "IREN", "CLSK", "MARA", "RIOT", "GLD", "SLV", "GDX",
        "XLE", "XLV", "IWM", "RSP", "IBIT",
    ]
    ordered = list(dict.fromkeys(preferred + symbols))
    excluded = {"^VIX", "^TNX", "ES=F", "NQ=F", "UUP"}
    return [s for s in ordered if s not in excluded][:max(8, max_symbols)]


def _download(symbols: Sequence[str], period: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if yf is None or pd is None or np is None:
        return {}, {"status": "dependency_missing", "dependencies": {"yfinance": yf is not None, "pandas": pd is not None, "numpy": np is not None}}
    data: Dict[str, Any] = {}
    errors: List[Dict[str, str]] = []
    try:
        raw = yf.download(
            tickers=list(symbols), period=period, interval="1d", auto_adjust=True,
            progress=False, threads=True, group_by="ticker",
        )
    except Exception as exc:
        raw = None
        errors.append({"scope": "batch", "error": f"{type(exc).__name__}: {exc}"})

    def normalize(frame: Any) -> Any:
        if frame is None or not hasattr(frame, "columns"):
            return None
        result = frame.copy()
        result.columns = [str(c).title() for c in result.columns]
        needed = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in result.columns]
        if "Close" not in needed:
            return None
        result = result[needed].dropna(subset=["Close"])
        if len(result) < 80:
            return None
        return result

    if raw is not None and hasattr(raw, "columns"):
        for symbol in symbols:
            frame = None
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    level0 = set(str(x) for x in raw.columns.get_level_values(0))
                    level1 = set(str(x) for x in raw.columns.get_level_values(1))
                    if symbol in level0:
                        frame = raw[symbol]
                    elif symbol in level1:
                        frame = raw.xs(symbol, axis=1, level=1)
                elif len(symbols) == 1:
                    frame = raw
            except Exception:
                frame = None
            normalized = normalize(frame)
            if normalized is not None:
                data[symbol] = normalized

    missing = [s for s in symbols if s not in data]
    for symbol in missing[:12]:
        try:
            frame = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
            normalized = normalize(frame)
            if normalized is not None:
                data[symbol] = normalized
        except Exception as exc:
            errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
    return data, {
        "status": "ok" if data else "no_data", "requested_symbols": len(symbols),
        "loaded_symbols": len(data), "missing_symbols": [s for s in symbols if s not in data],
        "errors": errors[:20],
    }


def _feature_frames(frames: Dict[str, Any]) -> Dict[str, Any]:
    if pd is None or np is None:
        return {}
    spy = frames.get("SPY")
    spy_ret20 = spy["Close"].pct_change(20) if spy is not None else None
    out: Dict[str, Any] = {}
    for symbol, frame in frames.items():
        df = frame.copy()
        close = df["Close"].astype(float)
        df["ret5"] = close.pct_change(5)
        df["ret20"] = close.pct_change(20)
        df["ret60"] = close.pct_change(60)
        df["ma20"] = close.rolling(20).mean()
        df["ma50"] = close.rolling(50).mean()
        df["vol20"] = close.pct_change().rolling(20).std() * np.sqrt(252)
        if "Volume" in df.columns:
            volume = df["Volume"].astype(float)
            df["volume_ratio"] = volume / volume.rolling(20).mean().replace(0, np.nan)
        else:
            df["volume_ratio"] = 1.0
        if spy_ret20 is not None:
            df["rs20"] = df["ret20"] - spy_ret20.reindex(df.index)
        else:
            df["rs20"] = 0.0
        if all(c in df.columns for c in ("High", "Low", "Close")):
            prev = close.shift(1)
            tr = pd.concat([(df["High"] - df["Low"]).abs(), (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1).max(axis=1)
            df["atr_pct"] = tr.rolling(14).mean() / close.replace(0, np.nan)
        else:
            df["atr_pct"] = close.pct_change().abs().rolling(14).mean()
        trend20 = (close > df["ma20"]).astype(float)
        trend50 = (close > df["ma50"]).astype(float)
        volume_bonus = (df["volume_ratio"].clip(0, 2.5) - 1.0).fillna(0.0) * 0.003
        df["score"] = (
            df["ret5"].fillna(0.0) * 0.34 + df["ret20"].fillna(0.0) * 0.30
            + df["ret60"].fillna(0.0) * 0.18 + df["rs20"].fillna(0.0) * 0.12
            + trend20 * 0.004 + trend50 * 0.003 + volume_bonus
        )
        df["confirmations"] = (
            (df["ret5"] > 0).astype(int) + (df["ret20"] > 0).astype(int)
            + (df["ret60"] > 0).astype(int) + (close > df["ma20"]).astype(int)
            + (close > df["ma50"]).astype(int) + (df["rs20"] > 0).astype(int)
            + (df["volume_ratio"] >= 1.0).astype(int)
        )
        out[symbol] = df.replace([np.inf, -np.inf], np.nan)
    return out


def _calendar(features: Dict[str, Any]) -> List[Any]:
    dates: set[Any] = set()
    for df in features.values():
        dates.update(df.index.tolist())
    return sorted(dates)


def _row(features: Dict[str, Any], symbol: str, date: Any) -> Dict[str, float] | None:
    df = features.get(symbol)
    if df is None or date not in df.index:
        return None
    try:
        raw = df.loc[date]
        if hasattr(raw, "iloc") and getattr(raw, "ndim", 1) > 1:
            raw = raw.iloc[-1]
        close = _f(raw.get("Close"), 0.0)
        if close <= 0:
            return None
        return {str(k): _f(raw.get(k), float("nan")) for k in raw.index}
    except Exception:
        return None


def _eligible(row: Dict[str, float], policy: Dict[str, Any], score_floor: float) -> bool:
    if not row or math.isnan(_f(row.get("score"), float("nan"))):
        return False
    if _f(row.get("score")) < score_floor:
        return False
    if _i(row.get("confirmations")) < _i(policy.get("min_confirmations")):
        return False
    if _f(row.get("volume_ratio"), 1.0) < _f(policy.get("min_volume_ratio"), 0.0):
        return False
    if _f(row.get("rs20"), 0.0) < _f(policy.get("min_relative_strength"), -1.0):
        return False
    if _f(row.get("Close")) <= _f(row.get("ma20"), 0.0):
        return False
    if policy.get("require_ma50") and _f(row.get("Close")) <= _f(row.get("ma50"), 0.0):
        return False
    return True


def _metrics(equity_curve: Sequence[float], trades: Sequence[Dict[str, Any]], exposure: Sequence[float], start: float) -> Dict[str, Any]:
    values = np.asarray(list(equity_curve), dtype=float) if np is not None else []
    if np is None or len(values) < 2:
        return {"status": "insufficient_data"}
    returns = np.diff(values) / np.maximum(values[:-1], 0.01)
    total_return = values[-1] / max(values[0], 0.01) - 1.0
    years = max(len(values) / 252.0, 1 / 252.0)
    cagr = (values[-1] / max(values[0], 0.01)) ** (1.0 / years) - 1.0
    peaks = np.maximum.accumulate(values)
    drawdowns = (values - peaks) / np.maximum(peaks, 0.01)
    max_dd = abs(float(np.min(drawdowns)))
    std = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    sharpe = float(np.mean(returns) / std * np.sqrt(252)) if std > 0 else 0.0
    closed = [t for t in trades if t.get("action") == "exit"]
    pnls = [_f(t.get("pnl")) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "status": "ok", "starting_equity": round(start, 2), "ending_equity": round(float(values[-1]), 2),
        "total_return_pct": round(total_return * 100, 2), "cagr_pct": round(cagr * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2), "sharpe": round(sharpe, 3),
        "trades": len(closed), "win_rate_pct": round(len(wins) / max(1, len(closed)) * 100, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        "average_trade_pnl": round(sum(pnls) / max(1, len(pnls)), 2),
        "average_exposure_pct": round(float(np.mean(exposure)) * 100, 2) if exposure else 0.0,
        "time_in_market_pct": round(sum(1 for x in exposure if x > 0) / max(1, len(exposure)) * 100, 2),
    }


def _simulate(
    features: Dict[str, Any], policy: Dict[str, Any], score_floor: float,
    dates: Sequence[Any], start: float = INITIAL_CAPITAL,
) -> Dict[str, Any]:
    if np is None or not dates:
        return {"metrics": {"status": "insufficient_data"}, "daily_returns": [], "trades": []}
    cash = float(start)
    positions: Dict[str, Dict[str, Any]] = {}
    trades: List[Dict[str, Any]] = []
    equity_curve: List[float] = []
    exposure_curve: List[float] = []
    cost_rate = TRANSACTION_COST_BPS / 10000.0
    max_positions = _i(policy.get("max_positions"), 2)
    target_alloc = _f(policy.get("target_allocation"), 0.15)
    stop_loss = _f(policy.get("stop_loss"), 0.015)
    max_hold = _i(policy.get("max_hold_days"), 10)
    rebalance_days = max(1, _i(policy.get("rebalance_days"), 2))

    for index, date in enumerate(dates):
        # Update exits first using daily OHLC and a conservative gap-aware stop fill.
        for symbol in list(positions):
            pos = positions[symbol]
            row = _row(features, symbol, date)
            if row is None:
                continue
            close = _f(row.get("Close"))
            low = _f(row.get("Low"), close)
            opening = _f(row.get("Open"), close)
            exit_price = None
            reason = None
            if low <= _f(pos.get("stop")):
                exit_price = min(opening, _f(pos.get("stop"))) if opening < _f(pos.get("stop")) else _f(pos.get("stop"))
                reason = "stop_loss"
            elif _i(pos.get("age")) >= max_hold:
                exit_price, reason = close, "max_hold"
            elif close < _f(row.get("ma20"), close) and _f(row.get("score")) < score_floor * 0.60:
                exit_price, reason = close, "trend_exit"
            if exit_price is not None and exit_price > 0:
                gross = _f(pos.get("shares")) * exit_price
                fee = gross * cost_rate
                cash += gross - fee
                pnl = gross - fee - _f(pos.get("cost"))
                trades.append({"action": "exit", "symbol": symbol, "date": str(date)[:10], "price": exit_price, "pnl": pnl, "reason": reason})
                del positions[symbol]
            else:
                pos["age"] = _i(pos.get("age")) + 1

        marked = 0.0
        for symbol, pos in positions.items():
            row = _row(features, symbol, date)
            marked += _f(pos.get("shares")) * (_f(row.get("Close")) if row else _f(pos.get("entry")))
        equity = cash + marked

        if index % rebalance_days == 0 and len(positions) < max_positions:
            ranked: List[Tuple[float, str, Dict[str, float]]] = []
            for symbol in features:
                if symbol in positions or symbol in {"SPY", "QQQ"}:
                    continue
                row = _row(features, symbol, date)
                if row and _eligible(row, policy, score_floor):
                    ranked.append((_f(row.get("score")), symbol, row))
            ranked.sort(reverse=True)
            for _score, symbol, row in ranked:
                if len(positions) >= max_positions:
                    break
                equity = cash + sum(
                    _f(pos.get("shares")) * (_f((_row(features, sym, date) or {}).get("Close"), _f(pos.get("entry"))))
                    for sym, pos in positions.items()
                )
                risk_cap = equity * 0.02 / max(stop_loss, 0.0001)
                allocation = min(equity * target_alloc, risk_cap, cash * 0.98)
                price = _f(row.get("Close"))
                if allocation < 50 or price <= 0:
                    continue
                fee = allocation * cost_rate
                shares = max(0.0, (allocation - fee) / price)
                cash -= allocation
                atr_stop = max(stop_loss, min(0.04, _f(row.get("atr_pct"), stop_loss) * 1.25))
                positions[symbol] = {
                    "entry": price, "shares": shares, "cost": allocation,
                    "stop": price * (1.0 - atr_stop), "age": 0,
                }
                trades.append({"action": "entry", "symbol": symbol, "date": str(date)[:10], "price": price, "score": _score, "allocation": allocation})

        marked = 0.0
        for symbol, pos in positions.items():
            row = _row(features, symbol, date)
            marked += _f(pos.get("shares")) * (_f(row.get("Close")) if row else _f(pos.get("entry")))
        equity = cash + marked
        equity_curve.append(equity)
        exposure_curve.append(marked / max(equity, 0.01))

    # Liquidate at the last available close for comparable ending values.
    if dates:
        date = dates[-1]
        for symbol, pos in list(positions.items()):
            row = _row(features, symbol, date)
            close = _f((row or {}).get("Close"), _f(pos.get("entry")))
            gross = _f(pos.get("shares")) * close
            fee = gross * cost_rate
            cash += gross - fee
            pnl = gross - fee - _f(pos.get("cost"))
            trades.append({"action": "exit", "symbol": symbol, "date": str(date)[:10], "price": close, "pnl": pnl, "reason": "end_of_test"})
        if equity_curve:
            equity_curve[-1] = cash
    return {
        "metrics": _metrics(equity_curve, trades, exposure_curve, start),
        "equity_curve": [round(float(x), 4) for x in equity_curve],
        "daily_returns": [round(float(x), 8) for x in np.diff(np.asarray(equity_curve)) / np.maximum(np.asarray(equity_curve[:-1]), 0.01)] if len(equity_curve) > 1 else [],
        "trades": trades,
        "score_floor": score_floor,
    }


def _objective(metrics: Dict[str, Any]) -> float:
    if metrics.get("status") != "ok":
        return -999.0
    return (
        _f(metrics.get("cagr_pct")) - _f(metrics.get("max_drawdown_pct")) * 1.15
        + _f(metrics.get("sharpe")) * 6.0 + min(_i(metrics.get("trades")), 40) * 0.05
    )


def _walk_forward(features: Dict[str, Any], policy: Dict[str, Any], dates: Sequence[Any]) -> Dict[str, Any]:
    if len(dates) < 315:
        return {"status": "insufficient_data", "formal_walk_forward_passed": False, "available_days": len(dates)}
    train_days = min(252, max(180, len(dates) // 2))
    test_days = 63
    folds: List[Dict[str, Any]] = []
    combined_returns: List[float] = []
    cursor = train_days
    while cursor + test_days <= len(dates) and len(folds) < 4:
        train = dates[cursor - train_days:cursor]
        test = dates[cursor:cursor + test_days]
        trials = []
        for floor in policy.get("score_candidates", [policy.get("score_floor")]):
            result = _simulate(features, policy, _f(floor), train)
            trials.append({"score_floor": _f(floor), "metrics": result["metrics"], "objective": _objective(result["metrics"])})
        trials.sort(key=lambda row: row["objective"], reverse=True)
        selected = trials[0]
        tested = _simulate(features, policy, _f(selected["score_floor"]), test)
        combined_returns.extend(tested.get("daily_returns", []))
        folds.append({
            "train_start": str(train[0])[:10], "train_end": str(train[-1])[:10],
            "test_start": str(test[0])[:10], "test_end": str(test[-1])[:10],
            "selected_score_floor": selected["score_floor"],
            "train_metrics": selected["metrics"], "test_metrics": tested["metrics"],
            "candidate_trials": trials,
        })
        cursor += test_days
    if not folds:
        return {"status": "insufficient_data", "formal_walk_forward_passed": False, "available_days": len(dates)}
    arr = np.asarray(combined_returns, dtype=float) if np is not None else []
    compounded = float(np.prod(1.0 + arr) - 1.0) if np is not None and len(arr) else 0.0
    std = float(np.std(arr, ddof=1)) if np is not None and len(arr) > 1 else 0.0
    sharpe = float(np.mean(arr) / std * np.sqrt(252)) if std > 0 else 0.0
    positive = sum(1 for fold in folds if _f(_d(fold.get("test_metrics")).get("total_return_pct")) > 0)
    max_dd = max((_f(_d(fold.get("test_metrics")).get("max_drawdown_pct")) for fold in folds), default=0.0)
    passed = bool(len(folds) >= 3 and positive >= math.ceil(len(folds) * 0.67) and compounded > 0 and sharpe > 0.25 and max_dd < 25)
    return {
        "status": "complete", "formal_walk_forward_passed": passed,
        "folds": folds, "fold_count": len(folds), "positive_test_folds": positive,
        "combined_out_of_sample_return_pct": round(compounded * 100, 2),
        "combined_out_of_sample_sharpe": round(sharpe, 3),
        "worst_test_fold_drawdown_pct": round(max_dd, 2),
    }


def _benchmark(frame: Any, dates: Sequence[Any], start: float = INITIAL_CAPITAL) -> Dict[str, Any]:
    if frame is None or not dates:
        return {"status": "missing"}
    closes: List[float] = []
    for date in dates:
        try:
            if date in frame.index:
                value = frame.loc[date]["Close"]
                if hasattr(value, "iloc"):
                    value = value.iloc[-1]
                closes.append(float(value))
        except Exception:
            pass
    if len(closes) < 2:
        return {"status": "insufficient_data"}
    curve = [start * price / closes[0] for price in closes]
    return _metrics(curve, [], [1.0] * len(curve), start)


def run_backtest(core: Any = None, period: str = AUTO_BACKTEST_PERIOD, max_symbols: int = AUTO_BACKTEST_MAX_SYMBOLS, force: bool = False) -> Dict[str, Any]:
    core = core or _module()
    if core is None:
        return {"status": "pending", "type": "performance_backtest", "version": VERSION, "reason": "core_missing"}
    if not ENABLED:
        return {"status": "disabled", "type": "performance_backtest", "version": VERSION}
    section = _section(core)
    prior = _d(section.get("backtest"))
    if not force and prior.get("status") == "ok":
        stamp = _f(prior.get("generated_epoch"), 0.0)
        if stamp and time.time() - stamp < AUTO_BACKTEST_STALE_HOURS * 3600:
            return prior
    if not _BACKTEST_LOCK.acquire(blocking=False):
        return {"status": "running", "type": "performance_backtest", "version": VERSION, "started_local": section.get("backtest_started_local")}
    try:
        section["backtest_started_local"] = _now(core)
        section["backtest_status"] = "running"
        symbols = _universe(core, max_symbols)
        frames, provider = _download(symbols, period)
        features = _feature_frames(frames)
        dates = _calendar(features)
        if len(dates) < 100 or len(features) < 5:
            result = {
                "status": "error", "type": "performance_backtest", "version": VERSION,
                "generated_local": _now(core), "generated_epoch": time.time(),
                "reason": "insufficient_historical_data", "provider": provider,
                "available_days": len(dates), "loaded_symbols": len(features),
            }
            section["backtest"] = result
            section["backtest_status"] = "error"
            _save(core)
            return result
        results: Dict[str, Any] = {}
        for name, policy in PROFILES.items():
            full = _simulate(features, policy, _f(policy.get("score_floor")), dates)
            walk = _walk_forward(features, policy, dates)
            results[name] = {
                "description": policy.get("description"), "policy": _json_safe(policy),
                "full_sample": full["metrics"], "walk_forward": walk,
                "trade_sample": full.get("trades", [])[-25:],
            }
        benchmarks = {
            "SPY_buy_hold": _benchmark(frames.get("SPY"), dates),
            "QQQ_buy_hold": _benchmark(frames.get("QQQ"), dates),
        }
        ranked = sorted(
            ({"profile": name, **_d(row.get("full_sample")),
              "walk_forward_passed": _d(row.get("walk_forward")).get("formal_walk_forward_passed"),
              "out_of_sample_return_pct": _d(row.get("walk_forward")).get("combined_out_of_sample_return_pct")}
             for name, row in results.items()),
            key=lambda row: (_b(row.get("walk_forward_passed")), _f(row.get("out_of_sample_return_pct")), _f(row.get("cagr_pct"))),
            reverse=True,
        )
        current = _d(_d(results.get("current_proxy")).get("full_sample"))
        balanced = _d(_d(results.get("balanced")).get("full_sample"))
        opportunity_cost = {
            "balanced_minus_current_total_return_pct": round(_f(balanced.get("total_return_pct")) - _f(current.get("total_return_pct")), 2),
            "balanced_minus_current_trade_count": _i(balanced.get("trades")) - _i(current.get("trades")),
            "balanced_minus_current_average_exposure_pct": round(_f(balanced.get("average_exposure_pct")) - _f(current.get("average_exposure_pct")), 2),
            "balanced_minus_current_max_drawdown_pct": round(_f(balanced.get("max_drawdown_pct")) - _f(current.get("max_drawdown_pct")), 2),
        }
        result = {
            "status": "ok", "type": "performance_backtest", "version": VERSION,
            "generated_local": _now(core), "generated_epoch": time.time(),
            "period": period, "requested_symbols": symbols, "provider": provider,
            "loaded_symbols": sorted(features), "trading_days": len(dates),
            "date_range": {"start": str(dates[0])[:10], "end": str(dates[-1])[:10]},
            "profiles": results, "benchmarks": benchmarks, "ranking": ranked,
            "opportunity_cost": opportunity_cost,
            "proxy_disclaimer": "Daily-bar policy proxy. It measures restriction and participation trade-offs; it is not an exact replay of 5-minute fills, provider latency, or every runtime wrapper.",
            "authority": {"advisory_only": True, "changes_strategy": False, "places_orders": False},
        }
        section["backtest"] = result
        section["backtest_status"] = "ok"
        _save(core)
        return result
    except Exception as exc:
        result = {
            "status": "error", "type": "performance_backtest", "version": VERSION,
            "generated_local": _now(core), "generated_epoch": time.time(),
            "error": f"{type(exc).__name__}: {exc}",
        }
        section["backtest"] = result
        section["backtest_status"] = "error"
        _save(core)
        return result
    finally:
        _BACKTEST_LOCK.release()


# ---------------------------------------------------------------------------
# Forward-looking shadow test
# ---------------------------------------------------------------------------

def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def _reason(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return str(row)
    quality = _d(row.get("quality_info"))
    valve = _d(row.get("participation_valve"))
    repair = _d(row.get("paper_underdeployment_repair"))
    return str(repair.get("reason") or row.get("reason") or quality.get("reason") or valve.get("reason") or "unknown")


def _candidate_floor(core: Any, market: Dict[str, Any], side: str = "long") -> float:
    try:
        return _f(core.min_entry_score_for_market(market, side), 0.014)
    except Exception:
        mode = str(market.get("market_mode") or "neutral").lower()
        attr = {"risk_on": "MIN_ENTRY_SCORE_RISK_ON", "constructive": "MIN_ENTRY_SCORE_CONSTRUCTIVE", "neutral": "MIN_ENTRY_SCORE_NEUTRAL"}.get(mode, "MIN_ENTRY_SCORE_DEFENSIVE")
        return _f(getattr(core, attr, 0.014), 0.014)


def _shadow_decisions(core: Any, candidate: Dict[str, Any], market: Dict[str, Any], blocker: str) -> Dict[str, bool]:
    score = _f(candidate.get("score"), _f(candidate.get("rank_score")))
    floor = _candidate_floor(core, market, str(candidate.get("side") or "long"))
    text = str(blocker or "").lower()
    hard = any(token in text for token in HARD_BLOCK_TOKENS)
    soft = any(token in text for token in SOFT_BLOCK_TOKENS)
    return {
        "current_proxy": bool(not hard and not soft and score >= floor),
        "balanced": bool(not hard and score >= max(0.007, floor - 0.0045)),
        "permissive": bool(not hard and score >= max(0.004, floor - 0.0080)),
    }


def _latest_price(core: Any, symbol: str) -> float | None:
    try:
        price = core.latest_price(symbol)
        if price is not None and _f(price) > 0:
            return _f(price)
    except Exception:
        pass
    pos = _d(_d(_portfolio(core).get("positions")).get(symbol))
    value = _f(pos.get("last_price") or pos.get("entry"), 0.0)
    return value if value > 0 else None


def _forward_rows(core: Any) -> List[Dict[str, Any]]:
    section = _section(core)
    rows = section.get("forward_rows")
    if not isinstance(rows, list):
        rows = []
        section["forward_rows"] = rows
    return rows


def _dedupe_key(row: Dict[str, Any]) -> str:
    bucket = int(_f(row.get("captured_epoch")) // 3600)
    return f"{row.get('symbol')}:{bucket}"


def _forward_mark_issue(entry: Any, price: Any) -> Dict[str, Any] | None:
    """Reject catastrophic shadow marks before they can become durable evidence."""
    try:
        entry_value = float(entry)
        price_value = float(price)
    except Exception:
        return {"reason": "nonfinite_or_nonpositive_forward_mark"}
    if not math.isfinite(entry_value) or not math.isfinite(price_value) or entry_value <= 0.0 or price_value <= 0.0:
        return {"reason": "nonfinite_or_nonpositive_forward_mark"}
    ratio = price_value / entry_value
    if ratio <= FORWARD_MIN_PRICE_RATIO or ratio >= FORWARD_MAX_PRICE_RATIO:
        return {
            "reason": "catastrophic_forward_mark_outlier",
            "entry_price": round(entry_value, 6),
            "rejected_mark_price": round(price_value, 6),
            "price_to_entry_ratio": round(ratio, 6),
        }
    return None


def _forward_row_integrity(row: Dict[str, Any]) -> Dict[str, Any]:
    """Classify stored evidence without rewriting historical forward rows."""
    side = str(row.get("side") or "long").lower().strip()
    if side not in {"long", "short"}:
        return {"eligible": False, "reason": "invalid_side"}
    try:
        entry = float(row.get("entry_price"))
        mfe = float(row.get("mfe_pct", 0.0))
        mae = float(row.get("mae_pct", 0.0))
    except Exception:
        return {"eligible": False, "reason": "nonfinite_or_incomplete_excursion"}
    if not all(math.isfinite(value) for value in (entry, mfe, mae)) or entry <= 0.0:
        return {"eligible": False, "reason": "nonfinite_or_incomplete_excursion"}

    maximum_favorable = ((FORWARD_MAX_PRICE_RATIO - 1.0) * 100.0 if side == "long"
                          else (1.0 - FORWARD_MIN_PRICE_RATIO) * 100.0)
    minimum_adverse = ((FORWARD_MIN_PRICE_RATIO - 1.0) * 100.0 if side == "long"
                       else (1.0 - FORWARD_MAX_PRICE_RATIO) * 100.0)
    if mfe < 0.0 or mae > 0.0 or mfe >= maximum_favorable or mae <= minimum_adverse:
        return {"eligible": False, "reason": "stored_excursion_outside_source_envelope"}

    for name, outcome in _d(row.get("outcomes")).items():
        if not isinstance(outcome, dict):
            return {"eligible": False, "reason": "invalid_horizon_outcome", "horizon": str(name)}
        issue = _forward_mark_issue(entry, outcome.get("mark_price"))
        if issue is not None:
            return {"eligible": False, "reason": "stored_horizon_outside_source_envelope", "horizon": str(name)}
    return {"eligible": True, "reason": None}


def _capture_forward(
    core: Any, candidates: Sequence[Dict[str, Any]], entries: Sequence[Dict[str, Any]],
    blocked: Sequence[Dict[str, Any]], market: Dict[str, Any],
) -> Dict[str, Any]:
    rows = _forward_rows(core)
    existing = {_dedupe_key(row) for row in rows if isinstance(row, dict)}
    entry_symbols = {_symbol(row) for row in entries if isinstance(row, dict)}
    blockers = {_symbol(row): _reason(row) for row in blocked if isinstance(row, dict) and _symbol(row)}
    added = 0
    for candidate in list(candidates)[:FORWARD_MAX_NEW_PER_CYCLE]:
        if not isinstance(candidate, dict):
            continue
        symbol = _symbol(candidate)
        price = _f(candidate.get("price") or candidate.get("last_price"), 0.0)
        if not symbol or price <= 0:
            continue
        row = {
            "captured_local": _now(core), "captured_epoch": time.time(),
            "symbol": symbol, "side": str(candidate.get("side") or "long"),
            "entry_price": price, "score": _f(candidate.get("score")),
            "rank_score": _f(candidate.get("core_entry_rank_score"), _f(candidate.get("rank_score"))),
            "market_mode": market.get("market_mode"), "risk_score": market.get("risk_score"),
            "actual_entered": symbol in entry_symbols,
            "actual_block_reason": blockers.get(symbol, "not_selected_or_unknown"),
        }
        key = _dedupe_key(row)
        if key in existing:
            continue
        row["shadow_policy_acceptance"] = _shadow_decisions(core, row, market, row["actual_block_reason"])
        row["outcomes"] = {}
        row["mfe_pct"] = 0.0
        row["mae_pct"] = 0.0
        rows.append(row)
        existing.add(key)
        added += 1
    if len(rows) > FORWARD_MAX_ROWS:
        del rows[:-FORWARD_MAX_ROWS]
    return {"rows_added": added, "rows_total": len(rows)}


def _resolve_forward(core: Any) -> Dict[str, Any]:
    rows = _forward_rows(core)
    now = time.time()
    resolved = 0
    reviewed = 0
    for row in reversed(rows):
        if reviewed >= FORWARD_RESOLVE_PER_CYCLE:
            break
        if not isinstance(row, dict) or _f(row.get("captured_epoch")) <= 0:
            continue
        outcomes = _d(row.get("outcomes"))
        if all(name in outcomes for name in HORIZONS):
            continue
        reviewed += 1
        price = _latest_price(core, str(row.get("symbol") or ""))
        entry = _f(row.get("entry_price"), 0.0)
        if price is None or entry <= 0:
            continue
        issue = _forward_mark_issue(entry, price)
        if issue is not None:
            row["integrity_rejection_count"] = min(9999, _i(row.get("integrity_rejection_count")) + 1)
            row["last_integrity_rejection"] = {**issue, "rejected_local": _now(core)}
            continue
        ret = (price / entry - 1.0) * (1 if str(row.get("side") or "long") != "short" else -1)
        row["last_mark_price"] = round(price, 6)
        row["last_mark_local"] = _now(core)
        row["mfe_pct"] = round(max(_f(row.get("mfe_pct")), ret * 100), 4)
        row["mae_pct"] = round(min(_f(row.get("mae_pct")), ret * 100), 4)
        age = now - _f(row.get("captured_epoch"))
        for name, seconds in HORIZONS.items():
            if name not in outcomes and age >= seconds:
                outcomes[name] = {
                    "return_pct": round(ret * 100, 4), "mark_price": round(price, 6),
                    "resolved_local": _now(core), "elapsed_seconds": round(age, 1),
                }
                resolved += 1
        row["outcomes"] = outcomes
    return {"rows_reviewed": reviewed, "outcomes_resolved": resolved}


def forward_summary(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is None:
        return {"status": "pending", "type": "performance_forward_test", "version": VERSION, "reason": "core_missing"}
    rows = [row for row in _forward_rows(core) if isinstance(row, dict)]
    classified = [(row, _forward_row_integrity(row)) for row in rows]
    eligible_rows = [row for row, integrity in classified if integrity["eligible"]]
    excluded = [(row, integrity) for row, integrity in classified if not integrity["eligible"]]
    summary: Dict[str, Any] = {}
    for profile in PROFILES:
        profile_rows = [row for row in eligible_rows if _d(row.get("shadow_policy_acceptance")).get(profile)]
        horizons: Dict[str, Any] = {}
        for horizon in HORIZONS:
            values = [
                _f(_d(_d(row.get("outcomes")).get(horizon)).get("return_pct"))
                for row in profile_rows if horizon in _d(row.get("outcomes"))
            ]
            horizons[horizon] = {
                "sample_size": len(values),
                "average_return_pct": round(sum(values) / max(1, len(values)), 4),
                "median_return_pct": round(float(np.median(values)), 4) if np is not None and values else None,
                "win_rate_pct": round(sum(1 for v in values if v > 0) / max(1, len(values)) * 100, 2),
                "average_upside_pct": round(sum(v for v in values if v > 0) / max(1, sum(1 for v in values if v > 0)), 4),
                "average_downside_pct": round(sum(v for v in values if v < 0) / max(1, sum(1 for v in values if v < 0)), 4),
            }
        summary[profile] = {
            "accepted_rows": len(profile_rows), "horizons": horizons,
            "average_mfe_pct": round(sum(_f(row.get("mfe_pct")) for row in profile_rows) / max(1, len(profile_rows)), 4),
            "average_mae_pct": round(sum(_f(row.get("mae_pct")) for row in profile_rows) / max(1, len(profile_rows)), 4),
        }
    actual = [row for row in eligible_rows if row.get("actual_entered")]
    missed = [row for row in eligible_rows if not row.get("actual_entered") and _d(row.get("shadow_policy_acceptance")).get("balanced")]
    top_missed = sorted(
        missed, key=lambda row: _f(_d(_d(row.get("outcomes")).get("one_day")).get("return_pct")), reverse=True,
    )[:15]
    return {
        "status": "ok", "type": "performance_forward_test", "version": VERSION,
        "evidence_status": "inconclusive" if excluded else "eligible",
        "promotion_eligible": False,
        "generated_local": _now(core), "rows_total": len(rows), "actual_entries_captured": len(actual),
        "integrity": {
            "status": "warn" if excluded else "pass",
            "eligible_rows": len(eligible_rows),
            "excluded_rows": len(excluded),
            "exclusion_reasons": dict(Counter(integrity["reason"] for _, integrity in excluded)),
            "source_price_ratio_envelope": [FORWARD_MIN_PRICE_RATIO, FORWARD_MAX_PRICE_RATIO],
            "historical_rows_rewritten": False,
        },
        "policy_summary": summary,
        "balanced_candidates_blocked_by_current": len(missed),
        "top_missed_balanced_candidates": [
            {"symbol": row.get("symbol"), "captured_local": row.get("captured_local"),
             "score": row.get("score"), "block_reason": row.get("actual_block_reason"),
             "one_hour": _d(_d(row.get("outcomes")).get("one_hour")).get("return_pct"),
             "one_day": _d(_d(row.get("outcomes")).get("one_day")).get("return_pct"),
             "mfe_pct": row.get("mfe_pct"), "mae_pct": row.get("mae_pct")}
            for row in top_missed
        ],
        "recent_rows": [
            {**row, "research_integrity": integrity}
            for row, integrity in classified[-30:]
        ],
        "authority": {"shadow_only": True, "places_orders": False, "changes_thresholds": False},
    }


def _patch_cycle(core: Any) -> bool:
    try:
        import core_entry_pipeline as pipeline
    except Exception:
        return False
    current = getattr(pipeline, "_core_try_entries_and_rotations", None)
    if not callable(current) or getattr(current, "_performance_audit_lab_version", None) == VERSION:
        return False
    prior = current

    def audited_cycle(runtime: Any, long_signals: Any, short_signals: Any, params: Any, market: Any, new_entries_allowed: bool = True, entry_block_reason: Any = None, __prior=prior):
        result = __prior(runtime, long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)
        try:
            if isinstance(result, tuple):
                entries = result[0] if len(result) > 0 and isinstance(result[0], list) else []
                blocked = result[2] if len(result) > 2 and isinstance(result[2], list) else []
            else:
                entries, blocked = [], []
            candidates = [row for row in list(long_signals or []) + list(short_signals or []) if isinstance(row, dict)]
            candidates.sort(key=lambda row: _f(row.get("core_entry_rank_score"), _f(row.get("score"))), reverse=True)
            capture = _capture_forward(runtime, candidates, entries, blocked, _d(market))
            resolve = _resolve_forward(runtime)
            section = _section(runtime)
            section["last_forward_cycle"] = {
                "generated_local": _now(runtime), "candidate_count": len(candidates),
                "entries_count": len(entries), "blocked_count": len(blocked),
                "capture": capture, "resolve": resolve,
            }
            section["forward_summary"] = forward_summary(runtime)
            _save(runtime)
        except Exception as exc:
            _section(runtime)["last_forward_error"] = f"{type(exc).__name__}: {exc}"
        return result

    audited_cycle._performance_audit_lab_version = VERSION  # type: ignore[attr-defined]
    audited_cycle.__wrapped__ = prior  # type: ignore[attr-defined]
    pipeline._core_try_entries_and_rotations = audited_cycle
    return True


def _patch_self_check(core: Any) -> bool:
    try:
        import fast_self_check_override as check
    except Exception:
        return False
    current = getattr(check, "_component_checks", None)
    if not callable(current) or getattr(current, "_performance_audit_lab_version", None) == VERSION:
        return False
    prior = current

    def components(runtime: Any, __prior=prior):
        out = dict(__prior(runtime))
        section = _section(runtime)
        backtest = _d(section.get("backtest"))
        forward = forward_summary(runtime)
        audit = _d(section.get("last_restriction_audit")) or restriction_audit(runtime)
        out["performance_evidence"] = {
            "name": "performance_evidence", "version": VERSION,
            "overall": "pass" if backtest.get("status") == "ok" else "warn",
            "backtest_status": backtest.get("status") or section.get("backtest_status") or "not_run",
            "backtest_generated_local": backtest.get("generated_local"),
            "forward_rows": forward.get("rows_total"),
            "balanced_candidates_blocked_by_current": forward.get("balanced_candidates_blocked_by_current"),
            "restriction_constants": _d(audit.get("summary")).get("restriction_constants"),
            "sub_one_sizing_factors": _d(audit.get("summary")).get("sub_one_sizing_factors"),
            "maximum_callable_depth": _d(audit.get("summary")).get("maximum_callable_depth"),
            "links": {
                "audit": "/paper/restriction-audit",
                "backtest": "/paper/performance-backtest",
                "forward": "/paper/performance-forward-test",
            },
        }
        return out

    components._performance_audit_lab_version = VERSION  # type: ignore[attr-defined]
    for attr in ("_neutral_late_session_version", "_paper_underdeployment_version"):
        if getattr(prior, attr, None):
            setattr(components, attr, getattr(prior, attr))
    components.__wrapped__ = prior  # type: ignore[attr-defined]
    check._component_checks = components
    return True


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    if core is None:
        return {"status": "pending", "type": "performance_audit_lab_status", "version": VERSION, "reason": "core_missing"}
    section = _section(core)
    return {
        "status": "ok", "type": "performance_audit_lab_status", "version": VERSION,
        "generated_local": _now(core), "enabled": ENABLED,
        "restriction_audit": _d(section.get("last_restriction_audit")) or restriction_audit(core),
        "backtest": _d(section.get("backtest")) or {"status": section.get("backtest_status") or "not_run"},
        "forward_test": forward_summary(core),
        "last_forward_cycle": section.get("last_forward_cycle"),
        "last_forward_error": section.get("last_forward_error"),
        "settings": {
            "auto_backtest_enabled": AUTO_BACKTEST, "auto_backtest_period": AUTO_BACKTEST_PERIOD,
            "auto_backtest_max_symbols": AUTO_BACKTEST_MAX_SYMBOLS,
            "auto_backtest_stale_hours": AUTO_BACKTEST_STALE_HOURS,
            "forward_max_rows": FORWARD_MAX_ROWS,
            "transaction_cost_bps": TRANSACTION_COST_BPS,
        },
        "authority": {
            "advisory_and_shadow_only": True, "changes_strategy": False,
            "changes_thresholds": False, "changes_sizing": False, "places_orders": False,
            "changes_live_authority": False, "changes_ml_authority": False,
        },
    }


def _market_open(core: Any) -> bool:
    try:
        return bool(_d(core.market_clock()).get("is_open"))
    except Exception:
        return False


def _backtest_stale(core: Any) -> bool:
    prior = _d(_section(core).get("backtest"))
    stamp = _f(prior.get("generated_epoch"), 0.0)
    return not stamp or time.time() - stamp >= AUTO_BACKTEST_STALE_HOURS * 3600


def _watchdog(core: Any) -> None:
    # Initial audit is cheap and gives immediate evidence even if the data provider is unavailable.
    try:
        restriction_audit(core)
    except Exception:
        pass
    while True:
        try:
            _patch_cycle(core)
            _patch_self_check(core)
            _resolve_forward(core)
            if AUTO_BACKTEST and not _market_open(core) and _backtest_stale(core) and not _BACKTEST_LOCK.locked():
                threading.Thread(
                    target=run_backtest,
                    kwargs={"core": core, "period": AUTO_BACKTEST_PERIOD, "max_symbols": AUTO_BACKTEST_MAX_SYMBOLS, "force": True},
                    name="performance-audit-backtest",
                    daemon=True,
                ).start()
        except Exception as exc:
            _section(core)["watchdog_error"] = f"{type(exc).__name__}: {exc}"
        time.sleep(max(30, WATCHDOG_SECONDS))


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST_INSTALL
    core = core or _module()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    with _LOCK:
        cycle = _patch_cycle(core)
        self_check = _patch_self_check(core)
        if id(core) not in _WATCHDOGS:
            _WATCHDOGS.add(id(core))
            threading.Thread(target=_watchdog, args=(core,), name="performance-audit-watchdog", daemon=True).start()
        _LAST_INSTALL = {
            "status": "ok", "overall": "pass", "version": VERSION,
            "generated_local": _now(core), "cycle_patched_this_call": cycle,
            "self_check_patched_this_call": self_check, "watchdog_started": id(core) in _WATCHDOGS,
        }
        setattr(core, "PERFORMANCE_AUDIT_LAB_VERSION", VERSION)
        _section(core)["last_install"] = dict(_LAST_INSTALL)
        return dict(_LAST_INSTALL)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "reason": "flask_app_missing"}
    core = core or _module()
    apply(core)
    if id(flask_app) in _REGISTERED:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify, request
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}

    def status_route():
        return jsonify(status_payload(core or _module()))

    def audit_route():
        return jsonify(restriction_audit(core or _module()))

    def backtest_route():
        runtime = core or _module()
        period = str(request.args.get("period") or AUTO_BACKTEST_PERIOD)
        max_symbols = max(8, min(75, _i(request.args.get("symbols"), AUTO_BACKTEST_MAX_SYMBOLS)))
        force = str(request.args.get("force") or "false").lower() in {"1", "true", "yes", "on"}
        return jsonify(run_backtest(runtime, period=period, max_symbols=max_symbols, force=force))

    def forward_route():
        runtime = core or _module()
        _resolve_forward(runtime)
        payload = forward_summary(runtime)
        _section(runtime)["forward_summary"] = payload
        _save(runtime)
        return jsonify(payload)

    routes = (
        ("/paper/performance-audit-status", "performance_audit_lab_status", status_route),
        ("/paper/restriction-audit", "performance_restriction_audit", audit_route),
        ("/paper/performance-backtest", "performance_policy_backtest", backtest_route),
        ("/paper/walk-forward-backtest", "performance_walk_forward_backtest", backtest_route),
        ("/paper/performance-forward-test", "performance_forward_shadow_test", forward_route),
    )
    for path, endpoint, fn in routes:
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, fn)
    _REGISTERED.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [row[0] for row in routes]}


try:
    apply(_module())
except Exception:
    pass
