"""Second-generation performance research lab.

This module extends performance_audit_lab with:
- next-session-open execution assumptions;
- full-history rolling walk-forward coverage (no four-fold truncation);
- regime segmentation and calendar-year reporting;
- a regime-adaptive balanced policy with defensive/inverse-ETF participation;
- one-variable-at-a-time ablation tests for position count, confirmations,
  MA50, allocation, stop width, and holding period;
- explicit universe-coverage and survivorship-bias warnings.

It is advisory research only. It never changes thresholds, sizing, strategy
authority, ML authority, or order placement.
"""
from __future__ import annotations

import copy
import math
import os
import threading
import time
from typing import Any, Dict, List, Sequence, Tuple

import performance_audit_lab as base

np = base.np
pd = base.pd

VERSION = "performance-audit-lab-v2-2026-08-03-v1"
ENABLED = os.environ.get("PERFORMANCE_AUDIT_V2_ENABLED", "true").lower() not in {
    "0", "false", "no", "off"
}
AUTO_BACKTEST = os.environ.get("PERFORMANCE_AUDIT_V2_AUTO_BACKTEST_ENABLED", "true").lower() not in {
    "0", "false", "no", "off"
}
AUTO_PERIOD = os.environ.get("PERFORMANCE_AUDIT_V2_AUTO_PERIOD", "5y")
AUTO_MAX_SYMBOLS = int(os.environ.get("PERFORMANCE_AUDIT_V2_AUTO_MAX_SYMBOLS", "45"))
STALE_HOURS = float(os.environ.get("PERFORMANCE_AUDIT_V2_STALE_HOURS", "24"))
WATCHDOG_SECONDS = max(60, int(os.environ.get("PERFORMANCE_AUDIT_V2_WATCHDOG_SECONDS", "600")))
INITIAL_CAPITAL = float(os.environ.get("PERFORMANCE_AUDIT_INITIAL_CAPITAL", "10000"))
TRANSACTION_COST_BPS = float(os.environ.get("PERFORMANCE_AUDIT_TRANSACTION_COST_BPS", "8"))

_LOCK = threading.RLock()
_RUN_LOCK = threading.Lock()
_WATCHDOGS: set[int] = set()
_REGISTERED: set[int] = set()

DEFENSIVE_SYMBOLS = {
    "SH", "PSQ", "SDS", "GLD", "GDX", "SLV", "TLT", "IEF", "XLU", "XLP", "XLV", "XLE", "RSP"
}

PREFERRED_UNIVERSE = [
    "SPY", "QQQ", "IWM", "RSP", "XLK", "SMH", "XLE", "XLV", "XLU", "XLP",
    "GLD", "SLV", "GDX", "TLT", "IEF", "SH", "PSQ",
    "NVDA", "AMD", "AVGO", "MU", "MSFT", "AMZN", "META", "GOOGL", "PLTR",
    "DELL", "HPE", "ANET", "VRT", "GEV", "PWR", "STX", "WDC", "CIEN",
    "RKLB", "ASTS", "CIFR", "IREN", "CLSK", "MARA", "RIOT", "IBIT",
]

STATIC_PROFILES: Dict[str, Dict[str, Any]] = {
    "current_proxy": {
        "score_floor": 0.014,
        "min_confirmations": 5,
        "min_volume_ratio": 1.00,
        "min_relative_strength": 0.000,
        "require_ma50": True,
        "max_positions": 2,
        "target_allocation": 0.18,
        "max_exposure": 0.36,
        "stop_loss": 0.012,
        "max_hold_days": 7,
        "rebalance_days": 2,
        "allowed_symbols": None,
        "description": "Current tight policy proxy with next-session execution.",
    },
    "balanced_static": {
        "score_floor": 0.009,
        "min_confirmations": 3,
        "min_volume_ratio": 0.75,
        "min_relative_strength": -0.010,
        "require_ma50": False,
        "max_positions": 4,
        "target_allocation": 0.16,
        "max_exposure": 0.62,
        "stop_loss": 0.015,
        "max_hold_days": 10,
        "rebalance_days": 2,
        "allowed_symbols": None,
        "description": "Static balanced profile from the first audit.",
    },
    "permissive": {
        "score_floor": 0.006,
        "min_confirmations": 2,
        "min_volume_ratio": 0.55,
        "min_relative_strength": -0.025,
        "require_ma50": False,
        "max_positions": 6,
        "target_allocation": 0.12,
        "max_exposure": 0.72,
        "stop_loss": 0.018,
        "max_hold_days": 12,
        "rebalance_days": 1,
        "allowed_symbols": None,
        "description": "High-participation comparison profile.",
    },
}

ADAPTIVE_REGIMES: Dict[str, Dict[str, Any]] = {
    "strong_risk_on": {
        "score_floor": 0.008,
        "min_confirmations": 3,
        "min_volume_ratio": 0.72,
        "min_relative_strength": -0.012,
        "require_ma50": False,
        "max_positions": 4,
        "target_allocation": 0.16,
        "max_exposure": 0.62,
        "stop_loss": 0.015,
        "max_hold_days": 10,
        "rebalance_days": 2,
        "allowed_symbols": None,
    },
    "risk_on": {
        "score_floor": 0.009,
        "min_confirmations": 3,
        "min_volume_ratio": 0.75,
        "min_relative_strength": -0.010,
        "require_ma50": False,
        "max_positions": 4,
        "target_allocation": 0.16,
        "max_exposure": 0.58,
        "stop_loss": 0.015,
        "max_hold_days": 10,
        "rebalance_days": 2,
        "allowed_symbols": None,
    },
    "constructive": {
        "score_floor": 0.010,
        "min_confirmations": 3,
        "min_volume_ratio": 0.80,
        "min_relative_strength": -0.005,
        "require_ma50": False,
        "max_positions": 4,
        "target_allocation": 0.15,
        "max_exposure": 0.52,
        "stop_loss": 0.015,
        "max_hold_days": 10,
        "rebalance_days": 2,
        "allowed_symbols": None,
    },
    "neutral": {
        "score_floor": 0.012,
        "min_confirmations": 4,
        "min_volume_ratio": 0.90,
        "min_relative_strength": 0.000,
        "require_ma50": False,
        "max_positions": 3,
        "target_allocation": 0.13,
        "max_exposure": 0.42,
        "stop_loss": 0.014,
        "max_hold_days": 8,
        "rebalance_days": 2,
        "allowed_symbols": None,
    },
    "defensive": {
        "score_floor": 0.012,
        "min_confirmations": 4,
        "min_volume_ratio": 0.75,
        "min_relative_strength": -0.020,
        "require_ma50": False,
        "max_positions": 2,
        "target_allocation": 0.09,
        "max_exposure": 0.20,
        "stop_loss": 0.014,
        "max_hold_days": 8,
        "rebalance_days": 2,
        "allowed_symbols": sorted(DEFENSIVE_SYMBOLS),
    },
    "risk_off": {
        "score_floor": 0.010,
        "min_confirmations": 3,
        "min_volume_ratio": 0.65,
        "min_relative_strength": -0.030,
        "require_ma50": False,
        "max_positions": 2,
        "target_allocation": 0.08,
        "max_exposure": 0.16,
        "stop_loss": 0.015,
        "max_hold_days": 7,
        "rebalance_days": 2,
        "allowed_symbols": sorted(DEFENSIVE_SYMBOLS),
    },
}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    return base._f(value, default)


def _i(value: Any, default: int = 0) -> int:
    return base._i(value, default)


def _core() -> Any | None:
    return base._module()


def _now(core: Any = None) -> str:
    return base._now(core)


def _portfolio(core: Any) -> Dict[str, Any]:
    return _d(getattr(core, "portfolio", {}))


def _section(core: Any) -> Dict[str, Any]:
    state = _portfolio(core)
    section = state.setdefault("performance_audit_lab_v2", {})
    if not isinstance(section, dict):
        section = {}
        state["performance_audit_lab_v2"] = section
    section["version"] = VERSION
    return section


def _save(core: Any) -> None:
    base._save(core)


def _universe(core: Any, max_symbols: int) -> List[str]:
    existing = base._universe(core, max_symbols * 2)
    ordered = list(dict.fromkeys(PREFERRED_UNIVERSE + existing))
    excluded = {"^VIX", "^TNX", "ES=F", "NQ=F", "UUP"}
    return [symbol for symbol in ordered if symbol not in excluded][: max(20, max_symbols)]


def _row(features: Dict[str, Any], symbol: str, date: Any) -> Dict[str, float] | None:
    return base._row(features, symbol, date)


def _regime(features: Dict[str, Any], date: Any) -> str:
    spy = _row(features, "SPY", date)
    qqq = _row(features, "QQQ", date)
    if not spy:
        return "neutral"
    spy_close = _f(spy.get("Close"))
    spy_ma20 = _f(spy.get("ma20"))
    spy_ma50 = _f(spy.get("ma50"))
    spy_ret20 = _f(spy.get("ret20"))
    spy_ret60 = _f(spy.get("ret60"))
    q_close = _f((qqq or {}).get("Close"))
    q_ma50 = _f((qqq or {}).get("ma50"))
    q_ret20 = _f((qqq or {}).get("ret20"))
    q_ret60 = _f((qqq or {}).get("ret60"))

    spy_above50 = spy_ma50 > 0 and spy_close > spy_ma50
    q_above50 = q_ma50 > 0 and q_close > q_ma50
    if (
        not spy_above50
        and spy_ret20 < -0.03
        and q_ret20 < -0.035
        and (spy_ret60 < -0.05 or q_ret60 < -0.07)
    ):
        return "risk_off"
    if (not spy_above50 and spy_ret20 < 0) or (qqq and not q_above50 and q_ret20 < 0):
        return "defensive"
    if spy_above50 and q_above50 and spy_ret20 > 0.04 and q_ret20 > 0.05 and spy_ret60 > 0.06:
        return "strong_risk_on"
    if spy_above50 and q_above50 and spy_ret20 > 0 and q_ret20 > 0:
        return "risk_on"
    if spy_close > spy_ma20 and (spy_above50 or q_above50):
        return "constructive"
    return "neutral"


def _static_regime_map(policy: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {name: dict(policy) for name in ADAPTIVE_REGIMES}


def _scaled_regime_map(
    regime_map: Dict[str, Dict[str, Any]],
    allocation_scale: float = 1.0,
    exposure_scale: float = 1.0,
    score_shift: float = 0.0,
) -> Dict[str, Dict[str, Any]]:
    out = copy.deepcopy(regime_map)
    for policy in out.values():
        policy["target_allocation"] = max(0.04, min(0.22, _f(policy.get("target_allocation")) * allocation_scale))
        policy["max_exposure"] = max(
            policy["target_allocation"],
            min(0.80, _f(policy.get("max_exposure")) * exposure_scale),
        )
        policy["score_floor"] = max(0.002, _f(policy.get("score_floor")) + score_shift)
    return out


def _eligible(row: Dict[str, float], policy: Dict[str, Any]) -> bool:
    if not row or math.isnan(_f(row.get("score"), float("nan"))):
        return False
    if _f(row.get("score")) < _f(policy.get("score_floor")):
        return False
    if _i(row.get("confirmations")) < _i(policy.get("min_confirmations")):
        return False
    if _f(row.get("volume_ratio"), 1.0) < _f(policy.get("min_volume_ratio"), 0.0):
        return False
    if _f(row.get("rs20"), 0.0) < _f(policy.get("min_relative_strength"), -1.0):
        return False
    close = _f(row.get("Close"))
    if close <= _f(row.get("ma20"), 0.0):
        return False
    if policy.get("require_ma50") and close <= _f(row.get("ma50"), 0.0):
        return False
    allowed = policy.get("allowed_symbols")
    if allowed is not None and str(row.get("_symbol") or "") not in set(allowed):
        return False
    return True


def _mark_value(features: Dict[str, Any], symbol: str, date: Any, fallback: float, field: str = "Close") -> float:
    row = _row(features, symbol, date)
    return _f((row or {}).get(field), fallback)


def _simulate_next_open(
    features: Dict[str, Any],
    regime_map: Dict[str, Dict[str, Any]],
    dates: Sequence[Any],
    start: float = INITIAL_CAPITAL,
) -> Dict[str, Any]:
    if np is None or len(dates) == 0:
        return {"metrics": {"status": "insufficient_data"}, "trades": [], "equity_curve": []}

    cash = float(start)
    positions: Dict[str, Dict[str, Any]] = {}
    pending: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    curve: List[float] = []
    exposure_curve: List[float] = []
    curve_dates: List[Any] = []
    regimes: List[str] = []
    cost_rate = TRANSACTION_COST_BPS / 10000.0

    for index, date in enumerate(dates):
        today_regime = _regime(features, date)
        policy_today = regime_map.get(today_regime, regime_map.get("neutral", {}))

        if pending:
            pending.sort(key=lambda row: _f(row.get("score")), reverse=True)
            for order in pending:
                order_policy = _d(order.get("policy"))
                max_positions = _i(order_policy.get("max_positions"), 2)
                if len(positions) >= max_positions:
                    break
                symbol = str(order.get("symbol") or "")
                if not symbol or symbol in positions:
                    continue
                row = _row(features, symbol, date)
                if row is None:
                    continue
                price = _f(row.get("Open"), _f(row.get("Close")))
                if price <= 0:
                    continue
                marked_open = sum(
                    _f(pos.get("shares"))
                    * _mark_value(features, sym, date, _f(pos.get("entry")), "Open")
                    for sym, pos in positions.items()
                )
                equity_open = cash + marked_open
                current_exposure = marked_open / max(equity_open, 0.01)
                max_exposure = _f(order_policy.get("max_exposure"), 0.40)
                remaining_exposure = max(0.0, max_exposure - current_exposure)
                target_alloc = _f(order_policy.get("target_allocation"), 0.12)
                stop_loss = _f(order_policy.get("stop_loss"), 0.015)
                risk_cap = equity_open * 0.02 / max(stop_loss, 0.0001)
                allocation = min(
                    equity_open * target_alloc,
                    equity_open * remaining_exposure,
                    risk_cap,
                    cash * 0.98,
                )
                if allocation < 50:
                    continue
                fee = allocation * cost_rate
                shares = max(0.0, (allocation - fee) / price)
                if shares <= 0:
                    continue
                cash -= allocation
                atr_stop = max(
                    stop_loss,
                    min(0.045, _f(row.get("atr_pct"), stop_loss) * 1.25),
                )
                positions[symbol] = {
                    "entry": price,
                    "shares": shares,
                    "cost": allocation,
                    "stop": price * (1.0 - atr_stop),
                    "age": 0,
                    "policy": order_policy,
                    "entry_regime": order.get("regime"),
                }
                trades.append(
                    {
                        "action": "entry",
                        "symbol": symbol,
                        "signal_date": str(order.get("signal_date"))[:10],
                        "date": str(date)[:10],
                        "price": price,
                        "score": order.get("score"),
                        "allocation": allocation,
                        "regime": order.get("regime"),
                        "execution": "next_session_open",
                    }
                )
        pending = []

        for symbol in list(positions):
            pos = positions[symbol]
            row = _row(features, symbol, date)
            if row is None:
                continue
            close = _f(row.get("Close"))
            low = _f(row.get("Low"), close)
            opening = _f(row.get("Open"), close)
            stop = _f(pos.get("stop"))
            max_hold = _i(_d(pos.get("policy")).get("max_hold_days"), 10)
            exit_price = None
            reason = None
            if low <= stop:
                exit_price = opening if opening < stop else stop
                reason = "stop_loss"
            elif _i(pos.get("age")) >= max_hold:
                exit_price = close
                reason = "max_hold"
            elif close < _f(row.get("ma20"), close) and _f(row.get("score")) < _f(
                _d(pos.get("policy")).get("score_floor"), 0.01
            ) * 0.60:
                exit_price = close
                reason = "trend_exit"
            if exit_price is not None and exit_price > 0:
                gross = _f(pos.get("shares")) * exit_price
                fee = gross * cost_rate
                cash += gross - fee
                pnl = gross - fee - _f(pos.get("cost"))
                trades.append(
                    {
                        "action": "exit",
                        "symbol": symbol,
                        "date": str(date)[:10],
                        "price": exit_price,
                        "pnl": pnl,
                        "reason": reason,
                        "entry_regime": pos.get("entry_regime"),
                    }
                )
                del positions[symbol]
            else:
                pos["age"] = _i(pos.get("age")) + 1

        marked = sum(
            _f(pos.get("shares"))
            * _mark_value(features, symbol, date, _f(pos.get("entry")), "Close")
            for symbol, pos in positions.items()
        )
        equity = cash + marked
        curve.append(equity)
        exposure_curve.append(marked / max(equity, 0.01))
        curve_dates.append(date)
        regimes.append(today_regime)

        if index >= len(dates) - 1:
            continue
        rebalance_days = max(1, _i(policy_today.get("rebalance_days"), 2))
        if index % rebalance_days != 0:
            continue
        max_positions = _i(policy_today.get("max_positions"), 2)
        slots = max(0, max_positions - len(positions))
        if slots <= 0:
            continue
        allowed = set(policy_today.get("allowed_symbols") or [])
        ranked: List[Tuple[float, str, Dict[str, float]]] = []
        for symbol in features:
            if symbol in positions or symbol in {"SPY", "QQQ"}:
                continue
            if allowed and symbol not in allowed:
                continue
            row = _row(features, symbol, date)
            if row is None:
                continue
            row = dict(row)
            row["_symbol"] = symbol
            if _eligible(row, policy_today):
                ranked.append((_f(row.get("score")), symbol, row))
        ranked.sort(reverse=True)
        for score, symbol, _row_data in ranked[:slots]:
            pending.append(
                {
                    "symbol": symbol,
                    "score": score,
                    "signal_date": date,
                    "regime": today_regime,
                    "policy": dict(policy_today),
                }
            )

    if dates:
        final_date = dates[-1]
        for symbol, pos in list(positions.items()):
            close = _mark_value(features, symbol, final_date, _f(pos.get("entry")), "Close")
            gross = _f(pos.get("shares")) * close
            fee = gross * cost_rate
            cash += gross - fee
            trades.append(
                {
                    "action": "exit",
                    "symbol": symbol,
                    "date": str(final_date)[:10],
                    "price": close,
                    "pnl": gross - fee - _f(pos.get("cost")),
                    "reason": "end_of_test",
                    "entry_regime": pos.get("entry_regime"),
                }
            )
        if curve:
            curve[-1] = cash

    metrics = base._metrics(curve, trades, exposure_curve, start)
    daily_returns = (
        np.diff(np.asarray(curve, dtype=float))
        / np.maximum(np.asarray(curve[:-1], dtype=float), 0.01)
        if np is not None and len(curve) > 1
        else np.asarray([], dtype=float) if np is not None else []
    )
    return {
        "metrics": metrics,
        "trades": trades,
        "equity_curve": curve,
        "dates": curve_dates,
        "exposure_curve": exposure_curve,
        "regimes": regimes,
        "daily_returns": [float(x) for x in daily_returns],
    }


def _slice_metrics(
    dates: Sequence[Any],
    curve: Sequence[float],
    exposure: Sequence[float],
    trades: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    if np is None or len(curve) < 2:
        return {"status": "insufficient_data"}
    return base._metrics(curve, trades, exposure, _f(curve[0], INITIAL_CAPITAL))


def _calendar_years(sim: Dict[str, Any]) -> Dict[str, Any]:
    dates = _l(sim.get("dates"))
    curve = _l(sim.get("equity_curve"))
    exposure = _l(sim.get("exposure_curve"))
    trades = _l(sim.get("trades"))
    grouped: Dict[str, List[int]] = {}
    for index, date in enumerate(dates):
        year = str(date)[:4]
        grouped.setdefault(year, []).append(index)
    out: Dict[str, Any] = {}
    for year, indexes in grouped.items():
        if len(indexes) < 2:
            continue
        lo, hi = indexes[0], indexes[-1]
        year_trades = [trade for trade in trades if str(trade.get("date") or "")[:4] == year]
        out[year] = _slice_metrics(
            dates[lo : hi + 1],
            curve[lo : hi + 1],
            exposure[lo : hi + 1],
            year_trades,
        )
    return out


def _series_summary(values: Sequence[float], exposure: Sequence[float]) -> Dict[str, Any]:
    if np is None or not values:
        return {"status": "insufficient_data", "days": len(values)}
    arr = np.asarray(values, dtype=float)
    compounded = float(np.prod(1.0 + arr) - 1.0)
    curve = np.cumprod(1.0 + arr)
    peaks = np.maximum.accumulate(curve)
    dd = (curve - peaks) / np.maximum(peaks, 1e-9)
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    sharpe = float(np.mean(arr) / std * np.sqrt(252)) if std > 0 else 0.0
    return {
        "status": "ok",
        "days": len(values),
        "return_pct": round(compounded * 100, 2),
        "max_drawdown_pct": round(abs(float(np.min(dd))) * 100, 2),
        "sharpe": round(sharpe, 3),
        "positive_day_pct": round(float(np.mean(arr > 0)) * 100, 2),
        "average_exposure_pct": round(float(np.mean(exposure)) * 100, 2) if exposure else 0.0,
    }


def _regime_report(sim: Dict[str, Any]) -> Dict[str, Any]:
    returns = _l(sim.get("daily_returns"))
    regimes = _l(sim.get("regimes"))
    exposure = _l(sim.get("exposure_curve"))
    out: Dict[str, Any] = {}
    for name in ADAPTIVE_REGIMES:
        values: List[float] = []
        exps: List[float] = []
        for index, value in enumerate(returns):
            regime_index = min(index + 1, len(regimes) - 1)
            if regime_index >= 0 and regimes[regime_index] == name:
                values.append(_f(value))
                if regime_index < len(exposure):
                    exps.append(_f(exposure[regime_index]))
        out[name] = _series_summary(values, exps)
    return out


def _objective(metrics: Dict[str, Any]) -> float:
    if metrics.get("status") != "ok":
        return -9999.0
    return (
        _f(metrics.get("cagr_pct"))
        - 1.20 * _f(metrics.get("max_drawdown_pct"))
        + 7.0 * _f(metrics.get("sharpe"))
        + 0.10 * min(100, _i(metrics.get("trades")))
    )


def _walk_forward(
    features: Dict[str, Any],
    regime_map: Dict[str, Dict[str, Any]],
    dates: Sequence[Any],
    optimize: bool,
) -> Dict[str, Any]:
    if len(dates) < 315:
        return {
            "status": "insufficient_data",
            "formal_walk_forward_passed": False,
            "available_days": len(dates),
        }
    train_days = 252
    test_days = 63
    cursor = train_days
    folds: List[Dict[str, Any]] = []
    combined_returns: List[float] = []
    scales = [0.90, 1.00, 1.10] if optimize else [1.00]

    while cursor + test_days <= len(dates):
        train = dates[cursor - train_days : cursor]
        test = dates[cursor : cursor + test_days]
        trials: List[Dict[str, Any]] = []
        for scale in scales:
            candidate_map = _scaled_regime_map(
                regime_map,
                allocation_scale=scale,
                exposure_scale=scale,
            )
            trained = _simulate_next_open(features, candidate_map, train)
            trials.append(
                {
                    "risk_scale": scale,
                    "metrics": trained["metrics"],
                    "objective": _objective(trained["metrics"]),
                }
            )
        trials.sort(key=lambda row: _f(row.get("objective"), -9999.0), reverse=True)
        selected = trials[0]
        selected_map = _scaled_regime_map(
            regime_map,
            allocation_scale=_f(selected.get("risk_scale"), 1.0),
            exposure_scale=_f(selected.get("risk_scale"), 1.0),
        )
        tested = _simulate_next_open(features, selected_map, test)
        combined_returns.extend(_l(tested.get("daily_returns")))
        folds.append(
            {
                "train_start": str(train[0])[:10],
                "train_end": str(train[-1])[:10],
                "test_start": str(test[0])[:10],
                "test_end": str(test[-1])[:10],
                "selected_risk_scale": selected.get("risk_scale"),
                "train_metrics": selected.get("metrics"),
                "test_metrics": tested.get("metrics"),
                "candidate_trials": trials,
            }
        )
        cursor += test_days

    if not folds:
        return {
            "status": "insufficient_data",
            "formal_walk_forward_passed": False,
            "available_days": len(dates),
        }
    summary = _series_summary(combined_returns, [])
    positive = sum(
        1
        for fold in folds
        if _f(_d(fold.get("test_metrics")).get("total_return_pct")) > 0
    )
    worst_dd = max(
        (_f(_d(fold.get("test_metrics")).get("max_drawdown_pct")) for fold in folds),
        default=0.0,
    )
    positive_ratio = positive / max(1, len(folds))
    passed = bool(
        len(folds) >= 6
        and positive_ratio >= 0.60
        and _f(summary.get("return_pct")) > 0
        and _f(summary.get("sharpe")) > 0.35
        and worst_dd < 25.0
    )
    return {
        "status": "complete",
        "formal_walk_forward_passed": passed,
        "fold_count": len(folds),
        "positive_test_folds": positive,
        "positive_fold_pct": round(positive_ratio * 100, 2),
        "combined_out_of_sample_return_pct": summary.get("return_pct"),
        "combined_out_of_sample_sharpe": summary.get("sharpe"),
        "combined_out_of_sample_max_drawdown_pct": summary.get("max_drawdown_pct"),
        "worst_test_fold_drawdown_pct": round(worst_dd, 2),
        "coverage": {
            "first_test_start": folds[0]["test_start"],
            "last_test_end": folds[-1]["test_end"],
            "uncovered_tail_days": max(0, len(dates) - cursor),
        },
        "folds": folds,
    }


def _coverage(frames: Dict[str, Any], dates: Sequence[Any]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for symbol, frame in frames.items():
        index = list(getattr(frame, "index", []))
        rows.append(
            {
                "symbol": symbol,
                "days": len(index),
                "start": str(index[0])[:10] if index else None,
                "end": str(index[-1])[:10] if index else None,
                "coverage_pct": round(len(index) / max(1, len(dates)) * 100, 2),
            }
        )
    rows.sort(key=lambda row: row["coverage_pct"])
    incomplete = [row for row in rows if _f(row.get("coverage_pct")) < 90.0]
    return {
        "symbols": rows,
        "incomplete_symbols": incomplete,
        "incomplete_symbol_count": len(incomplete),
        "minimum_coverage_pct": min((_f(row.get("coverage_pct")) for row in rows), default=0.0),
    }


def _ablation_maps() -> Dict[str, Dict[str, Dict[str, Any]]]:
    baseline = copy.deepcopy(ADAPTIVE_REGIMES)
    variants: Dict[str, Dict[str, Dict[str, Any]]] = {"adaptive_baseline": baseline}

    for count in (2, 3, 4, 6):
        variant = copy.deepcopy(baseline)
        for regime in ("strong_risk_on", "risk_on", "constructive"):
            variant[regime]["max_positions"] = count
            variant[regime]["max_exposure"] = min(
                0.72,
                max(
                    variant[regime]["target_allocation"],
                    variant[regime]["target_allocation"] * count,
                ),
            )
        variants[f"max_positions_{count}"] = variant

    for confirmations in (3, 5):
        variant = copy.deepcopy(baseline)
        for regime in ("strong_risk_on", "risk_on", "constructive", "neutral"):
            variant[regime]["min_confirmations"] = confirmations
        variants[f"confirmations_{confirmations}"] = variant

    for require in (False, True):
        variant = copy.deepcopy(baseline)
        for regime in ("strong_risk_on", "risk_on", "constructive", "neutral"):
            variant[regime]["require_ma50"] = require
        variants[f"ma50_{'on' if require else 'off'}"] = variant

    for allocation in (0.12, 0.16, 0.18):
        variant = copy.deepcopy(baseline)
        for regime in ("strong_risk_on", "risk_on", "constructive"):
            variant[regime]["target_allocation"] = allocation
            variant[regime]["max_exposure"] = min(0.72, allocation * 4)
        variants[f"allocation_{int(allocation * 100)}pct"] = variant

    for hold in (7, 10, 12):
        variant = copy.deepcopy(baseline)
        for policy in variant.values():
            policy["max_hold_days"] = hold
        variants[f"hold_{hold}d"] = variant

    for stop in (0.012, 0.015, 0.018):
        variant = copy.deepcopy(baseline)
        for policy in variant.values():
            policy["stop_loss"] = stop
        variants[f"stop_{stop * 100:.1f}pct"] = variant

    return variants


def _run_ablation(
    features: Dict[str, Any],
    dates: Sequence[Any],
    baseline_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    baseline_return = _f(baseline_metrics.get("total_return_pct"))
    baseline_dd = _f(baseline_metrics.get("max_drawdown_pct"))
    baseline_sharpe = _f(baseline_metrics.get("sharpe"))
    for name, regime_map in _ablation_maps().items():
        sim = _simulate_next_open(features, regime_map, dates)
        metrics = sim["metrics"]
        results.append(
            {
                "variant": name,
                **metrics,
                "delta_total_return_pct": round(
                    _f(metrics.get("total_return_pct")) - baseline_return, 2
                ),
                "delta_max_drawdown_pct": round(
                    _f(metrics.get("max_drawdown_pct")) - baseline_dd, 2
                ),
                "delta_sharpe": round(_f(metrics.get("sharpe")) - baseline_sharpe, 3),
                "objective": round(_objective(metrics), 3),
            }
        )
    results.sort(key=lambda row: _f(row.get("objective"), -9999.0), reverse=True)
    return {
        "status": "ok",
        "baseline": "adaptive_baseline",
        "variant_count": len(results),
        "ranking": results,
        "best_variant": results[0] if results else None,
        "interpretation": (
            "Each variant changes one parameter family from the adaptive baseline. "
            "Results remain daily-bar proxies and should be confirmed by forward shadow data."
        ),
    }


def _profile_payload(
    features: Dict[str, Any],
    dates: Sequence[Any],
    regime_map: Dict[str, Dict[str, Any]],
    optimize_walk_forward: bool,
) -> Dict[str, Any]:
    sim = _simulate_next_open(features, regime_map, dates)
    return {
        "full_sample": sim["metrics"],
        "calendar_years": _calendar_years(sim),
        "regime_report": _regime_report(sim),
        "walk_forward": _walk_forward(
            features,
            regime_map,
            dates,
            optimize=optimize_walk_forward,
        ),
        "trade_sample": _l(sim.get("trades"))[-30:],
    }


def run(
    core: Any = None,
    period: str = AUTO_PERIOD,
    max_symbols: int = AUTO_MAX_SYMBOLS,
    force: bool = False,
    include_ablation: bool = True,
) -> Dict[str, Any]:
    core = core or _core()
    if core is None:
        return {
            "status": "pending",
            "type": "performance_backtest_v2",
            "version": VERSION,
            "reason": "core_missing",
        }
    if not ENABLED:
        return {"status": "disabled", "type": "performance_backtest_v2", "version": VERSION}

    section = _section(core)
    runs = section.setdefault("runs", {})
    if not isinstance(runs, dict):
        runs = {}
        section["runs"] = runs
    key = f"{period}:{max_symbols}:ablation={bool(include_ablation)}"
    prior = _d(runs.get(key))
    if not force and prior.get("status") == "ok":
        stamp = _f(prior.get("generated_epoch"))
        if stamp and time.time() - stamp < STALE_HOURS * 3600:
            return prior
    if not _RUN_LOCK.acquire(blocking=False):
        return {
            "status": "running",
            "type": "performance_backtest_v2",
            "version": VERSION,
            "started_local": section.get("started_local"),
        }

    try:
        section["status"] = "running"
        section["started_local"] = _now(core)
        symbols = _universe(core, max_symbols)
        frames, provider = base._download(symbols, period)
        features = base._feature_frames(frames)
        dates = base._calendar(features)
        if len(dates) < 315 or len(features) < 10:
            result = {
                "status": "error",
                "type": "performance_backtest_v2",
                "version": VERSION,
                "generated_local": _now(core),
                "generated_epoch": time.time(),
                "reason": "insufficient_historical_data",
                "provider": provider,
                "available_days": len(dates),
                "loaded_symbols": len(features),
            }
            runs[key] = result
            section["status"] = "error"
            _save(core)
            return result

        profiles: Dict[str, Any] = {}
        for name, policy in STATIC_PROFILES.items():
            payload = _profile_payload(
                features,
                dates,
                _static_regime_map(policy),
                optimize_walk_forward=False,
            )
            payload["description"] = policy.get("description")
            payload["policy"] = base._json_safe(policy)
            profiles[name] = payload

        adaptive = _profile_payload(
            features,
            dates,
            copy.deepcopy(ADAPTIVE_REGIMES),
            optimize_walk_forward=True,
        )
        adaptive["description"] = (
            "Regime-adaptive balanced participation with next-session-open execution "
            "and defensive/inverse-ETF sleeves in deteriorating regimes."
        )
        adaptive["regime_policies"] = base._json_safe(ADAPTIVE_REGIMES)
        profiles["adaptive_balanced"] = adaptive

        benchmarks = {
            "SPY_buy_hold": base._benchmark(frames.get("SPY"), dates),
            "QQQ_buy_hold": base._benchmark(frames.get("QQQ"), dates),
        }
        ranking = sorted(
            [
                {
                    "profile": name,
                    **_d(payload.get("full_sample")),
                    "walk_forward_passed": _d(payload.get("walk_forward")).get(
                        "formal_walk_forward_passed"
                    ),
                    "out_of_sample_return_pct": _d(payload.get("walk_forward")).get(
                        "combined_out_of_sample_return_pct"
                    ),
                    "out_of_sample_sharpe": _d(payload.get("walk_forward")).get(
                        "combined_out_of_sample_sharpe"
                    ),
                    "positive_fold_pct": _d(payload.get("walk_forward")).get(
                        "positive_fold_pct"
                    ),
                }
                for name, payload in profiles.items()
            ],
            key=lambda row: (
                bool(row.get("walk_forward_passed")),
                _f(row.get("out_of_sample_sharpe")),
                _f(row.get("out_of_sample_return_pct")),
                _f(row.get("sharpe")),
            ),
            reverse=True,
        )

        adaptive_metrics = _d(adaptive.get("full_sample"))
        ablation = (
            _run_ablation(features, dates, adaptive_metrics)
            if include_ablation
            else {"status": "not_requested"}
        )
        coverage = _coverage(frames, dates)
        current_metrics = _d(_d(profiles.get("current_proxy")).get("full_sample"))
        result = {
            "status": "ok",
            "type": "performance_backtest_v2",
            "version": VERSION,
            "generated_local": _now(core),
            "generated_epoch": time.time(),
            "period": period,
            "requested_symbols": symbols,
            "loaded_symbols": sorted(features),
            "provider": provider,
            "trading_days": len(dates),
            "date_range": {
                "start": str(dates[0])[:10],
                "end": str(dates[-1])[:10],
            },
            "profiles": profiles,
            "ranking": ranking,
            "benchmarks": benchmarks,
            "ablation": ablation,
            "universe_coverage": coverage,
            "opportunity_cost": {
                "adaptive_minus_current_total_return_pct": round(
                    _f(adaptive_metrics.get("total_return_pct"))
                    - _f(current_metrics.get("total_return_pct")),
                    2,
                ),
                "adaptive_minus_current_max_drawdown_pct": round(
                    _f(adaptive_metrics.get("max_drawdown_pct"))
                    - _f(current_metrics.get("max_drawdown_pct")),
                    2,
                ),
                "adaptive_minus_current_average_exposure_pct": round(
                    _f(adaptive_metrics.get("average_exposure_pct"))
                    - _f(current_metrics.get("average_exposure_pct")),
                    2,
                ),
            },
            "methodology": {
                "execution_assumption": "signals_at_close_entries_next_session_open",
                "transaction_cost_bps": TRANSACTION_COST_BPS,
                "full_history_walk_forward": True,
                "walk_forward_train_days": 252,
                "walk_forward_test_days": 63,
                "walk_forward_fold_cap": None,
                "regime_segmentation": True,
                "calendar_year_reporting": True,
                "ablation": bool(include_ablation),
                "exact_intraday_replay": False,
            },
            "bias_warnings": [
                (
                    "The symbol list is not a point-in-time historical universe. Present-day "
                    "leaders and surviving securities create survivorship and selection bias."
                ),
                (
                    "Daily OHLC data cannot reproduce five-minute scanner timing, VWAP/reclaim "
                    "logic, provider latency, or exact stop sequencing."
                ),
                (
                    "Inverse ETFs are used as defensive proxies; this is not a replay of the "
                    "runtime short engine."
                ),
            ],
            "activation_gate": {
                "automatic_strategy_promotion": False,
                "requires_forward_shadow_confirmation": True,
                "minimum_forward_candidates": 30,
                "minimum_one_day_outcomes": 20,
                "paper_only": True,
            },
            "authority": {
                "advisory_only": True,
                "changes_strategy": False,
                "changes_thresholds": False,
                "changes_sizing": False,
                "changes_live_authority": False,
                "changes_ml_authority": False,
                "places_orders": False,
            },
        }
        runs[key] = result
        section["latest_key"] = key
        section["latest"] = result
        section["status"] = "ok"
        _save(core)
        return result
    except Exception as exc:
        result = {
            "status": "error",
            "type": "performance_backtest_v2",
            "version": VERSION,
            "generated_local": _now(core),
            "generated_epoch": time.time(),
            "error": f"{type(exc).__name__}: {exc}",
        }
        runs[key] = result
        section["status"] = "error"
        _save(core)
        return result
    finally:
        _RUN_LOCK.release()


def status(core: Any = None) -> Dict[str, Any]:
    core = core or _core()
    if core is None:
        return {
            "status": "pending",
            "type": "performance_audit_v2_status",
            "version": VERSION,
            "reason": "core_missing",
        }
    section = _section(core)
    latest = _d(section.get("latest"))
    return {
        "status": "ok",
        "type": "performance_audit_v2_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": ENABLED,
        "run_status": section.get("status") or "not_run",
        "latest_key": section.get("latest_key"),
        "latest": latest if latest else {"status": "not_run"},
        "settings": {
            "auto_backtest": AUTO_BACKTEST,
            "auto_period": AUTO_PERIOD,
            "auto_max_symbols": AUTO_MAX_SYMBOLS,
            "stale_hours": STALE_HOURS,
            "transaction_cost_bps": TRANSACTION_COST_BPS,
        },
        "routes": {
            "run": "/paper/performance-backtest-v2",
            "status": "/paper/performance-audit-v2-status",
            "ablation": "/paper/performance-ablation-v2",
            "regime": "/paper/performance-regime-report-v2",
        },
        "authority": {
            "advisory_only": True,
            "changes_strategy": False,
            "places_orders": False,
        },
    }


def _market_open(core: Any) -> bool:
    try:
        return bool(_d(core.market_clock()).get("is_open"))
    except Exception:
        return False


def _stale(core: Any) -> bool:
    latest = _d(_section(core).get("latest"))
    stamp = _f(latest.get("generated_epoch"))
    return not stamp or time.time() - stamp >= STALE_HOURS * 3600


def _watchdog(core: Any) -> None:
    while True:
        try:
            if (
                AUTO_BACKTEST
                and not _market_open(core)
                and _stale(core)
                and not _RUN_LOCK.locked()
            ):
                threading.Thread(
                    target=run,
                    kwargs={
                        "core": core,
                        "period": AUTO_PERIOD,
                        "max_symbols": AUTO_MAX_SYMBOLS,
                        "force": True,
                        "include_ablation": True,
                    },
                    name="performance-audit-v2-run",
                    daemon=True,
                ).start()
        except Exception as exc:
            _section(core)["watchdog_error"] = f"{type(exc).__name__}: {exc}"
        time.sleep(WATCHDOG_SECONDS)


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _core()
    if core is None:
        return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    with _LOCK:
        if id(core) not in _WATCHDOGS:
            _WATCHDOGS.add(id(core))
            threading.Thread(
                target=_watchdog,
                args=(core,),
                name="performance-audit-v2-watchdog",
                daemon=True,
            ).start()
        setattr(core, "PERFORMANCE_AUDIT_LAB_V2_VERSION", VERSION)
        return {
            "status": "ok",
            "overall": "pass",
            "version": VERSION,
            "watchdog_started": True,
            "authority": {
                "advisory_only": True,
                "places_orders": False,
            },
        }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "reason": "flask_app_missing"}
    core = core or _core()
    apply(core)
    if id(flask_app) in _REGISTERED:
        return {"status": "ok", "version": VERSION, "already_registered": True}

    from flask import jsonify, request

    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}

    def status_route():
        return jsonify(status(core or _core()))

    def run_route():
        runtime = core or _core()
        period = str(request.args.get("period") or AUTO_PERIOD)
        max_symbols = max(20, min(75, _i(request.args.get("symbols"), AUTO_MAX_SYMBOLS)))
        force = str(request.args.get("force") or "false").lower() in {
            "1", "true", "yes", "on"
        }
        include_ablation = str(request.args.get("ablation") or "true").lower() in {
            "1", "true", "yes", "on"
        }
        return jsonify(
            run(
                runtime,
                period=period,
                max_symbols=max_symbols,
                force=force,
                include_ablation=include_ablation,
            )
        )

    def ablation_route():
        latest = _d(_section(core or _core()).get("latest"))
        return jsonify(
            {
                "status": latest.get("status") or "not_run",
                "type": "performance_ablation_v2",
                "version": VERSION,
                "generated_local": latest.get("generated_local"),
                "ablation": latest.get("ablation") or {"status": "not_run"},
                "authority": {"advisory_only": True, "places_orders": False},
            }
        )

    def regime_route():
        latest = _d(_section(core or _core()).get("latest"))
        profiles = _d(latest.get("profiles"))
        return jsonify(
            {
                "status": latest.get("status") or "not_run",
                "type": "performance_regime_report_v2",
                "version": VERSION,
                "generated_local": latest.get("generated_local"),
                "profiles": {
                    name: {
                        "calendar_years": _d(payload).get("calendar_years"),
                        "regime_report": _d(payload).get("regime_report"),
                        "walk_forward": _d(payload).get("walk_forward"),
                    }
                    for name, payload in profiles.items()
                },
                "authority": {"advisory_only": True, "places_orders": False},
            }
        )

    routes = (
        ("/paper/performance-audit-v2-status", "performance_audit_v2_status", status_route),
        ("/paper/performance-backtest-v2", "performance_backtest_v2", run_route),
        ("/paper/performance-ablation-v2", "performance_ablation_v2", ablation_route),
        ("/paper/performance-regime-report-v2", "performance_regime_report_v2", regime_route),
    )
    for path, endpoint, fn in routes:
        if path not in existing:
            flask_app.add_url_rule(path, endpoint, fn)
    _REGISTERED.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [row[0] for row in routes]}


try:
    apply(_core())
except Exception:
    pass
