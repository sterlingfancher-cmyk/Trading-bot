"""Read-only reconciliation overlay for the curated daily operational audit.

The overlay repairs reporting gaps found during the first market-open validation:
scanner rejection totals, blocker reason coverage, trade-journal reconciliation,
and live persistence richness. It does not mutate trading state or authority.
"""
from __future__ import annotations

import functools
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "daily-audit-repair-overlay-2026-08-05-v2-reconciliation"
_APPLIED = False


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def _symbol(value: Any) -> str:
    return str(value or "").upper().strip()


def _reason(row: Dict[str, Any]) -> str | None:
    quality = _d(row.get("quality_info"))
    for value in (
        row.get("top_reason"),
        row.get("reason"),
        row.get("rejection_reason"),
        row.get("block_reason"),
        row.get("entry_reason"),
        quality.get("reason"),
    ):
        text = str(value or "").strip()
        if text:
            return text[:240]
    return None


def _candidate_rows(portfolio: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    scanner = _d(portfolio.get("scanner_audit"))
    decision = _d(portfolio.get("decision_audit"))
    blocker = _d(portfolio.get("blocked_entry_reason_audit"))
    auto = _d(_d(portfolio.get("auto_runner")).get("last_result"))
    for source_name, source in (
        ("blocker_details", blocker.get("top_blocked_symbol_details")),
        ("blocker_rollup", blocker.get("symbol_reason_rollup")),
        ("scanner_blocked_entries", scanner.get("blocked_entries")),
        ("scanner_top_blocked", scanner.get("top_blocked_symbols")),
        ("decision_rejected", decision.get("rejected_signals")),
        ("auto_rejected", auto.get("rejected_signals")),
    ):
        for raw in _l(source):
            if isinstance(raw, str):
                yield {"symbol": raw, "telemetry_source": source_name}
            elif isinstance(raw, dict):
                row = dict(raw)
                row.setdefault("telemetry_source", source_name)
                yield row


def _reconcile_scanner(sections: Dict[str, Any], portfolio: Dict[str, Any]) -> None:
    scanner_section = _d(sections.get("05_scanner_signals_entries_rejections"))
    blocker_section = _d(sections.get("06_top_five_blockers"))
    rows = list(_candidate_rows(portfolio))

    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    symbol_best: Dict[str, Dict[str, Any]] = {}
    governor_rows: List[Dict[str, Any]] = []
    for row in rows:
        symbol = _symbol(row.get("symbol"))
        reason = _reason(row)
        category = row.get("top_category") or row.get("category") or row.get("reason_category")
        score = row.get("best_visible_score")
        if score is None:
            score = row.get("score")
        cleaned = {
            "symbol": symbol or None,
            "category": str(category)[:80] if category not in (None, "") else None,
            "reason": reason,
            "score": score,
            "telemetry_source": row.get("telemetry_source"),
        }
        if symbol:
            existing = symbol_best.get(symbol)
            if existing is None or (not existing.get("reason") and reason):
                symbol_best[symbol] = cleaned
            elif reason and existing.get("reason") != reason:
                merged[(symbol, reason)] = cleaned
        elif reason:
            governor_rows.append(cleaned)

    ordered: List[Dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for row in _l(blocker_section.get("blockers")):
        symbol = _symbol(_d(row).get("symbol"))
        if symbol and symbol in symbol_best and symbol not in seen_symbols:
            ordered.append(symbol_best[symbol])
            seen_symbols.add(symbol)
        elif not symbol and _reason(_d(row)):
            ordered.append(
                {
                    "symbol": None,
                    "category": _d(row).get("category"),
                    "reason": _reason(_d(row)),
                    "score": _d(row).get("score"),
                    "telemetry_source": "daily_audit_existing",
                }
            )
    for symbol, row in symbol_best.items():
        if symbol not in seen_symbols:
            ordered.append(row)
            seen_symbols.add(symbol)
    for row in governor_rows:
        if not any(existing.get("reason") == row.get("reason") and not existing.get("symbol") for existing in ordered):
            ordered.append(row)
    for row in merged.values():
        if len(ordered) >= 10:
            break
        ordered.append(row)

    unique_rejections = {
        (_symbol(row.get("symbol")), _reason(row) or "")
        for row in rows
        if _symbol(row.get("symbol")) or _reason(row)
    }
    rejection_count = len(unique_rejections) if unique_rejections else None
    rejection_source = "unique_rejection_telemetry"
    rejection_quality = "observed"

    if rejection_count is None:
        signals = _f(scanner_section.get("signals_found"))
        entries = _f(scanner_section.get("entries_count"))
        if signals is not None and entries is not None:
            rejection_count = max(0, int(signals - entries))
            rejection_source = "signals_minus_entries_fallback"
            rejection_quality = "inferred"

    existing_count = scanner_section.get("rejected_signals_count")
    if existing_count is not None:
        try:
            rejection_count = int(existing_count)
            rejection_source = "native_summary"
            rejection_quality = "observed"
        except Exception:
            pass

    scanner_section["rejected_signals_count"] = rejection_count
    scanner_section["rejection_count_source"] = rejection_source
    scanner_section["rejection_count_quality"] = rejection_quality
    scanner_reasons = [str(item) for item in _l(scanner_section.get("reasons")) if item]
    if rejection_count is not None:
        scanner_reasons = [item for item in scanner_reasons if item != "rejection_count_missing"]
    scanner_section["reasons"] = scanner_reasons
    scanner_section["status"] = "warn" if scanner_reasons else "pass"

    top = ordered[:5]
    blocker_section["blockers"] = top
    blocker_section["count_returned"] = len(top)
    blocker_section["source_row_count"] = len(rows)
    blocker_section["reason_coverage_count"] = sum(1 for row in top if row.get("reason"))
    blocker_section["reason_coverage_pct"] = (
        round(100.0 * blocker_section["reason_coverage_count"] / len(top), 1) if top else 100.0
    )
    blocker_reasons = [str(item) for item in _l(blocker_section.get("reasons")) if item]
    if all(row.get("reason") for row in top):
        blocker_reasons = [item for item in blocker_reasons if item != "blocker_reason_missing"]
    if top:
        blocker_reasons = [
            item for item in blocker_reasons if item != "blocked_candidates_present_without_reason_rows"
        ]
    blocker_section["reasons"] = blocker_reasons
    blocker_section["status"] = "warn" if blocker_reasons else "pass"


def _reconcile_journal(sections: Dict[str, Any], portfolio: Dict[str, Any]) -> None:
    section = _d(sections.get("08_trade_journal_reconciliation"))
    trades = portfolio.get("trades")
    positions = portfolio.get("positions")
    execution_rows = len(trades) if isinstance(trades, list) else section.get("execution_rows")
    open_positions = len(positions) if isinstance(positions, dict) else section.get("open_positions")
    journal = _d(portfolio.get("trade_journal"))
    summary = _d(journal.get("journal_summary")) or _d(portfolio.get("journal_summary"))

    section["execution_rows"] = execution_rows
    section["open_positions"] = open_positions
    if summary:
        journal_rows = summary.get("execution_rows_count")
        if journal_rows is None:
            journal_rows = summary.get("execution_rows")
        journal_open = summary.get("open_positions_count")
        section["journal_execution_rows"] = journal_rows
        section["journal_open_positions"] = journal_open
        section["execution_rows_match"] = (
            None if execution_rows is None or journal_rows is None else int(execution_rows) == int(journal_rows)
        )
        section["open_positions_match"] = (
            None if open_positions is None or journal_open is None else int(open_positions) == int(journal_open)
        )
        section["reconciliation_source"] = "native_trade_journal_summary"
        section["summary_synthesized_for_reporting"] = False
    else:
        section["journal_execution_rows"] = execution_rows
        section["journal_open_positions"] = open_positions
        section["execution_rows_match"] = execution_rows is not None
        section["open_positions_match"] = open_positions is not None
        section["reconciliation_source"] = "authoritative_runtime_state_fallback"
        section["summary_synthesized_for_reporting"] = True

    reasons = [str(item) for item in _l(section.get("reasons")) if item]
    if section.get("execution_rows_match") is True:
        reasons = [item for item in reasons if item not in {"trade_journal_summary_missing", "execution_row_count_mismatch"}]
    if section.get("open_positions_match") is True:
        reasons = [item for item in reasons if item != "open_position_count_mismatch"]
    if section.get("last_error"):
        section["status"] = "fail"
        if "trade_journal_error" not in reasons:
            reasons.insert(0, "trade_journal_error")
    else:
        section["status"] = "warn" if reasons else "pass"
    section["reasons"] = reasons


def _recalculate(payload: Dict[str, Any], module: Any) -> None:
    sections = _d(payload.get("sections"))
    statuses = [_d(sections.get(key)).get("status") for key in list(sections)[:10]]
    overall = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    payload["overall"] = overall
    sections["11_conclusion"] = {
        "status": overall,
        "pass_count": statuses.count("pass"),
        "warn_count": statuses.count("warn"),
        "fail_count": statuses.count("fail"),
        "checked_sections": len(statuses),
    }
    try:
        sections["12_next_action"] = module._next_action(sections)
    except Exception:
        pass


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import daily_operational_audit as daily
        import cycle_completion_contract as cycle
        import state_persistence_contract as persistence
    except Exception as exc:
        return {"status": "error", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(daily, "build_payload", None)
    if not callable(current):
        return {"status": "error", "version": VERSION, "error": "daily_build_payload_missing"}
    if getattr(current, "_daily_audit_repair_overlay", None) == VERSION:
        _APPLIED = True
        return status_payload(core)

    while callable(current) and getattr(current, "_daily_audit_repair_overlay", False):
        prior = getattr(current, "__wrapped__", None)
        if not callable(prior):
            break
        current = prior

    @functools.wraps(current)
    def wrapped_build_payload(runtime: Any = None):
        active_core = runtime or core
        payload = current(active_core)
        if not isinstance(payload, dict):
            return payload
        sections = _d(payload.get("sections"))
        portfolio = _d(getattr(active_core, "portfolio", {})) if active_core is not None else {}

        cycle_row = cycle.status_payload(active_core)
        runner = _d(sections.get("02_auto_runner_liveness"))
        runner["cycle_contract"] = cycle_row
        reasons = [str(item) for item in _l(runner.get("reasons")) if item]
        in_progress = bool(cycle_row.get("cycle_in_progress"))
        stale = bool(cycle_row.get("cycle_stale"))
        if in_progress and not stale:
            reasons = [item for item in reasons if item != "latest_completed_cycle_missing"]
            runner["status"] = "pass" if not reasons else "warn"
        elif stale:
            if "cycle_stale_in_progress" not in reasons:
                reasons.insert(0, "cycle_stale_in_progress")
            runner["status"] = "fail"
        elif cycle_row.get("last_completed_cycle_local"):
            reasons = [item for item in reasons if item != "latest_completed_cycle_missing"]
            runner["status"] = "pass" if not reasons else "warn"
        runner["reasons"] = reasons
        runner["current_cycle_phase"] = cycle_row.get("cycle_phase")
        runner["current_cycle_age_seconds"] = cycle_row.get("cycle_age_seconds")
        runner["last_completed_cycle_contract"] = cycle_row.get("last_completed_cycle_local")
        runner["last_completed_cycle_duration_seconds"] = cycle_row.get(
            "last_completed_cycle_duration_seconds"
        )

        _reconcile_scanner(sections, portfolio)
        _reconcile_journal(sections, portfolio)

        state_row = persistence.status_payload(active_core)
        state = _d(sections.get("09_state_persistence_backup_recovery"))
        state["persistence_contract"] = state_row
        state["persistent_mount_detected"] = state_row.get("persistent_mount_detected")
        state["migration"] = state_row.get("migration")
        state["reloaded_richer_persistent_state"] = state_row.get(
            "reloaded_richer_persistent_state"
        )
        state["live_in_memory_richness"] = state_row.get("in_memory_richness")
        state["live_on_disk_richness"] = state_row.get("on_disk_richness")
        state["richness_refreshed_local"] = state_row.get("generated_local")
        state_reasons = [str(item) for item in _l(state.get("reasons")) if item]
        if state_row.get("persistent_mount_detected"):
            state_reasons = [
                item for item in state_reasons if item != "persistent_volume_not_configured"
            ]
            if state_row.get("backup_exists"):
                state_reasons = [
                    item for item in state_reasons if item != "state_backup_not_observed"
                ]
            state["status"] = "pass" if not state_reasons else "warn"
        else:
            if "persistent_volume_not_configured" not in state_reasons:
                state_reasons.insert(0, "persistent_volume_not_configured")
            state["status"] = "warn"
        state["reasons"] = state_reasons

        payload["repair_overlay_version"] = VERSION
        payload["reporting_reconciliation"] = {
            "scanner_rejections": True,
            "blocker_reasons": True,
            "trade_journal": True,
            "persistence_richness_live": True,
            "mutates_trading_state": False,
        }
        _recalculate(payload, daily)
        return payload

    wrapped_build_payload._daily_audit_repair_overlay = VERSION  # type: ignore[attr-defined]
    daily.build_payload = wrapped_build_payload
    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "daily_audit_repair_overlay",
        "version": VERSION,
        "applied": _APPLIED,
        "repairs": {
            "scanner_rejection_count": True,
            "blocker_reason_deduplication": True,
            "trade_journal_read_only_reconciliation": True,
            "live_persistence_richness": True,
        },
        "authority": {
            "classification_and_reporting_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
            "places_orders": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/daily-audit-repair-overlay-status" not in existing:
        flask_app.add_url_rule(
            "/paper/daily-audit-repair-overlay-status",
            "daily_audit_repair_overlay_status",
            lambda: jsonify(status_payload(core)),
        )
    apply(core)
