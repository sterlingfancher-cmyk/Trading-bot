"""One-shot Issue #82 verified-v2 successor accounting epoch migration.

This migration is deliberately accounting-only and paper-only. It archives the
entire verified-v2 persistent state, requires the existing consolidated recovery
gate to prove all eleven exact historical dispositions, requires the active
bidirectional accounting result to have only the already-proven immutable TEM
duplicate issue, and then starts a successor accounting epoch from the *current
verified state snapshot*.

Current cash, equity, positions, marks, realized statistics, history, and risk
controls are preserved exactly. Only the active accounting window is rolled
forward: state.trades and the mirrored journal are reset for the successor epoch,
while the append-only canonical execution ledger is never edited, truncated,
rotated, relabelled, or deleted. Future canonical rows naturally receive the new
accounting epoch id through the existing ledger hook.

The successor remains under validation hold. This module does not clear a halt,
rewrite day_start/day_peak, fabricate fills, place orders, or change strategy,
signals, sizing, hard-risk thresholds, live authority, or ML authority.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import os
import shutil
import threading
from typing import Any, Dict, List, Tuple

VERSION = "verified-v2-successor-epoch-migration-2026-08-25-v1"
OLD_EPOCH_ID = "stable-paper-v2-20260812-verified01"
TARGET_EPOCH_ID = "stable-paper-v3-20260825-successor01"
DECISION_ID = "issue-82-verified-v2-historical-disposition-2026-08-25"
TEM_DUPLICATE_EXECUTION_ID = "3530dbf965db4894ba93b7098cec3696"
TEM_DUPLICATE_QTY = 29.640567
TEM_DUPLICATE_PRICE = 52.905
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
ARCHIVE_ROOT = os.path.join(STATE_DIR, "forensic_archives")
MARKER_FILE = os.path.join(STATE_DIR, f"successor_epoch_{DECISION_ID}.json")
_LOCK = threading.RLock()
_REGISTERED_APP_IDS: set[int] = set()
_LAST_STATUS: Dict[str, Any] = {}


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


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper_only() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _atomic_json(path: str, payload: Dict[str, Any]) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _sha256(path: str) -> str | None:
    if not path or not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _marker() -> Dict[str, Any]:
    try:
        with open(MARKER_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _realized_snapshot(pf: Dict[str, Any]) -> Tuple[float, float]:
    realized = _d(pf.get("realized_pnl"))
    perf = _d(pf.get("performance"))
    today = _f(realized.get("today", realized.get("realized_today")))
    total = _f(realized.get("total"))
    if today is None:
        today = _f(perf.get("realized_pnl_today"))
    if total is None:
        total = _f(perf.get("realized_pnl_total"))
    return float(today or 0.0), float(total or 0.0)


def _verified_positions(pf: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for raw_symbol, raw_position in _d(pf.get("positions")).items():
        pos = _d(raw_position)
        symbol = str(raw_symbol or pos.get("symbol") or "").upper().strip()
        side = str(pos.get("side") or "long").lower().strip()
        qty = _f(pos.get("shares", pos.get("qty")))
        entry = _f(pos.get("entry", pos.get("entry_price")))
        mark = _f(pos.get("last_price"))
        if not symbol or side not in {"long", "short"} or qty is None or qty <= 0 or entry is None or entry <= 0 or mark is None or mark <= 0:
            return {}
        out[symbol] = {
            "side": side,
            "qty": qty,
            "entry_price": entry,
            "mark": mark,
        }
    return out


def _gate_evidence(core: Any) -> Tuple[Dict[str, Any], bool]:
    try:
        import verified_v2_successor_replay_status as gate
        payload = gate.status_payload(core)
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}, False
    readiness = _d(payload.get("recovery_readiness"))
    ledger = _d(payload.get("ledger"))
    ok = bool(
        payload.get("overall") == "pass"
        and payload.get("all_known_invalid_signatures_exact") is True
        and int(payload.get("known_invalid_execution_count") or 0) == 11
        and bool(ledger.get("chain_valid"))
        and str(ledger.get("epoch_ids", [None])[0] if _l(ledger.get("epoch_ids")) else "") == OLD_EPOCH_ID
        and bool(readiness.get("counterfactual_successor_projection_mechanically_reproducible"))
        and bool(readiness.get("all_canonical_rows_accounted_for"))
        and bool(readiness.get("mechanically_complete_for_successor_migration_design"))
    )
    return payload, ok


def _tem_issue_exact(issue: Dict[str, Any]) -> bool:
    qty = _f(issue.get("requested_qty", issue.get("shares")))
    price = _f(issue.get("price"))
    return bool(
        str(issue.get("symbol") or "").upper() == "TEM"
        and str(issue.get("action") or "").lower() == "exit"
        and str(issue.get("reason") or "") == "exit_exceeds_reconstructed_position"
        and qty is not None and abs(qty - TEM_DUPLICATE_QTY) <= 5e-6
        and price is not None and abs(price - TEM_DUPLICATE_PRICE) <= 5e-6
    )


def _active_accounting_evidence(core: Any) -> Tuple[Dict[str, Any], bool]:
    pf = _portfolio(core)
    try:
        import paper_bidirectional_accounting_guard as accounting
        result = accounting.analyze_ledger(pf, core)
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}, False
    coverage = [row for row in _l(result.get("coverage_issues")) if isinstance(row, dict)]
    economics = [row for row in _l(result.get("economic_issues")) if isinstance(row, dict)]
    if len(coverage) != 1 or len(economics) != 1 or not _tem_issue_exact(coverage[0]) or not _tem_issue_exact(economics[0]):
        return result, False
    current_cash = _f(pf.get("cash")); current_equity = _f(pf.get("equity"))
    rebuilt_cash = _f(result.get("reconstructed_cash")); rebuilt_equity = _f(result.get("reconstructed_equity"))
    rebuilt_positions = sorted(str(v).upper() for v in _l(result.get("reconstructed_open_positions")))
    current_positions = sorted(str(v).upper() for v in _d(pf.get("positions")).keys())
    ok = bool(
        current_cash is not None and current_cash > 0
        and current_equity is not None and current_equity > 0
        and rebuilt_cash is not None and abs(rebuilt_cash - current_cash) <= 0.01
        and rebuilt_equity is not None and abs(rebuilt_equity - current_equity) <= 0.05
        and rebuilt_positions == current_positions
    )
    return result, ok


def _archive_state(core: Any, gate: Dict[str, Any], accounting: Dict[str, Any], ledger_path: str, ledger_digest: str | None) -> Dict[str, Any]:
    os.makedirs(ARCHIVE_ROOT, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = os.path.join(ARCHIVE_ROOT, f"{stamp}_{DECISION_ID}")
    os.makedirs(archive_dir, exist_ok=False)
    root_abs = os.path.abspath(ARCHIVE_ROOT)
    copied: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(STATE_DIR)):
        src = os.path.join(STATE_DIR, name)
        src_abs = os.path.abspath(src)
        if src_abs == root_abs or src_abs.startswith(root_abs + os.sep):
            continue
        dst = os.path.join(archive_dir, name)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
                copied.append({"name": name, "type": "directory"})
            elif os.path.isfile(src):
                shutil.copy2(src, dst)
                copied.append({"name": name, "type": "file", "size_bytes": os.path.getsize(dst), "sha256": _sha256(dst)})
        except Exception as exc:
            copied.append({"name": name, "type": "copy_error", "error": f"{type(exc).__name__}: {exc}"})
    pf = _portfolio(core)
    manifest = {
        "status": "ok",
        "type": "issue_82_verified_v2_successor_archive",
        "version": VERSION,
        "decision_id": DECISION_ID,
        "prior_epoch_id": OLD_EPOCH_ID,
        "target_epoch_id": TARGET_EPOCH_ID,
        "created_local": _now(core),
        "archive_dir": archive_dir,
        "canonical_ledger": {
            "path": ledger_path,
            "sha256_before_cutover": ledger_digest,
            "immutable_history_retained_in_place": True,
            "rotated_or_truncated": False,
            "row_count": _d(gate.get("ledger")).get("row_count"),
            "chain_valid": _d(gate.get("ledger")).get("chain_valid"),
        },
        "historical_disposition": {
            "known_invalid_execution_count": gate.get("known_invalid_execution_count"),
            "all_known_invalid_signatures_exact": gate.get("all_known_invalid_signatures_exact"),
            "known_invalid_execution_disposition": gate.get("known_invalid_execution_disposition"),
            "projection_complete": _d(gate.get("projection")).get("projection_complete"),
            "decision": "archive_verified_v2_history_and_roll_current_verified_state_into_successor_epoch_without_rewriting_historical_economics",
        },
        "active_accounting_before_cutover": {
            "coverage_issue_count": accounting.get("coverage_issue_count"),
            "economic_issue_count": accounting.get("economic_issue_count"),
            "coverage_issues": accounting.get("coverage_issues"),
            "reconstructed_cash": accounting.get("reconstructed_cash"),
            "reconstructed_equity": accounting.get("reconstructed_equity"),
            "reconstructed_open_positions": accounting.get("reconstructed_open_positions"),
        },
        "pre_cutover_account": {
            "cash": pf.get("cash"), "equity": pf.get("equity"),
            "positions": copy.deepcopy(_d(pf.get("positions"))),
            "trade_rows": len(_l(pf.get("trades"))),
            "risk_controls": copy.deepcopy(_d(pf.get("risk_controls"))),
        },
        "copied_entries": copied,
    }
    _atomic_json(os.path.join(archive_dir, "issue_82_successor_archive_manifest.json"), manifest)
    return manifest


def build_successor_state(pf: Dict[str, Any], archive_dir: str, started_local: str) -> Dict[str, Any]:
    state = copy.deepcopy(pf)
    cash = _f(state.get("cash")); equity = _f(state.get("equity"))
    positions = _verified_positions(state)
    if cash is None or cash <= 0 or equity is None or equity <= 0:
        raise RuntimeError("current account snapshot is not sane")
    if _d(state.get("positions")) and not positions:
        raise RuntimeError("current open-position snapshot is not fully verifiable")
    realized_today, realized_total = _realized_snapshot(state)
    snapshot = {
        "verified": True,
        "version": VERSION,
        "started_local": started_local,
        "cash": cash,
        "equity": equity,
        "realized_today": realized_today,
        "realized_total": realized_total,
        "positions": positions,
        "source": "current_verified_state_after_issue_82_forward_session_and_exact_historical_disposition",
    }
    state["trades"] = []
    state["accounting_epoch_id"] = TARGET_EPOCH_ID
    state["paper_accounting_epoch"] = {
        "version": VERSION,
        "id": TARGET_EPOCH_ID,
        "decision_id": DECISION_ID,
        "started_local": started_local,
        "starting_cash": cash,
        "starting_equity": equity,
        "clean_start": False,
        "zero_trade_baseline": not bool(positions),
        "baseline_type": "verified_snapshot_with_open_position" if positions else "verified_snapshot_zero_position",
        "verified_snapshot_baseline": snapshot,
        "historical_recovery_decision": "verified_v2_historical_disposition_successor_rollforward",
        "prior_epoch_id": OLD_EPOCH_ID,
        "prior_epoch_disposition": "archived_with_exact_eleven_row_historical_disposition_and_immutable_canonical_ledger_retained",
        "historical_evidence_archived": True,
        "forensic_archive_dir": archive_dir,
        "validation_hold": True,
        "validation_hold_reason": "issue 82 successor epoch clean-active-audit validation hold",
        "validation_release_status": "blocked",
        "validation_released": False,
        "forward_validation_required": True,
        "valid_path_rows_baseline": 0,
    }
    return state


def _rotate_journal_for_successor(state: Dict[str, Any]) -> None:
    try:
        import trade_journal as tj
    except Exception:
        return
    factory = getattr(tj, "_empty_journal", None)
    try:
        journal = factory() if callable(factory) else {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
    except Exception:
        journal = {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
    if not isinstance(journal, dict):
        journal = {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
    journal["accounting_epoch_id"] = TARGET_EPOCH_ID
    journal["successor_epoch_started_local"] = _now()
    for attr in ("TRADE_JOURNAL_FILE", "TRADE_JOURNAL_BACKUP_FILE"):
        path = str(getattr(tj, attr, "") or "")
        if path:
            _atomic_json(path, journal)


def _cutover(core: Any, gate: Dict[str, Any], accounting: Dict[str, Any]) -> Dict[str, Any]:
    global _LAST_STATUS
    import canonical_execution_ledger as ledger
    import clean_accounting_epoch as clean
    ledger_path = str(getattr(ledger, "LEDGER_FILE", "") or "")
    digest_before = _sha256(ledger_path)
    archive = _archive_state(core, gate, accounting, ledger_path, digest_before)
    started = _now(core)
    started_marker = {
        "status": "cutover_started", "version": VERSION, "decision_id": DECISION_ID,
        "prior_epoch_id": OLD_EPOCH_ID, "target_epoch_id": TARGET_EPOCH_ID,
        "archive_dir": archive.get("archive_dir"), "started_local": started,
        "canonical_ledger_sha256_before": digest_before,
    }
    _atomic_json(MARKER_FILE, started_marker)
    successor = build_successor_state(_portfolio(core), str(archive.get("archive_dir") or ""), started)
    with clean._runtime_locks():
        state_file = clean._write_clean_state_and_backups(core, successor)
        _rotate_journal_for_successor(successor)
        clean._reset_snapshot_archive(successor, state_file)
        pf = _portfolio(core)
        pf.clear(); pf.update(successor)
    digest_after = _sha256(ledger_path)
    if digest_before != digest_after:
        raise RuntimeError("canonical ledger changed during successor cutover")
    completed = dict(started_marker)
    completed.update({
        "status": "completed", "overall": "pass", "completed_local": _now(core),
        "state_file": state_file, "validation_hold": True,
        "canonical_ledger_sha256_after": digest_after,
        "canonical_ledger_unchanged": True,
        "successor_cash": successor.get("cash"), "successor_equity": successor.get("equity"),
        "successor_positions": sorted(_d(successor.get("positions")).keys()),
        "successor_trade_rows": len(_l(successor.get("trades"))),
        "current_risk_state_preserved": True,
    })
    _atomic_json(MARKER_FILE, completed)
    _LAST_STATUS = completed
    return completed


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST_STATUS
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not _paper_only():
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "paper_runtime_only"}
    with _LOCK:
        pf = _portfolio(core)
        epoch = _d(pf.get("paper_accounting_epoch"))
        active_epoch = str(epoch.get("id") or pf.get("accounting_epoch_id") or "")
        marker = _marker()
        if active_epoch == TARGET_EPOCH_ID:
            return {
                "status": "validation_hold", "overall": "pass", "version": VERSION,
                "epoch_id": TARGET_EPOCH_ID, "prior_epoch_id": OLD_EPOCH_ID,
                "historical_evidence_archived": bool(epoch.get("historical_evidence_archived")),
                "forensic_archive_dir": epoch.get("forensic_archive_dir") or marker.get("archive_dir"),
                "validation_hold": bool(epoch.get("validation_hold", False)),
                "canonical_ledger_unchanged": bool(marker.get("canonical_ledger_unchanged", False)),
            }
        if marker.get("status") == "completed" and active_epoch != TARGET_EPOCH_ID:
            return {"status": "error", "overall": "fail", "version": VERSION, "reason": "completed_marker_present_but_successor_epoch_not_active", "marker": marker}
        if active_epoch != OLD_EPOCH_ID:
            return {"status": "not_applicable", "overall": "pass", "version": VERSION, "reason": "verified_v2_epoch_not_active", "active_epoch_id": active_epoch}
        gate, gate_ready = _gate_evidence(core)
        accounting, accounting_ready = _active_accounting_evidence(core)
        positions = _verified_positions(pf)
        state_snapshot_ready = bool(_f(pf.get("cash")) and _f(pf.get("equity")) and (not _d(pf.get("positions")) or positions))
        if not gate_ready or not accounting_ready or not state_snapshot_ready:
            status = {
                "status": "blocked", "overall": "warn", "version": VERSION,
                "reason": "successor_epoch_preconditions_not_met",
                "preconditions": {"consolidated_recovery_gate_ready": gate_ready, "active_accounting_only_known_tem_issue": accounting_ready, "current_state_snapshot_sane": state_snapshot_ready},
                "gate_diagnosis": gate.get("diagnosis"),
                "known_invalid_execution_count": gate.get("known_invalid_execution_count"),
                "accounting_coverage_issue_count": accounting.get("coverage_issue_count"),
                "accounting_economic_issue_count": accounting.get("economic_issue_count"),
            }
            _LAST_STATUS = status
            return status
        try:
            return _cutover(core, gate, accounting)
        except Exception as exc:
            status = {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}
            _LAST_STATUS = status
            return status


def status_payload(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core) if core is not None else {}
    epoch = _d(pf.get("paper_accounting_epoch"))
    marker = _marker()
    active = str(epoch.get("id") or pf.get("accounting_epoch_id") or "") == TARGET_EPOCH_ID
    return {
        "status": "validation_hold" if active else _LAST_STATUS.get("status", "pending"),
        "overall": "pass" if active else _LAST_STATUS.get("overall", "warn"),
        "type": "verified_v2_successor_epoch_migration_status",
        "version": VERSION,
        "epoch_id": TARGET_EPOCH_ID,
        "active": active,
        "prior_epoch_id": OLD_EPOCH_ID,
        "historical_evidence_archived": bool(epoch.get("historical_evidence_archived", False)) if active else False,
        "forensic_archive_dir": epoch.get("forensic_archive_dir") or marker.get("archive_dir"),
        "validation_hold": bool(epoch.get("validation_hold", False)) if active else False,
        "marker_status": marker.get("status"),
        "canonical_ledger_unchanged": bool(marker.get("canonical_ledger_unchanged", False)),
        "authority": {
            "paper_only": True, "one_time_accounting_epoch_rollforward": True,
            "preserves_current_cash_equity_positions_and_risk": True,
            "archives_prior_epoch": True, "clears_active_state_trade_window": True,
            "edits_or_deletes_canonical_rows": False, "rotates_or_truncates_canonical_ledger": False,
            "rewrites_current_day_peak": False, "clears_hard_halt": False,
            "places_orders": False, "changes_strategy": False, "changes_thresholds": False,
            "changes_risk_or_sizing": False, "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify
        path = "/paper/verified-v2-successor-epoch-status"
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if path not in existing:
            flask_app.add_url_rule(path, "verified_v2_successor_epoch_status", lambda: jsonify(status_payload(core)))
        _REGISTERED_APP_IDS.add(app_id)
    return status_payload(core)
