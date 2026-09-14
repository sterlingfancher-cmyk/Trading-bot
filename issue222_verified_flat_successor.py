"""Exact Issue #222 verified-flat v4 -> v5 successor epoch.

The v4 canonical ledger is immutable and hash-valid, but four contiguous short
entry rows disappeared from the mutable state projection and have no exact
later exit evidence.  The current state and its independent accounting
reconstruction are flat.  Under the user's explicit 2026-09-14 authorization,
this one-time paper-only migration archives all prior persistence, retains the
ledger byte-for-byte, marks the unresolved v4 discrepancy non-promotable, and
starts a verified-flat v5 accounting epoch under validation hold.

No exit is inferred or fabricated.  The active parity halt, risk/day-peak state,
and historical equity series are preserved exactly.  The module fails closed on
any drift from the demonstrated signatures or account shape.
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

import verified_v3_successor_epoch_migration as v3

VERSION = "issue222-verified-flat-successor-2026-09-14-v2-exact-later-lifecycle-evidence"
OLD_EPOCH_ID = "stable-paper-v4-20260826-successor01"
TARGET_EPOCH_ID = "stable-paper-v5-20260914-issue222-flat-successor01"
DECISION_ID = "issue-222-unresolved-v4-entry-projection-flat-successor-2026-09-14"
HISTORICAL_DECISION = "issue222_unresolved_v4_projection_verified_flat_successor"
HALT_REASON = "canonical execution/state projection divergence"
EXPECTED_LEDGER_ROWS = 88
EXPECTED_CURRENT_EPOCH_ROWS = 42
EXPECTED_STATE_ROWS = 38
EXPECTED_CASH = 13429.130485
EXPECTED_EQUITY = 13429.13
EXPECTED_LAST_EXECUTION_ID = "a28005eb52b34e31a431b446ea68f0c7"
MONEY_TOLERANCE = 0.05
QTY_TOLERANCE = 5e-9
PRICE_TOLERANCE = 5e-7
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
ARCHIVE_ROOT = os.path.join(STATE_DIR, "forensic_archives")
MARKER_FILE = os.path.join(STATE_DIR, "issue222_verified_flat_successor.json")
_LOCK = threading.RLock()
_REGISTERED_APP_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}

EXPECTED_MISSING_IDS = {
    "9554247470c54fe9a00598da6a346f46",
    "96cdc732bf6b475098a9b6887ac76fa7",
    "9cad03cbec994e29a9b65293d573f54b",
    "c90260025d4b4eed8b3a0029e0267b5f",
}
EXPECTED_MISSING_ROWS: Tuple[Dict[str, Any], ...] = (
    {
        "execution_id": "9cad03cbec994e29a9b65293d573f54b",
        "event_hash": "1504ba26dd40438328b463af2bda4eb7d5394234d8d9bf50acf37883209450ae",
        "previous_event_hash": "1eccf0bcfacc02db2cc3f0be3db0b1a6109f6de09d3dc95401ac9c72ede44712",
        "symbol": "GEV", "action": "entry", "side": "short",
        "price": 920.929993, "shares": 1.091006383,
    },
    {
        "event_hash": "82d2b757418690153b38e66b9e447132666401daf0a85c932ffc0f4b3795fcf2",
        "previous_event_hash": "1504ba26dd40438328b463af2bda4eb7d5394234d8d9bf50acf37883209450ae",
        "symbol": "SPCX", "action": "entry", "side": "short",
        "price": 149.514999, "shares": 6.719998021,
    },
    {
        "event_hash": "4bfc5ba82b6dd95bbc99952dbfce446cd29336ff82759458279627768c6ae598",
        "previous_event_hash": "82d2b757418690153b38e66b9e447132666401daf0a85c932ffc0f4b3795fcf2",
        "symbol": "SPCX", "action": "entry", "side": "short",
        "price": 148.880096, "shares": 6.748655623,
    },
    {
        "event_hash": "313543e183e5a7368e57fd7d7d50a7eb45f19b4db30e2d14375109199caf0949",
        "previous_event_hash": "4bfc5ba82b6dd95bbc99952dbfce446cd29336ff82759458279627768c6ae598",
        "symbol": "ACHR", "action": "entry", "side": "short",
        "price": 5.4631, "shares": 183.913988028,
    },
)


# Reuse the established successor primitives instead of adding parallel helper
# owners. The migration's module lock serializes their marker writes.
_d = v3._d
_l = v3._l
_f = v3._f
_close = v3._close
_now = v3._now
_portfolio = v3._portfolio
_epoch_id = v3._epoch_id
_atomic_json = v3._atomic_json
_sha256 = v3._sha256


def _marker() -> Dict[str, Any]:
    try:
        with open(MARKER_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _row_matches(row: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    return bool(
        str(row.get("accounting_epoch_id") or "") == OLD_EPOCH_ID
        and str(row.get("event_hash") or "") == expected["event_hash"]
        and str(row.get("previous_event_hash") or "") == expected["previous_event_hash"]
        and str(row.get("symbol") or "").upper() == expected["symbol"]
        and str(row.get("action") or "").lower() == expected["action"]
        and str(row.get("side") or "").lower() == expected["side"]
        and _close(row.get("price"), float(expected["price"]), PRICE_TOLERANCE)
        and _close(row.get("shares"), float(expected["shares"]), QTY_TOLERANCE)
        and (
            not expected.get("execution_id")
            or str(row.get("execution_id") or "") == expected["execution_id"]
        )
    )


def _canonical_evidence(pf: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import canonical_execution_ledger as ledger
        with ledger._LOCK:
            rows, parse_errors = ledger._read_rows()
            chain_valid, chain_errors = ledger._verify_rows(rows)
    except Exception as exc:
        return {"status": "fail", "issues": [f"ledger_read_error:{type(exc).__name__}:{exc}"]}

    issues: List[str] = []
    if parse_errors or not chain_valid:
        issues.append("canonical_chain_invalid")
    execution_ids = [str(row.get("execution_id") or "") for row in rows]
    if not all(execution_ids) or len(execution_ids) != len(set(execution_ids)):
        issues.append("canonical_execution_ids_not_unique")
    if len(rows) != EXPECTED_LEDGER_ROWS:
        issues.append("canonical_total_row_count_changed")

    epoch_rows = [
        row for row in rows
        if str(row.get("accounting_epoch_id") or "") == OLD_EPOCH_ID
    ]
    if len(epoch_rows) != EXPECTED_CURRENT_EPOCH_ROWS:
        issues.append("canonical_v4_row_count_changed")
    if not epoch_rows or str(epoch_rows[-1].get("execution_id") or "") != EXPECTED_LAST_EXECUTION_ID:
        issues.append("canonical_v4_tail_changed")

    state_rows = [
        row for row in _l(pf.get("trades"))
        if isinstance(row, dict) and str(row.get("accounting_epoch_id") or "") == OLD_EPOCH_ID
    ]
    state_ids = {str(row.get("execution_id") or "") for row in state_rows}
    ledger_by_id = {str(row.get("execution_id") or ""): row for row in epoch_rows}
    ledger_ids = set(ledger_by_id)
    if len(state_rows) != EXPECTED_STATE_ROWS:
        issues.append("state_v4_row_count_changed")
    if ledger_ids - state_ids != EXPECTED_MISSING_IDS:
        issues.append("missing_execution_set_changed")
    if state_ids - ledger_ids:
        issues.append("state_contains_noncanonical_execution")

    for row in state_rows:
        execution_id = str(row.get("execution_id") or "")
        canonical = ledger_by_id.get(execution_id)
        if canonical is None or str(row.get("canonical_ledger_event_hash") or "") != str(canonical.get("event_hash") or ""):
            issues.append(f"state_canonical_binding_mismatch:{execution_id}")

    matched: List[Dict[str, Any]] = []
    missing_indexes: List[int] = []
    for expected in EXPECTED_MISSING_ROWS:
        candidates = [
            (index, row) for index, row in enumerate(epoch_rows)
            if str(row.get("event_hash") or "") == expected["event_hash"]
        ]
        if len(candidates) != 1 or not _row_matches(candidates[0][1], expected):
            issues.append(f"missing_row_signature_mismatch:{expected['event_hash']}")
            continue
        index, row = candidates[0]
        if str(row.get("execution_id") or "") not in EXPECTED_MISSING_IDS:
            issues.append(f"missing_row_execution_id_unexpected:{expected['event_hash']}")
        missing_indexes.append(index)
        matched.append({
            "execution_id": row.get("execution_id"),
            "event_hash": row.get("event_hash"),
            "previous_event_hash": row.get("previous_event_hash"),
            "symbol": row.get("symbol"),
            "action": row.get("action"),
            "side": row.get("side"),
            "price": row.get("price"),
            "shares": row.get("shares"),
        })
    if len(missing_indexes) == 4 and missing_indexes != list(range(missing_indexes[0], missing_indexes[0] + 4)):
        issues.append("missing_rows_not_contiguous")

    first_index = min(missing_indexes) if missing_indexes else len(epoch_rows)
    later_exit_candidates = [
        {
            key: row.get(key)
            for key in (
                "execution_id",
                "event_hash",
                "previous_event_hash",
                "accounting_epoch_id",
                "ledger_version",
                "recorded_local",
                "timestamp",
                "action",
                "symbol",
                "side",
                "price",
                "shares",
                "entry_price",
                "realized_pnl",
                "pnl",
                "pnl_pct",
                "notional",
                "fees",
                "reason",
                "trade_id",
                "parent_execution_id",
                "position_id",
            )
        }
        for row in epoch_rows[first_index + 1:]
        if str(row.get("symbol") or "").upper() in {"GEV", "SPCX", "ACHR"}
        and str(row.get("side") or "").lower() == "short"
        and str(row.get("action") or "").lower() in {"exit", "partial_exit"}
    ]
    if later_exit_candidates:
        issues.append("possible_later_exit_evidence_requires_review")

    return {
        "status": "ok" if not issues else "fail",
        "issues": issues,
        "rows": rows,
        "ledger_file": str(getattr(ledger, "LEDGER_FILE", "")),
        "chain_valid": bool(chain_valid),
        "total_rows": len(rows),
        "current_epoch_rows": len(epoch_rows),
        "state_rows": len(state_rows),
        "missing_rows": matched,
        "missing_ids": sorted(ledger_ids - state_ids),
        "later_exit_candidates": later_exit_candidates,
    }


def _accounting_evidence(core: Any, pf: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    try:
        import paper_bidirectional_accounting_guard as accounting
        rebuilt = accounting.analyze_ledger(pf, core)
    except Exception as exc:
        return {"status": "fail", "error": f"{type(exc).__name__}:{exc}"}, False
    cash = _f(rebuilt.get("cash", rebuilt.get("reconstructed_cash")))
    equity = _f(rebuilt.get("equity", rebuilt.get("reconstructed_equity")))
    open_positions = _d(rebuilt.get("open_positions"))
    if not open_positions:
        open_positions = {
            str(symbol): {} for symbol in _l(rebuilt.get("reconstructed_open_positions"))
        }
    ready = bool(
        rebuilt.get("coverage_complete")
        and int(rebuilt.get("coverage_issue_count") or 0) == 0
        and int(rebuilt.get("economic_issue_count") or 0) == 0
        and not open_positions
        and cash is not None and equity is not None
        and _close(cash, float(pf.get("cash")), MONEY_TOLERANCE)
        and _close(equity, float(pf.get("equity")), MONEY_TOLERANCE)
    )
    return rebuilt, ready


def _preconditions(core: Any) -> Dict[str, Any]:
    pf = _portfolio(core)
    risk = _d(pf.get("risk_controls"))
    epoch = _d(pf.get("paper_accounting_epoch"))
    canonical = _canonical_evidence(pf)
    accounting, accounting_ready = _accounting_evidence(core, pf)
    checks = {
        "paper_runtime": v3._paper_only(),
        "active_epoch_exact_v4": _epoch_id(pf) == OLD_EPOCH_ID,
        "v4_release_was_completed": bool(
            epoch.get("validation_released")
            and epoch.get("validation_release_status") == "released"
            and not epoch.get("validation_hold")
        ),
        "exact_projection_halt_active": bool(
            risk.get("halted") and str(risk.get("halt_reason") or "") == HALT_REASON
        ),
        "current_state_flat": not _d(pf.get("positions")),
        "current_cash_exact": _close(pf.get("cash"), EXPECTED_CASH, MONEY_TOLERANCE),
        "current_equity_exact": _close(pf.get("equity"), EXPECTED_EQUITY, MONEY_TOLERANCE),
        "canonical_evidence_exact": canonical.get("status") == "ok",
        "independent_accounting_clean_flat": accounting_ready,
    }
    return {
        "checks": checks,
        "failed": [name for name, ok in checks.items() if not ok],
        "canonical": canonical,
        "accounting": accounting,
    }


def _archive(core: Any, pre: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(ARCHIVE_ROOT, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
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
                copied.append({
                    "name": name, "type": "file", "size_bytes": os.path.getsize(dst),
                    "sha256": _sha256(dst),
                })
        except Exception as exc:
            raise RuntimeError(f"archive_failed:{name}:{type(exc).__name__}:{exc}") from exc

    canonical = _d(pre.get("canonical"))
    manifest = {
        "status": "ok",
        "type": "issue222_verified_flat_successor_archive",
        "version": VERSION,
        "decision_id": DECISION_ID,
        "prior_epoch_id": OLD_EPOCH_ID,
        "target_epoch_id": TARGET_EPOCH_ID,
        "created_local": _now(core),
        "archive_dir": archive_dir,
        "canonical_ledger": {
            "path": canonical.get("ledger_file"),
            "sha256_before_cutover": _sha256(str(canonical.get("ledger_file") or "")),
            "immutable_history_retained_in_place": True,
            "rotated_or_truncated": False,
            "chain_valid": canonical.get("chain_valid"),
            "total_rows": canonical.get("total_rows"),
            "current_epoch_rows": canonical.get("current_epoch_rows"),
        },
        "unresolved_prior_discrepancy": {
            "status": "unresolved_non_promotable",
            "missing_ids": canonical.get("missing_ids"),
            "missing_rows": canonical.get("missing_rows"),
            "later_exit_candidates": canonical.get("later_exit_candidates"),
            "fabricated_exit_rows": 0,
            "prior_epoch_economics_promotable": False,
        },
        "pre_cutover_account": copy.deepcopy(_portfolio(core)),
        "copied_entries": copied,
    }
    _atomic_json(os.path.join(archive_dir, "issue222_verified_flat_successor_manifest.json"), manifest)
    return manifest


def build_successor_state(pf: Dict[str, Any], archive_dir: str, started_local: str, missing_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    state = copy.deepcopy(pf)
    risk_before = copy.deepcopy(_d(state.get("risk_controls")))
    history_before = copy.deepcopy(state.get("history"))
    cash = _f(state.get("cash"))
    equity = _f(state.get("equity"))
    if cash is None or equity is None or cash <= 0 or equity <= 0 or abs(cash - equity) > MONEY_TOLERANCE:
        raise RuntimeError("verified-flat successor valuation is not sane")
    if _d(state.get("positions")):
        raise RuntimeError("verified-flat successor requires flat state")
    if not risk_before.get("halted") or str(risk_before.get("halt_reason") or "") != HALT_REASON:
        raise RuntimeError("projection halt is not active")

    realized = copy.deepcopy(_d(state.get("realized_pnl")))
    performance = copy.deepcopy(_d(state.get("performance")))
    performance["open_positions"] = {}
    performance["unrealized_pnl"] = 0.0
    state["positions"] = {}
    state["trades"] = []
    state["performance"] = performance
    state["risk_controls"] = risk_before
    state["history"] = history_before

    snapshot = {
        "verified": True,
        "version": VERSION,
        "started_local": started_local,
        "cash": cash,
        "equity": equity,
        "realized_today": realized.get("today"),
        "realized_total": realized.get("total"),
        "positions": {},
        "source": "independently_clean_flat_v4_state_with_unresolved_canonical_projection_archived",
        "fabricated_exit_rows": 0,
    }
    state["accounting_epoch_id"] = TARGET_EPOCH_ID
    state["paper_accounting_epoch"] = {
        "version": VERSION,
        "id": TARGET_EPOCH_ID,
        "decision_id": DECISION_ID,
        "started_local": started_local,
        "starting_cash": cash,
        "starting_equity": equity,
        "clean_start": False,
        "zero_trade_baseline": True,
        "baseline_type": "verified_flat_snapshot_unresolved_prior_projection",
        "verified_snapshot_baseline": snapshot,
        "historical_recovery_decision": HISTORICAL_DECISION,
        "prior_epoch_id": OLD_EPOCH_ID,
        "prior_epoch_disposition": "archived_unresolved_non_promotable_immutable_v4_projection_divergence",
        "historical_evidence_archived": True,
        "forensic_archive_dir": archive_dir,
        "validation_hold": True,
        "validation_hold_reason": "issue 222 v5 verified-flat successor validation hold",
        "validation_release_status": "blocked",
        "validation_released": False,
        "validation_released_local": None,
        "forward_validation_required": True,
        "valid_path_rows_baseline": 0,
        "prior_epoch_discrepancy_status": "unresolved_non_promotable",
        "prior_epoch_economics_promotable": False,
        "missing_execution_ids": sorted(EXPECTED_MISSING_IDS),
        "missing_execution_rows": copy.deepcopy(missing_rows),
        "fabricated_exit_rows": 0,
        "canonical_history_retained_immutably": True,
    }
    state["issue222_verified_flat_successor"] = {
        "version": VERSION,
        "status": "validation_hold",
        "prior_epoch_id": OLD_EPOCH_ID,
        "target_epoch_id": TARGET_EPOCH_ID,
        "unresolved_prior_discrepancy": True,
        "prior_epoch_economics_promotable": False,
        "fabricated_exit_rows": 0,
        "risk_halt_cleared": False,
        "canonical_history_rewritten": False,
    }
    return state


def _rotate_journal() -> None:
    import trade_journal as tj
    factory = getattr(tj, "_empty_journal", None)
    journal = factory() if callable(factory) else {
        "trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []
    }
    if not isinstance(journal, dict):
        raise RuntimeError("trade journal factory returned non-object")
    journal["accounting_epoch_id"] = TARGET_EPOCH_ID
    journal["issue222_successor_epoch_started_local"] = _now()
    journal["issue222_successor_version"] = VERSION
    for attr in ("TRADE_JOURNAL_FILE", "TRADE_JOURNAL_BACKUP_FILE"):
        path = str(getattr(tj, attr, "") or "")
        if path:
            _atomic_json(path, journal)


def _cutover(core: Any, pre: Dict[str, Any], *, retried: bool) -> Dict[str, Any]:
    global _LAST
    import clean_accounting_epoch as clean
    canonical = _d(pre.get("canonical"))
    ledger_file = str(canonical.get("ledger_file") or "")
    digest_before = _sha256(ledger_file)
    archive = _archive(core, pre)
    started_local = _now(core)
    started = {
        "status": "cutover_started", "overall": "warn", "version": VERSION,
        "decision_id": DECISION_ID, "prior_epoch_id": OLD_EPOCH_ID,
        "target_epoch_id": TARGET_EPOCH_ID, "started_local": started_local,
        "archive_dir": archive.get("archive_dir"),
        "canonical_ledger_sha256_before": digest_before,
        "missing_execution_ids": sorted(EXPECTED_MISSING_IDS),
        "fabricated_exit_rows": 0,
    }
    _atomic_json(MARKER_FILE, started)
    pf = _portfolio(core)
    risk_before = copy.deepcopy(_d(pf.get("risk_controls")))
    history_before = copy.deepcopy(pf.get("history"))
    successor = build_successor_state(
        pf, str(archive.get("archive_dir") or ""), started_local,
        _l(canonical.get("missing_rows")),
    )
    with clean._runtime_locks():
        state_file = clean._write_clean_state_and_backups(core, successor)
        _rotate_journal()
        clean._reset_snapshot_archive(successor, state_file)
        pf.clear()
        pf.update(successor)

    digest_after = _sha256(ledger_file)
    if digest_before != digest_after:
        raise RuntimeError("canonical ledger changed during Issue #222 successor cutover")
    if _d(successor.get("risk_controls")) != risk_before:
        raise RuntimeError("risk controls changed during Issue #222 successor cutover")
    if successor.get("history") != history_before:
        raise RuntimeError("history changed during Issue #222 successor cutover")

    completed = {
        **started,
        "status": "completed", "overall": "pass", "completed_local": _now(core),
        "state_file": state_file, "validation_hold": True,
        "canonical_ledger_sha256_after": digest_after,
        "canonical_ledger_unchanged": digest_before == digest_after,
        "successor_cash": successor.get("cash"),
        "successor_equity": successor.get("equity"),
        "successor_positions": [],
        "successor_trade_rows": 0,
        "projection_halt_preserved": True,
        "projection_halt_reason": HALT_REASON,
        "unresolved_prior_discrepancy": True,
        "prior_epoch_economics_promotable": False,
        "interrupted_completion_retry_performed": retried,
    }
    _atomic_json(MARKER_FILE, completed)
    _LAST = completed
    return completed


def _active_status(core: Any) -> Dict[str, Any]:
    pf = _portfolio(core)
    epoch = _d(pf.get("paper_accounting_epoch"))
    marker = _marker()
    risk = _d(pf.get("risk_controls"))
    return {
        "status": "validation_hold",
        "overall": "pass",
        "version": VERSION,
        "epoch_id": TARGET_EPOCH_ID,
        "prior_epoch_id": OLD_EPOCH_ID,
        "historical_evidence_archived": bool(epoch.get("historical_evidence_archived")),
        "forensic_archive_dir": epoch.get("forensic_archive_dir"),
        "validation_hold": bool(epoch.get("validation_hold")),
        "canonical_ledger_unchanged": bool(marker.get("canonical_ledger_unchanged")),
        "unresolved_prior_discrepancy": epoch.get("prior_epoch_discrepancy_status") == "unresolved_non_promotable",
        "prior_epoch_economics_promotable": bool(epoch.get("prior_epoch_economics_promotable")),
        "fabricated_exit_rows": int(epoch.get("fabricated_exit_rows") or 0),
        "state_trade_rows": len(_l(pf.get("trades"))),
        "positions": sorted(_d(pf.get("positions"))),
        "cash": pf.get("cash"),
        "equity": pf.get("equity"),
        "projection_halt_preserved": bool(risk.get("halted")),
        "projection_halt_reason": risk.get("halt_reason"),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not v3._paper_only():
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "paper_runtime_only"}
    with _LOCK:
        pf = _portfolio(core)
        active_epoch = _epoch_id(pf)
        marker = _marker()
        if active_epoch == TARGET_EPOCH_ID:
            result = _active_status(core)
            if marker.get("status") != "completed":
                result.update({"status": "error", "overall": "fail", "reason": "v5_active_without_completed_issue222_marker"})
            _LAST = result
            return result
        if active_epoch != OLD_EPOCH_ID:
            result = {
                "status": "not_applicable", "overall": "pass", "version": VERSION,
                "reason": "issue222_v4_epoch_not_active", "active_epoch_id": active_epoch,
            }
            _LAST = result
            return result

        retry = marker.get("status") in {"cutover_started", "completed"}
        if retry and not (
            str(marker.get("prior_epoch_id") or "") == OLD_EPOCH_ID
            and str(marker.get("target_epoch_id") or "") == TARGET_EPOCH_ID
            and set(marker.get("missing_execution_ids") or []) == EXPECTED_MISSING_IDS
            and int(marker.get("fabricated_exit_rows") or 0) == 0
        ):
            result = {
                "status": "blocked", "overall": "fail", "version": VERSION,
                "reason": "issue222_successor_marker_mismatch",
            }
            _LAST = result
            return result

        pre = _preconditions(core)
        if pre["failed"]:
            canonical = _d(pre.get("canonical"))
            result = {
                "status": "blocked", "overall": "fail", "version": VERSION,
                "reason": "issue222_successor_preconditions_not_met",
                "failed_checks": pre["failed"], "checks": pre["checks"],
                "canonical": {key: value for key, value in canonical.items() if key != "rows"},
            }
            _LAST = result
            return result
        try:
            return _cutover(core, pre, retried=bool(retry))
        except Exception as exc:
            result = {
                "status": "error", "overall": "fail", "version": VERSION,
                "reason": "issue222_successor_cutover_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
            _LAST = result
            return result


def status_payload(core: Any = None) -> Dict[str, Any]:
    if core is not None and _epoch_id(_portfolio(core)) == TARGET_EPOCH_ID:
        result = _active_status(core)
    else:
        result = dict(_LAST) if _LAST else {
            "status": "pending", "overall": "warn", "version": VERSION,
            "active_epoch_id": _epoch_id(_portfolio(core)) if core is not None else None,
        }
    return {
        **result,
        "type": "issue222_verified_flat_successor_status",
        "status_reads_are_observational": True,
        "authority": {
            "paper_only": True,
            "one_time_accounting_epoch_rollforward": True,
            "archives_prior_evidence": True,
            "uses_verified_flat_snapshot": True,
            "marks_prior_discrepancy_non_promotable": True,
            "fabricates_exit_rows": False,
            "edits_or_deletes_canonical_rows": False,
            "rotates_or_truncates_canonical_ledger": False,
            "rewrites_current_day_peak": False,
            "rewrites_history": False,
            "clears_hard_halt": False,
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
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify
        path = "/paper/issue222-verified-flat-successor-status"
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if path not in existing:
            flask_app.add_url_rule(
                path, "issue222_verified_flat_successor_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(app_id)
    return status_payload(core)
