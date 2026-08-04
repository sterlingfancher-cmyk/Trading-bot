"""Paper participation capacity guard loaded from the bootstrap import path.

This guard repairs three narrow causes of chronic paper-account underdeployment:

1. Persisted position timestamps are Unix epochs. A naive conversion in the
   Railway container timezone could later be relabeled as Central time, moving
   an old entry into the future and holding the 15-minute starter-spacing gate
   at zero seconds forever.
2. The risk-on starter valve previously required exactly zero mark-to-market
   drawdown. A few dollars of normal unrealized noise could therefore disable
   every additional starter even while all hard risk controls remained clear.
3. A high-scoring, controlled-retest starter could be vetoed solely because the
   pattern classifier labeled an otherwise constructive setup ``mixed_structure``.
   A tightly bounded paper-only exception now permits one diversified second
   starter when the loss state is clear and the account remains mostly cash.

The guard patches every loaded copy of the affected modules, including modules
loaded through an alternate bootstrap path. It does not change the configured
spacing, global signal scores, sizing, hard loss limits, broker authority,
live-trading authority, or order execution.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

VERSION = "paper-participation-capacity-guard-2026-08-04-v5-controlled-retest"
STARTER_MARK_TO_MARKET_TOLERANCE_PCT = float(
    os.environ.get("RISK_ON_STARTER_MARK_TO_MARKET_TOLERANCE_PCT", "0.10")
)
CONTROLLED_RETEST_MIN_SCORE = float(
    os.environ.get("CONTROLLED_RETEST_STARTER_MIN_SCORE", "0.0525")
)
CONTROLLED_RETEST_MIN_CASH_PCT = float(
    os.environ.get("CONTROLLED_RETEST_STARTER_MIN_CASH_PCT", "75.0")
)
CONTROLLED_RETEST_MAX_OPEN_POSITIONS = int(
    os.environ.get("CONTROLLED_RETEST_STARTER_MAX_OPEN_POSITIONS", "1")
)
CONTROLLED_RETEST_ALLOWED_MODES = {
    value.strip().lower()
    for value in os.environ.get(
        "CONTROLLED_RETEST_STARTER_ALLOWED_MODES", "constructive,risk_on"
    ).split(",")
    if value.strip()
}
CONTROLLED_RETEST_POSITIVE_PATTERNS = {
    "breakout_retest_hold",
    "relative_strength_pullback",
    "higher_low_continuation",
    "failed_breakdown_reclaim",
}
CONTROLLED_RETEST_ALLOWED_RISK_PATTERNS = {"overextension_chase_risk"}
_LOCK = threading.RLock()
_PATCHED = False
_STARTED = False
_STATUS: Dict[str, Any] = {
    "version": VERSION,
    "status": "pending",
    "patched": False,
    "targets": [
        "paper_underdeployment_repair._parse_time",
        "risk_on_starter_participation_valve.MAX_DAILY_LOSS_PCT",
        "loss_streak_defensive_governor._govern_signal",
    ],
}


def _epoch_datetime(value: Any) -> dt.datetime | None:
    try:
        number = float(value)
        if not math.isfinite(number):
            return None
        if abs(number) >= 100_000_000_000:
            number /= 1000.0
        return dt.datetime.fromtimestamp(number, tz=dt.timezone.utc)
    except Exception:
        return None


def parse_time(value: Any) -> dt.datetime | None:
    """Parse timestamps while preserving absolute epoch semantics."""
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _epoch_datetime(value)

    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return _epoch_datetime(text)

    normalized = text.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    normalized = normalized.split(" CDT")[0].split(" CST")[0]
    for candidate in (normalized, normalized[:19]):
        try:
            return dt.datetime.fromisoformat(candidate)
        except Exception:
            pass
    return None


def _matching_modules(canonical_name: str, filename: str) -> Iterable[tuple[str, Any]]:
    seen: set[int] = set()
    for name, module in list(sys.modules.items()):
        if module is None or id(module) in seen:
            continue
        module_file = str(getattr(module, "__file__", "") or "")
        file_match = False
        if module_file:
            try:
                file_match = Path(module_file).name == filename
            except Exception:
                file_match = module_file.endswith(filename)
        if name == canonical_name or file_match:
            seen.add(id(module))
            yield name, module


def _patch_timestamp_modules() -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for name, module in _matching_modules(
        "paper_underdeployment_repair", "paper_underdeployment_repair.py"
    ):
        current = getattr(module, "_parse_time", None)
        import_complete = callable(current) and callable(getattr(module, "install", None))
        if not import_complete:
            rows.append({"module": name, "patched": False, "reason": "import_incomplete"})
            continue
        if getattr(current, "_paper_participation_capacity_version", None) != VERSION:
            parse_time._paper_participation_capacity_version = VERSION  # type: ignore[attr-defined]
            parse_time._paper_participation_capacity_original = current  # type: ignore[attr-defined]
            setattr(module, "_parse_time", parse_time)
        rows.append(
            {
                "module": name,
                "patched": True,
                "module_file": str(getattr(module, "__file__", "") or ""),
                "unix_epochs_are_utc_aware": True,
            }
        )
    return rows


def _patch_starter_modules() -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for name, module in _matching_modules(
        "risk_on_starter_participation_valve",
        "risk_on_starter_participation_valve.py",
    ):
        if not callable(getattr(module, "_risk_ok", None)):
            rows.append({"module": name, "patched": False, "reason": "import_incomplete"})
            continue
        try:
            before = float(getattr(module, "MAX_DAILY_LOSS_PCT", 0.0))
        except Exception:
            before = 0.0
        after = max(before, STARTER_MARK_TO_MARKET_TOLERANCE_PCT)
        setattr(module, "MAX_DAILY_LOSS_PCT", after)
        setattr(module, "PAPER_PARTICIPATION_CAPACITY_GUARD_VERSION", VERSION)
        rows.append(
            {
                "module": name,
                "patched": True,
                "module_file": str(getattr(module, "__file__", "") or ""),
                "daily_loss_tolerance_before_pct": before,
                "daily_loss_tolerance_after_pct": after,
                "intraday_drawdown_tolerance_pct": getattr(
                    module, "MAX_INTRADAY_DRAWDOWN_PCT", None
                ),
            }
        )
    return rows


def _paper_context() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {
        "1", "true", "yes", "on"
    }
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {
        "live", "real", "production"
    }
    return not live and not broker_live


def _starter_context(signal: Dict[str, Any]) -> bool:
    text = " ".join(
        str(signal.get(key) or "").lower()
        for key in ("entry_context", "trade_class", "reason", "signal_type")
    )
    if isinstance(signal.get("core_participation_valve"), dict):
        text += " core_participation_valve"
    return any(token in text for token in ("starter", "participation_valve"))


def _cash_and_positions(module: Any, core: Any) -> Tuple[float, int]:
    try:
        portfolio = module._portfolio(core)
    except Exception:
        portfolio = getattr(core, "portfolio", {}) if core is not None else {}
    portfolio = portfolio if isinstance(portfolio, dict) else {}
    try:
        cash = float(portfolio.get("cash") or 0.0)
        equity = float(portfolio.get("equity") or cash or 0.0)
        cash_pct = (cash / equity * 100.0) if equity > 0 else 0.0
    except Exception:
        cash_pct = 0.0
    positions = portfolio.get("positions") or {}
    return cash_pct, len(positions) if isinstance(positions, dict) else 0


def _controlled_retest_exception(
    module: Any,
    core: Any,
    signal: Dict[str, Any],
    decision: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    reasons = {str(value) for value in decision.get("reasons", [])}
    loss_state = decision.get("loss_state") or {}
    pattern = decision.get("pattern_veto") or {}
    detected = {str(value) for value in pattern.get("patterns_detected", [])}
    risk_patterns = {str(value) for value in pattern.get("risk_patterns", [])}
    positive_hits = sorted(detected.intersection(CONTROLLED_RETEST_POSITIVE_PATTERNS))
    try:
        score = float(signal.get("score") or decision.get("score") or 0.0)
    except Exception:
        score = 0.0
    side = str(signal.get("side") or "long").lower()
    cash_pct, open_positions = _cash_and_positions(module, core)
    try:
        market = module._market_context(core)
    except Exception:
        market = {}
    mode = str((market or {}).get("market_mode") or (market or {}).get("regime") or "").lower()

    checks = {
        "paper_context": _paper_context(),
        "starter_context": _starter_context(signal),
        "long_only": side == "long",
        "only_pattern_chase_veto": reasons == {"pattern_chase_risk_veto"},
        "loss_state_clear": str(loss_state.get("level") or "") == "clear",
        "no_realized_losses_today": int(loss_state.get("losses_today") or 0) == 0,
        "no_stop_losses_today": int(loss_state.get("stop_losses_today") or 0) == 0,
        "market_mode_allowed": mode in CONTROLLED_RETEST_ALLOWED_MODES,
        "score_strong_enough": score >= CONTROLLED_RETEST_MIN_SCORE,
        "multiple_constructive_patterns": len(positive_hits) >= 2,
        "risk_pattern_is_only_extension": bool(risk_patterns)
        and risk_patterns.issubset(CONTROLLED_RETEST_ALLOWED_RISK_PATTERNS),
        "cash_high_enough": cash_pct >= CONTROLLED_RETEST_MIN_CASH_PCT,
        "second_position_only": open_positions <= CONTROLLED_RETEST_MAX_OPEN_POSITIONS,
    }
    allowed = all(checks.values())
    return allowed, {
        "version": VERSION,
        "allowed": allowed,
        "checks": checks,
        "market_mode": mode,
        "score": round(score, 6),
        "required_score": CONTROLLED_RETEST_MIN_SCORE,
        "cash_pct": round(cash_pct, 4),
        "required_cash_pct": CONTROLLED_RETEST_MIN_CASH_PCT,
        "open_positions": open_positions,
        "maximum_open_positions": CONTROLLED_RETEST_MAX_OPEN_POSITIONS,
        "positive_patterns": positive_hits,
        "risk_patterns": sorted(risk_patterns),
        "paper_only": True,
        "hard_risk_limits_unchanged": True,
        "sizing_unchanged": True,
    }


def _make_governor_wrapper(module: Any, original: Any):
    def guarded_govern_signal(core: Any, signal: Dict[str, Any]):
        ok, raw_decision = original(core, signal)
        decision = raw_decision if isinstance(raw_decision, dict) else {
            "reasons": [str(raw_decision)]
        }
        if ok or not isinstance(signal, dict):
            return ok, decision
        allowed, exception = _controlled_retest_exception(
            module, core, signal, decision
        )
        decision = dict(decision)
        decision["controlled_retest_starter_exception"] = exception
        if not allowed:
            return ok, decision
        decision["ok"] = True
        decision["original_reasons"] = list(decision.get("reasons", []))
        decision["reasons"] = []
        decision["paper_underdeployment_exception"] = "controlled_retest_second_starter"
        return True, decision

    guarded_govern_signal._paper_participation_capacity_version = VERSION  # type: ignore[attr-defined]
    guarded_govern_signal._paper_participation_capacity_original = original  # type: ignore[attr-defined]
    guarded_govern_signal.__wrapped__ = original
    return guarded_govern_signal


def _patch_pattern_governor_modules() -> list[Dict[str, Any]]:
    try:
        __import__("loss_streak_defensive_governor")
    except Exception:
        pass
    rows: list[Dict[str, Any]] = []
    for name, module in _matching_modules(
        "loss_streak_defensive_governor", "loss_streak_defensive_governor.py"
    ):
        current = getattr(module, "_govern_signal", None)
        if not callable(current):
            rows.append({"module": name, "patched": False, "reason": "import_incomplete"})
            continue
        if getattr(current, "_paper_participation_capacity_version", None) != VERSION:
            setattr(module, "_govern_signal", _make_governor_wrapper(module, current))
        rows.append(
            {
                "module": name,
                "patched": True,
                "module_file": str(getattr(module, "__file__", "") or ""),
                "exception": "controlled_retest_second_starter",
                "minimum_score": CONTROLLED_RETEST_MIN_SCORE,
                "minimum_cash_pct": CONTROLLED_RETEST_MIN_CASH_PCT,
                "maximum_open_positions": CONTROLLED_RETEST_MAX_OPEN_POSITIONS,
            }
        )
    return rows


def _latest_entry_age_seconds(module: Any) -> float | None:
    try:
        core = module._mod()
        latest = module._latest_entry(core)
        if latest is None:
            return None
        if latest.tzinfo is not None:
            now = dt.datetime.now(dt.timezone.utc)
            age = (now - latest.astimezone(dt.timezone.utc)).total_seconds()
        else:
            now = module._now_dt(core)
            if getattr(now, "tzinfo", None) is not None:
                latest = latest.replace(tzinfo=now.tzinfo)
            age = (now - latest).total_seconds()
        return round(max(0.0, age), 1)
    except Exception:
        return None


def apply() -> Dict[str, Any]:
    global _PATCHED, _STATUS
    with _LOCK:
        timestamp_modules = _patch_timestamp_modules()
        starter_modules = _patch_starter_modules()
        pattern_governor_modules = _patch_pattern_governor_modules()
        timestamp_patched = any(row.get("patched") for row in timestamp_modules)
        starter_patched = any(row.get("patched") for row in starter_modules)
        pattern_governor_patched = any(
            row.get("patched") for row in pattern_governor_modules
        )

        age_seconds = None
        for _, module in _matching_modules(
            "paper_underdeployment_repair", "paper_underdeployment_repair.py"
        ):
            age_seconds = _latest_entry_age_seconds(module)
            if age_seconds is not None:
                break

        _PATCHED = bool(
            timestamp_patched and starter_patched and pattern_governor_patched
        )
        _STATUS = {
            "version": VERSION,
            "status": "ok" if _PATCHED else "pending",
            "overall": "pass" if _PATCHED else "warn",
            "patched": _PATCHED,
            "timestamp_parser_patched": timestamp_patched,
            "starter_drawdown_tolerance_patched": starter_patched,
            "pattern_governor_patched": pattern_governor_patched,
            "timestamp_modules": timestamp_modules,
            "starter_modules": starter_modules,
            "pattern_governor_modules": pattern_governor_modules,
            "latest_entry_age_seconds": age_seconds,
            "starter_mark_to_market_tolerance_pct": STARTER_MARK_TO_MARKET_TOLERANCE_PCT,
            "controlled_retest_min_score": CONTROLLED_RETEST_MIN_SCORE,
            "controlled_retest_min_cash_pct": CONTROLLED_RETEST_MIN_CASH_PCT,
            "controlled_retest_max_open_positions": CONTROLLED_RETEST_MAX_OPEN_POSITIONS,
            "spacing_threshold_changed": False,
            "global_signal_scores_changed": False,
            "sizing_changed": False,
            "hard_risk_limits_changed": False,
            "live_authority_changed": False,
            "places_orders": False,
        }
        if not timestamp_modules:
            _STATUS["reason"] = "paper_underdeployment_module_not_loaded"
        elif not starter_modules:
            _STATUS["reason"] = "risk_on_starter_module_not_loaded"
        elif not pattern_governor_modules:
            _STATUS["reason"] = "loss_streak_governor_module_not_loaded"
        return dict(_STATUS)


def status_payload() -> Dict[str, Any]:
    row = apply()
    return {
        **row,
        "watcher_started": bool(_STARTED),
        "authority": {
            "paper_only": True,
            "timestamp_normalization": True,
            "changes_spacing_seconds": False,
            "changes_global_signal_thresholds": False,
            "changes_paper_starter_drawdown_tolerance": True,
            "adds_controlled_retest_second_starter_exception": True,
            "changes_hard_risk_limits": False,
            "changes_sizing": False,
            "changes_live_authority": False,
            "places_orders": False,
        },
    }


def start_guard(timeout_seconds: float = 180.0) -> Dict[str, Any]:
    """Patch immediately and keep checking briefly for alternate module copies."""
    global _STARTED
    first = apply()
    with _LOCK:
        if _STARTED:
            return status_payload()
        _STARTED = True

    def worker() -> None:
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            apply()
            time.sleep(0.25)

    threading.Thread(
        target=worker,
        name="paper-participation-capacity-guard",
        daemon=True,
    ).start()
    return {**first, "watcher_started": True}
