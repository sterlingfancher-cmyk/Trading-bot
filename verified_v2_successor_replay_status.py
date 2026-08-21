"""Consolidated read-only recovery gate for the verified v2 paper epoch.

Issue #82 now has seven immutable canonical executions with durable evidence that
their economic effects must not be used in a successor projection:

* TEM duplicate full exit ``3530dbf965db4894ba93b7098cec3696``;
* two UCTT invalid exits, including a catastrophic favorable partial exit and a
  later unmatched/adverse exit inconsistent with independent market evidence;
* SLS catastrophic favorable partial exit ``b6584fe0e28744d8bfa2da26f413af70``;
* three TOST catastrophic favorable partial exits recorded after the SLS event.

The canonical ledger remains immutable. This module verifies the hash chain and
exact row signatures, starts from the mechanically verified 2026-08-12 v2
baseline, excludes only the proven-invalid economic effects, and replays every
other canonical execution in original order.

This is the single compact forensic/recovery gate. It never writes state, edits
or relabels ledger rows, fabricates replacement fills, clears a halt, rewrites
the current-day peak, or changes strategy/risk/sizing/live/ML authority.
Startup ``apply()`` is constant-time and performs no ledger/state scan.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Tuple

VERSION = "verified-v2-successor-replay-status-2026-08-21-v3-consolidated-seven-invalid"
ROUTE = "/paper/verified-v2-successor-replay-status"
TARGET_EPOCH_ID = "stable-paper-v2-20260812-verified01"
TODAY = "2026-08-21"

BASELINE_CASH = 10768.497730982748
BASELINE_LRCX_QTY = 3.42486
BASELINE_LRCX_ENTRY = 312.90

TEM_DUPLICATE_EXECUTION_ID = "3530dbf965db4894ba93b7098cec3696"
TEM_DUPLICATE_PRICE = 52.904999
TEM_DUPLICATE_QTY = 29.640567
UCTT_BAD_PARTIAL_EXECUTION_ID = "e604e478d0df47ed9c7da1c7b290cba8"
UCTT_BAD_DUPLICATE_EXIT_EXECUTION_ID = "b8062fa9c2464251b661957d0694bbfa"
SLS_BAD_EXECUTION_ID = "b6584fe0e28744d8bfa2da26f413af70"
SLS_BAD_PRICE = 186.2901
SLS_BAD_QTY = 2.144057692

TOST_BAD_1_EXECUTION_ID = "fd685aa6387247ff99a05e7386c325e9"
TOST_BAD_2_EXECUTION_ID = "cb10928f441148aaa3faf041a84bc4c8"
TOST_BAD_3_EXECUTION_ID = "1451d91c06b34b199364b56f72ad376f"

PRICE_TOLERANCE = 1e-9
QTY_TOLERANCE = 5e-9
CASH_TOLERANCE = 2.0
_REGISTERED_APP_IDS: set[int] = set()

KNOWN_INVALID_EXECUTIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "tem_duplicate",
        "execution_id": TEM_DUPLICATE_EXECUTION_ID,
        "accounting_epoch_id": TARGET_EPOCH_ID,
        "action": "exit",
        "symbol": "TEM",
        "side": "long",
        "price": TEM_DUPLICATE_PRICE,
        "shares": TEM_DUPLICATE_QTY,
        "recorded_local": "2026-08-14 08:48:37 CDT",
        "exit_reason": "stop_loss",
        "reason": "proven_duplicate_full_exit_retained_immutably_but_excluded_from_counterfactual_economics",
        "evidence": "prior_full_exit_closed_the_same_long_quantity_before_this_row",
    },
    {
        "key": "uctt_bad_partial_exit",
        "execution_id": UCTT_BAD_PARTIAL_EXECUTION_ID,
        "accounting_epoch_id": TARGET_EPOCH_ID,
        "action": "partial_exit",
        "symbol": "UCTT",
        "side": "long",
        "price": 337.54,
        "shares": 5.74555,
        "event_hash": "c7e23d77ecc86e6521f702b814828815a9f17e8f697c9baf07490be0e96ee41b",
        "reason": "proven_catastrophic_quote_outlier_retained_immutably_but_excluded_from_counterfactual_economics",
        "evidence": "independent_alpaca_iex_one_minute_bars_near_94_at_2026-08-13T19:37Z_and_no_split",
    },
    {
        "key": "uctt_bad_duplicate_exit",
        "execution_id": UCTT_BAD_DUPLICATE_EXIT_EXECUTION_ID,
        "accounting_epoch_id": TARGET_EPOCH_ID,
        "action": "exit",
        "symbol": "UCTT",
        "side": "long",
        "price": 39.145,
        "shares": 11.665207,
        "recorded_local": "2026-08-13 14:59:04 CDT",
        "exit_reason": "stop_loss",
        "event_hash": "d928b227f1f800b38e1b31fed9c35c9e62f2417f58c28b2d602a7c4104b71812",
        "reason": "proven_unmatched_duplicate_and_catastrophic_quote_outlier_retained_immutably_but_excluded_from_counterfactual_economics",
        "evidence": "prior_valid_uctt_exit_closed_the_remaining_quantity_and_independent_alpaca_iex_quote_at_2026-08-13T19:59:04Z_was_93.10x93.23_with_no_split",
    },
    {
        "key": "sls_bad_partial_exit",
        "execution_id": SLS_BAD_EXECUTION_ID,
        "accounting_epoch_id": TARGET_EPOCH_ID,
        "action": "partial_exit",
        "symbol": "SLS",
        "side": "long",
        "price": SLS_BAD_PRICE,
        "shares": SLS_BAD_QTY,
        "recorded_local": "2026-08-21 09:51:13 CDT",
        "exit_reason": "partial_profit_long",
        "reason": "proven_catastrophic_quote_outlier_retained_immutably_but_excluded_from_counterfactual_economics",
        "evidence": "independent_alpaca_iex_quotes_near_14.16_to_14.27_no_split",
    },
    {
        "key": "tost_bad_partial_exit_1",
        "execution_id": TOST_BAD_1_EXECUTION_ID,
        "accounting_epoch_id": TARGET_EPOCH_ID,
        "action": "partial_exit",
        "symbol": "TOST",
        "side": "long",
        "price": 73.940002,
        "shares": 1.24333584,
        "recorded_local": "2026-08-21 13:11:11 CDT",
        "exit_reason": "partial_profit_long",
        "reason": "proven_catastrophic_quote_outlier_retained_immutably_but_excluded_from_counterfactual_economics",
        "evidence": "independent_alpaca_iex_quotes_near_36.21_to_36.25_no_split",
    },
    {
        "key": "tost_bad_partial_exit_2",
        "execution_id": TOST_BAD_2_EXECUTION_ID,
        "accounting_epoch_id": TARGET_EPOCH_ID,
        "action": "partial_exit",
        "symbol": "TOST",
        "side": "long",
        "price": 190.244995,
        "shares": 1.24333584,
        "recorded_local": "2026-08-21 14:03:17 CDT",
        "exit_reason": "partial_profit_long",
        "reason": "proven_catastrophic_quote_outlier_retained_immutably_but_excluded_from_counterfactual_economics",
        "evidence": "independent_alpaca_iex_quotes_near_36.44_to_36.47_no_split",
    },
    {
        "key": "tost_bad_partial_exit_3",
        "execution_id": TOST_BAD_3_EXECUTION_ID,
        "accounting_epoch_id": TARGET_EPOCH_ID,
        "action": "partial_exit",
        "symbol": "TOST",
        "side": "long",
        "price": 74.269997,
        "shares": 1.24333584,
        "recorded_local": "2026-08-21 14:35:20 CDT",
        "exit_reason": "partial_profit_long",
        "reason": "proven_catastrophic_quote_outlier_retained_immutably_but_excluded_from_counterfactual_economics",
        "evidence": "independent_alpaca_iex_quotes_near_36.39_to_36.44_no_split",
    },
)
KNOWN_INVALID_BY_ID = {
    str(item["execution_id"]): item for item in KNOWN_INVALID_EXECUTIONS
}
KNOWN_INVALID_SYMBOLS = {str(item["symbol"]) for item in KNOWN_INVALID_EXECUTIONS}


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
    return number is not None and abs(number - expected) <= tolerance


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


def _signature_checks(row: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, bool]:
    checks = {
        "execution_id": str(row.get("execution_id") or "") == str(expected["execution_id"]),
        "accounting_epoch_id": str(row.get("accounting_epoch_id") or "") == str(expected["accounting_epoch_id"]),
        "action": str(row.get("action") or "").lower() == str(expected["action"]),
        "symbol": str(row.get("symbol") or "").upper() == str(expected["symbol"]),
        "side": str(row.get("side") or "long").lower() == str(expected["side"]),
        "price": _close(row.get("price"), float(expected["price"]), PRICE_TOLERANCE),
        "shares": _close(row.get("shares", row.get("qty")), float(expected["shares"]), QTY_TOLERANCE),
    }
    if "recorded_local" in expected:
        checks["recorded_local"] = str(row.get("recorded_local") or "") == str(expected["recorded_local"])
    if "exit_reason" in expected:
        checks["exit_reason"] = str(row.get("exit_reason") or "") == str(expected["exit_reason"])
    if "event_hash" in expected:
        checks["event_hash"] = str(row.get("event_hash") or "") == str(expected["event_hash"])
    return checks


def _signature_exact(row: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    return all(_signature_checks(row, expected).values())


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
        invalid = KNOWN_INVALID_BY_ID.get(execution_id)
        if invalid is not None:
            checks = _signature_checks(row, invalid)
            if not all(checks.values()):
                errors.append(
                    {
                        "ledger_index": index,
                        "reason": "known_invalid_execution_signature_mismatch",
                        "key": invalid["key"],
                        "failed_checks": [key for key, matches in checks.items() if not matches],
                        "row": _row_view(row, index),
                    }
                )
                break
            excluded.append(
                {
                    "ledger_index": index,
                    "key": invalid["key"],
                    "execution_id": execution_id,
                    "reason": invalid["reason"],
                    "evidence": invalid["evidence"],
                    "row": _row_view(row, index),
                }
            )
            continue

        fields = _valid_execution_fields(row)
        if fields is None:
            errors.append(
                {
                    "ledger_index": index,
                    "reason": "unsupported_or_invalid_execution_fields",
                    "row": _row_view(row, index),
                }
            )
            break

        action, symbol, side, price, qty = fields
        side_books = books.setdefault(symbol, {"long": [], "short": []})
        opposite = "short" if side == "long" else "long"

        if action == "entry":
            if _book_qty(side_books[opposite]) > QTY_TOLERANCE:
                errors.append(
                    {
                        "ledger_index": index,
                        "reason": "opposing_open_book",
                        "row": _row_view(row, index),
                    }
                )
                break
            notional = qty * price
            tolerance = max(CASH_TOLERANCE, abs(cash) * 0.0025)
            if notional > cash + tolerance:
                errors.append(
                    {
                        "ledger_index": index,
                        "reason": "entry_exceeds_available_cash",
                        "cash_before": cash,
                        "notional": notional,
                        "row": _row_view(row, index),
                    }
                )
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
            errors.append(
                {
                    "ledger_index": index,
                    "reason": "exit_exceeds_projected_position",
                    "unmatched_qty": remaining,
                    "row": _row_view(row, index),
                }
            )
            break

        cash += release
        realized_delta += realized
        if str(row.get("recorded_local") or "").startswith(TODAY):
            realized_today_delta += realized
        applied.append(_row_view(row, index))

    positions: List[Dict[str, Any]] = []
    if not errors:
        for symbol, side_books in sorted(books.items()):
            open_sides = [
                side
                for side in ("long", "short")
                if _book_qty(side_books[side]) > QTY_TOLERANCE
            ]
            if len(open_sides) > 1:
                errors.append({"reason": "opposing_books_remain", "symbol": symbol})
                break
            if not open_sides:
                continue
            side = open_sides[0]
            lots = side_books[side]
            qty = _book_qty(lots)
            basis = sum(float(lot_qty) * float(lot_price) for lot_qty, lot_price in lots)
            positions.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "shares": round(qty, 9),
                    "entry": round(basis / qty, 9),
                    "cost_basis": round(basis, 9),
                    "lot_count": len(lots),
                }
            )

    return {
        "projection_complete": not errors,
        "errors": errors,
        "baseline": {
            "cash": BASELINE_CASH,
            "positions": [
                {
                    "symbol": "LRCX",
                    "side": "long",
                    "shares": BASELINE_LRCX_QTY,
                    "entry": BASELINE_LRCX_ENTRY,
                }
            ],
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


def _state_comparison(portfolio: Dict[str, Any], projection: Dict[str, Any]) -> Dict[str, Any]:
    current_positions = _d(portfolio.get("positions"))
    projected_positions = {
        str(row.get("symbol") or ""): row
        for row in _l(projection.get("candidate_positions"))
        if isinstance(row, dict)
    }
    state_trades = [row for row in _l(portfolio.get("trades")) if isinstance(row, dict)]
    state_ids = {str(row.get("execution_id") or "") for row in state_trades}

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

        quantity_matches = bool(
            projected_qty is not None
            and current_qty is not None
            and abs(projected_qty - current_qty) <= 5e-6
        )
        entry_matches = bool(
            projected_entry is not None
            and current_entry is not None
            and abs(projected_entry - current_entry) <= 1e-5
        )
        side_matches = bool(projected_side and projected_side == current_side)
        exists_matches = bool(projected) == bool(current)

        if projected:
            if current_mark is None or current_mark <= 0:
                mark_coverage_complete = False
            elif projected_side == "long":
                projected_market_value += float(projected_qty or 0.0) * current_mark
            else:
                basis = float(projected.get("cost_basis") or 0.0)
                projected_market_value += basis + (
                    (float(projected_entry or 0.0) - current_mark)
                    * float(projected_qty or 0.0)
                )

        mismatch = not (
            exists_matches
            and (
                not projected
                or (
                    bool(current)
                    and side_matches
                    and quantity_matches
                    and entry_matches
                )
            )
        )
        symbol_rows.append(
            {
                "symbol": symbol,
                "known_invalid_symbol": symbol in KNOWN_INVALID_SYMBOLS,
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
                "quantity_matches": quantity_matches,
                "entry_matches": entry_matches,
                "mismatch": mismatch,
            }
        )

    candidate_cash = _f(projection.get("candidate_cash"))
    candidate_equity = None
    if mark_coverage_complete and candidate_cash is not None:
        candidate_equity = candidate_cash + projected_market_value

    current_cash = _f(portfolio.get("cash"))
    current_equity = _f(portfolio.get("equity"))
    current_realized_today = _f(portfolio.get("realized_today"))
    if current_realized_today is None:
        current_realized_today = _f(portfolio.get("realized_pnl_today"))
    candidate_realized_today = _f(projection.get("candidate_realized_today_delta"))

    unexplained_mismatches = [
        row["symbol"]
        for row in symbol_rows
        if row["mismatch"] and not row["known_invalid_symbol"]
    ]

    return {
        "current_account": {
            "cash": current_cash,
            "equity": current_equity,
            "realized_today": current_realized_today,
            "positions_count": len(current_positions),
            "state_trade_count": len(state_trades),
        },
        "known_invalid_execution_presence_in_state_trades": [
            {
                "key": item["key"],
                "execution_id": item["execution_id"],
                "symbol": item["symbol"],
                "present_in_state_trades": str(item["execution_id"]) in state_ids,
            }
            for item in KNOWN_INVALID_EXECUTIONS
        ],
        "position_comparison": symbol_rows,
        "unexplained_position_mismatches": unexplained_mismatches,
        "only_known_invalid_symbols_differ": not unexplained_mismatches,
        "candidate_equity_using_current_stored_marks": (
            round(candidate_equity, 9) if candidate_equity is not None else None
        ),
        "current_state_mark_coverage_complete_for_projected_positions": mark_coverage_complete,
        "candidate_cash_minus_current_cash": (
            round(candidate_cash - current_cash, 9)
            if candidate_cash is not None and current_cash is not None
            else None
        ),
        "candidate_equity_minus_current_equity": (
            round(candidate_equity - current_equity, 9)
            if candidate_equity is not None and current_equity is not None
            else None
        ),
        "candidate_realized_today_minus_current_realized_today": (
            round(candidate_realized_today - current_realized_today, 9)
            if candidate_realized_today is not None and current_realized_today is not None
            else None
        ),
    }


def _known_invalid_disposition(rows: List[Dict[str, Any]]) -> tuple[Dict[str, Any], bool]:
    disposition: Dict[str, Any] = {}
    all_exact = True

    for expected in KNOWN_INVALID_EXECUTIONS:
        matches = [
            (index, row)
            for index, row in enumerate(rows)
            if str(row.get("execution_id") or "") == str(expected["execution_id"])
        ]
        exact = len(matches) == 1 and _signature_exact(matches[0][1], expected)
        all_exact = all_exact and exact
        ledger_index = None
        observed = None
        failed_checks: List[str] = []

        if len(matches) == 1:
            ledger_index, observed_row = matches[0]
            field_checks = _signature_checks(observed_row, expected)
            failed_checks = [
                key for key, matches_field in field_checks.items() if not matches_field
            ]
            observed = _row_view(observed_row, ledger_index)

        disposition[str(expected["key"])] = {
            "execution_id": expected["execution_id"],
            "match_count": len(matches),
            "signature_exact": exact,
            "ledger_index": ledger_index,
            "failed_checks": failed_checks,
            "observed_row": observed,
            "immutable_row_retained": True,
            "counterfactual_economic_disposition": "exclude_only_from_successor_projection",
            "evidence": expected["evidence"],
        }

    return disposition, all_exact


def _risk_snapshot(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    risk = _d(portfolio.get("risk_controls"))
    return {
        "date": risk.get("date"),
        "day_start_equity": _f(risk.get("day_start_equity")),
        "day_peak_equity": _f(risk.get("day_peak_equity")),
        "halted": bool(risk.get("halted")),
        "halt_reason": risk.get("halt_reason"),
        "intraday_drawdown_pct": _f(risk.get("intraday_drawdown_pct")),
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    portfolio = _d(getattr(core, "portfolio", None)) if core is not None else {}
    rows, ledger_errors, chain_valid, ledger_file = _read_ledger()
    epoch_ids = sorted({str(row.get("accounting_epoch_id") or "") for row in rows})
    execution_ids = [str(row.get("execution_id") or "") for row in rows]

    disposition, all_invalid_signatures_exact = _known_invalid_disposition(rows)
    invalid_indices = sorted(
        int(item["ledger_index"])
        for item in disposition.values()
        if item.get("ledger_index") is not None
    )
    last_invalid_index = max(invalid_indices) if invalid_indices else None
    rows_after_last_invalid_raw = rows[last_invalid_index + 1 :] if last_invalid_index is not None else []
    rows_after_last_invalid = [
        _row_view(row, last_invalid_index + 1 + offset)
        for offset, row in enumerate(rows_after_last_invalid_raw)
    ]
    latest_invalid_is_last_canonical_execution = bool(
        rows and last_invalid_index == len(rows) - 1
    )

    ledger_ready = bool(
        chain_valid
        and not ledger_errors
        and rows
        and epoch_ids == [TARGET_EPOCH_ID]
        and len(execution_ids) == len(set(execution_ids))
        and all_invalid_signatures_exact
    )
    projection = (
        _project(rows)
        if ledger_ready
        else {
            "projection_complete": False,
            "errors": [{"reason": "ledger_or_known_invalid_signature_not_ready"}],
            "candidate_cash": None,
            "candidate_positions": [],
        }
    )
    comparison = (
        _state_comparison(portfolio, projection)
        if ledger_ready and bool(projection.get("projection_complete"))
        else {}
    )

    if not chain_valid or ledger_errors:
        diagnosis = "canonical_ledger_invalid_recovery_gate_blocked"
        overall = "fail"
    elif epoch_ids != [TARGET_EPOCH_ID]:
        diagnosis = "canonical_ledger_epoch_lineage_not_exactly_verified_v2"
        overall = "fail"
    elif len(execution_ids) != len(set(execution_ids)):
        diagnosis = "canonical_execution_ids_not_unique_recovery_gate_blocked"
        overall = "fail"
    elif not all_invalid_signatures_exact:
        diagnosis = "known_invalid_execution_signature_not_exact_recovery_gate_blocked"
        overall = "fail"
    elif not bool(projection.get("projection_complete")):
        diagnosis = "verified_v2_counterfactual_replay_failed_on_remaining_canonical_execution"
        overall = "fail"
    elif not latest_invalid_is_last_canonical_execution:
        diagnosis = "verified_v2_replay_complete_but_newer_canonical_rows_require_review"
        overall = "warn"
    elif not bool(comparison.get("only_known_invalid_symbols_differ", False)):
        diagnosis = "verified_v2_replay_complete_but_unexplained_state_position_difference_remains"
        overall = "warn"
    else:
        diagnosis = "verified_v2_consolidated_recovery_gate_mechanically_complete"
        overall = "pass"

    mechanically_complete = overall == "pass"
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
        "known_invalid_execution_count": len(KNOWN_INVALID_EXECUTIONS),
        "known_invalid_execution_disposition": disposition,
        "all_known_invalid_signatures_exact": all_invalid_signatures_exact,
        "last_known_invalid_ledger_index": last_invalid_index,
        "latest_invalid_is_last_canonical_execution": latest_invalid_is_last_canonical_execution,
        "canonical_rows_after_last_known_invalid": rows_after_last_invalid,
        "canonical_rows_after_last_known_invalid_count": len(rows_after_last_invalid),
        "projection": projection,
        "state_comparison": comparison,
        "current_risk": _risk_snapshot(portfolio),
        "recovery_readiness": {
            "counterfactual_successor_projection_mechanically_reproducible": bool(projection.get("projection_complete")),
            "all_canonical_rows_accounted_for": bool(projection.get("projection_complete")),
            "all_seven_known_invalid_rows_exact": all_invalid_signatures_exact,
            "latest_known_invalid_is_terminal": latest_invalid_is_last_canonical_execution,
            "only_known_invalid_symbols_explain_position_differences": bool(comparison.get("only_known_invalid_symbols_differ", False)),
            "mechanically_complete_for_successor_migration_design": mechanically_complete,
            "historical_execution_edit_required": False,
            "immutable_invalid_rows_must_remain_in_ledger": True,
            "state_write_authorized_by_this_probe": False,
            "risk_peak_repair_authorized_by_this_probe": False,
            "halt_clear_authorized_by_this_probe": False,
            "replacement_fill_fabricated": False,
            "manual_per_event_probe_required": False,
            "next_step": (
                "use this consolidated gate as the sole forensic runtime input for a bounded exact-signature successor-state migration under validation hold; do not request another per-event manual probe"
                if mechanically_complete
                else "stop at the named gate failure; do not mutate state or ledger"
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
        "consolidates_manual_forensic_routes": True,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {
            "status": "pending",
            "overall": "warn",
            "version": VERSION,
            "reason": "flask_app_missing",
        }

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

    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "route": ROUTE,
    }
