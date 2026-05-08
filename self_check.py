"""One-link internal smoke-test dashboard for the trading bot.

Purpose:
- Reduce manual testing burden from many separate links.
- Let the service check its own safe GET endpoints internally using Flask's
  test_client, so one URL summarizes what is working.
- Avoid mutating/trading endpoints such as /paper/run, /paper/trade-journal-sync,
  or /paper/trade-journal-seed.

Routes:
- /paper/self-check
- /paper/smoke-test
- /paper/test-links
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from typing import Any, Dict, List

VERSION = "one-link-self-check-2026-05-08"
BASE_URL = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "https://trading-bot-clean.up.railway.app"
if BASE_URL and not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL
BASE_URL = BASE_URL.rstrip("/")

REGISTERED_APP_IDS: set[int] = set()

CORE_ENDPOINTS = [
    {"path": "/health", "category": "core", "required": True},
    {"path": "/paper/status", "category": "core", "required": True},
    {"path": "/paper/feedback-loop", "category": "core", "required": True},
    {"path": "/paper/risk-review", "category": "core", "required": True},
    {"path": "/paper/journal", "category": "core", "required": True},
    {"path": "/paper/explain", "category": "core", "required": True},
    {"path": "/paper/intraday-report", "category": "reports", "required": False},
    {"path": "/paper/end-of-day-report", "category": "reports", "required": False},
    {"path": "/paper/report/today", "category": "reports", "required": False},
]

PROTECTION_ENDPOINTS = [
    {"path": "/paper/state-safety-status", "category": "state", "required": True},
    {"path": "/paper/state-recovery-status", "category": "state", "required": True},
    {"path": "/paper/risk-improvement-status", "category": "risk", "required": True},
    {"path": "/paper/live-volatility-status", "category": "risk", "required": True},
    {"path": "/paper/trade-journal-status", "category": "journal", "required": True},
    {"path": "/paper/trade-event-hook-status", "category": "journal", "required": True},
    {"path": "/paper/trade-journal", "category": "journal", "required": False},
]

EOD_AND_ADVISORY_ENDPOINTS = [
    {"path": "/paper/eod-hybrid-status", "category": "eod", "required": False},
    {"path": "/paper/eod-allocation-plan", "category": "eod", "required": False},
    {"path": "/paper/strategy-comparison", "category": "eod", "required": False},
    {"path": "/paper/next-session-watchlist", "category": "eod", "required": False},
    {"path": "/paper/eod-backtest-readiness", "category": "eod", "required": False},
    {"path": "/paper/next-session-readiness", "category": "ops", "required": False},
    {"path": "/paper/scanner-log", "category": "ops", "required": False},
    {"path": "/paper/next-session-risk-plan", "category": "risk", "required": False},
    {"path": "/paper/volatility-stop-plan", "category": "risk", "required": False},
    {"path": "/paper/follow-through-review", "category": "risk", "required": False},
]

ALL_SAFE_ENDPOINTS = CORE_ENDPOINTS + PROTECTION_ENDPOINTS + EOD_AND_ADVISORY_ENDPOINTS


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _full_url(path: str) -> str:
    return f"{BASE_URL}{path}"


def _extract_json(resp: Any) -> Dict[str, Any]:
    try:
        obj = resp.get_json(silent=True)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _compact_payload(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    compact: Dict[str, Any] = {}
    for key in ["status", "type", "version", "generated_local", "time"]:
        if key in payload:
            compact[key] = payload.get(key)
    if path == "/health":
        sd = payload.get("state_diagnostic", {}) if isinstance(payload.get("state_diagnostic"), dict) else {}
        compact["state_diagnostic"] = {
            "persistent_storage_configured": sd.get("persistent_storage_configured"),
            "state_file": sd.get("state_file"),
            "history_count": sd.get("history_count"),
            "trades_count": sd.get("trades_count"),
            "positions_count": sd.get("positions_count"),
            "size_bytes": sd.get("size_bytes"),
        }
    elif path == "/paper/status":
        compact["equity"] = payload.get("equity")
        compact["cash"] = payload.get("cash")
        compact["positions"] = payload.get("position_symbols") or list((payload.get("positions") or {}).keys()) if isinstance(payload.get("positions"), dict) else payload.get("positions")
        compact["performance"] = payload.get("performance")
        rc = payload.get("risk_controls", {}) if isinstance(payload.get("risk_controls"), dict) else {}
        compact["risk_controls"] = {
            "self_defense_active": rc.get("self_defense_active"),
            "self_defense_reason": rc.get("self_defense_reason"),
            "daily_loss_pct": rc.get("daily_loss_pct"),
            "intraday_drawdown_pct": rc.get("intraday_drawdown_pct"),
        }
        audit = payload.get("scanner_audit", {}) if isinstance(payload.get("scanner_audit"), dict) else {}
        compact["scanner_audit"] = {
            "signals_found": audit.get("signals_found"),
            "blocked_entries_count": len(audit.get("blocked_entries", [])) if isinstance(audit.get("blocked_entries"), list) else None,
            "top_blocked_symbols": audit.get("top_blocked_symbols"),
        }
    elif "trade-journal" in path or "trade-event" in path:
        compact["installed"] = payload.get("installed")
        compact["watcher_started"] = payload.get("watcher_started")
        compact["journal_summary"] = payload.get("journal_summary") or payload.get("summary")
        compact["state_json_written_by_trade_journal"] = payload.get("state_json_written_by_trade_journal")
    elif "state-safety" in path:
        compact["state_json_written_by_bootstrap"] = payload.get("state_json_written_by_bootstrap")
        compact["runtime_controls_write_ok"] = payload.get("runtime_controls_write_ok")
        compact["state_file_size_bytes"] = payload.get("state_file_size_bytes")
        compact["backup_largest_size_bytes"] = payload.get("backup_largest_size_bytes")
    elif "state-recovery" in path:
        compact["restore_enabled"] = payload.get("restore_enabled")
        compact["restored"] = payload.get("restored")
        decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
        compact["decision"] = {"should_restore": decision.get("should_restore"), "reason": decision.get("reason")}
    elif "live-volatility" in path:
        compact["enabled"] = payload.get("enabled")
        compact["runtime_expectation"] = payload.get("runtime_expectation")
    elif "risk-improvement" in path:
        compact["mode"] = payload.get("mode")
        compact["state_safety"] = payload.get("state_safety")
    elif "feedback-loop" in path:
        compact["actions"] = payload.get("actions")
        compact["self_defense_mode"] = payload.get("self_defense_mode")
        compact["block_new_entries"] = payload.get("block_new_entries")
        compact["dynamic_min_long_score"] = payload.get("dynamic_min_long_score")
    elif "risk-review" in path:
        compact["equity"] = payload.get("equity")
        compact["cash"] = payload.get("cash")
        compact["market_mode"] = payload.get("market_mode")
        compact["risk_score"] = payload.get("risk_score")
        compact["performance"] = payload.get("performance")
        compact["risk_controls"] = payload.get("risk_controls")
    elif "journal" in path:
        compact["summary"] = payload.get("summary")
        compact["diagnosis"] = payload.get("diagnosis")
    return compact


def _result_level(status_code: int, json_ok: bool, required: bool) -> str:
    if status_code == 200 and json_ok:
        return "pass"
    if required:
        return "fail"
    return "warn"


def run_self_check(flask_app: Any) -> Dict[str, Any]:
    start = time.time()
    results: List[Dict[str, Any]] = []
    summary = {"pass": 0, "warn": 0, "fail": 0}

    try:
        client = flask_app.test_client()
    except Exception as exc:
        return {
            "status": "error",
            "type": "self_check",
            "version": VERSION,
            "generated_local": _now_text(),
            "error": f"could not create flask test client: {exc}",
        }

    for ep in ALL_SAFE_ENDPOINTS:
        path = ep["path"]
        t0 = time.time()
        row: Dict[str, Any] = {
            "path": path,
            "url": _full_url(path),
            "category": ep.get("category"),
            "required": bool(ep.get("required")),
        }
        try:
            resp = client.get(path)
            payload = _extract_json(resp)
            json_ok = bool(payload)
            level = _result_level(int(resp.status_code), json_ok, bool(ep.get("required")))
            row.update({
                "level": level,
                "ok": level == "pass",
                "status_code": int(resp.status_code),
                "json_ok": json_ok,
                "content_type": resp.content_type,
                "elapsed_ms": round((time.time() - t0) * 1000, 2),
                "compact": _compact_payload(path, payload),
            })
        except Exception as exc:
            level = "fail" if ep.get("required") else "warn"
            row.update({
                "level": level,
                "ok": False,
                "status_code": None,
                "json_ok": False,
                "elapsed_ms": round((time.time() - t0) * 1000, 2),
                "error": str(exc),
            })
        summary[row["level"]] = summary.get(row["level"], 0) + 1
        results.append(row)

    failed_required = [r for r in results if r.get("level") == "fail"]
    warnings = [r for r in results if r.get("level") == "warn"]
    overall = "pass" if not failed_required else "fail"
    if overall == "pass" and warnings:
        overall = "warn"

    status_payload = next((r.get("compact", {}) for r in results if r.get("path") == "/paper/status"), {})
    health_payload = next((r.get("compact", {}) for r in results if r.get("path") == "/health"), {})
    journal_payload = next((r.get("compact", {}) for r in results if r.get("path") == "/paper/trade-journal-status"), {})

    return {
        "status": "ok" if overall != "fail" else "fail",
        "overall": overall,
        "type": "self_check",
        "version": VERSION,
        "generated_local": _now_text(),
        "elapsed_ms": round((time.time() - start) * 1000, 2),
        "summary_counts": summary,
        "failed_required": [{"path": r.get("path"), "status_code": r.get("status_code"), "error": r.get("error")} for r in failed_required],
        "warnings": [{"path": r.get("path"), "status_code": r.get("status_code"), "error": r.get("error")} for r in warnings],
        "dashboard": {
            "health": health_payload,
            "status": status_payload,
            "trade_journal": journal_payload,
        },
        "results": results,
        "copy_paste_links_separate": [_full_url(ep["path"]) for ep in ALL_SAFE_ENDPOINTS],
        "note": "This endpoint checks safe GET routes internally. It intentionally does not call /paper/run or journal seed/sync endpoints.",
    }


def test_links_payload() -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "test_links",
        "version": VERSION,
        "generated_local": _now_text(),
        "base_url": BASE_URL,
        "links_separate": [_full_url(ep["path"]) for ep in ALL_SAFE_ENDPOINTS],
        "single_best_link": _full_url("/paper/self-check"),
        "do_not_auto_test": [
            _full_url("/paper/run"),
            _full_url("/paper/trade-journal-sync"),
            _full_url("/paper/trade-journal-seed"),
        ],
    }


def register_routes(flask_app: Any, module: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/self-check" not in existing:
        flask_app.add_url_rule("/paper/self-check", "paper_self_check", lambda: jsonify(run_self_check(flask_app)))
    if "/paper/smoke-test" not in existing:
        flask_app.add_url_rule("/paper/smoke-test", "paper_smoke_test", lambda: jsonify(run_self_check(flask_app)))
    if "/paper/test-links" not in existing:
        flask_app.add_url_rule("/paper/test-links", "paper_test_links", lambda: jsonify(test_links_payload()))
    REGISTERED_APP_IDS.add(id(flask_app))
