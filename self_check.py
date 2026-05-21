"""Mobile-safe one-link self-check dashboard for the trading bot.

Purpose:
- Keep /paper/self-check fast enough for iPhone/Railway/browser sessions.
- Stop routine testing from internally executing 50-80 diagnostic routes.
- Preserve /paper/full-self-check for bounded diagnostics when deeper output is needed.
- Avoid mutating/trading endpoints such as /paper/run, /paper/trade-journal-sync,
  or /paper/trade-journal-seed.

Routes:
- /paper/self-check          mobile-safe daily check; reads state directly
- /paper/smoke-test          alias for mobile-safe daily check
- /paper/full-self-check     bounded diagnostic route runner
- /paper/test-links          separated copy/paste links
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from typing import Any, Dict, Iterable, List

VERSION = "mobile-safe-self-check-2026-05-21-v1"
BASE_URL = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "https://trading-bot-clean.up.railway.app"
if BASE_URL and not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL
BASE_URL = BASE_URL.rstrip("/")

REGISTERED_APP_IDS: set[int] = set()

# /paper/self-check is intentionally tiny now. The old behavior of checking many
# endpoints inside one request was timing out on Railway/mobile sessions.
MOBILE_SAFE_ENDPOINTS = [
    {"path": "/health", "category": "core", "required": True, "executed": "direct_state_snapshot"},
    {"path": "/paper/status", "category": "core", "required": True, "executed": "direct_state_snapshot"},
    {"path": "/paper/runner-freshness", "category": "ops", "required": False, "executed": "link_only"},
    {"path": "/paper/trade-journal-status", "category": "journal", "required": False, "executed": "link_only"},
    {"path": "/paper/state-journal-guard-status", "category": "journal", "required": False, "executed": "link_only"},
]

# Fast endpoints used only by /paper/full-self-check. Other modules may append to
# this list; /paper/self-check ignores those mutations and remains mobile-safe.
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
    {"path": "/paper/trade-journal-status", "category": "journal", "required": True},
    {"path": "/paper/trade-event-hook-status", "category": "journal", "required": True},
]

# Bounded extras. These are executed by /paper/full-self-check but intentionally
# avoid expensive report/allocation endpoints that can stall a request.
FULL_EXECUTED_EXTRA_ENDPOINTS = [
    {"path": "/paper/journal", "category": "core", "required": False},
    {"path": "/paper/explain", "category": "core", "required": False},
    {"path": "/paper/scanner-log", "category": "ops", "required": False},
    {"path": "/paper/next-session-readiness", "category": "ops", "required": False},
    {"path": "/paper/next-session-risk-plan", "category": "risk", "required": False},
    {"path": "/paper/volatility-stop-plan", "category": "risk", "required": False},
    {"path": "/paper/follow-through-review", "category": "risk", "required": False},
    {"path": "/paper/eod-hybrid-status", "category": "eod", "required": False},
    {"path": "/paper/eod-backtest-readiness", "category": "eod", "required": False},
]

# Heavy links are returned but not internally executed by self-check. These can
# generate reports, calculate allocation plans, or perform broad yfinance scans.
HEAVY_LINK_ONLY_ENDPOINTS = [
    {"path": "/paper/live-volatility-status", "category": "risk", "reason": "can take 15+ seconds during active sessions"},
    {"path": "/paper/risk-review", "category": "core", "reason": "can refresh broad risk data"},
    {"path": "/paper/intraday-report", "category": "reports", "reason": "report generation"},
    {"path": "/paper/end-of-day-report", "category": "reports", "reason": "report generation"},
    {"path": "/paper/report/today", "category": "reports", "reason": "stored/report generation"},
    {"path": "/paper/trade-journal", "category": "journal", "reason": "can be large"},
    {"path": "/paper/eod-allocation-plan", "category": "eod", "reason": "heavy allocation scan"},
    {"path": "/paper/strategy-comparison", "category": "eod", "reason": "strategy comparison scan"},
    {"path": "/paper/next-session-watchlist", "category": "eod", "reason": "heavy watchlist scan"},
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
    if normalized in {"mobile", "fast", "safe", "smoke"}:
        return list(MOBILE_SAFE_ENDPOINTS)
    if normalized in {"full", "diagnostic", "all"}:
        return _dedupe_endpoints(LIGHT_ENDPOINTS + FULL_EXECUTED_EXTRA_ENDPOINTS)
    return list(MOBILE_SAFE_ENDPOINTS)


def _state_file_path() -> str:
    state_dir = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    state_filename = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
    if state_dir:
        return os.path.join(state_dir, os.path.basename(state_filename))
    return state_filename


def _read_state() -> Dict[str, Any]:
    path = _state_file_path()
    try:
        if not os.path.exists(path):
            return {"_state_error": "state_file_missing", "_state_file": path}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data["_state_file"] = path
            data["_state_size_bytes"] = os.path.getsize(path)
            return data
        return {"_state_error": "state_file_not_object", "_state_file": path}
    except BaseException as exc:
        return {"_state_error": str(exc), "_state_file": path}


def _safe_dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _safe_list(obj: Any) -> List[Any]:
    return obj if isinstance(obj, list) else []


def _position_symbols_from_state(state: Dict[str, Any]) -> List[str]:
    positions = state.get("positions")
    if isinstance(positions, dict):
        return list(positions.keys())
    if isinstance(positions, list):
        return [str(x) for x in positions]
    portfolio = _safe_dict(state.get("portfolio"))
    p2 = portfolio.get("positions")
    if isinstance(p2, dict):
        return list(p2.keys())
    return []


def _performance_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    perf = _safe_dict(state.get("performance"))
    if perf:
        return perf
    portfolio = _safe_dict(state.get("portfolio"))
    return _safe_dict(portfolio.get("performance"))


def _cash_equity_from_state(state: Dict[str, Any]) -> tuple[Any, Any]:
    portfolio = _safe_dict(state.get("portfolio"))
    cash = state.get("cash", portfolio.get("cash"))
    equity = state.get("equity", portfolio.get("equity"))
    return cash, equity


def _state_diagnostic(state: Dict[str, Any]) -> Dict[str, Any]:
    positions_count = len(_position_symbols_from_state(state))
    trades = state.get("trades")
    history = state.get("history")
    reports = state.get("reports")
    return {
        "persistent_storage_configured": bool(os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")),
        "state_file": state.get("_state_file"),
        "state_file_error": state.get("_state_error"),
        "positions_count": positions_count,
        "trades_count": len(trades) if isinstance(trades, list) else None,
        "history_count": len(history) if isinstance(history, list) else None,
        "reports_present": isinstance(reports, dict),
        "size_bytes": state.get("_state_size_bytes"),
    }


def _direct_health_compact(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "running" if not state.get("_state_error") else "warn",
        "time": _now_text(),
        "state_diagnostic": _state_diagnostic(state),
    }


def _direct_status_compact(state: Dict[str, Any]) -> Dict[str, Any]:
    cash, equity = _cash_equity_from_state(state)
    positions = _position_symbols_from_state(state)
    perf = _performance_from_state(state)
    risk_controls = _safe_dict(state.get("risk_controls"))
    scanner_audit = _safe_dict(state.get("scanner_audit"))
    return {
        "status": "running" if not state.get("_state_error") else "warn",
        "time": _now_text(),
        "cash": cash,
        "equity": equity,
        "positions": positions,
        "performance": perf,
        "risk_controls": {
            "self_defense_active": risk_controls.get("self_defense_active"),
            "self_defense_reason": risk_controls.get("self_defense_reason"),
            "daily_loss_pct": risk_controls.get("daily_loss_pct"),
            "intraday_drawdown_pct": risk_controls.get("intraday_drawdown_pct"),
        },
        "scanner_audit": {
            "signals_found": scanner_audit.get("signals_found"),
            "blocked_entries_count": len(_safe_list(scanner_audit.get("blocked_entries"))),
            "top_blocked_symbols": scanner_audit.get("top_blocked_symbols"),
        },
    }


def _journal_summary_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    perf = _performance_from_state(state)
    trades = _safe_list(state.get("trades"))
    return {
        "status": "ok" if not state.get("_state_error") else "warn",
        "source_of_truth": "state_direct_mobile_safe",
        "execution_rows_count": len(trades),
        "realized_today": perf.get("realized_pnl_today"),
        "realized_total": perf.get("realized_pnl_total"),
        "unrealized_pnl": perf.get("unrealized_pnl"),
        "wins_total": perf.get("wins_total"),
        "losses_total": perf.get("losses_total"),
        "open_positions_count": len(_position_symbols_from_state(state)),
    }


def _extract_json(resp: Any) -> Dict[str, Any]:
    try:
        obj = resp.get_json(silent=True)
        return obj if isinstance(obj, dict) else {}
    except BaseException as exc:
        return {"_extract_error": str(exc)}


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
    elif "risk-improvement" in path:
        compact["mode"] = payload.get("mode")
        compact["state_safety"] = payload.get("state_safety")
    elif "opening-range-fvg" in path:
        tier = _safe_dict(payload.get("position_tier"))
        compact["guard_enabled"] = payload.get("guard_enabled")
        compact["pilot"] = payload.get("pilot")
        compact["hard_enforcement_active"] = payload.get("hard_enforcement_active")
        compact["position_tier"] = {
            "tier": tier.get("tier"),
            "max_positions": tier.get("max_positions"),
            "reason": tier.get("reason"),
        }
        compact["recent_decisions_count"] = payload.get("recent_decisions_count")
        compact["recent_would_block_count"] = payload.get("recent_would_block_count")
        compact["recent_tail_count"] = len(_safe_list(payload.get("recent_tail")))
    elif "feedback-loop" in path:
        compact["actions"] = payload.get("actions")
        compact["self_defense_mode"] = payload.get("self_defense_mode")
        compact["block_new_entries"] = payload.get("block_new_entries")
        compact["dynamic_min_long_score"] = payload.get("dynamic_min_long_score")
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


def run_mobile_self_check() -> Dict[str, Any]:
    start = time.time()
    state = _read_state()
    health = _direct_health_compact(state)
    status = _direct_status_compact(state)
    journal = _journal_summary_from_state(state)
    state_ok = not bool(state.get("_state_error"))
    overall = "pass" if state_ok else "warn"
    results = [
        {
            "path": "/health",
            "url": _full_url("/health"),
            "category": "core",
            "required": True,
            "executed": "direct_state_snapshot",
            "level": "pass" if state_ok else "warn",
            "ok": state_ok,
            "status_code": 200 if state_ok else None,
            "json_ok": state_ok,
            "elapsed_ms": 0.0,
            "compact": health,
        },
        {
            "path": "/paper/status",
            "url": _full_url("/paper/status"),
            "category": "core",
            "required": True,
            "executed": "direct_state_snapshot",
            "level": "pass" if state_ok else "warn",
            "ok": state_ok,
            "status_code": 200 if state_ok else None,
            "json_ok": state_ok,
            "elapsed_ms": 0.0,
            "compact": status,
        },
    ]
    return {
        "status": "ok" if overall == "pass" else "warn",
        "overall": overall,
        "type": "self_check",
        "mode": "mobile_safe",
        "version": VERSION,
        "generated_local": _now_text(),
        "elapsed_ms": round((time.time() - start) * 1000, 2),
        "summary_counts": {"pass": 2 if state_ok else 0, "warn": 0 if state_ok else 2, "fail": 0, "linked_only": 3},
        "failed_required": [] if state_ok else [{"path": _state_file_path(), "status_code": None, "error": state.get("_state_error")}],
        "warnings": [] if state_ok else [{"path": _state_file_path(), "status_code": None, "error": state.get("_state_error")}],
        "dashboard": {
            "health": health,
            "status": status,
            "trade_journal": {"journal_summary": journal, "status": journal.get("status")},
            "runner_freshness": {"status": "linked_only", "url": _full_url("/paper/runner-freshness")},
            "runner_safety": {"status": "linked_only", "url": _full_url("/paper/runner-safety-status")},
            "state_journal_guard": {"status": "linked_only", "url": _full_url("/paper/state-journal-guard-status")},
        },
        "operator_summary": {
            "overall": overall,
            "positions": status.get("positions"),
            "realized_today": journal.get("realized_today"),
            "realized_total": journal.get("realized_total"),
            "unrealized_pnl": journal.get("unrealized_pnl"),
            "open_positions_count": journal.get("open_positions_count"),
            "source": "direct_state_snapshot_no_internal_route_calls",
        },
        "truth_summary": journal,
        "results": results,
        "checked_links_count": 2,
        "checked_paths": ["/health", "/paper/status"],
        "linked_only_heavy_routes": [],
        "copy_paste_links_separate": [_full_url("/paper/self-check")],
        "light_self_check": _full_url("/paper/self-check"),
        "full_self_check": _full_url("/paper/full-self-check"),
        "test_links": _full_url("/paper/test-links"),
        "single_best_link": _full_url("/paper/self-check"),
        "normal_test_link": _full_url("/paper/self-check"),
        "heavy_links_separate_not_auto_run": [_full_url(ep["path"]) for ep in HEAVY_LINK_ONLY_ENDPOINTS],
        "note": "Mobile-safe self-check does not internally call /paper/status or the 80+ diagnostic routes. It reads state.json directly so the link opens quickly. Use /paper/full-self-check only when you intentionally need a deeper diagnostic.",
        "routine_test_policy": {
            "routine_test_url": _full_url("/paper/self-check"),
            "routine_testing_rule": "Use only /paper/self-check after normal pushes.",
            "extra_links_required": False,
            "deep_diagnostic_url": _full_url("/paper/full-self-check"),
        },
    }


def run_full_self_check(flask_app: Any, mode: str = "full") -> Dict[str, Any]:
    start = time.time()
    normalized_mode = str(mode or "full").lower().strip()
    endpoints = endpoints_for_mode("full")
    results: List[Dict[str, Any]] = []
    summary = {"pass": 0, "warn": 0, "fail": 0, "linked_only": 0, "skipped_timeout_budget": 0}
    timeout_budget_seconds = float(os.environ.get("SELF_CHECK_FULL_BUDGET_SECONDS", "35"))

    try:
        client = flask_app.test_client()
    except BaseException as exc:
        return {"status": "error", "overall": "fail", "type": "self_check", "mode": normalized_mode, "version": VERSION, "generated_local": _now_text(), "error": f"could not create flask test client: {exc}"}

    for ep in endpoints:
        path = ep["path"]
        if time.time() - start >= timeout_budget_seconds:
            row = {
                "path": path,
                "url": _full_url(path),
                "category": ep.get("category"),
                "required": bool(ep.get("required")),
                "level": "linked_only",
                "ok": None,
                "executed": False,
                "reason": "skipped_to_protect_self_check_timeout_budget",
            }
            summary["linked_only"] += 1
            summary["skipped_timeout_budget"] += 1
            results.append(row)
            continue

        t0 = time.time()
        row: Dict[str, Any] = {"path": path, "url": _full_url(path), "category": ep.get("category"), "required": bool(ep.get("required")), "executed": True}
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

    linked_only = []
    for item in HEAVY_LINK_ONLY_ENDPOINTS:
        linked_only.append({"path": item["path"], "url": _full_url(item["path"]), "category": item.get("category"), "reason": item.get("reason"), "level": "linked_only", "executed": False})
    summary["linked_only"] += len(linked_only)

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
    fvg_payload = next((r.get("compact", {}) for r in results if r.get("path") == "/paper/opening-range-fvg-status"), {})

    return {
        "status": "ok" if overall != "fail" else "fail",
        "overall": overall,
        "type": "self_check",
        "mode": "full_bounded",
        "version": VERSION,
        "generated_local": _now_text(),
        "elapsed_ms": round((time.time() - start) * 1000, 2),
        "timeout_budget_seconds": timeout_budget_seconds,
        "summary_counts": summary,
        "failed_required": [{"path": r.get("path"), "status_code": r.get("status_code"), "error": r.get("error")} for r in failed_required],
        "warnings": [{"path": r.get("path"), "status_code": r.get("status_code"), "error": r.get("error")} for r in warnings],
        "dashboard": {"health": health_payload, "status": status_payload, "trade_journal": journal_payload, "runner_freshness": freshness_payload, "runner_safety": safety_payload, "opening_range_fvg": fvg_payload},
        "results": results,
        "linked_only_heavy_routes": linked_only,
        "copy_paste_links_separate": [_full_url(ep["path"]) for ep in endpoints],
        "heavy_links_separate_not_auto_run": [_full_url(ep["path"]) for ep in HEAVY_LINK_ONLY_ENDPOINTS],
        "light_self_check": _full_url("/paper/self-check"),
        "full_self_check": _full_url("/paper/full-self-check"),
        "single_best_link": _full_url("/paper/self-check"),
        "normal_test_link": _full_url("/paper/self-check"),
        "note": "Full self-check is bounded and will skip remaining routes after the timeout budget. Heavy endpoints are listed as links but not internally executed.",
    }


def run_self_check(flask_app: Any, mode: str = "light") -> Dict[str, Any]:
    normalized_mode = str(mode or "light").lower().strip()
    if normalized_mode in {"full", "diagnostic", "all"}:
        return run_full_self_check(flask_app, mode=normalized_mode)
    return run_mobile_self_check()


def test_links_payload() -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "test_links",
        "version": VERSION,
        "generated_local": _now_text(),
        "base_url": BASE_URL,
        "single_best_link": _full_url("/paper/self-check"),
        "normal_test_link": _full_url("/paper/self-check"),
        "mobile_safe_link": _full_url("/paper/self-check"),
        "smoke_test_link": _full_url("/paper/smoke-test"),
        "full_bounded_diagnostic_link": _full_url("/paper/full-self-check"),
        "links_separate_mobile_safe": [_full_url(ep["path"]) for ep in MOBILE_SAFE_ENDPOINTS],
        "links_separate_full_bounded": [_full_url(ep["path"]) for ep in endpoints_for_mode("full")],
        "heavy_links_separate_not_auto_run": [_full_url(ep["path"]) for ep in HEAVY_LINK_ONLY_ENDPOINTS],
        "do_not_auto_test": [_full_url(path) for path in MUTATING_OR_ACTION_ENDPOINTS],
        "routine_testing_rule": "Use only /paper/self-check for normal checks. Use /paper/full-self-check only for deep diagnostics.",
    }


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
