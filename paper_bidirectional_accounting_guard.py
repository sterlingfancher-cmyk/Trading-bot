"""Bidirectional long/short accounting for the clean Stable Paper epoch.

The legacy reconciliation path was long-lot only.  This module makes the
paper-accounting source of truth understand the runtime's actual execution
semantics:

- long entry: reserve cash equal to entry notional
- long exit/partial exit: release matched sale proceeds
- short entry: reserve cash equal to short margin/notional
- short exit/partial exit: release matched margin plus realized P&L

Only quantities proven by reconstructed lots can be closed.  Unmatched exits
remain coverage failures and never create synthetic cash.

Paper-only accounting/reconciliation.  No signal, threshold, sizing, order,
live-authority, or ML-authority behavior is changed.
"""
from __future__ import annotations

import copy
import datetime as dt
from typing import Any, Dict, List, Tuple

VERSION = "paper-bidirectional-accounting-2026-08-10-v1"
_APPLIED = False
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
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    return _now(core)[:10]


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _initial_cash(accounting: Any, pf: Dict[str, Any]) -> float:
    try:
        return float(accounting._initial_cash(pf))
    except Exception:
        for key in ("initial_cash", "starting_cash", "starting_equity", "initial_equity"):
            value = _f(pf.get(key), 0.0)
            if value > 0:
                return value
        history = _l(pf.get("history"))
        return _f(history[0], 10000.0) if history else 10000.0


def _event_fields(row: Dict[str, Any]) -> Tuple[str, str, str, float, float, str]:
    symbol = str(row.get("symbol") or row.get("ticker") or "").upper().strip()
    action = str(row.get("action") or "").lower().strip()
    side = str(row.get("side") or row.get("direction") or "").lower().strip()
    qty = _f(row.get("qty", row.get("shares", row.get("quantity"))), 0.0)
    price = _f(row.get("price", row.get("fill_price", row.get("entry_price", row.get("exit_price")))), 0.0)
    timestamp = str(row.get("timestamp") or row.get("time") or row.get("ts_local") or row.get("created_at") or "")

    if side in {"buy", "b", "open_long"}:
        side = "long"
    elif side in {"sell", "s", "close_long"} and not action:
        side = "long"
    if side not in {"long", "short"}:
        side = "long"

    if action in {"entry", "buy", "open", "open_long", "open_short"}:
        event = "entry"
    elif action in {"exit", "partial_exit", "sell", "close", "close_long", "close_short", "cover"}:
        event = "exit"
    elif str(row.get("side") or "").lower().strip() in {"buy", "b"}:
        event, side = "entry", "long"
    elif str(row.get("side") or "").lower().strip() in {"sell", "s"}:
        event, side = "exit", "long"
    else:
        event = action
    return symbol, event, side, qty, price, timestamp


def _clean_zero_trade_baseline(pf: Dict[str, Any], core: Any, accounting: Any) -> Dict[str, Any] | None:
    try:
        import paper_ledger_matched_exit_guard as matched
        fn = getattr(matched, "_clean_epoch_zero_trade_baseline", None)
        if callable(fn):
            return fn(pf, core, accounting)
    except Exception:
        pass
    return None


def analyze_ledger(pf: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    import paper_accounting_integrity_guard as accounting

    trades = _l(pf.get("trades"))
    positions = _d(pf.get("positions"))
    if not trades:
        clean = _clean_zero_trade_baseline(pf, core, accounting)
        if clean is not None:
            clean = dict(clean)
            clean["accounting_model"] = "bidirectional_margin_v1"
            clean["supports_long_short"] = True
            return clean
        return {
            "status": "unavailable",
            "reason": "trade_ledger_empty",
            "coverage_complete": False,
            "parsed_trade_rows": 0,
            "ignored_trade_rows": 0,
            "coverage_issues": [],
            "coverage_issue_count": 0,
            "economic_issues": [],
            "economic_issue_count": 0,
            "accounting_model": "bidirectional_margin_v1",
            "supports_long_short": True,
        }

    initial = _initial_cash(accounting, pf)
    cash = initial
    books: Dict[str, Dict[str, List[List[float]]]] = {}
    parsed = 0
    ignored = 0
    coverage_issues: List[Dict[str, Any]] = []
    economic_issues: List[Dict[str, Any]] = []
    realized_total = 0.0
    realized_today = 0.0
    today = _today(core)

    for index, raw in enumerate(trades):
        if not isinstance(raw, dict):
            ignored += 1
            coverage_issues.append({"trade_index": index, "reason": "non_dict_trade_row"})
            continue

        symbol, event, side, qty, price, timestamp = _event_fields(raw)
        if not symbol or event not in {"entry", "exit"} or side not in {"long", "short"} or qty <= 0 or price <= 0:
            ignored += 1
            coverage_issues.append({
                "trade_index": index,
                "reason": "unsupported_or_incomplete_trade_row",
                "symbol": symbol,
                "event": event,
                "action": raw.get("action"),
                "side": raw.get("side"),
                "qty": qty,
                "price": price,
                "timestamp": timestamp,
            })
            continue

        parsed += 1
        side_books = books.setdefault(symbol, {"long": [], "short": []})
        book = side_books[side]

        if event == "entry":
            notional = qty * price
            tolerance = max(2.0, abs(cash) * 0.0025)
            if notional > cash + tolerance:
                economic_issues.append({
                    "trade_index": index,
                    "reason": "entry_exceeds_available_cash",
                    "symbol": symbol,
                    "side": side,
                    "timestamp": timestamp,
                    "cash_before": round(cash, 6),
                    "entry_notional": round(notional, 6),
                    "overspend": round(notional - cash, 6),
                })
            cash -= notional
            # [remaining qty, entry price].  For shorts, entry notional is also
            # the reserved margin released pro-rata on exits.
            book.append([qty, price])
            if cash < -max(2.0, initial * 0.0025):
                economic_issues.append({
                    "trade_index": index,
                    "reason": "negative_cash_after_entry",
                    "symbol": symbol,
                    "side": side,
                    "timestamp": timestamp,
                    "cash_after": round(cash, 6),
                })
            continue

        remaining = qty
        matched_qty = 0.0
        cash_release = 0.0
        trade_realized = 0.0
        while remaining > 1e-9 and book:
            lot_qty, lot_price = book[0]
            used = min(remaining, lot_qty)
            matched_qty += used
            if side == "long":
                cash_release += used * price
                trade_realized += (price - lot_price) * used
            else:
                pnl = (lot_price - price) * used
                trade_realized += pnl
                cash_release += (lot_price * used) + pnl
            lot_qty -= used
            remaining -= used
            if lot_qty <= 1e-9:
                book.pop(0)
            else:
                book[0][0] = lot_qty

        cash += cash_release
        realized_total += trade_realized
        if timestamp[:10] == today:
            realized_today += trade_realized

        if remaining > 1e-6:
            ignored += 1
            coverage_issues.append({
                "trade_index": index,
                "reason": "exit_exceeds_reconstructed_position",
                "symbol": symbol,
                "side": side,
                "timestamp": timestamp,
                "requested_qty": round(qty, 9),
                "matched_qty": round(matched_qty, 9),
                "unmatched_qty": round(remaining, 9),
                "price": round(price, 6),
                "action": raw.get("action"),
            })

    open_rows: Dict[str, Dict[str, Any]] = {}
    position_value_total = 0.0
    unrealized = 0.0
    for symbol, side_books in books.items():
        open_sides = [side for side in ("long", "short") if sum(row[0] for row in side_books[side]) > 1e-9]
        if len(open_sides) > 1:
            economic_issues.append({"reason": "opposing_open_books_same_symbol", "symbol": symbol, "open_sides": open_sides})
        for side in open_sides:
            book = side_books[side]
            qty = sum(row[0] for row in book)
            basis = sum(row[0] * row[1] for row in book)
            entry = basis / qty if qty else 0.0
            pos = _d(positions.get(symbol))
            last = _f(pos.get("last_price", pos.get("mark", pos.get("price"))), entry)
            if last <= 0:
                last = entry
            if side == "short":
                upnl = (entry - last) * qty
                value = basis + upnl
                pnl_pct = ((entry - last) / entry * 100.0) if entry else 0.0
            else:
                upnl = (last - entry) * qty
                value = qty * last
                pnl_pct = ((last - entry) / entry * 100.0) if entry else 0.0
            position_value_total += value
            unrealized += upnl
            open_rows[symbol] = {
                "side": side,
                "qty": qty,
                "entry_price": entry,
                "last_price": last,
                "market_value": value,
                "position_value": value,
                "cost_basis": basis,
                "margin": basis if side == "short" else 0.0,
                "unrealized_pnl": upnl,
                "unrealized_pnl_pct": pnl_pct,
            }

    coverage_complete = parsed > 0 and ignored == 0 and not coverage_issues
    equity = cash + position_value_total
    return {
        "status": "ok" if coverage_complete else "partial",
        "coverage_complete": coverage_complete,
        "parsed_trade_rows": parsed,
        "ignored_trade_rows": ignored,
        "initial_cash": round(initial, 6),
        "cash": round(cash, 6),
        "equity": round(equity, 6),
        "market_value": round(position_value_total, 6),
        "realized_total": round(realized_total, 6),
        "realized_today": round(realized_today, 6),
        "unrealized_pnl": round(unrealized, 6),
        "open_positions": open_rows,
        "coverage_issues": coverage_issues[:50],
        "coverage_issue_count": len(coverage_issues),
        "economic_issues": economic_issues[:50],
        "economic_issue_count": len(economic_issues),
        "accounting_model": "bidirectional_margin_v1",
        "supports_long_short": True,
    }


def _economic_status(core: Any = None) -> Dict[str, Any]:
    rebuilt = analyze_ledger(_portfolio(core), core)
    coverage_complete = bool(rebuilt.get("coverage_complete"))
    issues = _l(rebuilt.get("economic_issues")) + _l(rebuilt.get("coverage_issues"))
    ok = coverage_complete and not issues
    return {
        "status": "ok" if ok else "fail",
        "overall": "pass" if ok else "fail",
        "type": "paper_ledger_economic_integrity_status",
        "version": VERSION,
        "generated_local": _now(core),
        "cash_only_assumption": True,
        "short_margin_model": "entry_notional_reserved_and_released_with_pnl",
        "supports_long_short": True,
        "parsed_trade_rows": int(rebuilt.get("parsed_trade_rows") or 0),
        "ignored_trade_rows": int(rebuilt.get("ignored_trade_rows") or 0),
        "coverage_complete": coverage_complete,
        "selected_initial_cash": rebuilt.get("initial_cash"),
        "reconstructed_cash_after_ledger": rebuilt.get("cash"),
        "economic_issue_count": len(issues),
        "economic_issues": issues[:20],
        "promotion_evidence_eligible": bool(ok),
        "authority": {
            "reporting_only": True,
            "repairs_state": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def _repair_position_metadata(core: Any, rebuilt: Dict[str, Any], persist: bool) -> bool:
    state = _portfolio(core)
    positions = _d(state.get("positions"))
    changed = False
    for symbol, expected in _d(rebuilt.get("open_positions")).items():
        pos = _d(positions.get(symbol))
        if not pos:
            continue
        side = str(expected.get("side") or "long")
        if str(pos.get("side") or "long") != side:
            pos["side"] = side
            changed = True
        if side == "short":
            margin = _f(expected.get("margin"))
            if abs(_f(pos.get("margin")) - margin) > 0.01:
                pos["margin"] = round(margin, 6)
                changed = True
        positions[symbol] = pos
    if changed:
        state["positions"] = positions
        if persist:
            save = getattr(core, "save_state", None)
            if callable(save):
                try:
                    save(state)
                except TypeError:
                    save()
    return changed


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import paper_accounting_integrity_guard as accounting
        import paper_ledger_economic_integrity as economics
        import paper_ledger_matched_exit_guard as matched
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    accounting.reconstruct_from_ledger = analyze_ledger
    matched.analyze_ledger = analyze_ledger
    economics.status_payload = _economic_status
    economics.apply = _economic_status

    current_reconcile = getattr(accounting, "reconcile", None)
    if callable(current_reconcile) and getattr(current_reconcile, "_bidirectional_accounting_version", None) != VERSION:
        prior = getattr(current_reconcile, "_bidirectional_accounting_prior", current_reconcile)

        def wrapped_reconcile(runtime: Any = None, *, persist: bool = True):
            result = prior(runtime, persist=persist)
            active = runtime or core
            if active is not None:
                rebuilt = analyze_ledger(_portfolio(active), active)
                if rebuilt.get("coverage_complete"):
                    changed = _repair_position_metadata(active, rebuilt, persist)
                    if changed and isinstance(result, dict):
                        result = copy.deepcopy(result)
                        result["position_side_metadata_repaired"] = True
                        result["reconstructed"] = rebuilt
            return result

        wrapped_reconcile._bidirectional_accounting_version = VERSION  # type: ignore[attr-defined]
        wrapped_reconcile._bidirectional_accounting_prior = prior  # type: ignore[attr-defined]
        accounting.reconcile = wrapped_reconcile

    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    rebuilt = analyze_ledger(_portfolio(core), core) if core is not None else {}
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "paper_bidirectional_accounting_status",
        "version": VERSION,
        "applied": _APPLIED,
        "supports_long_short": True,
        "short_margin_model": "entry_notional_reserved_and_released_with_pnl",
        "coverage_complete": bool(rebuilt.get("coverage_complete")),
        "baseline_type": rebuilt.get("baseline_type"),
        "parsed_trade_rows": int(rebuilt.get("parsed_trade_rows") or 0),
        "ignored_trade_rows": int(rebuilt.get("ignored_trade_rows") or 0),
        "coverage_issue_count": int(rebuilt.get("coverage_issue_count") or 0),
        "economic_issue_count": int(rebuilt.get("economic_issue_count") or 0),
        "reconstructed_cash": rebuilt.get("cash"),
        "reconstructed_equity": rebuilt.get("equity"),
        "authority": {
            "paper_accounting_reconstruction_only": True,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    if id(flask_app) not in _REGISTERED_APP_IDS:
        from flask import jsonify
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        path = "/paper/bidirectional-accounting-status"
        if path not in existing:
            flask_app.add_url_rule(path, "paper_bidirectional_accounting_status", lambda: jsonify(status_payload(core)))
        _REGISTERED_APP_IDS.add(id(flask_app))
    return status_payload(core)
