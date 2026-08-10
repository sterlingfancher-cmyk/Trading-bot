"""One-time lock/persistence safety shim for the clean accounting epoch cutover.

The cutover already owns the trade-journal mirror lock and state file lock. A
nested call back into ``trade_journal.mirror_state`` is unnecessary and could
reacquire the state file lock. The base migration also fsyncs backup copies via a
read-only descriptor and writes the primary state before all fallback backups are
rotated. This shim replaces only those migration helpers before cutover runs.

The clean state is first written to a fully fsynced candidate file, all active
fallback backups are replaced from that candidate, and only then is the primary
state path atomically swapped. If backup rotation fails, the contaminated primary
state remains intact and the hard-halted migration can be retried safely.

This file is intentionally temporary migration plumbing and can be removed once
the clean epoch has been established and validated.
"""
from __future__ import annotations

import os
import shutil
from typing import Any, Dict

VERSION = "clean-accounting-epoch-lock-safety-2026-08-10-v3-atomic-final-swap"
_APPLIED = False


def _safe_rotate_journal(_state: Dict[str, Any]) -> None:
    import clean_accounting_epoch as clean
    try:
        import trade_journal as tj
    except Exception:
        return

    empty_factory = getattr(tj, "_empty_journal", None)
    try:
        journal = empty_factory() if callable(empty_factory) else {
            "trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []
        }
    except Exception:
        journal = {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
    if not isinstance(journal, dict):
        journal = {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}

    journal["accounting_epoch_id"] = clean.TARGET_EPOCH_ID
    journal["clean_epoch_started_local"] = clean._now()  # noqa: SLF001 - deliberate one-time migration hook
    for attr in ("TRADE_JOURNAL_FILE", "TRADE_JOURNAL_BACKUP_FILE"):
        path = str(getattr(tj, attr, "") or "")
        if path:
            clean._atomic_json(path, journal)  # noqa: SLF001 - same atomic writer as cutover


def _safe_copy_file_atomic(src: str, dst: str) -> None:
    folder = os.path.dirname(dst)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = dst + ".tmp"
    shutil.copy2(src, tmp)
    with open(tmp, "rb+") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, dst)


def _safe_write_clean_state_and_backups(core: Any, state: Dict[str, Any]) -> str:
    import clean_accounting_epoch as clean

    state_file = str(getattr(core, "STATE_FILE", os.path.join(clean.STATE_DIR, "state.json")))
    candidate = state_file + ".clean_epoch_candidate"
    clean._atomic_json(candidate, state)  # noqa: SLF001 - fully fsynced migration candidate

    backups = []
    try:
        import state_io_hardening as sio
        backups.extend([
            getattr(sio, "STATE_BACKUP_LATEST", None),
            getattr(sio, "STATE_BACKUP_LARGEST", None),
            getattr(sio, "STATE_BACKUP_PREWRITE", None),
        ])
    except Exception:
        pass
    backups.append(state_file + ".bak")

    for path in backups:
        if path:
            _safe_copy_file_atomic(candidate, str(path))

    # Primary state changes only after every fallback copy is clean and durable.
    os.replace(candidate, state_file)
    try:
        folder = os.path.dirname(os.path.abspath(state_file)) or "."
        directory_fd = os.open(folder, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        pass
    return state_file


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    import clean_accounting_epoch as clean
    clean._rotate_journal = _safe_rotate_journal  # type: ignore[attr-defined]  # noqa: SLF001
    clean._copy_file_atomic = _safe_copy_file_atomic  # type: ignore[attr-defined]  # noqa: SLF001
    clean._write_clean_state_and_backups = _safe_write_clean_state_and_backups  # type: ignore[attr-defined]  # noqa: SLF001
    _APPLIED = True
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "applied": True,
        "nested_journal_mirror_disabled": True,
        "portable_backup_fsync": True,
        "primary_state_swapped_last": True,
        "authority": {
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "version": VERSION,
        "applied": _APPLIED,
        "nested_journal_mirror_disabled": _APPLIED,
        "portable_backup_fsync": _APPLIED,
        "primary_state_swapped_last": _APPLIED,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
