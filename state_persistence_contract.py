"""State persistence safety contract (minimal prospective guard).

Purpose
--------
This module installs a narrow runtime guard that prevents a stale on-disk
persisted snapshot from resurrecting a position that has already been closed
according to the authoritative canonical execution ledger.

Behavioral constraints (non-negotiable):
- This file does NOT rewrite, delete, or fabricate any canonical ledger rows.
- It only prevents a persisted portfolio load from reintroducing positions
  whose originating entry execution id has a corresponding close recorded
  in the canonical ledger.
- It is paper-only / safety-only: it only patches the in-memory _replace_portfolio
  call (if present) to run a provenance check and prune resurrected positions
  from the snapshot before the real replace happens.
- No account state, risk thresholds, halts, authorities, or historical rows are
  changed or removed. We only avoid overwriting memory with an inconsistent
  resurrected position.

Design notes
------------
- The wrapper is intentionally conservative and defensive: it supports a variety
  of common field names used in persisted positions and canonical ledger rows
  so it can reliably detect closures in production-shaped artifacts without
  requiring a brittle schema dependency.
- If evidence is missing (no canonical ledger available), the wrapper is a
  no-op to avoid false positives.

Minimal patch rationale
-----------------------
This change implements the exact suggested fix in the handoff: compare
persisted-state execution/trade provenance against the canonical ledger
before any _replace_portfolio reload that would reintroduce a canonically
closed position, and fail-closed (prune) rather than mutating account or risk
state.

This module is intentionally small and focused so that it can be reviewed and
accepted without broad rewrite risk.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any, Dict, Iterable, List, Optional, Set

# Expose a VERSION so runtime diagnostics can confirm the guard is active.
VERSION = "state-persistence-contract-2026-08-14-v1"


def _mod() -> Optional[Any]:
    """Return the host application module when available (app or __main__).

    This mirrors the tolerant discovery used across the codebase so the guard
    can activate during normal imports in both test harness and running app.
    """
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        try:
            if module is not None and getattr(module, "app", None) is not None:
                return module
        except Exception:
            continue
    return None


def _collect_canonical_closed_entry_ids(core: Any) -> Set[str]:
    """Robustly scan for entry execution ids that have been closed in the
    canonical execution ledger.

    The function tries multiple access patterns commonly used in this codebase:
    - core.canonical_execution_ledger (list)
    - core.portfolio.get("canonical_execution_ledger")
    - a callable core.load_canonical_execution_ledger()
    - a filesystem fallback in the persistent STATE_DIR canonical file

    The set returns entry execution ids which will be used to decide whether a
    persisted open position is already closed.
    """
    out: Set[str] = set()

    # Try to obtain the ledger from multiple known locations
    ledger_candidates: Iterable[Any] = []
    try:
        ledger_candidates = (
            getattr(core, "canonical_execution_ledger", None),
            (getattr(core, "portfolio", {}) or {}).get("canonical_execution_ledger"),
            getattr(core, "load_canonical_execution_ledger", None),
        )
    except Exception:
        ledger_candidates = ()

    ledger_rows: List[Dict[str, Any]] = []

    for cand in ledger_candidates:
        try:
            if cand is None:
                continue
            if callable(cand):
                maybe = cand()
                if isinstance(maybe, list):
                    ledger_rows.extend([r for r in maybe if isinstance(r, dict)])
            elif isinstance(cand, list):
                ledger_rows.extend([r for r in cand if isinstance(r, dict)])
        except Exception:
            # Be defensive: if any callable raises, continue to other sources.
            continue

    # Filesystem fallback: conservative and optional. Do not raise on failure.
    try:
        state_dir = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
        cand_path = os.path.join(state_dir, "canonical_execution_ledger.json")
        if os.path.isfile(cand_path):
            with open(cand_path, "r", encoding="utf-8") as f:
                j = json.load(f)
                if isinstance(j, list):
                    ledger_rows.extend([r for r in j if isinstance(r, dict)])
    except Exception:
        pass

    # Normalize and extract: many canonical exit rows will reference the entry by
    # one of several keys. Be permissive but explicit.
    EXIT_ACTION_TOKENS = {"exit", "full_exit", "partial_exit", "reduce", "closed"}
    ENTRY_REFERENCE_KEYS = (
        "entry_execution_id",
        "entry_id",
        "entry",
        "in",
        "in_execution_id",
        "related_entry",
        "reconciles_entry",
    )

    for row in ledger_rows:
        try:
            if not isinstance(row, dict):
                continue
            action = str(row.get("action") or "").strip().lower()
            # If this row looks like an exit/closing record, check payload for an
            # entry reference. Some ledgers also label exits differently; we
            # check for any of the tokens above as a best-effort.
            if any(tok in action for tok in EXIT_ACTION_TOKENS) or row.get("exit") or row.get("closed"):
                for key in ENTRY_REFERENCE_KEYS:
                    val = row.get(key)
                    if isinstance(val, str) and val:
                        out.add(val)
                    elif isinstance(val, dict):
                        # Some rows embed an entry object
                        maybe = val.get("execution_id") or val.get("id")
                        if isinstance(maybe, str) and maybe:
                            out.add(maybe)
                # Also check generic fields that sometimes hold provenance
                for maybe_field in ("entry_execution_ids", "related_execution_ids", "provenance"):
                    val = row.get(maybe_field)
                    if isinstance(val, (list, tuple)):
                        for item in val:
                            if isinstance(item, str) and item:
                                out.add(item)
                    elif isinstance(val, dict):
                        maybe = val.get("entry_execution_id") or val.get("execution_id")
                        if isinstance(maybe, str) and maybe:
                            out.add(maybe)
        except Exception:
            continue

    return out


def _extract_position_entry_ids(pos: Any) -> Set[str]:
    """Extract candidate entry execution ids from a persisted position object.

    The persisted position may store provenance under different shapes. We
    attempt a series of common keys and nested lookups. The result is a set to
    permit multiple ids if present; callers treat presence conservatively.
    """
    out: Set[str] = set()
    if not isinstance(pos, dict):
        return out

    # Common flat keys
    for key in ("entry_execution_id", "entry_id", "entry", "execution_id", "id"):
        val = pos.get(key)
        if isinstance(val, str) and val:
            out.add(val)
        elif isinstance(val, dict):
            nested = val.get("execution_id") or val.get("id")
            if isinstance(nested, str) and nested:
                out.add(nested)

    # 'provenance' or 'meta' nested dicts
    for container in ("provenance", "meta", "provenance_info", "execution_provenance"):
        obj = pos.get(container)
        if isinstance(obj, dict):
            for subkey in ("entry_execution_id", "entry_id", "execution_id", "id"):
                v = obj.get(subkey)
                if isinstance(v, str) and v:
                    out.add(v)

    # Some persisted position representations store trade objects
    for k in ("entry_trade", "entry_trade_obj", "entry", "in_trade"):
        v = pos.get(k)
        if isinstance(v, dict):
            for subkey in ("execution_id", "entry_execution_id", "id"):
                s = v.get(subkey)
                if isinstance(s, str) and s:
                    out.add(s)

    return out


def _prune_resurrected_positions_from_snapshot(core: Any, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Return a snapshot copy with resurrected positions removed.

    The function is intentionally non-destructive to the original snapshot
    structure insofar as it returns a new dict that callers may apply. We also
    record a short diagnostic summary in the returned snapshot under
    "__state_persistence_prune__" for operator visibility.
    """
    try:
        closed_entry_ids = _collect_canonical_closed_entry_ids(core)
        if not closed_entry_ids:
            # No canonical evidence available => do nothing
            return snapshot

        positions = (snapshot.get("positions") or {})
        if not isinstance(positions, dict):
            return snapshot

        to_remove: List[str] = []
        pruned_details: List[Dict[str, Any]] = []

        for pos_key, pos_value in list(positions.items()):
            try:
                entry_ids = _extract_position_entry_ids(pos_value)
                if any(eid in closed_entry_ids for eid in entry_ids if isinstance(eid, str)):
                    to_remove.append(pos_key)
                    pruned_details.append({"position_key": pos_key, "entry_ids": sorted(entry_ids)})
            except Exception:
                continue

        if not to_remove:
            return snapshot

        # Create a shallow copy to avoid mutating caller-supplied object
        new_snap = dict(snapshot)
        new_positions = dict(positions)
        for k in to_remove:
            new_positions.pop(k, None)
        new_snap["positions"] = new_positions

        # Attach a conservative human-readable diagnostic. Tests and operators can
        # assert on this artifact; it's not used by runtime risk logic.
        new_snap.setdefault("__state_persistence_prune__", {})["version"] = VERSION
        new_snap.setdefault("__state_persistence_prune__", {})["removed_positions"] = pruned_details[:50]
        return new_snap
    except Exception:
        # Be paranoid: on any unexpected error, do not interfere with the
        # restore — failing-safe is to be a no-op here (so we avoid false
        # blocking of legitimate reloads). The net effect is: guard is
        # conservative and non-fatal.
        try:
            tb = traceback.format_exc()
            core.portfolio.setdefault("state_persistence_guard_error", tb)
        except Exception:
            pass
        return snapshot


def _install_guard_on_replace() -> None:
    """Patch the host core's _replace_portfolio (if present) with a wrapper
    that prunes resurrected positions before delegating to the original.

    The wrapper is applied only once and is idempotent.
    """
    core_mod = _mod()
    if core_mod is None:
        return

    try:
        # The runtime uses a variety of names; prefer a private hook if present.
        original = getattr(core_mod, "_replace_portfolio", None)
        if not callable(original):
            # Nothing to patch; exit quietly
            return

        if getattr(original, "_state_persistence_guard_wrapped", False):
            return

        def _wrapped_replace_portfolio(persisted_state: Dict[str, Any], *args, **kwargs):
            # Defensive: ensure persisted_state is dict-like
            try:
                snap = persisted_state if isinstance(persisted_state, dict) else dict(persisted_state or {})
            except Exception:
                snap = persisted_state

            try:
                safe_snap = _prune_resurrected_positions_from_snapshot(core_mod, snap)
            except Exception:
                safe_snap = snap

            # Record diagnostics for operator visibility (non-authoritative):
            try:
                diag = core_mod.portfolio.setdefault("state_persistence_contract", {})
                diag["last_checked"] = getattr(core_mod, "local_ts_text", lambda: "")()
                diag["active_version"] = VERSION
                diag["pruned_snapshot"] = bool(safe_snap is not snap and safe_snap.get("__state_persistence_prune__"))
            except Exception:
                pass

            # Delegate to the real replacer with the (possibly) sanitized snapshot
            return original(safe_snap, *args, **kwargs)

        _wrapped_replace_portfolio._state_persistence_guard_wrapped = True  # type: ignore[attr-defined]
        _wrapped_replace_portfolio._version = VERSION  # type: ignore[attr-defined]

        setattr(core_mod, "_replace_portfolio", _wrapped_replace_portfolio)

        # Provide a stable accessor for diagnostics/tests to confirm installation
        core_mod.__dict__.setdefault("_state_persistence_contract_installed", True)
    except Exception:
        # Swallow patch failures to avoid preventing startup. The gate is
        # optional and conservative; failure should not change runtime behavior.
        try:
            tb = traceback.format_exc()
            core_mod.portfolio.setdefault("state_persistence_guard_install_error", tb)
        except Exception:
            pass


# Install immediately on import so that module-level patches take effect for
# the typical startup path. This follows the established pattern in other
# 'patch' modules in the repository where import-time composition is used.
try:
    _install_guard_on_replace()
except Exception:
    # Do not allow the guard to raise during import; any failure must be a
    # no-op so test harness / startup is not blocked.
    try:
        m = _mod()
        if m is not None:
            m.portfolio.setdefault("state_persistence_contract_import_error", "install_failed")
    except Exception:
        pass
