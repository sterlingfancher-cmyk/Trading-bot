from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

HARD_INTRADAY_THRESHOLD = 0.025  # fixed hard intraday threshold (do NOT change)


def _norm_action(row: Dict[str, Any]) -> str:
    return str(row.get("action") or row.get("type") or "").strip().lower()


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def forensic_audit(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight forensic audit of persisted trades.

    Behaviour (surgical, reporting-only):
    - Reproduce an observed persisted UCTT production sequence where a bad
      partial-exit row lacked an entry_price but followed a valid entry row.
    - Correlate a partial_exit with its prior same-symbol entry using sequence
      (ordering) and symbol alone — do NOT require entry_price on the partial row.
    - Quarantine ONLY that exact proven bad partial row (report it); do NOT
      quarantine the entry row or a legitimate final exit.
    - Preserve the fixed hard intraday threshold exactly as HARD_INTRADAY_THRESHOLD.
    - Do NOT use stored risk_controls.day_peak_equity or intraday_drawdown_pct as
      candidate peak evidence. Candidate peak is built only from independent
      non-quarantined equity snapshots and/or economically supportable
      realized-P&L progression. If no independent evidence is available,
      return conclusion='insufficient_evidence' and candidate_peak_equity=None.

    The input `state` is treated read-only (not modified).
    Returns a dictionary with keys:
      - quarantined_trade_indices: list[int] indexes (into state.get('trades', []))
      - quarantined_trades: list[Dict] (actual rows copied)
      - conclusion: 'insufficient_evidence' | 'sufficient_evidence'
      - candidate_peak_equity: Optional[float]
      - candidate_hard_halt_exceeded: Optional[bool]
    """
    trades: List[Dict[str, Any]] = list(state.get("trades") or [])

    quarantined_indices: List[int] = []
    quarantined_trades: List[Dict[str, Any]] = []

    # Map most recent prior entry index for each symbol by sequence order
    last_entry_index_by_symbol: Dict[str, int] = {}
    for idx, row in enumerate(trades):
        action = _norm_action(row)
        sym = _symbol(row)
        if not sym:
            continue
        if action in {"entry", "buy", "open"}:
            last_entry_index_by_symbol[sym] = idx

    # Identify suspicious partial exits that lack their own entry_price but
    # follow a prior entry for the same symbol. Correlate by sequence & symbol.
    for idx, row in enumerate(trades):
        action = _norm_action(row)
        if action not in {"partial_exit", "partial-close", "partial_close", "partial"}:
            continue
        sym = _symbol(row)
        if not sym:
            continue
        # If the partial row does not include an entry price, attempt to
        # correlate it to a prior entry for the same symbol in earlier rows.
        has_entry_price = any(
            (k in row and row.get(k) not in (None, "")) for k in ("entry_price", "entry", "price")
        )
        if has_entry_price:
            # It already carries price; do not quarantine purely for missing entry_price
            continue
        prior_entry_idx = last_entry_index_by_symbol.get(sym)
        if prior_entry_idx is None:
            # no prior entry to correlate to — cannot mark as proven bad here
            continue
        if prior_entry_idx < idx:
            # Proven bad partial row as persisted: quarantine only this row
            quarantined_indices.append(idx)
            quarantined_trades.append(dict(trades[idx]))
            # Do not quarantine the prior entry or any subsequent legitimate exit

    # Candidate peak evidence: only from independent equity snapshots and/or
    # realized-P&L progression summarized from non-quarantined exits.
    # Do NOT read risk_controls.day_peak_equity or intraday_drawdown_pct.
    candidate_peak_equity: Optional[float] = None
    candidate_hard_halt_exceeded: Optional[bool] = None

    # 1) Independent equity snapshots (preferred): state.get('equity_snapshots')
    snapshots = state.get("equity_snapshots") or []
    snap_values: List[float] = []
    for item in snapshots:
        if item is None:
            continue
        if isinstance(item, dict):
            val = item.get("equity")
            try:
                if val is not None:
                    snap_values.append(float(val))
            except Exception:
                continue
        else:
            try:
                snap_values.append(float(item))
            except Exception:
                continue
    if snap_values:
        candidate_peak_equity = max(snap_values)

    # 2) If no independent snapshots, attempt economically supportable realized-P&L
    # progression: start from a declared starting equity (if present) and apply
    # realized pnls from non-quarantined exit rows.
    if candidate_peak_equity is None:
        starting_equity = None
        try:
            se = state.get("starting_equity")
            if se is None:
                se = state.get("starting_cash")
            if se is not None:
                starting_equity = float(se)
        except Exception:
            starting_equity = None

        # Sum realized pnl over time (ignore quarantined exit rows)
        realized_series: List[Tuple[int, float]] = []  # (index, cumulative_realized)
        cum = 0.0
        for idx, row in enumerate(trades):
            if idx in quarantined_indices:
                # ignore quarantined rows when building realized progression
                continue
            # treat rows that look like realized exits
            # recognized keys: pnl_dollars, pnl, pnl_pct (we prefer absolute)
            pnl = None
            if row.get("pnl_dollars") is not None:
                try:
                    pnl = float(row.get("pnl_dollars"))
                except Exception:
                    pnl = None
            if pnl is None and row.get("pnl") is not None:
                try:
                    pnl = float(row.get("pnl"))
                except Exception:
                    pnl = None
            if pnl is None and row.get("pnl_pct") is not None and starting_equity is not None:
                try:
                    pnl = float(row.get("pnl_pct")) * starting_equity
                except Exception:
                    pnl = None
            if pnl is not None:
                cum += pnl
                realized_series.append((idx, cum))

        if starting_equity is not None and realized_series:
            # candidate peak is the maximum realized-driven equity observed
            candidate_peak_equity = max(starting_equity + v for (_i, v) in realized_series)

    # If no independent evidence was found, report insufficient evidence
    if candidate_peak_equity is None:
        return {
            "quarantined_trade_indices": quarantined_indices,
            "quarantined_trades": quarantined_trades,
            "conclusion": "insufficient_evidence",
            "candidate_peak_equity": None,
            "candidate_hard_halt_exceeded": None,
            "hard_intraday_threshold": HARD_INTRADAY_THRESHOLD,
        }

    # Otherwise, evaluate whether a hard intraday halt threshold would have been
    # exceeded at any time vs current equity (current equity read from state if present)
    current_equity = None
    try:
        cur = state.get("current_equity") or state.get("equity")
        if cur is not None:
            current_equity = float(cur)
    except Exception:
        current_equity = None

    if current_equity is None:
        candidate_hard_halt_exceeded = None
    else:
        candidate_hard_halt_exceeded = (candidate_peak_equity is not None) and (
            (candidate_peak_equity - current_equity) / candidate_peak_equity >= HARD_INTRADAY_THRESHOLD
        )

    return {
        "quarantined_trade_indices": quarantined_indices,
        "quarantined_trades": quarantined_trades,
        "conclusion": "sufficient_evidence" if quarantined_indices else "insufficient_evidence",
        "candidate_peak_equity": candidate_peak_equity,
        "candidate_hard_halt_exceeded": candidate_hard_halt_exceeded,
        "hard_intraday_threshold": HARD_INTRADAY_THRESHOLD,
    }
