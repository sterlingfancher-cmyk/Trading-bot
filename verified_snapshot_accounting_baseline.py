from __future__ import annotations

"""
Verified Snapshot — Accounting-only detached view builder.

Purpose:
- Avoid deepcopying the entire live portfolio/state (which can traverse
  non-copyable, mutable, or threaded telemetry objects and cause concurrency
  tracebacks in production).
- Build a small, detached, accounting-only working view that contains only the
  fields required by the bidirectional accounting analyzer: verified snapshot
  baseline inputs, current trade rows, current positions/marks, and required
  accounting scalar inputs.

Semantics:
- Preserve the same logical accounting inputs as the original verified
  snapshot baseline semantics (cash/equity, trades, positions, marks, and
  the verified snapshot metadata) but do not attempt to traverse or clone
  scanner, research, provider, reporting, or auto-runner telemetry.
- Be defensive: tolerate missing fields and fall back to state.load_state()
  read when appropriate.

This module intentionally avoids any global deepcopy of the running process
state. It attempts to read only the minimal, well-known keys and returns a
plain dict composed of immutable primitives (numbers, strings, lists, maps)
that accounting analyzers can safely inspect and manipulate.

Note: This file intentionally exposes a conservative top-level function named
"build_accounting_view". Other modules may import a different symbol; to be
resilient during the transition we also export the older common aliases
(verified_snapshot_baseline) to reduce the chance of downstream breakage.
"""
from typing import Any, Dict, List


def _safe_get_portfolio(core: Any) -> Dict[str, Any]:
    """Return the in-process portfolio mapping, if available and a dict.

    We purposely do not deepcopy or traverse nested objects here. The caller
    will receive only shallow snapshots of the few keys we extract below.
    """
    try:
        pf = getattr(core, "portfolio", None)
        if isinstance(pf, dict):
            return pf
    except Exception:
        # Be conservative: if attribute access fails, fall back to explicit
        # state load below.
        pass

    # Attempt to load persisted state (safe read) as a fallback. load_state may
    # itself access I/O, so wrap defensively.
    try:
        load = getattr(core, "load_state", None)
        if callable(load):
            st = load()
            if isinstance(st, dict):
                return st
    except Exception:
        pass

    return {}


def _shallow_copy_if_present(source: Any, key: str):
    """Return a shallow copy of source[key] if it exists and is of a safe
    primitive collection type. Otherwise return None.

    We intentionally avoid walking arbitrary nested structures. Only
    dict/list/scalar types are allowed here and are copied shallowly so the
    returned view is detached from potential live mutable objects.
    """
    if not isinstance(source, dict):
        return None
    val = source.get(key)
    if val is None:
        return None
    # Allow basic immutable or container types; copy lists/dicts shallowly.
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, list):
        return list(val)
    if isinstance(val, dict):
        return dict(val)
    # Otherwise avoid copying/traversing non-copyable objects.
    return None


def build_accounting_view(core: Any) -> Dict[str, Any]:
    """Build and return a detached accounting-only view from the running core.

    Returned structure (best-effort, keys may be missing):
    - verified_snapshot: dict | None  (baseline snapshot metadata)
    - trades: list  (list of trade rows)
    - positions: dict  (mapping symbol -> position dict)
    - marks: dict  (symbol -> mark/price mapping)
    - scalars: dict (cash, equity, realized_today, accounting_model, epoch)

    This function never performs a deep copy or walks unknown nested objects
    such as scanner, telemetry, or provider pools. It only shallow-copies the
    handful of allowed containers above.
    """
    pf = _safe_get_portfolio(core)

    # Extract verified snapshot baseline inputs
    verified_snapshot = _shallow_copy_if_present(pf, "verified_snapshot") or _shallow_copy_if_present(pf, "baseline") or {}

    # Current trade rows (journal/trades). Accept list-of-dicts only.
    trades = _shallow_copy_if_present(pf, "trades")
    if trades is None:
        # Some runtimes call the journal "trade_journal" with inner key "trades".
        tj = _shallow_copy_if_present(pf, "trade_journal")
        if isinstance(tj, dict):
            trades = list(tj.get("trades", []))
    if trades is None:
        trades = []

    # Current positions: prefer a dict mapping symbol->position
    positions = _shallow_copy_if_present(pf, "positions")
    if positions is None:
        # Some code stores positions under nested portfolio -> portfolio.positions
        nested = _shallow_copy_if_present(pf, "portfolio")
        if isinstance(nested, dict):
            positions = _shallow_copy_if_present(nested, "positions")
    if positions is None:
        positions = {}

    # Marks/prices mapping
    marks = _shallow_copy_if_present(pf, "marks") or _shallow_copy_if_present(pf, "prices") or _shallow_copy_if_present(pf, "latest_prices") or {}

    # Accounting scalars: cash, equity, realized_today, accounting model, epoch id
    scalars = {
        "cash": _shallow_copy_if_present(pf, "cash") or _shallow_copy_if_present(pf, "cash_balance") or None,
        "equity": _shallow_copy_if_present(pf, "equity") or _shallow_copy_if_present(pf, "nav") or None,
        "realized_today": _shallow_copy_if_present(pf, "realized_today") or _shallow_copy_if_present(pf, "realized") or None,
        "accounting_model": _shallow_copy_if_present(pf, "accounting_model") or _shallow_copy_if_present(pf, "model") or None,
        "epoch": _shallow_copy_if_present(pf, "epoch") or _shallow_copy_if_present(pf, "accounting_epoch") or None,
    }

    # Always return primitive-typed containers only (dict/list/primitives).
    return {
        "verified_snapshot": verified_snapshot,
        "trades": trades,
        "positions": positions,
        "marks": marks,
        "scalars": scalars,
    }


# Backwards-compatible aliases for callers expecting older names.
def verified_snapshot_baseline(core: Any) -> Dict[str, Any]:
    """Alias preserving older import names.

    Prefer calling build_accounting_view() directly in new code.
    """
    return build_accounting_view(core)


__all__ = ["build_accounting_view", "verified_snapshot_baseline"]
