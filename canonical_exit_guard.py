from __future__ import annotations

import errno
import json
import os
from typing import Any, Callable, Dict, Optional, Tuple

# Small, surgical duplicate-full-exit guard helper.
# This module intentionally does NOT change any canonical_execution_ledger behavior.
# It provides an installer that can wrap an existing exit_position-style callable
# to block a candidate full exit before any cash/P&L/position/ledger mutation when:
#  - the authoritative canonical ledger (JSONL) already contains at least one
#    canonical entry for the same symbol/side (i.e. this symbol has canonical history),
#  - and the canonical net open quantity for that symbol/side is already <= epsilon.
#
# The guard is conservative: if the canonical ledger contains no entry rows for the
# symbol/side it will not block (this prevents inferring that a verified-snapshot
# position without canonical history is closed).
#
# Install by calling canonical_exit_guard.install_into_module(module)
# where module.exit_position is the original function to wrap. The wrapper will
# attempt to extract (symbol, side) from kwargs or positional args in a robust way.

# Default ledger location fallback. The real runtime canonical module defines
# LEDGER_FILE; we try to detect it dynamically but fall back to this filename.
FALLBACK_LEDGER_FILE = os.environ.get("CANONICAL_LEDGER_FILE", "canonical_execution_ledger.jsonl")

# Small epsilon for float quantity comparisons.
DEFAULT_EPSILON = float(os.environ.get("DUP_EXIT_EPSILON", "1e-8"))


def _read_ledger_rows(path: str) -> list[dict]:
    rows: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    # ignore malformed lines rather than fail the guard
                    continue
    except IOError as e:
        if getattr(e, "errno", None) in (errno.ENOENT,):
            return []
        return []
    return rows


def _qty_from_row(row: dict) -> float:
    # Common keys observed across repository/testing fixtures
    for key in ("qty", "quantity", "size", "shares"):
        try:
            v = row.get(key)
            if v is None:
                continue
            return float(v)
        except Exception:
            continue
    # fallback: try numeric 'amount' or 'filled_qty'
    for key in ("amount", "filled_qty", "filled_qty"):
        try:
            v = row.get(key)
            if v is None:
                continue
            return float(v)
        except Exception:
            continue
    return 0.0


def _action_from_row(row: dict) -> str:
    return str(row.get("action") or row.get("type") or "").lower()


def _side_from_row(row: dict) -> str:
    return str(row.get("side") or row.get("direction") or "long").lower()


def _symbol_from_row(row: dict) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def compute_canonical_net_open(ledger_file: str, symbol: str, side: str) -> Tuple[float, int]:
    """
    Returns (net_open_qty, entry_count) where
      net_open_qty = sum(entries) - sum(exits)
      entry_count = count of canonical entry rows for this symbol/side

    If ledger_file missing or unreadable returns (0.0, 0)
    """
    rows = _read_ledger_rows(ledger_file)
    if not rows:
        return 0.0, 0
    symbol = (symbol or "").upper().strip()
    side = (side or "long").lower().strip() or "long"
    entries_sum = 0.0
    exits_sum = 0.0
    entry_count = 0
    for r in rows:
        try:
            r_sym = _symbol_from_row(r)
            if not r_sym or r_sym != symbol:
                continue
            r_side = _side_from_row(r)
            if r_side != side:
                continue
            act = _action_from_row(r)
            q = _qty_from_row(r) or 0.0
            if act in ("entry", "buy", "open"):
                entries_sum += q
                entry_count += 1
            elif act in ("exit", "sell", "close", "partial_exit", "partial"):
                exits_sum += q
            else:
                # ignore unknown actions
                continue
        except Exception:
            continue
    net = max(0.0, float(entries_sum - exits_sum))
    return net, entry_count


def _extract_symbol_side_from_call(args: tuple, kwargs: dict) -> Tuple[Optional[str], Optional[str]]:
    # Prefer explicit kwargs
    for key in ("symbol", "ticker", "s", "sym"):
        if key in kwargs:
            return (str(kwargs.get(key) or "").upper().strip(), str(kwargs.get("side") or "long").lower().strip() or "long")
    if "side" in kwargs:
        # symbol might be positional
        sym = None
        for a in args:
            if isinstance(a, str) and a.strip():
                sym = a
                break
        return (str(sym or "").upper().strip(), str(kwargs.get("side") or "long").lower().strip() or "long")

    # scan positional args for likely core and symbol
    sym = None
    side = None
    # If first positional is core (has portfolio), then try to pick the first string after it.
    start = 0
    if args:
        first = args[0]
        if hasattr(first, "portfolio") or hasattr(first, "save_state"):
            start = 1
    for a in args[start:]:
        if a is None:
            continue
        if isinstance(a, str) and a.strip():
            # treat as symbol candidate
            sym = a
            continue
        if isinstance(a, dict) and not sym:
            if "symbol" in a:
                sym = a.get("symbol")
            elif "ticker" in a:
                sym = a.get("ticker")
        if isinstance(a, (int, float)) and side is None:
            # numeric args likely qty/price, skip
            continue
    # try to find explicit side in any arg dict
    for a in args:
        if isinstance(a, dict) and "side" in a:
            side = a.get("side")
            break
    if not side:
        side = "long"
    if not sym:
        # last resort: check kwargs for any plausible symbol-like value
        for key in ("in", "out", "position"):
            v = kwargs.get(key)
            if isinstance(v, str) and v.strip():
                sym = v
                break
    return (str(sym or "").upper().strip() or None, str(side or "long").lower().strip() or None)


def install_into_module(target_module: Any, ledger_file: Optional[str] = None, epsilon: float = DEFAULT_EPSILON) -> Dict[str, Any]:
    """
    Wraps target_module.exit_position with the duplicate-full-exit guard.

    Returns metadata dict about installation.
    """
    if ledger_file is None:
        # try to detect canonical module LEDGER_FILE
        try:
            import canonical_execution_ledger as cel  # type: ignore
            ledger_file = getattr(cel, "LEDGER_FILE", FALLBACK_LEDGER_FILE)
        except Exception:
            ledger_file = FALLBACK_LEDGER_FILE

    if not hasattr(target_module, "exit_position") or not callable(getattr(target_module, "exit_position")):
        return {"status": "no_exit_position_to_patch"}

    original = getattr(target_module, "exit_position")

    def _wrapped(*args, **kwargs):
        # Determine symbol and side for the candidate exit
        try:
            symbol, side = _extract_symbol_side_from_call(args, kwargs)
        except Exception:
            symbol, side = (None, None)

        if symbol:
            try:
                net_open, entry_count = compute_canonical_net_open(ledger_file, symbol, side or "long")
                if entry_count >= 1 and float(net_open) <= float(epsilon):
                    # Block: emit diagnostic evidence into the target_module.portfolio (best-effort).
                    try:
                        portfolio = getattr(args[0], "portfolio", None) if args else getattr(target_module, "portfolio", None)
                        if isinstance(portfolio, dict):
                            audit = portfolio.setdefault("duplicate_exit_guard", {})
                            audit_entry = {
                                "status": "blocked_duplicate_full_exit",
                                "symbol": symbol,
                                "side": side,
                                "reason": "canonical_net_open_already_zero",
                                "ledger_file": ledger_file,
                                "net_open": net_open,
                                "entry_count": entry_count,
                            }
                            audit.setdefault("history", []).append(audit_entry)
                            # Also set a short top-level marker for runtime routes to see quickly
                            portfolio["duplicate_exit_guard_last"] = audit_entry
                    except Exception:
                        pass
                    # Fail closed: do not call original; return a diagnostic dict
                    return {"status": "blocked_duplicate_full_exit", "symbol": symbol, "side": side, "net_open": net_open, "entry_count": entry_count}
            except Exception:
                # on any ledger-read error, be conservative and allow (do not block)
                pass

        # Otherwise call original exit_position
        return original(*args, **kwargs)

    setattr(target_module, "exit_position", _wrapped)
    return {"status": "ok", "wrapped": True, "ledger_file": ledger_file}


# For convenience, expose compute helper at module level for direct test use
__all__ = [
    "install_into_module",
    "compute_canonical_net_open",
    "_read_ledger_rows",
]
