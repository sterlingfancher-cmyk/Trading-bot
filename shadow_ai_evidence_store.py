"""Atomic bounded persistence for non-authoritative shadow-AI evidence.

The store is separate from portfolio state and the canonical execution ledger.
It accepts only the already-sanitized reviewer record, keeps a bounded snapshot,
and fails closed on checksum or identity conflicts.  No trading code reads this
file as an execution input.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


VERSION = "shadow-ai-evidence-store-2026-09-03-v1"
SCHEMA_VERSION = "shadow-ai-evidence-v1"
FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "full_prompt",
    "prompt",
    "raw_reasoning",
    "raw_source_body",
    "secret",
}


@dataclass(frozen=True, slots=True)
class EvidenceStoreConfig:
    path: str
    max_records: int = 500
    max_record_bytes: int = 32_000
    max_store_bytes: int = 8_000_000

    def __post_init__(self) -> None:
        if not str(self.path).strip():
            raise ValueError("path is required")
        if not 1 <= int(self.max_records) <= 5_000:
            raise ValueError("max_records must be in [1, 5000]")
        if not 1_024 <= int(self.max_record_bytes) <= 128_000:
            raise ValueError("max_record_bytes must be in [1024, 128000]")
        if not 65_536 <= int(self.max_store_bytes) <= 32_000_000:
            raise ValueError("max_store_bytes must be in [65536, 32000000]")


def default_evidence_path() -> str:
    root = (
        os.environ.get("STATE_DIR")
        or os.environ.get("PERSISTENT_STATE_DIR")
        or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
        or "."
    )
    return str(Path(root) / "shadow_ai_research_evidence.json")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _checksum(records: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical_json(records).encode("utf-8")).hexdigest()


def _forbidden_key(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if (
                normalized in FORBIDDEN_KEYS
                or normalized.endswith(
                    (
                        "_api_key",
                        "_authorization",
                        "_secret",
                        "_password",
                        "_credential",
                        "_prompt",
                    )
                )
                or normalized in {"access_token", "refresh_token", "bearer_token"}
            ):
                return normalized
            nested = _forbidden_key(item)
            if nested:
                return nested
    elif isinstance(value, (list, tuple)):
        for item in value:
            nested = _forbidden_key(item)
            if nested:
                return nested
    return None


def _identity(record: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("cycle_id") or "").strip(),
        str(record.get("candidate_id") or "").strip(),
        str(record.get("input_fingerprint") or "").strip(),
    )


class ShadowAIEvidenceStore:
    def __init__(self, config: EvidenceStoreConfig) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._records: list[dict[str, Any]] = []
        self._loaded = False
        self._integrity_error: str | None = None
        self._writes = 0
        self._deduplicated = 0
        self._rejected = 0

    def load(self) -> dict[str, Any]:
        with self._lock:
            path = Path(self.config.path)
            if not path.exists():
                self._records = []
                self._loaded = True
                self._integrity_error = None
                return self.status_payload()
            try:
                if path.stat().st_size > self.config.max_store_bytes:
                    raise ValueError("store_size_bound_exceeded")
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("envelope_not_mapping")
                if payload.get("schema_version") != SCHEMA_VERSION:
                    raise ValueError("schema_version_mismatch")
                records = payload.get("records")
                if not isinstance(records, list):
                    raise ValueError("records_not_list")
                if len(records) > self.config.max_records:
                    raise ValueError("retention_bound_exceeded")
                if not all(isinstance(row, dict) for row in records):
                    raise ValueError("record_not_mapping")
                if any(
                    len(_canonical_json(row).encode("utf-8"))
                    > self.config.max_record_bytes
                    for row in records
                ):
                    raise ValueError("record_size_bound_exceeded")
                if payload.get("checksum") != _checksum(records):
                    raise ValueError("checksum_mismatch")
                identities = [_identity(row) for row in records]
                if any(not all(identity) for identity in identities):
                    raise ValueError("record_identity_missing")
                if len(identities) != len(set(identities)):
                    raise ValueError("duplicate_record_identity")
                if any(_forbidden_key(row) for row in records):
                    raise ValueError("forbidden_content_key")
                self._records = json.loads(_canonical_json(records))
                self._loaded = True
                self._integrity_error = None
            except Exception as exc:
                self._records = []
                self._loaded = True
                self._integrity_error = f"{type(exc).__name__}:{exc}"
            return self.status_payload()

    def append(self, record: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not self._loaded:
                self.load()
            if self._integrity_error:
                self._rejected += 1
                return {"status": "rejected", "reason": "store_integrity_error"}
            if not isinstance(record, Mapping):
                self._rejected += 1
                return {"status": "rejected", "reason": "record_not_mapping"}
            identity = _identity(record)
            if not all(identity):
                self._rejected += 1
                return {"status": "rejected", "reason": "record_identity_missing"}
            forbidden = _forbidden_key(record)
            if forbidden:
                self._rejected += 1
                return {"status": "rejected", "reason": f"forbidden_key:{forbidden}"}
            try:
                frozen = _canonical_json(record)
            except (TypeError, ValueError):
                self._rejected += 1
                return {"status": "rejected", "reason": "record_not_json_safe"}
            if len(frozen.encode("utf-8")) > self.config.max_record_bytes:
                self._rejected += 1
                return {"status": "rejected", "reason": "record_too_large"}
            normalized = json.loads(frozen)
            existing = [row for row in self._records if _identity(row) == identity]
            if existing:
                if _canonical_json(existing[0]) == frozen:
                    self._deduplicated += 1
                    return {"status": "deduplicated", "record_count": len(self._records)}
                self._rejected += 1
                return {"status": "rejected", "reason": "contradictory_record_identity"}
            candidate = (self._records + [normalized])[-self.config.max_records :]
            try:
                self._write(candidate)
            except Exception as exc:
                self._rejected += 1
                return {"status": "rejected", "reason": f"write_failed:{type(exc).__name__}"}
            self._records = candidate
            self._writes += 1
            return {"status": "persisted", "record_count": len(self._records)}

    def records_snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            if not self._loaded:
                self.load()
            return tuple(json.loads(_canonical_json(row)) for row in self._records)

    def status_payload(self) -> dict[str, Any]:
        with self._lock:
            path = Path(self.config.path)
            return {
                "status": "ok" if not self._integrity_error else "error",
                "overall": "pass" if not self._integrity_error else "warn",
                "type": "shadow_ai_evidence_store_status",
                "version": VERSION,
                "schema_version": SCHEMA_VERSION,
                "loaded": self._loaded,
                "integrity_valid": self._integrity_error is None,
                "integrity_error": self._integrity_error,
                "record_count": len(self._records),
                "max_records": self.config.max_records,
                "max_record_bytes": self.config.max_record_bytes,
                "max_store_bytes": self.config.max_store_bytes,
                "file_exists": path.exists(),
                "file_bytes": path.stat().st_size if path.exists() else 0,
                "restart_loadable": bool(self._loaded and not self._integrity_error),
                "writes": self._writes,
                "deduplicated": self._deduplicated,
                "rejected": self._rejected,
                "authority": {
                    "research_evidence_only": True,
                    "separate_from_portfolio_state": True,
                    "separate_from_canonical_ledger": True,
                    "changes_trading_behavior": False,
                    "execution_input": False,
                    "places_or_cancels_orders": False,
                },
            }

    def _write(self, records: list[dict[str, Any]]) -> None:
        path = Path(self.config.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "version": VERSION,
            "checksum": _checksum(records),
            "records": records,
        }
        data = (_canonical_json(envelope) + "\n").encode("utf-8")
        if len(data) > self.config.max_store_bytes:
            raise ValueError("store_size_bound_exceeded")
        temporary = path.with_name(path.name + ".tmp")
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
