'''Runtime research snapshot aggregator and bounded diagnostics-only adjustments.

This module implements a small, reviewable diagnostics policy used by the
read-only runtime research audit. It intentionally does NOT change any runtime
or accounting authority. It only adjusts how certain legacy/superseded probes
are interpreted for the overall snapshot diagnostics.

Key behavioral rules implemented here (Issue #143):
- Keep collecting verified_v2_recovery_gate evidence but:
  - If the active daily-audit epoch is exactly a verified v2 epoch (stable-paper-v2...)
    then a failing verified_v2_recovery_gate should be reported as WARN (not FAIL)
    and included in the snapshot warnings.
  - If the active daily-audit epoch is stable-paper-v4 or later (v4+), then a
    failing verified_v2_recovery_gate is considered superseded/non-applicable and
    should NOT downgrade an otherwise-clean active audit. In that case the v2
    gate failure is omitted from the active snapshot warnings.
- Treat the root ('/') endpoint as optional once bootstrap + app readiness plus
  either paper_status OR self_check are healthy. If those readiness conditions
  are satisfied, a failing root should not downgrade the overall snapshot.
  Other required endpoint failures (daily_audit, self_check, paper_status, etc.)
  still produce WARN/FAIL as usual.

This file exposes a single pure function evaluate_snapshot(snapshot: dict)
that accepts a pre-collected snapshot (mapping of endpoint names -> result
objects) and returns an evaluation dict with keys: overall, warnings, errors,
per_check (the original results mapped). This makes the policy deterministic
and easy to unit test.

Safety boundaries (non-negotiable):
- This module is diagnostics-only. It never writes state, places orders, clears
  halts, or changes risk/accounting authority.
'''
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def _epoch_version_from_id(epoch_id: str) -> int | None:
    """Extract the numeric epoch version from an epoch id like
    'stable-paper-v4-20260826-successor01'. Returns None when unknown.
    """
    if not epoch_id or not isinstance(epoch_id, str):
        return None
    m = re.search(r"stable[-_]paper[-_]v(\d+)", epoch_id)
    if not m:
        m = re.search(r"paper_accounting_epoch.*v(\d+)", epoch_id)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _is_healthy(check: Any) -> bool:
    """Normalize endpoint result shapes for boolean healthy/ok determination.

    Accepts either: a dict with 'overall' in {'pass','warn','fail'},
    or a simple truthy value (True/False).
    """
    if isinstance(check, dict):
        overall = str(check.get("overall") or "").lower()
        return overall in ("pass", "ok")
    return bool(check)


def evaluate_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a runtime research snapshot and apply bounded diagnostics
    policy described in Issue #143.

    Input snapshot is a mapping from endpoint name -> result object. Result
    objects are opaque to this function beyond reading 'overall' where present.

    Returns a dictionary:
      - overall: 'pass' | 'warn' | 'fail'
      - warnings: list[str] of warning keys
      - errors: list[str] of failing required checks
      - per_check: copy of incoming snapshot

    Behavior summary (minimal and reviewable):
      - Any explicit failing required check (daily_audit, self_check, paper_status)
        causes overall 'warn' or 'fail' depending on strictness (here we keep
        to 'warn' for diagnostics-only; tests expect warn behavior for these)
      - The legacy verified_v2_recovery_gate failure is only relevant when the
        active epoch version is exactly 2. When active epoch is v4 or later the
        legacy gate is treated as superseded and omitted from warnings.
      - The root endpoint failure is treated as optional once bootstrap/app
        readiness plus (paper_status OR self_check) are healthy.

    This function intentionally keeps policy narrow and conservative.
    """
    per_check = dict(snapshot or {})
    warnings: List[str] = []
    errors: List[str] = []

    # Helper to read overall from a result object
    def _overall_of(obj: Any) -> str:
        if isinstance(obj, dict):
            return str(obj.get("overall") or obj.get("status") or "").lower()
        return "pass" if bool(obj) else "fail"

    # 1) Determine active epoch version from daily_audit or paper_status payloads.
    active_epoch_id = None
    # Try common locations: daily_audit.epoch_id, daily_audit.accounting_epoch.id,
    # paper_status.paper_accounting_epoch.id, paper_status.epoch_id
    daily_audit = per_check.get("daily_audit") or per_check.get("fresh_day")
    if isinstance(daily_audit, dict):
        # try common shapes
        epoch = daily_audit.get("epoch_id") or daily_audit.get("paper_accounting_epoch") or daily_audit.get("accounting_epoch")
        if isinstance(epoch, dict):
            active_epoch_id = epoch.get("id") or epoch.get("epoch_id")
        elif isinstance(epoch, str):
            active_epoch_id = epoch
        else:
            # maybe daily_audit contains an 'active_epoch' string directly
            active_epoch_id = daily_audit.get("active_epoch") or active_epoch_id

    # fallback to paper_status shapes
    if not active_epoch_id:
        paper_status = per_check.get("paper_status")
        if isinstance(paper_status, dict):
            epoch = paper_status.get("paper_accounting_epoch") or paper_status.get("accounting_epoch")
            if isinstance(epoch, dict):
                active_epoch_id = epoch.get("id") or epoch.get("epoch_id")
            elif isinstance(epoch, str):
                active_epoch_id = epoch
            else:
                active_epoch_id = paper_status.get("epoch_id") or active_epoch_id

    epoch_version = _epoch_version_from_id(active_epoch_id or "")

    # 2) Evaluate required critical components and collect their statuses.
    # Consider these endpoints required for an active audit: daily_audit, self_check, paper_status
    required_keys = ["daily_audit", "self_check", "paper_status"]

    for key in required_keys:
        val = per_check.get(key)
        if val is None:
            # missing required check is a warning (diagnostics-only)
            warnings.append(f"{key}_missing")
            continue
        overall = _overall_of(val)
        if overall in ("fail", "error"):
            errors.append(key)
        elif overall == "warn":
            warnings.append(key)

    # 3) Treat verified_v2_recovery_gate specially per Issue #143.
    v2_gate = per_check.get("verified_v2_recovery_gate")
    if v2_gate is not None:
        v2_overall = _overall_of(v2_gate)
        if v2_overall in ("fail", "error"):
            # Only make it relevant when active epoch is exactly v2.
            if epoch_version == 2:
                # report as a warning only (do not escalate to error/fail)
                warnings.append("verified_v2_recovery_gate")
            else:
                # On v4+ or when epoch is not v2, treat as superseded/non-applicable
                # and DO NOT add to warnings/errors. Keep it present in per_check for
                # forensic/read-only visibility but it should not downgrade an otherwise
                # clean active audit.
                pass
        elif v2_overall == "warn":
            # Only relevant for v2 active epoch; on v2 keep warn; otherwise ignore.
            if epoch_version == 2:
                warnings.append("verified_v2_recovery_gate")

    # 4) Root '/' optionality rule: if root failing but bootstrap/app readiness plus
    #    (paper_status OR self_check) are healthy, then don't count root as a warning.
    root = per_check.get("root")
    if root is not None:
        root_overall = _overall_of(root)
        if root_overall in ("fail", "error"):
            # Evaluate readiness pieces
            bootstrap_ok = _is_healthy(per_check.get("bootstrap_listener")) or _is_healthy(per_check.get("bootstrap"))
            app_ready_ok = _is_healthy(per_check.get("app_ready")) or _is_healthy(per_check.get("application_ready"))
            paper_ok = _is_healthy(per_check.get("paper_status"))
            self_check_ok = _is_healthy(per_check.get("self_check"))
            if bootstrap_ok and app_ready_ok and (paper_ok or self_check_ok):
                # Root is optional now; do not warn.
                pass
            else:
                # Root remains required; add to warnings/errors depending on strictness.
                warnings.append("root")

    # 5) Any other named checks in snapshot that carry explicit 'overall: fail' and
    #    are not the special-case v2 gate should be included in warnings/errors
    #    so operators can see them. We do not aggressively fail here; diagnostics-only
    #    policy keeps to warn presence unless a required component failed above.
    for key, val in per_check.items():
        if key in required_keys or key in ("verified_v2_recovery_gate", "root"):
            continue
        overall = _overall_of(val)
        if overall in ("fail", "error"):
            # Only add when not already recorded
            if key not in errors and key not in warnings:
                warnings.append(key)

    # 6) Compose overall result. Conservative diagnostics-only mapping:
    #    - If any required component is in errors -> overall = 'warn' (do not force 'fail')
    #    - Else if any warnings were collected -> overall = 'warn'
    #    - Else -> 'pass'
    overall = "pass"
    if errors:
        overall = "warn"
    elif warnings:
        overall = "warn"

    return {"overall": overall, "warnings": sorted(set(warnings)), "errors": sorted(set(errors)), "per_check": per_check, "active_epoch_id": active_epoch_id, "active_epoch_version": epoch_version}


# small convenience for CLI debugging (keeps module side-effects minimal)
if __name__ == "__main__":
    import json
    import sys

    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    out = evaluate_snapshot(data)
    print(json.dumps(out, indent=2, sort_keys=True))
