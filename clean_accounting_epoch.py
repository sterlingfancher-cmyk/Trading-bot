"""One-time clean accounting epoch cutover after failed historical recovery.

The 2026-08-10 compact audit proved that the mirrored historical trade journal is
not a trustworthy recovery source (incomplete entry/exit coverage).  Stable Core
therefore starts a new paper-accounting epoch instead of fabricating missing
history.

This module is intentionally narrow and one-shot:

* paper runtime only
* requires the known contaminated-account signature
* requires the historical journal recovery candidate to be untrusted
* requires the new canonical execution ledger to be healthy and still empty
* archives the entire persistent state directory before mutation
* starts a clean $10,000 accounting epoch with no positions/trades/P&L
* rotates state backups, mirrored journal, canonical ledger, and snapshots so
  contaminated persistence cannot be resurrected by fallback recovery
* keeps a hard validation hold active after cutover

It does not alter scanner/strategy logic, thresholds, sizing, risk limits, live
or ML authority.  The validation hold is deliberately not cleared here.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import shutil
import threading
from typing import Any, Dict, Iterator, List

VERSION = "clean-accounting-epoch-2026-08-10-v1"
DECISION_ID = "journal-recovery-incomplete-2026-08-10"
TARGET_EPOCH_ID = "stable-paper-v1-20260810-clean01"
STARTING_CASH = float(os.environ.get("CLEAN_EPOCH_STARTING_CASH", "10000"))

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
ARCHIVE_ROOT = os.path.join(STATE_DIR, "forensic_archives")
MARKER_FILE = os.path.join(STATE_DIR, f"clean_epoch_{DECISION_ID}.json")

_LOCK = threading.RLock()
_REGISTERED_APP_IDS: set[int] = set()
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


def _paper_only() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _portfolio(core: Any = None) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _epoch(pf: Dict[str, Any]) -> Dict[str, Any]:
    return _d(pf.get("paper_accounting_epoch"))


def _marker() -> Dict[str, Any]:
    try:
        with open(MARKER_FILE, "r", encoding="utf-8") as handle:
            obj = json.load(handle)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


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


def _sha256(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()
    except Exception:
        return None


def _copy_file_atomic(src: str, dst: str) -> None:
    folder = os.path.dirname(dst)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = dst + ".tmp"
    shutil.copy2(src, tmp)
    with open(tmp, "rb") as handle:
        os.fsync(handle.fileno())
    os.replace(tmp, dst)


def _archive_persistent_state(core: Any, journal: Dict[str, Any], ledger: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(ARCHIVE_ROOT, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = os.path.join(ARCHIVE_ROOT, f"{stamp}_{DECISION_ID}")
    os.makedirs(archive_dir, exist_ok=False)

    copied: List[Dict[str, Any]] = []
    archive_root_abs = os.path.abspath(ARCHIVE_ROOT)
    for name in sorted(os.listdir(STATE_DIR)):
        source = os.path.join(STATE_DIR, name)
        source_abs = os.path.abspath(source)
        if source_abs == archive_root_abs or source_abs.startswith(archive_root_abs + os.sep):
            continue
        destination = os.path.join(archive_dir, name)
        try:
            if os.path.isdir(source):
                shutil.copytree(source, destination)
                copied.append({"name": name, "type": "directory"})
            elif os.path.isfile(source):
                shutil.copy2(source, destination)
                copied.append({
                    "name": name,
                    "type": "file",
                    "size_bytes": os.path.getsize(destination),
                    "sha256": _sha256(destination),
                })
        except Exception as exc:
            copied.append({"name": name, "type": "copy_error", "error": f"{type(exc).__name__}: {exc}"})

    pf = _portfolio(core)
    manifest = {
        "status": "ok",
        "type": "clean_accounting_epoch_forensic_archive",
        "version": VERSION,
        "decision_id": DECISION_ID,
        "target_epoch_id": TARGET_EPOCH_ID,
        "created_local": _now(core),
        "archive_dir": archive_dir,
        "pre_cutover_account": {
            "cash": pf.get("cash"),
            "equity": pf.get("equity"),
            "positions": sorted(_d(pf.get("positions")).keys()),
            "trade_rows": len(_l(pf.get("trades"))),
            "risk_halted": bool(_d(pf.get("risk_controls")).get("halted", False)),
            "halt_reason": _d(pf.get("risk_controls")).get("halt_reason"),
        },
        "journal_recovery_evidence": {
            "journal_trade_rows": journal.get("journal_trade_rows"),
            "deduplicated_execution_rows": journal.get("deduplicated_execution_rows"),
            "entry_rows": journal.get("entry_rows"),
            "exit_rows": journal.get("exit_rows"),
            "coverage_complete": journal.get("coverage_complete"),
            "coverage_issue_count": journal.get("coverage_issue_count"),
            "economic_issue_count": journal.get("economic_issue_count"),
            "trusted_recovery_candidate": journal.get("trusted_recovery_candidate"),
        },
        "canonical_ledger_before_cutover": {
            "chain_valid": ledger.get("chain_valid"),
            "row_count": ledger.get("row_count"),
            "current_epoch_id": ledger.get("current_epoch_id"),
            "authoritative_for_new_executions": ledger.get("authoritative_for_new_executions"),
        },
        "copied_entries": copied,
    }
    _atomic_json(os.path.join(archive_dir, "clean_epoch_archive_manifest.json"), manifest)
    return manifest


def _base_state(core: Any) -> Dict[str, Any]:
    fn = getattr(core, "default_state", None)
    try:
        value = fn() if callable(fn) else {}
    except Exception:
        value = {}
    return value if isinstance(value, dict) else {}


def build_clean_state(core: Any, archive_manifest: Dict[str, Any], journal: Dict[str, Any]) -> Dict[str, Any]:
    state = _base_state(core)
    state["initial_cash"] = float(STARTING_CASH)
    state["starting_cash"] = float(STARTING_CASH)
    state["initial_equity"] = float(STARTING_CASH)
    state["cash"] = float(STARTING_CASH)
    state["equity"] = float(STARTING_CASH)
    state["peak"] = float(STARTING_CASH)
    state["history"] = [float(STARTING_CASH)]
    state["positions"] = {}
    state["trades"] = []
    state["last_market"] = {}

    risk_fn = getattr(core, "default_risk_controls", None)
    try:
        risk = risk_fn() if callable(risk_fn) else {}
    except Exception:
        risk = {}
    risk = risk if isinstance(risk, dict) else {}
    risk.update({
        "day_start_equity": float(STARTING_CASH),
        "day_peak_equity": float(STARTING_CASH),
        "day_pnl_pct": 0.0,
        "daily_loss_pct": 0.0,
        "daily_drawdown_pct": 0.0,
        "intraday_drawdown_pct": 0.0,
        "halted": True,
        "halt_reason": "clean accounting epoch validation hold",
        "clean_epoch_validation_hold": True,
        "clean_epoch_validation_hold_reason": "verify zero-trade baseline and persistence before releasing execution",
        "profit_guard_active": False,
        "profit_guard_reason": "",
        "self_defense_active": False,
        "self_defense_reason": "",
        "cooldowns": {},
    })
    state["risk_controls"] = risk

    for key, factory_name in (
        ("auto_runner", "default_auto_runner"),
        ("realized_pnl", "default_realized_pnl"),
        ("performance", "default_performance"),
        ("feedback_loop", "default_feedback_loop"),
        ("reports", "default_reports"),
        ("scanner_audit", "default_scanner_audit"),
    ):
        factory = getattr(core, factory_name, None)
        try:
            value = factory() if callable(factory) else state.get(key, {})
        except Exception:
            value = state.get(key, {})
        state[key] = value if isinstance(value, dict) else {}

    realized = _d(state.get("realized_pnl"))
    realized.update({"today": 0.0, "total": 0.0, "wins_today": 0, "losses_today": 0, "wins_total": 0, "losses_total": 0})
    state["realized_pnl"] = realized
    perf = _d(state.get("performance"))
    perf.update({
        "realized_pnl_today": 0.0,
        "realized_pnl_total": 0.0,
        "unrealized_pnl": 0.0,
        "wins_today": 0,
        "losses_today": 0,
        "wins_total": 0,
        "losses_total": 0,
        "open_positions": {},
    })
    state["performance"] = perf
    state["pullback_watchlist"] = {}

    started = _now(core)
    state["accounting_epoch_id"] = TARGET_EPOCH_ID
    state["paper_accounting_epoch"] = {
        "version": VERSION,
        "id": TARGET_EPOCH_ID,
        "decision_id": DECISION_ID,
        "started_local": started,
        "starting_cash": float(STARTING_CASH),
        "clean_start": True,
        "zero_trade_baseline": True,
        "historical_recovery_decision": "clean_epoch",
        "historical_journal_trusted": False,
        "historical_evidence_archived": True,
        "forensic_archive_dir": archive_manifest.get("archive_dir"),
        "journal_coverage_issue_count": int(journal.get("coverage_issue_count") or 0),
        "journal_economic_issue_count": int(journal.get("economic_issue_count") or 0),
        "forward_validation_required": True,
        "valid_path_rows_baseline": 0,
        "validation_hold": True,
        "validation_hold_reason": "clean accounting epoch validation hold",
        "stable_paper_day_count": 0,
    }
    return state


def _contamination_signature(pf: Dict[str, Any]) -> bool:
    if _epoch(pf).get("id") == TARGET_EPOCH_ID:
        return False
    risk = _d(pf.get("risk_controls"))
    cash = _f(pf.get("cash"), 0.0)
    equity = _f(pf.get("equity"), 0.0)
    trades = _l(pf.get("trades"))
    return bool(
        risk.get("halted", False)
        and len(trades) > 0
        and (cash < -1000.0 or equity < 0.0)
    )


@contextlib.contextmanager
def _runtime_locks() -> Iterator[None]:
    """Match existing journal->state lock order to avoid watcher deadlocks."""
    journal_lock = None
    state_lock = None
    file_lock = None
    try:
        try:
            import trade_journal as tj
            journal_lock = getattr(tj, "_MIRROR_LOCK", None)
        except Exception:
            journal_lock = None
        try:
            import state_io_hardening as sio
            state_lock = getattr(sio, "_THREAD_LOCK", None)
            file_lock_cls = getattr(sio, "_FileLock", None)
            file_lock = file_lock_cls(exclusive=True) if callable(file_lock_cls) else None
        except Exception:
            state_lock = None
            file_lock = None
        if journal_lock is not None:
            journal_lock.acquire()
        if state_lock is not None:
            state_lock.acquire()
        if file_lock is not None:
            file_lock.__enter__()
        yield
    finally:
        if file_lock is not None:
            try:
                file_lock.__exit__(None, None, None)
            except Exception:
                pass
        if state_lock is not None:
            try:
                state_lock.release()
            except Exception:
                pass
        if journal_lock is not None:
            try:
                journal_lock.release()
            except Exception:
                pass


def _write_clean_state_and_backups(core: Any, state: Dict[str, Any]) -> str:
    state_file = str(getattr(core, "STATE_FILE", os.path.join(STATE_DIR, "state.json")))
    try:
        import state_io_hardening as sio
        sio.atomic_json_write(state_file, state)
        backups = [
            getattr(sio, "STATE_BACKUP_LATEST", None),
            getattr(sio, "STATE_BACKUP_LARGEST", None),
            getattr(sio, "STATE_BACKUP_PREWRITE", None),
        ]
    except Exception:
        _atomic_json(state_file, state)
        backups = []
    app_backup = state_file + ".bak"
    backups.append(app_backup)
    for path in backups:
        if path:
            _copy_file_atomic(state_file, str(path))
    return state_file


def _rotate_journal(state: Dict[str, Any]) -> None:
    try:
        import trade_journal as tj
    except Exception:
        return
    empty_factory = getattr(tj, "_empty_journal", None)
    try:
        journal = empty_factory() if callable(empty_factory) else {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
    except Exception:
        journal = {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
    if not isinstance(journal, dict):
        journal = {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
    journal["accounting_epoch_id"] = TARGET_EPOCH_ID
    journal["clean_epoch_started_local"] = _now()
    for attr in ("TRADE_JOURNAL_FILE", "TRADE_JOURNAL_BACKUP_FILE"):
        path = str(getattr(tj, attr, "") or "")
        if path:
            _atomic_json(path, journal)
    try:
        mirror = getattr(tj, "mirror_state", None)
        if callable(mirror):
            mirror(state, source="clean_accounting_epoch", source_file=str(getattr(tj, "STATE_FILE", "") or ""))
    except Exception:
        pass


def _rotate_canonical_ledger() -> None:
    try:
        import canonical_execution_ledger as ledger
        lock = getattr(ledger, "_LOCK", None)
        if lock is not None:
            lock.acquire()
        try:
            path = str(getattr(ledger, "LEDGER_FILE", "") or "")
            if path:
                folder = os.path.dirname(path)
                if folder:
                    os.makedirs(folder, exist_ok=True)
                with open(path, "w", encoding="utf-8") as handle:
                    handle.flush()
                    os.fsync(handle.fileno())
        finally:
            if lock is not None:
                lock.release()
    except Exception:
        pass


def _reset_snapshot_archive(state: Dict[str, Any], state_file: str) -> None:
    try:
        import state_snapshot_archive as snapshots
        directory = str(getattr(snapshots, "SNAPSHOT_DIR", "") or "")
        if directory:
            shutil.rmtree(directory, ignore_errors=True)
            os.makedirs(directory, exist_ok=True)
        archive = getattr(snapshots, "archive_state", None)
        if callable(archive):
            archive(state, state_file)
    except Exception:
        pass


def _cutover(core: Any, journal: Dict[str, Any], ledger: Dict[str, Any]) -> Dict[str, Any]:
    global _LAST_STATUS
    with _runtime_locks():
        archive = _archive_persistent_state(core, journal, ledger)
        started_marker = {
            "status": "cutover_started",
            "version": VERSION,
            "decision_id": DECISION_ID,
            "target_epoch_id": TARGET_EPOCH_ID,
            "archive_dir": archive.get("archive_dir"),
            "started_local": _now(core),
        }
        _atomic_json(MARKER_FILE, started_marker)
        clean = build_clean_state(core, archive, journal)
        state_file = _write_clean_state_and_backups(core, clean)
        _rotate_canonical_ledger()
        _rotate_journal(clean)
        _reset_snapshot_archive(clean, state_file)

        pf = _portfolio(core)
        pf.clear()
        pf.update(clean)

        completed = dict(started_marker)
        completed.update({
            "status": "completed",
            "completed_local": _now(core),
            "starting_cash": float(STARTING_CASH),
            "validation_hold": True,
            "state_file": state_file,
        })
        _atomic_json(MARKER_FILE, completed)
        _LAST_STATUS = completed
        return completed


def _decision_evidence(core: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    try:
        import paper_journal_forensic_recovery as journal_module
        journal = journal_module.status_payload(core)
    except Exception as exc:
        journal = {"status": "error", "trusted_recovery_candidate": None, "error": f"{type(exc).__name__}: {exc}"}
    try:
        import canonical_execution_ledger as ledger_module
        ledger = ledger_module.status_payload(core)
    except Exception as exc:
        ledger = {"status": "error", "chain_valid": False, "row_count": None, "error": f"{type(exc).__name__}: {exc}"}
    return journal, ledger


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST_STATUS
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not _paper_only():
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "paper_runtime_only"}

    with _LOCK:
        pf = _portfolio(core)
        existing_epoch = _epoch(pf)
        marker = _marker()
        if existing_epoch.get("id") == TARGET_EPOCH_ID:
            status = {
                "status": "validation_hold" if bool(_d(pf.get("risk_controls")).get("clean_epoch_validation_hold", False)) else "active",
                "overall": "warn" if bool(_d(pf.get("risk_controls")).get("clean_epoch_validation_hold", False)) else "pass",
                "version": VERSION,
                "decision_id": DECISION_ID,
                "epoch_id": TARGET_EPOCH_ID,
                "starting_cash": existing_epoch.get("starting_cash"),
                "historical_recovery_decision": existing_epoch.get("historical_recovery_decision"),
                "forensic_archive_dir": existing_epoch.get("forensic_archive_dir") or marker.get("archive_dir"),
                "archive_complete": bool(existing_epoch.get("historical_evidence_archived", False)),
                "validation_hold": bool(_d(pf.get("risk_controls")).get("clean_epoch_validation_hold", False)),
                "zero_trade_baseline": bool(existing_epoch.get("zero_trade_baseline", False)),
            }
            _LAST_STATUS = status
            return status

        journal, ledger = _decision_evidence(core)
        contamination = _contamination_signature(pf)
        journal_untrusted = journal.get("trusted_recovery_candidate") is False and int(journal.get("journal_trade_rows") or 0) > 0
        ledger_ready = bool(ledger.get("chain_valid")) and int(ledger.get("row_count") or 0) == 0 and bool(ledger.get("authoritative_for_new_executions"))

        if marker.get("status") == "completed" and marker.get("target_epoch_id") == TARGET_EPOCH_ID:
            return {
                "status": "error",
                "overall": "fail",
                "version": VERSION,
                "reason": "completed_marker_present_but_active_state_epoch_missing",
                "marker": marker,
            }
        if not contamination or not journal_untrusted or not ledger_ready:
            status = {
                "status": "blocked",
                "overall": "warn",
                "version": VERSION,
                "decision_id": DECISION_ID,
                "epoch_id": TARGET_EPOCH_ID,
                "reason": "clean_epoch_preconditions_not_met",
                "preconditions": {
                    "contaminated_halted_state": contamination,
                    "historical_journal_untrusted": journal_untrusted,
                    "canonical_ledger_healthy_and_empty": ledger_ready,
                },
                "journal": {
                    "journal_trade_rows": journal.get("journal_trade_rows"),
                    "coverage_issue_count": journal.get("coverage_issue_count"),
                    "economic_issue_count": journal.get("economic_issue_count"),
                    "trusted_recovery_candidate": journal.get("trusted_recovery_candidate"),
                },
                "ledger": {
                    "chain_valid": ledger.get("chain_valid"),
                    "row_count": ledger.get("row_count"),
                    "authoritative_for_new_executions": ledger.get("authoritative_for_new_executions"),
                },
            }
            _LAST_STATUS = status
            return status

        try:
            result = _cutover(core, journal, ledger)
            return {
                "status": "validation_hold",
                "overall": "warn",
                "version": VERSION,
                "decision_id": DECISION_ID,
                "epoch_id": TARGET_EPOCH_ID,
                "starting_cash": float(STARTING_CASH),
                "historical_recovery_decision": "clean_epoch",
                "forensic_archive_dir": result.get("archive_dir"),
                "archive_complete": True,
                "validation_hold": True,
                "zero_trade_baseline": True,
            }
        except Exception as exc:
            risk = _d(_portfolio(core).setdefault("risk_controls", {}))
            risk["halted"] = True
            risk["clean_epoch_cutover_error"] = f"{type(exc).__name__}: {exc}"
            if not risk.get("halt_reason"):
                risk["halt_reason"] = "clean accounting epoch cutover failed"
            status = {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}
            _LAST_STATUS = status
            return status


def status_payload(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core) if core is not None else {}
    epoch = _epoch(pf)
    risk = _d(pf.get("risk_controls"))
    marker = _marker()
    active = epoch.get("id") == TARGET_EPOCH_ID
    return {
        "status": "validation_hold" if active and risk.get("clean_epoch_validation_hold") else "active" if active else _LAST_STATUS.get("status", "pending"),
        "overall": "warn" if active and risk.get("clean_epoch_validation_hold") else "pass" if active else _LAST_STATUS.get("overall", "warn"),
        "type": "clean_accounting_epoch_status",
        "version": VERSION,
        "decision_id": DECISION_ID,
        "epoch_id": epoch.get("id") if active else TARGET_EPOCH_ID,
        "starting_cash": epoch.get("starting_cash") if active else STARTING_CASH,
        "clean_start": bool(epoch.get("clean_start", False)),
        "zero_trade_baseline": bool(epoch.get("zero_trade_baseline", False)),
        "historical_recovery_decision": epoch.get("historical_recovery_decision"),
        "historical_evidence_archived": bool(epoch.get("historical_evidence_archived", False)),
        "forensic_archive_dir": epoch.get("forensic_archive_dir") or marker.get("archive_dir"),
        "validation_hold": bool(risk.get("clean_epoch_validation_hold", False)),
        "validation_hold_reason": risk.get("clean_epoch_validation_hold_reason"),
        "marker_status": marker.get("status"),
        "authority": {
            "one_time_paper_account_reset": True,
            "historical_recovery_decision_already_proven": True,
            "clears_validation_hold": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_limits_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        path = "/paper/clean-accounting-epoch-status"
        if path not in existing:
            flask_app.add_url_rule(path, "clean_accounting_epoch_status", lambda: jsonify(status_payload(core)))
        _REGISTERED_APP_IDS.add(app_id)
    return status_payload(core)
