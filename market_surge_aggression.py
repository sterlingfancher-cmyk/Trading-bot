'''Paper-only Market Surge Aggression Mode.

Creates a controlled paper-only surge deployment plan when broad market and
speculative/risk-on context are aligned.

Guardrails:
- live_trade_authority: none
- ml_authority: shadow_only
- paper_only: true
- does_not_lower_global_thresholds: true
- does_not_bypass_hard_blocks: true

Routes:
- /paper/market-surge-aggression-status
- /paper/market-surge-plan
- /paper/surge-aggression-status
'''
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Set

VERSION = "market-surge-aggression-2026-06-08-v1-paper-only"
REGISTERED_APP_IDS: set[int] = set()

BROAD_RISK_ON_SYMBOLS = ["SPY", "QQQ", "IWM", "IWO", "ARKK", "XLK", "SMH"]
BROAD_ENTRY_PRIORITY = ["QQQ", "SPY", "IWM", "IWO", "XLK", "SMH", "ARKK"]

MAX_SURGE_POSITIONS = 6
MAX_SURGE_DEPLOYMENT_PCT = 55.0
MIN_CASH_RESERVE_PCT = 45.0
MIN_SPY_SURGE_PCT = 0.30
MIN_QQQ_SURGE_PCT = 1.00
MIN_SMALL_CAP_AVG_PCT = 0.25
MIN_SHADOW_MOVE_PCT = 5.00
MAX_DAILY_DRAWDOWN_FOR_SURGE = 1.50
MAX_INTRADAY_DRAWDOWN_FOR_SURGE = 1.50

HARD_REJECTION_TERMS = {
    "self_defense", "halt", "cooldown", "daily_loss", "risk_lock",
    "liquidity", "no_data", "spread", "hard_block",
}
SOFT_REJECTION_TERMS = {
    "market_risk_not_ok", "trend_not_confirmed",
    "relative_strength_leader_exception_block", "dynamic_discovery_block",
}


def _now(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
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


def _sym(value: Any) -> str:
    return str(value or "").upper().strip()


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


def _save_portfolio(core: Any, pf: Dict[str, Any]) -> Dict[str, Any]:
    attempted = False
    ok = False
    error = None
    try:
        save_fn = getattr(core, "save_state", None)
        if callable(save_fn):
            attempted = True
            try:
                save_fn(pf)
                ok = True
            except TypeError:
                save_fn()
                ok = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {"save_attempted": attempted, "save_ok": ok, "save_error": error}


def _positions(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    obj = pf.get("positions")
    if not isinstance(obj, dict):
        obj = state.get("positions")
    return obj if isinstance(obj, dict) else {}


def _performance(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    for src in (pf, state):
        perf = src.get("performance")
        if isinstance(perf, dict):
            return perf
    return {}


def _risk_controls(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    for src in (pf, state):
        rc = src.get("risk_controls")
        if isinstance(rc, dict):
            return rc
    return {}


def _flatten_symbols(obj: Any, max_items: int = 10000) -> Set[str]:
    out: Set[str] = set()
    count = 0

    def walk(x: Any) -> None:
        nonlocal count
        if count >= max_items:
            return
        count += 1
        if isinstance(x, dict):
            for key in ("symbol", "ticker", "asset"):
                if key in x:
                    s = _sym(x.get(key))
                    if 1 <= len(s) <= 12:
                        out.add(s)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)
        elif isinstance(x, str):
            s = _sym(x)
            if 1 <= len(s) <= 12 and s.replace(".", "").replace("-", "").isalnum():
                out.add(s)

    walk(obj)
    return out


def _watchlist_symbols(core: Any, state: Dict[str, Any]) -> Set[str]:
    symbols: Set[str] = set()
    for attr in ("WATCHLIST", "WATCHLIST_SYMBOLS", "UNIVERSE", "SCAN_UNIVERSE", "TRADING_UNIVERSE"):
        try:
            symbols |= _flatten_symbols(getattr(core, attr, None))
        except Exception:
            pass
    for key in ("watchlist", "watchlists", "universe", "scanner_universe", "symbols"):
        symbols |= _flatten_symbols(state.get(key))
    return symbols


def _series_for_column(data: Any, column_name: str, symbol: str):
    try:
        if data is None or data.empty:
            return None
        columns = data.columns
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
                    if len(col) >= 2 and str(col[0]).lower() == column_name.lower() and _sym(col[1]) == _sym(symbol):
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


def _clean_values(series: Any) -> List[float]:
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
    symbol = _sym(symbol)
    base = {
        "symbol": symbol, "data_available": False, "price": None,
        "previous_close": None, "pct_change": None, "volume": None,
        "avg_volume": None, "volume_spike_ratio": None,
        "data_quality": {"price_ok": False, "volume_ok": False, "volume_source": "none", "volume_error": None},
        "data_error": None,
    }
    try:
        import yfinance as yf  # type: ignore
        data = yf.download(symbol, period="20d", interval="1d", progress=False, auto_adjust=False, threads=False)
        if data is None or len(data) < 2:
            base["data_error"] = "not_enough_rows"
            return base

        closes = _clean_values(_series_for_column(data, "Close", symbol))
        volumes = _clean_values(_series_for_column(data, "Volume", symbol))
        if len(closes) < 2:
            base["data_error"] = "close_values_unavailable"
            return base

        last_close = closes[-1]
        prev_close = closes[-2]
        pct_change = ((last_close - prev_close) / prev_close) * 100.0 if prev_close else 0.0

        volume = None
        avg_volume = None
        volume_spike = None
        volume_error = None
        if len(volumes) >= 2:
            volume = volumes[-1]
            prior = [v for v in volumes[:-1][-5:] if v and v > 0]
            if prior:
                avg_volume = sum(prior) / len(prior)
                volume_spike = volume / avg_volume if avg_volume else None
            else:
                volume_error = "prior_volume_average_unavailable"
        else:
            volume_error = "volume_values_unavailable"

        volume_ok = bool(volume is not None and avg_volume and volume_spike is not None)
        return {
            "symbol": symbol, "data_available": True,
            "price": round(last_close, 4), "previous_close": round(prev_close, 4),
            "pct_change": round(pct_change, 4),
            "volume": _safe_int(volume, 0) if volume is not None else None,
            "avg_volume": round(avg_volume, 2) if avg_volume is not None else None,
            "volume_spike_ratio": round(volume_spike, 4) if volume_spike is not None else None,
            "data_quality": {
                "price_ok": True, "volume_ok": volume_ok,
                "volume_source": "yfinance_daily_prior_5_rows" if volume_ok else "unavailable",
                "volume_error": volume_error,
            },
            "data_error": None,
        }
    except Exception as exc:
        base["data_error"] = f"snapshot_failed:{type(exc).__name__}"
        base["data_quality"]["volume_error"] = base["data_error"]
        return base


def _broad_market_context() -> Dict[str, Any]:
    rows = [_fetch_snapshot(symbol) for symbol in BROAD_RISK_ON_SYMBOLS]
    by_symbol = {row.get("symbol"): row for row in rows if row.get("symbol")}
    spy = _safe_float((by_symbol.get("SPY") or {}).get("pct_change"))
    qqq = _safe_float((by_symbol.get("QQQ") or {}).get("pct_change"))
    iwm = _safe_float((by_symbol.get("IWM") or {}).get("pct_change"))
    iwo = _safe_float((by_symbol.get("IWO") or {}).get("pct_change"))
    arkk = _safe_float((by_symbol.get("ARKK") or {}).get("pct_change"))

    small_cap_avg = round((iwm + iwo + arkk) / 3.0, 4)
    positive_count = sum(1 for row in rows if _safe_float(row.get("pct_change"), -999) > 0)
    volume_ok_count = sum(1 for row in rows if (row.get("data_quality") or {}).get("volume_ok"))

    surge_score = 0
    reasons: List[str] = []
    if spy >= MIN_SPY_SURGE_PCT:
        surge_score += 1
        reasons.append("SPY above surge threshold")
    if qqq >= MIN_QQQ_SURGE_PCT:
        surge_score += 2
        reasons.append("QQQ above surge threshold")
    if small_cap_avg >= MIN_SMALL_CAP_AVG_PCT:
        surge_score += 1
        reasons.append("small-cap/innovation average risk-on")
    if positive_count >= 5:
        surge_score += 1
        reasons.append("broad risk-on breadth")

    if surge_score >= 5:
        surge_level, risk_context = 3, "market_surge"
    elif surge_score >= 3:
        surge_level, risk_context = 2, "risk_on"
    elif surge_score >= 2:
        surge_level, risk_context = 1, "early_risk_on"
    else:
        surge_level, risk_context = 0, "not_surge"

    return {
        "risk_context": risk_context,
        "surge_level": surge_level,
        "surge_score": surge_score,
        "reasons": reasons,
        "spy_pct": spy,
        "qqq_pct": qqq,
        "small_cap_avg_pct": small_cap_avg,
        "positive_count": positive_count,
        "volume_ok_count": volume_ok_count,
        "rows": rows,
    }


def _call_speculative_movers(core: Any, limit: int = 40) -> Dict[str, Any]:
    try:
        import missed_mover_audit  # type: ignore
        fn = getattr(missed_mover_audit, "build_speculative_movers", None)
        if callable(fn):
            return fn(core, limit=limit, persist=True)
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}", "top_shadow_movers": []}
    return {"status": "unavailable", "error": "missed_mover_audit unavailable", "top_shadow_movers": []}


def _reason_text(row: Dict[str, Any]) -> str:
    bridge = row.get("scanner_bridge") or {}
    hits = bridge.get("decision_hits") or []
    parts = []
    for hit in hits:
        if isinstance(hit, dict):
            for key in ("reason", "status", "decision"):
                value = hit.get(key)
                if value:
                    parts.append(str(value).lower())
    if bridge.get("reason"):
        parts.append(str(bridge.get("reason")).lower())
    return ",".join(parts)


def _rejection_severity(row: Dict[str, Any]) -> str:
    text = _reason_text(row)
    if any(term in text for term in HARD_REJECTION_TERMS):
        return "hard_reject"
    if any(term in text for term in SOFT_REJECTION_TERMS):
        return "soft_reject"
    return "none"


def _max_new_entries_for_level(level: int) -> int:
    if level >= 3:
        return 3
    if level == 2:
        return 2
    if level == 1:
        return 1
    return 0


def _build_broad_candidates(market_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows_by_symbol = {row.get("symbol"): row for row in market_context.get("rows", []) if row.get("symbol")}
    candidates: List[Dict[str, Any]] = []
    for rank, symbol in enumerate(BROAD_ENTRY_PRIORITY, start=1):
        snap = rows_by_symbol.get(symbol) or _fetch_snapshot(symbol)
        pct = _safe_float(snap.get("pct_change"))
        if pct <= 0 or not snap.get("data_available"):
            continue
        candidates.append({
            "symbol": symbol,
            "source": "broad_market_surge",
            "tier": "tier_1_broad_risk_on",
            "rank": rank,
            "pct_change": pct,
            "volume_ok": bool((snap.get("data_quality") or {}).get("volume_ok")),
            "volume_spike_ratio": snap.get("volume_spike_ratio"),
            "core_scanner_status": "broad_market_proxy",
            "eligible_for_paper_surge": True,
            "allocation_hint_pct_of_equity": 8.0 if symbol in {"QQQ", "SPY"} else 5.0,
            "starter_size_factor": 0.35 if symbol in {"QQQ", "SPY"} else 0.25,
            "reason": "Broad risk-on proxy during market surge.",
            "snapshot": snap,
            "trade_authority": "paper_only_queue",
            "ml_authority": "shadow_only",
        })
    return candidates


def _build_shadow_candidates(spec: Dict[str, Any], surge_level: int) -> List[Dict[str, Any]]:
    rows = spec.get("top_shadow_movers")
    rows = rows if isinstance(rows, list) else []
    out: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = _sym(row.get("symbol"))
        bridge = row.get("scanner_bridge") if isinstance(row.get("scanner_bridge"), dict) else {}
        snap = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
        tags = row.get("tags") if isinstance(row.get("tags"), dict) else {}

        core_status = bridge.get("core_scanner_status")
        pct = _safe_float(snap.get("pct_change"))
        volume_ok = bool((snap.get("data_quality") or {}).get("volume_ok"))
        rejected = bool(bridge.get("rejected_symbol"))
        blocked = bool(bridge.get("blocked_symbol"))
        severity = _rejection_severity(row)

        if blocked or severity == "hard_reject":
            eligible, tier, reason = False, "excluded", "Blocked/hard-rejected; surge mode cannot bypass hard controls."
        elif core_status in {"seen_not_selected", "ignored_watchlist_not_triggered"} and pct >= MIN_SHADOW_MOVE_PCT and volume_ok:
            eligible, tier, reason = True, "tier_2_shadow_bridge", "Shadow mover is risk-on, volume data valid, and not hard rejected."
        elif rejected and severity == "soft_reject" and surge_level >= 3 and pct >= MIN_SHADOW_MOVE_PCT and volume_ok:
            eligible, tier, reason = True, "tier_3_soft_reject_surge_review", "Soft-rejected only; allowed for smaller paper review in strongest surge."
        else:
            eligible, tier, reason = False, "watch_only", "Observation only; did not clear surge bridge conditions."

        out.append({
            "symbol": symbol,
            "source": "shadow_speculative_momentum",
            "tier": tier,
            "pct_change": pct,
            "volume_ok": volume_ok,
            "volume_spike_ratio": snap.get("volume_spike_ratio"),
            "core_scanner_status": core_status,
            "rejection_severity": severity,
            "eligible_for_paper_surge": eligible,
            "allocation_hint_pct_of_equity": 3.5 if tier == "tier_2_shadow_bridge" else 2.0,
            "starter_size_factor": 0.18 if tier == "tier_2_shadow_bridge" else 0.10,
            "reason": reason,
            "snapshot": snap,
            "scanner_bridge": bridge,
            "tags": tags,
            "trade_authority": "paper_only_queue" if eligible else "none",
            "ml_authority": "shadow_only",
        })

    out.sort(key=lambda item: (item.get("eligible_for_paper_surge", False), item.get("pct_change", 0.0)), reverse=True)
    return out


def build_market_surge_plan(core: Any = None, persist: bool = True) -> Dict[str, Any]:
    state = _state(core)
    pf = _portfolio(core)
    positions = _positions(pf, state)
    perf = _performance(pf, state)
    risk = _risk_controls(pf, state)

    equity = _safe_float(pf.get("equity", state.get("equity", 0.0)))
    cash = _safe_float(pf.get("cash", state.get("cash", 0.0)))
    cash_pct = round((cash / equity * 100.0), 4) if equity else 0.0

    realized_today = _safe_float(perf.get("realized_pnl_today", pf.get("realized_today", 0.0)))
    losses_today = _safe_int(perf.get("losses_today", 0))
    wins_today = _safe_int(perf.get("wins_today", 0))
    self_defense = bool(risk.get("self_defense_active", False))
    daily_dd = _safe_float(risk.get("daily_loss_pct", risk.get("daily_drawdown_pct", 0.0)))
    intraday_dd = _safe_float(risk.get("intraday_drawdown_pct", 0.0))

    market_context = _broad_market_context()
    surge_level = int(market_context.get("surge_level", 0) or 0)
    spec = _call_speculative_movers(core, limit=40)
    shadow_rows = spec.get("top_shadow_movers") if isinstance(spec.get("top_shadow_movers"), list) else []
    move_count = sum(
        1 for row in shadow_rows
        if isinstance(row, dict) and _safe_float((row.get("snapshot") or {}).get("pct_change")) >= MIN_SHADOW_MOVE_PCT
    )

    clean_risk = (
        not self_defense
        and daily_dd <= MAX_DAILY_DRAWDOWN_FOR_SURGE
        and intraday_dd <= MAX_INTRADAY_DRAWDOWN_FOR_SURGE
        and realized_today >= 0
    )

    eligible_mode = bool(surge_level >= 2 and clean_risk and cash_pct >= 35.0 and move_count >= 2)
    override_losses_today_not_clean = bool(eligible_mode and losses_today > 0 and realized_today >= 0 and not self_defense)

    broad_candidates = _build_broad_candidates(market_context)
    shadow_candidates = _build_shadow_candidates(spec, surge_level)

    eligible_broad = [c for c in broad_candidates if c.get("eligible_for_paper_surge")]
    eligible_shadow = [c for c in shadow_candidates if c.get("eligible_for_paper_surge")]
    max_new_entries = _max_new_entries_for_level(surge_level) if eligible_mode else 0
    available_slots = max(0, MAX_SURGE_POSITIONS - len(positions))
    planned_count = min(max_new_entries, available_slots)

    ordered = []
    ordered.extend(eligible_broad[:2])
    ordered.extend(eligible_shadow)

    seen = set()
    deduped = []
    for candidate in ordered:
        symbol = _sym(candidate.get("symbol"))
        if symbol and symbol not in seen:
            seen.add(symbol)
            deduped.append(candidate)

    proposed_entries = deduped[:planned_count] if eligible_mode else []

    total_alloc = sum(_safe_float(e.get("allocation_hint_pct_of_equity")) for e in proposed_entries)
    if total_alloc > MAX_SURGE_DEPLOYMENT_PCT:
        scale = MAX_SURGE_DEPLOYMENT_PCT / total_alloc
        for entry in proposed_entries:
            entry["allocation_hint_pct_of_equity"] = round(_safe_float(entry.get("allocation_hint_pct_of_equity")) * scale, 4)

    status = {
        "status": "ok",
        "overall": "pass",
        "type": "market_surge_aggression_status",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": False,
        "trade_authority": "paper_only_queue",
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
        "eligible_mode": eligible_mode,
        "surge_level": surge_level,
        "market_context": market_context,
        "risk_context": {
            "clean_risk": clean_risk,
            "self_defense_active": self_defense,
            "daily_drawdown_pct": daily_dd,
            "intraday_drawdown_pct": intraday_dd,
            "realized_today": round(realized_today, 4),
            "wins_today": wins_today,
            "losses_today": losses_today,
            "override_losses_today_not_clean": override_losses_today_not_clean,
            "cash_pct": cash_pct,
            "open_positions": len(positions),
        },
        "deployment_policy": {
            "max_surge_positions": MAX_SURGE_POSITIONS,
            "target_open_positions_when_active": min(MAX_SURGE_POSITIONS, max(3, planned_count + len(positions))),
            "max_new_entries_this_cycle": max_new_entries,
            "planned_new_entries": len(proposed_entries),
            "max_surge_deployment_pct": MAX_SURGE_DEPLOYMENT_PCT,
            "min_cash_reserve_pct": MIN_CASH_RESERVE_PCT,
            "does_not_lower_global_thresholds": True,
            "does_not_change_ml_authority": True,
            "does_not_bypass_hard_blocks": True,
            "paper_only": True,
        },
        "surge_evidence": {
            "shadow_move_count": move_count,
            "speculative_status": spec.get("status"),
            "speculative_version": spec.get("version"),
            "persistence": spec.get("persistence"),
        },
        "proposed_entries": proposed_entries,
        "eligible_broad_candidates": eligible_broad,
        "eligible_shadow_candidates": eligible_shadow[:15],
        "watch_only_shadow_candidates": [c for c in shadow_candidates if not c.get("eligible_for_paper_surge")][:15],
        "next_actions": [
            "Allow the entry router to consume proposed_entries only in paper mode.",
            "Do not lower global thresholds.",
            "Keep ML shadow-only.",
            "Disable surge mode immediately if self-defense activates or realized_today turns negative.",
        ],
        "warnings": [],
    }

    if not eligible_mode:
        status["warnings"].append("Surge aggression mode not active; conditions did not fully clear.")
    if eligible_mode and not proposed_entries:
        status["warnings"].append("Surge mode active but no eligible proposed entries after filters.")

    if persist:
        try:
            pf["market_surge_aggression"] = status
            pf["paper_surge_candidate_queue"] = proposed_entries
            save_result = _save_portfolio(core, pf)
            status["persistence"] = {
                "persisted": True,
                "target": "portfolio.paper_surge_candidate_queue",
                "rows_added": len(proposed_entries),
                **save_result,
            }
        except Exception as exc:
            status["persistence"] = {
                "persisted": False,
                "rows_added": 0,
                "save_attempted": False,
                "save_ok": False,
                "save_error": f"{type(exc).__name__}: {exc}",
            }

    return status


def apply(core: Any = None) -> Dict[str, Any]:
    return build_market_surge_plan(core, persist=True)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    from flask import jsonify, request

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        persist_arg = str(request.args.get("persist", "1")).lower()
        persist = persist_arg not in {"0", "false", "no"}
        return jsonify(build_market_surge_plan(core, persist=persist))

    for route, endpoint in (
        ("/paper/market-surge-aggression-status", "market_surge_aggression_status"),
        ("/paper/market-surge-plan", "market_surge_plan"),
        ("/paper/surge-aggression-status", "surge_aggression_status"),
    ):
        if route not in existing:
            flask_app.add_url_rule(route, endpoint, status_route)

    REGISTERED_APP_IDS.add(id(flask_app))
