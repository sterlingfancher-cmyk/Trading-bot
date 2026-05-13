"""State/journal reconciliation guard.

Detects cases where state.json still shows an open position after the journal has
recorded a newer full exit for that same symbol. This module does not mutate
state; it surfaces a hard operator guard so reporting and next-cycle diagnostics
do not encourage add-ons into a stale position record.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from typing import Any, Dict, List

VERSION = "state-journal-reconciliation-guard-2026-05-13"

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
STATE_FILE = os.path.join(STATE_DIR, "state.json")
TRADE_JOURNAL_FILE = os.path.join(STATE_DIR, "trade_journal.json")
REGISTERED_APP_IDS: set[int] = set()


def _now_text() -> str:
    try:
        import pytz
        tz = pytz.timezone(os.environ.get("MARKET_TZ", "America/Chicago"))
        return dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: str) -> Dict[str, Any]:
    for attempt in range(3):
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
                return obj if isinstance(obj, dict) else {}
        except Exception:
            if attempt < 2:
                time.sleep(0.05)
    return {}


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _time_float(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("time", "timestamp", "entry_time", "exit_time", "journal_mirrored_local"):
            parsed = _time_float(value.get(key))
            if parsed is not None:
                return parsed
        return None
    try:
        if value not in (None, ""):
            return float(value)
    except Exception:
        pass
    if isinstance(value, str):
        normalized = value.replace(" CDT", "").replace(" CST", "").replace(" UTC", "").replace("Z", "")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return dt.datetime.strptime(normalized[:19], fmt).timestamp()
            except Exception:
                continue
    return None


def _action(row: Dict[str, Any]) -> str:
    return str(row.get("action", "") or "").strip().lower()


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol", "") or "").strip().upper()


def _side(row: Dict[str, Any]) -> str:
    return str(row.get("side", "") or "").strip().lower()


def _has_full_exit_fill(row: Dict[str, Any]) -> bool:
    return bool(_symbol(row) and _action(row) == "exit" and any(key in row for key in ("price", "shares", "pnl_dollars", "pnl_pct", "exit_reason")))


def _journal_full_exits(journal: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = journal.get("trades", []) if isinstance(journal.get("trades"), list) else []
    exits = [dict(row) for row in rows if isinstance(row, dict) and _has_full_exit_fill(row)]
    exits.sort(key=lambda row: _time_float(row) or 0.0)
    return exits


def _state_open_positions(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    positions = state.get("positions")
    if isinstance(positions, dict):
        for sym, pos in positions.items():
            if isinstance(pos, dict):
                row = dict(pos)
                row.setdefault("symbol", sym)
                out[str(sym).upper()] = row
    elif isinstance(positions, list):
        for sym in positions:
            if isinstance(sym, str):
                out.setdefault(sym.upper(), {"symbol": sym.upper()})

    perf = state.get("performance") if isinstance(state.get("performance"), dict) else {}
    perf_open = perf.get("open_positions") if isinstance(perf.get("open_positions"), dict) else {}
    for sym, pos in perf_open.items():
        if isinstance(pos, dict):
            row = dict(out.get(str(sym).upper(), {}))
            row.update(pos)
            row.setdefault("symbol", sym)
            out[str(sym).upper()] = row
    return [row for row in out.values() if _symbol(row)]


def _latest_full_exit_by_symbol(journal: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for row in _journal_full_exits(journal):
        sym = _symbol(row)
        if not sym:
            continue
        row_ts = _time_float(row) or 0.0
        prior_ts = _time_float(latest.get(sym, {})) or 0.0
        if sym not in latest or row_ts >= prior_ts:
            latest[sym] = row
    return latest


def build_guard(state: Dict[str, Any] | None = None, journal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = state if isinstance(state, dict) else _load_json(STATE_FILE)
    journal = journal if isinstance(journal, dict) else _load_json(TRADE_JOURNAL_FILE)
    latest_exit = _latest_full_exit_by_symbol(journal)
    mismatches: List[Dict[str, Any]] = []

    for pos in _state_open_positions(state):
        sym = _symbol(pos)
        exit_row = latest_exit.get(sym)
        if not exit_row:
            continue
        entry_ts = _time_float(pos.get("entry_time")) or _time_float(pos.get("time"))
        exit_ts = _time_float(exit_row)
        if exit_ts is None:
            continue
        if entry_ts is not None and exit_ts < entry_ts - 60:
            continue
        open_shares = _float_or_none(pos.get("shares"))
        exit_shares = _float_or_none(exit_row.get("shares"))
        share_coverage = round(exit_shares / open_shares, 4) if open_shares and open_shares > 0 and exit_shares is not None else None
        mismatches.append({
            "symbol": sym,
            "side": _side(pos) or _side(exit_row) or "long",
            "state_open_entry_time": pos.get("entry_time") or pos.get("time"),
            "state_open_entry_price": pos.get("entry"),
            "state_open_shares": pos.get("shares"),
            "journal_exit_time": exit_row.get("time") or exit_row.get("timestamp") or exit_row.get("journal_mirrored_local"),
            "journal_exit_price": exit_row.get("price"),
            "journal_exit_shares": exit_row.get("shares"),
            "journal_exit_reason": exit_row.get("exit_reason") or exit_row.get("reason"),
            "journal_exit_pnl_dollars": exit_row.get("pnl_dollars"),
            "journal_exit_pnl_pct": exit_row.get("pnl_pct"),
            "share_coverage_ratio": share_coverage,
            "reason": "state_open_position_has_newer_journal_full_exit",
        })

    blocked_symbols = sorted({m["symbol"] for m in mismatches if m.get("symbol")})
    active = bool(blocked_symbols)
    return {
        "status": "ok",
        "type": "state_journal_reconciliation_guard",
        "version": VERSION,
        "generated_local": _now_text(),
        "active": active,
        "reconciliation_status": "mismatch" if active else "ok",
        "blocked_symbols": blocked_symbols,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "operator_message": (
            "State still reports open position(s) after newer full journal exit(s); block add-ons for affected symbols until state and journal agree."
            if active else "No open-position/full-exit state-journal mismatch detected."
        ),
        "recommended_actions": ([
            "Block add-ons and new same-symbol entries for: " + ", ".join(blocked_symbols) + ".",
            "Confirm whether state.json or trade_journal.json is authoritative for the affected symbol(s).",
            "If the journal exit is correct, repair state open_positions before the next live/paper run cycle.",
        ] if active else []),
    }


def status_payload() -> Dict[str, Any]:
    return build_guard()


def register_routes(flask_app: Any, core: Any | None = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    if id(flask_app) in REGISTERED_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/state-journal-guard-status" not in existing:
        flask_app.add_url_rule("/paper/state-journal-guard-status", "state_journal_guard_status", lambda: jsonify(status_payload()))
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "registered": True}
