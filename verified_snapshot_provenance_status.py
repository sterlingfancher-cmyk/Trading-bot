"""Read-only provenance status for the Stable Paper accounting recoveries.

This module exists only to answer a forensic question: did the durable clean-epoch
or verified-snapshot recovery evidence survive on the persistent volume after the
active paper state lost its accounting-epoch identity?

It never imports or calls either one-shot recovery module, never writes files,
never restores a backup, never changes the portfolio/risk/ledger, and never
places orders.  The route intentionally inspects only small marker/manifest
metadata plus the already-loaded in-memory portfolio so normal status reads stay
bounded.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Dict, List

VERSION = "verified-snapshot-provenance-status-2026-08-21-v1"

CLEAN_DECISION_ID = "journal-recovery-incomplete-2026-08-10"
CLEAN_EPOCH_ID = "stable-paper-v1-20260810-clean01"
VERIFIED_DECISION_ID = "verified-bad-tick-and-ledger-divergence-2026-08-12"
VERIFIED_EPOCH_ID = "stable-paper-v2-20260812-verified01"

STATE_DIR = (
    os.environ.get("STATE_DIR")
    or os.environ.get("PERSISTENT_STATE_DIR")
    or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    or "."
)
ARCHIVE_ROOT = os.path.join(STATE_DIR, "forensic_archives")
CLEAN_MARKER_FILE = os.path.join(STATE_DIR, f"clean_epoch_{CLEAN_DECISION_ID}.json")
VERIFIED_MARKER_FILE = os.path.join(STATE_DIR, f"verified_snapshot_{VERIFIED_DECISION_ID}.json")
MANIFEST_NAME = "verified_snapshot_recovery_manifest.json"
MAX_ARCHIVE_DIRS_SCANNED = 128
MAX_MATCHES_RETURNED = 16

_REGISTERED_APP_IDS: set[int] = set()


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_small_json(path: str) -> tuple[Dict[str, Any], str | None]:
    """Read marker/manifest JSON only; callers never point this at state.json."""
    try:
        if not os.path.isfile(path):
            return {}, None
        # Markers/manifests are expected to be tiny.  Fail closed on an
        # unexpectedly large file rather than turning a status route into a
        # heavyweight state reader.
        size = int(os.path.getsize(path))
        if size > 2_000_000:
            return {}, "metadata_file_too_large"
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            return {}, "metadata_not_object"
        return value, None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def _marker_summary(path: str, expected_decision: str, expected_epoch: str) -> Dict[str, Any]:
    payload, error = _load_small_json(path)
    exists = os.path.isfile(path)
    decision_id = str(payload.get("decision_id") or "") if payload else ""
    epoch_id = str(
        payload.get("target_epoch_id")
        or payload.get("epoch_id")
        or payload.get("accounting_epoch_id")
        or ""
    ) if payload else ""
    return {
        "path": path,
        "exists": exists,
        "size_bytes": int(os.path.getsize(path)) if exists else 0,
        "read_error": error,
        "status": payload.get("status") if payload else None,
        "decision_id": decision_id or None,
        "target_epoch_id": epoch_id or None,
        "archive_dir": payload.get("archive_dir") if payload else None,
        "started_local": payload.get("started_local") if payload else None,
        "completed_local": payload.get("completed_local") if payload else None,
        "decision_matches": bool(payload) and decision_id == expected_decision,
        "epoch_matches": bool(payload) and epoch_id == expected_epoch,
    }


def _archive_manifest_summaries() -> Dict[str, Any]:
    matches: List[Dict[str, Any]] = []
    scanned = 0
    errors: List[str] = []
    if not os.path.isdir(ARCHIVE_ROOT):
        return {
            "archive_root": ARCHIVE_ROOT,
            "root_exists": False,
            "directories_scanned": 0,
            "scan_truncated": False,
            "matching_manifest_count": 0,
            "matching_manifests": [],
            "errors": [],
        }

    try:
        names = sorted(os.listdir(ARCHIVE_ROOT), reverse=True)
    except Exception as exc:
        return {
            "archive_root": ARCHIVE_ROOT,
            "root_exists": True,
            "directories_scanned": 0,
            "scan_truncated": False,
            "matching_manifest_count": 0,
            "matching_manifests": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
        }

    candidates = [name for name in names if os.path.isdir(os.path.join(ARCHIVE_ROOT, name))]
    for name in candidates[:MAX_ARCHIVE_DIRS_SCANNED]:
        scanned += 1
        manifest_path = os.path.join(ARCHIVE_ROOT, name, MANIFEST_NAME)
        if not os.path.isfile(manifest_path):
            continue
        payload, error = _load_small_json(manifest_path)
        if error:
            errors.append(f"{name}: {error}")
            continue
        decision_id = str(payload.get("decision_id") or "")
        target_epoch_id = str(payload.get("target_epoch_id") or "")
        if decision_id != VERIFIED_DECISION_ID and target_epoch_id != VERIFIED_EPOCH_ID:
            continue
        if len(matches) < MAX_MATCHES_RETURNED:
            matches.append({
                "archive_dir": os.path.join(ARCHIVE_ROOT, name),
                "manifest_path": manifest_path,
                "status": payload.get("status"),
                "decision_id": decision_id or None,
                "old_epoch_id": payload.get("old_epoch_id"),
                "target_epoch_id": target_epoch_id or None,
                "created_local": payload.get("created_local"),
                "bad_execution_id": payload.get("bad_execution_id"),
            })

    return {
        "archive_root": ARCHIVE_ROOT,
        "root_exists": True,
        "directories_scanned": scanned,
        "scan_truncated": len(candidates) > MAX_ARCHIVE_DIRS_SCANNED,
        "matching_manifest_count": len(matches),
        "matching_manifests": matches,
        "errors": errors[:MAX_MATCHES_RETURNED],
    }


def _active_epoch_summary(core: Any = None) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    pf = pf if isinstance(pf, dict) else {}
    epoch = _d(pf.get("paper_accounting_epoch"))
    return {
        "portfolio_available": bool(pf),
        "cash": pf.get("cash"),
        "equity": pf.get("equity"),
        "positions_count": len(_d(pf.get("positions"))),
        "trades_count": len(pf.get("trades") or []) if isinstance(pf.get("trades"), list) else 0,
        "accounting_epoch_id": pf.get("accounting_epoch_id"),
        "paper_accounting_epoch_id": epoch.get("id"),
        "decision_id": epoch.get("decision_id"),
        "baseline_type": epoch.get("baseline_type"),
        "historical_recovery_decision": epoch.get("historical_recovery_decision"),
        "historical_evidence_archived": epoch.get("historical_evidence_archived"),
        "forensic_archive_dir": epoch.get("forensic_archive_dir"),
        "validation_hold": epoch.get("validation_hold"),
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    clean_marker = _marker_summary(CLEAN_MARKER_FILE, CLEAN_DECISION_ID, CLEAN_EPOCH_ID)
    verified_marker = _marker_summary(
        VERIFIED_MARKER_FILE, VERIFIED_DECISION_ID, VERIFIED_EPOCH_ID
    )
    archives = _archive_manifest_summaries()
    active = _active_epoch_summary(core)

    verified_marker_proves = bool(
        verified_marker.get("exists")
        and verified_marker.get("decision_matches")
        and verified_marker.get("epoch_matches")
        and not verified_marker.get("read_error")
    )
    verified_archive_proves = bool(archives.get("matching_manifest_count"))
    clean_marker_proves = bool(
        clean_marker.get("exists")
        and clean_marker.get("decision_matches")
        and clean_marker.get("epoch_matches")
        and not clean_marker.get("read_error")
    )
    durable_verified_evidence = verified_marker_proves or verified_archive_proves

    if durable_verified_evidence:
        diagnosis = "verified_snapshot_durable_provenance_found"
        overall = "pass"
    elif clean_marker_proves:
        diagnosis = "clean_epoch_provenance_found_verified_snapshot_missing"
        overall = "warn"
    else:
        diagnosis = "recovery_markers_and_verified_archive_not_found"
        overall = "warn"

    return {
        "status": "ok",
        "overall": overall,
        "type": "verified_snapshot_provenance_status",
        "version": VERSION,
        "generated_local": _now(core),
        "diagnosis": diagnosis,
        "durable_verified_evidence_found": durable_verified_evidence,
        "clean_epoch_marker_found": clean_marker_proves,
        "verified_snapshot_marker_found": verified_marker_proves,
        "verified_snapshot_archive_found": verified_archive_proves,
        "active_runtime": active,
        "clean_epoch_marker": clean_marker,
        "verified_snapshot_marker": verified_marker,
        "verified_snapshot_archives": archives,
        "performance_contract": {
            "reads_large_state_or_backup_files": False,
            "archive_directories_scan_limit": MAX_ARCHIVE_DIRS_SCANNED,
            "manifest_matches_return_limit": MAX_MATCHES_RETURNED,
        },
        "authority": {
            "reporting_only": True,
            "places_orders": False,
            "writes_files": False,
            "restores_backups": False,
            "repairs_historical_state": False,
            "rewrites_canonical_ledger": False,
            "clears_hard_halt": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return status_payload(core)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "flask_app_missing"}
    if id(flask_app) not in _REGISTERED_APP_IDS:
        from flask import jsonify
        try:
            existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        except Exception:
            existing = set()
        if "/paper/verified-snapshot-provenance-status" not in existing:
            flask_app.add_url_rule(
                "/paper/verified-snapshot-provenance-status",
                "verified_snapshot_provenance_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "overall": "pass", "version": VERSION, "route_registered": True}
