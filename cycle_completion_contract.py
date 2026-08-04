"""Observable completion contract for the existing paper run cycle.

The module adds lifecycle and phase telemetry around the existing run_cycle
callable. It does not create a new trading loop, interrupt a running cycle,
change scanner inputs, or alter trade/risk decisions.
"""
from __future__ import annotations

import datetime as dt
import functools
import os
import threading
import time
import uuid
from typing import Any, Dict

VERSION = "cycle-completion-contract-2026-08-04-v2-rebind-safe"
STALE_SECONDS = float(os.environ.get("AUTO_CYCLE_STALE_SECONDS", "720"))
_LOCK = threading.RLock()
_APPLIED: set[int] = set()
_PHASE_APPLIED: set[tuple[int, str]] = set()
_ACTIVE: Dict[int, set[str]] = {}
_LAST: Dict[str, Any] = {}


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _portfolio(core: Any) -> Dict[str, Any]:
    value = getattr(core, "portfolio", {})
    return value if isinstance(value, dict) else {}


def _auto(core: Any) -> Dict[str, Any]:
    portfolio = _portfolio(core)
    value = portfolio.setdefault("auto_runner", {})
    return value if isinstance(value, dict) else {}


def _save(core: Any) -> None:
    try:
        fn = getattr(core, "save_state", None)
        if callable(fn):
            fn(_portfolio(core))
    except Exception:
        pass


def _active(core: Any) -> set[str]:
    with _LOCK:
        return _ACTIVE.setdefault(id(core), set())


def _set_phase(core: Any, phase: str) -> None:
    auto = _auto(core)
    if not auto.get("cycle_in_progress"):
        return
    now = time.time()
    previous = auto.get("cycle_phase")
    previous_started = auto.get("cycle_phase_started_ts")
    if previous and previous_started:
        try:
            durations = auto.setdefault("cycle_phase_durations_seconds", {})
            durations[str(previous)] = round(now - float(previous_started), 3)
        except Exception:
            pass
    auto["cycle_phase"] = phase
    auto["cycle_phase_started_ts"] = now
    auto["cycle_phase_started_local"] = _now(core)
    auto["cycle_heartbeat_ts"] = now
    auto["cycle_heartbeat_local"] = _now(core)


def _wrap_phase(core: Any, name: str, phase: str) -> None:
    key = (id(core), name)
    if key in _PHASE_APPLIED:
        return
    current = getattr(core, name, None)
    if not callable(current) or getattr(current, "_cycle_completion_phase", False):
        return

    @functools.wraps(current)
    def wrapped(*args, **kwargs):
        _set_phase(core, phase)
        try:
            return current(*args, **kwargs)
        finally:
            auto = _auto(core)
            if auto.get("cycle_in_progress"):
                auto["cycle_heartbeat_ts"] = time.time()
                auto["cycle_heartbeat_local"] = _now(core)

    wrapped._cycle_completion_phase = True  # type: ignore[attr-defined]
    wrapped._cycle_completion_phase_name = phase  # type: ignore[attr-defined]
    setattr(core, name, wrapped)
    _PHASE_APPLIED.add(key)


def _complete(
    core: Any,
    *,
    cycle_id: str,
    source: str,
    started: float,
    status: str,
    error: str | None = None,
) -> None:
    """Write completion into the current portfolio, even if a wrapper replaced it."""
    global _LAST
    completed = time.time()
    duration = round(completed - started, 3)
    completed_local = _now(core)
    with _LOCK:
        active = _ACTIVE.setdefault(id(core), set())
        active.discard(cycle_id)
        current_auto = _auto(core)
        same_current_cycle = current_auto.get("cycle_id") == cycle_id
        no_other_active_cycle = not active
        current_auto.update({
            "last_completed_cycle_id": cycle_id,
            "last_completed_cycle_status": status,
            "last_completed_cycle_source": source,
            "last_completed_cycle_duration_seconds": duration,
            "last_completed_cycle_local": completed_local,
            "last_completed_cycle_ts": completed,
        })
        if same_current_cycle or no_other_active_cycle:
            current_auto.update({
                "cycle_id": cycle_id,
                "cycle_in_progress": False,
                "cycle_health": status,
                "cycle_phase": status,
                "cycle_completed_ts": completed,
                "cycle_completed_local": completed_local,
                "cycle_duration_seconds": duration,
                "cycle_stale": False,
                "cycle_stale_reason": None,
            })
            if error:
                current_auto["cycle_error"] = error
            else:
                current_auto.pop("cycle_error", None)
        _LAST = {
            "status": "error" if error else "ok",
            "overall": "warn" if error else "pass",
            "version": VERSION,
            "cycle_id": cycle_id,
            "cycle_status": status,
            "source": source,
            "duration_seconds": duration,
            "completed_ts": completed,
            "completed_local": completed_local,
            "error": error,
        }
    _save(core)


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None or not callable(getattr(core, "run_cycle", None)):
        return {"status": "pending", "version": VERSION, "reason": "core_or_run_cycle_missing"}
    if id(core) in _APPLIED:
        return status_payload(core)

    for name, phase in (
        ("market_status", "market_status"),
        ("manage_exits", "manage_exits"),
        ("calculate_equity", "equity_refresh"),
        ("scan_signals", "scanner"),
        ("try_entries_and_rotations", "entry_pipeline"),
        ("performance_snapshot", "performance_snapshot"),
    ):
        _wrap_phase(core, name, phase)

    original = core.run_cycle
    if getattr(original, "_cycle_completion_contract", False):
        _APPLIED.add(id(core))
        return status_payload(core)

    @functools.wraps(original)
    def wrapped_run_cycle(*args, **kwargs):
        started = time.time()
        source = kwargs.get("source")
        if source is None and args:
            source = args[0]
        source = str(source or "manual")
        with _LOCK:
            auto = _auto(core)
            sequence = int(auto.get("cycle_sequence") or 0) + 1
            cycle_id = f"{source}-{int(started)}-{sequence}-{uuid.uuid4().hex[:8]}"
            _ACTIVE.setdefault(id(core), set()).add(cycle_id)
            auto.update({
                "cycle_sequence": sequence,
                "cycle_id": cycle_id,
                "cycle_in_progress": True,
                "cycle_health": "running",
                "cycle_source": source,
                "cycle_started_ts": started,
                "cycle_started_local": _now(core),
                "cycle_phase": "starting",
                "cycle_phase_started_ts": started,
                "cycle_phase_started_local": _now(core),
                "cycle_heartbeat_ts": started,
                "cycle_heartbeat_local": _now(core),
                "cycle_stale": False,
                "cycle_stale_reason": None,
            })
        _save(core)
        try:
            result = original(*args, **kwargs)
            status = (
                "skipped"
                if isinstance(result, dict) and result.get("skipped")
                else "busy"
                if isinstance(result, dict) and result.get("status") == "cycle_busy"
                else "completed"
            )
            _complete(
                core,
                cycle_id=cycle_id,
                source=source,
                started=started,
                status=status,
            )
            return result
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
            _complete(
                core,
                cycle_id=cycle_id,
                source=source,
                started=started,
                status="error",
                error=error,
            )
            raise

    wrapped_run_cycle._cycle_completion_contract = True  # type: ignore[attr-defined]
    wrapped_run_cycle._cycle_completion_contract_version = VERSION  # type: ignore[attr-defined]
    core.run_cycle = wrapped_run_cycle
    _APPLIED.add(id(core))
    return status_payload(core)


def _reconcile_detached_completion(core: Any, auto: Dict[str, Any]) -> bool:
    """Clear a stale in-progress flag left behind when portfolio dicts were replaced."""
    if not auto.get("cycle_in_progress"):
        return False
    cycle_id = str(auto.get("cycle_id") or "")
    if not cycle_id:
        return False
    with _LOCK:
        if cycle_id in _ACTIVE.get(id(core), set()):
            return False
        last = dict(_LAST)
    if last.get("cycle_id") != cycle_id or last.get("cycle_status") not in {"completed", "skipped", "busy", "error"}:
        return False
    auto.update({
        "cycle_in_progress": False,
        "cycle_health": last.get("cycle_status"),
        "cycle_phase": last.get("cycle_status"),
        "cycle_completed_ts": last.get("completed_ts"),
        "cycle_completed_local": last.get("completed_local"),
        "cycle_duration_seconds": last.get("duration_seconds"),
        "last_completed_cycle_id": cycle_id,
        "last_completed_cycle_status": last.get("cycle_status"),
        "last_completed_cycle_source": last.get("source"),
        "last_completed_cycle_duration_seconds": last.get("duration_seconds"),
        "last_completed_cycle_local": last.get("completed_local"),
        "last_completed_cycle_ts": last.get("completed_ts"),
        "cycle_stale": False,
        "cycle_stale_reason": None,
    })
    _save(core)
    return True


def status_payload(core: Any = None) -> Dict[str, Any]:
    auto = _auto(core) if core is not None else {}
    reconciled = _reconcile_detached_completion(core, auto) if core is not None else False
    now = time.time()
    started = auto.get("cycle_started_ts")
    age = None
    try:
        age = round(now - float(started), 1) if auto.get("cycle_in_progress") and started else None
    except Exception:
        age = None
    stale = bool(age is not None and age > STALE_SECONDS)
    if stale:
        auto["cycle_stale"] = True
        auto["cycle_health"] = "stale_in_progress"
        auto["cycle_stale_reason"] = f"cycle exceeded {STALE_SECONDS:.0f}s without completion"
    installed = bool(core is not None and id(core) in _APPLIED)
    last = dict(_LAST)
    return {
        "status": "ok" if installed else "pending",
        "overall": "warn" if stale else "pass" if installed else "pending",
        "type": "cycle_completion_contract",
        "version": VERSION,
        "installed": installed,
        "detached_completion_reconciled": reconciled,
        "active_cycle_count": len(_ACTIVE.get(id(core), set())) if core is not None else 0,
        "cycle_in_progress": bool(auto.get("cycle_in_progress")),
        "cycle_health": auto.get("cycle_health"),
        "cycle_id": auto.get("cycle_id"),
        "cycle_source": auto.get("cycle_source"),
        "cycle_phase": auto.get("cycle_phase"),
        "cycle_started_local": auto.get("cycle_started_local"),
        "cycle_age_seconds": age,
        "cycle_stale_seconds": STALE_SECONDS,
        "cycle_stale": stale or bool(auto.get("cycle_stale")),
        "cycle_stale_reason": auto.get("cycle_stale_reason"),
        "last_completed_cycle_id": auto.get("last_completed_cycle_id") or last.get("cycle_id"),
        "last_completed_cycle_status": auto.get("last_completed_cycle_status") or last.get("cycle_status"),
        "last_completed_cycle_source": auto.get("last_completed_cycle_source") or last.get("source"),
        "last_completed_cycle_duration_seconds": auto.get("last_completed_cycle_duration_seconds") or last.get("duration_seconds"),
        "last_completed_cycle_local": auto.get("last_completed_cycle_local") or auto.get("cycle_completed_local") or last.get("completed_local"),
        "last": last,
        "authority": {
            "observability_only": True,
            "interrupts_cycle": False,
            "starts_new_runner": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/cycle-completion-contract-status" not in existing:
        flask_app.add_url_rule(
            "/paper/cycle-completion-contract-status",
            "cycle_completion_contract_status",
            lambda: jsonify(status_payload(core)),
        )
