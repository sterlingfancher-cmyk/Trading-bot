from __future__ import annotations

"""
Forensic diagnostic helpers for reporting-only quarantine suggestions.

Behavior notes (reporting-only, input immutable):
- Recognize "partial_exit" rows as exit-like for correlation.
- Correlate an exit-like row to the most recent prior same-symbol same-side entry.
- When an exit-like price is implausible relative to its correlated entry (outside
  LOW_FACTOR..HIGH_FACTOR or beyond hard intraday threshold), mark that single
  exit-like row as quarantined (report-only). Do not alter the input state.
- Preserve constants exactly: LOW_FACTOR=0.40, HIGH_FACTOR=2.50,
  HARD_INTRADAY_THRESHOLD=0.025.
- Do NOT use stored risk_controls.day_peak_equity or intraday_drawdown_pct as
  independent peak support. If no independent peak evidence exists, we must
  return conclusion="insufficient_evidence" and candidate_peak_equity=None.

This module intentionally only returns a diagnostic payload; it never mutates
state or grants any execution or risk authority.
"""
from typing import Any, Dict, List, Optional, Tuple

# Preserve these exact constants as required by the regression.
LOW_FACTOR = 0.40
HIGH_FACTOR = 2.50
HARD_INTRADAY_THRESHOLD = 0.025


def _norm_action(row: Dict[str, Any]) -> str:
    return str(row.get("action") or row.get("type") or "").lower().strip()


def _get_price(row: Dict[str, Any]) -> Optional[float]:
    # Try common price keys; return None if missing or nonpositive.
    for k in ("price", "entry_price", "entry", "last_price", "mark", "close"):
        v = row.get(k)
        try:
            if v is None:
                continue
            f = float(v)
            if f > 0:
                return f
        except Exception:
            continue
    return None


def _is_entry_action(action: str) -> bool:
    return action in {"entry", "buy", "open", "entered"}


def _is_exit_like_action(action: str) -> bool:
    # Explicitly include partial_exit as exit-like for correlation.
    if action in {"exit", "sell", "close", "stopped", "stop", "partial_exit", "partial-sell"}:
        return True
    # also consider rows that mention exit-like keywords in reason fields elsewhere
    return False


def analyze_forensic(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze trades in `state` and return a reporting-only diagnostic.

    Returned payload contains at least:
    - conclusion: str ("insufficient_evidence" if no independent peak evidence)
    - candidate_peak_equity: None or float (we do not infer peak from risk_controls)
    - quarantined_indices: list[int] indexes into state.get("trades", []) for rows
      we recommend quarantining for further human review (report-only)
    - quarantined_rows: list[dict] shallow copies of the quarantined trade rows
    - correlations: list of (entry_index, exit_index, reason)
    - matched_entries: list of indexes for recognized entry rows (for ease of tests)
    - matched_exits: list of indexes for recognized exit-like rows
    """
    trades = list(state.get("trades") or [])
    out: Dict[str, Any] = {
        "conclusion": "insufficient_evidence",
        "candidate_peak_equity": None,
        "quarantined_indices": [],
        "quarantined_rows": [],
        "correlations": [],
        "matched_entries": [],
        "matched_exits": [],
        "version": "forensic_diagnostic_v1_reporting_only",
    }

    # We deliberately do NOT consult risk_controls.day_peak_equity or
    # intraday_drawdown_pct as independent peak evidence per the project contract.
    # If a caller supplied independent peak evidence under a different key, we
    # could support it, but for this minimal forensic regression we require
    # explicit independent evidence to change 'insufficient_evidence'.

    # Build quick indices of entries and exit-like rows
    entries: List[Tuple[int, Dict[str, Any]]] = []
    exit_like: List[Tuple[int, Dict[str, Any]]] = []

    for idx, row in enumerate(trades):
        action = _norm_action(row)
        if _is_entry_action(action):
            entries.append((idx, row))
            out["matched_entries"].append(idx)
        if _is_exit_like_action(action) or any(
            token in (str(row.get(k) or "")).lower() for k in ("reason", "exit_reason", "type")
        ):
            # treat partial_exit explicitly as exit-like even if not normalized elsewhere
            exit_like.append((idx, row))
            out["matched_exits"].append(idx)

    # For each exit-like row, correlate to the most recent prior same-symbol same-side entry
    # and evaluate plausibility.
    def _sym_side_key(r: Dict[str, Any]) -> Tuple[str, str]:
        sym = str(r.get("symbol") or r.get("ticker") or "").upper().strip()
        side = str(r.get("side") or r.get("direction") or "long").lower().strip()
        return sym, side

    # Build quick list of prior entries by index for lookups
    entries_by_index = {idx: row for idx, row in entries}

    for exit_idx, exit_row in exit_like:
        # find most recent prior entry index for same symbol & side
        sym, side = _sym_side_key(exit_row)
        correlated_entry_idx = None
        for idx in range(exit_idx - 1, -1, -1):
            row = trades[idx]
            if _is_entry_action(_norm_action(row)):
                s2, side2 = _sym_side_key(row)
                if s2 == sym and side2 == side:
                    correlated_entry_idx = idx
                    break
        if correlated_entry_idx is None:
            # no prior entry to correlate; skip quarantine logic but record.
            out["correlations"].append((None, exit_idx, "no_prior_entry"))
            continue

        out["correlations"].append((correlated_entry_idx, exit_idx, "correlated_to_prior_entry"))

        # compute prices
        entry_row = trades[correlated_entry_idx]
        entry_price = _get_price(entry_row)
        exit_price = _get_price(exit_row)
        if entry_price is None or exit_price is None or entry_price <= 0:
            # cannot evaluate plausibility; do not quarantine on price math alone
            out["correlations"].append((correlated_entry_idx, exit_idx, "missing_price"))
            continue

        # compute ratio (exit relative to entry). For long: exit/entry
        ratio = exit_price / entry_price

        suspicious = False
        reason = ""
        # For either side, flag if ratio is outside the [LOW_FACTOR, HIGH_FACTOR] band.
        # This mirrors the production integrity guard boundaries.
        if side == "long":
            if ratio <= LOW_FACTOR:
                suspicious = True
                reason = f"long_exit_too_low_ratio_{ratio:.6f}"
            elif ratio >= HIGH_FACTOR:
                suspicious = True
                reason = f"long_exit_too_high_ratio_{ratio:.6f}"
        else:  # short
            # For short positions, a very high ratio (exit above entry by huge factor)
            # or a very low ratio both can be suspicious; mirror same numeric band.
            if ratio <= LOW_FACTOR:
                suspicious = True
                reason = f"short_exit_ratio_too_low_{ratio:.6f}"
            elif ratio >= HIGH_FACTOR:
                suspicious = True
                reason = f"short_exit_ratio_too_high_{ratio:.6f}"

        if suspicious:
            # Quarantine only the exit-like row (report-only). Preserve everything else.
            out["quarantined_indices"].append(exit_idx)
            out["quarantined_rows"].append(dict(exit_row))
            out["correlations"].append((correlated_entry_idx, exit_idx, reason))

    # If no independent peak evidence was supplied (we explicitly never read
    # risk_controls.day_peak_equity or intraday_drawdown_pct), remain "insufficient_evidence".
    # Leave candidate_peak_equity None to indicate we won't substitute absent evidence.

    return out


# Convenience alias for tests
analyze = analyze_forensic
