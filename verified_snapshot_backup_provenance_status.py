"""Read-only backup/snapshot provenance probe for the Aug. 12 verified epoch.

This module answers one narrow forensic question after Issue #82 evidence showed
that the active state lost its accounting-epoch identity and the dedicated
recovery marker/archive files are gone: do any currently retained state backups
or low-trade-count snapshots still contain the exact verified-snapshot epoch
metadata?

The probe is deliberately observational:
- it never imports/calls either one-shot recovery module;
- it never writes, restores, deletes, renames, or relabels any file/state/ledger;
- startup apply() is constant-time and does not scan backups;
- the HTTP status route scans only a fixed set of known backup files plus a small
  bounded subset of snapshot files selected from the snapshot manifest;
- files are streamed in chunks and never fully parsed into memory.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Any, Dict, List

VERSION = "verified-snapshot-backup-provenance-status-2026-08-21-v2-object-bounded"

CLEAN_DECISION_ID = "journal-recovery-incomplete-2026-08-10"
CLEAN_EPOCH_ID = "stable-paper-v1-20260810-clean01"
VERIFIED_DECISION_ID = "verified-bad-tick-and-ledger-divergence-2026-08-12"
VERIFIED_EPOCH_ID = "stable-paper-v2-20260812-verified01"
VERIFIED_BASELINE_TYPE = "verified_snapshot_with_open_position"
VERIFIED_RECOVERY_DECISION = "verified_snapshot_rollforward"
BAD_EXECUTION_ID = "5ca38922916e4612ae3cda8d9801107d"

STATE_DIR = (
    os.environ.get("STATE_DIR")
    or os.environ.get("PERSISTENT_STATE_DIR")
    or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    or "."
)
STATE_FILE = os.path.join(STATE_DIR, "state.json")
BACKUP_FILES = (
    os.path.join(STATE_DIR, "state.json.bak"),
    os.path.join(STATE_DIR, "state_backup_latest.json"),
    os.path.join(STATE_DIR, "state_backup_prewrite.json"),
    os.path.join(STATE_DIR, "state_backup_largest.json"),
)
SNAPSHOT_DIR = os.path.join(STATE_DIR, "state_snapshots")
SNAPSHOT_MANIFEST = os.path.join(SNAPSHOT_DIR, "manifest.json")

CHUNK_BYTES = 1024 * 1024
OVERLAP_BYTES = 256 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
EPOCH_BLOCK_BYTES = 256 * 1024
MAX_SNAPSHOT_ROWS = 16
MAX_SNAPSHOT_FILES_SCANNED = 3
MAX_METADATA_BYTES = 2 * 1024 * 1024

_REGISTERED_APP_IDS: set[int] = set()

_FIELD_PATTERNS = {
    "id": re.compile(rb'"id"\s*:\s*"([^"]+)"'),
    "decision_id": re.compile(rb'"decision_id"\s*:\s*"([^"]+)"'),
    "baseline_type": re.compile(rb'"baseline_type"\s*:\s*"([^"]+)"'),
    "historical_recovery_decision": re.compile(
        rb'"historical_recovery_decision"\s*:\s*"([^"]+)"'
    ),
    "prior_epoch_id": re.compile(rb'"prior_epoch_id"\s*:\s*"([^"]+)"'),
    "forensic_archive_dir": re.compile(
        rb'"forensic_archive_dir"\s*:\s*(?:"([^"]*)"|null)'
    ),
}
_ACCOUNTING_EPOCH_ID_PATTERN = re.compile(
    rb'"accounting_epoch_id"\s*:\s*(?:"([^"]+)"|null)'
)
_ARCHIVED_PATTERN = re.compile(
    rb'"historical_evidence_archived"\s*:\s*(true|false|null)'
)


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _decode(value: bytes | None) -> str | None:
    if not value:
        return None
    try:
        return value.decode("utf-8", errors="replace")
    except Exception:
        return None


def _bool_token(value: bytes | None) -> bool | None:
    if value == b"true":
        return True
    if value == b"false":
        return False
    return None


def _mtime_local(path: str) -> str | None:
    try:
        return dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except Exception:
        return None


def _load_small_json(path: str) -> tuple[Dict[str, Any], str | None]:
    try:
        if not os.path.isfile(path):
            return {}, None
        size = int(os.path.getsize(path))
        if size > MAX_METADATA_BYTES:
            return {}, "metadata_file_too_large"
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            return {}, "metadata_not_object"
        return value, None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def _bounded_json_object(raw: bytes) -> tuple[bytes, str | None]:
    """Return the first complete JSON object in raw without parsing whole state."""
    start = raw.find(b"{")
    if start < 0:
        return b"", "epoch_object_start_not_found"
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(raw)):
        value = raw[index]
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:
                escaped = True
            elif value == 0x22:
                in_string = False
            continue
        if value == 0x22:
            in_string = True
        elif value == 0x7B:
            depth += 1
        elif value == 0x7D:
            depth -= 1
            if depth == 0:
                return raw[start : index + 1], None
    return b"", "epoch_object_exceeds_bounded_read"


def _extract_epoch_block(path: str, offset: int) -> Dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            handle.seek(max(0, offset))
            raw = handle.read(EPOCH_BLOCK_BYTES)
    except Exception as exc:
        return {"read_error": f"{type(exc).__name__}: {exc}"}

    block, object_error = _bounded_json_object(raw)
    if object_error:
        return {
            "read_error": object_error,
            "verified_signature": False,
            "clean_signature": False,
        }

    values: Dict[str, Any] = {"read_error": None}
    for name, pattern in _FIELD_PATTERNS.items():
        match = pattern.search(block)
        values[name] = _decode(match.group(1)) if match and match.group(1) else None
    archived_match = _ARCHIVED_PATTERN.search(block)
    values["historical_evidence_archived"] = (
        _bool_token(archived_match.group(1)) if archived_match else None
    )
    values["bad_execution_id_found_in_epoch_block"] = BAD_EXECUTION_ID.encode() in block
    values["epoch_object_bytes"] = len(block)

    values["verified_signature"] = bool(
        values.get("id") == VERIFIED_EPOCH_ID
        and values.get("decision_id") == VERIFIED_DECISION_ID
        and values.get("baseline_type") == VERIFIED_BASELINE_TYPE
        and values.get("historical_recovery_decision") == VERIFIED_RECOVERY_DECISION
        and values.get("historical_evidence_archived") is True
        and values.get("prior_epoch_id") == CLEAN_EPOCH_ID
    )
    values["clean_signature"] = bool(
        values.get("id") == CLEAN_EPOCH_ID
        and values.get("decision_id") == CLEAN_DECISION_ID
    )
    return values


def _scan_state_file(path: str, remaining_budget: int) -> Dict[str, Any]:
    exists = os.path.isfile(path)
    size = int(os.path.getsize(path)) if exists else 0
    result: Dict[str, Any] = {
        "path": path,
        "exists": exists,
        "size_bytes": size,
        "modified_local": _mtime_local(path) if exists else None,
        "bytes_scanned": 0,
        "scan_truncated": False,
        "paper_accounting_epoch_key_found": False,
        "accounting_epoch_ids_found": [],
        "verified_epoch_token_found": False,
        "verified_decision_token_found": False,
        "verified_baseline_token_found": False,
        "bad_execution_id_token_found": False,
        "verified_signature": False,
        "clean_signature": False,
        "epoch_block": None,
        "read_error": None,
    }
    if not exists or size <= 0 or remaining_budget <= 0:
        return result

    file_budget = min(size, MAX_FILE_BYTES, remaining_budget)
    overlap = b""
    absolute = 0
    epoch_offset: int | None = None
    accounting_ids: List[str] = []
    verified_token = VERIFIED_EPOCH_ID.encode()
    decision_token = VERIFIED_DECISION_ID.encode()
    baseline_token = VERIFIED_BASELINE_TYPE.encode()
    bad_execution_token = BAD_EXECUTION_ID.encode()
    epoch_key = b'"paper_accounting_epoch"'

    try:
        with open(path, "rb") as handle:
            while absolute < file_budget:
                to_read = min(CHUNK_BYTES, file_budget - absolute)
                chunk = handle.read(to_read)
                if not chunk:
                    break
                data = overlap + chunk
                data_start = absolute - len(overlap)

                if epoch_offset is None:
                    idx = data.find(epoch_key)
                    if idx >= 0:
                        epoch_offset = max(0, data_start + idx)
                        result["paper_accounting_epoch_key_found"] = True

                if verified_token in data:
                    result["verified_epoch_token_found"] = True
                if decision_token in data:
                    result["verified_decision_token_found"] = True
                if baseline_token in data:
                    result["verified_baseline_token_found"] = True
                if bad_execution_token in data:
                    result["bad_execution_id_token_found"] = True

                for match in _ACCOUNTING_EPOCH_ID_PATTERN.finditer(data):
                    value = _decode(match.group(1)) if match.group(1) else None
                    if value and value not in accounting_ids:
                        accounting_ids.append(value)
                        if len(accounting_ids) >= 8:
                            break

                absolute += len(chunk)
                overlap = data[-OVERLAP_BYTES:]

        result["bytes_scanned"] = absolute
        result["scan_truncated"] = absolute < size
        result["accounting_epoch_ids_found"] = accounting_ids
        if epoch_offset is not None:
            block = _extract_epoch_block(path, epoch_offset)
            result["epoch_block"] = block
            result["verified_signature"] = bool(block.get("verified_signature"))
            result["clean_signature"] = bool(block.get("clean_signature"))
    except Exception as exc:
        result["read_error"] = f"{type(exc).__name__}: {exc}"

    return result


def _snapshot_manifest_summary() -> Dict[str, Any]:
    payload, error = _load_small_json(SNAPSHOT_MANIFEST)
    rows = payload.get("snapshots") if isinstance(payload.get("snapshots"), list) else []
    cleaned: List[Dict[str, Any]] = []
    for row in rows[:MAX_SNAPSHOT_ROWS]:
        if not isinstance(row, dict):
            continue
        cleaned.append(
            {
                "path": row.get("path"),
                "filename": row.get("filename"),
                "created_local": row.get("created_local"),
                "created_ts": row.get("created_ts"),
                "trades_count": row.get("trades_count"),
                "positions_count": row.get("positions_count"),
                "runner_timestamp_rank": row.get("runner_timestamp_rank"),
                "size_bytes": row.get("size_bytes"),
                "reason": row.get("reason"),
            }
        )
    return {
        "manifest_path": SNAPSHOT_MANIFEST,
        "manifest_exists": os.path.isfile(SNAPSHOT_MANIFEST),
        "read_error": error,
        "retained_rows_reported": len(rows),
        "rows_returned": cleaned,
    }


def _snapshot_candidates(manifest: Dict[str, Any]) -> List[str]:
    rows = manifest.get("rows_returned")
    rows = rows if isinstance(rows, list) else []
    candidates: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        created = str(row.get("created_local") or "")
        raw_trades = row.get("trades_count")
        try:
            trades = int(raw_trades) if raw_trades is not None else 999999
        except Exception:
            trades = 999999
        likely_recovery_snapshot = bool(
            trades <= 11 or created.startswith("2026-08-12")
        )
        if likely_recovery_snapshot and path and path not in candidates:
            candidates.append(path)
        if len(candidates) >= MAX_SNAPSHOT_FILES_SCANNED:
            break
    return candidates


def status_payload(core: Any = None) -> Dict[str, Any]:
    total_scanned = 0
    backup_rows: List[Dict[str, Any]] = []
    for path in BACKUP_FILES:
        row = _scan_state_file(path, MAX_TOTAL_BYTES - total_scanned)
        total_scanned += int(row.get("bytes_scanned") or 0)
        backup_rows.append(row)

    manifest = _snapshot_manifest_summary()
    snapshot_rows: List[Dict[str, Any]] = []
    for path in _snapshot_candidates(manifest):
        if total_scanned >= MAX_TOTAL_BYTES:
            break
        row = _scan_state_file(path, MAX_TOTAL_BYTES - total_scanned)
        total_scanned += int(row.get("bytes_scanned") or 0)
        snapshot_rows.append(row)

    all_rows = backup_rows + snapshot_rows
    verified_rows = [row for row in all_rows if bool(row.get("verified_signature"))]
    clean_rows = [row for row in all_rows if bool(row.get("clean_signature"))]
    token_only_rows = [
        row
        for row in all_rows
        if not bool(row.get("verified_signature"))
        and bool(row.get("verified_epoch_token_found"))
    ]

    if verified_rows:
        diagnosis = "verified_snapshot_backup_provenance_found"
        overall = "pass"
    elif token_only_rows:
        diagnosis = "verified_epoch_token_found_without_verified_epoch_block_signature"
        overall = "warn"
    elif clean_rows:
        diagnosis = "clean_epoch_backup_provenance_found_verified_snapshot_missing"
        overall = "warn"
    else:
        diagnosis = "verified_snapshot_not_found_in_retained_backup_or_targeted_snapshot_set"
        overall = "warn"

    return {
        "status": "ok",
        "overall": overall,
        "type": "verified_snapshot_backup_provenance_status",
        "version": VERSION,
        "generated_local": _now(core),
        "diagnosis": diagnosis,
        "verified_snapshot_backup_evidence_found": bool(verified_rows),
        "verified_signature_paths": [row.get("path") for row in verified_rows],
        "clean_signature_paths": [row.get("path") for row in clean_rows],
        "verified_token_only_paths": [row.get("path") for row in token_only_rows],
        "backup_files": backup_rows,
        "snapshot_manifest": manifest,
        "targeted_snapshot_files": snapshot_rows,
        "performance_contract": {
            "streaming_reads_only": True,
            "loads_whole_state_files_into_memory": False,
            "max_file_bytes": MAX_FILE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "bytes_scanned": total_scanned,
            "max_snapshot_files_scanned": MAX_SNAPSHOT_FILES_SCANNED,
            "startup_scans_backups": False,
        },
        "authority": {
            "reporting_only": True,
            "places_orders": False,
            "writes_files": False,
            "restores_backups": False,
            "deletes_or_prunes_snapshots": False,
            "repairs_historical_state": False,
            "rewrites_or_relabels_canonical_ledger": False,
            "clears_hard_halt": False,
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
        "startup_scans_backups": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {
            "status": "pending",
            "overall": "warn",
            "version": VERSION,
            "reason": "flask_app_missing",
        }
    if id(flask_app) not in _REGISTERED_APP_IDS:
        from flask import jsonify

        try:
            existing = {
                getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()
            }
        except Exception:
            existing = set()
        route = "/paper/verified-snapshot-backup-provenance-status"
        if route not in existing:
            flask_app.add_url_rule(
                route,
                "verified_snapshot_backup_provenance_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(id(flask_app))
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "route_registered": True,
        "startup_scans_backups": False,
    }
