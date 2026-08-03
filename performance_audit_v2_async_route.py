"""Resumable non-blocking launcher for the heavy performance audit V2 run.

The five-year V2 research job is intentionally much heavier than an ordinary
HTTP request. This module keeps the browser request short, persists a run
checkpoint, separates the core walk-forward test from ablation, and resumes an
interrupted queued/running request after a Railway worker restart.

It does not change trading logic, strategy thresholds, sizing, ML authority, or
order placement.
"""
from __future__ import annotations

import copy
import datetime as dt
import threading
import time
from typing import Any, Dict

import performance_audit_lab_v2 as lab

VERSION = "performance-audit-v2-resumable-route-2026-08-03-v2"

_LOCK = threading.RLock()
_REGISTERED: set[int] = set()
_RECOVERY_STARTED: set[int] = set()
_THREADS: Dict[int, threading.Thread] = {}
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


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _thread_alive(core: Any) -> bool:
    thread = _THREADS.get(id(core))
    return bool(thread is not None and thread.is_alive())


def _save(core: Any) -> None:
    try:
        lab._save(core)
    except Exception:
        pass


def _runner(core: Any) -> Dict[str, Any]:
    section = lab._section(core)
    runner = section.get("resilient_runner")
    if not isinstance(runner, dict):
        runner = {}
        section["resilient_runner"] = runner
    runner["version"] = VERSION
    return runner


def _heartbeat(
    core: Any,
    *,
    phase: str,
    state: str = "running",
    progress_current: int | None = None,
    progress_total: int | None = None,
    detail: str | None = None,
) -> None:
    section = lab._section(core)
    runner = _runner(core)
    section["status"] = state
    runner.update(
        {
            "state": state,
            "phase": phase,
            "heartbeat_local": _now(core),
            "heartbeat_epoch": time.time(),
        }
    )
    if progress_current is not None:
        runner["progress_current"] = int(progress_current)
    if progress_total is not None:
        runner["progress_total"] = int(progress_total)
    if detail is not None:
        runner["detail"] = str(detail)
    _save(core)


def _request_matches(row: Dict[str, Any], period: str, max_symbols: int) -> bool:
    return bool(
        row
        and str(row.get("period")) == str(period)
        and int(_f(row.get("max_symbols"), -1)) == int(max_symbols)
    )


def _status_payload(
    core: Any,
    state: str,
    period: str,
    max_symbols: int,
    include_ablation: bool,
) -> Dict[str, Any]:
    section = lab._section(core)
    runner = _d(section.get("resilient_runner"))
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
        "phase": runner.get("phase"),
        "progress_current": runner.get("progress_current"),
        "progress_total": runner.get("progress_total"),
        "status_url": "/paper/performance-audit-v2-status",
        "ablation_url": "/paper/performance-ablation-v2",
        "regime_report_url": "/paper/performance-regime-report-v2",
        "message": (
            "The research run is executing outside the HTTP request. The core "
            "walk-forward result is checkpointed before the ablation phase."
        ),
        "authority": {
            "advisory_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "places_orders": False,
        },
    }


def _ablation_row(
    name: str,
    regime_map: Dict[str, Dict[str, Any]],
    features: Dict[str, Any],
    dates: list[Any],
    baseline_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    sim = lab._simulate_next_open(features, regime_map, dates)
    metrics = _d(sim.get("metrics"))
    return {
        "variant": name,
        **metrics,
        "delta_total_return_pct": round(
            _f(metrics.get("total_return_pct"))
            - _f(baseline_metrics.get("total_return_pct")),
            2,
        ),
        "delta_max_drawdown_pct": round(
            _f(metrics.get("max_drawdown_pct"))
            - _f(baseline_metrics.get("max_drawdown_pct")),
            2,
        ),
        "delta_sharpe": round(
            _f(metrics.get("sharpe")) - _f(baseline_metrics.get("sharpe")),
            3,
        ),
        "objective": round(lab._objective(metrics), 3),
    }


def _run_resumable_ablation(
    core: Any,
    period: str,
    max_symbols: int,
    core_result: Dict[str, Any],
) -> Dict[str, Any]:
    section = lab._section(core)
    _heartbeat(core, phase="ablation_data_load", detail="Reloading daily history for resumable ablation")

    symbols = lab._universe(core, max_symbols)
    frames, provider = lab.base._download(symbols, period)
    features = lab.base._feature_frames(frames)
    dates = list(lab.base._calendar(features))
    if len(dates) < 315 or len(features) < 10:
        return {
            "status": "error",
            "reason": "insufficient_historical_data_for_ablation",
            "provider": provider,
            "available_days": len(dates),
            "loaded_symbols": len(features),
        }

    adaptive = _d(_d(core_result.get("profiles")).get("adaptive_balanced"))
    baseline_metrics = _d(adaptive.get("full_sample"))
    variants = lab._ablation_maps()

    partial = _d(section.get("resilient_ablation_partial"))
    if not _request_matches(partial, period, max_symbols):
        partial = {
            "period": period,
            "max_symbols": max_symbols,
            "results": {},
            "started_local": _now(core),
        }
    completed = partial.get("results")
    if not isinstance(completed, dict):
        completed = {}
        partial["results"] = completed

    total = len(variants)
    for index, (name, regime_map) in enumerate(variants.items(), start=1):
        if name in completed:
            continue
        _heartbeat(
            core,
            phase="ablation",
            progress_current=index - 1,
            progress_total=total,
            detail=f"Running {name}",
        )
        completed[name] = _ablation_row(
            name,
            regime_map,
            features,
            dates,
            baseline_metrics,
        )
        partial["updated_local"] = _now(core)
        partial["completed_count"] = len(completed)
        partial["variant_count"] = total
        section["resilient_ablation_partial"] = partial
        _heartbeat(
            core,
            phase="ablation",
            progress_current=len(completed),
            progress_total=total,
            detail=f"Completed {name}",
        )

    ranking = list(completed.values())
    ranking.sort(key=lambda row: _f(_d(row).get("objective"), -9999.0), reverse=True)
    return {
        "status": "ok",
        "baseline": "adaptive_baseline",
        "variant_count": len(ranking),
        "ranking": ranking,
        "best_variant": ranking[0] if ranking else None,
        "interpretation": (
            "Each variant changes one parameter family from the adaptive baseline. "
            "Results remain daily-bar proxies and require forward-shadow confirmation."
        ),
    }


def _matching_checkpoint(
    section: Dict[str, Any], period: str, max_symbols: int
) -> Dict[str, Any] | None:
    checkpoint = _d(section.get("resilient_core_checkpoint"))
    result = _d(checkpoint.get("result"))
    if (
        _request_matches(checkpoint, period, max_symbols)
        and result.get("status") == "ok"
    ):
        return copy.deepcopy(result)
    return None


def _background_run(
    core: Any,
    period: str,
    max_symbols: int,
    force: bool,
    include_ablation: bool,
) -> None:
    global _LAST
    section = lab._section(core)
    try:
        section["started_local"] = section.get("started_local") or _now(core)
        _heartbeat(
            core,
            phase="core_walk_forward",
            state="running",
            detail="Running full-history profiles without ablation",
        )

        core_result = None if force else _matching_checkpoint(section, period, max_symbols)
        # A persisted checkpoint is safe to reuse even when force=true after a
        # worker restart. The queued request records whether this is a resume.
        queued = _d(section.get("queued_request"))
        if bool(queued.get("resume")):
            core_result = _matching_checkpoint(section, period, max_symbols)

        if core_result is None:
            core_result = lab.run(
                core,
                period=period,
                max_symbols=max_symbols,
                force=True,
                include_ablation=False,
            )
            if not isinstance(core_result, dict) or core_result.get("status") != "ok":
                raise RuntimeError(
                    f"core V2 run did not complete: {_d(core_result).get('error') or _d(core_result).get('reason') or _d(core_result).get('status')}"
                )
            section = lab._section(core)
            section["resilient_core_checkpoint"] = {
                "period": period,
                "max_symbols": max_symbols,
                "completed_local": _now(core),
                "result": core_result,
            }
            _save(core)

        final_result = copy.deepcopy(core_result)
        if include_ablation:
            _heartbeat(
                core,
                phase="ablation",
                state="running",
                detail="Core checkpoint complete; starting resumable ablation",
            )
            ablation = _run_resumable_ablation(
                core,
                period,
                max_symbols,
                core_result,
            )
            if ablation.get("status") != "ok":
                raise RuntimeError(
                    f"ablation did not complete: {ablation.get('reason') or ablation.get('status')}"
                )
            final_result["ablation"] = ablation
            methodology = _d(final_result.get("methodology"))
            methodology["ablation"] = True
            methodology["resumable_staged_execution"] = True
            final_result["methodology"] = methodology
        else:
            final_result["ablation"] = {"status": "not_requested"}

        final_result["generated_local"] = _now(core)
        final_result["generated_epoch"] = time.time()
        final_result["resumable_runner_version"] = VERSION

        section = lab._section(core)
        runs = section.setdefault("runs", {})
        if not isinstance(runs, dict):
            runs = {}
            section["runs"] = runs
        key = f"{period}:{max_symbols}:ablation={bool(include_ablation)}"
        runs[key] = final_result
        section["latest_key"] = key
        section["latest"] = final_result
        section["status"] = "ok"
        section.pop("queued_request", None)
        runner = _runner(core)
        runner.update(
            {
                "state": "ok",
                "phase": "complete",
                "completed_local": _now(core),
                "heartbeat_local": _now(core),
                "heartbeat_epoch": time.time(),
                "progress_current": runner.get("progress_total"),
            }
        )
        _save(core)
        _LAST = {
            "status": "ok",
            "completed_local": _now(core),
            "period": period,
            "symbols": max_symbols,
            "ablation": include_ablation,
            "latest_key": key,
        }
    except Exception as exc:
        section = lab._section(core)
        section["status"] = "error"
        section["async_launcher_error"] = f"{type(exc).__name__}: {exc}"
        runner = _runner(core)
        runner.update(
            {
                "state": "error",
                "phase": runner.get("phase") or "unknown",
                "error": f"{type(exc).__name__}: {exc}",
                "heartbeat_local": _now(core),
                "heartbeat_epoch": time.time(),
            }
        )
        _save(core)
        _LAST = {
            "status": "error",
            "completed_local": _now(core),
            "error": f"{type(exc).__name__}: {exc}",
        }


def start(
    core: Any,
    period: str,
    max_symbols: int,
    force: bool,
    include_ablation: bool,
    *,
    resume: bool = False,
) -> Dict[str, Any]:
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
        live_thread = _thread_alive(core)
        engine_locked = lab._RUN_LOCK.locked()
        if live_thread or engine_locked:
            payload = _status_payload(
                core, "running", period, max_symbols, include_ablation
            )
            payload["message"] = "A V2 research stage is currently running."
            payload["thread_alive"] = live_thread
            payload["engine_locked"] = engine_locked
            _LAST = payload
            return payload

        previous = str(section.get("status") or "not_run")
        if previous in {"queued", "running"}:
            section["last_interrupted_state"] = {
                "state": previous,
                "detected_local": _now(core),
                "reason": "no_live_thread_and_engine_lock_clear",
            }
            resume = True

        section["status"] = "queued"
        section["queued_local"] = _now(core)
        section["queued_request"] = {
            "period": period,
            "max_symbols": max_symbols,
            "force": force,
            "include_ablation": include_ablation,
            "resume": resume,
        }
        runner = _runner(core)
        runner.update(
            {
                "state": "queued",
                "phase": "resume_pending" if resume else "queued",
                "queued_local": _now(core),
                "heartbeat_local": _now(core),
                "heartbeat_epoch": time.time(),
            }
        )
        _save(core)

        thread = threading.Thread(
            target=_background_run,
            args=(core, period, max_symbols, force, include_ablation),
            name="performance-audit-v2-resumable-run",
            daemon=True,
        )
        _THREADS[id(core)] = thread
        thread.start()

        payload = _status_payload(
            core, "started", period, max_symbols, include_ablation
        )
        payload["thread_alive"] = thread.is_alive()
        payload["resumed"] = resume
        _LAST = payload
        return payload


def _recover_after_startup(core: Any) -> None:
    time.sleep(2.0)
    try:
        section = lab._section(core)
        request = _d(section.get("queued_request"))
        state = str(section.get("status") or "not_run")
        if (
            state in {"queued", "running"}
            and request
            and not _thread_alive(core)
            and not lab._RUN_LOCK.locked()
        ):
            start(
                core,
                period=str(request.get("period") or lab.AUTO_PERIOD),
                max_symbols=max(
                    20,
                    min(75, int(_f(request.get("max_symbols"), lab.AUTO_MAX_SYMBOLS))),
                ),
                force=bool(request.get("force", True)),
                include_ablation=bool(request.get("include_ablation", True)),
                resume=True,
            )
    except Exception as exc:
        section = lab._section(core)
        section["resilient_recovery_error"] = f"{type(exc).__name__}: {exc}"
        _save(core)


def _enhanced_status(core: Any) -> Dict[str, Any]:
    payload = lab.status(core)
    section = lab._section(core)
    runner = _d(section.get("resilient_runner"))
    payload["resilient_runner"] = {
        **runner,
        "thread_alive": _thread_alive(core),
        "engine_locked": lab._RUN_LOCK.locked(),
        "queued_request": section.get("queued_request"),
        "core_checkpoint_available": bool(
            _d(_d(section.get("resilient_core_checkpoint")).get("result")).get(
                "status"
            )
            == "ok"
        ),
        "ablation_partial": {
            "completed_count": _d(section.get("resilient_ablation_partial")).get(
                "completed_count", 0
            ),
            "variant_count": _d(section.get("resilient_ablation_partial")).get(
                "variant_count", 0
            ),
        },
        "last_interrupted_state": section.get("last_interrupted_state"),
    }
    payload["run_status"] = section.get("status") or payload.get("run_status")
    payload["async_launcher_error"] = section.get("async_launcher_error")
    return payload


def apply(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "reason": "flask_app_missing"}
    core = core or lab._core()

    lab.register_routes(flask_app, core)

    from flask import jsonify, request

    def async_run_route():
        runtime = core or lab._core()
        period = str(request.args.get("period") or lab.AUTO_PERIOD)
        max_symbols = max(
            20,
            min(75, lab._i(request.args.get("symbols"), lab.AUTO_MAX_SYMBOLS)),
        )
        force = _bool_arg(request.args.get("force"), False)
        include_ablation = _bool_arg(request.args.get("ablation"), True)
        payload = start(
            runtime,
            period,
            max_symbols,
            force,
            include_ablation,
        )
        code = 202 if payload.get("status") in {"started", "running"} else 200
        return jsonify(payload), code

    def enhanced_status_route():
        return jsonify(_enhanced_status(core or lab._core()))

    async_run_route._performance_audit_v2_async_version = VERSION  # type: ignore[attr-defined]
    enhanced_status_route._performance_audit_v2_async_version = VERSION  # type: ignore[attr-defined]

    if flask_app.view_functions.get("performance_backtest_v2") is None:
        return {
            "status": "error",
            "version": VERSION,
            "reason": "performance_backtest_v2_endpoint_missing",
        }
    flask_app.view_functions["performance_backtest_v2"] = async_run_route
    if flask_app.view_functions.get("performance_audit_v2_status") is not None:
        flask_app.view_functions["performance_audit_v2_status"] = enhanced_status_route

    routes = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if "/paper/performance-backtest-v2-start" not in routes:
        flask_app.add_url_rule(
            "/paper/performance-backtest-v2-start",
            "performance_backtest_v2_async_start",
            async_run_route,
        )

    if id(core) not in _RECOVERY_STARTED:
        _RECOVERY_STARTED.add(id(core))
        threading.Thread(
            target=_recover_after_startup,
            args=(core,),
            name="performance-audit-v2-recovery",
            daemon=True,
        ).start()

    _REGISTERED.add(id(flask_app))
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "replaced_endpoints": [
            "performance_backtest_v2",
            "performance_audit_v2_status",
        ],
        "routes": [
            "/paper/performance-backtest-v2",
            "/paper/performance-backtest-v2-start",
            "/paper/performance-audit-v2-status",
        ],
        "resumable": True,
        "staged_ablation": True,
        "authority": {
            "advisory_only": True,
            "changes_strategy": False,
            "places_orders": False,
        },
    }


try:
    _core = lab._core()
    if _core is not None and getattr(_core, "app", None) is not None:
        apply(_core.app, _core)
except Exception:
    pass
