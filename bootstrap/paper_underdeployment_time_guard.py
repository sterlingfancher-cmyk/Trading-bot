"""Paper participation capacity guard loaded from the bootstrap import path.

This guard repairs two narrow causes of chronic paper-account underdeployment:

1. Persisted position timestamps are Unix epochs. A naive conversion in the
   Railway container timezone could later be relabeled as Central time, moving
   an old entry into the future and holding the 15-minute starter-spacing gate
   at zero seconds forever.
2. The risk-on starter valve previously required exactly zero mark-to-market
   drawdown. A few dollars of normal unrealized noise could therefore disable
   every additional starter even while all hard risk controls remained clear.

The guard patches every loaded copy of the affected modules, including modules
loaded through an alternate bootstrap path. It does not change the configured
spacing, signal scores, sizing, hard loss limits, broker authority, live-trading
authority, or order execution. The small drawdown tolerance applies only to the
existing paper-only risk-on starter valve.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable

VERSION = "paper-participation-capacity-guard-2026-08-04-v4-all-modules"
STARTER_MARK_TO_MARKET_TOLERANCE_PCT = float(
    os.environ.get("RISK_ON_STARTER_MARK_TO_MARKET_TOLERANCE_PCT", "0.10")
)
_LOCK = threading.RLock()
_PATCHED = False
_STARTED = False
_STATUS: Dict[str, Any] = {
    "version": VERSION,
    "status": "pending",
    "patched": False,
    "targets": [
        "paper_underdeployment_repair._parse_time",
        "risk_on_starter_participation_valve.MAX_DAILY_LOSS_PCT",
    ],
}


def _epoch_datetime(value: Any) -> dt.datetime | None:
    try:
        number = float(value)
        if not math.isfinite(number):
            return None
        if abs(number) >= 100_000_000_000:
            number /= 1000.0
        return dt.datetime.fromtimestamp(number, tz=dt.timezone.utc)
    except Exception:
        return None


def parse_time(value: Any) -> dt.datetime | None:
    """Parse timestamps while preserving absolute epoch semantics."""
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
    normalized = normalized.split(" CDT")[0].split(" CST")[0]
    for candidate in (normalized, normalized[:19]):
        try:
            return dt.datetime.fromisoformat(candidate)
        except Exception:
            pass
    return None


def _matching_modules(canonical_name: str, filename: str) -> Iterable[tuple[str, Any]]:
    seen: set[int] = set()
    for name, module in list(sys.modules.items()):
        if module is None or id(module) in seen:
            continue
        module_file = str(getattr(module, "__file__", "") or "")
        file_match = False
        if module_file:
            try:
                file_match = Path(module_file).name == filename
            except Exception:
                file_match = module_file.endswith(filename)
        if name == canonical_name or file_match:
            seen.add(id(module))
            yield name, module


def _patch_timestamp_modules() -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for name, module in _matching_modules(
        "paper_underdeployment_repair", "paper_underdeployment_repair.py"
    ):
        current = getattr(module, "_parse_time", None)
        import_complete = callable(current) and callable(getattr(module, "install", None))
        if not import_complete:
            rows.append({"module": name, "patched": False, "reason": "import_incomplete"})
            continue
        if getattr(current, "_paper_participation_capacity_version", None) != VERSION:
            parse_time._paper_participation_capacity_version = VERSION  # type: ignore[attr-defined]
            parse_time._paper_participation_capacity_original = current  # type: ignore[attr-defined]
            setattr(module, "_parse_time", parse_time)
        rows.append(
            {
                "module": name,
                "patched": True,
                "module_file": str(getattr(module, "__file__", "") or ""),
                "unix_epochs_are_utc_aware": True,
            }
        )
    return rows


def _patch_starter_modules() -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for name, module in _matching_modules(
        "risk_on_starter_participation_valve",
        "risk_on_starter_participation_valve.py",
    ):
        if not callable(getattr(module, "_risk_ok", None)):
            rows.append({"module": name, "patched": False, "reason": "import_incomplete"})
            continue
        try:
            before = float(getattr(module, "MAX_DAILY_LOSS_PCT", 0.0))
        except Exception:
            before = 0.0
        after = max(before, STARTER_MARK_TO_MARKET_TOLERANCE_PCT)
        setattr(module, "MAX_DAILY_LOSS_PCT", after)
        setattr(module, "PAPER_PARTICIPATION_CAPACITY_GUARD_VERSION", VERSION)
        rows.append(
            {
                "module": name,
                "patched": True,
                "module_file": str(getattr(module, "__file__", "") or ""),
                "daily_loss_tolerance_before_pct": before,
                "daily_loss_tolerance_after_pct": after,
                "intraday_drawdown_tolerance_pct": getattr(
                    module, "MAX_INTRADAY_DRAWDOWN_PCT", None
                ),
            }
        )
    return rows


def _latest_entry_age_seconds(module: Any) -> float | None:
    try:
        core = module._mod()
        latest = module._latest_entry(core)
        if latest is None:
            return None
        if latest.tzinfo is not None:
            now = dt.datetime.now(dt.timezone.utc)
            age = (now - latest.astimezone(dt.timezone.utc)).total_seconds()
        else:
            now = module._now_dt(core)
            if getattr(now, "tzinfo", None) is not None:
                latest = latest.replace(tzinfo=now.tzinfo)
            age = (now - latest).total_seconds()
        return round(max(0.0, age), 1)
    except Exception:
        return None


def apply() -> Dict[str, Any]:
    global _PATCHED, _STATUS
    with _LOCK:
        timestamp_modules = _patch_timestamp_modules()
        starter_modules = _patch_starter_modules()
        timestamp_patched = any(row.get("patched") for row in timestamp_modules)
        starter_patched = any(row.get("patched") for row in starter_modules)

        age_seconds = None
        for _, module in _matching_modules(
            "paper_underdeployment_repair", "paper_underdeployment_repair.py"
        ):
            age_seconds = _latest_entry_age_seconds(module)
            if age_seconds is not None:
                break

        _PATCHED = bool(timestamp_patched and starter_patched)
        _STATUS = {
            "version": VERSION,
            "status": "ok" if _PATCHED else "pending",
            "overall": "pass" if _PATCHED else "warn",
            "patched": _PATCHED,
            "timestamp_parser_patched": timestamp_patched,
            "starter_drawdown_tolerance_patched": starter_patched,
            "timestamp_modules": timestamp_modules,
            "starter_modules": starter_modules,
            "latest_entry_age_seconds": age_seconds,
            "starter_mark_to_market_tolerance_pct": STARTER_MARK_TO_MARKET_TOLERANCE_PCT,
            "spacing_threshold_changed": False,
            "signal_scores_changed": False,
            "sizing_changed": False,
            "hard_risk_limits_changed": False,
            "live_authority_changed": False,
            "places_orders": False,
        }
        if not timestamp_modules:
            _STATUS["reason"] = "paper_underdeployment_module_not_loaded"
        elif not starter_modules:
            _STATUS["reason"] = "risk_on_starter_module_not_loaded"
        return dict(_STATUS)


def status_payload() -> Dict[str, Any]:
    row = apply()
    return {
        **row,
        "watcher_started": bool(_STARTED),
        "authority": {
            "paper_only": True,
            "timestamp_normalization": True,
            "changes_spacing_seconds": False,
            "changes_global_signal_thresholds": False,
            "changes_paper_starter_drawdown_tolerance": True,
            "changes_hard_risk_limits": False,
            "changes_sizing": False,
            "changes_live_authority": False,
            "places_orders": False,
        },
    }


def start_guard(timeout_seconds: float = 180.0) -> Dict[str, Any]:
    """Patch immediately and keep checking briefly for alternate module copies."""
    global _STARTED
    first = apply()
    with _LOCK:
        if _STARTED:
            return status_payload()
        _STARTED = True

    def worker() -> None:
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            apply()
            time.sleep(0.25)

    threading.Thread(
        target=worker,
        name="paper-participation-capacity-guard",
        daemon=True,
    ).start()
    return {**first, "watcher_started": True}
