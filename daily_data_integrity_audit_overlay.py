"""Read-only data-integrity finalizer for the routine daily audit.

The overlay makes provider and MAE/MFE integrity failures visible in the same
routine audit the operator already uses. It also provides a compact default
response while preserving the complete audit behind ``?full=1``.

It does not call providers, place orders, repair state, change strategy logic,
change thresholds, change sizing, or change live/ML authority.
"""
from __future__ import annotations

import functools
import sys
from typing import Any, Dict, List

VERSION = "daily-data-integrity-audit-overlay-2026-08-06-v2-compact-finalizer"
SECTION_KEY = "10b_market_data_and_path_integrity"
_APPLIED = False
_REGISTERED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _module() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "portfolio"):
            return module
    return None


def _safe_status(module_name: str, core: Any) -> Dict[str, Any]:
    try:
        module = __import__(module_name)
        fn = getattr(module, "status_payload", None)
        if callable(fn):
            try:
                value = fn(core)
            except TypeError:
                value = fn()
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def _feature_contamination(rows: Any) -> List[Dict[str, Any]]:
    contaminated: List[Dict[str, Any]] = []
    for raw in _l(rows):
        if not isinstance(raw, dict):
            continue
        feature = _d(raw.get("mae_mfe_features"))
        if not feature or feature.get("ml_feature_ready") is not True:
            continue
        valid = bool(
            feature.get("path_id")
            and feature.get("training_eligible") is True
            and feature.get("integrity_status") == "valid"
        )
        if not valid:
            contaminated.append(
                {
                    "symbol": str(raw.get("symbol") or raw.get("ticker") or "").upper() or None,
                    "path_id": feature.get("path_id"),
                    "mae_pct": feature.get("mae_pct"),
                    "mfe_pct": feature.get("mfe_pct"),
                    "reason": "ml_feature_ready_without_valid_exact_path",
                }
            )
    return contaminated


def _integrity_counts(
    path: Dict[str, Any],
    path_status: Dict[str, Any],
    integration: Dict[str, Any],
    integration_status: Dict[str, Any],
) -> Dict[str, int]:
    valid_path_rows = _int(
        _first(
            integration_status.get("valid_path_rows"),
            integration.get("valid_path_rows"),
            path_status.get("valid_path_rows"),
        )
    )
    invalid_path_rows = _int(
        _first(
            integration_status.get("invalid_or_quarantined_path_rows"),
            integration.get("invalid_or_quarantined_path_rows"),
            path_status.get("invalid_or_quarantined_rows"),
            path.get("invalid_or_quarantined_rows"),
        )
    )
    training_eligible_path_rows = _int(
        _first(
            path_status.get("training_eligible_rows"),
            path.get("training_eligible_rows"),
            valid_path_rows,
        )
    )
    ml_rows_enriched = _int(
        _first(integration_status.get("ml_rows_enriched"), integration.get("ml_rows_enriched"))
    )
    ml_rows_quarantined = _int(
        _first(integration_status.get("ml_rows_quarantined"), integration.get("ml_rows_quarantined"))
    )
    trade_rows_enriched = _int(
        _first(integration_status.get("trade_rows_enriched"), integration.get("trade_rows_enriched"))
    )
    trade_rows_quarantined = _int(
        _first(
            integration_status.get("trade_rows_quarantined"),
            integration.get("trade_rows_quarantined"),
        )
    )
    recomputed_rows = _int(
        _first(
            integration_status.get("recomputed_rows"),
            integration.get("recomputed_rows"),
            path_status.get("recomputed_rows"),
            path.get("recomputed_rows"),
            0,
        )
    )
    return {
        "valid_path_rows": valid_path_rows,
        "invalid_or_quarantined_path_rows": invalid_path_rows,
        "training_eligible_path_rows": training_eligible_path_rows,
        "training_eligible_feature_rows": valid_path_rows,
        "ml_rows_enriched": ml_rows_enriched,
        "ml_rows_quarantined": ml_rows_quarantined,
        "trade_rows_enriched": trade_rows_enriched,
        "trade_rows_quarantined": trade_rows_quarantined,
        "quarantined_feature_rows": ml_rows_quarantined + trade_rows_quarantined,
        "recomputed_rows": recomputed_rows,
    }


def build_integrity_section(core: Any = None) -> Dict[str, Any]:
    core = core or _module()
    portfolio = _d(getattr(core, "portfolio", {})) if core is not None else {}
    hygiene = _safe_status("yfinance_data_hygiene", core)
    provider = _safe_status("market_data_resilience", core)

    positions = _d(portfolio.get("positions"))
    protected = {str(symbol).upper() for symbol in _l(hygiene.get("protected_symbols")) if str(symbol).strip()}
    protected.update({"SPY", "QQQ", "IWM", "DIA"})
    protected.update(str(symbol).upper() for symbol in positions)
    active_backoffs = _d(hygiene.get("active_symbol_backoffs"))
    blocked_symbols = {str(symbol).upper() for symbol in active_backoffs}
    protected_blocked = sorted(protected & blocked_symbols)
    benchmark_blocked = sorted({"SPY", "QQQ", "IWM", "DIA"} & blocked_symbols)

    path = _d(portfolio.get("intratrade_path_capture"))
    path_status = _safe_status("intratrade_path_capture", core)
    integration = _d(portfolio.get("mae_mfe_integration"))
    integration_status = _safe_status("mae_mfe_integration", core)
    counts = _integrity_counts(path, path_status, integration, integration_status)

    ml2 = _d(portfolio.get("ml_phase2"))
    contaminated = _feature_contamination(ml2.get("dataset")) + _feature_contamination(portfolio.get("trades"))

    integration_error = (
        integration_status.get("last_error")
        or integration.get("last_error")
        or path_status.get("last_error")
        or path.get("last_error")
        or (_d(integration.get("intratrade_refresh")).get("error"))
    )
    provider_circuit_open = bool(provider.get("provider_circuit_open") or provider.get("circuit_open"))
    hygiene_installed = hygiene.get("installed") is True
    provider_installed = provider.get("installed") is True

    fail_reasons: List[str] = []
    warn_reasons: List[str] = []
    if protected_blocked:
        fail_reasons.append("protected_symbol_quarantined")
    if provider_circuit_open:
        fail_reasons.append("provider_circuit_open")
    if contaminated:
        fail_reasons.append("contaminated_mae_mfe_feature_active")
    if integration_error:
        fail_reasons.append("mae_mfe_integrity_error")
    if not hygiene_installed:
        warn_reasons.append("yfinance_hygiene_not_confirmed_installed")
    if not provider_installed:
        warn_reasons.append("provider_resilience_not_confirmed_installed")

    status = "fail" if fail_reasons else "warn" if warn_reasons else "pass"
    reasons = fail_reasons or warn_reasons
    return {
        "status": status,
        "reasons": reasons,
        "protected_symbols": sorted(protected),
        "active_symbol_backoffs": active_backoffs,
        "protected_symbols_blocked": protected_blocked,
        "benchmark_symbols_blocked": benchmark_blocked,
        "provider_circuit_open": provider_circuit_open,
        "provider_distinct_failure_symbols": provider.get("distinct_provider_failure_symbols") or [],
        "provider_totals": provider.get("totals") or {},
        "path_integrity": {
            "version": _first(path_status.get("version"), path.get("version")),
            "valid_rows": counts["valid_path_rows"],
            "invalid_or_quarantined_rows": counts["invalid_or_quarantined_path_rows"],
            "training_eligible_rows": counts["training_eligible_path_rows"],
            "recomputed_rows": counts["recomputed_rows"],
            "integrity_resets": _int(_first(path_status.get("integrity_resets"), path.get("integrity_resets"))),
            "last_error": _first(path_status.get("last_error"), path.get("last_error")),
        },
        "mae_mfe_integrity": {
            "version": _first(integration_status.get("version"), integration.get("version")),
            "valid_path_rows": counts["valid_path_rows"],
            "invalid_or_quarantined_path_rows": counts["invalid_or_quarantined_path_rows"],
            "training_eligible_feature_rows": counts["training_eligible_feature_rows"],
            "quarantined_feature_rows": counts["quarantined_feature_rows"],
            "ml_rows_enriched": counts["ml_rows_enriched"],
            "ml_rows_quarantined": counts["ml_rows_quarantined"],
            "trade_rows_enriched": counts["trade_rows_enriched"],
            "trade_rows_quarantined": counts["trade_rows_quarantined"],
            "recomputed_rows": counts["recomputed_rows"],
            "last_error": integration_error,
        },
        "active_contaminated_feature_count": len(contaminated),
        "active_contaminated_feature_examples": contaminated[:10],
        "forward_validation": {
            "valid_exact_lifecycle_rows_observed": counts["valid_path_rows"],
            "complete": counts["valid_path_rows"] > 0,
            "historical_backfill_established": counts["recomputed_rows"] > 0,
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


def _recalculate(payload: Dict[str, Any], daily: Any) -> None:
    sections = _d(payload.get("sections"))
    operational_keys = [
        key
        for key in sections
        if key not in {"11_conclusion", "12_next_action"}
    ]
    statuses = [_d(sections.get(key)).get("status") for key in operational_keys]
    overall = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    payload["overall"] = overall
    sections["11_conclusion"] = {
        "status": overall,
        "pass_count": statuses.count("pass"),
        "warn_count": statuses.count("warn"),
        "fail_count": statuses.count("fail"),
        "checked_sections": len(statuses),
    }
    integrity = _d(sections.get(SECTION_KEY))
    if integrity.get("status") in {"fail", "warn"}:
        sections["12_next_action"] = {
            "status": "required",
            "priority": "high" if integrity.get("status") == "fail" else "normal",
            "section": SECTION_KEY,
            "action": "Restore protected market data and keep invalid MAE/MFE rows quarantined before relying on the next trading cycle.",
            "reason": (_l(integrity.get("reasons")) or [None])[0],
        }
    else:
        try:
            sections["12_next_action"] = daily._next_action(sections)
        except Exception:
            pass


def _finalize_payload(payload: Dict[str, Any], daily: Any, core: Any = None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    sections = _d(payload.setdefault("sections", {}))
    sections[SECTION_KEY] = build_integrity_section(core)
    payload["data_integrity_overlay_version"] = VERSION
    _recalculate(payload, daily)

    risk = _d(sections.get("04_risk_controls_and_drawdown"))
    if "realized_loss_pct" in risk:
        risk["net_daily_loss_pct"] = risk.get("realized_loss_pct")
        risk["realized_loss_pct_source_key"] = "risk_controls.daily_loss_pct"
        risk["metric_label_note"] = (
            "realized_loss_pct is retained for compatibility; net_daily_loss_pct "
            "is the canonical operator label for this runtime daily-loss metric."
        )

    links = _d(payload.get("links"))
    routine = links.get("routine_daily_audit")
    if routine:
        links["full_daily_audit"] = f"{str(routine).split('?')[0]}?full=1"
    return payload


def _compact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sections = _d(payload.get("sections"))
    account = _d(sections.get("01_account_and_open_position_performance"))
    runner = _d(sections.get("02_auto_runner_liveness"))
    errors = _d(sections.get("03_active_errors_and_recursion"))
    risk = _d(sections.get("04_risk_controls_and_drawdown"))
    scanner = _d(sections.get("05_scanner_signals_entries_rejections"))
    blockers = _d(sections.get("06_top_five_blockers"))
    journal = _d(sections.get("08_trade_journal_reconciliation"))
    persistence = _d(sections.get("09_state_persistence_backup_recovery"))
    integrity = _d(sections.get(SECTION_KEY))
    conclusion = _d(sections.get("11_conclusion"))
    next_action = _d(sections.get("12_next_action"))

    return {
        "status": payload.get("status"),
        "overall": payload.get("overall"),
        "type": "daily_operational_audit_compact",
        "version": payload.get("version"),
        "data_integrity_overlay_version": VERSION,
        "generated_local": payload.get("generated_local"),
        "duration_seconds": payload.get("duration_seconds"),
        "section_summary": {
            "checked": conclusion.get("checked_sections"),
            "pass": conclusion.get("pass_count"),
            "warn": conclusion.get("warn_count"),
            "fail": conclusion.get("fail_count"),
        },
        "account": {
            "cash": account.get("cash"),
            "equity": account.get("equity"),
            "open_positions_count": account.get("open_positions_count"),
            "positions": account.get("positions") or [],
            "realized_today": account.get("realized_today"),
            "realized_total": account.get("realized_total"),
            "unrealized_pnl": account.get("unrealized_pnl"),
            "wins_total": account.get("wins_total"),
            "losses_total": account.get("losses_total"),
        },
        "runner": {
            "status": runner.get("status"),
            "enabled": runner.get("enabled"),
            "liveness_state": runner.get("liveness_state"),
            "last_completed_cycle": runner.get("last_completed_cycle"),
            "last_completed_cycle_duration_seconds": runner.get("last_completed_cycle_duration_seconds"),
            "last_skip_reason": runner.get("last_skip_reason"),
        },
        "errors": {
            "status": errors.get("status"),
            "active_error": errors.get("active_error"),
            "last_error": errors.get("last_error"),
            "recursion_error_active": errors.get("recursion_error_active"),
        },
        "risk": {
            "status": risk.get("status"),
            "halted": risk.get("halted"),
            "halt_reason": risk.get("halt_reason"),
            "self_defense_active": risk.get("self_defense_active"),
            "net_daily_loss_pct": _first(risk.get("net_daily_loss_pct"), risk.get("realized_loss_pct")),
            "intraday_drawdown_pct": risk.get("intraday_drawdown_pct"),
            "absolute_daily_loss_ceiling_pct": risk.get("absolute_daily_loss_ceiling_pct"),
            "hard_intraday_drawdown_halt_pct": risk.get("hard_intraday_drawdown_halt_pct"),
        },
        "scanner": {
            "status": scanner.get("status"),
            "signals_found": scanner.get("signals_found"),
            "entries_count": scanner.get("entries_count"),
            "rejected_signals_count": scanner.get("rejected_signals_count"),
            "top_blockers": _l(blockers.get("blockers"))[:5],
        },
        "reconciliation": {
            "journal_status": journal.get("status"),
            "execution_rows_match": journal.get("execution_rows_match"),
            "open_positions_match": journal.get("open_positions_match"),
            "persistence_status": persistence.get("status"),
            "state_file_exists": persistence.get("state_file_exists"),
            "backup_count": persistence.get("backup_count"),
        },
        "data_integrity": {
            "status": integrity.get("status"),
            "reasons": integrity.get("reasons") or [],
            "provider_circuit_open": integrity.get("provider_circuit_open"),
            "protected_symbols_blocked": integrity.get("protected_symbols_blocked") or [],
            "active_contaminated_feature_count": integrity.get("active_contaminated_feature_count"),
            "path_integrity": integrity.get("path_integrity") or {},
            "mae_mfe_integrity": integrity.get("mae_mfe_integrity") or {},
            "forward_validation": integrity.get("forward_validation") or {},
        },
        "next_action": next_action,
        "links": payload.get("links") or {},
        "authority": payload.get("authority") or {},
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import daily_operational_audit as daily
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(daily, "build_payload", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "daily_build_payload_missing"}
    if getattr(current, "_daily_data_integrity_overlay", None) == VERSION:
        _APPLIED = True
        return status_payload(core)

    while callable(current) and getattr(current, "_daily_data_integrity_overlay", False):
        prior = getattr(current, "__wrapped__", None)
        if not callable(prior):
            break
        current = prior

    @functools.wraps(current)
    def wrapped_build_payload(runtime: Any = None):
        active_core = runtime or core or _module()
        payload = current(active_core)
        return _finalize_payload(payload, daily, active_core)

    wrapped_build_payload._daily_data_integrity_overlay = VERSION  # type: ignore[attr-defined]
    daily.build_payload = wrapped_build_payload
    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "type": "daily_data_integrity_audit_overlay_status",
        "version": VERSION,
        "applied": _APPLIED,
        "section_key": SECTION_KEY,
        "daily_audit_default_mode": "compact",
        "daily_audit_full_query": "?full=1",
        "integrity": build_integrity_section(core),
        "authority": {
            "reporting_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "places_orders": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}

    from flask import jsonify, request
    import daily_operational_audit as daily

    apply(core)
    active_core = core or _module()

    def daily_audit_view():
        payload = daily.build_payload(active_core or _module())
        payload = _finalize_payload(payload, daily, active_core or _module())
        full = str(request.args.get("full", "")).strip().lower() in {"1", "true", "yes", "on"}
        return jsonify(payload if full else _compact_payload(payload))

    daily_audit_view._daily_operational_audit_version = VERSION  # type: ignore[attr-defined]
    try:
        rules = list(flask_app.url_map.iter_rules())
        existing = {getattr(rule, "rule", "") for rule in rules}
    except Exception:
        rules = []
        existing = set()

    daily_path = getattr(daily, "ROUTE", "/paper/daily-audit")
    if daily_path not in existing:
        flask_app.add_url_rule(daily_path, "paper_daily_audit", daily_audit_view)
    else:
        endpoint = next(
            (getattr(rule, "endpoint", None) for rule in rules if getattr(rule, "rule", "") == daily_path),
            None,
        )
        if endpoint:
            flask_app.view_functions[endpoint] = daily_audit_view

    status_path = "/paper/data-integrity-audit-status"
    if status_path not in existing:
        flask_app.add_url_rule(
            status_path,
            "paper_data_integrity_audit_status",
            lambda: jsonify(status_payload(active_core or _module())),
        )

    _REGISTERED_APP_IDS.add(id(flask_app))
    return {
        "status": "ok",
        "version": VERSION,
        "daily_route_finalizer_installed": True,
        "daily_audit_default_mode": "compact",
        "daily_audit_full_query": "?full=1",
    }


try:
    apply(None)
except Exception:
    pass
