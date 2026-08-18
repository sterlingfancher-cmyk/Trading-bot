"""Matched-exit accounting guard for paper-ledger recovery and execution safety.

Prevents unmatched/duplicate exits from creating synthetic cash during ledger
reconstruction and, at the live paper full-exit boundary, prevents stale runtime
state from closing more quantity than the authoritative canonical execution
ledger says remains open.

The runtime preflight is deliberately narrow:
- it runs before the existing ``exit_position`` owner can mutate cash/P&L/state;
- it uses the existing canonical JSONL reader and hash-chain verifier;
- it fails closed on missing/unreadable/invalid canonical evidence;
- it includes an explicitly verified snapshot opening lot in canonical remaining
  quantity so that inherited positions remain manageable but cannot be re-closed;
- it does not alter partial exits, strategy, sizing, thresholds, live authority,
  or ML authority.

A deliberately created clean accounting epoch is also a valid zero-trade ledger
baseline when cash/equity/P&L and the canonical execution ledger all agree.
"""
from __future__ import annotations

import datetime as dt
import functools
import os
from typing import Any, Dict, List

VERSION = "paper-ledger-matched-exit-guard-2026-08-18-v3-runtime-preflight"
FULL_EXIT_EPSILON = 1e-6
_APPLIED = False
_REGISTERED_APP_IDS: set[int] = set()
_RUNTIME_GUARD_CORE_IDS: set[int] = set()


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


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _today(core: Any = None) -> str:
    return _now(core)[:10]


def _initial_cash(accounting: Any, pf: Dict[str, Any]) -> float:
    try:
        return float(accounting._initial_cash(pf))
    except Exception:
        history = _l(pf.get("history"))
        return _f(history[0], 10000.0) if history else 10000.0


def _clean_epoch_zero_trade_baseline(pf: Dict[str, Any], core: Any, accounting: Any) -> Dict[str, Any] | None:
    epoch = _d(pf.get("paper_accounting_epoch"))
    if not bool(epoch.get("clean_start")) or not bool(epoch.get("zero_trade_baseline")):
        return None
    if _l(pf.get("trades")) or _d(pf.get("positions")):
        return None

    initial = _f(epoch.get("starting_cash"), _initial_cash(accounting, pf))
    cash = _f(pf.get("cash"), initial)
    equity = _f(pf.get("equity"), cash)
    realized = _d(pf.get("realized_pnl"))
    performance = _d(pf.get("performance"))
    issues: List[Dict[str, Any]] = []
    money_tol = max(0.01, abs(initial) * 1e-8)

    if initial <= 0:
        issues.append({"reason": "clean_epoch_starting_cash_invalid", "starting_cash": initial})
    if abs(cash - initial) > money_tol:
        issues.append({"reason": "clean_epoch_cash_not_at_baseline", "cash": cash, "starting_cash": initial})
    if abs(equity - initial) > money_tol:
        issues.append({"reason": "clean_epoch_equity_not_at_baseline", "equity": equity, "starting_cash": initial})
    if abs(_f(realized.get("today"), 0.0)) > money_tol or abs(_f(realized.get("total"), 0.0)) > money_tol:
        issues.append({"reason": "clean_epoch_realized_pnl_not_zero"})
    if abs(_f(performance.get("unrealized_pnl"), 0.0)) > money_tol:
        issues.append({"reason": "clean_epoch_unrealized_pnl_not_zero"})

    try:
        import canonical_execution_ledger as ledger
        ledger_status = ledger.status_payload(core)
        if not bool(ledger_status.get("chain_valid")):
            issues.append({"reason": "canonical_execution_ledger_chain_invalid"})
        if not bool(ledger_status.get("authoritative_for_new_executions")):
            issues.append({"reason": "canonical_execution_ledger_not_authoritative"})
        if int(ledger_status.get("row_count") or 0) != 0:
            issues.append({"reason": "clean_epoch_canonical_ledger_not_empty", "row_count": ledger_status.get("row_count")})
        if int(ledger_status.get("current_epoch_rows") or 0) != 0:
            issues.append({"reason": "clean_epoch_current_epoch_ledger_not_empty", "current_epoch_rows": ledger_status.get("current_epoch_rows")})
        if str(ledger_status.get("current_epoch_id") or "") != str(epoch.get("id") or pf.get("accounting_epoch_id") or ""):
            issues.append({"reason": "clean_epoch_ledger_epoch_id_mismatch"})
    except Exception as exc:
        issues.append({"reason": "canonical_execution_ledger_status_error", "error": f"{type(exc).__name__}: {exc}"})

    complete = not issues
    return {
        "status": "ok" if complete else "partial",
        "reason": "clean_zero_trade_epoch_baseline" if complete else "clean_zero_trade_epoch_baseline_invalid",
        "baseline_type": "clean_zero_trade_epoch",
        "coverage_complete": complete,
        "parsed_trade_rows": 0,
        "ignored_trade_rows": 0,
        "initial_cash": round(initial, 6),
        "cash": round(cash, 6),
        "equity": round(equity, 6),
        "market_value": 0.0,
        "realized_total": 0.0,
        "realized_today": 0.0,
        "unrealized_pnl": 0.0,
        "open_positions": {},
        "coverage_issues": issues[:50],
        "coverage_issue_count": len(issues),
        "economic_issues": [],
        "economic_issue_count": 0,
    }


def analyze_ledger(pf: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    import paper_accounting_integrity_guard as accounting

    trades = _l(pf.get("trades"))
    positions = _d(pf.get("positions"))
    if not trades:
        clean = _clean_epoch_zero_trade_baseline(pf, core, accounting)
        if clean is not None:
            return clean
        return {
            "status": "unavailable",
            "reason": "trade_ledger_empty",
            "coverage_complete": False,
            "parsed_trade_rows": 0,
            "ignored_trade_rows": 0,
            "coverage_issues": [],
        }

    initial = _initial_cash(accounting, pf)
    cash = initial
    lots: Dict[str, List[List[float]]] = {}
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

        symbol, event, qty, price, timestamp = accounting._trade_fields(raw)
        if not symbol or event not in {"buy", "sell"} or qty <= 0 or price <= 0:
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
        book = lots.setdefault(symbol, [])
        if event == "buy":
            notional = qty * price
            tolerance = max(2.0, abs(cash) * 0.0025)
            if notional > cash + tolerance:
                economic_issues.append({
                    "trade_index": index,
                    "reason": "buy_exceeds_available_cash",
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "cash_before": round(cash, 6),
                    "buy_notional": round(notional, 6),
                    "overspend": round(notional - cash, 6),
                })
            cash -= notional
            book.append([qty, price])
            if cash < -max(2.0, initial * 0.0025):
                economic_issues.append({
                    "trade_index": index,
                    "reason": "negative_cash_after_trade",
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "cash_after": round(cash, 6),
                })
            continue

        remaining = qty
        matched_qty = 0.0
        matched_proceeds = 0.0
        trade_realized = 0.0
        while remaining > 1e-9 and book:
            lot_qty, lot_price = book[0]
            used = min(remaining, lot_qty)
            matched_qty += used
            matched_proceeds += used * price
            trade_realized += (price - lot_price) * used
            lot_qty -= used
            remaining -= used
            if lot_qty <= 1e-9:
                book.pop(0)
            else:
                book[0][0] = lot_qty

        cash += matched_proceeds
        realized_total += trade_realized
        if timestamp[:10] == today:
            realized_today += trade_realized

        if remaining > 1e-6:
            ignored += 1
            coverage_issues.append({
                "trade_index": index,
                "reason": "sell_exceeds_reconstructed_position",
                "symbol": symbol,
                "timestamp": timestamp,
                "requested_qty": round(qty, 9),
                "matched_qty": round(matched_qty, 9),
                "unmatched_qty": round(remaining, 9),
                "price": round(price, 6),
                "action": raw.get("action"),
                "side": raw.get("side"),
            })

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

    coverage_complete = parsed > 0 and ignored == 0 and not coverage_issues
    equity = cash + market_value
    return {
        "status": "ok" if coverage_complete else "partial",
        "coverage_complete": coverage_complete,
        "parsed_trade_rows": parsed,
        "ignored_trade_rows": ignored,
        "initial_cash": round(initial, 6),
        "cash": round(cash, 6),
        "equity": round(equity, 6),
        "market_value": round(market_value, 6),
        "realized_total": round(realized_total, 6),
        "realized_today": round(realized_today, 6),
        "unrealized_pnl": round(unrealized, 6),
        "open_positions": open_rows,
        "coverage_issues": coverage_issues[:50],
        "coverage_issue_count": len(coverage_issues),
        "economic_issues": economic_issues[:50],
        "economic_issue_count": len(economic_issues),
    }


def _verified_snapshot_baseline_qty(pf: Dict[str, Any], symbol: str, side: str) -> float:
    epoch = _d(pf.get("paper_accounting_epoch"))
    if str(epoch.get("baseline_type") or "") != "verified_snapshot_with_open_position":
        return 0.0
    snapshot = _d(epoch.get("verified_snapshot_baseline"))
    if not bool(snapshot.get("verified", False)):
        return 0.0
    raw = _d(_d(snapshot.get("positions")).get(str(symbol or "").upper().strip()))
    if not raw:
        return 0.0
    snapshot_side = str(raw.get("side") or "long").lower().strip()
    if snapshot_side != str(side or "long").lower().strip():
        return 0.0
    snapshot_qty = _f(raw.get("qty", raw.get("shares")), 0.0)
    return snapshot_qty if snapshot_qty > FULL_EXIT_EPSILON else 0.0


def _canonical_full_exit_preflight(core: Any, symbol: str, side: str, requested_qty: float) -> Dict[str, Any]:
    """Return a fail-closed canonical lifecycle decision for one paper full exit."""
    sym = str(symbol or "").upper().strip()
    side_key = str(side or "long").lower().strip()
    qty = _f(requested_qty, 0.0)
    if not sym or side_key not in {"long", "short"} or qty <= FULL_EXIT_EPSILON:
        return {
            "allow": False,
            "reason": "canonical_full_exit_request_invalid",
            "symbol": sym,
            "side": side_key,
            "requested_qty": qty,
        }

    try:
        import canonical_execution_ledger as ledger
        with ledger._LOCK:
            file_exists = os.path.exists(ledger.LEDGER_FILE)
            rows, parse_errors = ledger._read_rows()
            if parse_errors:
                return {
                    "allow": False,
                    "reason": "canonical_execution_ledger_unreadable_for_full_exit",
                    "symbol": sym,
                    "side": side_key,
                    "requested_qty": qty,
                    "errors": parse_errors[:3],
                }
            chain_valid, chain_errors = ledger._verify_rows(rows)
            if rows and not chain_valid:
                return {
                    "allow": False,
                    "reason": "canonical_execution_ledger_chain_invalid_for_full_exit",
                    "symbol": sym,
                    "side": side_key,
                    "requested_qty": qty,
                    "errors": chain_errors[:3],
                }
            epoch_id = str(ledger._epoch_id(core) or "")
    except Exception as exc:
        return {
            "allow": False,
            "reason": "canonical_execution_ledger_preflight_error",
            "symbol": sym,
            "side": side_key,
            "requested_qty": qty,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if not file_exists:
        return {
            "allow": False,
            "reason": "canonical_execution_ledger_missing_for_full_exit",
            "symbol": sym,
            "side": side_key,
            "requested_qty": qty,
            "accounting_epoch_id": epoch_id,
        }

    relevant = [
        row for row in rows
        if str(row.get("accounting_epoch_id") or "") == epoch_id
        and str(row.get("symbol") or "").upper().strip() == sym
        and str(row.get("side") or "long").lower().strip() == side_key
    ]
    baseline_qty = _verified_snapshot_baseline_qty(_portfolio(core), sym, side_key)
    entry_qty = sum(_f(row.get("shares"), 0.0) for row in relevant if str(row.get("action") or "").lower().strip() == "entry")
    exit_qty = sum(
        _f(row.get("shares"), 0.0)
        for row in relevant
        if str(row.get("action") or "").lower().strip() in {"partial_exit", "exit"}
    )
    opening_qty = baseline_qty + entry_qty

    if opening_qty <= FULL_EXIT_EPSILON:
        return {
            "allow": False,
            "reason": "canonical_entry_missing_for_runtime_position",
            "symbol": sym,
            "side": side_key,
            "requested_qty": qty,
            "accounting_epoch_id": epoch_id,
            "verified_snapshot_baseline_qty": round(baseline_qty, 9),
            "canonical_entry_qty": round(entry_qty, 9),
            "canonical_exit_qty": round(exit_qty, 9),
        }

    remaining = opening_qty - exit_qty
    tolerance = max(FULL_EXIT_EPSILON, abs(opening_qty) * 1e-9)
    if remaining <= tolerance:
        return {
            "allow": False,
            "reason": "canonical_position_already_closed",
            "symbol": sym,
            "side": side_key,
            "requested_qty": qty,
            "accounting_epoch_id": epoch_id,
            "verified_snapshot_baseline_qty": round(baseline_qty, 9),
            "canonical_entry_qty": round(entry_qty, 9),
            "canonical_exit_qty": round(exit_qty, 9),
            "canonical_remaining_qty": round(remaining, 9),
        }
    if qty > remaining + tolerance:
        return {
            "allow": False,
            "reason": "requested_full_exit_exceeds_canonical_remaining_quantity",
            "symbol": sym,
            "side": side_key,
            "requested_qty": round(qty, 9),
            "accounting_epoch_id": epoch_id,
            "verified_snapshot_baseline_qty": round(baseline_qty, 9),
            "canonical_entry_qty": round(entry_qty, 9),
            "canonical_exit_qty": round(exit_qty, 9),
            "canonical_remaining_qty": round(remaining, 9),
        }
    return {
        "allow": True,
        "reason": "canonical_remaining_quantity_allows_full_exit",
        "symbol": sym,
        "side": side_key,
        "requested_qty": round(qty, 9),
        "accounting_epoch_id": epoch_id,
        "verified_snapshot_baseline_qty": round(baseline_qty, 9),
        "canonical_entry_qty": round(entry_qty, 9),
        "canonical_exit_qty": round(exit_qty, 9),
        "canonical_remaining_qty": round(remaining, 9),
    }


def _mark_runtime_full_exit_block(core: Any, decision: Dict[str, Any]) -> None:
    pf = _portfolio(core)
    risk = _d(pf.setdefault("risk_controls", {}))
    diagnostic = {
        **decision,
        "boundary": "exit_position_pre_mutation",
        "version": VERSION,
        "blocked_local": _now(core),
    }
    risk["canonical_full_exit_preflight_block"] = diagnostic
    risk["canonical_full_exit_preflight_active"] = True
    if not bool(risk.get("halted", False)):
        risk["halted"] = True
        risk["halt_reason"] = "canonical execution lifecycle integrity halt"
    pf["risk_controls"] = risk
    save = getattr(core, "save_state", None)
    if callable(save):
        try:
            save(pf)
        except TypeError:
            save()
        except Exception:
            pass


def _install_runtime_full_exit_guard(core: Any) -> bool:
    current = getattr(core, "exit_position", None)
    if not callable(current):
        return False
    marker = "_canonical_full_exit_preflight_version"
    if getattr(current, marker, None) == VERSION:
        _RUNTIME_GUARD_CORE_IDS.add(id(core))
        return True
    prior = getattr(current, "_canonical_full_exit_preflight_prior", current)

    @functools.wraps(prior)
    def guarded(symbol, px, *args, **kwargs):
        pf = _portfolio(core)
        pos = _d(_d(pf.get("positions")).get(str(symbol or "").upper().strip()))
        if not pos:
            return prior(symbol, px, *args, **kwargs)
        side = str(pos.get("side") or "long").lower().strip()
        shares = _f(pos.get("shares", pos.get("qty")), 0.0)
        decision = _canonical_full_exit_preflight(core, symbol, side, shares)
        if not bool(decision.get("allow")):
            _mark_runtime_full_exit_block(core, decision)
            return None
        return prior(symbol, px, *args, **kwargs)

    setattr(guarded, marker, VERSION)
    setattr(guarded, "_canonical_full_exit_preflight_prior", prior)
    setattr(core, "exit_position", guarded)
    _RUNTIME_GUARD_CORE_IDS.add(id(core))
    return True


def _economic_status(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core)
    rebuilt = analyze_ledger(pf, core)
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


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import paper_accounting_integrity_guard as accounting
        import paper_ledger_economic_integrity as economics
        accounting.reconstruct_from_ledger = analyze_ledger
        economics.status_payload = _economic_status
        economics.apply = _economic_status
        if core is not None and not _install_runtime_full_exit_guard(core):
            raise RuntimeError("core.exit_position_missing_for_canonical_full_exit_preflight")
        _APPLIED = True
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    rebuilt = analyze_ledger(_portfolio(core), core) if core is not None else {}
    risk = _d(_portfolio(core).get("risk_controls")) if core is not None else {}
    runtime_installed = bool(core is not None and id(core) in _RUNTIME_GUARD_CORE_IDS)
    return {
        "status": "ok" if _APPLIED and (core is None or runtime_installed) else "pending",
        "overall": "pass" if _APPLIED and (core is None or runtime_installed) else "warn",
        "type": "paper_ledger_matched_exit_guard_status",
        "version": VERSION,
        "applied": _APPLIED,
        "runtime_full_exit_guard_installed": runtime_installed,
        "runtime_full_exit_guard_boundary": "exit_position_pre_mutation",
        "runtime_full_exit_guard_fail_closed": True,
        "runtime_full_exit_guard_block": risk.get("canonical_full_exit_preflight_block"),
        "coverage_complete": bool(rebuilt.get("coverage_complete")),
        "baseline_type": rebuilt.get("baseline_type"),
        "parsed_trade_rows": int(rebuilt.get("parsed_trade_rows") or 0),
        "ignored_trade_rows": int(rebuilt.get("ignored_trade_rows") or 0),
        "coverage_issue_count": int(rebuilt.get("coverage_issue_count") or 0),
        "coverage_issues": _l(rebuilt.get("coverage_issues"))[:20],
        "reconstructed_cash": rebuilt.get("cash"),
        "authority": {
            "paper_accounting_reconstruction": True,
            "blocks_duplicate_or_unmatched_full_exit_before_mutation": True,
            "verified_snapshot_baseline_positions_remain_manageable": True,
            "repairs_historical_state": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    apply(core)
    if flask_app is None:
        return status_payload(core)
    if id(flask_app) not in _REGISTERED_APP_IDS:
        from flask import jsonify
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if "/paper/ledger-matched-exit-status" not in existing:
            flask_app.add_url_rule(
                "/paper/ledger-matched-exit-status",
                "paper_ledger_matched_exit_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(id(flask_app))
    return status_payload(core)
