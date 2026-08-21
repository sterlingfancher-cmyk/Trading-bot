"""Read-only provenance for the immutable TEM duplicate-exit signature.

Issue #82's verified-v2 successor replay intentionally fails closed unless the
known duplicate TEM execution matches its exact historical signature. Production
reported that the execution id exists exactly once but one signature field does
not match the replay expectation. This module only exposes the observed immutable
row and field-by-field comparison so the discrepancy can be identified without
loosening a signature or mutating any state/ledger data.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List

VERSION = "verified-v2-successor-replay-tem-provenance-2026-08-21-v1"
ROUTE = "/paper/verified-v2-successor-replay-tem-provenance"
TARGET_EPOCH_ID = "stable-paper-v2-20260812-verified01"
TEM_EXECUTION_ID = "3530dbf965db4894ba93b7098cec3696"
EXPECTED_SYMBOL = "TEM"
EXPECTED_ACTION = "exit"
EXPECTED_SIDE = "long"
EXPECTED_PRICE = 52.905
EXPECTED_SHARES = 29.640567
PRICE_TOLERANCE = 1e-6
SHARE_TOLERANCE = 5e-6
_REGISTERED_TEM_PROVENANCE_APP_IDS: set[int] = set()


def _temprov_number(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _temprov_now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _temprov_row_view(row: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    return {
        "execution_id": row.get("execution_id"),
        "accounting_epoch_id": row.get("accounting_epoch_id"),
        "recorded_local": row.get("recorded_local"),
        "time": row.get("time"),
        "action": row.get("action"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "price": _temprov_number(row.get("price")),
        "shares": _temprov_number(row.get("shares", row.get("qty"))),
        "raw_price": row.get("price"),
        "raw_shares": row.get("shares", row.get("qty")),
        "exit_reason": row.get("exit_reason"),
        "event_hash": row.get("event_hash"),
        "available_keys": sorted(str(key) for key in row.keys()),
    }


def _temprov_field_checks(row: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    observed_price = _temprov_number(row.get("price"))
    observed_shares = _temprov_number(row.get("shares", row.get("qty")))
    observed_epoch = str(row.get("accounting_epoch_id") or "")
    observed_symbol = str(row.get("symbol") or "").upper()
    observed_action = str(row.get("action") or "").lower()
    observed_side = str(row.get("side") or "long").lower()
    observed_execution = str(row.get("execution_id") or "")

    return {
        "execution_id": {
            "observed": observed_execution,
            "expected": TEM_EXECUTION_ID,
            "matches": observed_execution == TEM_EXECUTION_ID,
        },
        "accounting_epoch_id": {
            "observed": observed_epoch,
            "expected": TARGET_EPOCH_ID,
            "matches": observed_epoch == TARGET_EPOCH_ID,
        },
        "symbol": {
            "observed": observed_symbol,
            "expected": EXPECTED_SYMBOL,
            "matches": observed_symbol == EXPECTED_SYMBOL,
        },
        "action": {
            "observed": observed_action,
            "expected": EXPECTED_ACTION,
            "matches": observed_action == EXPECTED_ACTION,
        },
        "side": {
            "observed": observed_side,
            "expected": EXPECTED_SIDE,
            "matches": observed_side == EXPECTED_SIDE,
        },
        "price": {
            "observed": observed_price,
            "expected": EXPECTED_PRICE,
            "tolerance": PRICE_TOLERANCE,
            "absolute_delta": (
                abs(observed_price - EXPECTED_PRICE) if observed_price is not None else None
            ),
            "matches": bool(
                observed_price is not None
                and abs(observed_price - EXPECTED_PRICE) <= PRICE_TOLERANCE
            ),
        },
        "shares": {
            "observed": observed_shares,
            "expected": EXPECTED_SHARES,
            "tolerance": SHARE_TOLERANCE,
            "absolute_delta": (
                abs(observed_shares - EXPECTED_SHARES) if observed_shares is not None else None
            ),
            "matches": bool(
                observed_shares is not None
                and abs(observed_shares - EXPECTED_SHARES) <= SHARE_TOLERANCE
            ),
        },
    }


def tem_duplicate_provenance_payload(core: Any = None) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    parse_errors: List[str] = []
    chain_errors: List[str] = []
    chain_valid = False
    ledger_file = ""
    read_error = None
    try:
        import canonical_execution_ledger as ledger

        ledger_file = str(getattr(ledger, "LEDGER_FILE", "") or "")
        read_rows = getattr(ledger, "_read_rows", None)
        verify_rows = getattr(ledger, "_verify_rows", None)
        if not callable(read_rows) or not callable(verify_rows):
            read_error = "canonical_ledger_read_or_verify_helper_missing"
        else:
            rows, parse_errors = read_rows()
            chain_valid, chain_errors = verify_rows(rows)
    except Exception as exc:
        read_error = f"{type(exc).__name__}: {exc}"

    matches = [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("execution_id") or "") == TEM_EXECUTION_ID
    ]
    row = matches[0] if len(matches) == 1 else None
    checks = _temprov_field_checks(row) if isinstance(row, dict) else {}
    failed_checks = [name for name, detail in checks.items() if not bool(detail.get("matches"))]
    exact = bool(checks) and not failed_checks

    if read_error or parse_errors or chain_errors or not chain_valid:
        diagnosis = "canonical_ledger_not_ready_for_tem_signature_provenance"
        overall = "fail"
    elif len(matches) != 1:
        diagnosis = "tem_execution_id_not_unique_in_canonical_ledger"
        overall = "fail"
    elif exact:
        diagnosis = "tem_duplicate_signature_exact_under_successor_replay_expectation"
        overall = "pass"
    else:
        diagnosis = "tem_duplicate_signature_field_mismatch_identified"
        overall = "warn"

    return {
        "status": "ok",
        "overall": overall,
        "type": "verified_v2_successor_replay_tem_provenance",
        "version": VERSION,
        "generated_local": _temprov_now(core),
        "diagnosis": diagnosis,
        "ledger": {
            "file": ledger_file,
            "row_count": len(rows),
            "chain_valid": bool(chain_valid and not parse_errors and not chain_errors),
            "parse_errors": list(parse_errors)[:10],
            "chain_errors": list(chain_errors)[:10],
            "read_error": read_error,
        },
        "match_count": len(matches),
        "observed_row": _temprov_row_view(row),
        "expected_signature": {
            "execution_id": TEM_EXECUTION_ID,
            "accounting_epoch_id": TARGET_EPOCH_ID,
            "symbol": EXPECTED_SYMBOL,
            "action": EXPECTED_ACTION,
            "side": EXPECTED_SIDE,
            "price": EXPECTED_PRICE,
            "shares": EXPECTED_SHARES,
        },
        "field_checks": checks,
        "failed_checks": failed_checks,
        "signature_exact": exact,
        "interpretation": {
            "does_not_loosen_successor_replay_signature": True,
            "does_not_change_known_invalid_disposition": True,
            "next_step": (
                "if a field mismatch is historical-semantics-only, verify its durable provenance before changing the replay expectation; otherwise stop and investigate the contradiction"
                if not exact
                else "the TEM signature expectation is confirmed; investigate why the parent replay reported false before changing recovery logic"
            ),
        },
        "authority": {
            "reporting_only": True,
            "reads_canonical_ledger": True,
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


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {
            "status": "pending",
            "overall": "warn",
            "version": VERSION,
            "reason": "flask_app_missing",
        }
    app_id = id(flask_app)
    if app_id not in _REGISTERED_TEM_PROVENANCE_APP_IDS:
        from flask import jsonify

        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if ROUTE not in existing:
            flask_app.add_url_rule(
                ROUTE,
                "verified_v2_successor_replay_tem_provenance",
                lambda: jsonify(tem_duplicate_provenance_payload(core)),
            )
        _REGISTERED_TEM_PROVENANCE_APP_IDS.add(app_id)
    return {"status": "ok", "overall": "pass", "version": VERSION, "route": ROUTE}
