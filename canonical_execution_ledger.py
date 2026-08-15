"""Canonical execution ledger wrapper with prospective duplicate full-exit guard.

This module provides a minimal, production-shaped apply(core, row) entrypoint
that emulates the documented canonical append-before-mirror behavior while
adding a fail-closed guard to block a second full exit for the same
symbol/side when the authoritative canonical rows already show the net open
quantity as closed (<= epsilon) and at least one canonical entry exists.

Guard rules (conservative / fail-closed):
- Only applies when the candidate row is an exit (action in exit tokens).
- Reads the authoritative canonical JSONL file (env CANONICAL_EXECUTION_JSONL or
  STATE_DIR/canonical_executions.jsonl) and computes canonical net open qty for
  the same symbol + side across all canonical rows in the file.
- If canonical_entries_count >= 1 and canonical_net_open_qty <= EPSILON,
  the candidate exit is blocked: no mutation of account state, no canonical
  append, and a diagnostic marker is emitted to core.portfolio without
  deleting/replacing historical rows.
- If no canonical entry exists for that symbol/side, do NOT infer closure (do
  not block).

This file intentionally keeps a small, well-documented surface so it can be
reviewed/rolled-back easily. It does not grant any live authority or alter risk
controls. It only implements a narrowly-scoped prospective fail-closed guard.
"""
from __future__ import annotations

import os
import json
import typing as t

VERSION = "canonical-execution-guard-2026-08-15-v1"
EPSILON = float(os.environ.get("CANONICAL_DUPLICATE_EXIT_EPSILON", "1e-6"))


def _canonical_path() -> str:
    # Default canonical execution JSONL location. This mirrors production-style
    # placement under a persistent STATE_DIR when available.
    env = os.environ.get("CANONICAL_EXECUTION_JSONL")
    if env:
        return env
    state_dir = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if state_dir:
        return os.path.join(state_dir, "canonical_executions.jsonl")
    return os.path.join(os.getcwd(), "canonical_executions.jsonl")


def _read_canonical_rows(path: str) -> t.List[t.Dict[str, t.Any]]:
    out: t.List[t.Dict[str, t.Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        out.append(row)
                except Exception:
                    # Skip malformed lines; do not fail the guard (be conservative).
                    continue
    except FileNotFoundError:
        return []
    except Exception:
        return []
    return out


def _is_exit_action(row: t.Dict[str, t.Any]) -> bool:
    action = str(row.get("action") or row.get("type") or "").lower()
    if action in {"exit", "sell", "close", "cover"}:
        return True
    # Some canonical rows may use other hints; interpret presence of realized pnl
    # as an exit marker.
    if row.get("realized_pnl") is not None or row.get("pnl_dollars") is not None:
        return True
    return False


def _is_entry_action(row: t.Dict[str, t.Any]) -> bool:
    action = str(row.get("action") or row.get("type") or "").lower()
    if action in {"entry", "buy", "open", "entered"}:
        return True
    # Fallback: positive shares without realized pnl -> likely an entry
    try:
        shares = float(row.get("shares") or row.get("size") or 0.0)
        if shares > 0 and row.get("realized_pnl") is None and row.get("pnl_dollars") is None:
            return True
    except Exception:
        pass
    return False


def _net_open_for_symbol_side(rows: t.Iterable[t.Dict[str, t.Any]], symbol: str, side: str) -> t.Tuple[float, int]:
    """Compute (net_open_qty, entry_count) for canonical rows of symbol+side.

    entry_count is the number of canonical entry rows found for this symbol+side.
    net_open_qty is entries_sum - exits_sum (shares units)."""
    net = 0.0
    entry_count = 0
    for r in rows:
        try:
            rsym = str(r.get("symbol") or r.get("ticker") or "").upper().strip()
            rside = str(r.get("side") or r.get("direction") or "long").lower().strip()
            if rsym != symbol or rside != side:
                continue
            shares = float(r.get("shares") or r.get("size") or 0.0)
            if shares == 0:
                continue
            if _is_entry_action(r):
                net += abs(shares)
                entry_count += 1
            elif _is_exit_action(r):
                net -= abs(shares)
        except Exception:
            continue
    return net, entry_count


def _emit_diagnostic(core: t.Any, symbol: str, side: str, candidate: t.Dict[str, t.Any]) -> None:
    try:
        portfolio = getattr(core, "portfolio", None)
        if not isinstance(portfolio, dict):
            return
        diag = portfolio.setdefault("diagnostics", {})
        blocked = diag.setdefault("blocked_duplicate_full_exits", [])
        blocked.append({
            "version": VERSION,
            "symbol": symbol,
            "side": side,
            "candidate_execution_id": candidate.get("execution_id"),
            "candidate_price": candidate.get("price") or candidate.get("trade_price"),
            "note": "blocked prospective duplicate full exit because canonical net open qty <= epsilon and canonical entry exists",
        })
    except Exception:
        pass


def apply(core: t.Any, candidate_row: t.Dict[str, t.Any]) -> t.Dict[str, t.Any]:
    """Apply a canonical execution row with a duplicate-exit guard.

    Returns a small status dict. Do not mutate account state if the guard blocks.
    """
    try:
        symbol = str(candidate_row.get("symbol") or candidate_row.get("ticker") or "").upper().strip()
        side = str(candidate_row.get("side") or candidate_row.get("direction") or "long").lower().strip() or "long"
        # Only consider exit candidates for this guard. Non-exits proceed normally.
        if not _is_exit_action(candidate_row):
            # Append canonical row then mirror via core.record_trade when available.
            path = _canonical_path()
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
            except Exception:
                pass
            try:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(candidate_row, default=str) + "\n")
            except Exception:
                # Fall through; we still try to call the mirror.
                pass
            try:
                if hasattr(core, "record_trade") and callable(core.record_trade):
                    core.record_trade(candidate_row)
            except Exception:
                pass
            return {"status": "appended_and_mirrored"}

        # For exit candidates, consult canonical JSONL authoritative rows.
        path = _canonical_path()
        rows = _read_canonical_rows(path)
        net, entry_count = _net_open_for_symbol_side(rows, symbol, side)
        # If canonical ledger already contains at least one entry for this symbol/side
        # and the canonical net open quantity is already <= EPSILON, then this
        # candidate exit is a duplicate/stale attempt and must be blocked here
        # BEFORE any mutation of cash/P&L/positions/ledger.
        if entry_count >= 1 and net <= EPSILON:
            _emit_diagnostic(core, symbol, side, candidate_row)
            # Do NOT append the canonical row, do NOT call the mirror.
            return {"status": "blocked_duplicate_full_exit", "reason": "canonical_net_closed", "symbol": symbol, "side": side}

        # Otherwise safe to append canonical row and mirror it into state.
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            pass
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(candidate_row, default=str) + "\n")
        except Exception:
            pass
        try:
            if hasattr(core, "record_trade") and callable(core.record_trade):
                core.record_trade(candidate_row)
        except Exception:
            pass
        return {"status": "appended_and_mirrored"}
    except Exception as e:
        # Fail-closed: if anything unexpected happens, emit a diagnostic but do not
        # proceed with a potentially duplicative mutation. This is conservative.
        try:
            _emit_diagnostic(core, str(candidate_row.get("symbol") or ""), str(candidate_row.get("side") or ""), candidate_row)
        except Exception:
            pass
        return {"status": "error_blocked", "error": str(e)}
