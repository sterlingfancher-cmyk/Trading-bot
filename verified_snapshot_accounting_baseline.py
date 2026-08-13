"""Verified-snapshot accounting baseline helpers.

This module preserves the public/runtime surface used by the runtime and tests
while fixing a concurrency / deepcopy defect: the prior implementation used a
full copy.deepcopy(pf) which eagerly traversed and attempted to copy arbitrary
telemetry objects (scanner / research /provider / auto_runner substructures)
which may be non-copyable or hold runtime locks. The minimal correction is to
construct a detached, accounting-only working dict that contains only the fields
required by the downstream bidirectional accounting analyzer.

Preserved public surface:
- VERSION constant pattern
- _snapshot, _synthetic_entry_rows, _adjust_issue_indexes helpers
- apply(), status_payload(), register_routes() runtime hooks
- wrapper-installation marker attributes for the accounting guard wrappers

This file intentionally does NOT traverse or deep-copy unrelated telemetry.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

VERSION = "verified-snapshot-accounting-baseline-2026-08-12-v1"

# The set of scalar and structural keys we consider necessary for accounting
# reconstruction. Keep this small and explicit to avoid traversing large
# telemetry graphs.
_REQUIRED_ACCOUNTING_KEYS = (
    "trades",
    "positions",
    "cash",
    "equity",
    "history",
    "performance",
    "risk_controls",
    "paper_accounting_epoch",
    "accounting_epoch_id",
)


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _snapshot(working: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact snapshot view used by callers/tests.

    Keep the shape stable: include epoch id and a minimal verified_snapshot_baseline
    if present.
    """
    epoch = _d(working.get("paper_accounting_epoch"))
    snap: Dict[str, Any] = {
        "epoch_id": epoch.get("id") if epoch else None,
        "verified_snapshot_baseline": epoch.get("verified_snapshot_baseline") if epoch else None,
    }
    return snap


def _synthetic_entry_rows(working: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return synthetic opening-lot rows if the baseline describes an open lot.

    This preserves the previous module runtime hook semantics: callers expect a
    list of trade-like dicts representing synthetic opening lots that were
    introduced by a verified-snapshot baseline. Keep minimal semantics: if the
    epoch verified_snapshot_baseline contains "positions" with symbols, build
    synthetic entry rows for them.
    """
    epoch = _d(working.get("paper_accounting_epoch"))
    vs = _d(epoch.get("verified_snapshot_baseline"))
    positions = _d(vs.get("positions"))
    rows: List[Dict[str, Any]] = []
    for sym, pos in positions.items():
        try:
            side = pos.get("side", "long")
            qty = float(pos.get("qty", pos.get("quantity", 0)))
            entry_price = float(pos.get("entry_price", pos.get("entry", 0)))
        except Exception:
            continue
        rows.append({
            "symbol": str(sym).upper(),
            "action": "entry",
            "side": side,
            "shares": qty,
            "qty": qty,
            "price": entry_price,
            "synthetic": True,
            "source": "verified_snapshot_baseline",
        })
    return rows


def _adjust_issue_indexes(working: Dict[str, Any], trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Adjust issue/trade indexes to be contiguous starting at zero.

    This helper mirrors prior behavior: ensure trades returned to downstream
    analyzers have stable sequential indexes in the 'issue_index' field.
    """
    out: List[Dict[str, Any]] = []
    for idx, t in enumerate(trades):
        if not isinstance(t, dict):
            continue
        row = dict(t)
        row["issue_index"] = idx
        out.append(row)
    return out


def _build_working_from_portfolio(pf: Dict[str, Any]) -> Dict[str, Any]:
    """Construct a detached accounting-only 'working' dict from pf.

    This is the minimal and safe replacement for copy.deepcopy(pf). It only
    copies a small explicit set of keys and leaves all other telemetry objects
    untouched in the original pf. The returned dict is shallow-copied for those
    keys and will not hold references into large telemetry graphs.
    """
    if not isinstance(pf, dict):
        return {}

    working: Dict[str, Any] = {}
    # Copy only required accounting keys. For list/dict values we ensure a new
    # (shallow) list/dict object is created so downstream mutation cannot
    # accidentally touch original telemetry containers.
    for k in _REQUIRED_ACCOUNTING_KEYS:
        v = pf.get(k)
        if isinstance(v, dict):
            working[k] = dict(v)
        elif isinstance(v, list):
            working[k] = list(v)
        else:
            # scalars, None, or other small values are safe to copy by assignment
            working[k] = v

    # Backwards-compatible aliases expected by analyzers
    working.setdefault("positions", working.get("positions", {}))
    working.setdefault("trades", working.get("trades", []))
    working.setdefault("history", working.get("history", []))
    working.setdefault("performance", working.get("performance", {}))
    working.setdefault("risk_controls", working.get("risk_controls", {}))

    # Attach derived synthetic opening rows if the baseline requires it. These
    # should only be derived from the verified_snapshot_baseline (already
    # copied shallowly above) and not from any telemetry.
    synthetic = _synthetic_entry_rows(working)
    if synthetic:
        # Create a new trades list that appends synthetic entries at the start to
        # preserve prior semantics where baseline opening-lots preceded new
        # trades in the working view.
        base_trades = list(working.get("trades") or [])
        working["trades"] = synthetic + base_trades

    # Normalize issue indexes
    working["trades"] = _adjust_issue_indexes(working, list(working.get("trades") or []))

    return working


def apply(core: Any | None = None) -> Dict[str, Any]:
    """Primary runtime hook used to inspect / analyze the verified snapshot baseline.

    The implementation intentionally avoids traversing or deep-copying any
    telemetry objects attached to the runtime portfolio. It uses _build_working_from_portfolio
    to produce a minimal accounting-only view.
    """
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}

    pf = getattr(core, "portfolio", None)
    if not isinstance(pf, dict):
        return {"status": "ok", "version": VERSION, "working": {}, "note": "no_portfolio_dict"}

    working = _build_working_from_portfolio(pf)

    # Provide a compact status describing the verified snapshot baseline state.
    snapshot = _snapshot(working)
    return {
        "status": "ok",
        "version": VERSION,
        "generated_local": _now(core),
        "working_snapshot": snapshot,
        "working_trades_count": len(working.get("trades") or []),
        "working_positions_count": len(working.get("positions") or {}),
    }


def status_payload(core: Any | None = None) -> Dict[str, Any]:
    """Compatibility shim: return the same payload as apply()."""
    return apply(core)


def register_routes(app: Any, core: Any | None = None) -> None:
    """No runtime routes required for this helper module; kept for compatibility."""
    return None


# Wrapper-installation markers used by external guard modules to detect
# whether this accounting baseline has been installed/wrapped. Keep the simple
# attributes to preserve the runtime discovery hooks.
try:
    import paper_bidirectional_accounting_guard as _bid

    _bid._verified_snapshot_accounting_baseline_version = VERSION
except Exception:
    pass

try:
    import paper_accounting_integrity_guard as _intg

    _intg._verified_snapshot_accounting_baseline_version = VERSION
except Exception:
    pass

try:
    import paper_ledger_matched_exit_guard as _led

    _led._verified_snapshot_accounting_baseline_version = VERSION
except Exception:
    pass
