"""Production-shape compatibility for the Issue #82 successor precondition.

The initial successor migration expected the known immutable TEM duplicate to be
reported in both ``coverage_issues`` and ``economic_issues`` and expected
``reconstructed_*`` field names. The authoritative bidirectional analyzer
actually reports the exact TEM duplicate once as a coverage issue and exposes
``cash``, ``equity`` and ``open_positions`` directly.

Production later proved one additional startup-composition shape: the successor
cutover can complete and persist its exact durable marker, then a stale verified-v2
state can be restored by later registration before the final startup consistency
owner runs. The migration correctly reports that mismatch as an error, but doing
so inside the bridge prevents the finalizer from getting the chance to repair the
already-proven interrupted completion. This compatibility layer therefore defers
only that exact error shape to the dedicated finalizer. It never performs the
cutover itself and leaves every other migration error unchanged.

No state, ledger, risk, order, strategy, sizing, threshold, live, or ML authority
is added here.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

VERSION = "verified-v2-successor-precondition-production-shape-2026-08-25-v2-finalizer-deferral"
EQUITY_MARK_DRIFT_TOLERANCE = 2.0
QTY_SERIALIZATION_TOLERANCE = 5e-6
ENTRY_PRICE_TOLERANCE = 1e-4
_APPLIED = False


def _positions_match(migration: Any, pf: Dict[str, Any], result: Dict[str, Any]) -> bool:
    current = migration._verified_positions(pf)
    raw_rebuilt = migration._d(result.get("open_positions"))
    if set(current) != set(raw_rebuilt):
        return False
    for symbol, expected in current.items():
        rebuilt = migration._d(raw_rebuilt.get(symbol))
        side = str(rebuilt.get("side") or "").lower().strip()
        qty = migration._f(rebuilt.get("qty", rebuilt.get("shares")))
        entry = migration._f(rebuilt.get("entry_price", rebuilt.get("entry")))
        if side != str(expected.get("side") or ""):
            return False
        if qty is None or abs(qty - float(expected.get("qty") or 0.0)) > QTY_SERIALIZATION_TOLERANCE:
            return False
        if entry is None or abs(entry - float(expected.get("entry_price") or 0.0)) > ENTRY_PRICE_TOLERANCE:
            return False
    return True


def _production_active_accounting_evidence(migration: Any, core: Any) -> Tuple[Dict[str, Any], bool]:
    pf = migration._portfolio(core)
    try:
        import paper_bidirectional_accounting_guard as accounting
        result = accounting.analyze_ledger(pf, core)
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}, False

    coverage = [row for row in migration._l(result.get("coverage_issues")) if isinstance(row, dict)]
    economics = [row for row in migration._l(result.get("economic_issues")) if isinstance(row, dict)]
    issues = coverage + economics
    issue_shape_exact = bool(
        len(coverage) <= 1
        and len(economics) <= 1
        and issues
        and all(migration._tem_issue_exact(row) for row in issues)
    )
    if not issue_shape_exact:
        return result, False

    current_cash = migration._f(pf.get("cash"))
    current_equity = migration._f(pf.get("equity"))
    rebuilt_cash = migration._f(result.get("reconstructed_cash", result.get("cash")))
    rebuilt_equity = migration._f(result.get("reconstructed_equity", result.get("equity")))
    positions_match = _positions_match(migration, pf, result)

    ok = bool(
        current_cash is not None and current_cash > 0
        and current_equity is not None and current_equity > 0
        and rebuilt_cash is not None and abs(rebuilt_cash - current_cash) <= 0.01
        and rebuilt_equity is not None and rebuilt_equity > 0
        and abs(rebuilt_equity - current_equity) <= EQUITY_MARK_DRIFT_TOLERANCE
        and positions_match
    )
    return result, ok


def _active_epoch_id(migration: Any, core: Any) -> str:
    pf = migration._portfolio(core)
    epoch = migration._d(pf.get("paper_accounting_epoch"))
    return str(epoch.get("id") or pf.get("accounting_epoch_id") or "")


def _exact_interrupted_completion(migration: Any, core: Any) -> bool:
    if core is None:
        return False
    marker = migration._marker()
    return bool(
        marker.get("status") == "completed"
        and str(marker.get("target_epoch_id") or "") == migration.TARGET_EPOCH_ID
        and str(marker.get("prior_epoch_id") or "") == migration.OLD_EPOCH_ID
        and marker.get("canonical_ledger_unchanged") is True
        and _active_epoch_id(migration, core) == migration.OLD_EPOCH_ID
    )


def _defer_exact_interrupted_completion_error(
    migration: Any, core: Any, result: Any
) -> Any:
    if not isinstance(result, dict):
        return result
    if not (
        result.get("status") == "error"
        and result.get("reason") == "completed_marker_present_but_successor_epoch_not_active"
        and _exact_interrupted_completion(migration, core)
    ):
        return result
    return {
        "status": "pending_finalizer",
        "overall": "warn",
        "version": VERSION,
        "reason": "exact_interrupted_completion_deferred_to_finalizer",
        "active_epoch_id": migration.OLD_EPOCH_ID,
        "target_epoch_id": migration.TARGET_EPOCH_ID,
        "completed_marker_present": True,
        "canonical_ledger_unchanged": True,
        "finalizer_retry_owner": "verified_v2_successor_epoch_migration_finalizer",
        "writes_state": False,
    }


def _install_migration_apply_compatibility(migration: Any) -> None:
    current = getattr(migration, "apply", None)
    if not callable(current):
        return
    if getattr(current, "_interrupted_completion_compatibility_version", None) == VERSION:
        return
    original = current

    def wrapped(runtime_core: Any = None) -> Any:
        result = original(runtime_core)
        return _defer_exact_interrupted_completion_error(migration, runtime_core, result)

    wrapped._interrupted_completion_compatibility_version = VERSION  # type: ignore[attr-defined]
    wrapped._interrupted_completion_original_apply = original  # type: ignore[attr-defined]
    migration.apply = wrapped


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import verified_v2_successor_epoch_migration as migration
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(migration, "_active_accounting_evidence", None)
    if getattr(current, "_production_shape_compatibility_version", None) != VERSION:
        def wrapped(runtime_core: Any) -> Tuple[Dict[str, Any], bool]:
            return _production_active_accounting_evidence(migration, runtime_core)

        wrapped._production_shape_compatibility_version = VERSION  # type: ignore[attr-defined]
        migration._active_accounting_evidence = wrapped

    _install_migration_apply_compatibility(migration)
    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "version": VERSION,
        "production_accounting_payload_shape_supported": bool(_APPLIED),
        "exact_interrupted_completion_error_deferred_to_finalizer": bool(_APPLIED),
        "equity_mark_drift_tolerance_dollars": EQUITY_MARK_DRIFT_TOLERANCE,
        "authority": {
            "precondition_only": True,
            "writes_state": False,
            "defers_only_exact_completed_v3_marker_with_verified_v2_reversion": True,
            "finalizer_remains_only_retry_owner": True,
            "edits_or_deletes_canonical_rows": False,
            "rewrites_current_day_peak": False,
            "clears_hard_halt": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
