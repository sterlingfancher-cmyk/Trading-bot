"""ML shadow-mode add-on for the trading bot.

This file is imported automatically by Python as ``sitecustomize``. The Railway
Procfile currently starts the bot with ``python app.py``, which means the running
module is usually ``__main__`` instead of ``app``. This version supports both:
- imported module startup, e.g. gunicorn app:app
- script startup, e.g. python app.py

The add-on is shadow-only. It logs scanner features and exposes review endpoints,
but it never places trades or overrides risk controls.
"""
from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import json
import math
import os
import sys
import threading
import time
import datetime as dt

VERSION = "ml-shadow-2026-05-07b"
ENABLED = os.environ.get("ML_SHADOW_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MAX_ROWS = int(os.environ.get("ML_SHADOW_MAX_ROWS", "3000"))
MIN_ROWS = int(os.environ.get("ML_SHADOW_MIN_ROWS_FOR_SIGNAL", "100"))
_PATCHING = False
_INSTALLED_MODULE_IDS: set[int] = set()


def fnum(x, d=0.0):
    try:
        x = float(x)
        return d if math.isnan(x) or math.isinf(x) else x
    except Exception:
        return d


def fint(x, d=0):
    try:
        return int(x)
    except Exception:
        return d


def h(obj) -> str:
    try:
        raw = json.dumps(obj, sort_keys=True, default=str)
    except Exception:
        raw = str(obj)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def nested(d, keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur.get(k)
    return cur


def now_text(appmod=None):
    try:
        return appmod.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today(appmod=None):
    try:
        return appmod.today_key()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def bucket(sym, appmod=None):
    try:
        return getattr(appmod, "SYMBOL_BUCKET", {}).get((sym or "").upper(), "unknown")
    except Exception:
        return "unknown"


def sector(sym, appmod=None):
    try:
        return getattr(appmod, "SYMBOL_SECTOR", {}).get((sym or "").upper(), "unknown")
    except Exception:
        return "unknown"


def candidate_items(state):
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

    lr = nested(state, ["auto_runner", "last_result"], {}) or {}
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


def entry_floor(state):
    return fnum(
        nested(state, ["feedback_loop", "dynamic_min_long_score"], None),
        fnum(nested(state, ["explain", "current_permission", "active_min_entry_score"], None), 0.0),
    )


def feature_row(item, decision, state, appmod=None):
    sym = str(item.get("symbol") or item.get("ticker") or "").upper()
    market = state.get("last_market") or nested(state, ["auto_runner", "last_result"], {}) or {}
    feedback = state.get("feedback_loop") or {}
    risk = state.get("risk_controls") or {}
    perf = state.get("performance") or {}
    tech = market.get("tech_leadership") or feedback.get("tech_leadership") or {}
    precious = market.get("precious_metals") or feedback.get("precious_metals") or state.get("precious_metals") or {}
    breadth = market.get("breadth") or feedback.get("breadth") or state.get("breadth") or {}
    futures = market.get("futures_bias") or feedback.get("futures_bias") or state.get("futures_bias") or {}
    score = fnum(item.get("score"), fnum(nested(item, ["quality_info", "score"], None), 0.0))
    row = {
        "logged_local": now_text(appmod),
        "date": today(appmod),
        "symbol": sym,
        "side": item.get("side") or item.get("direction") or "long",
        "bucket": item.get("bucket") or bucket(sym, appmod),
        "sector": item.get("sector") or sector(sym, appmod),
        "score": round(score, 6),
        "decision": decision,
        "reason": item.get("reason") or item.get("entry_block_reason") or nested(item, ["quality_info", "reason"], ""),
        "market_mode": market.get("market_mode") or state.get("market_mode"),
        "regime": market.get("regime") or state.get("regime"),
        "risk_score": fnum(market.get("risk_score"), fnum(state.get("risk_score"), 0.0)),
        "spy_5d_pct": fnum(market.get("spy_5d_pct"), 0.0),
        "qqq_5d_pct": fnum(market.get("qqq_5d_pct"), 0.0),
        "vix_5d_pct": fnum(market.get("vix_5d_pct"), 0.0),
        "rates_5d_pct": fnum(market.get("rates_5d_pct"), 0.0),
        "futures_action": futures.get("action") or "",
        "futures_bias": futures.get("bias") or futures.get("action") or "",
        "breadth_state": breadth.get("state") or "",
        "breadth_action": breadth.get("action") or "",
        "tech_leadership_active": bool(tech.get("active", False)),
        "tech_leadership_state": tech.get("state") or "",
        "precious_metals_state": precious.get("state") or "",
        "precious_metals_action": precious.get("action") or "",
        "entry_floor": round(entry_floor(state), 6),
        "cash": round(fnum(state.get("cash"), 0.0), 2),
        "equity": round(fnum(state.get("equity"), 0.0), 2),
        "realized_pnl_today": round(fnum(perf.get("realized_pnl_today"), 0.0), 2),
        "daily_loss_pct": round(fnum(risk.get("daily_loss_pct"), 0.0), 4),
        "intraday_drawdown_pct": round(fnum(risk.get("intraday_drawdown_pct"), 0.0), 4),
        "self_defense_active": bool(risk.get("self_defense_active") or feedback.get("self_defense_mode")),
        "future_outcome_pending": True,
        "future_return_close_pct": None,
        "future_return_next_day_pct": None,
        "source_hash": h(item),
    }
    row["row_id"] = h({"d": row["date"], "s": sym, "side": row["side"], "decision": decision, "score": row["score"], "reason": row["reason"], "src": row["source_hash"]})
    return row


def ensure_ml(state):
    ml = state.setdefault("ml_shadow", {})
    ml.setdefault("version", VERSION)
    ml["enabled"] = ENABLED
    ml["live_trade_decider"] = False
    ml.setdefault("feature_log", [])
    ml.setdefault("notes", ["ML is shadow-only; rules and risk controls remain live authority."])
    return ml


def batch_key(state):
    items = candidate_items(state)
    if not items:
        return ""
    scan = state.get("scanner_audit") or state.get("scanner_log") or {}
    return h({"updated": scan.get("last_updated_local") if isinstance(scan, dict) else None, "last_run": nested(state, ["auto_runner", "last_run_local"], None), "items": items})


def group(rows, field):
    out = {}
    for r in rows:
        k = str(r.get(field) or "unknown")
        g = out.setdefault(k, {"total": 0, "accepted": 0, "blocked": 0, "rejected": 0, "signal": 0, "avg_score": 0.0})
        g["total"] += 1
        dec = r.get("decision", "unknown")
        g[dec] = g.get(dec, 0) + 1
        g["avg_score"] += fnum(r.get("score"), 0.0)
    for g in out.values():
        if g["total"]:
            g["avg_score"] = round(g["avg_score"] / g["total"], 6)
    return out


def prob(row, total):
    p = 0.50 + max(min((fnum(row.get("score")) - fnum(row.get("entry_floor"), 0.012)) * 8, 0.12), -0.12)
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


def review(state, appmod=None):
    rows = [r for r in ensure_ml(state).get("feature_log", []) if isinstance(r, dict)]
    total = len(rows)
    preds = sorted([prob(r, total) for r in rows[-25:]], key=lambda x: x["ml_shadow_probability"], reverse=True)
    return {
        "version": VERSION,
        "enabled": ENABLED,
        "live_trade_decider": False,
        "rows_logged": total,
        "accepted_rows": sum(r.get("decision") == "accepted" for r in rows),
        "blocked_rows": sum(r.get("decision") == "blocked" for r in rows),
        "rejected_rows": sum(r.get("decision") == "rejected" for r in rows),
        "pending_outcome_rows": sum(bool(r.get("future_outcome_pending")) for r in rows),
        "bucket_summary": group(rows, "bucket"),
        "sector_summary": group(rows, "sector"),
        "latest_shadow_rankings": preds[:15],
        "readiness": {
            "ml_ready_for_live_decisions": False,
            "reason": "shadow data capture active; live ML requires enough rows plus walk-forward/backtest evidence",
            "recommended_next_threshold": "100+ logged scanner opportunities and 2-4 weeks of paper data before ML affects entries",
        },
        "last_updated_local": now_text(appmod),
    }


def append_features(state, appmod=None):
    if not ENABLED or not isinstance(state, dict):
        return state
    ml = ensure_ml(state)
    key = batch_key(state)
    if not key or key == ml.get("last_candidate_batch_key"):
        ml["last_review"] = review(state, appmod)
        return state
    ids = {r.get("row_id") for r in ml.get("feature_log", []) if isinstance(r, dict)}
    new_rows = []
    for item, decision in candidate_items(state):
        row = feature_row(item, decision, state, appmod)
        if row["row_id"] not in ids:
            ids.add(row["row_id"])
            new_rows.append(row)
    if new_rows:
        ml["feature_log"] = (ml.get("feature_log", []) + new_rows)[-MAX_ROWS:]
        ml["last_candidate_batch_key"] = key
        ml["last_updated_local"] = now_text(appmod)
        ml["last_added_rows"] = len(new_rows)
        ml["total_rows"] = len(ml["feature_log"])
    ml["last_review"] = review(state, appmod)
    return state


def load_state(appmod):
    try:
        state = appmod.load_state()
        if isinstance(state, dict):
            append_features(state, appmod)
            return state
    except Exception:
        pass
    return {}


def patch_save(appmod):
    global _PATCHING
    if not hasattr(appmod, "save_state") or getattr(appmod.save_state, "_ml_shadow_patched", False):
        return False
    original = appmod.save_state

    def patched(state):
        global _PATCHING
        if _PATCHING:
            return original(state)
        try:
            _PATCHING = True
            append_features(state, appmod)
        finally:
            _PATCHING = False
        return original(state)

    patched._ml_shadow_patched = True
    appmod.save_state = patched
    return True


def install_routes(appmod):
    flask_app = getattr(appmod, "app", None)
    if flask_app is None:
        return False
    rules = {getattr(r, "rule", "") for r in flask_app.url_map.iter_rules()}

    def js(x):
        try:
            return appmod.jsonify(x)
        except Exception:
            from flask import jsonify
            return jsonify(x)

    if "/paper/ml-health" not in rules:
        @flask_app.route("/paper/ml-health")
        def ml_health():
            state = load_state(appmod)
            ml = ensure_ml(state)
            return js({
                "status": "ok",
                "version": VERSION,
                "enabled": ENABLED,
                "startup_mode_supported": ["python app.py", "gunicorn app:app"],
                "live_trade_decider": False,
                "rows_logged": len(ml.get("feature_log", [])),
                "state_persistence_mode": getattr(appmod, "STATE_PERSISTENCE_MODE", None),
                "state_file": getattr(appmod, "STATE_FILE", None),
            })

    if "/paper/ml-dataset" not in rules:
        @flask_app.route("/paper/ml-dataset")
        def ml_dataset():
            state = load_state(appmod)
            ml = ensure_ml(state)
            try:
                limit = int(appmod.request.args.get("limit", "250"))
            except Exception:
                limit = 250
            limit = max(1, min(limit, 1000))
            rows = ml.get("feature_log", [])
            return js({"status": "ok", "version": VERSION, "rows_logged": len(rows), "rows_returned": min(limit, len(rows)), "feature_log_tail": rows[-limit:]})

    if "/paper/ml-review" not in rules:
        @flask_app.route("/paper/ml-review")
        def ml_review():
            return js({"status": "ok", "ml_review": review(load_state(appmod), appmod)})

    if "/paper/ml-shadow" not in rules:
        @flask_app.route("/paper/ml-shadow")
        def ml_shadow():
            r = review(load_state(appmod), appmod)
            return js({
                "status": "ok",
                "mode": "shadow_only",
                "live_trade_decider": False,
                "latest_shadow_rankings": r.get("latest_shadow_rankings", []),
                "readiness": r.get("readiness", {}),
                "plain_english": ["ML shadow mode logs and ranks scanner patterns only.", "It cannot place trades or override risk controls."],
            })

    if "/paper/ml-feature-log" not in rules:
        @flask_app.route("/paper/ml-feature-log")
        def ml_feature_log():
            state = load_state(appmod)
            ml = ensure_ml(state)
            rows = ml.get("feature_log", [])
            return js({"status": "ok", "version": VERSION, "rows_logged": len(rows), "last_updated_local": ml.get("last_updated_local"), "last_added_rows": ml.get("last_added_rows", 0), "latest_rows": rows[-50:]})

    if "/paper/backtest-summary" not in rules:
        @flask_app.route("/paper/backtest-summary")
        def backtest_summary():
            state = load_state(appmod)
            trades = state.get("trades", [])
            realized = state.get("realized_pnl", {})
            risk = state.get("risk_controls", {})
            return js({
                "status": "ok",
                "version": VERSION,
                "type": "paper_replay_backtest_readiness",
                "note": "Full walk-forward simulation comes after enough ML feature rows are collected.",
                "rule_system_snapshot": {
                    "trades_logged": len(trades),
                    "realized_pnl_today": fnum(realized.get("today")),
                    "realized_pnl_total": fnum(realized.get("total")),
                    "wins_total": fint(realized.get("wins_total")),
                    "losses_total": fint(realized.get("losses_total")),
                    "intraday_drawdown_pct": fnum(risk.get("intraday_drawdown_pct")),
                    "daily_loss_pct": fnum(risk.get("daily_loss_pct")),
                },
                "ml_shadow_snapshot": review(state, appmod),
                "recommended_next_step": "Collect scanner rows during regular sessions, then compare rules vs ML ranking on profit factor, stop-loss rate, and missed-winner rate.",
            })
    return True


def module_ready(appmod) -> bool:
    return bool(getattr(appmod, "app", None) is not None and hasattr(appmod, "load_state") and hasattr(appmod, "save_state"))


def install(appmod):
    if not ENABLED or appmod is None:
        return False
    if id(appmod) in _INSTALLED_MODULE_IDS:
        return True
    if not module_ready(appmod):
        return False
    if install_routes(appmod):
        patch_save(appmod)
        _INSTALLED_MODULE_IDS.add(id(appmod))
        return True
    return False


class Loader(importlib.abc.Loader):
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def create_module(self, spec):
        return self.wrapped.create_module(spec) if hasattr(self.wrapped, "create_module") else None

    def exec_module(self, module):
        self.wrapped.exec_module(module)
        if getattr(module, "__name__", "") == "app":
            install(module)


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "app":
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            try:
                spec = finder.find_spec(fullname, path, target)
            except Exception:
                continue
            if spec and spec.loader:
                spec.loader = Loader(spec.loader)
                return spec
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.loader:
            spec.loader = Loader(spec.loader)
        return spec


def watchdog():
    # Supports ``python app.py`` where the live module is __main__.
    # Wait for app.py to finish defining load_state/save_state before adding routes.
    for _ in range(250):  # ~25 seconds
        for name in ("app", "__main__"):
            mod = sys.modules.get(name)
            if install(mod):
                return
        time.sleep(0.1)


if ENABLED:
    if not any(isinstance(x, Finder) for x in sys.meta_path):
        sys.meta_path.insert(0, Finder())
    threading.Thread(target=watchdog, daemon=True).start()
