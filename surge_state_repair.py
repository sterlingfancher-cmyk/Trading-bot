"""Targeted paper-state repair for market surge queue entries.

Fixes paper-only state accounting issues from market surge queue execution.

Routes:
- /paper/surge-state-repair-status
- /paper/surge-state-repair?confirm=1

This module does not trade, does not change cash, does not change ML authority,
and does not enable live trading.

It can repair:
1. A malformed SPY paper surge position missing legacy aliases:
   entry / shares
2. Stale risk-control drawdown flags left at 8.0 after the SPY repair is valid.
3. A stale halted=True / halt_reason="daily loss limit hit" flag when account
   reality is clean.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict

VERSION = "surge-state-repair-2026-06-08-v4-clear-stale-halt-flag"
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


def _performance(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    obj = pf.get("performance")
    if not isinstance(obj, dict):
        obj = state.get("performance")
    if not isinstance(obj, dict):
        obj = {}
    return obj


def _risk_controls(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    obj = pf.get("risk_controls")
    if not isinstance(obj, dict):
        obj = state.get("risk_controls")
    if not isinstance(obj, dict):
        obj = {}
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


def _spy_position(positions: Dict[str, Any]) -> Dict[str, Any] | None:
    spy = positions.get("SPY")
    return spy if isinstance(spy, dict) else None


def _alias_repair_needed(spy: Dict[str, Any] | None) -> bool:
    if spy is None:
        return False

    entry = _safe_float(spy.get("entry"))
    shares = _safe_float(spy.get("shares"))

    return entry <= 0.0 or shares <= 0.0


def _spy_complete(spy: Dict[str, Any] | None) -> bool:
    if spy is None:
        return False

    entry = _safe_float(spy.get("entry"))
    shares = _safe_float(spy.get("shares"))

    return entry > 0.0 and shares > 0.0


def _account_reality_clean(
    pf: Dict[str, Any],
    state: Dict[str, Any],
    spy: Dict[str, Any] | None,
) -> bool:
    if not _spy_complete(spy):
        return False

    risk = _risk_controls(pf, state)
    perf = _performance(pf, state)

    self_defense_active = bool(risk.get("self_defense_active", False))
    realized_today = _safe_float(
        perf.get("realized_pnl_today", perf.get("realized_today", 0.0))
    )
    losses_today = _safe_int(perf.get("losses_today", 0))

    return (
        not self_defense_active
        and realized_today >= 0.0
        and losses_today == 0
    )


def _stale_drawdown_repair_needed(
    pf: Dict[str, Any],
    state: Dict[str, Any],
    spy: Dict[str, Any] | None,
) -> bool:
    if not _account_reality_clean(pf, state, spy):
        return False

    risk = _risk_controls(pf, state)

    daily_loss_pct = _safe_float(risk.get("daily_loss_pct"))
    daily_drawdown_pct = _safe_float(risk.get("daily_drawdown_pct"))
    intraday_drawdown_pct = _safe_float(risk.get("intraday_drawdown_pct"))

    return (
        daily_loss_pct >= 7.5
        or daily_drawdown_pct >= 7.5
        or intraday_drawdown_pct >= 7.5
    )


def _stale_halt_repair_needed(
    pf: Dict[str, Any],
    state: Dict[str, Any],
    spy: Dict[str, Any] | None,
) -> bool:
    if not _account_reality_clean(pf, state, spy):
        return False

    risk = _risk_controls(pf, state)

    halted = bool(risk.get("halted", False))
    halt_reason = str(risk.get("halt_reason", "") or "").lower()

    if not halted:
        return False

    stale_daily_loss_halt = (
        "daily loss" in halt_reason
        or "loss limit" in halt_reason
        or "drawdown" in halt_reason
    )

    daily_loss_pct = _safe_float(risk.get("daily_loss_pct"))
    daily_drawdown_pct = _safe_float(risk.get("daily_drawdown_pct"))
    intraday_drawdown_pct = _safe_float(risk.get("intraday_drawdown_pct"))

    drawdowns_now_clean = (
        daily_loss_pct <= 0.01
        and daily_drawdown_pct <= 0.01
        and intraday_drawdown_pct <= 0.01
    )

    return stale_daily_loss_halt and drawdowns_now_clean


def _repair_spy_aliases(spy: Dict[str, Any]) -> Dict[str, Any]:
    entry = _safe_float(spy.get("entry"), 0.0)
    if entry <= 0.0:
        entry = _safe_float(spy.get("entry_price"), SPY_REPAIR["entry"])
    if entry <= 0.0:
        entry = float(SPY_REPAIR["entry"])

    shares = _safe_float(spy.get("shares"), 0.0)
    if shares <= 0.0:
        shares = _safe_float(spy.get("qty"), SPY_REPAIR["shares"])
    if shares <= 0.0:
        shares = float(SPY_REPAIR["shares"])

    last_price = _safe_float(spy.get("last_price"), entry)
    if last_price <= 0.0:
        last_price = entry

    pnl = _compute_pnl(entry, last_price, shares)

    repaired = dict(spy)
    repaired.update(
        {
            "entry": round(entry, 4),
            "entry_price": round(entry, 4),
            "shares": round(shares, 6),
            "qty": round(shares, 6),
            "last_price": round(last_price, 4),
            "market_value": round(shares * last_price, 4),
            "cost_basis": round(shares * entry, 4),
            "side": repaired.get("side") or "long",
            "sector": repaired.get("sector") or "SPY",
            "score": _safe_float(repaired.get("score"), 0.0),
            "adds": _safe_int(repaired.get("adds"), 0),
            "entry_time": repaired.get("entry_time") or int(dt.datetime.now().timestamp()),
            "pnl_dollars": pnl["pnl_dollars"],
            "pnl_pct": pnl["pnl_pct"],
            "entry_tag": repaired.get("entry_tag") or "paper_surge_entry_repaired",
            "trade_authority": "paper_only_state_entry",
            "live_trade_authority": "none",
            "ml_authority": "shadow_only",
            "repair_version": VERSION,
        }
    )
    return repaired


def _recompute_portfolio_totals(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    positions = _positions(pf, state)
    cash = _safe_float(pf.get("cash", state.get("cash", 0.0)))

    market_value = 0.0
    unrealized = 0.0

    for pos in positions.values():
        if not isinstance(pos, dict):
            continue

        shares = _safe_float(pos.get("shares"), _safe_float(pos.get("qty")))
        entry = _safe_float(pos.get("entry"), _safe_float(pos.get("entry_price")))
        last_price = _safe_float(pos.get("last_price"), entry)

        if shares > 0.0 and last_price > 0.0:
            market_value += shares * last_price

        if shares > 0.0 and entry > 0.0 and last_price > 0.0:
            unrealized += (last_price - entry) * shares
        else:
            unrealized += _safe_float(
                pos.get("pnl_dollars", pos.get("unrealized_pnl", 0.0))
            )

    pf["positions"] = positions
    pf["equity"] = round(cash + market_value, 4)

    perf = _performance(pf, state)
    perf["open_positions"] = positions
    perf["unrealized_pnl"] = round(unrealized, 4)
    pf["performance"] = perf

    return {
        "cash": round(cash, 4),
        "market_value": round(market_value, 4),
        "equity": pf["equity"],
        "unrealized_pnl": perf["unrealized_pnl"],
    }


def _status(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core)
    state = _load_state(core)
    positions = _positions(pf, state)
    spy = _spy_position(positions)

    risk = _risk_controls(pf, state)

    alias_needed = _alias_repair_needed(spy)
    stale_drawdown_needed = _stale_drawdown_repair_needed(pf, state, spy)
    stale_halt_needed = _stale_halt_repair_needed(pf, state, spy)

    repair_needed = alias_needed or stale_drawdown_needed or stale_halt_needed

    cash = _safe_float(pf.get("cash", state.get("cash", 0.0)))
    equity = _safe_float(pf.get("equity", state.get("equity", 0.0)))

    return {
        "status": "ok",
        "overall": "warn" if repair_needed else "pass",
        "type": "surge_state_repair_status",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
        "repair_needed": repair_needed,
        "alias_repair_needed": alias_needed,
        "stale_drawdown_repair_needed": stale_drawdown_needed,
        "stale_halt_repair_needed": stale_halt_needed,
        "detected_position": spy,
        "risk_controls": risk,
        "cash": round(cash, 4),
        "equity": round(equity, 4),
        "repair_plan": {
            "symbol": "SPY",
            "entry": SPY_REPAIR["entry"],
            "shares": SPY_REPAIR["shares"],
            "cash_action": "no_cash_change",
            "risk_action": (
                "clear stale drawdown/halt flags only if SPY is complete, "
                "self-defense is inactive, realized_today is nonnegative, and losses_today is zero"
            ),
            "reason": (
                "Cash was already deducted by the prior paper surge executor run; "
                "complete malformed aliases and clear stale risk flags only when the account reality is clean."
            ),
        },
        "guardrails": {
            "does_not_trade": True,
            "does_not_change_cash": True,
            "does_not_change_ml_authority": True,
            "does_not_enable_live_trading": True,
            "does_not_bypass_hard_blocks": True,
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
        status["message"] = "No repair needed."
        return status

    pf = _portfolio(core)
    state = _load_state(core)
    positions = _positions(pf, state)
    spy = _spy_position(positions)

    actions = []

    if status.get("alias_repair_needed") and spy is not None:
        repaired_spy = _repair_spy_aliases(spy)
        positions["SPY"] = repaired_spy
        pf["positions"] = positions
        actions.append("repaired_spy_position_aliases")

    if status.get("stale_drawdown_repair_needed") or status.get("stale_halt_repair_needed"):
        risk = _risk_controls(pf, state)
        risk["daily_loss_pct"] = 0.0
        risk["daily_drawdown_pct"] = 0.0
        risk["intraday_drawdown_pct"] = 0.0
        risk["halted"] = False
        risk["halt_reason"] = ""
        risk["self_defense_active"] = False
        risk["self_defense_reason"] = "feedback loop clear"
        risk["surge_state_repair_version"] = VERSION
        risk["surge_state_repair_time"] = _now(core)
        pf["risk_controls"] = risk
        actions.append("cleared_stale_drawdown_and_halt_flags")

    totals = _recompute_portfolio_totals(pf, state)
    save_result = _save(core, pf)

    after = _status(core)
    after.update(
        {
            "executed": True,
            "message": "Applied surge state repair. Cash was not changed.",
            "actions": actions,
            "post_repair_totals": totals,
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
