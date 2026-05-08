"""Persistent trade-journal mirror with event hooks for the paper trading bot.

This module protects realized trade history from state.json resets by keeping a
separate append-only journal in the persistent Railway volume.

Files written:
- /data/trade_journal.json
- /data/trade_journal_backup.json
- /data/trade_journal_status.json
- /data/trade_event_hook_status.json

Runtime behavior:
- Wraps app.save_state(*args, **kwargs) without changing the core function's
  signature or return value.
- Wraps high-probability trade/risk cycle functions so the journal mirrors after
  the function returns, even if the function wrote state directly.
- Wraps Flask view functions whose route/name suggests paper trading so manual
  runs and status-producing endpoints trigger a mirror pass after execution.
- Starts a lightweight state-file watcher that mirrors whenever /data/state.json
  changes on disk.
- Seeds the journal from state.json and state backups without ever shrinking it.
- Never writes to state.json.
"""
from __future__ import annotations

import datetime as dt
import functools
import inspect
import json
import os
import shutil
import sys
import threading
import time
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "trade-journal-event-hook-2026-05-08"

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
STATE_BACKUP_LATEST = os.path.join(STATE_DIR, "state_backup_latest.json")
STATE_BACKUP_LARGEST = os.path.join(STATE_DIR, "state_backup_largest.json")
TRADE_JOURNAL_FILE = os.path.join(STATE_DIR, "trade_journal.json")
TRADE_JOURNAL_BACKUP_FILE = os.path.join(STATE_DIR, "trade_journal_backup.json")
TRADE_JOURNAL_STATUS_FILE = os.path.join(STATE_DIR, "trade_journal_status.json")
TRADE_EVENT_HOOK_STATUS_FILE = os.path.join(STATE_DIR, "trade_event_hook_status.json")

WATCHER_ENABLED = os.environ.get("TRADE_JOURNAL_WATCHER_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
WATCHER_INTERVAL_SECONDS = float(os.environ.get("TRADE_JOURNAL_WATCHER_INTERVAL_SECONDS", "2.0"))
FUNCTION_HOOKS_ENABLED = os.environ.get("TRADE_JOURNAL_FUNCTION_HOOKS_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
VIEW_HOOKS_ENABLED = os.environ.get("TRADE_JOURNAL_VIEW_HOOKS_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MAX_FUNCTION_HOOKS = int(os.environ.get("TRADE_JOURNAL_MAX_FUNCTION_HOOKS", "80"))

REGISTERED_APP_IDS: set[int] = set()
_PATCHED_FUNCTION_IDS: set[int] = set()
_PATCHED_VIEW_NAMES: set[str] = set()
_INSTALLED = False
_WATCHER_STARTED = False
_WATCHER_STOP = False
_LAST_STATUS: Dict[str, Any] = {}
_LAST_HOOK_STATUS: Dict[str, Any] = {}
_MIRROR_LOCK = threading.RLock()
_LAST_STATE_MTIME = 0.0
_LAST_STATE_SIZE = 0
_LAST_MIRROR_TS = 0.0


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _file_size(path: str) -> int:
    try:
        return int(os.path.getsize(path))
    except Exception:
        return 0


def _file_mtime(path: str) -> float:
    try:
        return float(os.path.getmtime(path))
    except Exception:
        return 0.0


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


def _float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _state_summary(state: Dict[str, Any], state_file: str = STATE_FILE) -> Dict[str, Any]:
    trades = state.get("trades", []) if isinstance(state.get("trades"), list) else []
    recent = state.get("recent_trades", []) if isinstance(state.get("recent_trades"), list) else []
    positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    realized = state.get("realized_pnl", {}) if isinstance(state.get("realized_pnl"), dict) else {}
    perf = state.get("performance", {}) if isinstance(state.get("performance"), dict) else {}
    risk = state.get("risk_controls", {}) if isinstance(state.get("risk_controls"), dict) else {}
    scanner = state.get("scanner_audit", {}) if isinstance(state.get("scanner_audit"), dict) else {}
    return {
        "state_file": state_file,
        "state_size_bytes": _file_size(state_file),
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
    parts = [
        row.get("time", ""),
        row.get("action", ""),
        row.get("symbol", ""),
        row.get("side", ""),
        row.get("shares", ""),
        row.get("price", ""),
        row.get("exit_reason", ""),
        row.get("pnl_dollars", ""),
        row.get("pnl_pct", ""),
        fallback_index,
    ]
    return "|".join(str(p) for p in parts)


def _looks_like_trade(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    action = str(row.get("action", "")).lower()
    has_symbol = bool(row.get("symbol"))
    has_trade_fields = any(k in row for k in ["side", "shares", "price", "pnl_dollars", "pnl_pct", "exit_reason", "alloc", "score"])
    return has_symbol and (action in {"entry", "exit", "partial_exit", "rotation", "blocked", "rejected"} or has_trade_fields)


def _normalize_trade(row: Any, fallback_index: int = 0, source: str = "state.trades") -> Dict[str, Any] | None:
    if not _looks_like_trade(row):
        return None
    out = dict(row)
    out["symbol"] = str(out.get("symbol", "")).upper()
    out["journal_key"] = out.get("journal_key") or _trade_key(out, fallback_index)
    out["journal_source"] = source
    out["journal_mirrored_local"] = _now_text()
    return out


def _extract_candidate_trade_rows(obj: Any, source: str = "unknown", limit: int = 200) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def walk(x: Any, path: str, depth: int) -> None:
        if len(rows) >= limit or depth > 5:
            return
        if _looks_like_trade(x):
            n = _normalize_trade(x, len(rows), f"{source}:{path}")
            if n:
                rows.append(n)
            return
        if isinstance(x, list):
            for idx, item in enumerate(x):
                if len(rows) >= limit:
                    break
                walk(item, f"{path}[{idx}]", depth + 1)
        elif isinstance(x, dict):
            # Only walk likely trade-bearing branches to avoid bloating the journal
            likely_keys = {
                "trades", "recent_trades", "entries", "exits", "rotations",
                "accepted_entries", "blocked_entries", "rejected_signals", "long_signals", "short_signals",
                "last_result", "scanner_audit", "performance", "journal", "reports",
            }
            for key, val in x.items():
                if key in likely_keys or depth <= 1:
                    walk(val, f"{path}.{key}" if path else str(key), depth + 1)

    walk(obj, "", 0)
    return rows


def _extract_trades(state: Dict[str, Any], source_file: str = STATE_FILE) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    trades_raw = state.get("trades", []) if isinstance(state.get("trades"), list) else []
    recent_raw = state.get("recent_trades", []) if isinstance(state.get("recent_trades"), list) else []
    trades: List[Dict[str, Any]] = []
    recent: List[Dict[str, Any]] = []
    for i, row in enumerate(trades_raw):
        n = _normalize_trade(row, i, f"{source_file}:trades")
        if n:
            trades.append(n)
    for i, row in enumerate(recent_raw):
        n = _normalize_trade(row, i, f"{source_file}:recent_trades")
        if n:
            recent.append(n)
    if not trades and not recent:
        # Salvage trade-like rows from scanner or reports if state.trades was reset.
        discovered = _extract_candidate_trade_rows(state, source=f"{source_file}:deep_scan")
        trades.extend(discovered)
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
        if not isinstance(row, dict):
            continue
        key = row.get("journal_key") or _trade_key(row, len(merged))
        if key not in seen:
            row = dict(row)
            row["journal_key"] = key
            merged.append(row)
            seen.add(key)
            added += 1
    return merged, added


def _journal_summary(journal: Dict[str, Any]) -> Dict[str, Any]:
    trades = journal.get("trades", []) if isinstance(journal.get("trades"), list) else []
    exits = [t for t in trades if isinstance(t, dict) and str(t.get("action", "")).lower() == "exit"]
    entries = [t for t in trades if isinstance(t, dict) and str(t.get("action", "")).lower() == "entry"]
    blocked = [t for t in trades if isinstance(t, dict) and ("blocked" in str(t.get("journal_source", "")).lower() or str(t.get("action", "")).lower() == "blocked")]
    stop_exits = [t for t in exits if "stop" in str(t.get("exit_reason", "")).lower()]
    wins = [t for t in exits if _float(t.get("pnl_dollars", 0.0)) > 0]
    losses = [t for t in exits if _float(t.get("pnl_dollars", 0.0)) < 0]
    gross_profit = sum(_float(t.get("pnl_dollars", 0.0)) for t in wins)
    gross_loss = abs(sum(_float(t.get("pnl_dollars", 0.0)) for t in losses))
    return {
        "trades_count": len(trades),
        "entries_count": len(entries),
        "exits_count": len(exits),
        "blocked_or_rejected_count": len(blocked),
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


def _empty_journal() -> Dict[str, Any]:
    return {
        "version": VERSION,
        "created_local": _now_text(),
        "trades": [],
        "recent_trades": [],
        "snapshots": [],
        "event_hook_events": [],
    }


def mirror_state(state: Dict[str, Any] | None, source: str = "manual", source_file: str = STATE_FILE, extra_trade_rows: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Mirror state trades into persistent trade_journal.json without shrinking."""
    global _LAST_STATUS, _LAST_MIRROR_TS
    with _MIRROR_LOCK:
        if not isinstance(state, dict):
            state = _load_json(source_file)

        existing = _load_json(TRADE_JOURNAL_FILE) or _empty_journal()
        backup = _backup_journal()
        state_trades, state_recent = _extract_trades(state, source_file=source_file)
        extra_rows = list(extra_trade_rows or [])
        existing_trades = existing.get("trades", []) if isinstance(existing.get("trades"), list) else []
        existing_recent = existing.get("recent_trades", []) if isinstance(existing.get("recent_trades"), list) else []

        merged_trades, added_trades = _merge_trade_lists(existing_trades, state_trades + state_recent + extra_rows)
        merged_recent, added_recent = _merge_trade_lists(existing_recent, (state_recent + extra_rows)[-50:])
        snapshots = existing.get("snapshots", []) if isinstance(existing.get("snapshots"), list) else []
        events = existing.get("event_hook_events", []) if isinstance(existing.get("event_hook_events"), list) else []
        snapshot = {
            "mirrored_local": _now_text(),
            "source": source,
            "source_file": source_file,
            "state_summary": _state_summary(state, source_file),
            "extra_trade_rows": len(extra_rows),
            "new_trades_mirrored": added_trades,
        }
        snapshots.append(snapshot)
        snapshots = snapshots[-180:]
        if source.startswith("function_hook") or source.startswith("view_hook") or source.startswith("state_file_watcher"):
            events.append(snapshot)
            events = events[-240:]

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
            "event_hook_events": events,
        })
        journal["summary"] = _journal_summary(journal)

        write_ok = _atomic_write(TRADE_JOURNAL_FILE, journal)
        _LAST_MIRROR_TS = time.time()
        status = {
            "status": "ok" if write_ok else "error",
            "type": "trade_journal_status",
            "version": VERSION,
            "generated_local": _now_text(),
            "source": source,
            "state_file": STATE_FILE,
            "source_file": source_file,
            "journal_file": TRADE_JOURNAL_FILE,
            "backup_file": TRADE_JOURNAL_BACKUP_FILE,
            "write_ok": write_ok,
            "backup": backup,
            "state_summary": _state_summary(state, source_file),
            "journal_summary": journal.get("summary", {}),
            "new_trades_mirrored": added_trades,
            "new_recent_rows_mirrored": added_recent,
            "extra_trade_rows_seen": len(extra_rows),
            "journal_size_bytes": _file_size(TRADE_JOURNAL_FILE),
            "backup_size_bytes": _file_size(TRADE_JOURNAL_BACKUP_FILE),
            "state_json_written_by_trade_journal": False,
        }
        _LAST_STATUS = status
        _atomic_write(TRADE_JOURNAL_STATUS_FILE, status)
        return status


def seed_from_state_files() -> Dict[str, Any]:
    files = [STATE_BACKUP_LARGEST, STATE_BACKUP_LATEST, STATE_FILE]
    results = []
    for path in files:
        if os.path.exists(path):
            results.append(mirror_state(_load_json(path), source="seed_from_state_file", source_file=path))
    return {"status": "ok", "version": VERSION, "files_checked": files, "results_count": len(results), "results": results[-3:]}


def _load_current_state(module: Any | None = None) -> Dict[str, Any]:
    if module is not None and hasattr(module, "load_state"):
        try:
            s = module.load_state()
            if isinstance(s, dict):
                return s
        except Exception:
            pass
    return _load_json(STATE_FILE)


def _function_should_be_hooked(name: str, fn: Any) -> bool:
    if name in {"save_state", "load_state"}:
        return False
    low_name = name.lower()
    positive_name = any(k in low_name for k in ["paper", "trade", "entry", "exit", "position", "run", "cycle", "auto"])
    if not positive_name:
        return False
    try:
        consts = " ".join(str(c).lower() for c in getattr(fn, "__code__", None).co_consts)
    except Exception:
        consts = ""
    positive_consts = any(k in consts for k in ["trades", "recent_trades", "entry", "exit", "stop_loss", "blocked_entries", "accepted_entries"])
    # Avoid wrapping helpers that are called constantly and clearly do not trade.
    negative = any(k in low_name for k in ["status", "health", "explain", "journal", "report", "auth", "clock"])
    return bool(positive_consts and not negative)


def _hook_module_functions(module: Any | None = None) -> Dict[str, Any]:
    if not FUNCTION_HOOKS_ENABLED or module is None:
        return {"enabled": FUNCTION_HOOKS_ENABLED, "wrapped_count": 0, "wrapped_functions": []}
    wrapped = []
    for name, fn in list(getattr(module, "__dict__", {}).items()):
        if len(wrapped) >= MAX_FUNCTION_HOOKS:
            break
        if not inspect.isfunction(fn):
            continue
        if getattr(fn, "_trade_journal_event_wrapped", False) or id(fn) in _PATCHED_FUNCTION_IDS:
            continue
        if not _function_should_be_hooked(name, fn):
            continue

        @functools.wraps(fn)
        def wrapper(*args, __fn=fn, __name=name, **kwargs):
            result = __fn(*args, **kwargs)
            try:
                extra_rows = _extract_candidate_trade_rows(result, source=f"function_hook:{__name}:return")
                mirror_state(_load_current_state(module), source=f"function_hook:{__name}", extra_trade_rows=extra_rows)
            except Exception:
                pass
            return result

        wrapper._trade_journal_event_wrapped = True  # type: ignore[attr-defined]
        try:
            setattr(module, name, wrapper)
            _PATCHED_FUNCTION_IDS.add(id(fn))
            wrapped.append(name)
        except Exception:
            pass
    return {"enabled": FUNCTION_HOOKS_ENABLED, "wrapped_count": len(wrapped), "wrapped_functions": wrapped}


def _hook_flask_views(flask_app: Any | None = None, module: Any | None = None) -> Dict[str, Any]:
    if not VIEW_HOOKS_ENABLED or flask_app is None:
        return {"enabled": VIEW_HOOKS_ENABLED, "wrapped_count": 0, "wrapped_views": []}
    wrapped = []
    try:
        rules_by_endpoint = {r.endpoint: r.rule for r in flask_app.url_map.iter_rules()}
        for endpoint, view in list(flask_app.view_functions.items()):
            if endpoint in _PATCHED_VIEW_NAMES or getattr(view, "_trade_journal_view_wrapped", False):
                continue
            rule = rules_by_endpoint.get(endpoint, "")
            haystack = f"{endpoint} {rule}".lower()
            if "/paper" not in haystack:
                continue
            if any(x in haystack for x in ["trade-journal", "state-safety", "state-recovery", "risk-improvement", "live-volatility"]):
                continue
            if not any(x in haystack for x in ["run", "status", "intraday", "end-of-day", "report", "journal", "risk", "explain"]):
                continue

            @functools.wraps(view)
            def wrapped_view(*args, __view=view, __endpoint=endpoint, __rule=rule, **kwargs):
                result = __view(*args, **kwargs)
                try:
                    extra_rows = _extract_candidate_trade_rows(result, source=f"view_hook:{__endpoint}:return")
                    mirror_state(_load_current_state(module), source=f"view_hook:{__endpoint}:{__rule}", extra_trade_rows=extra_rows)
                except Exception:
                    pass
                return result

            wrapped_view._trade_journal_view_wrapped = True  # type: ignore[attr-defined]
            flask_app.view_functions[endpoint] = wrapped_view
            _PATCHED_VIEW_NAMES.add(endpoint)
            wrapped.append({"endpoint": endpoint, "rule": rule})
    except Exception as exc:
        return {"enabled": VIEW_HOOKS_ENABLED, "wrapped_count": len(wrapped), "wrapped_views": wrapped, "error": str(exc)}
    return {"enabled": VIEW_HOOKS_ENABLED, "wrapped_count": len(wrapped), "wrapped_views": wrapped}


def _watcher_loop(module: Any | None = None) -> None:
    global _LAST_STATE_MTIME, _LAST_STATE_SIZE
    while not _WATCHER_STOP:
        try:
            mtime = _file_mtime(STATE_FILE)
            size = _file_size(STATE_FILE)
            if mtime and (mtime != _LAST_STATE_MTIME or size != _LAST_STATE_SIZE):
                _LAST_STATE_MTIME = mtime
                _LAST_STATE_SIZE = size
                mirror_state(_load_current_state(module), source="state_file_watcher")
        except Exception:
            pass
        time.sleep(max(0.5, WATCHER_INTERVAL_SECONDS))


def _start_watcher(module: Any | None = None) -> Dict[str, Any]:
    global _WATCHER_STARTED, _LAST_STATE_MTIME, _LAST_STATE_SIZE
    if not WATCHER_ENABLED:
        return {"enabled": False, "started": False}
    if _WATCHER_STARTED:
        return {"enabled": True, "started": True, "already_started": True}
    _LAST_STATE_MTIME = _file_mtime(STATE_FILE)
    _LAST_STATE_SIZE = _file_size(STATE_FILE)
    t = threading.Thread(target=_watcher_loop, args=(module,), daemon=True, name="trade_journal_state_watcher")
    t.start()
    _WATCHER_STARTED = True
    return {"enabled": True, "started": True, "interval_seconds": WATCHER_INTERVAL_SECONDS}


def install(module: Any | None = None) -> Dict[str, Any]:
    """Install save_state wrapper, function hooks, view hooks, watcher, and seed journal."""
    global _INSTALLED, _LAST_HOOK_STATUS
    if module is None:
        for mod in list(sys.modules.values()):
            if getattr(mod, "app", None) is not None and hasattr(mod, "save_state"):
                module = mod
                break

    if module is None:
        status = {"status": "not_installed", "version": VERSION, "reason": "app module with save_state not found", "generated_local": _now_text()}
        _atomic_write(TRADE_JOURNAL_STATUS_FILE, status)
        return status

    save_state_wrapped = False
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
        save_state_wrapped = True
        _INSTALLED = True
    else:
        _INSTALLED = bool(hasattr(module, "save_state"))
        save_state_wrapped = bool(getattr(getattr(module, "save_state", None), "_trade_journal_wrapped", False))

    seed_status = seed_from_state_files()
    function_hooks = _hook_module_functions(module)
    flask_app = getattr(module, "app", None)
    view_hooks = _hook_flask_views(flask_app, module)
    watcher = _start_watcher(module)
    status = mirror_state(_load_current_state(module), source="install")
    status.update({
        "save_state_wrapped": save_state_wrapped,
        "installed": _INSTALLED,
        "function_hooks": function_hooks,
        "view_hooks": view_hooks,
        "watcher": watcher,
        "seed_status": {"files_checked": seed_status.get("files_checked"), "results_count": seed_status.get("results_count")},
    })
    _LAST_HOOK_STATUS = {
        "status": "ok",
        "type": "trade_event_hook_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "installed": _INSTALLED,
        "save_state_wrapped": save_state_wrapped,
        "function_hooks": function_hooks,
        "view_hooks": view_hooks,
        "watcher": watcher,
        "state_json_written_by_trade_journal": False,
    }
    _atomic_write(TRADE_EVENT_HOOK_STATUS_FILE, _LAST_HOOK_STATUS)
    _atomic_write(TRADE_JOURNAL_STATUS_FILE, status)
    return status


def get_status(module: Any | None = None) -> Dict[str, Any]:
    journal = _load_json(TRADE_JOURNAL_FILE)
    status = _load_json(TRADE_JOURNAL_STATUS_FILE) or dict(_LAST_STATUS)
    state = _load_current_state(module)
    return {
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
        "watcher_started": _WATCHER_STARTED,
        "last_mirror_local": dt.datetime.fromtimestamp(_LAST_MIRROR_TS).strftime("%Y-%m-%d %H:%M:%S") if _LAST_MIRROR_TS else None,
        "state_json_written_by_trade_journal": False,
    }


def get_event_hook_status(module: Any | None = None) -> Dict[str, Any]:
    status = _load_json(TRADE_EVENT_HOOK_STATUS_FILE) or dict(_LAST_HOOK_STATUS)
    status.update({
        "status": "ok",
        "type": "trade_event_hook_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "installed": _INSTALLED,
        "watcher_started": _WATCHER_STARTED,
        "state_file_mtime": _file_mtime(STATE_FILE),
        "state_file_size_bytes": _file_size(STATE_FILE),
        "journal_size_bytes": _file_size(TRADE_JOURNAL_FILE),
        "journal_summary": _journal_summary(_load_json(TRADE_JOURNAL_FILE)),
        "last_mirror_status": _load_json(TRADE_JOURNAL_STATUS_FILE),
        "state_json_written_by_trade_journal": False,
    })
    return status


def get_journal(full: bool = False) -> Dict[str, Any]:
    journal = _load_json(TRADE_JOURNAL_FILE)
    if not journal:
        return {"status": "ok", "type": "trade_journal", "version": VERSION, "journal_file": TRADE_JOURNAL_FILE, "summary": _journal_summary({}), "trades": []}
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
        flask_app.add_url_rule("/paper/trade-journal-status", "trade_journal_status", lambda: jsonify(get_status(module)))
    if "/paper/trade-event-hook-status" not in existing:
        flask_app.add_url_rule("/paper/trade-event-hook-status", "trade_event_hook_status", lambda: jsonify(get_event_hook_status(module)))
    if "/paper/trade-journal" not in existing:
        flask_app.add_url_rule(
            "/paper/trade-journal",
            "trade_journal",
            lambda: jsonify(get_journal(full=str(request.args.get("full", "0")).lower() in {"1", "true", "yes"})),
        )
    if "/paper/trade-journal-sync" not in existing:
        flask_app.add_url_rule("/paper/trade-journal-sync", "trade_journal_sync", lambda: jsonify(mirror_state(_load_current_state(module), source="manual_sync_endpoint")))
    if "/paper/trade-journal-seed" not in existing:
        flask_app.add_url_rule("/paper/trade-journal-seed", "trade_journal_seed", lambda: jsonify(seed_from_state_files()))
    REGISTERED_APP_IDS.add(id(flask_app))
