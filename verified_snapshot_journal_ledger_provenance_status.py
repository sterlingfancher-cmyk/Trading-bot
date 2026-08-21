"""Read-only journal/ledger provenance probe for the Aug. 12 verified epoch.

Issue #82 evidence shows the active paper state, dedicated recovery markers,
forensic archives, retained state backups, and retained state snapshots no longer
carry the verified-snapshot epoch.  This probe asks the next narrower question:
did the independently persisted trade journal retain the verified epoch marker,
and if so, is the current append-only canonical ledger chronologically downstream
of that cutover?

The probe is observational only.  Startup ``apply()`` is constant-time.  File
reads occur only when the explicit status endpoint is requested.  It never calls
journal sync/seed, recovery routines, state writers, or ledger append functions.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "verified-snapshot-journal-ledger-provenance-2026-08-21-v1"
VERIFIED_EPOCH_ID = "stable-paper-v2-20260812-verified01"
CLEAN_EPOCH_ID = "stable-paper-v1-20260810-clean01"

STATE_DIR = (
    os.environ.get("STATE_DIR")
    or os.environ.get("PERSISTENT_STATE_DIR")
    or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    or "."
)
JOURNAL_FILES = (
    os.path.join(STATE_DIR, "trade_journal.json"),
    os.path.join(STATE_DIR, "trade_journal_backup.json"),
)
LEDGER_FILE = os.path.join(STATE_DIR, "canonical_execution_ledger.jsonl")

JOURNAL_KEYS = {
    "accounting_epoch_id",
    "verified_snapshot_epoch_started_local",
    "clean_epoch_started_local",
    "created_local",
    "updated_local",
    "version",
}
MAX_JOURNAL_BYTES_PER_FILE = 128 * 1024 * 1024
MAX_LEDGER_BYTES = 32 * 1024 * 1024
MAX_LEDGER_LINE_BYTES = 2 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024

_REGISTERED_APP_IDS: set[int] = set()


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _mtime_local(path: str) -> str | None:
    try:
        return dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except Exception:
        return None


def _decode_json_string(raw: bytearray) -> str | None:
    try:
        # Reuse the JSON decoder so escaped quotes/backslashes are interpreted
        # exactly as JSON rather than with a hand-written unescape table.
        return json.loads(b'"' + bytes(raw) + b'"'.decode("utf-8"))
    except Exception:
        try:
            return bytes(raw).decode("utf-8", errors="replace")
        except Exception:
            return None


def _stream_top_level_strings(path: str) -> Dict[str, Any]:
    """Extract selected string/null scalar keys from the root JSON object only."""
    exists = os.path.isfile(path)
    size = int(os.path.getsize(path)) if exists else 0
    out: Dict[str, Any] = {
        "path": path,
        "exists": exists,
        "size_bytes": size,
        "modified_local": _mtime_local(path) if exists else None,
        "bytes_scanned": 0,
        "scan_truncated": False,
        "read_error": None,
        "top_level": {},
    }
    if not exists or size <= 0:
        return out

    budget = min(size, MAX_JOURNAL_BYTES_PER_FILE)
    nesting = 0
    in_string = False
    escaped = False
    string_role: str | None = None
    string_buf = bytearray()
    current_key: str | None = None
    expecting_key = False
    expecting_value = False
    primitive_buf = bytearray()
    primitive_active = False
    scanned = 0

    def finish_primitive() -> None:
        nonlocal primitive_active, primitive_buf, current_key, expecting_value
        if not primitive_active:
            return
        token = bytes(primitive_buf).strip().decode("utf-8", errors="replace")
        if current_key in JOURNAL_KEYS:
            if token == "null":
                out["top_level"][current_key] = None
            elif token in {"true", "false"}:
                out["top_level"][current_key] = token == "true"
            else:
                out["top_level"][current_key] = token
        primitive_active = False
        primitive_buf = bytearray()
        current_key = None
        expecting_value = False

    try:
        with open(path, "rb") as handle:
            while scanned < budget:
                chunk = handle.read(min(CHUNK_BYTES, budget - scanned))
                if not chunk:
                    break
                scanned += len(chunk)
                for value in chunk:
                    if in_string:
                        if escaped:
                            string_buf.append(value)
                            escaped = False
                            continue
                        if value == 0x5C:  # backslash
                            string_buf.append(value)
                            escaped = True
                            continue
                        if value == 0x22:  # quote
                            text = _decode_json_string(string_buf)
                            in_string = False
                            string_buf = bytearray()
                            if string_role == "key":
                                current_key = text
                                expecting_key = False
                            elif string_role == "value":
                                if current_key in JOURNAL_KEYS:
                                    out["top_level"][current_key] = text
                                current_key = None
                                expecting_value = False
                            string_role = None
                            continue
                        string_buf.append(value)
                        continue

                    if primitive_active:
                        if nesting == 1 and value in (0x2C, 0x7D):  # comma or }
                            finish_primitive()
                            if value == 0x2C:
                                expecting_key = True
                            else:
                                nesting -= 1
                            continue
                        primitive_buf.append(value)
                        continue

                    if value == 0x22:  # quote
                        if nesting == 1 and expecting_key:
                            in_string = True
                            string_role = "key"
                            string_buf = bytearray()
                        elif nesting == 1 and expecting_value:
                            in_string = True
                            string_role = "value"
                            string_buf = bytearray()
                        else:
                            # A nested string is irrelevant; still consume it so
                            # braces/commas inside the string do not affect depth.
                            in_string = True
                            string_role = "ignore"
                            string_buf = bytearray()
                        continue

                    if value in (0x7B, 0x5B):  # { or [
                        nesting += 1
                        if nesting == 1:
                            expecting_key = True
                        continue
                    if value in (0x7D, 0x5D):  # } or ]
                        if nesting == 1 and expecting_value:
                            finish_primitive()
                        nesting = max(0, nesting - 1)
                        if nesting == 0:
                            break
                        continue
                    if nesting != 1:
                        continue
                    if value == 0x3A and current_key is not None:  # colon
                        expecting_value = True
                        continue
                    if value == 0x2C:  # comma
                        current_key = None
                        expecting_value = False
                        expecting_key = True
                        continue
                    if expecting_value and value not in (0x20, 0x09, 0x0A, 0x0D):
                        # Root scalar that is not a JSON string.
                        primitive_active = True
                        primitive_buf = bytearray([value])

                if nesting == 0 and scanned > 0:
                    break
        if primitive_active:
            finish_primitive()
    except Exception as exc:
        out["read_error"] = f"{type(exc).__name__}: {exc}"

    out["bytes_scanned"] = scanned
    out["scan_truncated"] = scanned < size and nesting != 0
    epoch = out["top_level"].get("accounting_epoch_id")
    out["verified_epoch_top_level"] = epoch == VERIFIED_EPOCH_ID
    out["clean_epoch_top_level"] = epoch == CLEAN_EPOCH_ID
    out["verified_start_local"] = out["top_level"].get(
        "verified_snapshot_epoch_started_local"
    )
    return out


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _parse_local_timestamp(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if len(text) < 19:
        return None
    try:
        return dt.datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _ledger_summary(path: str) -> Dict[str, Any]:
    exists = os.path.isfile(path)
    size = int(os.path.getsize(path)) if exists else 0
    result: Dict[str, Any] = {
        "path": path,
        "exists": exists,
        "size_bytes": size,
        "modified_local": _mtime_local(path) if exists else None,
        "bytes_scanned": 0,
        "scan_truncated": False,
        "row_count": 0,
        "parse_error_count": 0,
        "chain_error_count": 0,
        "chain_valid": True,
        "errors": [],
        "epoch_counts": {},
        "first_execution_id": None,
        "last_execution_id": None,
        "first_recorded_local": None,
        "last_recorded_local": None,
        "recorded_local_parseable_count": 0,
        "recorded_local_unparseable_count": 0,
        "recorded_local_values": [],
    }
    if not exists or size <= 0:
        return result

    prev_hash = ""
    total = 0
    rows = 0
    errors: List[str] = []
    epoch_counts: Dict[str, int] = {}
    timestamps: List[str] = []
    try:
        with open(path, "rb") as handle:
            for line_no, raw in enumerate(handle, start=1):
                if total >= MAX_LEDGER_BYTES:
                    result["scan_truncated"] = True
                    break
                total += len(raw)
                if total > MAX_LEDGER_BYTES:
                    result["scan_truncated"] = True
                    break
                if len(raw) > MAX_LEDGER_LINE_BYTES:
                    errors.append(f"line_{line_no}:line_too_large")
                    continue
                text = raw.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text.decode("utf-8"))
                except Exception as exc:
                    errors.append(f"line_{line_no}:{type(exc).__name__}")
                    continue
                if not isinstance(row, dict):
                    errors.append(f"line_{line_no}:non_dict")
                    continue

                rows += 1
                expected_prev = str(row.get("previous_event_hash") or "")
                if expected_prev != prev_hash:
                    errors.append(f"line_{line_no}:previous_hash_mismatch")
                body = dict(row)
                stored_hash = str(body.pop("event_hash", "") or "")
                body.pop("previous_event_hash", None)
                expected_hash = hashlib.sha256(
                    (prev_hash + "|" + _canonical_json(body)).encode("utf-8")
                ).hexdigest()
                if not stored_hash or stored_hash != expected_hash:
                    errors.append(f"line_{line_no}:event_hash_mismatch")
                prev_hash = stored_hash

                epoch = str(row.get("accounting_epoch_id") or "missing")
                epoch_counts[epoch] = epoch_counts.get(epoch, 0) + 1
                execution_id = row.get("execution_id")
                recorded = row.get("recorded_local")
                if result["first_execution_id"] is None:
                    result["first_execution_id"] = execution_id
                    result["first_recorded_local"] = recorded
                result["last_execution_id"] = execution_id
                result["last_recorded_local"] = recorded
                if recorded is not None and len(timestamps) < 256:
                    timestamps.append(str(recorded))
    except Exception as exc:
        errors.append(f"read:{type(exc).__name__}:{exc}")

    parse_errors = [e for e in errors if "hash_mismatch" not in e]
    chain_errors = [e for e in errors if "hash_mismatch" in e]
    parseable = sum(1 for value in timestamps if _parse_local_timestamp(value) is not None)
    result.update(
        {
            "bytes_scanned": min(total, MAX_LEDGER_BYTES),
            "row_count": rows,
            "parse_error_count": len(parse_errors),
            "chain_error_count": len(chain_errors),
            "chain_valid": not errors and not result["scan_truncated"],
            "errors": errors[:8],
            "epoch_counts": dict(sorted(epoch_counts.items())),
            "recorded_local_parseable_count": parseable,
            "recorded_local_unparseable_count": len(timestamps) - parseable,
            "recorded_local_values": timestamps,
        }
    )
    return result


def _chronology(ledger: Dict[str, Any], verified_start: Any) -> Dict[str, Any]:
    start_dt = _parse_local_timestamp(verified_start)
    values = ledger.get("recorded_local_values")
    values = values if isinstance(values, list) else []
    parsed = [_parse_local_timestamp(v) for v in values]
    parseable = [value for value in parsed if value is not None]
    all_parseable = bool(values) and len(parseable) == len(values)
    all_after = bool(start_dt is not None and all_parseable) and all(
        value >= start_dt for value in parseable
    )
    return {
        "verified_start_local": verified_start,
        "verified_start_parseable": start_dt is not None,
        "ledger_timestamp_count": len(values),
        "ledger_all_timestamps_parseable": all_parseable,
        "all_ledger_rows_at_or_after_verified_start": all_after,
        "earliest_ledger_recorded_local": (
            min(parseable).strftime("%Y-%m-%d %H:%M:%S") if parseable else None
        ),
        "latest_ledger_recorded_local": (
            max(parseable).strftime("%Y-%m-%d %H:%M:%S") if parseable else None
        ),
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    journals = [_stream_top_level_strings(path) for path in JOURNAL_FILES]
    verified_journals = [row for row in journals if row.get("verified_epoch_top_level")]
    verified_starts = [
        row.get("verified_start_local")
        for row in verified_journals
        if row.get("verified_start_local")
    ]
    ledger = _ledger_summary(LEDGER_FILE)

    verified_start = min(
        verified_starts,
        key=lambda value: _parse_local_timestamp(value) or dt.datetime.max,
    ) if verified_starts else None
    chronology = _chronology(ledger, verified_start)

    if verified_journals and verified_start and ledger.get("chain_valid") and chronology.get(
        "all_ledger_rows_at_or_after_verified_start"
    ):
        diagnosis = "verified_journal_cutover_with_post_cutover_ledger_provenance_found"
        overall = "pass"
    elif verified_journals and not verified_start:
        diagnosis = "verified_journal_epoch_found_without_verified_start_time"
        overall = "warn"
    elif verified_journals and not ledger.get("chain_valid"):
        diagnosis = "verified_journal_epoch_found_but_canonical_ledger_not_valid"
        overall = "fail"
    elif verified_journals:
        diagnosis = "verified_journal_epoch_found_but_ledger_chronology_not_proven"
        overall = "warn"
    elif any(row.get("verified_start_local") for row in journals):
        diagnosis = "verified_journal_start_marker_found_without_verified_epoch_identity"
        overall = "warn"
    else:
        diagnosis = "verified_journal_provenance_not_found"
        overall = "warn"

    # Keep the response compact: chronology has already consumed the timestamp
    # list; operators need boundaries/counts, not every ledger timestamp.
    ledger.pop("recorded_local_values", None)

    return {
        "status": "ok",
        "overall": overall,
        "type": "verified_snapshot_journal_ledger_provenance_status",
        "version": VERSION,
        "generated_local": _now(core),
        "diagnosis": diagnosis,
        "verified_journal_epoch_found": bool(verified_journals),
        "verified_journal_paths": [row.get("path") for row in verified_journals],
        "verified_snapshot_epoch_started_local": verified_start,
        "journal_files": journals,
        "canonical_ledger": ledger,
        "chronology": chronology,
        "performance_contract": {
            "startup_scans_files": False,
            "journal_streaming_reads_only": True,
            "ledger_line_streaming_only": True,
            "max_journal_bytes_per_file": MAX_JOURNAL_BYTES_PER_FILE,
            "max_ledger_bytes": MAX_LEDGER_BYTES,
        },
        "authority": {
            "reporting_only": True,
            "places_orders": False,
            "writes_files": False,
            "syncs_or_seeds_journal": False,
            "restores_backups": False,
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
    # Called during deterministic startup: deliberately perform no file scans.
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "installed": True,
        "startup_scans_files": False,
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
        route = "/paper/verified-snapshot-journal-ledger-provenance-status"
        if route not in existing:
            flask_app.add_url_rule(
                route,
                "verified_snapshot_journal_ledger_provenance_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(id(flask_app))
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "route_registered": True,
        "startup_scans_files": False,
    }
