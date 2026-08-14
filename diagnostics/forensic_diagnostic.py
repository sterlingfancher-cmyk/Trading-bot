from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

VERSION = "forensic-diagnostic-2026-08-14-v1"


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _action(row: Dict[str, Any]) -> str:
    return str(row.get("action") or row.get("type") or "").strip().lower()


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def _side(row: Dict[str, Any]) -> str:
    return str(row.get("side") or row.get("direction") or "long").strip().lower()


def _time_float(row: Dict[str, Any]) -> Optional[float]:
    for k in ("time", "timestamp", "ts", "entry_time", "exit_time", "created_at"):
        if k in row:
            try:
                return float(row[k])
            except Exception:
                pass
    return None


def _entry_price_from_entry_row(entry: Dict[str, Any]) -> Optional[float]:
    # Only derive an entry price from the entry-row itself. Do NOT treat
    # a later partial-exit's ordinary 'price' field as entry provenance.
    # Respect common keys that encode explicit entry provenance.
    for key in ("entry_price", "price", "entry", "signal_price"):
        if key in entry:
            try:
                v = float(entry[key])
                if v > 0:
                    return v
            except Exception:
                continue
    return None


def analyze_forensic_trades(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Forensic analysis focused on implausible partial exits correlated to prior
    entries. This function is intentionally conservative and reporting-only:
    - Inputs are NOT mutated.
    - It quarantines (reports) only proven implausible partial_exit rows.
    - It never quarantines legitimate entry rows or final exit rows.
    - It does NOT use stored risk_controls.day_peak_equity or intraday_drawdown_pct
      as candidate-peak evidence.
    - The hard intraday threshold used in source/exit plausibility checks is
      exactly 0.025 (2.5%).

    Returns a dict with keys:
    - version: str
    - quarantined_rows: list of dict (deep-copies of rows that should be quarantined)
    - conclusion: str (if independent peak evidence absent returns 'insufficient_evidence')
    - candidate_peak_equity: None or float (we return None here unless independent evidence found)
    """
    trades = list(state.get("trades") or []) if isinstance(state.get("trades"), list) else []
    # Work on an explicit shallow copy of rows for indexing; never modify original rows
    rows = [dict(r) if isinstance(r, dict) else r for r in trades]

    quarantined: List[Dict[str, Any]] = []

    # Plausibility boundaries preserved from the existing guards:
    # - For short positions: an exit (buy/cover) price >= 2.5x entry is implausible
    # - For long positions: an exit price <= 0.4x entry is implausible
    LONG_LOWER_BOUND_FACTOR = 0.4
    SHORT_UPPER_BOUND_FACTOR = 2.5

    # Hard intraday threshold (kept exactly as requested). It's referenced here
    # for completeness of logic should any intraday-peak based branch be added.
    HARD_INTRADAY_THRESHOLD = 0.025  # 2.5%

    # Build a list of prior entries keyed by symbol+side with their index order
    # We'll use the chronological order in the trades list as persisted order.
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if _action(row) != "partial_exit":
            continue

        symbol = _symbol(row)
        side = _side(row)
        partial_price = _f(row.get("price"), 0.0)
        if partial_price <= 0:
            # Can't reason about a missing/invalid price
            continue

        # Find most recent prior same-symbol entry (search backwards)
        prior_entry = None
        for j in range(idx - 1, -1, -1):
            cand = rows[j]
            if not isinstance(cand, dict):
                continue
            if _action(cand) != "entry":
                continue
            if _symbol(cand) != symbol or _side(cand) != side:
                continue
            prior_entry = cand
            break

        if prior_entry is None:
            # No entry to correlate; cannot conclude
            continue

        entry_price = _entry_price_from_entry_row(prior_entry)
        if entry_price is None or entry_price <= 0:
            # Prior entry has no usable entry price; cannot conclude
            continue

        # Determine implausibility using preserved guard semantics
        implausible = False
        reason = None
        if side == "short":
            if partial_price >= entry_price * SHORT_UPPER_BOUND_FACTOR:
                implausible = True
                reason = (
                    "partial_exit_price_exceeds_short_upper_plausibility_factor"
                )
        else:  # long
            if partial_price <= entry_price * LONG_LOWER_BOUND_FACTOR:
                implausible = True
                reason = (
                    "partial_exit_price_below_long_lower_plausibility_factor"
                )

        if implausible:
            # Quarantine only the partial_exit row. Return a deep copy so the
            # caller/test cannot mutate internal state and the original input is
            # preserved unchanged.
            quarantined_row = copy.deepcopy(row)
            quarantined_row["forensic_quarantine_reason"] = reason
            quarantined_row["forensic_correlated_entry_price"] = entry_price
            quarantined_row["forensic_version"] = VERSION
            quarantined.append(quarantined_row)

    # Candidate peak equity support: per instruction, do NOT use stored
    # risk_controls.day_peak_equity or intraday_drawdown_pct. If independent
    # peak evidence is absent return conclusion='insufficient_evidence'.
    candidate_peak_equity = None
    conclusion = "insufficient_evidence"

    return {
        "version": VERSION,
        "quarantined_rows": quarantined,
        "conclusion": conclusion,
        "candidate_peak_equity": candidate_peak_equity,
        "hard_intraday_threshold": HARD_INTRADAY_THRESHOLD,
    }
