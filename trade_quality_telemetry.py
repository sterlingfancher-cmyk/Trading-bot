"""MAE/MFE and trade-quality telemetry layer.

Shadow/advisory only. This module does not place trades, change orders,
modify allocation, or override live risk controls. It adds structured outcome
analytics so future ML phases can learn from trade quality rather than only
from win/loss labels.

Routes:
- /paper/trade-quality-status
- /paper/mae-mfe-status

State section:
- state["trade_quality_telemetry"]
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "trade-quality-mae-mfe-telemetry-2026-05-16"
ENABLED = os.environ.get("TRADE_QUALITY_TELEMETRY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_AUTHORITY = False
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        v = float(x)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
            return mod
    return None


def _now(mod: Any = None) -> str:
    try:
        return mod.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return (state if isinstance(state, dict) else {}), mod


def _is_entry(row: Dict[str, Any]) -> bool:
    action = str(row.get("action") or row.get("type") or "").lower()
    reason = str(row.get("reason") or row.get("entry_reason") or "").lower()
    return action in {"entry", "buy", "short", "open"} or "entry" in reason or row.get("entry_price") is not None


def _is_exit(row: Dict[str, Any]) -> bool:
    action = str(row.get("action") or row.get("type") or "").lower()
    reason = str(row.get("exit_reason") or row.get("reason") or "").lower()
    has_pnl = row.get("pnl_dollars") is not None or row.get("pnl_pct") is not None
    return action in {"exit", "sell", "cover", "close"} or "exit" in reason or "stop" in reason or has_pnl


def _trade_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [row for row in _list(state.get("trades")) if isinstance(row, dict)]


def _price(row: Dict[str, Any]) -> float:
    return _f(row.get("price"), _f(row.get("entry_price"), _f(row.get("exit_price"), 0.0)))


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper()


def _side(row: Dict[str, Any]) -> str:
    return str(row.get("side") or row.get("direction") or "long").lower()


def _time_value(row: Dict[str, Any]) -> float:
    return _f(row.get("time"), _f(row.get("timestamp"), 0.0))


def _pair_trades(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    open_by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    pairs: List[Dict[str, Any]] = []
    for row in rows:
        sym = _symbol(row)
        side = _side(row)
        if not sym:
            continue
        key = (sym, side)
        if _is_entry(row):
            open_by_key.setdefault(key, []).append(row)
        elif _is_exit(row):
            entry = None
            if open_by_key.get(key):
                entry = open_by_key[key].pop(0)
            entry_price = _price(entry) if isinstance(entry, dict) else _f(row.get("entry_price"), 0.0)
            exit_price = _price(row)
            pnl_pct = _f(row.get("pnl_pct"), 0.0)
            if pnl_pct == 0.0 and entry_price > 0 and exit_price > 0:
                pnl_pct = ((exit_price / entry_price - 1.0) * 100.0) if side != "short" else ((entry_price / exit_price - 1.0) * 100.0)
            pairs.append({
                "symbol": sym,
                "side": side,
                "entry_price": round(entry_price, 4) if entry_price else None,
                "exit_price": round(exit_price, 4) if exit_price else None,
                "entry_time": _time_value(entry) if isinstance(entry, dict) else None,
                "exit_time": _time_value(row),
                "pnl_dollars": round(_f(row.get("pnl_dollars"), 0.0), 4),
                "pnl_pct": round(pnl_pct, 4),
                "exit_reason": row.get("exit_reason") or row.get("reason"),
                "market_mode": row.get("market_mode") or (entry.get("market_mode") if isinstance(entry, dict) else None),
                "setup_family": (entry.get("setup_family") if isinstance(entry, dict) else None) or row.get("setup_family") or "unknown",
            })
    return pairs


def _scanner_context(state: Dict[str, Any]) -> Dict[str, Any]:
    audit = _dict(state.get("scanner_audit"))
    fvg = _list(audit.get("opening_range_fvg_guard"))
    return {
        "signals_found": audit.get("signals_found"),
        "blocked_entries_count": len(_list(audit.get("blocked_entries"))),
        "rejected_signals_count": len(_list(audit.get("rejected_signals"))),
        "fvg_recent_decisions": len(fvg),
        "fvg_recent_would_block": sum(1 for row in fvg[-100:] if isinstance(row, dict) and row.get("would_block")),
    }


def _grade_pair(pair: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    pnl_pct = _f(pair.get("pnl_pct"), 0.0)
    pnl_dollars = _f(pair.get("pnl_dollars"), 0.0)
    exit_reason = str(pair.get("exit_reason") or "").lower()
    market = _dict(state.get("last_market"))
    scanner = _scanner_context(state)

    score = 50.0
    score += min(25.0, max(-25.0, pnl_pct * 8.0))
    score += 8.0 if pnl_dollars > 0 else -8.0 if pnl_dollars < 0 else 0.0
    score += 5.0 if market.get("market_mode") == "risk_on" else 0.0
    score -= 8.0 if "stop" in exit_reason else 0.0
    score -= 4.0 if "breakeven" in exit_reason and pnl_pct < 0 else 0.0
    score -= 3.0 if scanner.get("fvg_recent_would_block", 0) > 0 else 0.0
    score = max(0.0, min(100.0, score))

    if score >= 78:
        grade = "A"
    elif score >= 63:
        grade = "B"
    elif score >= 48:
        grade = "C"
    else:
        grade = "D"

    # MAE/MFE placeholders: without high/low path data at trade level, do not
    # invent values. These fields become real once intratrade price path capture is added.
    mae_pct = pair.get("mae_pct")
    mfe_pct = pair.get("mfe_pct")
    stop_efficiency = None
    if mae_pct is not None and mfe_pct is not None:
        mae = abs(_f(mae_pct))
        mfe = abs(_f(mfe_pct))
        stop_efficiency = round(mfe / max(0.01, mae), 4)

    return {
        **pair,
        "trade_quality_score": round(score, 2),
        "trade_quality_grade": grade,
        "mae_pct": mae_pct,
        "mfe_pct": mfe_pct,
        "stop_efficiency": stop_efficiency,
        "mae_mfe_status": "pending_intratrade_path_capture" if mae_pct is None or mfe_pct is None else "complete",
        "market_alignment": bool(market.get("market_mode") == "risk_on" and pair.get("side") != "short"),
        "trend_alignment": None,
        "volatility_alignment": None,
        "quality_note": "Grade uses realized result plus available context; MAE/MFE waits for intratrade path capture.",
    }


def _summarize(graded: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    mae_complete = 0
    mfe_complete = 0
    total_score = 0.0
    for row in graded:
        grade = str(row.get("trade_quality_grade") or "D")
        counts[grade] = counts.get(grade, 0) + 1
        total_score += _f(row.get("trade_quality_score"), 0.0)
        mae_complete += 1 if row.get("mae_pct") is not None else 0
        mfe_complete += 1 if row.get("mfe_pct") is not None else 0
    n = len(graded)
    return {
        "graded_trades": n,
        "grade_counts": counts,
        "average_quality_score": round(total_score / max(1, n), 2),
        "mae_complete_count": mae_complete,
        "mfe_complete_count": mfe_complete,
        "mae_mfe_complete": bool(n > 0 and mae_complete == n and mfe_complete == n),
    }


def build_payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    rows = _trade_rows(state)
    pairs = _pair_trades(rows)
    graded = [_grade_pair(pair, state) for pair in pairs]
    summary = _summarize(graded)
    scanner = _scanner_context(state)
    section = {
        "version": VERSION,
        "enabled": ENABLED,
        "live_authority": False,
        "last_updated_local": _now(mod),
        "summary": summary,
        "scanner_context": scanner,
        "recent_quality_tail": graded[-25:],
        "recommended_actions": [
            "Keep trade-quality telemetry advisory only until MAE/MFE path capture is complete.",
            "Use grades to identify weak setup families before letting ML adjust sizing.",
            "Next improvement: capture intratrade high/low path for true MAE/MFE rather than placeholders.",
        ],
    }
    state["trade_quality_telemetry"] = section
    return {
        "status": "ok",
        "type": "trade_quality_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "live_authority": False,
        "summary": summary,
        "scanner_context": scanner,
        "recent_quality_tail": graded[-10:],
        "recommended_actions": section["recommended_actions"],
    }


def apply(module: Any = None) -> Dict[str, Any]:
    module = module or _module()
    if module is None:
        return {"status": "not_applied", "version": VERSION, "reason": "module_missing"}
    if id(module) in PATCHED_MODULE_IDS:
        return {"status": "ok", "version": VERSION, "already_patched": True, "live_authority": False}
    try:
        original = getattr(module, "save_state", None)
        if callable(original):
            def patched_save_state(state):
                try:
                    if ENABLED and isinstance(state, dict):
                        build_payload(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("trade_quality_telemetry", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                return original(state)
            patched_save_state._trade_quality_telemetry_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "TRADE_QUALITY_TELEMETRY_VERSION", VERSION)
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(module))
    return {"status": "ok", "version": VERSION, "live_authority": False}


def register_routes(flask_app: Any, module: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    module = module or _module()
    apply(module)
    if id(flask_app) in REGISTERED_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def quality_status():
        state, mod = _load_state(module)
        return jsonify(build_payload(state, mod))

    def mae_mfe_status():
        state, mod = _load_state(module)
        payload = build_payload(state, mod)
        summary = _dict(payload.get("summary"))
        return jsonify({
            "status": "ok",
            "type": "mae_mfe_status",
            "version": VERSION,
            "generated_local": _now(mod),
            "enabled": ENABLED,
            "live_authority": False,
            "graded_trades": summary.get("graded_trades"),
            "mae_complete_count": summary.get("mae_complete_count"),
            "mfe_complete_count": summary.get("mfe_complete_count"),
            "mae_mfe_complete": summary.get("mae_mfe_complete"),
            "note": "True MAE/MFE requires intratrade high/low path capture; current values remain placeholders unless present in state.",
        })

    if "/paper/trade-quality-status" not in existing:
        flask_app.add_url_rule("/paper/trade-quality-status", "paper_trade_quality_status", quality_status)
    if "/paper/mae-mfe-status" not in existing:
        flask_app.add_url_rule("/paper/mae-mfe-status", "paper_mae_mfe_status", mae_mfe_status)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/trade-quality-status", "/paper/mae-mfe-status"], "live_authority": False}
