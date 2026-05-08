"""Early ML shadow-route registration for the trading bot.

This file is imported by Python automatically as sitecustomize when available.
It patches Flask.__init__ so ML endpoints are registered immediately when
app = Flask(__name__) is created. The route handlers resolve app.py functions
lazily at request time, so they work even when the bot starts as python app.py
and the live module is __main__.

Shadow mode only: no live trade decisions are made here.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import threading
import time
import datetime as dt

VERSION = "ml-shadow-early-routes-2026-05-07"
ENABLED = os.environ.get("ML_SHADOW_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MAX_ROWS = int(os.environ.get("ML_SHADOW_MAX_ROWS", "3000"))
MIN_ROWS = int(os.environ.get("ML_SHADOW_MIN_ROWS_FOR_SIGNAL", "100"))
_REGISTERED_APP_IDS: set[int] = set()
_PATCHED_SAVE_IDS: set[int] = set()
_PATCHING_SAVE = False


def _fnum(x, d=0.0):
    try:
        x = float(x)
        return d if math.isnan(x) or math.isinf(x) else x
    except Exception:
        return d


def _h(obj) -> str:
    try:
        raw = json.dumps(obj, sort_keys=True, default=str)
    except Exception:
        raw = str(obj)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _mod():
    # When Railway starts with python app.py, the bot is usually __main__.
    # When started by gunicorn/import, the bot is usually app.
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None:
            return m
    return None


def _now_text(m=None):
    try:
        return m.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(m=None):
    try:
        return m.today_key()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _nested(d, keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur.get(k)
    return cur


def _ensure_ml(state):
    if not isinstance(state, dict):
        state = {}
    ml = state.setdefault("ml_shadow", {})
    ml["version"] = VERSION
    ml["enabled"] = ENABLED
    ml["live_trade_decider"] = False
    ml.setdefault("feature_log", [])
    ml.setdefault("notes", ["ML is shadow-only; rules and risk controls remain live authority."])
    return ml


def _candidate_items(state):
    out = []
    scan = state.get("scanner_audit") or state.get("scanner_log") or {}
    if isinstance(scan, dict):
        for key, decision in (("accepted_entries", "accepted"), ("blocked_entries", "blocked"), ("rejected_signals", "rejected")):
            for item in scan.get(key) or []:
                if isinstance(item, dict):
                    out.append((item, decision))
        seen = {(str(i.get("symbol") or "").upper(), d) for i, d in out}
        for sym in scan.get("long_signals") or []:
            if isinstance(sym, str) and (sym.upper(), "signal") not in seen:
                out.append(({"symbol": sym, "side": "long"}, "signal"))
        for sym in scan.get("short_signals") or []:
            if isinstance(sym, str) and (sym.upper(), "signal") not in seen:
                out.append(({"symbol": sym, "side": "short"}, "signal"))
    if out:
        return out
    lr = _nested(state, ["auto_runner", "last_result"], {}) or {}
    if isinstance(lr, dict):
        for key, decision in (("entries", "accepted"), ("blocked_entries", "blocked"), ("rejected_signals", "rejected")):
            for item in lr.get(key) or []:
                if isinstance(item, dict):
                    out.append((item, decision))
        seen_syms = {str(i.get("symbol") or "").upper() for i, _ in out}
        for sym in lr.get("long_signals") or []:
            if isinstance(sym, str) and sym.upper() not in seen_syms:
                out.append(({"symbol": sym, "side": "long"}, "signal"))
        for sym in lr.get("short_signals") or []:
            if isinstance(sym, str) and sym.upper() not in seen_syms:
                out.append(({"symbol": sym, "side": "short"}, "signal"))
    return out


def _entry_floor(state):
    return _fnum(
        _nested(state, ["feedback_loop", "dynamic_min_long_score"], None),
        _fnum(_nested(state, ["explain", "current_permission", "active_min_entry_score"], None), 0.0),
    )


def _feature_row(item, decision, state, m=None):
    sym = str(item.get("symbol") or item.get("ticker") or "").upper()
    market = state.get("last_market") or _nested(state, ["auto_runner", "last_result"], {}) or {}
    feedback = state.get("feedback_loop") or {}
    risk = state.get("risk_controls") or {}
    perf = state.get("performance") or {}
    tech = market.get("tech_leadership") or feedback.get("tech_leadership") or {}
    precious = market.get("precious_metals") or feedback.get("precious_metals") or state.get("precious_metals") or {}
    breadth = market.get("breadth") or feedback.get("breadth") or state.get("breadth") or {}
    futures = market.get("futures_bias") or feedback.get("futures_bias") or state.get("futures_bias") or {}
    bucket_map = getattr(m, "SYMBOL_BUCKET", {}) if m is not None else {}
    sector_map = getattr(m, "SYMBOL_SECTOR", {}) if m is not None else {}
    score = _fnum(item.get("score"), _fnum(_nested(item, ["quality_info", "score"], None), 0.0))
    row = {
        "logged_local": _now_text(m),
        "date": _today(m),
        "symbol": sym,
        "side": item.get("side") or item.get("direction") or "long",
        "bucket": item.get("bucket") or bucket_map.get(sym, "unknown"),
        "sector": item.get("sector") or sector_map.get(sym, "unknown"),
        "score": round(score, 6),
        "decision": decision,
        "reason": item.get("reason") or item.get("entry_block_reason") or _nested(item, ["quality_info", "reason"], ""),
        "market_mode": market.get("market_mode") or state.get("market_mode"),
        "regime": market.get("regime") or state.get("regime"),
        "risk_score": _fnum(market.get("risk_score"), _fnum(state.get("risk_score"), 0.0)),
        "spy_5d_pct": _fnum(market.get("spy_5d_pct"), 0.0),
        "qqq_5d_pct": _fnum(market.get("qqq_5d_pct"), 0.0),
        "vix_5d_pct": _fnum(market.get("vix_5d_pct"), 0.0),
        "rates_5d_pct": _fnum(market.get("rates_5d_pct"), 0.0),
        "futures_action": futures.get("action") or "",
        "futures_bias": futures.get("bias") or futures.get("action") or "",
        "breadth_state": breadth.get("state") or "",
        "breadth_action": breadth.get("action") or "",
        "tech_leadership_active": bool(tech.get("active", False)),
        "tech_leadership_state": tech.get("state") or "",
        "precious_metals_state": precious.get("state") or "",
        "precious_metals_action": precious.get("action") or "",
        "entry_floor": round(_entry_floor(state), 6),
        "cash": round(_fnum(state.get("cash"), 0.0), 2),
        "equity": round(_fnum(state.get("equity"), 0.0), 2),
        "realized_pnl_today": round(_fnum(perf.get("realized_pnl_today"), 0.0), 2),
        "daily_loss_pct": round(_fnum(risk.get("daily_loss_pct"), 0.0), 4),
        "intraday_drawdown_pct": round(_fnum(risk.get("intraday_drawdown_pct"), 0.0), 4),
        "self_defense_active": bool(risk.get("self_defense_active") or feedback.get("self_defense_mode")),
        "future_outcome_pending": True,
        "future_return_close_pct": None,
        "future_return_next_day_pct": None,
        "source_hash": _h(item),
    }
    row["row_id"] = _h({"d": row["date"], "s": sym, "side": row["side"], "decision": decision, "score": row["score"], "reason": row["reason"], "src": row["source_hash"]})
    return row


def _batch_key(state):
    items = _candidate_items(state)
    if not items:
        return ""
    scan = state.get("scanner_audit") or state.get("scanner_log") or {}
    return _h({"updated": scan.get("last_updated_local") if isinstance(scan, dict) else None, "last_run": _nested(state, ["auto_runner", "last_run_local"], None), "items": items})


def _append_features(state, m=None):
    if not ENABLED or not isinstance(state, dict):
        return state
    ml = _ensure_ml(state)
    key = _batch_key(state)
    if not key or key == ml.get("last_candidate_batch_key"):
        ml["last_review"] = _review(state, m)
        return state
    ids = {r.get("row_id") for r in ml.get("feature_log", []) if isinstance(r, dict)}
    new_rows = []
    for item, decision in _candidate_items(state):
        row = _feature_row(item, decision, state, m)
        if row["row_id"] not in ids:
            ids.add(row["row_id"])
            new_rows.append(row)
    if new_rows:
        ml["feature_log"] = (ml.get("feature_log", []) + new_rows)[-MAX_ROWS:]
        ml["last_candidate_batch_key"] = key
        ml["last_updated_local"] = _now_text(m)
        ml["last_added_rows"] = len(new_rows)
        ml["total_rows"] = len(ml["feature_log"])
    ml["last_review"] = _review(state, m)
    return state


def _group(rows, field):
    out = {}
    for r in rows:
        k = str(r.get(field) or "unknown")
        g = out.setdefault(k, {"total": 0, "accepted": 0, "blocked": 0, "rejected": 0, "signal": 0, "avg_score": 0.0})
        g["total"] += 1
        dec = r.get("decision", "unknown")
        g[dec] = g.get(dec, 0) + 1
        g["avg_score"] += _fnum(r.get("score"), 0.0)
    for g in out.values():
        if g["total"]:
            g["avg_score"] = round(g["avg_score"] / g["total"], 6)
    return out


def _prob(row, total):
    p = 0.50 + max(min((_fnum(row.get("score")) - _fnum(row.get("entry_floor"), 0.012)) * 8, 0.12), -0.12)
    if row.get("tech_leadership_active") and row.get("sector") in {"XLK", "XLY"}:
        p += 0.035
    if row.get("bucket") == "precious_metals" and row.get("precious_metals_state") in {"safe_haven_bid", "trend_confirmed"}:
        p += 0.035
    if row.get("futures_action") in {"gap_chase_protection", "bearish_caution", "risk_off"}:
        p -= 0.025
    if row.get("self_defense_active"):
        p -= 0.08
    confidence = "low_data" if total < MIN_ROWS else "developing" if total < MIN_ROWS * 3 else "usable_shadow"
    if confidence == "low_data":
        p = 0.50 + (p - 0.50) * 0.35
    elif confidence == "developing":
        p = 0.50 + (p - 0.50) * 0.65
    p = max(0.05, min(0.95, p))
    return {
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "bucket": row.get("bucket"),
        "sector": row.get("sector"),
        "rule_score": row.get("score"),
        "entry_floor": row.get("entry_floor"),
        "decision_seen": row.get("decision"),
        "ml_shadow_probability": round(p, 4),
        "confidence": confidence,
        "shadow_action": "rank_higher" if p >= 0.58 else "rank_lower" if p <= 0.45 else "neutral",
    }


def _review(state, m=None):
    rows = [r for r in _ensure_ml(state).get("feature_log", []) if isinstance(r, dict)]
    total = len(rows)
    preds = sorted([_prob(r, total) for r in rows[-25:]], key=lambda x: x["ml_shadow_probability"], reverse=True)
    return {
        "version": VERSION,
        "enabled": ENABLED,
        "live_trade_decider": False,
        "rows_logged": total,
        "accepted_rows": sum(r.get("decision") == "accepted" for r in rows),
        "blocked_rows": sum(r.get("decision") == "blocked" for r in rows),
        "rejected_rows": sum(r.get("decision") == "rejected" for r in rows),
        "pending_outcome_rows": sum(bool(r.get("future_outcome_pending")) for r in rows),
        "bucket_summary": _group(rows, "bucket"),
        "sector_summary": _group(rows, "sector"),
        "latest_shadow_rankings": preds[:15],
        "readiness": {
            "ml_ready_for_live_decisions": False,
            "reason": "shadow data capture active; live ML requires enough rows plus walk-forward/backtest evidence",
            "recommended_next_threshold": "100+ logged scanner opportunities and 2-4 weeks of paper data before ML affects entries",
        },
        "last_updated_local": _now_text(m),
    }


def _load_state():
    m = _mod()
    try:
        state = m.load_state() if m is not None and hasattr(m, "load_state") else {}
    except Exception:
        state = {}
    if not isinstance(state, dict):
        state = {}
    try:
        _append_features(state, m)
    except Exception as e:
        state.setdefault("ml_shadow", {})["last_error"] = str(e)
    return state, m


def _patch_save_state(m):
    global _PATCHING_SAVE
    if m is None or not hasattr(m, "save_state") or id(m) in _PATCHED_SAVE_IDS:
        return False
    original = m.save_state

    def patched_save_state(state):
        global _PATCHING_SAVE
        if _PATCHING_SAVE:
            return original(state)
        try:
            _PATCHING_SAVE = True
            _append_features(state, m)
        finally:
            _PATCHING_SAVE = False
        return original(state)

    patched_save_state._ml_shadow_patched = True
    m.save_state = patched_save_state
    _PATCHED_SAVE_IDS.add(id(m))
    return True


def _register_routes(flask_app):
    if id(flask_app) in _REGISTERED_APP_IDS:
        return
    try:
        existing = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    from flask import jsonify, request

    if "/paper/ml-health" not in existing:
        def ml_health():
            state, m = _load_state()
            ml = _ensure_ml(state)
            _patch_save_state(m)
            return jsonify({
                "status": "ok",
                "version": VERSION,
                "enabled": ENABLED,
                "registered_by": "sitecustomize_flask_init_patch",
                "live_trade_decider": False,
                "rows_logged": len(ml.get("feature_log", [])),
                "state_persistence_mode": getattr(m, "STATE_PERSISTENCE_MODE", None) if m else None,
                "state_file": getattr(m, "STATE_FILE", None) if m else None,
            })
        flask_app.add_url_rule("/paper/ml-health", "ml_health_shadow", ml_health)

    if "/paper/ml-review" not in existing:
        def ml_review():
            state, m = _load_state()
            _patch_save_state(m)
            return jsonify({"status": "ok", "ml_review": _review(state, m)})
        flask_app.add_url_rule("/paper/ml-review", "ml_review_shadow", ml_review)

    if "/paper/ml-shadow" not in existing:
        def ml_shadow():
            state, m = _load_state()
            _patch_save_state(m)
            r = _review(state, m)
            return jsonify({
                "status": "ok",
                "mode": "shadow_only",
                "live_trade_decider": False,
                "latest_shadow_rankings": r.get("latest_shadow_rankings", []),
                "readiness": r.get("readiness", {}),
                "plain_english": ["ML shadow mode logs and ranks scanner patterns only.", "It cannot place trades or override risk controls."],
            })
        flask_app.add_url_rule("/paper/ml-shadow", "ml_shadow_shadow", ml_shadow)

    if "/paper/ml-dataset" not in existing:
        def ml_dataset():
            state, m = _load_state()
            _patch_save_state(m)
            ml = _ensure_ml(state)
            try:
                limit = int(request.args.get("limit", "250"))
            except Exception:
                limit = 250
            limit = max(1, min(limit, 1000))
            rows = ml.get("feature_log", [])
            return jsonify({"status": "ok", "version": VERSION, "rows_logged": len(rows), "rows_returned": min(limit, len(rows)), "feature_log_tail": rows[-limit:]})
        flask_app.add_url_rule("/paper/ml-dataset", "ml_dataset_shadow", ml_dataset)

    if "/paper/ml-feature-log" not in existing:
        def ml_feature_log():
            state, m = _load_state()
            _patch_save_state(m)
            ml = _ensure_ml(state)
            rows = ml.get("feature_log", [])
            return jsonify({"status": "ok", "version": VERSION, "rows_logged": len(rows), "last_updated_local": ml.get("last_updated_local"), "last_added_rows": ml.get("last_added_rows", 0), "latest_rows": rows[-50:]})
        flask_app.add_url_rule("/paper/ml-feature-log", "ml_feature_log_shadow", ml_feature_log)

    if "/paper/backtest-summary" not in existing:
        def backtest_summary():
            state, m = _load_state()
            _patch_save_state(m)
            trades = state.get("trades", [])
            realized = state.get("realized_pnl", {})
            risk = state.get("risk_controls", {})
            return jsonify({
                "status": "ok",
                "version": VERSION,
                "type": "paper_replay_backtest_readiness",
                "note": "Full walk-forward simulation comes after enough ML feature rows are collected.",
                "rule_system_snapshot": {
                    "trades_logged": len(trades),
                    "realized_pnl_today": _fnum(realized.get("today")),
                    "realized_pnl_total": _fnum(realized.get("total")),
                    "wins_total": int(_fnum(realized.get("wins_total"), 0)),
                    "losses_total": int(_fnum(realized.get("losses_total"), 0)),
                    "intraday_drawdown_pct": _fnum(risk.get("intraday_drawdown_pct")),
                    "daily_loss_pct": _fnum(risk.get("daily_loss_pct")),
                },
                "ml_shadow_snapshot": _review(state, m),
                "recommended_next_step": "Collect scanner rows during regular sessions, then compare rules vs ML ranking on profit factor, stop-loss rate, and missed-winner rate.",
            })
        flask_app.add_url_rule("/paper/backtest-summary", "backtest_summary_shadow", backtest_summary)

    _REGISTERED_APP_IDS.add(id(flask_app))


def _watchdog():
    for _ in range(300):
        try:
            m = _mod()
            if m is not None:
                flask_app = getattr(m, "app", None)
                if flask_app is not None:
                    _register_routes(flask_app)
                _patch_save_state(m)
        except Exception:
            pass
        time.sleep(0.1)


if ENABLED:
    try:
        from flask import Flask
        if not getattr(Flask.__init__, "_ml_shadow_init_patched", False):
            _original_init = Flask.__init__

            def _patched_init(self, *args, **kwargs):
                _original_init(self, *args, **kwargs)
                try:
                    _register_routes(self)
                except Exception:
                    pass

            _patched_init._ml_shadow_init_patched = True
            Flask.__init__ = _patched_init
    except Exception:
        pass
    threading.Thread(target=_watchdog, daemon=True).start()
