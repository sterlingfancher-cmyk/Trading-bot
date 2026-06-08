"""Paper-only Market Surge Queue Executor.

Consumes `portfolio.paper_surge_candidate_queue` created by
`market_surge_aggression.py` and opens controlled paper positions during a
validated market-surge regime.

Guardrails:
- Paper-only state mutation; no live broker calls.
- ML remains shadow-only.
- Does not lower global thresholds.
- Does not bypass self-defense, drawdown, cash reserve, or existing positions.
- Uses a per-day execution ledger to avoid duplicate entries.

Routes:
- /paper/surge-queue-executor-status        non-mutating status
- /paper/surge-queue-execute?confirm=1      explicit paper execution
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Tuple

VERSION = "market-surge-queue-executor-2026-06-08-v1-paper-only"
REGISTERED_APP_IDS: set[int] = set()

MAX_NEW_ENTRIES_PER_EXECUTION = 3
MAX_SURGE_DEPLOYMENT_PCT = 55.0
MIN_CASH_RESERVE_PCT = 45.0
MAX_DAILY_DRAWDOWN_PCT = 1.50
MAX_INTRADAY_DRAWDOWN_PCT = 1.50
DEFAULT_STOP_LOSS_PCT = 3.5
DEFAULT_TAKE_PROFIT_PCT = 8.0


def _now(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    return _now(core).split(" ")[0]


def _sym(value: Any) -> str:
    return str(value or "").upper().strip()


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
        pf = getattr(core, "portfolio", None)
        if isinstance(pf, dict):
            return pf
    except Exception:
        pass

    try:
        state = core.load_state()
        if isinstance(state, dict):
            return state
    except Exception:
        pass

    return {}


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
                ok = True
            except TypeError:
                save_fn()
                ok = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {"save_attempted": attempted, "save_ok": ok, "save_error": error}


def _performance(pf: Dict[str, Any]) -> Dict[str, Any]:
    perf = pf.get("performance")
    return perf if isinstance(perf, dict) else {}


def _risk_controls(pf: Dict[str, Any]) -> Dict[str, Any]:
    rc = pf.get("risk_controls")
    return rc if isinstance(rc, dict) else {}


def _positions(pf: Dict[str, Any]) -> Dict[str, Any]:
    positions = pf.setdefault("positions", {})
    if not isinstance(positions, dict):
        pf["positions"] = {}
        positions = pf["positions"]
    return positions


def _trades(pf: Dict[str, Any]) -> List[Dict[str, Any]]:
    trades = pf.setdefault("trades", [])
    if not isinstance(trades, list):
        pf["trades"] = []
        trades = pf["trades"]
    return trades


def _ledger(pf: Dict[str, Any]) -> Dict[str, Any]:
    ledger = pf.setdefault("surge_queue_executor_ledger", {})
    if not isinstance(ledger, dict):
        pf["surge_queue_executor_ledger"] = {}
        ledger = pf["surge_queue_executor_ledger"]
    return ledger


def _queue(pf: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = pf.get("paper_surge_candidate_queue", [])
    return q if isinstance(q, list) else []


def _market_surge_status(pf: Dict[str, Any]) -> Dict[str, Any]:
    status = pf.get("market_surge_aggression")
    return status if isinstance(status, dict) else {}


def _entry_price(entry: Dict[str, Any]) -> float:
    snapshot = entry.get("snapshot") if isinstance(entry.get("snapshot"), dict) else {}
    price = _safe_float(snapshot.get("price"), 0.0)
    if price <= 0:
        price = _safe_float(entry.get("price"), 0.0)
    return price


def _entry_allocation_pct(entry: Dict[str, Any]) -> float:
    pct = _safe_float(entry.get("allocation_hint_pct_of_equity"), 0.0)
    if pct <= 0:
        pct = 2.0
    # Hard per-entry cap; broad proxies can be larger than speculative names.
    tier = str(entry.get("tier", ""))
    if tier == "tier_1_broad_risk_on":
        return min(pct, 8.0)
    return min(pct, 3.5)


def _validate_environment(pf: Dict[str, Any], core: Any = None) -> Tuple[bool, List[str], Dict[str, Any]]:
    perf = _performance(pf)
    risk = _risk_controls(pf)
    surge = _market_surge_status(pf)
    positions = _positions(pf)
    q = _queue(pf)

    equity = _safe_float(pf.get("equity"), 0.0)
    cash = _safe_float(pf.get("cash"), 0.0)
    cash_pct = round((cash / equity * 100.0), 4) if equity else 0.0

    realized_today = _safe_float(perf.get("realized_pnl_today", pf.get("realized_today", 0.0)))
    self_defense = bool(risk.get("self_defense_active", False))
    daily_dd = _safe_float(risk.get("daily_loss_pct", risk.get("daily_drawdown_pct", 0.0)))
    intraday_dd = _safe_float(risk.get("intraday_drawdown_pct", 0.0))
    eligible_mode = bool(surge.get("eligible_mode", False))
    surge_level = _safe_int(surge.get("surge_level", 0), 0)

    failures: List[str] = []
    if not q:
        failures.append("paper_surge_candidate_queue_empty")
    if not eligible_mode or surge_level < 2:
        failures.append("market_surge_aggression_not_eligible")
    if self_defense:
        failures.append("self_defense_active")
    if realized_today < 0:
        failures.append("realized_today_negative")
    if daily_dd > MAX_DAILY_DRAWDOWN_PCT:
        failures.append("daily_drawdown_above_surge_limit")
    if intraday_dd > MAX_INTRADAY_DRAWDOWN_PCT:
        failures.append("intraday_drawdown_above_surge_limit")
    if cash_pct < MIN_CASH_RESERVE_PCT:
        failures.append("cash_reserve_below_minimum")
    if len(positions) >= _safe_int((surge.get("deployment_policy") or {}).get("max_surge_positions", 6), 6):
        failures.append("max_surge_positions_already_reached")

    context = {
        "eligible_mode": eligible_mode,
        "surge_level": surge_level,
        "cash": round(cash, 4),
        "equity": round(equity, 4),
        "cash_pct": cash_pct,
        "realized_today": round(realized_today, 4),
        "self_defense_active": self_defense,
        "daily_drawdown_pct": daily_dd,
        "intraday_drawdown_pct": intraday_dd,
        "open_positions": len(positions),
        "queue_length": len(q),
    }
    return not failures, failures, context


def preview_surge_queue_execution(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core)
    q = _queue(pf)
    positions = _positions(pf)
    ledger = _ledger(pf)
    ok, failures, context = _validate_environment(pf, core)

    today = _today(core)
    executed_today = set(ledger.get(today, [])) if isinstance(ledger.get(today), list) else set()

    planned = []
    skipped = []
    equity = _safe_float(pf.get("equity"), 0.0)
    cash = _safe_float(pf.get("cash"), 0.0)
    projected_cash = cash

    for entry in q:
        if len(planned) >= MAX_NEW_ENTRIES_PER_EXECUTION:
            break
        if not isinstance(entry, dict):
            continue
        symbol = _sym(entry.get("symbol"))
        price = _entry_price(entry)
        if not symbol:
            continue
        if symbol in positions:
            skipped.append({"symbol": symbol, "reason": "already_open"})
            continue
        if symbol in executed_today:
            skipped.append({"symbol": symbol, "reason": "already_executed_today"})
            continue
        if not entry.get("eligible_for_paper_surge", True):
            skipped.append({"symbol": symbol, "reason": "queue_entry_not_eligible"})
            continue
        if price <= 0:
            skipped.append({"symbol": symbol, "reason": "missing_price"})
            continue

        allocation_pct = _entry_allocation_pct(entry)
        allocation = round(equity * allocation_pct / 100.0, 2) if equity else 0.0
        if allocation <= 0:
            skipped.append({"symbol": symbol, "reason": "zero_allocation"})
            continue
        if projected_cash - allocation < equity * MIN_CASH_RESERVE_PCT / 100.0:
            skipped.append({"symbol": symbol, "reason": "cash_reserve_guard"})
            continue

        qty = round(allocation / price, 6)
        projected_cash -= allocation
        planned.append({
            "symbol": symbol,
            "price": round(price, 4),
            "qty": qty,
            "allocation": allocation,
            "allocation_pct_of_equity": allocation_pct,
            "source": entry.get("source"),
            "tier": entry.get("tier"),
            "reason": entry.get("reason"),
            "trade_authority": "paper_only_state_entry",
            "ml_authority": "shadow_only",
        })

    return {
        "status": "ok",
        "overall": "pass" if ok else "warn",
        "type": "surge_queue_executor_preview",
        "version": VERSION,
        "generated_local": _now(core),
        "can_execute": ok and bool(planned),
        "validation_failures": failures,
        "context": context,
        "planned_entries": planned,
        "skipped_entries": skipped,
        "guardrails": {
            "paper_only": True,
            "live_trade_authority": "none",
            "ml_authority": "shadow_only",
            "does_not_lower_global_thresholds": True,
            "does_not_bypass_hard_blocks": True,
            "max_new_entries_per_execution": MAX_NEW_ENTRIES_PER_EXECUTION,
            "min_cash_reserve_pct": MIN_CASH_RESERVE_PCT,
        },
    }


def execute_surge_queue(core: Any = None, *, explicit_confirm: bool = False) -> Dict[str, Any]:
    pf = _portfolio(core)
    preview = preview_surge_queue_execution(core)
    if not explicit_confirm:
        return {
            **preview,
            "executed": False,
            "execution_reason": "explicit_confirm_required",
        }
    if not preview.get("can_execute"):
        return {
            **preview,
            "executed": False,
            "execution_reason": "validation_failed_or_no_planned_entries",
        }

    positions = _positions(pf)
    trades = _trades(pf)
    ledger = _ledger(pf)
    today = _today(core)
    executed_today = ledger.setdefault(today, [])
    if not isinstance(executed_today, list):
        ledger[today] = []
        executed_today = ledger[today]

    now_text = _now(core)
    cash = _safe_float(pf.get("cash"), 0.0)
    executed = []

    for plan in preview.get("planned_entries", []):
        symbol = _sym(plan.get("symbol"))
        if not symbol or symbol in positions:
            continue

        price = _safe_float(plan.get("price"), 0.0)
        qty = _safe_float(plan.get("qty"), 0.0)
        allocation = _safe_float(plan.get("allocation"), 0.0)
        if price <= 0 or qty <= 0 or allocation <= 0:
            continue

        positions[symbol] = {
            "symbol": symbol,
            "side": "long",
            "qty": qty,
            "entry_price": round(price, 4),
            "last_price": round(price, 4),
            "market_value": round(allocation, 2),
            "cost_basis": round(allocation, 2),
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "opened_at": now_text,
            "source": "market_surge_queue_executor",
            "entry_tag": "paper_surge_entry",
            "tier": plan.get("tier"),
            "allocation_pct_of_equity": plan.get("allocation_pct_of_equity"),
            "stop_loss_pct": DEFAULT_STOP_LOSS_PCT,
            "take_profit_pct": DEFAULT_TAKE_PROFIT_PCT,
            "trade_authority": "paper_only_state_entry",
            "live_trade_authority": "none",
            "ml_authority": "shadow_only",
        }

        trades.append({
            "timestamp": now_text,
            "symbol": symbol,
            "side": "buy",
            "qty": qty,
            "price": round(price, 4),
            "value": round(allocation, 2),
            "pnl": 0.0,
            "source": "market_surge_queue_executor",
            "entry_tag": "paper_surge_entry",
            "trade_authority": "paper_only_state_entry",
            "live_trade_authority": "none",
            "ml_authority": "shadow_only",
            "reason": plan.get("reason"),
        })

        cash -= allocation
        executed_today.append(symbol)
        executed.append(plan)

    pf["cash"] = round(max(0.0, cash), 4)
    pf["last_surge_queue_execution"] = {
        "ts_local": now_text,
        "version": VERSION,
        "executed_symbols": [row.get("symbol") for row in executed],
        "executed_count": len(executed),
        "paper_only": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
    }

    save_result = _save(core, pf)
    return {
        **preview,
        "executed": bool(executed),
        "executed_entries": executed,
        "execution_reason": "executed_paper_queue" if executed else "nothing_executed_after_final_checks",
        "persistence": save_result,
        "post_execution_cash": pf.get("cash"),
        "post_execution_open_positions": len(_positions(pf)),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    # Non-mutating by default at import/startup. This prevents accidental entries on deploy.
    return preview_surge_queue_execution(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    from flask import jsonify, request

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        return jsonify(preview_surge_queue_execution(core))

    def execute_route():
        confirm = str(request.args.get("confirm", "0")).lower() in {"1", "true", "yes"}
        return jsonify(execute_surge_queue(core, explicit_confirm=confirm))

    if "/paper/surge-queue-executor-status" not in existing:
        flask_app.add_url_rule(
            "/paper/surge-queue-executor-status",
            "surge_queue_executor_status",
            status_route,
        )

    if "/paper/surge-queue-execute" not in existing:
        flask_app.add_url_rule(
            "/paper/surge-queue-execute",
            "surge_queue_execute",
            execute_route,
        )

    REGISTERED_APP_IDS.add(id(flask_app))
