"""Execution-only journal truth layer.

This module fixes the journal reporting problem where advisory/diagnostic rows
from helpers such as weakest_position_for_rotation:return can be counted like
real trades. It does not delete journal rows. Instead, it classifies rows into:

- execution rows: actual entry / exit / partial_exit / reduce_position events
- review rows: rotation-review, weakest-position, scanner, blocked/rejected,
  and other non-execution diagnostics

Important: some current deployments keep actual execution rows in state.json
while trade_journal.json contains many mirrored diagnostic rows. To keep the
reported realized stats honest, this module reconciles execution rows from both
trade_journal.json and state.json, then deduplicates them before calculating
execution-only performance.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Dict, List, Tuple

VERSION = "journal-truth-state-reconciled-2026-05-11"

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
TRADE_JOURNAL_FILE = os.path.join(STATE_DIR, "trade_journal.json")
STATE_FILE = os.path.join(STATE_DIR, "state.json")

REGISTERED_APP_IDS: set[int] = set()
_ORIGINAL_SUMMARY = None
_PATCHED = False

REAL_EXECUTION_ACTIONS = {"entry", "exit", "partial_exit", "reduce", "reduce_position", "scale_out"}
ENTRY_ACTIONS = {"entry"}
EXIT_ACTIONS = {"exit", "partial_exit", "reduce", "reduce_position", "scale_out"}
REVIEW_ACTIONS = {"blocked", "rejected", "rotation", "review", "watch", "signal"}
REVIEW_SOURCE_HINTS = (
    "weakest_position_for_rotation",
    "scanner_audit",
    "blocked_entries",
    "rejected_signals",
    "accepted_entries",
    "long_signals",
    "short_signals",
    "journal_summary",
    "performance.open_positions",
    "return:",
)


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _action(row: Dict[str, Any]) -> str:
    return str(row.get("action", "")).strip().lower()


def _source(row: Dict[str, Any]) -> str:
    return str(row.get("journal_source", "") or row.get("source", "")).lower()


def _time_value(row: Dict[str, Any]) -> Any:
    return row.get("time") or row.get("timestamp") or row.get("entry_time") or row.get("exit_time") or row.get("journal_mirrored_local")


def _fingerprint(row: Dict[str, Any]) -> str:
    parts = [
        str(_action(row)),
        str(row.get("symbol", "")),
        str(row.get("side", "")),
        str(_time_value(row)),
        str(row.get("price", "")),
        str(row.get("shares", "")),
        str(row.get("pnl_dollars", "")),
        str(row.get("exit_reason", "")),
    ]
    return "|".join(parts)


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        fp = _fingerprint(row)
        if fp in seen:
            continue
        seen.add(fp)
        out.append(row)
    return out


def is_review_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return True
    action = _action(row)
    source = _source(row)
    if action in REVIEW_ACTIONS:
        return True
    if any(hint in source for hint in REVIEW_SOURCE_HINTS):
        return True
    # Rotation-review rows often have same_side/score/pnl_pct but no execution
    # price/shares/exit_reason/action. They are useful diagnostics, not fills.
    if row.get("same_side") is not None and action not in REAL_EXECUTION_ACTIONS:
        return True
    return False


def is_execution_row(row: Any) -> bool:
    if not isinstance(row, dict) or is_review_row(row):
        return False
    action = _action(row)
    if action not in REAL_EXECUTION_ACTIONS:
        return False
    if not row.get("symbol"):
        return False
    # Actual executions should have fill-like data. Exits can have pnl even when
    # price is absent, but entries/reductions should have either price/shares or alloc.
    if action in ENTRY_ACTIONS:
        return any(k in row for k in ("price", "shares", "alloc"))
    if action in EXIT_ACTIONS:
        return any(k in row for k in ("price", "shares", "pnl_dollars", "pnl_pct", "exit_reason"))
    return False


def classify_rows(journal: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    trades = journal.get("trades", []) if isinstance(journal.get("trades"), list) else []
    execution: List[Dict[str, Any]] = []
    review: List[Dict[str, Any]] = []
    unknown: List[Dict[str, Any]] = []
    for row in trades:
        if not isinstance(row, dict):
            continue
        if is_execution_row(row):
            execution.append(row)
        elif is_review_row(row):
            review.append(row)
        else:
            unknown.append(row)
    return execution, review, unknown


def state_execution_rows(state: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    state = state if isinstance(state, dict) else _load_json(STATE_FILE)
    rows: List[Dict[str, Any]] = []
    for key in ("trades", "recent_trades"):
        value = state.get(key)
        if isinstance(value, list):
            for row in value:
                if isinstance(row, dict) and is_execution_row(row):
                    clean = dict(row)
                    clean.setdefault("journal_source", f"state.{key}")
                    rows.append(clean)
    return _dedupe_rows(rows)


def reconciled_execution_rows(journal: Dict[str, Any], state: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    journal_execution, _, _ = classify_rows(journal)
    combined = list(journal_execution) + state_execution_rows(state)
    return _dedupe_rows(combined)


def execution_summary(journal: Dict[str, Any]) -> Dict[str, Any]:
    state = _load_json(STATE_FILE)
    journal_execution, review, unknown = classify_rows(journal)
    state_execution = state_execution_rows(state)
    execution = _dedupe_rows(list(journal_execution) + list(state_execution))
    entries = [t for t in execution if _action(t) in ENTRY_ACTIONS]
    exits = [t for t in execution if _action(t) in EXIT_ACTIONS]
    stop_exits = [t for t in exits if "stop" in str(t.get("exit_reason", "")).lower()]
    wins = [t for t in exits if _float(t.get("pnl_dollars", 0.0)) > 0]
    losses = [t for t in exits if _float(t.get("pnl_dollars", 0.0)) < 0]
    flat = [t for t in exits if _float(t.get("pnl_dollars", 0.0)) == 0]
    gross_profit = sum(_float(t.get("pnl_dollars", 0.0)) for t in wins)
    gross_loss = abs(sum(_float(t.get("pnl_dollars", 0.0)) for t in losses))
    total_trades = len(journal.get("trades", [])) if isinstance(journal.get("trades"), list) else 0
    perf = state.get("performance", {}) if isinstance(state.get("performance"), dict) else {}
    state_realized_today = perf.get("realized_pnl_today")
    state_realized_total = perf.get("realized_pnl_total")
    return {
        "summary_type": "execution_only_state_reconciled",
        "trades_count": len(execution),
        "total_raw_rows": total_trades,
        "execution_rows_count": len(execution),
        "journal_execution_rows_count": len(journal_execution),
        "state_execution_rows_count": len(state_execution),
        "review_rows_count": len(review),
        "unknown_rows_count": len(unknown),
        "entries_count": len(entries),
        "exits_count": len(exits),
        "blocked_or_rejected_count": len([r for r in review if _action(r) in {"blocked", "rejected"} or "blocked" in _source(r) or "rejected" in _source(r)]),
        "stop_loss_exits_count": len(stop_exits),
        "wins_count": len(wins),
        "losses_count": len(losses),
        "flat_exits_count": len(flat),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_realized_from_execution_rows": round(gross_profit - gross_loss, 2),
        "state_realized_pnl_today": state_realized_today,
        "state_realized_pnl_total": state_realized_total,
        "realized_reconciliation_note": "Execution rows are reconciled from trade_journal.json plus state.json trades/recent_trades. State performance remains the authoritative live P/L display.",
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        "win_rate_pct": round(len(wins) / len(exits) * 100, 2) if exits else None,
        "latest_execution_trade": execution[-1] if execution else None,
        "latest_trade": execution[-1] if execution else None,
        "latest_review_row": review[-1] if review else None,
        "note": "Realized stats exclude rotation-review/scanner/blocked rows and count only actual execution actions.",
    }


def patch_trade_journal(trade_journal_module: Any | None = None) -> Dict[str, Any]:
    global _ORIGINAL_SUMMARY, _PATCHED
    try:
        if trade_journal_module is None:
            import trade_journal as trade_journal_module  # type: ignore[no-redef]
        if _ORIGINAL_SUMMARY is None and hasattr(trade_journal_module, "_journal_summary"):
            _ORIGINAL_SUMMARY = trade_journal_module._journal_summary
        trade_journal_module._journal_summary = execution_summary
        _PATCHED = True
        return {"status": "ok", "patched": True, "version": VERSION, "generated_local": _now_text()}
    except Exception as exc:
        return {"status": "error", "patched": False, "version": VERSION, "generated_local": _now_text(), "error": str(exc)}


def status_payload() -> Dict[str, Any]:
    journal = _load_json(TRADE_JOURNAL_FILE)
    state = _load_json(STATE_FILE)
    summary = execution_summary(journal)
    original_summary = None
    try:
        if callable(_ORIGINAL_SUMMARY):
            original_summary = _ORIGINAL_SUMMARY(journal)
    except Exception as exc:
        original_summary = {"error": str(exc)}
    journal_execution, review, unknown = classify_rows(journal)
    state_execution = state_execution_rows(state)
    execution = reconciled_execution_rows(journal, state)
    return {
        "status": "ok",
        "type": "journal_truth_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "patched_trade_journal_summary": _PATCHED,
        "journal_file": TRADE_JOURNAL_FILE,
        "state_file": STATE_FILE,
        "execution_summary": summary,
        "legacy_summary_before_patch": original_summary,
        "recent_execution_trades": execution[-20:],
        "recent_state_execution_trades": state_execution[-20:],
        "recent_journal_execution_trades": journal_execution[-20:],
        "recent_review_rows": review[-10:],
        "recent_unknown_rows": unknown[-10:],
        "state_performance": state.get("performance") if isinstance(state.get("performance"), dict) else {},
        "rules": {
            "execution_actions": sorted(REAL_EXECUTION_ACTIONS),
            "review_actions": sorted(REVIEW_ACTIONS),
            "review_source_hints": list(REVIEW_SOURCE_HINTS),
        },
    }


def register_routes(flask_app: Any, module: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/journal-truth-status" not in existing:
        flask_app.add_url_rule("/paper/journal-truth-status", "journal_truth_status", lambda: jsonify(status_payload()))
    REGISTERED_APP_IDS.add(id(flask_app))
