"""Epoch-safe timestamp guard for the paper underdeployment spacing gate.

The persisted paper position timestamps are Unix epochs.  The legacy helper used
``datetime.fromtimestamp`` without a timezone, which interpreted the epoch in the
Railway container timezone and later relabeled that wall clock as Central time.
That could move the recorded entry into the future and clamp the elapsed spacing
to zero.  This module patches only the timestamp parser used by
``paper_underdeployment_repair``; it does not alter the configured spacing,
entry quality, sizing, risk controls, live authority, or order execution.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import sys
import threading
import time
from typing import Any, Dict

VERSION = "paper-underdeployment-time-guard-2026-08-04-v1-epoch-aware"
_LOCK = threading.RLock()
_PATCHED = False
_STARTED = False
_STATUS: Dict[str, Any] = {
    "version": VERSION,
    "status": "pending",
    "patched": False,
    "target": "paper_underdeployment_repair._parse_time",
}


def _epoch_datetime(value: Any) -> dt.datetime | None:
    try:
        number = float(value)
        if not math.isfinite(number):
            return None
        # Accept both seconds and millisecond Unix epochs without guessing for
        # ordinary date-like strings.
        if abs(number) >= 100_000_000_000:
            number /= 1000.0
        return dt.datetime.fromtimestamp(number, tz=dt.timezone.utc)
    except Exception:
        return None


def parse_time(value: Any) -> dt.datetime | None:
    """Parse persisted timestamps while preserving their timezone semantics."""
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _epoch_datetime(value)

    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return _epoch_datetime(text)

    normalized = text.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    # Existing local telemetry commonly includes a Central abbreviation.  Keep
    # those values naive so the caller can attach the runtime's local timezone.
    normalized = normalized.split(" CDT")[0].split(" CST")[0]
    for candidate in (normalized, normalized[:19]):
        try:
            return dt.datetime.fromisoformat(candidate)
        except Exception:
            pass
    return None


def apply() -> Dict[str, Any]:
    global _PATCHED, _STATUS
    with _LOCK:
        module = sys.modules.get("paper_underdeployment_repair")
        if module is None:
            _STATUS = {
                "version": VERSION,
                "status": "pending",
                "patched": False,
                "reason": "target_module_not_loaded",
                "target": "paper_underdeployment_repair._parse_time",
            }
            return dict(_STATUS)

        current = getattr(module, "_parse_time", None)
        if getattr(current, "_paper_underdeployment_time_guard_version", None) != VERSION:
            parse_time._paper_underdeployment_time_guard_version = VERSION  # type: ignore[attr-defined]
            parse_time._paper_underdeployment_time_guard_original = current  # type: ignore[attr-defined]
            setattr(module, "_parse_time", parse_time)
        _PATCHED = True
        _STATUS = {
            "version": VERSION,
            "status": "ok",
            "overall": "pass",
            "patched": True,
            "target": "paper_underdeployment_repair._parse_time",
            "unix_epochs_are_utc_aware": True,
            "spacing_threshold_changed": False,
            "risk_or_sizing_changed": False,
            "live_authority_changed": False,
            "places_orders": False,
        }
        return dict(_STATUS)


def status_payload() -> Dict[str, Any]:
    row = apply() if not _PATCHED else dict(_STATUS)
    return {
        **row,
        "watcher_started": bool(_STARTED),
        "authority": {
            "timestamp_normalization_only": True,
            "changes_spacing_seconds": False,
            "changes_entry_quality": False,
            "changes_risk_or_sizing": False,
            "changes_live_authority": False,
            "places_orders": False,
        },
    }


def start_guard(timeout_seconds: float = 180.0) -> Dict[str, Any]:
    """Patch immediately or wait briefly for the target module to be imported."""
    global _STARTED
    first = apply()
    if first.get("patched"):
        return status_payload()
    with _LOCK:
        if _STARTED:
            return status_payload()
        _STARTED = True

    def worker() -> None:
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            if apply().get("patched"):
                return
            time.sleep(0.05)
        with _LOCK:
            _STATUS.update({"status": "warn", "reason": "target_module_not_loaded_before_timeout"})

    threading.Thread(
        target=worker,
        name="paper-underdeployment-time-guard",
        daemon=True,
    ).start()
    return status_payload()
