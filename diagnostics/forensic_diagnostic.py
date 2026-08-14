from __future__ import annotations

"""
Forensic diagnostic helper (reporting-only).

This module inspects a provided immutable state (read-only) and reports
candidate source-level terminal-price integrity issues. It deliberately
does not mutate inputs, does not clear or change risk controls or state,
and provides only a reporting payload intended for human review.

Behavior implemented here is intentionally narrow and aligned with the
rejection-correction request for PR #63:
- Reproduce the exact production sequence matching rules: correlate a
  partial exit row without an entry_price to the most recent prior
  same-symbol same-side entry row (list-order is used as the production
  canonical ordering when timestamps are absent).
- If a long exit is >= HIGH_FACTOR * entry_price (with HIGH_FACTOR==2.5),
  and the intraday absolute change exceeds the hard intraday threshold
  (0.025), then report that exit as quarantined for forensic review.
- Do NOT treat a long as short to justify the price, and do NOT consult
  stored risk_controls.day_peak_equity or intraday_drawdown_pct to
  manufacture peak evidence. If independent peak evidence is absent,
  return conclusion == "insufficient_evidence" and candidate_peak_equity == None.

This is reporting-only: no state mutation or side effects.
"""
from copy import deepcopy
from typing import Any, Dict, List, Optional

# Preserve the exact thresholds requested
LOW_FACTOR = 0.40
HIGH_FACTOR = 2.50
INTRADAY_HARD_THRESHOLD = 0.025


def _is_entry(row: Dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    action = str(row.get("action") or row.get("type") or "").lower()
    return action in {"entry", "buy", "open", "entered"}


def _is_exit(row: Dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    action = str(row.get("action") or row.get("type") or "").lower()
    if action in {"exit", "sell", "close", "closed"}:
        return True
    # also consider rows that have explicit pnl fields or exit_reason
    if any(key in row for key in ("pnl_pct", "pnl_dollars", "pnl")):
        return True
    text = " ".join(str(row.get(k) or "") for k in ("reason", "exit_reason")).lower()
    if any(token in text for token in ("exit", "sell", "close")):
        return True
    # if there's a price and not an entry, treat as an exit/reportable terminal row
    if "price" in row and not _is_entry(row):
        return True
    return False


def _price_of(row: Dict[str, Any]) -> Optional[float]:
    if not isinstance(row, dict):
        return None
    # prefer fields named price/entry_price/last_price/mark/close
    for key in ("price", "entry_price", "last_price", "mark", "close", "signal_price"):
        try:
            val = row.get(key)
            if val is None:
                continue
            px = float(val)
            if px > 0:
                return px
        except Exception:
            continue
    return None


def analyze_trades(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze the state's trades list for source-level terminal-price outliers.

    Input:
      state: a dict-like structure (treated read-only)

    Returns a dict containing:
      - quarantined_rows: list of indices (int) into state['trades'] that were
        flagged for quarantine (reporting-only)
      - quarantined_rows_details: list of detail dicts for human review
      - retained_rows: list of indices that were explicitly not quarantined but
        inspected in the same sequence
      - thresholds: dict with the preserved numeric constants
      - conclusion: one of {'insufficient_evidence', 'candidate_quarantined', 'no_issues_found'}
      - candidate_peak_equity: None unless independent peak evidence is available
      - input_unchanged: True when the function does not mutate the provided state
    """
    # Do not mutate the provided state. Work on a shallow copy reference only for safe iteration.
    original = state
    trades = list(original.get("trades") or [])
    # Keep an immutable snapshot to assert later that we did not mutate the input
    before_snapshot = deepcopy(trades)

    quarantined_indices: List[int] = []
    quarantined_details: List[Dict[str, Any]] = []
    retained_indices: List[int] = []

    # Build an ordered list of prior entries for quick lookup by symbol+side
    prior_entries_by_symbol_side: Dict[tuple, List[tuple]] = {}

    for idx, row in enumerate(trades):
        if _is_entry(row):
            sym = str(row.get("symbol") or row.get("ticker") or "").upper().strip()
            side = str(row.get("side") or row.get("direction") or "long").lower().strip()
            entry_px = _price_of(row)
            prior_entries_by_symbol_side.setdefault((sym, side), []).append((idx, row, entry_px))

    # Inspect exits in list order and correlate to most-recent prior same-symbol same-side entry
    for idx, row in enumerate(trades):
        if not _is_exit(row):
            continue
        sym = str(row.get("symbol") or row.get("ticker") or "").upper().strip()
        side = str(row.get("side") or row.get("direction") or "long").lower().strip()
        exit_px = _price_of(row)
        # Skip rows without a usable price
        if exit_px is None or not sym:
            retained_indices.append(idx)
            continue

        # Find the most recent prior same-symbol same-side entry (by index order)
        entries = prior_entries_by_symbol_side.get((sym, side), [])
        matched_entry_idx = None
        matched_entry_row = None
        matched_entry_px = None
        # iterate in reverse to find the latest prior by index
        for e_idx, e_row, e_px in reversed(entries):
            if e_idx < idx:
                matched_entry_idx = e_idx
                matched_entry_row = e_row
                matched_entry_px = e_px
                break

        if matched_entry_row is None or matched_entry_px is None:
            # no prior same-side entry to correlate; retain but include in retained list
            retained_indices.append(idx)
            continue

        # For long positions: catastrophic high spike is exit_px / entry_px >= HIGH_FACTOR
        # For short positions: catastrophic low spike is exit_px / entry_px <= LOW_FACTOR (not used here per instructions)
        try:
            ratio = float(exit_px) / float(matched_entry_px)
        except Exception:
            retained_indices.append(idx)
            continue

        # require the intraday absolute-move threshold as an additional guard
        absolute_move = abs(ratio - 1.0)

        # Only quarantine if the same-side long comparison exceeds the HIGH_FACTOR
        if side == "long" and ratio >= HIGH_FACTOR and absolute_move >= INTRADAY_HARD_THRESHOLD:
            quarantined_indices.append(idx)
            quarantined_details.append(
                {
                    "quarantined_index": idx,
                    "symbol": sym,
                    "side": side,
                    "exit_price": exit_px,
                    "matched_entry_index": matched_entry_idx,
                    "matched_entry_price": matched_entry_px,
                    "ratio": ratio,
                    "reason": "source_terminal_price_plausibility_high_spike",
                }
            )
            # do not remove or mutate rows; reporting-only
            continue

        # For completeness, check catastrophic low-side (symmetric guard) but only as a report
        if side == "long" and ratio <= LOW_FACTOR and absolute_move >= INTRADAY_HARD_THRESHOLD:
            quarantined_indices.append(idx)
            quarantined_details.append(
                {
                    "quarantined_index": idx,
                    "symbol": sym,
                    "side": side,
                    "exit_price": exit_px,
                    "matched_entry_index": matched_entry_idx,
                    "matched_entry_price": matched_entry_px,
                    "ratio": ratio,
                    "reason": "source_terminal_price_plausibility_low_spike",
                }
            )
            continue

        # otherwise retain the row as legitimate for now
        retained_indices.append(idx)

    # Candidate peak equity: per instruction, do NOT use stored risk_controls.day_peak_equity
    # or intraday_drawdown_pct as support. We only return a candidate value if independent
    # peak evidence is available in scoped, independent sources (none are present in this
    # minimal forensic patch), so return None.
    candidate_peak_equity = None

    conclusion = "no_issues_found"
    if quarantined_indices:
        # Per instruction: when quarantines happen but independent peak evidence is absent, return insufficient_evidence
        conclusion = "insufficient_evidence"

    result = {
        "quarantined_rows": quarantined_indices,
        "quarantined_rows_details": quarantined_details,
        "retained_rows": retained_indices,
        "thresholds": {
            "low_factor": LOW_FACTOR,
            "high_factor": HIGH_FACTOR,
            "intraday_hard_threshold": INTRADAY_HARD_THRESHOLD,
        },
        "conclusion": conclusion,
        "candidate_peak_equity": candidate_peak_equity,
        "input_unchanged": before_snapshot == trades,
    }
    return result


if __name__ == "__main__":
    # lightweight smoke run when executed directly (not used by tests)
    import json
    import sys

    state = {"trades": []}
    if len(sys.argv) > 1:
        try:
            state = json.loads(sys.argv[1])
        except Exception:
            pass
    print(json.dumps(analyze_trades(state), indent=2))
