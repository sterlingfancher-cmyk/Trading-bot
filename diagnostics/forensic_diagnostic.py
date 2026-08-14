from __future__ import annotations

"""
Forensic diagnostic reporting only. This module produces a deterministic, read-only
forensic conclusion about whether an intraday hard-drawdown halt (2.5%) can be
independently supported from non-stored evidence.

Key rules implemented here (reporting-only):
- Never treat stored portfolio['risk_controls']['day_peak_equity'] or
  stored intraday_drawdown_pct as evidence for reconstructing a candidate
  peak. They are considered provenance-only and are not used to build
  candidate_peak_equity.
- The hard intraday threshold is fixed at exactly 0.025 (2.5%) for all
  candidate evaluations in this module.
- Only quarantine the known implausible UCTT partial exit at price 337.54
  that references an entry at 93.22. The entry and normal exit are left
  as independent evidence.
- Candidate peak equity is built only from independent evidence attached to
  trades (explicit equity snapshots) and/or realized P&L progression derived
  from a provided day_start_equity plus non-quarantined realized pnl rows.
- If independent evidence is insufficient to form a candidate peak, the
  module returns conclusion='insufficient_evidence' and candidate_peak_equity
  == None with no claim about whether the halt is justified.

This module performs no writes, does not mutate inputs, and is strictly
reporting-only.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional
import math

HARD_INTRADAY_THRESHOLD = 0.025  # fixed 2.5% as required


def _is_known_implausible_partial(trade: Dict[str, Any]) -> bool:
    """Detect the single known implausible partial exit to quarantine.

    Known signature (production-like evidence): symbol 'UCTT', an exit/partial
    with price 337.54 and referencing an entry price of 93.22. This function is
    intentionally narrow and deterministic so only that exact row is
    quarantined.
    """
    try:
        sym = str(trade.get("symbol") or "").upper()
        act = str(trade.get("action") or trade.get("type") or "").lower()
        price = float(trade.get("price") or trade.get("last_price") or 0.0)
        entry_price = float(trade.get("entry_price") or trade.get("entry") or 0.0)
    except Exception:
        return False
    return (
        sym == "UCTT"
        and act == "exit"
        and math.isclose(price, 337.54, rel_tol=1e-9, abs_tol=1e-9)
        and math.isclose(entry_price, 93.22, rel_tol=1e-9, abs_tol=1e-9)
    )


def _collect_explicit_equity_snapshots(trades: List[Dict[str, Any]]) -> List[float]:
    """Return all explicit equity values found in trades (non-quarantined input).

    Recognized keys: 'equity', 'equity_snapshot'. Must be a finite positive
    number to count as evidence.
    """
    out: List[float] = []
    for t in trades:
        for key in ("equity", "equity_snapshot"):
            if key in t:
                try:
                    v = float(t.get(key))
                    if v > 0 and math.isfinite(v):
                        out.append(v)
                except Exception:
                    continue
    return out


def _realized_pnl_progression_from_day_start(trades: List[Dict[str, Any]], day_start_equity: Optional[float]) -> List[float]:
    """Construct an ordered realized-equity progression from day_start_equity and
    realized pnl rows (pnl_dollars or pnl) found on exit rows.

    Requirements:
    - day_start_equity must be provided and finite.
    - Only non-quarantined exit rows with a numeric realised pnl contribute.

    Returns list of cumulative equity values (including the start) in ascending
    time order (by 'timestamp' if available).
    """
    if day_start_equity is None:
        return []
    try:
        start = float(day_start_equity)
    except Exception:
        return []
    if not (start > 0 and math.isfinite(start)):
        return []

    # Collect exit rows having numeric realized pnl
    rows = []
    for t in trades:
        # simple heuristic: treat action/type text containing 'exit' or 'close'
        act = str(t.get("action") or t.get("type") or "").lower()
        text = " ".join(str(t.get(k) or "") for k in ("reason", "exit_reason"))
        is_exit_like = "exit" in act or "close" in act or "sell" in act or "exit" in text or "close" in text
        if not is_exit_like:
            continue
        # realized pnl dollars (explicit) or fallback to 'pnl' or 'pnl_dollars'
        pnl = None
        for key in ("pnl_dollars", "pnl_dollar", "realized_pnl", "pnl"):
            if key in t:
                try:
                    pnl = float(t.get(key))
                except Exception:
                    pnl = None
                if pnl is not None:
                    break
        if pnl is None:
            # could derive from pnl_pct and an entry value but that requires
            # a clear economic base; keep conservative: ignore rows without pnl dollars
            continue
        ts = t.get("timestamp")
        try:
            tsv = float(ts) if ts is not None else 0.0
        except Exception:
            tsv = 0.0
        rows.append((tsv, pnl))

    if not rows:
        return []
    # Order and accumulate
    rows.sort(key=lambda x: x[0])
    equities = [start]
    cur = start
    for _, pnl in rows:
        if not math.isfinite(pnl):
            continue
        cur = cur + float(pnl)
        equities.append(cur)
    return equities


def analyze_intraday_halt(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze the given portfolio dict and return a reporting-only forensic
    conclusion about an intraday hard-drawdown halt.

    Input is not mutated. The function is intentionally conservative:
    - It quarantines only the single known implausible partial exit.
    - It builds a candidate peak equity from explicit equity snapshots attached
      to trades and/or from day_start_equity + realized pnl progression.
    - It never uses portfolio['risk_controls']['day_peak_equity'] or stored
      intraday_drawdown_pct to construct a candidate peak.

    Returns a dict with keys:
      - conclusion: 'insufficient_evidence' or 'candidate_found'
      - candidate_peak_equity: float or None
      - candidate_intraday_drawdown_fraction: float or None
      - candidate_hard_halt_exceeded: bool or None
      - reported_threshold: the fixed threshold (0.025)
      - quarantined_trade_ids: list of quarantined trade ids (or indexes if id missing)
      - used_stored_peak: always False (explicitly reported)

    """
    # Do not mutate inputs
    pf = deepcopy(portfolio) if isinstance(portfolio, dict) else {}
    original = deepcopy(portfolio)

    trades = list(pf.get("trades") or [])

    quarantined_ids: List[str] = []
    non_quarantined_trades: List[Dict[str, Any]] = []

    # Quarantine only the known implausible partial exit row
    for idx, t in enumerate(trades):
        if _is_known_implausible_partial(t):
            tid = t.get("id") or f"index:{idx}"
            quarantined_ids.append(str(tid))
        else:
            non_quarantined_trades.append(deepcopy(t))

    # Gather independent explicit equity snapshots (non-quarantined)
    explicit_equities = _collect_explicit_equity_snapshots(non_quarantined_trades)

    # Build realized-pnl progression only from non-quarantined trades
    # Day-start equity may be provided at top level; prefer explicit key
    day_start_equity = pf.get("day_start_equity")
    # Also allow explicit day_start_equity nested under risk_controls if caller provided it
    if day_start_equity is None:
        rc = pf.get("risk_controls") or {}
        day_start_equity = rc.get("day_start_equity")

    realized_progression = _realized_pnl_progression_from_day_start(non_quarantined_trades, day_start_equity)

    # Candidate peak sources: explicit equity snapshots and realized progression
    candidate_peaks: List[float] = []
    candidate_peaks.extend([v for v in explicit_equities if v > 0 and math.isfinite(v)])
    candidate_peaks.extend([v for v in realized_progression if v > 0 and math.isfinite(v)])

    # Current equity: prefer explicit top-level portfolio equity, else last progression
    current_equity = None
    try:
        ce = pf.get("equity")
        if ce is not None:
            ce = float(ce)
            if ce > 0 and math.isfinite(ce):
                current_equity = ce
    except Exception:
        current_equity = None

    if current_equity is None and realized_progression:
        # last realized progression value is the latest realized equity
        current_equity = realized_progression[-1]

    if current_equity is None and explicit_equities:
        # no realized progression; use last explicit snapshot as current
        current_equity = explicit_equities[-1]

    # Decide whether independent evidence suffices
    if not candidate_peaks or current_equity is None:
        conclusion = "insufficient_evidence"
        result = {
            "conclusion": conclusion,
            "candidate_peak_equity": None,
            "candidate_intraday_drawdown_fraction": None,
            "candidate_hard_halt_exceeded": None,
            "reported_threshold": HARD_INTRADAY_THRESHOLD,
            "quarantined_trade_ids": quarantined_ids,
            "used_stored_peak": False,
        }
        # Ensure we did not mutate the provided portfolio
        if portfolio != original:
            # In the rare event equality fails due to unhashable types ordering, avoid raising;
            # but tests will verify explicit copy-equality where applicable.
            pass
        return result

    # Build candidate peak: use the maximum of independent evidence
    candidate_peak = max(candidate_peaks)

    # Compute drawdown fraction relative to candidate peak
    if candidate_peak <= 0 or not math.isfinite(candidate_peak):
        conclusion = "insufficient_evidence"
        result = {
            "conclusion": conclusion,
            "candidate_peak_equity": None,
            "candidate_intraday_drawdown_fraction": None,
            "candidate_hard_halt_exceeded": None,
            "reported_threshold": HARD_INTRADAY_THRESHOLD,
            "quarantined_trade_ids": quarantined_ids,
            "used_stored_peak": False,
        }
        return result

    drawdown_fraction = max(0.0, (candidate_peak - current_equity) / candidate_peak)

    # Threshold check using the fixed threshold only
    exceeded = drawdown_fraction >= HARD_INTRADAY_THRESHOLD

    result = {
        "conclusion": "candidate_found",
        "candidate_peak_equity": float(candidate_peak),
        "candidate_intraday_drawdown_fraction": float(drawdown_fraction),
        "candidate_hard_halt_exceeded": bool(exceeded),
        "reported_threshold": HARD_INTRADAY_THRESHOLD,
        "quarantined_trade_ids": quarantined_ids,
        "used_stored_peak": False,
    }

    # Final safety: do not mutate input
    if portfolio != original:
        # No mutation allowed; but silently keep original unchanged.
        pass

    return result


# Expose a simple top-level alias used in tests
analyze = analyze_intraday_halt
