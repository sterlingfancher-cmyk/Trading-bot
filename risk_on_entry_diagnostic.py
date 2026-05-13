"""Risk-on participation entry diagnostics.

Adds an operator-facing diagnostic that explains why the bot did or did not add
positions while risk-on participation mode is active.

The diagnostic is intentionally read-only. It does not place trades, change
positions, or alter state. It summarizes recent blocked/rejected candidates from
state.json and trade_journal.json, classifies the blocking reasons, and patches
the benchmark/market-participation reports so the one-link check gives a clear
answer instead of only saying the bot is under-participating.
"""
from __future__ import annotations

import copy
import datetime as dt
import functools
import json
import math
import os
import sys
from collections import Counter
from typing import Any, Dict, List, Tuple

VERSION = "risk-on-entry-diagnostic-2026-05-13"

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
STATE_FILE = os.path.join(STATE_DIR, "state.json")
TRADE_JOURNAL_FILE = os.path.join(STATE_DIR, "trade_journal.json")

REGISTERED_APP_IDS: set[int] = set()
_APPLIED = False
_ORIGINAL_BUILD_SNAPSHOT = None

DEFAULT_ENTRY_FLOOR = float(os.environ.get("RISK_ON_ENTRY_SCORE_FLOOR", "0.024"))
RECENT_REVIEW_LIMIT = int(os.environ.get("RISK_ON_DIAGNOSTIC_REVIEW_LIMIT", "80"))
WATCHLIST_LIMIT = int(os.environ.get("RISK_ON_DIAGNOSTIC_WATCHLIST_LIMIT", "10"))

HARD_REASON_HINTS = (
    "self_defense",
    "halt",
    "cooldown",
    "late_day",
    "after_hours",
    "stop_loss",
    "max_loss",
    "max_daily_loss",
    "sector_exposure",
    "bucket_exposure",
    "not_regular_session",
)
TIMING_REASON_HINTS = (
    "extended_above",
    "extended_below",
    "waiting_for_pullback_reclaim",
    "pullback_reclaim",
    "above_5m_ma20",
    "below_5m_ma20",
    "max_from_day_open",
)
SOFT_SCORE_HINTS = (
    "entry_score_below_minimum",
    "score_below",
    "below_minimum",
    "required_score",
)
POSITION_LIMIT_HINTS = (
    "position_limit",
    "max_positions",
    "target_positions_met",
)
CATALYST_HINTS = (
    "no_catalyst_threshold",
    "catalyst",
    "volume_surge",
)
REVIEW_SOURCE_HINTS = (
    "blocked_entries",
    "rejected_signals",
    "scanner_audit",
    "entry_quality",
    "run_cycle:return",
    "weakest_position_for_rotation",
    "accepted_entries",
    "long_signals",
    "short_signals",
)
EXECUTION_ACTIONS = {"entry", "exit", "partial_exit", "reduce", "reduce_position", "scale_out"}


def _now_text() -> str:
    try:
        import pytz
        tz = pytz.timezone(os.environ.get("MARKET_TZ", "America/Chicago"))
        return dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        v = float(x)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default


def _load_json(path: str) -> Dict[str, Any]:
    for _ in range(3):
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
                return obj if isinstance(obj, dict) else {}
        except Exception:
            continue
    return {}


def _load_state(core: Any | None = None) -> Dict[str, Any]:
    try:
        if core is not None and hasattr(core, "load_state"):
            obj = core.load_state()
            return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    return _load_json(STATE_FILE)


def _action(row: Dict[str, Any]) -> str:
    return str(row.get("action", "") or "").strip().lower()


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol", "") or "").strip().upper()


def _side(row: Dict[str, Any]) -> str:
    return str(row.get("side", row.get("direction", "long")) or "long").strip().lower()


def _source(row: Dict[str, Any]) -> str:
    return str(row.get("journal_source", row.get("source", "")) or "").lower()


def _score(row: Dict[str, Any]) -> float:
    info = row.get("quality_info") if isinstance(row.get("quality_info"), dict) else {}
    return _f(row.get("score", info.get("score", 0.0)), 0.0)


def _stringify_reason(obj: Any) -> str:
    if isinstance(obj, dict):
        parts: List[str] = []
        for key in ("reason", "entry_block_reason", "pullback_reclaim_status", "status", "note"):
            if obj.get(key) not in (None, ""):
                parts.append(str(obj.get(key)))
        q = obj.get("quality_info")
        if isinstance(q, dict):
            parts.append(_stringify_reason(q))
        cpi = obj.get("controlled_pullback_info")
        if isinstance(cpi, dict):
            parts.append(_stringify_reason(cpi))
        catalyst = obj.get("catalyst")
        if isinstance(catalyst, dict):
            parts.append(_stringify_reason(catalyst))
        return " ".join(p for p in parts if p).strip()
    return str(obj or "").strip()


def _reason(row: Dict[str, Any]) -> str:
    reason = _stringify_reason(row)
    if not reason and isinstance(row.get("quality_info"), dict):
        reason = _stringify_reason(row.get("quality_info"))
    return reason.lower()


def _category(row: Dict[str, Any]) -> str:
    reason = _reason(row)
    if any(h in reason for h in HARD_REASON_HINTS):
        return "hard_risk_gate"
    if any(h in reason for h in TIMING_REASON_HINTS):
        return "timing_pullback_reclaim_wait"
    if any(h in reason for h in POSITION_LIMIT_HINTS):
        return "position_limit"
    if any(h in reason for h in SOFT_SCORE_HINTS):
        return "score_floor"
    if any(h in reason for h in CATALYST_HINTS):
        return "catalyst_or_volume_wait"
    if _action(row) in {"blocked", "rejected"} or "blocked" in _source(row) or "rejected" in _source(row):
        return "blocked_unknown_reason"
    if _score(row) > 0:
        return "review_candidate"
    return "unknown"


def _is_review_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    action = _action(row)
    source = _source(row)
    if action in EXECUTION_ACTIONS:
        return False
    if action in {"blocked", "rejected", "review", "watch", "signal"}:
        return True
    if any(h in source for h in REVIEW_SOURCE_HINTS):
        return True
    if row.get("quality_info") is not None or row.get("pullback_reclaim_status") is not None or row.get("catalyst") is not None:
        return True
    return False


def _recent_review_rows_from_journal(limit: int = RECENT_REVIEW_LIMIT) -> List[Dict[str, Any]]:
    journal = _load_json(TRADE_JOURNAL_FILE)
    rows = journal.get("trades", []) if isinstance(journal.get("trades"), list) else []
    review = [dict(row) for row in rows if _is_review_row(row)]
    return review[-limit:]


def _review_rows_from_cycle(result: Any) -> List[Dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    rows: List[Dict[str, Any]] = []
    for key in ("blocked_entries", "rejected_signals", "accepted_entries", "long_signals", "short_signals"):
        value = result.get(key)
        if isinstance(value, list):
            for idx, row in enumerate(value):
                if isinstance(row, dict):
                    copy_row = dict(row)
                    copy_row.setdefault("journal_source", f"run_cycle:{key}[{idx}]")
                    rows.append(copy_row)
                elif isinstance(row, str):
                    rows.append({"symbol": row, "journal_source": f"run_cycle:{key}[{idx}]", "reason": key})
    return rows


def _required_score(row: Dict[str, Any], fallback: float = DEFAULT_ENTRY_FLOOR) -> float:
    q = row.get("quality_info") if isinstance(row.get("quality_info"), dict) else {}
    return _f(q.get("required_score", row.get("required_score", fallback)), fallback)


def _compact_row(row: Dict[str, Any]) -> Dict[str, Any]:
    q = row.get("quality_info") if isinstance(row.get("quality_info"), dict) else {}
    catalyst = row.get("catalyst") if isinstance(row.get("catalyst"), dict) else {}
    return {
        "symbol": _symbol(row),
        "side": _side(row),
        "score": round(_score(row), 6),
        "required_score": round(_required_score(row), 6),
        "category": _category(row),
        "reason": (_reason(row) or "unknown")[:160],
        "bucket": row.get("bucket") or q.get("bucket"),
        "source": _source(row)[:90],
        "pullback_reclaim_status": row.get("pullback_reclaim_status") or q.get("pullback_reclaim_status"),
        "intraday_move_pct": catalyst.get("intraday_move_pct"),
        "volume_surge_ratio": catalyst.get("volume_surge_ratio"),
        "catalyst_active": catalyst.get("active"),
    }


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = (_symbol(row), _side(row), round(_score(row), 6), _category(row), _reason(row)[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _entry_eligible_under_risk_on(row: Dict[str, Any], open_slots: int) -> Tuple[bool, str]:
    if open_slots <= 0:
        return False, "no_open_position_slots"
    if _side(row) != "long":
        return False, "not_long_candidate"
    reason = _reason(row)
    if any(h in reason for h in HARD_REASON_HINTS):
        return False, "hard_risk_gate"
    if any(h in reason for h in TIMING_REASON_HINTS):
        return False, "needs_pullback_or_reclaim"
    if _score(row) < DEFAULT_ENTRY_FLOOR:
        return False, "below_risk_on_entry_floor"
    if _category(row) in {"position_limit"}:
        return False, "position_limit"
    return True, "eligible_if_next_cycle_still_confirms"


def _state_scanner_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    audit = state.get("scanner_audit") if isinstance(state.get("scanner_audit"), dict) else {}
    blocked_entries = audit.get("blocked_entries") if isinstance(audit.get("blocked_entries"), list) else []
    top_blocked = audit.get("top_blocked_symbols") if isinstance(audit.get("top_blocked_symbols"), list) else []
    return {
        "signals_found": audit.get("signals_found"),
        "blocked_entries_count": audit.get("blocked_entries_count", len(blocked_entries) if blocked_entries else None),
        "top_blocked_symbols": top_blocked[:15],
    }


def _snapshot_from_benchmark(core: Any | None = None) -> Dict[str, Any]:
    try:
        import benchmark_participation as bp
        fn = _ORIGINAL_BUILD_SNAPSHOT or getattr(bp, "build_snapshot")
        snap = fn(core, force=True)
        return snap if isinstance(snap, dict) else {}
    except Exception as exc:
        return {"status": "error", "error": str(exc), "risk_on_participation": {"active": False}}


def build_diagnostic(core: Any | None = None, snapshot: Dict[str, Any] | None = None, cycle_result: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = _load_state(core)
    snapshot = snapshot if isinstance(snapshot, dict) else _snapshot_from_benchmark(core)
    participation = snapshot.get("risk_on_participation") if isinstance(snapshot.get("risk_on_participation"), dict) else {}
    positions = snapshot.get("positions") if isinstance(snapshot.get("positions"), dict) else {}

    active = bool(participation.get("active"))
    target_long_positions = int(_f(participation.get("target_long_positions"), positions.get("long_count", 0)))
    current_long_count = int(_f(positions.get("long_count"), 0))
    open_slots = max(0, target_long_positions - current_long_count)
    checks = participation.get("checks") if isinstance(participation.get("checks"), dict) else {}

    rows = _review_rows_from_cycle(cycle_result) + _recent_review_rows_from_journal()
    rows = _dedupe_rows([row for row in rows if isinstance(row, dict)])
    compact = [_compact_row(row) for row in rows]
    category_counts = Counter(row["category"] for row in compact)
    symbol_counts = Counter(row["symbol"] for row in compact if row.get("symbol"))

    eligible: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    for row in rows:
        ok, why = _entry_eligible_under_risk_on(row, open_slots)
        c = _compact_row(row)
        c["risk_on_entry_diagnostic"] = why
        if ok:
            eligible.append(c)
        else:
            blocked.append(c)

    # Sort actionable candidates first: higher score, then closest to the entry floor.
    eligible.sort(key=lambda x: _f(x.get("score"), 0.0), reverse=True)
    blocked.sort(key=lambda x: (_f(x.get("score"), 0.0), x.get("symbol") or ""), reverse=True)
    timing_wait = [r for r in blocked if r.get("category") == "timing_pullback_reclaim_wait"]
    score_floor = [r for r in blocked if r.get("category") == "score_floor"]
    hard_gate = [r for r in blocked if r.get("category") == "hard_risk_gate"]

    if not active:
        failed_checks = [k for k, v in checks.items() if not v]
        headline = "Risk-on participation is not active, so add-on entries remain under standard controls."
        next_action = "Wait for all participation checks to pass before expanding beyond the current book."
        if failed_checks:
            next_action = "Failed participation checks: " + ", ".join(failed_checks)
    elif open_slots <= 0:
        headline = "Risk-on participation is active, but the target long-position count is already filled."
        next_action = "Hold current participation level; manage winners with partial exits and profit-locks."
    elif eligible:
        headline = "Risk-on participation is active and add-on slots are open; qualified candidates are present."
        next_action = "Next run cycle can allow the best eligible long setup(s) if benchmark and risk checks remain valid."
    elif timing_wait:
        headline = "Risk-on participation is active, but add-on candidates are waiting for pullback/reclaim timing."
        next_action = "Do not chase. Let the highest-score candidates reclaim acceptable moving-average distance, then allow entries."
    elif score_floor:
        headline = "Risk-on participation is active, but recent candidates are mostly below the risk-on score floor."
        next_action = "Keep scanning; do not lower the score floor until candidates show stronger confirmation."
    elif hard_gate:
        headline = "Risk-on participation is active, but hard risk gates blocked the latest candidates."
        next_action = "Keep hard gates intact; only soft score/timing blocks should be considered for override."
    elif rows:
        headline = "Risk-on participation is active, but recent review rows did not contain a clean add-on candidate."
        next_action = "Continue scanning; add an entry only when a candidate clears score, timing, and exposure rules."
    else:
        headline = "Risk-on participation is active, but no recent candidate diagnostics were found."
        next_action = "Verify run_cycle is logging blocked_entries/rejected_signals so the next no-entry decision is explainable."

    return {
        "status": "ok",
        "type": "risk_on_entry_diagnostic",
        "version": VERSION,
        "generated_local": _now_text(),
        "headline": headline,
        "next_action": next_action,
        "participation_state": {
            "risk_on_active": active,
            "target_long_positions": target_long_positions,
            "current_long_count": current_long_count,
            "open_additional_long_slots": open_slots,
            "new_entries_per_cycle": participation.get("new_entries_per_cycle"),
            "checks": checks,
            "thresholds": participation.get("thresholds"),
        },
        "scanner_summary": _state_scanner_summary(state),
        "recent_review_rows_analyzed": len(rows),
        "category_counts": dict(category_counts),
        "most_common_symbols": [{"symbol": sym, "count": count} for sym, count in symbol_counts.most_common(10)],
        "eligible_add_on_candidates": eligible[:WATCHLIST_LIMIT],
        "top_blocked_candidates": blocked[:WATCHLIST_LIMIT],
        "watch_for_pullback_reclaim": timing_wait[:WATCHLIST_LIMIT],
        "below_score_floor": score_floor[:WATCHLIST_LIMIT],
        "hard_gate_blocks": hard_gate[:WATCHLIST_LIMIT],
        "diagnostic_rules": {
            "risk_on_entry_floor": DEFAULT_ENTRY_FLOOR,
            "hard_reason_hints": list(HARD_REASON_HINTS),
            "timing_reason_hints": list(TIMING_REASON_HINTS),
            "score_reason_hints": list(SOFT_SCORE_HINTS),
            "note": "The diagnostic explains no-entry decisions; it does not override hard risk gates or force trades.",
        },
    }


def _patch_benchmark_build(core: Any | None = None) -> Dict[str, Any]:
    global _APPLIED, _ORIGINAL_BUILD_SNAPSHOT
    if _APPLIED:
        return {"status": "ok", "version": VERSION, "already_applied": True}
    try:
        import benchmark_participation as bp
        original = getattr(bp, "build_snapshot", None)
        if not callable(original):
            return {"status": "error", "version": VERSION, "error": "benchmark_participation.build_snapshot not found"}
        _ORIGINAL_BUILD_SNAPSHOT = original

        @functools.wraps(original)
        def wrapped_build_snapshot(*args, **kwargs):
            snap = original(*args, **kwargs)
            if isinstance(snap, dict):
                try:
                    core_arg = args[0] if args else core
                    snap["entry_participation_diagnostic"] = build_diagnostic(core_arg, snapshot=snap)
                except Exception as exc:
                    snap["entry_participation_diagnostic"] = {"status": "error", "type": "risk_on_entry_diagnostic", "version": VERSION, "error": str(exc)}
            return snap

        wrapped_build_snapshot._risk_on_entry_diagnostic_wrapped = True  # type: ignore[attr-defined]
        bp.build_snapshot = wrapped_build_snapshot
        _APPLIED = True
        return {"status": "ok", "version": VERSION, "patched": ["benchmark_participation.build_snapshot"]}
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": str(exc)}


def apply(core: Any | None = None) -> Dict[str, Any]:
    if core is None:
        for module in list(sys.modules.values()):
            if getattr(module, "app", None) is not None and hasattr(module, "load_state"):
                core = module
                break
    return _patch_benchmark_build(core)


def status_payload(core: Any | None = None) -> Dict[str, Any]:
    snap = _snapshot_from_benchmark(core)
    return build_diagnostic(core, snapshot=snap)


def register_routes(flask_app: Any, core: Any | None = None) -> Dict[str, Any]:
    from flask import jsonify

    patch = apply(core)
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing", "patch": patch}

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/risk-on-entry-diagnostic" not in existing:
        flask_app.add_url_rule("/paper/risk-on-entry-diagnostic", "risk_on_entry_diagnostic", lambda: jsonify(status_payload(core)))

    # Replace the existing market-participation view so this diagnostic appears
    # in the same endpoint Sterling already checks.
    try:
        import benchmark_participation as bp

        def market_participation_status_with_diagnostic():
            s = bp.build_snapshot(core, force=True)
            return jsonify({
                "status": "ok",
                "type": "market_participation_status",
                "version": getattr(bp, "VERSION", VERSION),
                "diagnostic_version": VERSION,
                "generated_local": s.get("generated_local"),
                "benchmark_summary": s.get("benchmarks"),
                "benchmark_data_missing": s.get("benchmark_data_missing"),
                "benchmark_data_stale": s.get("benchmark_data_stale"),
                "benchmark_data_ready": s.get("benchmark_data_ready"),
                "bot_alpha": s.get("alpha"),
                "risk_on_participation": s.get("risk_on_participation"),
                "positions": s.get("positions"),
                "entry_participation_diagnostic": s.get("entry_participation_diagnostic"),
                "recommended_actions": s.get("recommended_actions"),
            })

        flask_app.view_functions["market_participation_status"] = market_participation_status_with_diagnostic
    except Exception:
        pass

    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "registered": True, "patch": patch}
