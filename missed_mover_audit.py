"""Missed mover audit.

Advisory-only diagnostic route for symbols that made large moves but were not
entered by the paper bot.

Example:
    /paper/missed-mover-audit?symbol=MNTS

This module does not trade, resize, change risk controls, change ML authority,
lower thresholds, or modify scanner behavior.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Set

VERSION = "missed-mover-audit-2026-06-04-v1-manual"
REGISTERED_APP_IDS: set[int] = set()

MICROCAP_BUCKETS = {
    "space": ["MNTS", "RKLB", "LUNR", "ASTS", "BKSY", "SPIR", "SIDU"],
    "small_cap_momentum": ["MNTS", "SOUN", "JOBY", "QBTS", "RXRX", "TEM"],
    "bitcoin_ai_compute": ["HIVE", "HUT", "RIOT", "CLSK", "MARA", "BTDR", "WULF", "IREN"],
}


def _now(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state(core: Any = None) -> Dict[str, Any]:
    try:
        state = core.load_state()
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _portfolio(core: Any = None) -> Dict[str, Any]:
    try:
        pf = getattr(core, "portfolio", {})
        return pf if isinstance(pf, dict) else {}
    except Exception:
        return {}


def _symbol(value: Any) -> str:
    return str(value or "").upper().strip()


def _flatten_symbols(obj: Any, max_items: int = 8000) -> Set[str]:
    """Collect symbol-like strings from nested lists/dicts without assuming schema."""
    out: Set[str] = set()
    seen = 0

    def walk(x: Any) -> None:
        nonlocal seen
        if seen >= max_items:
            return
        seen += 1

        if isinstance(x, dict):
            for key in ("symbol", "ticker", "asset", "name"):
                if key in x:
                    s = _symbol(x.get(key))
                    if 1 <= len(s) <= 12 and s.replace(".", "").replace("-", "").isalnum():
                        out.add(s)
            for value in x.values():
                walk(value)
        elif isinstance(x, list):
            for item in x:
                walk(item)
        elif isinstance(x, str):
            s = _symbol(x)
            if 1 <= len(s) <= 12 and s.replace(".", "").replace("-", "").isalnum():
                out.add(s)

    walk(obj)
    return out


def _find_dicts_for_symbol(obj: Any, symbol: str, max_hits: int = 25) -> List[Dict[str, Any]]:
    """Return small dict snippets that directly reference symbol."""
    hits: List[Dict[str, Any]] = []

    def walk(x: Any) -> None:
        if len(hits) >= max_hits:
            return
        if isinstance(x, dict):
            values = {_symbol(v) for v in x.values() if isinstance(v, str)}
            if symbol in values or _symbol(x.get("symbol")) == symbol or _symbol(x.get("ticker")) == symbol:
                slim = {}
                for key in (
                    "symbol", "ticker", "score", "reason", "entry_context",
                    "trade_class", "bucket", "sector", "side", "price",
                    "blocked", "status", "decision", "risk_tier"
                ):
                    if key in x:
                        slim[key] = x.get(key)
                hits.append(slim or {"symbol": symbol})
            for value in x.values():
                walk(value)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(obj)
    return hits


def _watchlist_symbols(core: Any = None, state: Dict[str, Any] | None = None) -> Set[str]:
    state = state or {}
    symbols: Set[str] = set()

    for attr in (
        "WATCHLIST", "WATCHLIST_SYMBOLS", "DEFAULT_WATCHLIST",
        "UNIVERSE", "TRADING_UNIVERSE", "SCAN_UNIVERSE",
    ):
        try:
            value = getattr(core, attr, None)
            symbols |= _flatten_symbols(value)
        except Exception:
            pass

    for key in (
        "watchlist", "watchlists", "universe", "scanner_universe",
        "symbols", "long_symbols", "short_symbols",
    ):
        symbols |= _flatten_symbols(state.get(key))

    return symbols


def _bucket_for_symbol(symbol: str) -> str:
    for bucket, members in MICROCAP_BUCKETS.items():
        if symbol in members:
            return bucket
    return "unknown"


def _latest_decision_sections(state: Dict[str, Any], pf: Dict[str, Any]) -> Dict[str, Any]:
    sections = {}

    for key in (
        "scanner_audit",
        "decision_audit",
        "decision_audit_summary",
        "latest_redeployment",
        "post_harvest_redeployment",
        "entry_decision_visibility",
        "paper_controlled_expansion",
        "expansion_impact_monitor",
    ):
        if isinstance(pf.get(key), dict):
            sections[key] = pf.get(key)
        elif isinstance(state.get(key), dict):
            sections[key] = state.get(key)

    return sections


def build_payload(symbol: str, core: Any = None) -> Dict[str, Any]:
    symbol = _symbol(symbol)
    state = _state(core)
    pf = _portfolio(core)

    positions = pf.get("positions") if isinstance(pf.get("positions"), dict) else state.get("positions", {})
    trades = pf.get("trades") if isinstance(pf.get("trades"), list) else state.get("trades", [])

    positions = positions if isinstance(positions, dict) else {}
    trades = trades if isinstance(trades, list) else []

    decision_sections = _latest_decision_sections(state, pf)
    watchlist = _watchlist_symbols(core, state)

    scanned_symbols = set()
    blocked_symbols = set()
    candidate_symbols = set()

    for section in decision_sections.values():
        if isinstance(section, dict):
            scanned_symbols |= _flatten_symbols(section.get("signals"))
            scanned_symbols |= _flatten_symbols(section.get("signals_found"))
            scanned_symbols |= _flatten_symbols(section.get("top_signals"))
            scanned_symbols |= _flatten_symbols(section.get("rejected_signals"))
            scanned_symbols |= _flatten_symbols(section.get("rejected_top_candidates"))
            blocked_symbols |= _flatten_symbols(section.get("top_blocked_symbols"))
            blocked_symbols |= _flatten_symbols(section.get("blocked_entries"))
            candidate_symbols |= _flatten_symbols(section.get("candidate_symbols"))
            candidate_symbols |= _flatten_symbols(section.get("candidates"))
            candidate_symbols |= _flatten_symbols(section.get("top_candidates_reviewed"))

    open_position = symbol in {_symbol(s) for s in positions.keys()}
    trade_mentions = [row for row in trades if isinstance(row, dict) and _symbol(row.get("symbol")) == symbol]
    decision_hits = _find_dicts_for_symbol(decision_sections, symbol)

    in_watchlist = symbol in watchlist
    scanned = symbol in scanned_symbols or bool(decision_hits)
    blocked = symbol in blocked_symbols
    candidate = symbol in candidate_symbols

    if open_position:
        decision = "already_open"
        reason = "Symbol is already an open position."
    elif blocked:
        decision = "blocked"
        reason = "Symbol appeared in blocked symbols or blocked entry diagnostics."
    elif candidate:
        decision = "candidate_not_entered"
        reason = "Symbol appeared as a candidate but no entry was recorded."
    elif scanned:
        decision = "scanned_not_selected"
        reason = "Symbol appeared in scanner/decision sections but was not selected."
    elif in_watchlist:
        decision = "watchlist_not_triggered"
        reason = "Symbol is in a configured universe/watchlist but did not appear in recent decision sections."
    else:
        decision = "not_in_recent_scanner_context"
        reason = "Symbol was not found in current watchlist, positions, trades, or recent scanner/decision state."

    asset_bucket = _bucket_for_symbol(symbol)
    microcap_or_speculative = asset_bucket in {"space", "small_cap_momentum"}

    recommendations = [
        "Do not lower thresholds just because one symbol moved.",
        "Use this audit to determine whether the issue was universe coverage, rejection, block, or timing.",
        "If this symbol class repeats, consider a shadow-only momentum bucket before allowing trades.",
    ]

    if decision == "not_in_recent_scanner_context":
        recommendations.insert(0, "Likely scanner-universe gap; consider shadow-only discovery coverage.")
    if microcap_or_speculative:
        recommendations.append("Treat as speculative/microcap momentum until liquidity, dilution, and news risk are reviewed.")

    payload = {
        "status": "ok",
        "overall": "pass",
        "type": "missed_mover_audit",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "authority_changed": False,
        "symbol": symbol,
        "classification": {
            "asset_class": "equity",
            "asset_bucket": asset_bucket,
            "microcap_or_speculative": microcap_or_speculative,
        },
        "coverage": {
            "in_watchlist_or_universe": in_watchlist,
            "in_open_positions": open_position,
            "trade_rows_found": len(trade_mentions),
            "found_in_recent_decision_sections": scanned,
            "candidate_symbol": candidate,
            "blocked_symbol": blocked,
        },
        "decision_read": {
            "decision": decision,
            "reason": reason,
            "decision_hits": decision_hits[:10],
        },
        "context": {
            "open_positions_count": len(positions),
            "recent_trade_rows_count": len(trades),
            "sections_reviewed": sorted(decision_sections.keys()),
            "watchlist_symbols_seen_count": len(watchlist),
        },
        "guardrails": {
            "does_not_trade": True,
            "does_not_change_risk": True,
            "does_not_change_ml_authority": True,
            "does_not_lower_thresholds": True,
            "one_test_workflow_preserved": True,
        },
        "recommendations": recommendations,
    }

    try:
        if isinstance(pf, dict):
            pf["missed_mover_audit_last"] = {
                "symbol": symbol,
                "decision": decision,
                "version": VERSION,
                "authority_changed": False,
            }
    except Exception:
        pass

    return payload


def apply(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "overall": "pass",
        "type": "missed_mover_audit_status",
        "version": VERSION,
        "advisory_only": True,
        "authority_changed": False,
        "route": "/paper/missed-mover-audit?symbol=MNTS",
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    from flask import jsonify, request

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def audit_route():
        symbol = request.args.get("symbol", "MNTS")
        return jsonify(build_payload(symbol, core))

    def status_route():
        return jsonify(apply(core))

    if "/paper/missed-mover-audit" not in existing:
        flask_app.add_url_rule(
            "/paper/missed-mover-audit",
            "missed_mover_audit",
            audit_route,
        )

    if "/paper/missed-mover-audit-status" not in existing:
        flask_app.add_url_rule(
            "/paper/missed-mover-audit-status",
            "missed_mover_audit_status",
            status_route,
        )

    REGISTERED_APP_IDS.add(id(flask_app))
