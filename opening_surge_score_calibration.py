"""Two-stage score calibration for the paper opening-surge valve.

The raw scanner score is used only as a profiling prefilter. Candidates must
still pass the existing opening-gap, post-open follow-through, opening-range,
near-high, momentum, volume, bucket, cluster, permission, and hard-risk checks.
A fully confirmed structure receives an auditable composite score before it is
returned to the normal core entry pipeline.

Paper-only. No direct orders, live authority, ML authority, hard-risk changes,
position-limit changes, or broad defensive-regime permission.
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from typing import Any, Dict

VERSION = "opening-surge-score-calibration-2026-07-31-v1"
PREFILTER_SCORE = float(
    os.getenv("OPENING_SURGE_PROFILE_PREFILTER_SCORE", "0.012")
)
FINAL_SCORE_FLOOR = float(
    os.getenv("OPENING_SURGE_STRUCTURE_SCORE_FLOOR", "0.045")
)
FINAL_SCORE_CAP = float(
    os.getenv("OPENING_SURGE_STRUCTURE_SCORE_CAP", "0.080")
)
STRUCTURE_BASE_CREDIT = float(
    os.getenv("OPENING_SURGE_STRUCTURE_BASE_CREDIT", "0.018")
)

_LOCK = threading.RLock()
_WATCHDOGS: set[int] = set()
_REGISTERED_APPS: set[int] = set()
_LAST_INSTALL: Dict[str, Any] = {}
_LAST_PROFILE: Dict[str, Any] = {}


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _module():
    import opening_surge_participation as opening

    return opening


def _composite_score(opening: Any, profile: Dict[str, Any]) -> Dict[str, float]:
    raw = _f(profile.get("score"))
    day_move = _f(profile.get("day_move_pct")) / 100.0
    session_move = _f(profile.get("session_move_pct")) / 100.0
    relative_volume = _f(profile.get("relative_volume_ratio"))

    day_excess = max(
        0.0,
        day_move - _f(getattr(opening, "MIN_DAY_MOVE", 0.08)),
    )
    session_excess = max(
        0.0,
        session_move - _f(getattr(opening, "MIN_SESSION_MOVE", 0.04)),
    )
    volume_excess = max(
        0.0,
        relative_volume - _f(getattr(opening, "MIN_RVOL", 1.25)),
    )

    day_bonus = min(0.008, day_excess * 0.20)
    session_bonus = min(0.008, session_excess * 0.20)
    volume_bonus = min(0.006, volume_excess * 0.006)

    calculated = (
        raw
        + STRUCTURE_BASE_CREDIT
        + day_bonus
        + session_bonus
        + volume_bonus
    )
    adjusted = min(
        FINAL_SCORE_CAP,
        max(FINAL_SCORE_FLOOR, calculated),
    )
    return {
        "raw_score": round(raw, 6),
        "structure_base_credit": round(STRUCTURE_BASE_CREDIT, 6),
        "day_move_bonus": round(day_bonus, 6),
        "session_follow_through_bonus": round(session_bonus, 6),
        "relative_volume_bonus": round(volume_bonus, 6),
        "calculated_score": round(calculated, 6),
        "adjusted_score": round(adjusted, 6),
    }


def install(core: Any = None) -> Dict[str, Any]:
    global _LAST_INSTALL, _LAST_PROFILE

    with _LOCK:
        opening = _module()
        prior_floor = _f(getattr(opening, "MIN_SCORE", 0.0))
        opening.MIN_SCORE = PREFILTER_SCORE

        current = getattr(opening, "_profile", None)
        if not callable(current):
            _LAST_INSTALL = {
                "status": "warn",
                "overall": "warn",
                "version": VERSION,
                "generated_local": _now(core),
                "reason": "opening_profile_missing",
            }
            return dict(_LAST_INSTALL)

        active = (
            getattr(
                current,
                "_opening_surge_score_calibration_version",
                None,
            )
            == VERSION
        )
        patched = False
        if not active:
            original = getattr(
                current,
                "_opening_surge_score_calibration_original",
                current,
            )

            def calibrated_profile(
                profile_core: Any,
                row: Dict[str, Any],
                minutes: float,
                __original=original,
            ) -> Dict[str, Any]:
                global _LAST_PROFILE

                result = dict(__original(profile_core, row, minutes) or {})
                raw_score = _f(row.get("score"))
                result.setdefault("raw_score", round(raw_score, 6))
                result["profile_prefilter_score"] = PREFILTER_SCORE
                result["final_structure_score_floor"] = FINAL_SCORE_FLOOR

                if result.get("qualified"):
                    ledger = _composite_score(opening, result)
                    result["score_calibration"] = ledger
                    result["raw_score"] = ledger["raw_score"]
                    result["score"] = ledger["adjusted_score"]
                    result["reason"] = (
                        "opening_surge_structure_and_score_confirmed"
                    )

                _LAST_PROFILE = {
                    "generated_local": _now(profile_core),
                    "symbol": result.get("symbol"),
                    "qualified": bool(result.get("qualified")),
                    "reason": result.get("reason"),
                    "raw_score": result.get("raw_score"),
                    "promoted_score": result.get("score"),
                    "score_calibration": result.get("score_calibration"),
                }
                return result

            calibrated_profile._opening_surge_score_calibration_version = VERSION
            calibrated_profile._opening_surge_score_calibration_original = original
            calibrated_profile.__wrapped__ = original
            opening._profile = calibrated_profile
            patched = True

        active = (
            getattr(
                getattr(opening, "_profile", None),
                "_opening_surge_score_calibration_version",
                None,
            )
            == VERSION
        )
        _LAST_INSTALL = {
            "status": "ok" if active else "warn",
            "overall": "pass" if active else "warn",
            "version": VERSION,
            "generated_local": _now(core),
            "patched_this_call": patched,
            "active": active,
            "prior_raw_score_floor": prior_floor,
            "profile_prefilter_score": PREFILTER_SCORE,
            "final_structure_score_floor": FINAL_SCORE_FLOOR,
            "final_structure_score_cap": FINAL_SCORE_CAP,
            "structure_base_credit": STRUCTURE_BASE_CREDIT,
            "opening_surge_version": getattr(opening, "VERSION", None),
        }
        setattr(
            opening,
            "OPENING_SURGE_SCORE_CALIBRATION_VERSION",
            VERSION,
        )
        if core is not None:
            setattr(
                core,
                "OPENING_SURGE_SCORE_CALIBRATION_VERSION",
                VERSION,
            )
        return dict(_LAST_INSTALL)


def status_payload(core: Any = None) -> Dict[str, Any]:
    installed = install(core)
    opening = _module()
    current = getattr(opening, "_profile", None)
    active = (
        getattr(
            current,
            "_opening_surge_score_calibration_version",
            None,
        )
        == VERSION
    )
    return {
        "status": "ok" if active else "warn",
        "overall": "pass" if active else "warn",
        "type": "opening_surge_score_calibration_status",
        "version": VERSION,
        "generated_local": _now(core),
        "active": active,
        "settings": {
            "profile_prefilter_score": PREFILTER_SCORE,
            "final_structure_score_floor": FINAL_SCORE_FLOOR,
            "final_structure_score_cap": FINAL_SCORE_CAP,
            "structure_base_credit": STRUCTURE_BASE_CREDIT,
            "existing_structure_tests_unchanged": True,
            "existing_cluster_requirement_unchanged": True,
            "existing_opening_window_unchanged": True,
        },
        "last_install": installed,
        "last_profile": dict(_LAST_PROFILE),
        "authority": {
            "paper_only": True,
            "places_orders_directly": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "changes_hard_risk_limits": False,
            "changes_position_limits": False,
            "changes_opening_permission": False,
            "changes_structure_tests": False,
            "changes_cluster_requirement": False,
            "changes_score_calibration": True,
            "raw_score_is_prefilter_only": True,
        },
    }


def register_routes(
    flask_app: Any,
    core: Any = None,
) -> Dict[str, Any]:
    if flask_app is None:
        return {
            "status": "pending",
            "version": VERSION,
            "reason": "flask_app_missing",
        }
    install(core)
    if id(flask_app) in _REGISTERED_APPS:
        return {
            "status": "ok",
            "version": VERSION,
            "already_registered": True,
        }

    from flask import jsonify

    path = "/paper/opening-surge-score-calibration-status"
    existing = {
        getattr(rule, "rule", "")
        for rule in flask_app.url_map.iter_rules()
    }
    if path not in existing:
        flask_app.add_url_rule(
            path,
            "opening_surge_score_calibration_status",
            lambda: jsonify(status_payload(core)),
        )
    _REGISTERED_APPS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": [path]}


def start_watchdog(core: Any = None) -> Dict[str, Any]:
    install(core)
    flask_app = getattr(core, "app", None) if core is not None else None
    if flask_app is not None:
        register_routes(flask_app, core)

    if core is None or id(core) in _WATCHDOGS:
        return {
            "status": "ok",
            "version": VERSION,
            "watchdog_started": (
                core is not None and id(core) in _WATCHDOGS
            ),
        }

    _WATCHDOGS.add(id(core))

    def watch() -> None:
        for iteration in range(1200):
            try:
                install(core)
            except Exception:
                pass
            time.sleep(0.5 if iteration < 60 else 30.0)

    threading.Thread(
        target=watch,
        daemon=True,
        name="opening-surge-score-calibration-watchdog",
    ).start()
    return {"status": "ok", "version": VERSION, "watchdog_started": True}
