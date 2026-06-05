"""Runtime module registry and startup verification.

Read-only observability layer for the overlay architecture.
It reports which important modules are loaded and whether optional diagnostic
routes are registered.

This module does not trade, resize, change risk controls, change ML authority,
or modify strategy behavior.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, List

VERSION = "runtime-module-registry-2026-06-04-v1-manual"
REGISTERED_APP_IDS: set[int] = set()

CRITICAL_MODULES = [
    "state_io_hardening",
    "runner_safety",
    "trade_journal",
    "state_journal_guard",
    "decision_audit_consolidation",
    "ml_phase2_shadow",
    "ml_phase25_readiness",
    "ml_feature_journal_quality",
    "intratrade_path_capture",
    "mae_mfe_integration",
    "state_size_watchdog",
    "advisory_authority_guard",
    "paper_controlled_expansion",
    "post_harvest_redeployment_controller",
    "post_harvest_entry_fallback",
    "expansion_impact_monitor",
]

ADVISORY_ONLY_MODULES = [
    "runtime_module_registry",
    "expansion_impact_monitor",
    "decision_audit_consolidation",
    "news_sentiment_engine",
    "ml_phase2_shadow",
    "ml_phase25_readiness",
    "ml_feature_journal_quality",
    "trade_quality_telemetry",
    "intratrade_path_capture",
    "mae_mfe_integration",
    "adaptive_ml_research",
    "adaptive_portfolio_intelligence",
    "strategy_scorecard",
    "strategy_promotion_readiness",
]

BEHAVIOR_MODULES = [
    "paper_controlled_expansion",
    "post_harvest_redeployment_controller",
    "post_harvest_entry_fallback",
    "risk_bootstrap",
    "market_extension_guard",
    "risk_reward_structure",
    "position_quality_governor",
    "benchmark_participation",
    "relative_strength_leader_exception",
    "pattern_recognition_layer",
    "loss_streak_defensive_governor",
    "multi_timeframe_swing",
]

EXPECTED_ROUTES = {
    "runtime_module_registry": [
        "/paper/runtime-module-registry-status",
        "/paper/startup-patch-status",
    ],
    "expansion_impact_monitor": [
        "/paper/expansion-impact-status",
        "/paper/expansion-impact-monitor",
    ],
    "paper_controlled_expansion": [
        "/paper/paper-controlled-expansion-status",
    ],
    "state_size_watchdog": [
        "/paper/state-size-watchdog",
    ],
    "decision_audit_consolidation": [
        "/paper/decision-audit-status",
    ],
    "ml_phase2_shadow": [
        "/paper/ml2-status",
    ],
    "ml_phase25_readiness": [
        "/paper/ml-readiness-status",
        "/paper/ml-phase25-status",
    ],
    "ml_feature_journal_quality": [
        "/paper/ml-feature-journal-status",
    ],
    "mae_mfe_integration": [
        "/paper/mae-mfe-integration-status",
    ],
}


def _now(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _routes(flask_app: Any = None) -> List[str]:
    try:
        return sorted(
            {
                getattr(rule, "rule", "")
                for rule in flask_app.url_map.iter_rules()
                if getattr(rule, "rule", "")
            }
        )
    except Exception:
        return []


def build_payload(core: Any = None, flask_app: Any = None) -> Dict[str, Any]:
    route_set = set(_routes(flask_app))

    modules: Dict[str, Dict[str, Any]] = {}
    names = sorted(set(CRITICAL_MODULES + ADVISORY_ONLY_MODULES + BEHAVIOR_MODULES))

    for name in names:
        loaded = name in sys.modules
        expected_routes = EXPECTED_ROUTES.get(name, [])
        registered_routes = [route for route in expected_routes if route in route_set]
        missing_routes = [route for route in expected_routes if route not in route_set]

        modules[name] = {
            "module": name,
            "loaded": loaded,
            "critical": name in CRITICAL_MODULES,
            "advisory_only": name in ADVISORY_ONLY_MODULES,
            "behavior_affecting": name in BEHAVIOR_MODULES,
            "expected_routes": expected_routes,
            "registered_routes": registered_routes,
            "missing_routes": missing_routes,
            "version": getattr(sys.modules.get(name), "VERSION", None),
        }

    critical_missing = [
        name for name, row in modules.items()
        if row["critical"] and not row["loaded"]
    ]

    critical_missing_routes = [
        name for name, row in modules.items()
        if row["critical"] and row["expected_routes"] and row["missing_routes"]
    ]

    if critical_missing:
        overall = "fail"
    elif critical_missing_routes:
        overall = "warn"
    else:
        overall = "pass"

    payload = {
        "status": "ok" if overall == "pass" else "warn" if overall == "warn" else "fail",
        "overall": overall,
        "type": "runtime_module_registry_status",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "authority_changed": False,
        "summary": {
            "modules_checked": len(modules),
            "critical_modules": len(CRITICAL_MODULES),
            "critical_missing": critical_missing,
            "critical_missing_routes": critical_missing_routes,
            "routes_registered_count": len(route_set),
            "behavior_affecting_modules": [
                name for name, row in modules.items()
                if row["behavior_affecting"]
            ],
            "advisory_only_modules": [
                name for name, row in modules.items()
                if row["advisory_only"]
            ],
        },
        "modules": modules,
        "recommendation": (
            "Runtime overlays verified."
            if overall == "pass"
            else "Review missing critical overlays/routes before adding more trading features."
        ),
    }

    try:
        if core is not None and hasattr(core, "portfolio"):
            core.portfolio["runtime_module_registry"] = {
                "status": payload["status"],
                "overall": payload["overall"],
                "version": VERSION,
                "summary": payload["summary"],
                "authority_changed": False,
            }
    except Exception:
        pass

    return payload


def apply(core: Any = None) -> Dict[str, Any]:
    return build_payload(core=core, flask_app=getattr(core, "app", None))


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    from flask import jsonify

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        return jsonify(build_payload(core=core, flask_app=flask_app))

    if "/paper/runtime-module-registry-status" not in existing:
        flask_app.add_url_rule(
            "/paper/runtime-module-registry-status",
            "runtime_module_registry_status",
            status_route,
        )

    if "/paper/startup-patch-status" not in existing:
        flask_app.add_url_rule(
            "/paper/startup-patch-status",
            "startup_patch_status",
            status_route,
        )

    REGISTERED_APP_IDS.add(id(flask_app))
