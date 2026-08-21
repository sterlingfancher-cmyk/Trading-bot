"""Read-only deterministic successor replay for the verified v2 paper epoch.

Issue #82 now has two exact historical execution defects with durable evidence:

* TEM duplicate full exit ``3530dbf965db4894ba93b7098cec3696``;
* SLS catastrophic favorable partial exit ``b6584fe0e28744d8bfa2da26f413af70``.

The immutable canonical ledger must retain both rows.  This module therefore does
not edit, relabel, delete, or replace them.  On its explicit route it verifies the
ledger hash chain and exact signatures, starts from the mechanically verified
2026-08-12 v2 baseline, excludes only those two proven-invalid rows from a
counterfactual economic projection, and deterministically replays every other
canonical execution in order, including all executions after the SLS incident.

The result is evidence for a possible successor-state migration, not authority to
write state, clear a halt, rewrite a day peak, fabricate a replacement fill, or
change strategy/risk/sizing/live/ML behavior.  Startup ``apply()`` is constant-
time and performs no ledger or runtime-state scan.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Tuple

VERSION = "verified-v2-successor-replay-status-2026-08-21-v1"
ROUTE = "/paper/verified-v2-successor-replay-status"
TARGET_EPOCH_ID = "stable-paper-v2-20260812-verified01"
TODAY = "2026-08-21"

BASELINE_CASH = 10768.497730982748
BASELINE_LRCX_QTY = 3.42486
BASELINE_LRCX_ENTRY = 312.90

TEM_DUPLICATE_EXECUTION_ID = "3530dbf965db4894ba93b7098cec3696"
TEM_DUPLICATE_PRICE = 52.905
TEM_DUPLICATE_QTY = 29.640567
SLS_BAD_EXECUTION_ID = "b6584fe0e28744d8bfa2da26f413af70"
SLS_BAD_PRICE = 186.2901
SLS_BAD_QTY = 2.144058

QTY_TOLERANCE = 5e-6
PRICE_TOLERANCE = 1e-6
CASH_TOLERANCE = 2.0
_REGISTERED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _close(value: Any, expected: float, tolerance: float) -> bool:
    number = _f(value)
    return bool(number is not None and abs(number - expected) <= tolerance)


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_view(row: Dict[str, Any], index: int | None = None) -> Dict[str, Any]:
    out = {
        "execution_id": row.get("execution_id"),
        "accounting_epoch_id": row.get("accounting_epoch_id"),
        "recorded_local": row.get("recorded_local"),
        "action": row.get("action"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "price": _f(row.get("price")),
        "shares": _f(row.get("shares", row.get("qty"))),
        "exit_reason": row.get("exit_reason"),
        "event_hash": row.get("event_hash"),
    }
    if index is not None:
        out["ledger_index"] = index
    return out


def _tem_duplicate_signature(row: Dict[str, Any]) -> bool:
    return bool(
        str(row.get("execution_id") or "") == TEM_DUPLICATE_EXECUTION_ID
        and str(row.get("symbol") or "").upper() == "TEM"
        and str(row.get("action") or "").lower() == "exit"
        and str(row.get("side") or "long").lower() == "long"
        and _close(row.get("price"), TEM_DUPLICATE_PRICE, PRICE_TOLERANCE)
        and _close(row.get("shares", row.get("qty")), TEM_DUPLICATE_QTY, QTY_TOLERANCE)
    )


def _sls_bad_signature(row: Dict[str, Any]) -> bool:
    return bool(
        str(row.get("execution_id") or "") == SLS_BAD_EXECUTION_ID
        and str(row.get("symbol") or "").upper() == "SLS"
        and str(row.get("action") or "").lower() == "partial_exit"
        and str(row.get("side") or "long").lower() == "long"
        and _close(row.get("price"), SLS_BAD_PRICE, PRICE_TOLERANCE)
        and _close(row.get("shares", row.get("qty")), SLS_BAD_QTY, QTY_TOLERANCE)
    )


def _read_ledger() -> Tuple[List[Dict[str, Any]], List[str], bool, str]:
    try:
        import canonical_execution_ledger as ledger

        read_rows = getattr(ledger, "_read_rows", None)
        verify_rows = getattr(ledger, "_verify_rows", None)
        if not callable(read_rows) or not callable(verify_rows):
            return [], ["canonical_ledger_read_or_verify_helper_missing"], False, ""
        rows, parse_errors = read_rows()
        chain_valid, chain_errors = verify_rows(rows)
        return rows, list(parse_errors + chain_errors), bool(chain_valid and not parse_errors), str(
            getattr(ledger, "LEDGER_FILE", "") or ""
        )
    except Exception as exc:
        return [], [f"{type(exc).__name__}: {exc}"], False, ""


def _valid_execution_fields(row: Dict[str, Any]) -> Tuple[str, str, str, float, float] | None:
    action = str(row.get("action") or "").lower().strip()
    symbol = str(row.get("symbol") or "").upper().strip()
    side = str(row.get("side") or "").lower().strip()
    price = _f(row.get("price"))
    qty = _f(row.get("shares", row.get("qty")))
    if action not in {"entry", "exit", "partial_exit"}:
        return None
    if not symbol or side not in {"long", "short"}:
        return None
    if price is None or price <= 0 or qty is None or qty <= 0:
        return None
    return action, symbol, side, price, qty


def _empty_books() -> Dict[str, Dict[str, List[List[float]]]]:
    return {"LRCX": {"long": [[BASELINE_LRCX_QTY, BASELINE_LRCX_ENTRY]], "short": []}}


def _book_qty(book: List[List[float]]) -> float:
    return sum(float(row[0]) for row in book)


def _project(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    books = _empty_books()
    cash = BASELINE_CASH
    realized_delta = 0.0
    realized_today_delta = 0.0
    applied: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for index, row in enumerate(rows):
        execution_id = str(row.get("execution_id") or "")
        if execution_id == TEM_DUPLICATE_EXECUTION_ID:
            if not _tem_duplicate_signature(row):
                errors.append({"ledger_index": index, "reason": "tem_duplicate_signature_mismatch", "row": _row_view(row, index)})
                break
            excluded.append({
                "ledger_index": index,
                "execution_id": execution_id,
                "reason": "proven_duplicate_full_exit_retained_immutably_but_excluded_from_counterfactual_economics",
                "row": _row_view(row, index),
            })
            continue
        if execution_id == SLS_BAD_EXECUTION_ID:
            if not _sls_bad_signature(row):
                errors.append({"ledger_index": index, "reason": "sls_bad_execution_signature_mismatch", "row": _row_view(row, index)})
                break
            excluded.append({
                "ledger_index": index,
                "execution_id": execution_id,
                "reason": "independently_proven_catastrophic_quote_outlier_retained_immutably_but_excluded_from_counterfactual_economics",
                "row": _row_view(row, index),
            })
            continue

        fields = _valid_execution_fields(row)
        if fields is None:
            errors.append({"ledger_index": index, "reason": "unsupported_or_invalid_execution_fields", "row": _row_view(row, index)})
            break
        action, symbol, side, price, qty = fields
        side_books = books.setdefault(symbol, {"long": [], "short": []})
        opposite = "short" if side == "long" else "long"
        if action == "entry":
            if _book_qty(side_books[opposite]) > QTY_TOLERANCE:
                errors.append({"ledger_index": index, "reason": "opposing_open_book", "row": _row_view(row, index)})
                break
            notional = qty * price
            tolerance = max(CASH_TOLERANCE, abs(cash) * 0.0025)
            if notional > cash + tolerance:
                errors.append({
                    "ledger_index": index,
                    "reason": "entry_exceeds_available_cash",
                    "cash_before": cash,
                    "notional": notional,
                    "row": _row_view(row, index),
                })
                break
            cash -= notional
            side_books[side].append([qty, price])
            applied.append(_row_view(row, index))
            continue

        book = side_books[side]
        remaining = qty
        release = 0.0
        realized = 0.0
        while remaining > QTY_TOLERANCE and book:
            lot_qty, lot_price = book[0]
            used = min(remaining, lot_qty)
            if side == "long":
                release += used * price
                realized += (price - lot_price) * used
            else:
                pnl = (lot_price - price) * used
                release += (lot_price * used) + pnl
                realized += pnl
            lot_qty -= used
            remaining -= used
            if lot_qty <= QTY_TOLERANCE:
                book.pop(0)
            else:
                book[0][0] = lot_qty
        if remaining > QTY_TOLERANCE:
            errors.append({
                "ledger_index": index,
                "reason": "exit_exceeds_projected_position",
                "unmatched_qty": remaining,
                "row": _row_view(row, index),
            })
            break
        cash += release
        realized_delta += realized
        if str(row.get("recorded_local") or "").startswith(TODAY):
            realized_today_delta += realized
        applied.append(_row_view(row, index))

    positions: List[Dict[str, Any]] = []
    if not errors:
        for symbol, side_books in sorted(books.items()):
            open_sides = [side for side in ("long", "short") if _book_qty(side_books[side]) > QTY_TOLERANCE]
            if len(open_sides) > 1:
                errors.append({"reason": "opposing_books_remain", "symbol": symbol})
                break
            if not open_sides:
                continue
            side = open_sides[0]
            lots = side_books[side]
            qty = _book_qty(lots)
            basis = sum(float(lot_qty) * float(lot_price) for lot_qty, lot_price in lots)
            positions.append({
                "symbol": symbol,
                "side": side,
                "shares": round(qty, 9),
                "entry": round(basis / qty, 9),
                "cost_basis": round(basis, 9),
                "lot_count": len(lots),
            })

    return {
        "projection_complete": not errors,
        "errors": errors,
        "baseline": {
            "cash": BASELINE_CASH,
            "positions": [{"symbol": "LRCX", "side": "long", "shares": BASELINE_LRCX_QTY, "entry": BASELINE_LRCX_ENTRY}],
            "epoch_id": TARGET_EPOCH_ID,
        },
        "applied_execution_count": len(applied),
        "excluded_execution_count": len(excluded),
        "excluded_executions": excluded,
        "candidate_cash": round(cash, 9),
        "candidate_realized_delta_from_verified_baseline": round(realized_delta, 9),
        "candidate_realized_today_delta": round(realized_today_delta, 9),
        "candidate_positions": positions,
    }


def _state_comparison(portfolio: Dict[str, Any], projection: Dict[str, Any], successor_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    current_positions = _d(portfolio.get("positions"))
    projected_positions = {
        str(row.get("symbol") or ""): row
        for row in _l(projection.get("candidate_positions"))
        if isinstance(row, dict)
    }
    state_trades = [row for row in _l(portfolio.get("trades")) if isinstance(row, dict)]
    state_ids = {str(row.get("execution_id") or "") for row in state_trades}

    touched = sorted({str(row.get("symbol") or "").upper() for row in successor_rows if str(row.get("symbol") or "").strip()})
    symbol_rows: List[Dict[str, Any]] = []
    mark_coverage_complete = True
    projected_market_value = 0.0
    for symbol in sorted(set(projected_positions) | set(current_positions)):
        projected = _d(projected_positions.get(symbol))
        current = _d(current_positions.get(symbol))
        projected_qty = _f(projected.get("shares"))
        projected_entry = _f(projected.get("entry"))
        current_qty = _f(current.get("shares", current.get("qty")))
        current_entry = _f(current.get("entry", current.get("entry_price")))
        current_mark = _f(current.get("last_price"))
        projected_side = str(projected.get("side") or "")
        current_side = str(current.get("side") or "")
        qty_matches = bool(
            projected_qty is not None and current_qty is not None and abs(projected_qty - current_qty) <= QTY_TOLERANCE
        )
        entry_matches = bool(
            projected_entry is not None and current_entry is not None and abs(projected_entry - current_entry) <= 1e-5
        )
        side_matches = bool(projected_side and projected_side == current_side)
        if projected:
            if current_mark is None or current_mark <= 0:
                mark_coverage_complete = False
            else:
                if projected_side == "long":
                    projected_market_value += float(projected_qty or 0.0) * current_mark
                else:
                    basis = float(projected.get("cost_basis") or 0.0)
                    projected_market_value += basis + ((float(projected_entry or 0.0) - current_mark) * float(projected_qty or 0.0))
        symbol_rows.append({
            "symbol": symbol,
            "projected_exists": bool(projected),
            "projected_side": projected.get("side"),
            "projected_shares": projected_qty,
            "projected_entry": projected_entry,
            "current_exists": bool(current),
            "current_side": current.get("side"),
            "current_shares": current_qty,
            "current_entry": current_entry,
            "current_last_price": current_mark,
            "side_matches": side_matches,
            "quantity_matches": qty_matches,
            "entry_matches": entry_matches,
        })

    candidate_cash = _f(projection.get("candidate_cash"))
    candidate_equity = None
    if mark_coverage_complete and candidate_cash is not None:
        candidate_equity = candidate_cash + projected_market_value

    current_cash = _f(portfolio.get("cash"))
    current_equity = _f(portfolio.get("equity"))
    return {
        "current_account": {
            "cash": current_cash,
            "equity": current_equity,
            "positions_count": len(current_positions),
            "state_trade_count": len(state_trades),
        },
        "successor_execution_presence_in_state_trades": [
            {
                "execution_id": row.get("execution_id"),
                "symbol": row.get("symbol"),
                "action": row.get("action"),
                "present_in_state_trades": str(row.get("execution_id") or "") in state_ids,
            }
            for row in successor_rows
        ],
        "successor_touched_symbols": touched,
        "position_comparison": symbol_rows,
        "all_projected_positions_match_current_quantity_side_entry": bool(symbol_rows) and all(
            (not row["projected_exists"] and not row["current_exists"])
            or (row["projected_exists"] and row["current_exists"] and row["side_matches"] and row["quantity_matches"] and row["entry_matches"])
            for row in symbol_rows
        ),
        "candidate_equity_using_current_stored_marks": round(candidate_equity, 9) if candidate_equity is not None else None,
        "current_state_mark_coverage_complete_for_projected_positions": mark_coverage_complete,
        "candidate_cash_minus_current_cash": round(candidate_cash - current_cash, 9) if candidate_cash is not None and current_cash is not None else None,
        "candidate_equity_minus_current_equity": round(candidate_equity - current_equity, 9) if candidate_equity is not None and current_equity is not None else None,
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    portfolio = _d(getattr(core, "portfolio", None)) if core is not None else {}
    rows, ledger_errors, chain_valid, ledger_file = _read_ledger()
    epoch_ids = sorted({str(row.get("accounting_epoch_id") or "") for row in rows})
    execution_ids = [str(row.get("execution_id") or "") for row in rows]

    tem_rows = [row for row in rows if str(row.get("execution_id") or "") == TEM_DUPLICATE_EXECUTION_ID]
    sls_rows = [row for row in rows if str(row.get("execution_id") or "") == SLS_BAD_EXECUTION_ID]
    tem_exact = len(tem_rows) == 1 and _tem_duplicate_signature(tem_rows[0])
    sls_exact = len(sls_rows) == 1 and _sls_bad_signature(sls_rows[0])
    sls_index = execution_ids.index(SLS_BAD_EXECUTION_ID) if execution_ids.count(SLS_BAD_EXECUTION_ID) == 1 else None
    successor_rows_raw = rows[sls_index + 1 :] if sls_index is not None else []
    successor_rows = [_row_view(row, sls_index + 1 + offset) for offset, row in enumerate(successor_rows_raw)]

    ledger_ready = bool(
        chain_valid
        and not ledger_errors
        and rows
        and epoch_ids == [TARGET_EPOCH_ID]
        and len(execution_ids) == len(set(execution_ids))
        and tem_exact
        and sls_exact
    )
    projection = _project(rows) if ledger_ready else {
        "projection_complete": False,
        "errors": [{"reason": "ledger_or_known_invalid_signature_not_ready"}],
        "candidate_cash": None,
        "candidate_positions": [],
    }
    comparison = _state_comparison(portfolio, projection, successor_rows) if ledger_ready else {}

    if not chain_valid or ledger_errors:
        diagnosis = "canonical_ledger_invalid_successor_replay_blocked"
        overall = "fail"
    elif epoch_ids != [TARGET_EPOCH_ID]:
        diagnosis = "canonical_ledger_epoch_lineage_not_exactly_verified_v2"
        overall = "fail"
    elif not tem_exact or not sls_exact:
        diagnosis = "known_invalid_execution_signature_not_exact_successor_replay_blocked"
        overall = "fail"
    elif not bool(projection.get("projection_complete")):
        diagnosis = "verified_v2_counterfactual_replay_failed_on_remaining_canonical_execution"
        overall = "fail"
    else:
        diagnosis = "verified_v2_successor_replay_mechanically_complete"
        overall = "pass"

    return {
        "status": "ok",
        "overall": overall,
        "type": "verified_v2_successor_replay_status",
        "version": VERSION,
        "generated_local": _now(core),
        "diagnosis": diagnosis,
        "ledger": {
            "file": ledger_file,
            "row_count": len(rows),
            "chain_valid": chain_valid,
            "errors": ledger_errors[:10],
            "epoch_ids": epoch_ids,
            "all_rows_target_epoch": epoch_ids == [TARGET_EPOCH_ID],
            "execution_ids_unique": len(execution_ids) == len(set(execution_ids)),
        },
        "known_invalid_execution_disposition": {
            "tem_duplicate": {
                "execution_id": TEM_DUPLICATE_EXECUTION_ID,
                "match_count": len(tem_rows),
                "signature_exact": tem_exact,
                "immutable_row_retained": True,
                "counterfactual_economic_disposition": "exclude_only_from_successor_projection",
            },
            "sls_bad_partial_exit": {
                "execution_id": SLS_BAD_EXECUTION_ID,
                "match_count": len(sls_rows),
                "signature_exact": sls_exact,
                "immutable_row_retained": True,
                "counterfactual_economic_disposition": "exclude_only_from_successor_projection",
            },
        },
        "successor_rows_after_sls_bad_execution": successor_rows,
        "successor_row_count": len(successor_rows),
        "projection": projection,
        "state_comparison": comparison,
        "recovery_readiness": {
            "counterfactual_successor_projection_mechanically_reproducible": bool(projection.get("projection_complete")),
            "all_post_sls_canonical_rows_replayed": bool(projection.get("projection_complete") and len(successor_rows) == 3),
            "historical_execution_edit_required": False,
            "immutable_invalid_rows_must_remain_in_ledger": True,
            "state_write_authorized_by_this_probe": False,
            "risk_peak_repair_authorized_by_this_probe": False,
            "halt_clear_authorized_by_this_probe": False,
            "replacement_fill_fabricated": False,
            "next_step": (
                "compare deterministic projected economics with current-state evidence and independently validate any remaining valuation/risk difference before designing a bounded one-shot successor migration"
                if bool(projection.get("projection_complete"))
                else "stop; inspect the first projection error without mutating state or ledger"
            ),
        },
        "authority": {
            "reporting_only": True,
            "counterfactual_only": True,
            "reads_canonical_ledger": True,
            "calls_market_data_providers": False,
            "writes_files": False,
            "saves_state": False,
            "repairs_historical_state": False,
            "deletes_execution_rows": False,
            "rewrites_or_relabels_canonical_ledger": False,
            "rewrites_current_day_peak": False,
            "clears_hard_halt": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "installed": True,
        "startup_reads_runtime_state": False,
        "startup_reads_canonical_ledger": False,
        "startup_writes_state_or_files": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "flask_app_missing"}
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify

        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if ROUTE not in existing:
            flask_app.add_url_rule(
                ROUTE,
                "verified_v2_successor_replay_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(app_id)
    return {"status": "ok", "overall": "pass", "version": VERSION, "route": ROUTE}
