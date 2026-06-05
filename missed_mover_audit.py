"""Safe fallback for missed mover audit.

The full speculative momentum shadow diagnostics were not installed because the connector truncated file writes.
This fallback is valid Python and advisory-only.
"""
VERSION = "missed-mover-audit-safe-fallback-2026-06-05"


def apply(core=None):
    return {
        "status": "not_installed",
        "overall": "warn",
        "type": "missed_mover_audit_status",
        "version": VERSION,
        "advisory_only": True,
        "authority_changed": False,
        "reason": "safe fallback only; full shadow speculative