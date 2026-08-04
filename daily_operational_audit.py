"""Curated, read-only operational audit for routine paper-trading checks.

The route intentionally avoids endpoint fan-out, provider calls, trading actions,
repair actions, backtests, and report generation. It reads the in-process state
and a small allowlist of local status producers, then returns twelve bounded,
mobile-readable sections.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "daily-operational-audit-2026-08-04-v1"
ROUTE = "/paper/daily-audit"
CANONICAL_BASE_URL = "https://web-production-e1796.up.railway.app"
_PATCHED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any, limit: int = 500) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "portfolio"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _base_url() -> str:
    base = str(
        os.environ.get("PUBLIC_BASE_URL")
        or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or os.environ.get("BASE_URL")
        or CANONICAL_BASE_URL
    ).strip()
    if base and not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")


def _time_key(value: Any) -> float:
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return 0.0
    text = str(value or "").strip()
    if not text:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(text[:19], fmt).timestamp()
        except Exception:
            continue
    try:
        return float(text)
    except Exception:
        return 0.0


def _error_freshness(last_error: Any, last_attempt: Any, last_run: Any, last_success: Any) -> Dict[str, Any]:
    error_present = bool(last_error)
    attempt_key = _time_key(last_attempt)
    recovery_key = max(_time_key(last_run), _time_key(last_success))
    superseded = bool(error_present and attempt_key > 0.0 and recovery_key >= attempt_key)
    active = bool(error_present and not superseded)
    return {
        "present": error_present,
        "active": active,
        "historical": superseded,
        "state": "active" if active else "historical_superseded" if superseded else "none",
    }


def _runner_liveness(auto: Dict[str, Any], now_epoch: float | None = None) -> Dict[str, Any]:
    now_epoch = float(now_epoch if now_epoch is not None else time.time())
    try:
        interval = max(30.0, float(auto.get("interval_seconds") or 300.0))
    except Exception:
        interval = 300.0
    freshness_window = max(180.0, interval * 2.5)
    attempt_epoch = _time_key(auto.get("last_attempt_ts") or auto.get("last_attempt_local"))
    age = now_epoch - attempt_epoch if attempt_epoch > 0.0 else None
    source = str(auto.get("last_attempt_source") or "").strip().lower()
    recent_auto_attempt = bool(
        source == "auto"
        and age is not None
        and age >= -5.0
        and age <= freshness_window
    )
    reported_started = auto.get("thread_started") is True
    active = bool(reported_started or recent_auto_attempt)
    return {
        "active": active,
        "state": (
            "reported_started"
            if reported_started
            else "inferred_from_recent_auto_attempt"
            if recent_auto_attempt
            else "not_observed"
        ),
        "reported_started": reported_started,
        "recent_auto_attempt": recent_auto_attempt,
        "last_attempt_age_seconds": round(age, 1) if age is not None else None,
        "freshness_window_seconds": round(freshness_window, 1),
    }


def _positions(portfolio: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    value = portfolio.get("positions")
    if isinstance(value, dict):
        return [str(symbol) for symbol in value.keys()][:20], value
    if isinstance(value, list):
        symbols = [str(item.get("symbol") if isinstance(item, dict) else item) for item in value]
        return symbols[:20], {symbol: {} for symbol in symbols}
    nested = _d(portfolio.get("portfolio"))
    value = nested.get("positions")
    if isinstance(value, dict):
        return [str(symbol) for symbol in value.keys()][:20], value
    return [], {}


def _position_unrealized(positions: Dict[str, Any]) -> float | None:
    total = 0.0
    found = False
    for row in positions.values():
        if not isinstance(row, dict):
            continue
        value = _first(row.get("unrealized_pnl"), row.get("unrealized_pl"), row.get("pnl"))
        number = _number(value)
        if number is not None:
            total += number
            found = True
    return round(total, 4) if found else None


def _status_payload(module_name: str, core: Any, argument: Any = None) -> Dict[str, Any]:
    """Call only a local status producer; never call apply/install/repair functions."""
    try:
        module = __import__(module_name)
    except Exception:
        return {}
    fn = getattr(module, "status_payload", None)
    if not callable(fn):
        return {}
    attempts: Iterable[Tuple[Any, ...]] = (
        (argument,) if argument is not None else (),
        (core,) if core is not None else (),
        (),
    )
    seen: set[Tuple[int, ...]] = set()
    for args in attempts:
        key = tuple(id(item) for item in args)
        if key in seen:
            continue
        seen.add(key)
        try:
            value = fn(*args)
            return value if isinstance(value, dict) else {}
        except TypeError:
            continue
        except Exception:
            return {}
    return {}


def _blocker_rows(portfolio: Dict[str, Any], scanner: Dict[str, Any], decision: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int | None]:
    audit = _d(portfolio.get("blocked_entry_reason_audit"))
    candidate_lists = [
        audit.get("top_blocked_symbol_details"),
        audit.get("symbol_reason_rollup"),
        scanner.get("blocked_entries"),
        scanner.get("top_blocked_symbols"),
        decision.get("rejected_signals"),
    ]
    out: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    total_source_rows: int | None = None
    for source in candidate_lists:
        rows = source if isinstance(source, list) else []
        if rows and total_source_rows is None:
            total_source_rows = len(rows)
        for raw in rows:
            if isinstance(raw, str):
                row = {"symbol": raw}
            elif isinstance(raw, dict):
                row = raw
            else:
                continue
            quality = _d(row.get("quality_info"))
            reason = _first(
                row.get("top_reason"),
                row.get("reason"),
                row.get("rejection_reason"),
                quality.get("reason"),
            )
            category = _first(row.get("top_category"), row.get("category"), row.get("reason_category"))
            symbol = _text(row.get("symbol"), 40)
            reason_text = _text(reason, 240)
            key = (symbol or "", reason_text or "")
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "symbol": symbol,
                    "category": _text(category, 80),
                    "reason": reason_text,
                    "score": _first(row.get("best_visible_score"), row.get("score")),
                }
            )
            if len(out) >= 5:
                return out, total_source_rows
    return out, total_source_rows


def _state_path(core: Any) -> str | None:
    for attr in ("STATE_PATH", "STATE_FILE", "STATE_FILENAME"):
        value = getattr(core, attr, None) if core is not None else None
        if isinstance(value, str) and value.strip():
            path = value.strip()
            state_dir = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
            if state_dir and not os.path.isabs(path):
                path = os.path.join(state_dir, os.path.basename(path))
            return os.path.abspath(path)
    state_dir = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    filename = os.environ.get("STATE_FILENAME") or os.environ.get("STATE_FILE") or "state.json"
    if state_dir:
        return os.path.abspath(os.path.join(state_dir, os.path.basename(filename)))
    return os.path.abspath(filename)


def _state_persistence(portfolio: Dict[str, Any], core: Any) -> Dict[str, Any]:
    path = _state_path(core)
    exists = bool(path and os.path.exists(path))
    size = os.path.getsize(path) if exists and path else None
    modified_age = round(time.time() - os.path.getmtime(path), 1) if exists and path else None
    backup_paths: List[str] = []
    if path:
        patterns = (f"{path}.bak*", f"{path}.backup*", f"{path}.prev*", f"{path}.recovery*")
        for pattern in patterns:
            for candidate in glob.glob(pattern):
                if os.path.isfile(candidate) and candidate not in backup_paths:
                    backup_paths.append(candidate)
    backup_paths.sort(key=lambda item: os.path.getmtime(item), reverse=True)

    tx = _d(portfolio.get("state_transaction")) or _d(portfolio.get("state_transaction_manager"))
    recovery = _d(portfolio.get("state_recovery")) or _d(portfolio.get("state_recovery_status"))
    archive = _d(portfolio.get("state_snapshot_archive"))
    provenance = _d(portfolio.get("state_provenance")) or _d(portfolio.get("state_provenance_monitor"))
    error = _first(
        tx.get("last_error"),
        recovery.get("last_error"),
        archive.get("last_error"),
        provenance.get("last_error"),
    )
    recovery_state = str(_first(recovery.get("status"), recovery.get("overall"), "unknown")).lower()
    corrupt = bool(
        recovery.get("corrupt")
        or recovery.get("corruption_detected")
        or tx.get("corrupt")
        or "corrupt" in str(error or "").lower()
    )
    return {
        "state_file": path,
        "state_file_exists": exists,
        "state_file_size_bytes": size,
        "state_file_modified_age_seconds": modified_age,
        "persistent_volume_configured": bool(
            os.environ.get("STATE_DIR")
            or os.environ.get("PERSISTENT_STATE_DIR")
            or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
        ),
        "backup_count": len(backup_paths),
        "latest_backup": backup_paths[0] if backup_paths else None,
        "transaction_status": _first(tx.get("status"), tx.get("overall")),
        "recovery_status": _first(recovery.get("status"), recovery.get("overall")),
        "archive_status": _first(archive.get("status"), archive.get("overall")),
        "provenance_status": _first(provenance.get("status"), provenance.get("overall")),
        "corruption_detected": corrupt,
        "last_error": _text(error),
        "recovery_failed": recovery_state in {"fail", "failed", "error"},
    }


def _section(status: str, data: Dict[str, Any], reasons: List[str] | None = None) -> Dict[str, Any]:
    return {
        "status": status,
        "reasons": reasons or [],
        **data,
    }


def _status_from_flags(*, fail: List[str] | None = None, warn: List[str] | None = None) -> Tuple[str, List[str]]:
    fail = [item for item in (fail or []) if item]
    warn = [item for item in (warn or []) if item]
    if fail:
        return "fail", fail
    if warn:
        return "warn", warn
    return "pass", []


def _next_action(sections: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    priorities = [
        ("03_active_errors_and_recursion", "Stop routine operation and inspect the active runtime error before another automatic cycle."),
        ("04_risk_controls_and_drawdown", "Review the active risk halt or self-defense reason before allowing new entries."),
        ("02_auto_runner_liveness", "Inspect runtime-worker registration and Railway logs because auto-runner liveness is not current."),
        ("07_entry_pipeline_ownership_and_stability", "Run /paper/full-self-check and inspect only entry-pipeline ownership/composition."),
        ("09_state_persistence_backup_recovery", "Inspect the persistent state path and restore backup/recovery health before relying on the next cycle."),
        ("08_trade_journal_reconciliation", "Reconcile the trade journal against execution rows and open positions."),
        ("10_runtime_shadow_cycles_and_parity", "Inspect the latest runtime-shadow divergence before collecting more promotion evidence."),
        ("05_scanner_signals_entries_rejections", "Compare scanner and decision-audit counts for the latest completed cycle."),
        ("06_top_five_blockers", "Inspect blocker reason coverage so rejected candidates retain actionable reasons."),
        ("01_account_and_open_position_performance", "Inspect missing account or open-position performance fields in the persisted state."),
    ]
    for key, action in priorities:
        row = _d(sections.get(key))
        if row.get("status") == "fail":
            return {"status": "required", "priority": "high", "section": key, "action": action, "reason": _first(*_l(row.get("reasons")))}
    for key, action in priorities:
        row = _d(sections.get(key))
        if row.get("status") == "warn":
            return {"status": "required", "priority": "normal", "section": key, "action": action, "reason": _first(*_l(row.get("reasons")))}
    return {"status": "none", "priority": None, "section": None, "action": "none", "reason": None}


def build_payload(core: Any = None) -> Dict[str, Any]:
    started = time.perf_counter()
    core = core or _mod()
    portfolio = _d(getattr(core, "portfolio", {})) if core is not None else {}
    perf = _d(portfolio.get("performance"))
    auto = _d(portfolio.get("auto_runner"))
    risk = _d(portfolio.get("risk_controls"))
    scanner = _d(portfolio.get("scanner_audit"))
    decision = _d(portfolio.get("decision_audit"))
    positions, position_rows = _positions(portfolio)
    trades = portfolio.get("trades")

    cash = _first(portfolio.get("cash"), _d(portfolio.get("portfolio")).get("cash"))
    equity = _first(portfolio.get("equity"), _d(portfolio.get("portfolio")).get("equity"))
    realized_today = _first(perf.get("realized_pnl_today"), portfolio.get("realized_pnl_today"))
    realized_total = _first(perf.get("realized_pnl_total"), portfolio.get("realized_pnl_total"))
    unrealized = _first(perf.get("unrealized_pnl"), portfolio.get("unrealized_pnl"), _position_unrealized(position_rows))
    account_status, account_reasons = _status_from_flags(
        fail=["core_runtime_missing" if core is None else ""],
        warn=[
            "cash_missing" if cash is None else "",
            "equity_missing" if equity is None else "",
            "unrealized_pnl_missing" if unrealized is None and positions else "",
        ],
    )

    last_attempt = auto.get("last_attempt_local") or auto.get("last_attempt_ts")
    last_run = auto.get("last_run_local") or auto.get("last_run_ts")
    last_success = auto.get("last_successful_run_local") or auto.get("last_successful_run_ts")
    error_freshness = _error_freshness(auto.get("last_error"), last_attempt, last_run, last_success)
    liveness = _runner_liveness(auto)
    runner_status, runner_reasons = _status_from_flags(
        fail=["auto_runner_disabled" if auto.get("enabled") is False else ""],
        warn=[
            "auto_runner_liveness_not_observed" if auto.get("enabled") is not False and not liveness["active"] else "",
            "latest_completed_cycle_missing" if not last_success and not last_run else "",
        ],
    )

    recursion_text = "recursion" in str(auto.get("last_error") or "").lower()
    error_status, error_reasons = _status_from_flags(
        fail=[
            "active_recursion_error" if recursion_text and error_freshness["active"] else "",
            "active_auto_runner_error" if error_freshness["active"] and not recursion_text else "",
        ]
    )

    daily_loss = _number(_first(risk.get("daily_loss_pct"), risk.get("realized_loss_pct")))
    intraday_dd = _number(risk.get("intraday_drawdown_pct"))
    risk_status, risk_reasons = _status_from_flags(
        fail=[
            "risk_halted" if risk.get("halted") else "",
            "self_defense_active" if risk.get("self_defense_active") else "",
            "intraday_drawdown_at_or_above_hard_limit" if intraday_dd is not None and intraday_dd >= 2.5 else "",
            "realized_loss_at_or_above_hard_limit" if daily_loss is not None and daily_loss >= 2.5 else "",
        ],
        warn=[
            "soft_realized_loss_pause_threshold_reached" if daily_loss is not None and 1.0 <= daily_loss < 2.5 else "",
            "drawdown_elevated" if intraday_dd is not None and 1.0 <= intraday_dd < 2.5 else "",
        ],
    )

    signals = _first(scanner.get("signals_found"), decision.get("signals_found"), _d(auto.get("last_result")).get("signals_found"))
    entries = _first(decision.get("entries_count"), scanner.get("entries_count"), _d(auto.get("last_result")).get("entries_count"))
    rejected = _first(
        decision.get("rejected_signals_count"),
        scanner.get("rejected_signals_count"),
        len(_l(decision.get("rejected_signals"))) if isinstance(decision.get("rejected_signals"), list) else None,
    )
    blocker_rows, blocker_source_count = _blocker_rows(portfolio, scanner, decision)
    blocker_audit = _d(portfolio.get("blocked_entry_reason_audit"))
    blocker_signals = blocker_audit.get("signals_found")
    source_mismatch = bool(signals is not None and blocker_signals is not None and signals != blocker_signals)
    scanner_status, scanner_reasons = _status_from_flags(
        warn=[
            "scanner_signal_count_missing" if signals is None else "",
            "entry_count_missing" if entries is None else "",
            "rejection_count_missing" if rejected is None else "",
            "scanner_source_snapshot_mismatch" if source_mismatch else "",
        ]
    )
    blocker_status, blocker_reasons = _status_from_flags(
        warn=[
            "blocked_candidates_present_without_reason_rows" if (rejected or blocker_source_count or 0) > 0 and not blocker_rows else "",
            "blocker_reason_missing" if any(not row.get("reason") for row in blocker_rows) else "",
        ]
    )

    composition = _status_payload("entry_pipeline_composition_guard", core)
    bear = _status_payload("bear_recovery_stack_contract", core)
    wrapper_counts = _d(bear.get("wrapper_counts"))
    stack_stable = _first(composition.get("stack_stable"), composition.get("stable"))
    recursion_safe = _first(composition.get("recursion_safe"), not recursion_text if core is not None else None)
    chain_free = composition.get("participation_valve_chain_cycle_free")
    direct_core = composition.get("direct_core_base")
    owned = bear.get("owned")
    bear_count = wrapper_counts.get("bear_wrapper_count")
    xray_count = wrapper_counts.get("xray_wrapper_count")
    entry_status, entry_reasons = _status_from_flags(
        fail=[
            "entry_pipeline_recursion_unsafe" if recursion_safe is False else "",
            "entry_pipeline_chain_cycle_detected" if chain_free is False else "",
            "entry_pipeline_not_owned" if owned is False else "",
            "bear_wrapper_count_not_one" if bear_count is not None and int(bear_count) != 1 else "",
            "xray_wrapper_count_not_one" if xray_count is not None and int(xray_count) != 1 else "",
        ],
        warn=[
            "entry_pipeline_stability_missing" if stack_stable is None else "",
            "entry_pipeline_not_stable" if stack_stable is False else "",
            "direct_core_base_missing" if direct_core is None else "",
        ],
    )

    journal = _d(portfolio.get("trade_journal"))
    journal_summary = _d(journal.get("journal_summary")) or _d(portfolio.get("journal_summary"))
    execution_rows = len(trades) if isinstance(trades, list) else None
    journal_rows = _first(
        journal_summary.get("execution_rows_count"),
        journal_summary.get("execution_rows"),
        len(_l(journal.get("rows"))) if isinstance(journal.get("rows"), list) else None,
    )
    journal_open = journal_summary.get("open_positions_count")
    execution_mismatch = bool(execution_rows is not None and journal_rows is not None and execution_rows != journal_rows)
    position_mismatch = bool(journal_open is not None and int(journal_open) != len(positions))
    journal_error = _first(journal.get("last_error"), journal_summary.get("last_error"))
    journal_status, journal_reasons = _status_from_flags(
        fail=["trade_journal_error" if journal_error else ""],
        warn=[
            "trade_journal_summary_missing" if not journal_summary else "",
            "execution_row_count_mismatch" if execution_mismatch else "",
            "open_position_count_mismatch" if position_mismatch else "",
        ],
    )

    persistence = _state_persistence(portfolio, core)
    persistence_status, persistence_reasons = _status_from_flags(
        fail=[
            "state_corruption_detected" if persistence["corruption_detected"] else "",
            "state_recovery_failed" if persistence["recovery_failed"] else "",
            "state_persistence_error" if persistence["last_error"] else "",
        ],
        warn=[
            "state_file_missing" if not persistence["state_file_exists"] else "",
            "persistent_volume_not_configured" if not persistence["persistent_volume_configured"] else "",
            "state_backup_not_observed" if persistence["backup_count"] == 0 else "",
        ],
    )

    shadow = _status_payload("runtime_shadow_capture", core, portfolio)
    shadow_state = _first(shadow.get("capture_state"), _d(portfolio.get("runtime_shadow_capture")).get("capture_state"))
    parity = _first(shadow.get("latest_parity"), _d(portfolio.get("runtime_shadow_capture")).get("latest_parity"))
    shadow_status, shadow_reasons = _status_from_flags(
        warn=[
            "runtime_shadow_capture_missing" if not shadow and not _d(portfolio.get("runtime_shadow_capture")) else "",
            "runtime_shadow_parity_false" if parity is False else "",
            "runtime_shadow_not_captured" if shadow_state not in (None, "captured") else "",
        ]
    )

    sections: Dict[str, Dict[str, Any]] = {
        "01_account_and_open_position_performance": _section(account_status, {
            "cash": cash,
            "equity": equity,
            "positions": positions,
            "open_positions_count": len(positions),
            "realized_today": realized_today,
            "realized_total": realized_total,
            "unrealized_pnl": unrealized,
            "wins_total": perf.get("wins_total"),
            "losses_total": perf.get("losses_total"),
        }, account_reasons),
        "02_auto_runner_liveness": _section(runner_status, {
            "enabled": auto.get("enabled"),
            "thread_started_reported": liveness["reported_started"],
            "thread_active_observed": liveness["active"],
            "liveness_state": liveness["state"],
            "interval_seconds": auto.get("interval_seconds"),
            "last_attempt": last_attempt,
            "last_attempt_source": auto.get("last_attempt_source"),
            "last_completed_cycle": last_success or last_run,
            "last_completed_cycle_source": auto.get("last_successful_run_source") or auto.get("last_run_source"),
            "last_skip": auto.get("last_skip_local") or auto.get("last_skip_ts"),
            "last_skip_reason": auto.get("last_skip_reason"),
        }, runner_reasons),
        "03_active_errors_and_recursion": _section(error_status, {
            "last_error": _text(auto.get("last_error")),
            "last_error_state": error_freshness["state"],
            "active_error": error_freshness["active"],
            "recursion_error_active": bool(recursion_text and error_freshness["active"]),
            "recursion_error_historical": bool(recursion_text and error_freshness["historical"]),
            "last_recovered_error": _text(auto.get("last_recovered_error")),
            "last_recovered_error_local": auto.get("last_recovered_error_local"),
        }, error_reasons),
        "04_risk_controls_and_drawdown": _section(risk_status, {
            "halted": risk.get("halted"),
            "halt_reason": _text(risk.get("halt_reason")),
            "self_defense_active": risk.get("self_defense_active"),
            "self_defense_reason": _text(risk.get("self_defense_reason")),
            "realized_loss_pct": daily_loss,
            "intraday_drawdown_pct": intraday_dd,
            "soft_realized_loss_pause_pct": 1.0,
            "hard_realized_loss_halt_pct": 2.5,
            "hard_intraday_drawdown_halt_pct": 2.5,
            "absolute_daily_loss_ceiling_pct": 3.0,
        }, risk_reasons),
        "05_scanner_signals_entries_rejections": _section(scanner_status, {
            "signals_found": signals,
            "entries_count": entries,
            "rejected_signals_count": rejected,
            "last_updated_local": scanner.get("last_updated_local"),
            "last_cycle_source": scanner.get("last_cycle_source"),
            "blocker_audit_signals_found": blocker_signals,
            "source_mismatch": source_mismatch,
        }, scanner_reasons),
        "06_top_five_blockers": _section(blocker_status, {
            "count_returned": len(blocker_rows),
            "source_row_count": blocker_source_count,
            "blockers": blocker_rows,
        }, blocker_reasons),
        "07_entry_pipeline_ownership_and_stability": _section(entry_status, {
            "stack_stable": stack_stable,
            "recursion_safe": recursion_safe,
            "participation_valve_chain_cycle_free": chain_free,
            "direct_core_base": direct_core,
            "owned": owned,
            "bear_wrapper_count": bear_count,
            "xray_wrapper_count": xray_count,
            "scanner_callable": getattr(getattr(core, "scan_signals", None), "__qualname__", None) if core is not None else None,
            "entry_callable": getattr(getattr(core, "try_entries_and_rotations", None), "__qualname__", None) if core is not None else None,
        }, entry_reasons),
        "08_trade_journal_reconciliation": _section(journal_status, {
            "execution_rows": execution_rows,
            "journal_execution_rows": journal_rows,
            "execution_rows_match": None if execution_rows is None or journal_rows is None else not execution_mismatch,
            "open_positions": len(positions),
            "journal_open_positions": journal_open,
            "open_positions_match": None if journal_open is None else not position_mismatch,
            "realized_total": _first(journal_summary.get("realized_total"), realized_total),
            "unrealized_pnl": _first(journal_summary.get("unrealized_pnl"), unrealized),
            "last_error": _text(journal_error),
        }, journal_reasons),
        "09_state_persistence_backup_recovery": _section(persistence_status, persistence, persistence_reasons),
        "10_runtime_shadow_cycles_and_parity": _section(shadow_status, {
            "capture_state": shadow_state,
            "mode": shadow.get("mode"),
            "latest_cycle_id": shadow.get("latest_cycle_id"),
            "latest_parity": parity,
            "latest_candidate_count": shadow.get("latest_candidate_count"),
            "latest_selected_symbols": shadow.get("latest_selected_symbols"),
            "total_cycles": shadow.get("total_cycles"),
            "total_candidates": shadow.get("total_candidates"),
            "independent_policy_active": shadow.get("independent_policy_active"),
            "forward_evidence_eligible": _first(_d(shadow.get("forward_evidence")).get("eligible"), shadow.get("forward_evidence_eligible")),
        }, shadow_reasons),
    }

    operational_statuses = [row.get("status") for row in sections.values()]
    overall = "fail" if "fail" in operational_statuses else "warn" if "warn" in operational_statuses else "pass"
    sections["11_conclusion"] = {
        "status": overall,
        "pass_count": operational_statuses.count("pass"),
        "warn_count": operational_statuses.count("warn"),
        "fail_count": operational_statuses.count("fail"),
        "checked_sections": len(operational_statuses),
    }
    sections["12_next_action"] = _next_action(sections)

    duration = time.perf_counter() - started
    base = _base_url()
    return {
        "status": "ok" if core is not None else "pending",
        "overall": overall,
        "type": "daily_operational_audit",
        "version": VERSION,
        "generated_local": _now(core),
        "duration_seconds": round(duration, 4),
        "performance_contract": {
            "target_seconds": "2-5",
            "route_fanout_count": 0,
            "external_provider_calls": 0,
            "trading_actions": 0,
            "repair_actions": 0,
            "heavy_research": 0,
            "bounded_output": True,
        },
        "sections": sections,
        "links": {
            "routine_daily_audit": f"{base}{ROUTE}",
            "tiny_self_check": f"{base}/paper/self-check",
            "targeted_full_diagnostics": f"{base}/paper/full-self-check",
            "bootstrap_status": f"{base}/bootstrap-status",
        },
        "authority": {
            "reporting_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    flask_app = getattr(core, "app", None) if core is not None else None
    route_present = False
    if flask_app is not None:
        try:
            route_present = any(getattr(rule, "rule", "") == ROUTE for rule in flask_app.url_map.iter_rules())
        except Exception:
            route_present = False
    return {
        "status": "ok" if route_present else "pending",
        "version": VERSION,
        "route": ROUTE,
        "route_present": route_present,
        "reporting_only": True,
        "route_fanout_count": 0,
        "bounded_sections": 12,
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify

    def daily_audit_view():
        return jsonify(build_payload(core or _mod()))

    daily_audit_view._daily_operational_audit_version = VERSION  # type: ignore[attr-defined]
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if ROUTE not in existing:
        flask_app.add_url_rule(ROUTE, "paper_daily_audit", daily_audit_view)
    else:
        endpoint = next(
            (getattr(rule, "endpoint", None) for rule in flask_app.url_map.iter_rules() if getattr(rule, "rule", "") == ROUTE),
            None,
        )
        if endpoint:
            flask_app.view_functions[endpoint] = daily_audit_view
    _PATCHED_APP_IDS.add(id(flask_app))


try:
    runtime = _mod()
    if runtime is not None:
        register_routes(getattr(runtime, "app", None), runtime)
except Exception:
    pass
