from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

# Focused, single-responsibility bidirectional accounting reconstructor used by
# deterministic cross-checks in legacy migration and diagnostics tests.
# Safety boundaries: paper-only analysis, never performs live orders or mutates
# canonical history. This module intentionally avoids touching persistence or
# runtime risk controls.

# Tolerances
# QTY_TOLERANCE: used for numeric comparisons while applying executions and for
# exit-overrun detection (existing exit-exceeds-position behavior remains
# unchanged).
QTY_TOLERANCE = 5e-6
# STATE_TRADE_QTY_SERIALIZATION_TOLERANCE: only used at final reconstructed-open
# position classification to forgive tiny serialization residues (e.g. 1e-6)
# so micro-terminal residues do not create phantom open lots.
STATE_TRADE_QTY_SERIALIZATION_TOLERANCE = 1e-6


def _f(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        num = float(value)
        return num if math.isfinite(num) else None
    except (TypeError, ValueError):
        return None


def analyze_ledger(portfolio: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    """
    Reconstruct positions from the in-memory trade list found in portfolio['trades'].

    Returns a dict with keys including:
    - status: 'ok' if no reconstruction coverage issues, otherwise 'fail'
    - coverage_issues: list of dicts describing mismatches (e.g. exit_exceeds_reconstructed_position)
    - economic_issues: empty list here for compatibility with callers
    - open_positions: dict of reconstructed open positions (symbols -> qty/side)
    - reconstructed_open_positions: list of symbol strings (upper-case)
    - reconstructed_cash: None (placeholder)
    - reconstructed_equity: None (placeholder)

    Important behavior:
    - When applying exits, comparisons that detect "exit exceeds available"
      use QTY_TOLERANCE (5e-6) to preserve previous/established behavior.
    - Only at the final step, when deciding whether a tiny remaining qty should
      be considered an actual open position, we apply
      STATE_TRADE_QTY_SERIALIZATION_TOLERANCE (1e-6). This prevents a 1e-6
      terminal residue from becoming a phantom open lot, while preserving
      exit-overrun semantics.
    """
    trades = [t for t in (portfolio.get("trades") or []) if isinstance(t, dict)]
    books: Dict[str, Dict[str, float]] = {}
    coverage_issues: List[Dict[str, Any]] = []
    economic_issues: List[Dict[str, Any]] = []

    for idx, row in enumerate(trades):
        action = str(row.get("action") or "").lower().strip()
        symbol = str(row.get("symbol") or "").upper().strip()
        side = str(row.get("side") or "long").lower().strip()
        qty = _f(row.get("shares") or row.get("qty"))
        price = _f(row.get("price"))
        execution_id = str(row.get("execution_id") or "")

        if not action or not symbol or qty is None or qty <= 0:
            # ignore malformed rows for this lightweight analyzer
            continue

        if action == "entry":
            existing = books.get(symbol)
            if existing and float(existing.get("qty", 0.0)) > QTY_TOLERANCE:
                coverage_issues.append({
                    "reason": "entry_against_open_position",
                    "symbol": symbol,
                    "execution_id": execution_id,
                    "existing_qty": float(existing.get("qty", 0.0)),
                    "requested_qty": qty,
                })
                # still record the new entry as a separate lot by replacing --
                # this mimics the conservative behavior of not silently merging
            books[symbol] = {"side": side, "qty": qty, "entry_price": price}
            continue

        # Exits / partial_exit
        if action in {"exit", "partial_exit"}:
            pos = books.get(symbol)
            if not pos or float(pos.get("qty", 0.0)) <= 0:
                coverage_issues.append({
                    "reason": "exit_without_open_position",
                    "symbol": symbol,
                    "execution_id": execution_id,
                    "requested_qty": qty,
                    "price": price,
                })
                # nothing to consume
                continue

            available = float(pos.get("qty", 0.0))
            # Preserve exit-overrun detection semantics: compare requested qty to
            # available using the coarser QTY_TOLERANCE. This preserves tests that
            # expect an exit exceeding the open by more than 5e-6 to be flagged.
            if qty > available + QTY_TOLERANCE:
                coverage_issues.append({
                    "reason": "exit_exceeds_reconstructed_position",
                    "symbol": symbol,
                    "execution_id": execution_id,
                    "requested_qty": qty,
                    "available_qty": available,
                    "price": price,
                    "action": action,
                })
            # Only consume up to available (do not create negative positions);
            # this matches conservative reconstruction semantics.
            used = min(qty, available)
            remaining = available - used
            if remaining <= QTY_TOLERANCE:
                # If remaining is tiny (<= QTY_TOLERANCE) during sequential
                # application we remove the book entry here. Final classification
                # uses a stricter serialization tolerance to avoid phantom lots
                # from on-disk rounding.
                books.pop(symbol, None)
            else:
                pos["qty"] = remaining
                books[symbol] = pos
            continue

        # ignore unsupported actions
        continue

    # After applying all executions, decide which remaining books count as
    # reconstructed open positions. Use the serialization tolerance only here so
    # tiny terminal residues (e.g. exactly 1e-6) are forgiven and do not become
    # phantom open lots.
    open_positions: Dict[str, Dict[str, Any]] = {}
    reconstructed_open_positions: List[str] = []
    for symbol, pos in sorted(books.items()):
        qty = float(pos.get("qty", 0.0))
        if qty <= STATE_TRADE_QTY_SERIALIZATION_TOLERANCE:
            # treat as closed due to serialization residue
            continue
        # Otherwise, include as open
        open_positions[symbol] = {"qty": qty, "side": pos.get("side"), "entry_price": pos.get("entry_price")}
        reconstructed_open_positions.append(symbol)

    status = "ok" if not coverage_issues and not reconstructed_open_positions else "fail"
    result = {
        "status": status,
        "coverage_issues": coverage_issues,
        "economic_issues": economic_issues,
        "open_positions": open_positions,
        "reconstructed_open_positions": reconstructed_open_positions,
        # placeholders kept for compatibility with older callers
        "reconstructed_cash": None,
        "reconstructed_equity": None,
    }
    return result
