"""Position Quality Governor.

Adds stricter position-quality controls after the classic hard gate:
- Keep tech-heavy exposure allowed.
- Limit the most volatile high-beta names.
- Block new adds to red or not-yet-proven positions.
- Provide an EOD carry-quality review in /paper/position-quality-status.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, List, Tuple

VERSION = "position-quality-governor-2026-05-11"
MAX_HIGH_BETA_POSITIONS = int(os.environ.get("PQG_MAX_HIGH_BETA_POSITIONS", "2"))
REQUIRE_PROFIT_BEFORE_ADD_PCT = float(os.environ.get("PQG_REQUIRE_PROFIT_BEFORE_ADD_PCT", "0.0075"))
NEVER_ADD_BELOW_PCT = float(os.environ.get("PQG_NEVER_ADD_BELOW_PCT", "-0.005"))
WEAK_CARRY_REVIEW_PCT = float(os.environ.get("PQG_WEAK_CARRY_REVIEW_PCT", "-0.005"))
EOD_CARRY_REVIEW_WINDOW_MINUTES = int(os.environ.get("PQG_EOD_CARRY_REVIEW_WINDOW_MINUTES", "45"))
MAX_PILOT_ALLOC_PCT = float(os.environ.get("PQG_MAX_INTRADAY_PILOT_ALLOC_PCT", "0.015"))

HIGH_BETA_SYMBOLS = {
    "RGTI", "QBTS", "IONQ", "SOUN", "BBAI", "AI", "APLD", "IREN", "HUT", "CIFR",
    "WULF", "CLSK", "MARA", "RIOT", "BTDR", "CORZ", "RKLB", "JOBY", "ACHR", "TEM",
    "RXRX", "SMCI", "ALAB", "ARM", "MRVL", "MU", "ACLS", "AAOI", "LITE", "COHR",
    "PLTR", "COIN", "AMD", "NVDA", "VRT", "NET", "CRWD", "SNOW", "SHOP",
}

OVERRIDES = {
    "POSITION_QUALITY_GOVERNOR_ENABLED": ("set", True),
    "MAX_HIGH_BETA_POSITIONS": ("min", MAX_HIGH_BETA_POSITIONS),
    "REQUIRE_GREEN_POSITION_BEFORE_ADD": ("set", True),
    "MINIMUM_PNL_BEFORE_ADD_PCT": ("max", REQUIRE_PROFIT_BEFORE_ADD_PCT),
    "NEVER_ADD_TO_POSITION_BELOW_PCT": ("min", NEVER_ADD_BELOW_PCT),
    "MAX_INTRADAY_PILOT_ALLOC_PCT": ("min", MAX_PILOT_ALLOC_PCT),
    "CONTROLLED_PULLBACK_ALLOC_FACTOR": ("min", 0.15),
    "CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY": ("min", 1),
    "MAX_NEW_ENTRIES_PER_CYCLE": ("min", 1),
    "ROTATION_MIN_HOLD_SECONDS": ("max", 7200),
    "ROTATION_MIN_SCORE_EDGE": ("max", 0.012),
}

_REGISTERED_APP_IDS: set[int] = set()
_APPLIED_OVERRIDES: Dict[str, Any] = {}
_LATEST_DECISIONS: List[Dict[str, Any]] = []
_WRAPPED = False


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _append(row: Dict[str, Any]) -> None:
    obj = dict(row)
    obj.setdefault("generated_local", _now_text())
    _LATEST_DECISIONS.append(obj)
    del _LATEST_DECISIONS[:-100]


def _extract_symbol_side_score(args: tuple, kwargs: dict) -> Tuple[str | None, str, float | None]:
    symbol = kwargs.get("symbol") or kwargs.get("ticker")
    side = kwargs.get("side", "long")
    score = kwargs.get("score")
    for arg in args:
        if symbol is None and isinstance(arg, str) and 1 <= len(arg) <= 8:
            symbol = arg
        elif isinstance(arg, str) and arg.lower() in ("long", "short"):
            side = arg.lower()
        elif score is None and isinstance(arg, (int, float)):
            score = arg
    return (str(symbol).upper() if symbol else None, str(side).lower(), _float(score, None) if score is not None else None)


def _market_clock(module: Any) -> Dict[str, Any]:
    for name in ("market_clock", "get_market_clock", "market_clock_snapshot"):
        fn = getattr(module, name, None)
        if callable(fn):
            try:
                obj = fn()
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    return {"is_open": True, "minutes_to_close": None, "reason": "clock_unavailable"}


def _load_state(module: Any) -> Dict[str, Any]:
    try:
        if hasattr(module, "load_state"):
            state = module.load_state()
            return state if isinstance(state, dict) else {}
    except Exception:
        pass
    return {}


def _positions(module: Any) -> Dict[str, Dict[str, Any]]:
    positions = _load_state(module).get("positions", {})
    return positions if isinstance(positions, dict) else {}


def _position_pnl_pct(pos: Dict[str, Any]) -> float:
    raw = pos.get("pnl_pct")
    if raw is not None:
        val = _float(raw, 0.0)
        return val / 100.0 if abs(val) > 5 else val
    entry = _float(pos.get("entry") or pos.get("entry_price"), 0.0)
    price = _float(pos.get("last_price") or pos.get("price"), 0.0)
    return price / entry - 1.0 if entry and price else 0.0


def _is_high_beta(symbol: str, pos: Dict[str, Any] | None = None) -> bool:
    if symbol.upper() in HIGH_BETA_SYMBOLS:
        return True
    sector = str((pos or {}).get("sector", "")).upper()
    return sector in {"SMALL_CAP_MOMENTUM", "BITCOIN_AI_COMPUTE"}


def _high_beta_count(module: Any) -> int:
    return sum(1 for symbol, pos in _positions(module).items() if _is_high_beta(str(symbol), pos if isinstance(pos, dict) else {}))


def _result_allows(result: Any) -> bool:
    if isinstance(result, bool):
        return bool(result)
    if isinstance(result, dict):
        for key in ("allowed", "ok", "pass", "passes", "entry_allowed"):
            if key in result:
                return bool(result.get(key))
        return not bool(result.get("blocked", False))
    if isinstance(result, tuple) and result and isinstance(result[0], bool):
        return bool(result[0])
    return True


def _block_like(result: Any, reason: str) -> Any:
    if isinstance(result, bool):
        return False
    if isinstance(result, tuple) and result and isinstance(result[0], bool):
        values = list(result)
        values[0] = False
        if len(values) >= 2:
            values[1] = reason
        else:
            values.append(reason)
        return tuple(values)
    if isinstance(result, dict):
        out = dict(result)
        out["allowed"] = False
        out["ok"] = False
        out["blocked"] = True
        prior = str(out.get("reason") or out.get("block_reason") or "").strip()
        out["reason"] = f"{prior},{reason}".strip(",") if prior else reason
        out["block_reason"] = out["reason"]
        return out
    return result


def governor_decision(module: Any, symbol: str, side: str = "long", score: float | None = None, action: str = "entry") -> Dict[str, Any]:
    symbol = str(symbol).upper()
    side = (side or "long").lower()
    if side != "long":
        return {"allowed": True, "symbol": symbol, "side": side, "reason": "non_long_not_blocked"}
    positions = _positions(module)
    pos = positions.get(symbol)
    high_beta_count = _high_beta_count(module)
    high_beta = _is_high_beta(symbol, pos if isinstance(pos, dict) else {})
    reasons: List[str] = []
    allowed = True
    pnl_pct = None
    if isinstance(pos, dict):
        pnl_pct = _position_pnl_pct(pos)
        if pnl_pct < NEVER_ADD_BELOW_PCT:
            allowed = False
            reasons.append("never_add_to_red_position")
        elif pnl_pct < REQUIRE_PROFIT_BEFORE_ADD_PCT:
            allowed = False
            reasons.append("requires_green_position_before_add")
    elif high_beta and high_beta_count >= MAX_HIGH_BETA_POSITIONS:
        allowed = False
        reasons.append("max_high_beta_positions_reached")
    return {
        "allowed": allowed,
        "symbol": symbol,
        "side": side,
        "score": score,
        "action": action,
        "reason": "position_quality_confirmed" if allowed else ",".join(reasons),
        "high_beta_symbol": high_beta,
        "high_beta_position_count": high_beta_count,
        "max_high_beta_positions": MAX_HIGH_BETA_POSITIONS,
        "existing_position": isinstance(pos, dict),
        "position_pnl_pct": round(pnl_pct * 100, 3) if pnl_pct is not None else None,
    }


def carry_review(module: Any) -> Dict[str, Any]:
    positions = _positions(module)
    clock = _market_clock(module)
    mtc = clock.get("minutes_to_close")
    in_window = bool(clock.get("is_open") and mtc is not None and _float(mtc, 9999.0) <= EOD_CARRY_REVIEW_WINDOW_MINUTES)
    rows: List[Dict[str, Any]] = []
    for symbol, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        pnl_pct = _position_pnl_pct(pos)
        high_beta = _is_high_beta(str(symbol), pos)
        weak = pnl_pct <= WEAK_CARRY_REVIEW_PCT
        if weak and high_beta:
            recommendation = "reduce_or_do_not_carry_unless_classic_confirmed"
        elif weak:
            recommendation = "review_before_carry"
        elif pnl_pct < 0:
            recommendation = "carry_only_if_classic_confirmed"
        else:
            recommendation = "eligible_to_carry_if_regime_supports"
        rows.append({
            "symbol": str(symbol).upper(),
            "side": pos.get("side", "long"),
            "sector": pos.get("sector"),
            "high_beta": high_beta,
            "pnl_pct": round(pnl_pct * 100, 3),
            "recommendation": recommendation,
            "eod_actionable_now": bool(in_window and weak),
        })
    return {
        "market_clock": clock,
        "in_eod_carry_review_window": in_window,
        "open_positions_count": len(rows),
        "high_beta_positions_count": sum(1 for r in rows if r["high_beta"]),
        "weak_positions_count": sum(1 for r in rows if r["pnl_pct"] <= WEAK_CARRY_REVIEW_PCT * 100),
        "positions": rows,
    }


def apply_runtime_overrides(module: Any) -> Dict[str, Any]:
    applied: Dict[str, Any] = {}
    for name, (mode, value) in OVERRIDES.items():
        try:
            old = getattr(module, name, None)
            new = value
            if old is not None:
                if mode == "min":
                    new = min(old, value)
                elif mode == "max":
                    new = max(old, value)
                elif mode == "set":
                    new = value
            setattr(module, name, new)
            applied[name] = {"old": old, "new": new, "mode": mode, "applied": True}
        except Exception as exc:
            applied[name] = {"new": value, "mode": mode, "applied": False, "error": str(exc)}
    _APPLIED_OVERRIDES.clear()
    _APPLIED_OVERRIDES.update(applied)
    return applied


def _wrap_entry_points(module: Any) -> None:
    global _WRAPPED
    if _WRAPPED:
        return
    for fn_name in ("entry_quality_check", "controlled_pullback_entry_check"):
        fn = getattr(module, fn_name, None)
        if callable(fn) and not getattr(fn, "_position_quality_wrapped", False):
            def make_wrapper(__fn, __name):
                def wrapper(*args, **kwargs):
                    result = __fn(*args, **kwargs)
                    try:
                        if not _result_allows(result):
                            return result
                        symbol, side, score = _extract_symbol_side_score(args, kwargs)
                        if not symbol:
                            return result
                        decision = governor_decision(module, symbol, side, score, action=__name)
                        decision["hook"] = __name
                        _append(decision)
                        if not decision.get("allowed", True):
                            return _block_like(result, "position_quality_governor:" + str(decision.get("reason", "blocked")))
                    except Exception as exc:
                        _append({"hook": __name, "allowed": True, "error": str(exc), "reason": "position_quality_error_allowed"})
                    return result
                wrapper._position_quality_wrapped = True
                return wrapper
            setattr(module, fn_name, make_wrapper(fn, fn_name))
    fn = getattr(module, "enter_position", None)
    if callable(fn) and not getattr(fn, "_position_quality_wrapped", False):
        def enter_wrapper(*args, **kwargs):
            try:
                symbol, side, score = _extract_symbol_side_score(args, kwargs)
                if symbol:
                    decision = governor_decision(module, symbol, side, score, action="enter_position")
                    decision["hook"] = "enter_position"
                    _append(decision)
                    if not decision.get("allowed", True):
                        return None
            except Exception as exc:
                _append({"hook": "enter_position", "allowed": True, "error": str(exc), "reason": "position_quality_error_allowed"})
            return fn(*args, **kwargs)
        enter_wrapper._position_quality_wrapped = True
        setattr(module, "enter_position", enter_wrapper)
    _WRAPPED = True


def apply(module: Any) -> Dict[str, Any]:
    applied = apply_runtime_overrides(module)
    _wrap_entry_points(module)
    try:
        setattr(module, "POSITION_QUALITY_GOVERNOR_VERSION", VERSION)
    except Exception:
        pass
    return {
        "status": "ok",
        "type": "position_quality_apply",
        "version": VERSION,
        "generated_local": _now_text(),
        "wrapped": _WRAPPED,
        "applied_runtime_overrides": applied,
        "rules": status_rules(),
    }


def status_rules() -> Dict[str, Any]:
    return {
        "max_high_beta_positions": MAX_HIGH_BETA_POSITIONS,
        "require_profit_before_add_pct": REQUIRE_PROFIT_BEFORE_ADD_PCT * 100,
        "never_add_below_pct": NEVER_ADD_BELOW_PCT * 100,
        "weak_carry_review_pct": WEAK_CARRY_REVIEW_PCT * 100,
        "eod_carry_review_window_minutes": EOD_CARRY_REVIEW_WINDOW_MINUTES,
        "max_intraday_pilot_alloc_pct": MAX_PILOT_ALLOC_PCT * 100,
    }


def status_payload(module: Any | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": "ok",
        "type": "position_quality_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "wrapped": _WRAPPED,
        "rules": status_rules(),
        "applied_runtime_overrides": _APPLIED_OVERRIDES,
        "latest_decisions": _LATEST_DECISIONS[-20:],
        "blocked_decisions_recent": [d for d in _LATEST_DECISIONS[-50:] if not d.get("allowed", True)][-10:],
        "normal_test_link": "https://trading-bot-clean.up.railway.app/paper/self-check",
    }
    try:
        if module is not None:
            payload["carry_review"] = carry_review(module)
    except Exception as exc:
        payload["carry_review_error"] = str(exc)
    return payload


def register_routes(flask_app: Any, module: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in _REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if module is not None:
        try:
            apply(module)
        except Exception:
            pass
    if "/paper/position-quality-status" not in existing:
        flask_app.add_url_rule("/paper/position-quality-status", "position_quality_status", lambda: jsonify(status_payload(module)))
    _REGISTERED_APP_IDS.add(id(flask_app))
