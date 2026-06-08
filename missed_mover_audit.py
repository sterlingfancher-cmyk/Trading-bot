"""Missed mover audit + shadow speculative momentum discovery.

Advisory-only diagnostics for fast movers that are outside the main scanner.

Adds:
- Better volume-spike telemetry.
- Top shadow-mover observations persisted into the ML feature journal area.
- Scanner bridge reporting: shadow mover seen -> core scanner ignored/rejected/blocked/eligible.
- Shadow-only authority preserved.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Set, Tuple

VERSION = "missed-mover-audit-2026-06-08-v3-volume-bridge-journal"
REGISTERED_APP_IDS: set[int] = set()

SMALL_CAP_CONTEXT_ETFS = ["IWM", "IWO", "IJR", "XBI", "ARKK", "UFO"]

SPECULATIVE_BUCKETS = {
    "space_momentum": ["MNTS", "RKLB", "LUNR", "ASTS", "BKSY", "SPIR", "SIDU"],
    "small_cap_momentum": ["MNTS", "SOUN", "JOBY", "QBTS", "RXRX", "TEM", "ACHR", "IONQ", "RGTI"],
    "bitcoin_ai_compute": ["HIVE", "HUT", "RIOT", "CLSK", "MARA", "BTDR", "WULF", "IREN", "CORZ", "CIFR"],
    "ai_software_momentum": ["SOUN", "AI", "BBAI", "PLTR", "PATH", "DDOG", "APP", "DUOL"],
    "biotech_speculative": ["RXRX", "TEM", "DNA", "EDIT", "CRSP", "NTLA", "BEAM"],
}

MIN_MOVE_PCT_WATCH = 5.0
MIN_VOLUME_SPIKE_RATIO_WATCH = 1.5
MAX_PERSISTED_SHADOW_ROWS = 500
MAX_OBSERVATIONS_PER_CALL = 25


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


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return int(float(value))
    except Exception:
        return default


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
    symbol = _symbol(symbol)
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
        "WATCHLIST", "WATCHLIST_SYMBOLS", "DEFAULT_WATCHLIST", "UNIVERSE",
        "TRADING_UNIVERSE", "SCAN_UNIVERSE", "LONG_WATCHLIST", "SHORT_WATCHLIST",
    ):
        try:
            symbols |= _flatten_symbols(getattr(core, attr, None))
        except Exception:
            pass

    for key in ("watchlist", "watchlists", "universe", "scanner_universe", "symbols", "long_symbols", "short_symbols"):
        symbols |= _flatten_symbols(state.get(key))

    return symbols


def _latest_decision_sections(state: Dict[str, Any], pf: Dict[str, Any]) -> Dict[str, Any]:
    sections = {}
    for key in (
        "scanner_audit", "decision_audit", "decision_audit_summary", "latest_redeployment",
        "post_harvest_redeployment", "entry_decision_visibility", "paper_controlled_expansion",
        "expansion_impact_monitor", "ml_feature_journal",
    ):
        if isinstance(pf.get(key), dict):
            sections[key] = pf.get(key)
        elif isinstance(state.get(key), dict):
            sections[key] = state.get(key)
    return sections


def _bucket_for_symbol(symbol: str) -> Tuple[str, List[str]]:
    symbol = _symbol(symbol)
    matched = [bucket for bucket, members in SPECULATIVE_BUCKETS.items() if symbol in members]
    return (matched[0], matched) if matched else ("unknown", [])


def _seed_symbols() -> List[str]:
    seen = []
    for members in SPECULATIVE_BUCKETS.values():
        for symbol in members:
            if symbol not in seen:
                seen.append(symbol)
    return seen


def _series_for_column(data: Any, column_name: str, symbol: str):
    """Return a pandas Series for a yfinance column across flat or MultiIndex columns."""
    try:
        if data is None or data.empty:
            return None
        columns = getattr(data, "columns", None)
        if columns is None:
            return None

        if column_name in columns:
            series = data[column_name]
            if hasattr(series, "columns"):
                if symbol in series.columns:
                    return series[symbol]
                return series.iloc[:, 0]
            return series

        if hasattr(columns, "levels"):
            for col in columns:
                try:
                    if len(col) >= 2 and str(col[0]).lower() == column_name.lower() and _symbol(col[1]) == _symbol(symbol):
                        return data[col]
                except Exception:
                    pass
            for col in columns:
                try:
                    if len(col) >= 1 and str(col[0]).lower() == column_name.lower():
                        return data[col]
                except Exception:
                    pass
    except Exception:
        return None
    return None


def _clean_series_values(series: Any) -> List[float]:
    values: List[float] = []
    try:
        if series is None:
            return values
        for raw in list(series):
            value = _safe_float(raw, None)
            if value is not None and value == value:
                values.append(float(value))
    except Exception:
        return []
    return values


def _fetch_snapshot(symbol: str) -> Dict[str, Any]:
    """Best-effort daily price and volume snapshot.

    Volume average uses prior completed rows and excludes the current row.
    Failure is non-fatal and advisory-only.
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
        "data_quality": {"price_ok": False, "volume_ok": False, "volume_source": "none", "volume_error": None},
        "data_error": None,
    }

    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        empty["data_error"] = f"yfinance_unavailable:{type(exc).__name__}"
        empty["data_quality"]["volume_error"] = empty["data_error"]
        return empty

    try:
        data = yf.download(symbol, period="20d", interval="1d", progress=False, auto_adjust=False, threads=False)
    except Exception as exc:
        empty["data_error"] = f"download_failed:{type(exc).__name__}"
        empty["data_quality"]["volume_error"] = empty["data_error"]
        return empty

    try:
        if data is None or len(data) < 2:
            empty["data_error"] = "not_enough_rows"
            empty["data_quality"]["volume_error"] = "not_enough_rows"
            return empty

        closes = _series_for_column(data, "Close", symbol)
        volumes = _series_for_column(data, "Volume", symbol)

        close_values = _clean_series_values(closes)
        if len(close_values) < 2:
            empty["data_error"] = "close_values_unavailable"
            return empty

        last_close = close_values[-1]
        prev_close = close_values[-2]
        pct_change = ((last_close - prev_close) / prev_close) * 100.0 if prev_close else 0.0

        volume = None
        avg_volume = None
        volume_spike = None
        volume_error = None

        volume_values = _clean_series_values(volumes)
        if len(volume_values) >= 2:
            volume = volume_values[-1]
            prior_values = [v for v in volume_values[:-1][-5:] if v and v > 0]
            if prior_values:
                avg_volume = sum(prior_values) / len(prior_values)
                if avg_volume > 0 and volume is not None:
                    volume_spike = volume / avg_volume
            else:
                volume_error = "prior_volume_average_unavailable"
        else:
            volume_error = "volume_values_unavailable"

        volume_ok = volume is not None and avg_volume is not None and avg_volume > 0 and volume_spike is not None

        return {
            "symbol": symbol,
            "data_available": True,
            "price": round(last_close, 4),
            "previous_close": round(prev_close, 4),
            "pct_change": round(pct_change, 4),
            "volume": _safe_int(volume, 0) if volume is not None else None,
            "avg_volume": round(avg_volume, 2) if avg_volume is not None else None,
            "volume_spike_ratio": round(volume_spike, 4) if volume_spike is not None else None,
            "data_quality": {
                "price_ok": True,
                "volume_ok": bool(volume_ok),
                "volume_source": "yfinance_daily_prior_5_rows" if volume_ok else "unavailable",
                "volume_error": volume_error,
            },
            "data_error": None,
        }
    except Exception as exc:
        empty["data_error"] = f"snapshot_parse_failed:{type(exc).__name__}"
        empty["data_quality"]["volume_error"] = empty["data_error"]
        return empty


def _small_cap_context() -> Dict[str, Any]:
    rows = []
    positives = 0
    usable = 0
    volume_ok_count = 0

    for symbol in SMALL_CAP_CONTEXT_ETFS:
        snap = _fetch_snapshot(symbol)
        rows.append(snap)
        if snap.get("data_available") and snap.get("pct_change") is not None:
            usable += 1
            if _safe_float(snap.get("pct_change")) > 0:
                positives += 1
        if isinstance(snap.get("data_quality"), dict) and snap["data_quality"].get("volume_ok"):
            volume_ok_count += 1

    usable_changes = [_safe_float(row.get("pct_change")) for row in rows if row.get("pct_change") is not None]
    avg_change = round(sum(usable_changes) / len(usable_changes), 4) if usable_changes else None

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
        "volume_ok_count": volume_ok_count,
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


def _scanner_bridge_for_symbol(
    symbol: str,
    decision_sections: Dict[str, Any],
    watchlist: Set[str],
    positions: Dict[str, Any],
    trades: List[Dict[str, Any]],
) -> Dict[str, Any]:
    symbol = _symbol(symbol)
    positions_symbols = {_symbol(s) for s in positions.keys()}
    trade_rows = [row for row in trades if isinstance(row, dict) and _symbol(row.get("symbol")) == symbol]

    scanned_symbols = set()
    rejected_symbols = set()
    blocked_symbols = set()
    candidate_symbols = set()
    eligible_symbols = set()

    for section in decision_sections.values():
        if not isinstance(section, dict):
            continue

        scanned_symbols |= _flatten_symbols(section.get("signals"))
        scanned_symbols |= _flatten_symbols(section.get("signals_found"))
        scanned_symbols |= _flatten_symbols(section.get("top_signals"))
        scanned_symbols |= _flatten_symbols(section.get("top_candidates_reviewed"))

        rejected_symbols |= _flatten_symbols(section.get("rejected_signals"))
        rejected_symbols |= _flatten_symbols(section.get("rejected_top_candidates"))

        blocked_symbols |= _flatten_symbols(section.get("top_blocked_symbols"))
        blocked_symbols |= _flatten_symbols(section.get("blocked_entries"))
        blocked_symbols |= _flatten_symbols(section.get("blocked_post_harvest_entries"))

        candidate_symbols |= _flatten_symbols(section.get("candidate_symbols"))
        candidate_symbols |= _flatten_symbols(section.get("candidates"))

        eligible_symbols |= _flatten_symbols(section.get("eligible_symbols"))
        eligible_symbols |= _flatten_symbols(section.get("eligible_candidates"))

    decision_hits = _find_dicts_for_symbol(decision_sections, symbol)

    if symbol in positions_symbols:
        status = "eligible_open_position"
        reason = "Symbol is already open in the core book."
    elif symbol in blocked_symbols:
        status = "blocked"
        reason = "Symbol appeared in blocked-entry diagnostics."
    elif symbol in rejected_symbols:
        status = "rejected"
        reason = "Symbol appeared in rejected-signal or rejected-candidate diagnostics."
    elif symbol in eligible_symbols or symbol in candidate_symbols:
        status = "eligible"
        reason = "Symbol appeared as eligible/candidate but no trade may have been placed."
    elif symbol in scanned_symbols or decision_hits:
        status = "seen_not_selected"
        reason = "Symbol was seen in scanner context but not selected."
    elif symbol in watchlist:
        status = "ignored_watchlist_not_triggered"
        reason = "Symbol is in watchlist/universe but did not trigger recent scanner/candidate records."
    else:
        status = "ignored_not_in_core_context"
        reason = "Symbol was not found in current core scanner, watchlist, position, or trade context."

    return {
        "symbol": symbol,
        "core_scanner_status": status,
        "reason": reason,
        "in_watchlist_or_universe": symbol in watchlist,
        "in_open_positions": symbol in positions_symbols,
        "trade_rows_found": len(trade_rows),
        "found_in_recent_decision_sections": bool(symbol in scanned_symbols or decision_hits),
        "candidate_symbol": symbol in candidate_symbols,
        "eligible_symbol": symbol in eligible_symbols,
        "rejected_symbol": symbol in rejected_symbols,
        "blocked_symbol": symbol in blocked_symbols,
        "decision_hits": decision_hits[:10],
    }


def _score_shadow_mover(snapshot: Dict[str, Any], tags: Dict[str, Any], bridge: Dict[str, Any]) -> float:
    score = 0.0
    pct = snapshot.get("pct_change")
    spike = snapshot.get("volume_spike_ratio")

    if pct is not None:
        score += max(0.0, min(50.0, _safe_float(pct) or 0.0)) / 50.0
    if spike is not None:
        score += max(0.0, min(5.0, _safe_float(spike) or 0.0)) / 10.0
    if tags.get("microcap_or_speculative"):
        score += 0.15
    if tags.get("seen_in_recent_decision_context"):
        score += 0.10

    status = bridge.get("core_scanner_status")
    if status in {"eligible", "seen_not_selected"}:
        score += 0.10
    elif status == "blocked":
        score -= 0.05

    return round(score, 6)


def _persist_shadow_observations(core: Any, rows: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort telemetry persistence only. Does not change trading authority."""
    pf = _portfolio(core)
    if not isinstance(pf, dict):
        return {"persisted": False, "reason": "portfolio_unavailable", "rows_added": 0}

    now_text = _now(core)
    observations = []
    for row in rows[:MAX_OBSERVATIONS_PER_CALL]:
        snapshot = row.get("snapshot", {}) if isinstance(row.get("snapshot"), dict) else {}
        tags = row.get("tags", {}) if isinstance(row.get("tags"), dict) else {}
        bridge = row.get("scanner_bridge", {}) if isinstance(row.get("scanner_bridge"), dict) else {}
        quality = snapshot.get("data_quality", {}) if isinstance(snapshot.get("data_quality"), dict) else {}

        observations.append({
            "ts_local": now_text,
            "source": "speculative_momentum_shadow",
            "symbol": row.get("symbol"),
            "asset_class": "equity",
            "primary_bucket": tags.get("primary_bucket"),
            "buckets": tags.get("buckets"),
            "shadow_score": row.get("shadow_score"),
            "pct_change": snapshot.get("pct_change"),
            "price": snapshot.get("price"),
            "volume": snapshot.get("volume"),
            "avg_volume": snapshot.get("avg_volume"),
            "volume_spike_ratio": snapshot.get("volume_spike_ratio"),
            "volume_ok": quality.get("volume_ok"),
            "move_watch": row.get("move_watch"),
            "volume_watch": row.get("volume_watch"),
            "core_scanner_status": bridge.get("core_scanner_status"),
            "core_scanner_reason": bridge.get("reason"),
            "trade_authority": "none",
            "ml_authority": "shadow_only",
            "included_in_ml_observation_data": True,
            "small_cap_risk_context": context.get("risk_context"),
        })

    journal = pf.setdefault("ml_feature_journal", {})
    if not isinstance(journal, dict):
        journal = {}
        pf["ml_feature_journal"] = journal

    existing = journal.setdefault("shadow_mover_observations", [])
    if not isinstance(existing, list):
        existing = []
        journal["shadow_mover_observations"] = existing

    existing.extend(observations)
    if len(existing) > MAX_PERSISTED_SHADOW_ROWS:
        del existing[:-MAX_PERSISTED_SHADOW_ROWS]

    pf["speculative_momentum_last_observation"] = {
        "ts_local": now_text,
        "version": VERSION,
        "rows_added": len(observations),
        "rows_total": len(existing),
        "authority_changed": False,
        "trade_authority": "none",
        "ml_authority": "shadow_only",
        "small_cap_context": {
            "risk_context": context.get("risk_context"),
            "average_pct_change": context.get("average_pct_change"),
            "positive_count": context.get("positive_count"),
            "usable_count": context.get("usable_count"),
            "volume_ok_count": context.get("volume_ok_count"),
        },
    }

    save_attempted = False
    save_ok = False
    save_error = None
    try:
        save_fn = getattr(core, "save_state", None)
        if callable(save_fn):
            save_attempted = True
            try:
                save_fn(pf)
                save_ok = True
            except TypeError:
                save_fn()
                save_ok = True
    except Exception as exc:
        save_error = f"{type(exc).__name__}: {exc}"

    return {
        "persisted": True,
        "rows_added": len(observations),
        "rows_total": len(existing),
        "save_attempted": save_attempted,
        "save_ok": save_ok,
        "save_error": save_error,
        "target": "portfolio.ml_feature_journal.shadow_mover_observations",
    }


def build_speculative_movers(core: Any = None, limit: int = 25, persist: bool = True) -> Dict[str, Any]:
    state = _state(core)
    pf = _portfolio(core)
    watchlist = _watchlist_symbols(core, state)
    sections = _latest_decision_sections(state, pf)

    positions = pf.get("positions") if isinstance(pf.get("positions"), dict) else state.get("positions", {})
    trades = pf.get("trades") if isinstance(pf.get("trades"), list) else state.get("trades", [])
    positions = positions if isinstance(positions, dict) else {}
    trades = trades if isinstance(trades, list) else []

    recent_symbols = _flatten_symbols(sections)
    symbols = set(_seed_symbols()) | (recent_symbols & set(_seed_symbols()))

    rows = []
    for symbol in sorted(symbols):
        in_watchlist = symbol in watchlist
        seen_recent = symbol in recent_symbols
        tags = _speculative_tags(symbol, in_watchlist, seen_recent)
        snapshot = _fetch_snapshot(symbol)
        bridge = _scanner_bridge_for_symbol(symbol, sections, watchlist, positions, trades)

        pct = snapshot.get("pct_change")
        spike = snapshot.get("volume_spike_ratio")

        move_watch = bool(pct is not None and abs(_safe_float(pct) or 0.0) >= MIN_MOVE_PCT_WATCH)
        volume_watch = bool(spike is not None and (_safe_float(spike) or 0.0) >= MIN_VOLUME_SPIKE_RATIO_WATCH)

        rows.append({
            "symbol": symbol,
            "shadow_score": _score_shadow_mover(snapshot, tags, bridge),
            "move_watch": move_watch,
            "volume_watch": volume_watch,
            "snapshot": snapshot,
            "tags": tags,
            "scanner_bridge": bridge,
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
    top_rows = rows[:max(1, int(limit or 25))]
    persistence = _persist_shadow_observations(core, top_rows, context) if persist else {
        "persisted": False,
        "reason": "persist_disabled",
        "rows_added": 0,
    }

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
        "persistence": persistence,
        "policy": {
            "small_cap_context_etfs": SMALL_CAP_CONTEXT_ETFS,
            "speculative_buckets": SPECULATIVE_BUCKETS,
            "min_move_pct_watch": MIN_MOVE_PCT_WATCH,
            "min_volume_spike_ratio_watch": MIN_VOLUME_SPIKE_RATIO_WATCH,
            "does_not_trade": True,
            "does_not_change_risk": True,
            "does_not_lower_thresholds": True,
            "does_not_change_ml_authority": True,
        },
        "top_shadow_movers": top_rows,
        "rows_total": len(rows),
        "next_actions": [
            "Use this for observation only.",
            "Do not allow this bucket to trade until enough shadow data exists.",
            "Review scanner_bridge.core_scanner_status to distinguish ignored/rejected/blocked/eligible names.",
            "If repeated movers appear outside the core universe, consider a separate paper-only promotion gate.",
        ],
    }


def build_bridge_report(symbol: str, core: Any = None) -> Dict[str, Any]:
    symbol = _symbol(symbol)
    state = _state(core)
    pf = _portfolio(core)
    watchlist = _watchlist_symbols(core, state)
    sections = _latest_decision_sections(state, pf)

    positions = pf.get("positions") if isinstance(pf.get("positions"), dict) else state.get("positions", {})
    trades = pf.get("trades") if isinstance(pf.get("trades"), list) else state.get("trades", [])
    positions = positions if isinstance(positions, dict) else {}
    trades = trades if isinstance(trades, list) else []

    tags = _speculative_tags(symbol, symbol in watchlist, symbol in _flatten_symbols(sections))
    bridge = _scanner_bridge_for_symbol(symbol, sections, watchlist, positions, trades)
    snapshot = _fetch_snapshot(symbol)

    return {
        "status": "ok",
        "overall": "pass",
        "type": "speculative_scanner_bridge_report",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "authority_changed": False,
        "symbol": symbol,
        "snapshot": snapshot,
        "dynamic_discovery_tags": tags,
        "scanner_bridge": bridge,
        "interpretation": bridge.get("reason"),
        "guardrails": {
            "does_not_trade": True,
            "does_not_change_risk": True,
            "does_not_change_ml_authority": True,
            "does_not_lower_thresholds": True,
            "one_test_workflow_preserved": True,
        },
    }


def build_missed_mover_payload(symbol: str, core: Any = None) -> Dict[str, Any]:
    bridge_report = build_bridge_report(symbol, core)
    bridge = bridge_report.get("scanner_bridge", {})
    tags = bridge_report.get("dynamic_discovery_tags", {})

    recommendations = [
        "Do not lower thresholds just because one symbol moved.",
        "Use this audit to determine whether the issue was universe coverage, rejection, block, or timing.",
        "If this symbol class repeats, keep it shadow-only before allowing paper entries.",
    ]
    if bridge.get("core_scanner_status") == "ignored_not_in_core_context":
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
        "symbol": _symbol(symbol),
        "classification": {
            "asset_class": "equity",
            "asset_bucket": tags.get("primary_bucket"),
            "all_buckets": tags.get("buckets"),
            "microcap_or_speculative": tags.get("microcap_or_speculative"),
            "shadow_only": True,
        },
        "coverage": {
            "in_watchlist_or_universe": bridge.get("in_watchlist_or_universe"),
            "in_open_positions": bridge.get("in_open_positions"),
            "trade_rows_found": bridge.get("trade_rows_found"),
            "found_in_recent_decision_sections": bridge.get("found_in_recent_decision_sections"),
            "candidate_symbol": bridge.get("candidate_symbol"),
            "eligible_symbol": bridge.get("eligible_symbol"),
            "rejected_symbol": bridge.get("rejected_symbol"),
            "blocked_symbol": bridge.get("blocked_symbol"),
        },
        "market_snapshot": bridge_report.get("snapshot"),
        "dynamic_discovery_tags": tags,
        "scanner_bridge": bridge,
        "decision_read": {
            "decision": bridge.get("core_scanner_status"),
            "reason": bridge.get("reason"),
            "decision_hits": bridge.get("decision_hits", []),
        },
        "guardrails": bridge_report.get("guardrails"),
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
            "/paper/speculative-bridge?symbol=QBTS",
        ],
        "trading_authority": "none",
        "ml_authority": "shadow_only",
        "features": [
            "volume_spike_telemetry",
            "ml_feature_journal_shadow_observation_persistence",
            "scanner_bridge_report_ignored_rejected_blocked_eligible",
        ],
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
        persist_arg = str(request.args.get("persist", "1")).lower()
        persist = persist_arg not in {"0", "false", "no"}
        try:
            limit_int = int(limit)
        except Exception:
            limit_int = 25
        return jsonify(build_speculative_movers(core, limit_int, persist=persist))

    def bridge_route():
        symbol = request.args.get("symbol", "QBTS")
        return jsonify(build_bridge_report(symbol, core))

    if "/paper/missed-mover-audit" not in existing:
        flask_app.add_url_rule("/paper/missed-mover-audit", "missed_mover_audit", audit_route)

    if "/paper/missed-mover-audit-status" not in existing:
        flask_app.add_url_rule("/paper/missed-mover-audit-status", "missed_mover_audit_status", status_route)

    if "/paper/speculative-momentum-status" not in existing:
        flask_app.add_url_rule("/paper/speculative-momentum-status", "speculative_momentum_status", status_route)

    if "/paper/speculative-movers" not in existing:
        flask_app.add_url_rule("/paper/speculative-movers", "speculative_movers", speculative_route)

    if "/paper/speculative-bridge" not in existing:
        flask_app.add_url_rule("/paper/speculative-bridge", "speculative_bridge", bridge_route)

    REGISTERED_APP_IDS.add(id(flask_app))
