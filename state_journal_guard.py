"""State/journal reconciliation guard plus safe repair endpoint.

The guard detects stale open positions in state.json when trade_journal.json has a
newer full exit for the same symbol. The repair endpoint is dry-run by default;
mutation requires apply=1 plus either RUN_KEY or an explicit confirmation token.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
import time
from typing import Any, Dict, List, Tuple

VERSION = "state-journal-reconciliation-guard-2026-05-13"
REPAIR_VERSION = "state-journal-safe-repair-2026-05-13"
REGISTERED_APP_IDS: set[int] = set()

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME
TRADE_JOURNAL_FILE = os.environ.get("TRADE_JOURNAL_FILE") or os.path.join(STATE_DIR, os.path.basename(os.environ.get("TRADE_JOURNAL_FILENAME", "trade_journal.json")))


def _now_text() -> str:
    try:
        import pytz
        tz = pytz.timezone(os.environ.get("MARKET_TZ", "America/Chicago"))
        return dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_key() -> str:
    try:
        import pytz
        tz = pytz.timezone(os.environ.get("MARKET_TZ", "America/Chicago"))
        return dt.datetime.now(tz).strftime("%Y-%m-%d")
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


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


def _load_state(core: Any | None = None) -> Dict[str, Any]:
    try:
        if core is not None and hasattr(core, "load_state"):
            obj = core.load_state()
            return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    return _load_json(STATE_FILE)


def _atomic_write_json(path: str, obj: Dict[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state_journal_repair_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=True, default=str)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def _save_state(state: Dict[str, Any], core: Any | None = None) -> Dict[str, Any]:
    try:
        if core is not None and hasattr(core, "save_state"):
            core.save_state(state)
            return {"saved_by": "core.save_state", "state_file": STATE_FILE}
    except Exception as exc:
        _atomic_write_json(STATE_FILE, state)
        return {"saved_by": "atomic_direct_write", "state_file": STATE_FILE, "core_save_error": str(exc)}
    _atomic_write_json(STATE_FILE, state)
    return {"saved_by": "atomic_direct_write", "state_file": STATE_FILE}


def _backup_state_file() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"created": False, "reason": "state_file_missing", "state_file": STATE_FILE}
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(os.path.dirname(STATE_FILE) or ".", f"state_backup_pre_journal_repair_{stamp}.json")
    shutil.copy2(STATE_FILE, backup_path)
    return {"created": True, "backup_path": backup_path, "state_file": STATE_FILE, "size_bytes": os.path.getsize(backup_path)}


def _f(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        out = float(value)
        return None if out != out else out
    except Exception:
        return None


def _money(value: Any) -> float:
    return round(float(value or 0.0), 2)


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


def _journal_full_exits(journal: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = journal.get("trades", []) if isinstance(journal.get("trades"), list) else []
    exits = []
    for row in rows:
        if isinstance(row, dict) and _symbol(row) and _action(row) == "exit" and any(k in row for k in ("price", "shares", "pnl_dollars", "pnl_pct", "exit_reason")):
            exits.append(dict(row))
    exits.sort(key=lambda r: _time_float(r) or 0.0)
    return exits


def _latest_full_exit_by_symbol(journal: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for row in _journal_full_exits(journal):
        sym = _symbol(row)
        if not sym:
            continue
        if sym not in latest or (_time_float(row) or 0.0) >= (_time_float(latest.get(sym, {})) or 0.0):
            latest[sym] = row
    return latest


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


def build_guard(state: Dict[str, Any] | None = None, journal: Dict[str, Any] | None = None, core: Any | None = None) -> Dict[str, Any]:
    state = state if isinstance(state, dict) else _load_state(core)
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
        if exit_ts is None or (entry_ts is not None and exit_ts < entry_ts - 60):
            continue
        open_shares = _f(pos.get("shares"))
        exit_shares = _f(exit_row.get("shares"))
        share_coverage = round(exit_shares / open_shares, 4) if open_shares and open_shares > 0 and exit_shares is not None else None
        repair_eligible = bool(share_coverage is not None and share_coverage >= 0.999)
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
            "repair_eligible": repair_eligible,
            "reason": "state_open_position_has_newer_journal_full_exit",
        })
    blocked_symbols = sorted({m["symbol"] for m in mismatches if m.get("symbol")})
    repairable_symbols = sorted({m["symbol"] for m in mismatches if m.get("symbol") and m.get("repair_eligible")})
    active = bool(blocked_symbols)
    return {
        "status": "ok",
        "type": "state_journal_reconciliation_guard",
        "version": VERSION,
        "repair_version": REPAIR_VERSION,
        "generated_local": _now_text(),
        "active": active,
        "reconciliation_status": "mismatch" if active else "ok",
        "safe_to_trade_guarded_symbols": not active,
        "blocked_symbols": blocked_symbols,
        "repairable_symbols": repairable_symbols,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "state_file": STATE_FILE,
        "trade_journal_file": TRADE_JOURNAL_FILE,
        "repair_endpoint": "/paper/state-journal-repair",
        "repair_requires": "apply=1 and confirm=repair-state-journal-mismatch; RUN_KEY is required when configured",
        "operator_message": "State still reports open position(s) after newer full journal exit(s); block add-ons for affected symbols until state and journal agree." if active else "No open-position/full-exit state-journal mismatch detected.",
        "recommended_actions": [
            "Block add-ons and new same-symbol entries for: " + ", ".join(blocked_symbols) + ".",
            "Use /paper/state-journal-repair as a dry run first, then apply only if the journal full exit is correct.",
            "After repair, rerun /paper/state-journal-guard-status and /paper/self-check before the next live/paper cycle.",
        ] if active else [],
    }


def _repair_plan(guard: Dict[str, Any]) -> Dict[str, Any]:
    mismatches = guard.get("mismatches") if isinstance(guard.get("mismatches"), list) else []
    repairable = [m for m in mismatches if isinstance(m, dict) and m.get("repair_eligible")]
    manual = [m for m in mismatches if isinstance(m, dict) and not m.get("repair_eligible")]
    return {
        "repairable_symbols": sorted({str(m.get("symbol", "")).upper() for m in repairable if m.get("symbol")}),
        "manual_review_symbols": sorted({str(m.get("symbol", "")).upper() for m in manual if m.get("symbol")}),
        "repairable_count": len(repairable),
        "manual_review_count": len(manual),
        "repair_steps": [
            "Back up state.json.",
            "Remove stale open rows from state.positions and performance.open_positions.",
            "Import missing journal full-exit row into state.trades if absent.",
            "Add missing realized P/L, cash proceeds, win/loss count, and cooldown if the exit was absent from state.trades.",
            "Recompute unrealized P/L and equity.",
        ] if repairable else [],
    }


def _positions_maps(state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    positions = state.get("positions")
    if not isinstance(positions, dict):
        positions = {str(s).upper(): {"symbol": str(s).upper()} for s in state.get("positions", []) if isinstance(s, str)} if isinstance(state.get("positions"), list) else {}
        state["positions"] = positions
    perf = state.setdefault("performance", {})
    if not isinstance(perf, dict):
        perf = {}
        state["performance"] = perf
    perf_open = perf.setdefault("open_positions", {})
    if not isinstance(perf_open, dict):
        perf_open = {}
        perf["open_positions"] = perf_open
    return positions, perf_open


def _remove_symbol(state: Dict[str, Any], sym: str) -> Dict[str, Any]:
    positions, perf_open = _positions_maps(state)
    removed = {"symbol": sym, "removed_from_positions": False, "removed_from_performance_open_positions": False}
    for source_name, source in (("positions", positions), ("performance_open_positions", perf_open)):
        for key in list(source.keys()):
            if str(key).upper() == sym:
                removed[f"removed_from_{source_name}"] = True
                removed[f"{source_name}_row"] = source.pop(key)
    return removed


def _duplicate_exit_in_state(state: Dict[str, Any], exit_row: Dict[str, Any]) -> bool:
    sym = _symbol(exit_row)
    ts = _time_float(exit_row)
    price = _f(exit_row.get("price"))
    shares = _f(exit_row.get("shares"))
    trades = state.get("trades") if isinstance(state.get("trades"), list) else []
    for row in trades:
        if not isinstance(row, dict) or _action(row) != "exit" or _symbol(row) != sym:
            continue
        r_ts = _time_float(row)
        time_match = ts is not None and r_ts is not None and abs(ts - r_ts) <= 2
        price_match = price is not None and _f(row.get("price")) is not None and abs(price - (_f(row.get("price")) or 0.0)) <= 0.01
        shares_match = shares is not None and _f(row.get("shares")) is not None and abs(shares - (_f(row.get("shares")) or 0.0)) <= 0.00001
        if time_match or (price_match and shares_match):
            return True
    return False


def _recompute_unrealized(state: Dict[str, Any]) -> float:
    perf = state.setdefault("performance", {})
    perf_open = perf.get("open_positions") if isinstance(perf.get("open_positions"), dict) else {}
    total = 0.0
    for pos in perf_open.values():
        if not isinstance(pos, dict):
            continue
        pnl = _f(pos.get("pnl_dollars"))
        if pnl is None:
            shares = _f(pos.get("shares")) or 0.0
            entry = _f(pos.get("entry")) or _f(pos.get("entry_price")) or 0.0
            last = _f(pos.get("last_price")) or entry
            pnl = (last - entry) * shares if str(pos.get("side") or "long").lower() != "short" else (entry - last) * shares
        total += pnl or 0.0
    perf["unrealized_pnl"] = _money(total)
    return perf["unrealized_pnl"]


def _apply_exit_accounting(state: Dict[str, Any], exit_row: Dict[str, Any]) -> Dict[str, Any]:
    pnl = _f(exit_row.get("pnl_dollars")) or 0.0
    shares = _f(exit_row.get("shares")) or 0.0
    price = _f(exit_row.get("price")) or 0.0
    proceeds = shares * price
    trades = state.setdefault("trades", [])
    if not isinstance(trades, list):
        trades = []
        state["trades"] = trades
    imported = dict(exit_row)
    imported.setdefault("action", "exit")
    imported.setdefault("journal_repair_imported", True)
    imported.setdefault("journal_repair_imported_local", _now_text())
    trades.append(imported)

    rp = state.setdefault("realized_pnl", {})
    if not isinstance(rp, dict):
        rp = {}
        state["realized_pnl"] = rp
    today = _today_key()
    if rp.get("date") != today:
        rp.update({"date": today, "today": 0.0, "wins_today": 0, "losses_today": 0})
    rp["today"] = _money((_f(rp.get("today")) or 0.0) + pnl)
    rp["total"] = _money((_f(rp.get("total")) or 0.0) + pnl)
    rp["wins_today"] = int(rp.get("wins_today") or 0) + (1 if pnl >= 0 else 0)
    rp["losses_today"] = int(rp.get("losses_today") or 0) + (0 if pnl >= 0 else 1)
    rp["wins_total"] = int(rp.get("wins_total") or 0) + (1 if pnl >= 0 else 0)
    rp["losses_total"] = int(rp.get("losses_total") or 0) + (0 if pnl >= 0 else 1)

    perf = state.setdefault("performance", {})
    perf["realized_pnl_today"] = rp["today"]
    perf["realized_pnl_total"] = rp["total"]
    perf["wins_today"] = rp["wins_today"]
    perf["losses_today"] = rp["losses_today"]
    perf["wins_total"] = rp["wins_total"]
    perf["losses_total"] = rp["losses_total"]

    state["cash"] = _money((_f(state.get("cash")) or 0.0) + proceeds)
    unrealized = _recompute_unrealized(state)
    state["equity"] = _money((_f(state.get("cash")) or 0.0) + unrealized)
    return {"state_trade_appended": True, "pnl_dollars_added": round(pnl, 4), "cash_added_from_exit_proceeds": round(proceeds, 4), "cash_after": state["cash"], "equity_after": state["equity"], "trades_count_after": len(trades)}


def _apply_cooldown(state: Dict[str, Any], exit_row: Dict[str, Any]) -> Dict[str, Any]:
    sym = _symbol(exit_row)
    exit_ts = _time_float(exit_row) or time.time()
    seconds = int(_f(exit_row.get("cooldown_seconds")) or int(os.environ.get("COOLDOWN_SECONDS", "1800")))
    risk = state.setdefault("risk_controls", {})
    if not isinstance(risk, dict):
        risk = {}
        state["risk_controls"] = risk
    cooldowns = risk.setdefault("cooldowns", {})
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        risk["cooldowns"] = cooldowns
    cooldowns[sym] = max(int(_f(cooldowns.get(sym)) or 0), int(exit_ts + seconds))
    return {"cooldown_symbol": sym, "cooldown_until_ts": cooldowns[sym], "cooldown_seconds": seconds}


def _authorized(req: Any) -> Tuple[bool, str]:
    run_key = os.environ.get("RUN_KEY", "changeme")
    if run_key and run_key != "changeme":
        supplied = req.headers.get("X-Run-Key") or req.args.get("key") or req.args.get("run_key") or ""
        return (True, "authorized_with_run_key") if supplied == run_key else (False, "RUN_KEY_required_for_mutating_repair")
    return (True, "authorized_with_confirm_only_RUN_KEY_not_configured") if req.args.get("confirm") == "repair-state-journal-mismatch" else (False, "confirm=repair-state-journal-mismatch_required_when_RUN_KEY_not_configured")


def repair_state_from_journal(apply: bool = False, core: Any | None = None) -> Dict[str, Any]:
    state = _load_state(core)
    journal = _load_json(TRADE_JOURNAL_FILE)
    guard = build_guard(state, journal, core)
    plan = _repair_plan(guard)
    result: Dict[str, Any] = {"status": "ok", "type": "state_journal_repair", "version": REPAIR_VERSION, "generated_local": _now_text(), "apply": bool(apply), "dry_run": not apply, "guard": guard, "plan": plan, "actions_taken": []}
    if not guard.get("active"):
        result["message"] = "No repair needed. State and journal do not show an open-position/full-exit mismatch."
        return result
    if not plan.get("repairable_symbols"):
        result.update({"status": "needs_manual_review", "message": "Mismatch found, but no symbol has a full-share journal exit eligible for automatic repair."})
        return result
    if not apply:
        result.update({"message": "Dry run only. No state was changed.", "apply_hint": "/paper/state-journal-repair?apply=1&confirm=repair-state-journal-mismatch"})
        return result

    backup = _backup_state_file()
    latest_exit = _latest_full_exit_by_symbol(journal)
    repaired: List[str] = []
    skipped: List[Dict[str, Any]] = []
    for sym in plan.get("repairable_symbols", []):
        exit_row = latest_exit.get(sym)
        if not exit_row:
            skipped.append({"symbol": sym, "reason": "latest_exit_missing"})
            continue
        duplicate = _duplicate_exit_in_state(state, exit_row)
        action: Dict[str, Any] = {"symbol": sym, "duplicate_exit_already_in_state_trades": duplicate, "removed": _remove_symbol(state, sym)}
        if not duplicate:
            action.update(_apply_exit_accounting(state, exit_row))
        else:
            action.update({"state_trade_appended": False, "accounting_adjusted": False})
            _recompute_unrealized(state)
        action.update(_apply_cooldown(state, exit_row))
        repaired.append(sym)
        result["actions_taken"].append(action)

    repairs = state.setdefault("state_journal_repairs", [])
    if not isinstance(repairs, list):
        repairs = []
        state["state_journal_repairs"] = repairs
    repairs.append({"version": REPAIR_VERSION, "repaired_local": _now_text(), "repaired_symbols": repaired, "skipped_symbols": skipped, "guard_before": guard, "backup": backup})
    state["state_journal_reconciliation_guard"] = {"last_repair_version": REPAIR_VERSION, "last_repair_local": _now_text(), "last_repaired_symbols": repaired}
    result.update({"backup": backup, "repaired_symbols": repaired, "skipped_symbols": skipped, "save": _save_state(state, core)})
    result["post_repair_guard"] = build_guard(_load_state(core), _load_json(TRADE_JOURNAL_FILE), core)
    result["message"] = "State repair applied. Rerun /paper/state-journal-guard-status and /paper/self-check to verify."
    return result


def status_payload(core: Any | None = None) -> Dict[str, Any]:
    return build_guard(core=core)


def register_routes(flask_app: Any, core: Any | None = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    if id(flask_app) in REGISTERED_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify, request
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/state-journal-guard-status" not in existing:
        flask_app.add_url_rule("/paper/state-journal-guard-status", "state_journal_guard_status", lambda: jsonify(status_payload(core)))
    if "/paper/state-journal-repair" not in existing:
        def state_journal_repair_route():
            apply_flag = str(request.args.get("apply", "0")).lower() in {"1", "true", "yes", "on"}
            if apply_flag:
                ok, reason = _authorized(request)
                if not ok:
                    return jsonify({"status": "blocked", "type": "state_journal_repair", "version": REPAIR_VERSION, "generated_local": _now_text(), "apply": False, "authorization_status": reason, "message": "Mutating repair was blocked. Run dry-run without apply=1, or provide the required key/confirmation.", "dry_run": repair_state_from_journal(apply=False, core=core)}), 403
            return jsonify(repair_state_from_journal(apply=apply_flag, core=core))
        flask_app.add_url_rule("/paper/state-journal-repair", "state_journal_repair", state_journal_repair_route, methods=["GET", "POST"])
    if "/paper/state-journal-repair-status" not in existing:
        flask_app.add_url_rule("/paper/state-journal-repair-status", "state_journal_repair_status", lambda: jsonify(repair_state_from_journal(apply=False, core=core)))
    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "repair_version": REPAIR_VERSION, "registered": True}
