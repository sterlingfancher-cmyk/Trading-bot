"""Missed mover audit + shadow speculative momentum discovery.

Advisory-only diagnostics for fast movers that are outside the main scanner.
This module adds:

- Small-cap ETF context scanner.
- Shadow-only speculative momentum bucket.
- Dynamic missed-mover discovery tags.
- Route that reports top small-cap/speculative movers seen.
- No trading authority.

Routes:
    /paper/missed-mover-audit?symbol=MNTS
    /paper/missed-mover-audit-status
    /paper/speculative-momentum-status
    /paper/speculative-movers

This module does not trade, resize, change risk controls, change ML authority,
lower thresholds, or modify scanner behavior.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Set, Tuple

VERSION = "missed-mover-audit-2026-06-05-v2-shadow-speculative-momentum"
REGISTERED_APP_IDS: set[int] = set()

SMALL_CAP_CONTEXT_ETFS = [
    "IWM",   # Russell 2000
    "IWO",   # Russell 2000 growth
    "IJR",   # S&P small-cap 600
    "XBI",   # biotech risk appetite
    "ARKK",  # speculative innovation proxy
    "UFO",   # space theme proxy
]

SPECULATIVE_BUCKETS = {
    "space_momentum": [
        "MNTS", "RKLB", "LUNR", "ASTS", "BKSY", "SPIR", "SIDU",
    ],
    "small_cap_momentum": [
        "MNTS", "SOUN", "JOBY", "QBTS", "RXRX", "TEM", "ACHR", "IONQ", "RGTI",
    ],
    "bitcoin_ai_compute": [
        "HIVE", "HUT", "RIOT", "CLSK", "MARA", "BTDR", "WULF", "IREN", "CORZ", "CIFR",
    ],
    "ai_software_momentum": [
        "SOUN", "AI", "BBAI", "PLTR", "PATH", "DDOG", "APP", "DUOL",
    ],
    "biotech_speculative": [
        "RXRX", "TEM", "DNA", "EDIT", "CRSP", "NTLA", "BEAM",
    ],
}

MIN_MOVE_PCT_WATCH = 5.0
MIN_VOLUME_SPIKE_RATIO_WATCH = 1.5


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


def _flatten_symbols(obj: Any, max_items: int = 10000) -> Set[str]:
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
        "LONG_WATCHLIST", "SHORT_WATCHLIST",
    ):
        try:
            symbols |= _flatten_symbols(getattr(core, attr, None))
        except Exception:
            pass

    for key in (
        "watchlist", "watchlists", "universe", "scanner_universe",
        "symbols", "long_symbols", "short_symbols",
    ):
        symbols |= _flatten_symbols(state.get(key))

    return symbols


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


def _bucket_for_symbol(symbol: str) -> Tuple[str, List[str]]:
    matched = []
    for bucket, members in SPECULATIVE_BUCKETS.items():
        if symbol in members:
            matched.append(bucket)
    if matched:
        return matched[0], matched
    return "unknown", []


def _seed_symbols() -> List[str]:
    seen = []
    for members in SPECULATIVE_BUCKETS.values():
        for symbol in members:
            if symbol not in seen:
                seen.append(symbol)
    return seen


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _fetch_snapshot(symbol: str) -> Dict[str, Any]:
    """Best-effort daily price snapshot.

    Uses yfinance if available. Failure is non-fatal and advisory-only.
    """
    symbol = _symbol(symbol)
    empty = {
        "symbol": symbol,
        "data_available": False,
        "price": None,
        "previous_close": None,
        "pct_change": None,
        "volume": None,
        "avg_volume": None,
        "volume_spike_ratio": None,
        "data_error": None,
    }

    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        empty["data_error"] = f"yfinance_unavailable:{type(exc).__name__}"
        return empty

    try:
        data = yf.download(
            symbol,
            period="10d",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
        )
    except Exception as exc:
        empty["data_error"] = f"download_failed:{type(exc).__name__}"
        return empty

    try:
        if data is None or len(data) < 2:
            empty["data_error"] = "not_enough_rows"
            return empty

        close_col = "Close"
        volume_col = "Volume"

        closes = data[close_col]
        volumes = data[volume_col] if volume_col in data else None

        # Handle possible single-column dataframe from yfinance multi-index cases.
        try:
            if hasattr(closes, "iloc") and hasattr(closes.iloc[-1], "item"):
                last_close = closes.iloc[-1].item()
                prev_close = closes.iloc[-2].item()
            else:
                last_close = closes.iloc[-1]
                prev_close = closes.iloc[-2]
        except Exception:
            last_close = closes.iloc[-1]
            prev_close = closes.iloc[-2]

        last_close = _safe_float(last_close)
        prev_close = _safe_float(prev_close)

        pct_change = 0.0
        if prev_close:
            pct_change = ((last_close - prev_close) / prev_close) * 100.0

        volume = None
        avg_volume = None
        volume_spike = None

        if volumes is not None and len(volumes) >= 2:
            try:
                volume = _safe_float(volumes.iloc[-1].item() if hasattr(volumes.iloc[-1], "item") else volumes.iloc[-1])
                avg_slice = volumes.iloc[:-1].tail(5)
                avg_volume = _safe_float(avg_slice.mean())
                if avg_volume:
                    volume_spike = volume / avg_volume
            except Exception:
                pass

        return {
            "symbol": symbol,
            "data_available": True,
            "price": round(last_close, 4),
            "previous_close": round(prev_close, 4),
            "pct_change": round(pct_change, 4),
            "volume": volume,
            "avg_volume": avg_volume,
            "volume_spike_ratio": round(volume_spike, 4) if volume_spike is not None else None,
            "data_error": None,
        }

    except Exception as exc:
        empty["data_error"] = f"snapshot_parse_failed:{type(exc).__name__}"
        return empty


def _small_cap_context() -> Dict[str, Any]:
    rows = []
    positives = 0
    usable = 0

    for symbol in SMALL_CAP_CONTEXT_ETFS:
        snap = _fetch_snapshot(symbol)
        rows.append(snap)
        if snap.get("data_available") and snap.get("pct_change") is not None:
            usable += 1
            if _safe_float(snap.get("pct_change")) > 0:
                positives += 1

    avg_change = None
    usable_changes = [_safe_float(row.get("pct_change")) for row in rows if row.get("pct_change") is not None]
    if usable_changes:
        avg_change = round(sum(usable_changes) / len(usable_changes), 4)

    risk_context = "unknown"
    if usable:
        if positives >= max(2, usable // 2) and (avg_change or 0) > 0:
            risk_context = "small_cap_risk_on"
        elif positives == 0 and (avg_change or 0) < 0:
            risk_context = "small_cap_risk_off"
        else:
            risk_context = "mixed"

    return {
        "risk_context": risk_context,
        "etfs_checked": SMALL_CAP_CONTEXT_ETFS,
        "usable_count": usable,
        "positive_count": positives,
        "average_pct_change": avg_change,
        "rows": rows,
    }


def _speculative_tags(symbol: str, in_watchlist: bool, seen_recently: bool) -> Dict[str, Any]:
    primary_bucket, buckets = _bucket_for_symbol(symbol)
    return {
        "symbol": symbol,
        "asset_class": "equity",
        "primary_bucket": primary_bucket,
        "buckets": buckets,
        "microcap_or_speculative": primary_bucket != "unknown",
        "shadow_only": True,
        "trade_authority": "none",
        "ml_authority": "shadow_only",
        "included_in_ml_observation_data": True,
        "included_in_core_strategy_score": False,
        "in_watchlist_or_universe": in_watchlist,
        "seen_in_recent_decision_context": seen_recently,
    }


def _score_shadow_mover(snapshot: Dict[str, Any], tags: Dict[str, Any]) -> float:
    score = 0.0

    pct = snapshot.get("pct_change")
    spike = snapshot.get("volume_spike_ratio")

    if pct is not None:
        score += max(0.0, min(50.0, _safe_float(pct))) / 50.0

    if spike is not None:
        score += max(0.0, min(5.0, _safe_float(spike))) / 10.0

    if tags.get("microcap_or_speculative"):
        score += 0.15

    if tags.get("seen_in_recent_decision_context"):
        score += 0.10

    return round(score, 6)


def build_speculative_movers(core: Any = None, limit: int = 25) -> Dict[str, Any]:
    state = _state(core)
    pf = _portfolio(core)
    watchlist = _watchlist_symbols(core, state)
    sections = _latest_decision_sections(state, pf)

    recent_symbols = _flatten_symbols(sections)
    symbols = set(_seed_symbols()) | (recent_symbols & set(_seed_symbols()))

    rows = []
    for symbol in sorted(symbols):
        in_watchlist = symbol in watchlist
        seen_recent = symbol in recent_symbols
        tags = _speculative_tags(symbol, in_watchlist, seen_recent)
        snapshot = _fetch_snapshot(symbol)

        pct = snapshot.get("pct_change")
        spike = snapshot.get("volume_spike_ratio")

        move_watch = bool(
            pct is not None and abs(_safe_float(pct)) >= MIN_MOVE_PCT_WATCH
        )
        volume_watch = bool(
            spike is not None and _safe_float(spike) >= MIN_VOLUME_SPIKE_RATIO_WATCH
        )

        rows.append({
            "symbol": symbol,
            "shadow_score": _score_shadow_mover(snapshot, tags),
            "move_watch": move_watch,
            "volume_watch": volume_watch,
            "snapshot": snapshot,
            "tags": tags,
            "decision": "shadow_observe_only",
            "reason": "Speculative momentum discovery is shadow-only and cannot place trades.",
        })

    rows.sort(
        key=lambda row: (
            row.get("move_watch", False),
            row.get("volume_watch", False),
            row.get("shadow_score", 0.0),
        ),
        reverse=True,
    )

    context = _small_cap_context()

    return {
        "status": "ok",
        "overall": "pass",
        "type": "speculative_momentum_shadow_status",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "authority_changed": False,
        "trading_authority": "none",
        "ml_authority": "shadow_only",
        "small_cap_context": context,
        "policy": {
            "small_cap_context_etfs": SMALL_CAP_CONTEXT_ETFS,
            "speculative_buckets": SPECULATIVE_BUCKETS,
            "min_move_pct_watch": MIN_MOVE_PCT_WATCH,
            "min_volume_spike_ratio_watch": MIN_VOLUME_SPIKE_RATIO_WATCH,
            "does_not_trade": True,
            "does_not_change_risk": True,
            "does_not_lower_thresholds": True,
        },
        "top_shadow_movers": rows[:max(1, int(limit or 25))],
        "rows_total": len(rows),
        "next_actions": [
            "Use this for observation only.",
            "Do not allow this bucket to trade until enough shadow data exists.",
            "If repeated movers appear outside the core universe, consider a separate paper-only promotion gate.",
        ],
    }


def build_missed_mover_payload(symbol: str, core: Any = None) -> Dict[str, Any]:
    symbol = _symbol(symbol)
    state = _state(core)
    pf = _portfolio(core)

    positions = pf.get("positions") if isinstance(pf.get("positions"), dict) else state.get("positions", {})
    trades = pf.get("trades") if isinstance(pf.get("trades"), list) else state.get("trades", [])

    positions = positions if isinstance(positions, dict) else {}
    trades = trades if isinstance(trades, list) else []

    decision_sections = _latest_decision_sections(state, pf)
    watchlist = _watchlist_symbols(core, state)
    recent_symbols = _flatten_symbols(decision_sections)

    scanned_symbols = set()
    blocked_symbols = set()
    candidate_symbols = set()

    for section in decision_sections.values():
        if isinstance(section, dict):
            scanned_symbols |= _flatten_symbols(section.get("signals"))
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
    scanned = symbol in scanned_symbols or symbol in recent_symbols or bool(decision_hits)
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

    snapshot = _fetch_snapshot(symbol)
    tags = _speculative_tags(symbol, in_watchlist, scanned)

    recommendations = [
        "Do not lower thresholds just because one symbol moved.",
        "Use this audit to determine whether the issue was universe coverage, rejection, block, or timing.",
        "If this symbol class repeats, keep it shadow-only before allowing paper entries.",
    ]

    if decision == "not_in_recent_scanner_context":
        recommendations.insert(0, "Likely scanner-universe gap; shadow-only discovery is appropriate.")
    if tags.get("microcap_or_speculative"):
        recommendations.append("Treat as speculative/microcap momentum until liquidity, dilution, and news risk are reviewed.")

    return {
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
            "asset_bucket": tags.get("primary_bucket"),
            "all_buckets": tags.get("buckets"),
            "microcap_or_speculative": tags.get("microcap_or_speculative"),
            "shadow_only": True,
        },
        "coverage": {
            "in_watchlist_or_universe": in_watchlist,
            "in_open_positions": open_position,
            "trade_rows_found": len(trade_mentions),
            "found_in_recent_decision_sections": scanned,
            "candidate_symbol": candidate,
            "blocked_symbol": blocked,
        },
        "market_snapshot": snapshot,
        "dynamic_discovery_tags": tags,
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


def apply(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "overall": "pass",
        "type": "missed_mover_audit_status",
        "version": VERSION,
        "advisory_only": True,
        "authority_changed": False,
        "routes": [
            "/paper/missed-mover-audit?symbol=MNTS",
            "/paper/missed-mover-audit-status",
            "/paper/speculative-momentum-status",
            "/paper/speculative-movers",
        ],
        "trading_authority": "none",
        "ml_authority": "shadow_only",
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
        return jsonify(build_missed_mover_payload(symbol, core))

    def status_route():
        return jsonify(apply(core))

    def speculative_route():
        limit = request.args.get("limit", "25")
        try:
            limit_int = int(limit)
        except Exception:
            limit_int = 25
        return jsonify(build_speculative_movers(core, limit_int))

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

    if "/paper/speculative-momentum-status" not in existing:
        flask_app.add_url_rule(
            "/paper/speculative-momentum-status",
            "speculative_momentum_status",
            status_route,
        )

    if "/paper/speculative-movers" not in existing:
        flask_app.add_url_rule(
            "/paper/speculative-movers",
            "speculative_movers",
            speculative_route,
        )

    REGISTERED_APP_IDS.add(id(flask_app))
