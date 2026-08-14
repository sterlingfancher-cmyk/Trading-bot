from __future__ import annotations

"""Forensic diagnostic reporting helper (reporting-only).

Goal: surgical, read-only diagnostics used by test/regression harness. This
module intentionally avoids mutating inputs and uses a single consistent unit
internally: fractions (e.g. 0.025 == 2.5%). All externally-facing pct fields
are clearly labeled with their units.

Key behaviors enforced by the regression tests in this PR:
- Canonical production shape expects day_start_equity and day_peak_equity to
  live inside portfolio['risk_controls']. The portfolio's current equity is
  stored at portfolio['equity'].
- risk_controls['intraday_drawdown_pct'] is treated as a CURRENT measured
  metric (percent units commonly stored). It is reported but NEVER used as a
  hard threshold for halting logic in this reporting helper.
- The effective hard intraday threshold remains 0.025 (2.5% fraction) unless
  an explicit threshold argument is supplied to the analysis function.
- Internally use fraction units; report both fraction and pct fields with
  explicit names so there is no ambiguity.
- The known bad-tick UCTT pattern (entry 93.22 -> partial_exit 337.54 ->
  exit 94.025) is excluded from suspect evidence (reporting-only exclusion).
- Do not treat stored day_peak_equity as independent support for suspect
  trade evidence; indicate in the report that day_peak_equity was not used
  as candidate support.
- If independent trade/equity support is inadequate, return a conclusion of
  'insufficient_evidence'.

This module intentionally performs only reporting/diagnostic duties. It does
not change any risk state, halts, or thresholds in the system, and does not
authorize any trading actions.
"""

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_HARD_INTRADAY_THRESHOLD_FRACTION = 0.025  # 2.5% fraction


def _as_fraction(value: Any) -> float:
    """Normalise an input that might be a fraction (0.025) or a percent (2.5 or 11.73)

    Heuristic: if value is a number > 1.0 treat it as percent and divide by 100.
    If it's None or invalid return 0.0.
    """
    try:
        v = float(value)
    except Exception:
        return 0.0
    if v > 1.0:
        return v / 100.0
    if v < 0.0:
        return 0.0
    return v


def _is_uctt_bad_tick_sequence(trades: List[Dict[str, Any]]) -> List[int]:
    """Detect indices of trades that match the known UCTT bad-tick pattern.

    We look for exact-price pattern described in the handoff and return the
    list of indices to exclude from suspect evidence. This is conservative and
    intentionally very specific.
    """
    exclude_indices: List[int] = []
    for i, t in enumerate(trades):
        try:
            sym = str(t.get("symbol") or "").upper()
            typ = str(t.get("type") or t.get("event") or "").lower()
            price = float(t.get("price") if t.get("price") is not None else t.get("price_usd", 0.0))
        except Exception:
            continue
        if sym == "UCTT":
            # match any of the three exact suspect prices (entry, partial_exit, exit)
            if any(abs(price - p) < 1e-6 for p in (93.22, 337.54, 94.025)):
                exclude_indices.append(i)
    return exclude_indices


def forensic_analysis(
    portfolio: Dict[str, Any],
    trades: Optional[List[Dict[str, Any]]] = None,
    intraday_hard_threshold_fraction: Optional[float] = None,
) -> Dict[str, Any]:
    """Produce a read-only forensic diagnostic report.

    Inputs are never mutated; a shallow-deep copy check is included in tests
    to verify that. The function expects the canonical shape described in the
    handoff (day_start_equity/day_peak_equity inside portfolio['risk_controls'],
    and portfolio['equity'] holding the current equity).

    Parameters:
    - portfolio: current portfolio dictionary (read-only)
    - trades: optional list of trade/event dicts (read-only)
    - intraday_hard_threshold_fraction: optional explicit hard intraday
      threshold (fraction units). If omitted the effective hard intraday
      threshold remains 0.025 (2.5%). If >1 it's treated as percent and
      converted to fraction.

    Returns a diagnostic dictionary containing: preserved inputs (copied), a
    measured-metrics block (fractions and pct fields), an explicit effective
    threshold (fraction), a list of suspect_trades (excluding the known
    UCTT bad-tick rows), flags showing that stored day_peak_equity was NOT
    used as independent support, and a conservative conclusion string.
    """
    # Keep everything read-only: operate on deep copies for reporting only.
    pf = deepcopy(portfolio) if portfolio is not None else {}
    tr = deepcopy(trades) if trades is not None else []

    # Prepare canonical risk_controls shape reporting
    risk_controls = dict(pf.get("risk_controls") or {})

    # Current equity: portfolio['equity'] per canonical shape
    equity = float(pf.get("equity") if pf.get("equity") is not None else 0.0)

    # day_start_equity and day_peak_equity must live inside risk_controls
    day_start_equity = float(risk_controls.get("day_start_equity") or 0.0)
    day_peak_equity = float(risk_controls.get("day_peak_equity") or 0.0)

    # Measured intraday drawdown metric may be stored as a pct (e.g. 11.73)
    stored_intraday_pct = risk_controls.get("intraday_drawdown_pct")
    intraday_drawdown_fraction_current = _as_fraction(stored_intraday_pct)

    # Effective hard threshold: explicit arg (if provided) else canonical default
    effective_threshold = (
        _as_fraction(intraday_hard_threshold_fraction)
        if intraday_hard_threshold_fraction is not None
        else DEFAULT_HARD_INTRADAY_THRESHOLD_FRACTION
    )

    # Compute derived fractions based on canonical fields (fractions internally)
    # Use day_start_equity and day_peak_equity only as measured metrics. Do NOT
    # treat stored day_peak_equity as independent support for suspect trades.
    daily_loss_fraction = 0.0
    if day_start_equity and day_start_equity > 0.0:
        daily_loss_fraction = max(0.0, (day_start_equity - equity) / day_start_equity)
    intraday_drawdown_fraction_computed = 0.0
    if day_peak_equity and day_peak_equity > 0.0:
        intraday_drawdown_fraction_computed = max(0.0, (day_peak_equity - equity) / day_peak_equity)

    # Suspect trade extraction: naive heuristics for diagnostics only.
    suspects: List[Dict[str, Any]] = []
    excluded_indices = set(_is_uctt_bad_tick_sequence(tr))
    for idx, row in enumerate(tr):
        if idx in excluded_indices:
            # purposely exclude these rows from further suspect consideration
            continue
        # Simple suspiciousness heuristic: extremely large one-off price move
        # or partial_exit with absurd price ratio. Keep conservative.
        try:
            sym = str(row.get("symbol") or "").upper()
            typ = str(row.get("type") or row.get("event") or "").lower()
            price = float(row.get("price") if row.get("price") is not None else row.get("price_usd", 0.0))
            qty = float(row.get("qty") or row.get("shares") or 0.0)
        except Exception:
            continue
        # Basic rule: ignore zero/near-zero quantity events
        if qty <= 0:
            continue
        # Example heuristic: prices above $1000 or price jumps > 10x flagged
        flagged = False
        reason = ""
        if price >= 1000.0:
            flagged = True
            reason = "large_absolute_price"
        # If previous trade of same symbol exists, check ratio
        for prior in (tr[:idx] if idx > 0 else []):
            try:
                if str(prior.get("symbol") or "").upper() != sym:
                    continue
                prior_price = float(prior.get("price") or 0.0)
            except Exception:
                continue
            if prior_price > 0.0 and (price / prior_price) > 5.0:
                flagged = True
                reason = "large_price_ratio_vs_prior"
                break
        if flagged:
            suspects.append({"index": idx, "symbol": sym, "type": typ, "price": price, "qty": qty, "reason": reason})

    # Decide conclusion conservatively: suspect evidence OR computed drawdown >= effective threshold
    concluded_issue = False
    reasons: List[str] = []
    if suspects:
        concluded_issue = True
        reasons.append("suspect_trades_detected")
    # use computed intraday drawdown (from stored peak) as a measured metric, but
    # do NOT treat stored intraday_drawdown_pct as a configured threshold.
    if intraday_drawdown_fraction_computed >= effective_threshold:
        concluded_issue = True
        reasons.append("intraday_drawdown_exceeded_effective_threshold")

    # If we have no independent trade support and no computed drawdown breach -> insufficient
    if not concluded_issue:
        conclusion = "insufficient_evidence"
    else:
        conclusion = "potential_issue" if reasons else "insufficient_evidence"

    report: Dict[str, Any] = {
        "inputs_preserved": {
            "portfolio_snapshot": pf,
            "trades_snapshot": tr,
        },
        "metrics": {
            # canonical placements and unambiguous units
            "equity": float(equity),
            "risk_controls": {
                # include raw stored values as-is for provenance
                "raw_intraday_drawdown_pct_stored": stored_intraday_pct,
                # reported metric in both fraction and pct with clear names
                "intraday_drawdown_fraction_current": float(intraday_drawdown_fraction_current),
                "intraday_drawdown_pct_current": round(float(intraday_drawdown_fraction_current) * 100.0, 6),
                "day_start_equity": float(day_start_equity),
                "day_peak_equity": float(day_peak_equity),
            },
            "computed": {
                "daily_loss_fraction": float(daily_loss_fraction),
                "daily_loss_pct": round(float(daily_loss_fraction) * 100.0, 6),
                "intraday_drawdown_fraction_computed": float(intraday_drawdown_fraction_computed),
                "intraday_drawdown_pct_computed": round(float(intraday_drawdown_fraction_computed) * 100.0, 6),
            },
        },
        "effective_hard_intraday_threshold_fraction": float(effective_threshold),
        "effective_hard_intraday_threshold_pct": round(float(effective_threshold) * 100.0, 6),
        "suspect_trades": suspects,
        "excluded_trade_indices_known_bad_ticks": sorted(list(excluded_indices)),
        # explicit statement: stored day_peak_equity was NOT used as candidate support
        "used_stored_day_peak_equity_as_support": False,
        "conclusion": conclusion,
        "conclusion_reasons": reasons,
    }

    return report
