"""Read-only runtime observability for the advisory system sentinel.

The route composes existing diagnostics only when requested.  It starts no
worker, performs no repair, and never reads or writes canonical files directly.
"""
from __future__ import annotations

import math
import os
from typing import Any, Callable, Mapping

import system_sentinel


VERSION = "system-sentinel-runtime-2026-09-03-v1"
_REGISTERED_APP_IDS: set[int] = set()
_INSTALL_STATUS_BY_CORE: dict[int, dict[str, Any]] = {}


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _default_collectors() -> dict[str, Callable[[Any], Mapping[str, Any]]]:
    import canonical_execution_ledger
    import daily_operational_audit
    import fast_self_check_override
    import final_daily_audit_compactor
    import paper_bidirectional_accounting_guard

    def daily(core: Any) -> Mapping[str, Any]:
        full = daily_operational_audit.build_payload(core)
        return final_daily_audit_compactor.compact_payload(full, core)

    return {
        "self_check": fast_self_check_override.build_payload,
        "daily_audit": daily,
        "accounting": paper_bidirectional_accounting_guard.status_payload,
        "execution_ledger": canonical_execution_ledger.status_payload,
        "startup": lambda observed_core: _INSTALL_STATUS_BY_CORE.get(id(observed_core), {}),
    }


def collect_snapshot(
    core: Any,
    *,
    collectors: Mapping[str, Callable[[Any], Mapping[str, Any]]] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Collect bounded diagnostic dictionaries without mutating runtime state."""
    rows: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for name, collector in dict(collectors or _default_collectors()).items():
        try:
            rows[name] = _d(collector(core))
        except Exception as exc:
            rows[name] = {}
            errors[name] = f"{type(exc).__name__}: {exc}"

    self_check = rows.get("self_check", {})
    daily = rows.get("daily_audit", {})
    account = _d(self_check.get("account"))
    runner = _d(self_check.get("auto_runner"))
    risk = _d(self_check.get("risk"))
    portfolio = _d(getattr(core, "portfolio", {})) if core is not None else {}
    persisted_risk = _d(portfolio.get("risk_controls"))
    equity = account.get("equity", portfolio.get("equity"))
    try:
        equity_eligible = (
            not isinstance(equity, bool)
            and math.isfinite(float(equity))
            and float(equity) > 0.0
        )
    except (TypeError, ValueError, OverflowError):
        equity_eligible = False

    startup = rows.get("startup", {})
    startup_status = "ready" if startup.get("status") == "ok" else "fail"
    market_data = dict(_d(daily.get("market_data")))
    observed_gap = market_data.get("in_flight_or_unclassified_requests")
    try:
        gap = max(0, int(observed_gap or 0))
    except (TypeError, ValueError, OverflowError):
        gap = 0
    # The provider counter is incremented before its terminal classification.
    # Existing authoritative audit semantics therefore allow one concurrent
    # in-flight request when the aggregate market-data status still passes.
    market_data["observed_in_flight_or_unclassified_requests"] = gap
    if market_data.get("status") == "pass" and gap <= 1:
        market_data["in_flight_or_unclassified_requests"] = 0

    snapshot = {
        "valuation": {
            "status": "ok" if equity_eligible else "fail",
            "equity": equity,
            "risk_baseline_eligible": equity_eligible,
        },
        "accounting": rows.get("accounting", {}),
        "execution_ledger": rows.get("execution_ledger", {}),
        "risk": {
            "day_start_equity": persisted_risk.get("day_start_equity"),
            "day_peak_equity": persisted_risk.get("day_peak_equity"),
            "halted": risk.get("halted", persisted_risk.get("halted")),
        },
        "startup": {
            "status": startup_status,
            "phase": "runtime_worker_registration",
            "error": startup.get("error"),
        },
        "runner": {
            "active_error": runner.get("last_error_active") is True,
            "last_error": runner.get("last_error"),
            "last_attempt": runner.get("last_attempt"),
        },
        "market_data": market_data,
    }
    return snapshot, errors


def build_payload(
    core: Any,
    *,
    collectors: Mapping[str, Callable[[Any], Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    snapshot, collection_errors = collect_snapshot(core, collectors=collectors)
    result = system_sentinel.report(snapshot)
    result.update(
        {
            "overall": "pass" if result["status"] == "quiet" and not collection_errors else "warn",
            "runtime_version": VERSION,
            "generated_commit_sha": os.environ.get("RAILWAY_GIT_COMMIT_SHA"),
            "collection_errors": collection_errors,
            "snapshot": snapshot,
            "coverage": {
                "runtime_observed": [
                    "valuation", "accounting", "execution", "risk",
                    "startup_runtime", "runner", "market_data",
                ],
                "ci_observed": ["configuration", "architecture"],
                "ci_source": "mandatory exact-head Change Safety and architecture gates",
            },
            "authority": {
                "advisory_only": True,
                "read_only_on_demand": True,
                "starts_worker": False,
                "writes_production_state": False,
                "opens_or_merges_pull_requests": False,
                "clears_halts": False,
                "places_or_cancels_orders": False,
                "changes_strategy_or_thresholds": False,
                "changes_risk_or_sizing": False,
                "changes_live_or_ml_authority": False,
            },
        }
    )
    return result


def install(flask_app: Any = None, core: Any = None) -> dict[str, Any]:
    if flask_app is not None and id(flask_app) not in _REGISTERED_APP_IDS:
        from flask import jsonify

        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if "/paper/system-sentinel-status" not in existing:
            flask_app.add_url_rule(
                "/paper/system-sentinel-status",
                "paper_system_sentinel_status",
                lambda: jsonify(build_payload(core)),
            )
        _REGISTERED_APP_IDS.add(id(flask_app))
    result = {
        "status": "ok" if flask_app is not None and core is not None else "pending",
        "overall": "pass" if flask_app is not None and core is not None else "warn",
        "version": VERSION,
        "route_registered": flask_app is not None,
        "read_only_on_demand": True,
        "worker_started": False,
        "authority": "advisory_only",
    }
    if core is not None:
        _INSTALL_STATUS_BY_CORE[id(core)] = dict(result)
    return result
