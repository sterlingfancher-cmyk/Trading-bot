"""Lock-safety adapter for the one-shot verified snapshot epoch recovery.

The recovery runs while clean_accounting_epoch._runtime_locks() already owns the
trade-journal mirror lock.  Calling trade_journal.mirror_state() from that
critical section can self-deadlock on production persistence.  This module
replaces only the recovery's journal rotation helper with a direct atomic empty
journal rotation that never re-enters the mirror path.

Paper/recovery plumbing only.  No account arithmetic, strategy, sizing, risk
limit, live authority, or ML authority is changed.
"""
from __future__ import annotations

import os
from typing import Any, Dict

VERSION = "verified-snapshot-epoch-recovery-lock-safety-2026-08-12-v1"
_APPLIED = False


def _safe_rotate_journal(state: Dict[str, Any]) -> None:
    try:
        import trade_journal as tj
        import verified_snapshot_epoch_recovery as recovery

        factory = getattr(tj, "_empty_journal", None)
        journal = factory() if callable(factory) else {
            "trades": [],
            "recent_trades": [],
            "snapshots": [],
            "event_hook_events": [],
        }
        if not isinstance(journal, dict):
            journal = {
                "trades": [],
                "recent_trades": [],
                "snapshots": [],
                "event_hook_events": [],
            }
        journal["accounting_epoch_id"] = recovery.TARGET_EPOCH_ID
        journal["verified_snapshot_epoch_started_local"] = recovery._now()
        journal["lock_safe_rotation_version"] = VERSION

        for attr in ("TRADE_JOURNAL_FILE", "TRADE_JOURNAL_BACKUP_FILE"):
            path = str(getattr(tj, attr, "") or "")
            if path:
                recovery._atomic_json(path, journal)
    except Exception:
        # Recovery already archives the pre-cutover persistence before mutation;
        # journal rotation failure must not re-enter the mirror lock or hang boot.
        return


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import verified_snapshot_epoch_recovery as recovery
        recovery._rotate_journal = _safe_rotate_journal
        _APPLIED = True
        return {
            "status": "ok",
            "overall": "pass",
            "version": VERSION,
            "patched": True,
            "nested_journal_mirror_disabled": True,
        }
    except Exception as exc:
        return {
            "status": "error",
            "overall": "fail",
            "version": VERSION,
            "error": f"{type(exc).__name__}: {exc}",
        }


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "version": VERSION,
        "nested_journal_mirror_disabled": _APPLIED,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
