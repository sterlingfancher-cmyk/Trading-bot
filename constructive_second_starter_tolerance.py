"""Controlled paper-only tolerance for a second diversified starter.

The original underdeployment gate blocks every additional position when the first
starter is down more than 0.50%, even when that starter is only about 10% of the
account, the account drawdown is roughly one tenth of one percent, the market is
constructive, cash is high, and all realized-loss controls are clear.

This module allows the existing gate to re-evaluate with a 1.25% first-position
mark-to-market tolerance only in that narrow state. The original gate still owns
spacing, daily entry limits, position limits, sector/bucket diversification, and
all exposure checks. This module is paper-only and never places an order.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Iterable

VERSION = "constructive-second-starter-tolerance-2026-08-04-v1"
ENABLED = os.environ.get("CONSTRUCTIVE_SECOND_STARTER_TOLERANCE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MIN_FIRST_POSITION_PNL = float(os.environ.get("CONSTRUCTIVE_SECOND_STARTER_MIN_FIRST_PNL_PCT", "-0.0125"))
MAX_ACCOUNT_DAILY_LOSS_PCT = float(os.environ.get("CONSTRUCTIVE_SECOND_STARTER_MAX_DAILY_LOSS_PCT", "0.15"))
MAX_ACCOUNT_DRAWDOWN_PCT = float(os.environ.get("CONSTRUCTIVE_SECOND_STARTER_MAX_DRAWDOWN_PCT", "0.15"))
MIN_CASH_PCT = float(os.environ.get("CONSTRUCTIVE_SECOND_STARTER_MIN_CASH_PCT", "0.80"))
ALLOWED_MODES = {x.strip().lower() for x in os.environ.get("CONSTRUCTIVE_SECOND_STARTER_ALLOWED_MODES", "constructive,risk_on").split(",") if x.strip()}

_LOCK = threading.RLock()
_PATCHED_MODULES: Dict[str, Dict[str, Any]] = {}
_LAST: Dict[str, Any] = {}
_REGISTERED_APP_IDS: set[int] = set()


def _matching_modules() -> Iterable[tuple[str, Any]]:
    seen: set[int] = set()
    for name, module in list(sys.modules.items()):
        if module is None or id(module) in seen:
            continue
        module_file = str(getattr(module, "__file__", "") or "")
        try:
            file_match = Path(module_file).name == "paper_underdeployment_repair.py"
        except Exception:
            file_match = module_file.endswith("paper_underdeployment_repair.py")
        if name == "paper_underdeployment_repair" or file_match:
            seen.add(id(module))
            yield name, module


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _state(module: Any, core: Any) -> Dict[str, Any]:
    try:
        value = module._state(core)
    except Exception:
        value = getattr(core, "portfolio", {})
    return value if isinstance(value, dict) else {}


def _qualify(module: Any, core: Any) -> tuple[bool, Dict[str, Any]]:
    state = _state(module, core)
    try:
        positions = module._positions(core)
    except Exception:
        positions = state.get("positions") or {}
    positions = positions if isinstance(positions, dict) else {}
    try:
        market = module._market(core)
    except Exception:
        market = state.get("last_market") or {}
    market = market if isinstance(market, dict) else {}
    try:
        risk = module._risk(core)
    except Exception:
        risk = {}
    risk = risk if isinstance(risk, dict) else {}
    try:
        exposure = module._exposure(core)
    except Exception:
        equity = max(_safe_float(state.get("equity"), _safe_float(state.get("cash"), 0.0)), 0.01)
        exposure = {"cash_pct": _safe_float(state.get("cash"), 0.0) / equity}
    exposure = exposure if isinstance(exposure, dict) else {}

    first_rows = []
    worst_pnl = 0.0
    for symbol, raw in positions.items():
        row = raw if isinstance(raw, dict) else {}
        try:
            pnl = module._pnl(row)
        except Exception:
            pnl = None
        if pnl is not None:
            pnl = _safe_float(pnl)
            worst_pnl = min(worst_pnl, pnl)
        first_rows.append({
            "symbol": str(symbol).upper(),
            "pnl_pct": None if pnl is None else round(pnl * 100.0, 4),
        })

    performance = state.get("performance") if isinstance(state.get("performance"), dict) else {}
    risk_controls = state.get("risk_controls") if isinstance(state.get("risk_controls"), dict) else {}
    mode = str(market.get("market_mode") or market.get("regime") or "").lower()
    cash_pct = _safe_float(exposure.get("cash_pct"), 0.0)
    daily_loss = _safe_float(risk.get("daily_loss"), _safe_float(risk_controls.get("daily_loss_pct"), 0.0))
    drawdown = _safe_float(risk.get("drawdown"), _safe_float(risk_controls.get("intraday_drawdown_pct"), 0.0))
    realized_loss = _safe_float(risk_controls.get("realized_loss_pct"), 0.0)
    losses_today = int(_safe_float(performance.get("losses_today"), 0.0))

    checks = {
        "enabled": bool(ENABLED),
        "paper_only": bool(module._paper()) if callable(getattr(module, "_paper", None)) else True,
        "exactly_one_open_position": len(positions) == 1,
        "allowed_market_mode": mode in ALLOWED_MODES,
        "cash_high": cash_pct >= MIN_CASH_PCT,
        "risk_not_halted": not bool(risk.get("halted")),
        "profit_guard_inactive": not bool(risk.get("profit_guard")),
        "feedback_block_inactive": not bool(risk.get("feedback_block")),
        "self_defense_inactive": not bool(risk.get("self_defense")),
        "no_realized_loss": realized_loss <= 0.0 and losses_today == 0,
        "account_daily_loss_small": daily_loss <= MAX_ACCOUNT_DAILY_LOSS_PCT,
        "account_drawdown_small": drawdown <= MAX_ACCOUNT_DRAWDOWN_PCT,
        "first_position_above_controlled_floor": worst_pnl >= MIN_FIRST_POSITION_PNL,
    }
    detail = {
        "version": VERSION,
        "market_mode": mode,
        "cash_pct": round(cash_pct * 100.0, 4),
        "daily_loss_pct": daily_loss,
        "intraday_drawdown_pct": drawdown,
        "realized_loss_pct": realized_loss,
        "losses_today": losses_today,
        "first_positions": first_rows,
        "worst_first_position_pnl_pct": round(worst_pnl * 100.0, 4),
        "controlled_floor_pct": round(MIN_FIRST_POSITION_PNL * 100.0, 4),
        "checks": checks,
    }
    return all(checks.values()), detail


def _patch_module(name: str, module: Any) -> Dict[str, Any]:
    current = getattr(module, "_gate", None)
    if not callable(current):
        return {"module": name, "patched": False, "reason": "gate_missing"}
    if getattr(current, "_constructive_second_starter_tolerance_version", None) == VERSION:
        return {"module": name, "patched": True, "already_patched": True}

    original = current
    module_lock = threading.RLock()

    def gate(core: Any, signal: Dict[str, Any], __original=original, __module=module):
        global _LAST
        ok, result = __original(core, signal)
        if ok or not isinstance(result, dict) or result.get("reason") != "first_position_materially_losing":
            return ok, result

        qualifies, detail = _qualify(__module, core)
        if not qualifies:
            _LAST = {"status": "blocked", "detail": detail, "original_result": result}
            return ok, result

        with module_lock:
            prior_floor = getattr(__module, "MIN_FIRST_PNL", -0.005)
            try:
                setattr(__module, "MIN_FIRST_PNL", MIN_FIRST_POSITION_PNL)
                retry_ok, retry_result = __original(core, signal)
            finally:
                setattr(__module, "MIN_FIRST_PNL", prior_floor)

        if isinstance(retry_result, dict):
            retry_result = dict(retry_result)
            retry_result["constructive_second_starter_tolerance"] = detail
            if retry_ok:
                retry_result["reason"] = "starter_gate_allowed_with_controlled_first_position_tolerance"
        _LAST = {
            "status": "allowed" if retry_ok else "downstream_gate_blocked",
            "detail": detail,
            "original_result": result,
            "retry_result": retry_result,
        }
        return retry_ok, retry_result

    gate._constructive_second_starter_tolerance_version = VERSION  # type: ignore[attr-defined]
    gate._constructive_second_starter_tolerance_original = original  # type: ignore[attr-defined]
    setattr(module, "_gate", gate)
    return {
        "module": name,
        "patched": True,
        "module_file": str(getattr(module, "__file__", "") or ""),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _PATCHED_MODULES
    rows = []
    for name, module in _matching_modules():
        row = _patch_module(name, module)
        rows.append(row)
        if row.get("patched"):
            _PATCHED_MODULES[name] = row
    patched = any(row.get("patched") for row in rows)
    return {
        "status": "ok" if patched else "pending",
        "overall": "pass" if patched else "warn",
        "type": "constructive_second_starter_tolerance_status",
        "version": VERSION,
        "generated_local": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "enabled": bool(ENABLED),
        "patched": patched,
        "modules": rows,
        "latest": dict(_LAST),
        "policy": {
            "paper_only": True,
            "allowed_market_modes": sorted(ALLOWED_MODES),
            "minimum_cash_pct": round(MIN_CASH_PCT * 100.0, 2),
            "first_position_controlled_floor_pct": round(MIN_FIRST_POSITION_PNL * 100.0, 2),
            "maximum_account_daily_loss_pct": MAX_ACCOUNT_DAILY_LOSS_PCT,
            "maximum_account_drawdown_pct": MAX_ACCOUNT_DRAWDOWN_PCT,
            "requires_zero_realized_losses": True,
            "preserves_spacing": True,
            "preserves_daily_entry_cap": True,
            "preserves_position_cap": True,
            "preserves_sector_and_bucket_diversification": True,
            "preserves_exposure_caps": True,
            "changes_sizing": False,
            "changes_live_authority": False,
            "places_orders": False,
        },
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if "/paper/constructive-second-starter-tolerance-status" not in existing:
        flask_app.add_url_rule(
            "/paper/constructive-second-starter-tolerance-status",
            "constructive_second_starter_tolerance_status",
            lambda: jsonify(status_payload(core)),
        )
    _REGISTERED_APP_IDS.add(id(flask_app))
