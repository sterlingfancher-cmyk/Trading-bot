"""No-op persistence patch for state-journal repair.

This module used to monkey-patch state_journal_guard.status_payload and
repair_state_from_journal. That extra wrapper layer caused apply-time failures
when the next wrapper called status_payload(core=None) and the older patched
function did not accept the core keyword.

The active implementation now lives in state_journal_guard.py plus
state_journal_apply_guardrail.py. Keeping this module as a no-op preserves the
existing wsgi import path while removing the failing wrapper stack.
"""
from __future__ import annotations
from typing import Any, Dict

VERSION = "state-journal-persist-noop-2026-05-13"


def apply(guard_module: Any, core: Any | None = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": VERSION,
        "patched": False,
        "noop": True,
        "reason": "persistence wrapper disabled to prevent status_payload core keyword wrapper errors",
    }
