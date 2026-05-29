"""Labels historical cached FMP valuation rows so old provider errors are not read as current failures."""
from __future__ import annotations

from typing import Any

VERSION = "fmp-cached-profile-label-guard-2026-05-29-v1"


def _text(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"error", "cached_error", "reason", "skip_reason", "status", "endpoint"} and item is not None:
                out.append(str(item))
            out.extend(_text(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(_text(item))
    elif isinstance(value, str):
        out.append(value)
    return out[:100]


def _is_denied(text: str) -> bool:
    s = str(text or "").lower()
    return "402" in s or "payment required" in s or "valid subscriptions" in s or "legacy endpoint" in s


def _label(row: dict[str, Any]) -> str:
    joined = " | ".join(_text(row)).lower()
    endpoint_status = row.get("provider_endpoint_status") or row.get("endpoint_status")
    has_current_guard_tag = bool(row.get("fmp_endpoint_skip_policy") or row.get("fmp_data_access_tier"))
    if "legacy endpoint" in joined or (endpoint_status and row.get("provider_endpoint_family") not in {"stable", None}):
        return "legacy_cached_profile"
    if _is_denied(joined) and (not has_current_guard_tag or row.get("status") in {"provider_error", "provider_empty", "missing_api_key"}):
        return "pre_guard_cached_profile"
    return ""


def sanitize_cached_profile(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    out = dict(row)
    label = _label(out)
    if not label:
        return out
    old_status = out.get("status")
    reasons = [label, "cached_historical_provider_diagnostic_not_current_guard_failure"]
    for reason in out.get("reasons", []) if isinstance(out.get("reasons"), list) else []:
        if reason not in reasons:
            reasons.append(reason)
    out["status"] = label
    out["cached_profile_label"] = label
    out["cached_profile_status_detail"] = "historical_cached_row; provider diagnostics are preserved but ignored as current guard failures"
    out["cached_provider_errors_are_historical"] = True
    out["original_cached_status"] = old_status
    out["fmp_endpoint_skip_policy"] = out.get("fmp_endpoint_skip_policy") or "daily_endpoint_cache"
    out["fmp_data_access_tier"] = out.get("fmp_data_access_tier") or "no_data"
    out["fmp_plan_limited"] = bool(out.get("fmp_plan_limited") or _is_denied(" | ".join(_text(out))))
    out["provider_endpoint_family"] = out.get("provider_endpoint_family") or "stable"
    out["provider_legacy_endpoint_disabled"] = True
    out["reasons"] = reasons[:12]
    out["live_trade_authority_changed"] = False
    return out


def apply_runtime_overrides(m: Any | None = None) -> dict[str, Any]:
    patched: list[str] = []
    errors: list[str] = []
    try:
        import fundamental_valuation_risk_layer as fvr
        original = getattr(fvr, "_stored_profiles", None)
        if callable(original) and not getattr(original, "_fmp_cached_profile_label_guard", False):
            def patched_stored_profiles(core: Any) -> dict[str, dict[str, Any]]:
                rows = original(core)
                if not isinstance(rows, dict):
                    return {}
                return {str(sym).upper(): sanitize_cached_profile(row) for sym, row in rows.items() if sym and isinstance(row, dict)}
            patched_stored_profiles._fmp_cached_profile_label_guard = True  # type: ignore[attr-defined]
            patched_stored_profiles._original_stored_profiles = original  # type: ignore[attr-defined]
            fvr._stored_profiles = patched_stored_profiles  # type: ignore[attr-defined]
            patched.append("fundamental_valuation_risk_layer._stored_profiles")
    except Exception as exc:
        errors.append(f"fundamental_valuation_risk_layer: {type(exc).__name__}: {str(exc)[:160]}")
    return {"status": "ok" if not errors else "warn", "type": "fmp_cached_profile_label_guard_apply", "version": VERSION, "patched": patched, "errors": errors}


def status_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "type": "fmp_cached_profile_label_guard_status",
        "version": VERSION,
        "cached_profile_labels": ["legacy_cached_profile", "pre_guard_cached_profile"],
        "policy": "historical cached provider errors are labeled and not treated as current guard failures",
    }


try:
    apply_runtime_overrides()
except Exception:
    pass
