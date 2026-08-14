"""Paper-only forensic diagnostic: intraday-peak validation from independent evidence.

This module is read-only and reporting-only. It inspects a supplied portfolio
(dict-like) and a sequence of current-epoch execution/trade rows (list of dicts)
and attempts to compute a candidate supportable intraday equity peak using
only independently supportable evidence supplied to it (trade-level equity or
realized pnl snapshots). It never mutates the inputs.

Behavior summary required by the handoff:
- Accept the canonical production shape where risk state may be nested at
  portfolio['risk_controls'] (but operate generically if fields are in other
  well-known locations).
- Report stored day_start_equity, stored day_peak_equity, current_equity, and
  a calculated intraday drawdown derived from stored_day_peak_equity.
- Inspect actual provided trades and identify the UCTT entry 93.22 ->
  partial_exit 337.54 -> final exit 94.025 pattern (or similar implausible
  partial-exit spikes) as unsupported/implausible peak evidence and exclude
  such suspect rows from candidate peak computation.
- MUST NOT use stored_day_peak_equity as evidence for the candidate corrected
  peak. Candidate peaks are computed only from per-trade evidence (trade
  'equity' fields or cumulative realized pnl computed from 'pnl_dollars'
  snapshots plus a supplied day_start_equity).
- Report whether the configured hard intraday drawdown threshold (default
  2.5%) would still be exceeded under the candidate supportable peak.
- If independently supportable peak evidence is insufficient, return
  candidate_supportable_peak_equity = 'insufficient_evidence'.

This file intentionally contains no runtime registration (no Flask routes).
Unit tests call its functions directly.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple


def _safe_get_portfolio_field(pf: Dict[str, Any], *keys: str) -> Optional[float]:
    """Try a few possible locations for common numeric portfolio fields.

    Returns None if no numeric value is found.
    """
    for k in keys:
        v = pf.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    # support nested risk_controls: portfolio['risk_controls']['day_start_equity']
    rc = pf.get("risk_controls") or pf.get("risk")
    if isinstance(rc, dict):
        for k in keys:
            v = rc.get(k)
            if isinstance(v, (int, float)):
                return float(v)
    # support portfolio wrapped under a top-level 'portfolio' key
    top = pf.get("portfolio")
    if isinstance(top, dict):
        return _safe_get_portfolio_field(top, *keys)
    return None


def _looks_like_trade(row: Any) -> bool:
    return isinstance(row, dict) and bool(row.get("symbol"))


def _identify_suspect_spikes(trades: List[Dict[str, Any]]) -> List[int]:
    """Identify indices of trades that look like implausible high spikes.

    Heuristic:
    - Look for sequences for the same symbol in order: entry -> partial_exit -> exit
    - If the partial_exit price (or trade equity) is dramatically larger than
      both entry and exit values (we use a factor threshold of 2x), mark the
      partial_exit as suspect.

    Returns a list of indices into the provided trades list that are suspect.
    """
    suspects: List[int] = []
    # Group indices by symbol preserving order
    symbol_indices: Dict[str, List[int]] = {}
    for idx, row in enumerate(trades):
        if not _looks_like_trade(row):
            continue
        sym = str(row.get("symbol") or "").upper()
        symbol_indices.setdefault(sym, []).append(idx)

    for sym, idxs in symbol_indices.items():
        # walk sequences of three (entry, partial_exit, exit) in chronological order
        for i in range(len(idxs) - 2):
            e_idx, p_idx, x_idx = idxs[i], idxs[i + 1], idxs[i + 2]
            e = trades[e_idx]
            p = trades[p_idx]
            x = trades[x_idx]
            if (str(e.get("action", "")).lower() != "entry"):
                continue
            if (str(p.get("action", "")).lower() not in {"partial_exit", "partial"}):
                continue
            if (str(x.get("action", "")).lower() not in {"exit", "final_exit", "rotation"}):
                continue
            # collect numeric comparators
            def _num(v: Any) -> Optional[float]:
                try:
                    return float(v)
                except Exception:
                    return None
            e_price = _num(e.get("price"))
            p_price = _num(p.get("price"))
            x_price = _num(x.get("price"))
            e_equity = _num(e.get("equity"))
            p_equity = _num(p.get("equity"))
            x_equity = _num(x.get("equity"))
            # If price-based evidence present, use it. Otherwise fall back to equity.
            if p_price is not None and ((e_price is not None) or (x_price is not None)):
                baseline = max(v for v in (e_price, x_price) if v is not None)
                if baseline > 0 and p_price >= baseline * 2.0:
                    suspects.append(p_idx)
                    continue
            if p_equity is not None and ((e_equity is not None) or (x_equity is not None)):
                baseline = max(v for v in (e_equity, x_equity) if v is not None)
                if baseline > 0 and p_equity >= baseline * 2.0:
                    suspects.append(p_idx)
                    continue
            # specific hard-pattern detection for the known UCTT numbers: 93.22->337.54->94.025
            if (e_price is not None and p_price is not None and x_price is not None):
                if round(e_price, 3) == 93.22 and round(p_price, 3) == 337.54 and round(x_price, 3) == 94.025:
                    suspects.append(p_idx)
                    continue
    # unique
    return sorted(set(suspects))


def _compute_candidate_peak_from_trades(trades: List[Dict[str, Any]], suspect_indices: List[int], day_start_equity: Optional[float]) -> Tuple[Optional[float], str]:
    """Compute a candidate peak equity from trades only (no use of stored peak).

    Strategy (in decreasing priority):
    1) If any trade rows contain numeric 'equity' values, use the max equity among
       those rows excluding suspect indices.
    2) Else, if trades include 'pnl_dollars' (realized) snapshots and day_start_equity
       is available, compute running cumulative realized pnl in chronological order
       and use the max derived equity value excluding suspect rows' pnl contributions.
    3) Otherwise return (None, 'insufficient_evidence').
    """
    # 1) equity field evidence
    equities: List[float] = []
    for idx, row in enumerate(trades):
        if idx in suspect_indices:
            continue
        v = row.get("equity")
        if isinstance(v, (int, float)):
            equities.append(float(v))
    if equities:
        return max(equities), "derived_from_trade_equity" 

    # 2) cumulative realized pnl
    if day_start_equity is None:
        return None, "insufficient_evidence"
    cumulative = 0.0
    max_equity = float(day_start_equity)
    seen_any = False
    for idx, row in enumerate(trades):
        if idx in suspect_indices:
            # skip suspect trades entirely (do not add their pnl)
            continue
        v = row.get("pnl_dollars")
        if isinstance(v, (int, float)):
            seen_any = True
            cumulative += float(v)
            cand = float(day_start_equity) + cumulative
            if cand > max_equity:
                max_equity = cand
    if seen_any:
        return max_equity, "derived_from_cumulative_realized_pnl"
    return None, "insufficient_evidence"


def analyze_portfolio_forensic(portfolio: Dict[str, Any], trades: List[Dict[str, Any]], intraday_threshold_pct: Optional[float] = None) -> Dict[str, Any]:
    """Main forensic analysis entrypoint.

    Inputs are not mutated. Returns a dictionary with diagnostic fields.
    """
    # operate on shallow copies for safety in our logic (but do not mutate inputs)
    pf = portfolio if isinstance(portfolio, dict) else {}
    tr = list(trades) if isinstance(trades, list) else []

    # gather stored values from common locations
    stored_day_start_equity = _safe_get_portfolio_field(pf, "day_start_equity", "start_of_day_equity", "day_start")
    stored_day_peak_equity = _safe_get_portfolio_field(pf, "day_peak_equity", "peak")
    current_equity = _safe_get_portfolio_field(pf, "equity", "current_equity", "cash_equity")

    # intraday threshold: prefer provided argument, else try to read from risk_controls
    threshold = intraday_threshold_pct
    if threshold is None:
        rc = (pf.get("risk_controls") or {}).get("intraday_drawdown_pct") if isinstance(pf.get("risk_controls"), dict) else None
        if isinstance(rc, (int, float)):
            threshold = float(rc)
    if threshold is None:
        threshold = 0.025  # default hard stop as required by project handoff

    # calculate intraday drawdown using stored_peak if present
    calculated_intraday_drawdown_pct = None
    threshold_exceeded_under_stored_peak = None
    if stored_day_peak_equity is not None and current_equity is not None and stored_day_peak_equity > 0:
        calculated_intraday_drawdown_pct = (float(stored_day_peak_equity) - float(current_equity)) / float(stored_day_peak_equity)
        threshold_exceeded_under_stored_peak = calculated_intraday_drawdown_pct > float(threshold)

    # identify suspect spike rows from provided trades
    suspect_indices = _identify_suspect_spikes(tr)

    # compute candidate peak from trades only (never uses stored_day_peak_equity)
    candidate_peak, candidate_method = _compute_candidate_peak_from_trades(tr, suspect_indices, stored_day_start_equity)

    candidate_intraday_drawdown_pct = None
    threshold_exceeded_under_candidate = None
    if candidate_peak is not None and current_equity is not None and candidate_peak > 0:
        candidate_intraday_drawdown_pct = (float(candidate_peak) - float(current_equity)) / float(candidate_peak)
        threshold_exceeded_under_candidate = candidate_intraday_drawdown_pct > float(threshold)

    result: Dict[str, Any] = {
        "stored_day_start_equity": stored_day_start_equity,
        "stored_day_peak_equity": stored_day_peak_equity,
        "current_equity": current_equity,
        "calculated_intraday_drawdown_pct": calculated_intraday_drawdown_pct,
        "intraday_threshold_pct": float(threshold),
        "threshold_exceeded_under_stored_peak": threshold_exceeded_under_stored_peak,
        "candidate_supportable_peak_equity": candidate_peak if candidate_peak is not None else "insufficient_evidence",
        "candidate_supportable_peak_method": candidate_method if candidate_peak is not None else "insufficient_evidence",
        "candidate_intraday_drawdown_pct": candidate_intraday_drawdown_pct,
        "threshold_exceeded_under_candidate": threshold_exceeded_under_candidate,
        "suspect_trade_indices": suspect_indices,
        "notes": (
            "candidate computed only from supplied trade evidence; stored_day_peak_equity was NOT used "
            "to support candidate. If candidate_supportable_peak_equity == 'insufficient_evidence', "
            "no corrective peak could be independently derived from the provided trades."
        ),
    }
    return result


__all__ = ["analyze_portfolio_forensic"]
