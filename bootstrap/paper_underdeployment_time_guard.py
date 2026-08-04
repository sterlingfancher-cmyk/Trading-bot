"""Paper participation capacity guard loaded from the bootstrap import path.

This guard repairs four narrow causes of chronic paper-account underdeployment:

1. Persisted position timestamps are Unix epochs. A naive conversion in the
   Railway container timezone could later be relabeled as Central time, moving
   an old entry into the future and holding the 15-minute starter-spacing gate
   at zero seconds forever.
2. The risk-on starter valves previously required nearly zero mark-to-market
   drawdown. Normal noise from a small first starter could therefore disable
   every additional starter while all hard risk controls remained clear.
3. An older chase-pattern governor could reject an exceptional constructive-
   market leader despite zero realized losses and multiple clean continuation
   patterns. A narrow paper-only exception resolves only that contradiction.
4. The underdeployment gate blocked all diversification once a roughly 10%
   starter fell more than 0.50%. A controlled constructive-market exception now
   permits the original gate to re-evaluate down to a 1.25% first-position loss,
   while preserving spacing, daily caps, diversification, and exposure limits.

The guard patches every loaded copy of the affected modules. It does not change
the configured spacing, general signal thresholds, sizing, hard loss limits,
broker authority, live-trading authority, or order execution.
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

VERSION = "paper-participation-capacity-guard-2026-08-04-v6-second-starter"
STARTER_MARK_TO_MARKET_TOLERANCE_PCT = float(
    os.environ.get("RISK_ON_STARTER_MARK_TO_MARKET_TOLERANCE_PCT", "0.15")
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
        "risk_on_starter_participation_valve.MAX_INTRADAY_DRAWDOWN_PCT",
        "extended_leader_starter_valve.MAX_DAILY_LOSS_PCT",
        "extended_leader_starter_valve.MAX_INTRADAY_DRAWDOWN_PCT",
        "loss_streak_defensive_governor._govern_signal",
        "paper_underdeployment_repair._gate",
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


def _patch_one_starter_family(canonical_name: str, filename: str) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for name, module in _matching_modules(canonical_name, filename):
        if not callable(getattr(module, "_risk_ok", None)):
            rows.append({"module": name, "patched": False, "reason": "import_incomplete"})
            continue
        try:
            daily_before = float(getattr(module, "MAX_DAILY_LOSS_PCT", 0.0))
        except Exception:
            daily_before = 0.0
        try:
            drawdown_before = float(getattr(module, "MAX_INTRADAY_DRAWDOWN_PCT", 0.0))
        except Exception:
            drawdown_before = 0.0
        daily_after = max(daily_before, STARTER_MARK_TO_MARKET_TOLERANCE_PCT)
        drawdown_after = max(drawdown_before, STARTER_MARK_TO_MARKET_TOLERANCE_PCT)
        setattr(module, "MAX_DAILY_LOSS_PCT", daily_after)
        setattr(module, "MAX_INTRADAY_DRAWDOWN_PCT", drawdown_after)
        setattr(module, "PAPER_PARTICIPATION_CAPACITY_GUARD_VERSION", VERSION)
        rows.append(
            {
                "module": name,
                "patched": True,
                "module_file": str(getattr(module, "__file__", "") or ""),
                "daily_loss_tolerance_before_pct": daily_before,
                "daily_loss_tolerance_after_pct": daily_after,
                "intraday_drawdown_tolerance_before_pct": drawdown_before,
                "intraday_drawdown_tolerance_after_pct": drawdown_after,
            }
        )
    return rows


def _patch_starter_modules() -> list[Dict[str, Any]]:
    return (
        _patch_one_starter_family(
            "risk_on_starter_participation_valve",
            "risk_on_starter_participation_valve.py",
        )
        + _patch_one_starter_family(
            "extended_leader_starter_valve",
            "extended_leader_starter_valve.py",
        )
    )


def _core_module() -> Any | None:
    for _, module in _matching_modules(
        "paper_underdeployment_repair", "paper_underdeployment_repair.py"
    ):
        try:
            core = module._mod()
        except Exception:
            core = None
        if core is not None:
            return core
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    return None


def _install_controlled_exception(module_name: str) -> Dict[str, Any]:
    try:
        module = __import__(module_name)
        core = _core_module()
        result = module.apply(core)
        flask_app = getattr(core, "app", None) if core is not None else None
        if flask_app is not None and callable(getattr(module, "register_routes", None)):
            module.register_routes(flask_app, core)
        return {
            "patched": bool(result.get("patched")),
            "version": result.get("version") or getattr(module, "VERSION", None),
            "status": result.get("status"),
            "overall": result.get("overall"),
            "policy": result.get("policy"),
            "route_registered": flask_app is not None,
        }
    except Exception as exc:
        return {
            "patched": False,
            "status": "error",
            "overall": "warn",
            "error": f"{type(exc).__name__}: {exc}",
        }


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
        pattern_exception = _install_controlled_exception(
            "favorable_regime_pattern_exception"
        )
        second_starter_tolerance = _install_controlled_exception(
            "constructive_second_starter_tolerance"
        )
        timestamp_patched = any(row.get("patched") for row in timestamp_modules)
        starter_patched = any(row.get("patched") for row in starter_modules)
        pattern_exception_patched = bool(pattern_exception.get("patched"))
        second_starter_patched = bool(second_starter_tolerance.get("patched"))

        age_seconds = None
        for _, module in _matching_modules(
            "paper_underdeployment_repair", "paper_underdeployment_repair.py"
        ):
            age_seconds = _latest_entry_age_seconds(module)
            if age_seconds is not None:
                break

        _PATCHED = bool(
            timestamp_patched
            and starter_patched
            and pattern_exception_patched
            and second_starter_patched
        )
        _STATUS = {
            "version": VERSION,
            "status": "ok" if _PATCHED else "pending",
            "overall": "pass" if _PATCHED else "warn",
            "patched": _PATCHED,
            "timestamp_parser_patched": timestamp_patched,
            "starter_drawdown_tolerance_patched": starter_patched,
            "favorable_pattern_exception_patched": pattern_exception_patched,
            "constructive_second_starter_tolerance_patched": second_starter_patched,
            "timestamp_modules": timestamp_modules,
            "starter_modules": starter_modules,
            "favorable_pattern_exception": pattern_exception,
            "constructive_second_starter_tolerance": second_starter_tolerance,
            "latest_entry_age_seconds": age_seconds,
            "starter_mark_to_market_tolerance_pct": STARTER_MARK_TO_MARKET_TOLERANCE_PCT,
            "spacing_threshold_changed": False,
            "general_signal_scores_changed": False,
            "controlled_paper_pattern_exception_added": True,
            "controlled_second_starter_tolerance_added": True,
            "sizing_changed": False,
            "hard_risk_limits_changed": False,
            "live_authority_changed": False,
            "places_orders": False,
        }
        if not timestamp_modules:
            _STATUS["reason"] = "paper_underdeployment_module_not_loaded"
        elif not starter_modules:
            _STATUS["reason"] = "starter_modules_not_loaded"
        elif not pattern_exception_patched:
            _STATUS["reason"] = "favorable_pattern_exception_not_installed"
        elif not second_starter_patched:
            _STATUS["reason"] = "constructive_second_starter_tolerance_not_installed"
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
            "changes_paper_starter_mark_to_market_tolerance": True,
            "adds_controlled_favorable_pattern_exception": True,
            "adds_controlled_constructive_second_starter_tolerance": True,
            "preserves_downstream_entry_and_risk_caps": True,
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
