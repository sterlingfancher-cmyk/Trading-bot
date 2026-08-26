"""Paper-accounting reconciliation and plausibility guard.

Reconstructs the paper account from the execution ledger when the ledger is
complete enough to do so, repairs malformed legacy open-position aliases/cost
basis, and prevents contaminated paper P&L from silently driving profit-guard
state.

For stable-paper successor epochs (v3+) that are still under validation hold,
reconstruction is observational only.  Those epochs already have an explicit
forensic baseline and immutable canonical execution history, so an accounting
read must never repair an in-flight execution mutation before its canonical row
is recorded.  Genuine successor mismatches remain visible as WARN/FAIL evidence
for the existing fail-closed lifecycle controls instead of being auto-mutated.

This module is paper-only. It does not place orders, change strategy thresholds,
change sizing rules, enable live trading, or grant ML authority.
"""
from __future__ import annotations

import copy
import datetime as dt
import functools
from typing import Any, Dict, List, Tuple

VERSION = "paper-accounting-integrity-2026-08-26-v2-successor-validation-readonly"
_APPLIED = False
_PATCHED_CORE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _sym(value: Any) -> str:
    return str(value or "").upper().strip()


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    return _now(core)[:10]


def _paper_only() -> bool:
    import os
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _successor_validation_hold_read_only(pf: Dict[str, Any]) -> bool:
    """Return True for stable-paper successor generations that must not auto-repair.

    Verified-v2 intentionally retains the legacy reconciler because it predates
    the bounded successor accounting disposition.  Generation v3 and later are
    explicit successor epochs with archived baselines and validation holds; their
    active economics must be changed only by canonical executions or a separately
    proven successor migration, never by a risk-control read.
    """
    epoch = _d(pf.get("paper_accounting_epoch"))
    epoch_id = str(epoch.get("id") or epoch.get("epoch_id") or pf.get("accounting_epoch_id") or "")
    if not bool(epoch.get("validation_hold", False)):
        return False
    parts = epoch_id.split("-")
    if len(parts) < 3 or parts[0] != "stable" or parts[1] != "paper" or not parts[2].startswith("v"):
        return False
    try:
        generation = int(parts[2][1:])
    except Exception:
        return False
    return generation >= 3


def _trade_fields(row: Dict[str, Any]) -> Tuple[str, str, float, float, str]:
    symbol = _sym(row.get("symbol") or row.get("ticker"))
    side = str(row.get("side") or row.get("action") or "").lower().strip()
    if side in {"b", "open_long", "long", "entry"}:
        side = "buy"
    elif side in {"s", "close_long", "exit"}:
        side = "sell"
    qty = _f(row.get("qty", row.get("shares", row.get("quantity"))), 0.0)
    price = _f(row.get("price", row.get("fill_price", row.get("entry_price", row.get("exit_price")))), 0.0)
    timestamp = str(row.get("timestamp") or row.get("time") or row.get("ts_local") or row.get("created_at") or "")
    return symbol, side, qty, price, timestamp


def _initial_cash(pf: Dict[str, Any]) -> float:
    for key in ("initial_cash", "starting_cash", "starting_equity", "initial_equity"):
        value = _f(pf.get(key), 0.0)
        if value > 0:
            return value
    history = _l(pf.get("history"))
    if history:
        value = _f(history[0], 0.0)
        if value > 0:
            return value
    return 10000.0


def reconstruct_from_ledger(pf: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    trades = _l(pf.get("trades"))
    positions = _d(pf.get("positions"))
    if not trades:
        return {"status": "unavailable", "reason": "trade_ledger_empty", "coverage_complete": False}

    lots: Dict[str, List[List[float]]] = {}
    cash = _initial_cash(pf)
    realized_total = 0.0
    realized_today = 0.0
    today = _today(core)
    parsed = 0
    ignored = 0

    for raw in trades:
        if not isinstance(raw, dict):
            ignored += 1
            continue
        symbol, side, qty, price, timestamp = _trade_fields(raw)
        if not symbol or side not in {"buy", "sell"} or qty <= 0 or price <= 0:
            ignored += 1
            continue
        parsed += 1
        book = lots.setdefault(symbol, [])
        if side == "buy":
            cash -= qty * price
            book.append([qty, price])
            continue

        cash += qty * price
        remaining = qty
        trade_realized = 0.0
        while remaining > 1e-9 and book:
            lot_qty, lot_price = book[0]
            used = min(remaining, lot_qty)
            trade_realized += (price - lot_price) * used
            lot_qty -= used
            remaining -= used
            if lot_qty <= 1e-9:
                book.pop(0)
            else:
                book[0][0] = lot_qty
        if remaining > 1e-6:
            ignored += 1
        realized_total += trade_realized
        if timestamp[:10] == today:
            realized_today += trade_realized

    coverage_complete = parsed > 0 and ignored == 0
    open_rows: Dict[str, Dict[str, float]] = {}
    market_value = 0.0
    unrealized = 0.0

    for symbol, book in lots.items():
        qty = sum(row[0] for row in book)
        if qty <= 1e-9:
            continue
        cost = sum(row[0] * row[1] for row in book)
        entry = cost / qty if qty else 0.0
        pos = _d(positions.get(symbol))
        last = _f(pos.get("last_price", pos.get("mark", pos.get("price"))), entry)
        if last <= 0:
            last = entry
        mv = qty * last
        upnl = (last - entry) * qty
        market_value += mv
        unrealized += upnl
        open_rows[symbol] = {
            "qty": qty,
            "entry_price": entry,
            "last_price": last,
            "market_value": mv,
            "cost_basis": cost,
            "unrealized_pnl": upnl,
            "unrealized_pnl_pct": ((last - entry) / entry * 100.0) if entry else 0.0,
        }

    equity = cash + market_value
    return {
        "status": "ok" if coverage_complete else "partial",
        "coverage_complete": coverage_complete,
        "parsed_trade_rows": parsed,
        "ignored_trade_rows": ignored,
        "initial_cash": round(_initial_cash(pf), 6),
        "cash": round(cash, 6),
        "equity": round(equity, 6),
        "market_value": round(market_value, 6),
        "realized_total": round(realized_total, 6),
        "realized_today": round(realized_today, 6),
        "unrealized_pnl": round(unrealized, 6),
        "open_positions": open_rows,
    }


def _discrepancies(pf: Dict[str, Any], rebuilt: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not rebuilt.get("coverage_complete"):
        return out
    for key in ("cash", "equity"):
        stored = _f(pf.get(key), 0.0)
        expected = _f(rebuilt.get(key), stored)
        delta = stored - expected
        tolerance = max(2.0, abs(expected) * 0.0025)
        if abs(delta) > tolerance:
            out.append({"field": key, "stored": round(stored, 4), "expected": round(expected, 4), "delta": round(delta, 4)})

    positions = _d(pf.get("positions"))
    for symbol, expected in _d(rebuilt.get("open_positions")).items():
        pos = _d(positions.get(symbol))
        stored_entry = _f(pos.get("entry", pos.get("entry_price")), 0.0)
        expected_entry = _f(expected.get("entry_price"), 0.0)
        stored_qty = _f(pos.get("shares", pos.get("qty")), 0.0)
        expected_qty = _f(expected.get("qty"), 0.0)
        if expected_entry > 0 and (stored_entry <= 0 or abs(stored_entry - expected_entry) / expected_entry > 0.01):
            out.append({"field": f"positions.{symbol}.entry_price", "stored": round(stored_entry, 4), "expected": round(expected_entry, 4)})
        if expected_qty > 0 and (stored_qty <= 0 or abs(stored_qty - expected_qty) / expected_qty > 0.01):
            out.append({"field": f"positions.{symbol}.qty", "stored": round(stored_qty, 6), "expected": round(expected_qty, 6)})
        stored_upnl = _f(pos.get("unrealized_pnl", pos.get("pnl_dollars")), 0.0)
        expected_upnl = _f(expected.get("unrealized_pnl"), 0.0)
        if abs(stored_upnl - expected_upnl) > max(2.0, abs(expected.get("market_value", 0.0)) * 0.01):
            out.append({"field": f"positions.{symbol}.unrealized_pnl", "stored": round(stored_upnl, 4), "expected": round(expected_upnl, 4)})
    return out


def reconcile(core: Any = None, *, persist: bool = True) -> Dict[str, Any]:
    if core is None or not _paper_only():
        return {"status": "skipped", "overall": "pass", "version": VERSION, "reason": "paper_runtime_only"}
    pf = _portfolio(core)
    rebuilt = reconstruct_from_ledger(pf, core)
    discrepancies = _discrepancies(pf, rebuilt)
    successor_read_only = _successor_validation_hold_read_only(pf)
    before = {
        "cash": _f(pf.get("cash")),
        "equity": _f(pf.get("equity")),
        "unrealized_pnl": _f(_d(pf.get("performance")).get("unrealized_pnl")),
        "realized_today": _f(_d(pf.get("performance")).get("realized_pnl_today")),
    }
    repaired = False

    if rebuilt.get("coverage_complete") and discrepancies and not successor_read_only:
        positions = _d(pf.get("positions"))
        for symbol, expected in _d(rebuilt.get("open_positions")).items():
            pos = dict(_d(positions.get(symbol)))
            qty = _f(expected.get("qty"))
            entry = _f(expected.get("entry_price"))
            last = _f(expected.get("last_price"), entry)
            pos.update({
                "symbol": symbol,
                "qty": round(qty, 6),
                "shares": round(qty, 6),
                "entry": round(entry, 6),
                "entry_price": round(entry, 6),
                "last_price": round(last, 6),
                "cost_basis": round(_f(expected.get("cost_basis")), 6),
                "market_value": round(_f(expected.get("market_value")), 6),
                "unrealized_pnl": round(_f(expected.get("unrealized_pnl")), 6),
                "pnl_dollars": round(_f(expected.get("unrealized_pnl")), 6),
                "unrealized_pnl_pct": round(_f(expected.get("unrealized_pnl_pct")), 6),
                "pnl_pct": round(_f(expected.get("unrealized_pnl_pct")), 6),
                "accounting_integrity_version": VERSION,
            })
            positions[symbol] = pos
        for symbol in list(positions):
            if symbol not in _d(rebuilt.get("open_positions")):
                # Do not silently delete unmatched positions; quarantine instead.
                pos = _d(positions.get(symbol))
                pos["accounting_integrity_quarantined"] = True
                pos["accounting_integrity_reason"] = "position_not_reconstructable_from_execution_ledger"

        pf["positions"] = positions
        pf["cash"] = round(_f(rebuilt.get("cash")), 6)
        pf["equity"] = round(_f(rebuilt.get("equity")), 6)
        perf = _d(pf.setdefault("performance", {}))
        perf["open_positions"] = positions
        perf["unrealized_pnl"] = round(_f(rebuilt.get("unrealized_pnl")), 6)
        perf["realized_pnl_today"] = round(_f(rebuilt.get("realized_today")), 6)
        perf["realized_pnl_total"] = round(_f(rebuilt.get("realized_total")), 6)
        pf["performance"] = perf

        # Quarantine stale profit-guard state until the normal risk engine sees
        # the reconciled account on its next update. Hard loss/halts are not cleared.
        risk = _d(pf.setdefault("risk_controls", {}))
        if risk.get("profit_guard_active"):
            risk["profit_guard_active"] = False
            risk["profit_guard_reason"] = "accounting integrity reconciliation; pending normal risk refresh"
        risk["accounting_integrity_reconciled_local"] = _now(core)
        risk["accounting_integrity_version"] = VERSION
        pf["risk_controls"] = risk
        repaired = True

        if persist:
            try:
                save = getattr(core, "save_state", None)
                if callable(save):
                    try:
                        save(pf)
                    except TypeError:
                        save()
            except Exception:
                pass

    remaining = _discrepancies(pf, rebuilt)
    status = {
        "status": "ok" if rebuilt.get("coverage_complete") and not remaining else "warn",
        "overall": "pass" if rebuilt.get("coverage_complete") and not remaining else "warn",
        "type": "paper_accounting_integrity_status",
        "version": VERSION,
        "generated_local": _now(core),
        "coverage_complete": bool(rebuilt.get("coverage_complete")),
        "repaired": repaired,
        "successor_validation_hold_read_only": successor_read_only,
        "automatic_repair_suppressed": bool(successor_read_only and discrepancies),
        "discrepancies_before_repair": discrepancies,
        "discrepancy_count_before_repair": len(discrepancies),
        "discrepancies_remaining": remaining,
        "discrepancy_count_remaining": len(remaining),
        "before": before,
        "reconstructed": rebuilt,
        "authority": {
            "paper_state_reconciliation_only": True,
            "legacy_epoch_auto_repair_retained": True,
            "successor_validation_hold_auto_repair": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_sizing_rules": False,
            "changes_live_or_ml_authority": False,
        },
    }
    pf["paper_accounting_integrity"] = copy.deepcopy(status)
    return status


def status_payload(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    return reconcile(core, persist=False)


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if id(core) not in _PATCHED_CORE_IDS:
        current = getattr(core, "get_risk_controls", None)
        if callable(current) and getattr(current, "_paper_accounting_integrity_version", None) != VERSION:
            @functools.wraps(current)
            def guarded_get_risk_controls(*args, **kwargs):
                reconcile(core, persist=True)
                return current(*args, **kwargs)
            guarded_get_risk_controls._paper_accounting_integrity_version = VERSION  # type: ignore[attr-defined]
            core.get_risk_controls = guarded_get_risk_controls
        _PATCHED_CORE_IDS.add(id(core))
    _APPLIED = True
    return reconcile(core, persist=True)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "reason": "flask_app_missing"}
    from flask import jsonify
    if id(flask_app) not in _REGISTERED_APP_IDS:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if "/paper/accounting-integrity-status" not in existing:
            flask_app.add_url_rule(
                "/paper/accounting-integrity-status",
                "paper_accounting_integrity_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(id(flask_app))
    return apply(core)