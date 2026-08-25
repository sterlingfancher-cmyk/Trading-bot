"""Production-shape compatibility for the Issue #82 successor precondition.

The initial successor migration expected the known immutable TEM duplicate to be
reported in both ``coverage_issues`` and ``economic_issues`` and expected
``reconstructed_*`` field names.  The authoritative bidirectional analyzer
actually reports the exact TEM duplicate once as a coverage issue and exposes
``cash``, ``equity`` and ``open_positions`` directly.

This shim changes only that migration evidence reader.  It remains fail-closed:
there must be exactly one issue slot at most in each issue collection, at least
one issue overall, every reported issue must be the exact known TEM duplicate,
reconstructed cash must agree within one cent, reconstructed open-position
side/quantity/basis must match the current state, and mark-derived equity may
differ by at most two dollars to allow the already-observed sub-dollar
asynchronous valuation refresh during a live snapshot.

No state, ledger, risk, order, strategy, sizing, threshold, live, or ML authority
is added here.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

VERSION = "verified-v2-successor-precondition-production-shape-2026-08-25-v1"
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


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    try:
        import verified_v2_successor_epoch_migration as migration
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    current = getattr(migration, "_active_accounting_evidence", None)
    if getattr(current, "_production_shape_compatibility_version", None) == VERSION:
        _APPLIED = True
        return status_payload(core)

    def wrapped(runtime_core: Any) -> Tuple[Dict[str, Any], bool]:
        return _production_active_accounting_evidence(migration, runtime_core)

    wrapped._production_shape_compatibility_version = VERSION  # type: ignore[attr-defined]
    migration._active_accounting_evidence = wrapped
    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok" if _APPLIED else "pending",
        "overall": "pass" if _APPLIED else "warn",
        "version": VERSION,
        "production_accounting_payload_shape_supported": bool(_APPLIED),
        "equity_mark_drift_tolerance_dollars": EQUITY_MARK_DRIFT_TOLERANCE,
        "authority": {
            "precondition_only": True,
            "writes_state": False,
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
