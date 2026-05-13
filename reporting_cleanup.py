"""Reporting cleanup layer for one-link bot diagnostics.

This module is intentionally lightweight and non-trading:
- cleans stale runner skip labels in /paper/self-check output
- adds a compact journal truth summary to /paper/self-check
- moves noisy multi-link lists behind an opt-in verbose flag
- classifies ml_shadow/deep_scan feature-log rows as review/diagnostic rows,
  not unknown rows, in journal truth reporting
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, Iterable, List

VERSION = "reporting-cleanup-2026-05-13"

REGISTERED_APP_IDS: set[int] = set()
_PATCHED_SELF_CHECK = False
_PATCHED_JOURNAL_TRUTH = False

EXTRA_LIGHT_ENDPOINTS = [
    {"path": "/paper/state-io-status", "category": "state", "required": False},
    {"path": "/paper/classic-signal-status", "category": "risk", "required": True},
    {"path": "/paper/intraday-timing-status", "category": "risk", "required": True},
    {"path": "/paper/position-quality-status", "category": "risk", "required": True},
    {"path": "/paper/journal-truth-status", "category": "journal", "required": True},
]

DIAGNOSTIC_REVIEW_SOURCE_HINTS = (
    "deep_scan",
    "ml_shadow",
    "feature_log",
    "feature_log[",
    "/data/state.json:deep_scan",
)


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _safe_list(obj: Any) -> List[Any]:
    return obj if isinstance(obj, list) else []


def _dedupe_endpoints(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for item in items:
        path = item.get("path")
        if path and path not in seen:
            out.append(item)
            seen.add(path)
    return out


def _parse_local_time(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        pass
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for suffix in (" CDT", " CST", " UTC", "Z"):
        text = text.replace(suffix, "")
    text = text.replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(text, fmt).timestamp()
        except Exception:
            continue
    return None


def _runner_freshness_cleanup(compact: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    skip_reason = payload.get("last_skip_reason")
    success_ts = payload.get("last_successful_run_ts") or _parse_local_time(payload.get("last_successful_run_local"))
    skip_ts = payload.get("last_skip_ts") or _parse_local_time(payload.get("last_skip_local"))
    stale = payload.get("stale_during_market")

    compact["last_skip_reason_raw"] = skip_reason
    compact["last_skip_reason_active"] = bool(skip_reason)

    # The old label is confusing when a newer successful run exists. Suppress it
    # in compact self-check output while preserving the raw value for debugging.
    newer_success_exists = success_ts is not None and (skip_ts is None or success_ts >= skip_ts)
    if skip_reason and newer_success_exists and stale is False:
        compact["last_skip_reason"] = None
        compact["last_skip_reason_active"] = False
        compact["last_skip_cleanup"] = "suppressed_old_skip_label_after_newer_success"
        compact["operator_note"] = "latest successful run is newer than the prior skip; skip label is informational only"
    return compact


def _compact_journal_truth(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(payload.get("execution_summary"))
    state_perf = _safe_dict(payload.get("state_performance"))
    return {
        "status": payload.get("status"),
        "type": payload.get("type"),
        "version": payload.get("version"),
        "generated_local": payload.get("generated_local"),
        "source_of_truth": summary.get("source_of_truth"),
        "summary_type": summary.get("summary_type"),
        "execution_rows_count": summary.get("execution_rows_count"),
        "journal_supplemental_execution_rows_count": summary.get("journal_supplemental_execution_rows_count"),
        "realized_reconciliation_delta": summary.get("realized_reconciliation_delta"),
        "realized_reconciliation_warning": summary.get("realized_reconciliation_warning"),
        "realized_today": state_perf.get("realized_pnl_today", summary.get("state_realized_pnl_today")),
        "realized_total": state_perf.get("realized_pnl_total", summary.get("state_realized_pnl_total")),
        "unrealized_pnl": state_perf.get("unrealized_pnl"),
        "wins_total": state_perf.get("wins_total", summary.get("wins_count")),
        "losses_total": state_perf.get("losses_total", summary.get("losses_count")),
        "open_positions_count": len(_safe_dict(state_perf.get("open_positions"))),
        "unknown_rows_count": summary.get("unknown_rows_count"),
        "review_rows_count": summary.get("review_rows_count"),
        "blocked_or_rejected_count": summary.get("blocked_or_rejected_count"),
        "profit_factor": summary.get("profit_factor"),
        "win_rate_pct": summary.get("win_rate_pct"),
    }


def _extract_truth_from_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in results:
        if row.get("path") == "/paper/journal-truth-status":
            compact = _safe_dict(row.get("compact"))
            if compact:
                return compact
    return {}


def _extract_runner_from_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in results:
        if row.get("path") == "/paper/runner-freshness":
            compact = _safe_dict(row.get("compact"))
            if compact:
                return compact
    return {}


def _extract_status_from_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    for row in results:
        if row.get("path") == "/paper/status":
            compact = _safe_dict(row.get("compact"))
            if compact:
                return compact
    return {}


def _postprocess_self_check_payload(payload: Dict[str, Any], self_check_module: Any) -> Dict[str, Any]:
    results = _safe_list(payload.get("results"))
    truth = _extract_truth_from_results(results)
    runner = _extract_runner_from_results(results)
    status = _extract_status_from_results(results)

    payload["reporting_cleanup_version"] = VERSION
    payload["single_best_link"] = getattr(self_check_module, "_full_url", lambda p: p)("/paper/self-check")
    payload["truth_summary"] = truth
    payload["operator_summary"] = {
        "overall": payload.get("overall"),
        "self_defense_active": _safe_dict(status.get("risk_controls")).get("self_defense_active"),
        "self_defense_reason": _safe_dict(status.get("risk_controls")).get("self_defense_reason"),
        "positions": status.get("positions"),
        "realized_today": truth.get("realized_today"),
        "realized_total": truth.get("realized_total"),
        "unrealized_pnl": truth.get("unrealized_pnl"),
        "reconciliation_delta": truth.get("realized_reconciliation_delta"),
        "runner_stale_during_market": runner.get("stale_during_market"),
        "runner_skip_label_active": runner.get("last_skip_reason_active"),
    }

    # Keep the output one-link-first. The raw link list is still available when
    # explicitly requested with SELF_CHECK_VERBOSE_LINKS=1.
    links = payload.pop("copy_paste_links_separate", []) or []
    payload["checked_links_count"] = len(links)
    payload["checked_paths"] = [str(link).replace(getattr(self_check_module, "BASE_URL", ""), "") for link in links]
    if str(os.environ.get("SELF_CHECK_VERBOSE_LINKS", "")).lower() in {"1", "true", "yes"}:
        payload["copy_paste_links_separate"] = links
    else:
        payload["copy_paste_links_separate"] = [payload["single_best_link"]]
        payload["debug_links_note"] = "Set SELF_CHECK_VERBOSE_LINKS=1 to return every checked URL."
    return payload


def patch_self_check(self_check_module: Any) -> Dict[str, Any]:
    global _PATCHED_SELF_CHECK
    if self_check_module is None:
        return {"status": "error", "patched": False, "reason": "self_check module missing"}
    if getattr(self_check_module, "_reporting_cleanup_patched", False):
        _PATCHED_SELF_CHECK = True
        return {"status": "ok", "patched": True, "already_patched": True, "version": VERSION}

    try:
        current = list(getattr(self_check_module, "LIGHT_ENDPOINTS", []))
        self_check_module.LIGHT_ENDPOINTS = _dedupe_endpoints(current + EXTRA_LIGHT_ENDPOINTS)

        original_compact = getattr(self_check_module, "_compact_payload")
        original_run = getattr(self_check_module, "run_self_check")
        original_test_links = getattr(self_check_module, "test_links_payload", None)

        def compact_payload(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
            compact = original_compact(path, payload)
            if "runner-freshness" in str(path):
                compact = _runner_freshness_cleanup(compact, _safe_dict(payload))
            elif "journal-truth" in str(path):
                compact = _compact_journal_truth(_safe_dict(payload))
            elif "state-io" in str(path):
                compact.update({
                    "protections": _safe_dict(payload).get("protections"),
                    "run_state": _safe_dict(payload).get("run_state"),
                    "state_quality": _safe_dict(payload).get("state_quality"),
                    "last_status_event": _safe_dict(payload).get("last_status_event"),
                })
            elif any(token in str(path) for token in ("classic-signal", "intraday-timing", "position-quality")):
                compact.update({
                    "mode": _safe_dict(payload).get("mode"),
                    "wrapped": _safe_dict(payload).get("wrapped"),
                    "settings": _safe_dict(payload).get("settings"),
                    "latest_decisions_count": len(_safe_list(_safe_dict(payload).get("latest_decisions"))),
                    "blocked_decisions_recent_count": len(_safe_list(_safe_dict(payload).get("blocked_decisions_recent"))),
                })
            return compact

        def run_self_check(flask_app: Any, mode: str = "light") -> Dict[str, Any]:
            payload = original_run(flask_app, mode=mode)
            if isinstance(payload, dict):
                return _postprocess_self_check_payload(payload, self_check_module)
            return payload

        def test_links_payload() -> Dict[str, Any]:
            if callable(original_test_links):
                payload = original_test_links()
            else:
                payload = {"status": "ok", "type": "test_links", "generated_local": _now_text()}
            if isinstance(payload, dict):
                payload["reporting_cleanup_version"] = VERSION
                payload["single_best_link"] = getattr(self_check_module, "_full_url", lambda p: p)("/paper/self-check")
                payload["note"] = "Use the single_best_link for routine testing. Full URL lists are debug-only."
                if str(os.environ.get("SELF_CHECK_VERBOSE_LINKS", "")).lower() not in {"1", "true", "yes"}:
                    payload["links_separate_light_debug_count"] = len(payload.pop("links_separate_light", []) or [])
                    payload["links_separate_full_bounded_debug_count"] = len(payload.pop("links_separate_full_bounded", []) or [])
            return payload

        self_check_module._compact_payload = compact_payload
        self_check_module.run_self_check = run_self_check
        self_check_module.test_links_payload = test_links_payload
        self_check_module.VERSION = VERSION
        self_check_module._reporting_cleanup_patched = True
        _PATCHED_SELF_CHECK = True
        return {"status": "ok", "patched": True, "version": VERSION, "light_endpoints_count": len(self_check_module.LIGHT_ENDPOINTS)}
    except Exception as exc:
        return {"status": "error", "patched": False, "version": VERSION, "error": str(exc)}


def patch_journal_truth(journal_truth_module: Any) -> Dict[str, Any]:
    global _PATCHED_JOURNAL_TRUTH
    if journal_truth_module is None:
        return {"status": "error", "patched": False, "reason": "journal_truth module missing"}
    if getattr(journal_truth_module, "_reporting_cleanup_patched", False):
        _PATCHED_JOURNAL_TRUTH = True
        return {"status": "ok", "patched": True, "already_patched": True, "version": VERSION}

    try:
        current_hints = tuple(getattr(journal_truth_module, "REVIEW_SOURCE_HINTS", ()))
        journal_truth_module.REVIEW_SOURCE_HINTS = tuple(dict.fromkeys(current_hints + DIAGNOSTIC_REVIEW_SOURCE_HINTS))
        original_is_review_row = getattr(journal_truth_module, "is_review_row")
        original_status_payload = getattr(journal_truth_module, "status_payload")

        def is_review_row(row: Any) -> bool:
            if not isinstance(row, dict):
                return True
            try:
                action = journal_truth_module._action(row)
                if action in getattr(journal_truth_module, "REAL_EXECUTION_ACTIONS", set()) and journal_truth_module._has_execution_fill_data(row, action):
                    return False
            except Exception:
                pass
            source = str(row.get("journal_source", "") or row.get("source", "")).lower()
            decision = str(row.get("decision", "") or "").lower().strip()
            if any(hint in source for hint in DIAGNOSTIC_REVIEW_SOURCE_HINTS):
                return True
            if decision in {"signal", "watch", "blocked", "rejected", "review", "shadow", "scan"}:
                return True
            if row.get("future_outcome_pending") is not None:
                return True
            return original_is_review_row(row)

        def status_payload() -> Dict[str, Any]:
            payload = original_status_payload()
            if isinstance(payload, dict):
                summary = _safe_dict(payload.get("execution_summary"))
                payload["reporting_cleanup"] = {
                    "version": VERSION,
                    "ml_shadow_feature_logs_classified_as_review": True,
                    "unknown_rows_count": summary.get("unknown_rows_count"),
                    "review_rows_count": summary.get("review_rows_count"),
                    "source_of_truth": summary.get("source_of_truth"),
                    "reconciliation_delta": summary.get("realized_reconciliation_delta"),
                    "reconciliation_warning": summary.get("realized_reconciliation_warning"),
                }
            return payload

        journal_truth_module.is_review_row = is_review_row
        journal_truth_module.status_payload = status_payload
        journal_truth_module.VERSION = VERSION
        journal_truth_module._reporting_cleanup_patched = True
        _PATCHED_JOURNAL_TRUTH = True
        return {"status": "ok", "patched": True, "version": VERSION, "review_hints_count": len(journal_truth_module.REVIEW_SOURCE_HINTS)}
    except Exception as exc:
        return {"status": "error", "patched": False, "version": VERSION, "error": str(exc)}


def apply(flask_app: Any | None = None, module: Any | None = None) -> Dict[str, Any]:
    results: Dict[str, Any] = {"status": "ok", "type": "reporting_cleanup_status", "version": VERSION, "generated_local": _now_text()}
    try:
        import journal_truth
        results["journal_truth"] = patch_journal_truth(journal_truth)
    except Exception as exc:
        results["journal_truth"] = {"status": "error", "patched": False, "error": str(exc)}
    try:
        import self_check
        results["self_check"] = patch_self_check(self_check)
    except Exception as exc:
        results["self_check"] = {"status": "error", "patched": False, "error": str(exc)}

    if flask_app is not None and id(flask_app) not in REGISTERED_APP_IDS:
        try:
            from flask import jsonify
            existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
            if "/paper/reporting-cleanup-status" not in existing:
                flask_app.add_url_rule("/paper/reporting-cleanup-status", "reporting_cleanup_status", lambda: jsonify(status()))
            REGISTERED_APP_IDS.add(id(flask_app))
        except Exception as exc:
            results["route_registration_error"] = str(exc)
    return results


def status() -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "reporting_cleanup_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "patched_self_check": _PATCHED_SELF_CHECK,
        "patched_journal_truth": _PATCHED_JOURNAL_TRUTH,
        "runner_skip_cleanup": "suppresses old skip labels in compact self-check output when a newer successful run exists",
        "journal_truth_cleanup": "classifies deep_scan/ml_shadow/feature_log rows as review diagnostics instead of unknown rows",
        "one_link_policy": "single_best_link is primary; verbose link lists require SELF_CHECK_VERBOSE_LINKS=1",
    }
