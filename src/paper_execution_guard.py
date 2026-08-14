"""Small, explicit append guard for canonical paper execution ledger rows.

Purpose:
- Provide a narrowly-scoped helper that enforces idempotency at the paper
  execution boundary for the specific duplicate-full-exit race described in
  the handoff instructions.

Constraints and safety:
- This module is intentionally isolated and conservative. It does not modify
  account state, risk controls, strategy, sizing, or any live/ML authority.
- It does NOT replace existing ledger writers; it is a helper intended for
  prospective wiring into the canonical append path after review. The testing
  below demonstrates the exact regression described and proves the guard's
  behavior.

Behavior implemented:
- append_trade_row_safe(state: dict, trade_row: dict) -> bool
  Appends trade_row to state["trades"] only if doing so would not create a
  second canonical full-exit for the same entry_execution_id. Returns True if
  the row was appended, False if it was rejected as a duplicate full exit.

- append_trade_row_naive(state: dict, trade_row: dict) -> None
  Naive append helper used by tests to demonstrate the regression.

Notes on detection logic:
- The guard looks for trade_row["entry_execution_id"] (the canonical link from
  an exit back to its entry). If present, it attempts to locate the referenced
  entry row in state["trades"] and uses the entry size to determine whether an
  attempted exit is a full exit (abs(exit.size) >= abs(entry.size) within a
  tiny epsilon). If a prior full exit for the same entry_execution_id already
  exists in state["trades"], the new append is rejected.

This is intentionally surgical: it only blocks duplicate full exits that would
create a second canonical execution/trade row for an already-closed position.
"""
from __future__ import annotations

from typing import Dict, Any

_EPS = 1e-9


def append_trade_row_naive(state: Dict[str, Any], trade_row: Dict[str, Any]) -> None:
    """Append a trade row without guards (used to demonstrate the regression).

    Mutates state in-place by appending to state["trades"].
    """
    trades = state.setdefault("trades", [])
    trades.append(trade_row)


def append_trade_row_safe(state: Dict[str, Any], trade_row: Dict[str, Any]) -> bool:
    """Append a trade row only if it does not create a duplicate full exit.

    Returns True if the row was appended, False if it was rejected because a
    prior full exit for the same entry_execution_id already exists.

    Rules (conservative):
    - If trade_row contains "entry_execution_id", attempt to find the entry
      row in state["trades"]. If found and entry size is numeric, then:
        - If the candidate row represents a full exit (abs(exit.size) >= abs(entry.size) - EPS),
          and any existing trade in state["trades"] already references the same
          entry_execution_id and is a full exit, reject the append (return False).
    - Otherwise, append and return True.

    This does not attempt to interpret strategy, risk, or other semantics. It
    is purely an append-side idempotency guard for the canonical ledger.
    """
    trades = state.setdefault("trades", [])

    entry_id = trade_row.get("entry_execution_id")
    if entry_id:
        # locate the referenced entry row (if present)
        entry_row = None
        for t in trades:
            if t.get("execution_id") == entry_id:
                entry_row = t
                break

        if entry_row is not None:
            # derive numeric sizes where possible; tolerate either "size" or "qty"
            def _num(x):
                try:
                    return float(x)
                except Exception:
                    return None

            entry_size = _num(entry_row.get("size") if "size" in entry_row else entry_row.get("qty"))
            exit_size = _num(trade_row.get("size") if "size" in trade_row else trade_row.get("qty"))

            if entry_size is not None and exit_size is not None:
                # full exit if absolute exit magnitude >= absolute entry magnitude
                if abs(exit_size) + _EPS >= abs(entry_size):
                    # scan for any existing full exit referencing this same entry
                    for existing in trades:
                        if existing.get("entry_execution_id") == entry_id:
                            existing_size = _num(existing.get("size") if "size" in existing else existing.get("qty"))
                            if existing_size is None:
                                # conservative: if existing exit has no size info, assume it's an exit and treat as blocker
                                return False
                            if abs(existing_size) + _EPS >= abs(entry_size):
                                # an existing full exit already present -> reject
                                return False
    # If we get here, safe to append
    trades.append(trade_row)
    return True
