"""Exact metadata contract for the governed Issue #84 v5 paper restart."""
from __future__ import annotations

from typing import Any, Mapping


VERSION = "governed-v5-paper-restart-2026-09-25-v1"
TARGET_EPOCH_ID = "stable-paper-v5-20260914-issue222-flat-successor01"
ACTIVATION_DECISION_ID = "issue84-governed-paper-restart-2026-09-25"
ACTIVATION_REVIEW_REFERENCE = "issue-84-comment-5802294002"


def release_metadata_exact(epoch: Mapping[str, Any]) -> bool:
    return bool(
        str(epoch.get("id") or epoch.get("epoch_id") or "") == TARGET_EPOCH_ID
        and epoch.get("validation_hold") is False
        and epoch.get("validation_released") is True
        and str(epoch.get("validation_release_status") or "")
        == "governed_paper_restart_active"
        and str(epoch.get("validation_release_version") or "") == VERSION
        and str(epoch.get("restart_activation_decision_id") or "")
        == ACTIVATION_DECISION_ID
        and str(epoch.get("restart_activation_review_reference") or "")
        == ACTIVATION_REVIEW_REFERENCE
    )
