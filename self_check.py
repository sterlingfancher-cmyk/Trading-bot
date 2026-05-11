"""One-link internal smoke-test dashboard for the trading bot.

Purpose:
- Reduce manual testing burden from many separate links.
- Keep /paper/self-check lightweight enough to use throughout the day.
- Put heavier/report-generating endpoints behind /paper/full-self-check only.
- Avoid mutating/trading endpoints such as /paper/run, /paper/trade-journal-sync,
  or /paper/trade-journal-seed.

Routes:
- /paper/self-check          lightweight daily check
- /paper/smoke-test          alias for lightweight daily check
- /paper/full-self-check     heavier troubleshooting check
- /paper/test-links          separated copy/paste links
"""
from __future__ import annotations

import datetime as dt
import os
import time
from typing import Any, Dict, Iterable, List

VERSION = "lightweight-self-check-runner-safety-2026-05-11"
BASE_URL = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "https://trading-bot-clean.up.railway.app"
if BASE_URL and not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL
BASE_URL = BASE_URL.rstrip("/")

REGISTERED_APP_IDS: set[int] = set()

LIGHT_ENDPOINTS = [
    {"path": "/health", "category": "core", "required": True},
    {"path": "/paper/status", "category": "core", "required": True},
    {"path": "/paper/feedback-loop", "category": "core", "required": False},
    {"path": "/paper/runner-freshness", "category": "ops", "required": True},
    {"path": "/paper/runner-safety-status", "category": "ops", "required": True},
    {"path": "/paper/price-health", "category": "ops", "required": False},
    {"path": "/paper/state-safety-status", "category": "state", "required": True},
    {"path": "/paper/state-recovery-status", "category": "state", "required": True},
    {"path": "/paper/risk-improvement-status", "category": "risk", "required": True},
    {"path": "/paper/live-volatility-status", "category": "risk", "required": True},
    {"path": "/paper/trade-journal-status", "category": "journal", "required": True},
    {"path": "/paper/trade-event-hook-status", "category": "journal", "required": True},
]

FULL_EXTRA_ENDPOINTS = [
    {"path": "/paper/risk-review", "category": "core", "required": False},
    {"path": "/paper/journal", "category": "core", "required": False},
    {"path": "/paper/explain", "category": "core", "required": False},
    {"path": "/paper/intraday-report", "category": "reports", "required": False},
    {"path": "/paper/end-of-day-report", "category": "reports", "required": False},
    {"path": "/paper/report/today", "category": "reports", "required": False},
    {"path": "/paper/trade-journal", "category": "journal", "required": False},
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

MUTATING_OR_ACTION_ENDPOINTS = [
    "/paper/run",
    "/paper/trade-journal-sync",
    "/paper/trade-journal-seed",
]


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _full_url(path: str) -> str:
    return f"{BASE_URL}{path}"


def _dedupe_endpoints(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for item in items:
        path = item.get("path")
        if path and path not in seen:
            out.append(item)
            seen.add(path)
    return out


def endpoints_for_mode(mode: str = "light") -> List[Dict[str, Any]]:
    normalized = str(mode or "light").lower().strip()
    if normalized in {"full", "diagnostic", "all"}:
        return _dedupe_endpoints(LIGHT_ENDPOINTS + FULL_EXTRA_ENDPOINTS)
    return list(LIGHT_ENDPOINTS)


def _extract_json(resp: Any) -> Dict[str, Any]:
    try:
        obj = resp.get_json(silent=True)
        return obj if isinstance(obj, dict) else {}
    except BaseException as exc:
        return {"_extract_error": str(exc)}


def _safe_dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _safe_list(obj: Any) -> List[Any]:
    return obj if isinstance(obj, list) else []


def _compact_payload(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    compact: Dict[str, Any] = {}
    for key in ["status", "type", "version", "generated_local", "time"]:
        if key in payload:
            compact[key] = payload.get(key)

    if path == "/health":
        sd = _safe_dict(payload.get("state_diagnostic"))
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
        positions_obj = payload.get("positions")
        compact["positions"] = payload.get("position_symbols") or (list(positions_obj.keys()) if isinstance(positions_obj, dict) else positions_obj)
        compact["performance"] = payload.get("performance")
        rc = _safe_dict(payload.get("risk_controls"))
        compact["risk_controls"] = {
            "self_defense_active": rc.get("self_defense_active"),
            "self_defense_reason": rc.get("self_defense_reason"),
            "daily_loss_pct": rc.get("daily_loss_pct"),
            "intraday_drawdown_pct": rc.get("intraday_drawdown_pct"),
        }
        audit = _safe_dict(payload.get("scanner_audit"))
        compact["scanner_audit"] = {
            "signals_found": audit.get("signals_found"),
            "blocked_entries_count": len(_safe_list(audit.get("blocked_entries"))),
            "top_blocked_symbols": audit.get("top_blocked_symbols"),
        }
    elif "runner-freshness" in path:
        compact["stale_during_market"] = payload.get("stale_during_market")
        compact["last_successful_run_local"] = payload.get("last_successful_run_local")
        compact["last_skip_reason"] = payload.get("last_skip_reason")
        compact["last_error"] = payload.get("last_error")
        compact["notes"] = payload.get("notes")
    elif "runner-safety" in path or "price-health" in path:
        compact["installed"] = payload.get("installed")
        compact["download_wrapper_active"] = payload.get("download_wrapper_active")
        compact["latest_price_wrapper_active"] = payload.get("latest_price_wrapper_active")
        compact["downloads_attempted"] = payload.get("downloads_attempted")
        compact["downloads_failed"] = payload.get("downloads_failed")
        compact["fallback_price_hits"] = payload.get("fallback_price_hits")
        compact["last_error"] = payload.get("last_error")
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
        decision = _safe_dict(payload.get("decision"))
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
    elif path == "/paper/journal":
        compact["summary"] = payload.get("summary")
        compact["diagnosis"] = payload.get("diagnosis")
    return compact


def _result_level(status_code: int | None, json_ok: bool, required: bool) -> str:
    if status_code == 200 and json_ok:
        return "pass"
    if required:
        return "fail"
    return "warn"


def run_self_check(flask_app: Any, mode: str = "light") -> Dict[str, Any]:
    start = time.time()
    normalized_mode = str(mode or "light").lower().strip()
    endpoints = endpoints_for_mode(normalized_mode)
    results: List[Dict[str, Any]] = []
    summary = {"pass": 0, "warn": 0, "fail": 0}

    try:
        client = flask_app.test_client()
    except BaseException as exc:
        return {"status": "error", "overall": "fail", "type": "self_check", "mode": normalized_mode, "version": VERSION, "generated_local": _now_text(), "error": f"could not create flask test client: {exc}"}

    for ep in endpoints:
        path = ep["path"]
        t0 = time.time()
        row: Dict[str, Any] = {"path": path, "url": _full_url(path), "category": ep.get("category"), "required": bool(ep.get("required"))}
        try:
            resp = client.get(path, buffered=True)
            payload = _extract_json(resp)
            json_ok = bool(payload) and "_extract_error" not in payload
            status_code = int(getattr(resp, "status_code", 0) or 0)
            level = _result_level(status_code, json_ok, bool(ep.get("required")))
            row.update({"level": level, "ok": level == "pass", "status_code": status_code, "json_ok": json_ok, "content_type": getattr(resp, "content_type", None), "elapsed_ms": round((time.time() - t0) * 1000, 2), "compact": _compact_payload(path, payload)})
            if "_extract_error" in payload:
                row["error"] = payload.get("_extract_error")
        except BaseException as exc:
            level = "fail" if ep.get("required") else "warn"
            row.update({"level": level, "ok": False, "status_code": None, "json_ok": False, "elapsed_ms": round((time.time() - t0) * 1000, 2), "error": str(exc), "error_type": type(exc).__name__})
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
    freshness_payload = next((r.get("compact", {}) for r in results if r.get("path") == "/paper/runner-freshness"), {})
    safety_payload = next((r.get("compact", {}) for r in results if r.get("path") == "/paper/runner-safety-status"), {})

    return {
        "status": "ok" if overall != "fail" else "fail",
        "overall": overall,
        "type": "self_check",
        "mode": "full" if normalized_mode in {"full", "diagnostic", "all"} else "light",
        "version": VERSION,
        "generated_local": _now_text(),
        "elapsed_ms": round((time.time() - start) * 1000, 2),
        "summary_counts": summary,
        "failed_required": [{"path": r.get("path"), "status_code": r.get("status_code"), "error": r.get("error")} for r in failed_required],
        "warnings": [{"path": r.get("path"), "status_code": r.get("status_code"), "error": r.get("error")} for r in warnings],
        "dashboard": {"health": health_payload, "status": status_payload, "trade_journal": journal_payload, "runner_freshness": freshness_payload, "runner_safety": safety_payload},
        "results": results,
        "copy_paste_links_separate": [_full_url(ep["path"]) for ep in endpoints],
        "light_self_check": _full_url("/paper/self-check"),
        "full_self_check": _full_url("/paper/full-self-check"),
        "note": "Light mode checks runner freshness, price safety, state safety, and journal health. Full mode adds report/EOD endpoints. Neither mode calls /paper/run or journal seed/sync endpoints.",
    }


def test_links_payload() -> Dict[str, Any]:
    light_links = [_full_url(ep["path"]) for ep in endpoints_for_mode("light")]
    full_links = [_full_url(ep["path"]) for ep in endpoints_for_mode("full")]
    return {"status": "ok", "type": "test_links", "version": VERSION, "generated_local": _now_text(), "base_url": BASE_URL, "single_best_link": _full_url("/paper/self-check"), "full_diagnostic_link": _full_url("/paper/full-self-check"), "links_separate_light": light_links, "links_separate_full": full_links, "do_not_auto_test": [_full_url(path) for path in MUTATING_OR_ACTION_ENDPOINTS]}


def register_routes(flask_app: Any, module: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except BaseException:
        existing = set()

    if "/paper/self-check" not in existing:
        flask_app.add_url_rule("/paper/self-check", "paper_self_check", lambda: jsonify(run_self_check(flask_app, mode="light")))
    if "/paper/smoke-test" not in existing:
        flask_app.add_url_rule("/paper/smoke-test", "paper_smoke_test", lambda: jsonify(run_self_check(flask_app, mode="light")))
    if "/paper/full-self-check" not in existing:
        flask_app.add_url_rule("/paper/full-self-check", "paper_full_self_check", lambda: jsonify(run_self_check(flask_app, mode="full")))
    if "/paper/test-links" not in existing:
        flask_app.add_url_rule("/paper/test-links", "paper_test_links", lambda: jsonify(test_links_payload()))
    REGISTERED_APP_IDS.add(id(flask_app))
