import json
import os
import tempfile
import hashlib
import time
from typing import Callable, Dict, Any, Optional

"""
Minimal canonical execution ledger wrapper with a small fail-closed commit/recovery
metadata mechanism. This module purposely implements only the smallest, testable
surface required by Issue #172's narrow scope:

- append(row, mirror_fn, ledger_dir=None)
    Append a canonical JSON line to a ledger file, fsync it, record deterministic
    pending commit metadata, then call the provided mirror_fn(row) to update the
    prior state mirror. If mirror_fn raises, the pending metadata remains on
    disk allowing deterministic detection on restart.

- reconcile(mirror_fn, ledger_dir=None)
    If a pending commit metadata file exists, attempt safe deterministic
    reconciliation. Reconciliation will only auto-apply when the pending
    metadata indicates it is safe (currently: row contains a deterministic
    execution_id). Otherwise it fails-closed by raising a RuntimeError so a
    human/operator can inspect immutable canonical rows instead of risking
    duplicate economics.

Safety boundaries / rationale:
- We never delete or rewrite canonical ledger rows. The ledger is append-only
  (ledger.jsonl). Our metadata files are small sidecar files used only to
  detect and reconcile an interrupted append->state-mirror window.
- Automatic reconciliation is only performed when the row includes an
  explicit, deterministic execution_id (string/number). This makes the
  state-mirror invocation idempotent-capable and prevents blind duplicate
  economics when the existing record_trade implementation is not guaranteed
  idempotent by execution_id.
- If safe deterministic reconciliation cannot be performed (missing
  execution_id), reconcile() raises and leaves the sidecar so an operator can
  run a governed recovery path. This is the intended fail-closed behavior.

This module intentionally avoids any call to real broker/order APIs and does
not change any risk/state policy. It is self-contained and focused on
append-without-state-mirror detection and limited reconciliation.
"""

LEDGER_FILENAME = "ledger.jsonl"
PENDING_META = "ledger.pending.json"
COMMITTED_META = "ledger.committed.json"


def _ensure_dir(path: Optional[str]) -> str:
    if path is None:
        path = os.getcwd()
    os.makedirs(path, exist_ok=True)
    return path


def _row_digest(row: Dict[str, Any]) -> str:
    # Deterministic JSON serialization + sha256
    raw = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _atomic_write(path: str, data: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    os.close(fd)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _fsync_fileobj(f):
    try:
        f.flush()
        os.fsync(f.fileno())
    except Exception:
        # fsync best-effort; callers expect exception on mirror failure, not on fsync.
        pass


def append(row: Dict[str, Any], mirror_fn: Callable[[Dict[str, Any]], Any], ledger_dir: Optional[str] = None) -> None:
    """
    Append a canonical row atomically to the ledger file, fsync it, write a
    deterministic pending metadata record, then call mirror_fn(row). If
    mirror_fn raises, the pending metadata file remains for deterministic
    recovery.

    Requirements for safe automatic recovery: row should include a stable
    'execution_id' field (string or number). If absent, reconciliation will
    be recorded as unsafe and reconcile() will fail-closed.
    """
    ledger_dir = _ensure_dir(ledger_dir)
    ledger_path = os.path.join(ledger_dir, LEDGER_FILENAME)
    pending_path = os.path.join(ledger_dir, PENDING_META)
    committed_path = os.path.join(ledger_dir, COMMITTED_META)

    # Normalize row to a real JSON object
    if not isinstance(row, dict):
        raise TypeError("row must be a dict")

    # Append canonical row
    line = json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n"
    # Open in binary to be explicit about fsync (we write utf-8 bytes)
    bline = line.encode("utf-8")
    with open(ledger_path, "ab") as f:
        f.write(bline)
        # Ensure the line is durable on disk before we proceed to state mirror
        _fsync_fileobj(f)

    # Compose deterministic pending metadata
    digest = _row_digest(row)
    exec_id = row.get("execution_id")
    reconcile_safe = exec_id is not None
    meta = {
        "execution_id": exec_id,
        "row_digest": digest,
        "timestamp": int(time.time()),
        "reconcile_safe": bool(reconcile_safe),
    }

    # Write pending metadata atomically
    _atomic_write(pending_path, json.dumps(meta, sort_keys=True, ensure_ascii=False))

    # Now call mirror_fn. If it raises, pending metadata remains.
    try:
        mirror_fn(row)
    except Exception:
        # Intentionally fail-closed: leave pending metadata for deterministic
        # recovery. Re-raise so the caller sees the mirror failure.
        raise

    # Mirror succeeded; remove pending and write committed metadata
    try:
        if os.path.exists(pending_path):
            os.remove(pending_path)
    except Exception:
        # best-effort; do not fail the successful append+mirror due to a cleanup
        pass

    _atomic_write(committed_path, json.dumps({**meta, "committed_at": int(time.time())}, sort_keys=True, ensure_ascii=False))


def _read_last_row(ledger_path: str) -> Dict[str, Any]:
    # Read last non-empty line from ledger.jsonl
    if not os.path.exists(ledger_path):
        raise FileNotFoundError("ledger file not found")
    with open(ledger_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        if pos == 0:
            raise ValueError("ledger is empty")
        # Scan backwards for newline
        buffer = bytearray()
        while pos > 0:
            pos -= 1
            f.seek(pos)
            ch = f.read(1)
            if ch == b"\n" and buffer:
                break
            if ch != b"\n":
                buffer.extend(ch)
        # buffer currently contains the last line in reverse
        last = bytes(reversed(buffer)).decode("utf-8", errors="replace")
        return json.loads(last)


def reconcile(mirror_fn: Callable[[Dict[str, Any]], Any], ledger_dir: Optional[str] = None) -> None:
    """
    If a pending commit metadata file exists, attempt deterministic reconciliation.

    - Validates the pending metadata against the actual last appended canonical
      row (digest match).
    - If reconcile_safe is True (execution_id present), calls mirror_fn(row).
    - If mirror_fn succeeds, clears pending and writes committed metadata.
    - If reconcile_safe is False, raises RuntimeError (fail-closed).
    """
    ledger_dir = _ensure_dir(ledger_dir)
    ledger_path = os.path.join(ledger_dir, LEDGER_FILENAME)
    pending_path = os.path.join(ledger_dir, PENDING_META)
    committed_path = os.path.join(ledger_dir, COMMITTED_META)

    if not os.path.exists(pending_path):
        return

    with open(pending_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Load last row and validate digest
    last_row = _read_last_row(ledger_path)
    actual_digest = _row_digest(last_row)
    if actual_digest != meta.get("row_digest"):
        # Digest mismatch between pending metadata and last canonical row is
        # a serious integrity issue. Fail-closed and preserve evidence.
        raise RuntimeError("pending metadata does not match last ledger row (digest mismatch)")

    if not bool(meta.get("reconcile_safe", False)):
        # We cannot safely auto-apply; fail-closed to avoid duplicate economics.
        raise RuntimeError("pending ledger row is not marked reconcile_safe; manual recovery required")

    # Attempt to call mirror_fn. If it raises, leave pending for operator.
    try:
        mirror_fn(last_row)
    except Exception:
        raise

    # Mirror succeeded; remove pending and write committed metadata
    try:
        if os.path.exists(pending_path):
            os.remove(pending_path)
    except Exception:
        pass

    _atomic_write(committed_path, json.dumps({**meta, "recovered_at": int(time.time())}, sort_keys=True, ensure_ascii=False))
