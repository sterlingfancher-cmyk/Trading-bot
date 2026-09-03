"""Exact Issue #172 recovery for canonical exits missing from portfolio state.

The canonical ledger is the write-ahead source of truth.  This one-time paper
recovery accepts only the demonstrated v4 shape: two exact terminal exits are
present in the valid ledger, absent from state.trades, and their matching short
positions remain open in state under the exact lifecycle-integrity halt.  It
archives the pre-repair state and ledger, applies only those two exits, preserves
the halt/risk/history/epoch records, and never edits canonical history.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import shutil
import threading
from typing import Any, Dict, List, Tuple

import verified_v3_successor_epoch_migration as v3

VERSION = "v4-canonical-state-reconciliation-2026-09-03-v1-issue172"
EPOCH_ID = "stable-paper-v4-20260826-successor01"
HALT_REASON = "canonical execution lifecycle integrity halt"
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
MARKER_FILE = os.path.join(STATE_DIR, "issue172_v4_canonical_state_reconciliation.json")
EXPECTED_MISSING = {
    "30c048c400aa44a68a2748609f8b807f": {
        "event_hash": "936aec884007c268c6223bd94d0b226a462aa7f89bc92f05d83edecddeaa6314",
        "symbol": "MU", "side": "short", "action": "exit", "price": 944.375, "shares": 1.079923684,
    },
    "f318d4513c5f4f119cfaa577d5f685a9": {
        "event_hash": "b1fd75f23d2d8327eebaf9d640bae9202c117a51f9b0de2f50d70fb77da56ad4",
        "symbol": "STX", "side": "short", "action": "exit", "price": 789.848572, "shares": 1.290454899,
    },
}
_LOCK = threading.RLock()
_REGISTERED_APP_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}


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


def _read_marker() -> Dict[str, Any]:
    try:
        with open(MARKER_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _atomic_json(path: str, payload: Dict[str, Any]) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"), default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _close(left: Any, right: Any, tolerance: float) -> bool:
    return abs(_f(left) - _f(right)) <= tolerance


def _exact_missing_rows(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    found: Dict[str, Dict[str, Any]] = {}
    issues: List[str] = []
    for row in rows:
        execution_id = str(row.get("execution_id") or "")
        expected = EXPECTED_MISSING.get(execution_id)
        if expected is None:
            continue
        checks = (
            str(row.get("accounting_epoch_id") or "") == EPOCH_ID,
            str(row.get("event_hash") or "") == expected["event_hash"],
            str(row.get("symbol") or "").upper() == expected["symbol"],
            str(row.get("side") or "").lower() == expected["side"],
            str(row.get("action") or "").lower() == expected["action"],
            _close(row.get("price"), expected["price"], 5e-7),
            _close(row.get("shares"), expected["shares"], 5e-10),
        )
        if not all(checks):
            issues.append(f"missing_exit_signature_mismatch:{execution_id}")
        elif execution_id in found:
            issues.append(f"duplicate_missing_exit:{execution_id}")
        else:
            found[execution_id] = row
    if set(found) != set(EXPECTED_MISSING):
        issues.append("exact_missing_exit_set_not_present")
    return found, issues


def _preflight(core: Any) -> Dict[str, Any]:
    pf = v3._portfolio(core)
    issues: List[str] = []
    if v3._epoch_id(pf) != EPOCH_ID:
        issues.append("active_epoch_not_exact_v4")
    risk = _d(pf.get("risk_controls"))
    if not bool(risk.get("halted")) or str(risk.get("halt_reason") or "") != HALT_REASON:
        issues.append("exact_lifecycle_halt_not_active")

    try:
        import canonical_execution_ledger as ledger
        with ledger._LOCK:
            rows, parse_errors = ledger._read_rows()
            chain_valid, chain_errors = ledger._verify_rows(rows)
    except Exception as exc:
        return {"status": "fail", "issues": [f"ledger_read_error:{type(exc).__name__}:{exc}"]}
    if parse_errors or not chain_valid:
        issues.append("canonical_ledger_not_valid")
    execution_ids = [str(row.get("execution_id") or "") for row in rows]
    if not all(execution_ids) or len(execution_ids) != len(set(execution_ids)):
        issues.append("canonical_execution_ids_not_unique")

    v4_rows = [row for row in rows if str(row.get("accounting_epoch_id") or "") == EPOCH_ID]
    state_rows = [row for row in _l(pf.get("trades")) if isinstance(row, dict)]
    state_by_id = {str(row.get("execution_id") or ""): row for row in state_rows if str(row.get("execution_id") or "")}
    v4_by_id = {str(row.get("execution_id") or ""): row for row in v4_rows}
    missing_ids = set(v4_by_id) - set(state_by_id)
    state_only_ids = set(state_by_id) - set(v4_by_id)
    if missing_ids != set(EXPECTED_MISSING):
        issues.append("state_missing_execution_set_not_exact")
    if state_only_ids:
        issues.append("state_contains_noncanonical_execution")
    for execution_id, state_row in state_by_id.items():
        canonical = v4_by_id.get(execution_id)
        if canonical is None or str(state_row.get("canonical_ledger_event_hash") or "") != str(canonical.get("event_hash") or ""):
            issues.append(f"state_canonical_binding_mismatch:{execution_id}")

    missing_rows, signature_issues = _exact_missing_rows(v4_rows)
    issues.extend(signature_issues)
    positions = _d(pf.get("positions"))
    if set(positions) != {"MU", "STX"}:
        issues.append("stale_position_set_not_exact")
    for expected in EXPECTED_MISSING.values():
        position = _d(positions.get(expected["symbol"]))
        if str(position.get("side") or "").lower() != "short":
            issues.append(f"stale_position_side_mismatch:{expected['symbol']}")
        if not _close(position.get("shares", position.get("qty")), expected["shares"], 5e-6):
            issues.append(f"stale_position_quantity_mismatch:{expected['symbol']}")

    try:
        import paper_bidirectional_accounting_guard as accounting
        rebuilt = accounting.analyze_ledger(pf, core)
    except Exception as exc:
        rebuilt = {"coverage_complete": False, "error": f"{type(exc).__name__}:{exc}"}
    if not bool(rebuilt.get("coverage_complete")) or int(rebuilt.get("coverage_issue_count") or 0) or int(rebuilt.get("economic_issue_count") or 0):
        issues.append("pre_repair_state_accounting_not_clean")

    return {
        "status": "ok" if not issues else "fail",
        "issues": issues,
        "rows": rows,
        "v4_rows": v4_rows,
        "state_rows": state_rows,
        "state_by_id": state_by_id,
        "missing_rows": missing_rows,
        "ledger_file": str(getattr(ledger, "LEDGER_FILE", "")),
        "rebuilt_before": rebuilt,
    }


def _mirror_row(row: Dict[str, Any]) -> Dict[str, Any]:
    mirror = {
        "time": str(row.get("recorded_local") or ""),
        "action": str(row.get("action") or ""),
        "symbol": str(row.get("symbol") or ""),
        "side": str(row.get("side") or ""),
        "price": round(_f(row.get("price")), 4),
        "shares": round(_f(row.get("shares")), 6),
        "execution_id": str(row.get("execution_id") or ""),
        "accounting_epoch_id": str(row.get("accounting_epoch_id") or ""),
        "canonical_ledger_event_hash": str(row.get("event_hash") or ""),
        "canonical_ledger_version": str(row.get("ledger_version") or ""),
    }
    excluded = {
        "execution_id", "ledger_version", "recorded_local", "accounting_epoch_id",
        "action", "symbol", "side", "price", "shares", "previous_event_hash", "event_hash",
    }
    for key, value in row.items():
        if key not in excluded:
            mirror[key] = copy.deepcopy(value)
    return mirror


def _archive(core: Any, pf: Dict[str, Any], ledger_file: str) -> Dict[str, Any]:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(STATE_DIR, "forensic_archives", f"{stamp}_issue172_canonical_state_divergence")
    os.makedirs(folder, exist_ok=False)
    state_path = os.path.join(folder, "state_before.json")
    _atomic_json(state_path, pf)
    ledger_copy = None
    if ledger_file and os.path.exists(ledger_file):
        ledger_copy = os.path.join(folder, "canonical_execution_ledger_immutable_copy.jsonl")
        shutil.copy2(ledger_file, ledger_copy)
    return {"archive_dir": folder, "state_file": state_path, "ledger_copy": ledger_copy}


def _repair(core: Any, preflight: Dict[str, Any]) -> Dict[str, Any]:
    pf = v3._portfolio(core)
    successor = copy.deepcopy(pf)
    state_by_id = _d(preflight.get("state_by_id"))
    ordered_trades: List[Dict[str, Any]] = []
    realized_delta = 0.0
    cash_delta = 0.0
    for row in _l(preflight.get("v4_rows")):
        execution_id = str(row.get("execution_id") or "")
        if execution_id in state_by_id:
            ordered_trades.append(copy.deepcopy(state_by_id[execution_id]))
            continue
        expected = EXPECTED_MISSING[execution_id]
        position = _d(_d(pf.get("positions")).get(expected["symbol"]))
        entry = _f(position.get("entry", position.get("entry_price")))
        qty = _f(row.get("shares"))
        exit_price = _f(row.get("price"))
        pnl = (entry - exit_price) * qty
        realized_delta += pnl
        cash_delta += (entry * qty) + pnl
        ordered_trades.append(_mirror_row(row))

    successor["trades"] = ordered_trades[-500:]
    successor["cash"] = _f(pf.get("cash")) + cash_delta
    successor["equity"] = successor["cash"]
    successor["positions"] = {}
    realized = _d(successor.setdefault("realized_pnl", {}))
    realized["today"] = round(_f(realized.get("today")) + realized_delta, 2)
    realized["total"] = round(_f(realized.get("total")) + realized_delta, 2)
    successor["realized_pnl"] = realized
    performance = _d(successor.setdefault("performance", {}))
    performance["open_positions"] = {}
    performance["unrealized_pnl"] = 0.0
    performance["realized_pnl_today"] = realized["today"]
    performance["realized_pnl_total"] = realized["total"]
    successor["performance"] = performance
    # Preserve the exact active halt and every risk/day-peak field.  Release is
    # a separate governed decision after settled post-deploy validation.
    successor["risk_controls"] = copy.deepcopy(_d(pf.get("risk_controls")))
    successor["issue172_reconciliation"] = {
        "version": VERSION,
        "status": "reconciled_halt_preserved",
        "completed_local": _now(core),
        "execution_ids": sorted(EXPECTED_MISSING),
        "realized_delta": round(realized_delta, 6),
        "cash_delta": round(cash_delta, 6),
        "canonical_history_rewritten": False,
        "risk_halt_cleared": False,
    }

    try:
        import paper_bidirectional_accounting_guard as accounting
        rebuilt_after = accounting.analyze_ledger(successor, core)
    except Exception as exc:
        raise RuntimeError(f"post-repair accounting unavailable:{type(exc).__name__}:{exc}") from exc
    if not bool(rebuilt_after.get("coverage_complete")) or int(rebuilt_after.get("coverage_issue_count") or 0) or int(rebuilt_after.get("economic_issue_count") or 0):
        raise RuntimeError("post-repair accounting projection is not complete")
    if _d(rebuilt_after.get("open_positions")):
        raise RuntimeError("post-repair canonical projection is not flat")
    if not _close(successor.get("cash"), rebuilt_after.get("cash"), 0.05):
        raise RuntimeError("post-repair cash does not match deterministic accounting")

    archive = _archive(core, copy.deepcopy(pf), str(preflight.get("ledger_file") or ""))
    marker = {
        "status": "repair_started", "overall": "warn", "version": VERSION,
        "started_local": _now(core), "archive": archive,
        "execution_ids": sorted(EXPECTED_MISSING),
    }
    _atomic_json(MARKER_FILE, marker)
    save = getattr(core, "save_state", None)
    if not callable(save):
        raise RuntimeError("core.save_state unavailable")
    try:
        save(successor)
    except TypeError:
        save()
    pf.clear()
    pf.update(successor)
    marker.update({
        "status": "completed", "overall": "pass", "completed_local": _now(core),
        "canonical_history_rewritten": False, "risk_halt_cleared": False,
        "cash": successor.get("cash"), "equity": successor.get("equity"),
        "positions": [], "state_trade_rows": len(ordered_trades),
        "rebuilt_after": rebuilt_after,
    })
    _atomic_json(MARKER_FILE, marker)
    return marker


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    with _LOCK:
        marker = _read_marker()
        if marker.get("status") == "completed":
            _LAST = marker
            return dict(marker)
        if marker.get("status") == "repair_started":
            result = {
                "status": "fail", "overall": "fail", "version": VERSION,
                "reason": "interrupted_reconciliation_requires_inspection",
                "marker": marker, "canonical_history_rewritten": False,
                "risk_halt_cleared": False,
            }
            _LAST = result
            return result
        if not v3._paper_only():
            result = {
                "status": "blocked", "overall": "fail", "version": VERSION,
                "reason": "paper_runtime_required", "canonical_history_rewritten": False,
                "risk_halt_cleared": False,
            }
            _LAST = result
            return result
        preflight = _preflight(core)
        if preflight.get("status") != "ok":
            result = {
                "status": "not_applicable", "overall": "pass", "version": VERSION,
                "reason": "exact_issue172_shape_not_present", "preflight_issues": preflight.get("issues", []),
                "canonical_history_rewritten": False, "risk_halt_cleared": False,
            }
            _LAST = result
            return result
        try:
            result = _repair(core, preflight)
        except Exception as exc:
            result = {
                "status": "fail", "overall": "fail", "version": VERSION,
                "error": f"{type(exc).__name__}: {exc}", "canonical_history_rewritten": False,
                "risk_halt_cleared": False,
            }
        _LAST = result
        return dict(result)


def status_payload(core: Any = None) -> Dict[str, Any]:
    marker = _read_marker()
    payload = marker or _LAST
    if payload:
        return dict(payload)
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION}
    preflight = _preflight(core)
    return {
        "status": "ready" if preflight.get("status") == "ok" else "not_applicable",
        "overall": "warn" if preflight.get("status") == "ok" else "pass",
        "version": VERSION, "preflight_issues": preflight.get("issues", []),
        "canonical_history_rewritten": False, "risk_halt_cleared": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is not None and id(flask_app) not in _REGISTERED_APP_IDS:
        from flask import jsonify
        path = "/paper/v4-canonical-state-reconciliation-status"
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if path not in existing:
            flask_app.add_url_rule(path, "v4_canonical_state_reconciliation_status", lambda: jsonify(status_payload(core)))
        _REGISTERED_APP_IDS.add(id(flask_app))
    return status_payload(core)
