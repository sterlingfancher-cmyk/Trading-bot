"""One-shot Stable Paper recovery for the proven 2026-08-12 bad-tick incident.

This migration is intentionally exact-signature and paper-only.  It archives the
contaminated epoch, reverses only the LRCX 36.26 bad-tick mutation, restores the
remaining LRCX lot, rotates the old canonical ledger/journal into forensic
history, and starts a new verified snapshot epoch under a validation hold.

It does not weaken risk limits or change strategy, sizing, live, or ML authority.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import shutil
from typing import Any, Dict, List

VERSION = "verified-snapshot-epoch-recovery-2026-08-12-v1"
OLD_EPOCH_ID = "stable-paper-v1-20260810-clean01"
TARGET_EPOCH_ID = "stable-paper-v2-20260812-verified01"
DECISION_ID = "verified-bad-tick-and-ledger-divergence-2026-08-12"
BAD_EXECUTION_ID = "5ca38922916e4612ae3cda8d9801107d"
BAD_VST_EXECUTION_ID = "36dbe6c2ee0f4b7bbc8be8f6794105a6"
EXPECTED_CURRENT_CASH = 10892.683154582748
LRCX_QTY = 3.42486
LRCX_ENTRY = 312.90
BAD_PRICE = 36.26
VERIFIED_MARK = 326.24
BAD_PROCEEDS = LRCX_QTY * BAD_PRICE
BAD_REALIZED = (BAD_PRICE - LRCX_ENTRY) * LRCX_QTY
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
ARCHIVE_ROOT = os.path.join(STATE_DIR, "forensic_archives")
MARKER_FILE = os.path.join(STATE_DIR, f"verified_snapshot_{DECISION_ID}.json")
_LAST_STATUS: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _paper_only() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _atomic_json(path: str, payload: Dict[str, Any]) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _marker() -> Dict[str, Any]:
    try:
        with open(MARKER_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _row_matches(row: Dict[str, Any], execution_id: str, symbol: str, action: str, price: float, qty: float) -> bool:
    return bool(
        str(row.get("execution_id") or "") == execution_id
        and str(row.get("symbol") or "").upper() == symbol
        and str(row.get("action") or "").lower() == action
        and abs(_f(row.get("price")) - price) <= 1e-6
        and abs(_f(row.get("shares", row.get("qty"))) - qty) <= 1e-6
    )


def contamination_signature(pf: Dict[str, Any]) -> bool:
    epoch = _d(pf.get("paper_accounting_epoch"))
    trades = _l(pf.get("trades"))
    risk = _d(pf.get("risk_controls"))
    if str(epoch.get("id") or "") != OLD_EPOCH_ID or len(trades) != 11:
        return False
    if _d(pf.get("positions")):
        return False
    if abs(_f(pf.get("cash")) - EXPECTED_CURRENT_CASH) > 1.0:
        return False
    if not bool(risk.get("halted", False)):
        return False
    if "absolute daily equity loss halt" not in str(risk.get("halt_reason") or ""):
        return False
    last = trades[-1] if trades and isinstance(trades[-1], dict) else {}
    vst = trades[4] if len(trades) > 4 and isinstance(trades[4], dict) else {}
    return _row_matches(last, BAD_EXECUTION_ID, "LRCX", "exit", BAD_PRICE, LRCX_QTY) and _row_matches(
        vst, BAD_VST_EXECUTION_ID, "VST", "exit", 20.16, 11.014993
    )


def _archive_state(core: Any) -> Dict[str, Any]:
    os.makedirs(ARCHIVE_ROOT, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = os.path.join(ARCHIVE_ROOT, f"{stamp}_{DECISION_ID}")
    os.makedirs(archive_dir, exist_ok=False)
    root_abs = os.path.abspath(ARCHIVE_ROOT)
    copied: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(STATE_DIR)):
        src = os.path.join(STATE_DIR, name)
        src_abs = os.path.abspath(src)
        if src_abs == root_abs or src_abs.startswith(root_abs + os.sep):
            continue
        dst = os.path.join(archive_dir, name)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
                copied.append({"name": name, "type": "directory"})
            elif os.path.isfile(src):
                shutil.copy2(src, dst)
                copied.append({"name": name, "type": "file", "size_bytes": os.path.getsize(dst)})
        except Exception as exc:
            copied.append({"name": name, "type": "copy_error", "error": f"{type(exc).__name__}: {exc}"})
    manifest = {
        "status": "ok",
        "type": "verified_snapshot_epoch_forensic_archive",
        "version": VERSION,
        "decision_id": DECISION_ID,
        "old_epoch_id": OLD_EPOCH_ID,
        "target_epoch_id": TARGET_EPOCH_ID,
        "created_local": _now(core),
        "archive_dir": archive_dir,
        "market_evidence": {
            "source": "Alpaca IEX 1-minute bars independently verified before migration",
            "LRCX_2026_08_12_15_43_UTC": {"open": 326.515, "high": 326.515, "low": 326.24, "close": 326.24},
            "VST_2026_08_11_14_38_to_14_40_UTC": {"observed_range_approx": [145.905, 146.45], "bad_recorded_price": 20.16},
            "bad_lrcx_recorded_price": BAD_PRICE,
        },
        "bad_execution_id": BAD_EXECUTION_ID,
        "copied_entries": copied,
    }
    _atomic_json(os.path.join(archive_dir, "verified_snapshot_recovery_manifest.json"), manifest)
    return manifest


def _adjust_realized(state: Dict[str, Any], correction: float) -> tuple[float, float]:
    realized = _d(state.setdefault("realized_pnl", {}))
    today_key = "today" if "today" in realized or "realized_today" not in realized else "realized_today"
    current_today = _f(realized.get(today_key), _f(_d(state.get("performance")).get("realized_pnl_today"), 0.0))
    current_total = _f(realized.get("total"), _f(_d(state.get("performance")).get("realized_pnl_total"), 0.0))
    corrected_today = current_today + correction
    corrected_total = current_total + correction
    realized[today_key] = corrected_today
    realized["total"] = corrected_total
    if _f(realized.get("losses_today"), 0.0) > 0:
        realized["losses_today"] = max(0, int(_f(realized.get("losses_today"))) - 1)
    if _f(realized.get("losses_total"), 0.0) > 0:
        realized["losses_total"] = max(0, int(_f(realized.get("losses_total"))) - 1)
    state["realized_pnl"] = realized
    perf = _d(state.setdefault("performance", {}))
    perf["realized_pnl_today"] = corrected_today
    perf["realized_pnl_total"] = corrected_total
    if _f(perf.get("losses_today"), 0.0) > 0:
        perf["losses_today"] = max(0, int(_f(perf.get("losses_today"))) - 1)
    if _f(perf.get("losses_total"), 0.0) > 0:
        perf["losses_total"] = max(0, int(_f(perf.get("losses_total"))) - 1)
    state["performance"] = perf
    return corrected_today, corrected_total


def build_recovered_state(pf: Dict[str, Any], archive_dir: str, started_local: str) -> Dict[str, Any]:
    state = copy.deepcopy(pf)
    corrected_cash = _f(state.get("cash")) - BAD_PROCEEDS
    correction = -BAD_REALIZED
    corrected_today, corrected_total = _adjust_realized(state, correction)
    unrealized = (VERIFIED_MARK - LRCX_ENTRY) * LRCX_QTY
    market_value = VERIFIED_MARK * LRCX_QTY
    position = {
        "symbol": "LRCX",
        "side": "long",
        "shares": LRCX_QTY,
        "qty": LRCX_QTY,
        "entry": LRCX_ENTRY,
        "entry_price": LRCX_ENTRY,
        "last_price": VERIFIED_MARK,
        "peak": max(VERIFIED_MARK, 327.1188),
        "partial_taken": True,
        "last_partial_exit_time": 1786541619,
        "cost_basis": LRCX_ENTRY * LRCX_QTY,
        "market_value": market_value,
        "unrealized_pnl": unrealized,
        "pnl_dollars": unrealized,
        "pnl_pct": (VERIFIED_MARK - LRCX_ENTRY) / LRCX_ENTRY * 100.0,
        "verified_snapshot_recovery_version": VERSION,
    }
    state["cash"] = corrected_cash
    state["positions"] = {"LRCX": position}
    state["equity"] = corrected_cash + market_value
    state["trades"] = []
    state["accounting_epoch_id"] = TARGET_EPOCH_ID
    history = _l(state.get("history"))
    history.append(state["equity"])
    state["history"] = history[-500:]
    perf = _d(state.setdefault("performance", {}))
    perf["unrealized_pnl"] = unrealized
    perf["open_positions"] = {"LRCX": copy.deepcopy(position)}
    state["performance"] = perf

    risk = _d(state.setdefault("risk_controls", {}))
    risk.update({
        "halted": True,
        "halt_reason": "verified snapshot recovery validation hold",
        "verified_snapshot_validation_hold": True,
        "verified_snapshot_validation_hold_reason": "verify repaired snapshot persistence and accounting before new entries",
        "clean_epoch_validation_hold": False,
        "self_defense_active": False,
        "self_defense_reason": "verified snapshot recovery validation hold",
        "day_start_equity": state["equity"],
        "day_peak_equity": state["equity"],
        "day_pnl_pct": 0.0,
        "daily_loss_pct": 0.0,
        "daily_drawdown_pct": 0.0,
        "intraday_drawdown_pct": 0.0,
        "net_daily_loss_pct": 0.0,
        "bad_tick_recovery_execution_id": BAD_EXECUTION_ID,
        "bad_tick_recovery_version": VERSION,
    })
    state["risk_controls"] = risk

    snapshot = {
        "verified": True,
        "version": VERSION,
        "started_local": started_local,
        "cash": corrected_cash,
        "equity": state["equity"],
        "realized_today": corrected_today,
        "realized_total": corrected_total,
        "positions": {"LRCX": {"side": "long", "qty": LRCX_QTY, "entry_price": LRCX_ENTRY, "mark": VERIFIED_MARK}},
        "bad_tick_reversed": {"execution_id": BAD_EXECUTION_ID, "price": BAD_PRICE, "qty": LRCX_QTY, "cash_proceeds_removed": BAD_PROCEEDS, "realized_pnl_reversed": BAD_REALIZED},
    }
    state["paper_accounting_epoch"] = {
        "version": VERSION,
        "id": TARGET_EPOCH_ID,
        "decision_id": DECISION_ID,
        "started_local": started_local,
        "starting_cash": corrected_cash,
        "starting_equity": state["equity"],
        "clean_start": False,
        "zero_trade_baseline": False,
        "baseline_type": "verified_snapshot_with_open_position",
        "verified_snapshot_baseline": snapshot,
        "historical_recovery_decision": "verified_snapshot_rollforward",
        "prior_epoch_id": OLD_EPOCH_ID,
        "prior_epoch_disposition": "archived_after_proven_bad_ticks_and_state_ledger_divergence",
        "historical_evidence_archived": True,
        "forensic_archive_dir": archive_dir,
        "validation_hold": True,
        "validation_hold_reason": "verified snapshot recovery validation hold",
        "forward_validation_required": True,
        "valid_path_rows_baseline": 0,
    }
    return state


def _rotate_journal(state: Dict[str, Any]) -> None:
    try:
        import trade_journal as tj
        factory = getattr(tj, "_empty_journal", None)
        journal = factory() if callable(factory) else {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
        if not isinstance(journal, dict):
            journal = {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
        journal["accounting_epoch_id"] = TARGET_EPOCH_ID
        journal["verified_snapshot_epoch_started_local"] = _now()
        for attr in ("TRADE_JOURNAL_FILE", "TRADE_JOURNAL_BACKUP_FILE"):
            path = str(getattr(tj, attr, "") or "")
            if path:
                _atomic_json(path, journal)
        mirror = getattr(tj, "mirror_state", None)
        if callable(mirror):
            mirror(state, source="verified_snapshot_epoch_recovery", source_file=str(getattr(tj, "STATE_FILE", "") or ""))
    except Exception:
        pass


def _cutover(core: Any) -> Dict[str, Any]:
    global _LAST_STATUS
    import clean_accounting_epoch as clean
    archive = _archive_state(core)
    started = _now(core)
    started_marker = {"status": "cutover_started", "version": VERSION, "decision_id": DECISION_ID, "target_epoch_id": TARGET_EPOCH_ID, "archive_dir": archive.get("archive_dir"), "started_local": started}
    _atomic_json(MARKER_FILE, started_marker)
    recovered = build_recovered_state(_portfolio(core), str(archive.get("archive_dir") or ""), started)
    with clean._runtime_locks():
        state_file = clean._write_clean_state_and_backups(core, recovered)
        clean._rotate_canonical_ledger()
        _rotate_journal(recovered)
        clean._reset_snapshot_archive(recovered, state_file)
        pf = _portfolio(core)
        pf.clear()
        pf.update(recovered)
    completed = dict(started_marker)
    completed.update({"status": "completed", "completed_local": _now(core), "state_file": state_file, "validation_hold": True, "corrected_cash": recovered.get("cash"), "corrected_equity": recovered.get("equity"), "restored_positions": ["LRCX"]})
    _atomic_json(MARKER_FILE, completed)
    _LAST_STATUS = completed
    return completed


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST_STATUS
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not _paper_only():
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "paper_runtime_only"}
    pf = _portfolio(core)
    epoch = _d(pf.get("paper_accounting_epoch"))
    if str(epoch.get("id") or "") == TARGET_EPOCH_ID:
        hold = bool(_d(pf.get("risk_controls")).get("verified_snapshot_validation_hold", False))
        return {"status": "validation_hold" if hold else "active", "overall": "warn" if hold else "pass", "version": VERSION, "epoch_id": TARGET_EPOCH_ID, "validation_hold": hold, "forensic_archive_dir": epoch.get("forensic_archive_dir")}
    marker = _marker()
    if marker.get("status") == "completed":
        return dict(marker)
    if not contamination_signature(pf):
        return {"status": "not_applicable", "overall": "pass", "version": VERSION, "reason": "exact_contamination_signature_not_present"}
    try:
        import canonical_execution_ledger as ledger
        ledger_status = ledger.status_payload(core)
    except Exception as exc:
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "canonical_ledger_status_unavailable", "error": f"{type(exc).__name__}: {exc}"}
    if not bool(ledger_status.get("chain_valid")) or int(ledger_status.get("row_count") or 0) != 11:
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "canonical_ledger_signature_mismatch", "ledger": ledger_status}
    try:
        import paper_exit_bad_tick_guard as bad_tick
        if not bool(bad_tick.status_payload(core).get("hook_applied")):
            return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "future_bad_tick_guard_not_active"}
    except Exception as exc:
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "future_bad_tick_guard_unavailable", "error": f"{type(exc).__name__}: {exc}"}
    return _cutover(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
