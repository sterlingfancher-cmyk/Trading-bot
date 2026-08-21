"""Read-only deterministic proof for the 2026-08-21 SLS bad execution.

Issue #82 runtime evidence proved that a long SLS position entered near 14.335 was
partially exited at 186.2901 even though independent IEX quotes around the exact
execution second were near 14.2.  The bad execution inflated cash/realized PnL and
also contaminated the position/risk path.

This module does *not* repair anything.  Its explicit route verifies the exact
state-trade and canonical-ledger signatures, verifies the immutable ledger hash
chain, determines whether any canonical executions occurred after the bad row,
and computes the arithmetic counterfactual obtained by reversing only that exact
partial exit while marking the restored shares at the position's already-stored
current mark.  It never deletes/relabels a ledger row, writes state, clears a
halt, rewrites a risk peak, calls a market-data provider, or places an order.

The independent market evidence is a durable transcription of the separate
Alpaca IEX query performed after the incident.  It is evidence for invalidity of
the 186.2901 execution, not a replacement execution price.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Tuple

VERSION = "sls-bad-execution-recovery-proof-2026-08-21-v1"
ROUTE = "/paper/sls-bad-execution-recovery-proof"
TARGET_EPOCH_ID = "stable-paper-v2-20260812-verified01"
SYMBOL = "SLS"
ENTRY_EXECUTION_ID = "4dfe9d5b3e50432c820723ea9a39dcb0"
BAD_EXECUTION_ID = "b6584fe0e28744d8bfa2da26f413af70"
ENTRY_PRICE = 14.335
ENTRY_SHARES = 6.497145
BAD_PRICE = 186.2901
BAD_SHARES = 2.144058
BAD_ACTION = "partial_exit"
BAD_SIDE = "long"
QUANTITY_TOLERANCE = 5e-6
MONEY_TOLERANCE = 0.05
_REGISTERED_APP_IDS: set[int] = set()

INDEPENDENT_MARKET_EVIDENCE = {
    "source": "Alpaca IEX historical quotes/bars queried independently after the incident",
    "symbol": SYMBOL,
    "quote_window_utc": "2026-08-21T14:50:30.339909Z..2026-08-21T14:51:35.481355Z",
    "observed_bid_range": [14.16, 14.23],
    "observed_ask_range": [14.26, 14.27],
    "one_minute_bar_window_utc": "2026-08-21T14:45:00Z..2026-08-21T14:55:00Z",
    "observed_one_minute_bar_low": 14.105,
    "observed_one_minute_bar_high": 14.29,
    "split_check_window": "2026-08-18..2026-08-22",
    "split_corporate_actions_found": 0,
    "recorded_bad_execution_price": BAD_PRICE,
    "bad_price_to_max_observed_ask_ratio": round(BAD_PRICE / 14.27, 6),
    "bad_price_to_entry_ratio": round(BAD_PRICE / ENTRY_PRICE, 6),
    "evidence_role": "proves recorded execution price is not economically plausible; does not fabricate a replacement fill",
}


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


def _close(value: Any, expected: float, tolerance: float = QUANTITY_TOLERANCE) -> bool:
    number = _f(value)
    return bool(number is not None and abs(number - expected) <= tolerance)


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _epoch_id(portfolio: Dict[str, Any]) -> str:
    direct = str(portfolio.get("accounting_epoch_id") or "").strip()
    if direct:
        return direct
    epoch = _d(portfolio.get("paper_accounting_epoch"))
    return str(epoch.get("id") or epoch.get("epoch_id") or "").strip()


def _row_view(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "execution_id": row.get("execution_id"),
        "accounting_epoch_id": row.get("accounting_epoch_id"),
        "recorded_local": row.get("recorded_local"),
        "time": row.get("time"),
        "action": row.get("action"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "price": _f(row.get("price")),
        "shares": _f(row.get("shares", row.get("qty"))),
        "exit_reason": row.get("exit_reason"),
        "event_hash": row.get("event_hash", row.get("canonical_ledger_event_hash")),
    }


def _entry_signature(row: Dict[str, Any]) -> bool:
    return bool(
        str(row.get("execution_id") or "") == ENTRY_EXECUTION_ID
        and str(row.get("symbol") or "").upper() == SYMBOL
        and str(row.get("action") or "").lower() == "entry"
        and str(row.get("side") or "long").lower() == "long"
        and _close(row.get("price"), ENTRY_PRICE, 1e-6)
        and _close(row.get("shares", row.get("qty")), ENTRY_SHARES)
    )


def _bad_signature(row: Dict[str, Any]) -> bool:
    return bool(
        str(row.get("execution_id") or "") == BAD_EXECUTION_ID
        and str(row.get("symbol") or "").upper() == SYMBOL
        and str(row.get("action") or "").lower() == BAD_ACTION
        and str(row.get("side") or "long").lower() == BAD_SIDE
        and _close(row.get("price"), BAD_PRICE, 1e-6)
        and _close(row.get("shares", row.get("qty")), BAD_SHARES)
    )


def _state_trade_evidence(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    trades = [row for row in _l(portfolio.get("trades")) if isinstance(row, dict)]
    entry_indexes = [i for i, row in enumerate(trades) if str(row.get("execution_id") or "") == ENTRY_EXECUTION_ID]
    bad_indexes = [i for i, row in enumerate(trades) if str(row.get("execution_id") or "") == BAD_EXECUTION_ID]
    entry_row = trades[entry_indexes[0]] if len(entry_indexes) == 1 else {}
    bad_row = trades[bad_indexes[0]] if len(bad_indexes) == 1 else {}
    rows_after_bad = trades[bad_indexes[0] + 1 :] if len(bad_indexes) == 1 else []
    return {
        "trade_row_count": len(trades),
        "entry_execution_match_count": len(entry_indexes),
        "bad_execution_match_count": len(bad_indexes),
        "entry_signature_exact": bool(entry_row and _entry_signature(entry_row)),
        "bad_signature_exact": bool(bad_row and _bad_signature(bad_row)),
        "entry_row": _row_view(entry_row) if entry_row else None,
        "bad_row": _row_view(bad_row) if bad_row else None,
        "bad_trade_index": bad_indexes[0] if len(bad_indexes) == 1 else None,
        "state_trade_rows_after_bad": len(rows_after_bad),
        "state_execution_ids_after_bad": [str(row.get("execution_id") or "") for row in rows_after_bad[:20]],
    }


def _ledger_evidence() -> Dict[str, Any]:
    try:
        import canonical_execution_ledger as ledger

        read_rows = getattr(ledger, "_read_rows", None)
        verify_rows = getattr(ledger, "_verify_rows", None)
        if not callable(read_rows) or not callable(verify_rows):
            return {
                "status": "error",
                "reason": "canonical_ledger_read_or_verify_helper_missing",
                "chain_valid": False,
            }
        rows, parse_errors = read_rows()
        chain_valid, chain_errors = verify_rows(rows)
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"{type(exc).__name__}: {exc}",
            "chain_valid": False,
        }

    entry_indexes = [i for i, row in enumerate(rows) if str(row.get("execution_id") or "") == ENTRY_EXECUTION_ID]
    bad_indexes = [i for i, row in enumerate(rows) if str(row.get("execution_id") or "") == BAD_EXECUTION_ID]
    entry_row = rows[entry_indexes[0]] if len(entry_indexes) == 1 else {}
    bad_row = rows[bad_indexes[0]] if len(bad_indexes) == 1 else {}
    rows_after_bad = rows[bad_indexes[0] + 1 :] if len(bad_indexes) == 1 else []
    return {
        "status": "ok" if not parse_errors and chain_valid else "warn",
        "ledger_file": str(getattr(ledger, "LEDGER_FILE", "") or ""),
        "row_count": len(rows),
        "parse_error_count": len(parse_errors),
        "chain_error_count": len(chain_errors),
        "chain_valid": bool(chain_valid and not parse_errors),
        "errors": list(parse_errors + chain_errors)[:10],
        "entry_execution_match_count": len(entry_indexes),
        "bad_execution_match_count": len(bad_indexes),
        "entry_signature_exact": bool(entry_row and _entry_signature(entry_row)),
        "bad_signature_exact": bool(bad_row and _bad_signature(bad_row)),
        "entry_row": _row_view(entry_row) if entry_row else None,
        "bad_row": _row_view(bad_row) if bad_row else None,
        "bad_ledger_index": bad_indexes[0] if len(bad_indexes) == 1 else None,
        "canonical_rows_after_bad": len(rows_after_bad),
        "canonical_execution_ids_after_bad": [str(row.get("execution_id") or "") for row in rows_after_bad[:20]],
        "bad_is_last_canonical_execution": bool(len(bad_indexes) == 1 and bad_indexes[0] == len(rows) - 1),
        "all_rows_same_target_epoch": bool(rows) and all(str(row.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID for row in rows),
    }


def _realized_values(portfolio: Dict[str, Any]) -> Tuple[float | None, float | None, str]:
    realized = _d(portfolio.get("realized_pnl"))
    performance = _d(portfolio.get("performance"))
    today = _f(realized.get("today", realized.get("realized_today")))
    total = _f(realized.get("total", realized.get("realized_total")))
    source = "realized_pnl"
    if today is None:
        today = _f(performance.get("realized_pnl_today"))
        source = "performance"
    if total is None:
        total = _f(performance.get("realized_pnl_total"))
        source = "performance" if source != "realized_pnl" else "mixed"
    return today, total, source


def _counterfactual(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    positions = _d(portfolio.get("positions"))
    position = _d(positions.get(SYMBOL))
    cash = _f(portfolio.get("cash"))
    equity = _f(portfolio.get("equity"))
    current_qty = _f(position.get("shares", position.get("qty")))
    current_mark = _f(position.get("last_price", position.get("entry")))
    current_entry = _f(position.get("entry", position.get("entry_price")))
    realized_today, realized_total, realized_source = _realized_values(portfolio)

    bad_proceeds = BAD_SHARES * BAD_PRICE
    bad_realized = (BAD_PRICE - ENTRY_PRICE) * BAD_SHARES
    restored_qty = (current_qty + BAD_SHARES) if current_qty is not None else None
    corrected_cash = (cash - bad_proceeds) if cash is not None else None
    corrected_today = (realized_today - bad_realized) if realized_today is not None else None
    corrected_total = (realized_total - bad_realized) if realized_total is not None else None
    corrected_equity = None
    restored_market_value = None
    restored_unrealized_delta = None
    if equity is not None and current_mark is not None:
        corrected_equity = equity - bad_proceeds + (BAD_SHARES * current_mark)
    if restored_qty is not None and current_mark is not None:
        restored_market_value = restored_qty * current_mark
    if current_mark is not None:
        restored_unrealized_delta = (current_mark - ENTRY_PRICE) * BAD_SHARES

    quantity_reconciles = bool(
        restored_qty is not None and abs(restored_qty - ENTRY_SHARES) <= QUANTITY_TOLERANCE
    )
    position_entry_matches = bool(current_entry is not None and abs(current_entry - ENTRY_PRICE) <= 1e-6)

    return {
        "current_observed": {
            "cash": cash,
            "equity": equity,
            "sls_shares": current_qty,
            "sls_entry": current_entry,
            "sls_last_price": current_mark,
            "sls_peak": _f(position.get("peak")),
            "realized_today": realized_today,
            "realized_total": realized_total,
            "realized_source": realized_source,
        },
        "exact_bad_execution_economics": {
            "shares": BAD_SHARES,
            "price": BAD_PRICE,
            "cash_proceeds": round(bad_proceeds, 9),
            "realized_pnl": round(bad_realized, 9),
            "entry_price": ENTRY_PRICE,
        },
        "counterfactual_if_exact_bad_partial_exit_is_reversed": {
            "cash": round(corrected_cash, 9) if corrected_cash is not None else None,
            "sls_shares": round(restored_qty, 9) if restored_qty is not None else None,
            "equity_using_current_stored_sls_mark": round(corrected_equity, 9) if corrected_equity is not None else None,
            "sls_market_value_using_current_stored_mark": round(restored_market_value, 9) if restored_market_value is not None else None,
            "restored_unrealized_pnl_delta_using_current_stored_mark": round(restored_unrealized_delta, 9) if restored_unrealized_delta is not None else None,
            "realized_today": round(corrected_today, 9) if corrected_today is not None else None,
            "realized_total": round(corrected_total, 9) if corrected_total is not None else None,
        },
        "position_consistency": {
            "position_exists": bool(position),
            "entry_price_matches_original_entry": position_entry_matches,
            "current_plus_bad_exit_qty_matches_original_entry_qty": quantity_reconciles,
            "expected_original_entry_qty": ENTRY_SHARES,
            "computed_restored_qty": restored_qty,
            "quantity_tolerance": QUANTITY_TOLERANCE,
        },
        "not_proven_or_not_rewritten": {
            "replacement_execution_price": None,
            "position_peak": None,
            "day_peak_equity": None,
            "halt_state": None,
            "reason": "counterfactual reverses only the proven invalid economic mutation; peak/risk correction remains a separate evidence boundary",
        },
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    portfolio = _d(getattr(core, "portfolio", None)) if core is not None else {}
    epoch_id = _epoch_id(portfolio)
    state = _state_trade_evidence(portfolio)
    ledger = _ledger_evidence()
    counterfactual = _counterfactual(portfolio)
    consistency = _d(counterfactual.get("position_consistency"))

    independent_invalidity = bool(
        INDEPENDENT_MARKET_EVIDENCE["split_corporate_actions_found"] == 0
        and BAD_PRICE > 2.5 * ENTRY_PRICE
        and BAD_PRICE > 10.0 * float(INDEPENDENT_MARKET_EVIDENCE["observed_ask_range"][1])
    )
    exact_execution_proven = bool(
        epoch_id == TARGET_EPOCH_ID
        and state.get("entry_signature_exact")
        and state.get("bad_signature_exact")
        and ledger.get("chain_valid")
        and ledger.get("entry_signature_exact")
        and ledger.get("bad_signature_exact")
        and independent_invalidity
        and consistency.get("position_exists")
        and consistency.get("entry_price_matches_original_entry")
        and consistency.get("current_plus_bad_exit_qty_matches_original_entry_qty")
    )
    no_later_canonical_execution = bool(
        exact_execution_proven and ledger.get("canonical_rows_after_bad") == 0
    )

    if no_later_canonical_execution:
        diagnosis = "exact_invalid_terminal_sls_execution_counterfactual_proven"
        overall = "pass"
    elif exact_execution_proven:
        diagnosis = "exact_invalid_sls_execution_proven_but_successor_replay_required"
        overall = "warn"
    else:
        diagnosis = "sls_bad_execution_counterfactual_not_fully_proven"
        overall = "warn"

    return {
        "status": "ok",
        "overall": overall,
        "type": "sls_bad_execution_recovery_proof",
        "version": VERSION,
        "generated_local": _now(core),
        "diagnosis": diagnosis,
        "active_epoch_id": epoch_id or None,
        "target_epoch_id": TARGET_EPOCH_ID,
        "exact_execution_proven": exact_execution_proven,
        "no_later_canonical_execution": no_later_canonical_execution,
        "state_trade_evidence": state,
        "canonical_ledger_evidence": ledger,
        "independent_market_evidence": dict(INDEPENDENT_MARKET_EVIDENCE),
        "economic_counterfactual": counterfactual,
        "recovery_readiness": {
            "counterfactual_arithmetic_mechanically_reproducible": exact_execution_proven,
            "terminal_reversal_sufficient_without_successor_replay": no_later_canonical_execution,
            "immutable_bad_execution_must_remain_in_ledger": True,
            "historical_execution_edit_required": False,
            "risk_peak_repair_authorized_by_this_probe": False,
            "halt_clear_authorized_by_this_probe": False,
            "state_write_authorized_by_this_probe": False,
            "next_step": (
                "if terminal reversal is proven, compare the counterfactual against independent account/valuation evidence before designing any successor-state migration"
                if no_later_canonical_execution
                else "replay all canonical executions after the bad row before considering any successor-state migration"
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
            "rewrites_or_relabels_canonical_ledger": False,
            "deletes_execution_rows": False,
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
        "startup_calls_market_data_providers": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "flask_app_missing"}
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify

        try:
            existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        except Exception:
            existing = set()
        if ROUTE not in existing:
            flask_app.add_url_rule(
                ROUTE,
                "sls_bad_execution_recovery_proof",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(app_id)
    return {"status": "ok", "overall": "pass", "version": VERSION, "route": ROUTE}
