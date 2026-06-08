"""Targeted paper-state repair for market surge queue entries.

Fixes a known paper-only state accounting issue where a surge queue entry
reduced cash but saved a position with entry=0 and shares=0.

Routes:
- /paper/surge-state-repair-status
- /paper/surge-state-repair?confirm=1

This module does not trade, does not change ML authority, and does not alter
live-trading settings. It only completes the malformed paper SPY position when
that exact broken pattern is detected.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict

VERSION = "surge-state-repair-2026-06-08-v2-ascii-safe"
REGISTERED_APP_IDS: set[int] = set()

SPY_REPAIR = {
    "symbol": "SPY",
    "entry": 739.22,
    "shares": 1.182638,
    "allocation": 874.23,
    "side": "long",
    "sector": "SPY",
    "score": 0.0,
}


def _now(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def _portfolio(core: Any = None) -> Dict[str, Any]:
    try:
        pf = getattr(core, "portfolio", {})
        return pf if isinstance(pf, dict) else {}
    except Exception:
        return {}


def _load_state(core: Any = None) -> Dict[str, Any]:
    try:
        state = core.load_state()
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _positions(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    obj = pf.get("positions")
    if not isinstance(obj, dict):
        obj = state.get("positions")
    if not isinstance(obj, dict):
        obj = {}
        pf["positions"] = obj
    return obj


def _save(core: Any, pf: Dict[str, Any]) -> Dict[str, Any]:
    attempted = False
    ok = False
    error = None

    try:
        save_fn = getattr(core, "save_state", None)
        if callable(save_fn):
            attempted = True
            try:
                save_fn(pf)
            except TypeError:
                save_fn()
            ok = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    return {
        "save_attempted": attempted,
        "save_ok": ok,
        "save_error": error,
    }


def _compute_pnl(entry: float, last_price: float, shares: float) -> Dict[str, float]:
    pnl_dollars = (last_price - entry) * shares if entry and shares else 0.0
    pnl_pct = ((last_price - entry) / entry) * 100.0 if entry else 0.0
    return {
        "pnl_dollars": round(pnl_dollars, 4),
        "pnl_pct": round(pnl_pct, 4),
    }


def _status(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core)
    state = _load_state(core)
    positions = _positions(pf, state)

    spy = positions.get("SPY")
    if not isinstance(spy, dict):
        spy = None

    broken = False
    if spy is not None:
        broken = (
            _safe_float(spy.get("entry")) <= 0.0
            or _safe_float(spy.get("shares")) <= 0.0
        )

    cash = _safe_float(pf.get("cash", state.get("cash", 0.0)))
    equity = _safe_float(pf.get("equity", state.get("equity", 0.0)))

    return {
        "status": "ok",
        "overall": "warn" if broken else "pass",
        "type": "surge_state_repair_status",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
        "repair_needed": broken,
        "detected_position": spy,
        "cash": round(cash, 4),
        "equity": round(equity, 4),
        "repair_plan": {
            "symbol": "SPY",
            "entry": SPY_REPAIR["entry"],
            "shares": SPY_REPAIR["shares"],
            "cash_action": "no_cash_change",
            "reason": (
                "Cash was already deducted by the prior paper surge executor run; "
                "complete the malformed position only."
            ),
        },
        "guardrails": {
            "does_not_trade": True,
            "does_not_change_cash": True,
            "does_not_change_ml_authority": True,
            "does_not_enable_live_trading": True,
        },
    }


def apply_repair(core: Any = None, confirm: bool = False) -> Dict[str, Any]:
    status = _status(core)

    if not confirm:
        status["executed"] = False
        status["message"] = "Preview only. Add confirm=1 to execute the repair."
        return status

    if not status.get("repair_needed"):
        status["executed"] = False
        status["message"] = "No matching broken SPY paper position found."
        return status

    pf = _portfolio(core)
    state = _load_state(core)
    positions = _positions(pf, state)

    spy = positions.get("SPY")
    if not isinstance(spy, dict):
        spy = {}

    entry = float(SPY_REPAIR["entry"])
    shares = float(SPY_REPAIR["shares"])

    last_price = _safe_float(spy.get("last_price"), entry)
    if last_price <= 0:
        last_price = entry

    pnl = _compute_pnl(entry, last_price, shares)

    repaired = dict(spy)
    repaired.update(
        {
            "entry": round(entry, 4),
            "shares": round(shares, 6),
            "last_price": round(last_price, 4),
            "side": "long",
            "sector": "SPY",
            "score": _safe_float(spy.get("score"), 0.0),
            "adds": _safe_int(spy.get("adds"), 0),
            "entry_time": spy.get("entry_time") or int(dt.datetime.now().timestamp()),
            "pnl_dollars": pnl["pnl_dollars"],
            "pnl_pct": pnl["pnl_pct"],
            "entry_tag": repaired.get("entry_tag") or "paper_surge_entry_repaired",
            "trade_authority": "paper_only_state_entry",
            "ml_authority": "shadow_only",
            "repair_version": VERSION,
        }
    )

    positions["SPY"] = repaired
    pf["positions"] = positions

    cash = _safe_float(pf.get("cash", state.get("cash", 0.0)))
    market_value = 0.0
    unrealized = 0.0

    for pos in positions.values():
        if not isinstance(pos, dict):
            continue

        qty = _safe_float(pos.get("shares"))
        lp = _safe_float(pos.get("last_price"), _safe_float(pos.get("entry")))
        ent = _safe_float(pos.get("entry"), lp)

        market_value += qty * lp

        if qty and ent:
            unrealized += (lp - ent) * qty
        else:
            unrealized += _safe_float(pos.get("pnl_dollars"), 0.0)

    if cash:
        pf["equity"] = round(cash + market_value, 4)

    perf = pf.get("performance")
    if not isinstance(perf, dict):
        perf = {}

    perf["open_positions"] = positions
    perf["unrealized_pnl"] = round(unrealized, 4)
    pf["performance"] = perf

    save_result = _save(core, pf)

    after = _status(core)
    after.update(
        {
            "executed": True,
            "message": "Repaired malformed SPY paper surge position. Cash was not changed.",
            "repaired_position": repaired,
            "persistence": save_result,
        }
    )
    return after


def apply(core: Any = None) -> Dict[str, Any]:
    return _status(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    from flask import jsonify, request

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/surge-state-repair-status" not in existing:
        flask_app.add_url_rule(
            "/paper/surge-state-repair-status",
            "surge_state_repair_status",
            lambda: jsonify(_status(core)),
        )

    if "/paper/surge-state-repair" not in existing:

        def repair_route():
            confirm = str(request.args.get("confirm", "0")).lower() in {
                "1",
                "true",
                "yes",
            }
            return jsonify(apply_repair(core, confirm=confirm))

        flask_app.add_url_rule(
            "/paper/surge-state-repair",
            "surge_state_repair",
            repair_route,
        )

    REGISTERED_APP_IDS.add(id(flask_app))
