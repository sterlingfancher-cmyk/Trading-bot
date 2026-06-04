"""State-size watchdog and conservative telemetry retention.

Governance/safety layer for persistent state growth. It preserves source-of-truth
account/trading data and only trims or thins derived telemetry/diagnostic data.

This module does not trade, resize, change risk controls, grant ML authority, or
change post-harvest thresholds.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "state-size-watchdog-2026-06-04-v2-retention-policy"
ENABLED = os.environ.get("STATE_SIZE_WATCHDOG_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
AUTO_COMPACT_ENABLED = os.environ.get("STATE_SIZE_AUTO_COMPACT_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
COMPACT_MB = float(os.environ.get("STATE_SIZE_COMPACT_MB", "15"))
WATCH_MB = float(os.environ.get("STATE_SIZE_WATCH_MB", "20"))
WARN_MB = float(os.environ.get("STATE_SIZE_WARN_MB", "25"))
CRITICAL_MB = float(os.environ.get("STATE_SIZE_CRITICAL_MB", "35"))
ML2_DATASET_MAX_ROWS = int(os.environ.get("STATE_SIZE_ML2_DATASET_MAX_ROWS", "6000"))
ML2_FULL_RECENT_ROWS = int(os.environ.get("STATE_SIZE_ML2_FULL_RECENT_ROWS", "1500"))
SCANNER_LIST_LIMIT = int(os.environ.get("STATE_SIZE_SCANNER_LIST_LIMIT", "100"))
REPORT_HISTORY_LIMIT = int(os.environ.get("STATE_SIZE_REPORT_HISTORY_LIMIT", "30"))
PATH_ARCHIVE_LIMIT = int(os.environ.get("STATE_SIZE_PATH_ARCHIVE_LIMIT", "300"))
ADVISORY_TAIL_LIMIT = int(os.environ.get("STATE_SIZE_ADVISORY_TAIL_LIMIT", "75"))
HISTORY_LIMIT = int(os.environ.get("STATE_SIZE_HISTORY_LIMIT", "2000"))
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
_IN_SAVE = False

ML2_KEEP_KEYS = {
    "symbol", "side", "decision", "decision_seen", "bucket", "sector", "score",
    "rule_score", "entry_floor", "score_edge", "date", "local_date", "timestamp",
    "ts", "regime", "regime_family", "regime_subtype", "regime_signature",
    "signal_cluster", "risk_state", "feature_quality", "feature_quality_score",
    "future_win", "future_pnl_pct", "future_outcome_pending", "outcome_label",
    "pnl_dollars", "pnl_pct", "journal_schema_version", "row_compacted",
}


def _module() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
            return mod
    return None


def _now(mod: Any = None) -> str:
    try:
        return mod.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _state_path(mod: Any = None) -> str:
    candidates = []
    if mod is not None:
        for key in ("STATE_FILE", "STATE_PATH", "state_file"):
            value = getattr(mod, key, None)
            if value:
                candidates.append(str(value))
    candidates.extend([os.environ.get("STATE_FILE", ""), os.environ.get("STATE_PATH", ""), "/data/state.json", "state.json"])
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return candidates[0] if candidates and candidates[0] else "/data/state.json"


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _module()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return (state if isinstance(state, dict) else {}), mod


def _json_bytes(value: Any) -> int:
    try:
        return len(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8"))
    except Exception:
        return 0


def _cap_list(value: Any, limit: int) -> Tuple[Any, int]:
    if not isinstance(value, list) or len(value) <= limit:
        return value, 0
    return value[-limit:], len(value) - limit


def _thin_row(row: Any) -> Any:
    if not isinstance(row, dict) or row.get("row_compacted"):
        return row
    out = {k: v for k, v in row.items() if k in ML2_KEEP_KEYS}
    features = row.get("mae_mfe_features")
    if isinstance(features, dict):
        out["mae_mfe_features"] = {k: features.get(k) for k in ("mae_pct", "mfe_pct", "path_efficiency", "path_quality_signal", "ml_feature_ready") if features.get(k) is not None}
    missing = row.get("feature_missing_fields")
    if isinstance(missing, list) and missing:
        out["feature_missing_fields"] = missing[:12]
    out["row_compacted"] = True
    return out


def _compact_ml2(state: Dict[str, Any], actions: List[Dict[str, Any]]) -> None:
    ml2 = state.get("ml_phase2")
    if not isinstance(ml2, dict):
        return
    dataset = ml2.get("dataset")
    if isinstance(dataset, list):
        original_len = len(dataset)
        if len(dataset) > ML2_DATASET_MAX_ROWS:
            dataset = dataset[-ML2_DATASET_MAX_ROWS:]
            actions.append({"section": "ml_phase2.dataset", "action": "cap_rows", "removed": original_len - len(dataset), "kept": len(dataset)})
        if len(dataset) > ML2_FULL_RECENT_ROWS:
            split_at = len(dataset) - ML2_FULL_RECENT_ROWS
            thinned = 0
            new_rows = []
            for idx, row in enumerate(dataset):
                if idx < split_at:
                    new_row = _thin_row(row)
                    thinned += 1 if isinstance(new_row, dict) and new_row.get("row_compacted") and new_row is not row else 0
                    new_rows.append(new_row)
                else:
                    new_rows.append(row)
            dataset = new_rows
            if thinned:
                actions.append({"section": "ml_phase2.dataset", "action": "thin_old_rows", "rows_thinned": thinned, "full_recent_rows": ML2_FULL_RECENT_ROWS})
        ml2["dataset"] = dataset
        ml2["rows_total"] = max(int(ml2.get("rows_total") or 0), original_len, len(dataset))
    for key in ("last_predictions", "top_shadow_predictions", "recent_predictions"):
        capped, removed = _cap_list(ml2.get(key), 75)
        if removed:
            ml2[key] = capped
            actions.append({"section": f"ml_phase2.{key}", "action": "cap_rows", "removed": removed, "kept": len(capped)})


def _compact_list_fields(container: Dict[str, Any], prefix: str, keys: Tuple[str, ...], limit: int, actions: List[Dict[str, Any]]) -> None:
    for key in keys:
        capped, removed = _cap_list(container.get(key), limit)
        if removed:
            container[key] = capped
            actions.append({"section": f"{prefix}.{key}", "action": "cap_rows", "removed": removed, "kept": len(capped)})


def compact_state(state: Dict[str, Any], mod: Any = None, force: bool = False) -> Dict[str, Any]:
    before = _json_bytes(state)
    before_mb = round(before / (1024 * 1024), 3)
    actions: List[Dict[str, Any]] = []
    should_compact = bool(force or (AUTO_COMPACT_ENABLED and before_mb >= COMPACT_MB))
    if isinstance(state, dict) and should_compact:
        _compact_ml2(state, actions)
        scanner = state.get("scanner_audit")
        if isinstance(scanner, dict):
            _compact_list_fields(scanner, "scanner_audit", ("accepted_entries", "blocked_entries", "rejected_signals", "long_signals", "short_signals", "notes"), SCANNER_LIST_LIMIT, actions)
        reports = state.get("reports")
        if isinstance(reports, dict):
            _compact_list_fields(reports, "reports", ("intraday_history", "daily_history"), REPORT_HISTORY_LIMIT, actions)
        paths = state.get("intratrade_path_capture")
        if isinstance(paths, dict):
            _compact_list_fields(paths, "intratrade_path_capture", ("closed_path_archive",), PATH_ARCHIVE_LIMIT, actions)
        mae = state.get("mae_mfe_integration")
        if isinstance(mae, dict):
            _compact_list_fields(mae, "mae_mfe_integration", ("closed_recommendations_tail", "closed_features_tail", "active_recommendations", "active_features"), ADVISORY_TAIL_LIMIT, actions)
        for section_name in ("adaptive_ml_research", "adaptive_portfolio_intelligence", "strategy_scorecard", "strategy_promotion_readiness", "trade_quality_telemetry"):
            section = state.get(section_name)
            if isinstance(section, dict):
                for key, value in list(section.items()):
                    if isinstance(value, list):
                        capped, removed = _cap_list(value, ADVISORY_TAIL_LIMIT)
                        if removed:
                            section[key] = capped
                            actions.append({"section": f"{section_name}.{key}", "action": "cap_rows", "removed": removed, "kept": len(capped)})
        history, removed = _cap_list(state.get("history"), HISTORY_LIMIT)
        if removed:
            state["history"] = history
            actions.append({"section": "history", "action": "cap_rows_generous", "removed": removed, "kept": len(history)})
    after = _json_bytes(state)
    after_mb = round(after / (1024 * 1024), 3)
    level = "critical" if after_mb >= CRITICAL_MB else "warn" if after_mb >= WARN_MB else "watch" if after_mb >= WATCH_MB else "ok"
    recommendation = "State size is within current telemetry-growth limits."
    if level == "watch":
        recommendation = "State is in watch range; conservative compaction is active."
    elif level == "warn":
        recommendation = "State is above warning threshold; avoid new large telemetry until size stabilizes."
    elif level == "critical":
        recommendation = "State is critical; prioritize retention tightening before more telemetry expansion."
    summary = {
        "status": "ok",
        "type": "state_size_watchdog",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "auto_compact_enabled": AUTO_COMPACT_ENABLED,
        "before_mb_estimated": before_mb,
        "after_mb_estimated": after_mb,
        "saved_mb_estimated": round(max(0, before - after) / (1024 * 1024), 3),
        "level": level,
        "recommendation": recommendation,
        "compacted_this_cycle": bool(actions),
        "actions_count": len(actions),
        "actions": actions[:25],
        "thresholds": {"compact_mb": COMPACT_MB, "watch_mb": WATCH_MB, "warn_mb": WARN_MB, "critical_mb": CRITICAL_MB},
        "retention_policy": {
            "ml2_dataset_max_rows": ML2_DATASET_MAX_ROWS,
            "ml2_full_recent_rows": ML2_FULL_RECENT_ROWS,
            "scanner_list_limit": SCANNER_LIST_LIMIT,
            "report_history_limit": REPORT_HISTORY_LIMIT,
            "path_archive_limit": PATH_ARCHIVE_LIMIT,
            "advisory_tail_limit": ADVISORY_TAIL_LIMIT,
            "history_limit_generous": HISTORY_LIMIT,
            "trades_pruned": False,
            "positions_pruned": False,
            "risk_controls_modified": False,
            "ml_authority_changed": False,
            "trading_authority_changed": False,
        },
        "live_authority": False,
    }
    try:
        state["state_size_watchdog"] = summary
    except Exception:
        pass
    return summary


def _section_lengths(state: Dict[str, Any]) -> Dict[str, Any]:
    sections = {}
    for key in ("trades", "history", "ml_phase2", "ml_phase25", "ml_feature_journal_quality", "trade_quality_telemetry", "intratrade_path_capture", "mae_mfe_integration", "adaptive_ml_research", "adaptive_portfolio_intelligence", "scanner_audit", "reports"):
        value = state.get(key)
        if isinstance(value, list):
            sections[key] = {"kind": "list", "rows": len(value)}
        elif isinstance(value, dict):
            item = {"kind": "dict", "keys": len(value)}
            if isinstance(value.get("dataset"), list):
                rows = value.get("dataset")
                item["dataset_rows"] = len(rows)
                item["dataset_compacted_rows"] = sum(1 for r in rows if isinstance(r, dict) and r.get("row_compacted"))
            if isinstance(value.get("paths"), dict):
                item["paths"] = len(value.get("paths"))
            if isinstance(value.get("closed_path_archive"), list):
                item["closed_path_archive_rows"] = len(value.get("closed_path_archive"))
            sections[key] = item
    return sections


def payload(state: Dict[str, Any] | None = None, mod: Any = None) -> Dict[str, Any]:
    if state is None:
        state, mod = _load_state(mod)
    mod = mod or _module()
    path = _state_path(mod)
    size_bytes = os.path.getsize(path) if path and os.path.exists(path) else 0
    size_mb = round(size_bytes / (1024 * 1024), 3)
    summary = state.get("state_size_watchdog") if isinstance(state, dict) else None
    if not isinstance(summary, dict):
        summary = compact_state(state if isinstance(state, dict) else {}, mod, force=False)
    summary = dict(summary)
    summary.update({"state_file": path, "state_size_bytes": size_bytes, "state_size_mb": size_mb, "section_lengths": _section_lengths(state if isinstance(state, dict) else {})})
    return summary


def apply(module: Any = None) -> Dict[str, Any]:
    global _IN_SAVE
    module = module or _module()
    if module is None:
        return {"status": "not_applied", "version": VERSION, "reason": "module_missing"}
    if id(module) in PATCHED_MODULE_IDS:
        return {"status": "ok", "version": VERSION, "already_patched": True, "live_authority": False}
    try:
        original = getattr(module, "save_state", None)
        if callable(original):
            def patched_save_state(state):
                global _IN_SAVE
                if _IN_SAVE:
                    return original(state)
                try:
                    _IN_SAVE = True
                    if ENABLED and isinstance(state, dict):
                        compact_state(state, module, force=False)
                    return original(state)
                except Exception as exc:
                    try:
                        if isinstance(state, dict):
                            state.setdefault("state_size_watchdog", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                    return original(state)
                finally:
                    _IN_SAVE = False
            patched_save_state._state_size_watchdog_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "STATE_SIZE_WATCHDOG_VERSION", VERSION)
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(module))
    return {"status": "ok", "version": VERSION, "enabled": ENABLED, "auto_compact_enabled": AUTO_COMPACT_ENABLED, "live_authority": False}


def register_routes(flask_app: Any, module: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    module = module or _module()
    apply(module)
    if id(flask_app) in REGISTERED_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        state, mod = _load_state(module)
        return jsonify(payload(state, mod))

    if "/paper/state-size-watchdog" not in existing:
        flask_app.add_url_rule("/paper/state-size-watchdog", "paper_state_size_watchdog", status_route)
    if "/paper/telemetry-retention-status" not in existing:
        flask_app.add_url_rule("/paper/telemetry-retention-status", "paper_telemetry_retention_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/state-size-watchdog", "/paper/telemetry-retention-status"], "live_authority": False}


try:
    apply(_module())
except Exception:
    pass
