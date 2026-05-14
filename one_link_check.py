"""One-test self-check policy patch.

Routine testing should use one URL only:
    /paper/self-check

This module keeps the important diagnostic endpoints inside that one check while
making the output one-link-first. It also promotes state/journal guard failures
and hidden endpoint status errors into the operator summary so a successful HTTP
200 cannot hide a bad internal diagnostic.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

VERSION = "one-test-policy-2026-05-14"

ONE_TEST_ROUTE = "/paper/self-check"
REPAIR_ROUTE = "/paper/state-journal-repair"

# Endpoints that are safe enough to be checked inside /paper/self-check.
# They are not separate routine tests for the operator.
ONE_TEST_ENDPOINTS = [
    {"path": "/paper/state-io-status", "category": "state", "required": False, "after": "/paper/state-recovery-status"},
    {"path": "/paper/classic-signal-status", "category": "risk", "required": True, "after": "/paper/risk-improvement-status"},
    {"path": "/paper/intraday-timing-status", "category": "risk", "required": True, "after": "/paper/classic-signal-status"},
    {"path": "/paper/position-quality-status", "category": "risk", "required": True, "after": "/paper/intraday-timing-status"},
    {"path": "/paper/benchmark-comparison", "category": "benchmark", "required": True, "after": "/paper/position-quality-status"},
    {"path": "/paper/market-participation-status", "category": "benchmark", "required": True, "after": "/paper/benchmark-comparison"},
    {"path": "/paper/risk-on-entry-diagnostic", "category": "benchmark", "required": True, "after": "/paper/market-participation-status"},
    {"path": "/paper/journal-truth-status", "category": "journal", "required": True, "after": "/paper/trade-event-hook-status"},
    {"path": "/paper/state-journal-guard-status", "category": "journal", "required": True, "after": "/paper/journal-truth-status"},
]


def _safe_dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _safe_list(obj: Any) -> List[Any]:
    return obj if isinstance(obj, list) else []


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).lower() in {"1", "true", "yes", "on"}


def _full_url(self_check_module: Any, path: str) -> str:
    fn = getattr(self_check_module, "_full_url", None)
    if callable(fn):
        try:
            return fn(path)
        except Exception:
            pass
    base = str(getattr(self_check_module, "BASE_URL", "https://trading-bot-clean.up.railway.app") or "").rstrip("/")
    if base and not base.startswith("http"):
        base = "https://" + base
    return f"{base}{path}" if base else path


def _add_endpoint(light: Any, endpoint: Dict[str, Any]) -> None:
    if not isinstance(light, list):
        return
    path = endpoint.get("path")
    if not path or any(isinstance(item, dict) and item.get("path") == path for item in light):
        return
    insert_at = len(light)
    after_path = endpoint.get("after")
    if after_path:
        for idx, item in enumerate(light):
            if isinstance(item, dict) and item.get("path") == after_path:
                insert_at = idx + 1
                break
    light.insert(insert_at, {k: v for k, v in endpoint.items() if k != "after"})


def _add_one_test_endpoints(self_check_module: Any) -> int:
    light = getattr(self_check_module, "LIGHT_ENDPOINTS", None)
    before = len(light) if isinstance(light, list) else 0
    for endpoint in ONE_TEST_ENDPOINTS:
        _add_endpoint(light, endpoint)
    return len(light) if isinstance(light, list) else before


def _compact_state_journal_guard(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": payload.get("status"),
        "type": payload.get("type"),
        "version": payload.get("version"),
        "repair_version": payload.get("repair_version"),
        "generated_local": payload.get("generated_local"),
        "active": payload.get("active"),
        "reconciliation_status": payload.get("reconciliation_status"),
        "safe_to_trade_guarded_symbols": payload.get("safe_to_trade_guarded_symbols"),
        "blocked_symbols": payload.get("blocked_symbols"),
        "repairable_symbols": payload.get("repairable_symbols"),
        "mismatch_count": payload.get("mismatch_count"),
        "operator_message": payload.get("operator_message"),
        "recommended_actions": payload.get("recommended_actions"),
        "repair_endpoint": payload.get("repair_endpoint"),
        "repair_requires": payload.get("repair_requires"),
        "direct_persist_patch_active": payload.get("direct_persist_patch_active"),
        "jsonsafe_patch_version": payload.get("jsonsafe_patch_version"),
        "stale_write_guard_status": payload.get("stale_write_guard_status"),
    }


def _extract_result(results: Iterable[Dict[str, Any]], path: str) -> Dict[str, Any]:
    for row in results:
        if isinstance(row, dict) and row.get("path") == path:
            return row
    return {}


def _extract_compact(results: Iterable[Dict[str, Any]], path: str) -> Dict[str, Any]:
    return _safe_dict(_extract_result(results, path).get("compact"))


def _derive_checked_paths(payload: Dict[str, Any]) -> List[str]:
    results = _safe_list(payload.get("results"))
    if results:
        return [str(row.get("path")) for row in results if isinstance(row, dict) and row.get("path")]
    paths = payload.get("checked_paths")
    if isinstance(paths, list):
        return [str(p) for p in paths]
    return []


def _append_warning(payload: Dict[str, Any], warning: Dict[str, Any]) -> None:
    warnings = _safe_list(payload.get("warnings"))
    key = (warning.get("path"), warning.get("error"))
    existing = {(w.get("path"), w.get("error")) for w in warnings if isinstance(w, dict)}
    if key not in existing:
        warnings.append(warning)
    payload["warnings"] = warnings


def _promote_hidden_status_errors(payload: Dict[str, Any]) -> List[str]:
    """Warn when a checked endpoint returns JSON status=error despite HTTP 200."""
    bad_required: List[str] = []
    bad_optional: List[str] = []
    for row in _safe_list(payload.get("results")):
        if not isinstance(row, dict):
            continue
        compact = _safe_dict(row.get("compact"))
        if compact.get("status") == "error":
            path = str(row.get("path") or "")
            target = bad_required if row.get("required") else bad_optional
            target.append(path)
            _append_warning(payload, {
                "path": path,
                "status_code": row.get("status_code"),
                "error": "endpoint returned JSON status=error inside self-check",
            })
    if bad_required:
        payload["overall"] = "warn" if payload.get("overall") != "fail" else payload.get("overall")
        if payload.get("status") == "ok":
            payload["status"] = "warn"
    payload["required_status_error_paths"] = bad_required
    payload["optional_status_error_paths"] = bad_optional
    return bad_required + bad_optional


def _promote_state_journal_guard(payload: Dict[str, Any]) -> Dict[str, Any]:
    results = _safe_list(payload.get("results"))
    guard = _extract_compact(results, "/paper/state-journal-guard-status")
    if not guard:
        return payload

    dashboard = _safe_dict(payload.get("dashboard"))
    dashboard["state_journal_guard"] = guard
    payload["dashboard"] = dashboard
    payload["state_journal_guard_summary"] = guard

    operator = _safe_dict(payload.get("operator_summary"))
    operator.update({
        "state_journal_guard_active": bool(guard.get("active")),
        "state_journal_guard_status": guard.get("reconciliation_status"),
        "state_journal_guard_message": guard.get("operator_message"),
        "guarded_blocked_symbols": guard.get("blocked_symbols") or [],
        "safe_to_trade_guarded_symbols": guard.get("safe_to_trade_guarded_symbols"),
    })
    payload["operator_summary"] = operator

    if guard.get("active") or guard.get("status") == "error":
        payload["overall"] = "warn" if payload.get("overall") != "fail" else payload.get("overall")
        if payload.get("status") == "ok":
            payload["status"] = "warn"
        _append_warning(payload, {
            "path": "/paper/state-journal-guard-status",
            "status_code": 200,
            "error": "state/journal guard is not clear" if guard.get("status") == "error" else "state/journal mismatch guard active; same-symbol trading is blocked until repaired",
            "blocked_symbols": guard.get("blocked_symbols") or [],
        })
    return payload


def _promote_position_truth_mismatch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Warn if /paper/status still shows open positions while journal truth says flat."""
    results = _safe_list(payload.get("results"))
    status = _extract_compact(results, "/paper/status")
    truth = payload.get("truth_summary") or _extract_compact(results, "/paper/journal-truth-status")
    if not isinstance(truth, dict):
        truth = {}
    positions = status.get("positions")
    status_count = len(positions) if isinstance(positions, list) else (len(positions.keys()) if isinstance(positions, dict) else 0)
    truth_count = truth.get("open_positions_count")
    if truth_count is not None and status_count != int(truth_count or 0):
        payload["overall"] = "warn" if payload.get("overall") != "fail" else payload.get("overall")
        if payload.get("status") == "ok":
            payload["status"] = "warn"
        _append_warning(payload, {
            "path": "/paper/status",
            "status_code": 200,
            "error": "status open-position count differs from journal-truth open-position count; rely on journal_truth/state_io until status refreshes",
            "status_positions_count": status_count,
            "journal_truth_open_positions_count": truth_count,
        })
        operator = _safe_dict(payload.get("operator_summary"))
        operator["status_vs_truth_position_mismatch"] = True
        operator["status_positions_count"] = status_count
        operator["journal_truth_open_positions_count"] = truth_count
        payload["operator_summary"] = operator
    return payload


def _enforce_one_test_output(payload: Dict[str, Any], self_check_module: Any) -> Dict[str, Any]:
    single = _full_url(self_check_module, ONE_TEST_ROUTE)
    checked_paths = _derive_checked_paths(payload)

    payload["one_test_policy_version"] = VERSION
    payload["single_best_link"] = single
    payload["normal_test_link"] = single
    payload["routine_test_policy"] = {
        "routine_test_url": single,
        "routine_testing_rule": "Use only /paper/self-check after normal pushes.",
        "extra_links_required": False,
        "exception": "Use the repair endpoint only when intentionally applying a mutating state repair.",
        "repair_endpoint": REPAIR_ROUTE,
    }
    payload["checked_links_count"] = len(checked_paths)
    payload["checked_paths"] = checked_paths

    # Keep the normal copy/paste area clean. Verbose mode remains available for debugging,
    # but the default operator workflow is one link.
    if _truthy_env("SELF_CHECK_VERBOSE_LINKS"):
        payload["copy_paste_links_separate"] = [_full_url(self_check_module, p) for p in checked_paths]
        payload["debug_links_note"] = "Verbose mode is on; routine testing still uses single_best_link."
    else:
        payload["copy_paste_links_separate"] = [single]
        payload["debug_links_note"] = "One-test mode: checked paths are internal; copy/paste only single_best_link. Set SELF_CHECK_VERBOSE_LINKS=1 only for debugging."

    if "heavy_links_separate_not_auto_run" in payload:
        payload["optional_heavy_diagnostic_links_note"] = "Heavy diagnostic links are optional and are not part of routine post-push testing."
    return payload


def _postprocess_one_test_payload(payload: Dict[str, Any], self_check_module: Any) -> Dict[str, Any]:
    payload = _enforce_one_test_output(payload, self_check_module)
    payload = _promote_state_journal_guard(payload)
    payload = _promote_position_truth_mismatch(payload)
    _promote_hidden_status_errors(payload)
    return payload


def _patch_self_check(self_check_module: Any) -> None:
    if getattr(self_check_module, "_one_test_policy_patched", False):
        return

    original_compact = getattr(self_check_module, "_compact_payload", None)
    original_run = getattr(self_check_module, "run_self_check", None)
    original_test_links = getattr(self_check_module, "test_links_payload", None)
    if not callable(original_compact) or not callable(original_run):
        return

    def compact_payload(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        compact = original_compact(path, payload)
        if str(path) == "/paper/state-journal-guard-status":
            compact.update(_compact_state_journal_guard(_safe_dict(payload)))
        return compact

    def run_self_check(flask_app: Any, mode: str = "light") -> Dict[str, Any]:
        payload = original_run(flask_app, mode=mode)
        if isinstance(payload, dict):
            return _postprocess_one_test_payload(payload, self_check_module)
        return payload

    def test_links_payload() -> Dict[str, Any]:
        single = _full_url(self_check_module, ONE_TEST_ROUTE)
        payload = original_test_links() if callable(original_test_links) else {"status": "ok", "type": "test_links"}
        if not isinstance(payload, dict):
            payload = {"status": "ok", "type": "test_links"}
        payload["version"] = VERSION
        payload["single_best_link"] = single
        payload["normal_test_link"] = single
        payload["routine_test_policy"] = {
            "routine_test_url": single,
            "routine_testing_rule": "Use only /paper/self-check after normal pushes.",
            "extra_links_required": False,
            "exception": "Use /paper/state-journal-repair only when intentionally applying a mutating repair.",
        }
        if not _truthy_env("SELF_CHECK_VERBOSE_LINKS"):
            payload.pop("links_separate_light", None)
            payload.pop("links_separate_full_bounded", None)
            payload["debug_links_note"] = "Verbose link lists are hidden by default to preserve the one-test workflow."
        return payload

    self_check_module._compact_payload = compact_payload
    self_check_module.run_self_check = run_self_check
    self_check_module.test_links_payload = test_links_payload
    self_check_module.VERSION = VERSION
    self_check_module._one_test_policy_patched = True


def apply(self_check_module: Any = None) -> Dict[str, Any]:
    try:
        if self_check_module is None:
            import self_check as self_check_module  # type: ignore[no-redef]
        light_count = _add_one_test_endpoints(self_check_module)
        _patch_self_check(self_check_module)
        return {
            "status": "ok",
            "version": VERSION,
            "single_best_link": ONE_TEST_ROUTE,
            "routine_testing_rule": "Use only /paper/self-check after normal pushes.",
            "extra_links_required": False,
            "mutating_repair_exception": REPAIR_ROUTE,
            "light_endpoints_count": light_count,
            "journal_truth_in_self_check": True,
            "state_journal_guard_in_self_check": True,
            "state_journal_guard_truth_in_operator_summary": True,
            "hidden_status_errors_promoted_to_warning": True,
            "status_vs_truth_position_mismatch_warning": True,
        }
    except Exception as exc:
        return {
            "status": "error",
            "version": VERSION,
            "single_best_link": ONE_TEST_ROUTE,
            "error": str(exc),
        }


def register_routes(flask_app: Any = None, module: Any = None) -> Dict[str, Any]:
    # Nothing new to register. This module patches self_check's existing route list.
    try:
        import self_check
        return apply(self_check)
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": str(exc)}
