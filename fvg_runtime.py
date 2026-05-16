from __future__ import annotations

import functools
import os
from typing import Any, Dict, Iterable, List

VERSION = "fvg-runtime-2026-05-16"
PATCHED_MODULE_IDS: set[int] = set()
PATCHED_APP_IDS: set[int] = set()


def enabled() -> bool:
    return os.environ.get("OR_FVG_RUNTIME_WIRING_ENABLED", "true").lower() not in {"0", "false", "no", "off"}


def _guard():
    try:
        import opening_range_fvg_guard as guard
        return guard
    except Exception:
        return None


def _audit_note(module: Any, text: str) -> None:
    try:
        portfolio = getattr(module, "portfolio", None)
        if isinstance(portfolio, dict):
            audit = portfolio.setdefault("scanner_audit", {})
            notes = audit.setdefault("notes", [])
            if text not in notes[-12:]:
                notes.append(text)
                audit["notes"] = notes[-80:]
    except Exception:
        pass


def _eval_guard(module: Any, guard: Any, signal: Dict[str, Any], source: str) -> Dict[str, Any]:
    symbol = str(signal.get("symbol") or "").upper()
    side = signal.get("side", "long")
    if not symbol:
        return {"enabled": False, "permit": True, "reason": "missing_symbol"}
    try:
        df = module.fetch_intraday(symbol) if hasattr(module, "fetch_intraday") else None
        decision = guard.evaluate_opening_range_fvg_guard(
            symbol,
            side,
            df,
            market_tz=getattr(module, "MARKET_TZ", None),
            open_hour=int(getattr(module, "REGULAR_OPEN_HOUR", 8)),
            open_minute=int(getattr(module, "REGULAR_OPEN_MINUTE", 30)),
        )
        decision["source"] = source
        signal["opening_range_fvg_guard"] = decision
        try:
            guard.log_guard_decision(getattr(module, "portfolio", {}), decision, source=source)
        except Exception:
            pass
        return decision
    except Exception as exc:
        decision = {
            "enabled": True,
            "pilot": True,
            "symbol": symbol,
            "side": side,
            "permit": True,
            "would_block": False,
            "reason": "guard_runtime_error_pilot_allows_signal",
            "error": str(exc),
            "source": source,
        }
        signal["opening_range_fvg_guard"] = decision
        return decision


def _apply_to_signals(module: Any, guard: Any, signals: Iterable[Dict[str, Any]], rejected: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    for signal in list(signals or []):
        if not isinstance(signal, dict):
            kept.append(signal)
            continue
        decision = _eval_guard(module, guard, signal, source)
        if decision.get("permit", True):
            kept.append(signal)
        else:
            blocked = dict(signal)
            blocked["reason"] = decision.get("reason", "opening_range_fvg_guard_block")
            blocked["guard"] = "opening_range_fvg_guard"
            blocked["opening_range_fvg_guard"] = decision
            rejected.append(blocked)
    return kept


def _patch_scan_signals(module: Any, guard: Any) -> None:
    original = getattr(module, "scan_signals", None)
    if not callable(original) or getattr(original, "_or_fvg_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped_scan_signals(market, *args, **kwargs):
        result = original(market, *args, **kwargs)
        if not isinstance(result, tuple) or len(result) < 3:
            return result
        long_signals, short_signals, rejected = result[0], result[1], result[2]
        if rejected is None:
            rejected = []
        try:
            long_signals = _apply_to_signals(module, guard, long_signals, rejected, "scan_long")
            short_signals = _apply_to_signals(module, guard, short_signals, rejected, "scan_short")
            _audit_note(module, f"{VERSION}: opening_range_fvg_guard active; pilot={getattr(guard, 'OR_FVG_GUARD_PILOT', True)}")
        except Exception as exc:
            _audit_note(module, f"{VERSION}: scan wrapper error: {exc}")
        return long_signals, short_signals, rejected

    wrapped_scan_signals._or_fvg_wrapped = True  # type: ignore[attr-defined]
    module.scan_signals = wrapped_scan_signals


def _patch_risk_parameters(module: Any, guard: Any) -> None:
    original = getattr(module, "risk_parameters", None)
    if not callable(original) or getattr(original, "_or_fvg_tier_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped_risk_parameters(market, *args, **kwargs):
        params = original(market, *args, **kwargs)
        if isinstance(params, dict):
            try:
                tier = guard.position_tier_for_market(market or {})
                params["max_positions"] = int(tier.get("max_positions", params.get("max_positions", 4)))
                params["position_tier"] = tier
                params["position_tier_version"] = VERSION
            except Exception as exc:
                params["position_tier_error"] = str(exc)
        return params

    wrapped_risk_parameters._or_fvg_tier_wrapped = True  # type: ignore[attr-defined]
    module.risk_parameters = wrapped_risk_parameters


def _patch_entry_quality_check(module: Any) -> None:
    original = getattr(module, "entry_quality_check", None)
    if not callable(original) or getattr(original, "_or_fvg_quality_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped_entry_quality_check(signal, params, market, exclude_symbol=None, *args, **kwargs):
        decision = signal.get("opening_range_fvg_guard") if isinstance(signal, dict) else None
        if isinstance(decision, dict) and not decision.get("permit", True):
            return False, {
                "reason": "opening_range_fvg_guard_block",
                "symbol": signal.get("symbol"),
                "side": signal.get("side", "long"),
                "opening_range_fvg_guard": decision,
                "pilot": decision.get("pilot"),
            }
        return original(signal, params, market, exclude_symbol=exclude_symbol, *args, **kwargs)

    wrapped_entry_quality_check._or_fvg_quality_wrapped = True  # type: ignore[attr-defined]
    module.entry_quality_check = wrapped_entry_quality_check


def _patch_entry_controls_snapshot(module: Any, guard: Any) -> None:
    original = getattr(module, "entry_controls_snapshot", None)
    if not callable(original) or getattr(original, "_or_fvg_snapshot_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped_entry_controls_snapshot(*args, **kwargs):
        snap = original(*args, **kwargs)
        if isinstance(snap, dict):
            portfolio = getattr(module, "portfolio", {})
            audit = portfolio.get("scanner_audit", {}) if isinstance(portfolio, dict) else {}
            recent = audit.get("opening_range_fvg_guard", []) if isinstance(audit, dict) else []
            snap["opening_range_fvg_guard"] = {
                "enabled": bool(getattr(guard, "OR_FVG_GUARD_ENABLED", True)),
                "pilot": bool(getattr(guard, "OR_FVG_GUARD_PILOT", True)),
                "runtime_version": VERSION,
                "hard_enforcement_active": bool(getattr(guard, "OR_FVG_GUARD_ENABLED", True)) and not bool(getattr(guard, "OR_FVG_GUARD_PILOT", True)),
                "early_window_minutes": int(getattr(guard, "OR_FVG_GUARD_EARLY_MINUTES", 45)),
                "opening_range_minutes": int(getattr(guard, "OR_FVG_OPENING_RANGE_MINUTES", 15)),
                "recent_decisions_count": len(recent or []),
                "recent_would_block_count": sum(1 for r in (recent or [])[-100:] if isinstance(r, dict) and r.get("would_block")),
                "recent_tail": (recent or [])[-10:],
            }
        return snap

    wrapped_entry_controls_snapshot._or_fvg_snapshot_wrapped = True  # type: ignore[attr-defined]
    module.entry_controls_snapshot = wrapped_entry_controls_snapshot


def _register_route(module: Any, guard: Any) -> None:
    flask_app = getattr(module, "app", None)
    if flask_app is None or id(flask_app) in PATCHED_APP_IDS:
        return
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if "/paper/opening-range-fvg-status" not in existing:
            from flask import jsonify

            def opening_range_fvg_status():
                portfolio = getattr(module, "portfolio", {})
                audit = portfolio.get("scanner_audit", {}) if isinstance(portfolio, dict) else {}
                recent = audit.get("opening_range_fvg_guard", []) if isinstance(audit, dict) else []
                market = portfolio.get("last_market", {}) if isinstance(portfolio, dict) else {}
                try:
                    tier = guard.position_tier_for_market(market or {})
                except Exception as exc:
                    tier = {"error": str(exc)}
                return jsonify({
                    "status": "ok",
                    "version": VERSION,
                    "guard_enabled": bool(getattr(guard, "OR_FVG_GUARD_ENABLED", True)),
                    "pilot": bool(getattr(guard, "OR_FVG_GUARD_PILOT", True)),
                    "hard_enforcement_active": bool(getattr(guard, "OR_FVG_GUARD_ENABLED", True)) and not bool(getattr(guard, "OR_FVG_GUARD_PILOT", True)),
                    "position_tier": tier,
                    "recent_decisions_count": len(recent or []),
                    "recent_would_block_count": sum(1 for r in (recent or [])[-100:] if isinstance(r, dict) and r.get("would_block")),
                    "recent_tail": (recent or [])[-20:],
                })

            flask_app.add_url_rule("/paper/opening-range-fvg-status", "opening_range_fvg_status_runtime", opening_range_fvg_status)
        PATCHED_APP_IDS.add(id(flask_app))
    except Exception:
        pass


def apply_runtime_wiring(module: Any = None) -> Dict[str, Any]:
    if not enabled():
        return {"status": "disabled", "version": VERSION}
    if module is None:
        return {"status": "not_applied", "version": VERSION, "reason": "module_missing"}
    guard = _guard()
    if guard is None:
        return {"status": "not_applied", "version": VERSION, "reason": "guard_import_failed"}

    _patch_scan_signals(module, guard)
    _patch_risk_parameters(module, guard)
    _patch_entry_quality_check(module)
    _patch_entry_controls_snapshot(module, guard)
    _register_route(module, guard)
    try:
        setattr(module, "OPENING_RANGE_FVG_RUNTIME_VERSION", VERSION)
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(module))
    return {
        "status": "ok",
        "version": VERSION,
        "module": getattr(module, "__name__", "unknown"),
        "pilot": bool(getattr(guard, "OR_FVG_GUARD_PILOT", True)),
        "guard_enabled": bool(getattr(guard, "OR_FVG_GUARD_ENABLED", True)),
    }
