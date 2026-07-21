"""Confidence-adjusted theme leadership for Scanner v2 shadow scoring.

Advisory-only overlay. It consumes the existing shadow composite report and adds
sample-size confidence so one-symbol themes cannot outrank broader leadership solely
because one stock had a large move.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

VERSION = "scanner-v2-theme-confidence-overlay-2026-07-21-v1"
REGISTERED_APP_IDS: set[int] = set()
MIN_FULL_CONFIDENCE_MEMBERS = 4


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def confidence_adjust(report: Dict[str, Any]) -> Dict[str, Any]:
    themes = report.get("theme_leadership") if isinstance(report, dict) else []
    adjusted: List[Dict[str, Any]] = []
    for row in themes if isinstance(themes, list) else []:
        if not isinstance(row, dict):
            continue
        members = int(_safe_float(row.get("members_scored"), 0.0))
        raw_score = _safe_float(row.get("leadership_score"), 0.0)
        sample_confidence = _clamp(math.sqrt(max(members, 0) / float(MIN_FULL_CONFIDENCE_MEMBERS)))
        breadth = _safe_float(row.get("positive_breadth"), 0.0) / max(members, 1)
        strong_share = _safe_float(row.get("strong_member_count"), 0.0) / max(members, 1)
        adjusted_score = _clamp(raw_score * (0.55 + 0.45 * sample_confidence))
        confidence_class = (
            "broad_confirmed" if members >= MIN_FULL_CONFIDENCE_MEMBERS and breadth >= 0.5 else
            "partial_confirmation" if members >= 2 else
            "single_member_signal"
        )
        adjusted.append({
            **row,
            "raw_leadership_score": round(raw_score, 6),
            "sample_confidence": round(sample_confidence, 6),
            "confidence_adjusted_leadership_score": round(adjusted_score, 6),
            "positive_breadth_ratio": round(breadth, 6),
            "strong_member_ratio": round(strong_share, 6),
            "confidence_class": confidence_class,
            "eligible_for_theme_confirmation": bool(members >= 2),
        })
    adjusted.sort(key=lambda row: _safe_float(row.get("confidence_adjusted_leadership_score")), reverse=True)
    return {
        "status": report.get("status", "ok") if isinstance(report, dict) else "ok",
        "overall": report.get("overall", "pass") if isinstance(report, dict) else "pass",
        "type": "scanner_v2_theme_confidence_overlay",
        "version": VERSION,
        "mode": "advisory_shadow_only",
        "source_version": report.get("version") if isinstance(report, dict) else None,
        "market_data_requested": bool(report.get("market_data_requested")) if isinstance(report, dict) else False,
        "ranked_candidates": report.get("ranked_candidates", []) if isinstance(report, dict) else [],
        "theme_leadership_confidence_adjusted": adjusted,
        "policy": {
            "minimum_members_for_theme_confirmation": 2,
            "members_for_full_sample_confidence": MIN_FULL_CONFIDENCE_MEMBERS,
            "single_member_themes_are_observations_not_confirmed_leadership": True,
        },
        "authority": {
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "changes_risk_or_sizing": False,
            "changes_thresholds": False,
            "core_universe_mutated": False,
            "places_orders": False,
            "scan_signals_patched": False,
        },
        "next_gate": "Score broader theme membership over repeated sessions before using theme leadership in any paper-only promotion proposal.",
    }


def build_report(core: Any = None, symbols=None, force_market_data: bool = False) -> Dict[str, Any]:
    try:
        import scanner_v2_shadow_composite_score as source  # type: ignore
        base = source.build_report(core, symbols=symbols, force_market_data=force_market_data)
    except Exception as exc:
        base = {"status": "warn", "overall": "warn", "version": None, "error": f"source_unavailable:{type(exc).__name__}"}
    return confidence_adjust(base)


def apply(core: Any = None) -> Dict[str, Any]:
    return build_report(core, force_market_data=False)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify, request
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def route():
        raw = str(request.args.get("symbols", "")).strip()
        symbols = raw.split(",") if raw else None
        force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes"}
        return jsonify(build_report(core, symbols=symbols, force_market_data=force))

    path = "/paper/scanner-v2-theme-confidence-status"
    if path not in existing:
        flask_app.add_url_rule(path, "scanner_v2_theme_confidence_status", route)
    REGISTERED_APP_IDS.add(id(flask_app))
