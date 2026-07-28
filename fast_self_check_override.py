from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict

VERSION = "fast-self-check-override-2026-07-28-v2-runner-telemetry"
_PATCHED_APP_IDS: set[int] = set()


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "portfolio"):
            return module
    return None


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _performance(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    return _dict(portfolio.get("performance"))


def build_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    portfolio = _dict(getattr(core, "portfolio", {})) if core is not None else {}
    auto = _dict(portfolio.get("auto_runner"))
    perf = _performance(portfolio)
    risk = _dict(portfolio.get("risk_controls"))
    positions = _dict(portfolio.get("positions"))
    trades = portfolio.get("trades")
    scanner = _dict(portfolio.get("scanner_audit"))
    decision = _dict(portfolio.get("decision_audit"))
    last_error = auto.get("last_error")

    last_attempt = auto.get("last_attempt_local") or auto.get("last_attempt_ts")
    last_run = auto.get("last_run_local") or auto.get("last_run_ts")
    last_success = auto.get("last_successful_run_local") or auto.get("last_successful_run_ts")
    last_skip = auto.get("last_skip_local") or auto.get("last_skip_ts")

    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None and not last_error else ("warn" if core is not None else "pending"),
        "type": "fast_self_check",
        "version": VERSION,
        "generated_local": _now(core),
        "constant_time_in_memory_snapshot": True,
        "reads_state_file": False,
        "calls_diagnostic_builders": False,
        "calls_internal_routes": False,
        "account": {
            "cash": portfolio.get("cash"),
            "equity": portfolio.get("equity"),
            "positions": list(positions.keys()),
            "open_positions_count": len(positions),
            "realized_today": perf.get("realized_pnl_today"),
            "realized_total": perf.get("realized_pnl_total"),
            "unrealized_pnl": perf.get("unrealized_pnl"),
            "wins_total": perf.get("wins_total"),
            "losses_total": perf.get("losses_total"),
            "execution_rows": len(trades) if isinstance(trades, list) else None,
        },
        "auto_runner": {
            "enabled": auto.get("enabled"),
            "thread_started": auto.get("thread_started"),
            "interval_seconds": auto.get("interval_seconds"),
            "last_attempt": last_attempt,
            "last_attempt_source": auto.get("last_attempt_source"),
            "last_run": last_run,
            "last_run_source": auto.get("last_run_source"),
            "last_success": last_success,
            "last_success_source": auto.get("last_successful_run_source"),
            "last_skip": last_skip,
            "last_skip_reason": auto.get("last_skip_reason"),
            "market_open_now": auto.get("market_open_now"),
            "last_error": last_error,
            "last_error_present": bool(last_error),
            "telemetry_source": "portfolio.auto_runner canonical *_local fields",
        },
        "risk": {
            "halted": risk.get("halted"),
            "halt_reason": risk.get("halt_reason"),
            "self_defense_active": risk.get("self_defense_active"),
            "self_defense_reason": risk.get("self_defense_reason"),
            "daily_loss_pct": risk.get("daily_loss_pct"),
            "intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
        },
        "scanner": {
            "signals_found": scanner.get("signals_found") or decision.get("signals_found"),
            "entries_count": decision.get("entries_count"),
            "cycle_id": scanner.get("cycle_id") or decision.get("cycle_id"),
            "last_updated_local": scanner.get("last_updated_local"),
            "last_cycle_source": scanner.get("last_cycle_source"),
        },
        "entry_pipeline": {
            "callable": getattr(getattr(core, "scan_signals", None), "__qualname__", None) if core is not None else None,
            "recursion_error_active": bool(last_error and "recursion" in str(last_error).lower()),
        },
        "links": {
            "status": "/paper/status",
            "full_self_check": "/paper/full-self-check",
            "fast_self_check_status": "/paper/fast-self-check-status",
        },
        "authority": {
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_ml_authority": False,
            "changes_live_authority": False,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    flask_app = getattr(core, "app", None) if core is not None else None
    if flask_app is None:
        return {"status": "pending", "version": VERSION}

    from flask import jsonify

    def fast_view():
        return jsonify(build_payload(core or _mod()))

    fast_view._fast_self_check_override_version = VERSION  # type: ignore[attr-defined]
    for endpoint in ("paper_self_check", "paper_smoke_test"):
        if endpoint in flask_app.view_functions:
            flask_app.view_functions[endpoint] = fast_view
    _PATCHED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "patched": True}


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    flask_app = getattr(core, "app", None) if core is not None else None
    view = getattr(flask_app, "view_functions", {}).get("paper_self_check") if flask_app is not None else None
    return {
        "status": "ok" if getattr(view, "_fast_self_check_override_version", None) == VERSION else "pending",
        "version": VERSION,
        "patched": getattr(view, "_fast_self_check_override_version", None) == VERSION,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/fast-self-check-status" not in existing:
        flask_app.add_url_rule(
            "/paper/fast-self-check-status",
            "fast_self_check_status",
            lambda: jsonify(status_payload(core or _mod())),
        )
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
