from __future__ import annotations

import datetime as dt
import functools
import os
import threading
from typing import Any, Dict, List

import runtime_shadow_capture

VERSION = "run-report-guard-2026-08-03-v3-shadow-observer"
_APPLIED: set[int] = set()
_LOCK = threading.RLock()
_LAST: Dict[str, Any] = {}
_RECENT: List[Dict[str, Any]] = []


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    try:
        return str(core.today_key())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _inline_enabled() -> bool:
    return str(os.environ.get("RUN_CYCLE_INLINE_REPORTS", "false")).lower() in {"1", "true", "yes", "on"}


def _lock_timeout_seconds() -> float:
    raw = os.environ.get("RUN_CYCLE_GUARD_LOCK_TIMEOUT_SECONDS", "2.0")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 2.0
    return max(0.1, min(value, 10.0))


def _deferred(core: Any, report_type: str, args: tuple, kwargs: dict) -> Dict[str, Any]:
    item = {
        "status": "deferred",
        "type": report_type or "intraday",
        "date": _today(core),
        "generated_local": _now(core),
        "version": VERSION,
        "reason": "Inline report compilation is skipped during /paper/run to prevent request timeouts.",
        "report_links": ["/paper/intraday-report", "/paper/risk-review", "/paper/report/today", "/paper/end-of-day-report"],
        "args_seen": len(args),
        "kwargs_seen": sorted(list(kwargs.keys())),
    }
    _RECENT.append(item)
    del _RECENT[:-10]
    return item


def _busy_payload(core: Any, timeout_seconds: float) -> Dict[str, Any]:
    return {
        "status": "cycle_busy",
        "ok": False,
        "version": VERSION,
        "generated_local": _now(core),
        "retryable": True,
        "lock_timeout_seconds": timeout_seconds,
        "reason": "Another run_cycle invocation is already active; this request was not allowed to wait until the Gunicorn worker timed out.",
        "normal_test_link": "/paper/self-check",
        "run_status_link": "/paper/run-report-guard-status",
        "safety": {
            "cycle_executed": False,
            "orders_placed_by_this_request": False,
            "strategy_changed": False,
        },
    }


def _capture_shadow(core: Any, result: Any) -> Dict[str, Any]:
    """Observe a completed market cycle without altering its return value."""
    if not isinstance(result, dict):
        return {"status": "not_captured", "reason": "result_not_dict"}
    if result.get("skipped") or result.get("status") == "cycle_busy":
        return {
            "status": "not_captured",
            "reason": "cycle_not_executed",
            "generated_local": _now(core),
        }

    portfolio = getattr(core, "portfolio", {})
    if not isinstance(portfolio, dict):
        return {"status": "not_captured", "reason": "portfolio_missing"}

    cycle_id = (
        getattr(core, "LAST_CYCLE_ID", None)
        or result.get("cycle_id")
        or f"observed-{_now(core)}"
    )
    generated_local = _now(core)
    try:
        report = runtime_shadow_capture.capture_cycle(
            cycle_id=str(cycle_id),
            generated_local=generated_local,
            market=result,
            risk=result.get("risk_controls") or portfolio.get("risk_controls") or {},
            positions=portfolio.get("positions") or {},
            equity=float(portfolio.get("equity") or result.get("equity") or 0.0),
            long_signals=result.get("long_signals") or [],
            short_signals=result.get("short_signals") or [],
            entries=result.get("entries") or [],
            blocked_entries=result.get("blocked_entries") or [],
            rejected_signals=result.get("rejected_signals") or [],
            new_entries_allowed=bool(result.get("new_entries_allowed")),
            entry_block_reason=result.get("entry_block_reason"),
            market_open=bool(result.get("market_open_now")),
        )
    except Exception as exc:
        report = runtime_shadow_capture.failure_record(
            cycle_id=str(cycle_id),
            generated_local=generated_local,
            error=exc,
        )

    portfolio["shadow_decision_comparison"] = runtime_shadow_capture.append_bounded(
        portfolio.get("shadow_decision_comparison"),
        report,
    )
    return {
        "status": report.get("status"),
        "version": report.get("version"),
        "cycle_id": report.get("cycle_id"),
        "parity": report.get("parity"),
        "candidate_count": report.get("candidate_count"),
        "independent_policy_active": False,
        "forward_evidence_eligible": False,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None or not hasattr(core, "run_cycle"):
        return {"status": "not_applied", "version": VERSION, "reason": "core_or_run_cycle_missing"}
    if id(core) in _APPLIED:
        return {"status": "ok", "version": VERSION, "already_applied": True}
    original = core.run_cycle
    if getattr(original, "_run_report_guard", False):
        _APPLIED.add(id(core))
        return {"status": "ok", "version": VERSION, "already_wrapped": True}

    @functools.wraps(original)
    def wrapped_run_cycle(*args, **kwargs):
        global _LAST
        if _inline_enabled():
            result = original(*args, **kwargs)
            shadow = _capture_shadow(core, result)
            _LAST = {
                "status": "ok",
                "version": VERSION,
                "generated_local": _now(core),
                "inline_report_compilation": True,
                "shadow_capture": shadow,
            }
            return result

        timeout_seconds = _lock_timeout_seconds()
        acquired = _LOCK.acquire(timeout=timeout_seconds)
        if not acquired:
            payload = _busy_payload(core, timeout_seconds)
            _LAST = dict(payload)
            return payload

        original_store = getattr(core, "store_compiled_report", None)
        deferred: List[Dict[str, Any]] = []

        def store_stub(report_type="intraday", *s_args, **s_kwargs):
            item = _deferred(core, report_type, s_args, s_kwargs)
            deferred.append(item)
            return item

        try:
            if callable(original_store):
                core.store_compiled_report = store_stub
            result = original(*args, **kwargs)
            shadow = _capture_shadow(core, result)
            if isinstance(result, dict):
                result["run_report_guard"] = {
                    "version": VERSION,
                    "inline_report_compilation": False,
                    "lock_timeout_seconds": timeout_seconds,
                    "normal_test_link": "/paper/self-check",
                    "report_links": ["/paper/intraday-report", "/paper/risk-review", "/paper/report/today", "/paper/end-of-day-report"],
                }
                if deferred:
                    result["compiled_report"] = deferred[-1]
                    result["deferred_reports_count"] = len(deferred)
            _LAST = {
                "status": "ok",
                "version": VERSION,
                "generated_local": _now(core),
                "deferred_reports_count": len(deferred),
                "lock_timeout_seconds": timeout_seconds,
                "shadow_capture": shadow,
            }
            return result
        finally:
            if callable(original_store):
                try:
                    core.store_compiled_report = original_store
                except Exception:
                    pass
            _LOCK.release()

    wrapped_run_cycle._run_report_guard = True
    core.run_cycle = wrapped_run_cycle
    try:
        core.RUN_REPORT_GUARD_VERSION = VERSION
    except Exception:
        pass
    _APPLIED.add(id(core))
    return {
        "status": "ok",
        "version": VERSION,
        "patched": ["run_cycle"],
        "existing_owner_extended": True,
        "new_callable_owner_added": False,
        "shadow_observer": runtime_shadow_capture.VERSION,
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    portfolio = getattr(core, "portfolio", {}) if core is not None else {}
    return {
        "status": "ok",
        "type": "run_report_guard_status",
        "version": VERSION,
        "generated_local": _now(core),
        "installed": bool(core is not None and id(core) in _APPLIED),
        "inline_report_compilation": _inline_enabled(),
        "lock_timeout_seconds": _lock_timeout_seconds(),
        "normal_test_link": "/paper/self-check",
        "recent_deferred_reports": list(_RECENT),
        "last_status": _LAST,
        "shadow_capture": runtime_shadow_capture.status_payload(portfolio),
        "authority": {
            "existing_run_cycle_owner_only": True,
            "new_callable_owner_added": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/run-report-guard-status" in existing:
        return
    from flask import jsonify
    flask_app.add_url_rule("/paper/run-report-guard-status", "run_report_guard_status", lambda: jsonify(status_payload(core)))
