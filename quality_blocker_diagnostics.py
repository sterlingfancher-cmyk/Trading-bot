from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "quality-blocker-diagnostics-2026-06-29-v1"
REGISTERED_APP_IDS: set[int] = set()

MIN_RAW_SCORE = float(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MIN_RAW_SCORE", "0.0135"))
MIN_RANK_SCORE = float(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MIN_RANK_SCORE", "0.0190"))
BORDERLINE_SCORE_BAND_PCT = float(os.environ.get("QUALITY_BLOCKER_BORDERLINE_SCORE_BAND_PCT", "0.05"))
MAX_ROWS = int(os.environ.get("QUALITY_BLOCKER_DIAGNOSTICS_MAX_ROWS", "25"))
DYNAMIC_DISCOVERY_REASONS = {"dynamic_discovery_block", "relative_strength_leader_exception_block", "dynamic_discovery_rejected"}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "load_state"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
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


def _portfolio(core: Any) -> Dict[str, Any]:
    try:
        pf = getattr(core, "portfolio", {}) or {}
        return pf if isinstance(pf, dict) else {}
    except Exception:
        return {}


def _load_state(core: Any) -> Dict[str, Any]:
    try:
        fn = getattr(core, "load_state", None)
        if callable(fn):
            state = fn()
            return state if isinstance(state, dict) else {}
    except Exception:
        pass
    return {}


def _scanner_rows(core: Any) -> List[Dict[str, Any]]:
    pf = _portfolio(core)
    state = _load_state(core)
    containers = [pf.get("scanner_audit"), state.get("scanner_audit"), pf.get("blocked_entry_reason_audit"), state.get("blocked_entry_reason_audit")]
    rows: List[Dict[str, Any]] = []
    for obj in containers:
        if not isinstance(obj, dict):
            continue
        for key in ("blocked_rows", "visible_blocked_rows", "rejected_signals", "blocked_entries", "rows", "signals"):
            value = obj.get(key)
            if isinstance(value, list):
                rows.extend([row for row in value if isinstance(row, dict)])
    return rows


def _latest_starter(core: Any) -> Dict[str, Any]:
    pf = _portfolio(core)
    state = _load_state(core)
    for obj in (pf.get("controlled_redeployment_starter_sleeve"), state.get("controlled_redeployment_starter_sleeve"), pf.get("core_entry_pipeline"), state.get("core_entry_pipeline")):
        if isinstance(obj, dict):
            latest = obj.get("latest") if isinstance(obj.get("latest"), dict) else obj
            if isinstance(latest, dict):
                return latest
    return {}


def _score_floor(row: Dict[str, Any]) -> Dict[str, Any]:
    score = _safe_float(row.get("score"), 0.0)
    rank_score = _safe_float(row.get("rank_score", row.get("core_entry_rank_score", score)), score)
    raw_gap = max(0.0, MIN_RAW_SCORE - score)
    rank_gap = max(0.0, MIN_RANK_SCORE - rank_score)
    raw_gap_pct = raw_gap / MIN_RAW_SCORE if MIN_RAW_SCORE > 0 else 0.0
    rank_gap_pct = rank_gap / MIN_RANK_SCORE if MIN_RANK_SCORE > 0 else 0.0
    failed = []
    if raw_gap > 0.0:
        failed.append("raw_score")
    if rank_gap > 0.0:
        failed.append("rank_score")
    return {
        "symbol": str(row.get("symbol") or row.get("ticker") or "").upper(),
        "side": str(row.get("side") or "long").lower(),
        "reason": row.get("reason") or row.get("rule_reason") or row.get("quality_reason"),
        "score": round(score, 6),
        "rank_score": round(rank_score, 6),
        "required_raw_score": round(MIN_RAW_SCORE, 6),
        "raw_score_gap": round(raw_gap, 6),
        "raw_score_gap_pct": round(raw_gap_pct * 100.0, 3),
        "required_rank_score": round(MIN_RANK_SCORE, 6),
        "rank_score_gap": round(rank_gap, 6),
        "rank_score_gap_pct": round(rank_gap_pct * 100.0, 3),
        "failed_floors": failed,
        "borderline_band_pct": round(BORDERLINE_SCORE_BAND_PCT * 100.0, 3),
        "borderline_quality_miss": bool(failed) and max(raw_gap_pct, rank_gap_pct) <= BORDERLINE_SCORE_BAND_PCT,
    }


def _dynamic_info(row: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("symbol", "side", "reason", "rule_reason", "quality_reason", "block_reason", "entry_block_reason", "scanner_reason", "daily_promotion_reason", "promotion_reason", "decision", "source", "bucket", "sector", "dynamic_discovery", "dynamic_discovery_info", "relative_strength_leader_exception", "relative_strength_leader_exception_info")
    info = {key: row.get(key) for key in keys if key in row}
    quality = row.get("quality_info")
    if isinstance(quality, dict):
        for key in keys:
            if key in quality:
                info[f"quality_info.{key}"] = quality.get(key)
    valve = row.get("participation_valve")
    if isinstance(valve, dict):
        for key in keys:
            if key in valve:
                info[f"participation_valve.{key}"] = valve.get(key)
    reasons = [str(value) for key, value in info.items() if "reason" in key and value]
    info["dynamic_discovery_reason_seen"] = any(reason in DYNAMIC_DISCOVERY_REASONS for reason in reasons)
    if not info:
        info["diagnostic_note"] = "no_row_level_dynamic_discovery_metadata_available"
    return info


def _collect_rows(core: Any) -> List[Dict[str, Any]]:
    latest = _latest_starter(core)
    rows: List[Dict[str, Any]] = []
    for key in ("rejected_preview", "score_floor_diagnostics", "borderline_quality_misses", "dynamic_discovery_diagnostics"):
        value = latest.get(key)
        if isinstance(value, list):
            rows.extend([row for row in value if isinstance(row, dict)])
    rows.extend(_scanner_rows(core))
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        ident = (row.get("symbol") or row.get("ticker"), row.get("side"), row.get("reason") or row.get("rule_reason") or row.get("quality_reason"), row.get("score"), row.get("rank_score") or row.get("core_entry_rank_score"))
        if ident in seen:
            continue
        seen.add(ident)
        deduped.append(row)
    return deduped[:MAX_ROWS]


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    rows = _collect_rows(core) if core is not None else []
    score_rows = [_score_floor(row) for row in rows if any(key in row for key in ("score", "rank_score", "core_entry_rank_score"))]
    borderline = [row for row in score_rows if row.get("borderline_quality_miss")]
    dynamic_rows = []
    for row in rows:
        reason = str(row.get("reason") or row.get("rule_reason") or row.get("quality_reason") or "")
        info = _dynamic_info(row)
        if reason in DYNAMIC_DISCOVERY_REASONS or info.get("dynamic_discovery_reason_seen"):
            dynamic_rows.append(info)
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "quality_blocker_diagnostics_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": True,
        "paper_context": os.environ.get("LIVE_TRADING_ENABLED", "false").lower() not in {"1", "true", "yes", "on"},
        "policy": {
            "advisory_only": True,
            "does_not_place_trades": True,
            "does_not_change_live_authority": True,
            "does_not_change_ml_authority": True,
            "does_not_lower_thresholds": True,
            "logs_score_floor_gap": True,
            "logs_borderline_quality_misses": True,
            "logs_dynamic_discovery_metadata": True,
            "borderline_score_band_pct": round(BORDERLINE_SCORE_BAND_PCT * 100.0, 3),
            "max_rows": MAX_ROWS,
        },
        "summary": {
            "rows_reviewed": len(rows),
            "score_floor_rows": len(score_rows),
            "borderline_quality_misses": len(borderline),
            "dynamic_discovery_rows": len(dynamic_rows),
            "next_actions": [
                "Use score_floor_gap fields to see whether score_below_post_harvest_floor misses are tiny or material.",
                "Use borderline_quality_misses as evidence only; do not lower thresholds from one sample.",
                "Use dynamic_discovery_rows to separate true dynamic-discovery rejects from unclassified rows.",
            ],
        },
        "score_floor_diagnostics": score_rows[:MAX_ROWS],
        "borderline_quality_misses": borderline[:MAX_ROWS],
        "dynamic_discovery_diagnostics": dynamic_rows[:MAX_ROWS],
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return status_payload(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    if "/paper/quality-blocker-diagnostics-status" not in existing:
        flask_app.add_url_rule("/paper/quality-blocker-diagnostics-status", "quality_blocker_diagnostics_status", lambda: jsonify(status_payload(core or _mod())))
    REGISTERED_APP_IDS.add(id(flask_app))


try:
    apply(_mod())
except Exception:
    pass
