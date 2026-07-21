"""Scanner v2 advisory composite scoring and theme-leadership attribution.

This module is shadow-only. It does not mutate the executable universe, patch
scan_signals, change thresholds, sizing, risk controls, ML authority, or place
orders. Market-data work runs only when force=1 is explicitly requested.
"""
from __future__ import annotations

import datetime as dt
import sys
from typing import Any, Dict, Iterable, List, Set

VERSION = "scanner-v2-shadow-composite-score-2026-07-21-v1"
REGISTERED_APP_IDS: set[int] = set()
DEFAULT_SYMBOLS = ["BE", "NVTS", "STX", "NUAI", "CRWV", "ONDS"]
MAX_SYMBOLS = 80


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _symbol(value: Any) -> str:
    raw = str(value or "").upper().strip().lstrip("$")
    clean = raw.replace(".", "").replace("-", "")
    return raw if raw and len(raw) <= 10 and clean.isalnum() else ""


def _unique(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for value in values or []:
        symbol = _symbol(value)
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out[:MAX_SYMBOLS]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _theme_map() -> Dict[str, List[str]]:
    try:
        from scanner_v2_shadow_universe import SHADOW_BASKETS  # type: ignore
        return {str(k): _unique(v) for k, v in SHADOW_BASKETS.items()}
    except Exception:
        return {
            "ai_data_center_infrastructure": ["CRWV", "STX"],
            "power_electrification": ["BE", "NUAI"],
            "semiconductor_power_components": ["NVTS"],
            "autonomy_drones_sensing": ["ONDS"],
        }


def _snapshot(symbol: str) -> Dict[str, Any]:
    try:
        from scanner_v2_shadow_quality_trace import _market_snapshot  # type: ignore
        return _market_snapshot(symbol)
    except Exception as exc:
        return {"symbol": symbol, "data_available": False, "data_error": f"quality_trace_unavailable:{type(exc).__name__}"}


def _themes_for_symbol(symbol: str, baskets: Dict[str, List[str]]) -> List[str]:
    return [theme for theme, members in baskets.items() if symbol in set(members)]


def _score(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not snapshot.get("data_available"):
        return {
            "composite_score": 0.0,
            "components": {},
            "score_status": "data_unavailable",
        }

    move_1d = _safe_float(snapshot.get("pct_change_1d"))
    move_5d = _safe_float(snapshot.get("pct_change_5d"))
    volume_ratio = _safe_float(snapshot.get("volume_ratio"))
    dollar_volume = _safe_float(snapshot.get("dollar_volume"))
    liquidity_pass = bool(snapshot.get("shadow_liquidity_pass"))

    momentum = _clamp(move_1d / 12.0)
    trend = _clamp((move_5d + 5.0) / 20.0)
    volume = _clamp(volume_ratio / 2.5)
    liquidity = 1.0 if liquidity_pass else _clamp(dollar_volume / 5_000_000.0)
    continuation = _clamp((move_1d + max(move_5d, 0.0)) / 30.0)

    # Penalize late-stage extension without making the score executable.
    extension_penalty = _clamp((move_1d - 12.0) / 18.0)
    reversal_penalty = _clamp((-move_5d) / 15.0) if move_1d > 5.0 else 0.0

    raw = (
        momentum * 0.28
        + trend * 0.20
        + volume * 0.18
        + liquidity * 0.14
        + continuation * 0.20
        - extension_penalty * 0.12
        - reversal_penalty * 0.08
    )
    composite = round(_clamp(raw), 6)
    return {
        "composite_score": composite,
        "score_status": "shadow_scored",
        "components": {
            "momentum": round(momentum, 6),
            "trend": round(trend, 6),
            "volume": round(volume, 6),
            "liquidity": round(liquidity, 6),
            "continuation": round(continuation, 6),
            "extension_penalty": round(extension_penalty, 6),
            "reversal_penalty": round(reversal_penalty, 6),
        },
        "weights": {
            "momentum": 0.28,
            "trend": 0.20,
            "volume": 0.18,
            "liquidity": 0.14,
            "continuation": 0.20,
            "extension_penalty": -0.12,
            "reversal_penalty": -0.08,
        },
    }


def build_report(core: Any = None, symbols: Iterable[Any] | None = None, force_market_data: bool = False) -> Dict[str, Any]:
    core = core or _mod()
    selected = _unique(symbols or DEFAULT_SYMBOLS)
    baskets = _theme_map()

    if not force_market_data:
        return {
            "status": "ok" if core is not None else "pending",
            "overall": "pass" if core is not None else "pending",
            "type": "scanner_v2_shadow_composite_score",
            "version": VERSION,
            "mode": "advisory_shadow_only",
            "symbols": selected,
            "market_data_requested": False,
            "heavy_market_data_deferred": True,
            "message": "Add force=1 for deliberate shadow scoring.",
            "authority": _authority(),
        }

    rows: List[Dict[str, Any]] = []
    for symbol in selected:
        market = _snapshot(symbol)
        scoring = _score(market)
        rows.append({
            "symbol": symbol,
            "themes": _themes_for_symbol(symbol, baskets),
            "market_snapshot": market,
            **scoring,
        })

    rows.sort(key=lambda row: _safe_float(row.get("composite_score")), reverse=True)

    theme_rows: List[Dict[str, Any]] = []
    for theme, members in baskets.items():
        member_rows = [row for row in rows if row["symbol"] in set(members) and row.get("score_status") == "shadow_scored"]
        if not member_rows:
            continue
        scores = [_safe_float(row.get("composite_score")) for row in member_rows]
        positive = sum(1 for row in member_rows if _safe_float((row.get("market_snapshot") or {}).get("pct_change_1d")) > 0)
        strong = sum(1 for row in member_rows if _safe_float(row.get("composite_score")) >= 0.60)
        leadership_score = round(_clamp((sum(scores) / len(scores)) * 0.70 + (positive / len(member_rows)) * 0.15 + (strong / len(member_rows)) * 0.15), 6)
        theme_rows.append({
            "theme": theme,
            "members_scored": len(member_rows),
            "positive_breadth": positive,
            "strong_member_count": strong,
            "average_member_score": round(sum(scores) / len(scores), 6),
            "leadership_score": leadership_score,
            "top_members": [row["symbol"] for row in sorted(member_rows, key=lambda x: _safe_float(x.get("composite_score")), reverse=True)[:5]],
        })
    theme_rows.sort(key=lambda row: _safe_float(row.get("leadership_score")), reverse=True)

    return {
        "status": "ok",
        "overall": "pass",
        "type": "scanner_v2_shadow_composite_score",
        "version": VERSION,
        "generated_local": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "advisory_shadow_only",
        "market_data_requested": True,
        "summary": {
            "symbols_requested": len(selected),
            "symbols_scored": sum(1 for row in rows if row.get("score_status") == "shadow_scored"),
            "liquidity_pass": sum(1 for row in rows if (row.get("market_snapshot") or {}).get("shadow_liquidity_pass") is True),
            "themes_scored": len(theme_rows),
        },
        "ranked_candidates": rows,
        "theme_leadership": theme_rows,
        "authority": _authority(),
        "next_gate": "Accumulate repeated shadow rankings and compare candidate-to-entry and candidate-to-outcome evidence before any paper-only promotion authority.",
    }


def _authority() -> Dict[str, bool]:
    return {
        "core_universe_mutated": False,
        "scan_signals_patched": False,
        "places_orders": False,
        "changes_thresholds": False,
        "changes_risk_or_sizing": False,
        "changes_ml_authority": False,
        "changes_live_authority": False,
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return build_report(core or _mod(), force_market_data=False)


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
        symbols = raw.split(",") if raw else DEFAULT_SYMBOLS
        force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes"}
        return jsonify(build_report(core or _mod(), symbols=symbols, force_market_data=force))

    path = "/paper/scanner-v2-shadow-composite-score-status"
    if path not in existing:
        flask_app.add_url_rule(path, "scanner_v2_shadow_composite_score_status", route)
    REGISTERED_APP_IDS.add(id(flask_app))
