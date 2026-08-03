"""Non-blocking HTTP launcher for the heavy performance audit V2 run.

The V2 research job can take longer than a browser, proxy, or Gunicorn request
lifetime. This module replaces only the Flask route handler so the request
returns immediately while the existing advisory-only research engine continues
in a daemon thread.

It does not change trading logic, strategy thresholds, sizing, ML authority, or
order placement.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Dict

import performance_audit_lab_v2 as lab

VERSION = "performance-audit-v2-async-route-2026-08-03-v1"

_LOCK = threading.RLock()
_REGISTERED: set[int] = set()
_LAST: Dict[str, Any] = {}


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _bool_arg(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _status_payload(core: Any, state: str, period: str, max_symbols: int, include_ablation: bool) -> Dict[str, Any]:
    section = lab._section(core)
    return {
        "status": state,
        "type": "performance_backtest_v2_launcher",
        "version": VERSION,
        "engine_version": lab.VERSION,
        "generated_local": _now(core),
        "started_local": section.get("started_local") or section.get("queued_local"),
        "period": period,
        "symbols": max_symbols,
        "ablation": include_ablation,
        "status_url": "/paper/performance-audit-v2-status",
        "ablation_url": "/paper/performance-ablation-v2",
        "regime_report_url": "/paper/performance-regime-report-v2",
        "message": (
            "The research run is executing outside the HTTP request. Poll the status URL; "
            "the browser no longer needs to remain connected."
        ),
        "authority": {
            "advisory_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "places_orders": False,
        },
    }


def _background_run(core: Any, period: str, max_symbols: int, force: bool, include_ablation: bool) -> None:
    global _LAST
    try:
        result = lab.run(
            core,
            period=period,
            max_symbols=max_symbols,
            force=force,
            include_ablation=include_ablation,
        )
        _LAST = {
            "status": result.get("status") if isinstance(result, dict) else "complete",
            "completed_local": _now(core),
            "period": period,
            "symbols": max_symbols,
            "ablation": include_ablation,
        }
    except Exception as exc:  # defensive guard around the existing engine
        section = lab._section(core)
        section["status"] = "error"
        section["async_launcher_error"] = f"{type(exc).__name__}: {exc}"
        try:
            lab._save(core)
        except Exception:
            pass
        _LAST = {
            "status": "error",
            "completed_local": _now(core),
            "error": f"{type(exc).__name__}: {exc}",
        }


def start(core: Any, period: str, max_symbols: int, force: bool, include_ablation: bool) -> Dict[str, Any]:
    global _LAST
    if core is None:
        return {
            "status": "pending",
            "type": "performance_backtest_v2_launcher",
            "version": VERSION,
            "reason": "core_missing",
        }

    section = lab._section(core)
    with _LOCK:
        current = str(section.get("status") or "not_run")
        if lab._RUN_LOCK.locked() or current in {"queued", "running"}:
            payload = _status_payload(core, "running", period, max_symbols, include_ablation)
            payload["message"] = "A V2 research run is already queued or running."
            _LAST = payload
            return payload

        section["status"] = "queued"
        section["queued_local"] = _now(core)
        section["queued_request"] = {
            "period": period,
            "max_symbols": max_symbols,
            "force": force,
            "include_ablation": include_ablation,
        }
        try:
            lab._save(core)
        except Exception:
            pass

        thread = threading.Thread(
            target=_background_run,
            args=(core, period, max_symbols, force, include_ablation),
            name="performance-audit-v2-http-run",
            daemon=True,
        )
        thread.start()

        # Give the worker a brief opportunity to acquire the engine lock so a
        # rapid second request cannot start a duplicate run.
        deadline = time.time() + 0.20
        while time.time() < deadline and thread.is_alive() and not lab._RUN_LOCK.locked():
            time.sleep(0.01)

        payload = _status_payload(core, "started", period, max_symbols, include_ablation)
        payload["thread_alive"] = thread.is_alive()
        _LAST = payload
        return payload


def apply(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "reason": "flask_app_missing"}
    core = core or lab._core()

    # Ensure the original V2 routes exist before replacing the heavy synchronous
    # handler. The status, ablation, and regime-report endpoints stay unchanged.
    lab.register_routes(flask_app, core)

    from flask import jsonify, request

    def async_run_route():
        runtime = core or lab._core()
        period = str(request.args.get("period") or lab.AUTO_PERIOD)
        max_symbols = max(20, min(75, lab._i(request.args.get("symbols"), lab.AUTO_MAX_SYMBOLS)))
        force = _bool_arg(request.args.get("force"), False)
        include_ablation = _bool_arg(request.args.get("ablation"), True)
        payload = start(runtime, period, max_symbols, force, include_ablation)
        code = 202 if payload.get("status") in {"started", "running"} else 200
        return jsonify(payload), code

    async_run_route._performance_audit_v2_async_version = VERSION  # type: ignore[attr-defined]

    existing = flask_app.view_functions.get("performance_backtest_v2")
    if existing is None:
        return {
            "status": "error",
            "version": VERSION,
            "reason": "performance_backtest_v2_endpoint_missing",
        }
    flask_app.view_functions["performance_backtest_v2"] = async_run_route

    routes = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if "/paper/performance-backtest-v2-start" not in routes:
        flask_app.add_url_rule(
            "/paper/performance-backtest-v2-start",
            "performance_backtest_v2_async_start",
            async_run_route,
        )

    _REGISTERED.add(id(flask_app))
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "replaced_endpoint": "performance_backtest_v2",
        "routes": [
            "/paper/performance-backtest-v2",
            "/paper/performance-backtest-v2-start",
            "/paper/performance-audit-v2-status",
        ],
        "authority": {
            "advisory_only": True,
            "changes_strategy": False,
            "places_orders": False,
        },
    }


try:
    core = lab._core()
    if core is not None and getattr(core, "app", None) is not None:
        apply(core.app, core)
except Exception:
    pass
