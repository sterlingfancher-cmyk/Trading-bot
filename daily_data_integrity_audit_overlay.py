"""Read-only data-integrity extension for the routine daily audit.

The overlay makes provider and MAE/MFE integrity failures visible in the same
routine audit the operator already uses. It does not call providers, place
orders, repair state, change strategy logic, change thresholds, change sizing,
or change live/ML authority.
"""
from __future__ import annotations

import functools
import sys
from typing import Any, Dict, List

VERSION = "daily-data-integrity-audit-overlay-2026-08-06-v1"
SECTION_KEY = "10b_market_data_and_path_integrity"
_APPLIED = False
_REGISTERED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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
    integration = _d(portfolio.get("mae_mfe_integration"))
    ml2 = _d(portfolio.get("ml_phase2"))
    contaminated = _feature_contamination(ml2.get("dataset")) + _feature_contamination(portfolio.get("trades"))

    integration_error = (
        integration.get("last_error")
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
            "version": path.get("version"),
            "invalid_or_quarantined_rows": path.get("invalid_or_quarantined_rows"),
            "training_eligible_rows": path.get("training_eligible_rows"),
            "integrity_resets": path.get("integrity_resets"),
            "last_error": path.get("last_error"),
        },
        "mae_mfe_integrity": {
            "version": integration.get("version"),
            "quarantined_feature_rows": integration.get("quarantined_feature_rows"),
            "training_eligible_feature_rows": integration.get("training_eligible_feature_rows"),
            "last_error": integration.get("last_error"),
        },
        "active_contaminated_feature_count": len(contaminated),
        "active_contaminated_feature_examples": contaminated[:10],
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
        key for key in sections
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
        if not isinstance(payload, dict):
            return payload
        sections = _d(payload.get("sections"))
        sections[SECTION_KEY] = build_integrity_section(active_core)
        payload["data_integrity_overlay_version"] = VERSION
        _recalculate(payload, daily)
        return payload

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


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None:
        return
    from flask import jsonify
    apply(core)
    if id(flask_app) in _REGISTERED_APP_IDS:
        return
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    path = "/paper/data-integrity-audit-status"
    if path not in existing:
        flask_app.add_url_rule(path, "paper_data_integrity_audit_status", lambda: jsonify(status_payload(core or _module())))
    _REGISTERED_APP_IDS.add(id(flask_app))


try:
    apply(None)
except Exception:
    pass
