"""Forensic intraday-peak diagnostic (paper-only, read-only, reporting-only).

This module is intentionally small, import-safe, and read-only. It inspects the
provided runtime "core" (or a plain object/dict shaped like the runtime's
portfolio snapshot) and emits a focused forensic report covering:

- stored_day_start_equity
- stored_day_peak_equity
- current_equity
- reported drawdown (stored peak -> current)
- identification of implausible historical partial exits for a symbol (ratio > 2.5x by default)
- a computed candidate corrected day_peak_equity derived from plausible current-epoch evidence (does not write)
- whether the configured intraday drawdown halt (default 2.5%) would still be warranted under that candidate

Safety boundaries (non-negotiable):
- Read-only: never mutates core or any persisted state
- Paper-only / reporting-only by design
- Does not change risk/halting state, orders, or any strategies

The module is deliberately conservative about source data. It will look for
portfolio-like dictionaries in these locations, in order of preference:
- core.portfolio (common runtime shape)
- core.load_state() (callable)
- If passed a plain dict as `core`, that dict is used directly as the portfolio

This file also intentionally avoids importing the trading application to
remain safe for static analysis and test runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

VERSION = "forensic-intraday-peak-diagnostic-2026-08-14-v1"


def _get_portfolio(core: Any) -> Dict[str, Any]:
    """Resolve a portfolio-like mapping from the provided core/context.

    Accepts either a runtime-like module/object with .portfolio or .load_state(),
    or a plain dict passed directly as core.
    Never mutates anything.
    """
    if core is None:
        return {}
    # If a plain dict was passed in, use it as-is.
    if isinstance(core, dict):
        return dict(core)
    try:
        pf = getattr(core, "portfolio", None)
        if isinstance(pf, dict):
            return dict(pf)
    except Exception:
        pass
    # Try calling load_state if available
    try:
        load = getattr(core, "load_state", None)
        if callable(load):
            state = load()
            if isinstance(state, dict):
                return dict(state)
    except Exception:
        pass
    # Last-resort: use getattr lookups if some minimal fields exist
    out: Dict[str, Any] = {}
    try:
        out["day_start_equity"] = getattr(core, "day_start_equity", None)
        out["day_peak_equity"] = getattr(core, "day_peak_equity", None)
        out["equity"] = getattr(core, "equity", None)
        # attempt to gather a simple trade_journal attribute
        tj = getattr(core, "trade_journal", None)
        if isinstance(tj, list):
            out["trade_journal"] = list(tj)
    except Exception:
        pass
    return out


@dataclass(frozen=True)
class PartialExitImplausibility:
    symbol: str
    entry_price: float
    partial_exit_price: float
    ratio: float
    threshold: float


def _scan_for_partial_exits(trade_journal: Optional[List[Dict[str, Any]]], threshold: float = 2.5) -> List[PartialExitImplausibility]:
    """Scan a simple trade journal list for partial-exit implausibility examples.

    Expected minimal trade_journal rows (test-friendly): a list of dicts with
    at least: symbol, action (or type), price, and optionally ref (to link entry->exit)

    This scanner is intentionally narrow: it pairs the most recent 'entry' for
    a symbol with a later 'partial_exit' for the same symbol if both provide
    numeric prices. If partial_exit_price / entry_price > threshold, it is
    reported as implausible.
    """
    out: List[PartialExitImplausibility] = []
    if not trade_journal:
        return out
    # Group entries by symbol, keep the last entry price seen (trusting journal order)
    last_entry_by_symbol: Dict[str, float] = {}
    for row in list(trade_journal or []):
        try:
            symbol = str(row.get("symbol") or "").upper()
            action = str(row.get("action") or row.get("type") or "").lower()
            price = row.get("price")
            if price is None:
                # some journals may use 'fill_price' or 'entry_price'
                price = row.get("fill_price") or row.get("entry_price") or row.get("exit_price")
            if price is None:
                continue
            price_f = float(price)
        except Exception:
            continue
        if action in {"entry", "buy", "filled_entry"}:
            last_entry_by_symbol[symbol] = price_f
            continue
        if action in {"partial_exit", "partial_sell", "partial_take"}:
            entry_price = last_entry_by_symbol.get(symbol)
            if entry_price is None:
                # No prior entry observed in the provided journal; skip
                continue
            if entry_price <= 0:
                continue
            ratio = price_f / float(entry_price)
            if ratio > float(threshold):
                out.append(
                    PartialExitImplausibility(
                        symbol=symbol,
                        entry_price=float(entry_price),
                        partial_exit_price=float(price_f),
                        ratio=ratio,
                        threshold=float(threshold),
                    )
                )
    return out


def analyze_intraday_peak(core: Any, intraday_halt_threshold: float = 0.025, partial_exit_implausible_ratio: float = 2.5) -> Dict[str, Any]:
    """Produce a focused forensic diagnostic report.

    Parameters
    - core: runtime-like object or plain dict containing portfolio-like keys
    - intraday_halt_threshold: the intraday drawdown fraction (e.g. 0.025)
    - partial_exit_implausible_ratio: multiplicative threshold to flag implausible partial exits

    Returns a dict with read-only forensic fields. Does not mutate core.
    """
    pf = _get_portfolio(core)

    # Stored values (may be None if missing)
    stored_day_start_equity = pf.get("day_start_equity")
    stored_day_peak_equity = pf.get("day_peak_equity")

    # Current equity: prefer explicit 'equity' key, fall back to 'current_equity' or 'cash + positions' if supplied
    current_equity = pf.get("equity")
    if current_equity is None:
        current_equity = pf.get("current_equity")
    try:
        if current_equity is not None:
            current_equity = float(current_equity)
    except Exception:
        current_equity = None

    # Compute stored drawdown from stored peak to current (if possible)
    reported_drawdown_pct: Optional[float] = None
    try:
        if stored_day_peak_equity is not None and current_equity is not None and float(stored_day_peak_equity) > 0:
            reported_drawdown_pct = max(0.0, (float(stored_day_peak_equity) - float(current_equity)) / float(stored_day_peak_equity))
    except Exception:
        reported_drawdown_pct = None

    # Scan trade journal for implausible partial exits
    trade_journal = None
    for key in ("trade_journal", "journal", "execution_ledger", "trades"):
        if key in pf and isinstance(pf.get(key), list):
            trade_journal = pf.get(key)
            break
    implausible_exits = _scan_for_partial_exits(trade_journal, threshold=partial_exit_implausible_ratio)

    # Candidate corrected day_peak_equity: derive from trusted/plausible current-epoch evidence.
    # Conservative rule used here for reporting-only candidate (no writes): choose the max of
    # stored_day_start_equity, stored_day_peak_equity, and current_equity when available.
    candidate_day_peak_equity: Optional[float] = None
    try:
        candidates: List[float] = []
        for v in (stored_day_start_equity, stored_day_peak_equity, current_equity):
            if v is None:
                continue
            fv = float(v)
            if fv > 0:
                candidates.append(fv)
        if candidates:
            candidate_day_peak_equity = max(candidates)
    except Exception:
        candidate_day_peak_equity = None

    # Compute candidate drawdown and whether an intraday halt would still be warranted
    candidate_drawdown_pct: Optional[float] = None
    candidate_halt_warranted: Optional[bool] = None
    try:
        if candidate_day_peak_equity is not None and current_equity is not None and float(candidate_day_peak_equity) > 0:
            candidate_drawdown_pct = max(0.0, (float(candidate_day_peak_equity) - float(current_equity)) / float(candidate_day_peak_equity))
            candidate_halt_warranted = bool(candidate_drawdown_pct > float(intraday_halt_threshold))
    except Exception:
        candidate_drawdown_pct = None
        candidate_halt_warranted = None

    report: Dict[str, Any] = {
        "version": VERSION,
        "generated_from": "forensic_intraday_peak_diagnostic",
        "stored_day_start_equity": stored_day_start_equity,
        "stored_day_peak_equity": stored_day_peak_equity,
        "current_equity": current_equity,
        "reported_drawdown_pct": reported_drawdown_pct,
        "candidate_day_peak_equity": candidate_day_peak_equity,
        "candidate_drawdown_pct": candidate_drawdown_pct,
        "candidate_halt_warranted": candidate_halt_warranted,
        "intraday_halt_threshold": float(intraday_halt_threshold),
        "partial_exit_implausible_ratio": float(partial_exit_implausible_ratio),
        "implausible_partial_exits": [e.__dict__ for e in implausible_exits],
    }
    return report


__all__ = ["analyze_intraday_peak", "VERSION"]
