"""Exact-evidence Issue #126 v3 -> v4 successor accounting migration.

This module exposes a focused verifier helper used by the successor gating tests.

Only a small, well-contained verifier helper is required by the focused test
changes in this PR. The full migration module in-tree is intentionally large;
for the narrow unit tests we only need the constants and the precise verifier
helper that was previously mis-behaving with alias fallbacks.

The canonical_only_terminal_dhr_state_shape_exact() function below is intentionally
strict: it requires the persisted snapshot to show exactly the two positions
(DHR and SLS), DHR must be long, and the DHR quantity must include both the
expected "qty" alias (equal to EXPECTED_BASELINE_DHR_QTY within QTY_TOLERANCE)
and the persistent canonical "shares" alias (equal to EXPECTED_DHR_REMAINDER
within QTY_TOLERANCE). This function will fail-closed if either alias is missing
or out-of-tolerance. The function returns a tuple (payload, ready_bool) to be
compatible with other verifier helpers in the repo.

This file intentionally avoids any write-paths, live trading authority, or any
mutation of canonical/ledger/accounting state. It is purely read-only logic
used by focused unit tests validating the exact pre-cutover persisted shape.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Tuple

VERSION = "verified-v3-successor-epoch-migration-mini-verifier-2026-08-28"

# Domain constants used by the exact-evidence v3->v4 migration tests.
EXPECTED_BASELINE_SLS_QTY = 4.353086829
EXPECTED_BASELINE_DHR_QTY = 0.540748758
QTY_TOLERANCE = 5e-6
EXPECTED_DHR_REMAINDER = EXPECTED_BASELINE_DHR_QTY - 0.178447


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _close(value: Any, expected: float, tolerance: float) -> bool:
    """Numeric closeness guard used by verification helpers.

    Returns False if the value cannot be interpreted as a finite float.
    """
    number = _f(value)
    if number is None:
        return False
    return abs(number - expected) <= tolerance


def canonical_only_terminal_dhr_state_shape_exact(pf: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Verify the exact persisted DHR canonical-only divergence shape.

    Rules (strict / fail-closed):
    - The verified snapshot baseline must expose positions and those positions
      must be exactly the two symbols: DHR and SLS (no extra symbols).
    - The DHR position must report side == 'long'.
    - The DHR position must contain an explicit 'qty' alias and it must be
      numerically close to EXPECTED_BASELINE_DHR_QTY within QTY_TOLERANCE.
      (Do NOT fall back to 'shares' for this check.)
    - The DHR position must also contain an explicit 'shares' alias and it must
      be numerically close to EXPECTED_DHR_REMAINDER within QTY_TOLERANCE.
      (This verifies the canonical-only exit remainder that never mirrored to
      state cash.)
    - The SLS position must be present and long; we allow the SLS quantity to
      be represented under either 'qty' or 'shares' (backwards compat alias),
      but it must be close to EXPECTED_BASELINE_SLS_QTY.

    Returns a tuple (payload_dict, ok_bool). The payload contains diagnostic
    fields to help unit tests and operator inspection.
    """
    issues = []

    epoch = _d(pf.get("paper_accounting_epoch"))
    snap = _d(epoch.get("verified_snapshot_baseline"))
    positions = _d(snap.get("positions"))

    # Must be exactly two positions: DHR and SLS.
    keys = {str(k).upper() for k in positions}
    if keys != {"DHR", "SLS"}:
        issues.append("position_set_not_exact_DHR_SLS")
        return ({"status": "fail", "issues": issues}, False)

    # SLS checks: present, long, qty/shares close to expected
    sls = _d(positions.get("SLS"))
    sls_side = str(sls.get("side") or "").lower()
    if sls_side != "long":
        issues.append("sls_side_not_long")
        return ({"status": "fail", "issues": issues}, False)

    # Accept either qty or shares alias for SLS (backwards compatibility)
    sls_qty_value = None
    if "qty" in sls:
        sls_qty_value = sls.get("qty")
    elif "shares" in sls:
        sls_qty_value = sls.get("shares")

    if sls_qty_value is None or not _close(sls_qty_value, EXPECTED_BASELINE_SLS_QTY, QTY_TOLERANCE):
        issues.append("sls_qty_mismatch")
        return ({"status": "fail", "issues": issues}, False)

    # DHR checks: present and long
    dhr = _d(positions.get("DHR"))
    dhr_side = str(dhr.get("side") or "").lower()
    if dhr_side != "long":
        issues.append("dhr_side_not_long")
        return ({"status": "fail", "issues": issues}, False)

    # Critical: require explicit 'qty' alias for DHR and check it exactly (no fallback)
    if "qty" not in dhr:
        issues.append("dhr_qty_alias_missing")
        return ({"status": "fail", "issues": issues}, False)

    if not _close(dhr.get("qty"), EXPECTED_BASELINE_DHR_QTY, QTY_TOLERANCE):
        issues.append("dhr_qty_mismatch")
        return ({"status": "fail", "issues": issues}, False)

    # Also require explicit 'shares' alias for DHR and check the remainder amount.
    if "shares" not in dhr:
        issues.append("dhr_shares_alias_missing")
        return ({"status": "fail", "issues": issues}, False)

    if not _close(dhr.get("shares"), EXPECTED_DHR_REMAINDER, QTY_TOLERANCE):
        issues.append("dhr_shares_mismatch")
        return ({"status": "fail", "issues": issues}, False)

    # If we reach here, shape matches exactly.
    payload = {
        "status": "ok",
        "issues": [],
        "positions_checked": ["DHR", "SLS"],
        "dhr_qty": float(dhr.get("qty")),
        "dhr_shares": float(dhr.get("shares")),
        "sls_qty_or_shares": float(sls_qty_value),
    }
    return (payload, True)
