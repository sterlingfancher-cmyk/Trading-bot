"""One-link check patch.

Keeps the user's daily testing flow to one URL: /paper/self-check.
Adds /paper/journal-truth-status into the light self-check set without requiring
Sterling to manually test another endpoint after each deploy.
"""
from __future__ import annotations

VERSION = "one-link-journal-truth-check-2026-05-11"


def apply(self_check_module=None):
    try:
        if self_check_module is None:
            import self_check as self_check_module  # type: ignore[no-redef]
        endpoint = {"path": "/paper/journal-truth-status", "category": "journal", "required": True}
        light = getattr(self_check_module, "LIGHT_ENDPOINTS", None)
        if isinstance(light, list) and not any(item.get("path") == endpoint["path"] for item in light if isinstance(item, dict)):
            # Put it near the journal endpoints so the dashboard stays logical.
            insert_at = len(light)
            for idx, item in enumerate(light):
                if isinstance(item, dict) and item.get("path") == "/paper/trade-event-hook-status":
                    insert_at = idx + 1
                    break
            light.insert(insert_at, endpoint)
        return {"status": "ok", "version": VERSION, "journal_truth_in_self_check": True}
    except Exception as exc:
        return {"status": "error", "version": VERSION, "journal_truth_in_self_check": False, "error": str(exc)}


def register_routes(flask_app=None, module=None):
    # Nothing new to register. This module patches self_check's existing route list.
    try:
        import self_check
        return apply(self_check)
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": str(exc)}
