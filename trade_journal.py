"""Persistent trade-journal mirror for the paper trading bot.

This module protects realized trade history from state.json resets by keeping a
separate append-only journal in the persistent Railway volume.

Files written:
- /data/trade_journal.json
- /data/trade_journal_backup.json
- /data/trade_journal_status.json

Runtime behavior:
- Wraps app.save_state(*args, **kwargs) without changing the core function's
  signature or return value.
- Mirrors trades/recent_trades/realized P&L snapshots after each save.
- Never shrinks the trade journal when state.json is reset or has fewer trades.
- Creates a backup before journal replacement.
- Exposes /paper/trade-journal-status and /paper/trade-journal.
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Tuple

VERSION = "trade-journal-mirror-2026-05-08"

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
TRADE_JOURNAL_FILE = os.path.join(STATE_DIR, "trade_journal.json")
TRADE_JOURNAL_BACKUP_FILE = os.path.join(STATE_DIR, "trade_journal_backup.json")
TRADE_JOURNAL_STATUS_FILE = os.path.join(STATE_DIR, "trade_journal_status.json")

REGISTERED_APP_IDS: set[int] = set()
_INSTALLED = False
_LAST_STATUS: Dict[str, Any] = {}


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _file_size(path: str) -> int:
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _atomic_write(path: str, payload: Dict[str, Any]) -> bool:
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _backup_journal() -> Dict[str, Any]:
    result = {
        "backup_file": TRADE_JOURNAL_BACKUP_FILE,
        "backup_written": False,
        "source_size_bytes": _file_size(TRADE_JOURNAL_FILE),
        "backup_size_bytes": _file_size(TRADE_JOURNAL_BACKUP_FILE),
    }
    try:
        if os.path.exists(TRADE_JOURNAL_FILE) and _file_size(TRADE_JOURNAL_FILE) > 0:
            folder = os.path.dirname(TRADE_JOURNAL_BACKUP_FILE)
            if folder:
                os.makedirs(folder, exist_ok=True)
            shutil.copy2(TRADE_JOURNAL_FILE, TRADE_JOURNAL_BACKUP_FILE)
            result["backup_written"] = True
            result["backup_size_bytes"] = _file_size(TRADE_JOURNAL_BACKUP_FILE)
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _state_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    trades = state.get("trades", []) if isinstance(state.get("trades"), list) else []
    recent = state.get("recent_trades", []) if isinstance(state.get("recent_trades"), list) else []
    positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    realized = state.get("realized_pnl", {}) if isinstance(state.get("realized_pnl"), dict) else {}
    perf = state.get("performance", {}) if isinstance(state.get("performance"), dict) else {}
    risk = state.get("risk_controls", {}) if isinstance(state.get("risk_controls"), dict) else {}
    scanner = state.get("scanner_audit", {}) if isinstance(state.get("scanner_audit"), dict) else {}
    return {
        "state_file": STATE_FILE,
        "state_size_bytes": _file_size(STATE_FILE),
        "state_trades_count": len(trades),
        "state_recent_trades_count": len(recent),
        "positions_count": len(positions),
        "open_positions": list(positions.keys()),
        "equity": state.get("equity"),
        "cash": state.get("cash"),
        "realized_pnl": realized,
        "performance": perf,
        "risk_controls": risk,
        "scanner_audit_summary": {
            "signals_found": scanner.get("signals_found"),
            "last_updated_local": scanner.get("last_updated_local"),
            "blocked_entries_count": len(scanner.get("blocked_entries", [])) if isinstance(scanner.get("blocked_entries"), list) else 0,
            "accepted_entries_count": len(scanner.get("accepted_entries", [])) if isinstance(scanner.get("accepted_entries"), list) else 0,
        },
    }


def _trade_key(row: Dict[str, Any], fallback_index: int = 0) -> str:
    # Stable enough for the bot's trade rows. Includes time, action, symbol,
    # side, shares, price, and exit reason when present.
    parts = [
        row.get("time", ""),
        row.get("action", ""),
        row.get("symbol", ""),
        row.get("side", ""),
        row.get("shares", ""),
        row.get("price", ""),
        row.get("exit_reason", ""),
        row.get("pnl_dollars", ""),
        fallback_index,
    ]
    return "|".join(str(p) for p in parts)


def _normalize_trade(row: Any, fallback_index: int = 0, source: str = "state.trades") -> Dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    out = dict(row)
    out.setdefault("symbol", str(out.get("symbol", "")).upper())
    out["journal_key"] = _trade_key(out, fallback_index)
    out["journal_source"] = source
    out["journal_mirrored_local"] = _now_text()
    return out


def _extract_trades(state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    trades_raw = state.get("trades", []) if isinstance(state.get("trades"), list) else []
    recent_raw = state.get("recent_trades", []) if isinstance(state.get("recent_trades"), list) else []
    trades: List[Dict[str, Any]] = []
    recent: List[Dict[str, Any]] = []
    for i, row in enumerate(trades_raw):
        n = _normalize_trade(row, i, "state.trades")
        if n:
            trades.append(n)
    for i, row in enumerate(recent_raw):
        n = _normalize_trade(row, i, "state.recent_trades")
        if n:
            recent.append(n)
    return trades, recent


def _merge_trade_lists(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    seen = set()
    merged: List[Dict[str, Any]] = []
    for row in existing:
        if not isinstance(row, dict):
            continue
        key = row.get("journal_key") or _trade_key(row, len(merged))
        row = dict(row)
        row["journal_key"] = key
        if key not in seen:
            merged.append(row)
            seen.add(key)
    added = 0
    for row in incoming:
        key = row.get("journal_key") or _trade_key(row, len(merged))
        if key not in seen:
            merged.append(row)
            seen.add(key)
            added += 1
    return merged, added


def _journal_summary(journal: Dict[str, Any]) -> Dict[str, Any]:
    trades = journal.get("trades", []) if isinstance(journal.get("trades"), list) else []
    exits = [t for t in trades if isinstance(t, dict) and str(t.get("action", "")).lower() == "exit"]
    entries = [t for t in trades if isinstance(t, dict) and str(t.get("action", "")).lower() == "entry"]
    stop_exits = [t for t in exits if "stop" in str(t.get("exit_reason", "")).lower()]
    wins = [t for t in exits if _float(t.get("pnl_dollars", 0.0)) > 0]
    losses = [t for t in exits if _float(t.get("pnl_dollars", 0.0)) < 0]
    gross_profit = sum(_float(t.get("pnl_dollars", 0.0)) for t in wins)
    gross_loss = abs(sum(_float(t.get("pnl_dollars", 0.0)) for t in losses))
    return {
        "trades_count": len(trades),
        "entries_count": len(entries),
        "exits_count": len(exits),
        "stop_loss_exits_count": len(stop_exits),
        "wins_count": len(wins),
        "losses_count": len(losses),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_realized_from_journal": round(gross_profit - gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        "win_rate_pct": round(len(wins) / len(exits) * 100, 2) if exits else None,
        "latest_trade": trades[-1] if trades else None,
    }


def _float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def mirror_state(state: Dict[str, Any] | None, source: str = "manual") -> Dict[str, Any]:
    """Mirror state trades into persistent trade_journal.json without shrinking."""
    global _LAST_STATUS
    if not isinstance(state, dict):
        state = _load_json(STATE_FILE)

    existing = _load_json(TRADE_JOURNAL_FILE)
    if not existing:
        existing = {
            "version": VERSION,
            "created_local": _now_text(),
            "trades": [],
            "recent_trades": [],
            "snapshots": [],
        }

    backup = _backup_journal()
    state_trades, state_recent = _extract_trades(state)
    existing_trades = existing.get("trades", []) if isinstance(existing.get("trades"), list) else []
    existing_recent = existing.get("recent_trades", []) if isinstance(existing.get("recent_trades"), list) else []

    merged_trades, added_trades = _merge_trade_lists(existing_trades, state_trades + state_recent)
    merged_recent, added_recent = _merge_trade_lists(existing_recent, state_recent[-50:])
    snapshots = existing.get("snapshots", []) if isinstance(existing.get("snapshots"), list) else []
    snapshot = {
        "mirrored_local": _now_text(),
        "source": source,
        "state_summary": _state_summary(state),
    }
    snapshots.append(snapshot)
    snapshots = snapshots[-120:]

    journal = dict(existing)
    journal.update({
        "version": VERSION,
        "updated_local": _now_text(),
        "state_file": STATE_FILE,
        "journal_file": TRADE_JOURNAL_FILE,
        "backup_file": TRADE_JOURNAL_BACKUP_FILE,
        "trades": merged_trades,
        "recent_trades": merged_recent[-50:],
        "snapshots": snapshots,
    })
    journal["summary"] = _journal_summary(journal)

    write_ok = _atomic_write(TRADE_JOURNAL_FILE, journal)
    status = {
        "status": "ok" if write_ok else "error",
        "type": "trade_journal_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "source": source,
        "state_file": STATE_FILE,
        "journal_file": TRADE_JOURNAL_FILE,
        "backup_file": TRADE_JOURNAL_BACKUP_FILE,
        "write_ok": write_ok,
        "backup": backup,
        "state_summary": _state_summary(state),
        "journal_summary": journal.get("summary", {}),
        "new_trades_mirrored": added_trades,
        "new_recent_rows_mirrored": added_recent,
        "journal_size_bytes": _file_size(TRADE_JOURNAL_FILE),
        "backup_size_bytes": _file_size(TRADE_JOURNAL_BACKUP_FILE),
        "state_json_written_by_trade_journal": False,
    }
    _LAST_STATUS = status
    _atomic_write(TRADE_JOURNAL_STATUS_FILE, status)
    return status


def _load_current_state(module: Any | None = None) -> Dict[str, Any]:
    if module is not None and hasattr(module, "load_state"):
        try:
            s = module.load_state()
            if isinstance(s, dict):
                return s
        except Exception:
            pass
    return _load_json(STATE_FILE)


def install(module: Any | None = None) -> Dict[str, Any]:
    """Install save_state wrapper and perform an immediate mirror pass."""
    global _INSTALLED
    if module is None:
        for mod in list(sys.modules.values()):
            if getattr(mod, "app", None) is not None and hasattr(mod, "save_state"):
                module = mod
                break

    if module is None:
        status = {
            "status": "not_installed",
            "version": VERSION,
            "reason": "app module with save_state not found",
            "generated_local": _now_text(),
        }
        _atomic_write(TRADE_JOURNAL_STATUS_FILE, status)
        return status

    if hasattr(module, "save_state") and not getattr(module.save_state, "_trade_journal_wrapped", False):
        original_save_state = module.save_state

        @functools.wraps(original_save_state)
        def wrapped_save_state(*args, **kwargs):
            result = original_save_state(*args, **kwargs)
            try:
                state_arg = args[0] if args and isinstance(args[0], dict) else None
                mirror_state(state_arg, source="save_state_wrapper")
            except Exception:
                pass
            return result

        wrapped_save_state._trade_journal_wrapped = True  # type: ignore[attr-defined]
        module.save_state = wrapped_save_state
        _INSTALLED = True
    else:
        _INSTALLED = bool(hasattr(module, "save_state"))

    state = _load_current_state(module)
    status = mirror_state(state, source="install")
    status["save_state_wrapped"] = bool(getattr(getattr(module, "save_state", None), "_trade_journal_wrapped", False))
    status["installed"] = _INSTALLED
    _atomic_write(TRADE_JOURNAL_STATUS_FILE, status)
    return status


def get_status(module: Any | None = None) -> Dict[str, Any]:
    journal = _load_json(TRADE_JOURNAL_FILE)
    status = _load_json(TRADE_JOURNAL_STATUS_FILE) or dict(_LAST_STATUS)
    state = _load_current_state(module)
    payload = {
        "status": "ok",
        "type": "trade_journal_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "installed": _INSTALLED,
        "state_file": STATE_FILE,
        "journal_file": TRADE_JOURNAL_FILE,
        "backup_file": TRADE_JOURNAL_BACKUP_FILE,
        "status_file": TRADE_JOURNAL_STATUS_FILE,
        "state_summary_now": _state_summary(state),
        "journal_summary": _journal_summary(journal),
        "journal_size_bytes": _file_size(TRADE_JOURNAL_FILE),
        "backup_size_bytes": _file_size(TRADE_JOURNAL_BACKUP_FILE),
        "last_mirror_status": status,
        "state_json_written_by_trade_journal": False,
    }
    return payload


def get_journal(full: bool = False) -> Dict[str, Any]:
    journal = _load_json(TRADE_JOURNAL_FILE)
    if not journal:
        return {
            "status": "ok",
            "type": "trade_journal",
            "version": VERSION,
            "journal_file": TRADE_JOURNAL_FILE,
            "summary": _journal_summary({}),
            "trades": [],
        }
    if full:
        payload = dict(journal)
        payload["status"] = "ok"
        payload["type"] = "trade_journal"
        return payload
    trades = journal.get("trades", []) if isinstance(journal.get("trades"), list) else []
    return {
        "status": "ok",
        "type": "trade_journal",
        "version": VERSION,
        "generated_local": _now_text(),
        "journal_file": TRADE_JOURNAL_FILE,
        "backup_file": TRADE_JOURNAL_BACKUP_FILE,
        "summary": _journal_summary(journal),
        "recent_trades": trades[-25:],
    }


def register_routes(flask_app: Any, module: Any | None = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify, request
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/trade-journal-status" not in existing:
        flask_app.add_url_rule(
            "/paper/trade-journal-status",
            "trade_journal_status",
            lambda: jsonify(get_status(module)),
        )
    if "/paper/trade-journal" not in existing:
        flask_app.add_url_rule(
            "/paper/trade-journal",
            "trade_journal",
            lambda: jsonify(get_journal(full=str(request.args.get("full", "0")).lower() in {"1", "true", "yes"})),
        )
    if "/paper/trade-journal-sync" not in existing:
        flask_app.add_url_rule(
            "/paper/trade-journal-sync",
            "trade_journal_sync",
            lambda: jsonify(mirror_state(_load_current_state(module), source="manual_sync_endpoint")),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
