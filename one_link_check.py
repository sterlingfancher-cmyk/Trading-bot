"""One-link check patch.

Keeps the user's daily testing flow to one URL: /paper/self-check.
Adds journal truth, classic signal mode, intraday timing, position-quality,
benchmark comparison, and market participation status into the light self-check
set without requiring Sterling to manually test more endpoints after each deploy.
"""
from __future__ import annotations

VERSION = "one-link-benchmark-participation-check-2026-05-13"


def _add_endpoint(light, endpoint, after_path=None):
    if not isinstance(light, list):
        return
    if any(isinstance(item, dict) and item.get("path") == endpoint["path"] for item in light):
        return
    insert_at = len(light)
    if after_path:
        for idx, item in enumerate(light):
            if isinstance(item, dict) and item.get("path") == after_path:
                insert_at = idx + 1
                break
    light.insert(insert_at, endpoint)


def apply(self_check_module=None):
    try:
        if self_check_module is None:
            import self_check as self_check_module  # type: ignore[no-redef]
        light = getattr(self_check_module, "LIGHT_ENDPOINTS", None)
        _add_endpoint(light, {"path": "/paper/journal-truth-status", "category": "journal", "required": True}, after_path="/paper/trade-event-hook-status")
        _add_endpoint(light, {"path": "/paper/classic-signal-status", "category": "risk", "required": True}, after_path="/paper/risk-improvement-status")
        _add_endpoint(light, {"path": "/paper/intraday-timing-status", "category": "risk", "required": True}, after_path="/paper/classic-signal-status")
        _add_endpoint(light, {"path": "/paper/position-quality-status", "category": "risk", "required": True}, after_path="/paper/intraday-timing-status")
        _add_endpoint(light, {"path": "/paper/benchmark-comparison", "category": "benchmark", "required": True}, after_path="/paper/position-quality-status")
        _add_endpoint(light, {"path": "/paper/market-participation-status", "category": "benchmark", "required": True}, after_path="/paper/benchmark-comparison")
        return {
            "status": "ok",
            "version": VERSION,
            "journal_truth_in_self_check": True,
            "classic_signal_in_self_check": True,
            "intraday_timing_in_self_check": True,
            "position_quality_in_self_check": True,
            "benchmark_comparison_in_self_check": True,
            "market_participation_in_self_check": True,
            "single_best_link": "/paper/self-check",
        }
    except Exception as exc:
        return {
            "status": "error",
            "version": VERSION,
            "journal_truth_in_self_check": False,
            "classic_signal_in_self_check": False,
            "intraday_timing_in_self_check": False,
            "position_quality_in_self_check": False,
            "benchmark_comparison_in_self_check": False,
            "market_participation_in_self_check": False,
            "error": str(exc),
        }


def register_routes(flask_app=None, module=None):
    # Nothing new to register. This module patches self_check's existing route list.
    try:
        import self_check
        return apply(self_check)
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": str(exc)}
