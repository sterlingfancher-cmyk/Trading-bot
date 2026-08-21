"""Read-only provenance probe for a suspicious current-day risk equity peak.

Issue #82 evidence on the historically canonical paper service shows a sane
fresh-day baseline and economically coherent current account, while the persisted
``day_peak_equity`` is far above current/day-start equity and is driving a hard
intraday-drawdown halt.  This module does not repair that state.  It only compares
three already-persisted observation streams:

* the current risk-control snapshot;
* the rolling equity ``history`` written by ``calculate_equity`` on every call;
* current-day compiled intraday reports, whose headline equity is copied at the
  end of a cycle.

That comparison can distinguish a sustained reported peak from a transient
valuation spike that occurred between compiled reports.  Startup ``apply()`` is
constant-time and performs no state scan.  The explicit route reads only the
in-process portfolio and never calls valuation/provider, state-save, recovery,
risk-update, order, journal, or ledger mutation functions.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List

VERSION = "day-peak-provenance-status-2026-08-21-v1"
ROUTE = "/paper/day-peak-provenance-status"
MAX_REPORT_ROWS = 16
MAX_TRADE_ROWS = 20
HISTORY_WINDOW_RADIUS = 6
_REGISTERED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _same_money(a: Any, b: Any, tolerance: float = 0.02) -> bool:
    left = _f(a)
    right = _f(b)
    return bool(left is not None and right is not None and abs(left - right) <= tolerance)


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _trade_local(core: Any, raw: Any) -> str | None:
    value = _f(raw)
    if value is None:
        return None
    try:
        return str(core.local_ts_text(value))
    except Exception:
        try:
            return dt.datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def _history_summary(portfolio: Dict[str, Any], peak: float | None) -> Dict[str, Any]:
    numeric: List[tuple[int, float]] = []
    for index, raw in enumerate(_l(portfolio.get("history"))):
        value = _f(raw)
        if value is not None:
            numeric.append((index, value))

    if not numeric:
        return {
            "count": 0,
            "numeric_count": 0,
            "minimum_equity": None,
            "maximum_equity": None,
            "maximum_index": None,
            "current_peak_observed": False,
            "peak_window": [],
        }

    maximum_index, maximum_equity = max(numeric, key=lambda row: row[1])
    minimum_equity = min(value for _, value in numeric)
    all_history = _l(portfolio.get("history"))
    start = max(0, maximum_index - HISTORY_WINDOW_RADIUS)
    stop = min(len(all_history), maximum_index + HISTORY_WINDOW_RADIUS + 1)
    window = []
    for index in range(start, stop):
        value = _f(all_history[index])
        window.append({"index": index, "equity": value})

    return {
        "count": len(all_history),
        "numeric_count": len(numeric),
        "minimum_equity": round(minimum_equity, 6),
        "maximum_equity": round(maximum_equity, 6),
        "maximum_index": maximum_index,
        "values_after_maximum": max(0, len(all_history) - maximum_index - 1),
        "current_peak_observed": _same_money(maximum_equity, peak),
        "peak_window": window,
    }


def _report_observation(report: Dict[str, Any]) -> Dict[str, Any]:
    headline = _d(report.get("headline"))
    risk = _d(report.get("risk_controls"))
    positions = headline.get("open_positions")
    if not isinstance(positions, list):
        positions = []
    return {
        "date": report.get("date"),
        "generated_local": report.get("generated_local"),
        "headline_equity": _f(headline.get("equity")),
        "headline_cash": _f(headline.get("cash")),
        "headline_day_pnl_pct": _f(headline.get("day_pnl_pct")),
        "headline_intraday_drawdown_pct": _f(headline.get("intraday_drawdown_pct")),
        "risk_day_start_equity": _f(risk.get("day_start_equity")),
        "risk_day_peak_equity": _f(risk.get("day_peak_equity")),
        "risk_intraday_drawdown_pct": _f(risk.get("intraday_drawdown_pct")),
        "risk_halted": bool(risk.get("halted")),
        "risk_halt_reason": risk.get("halt_reason"),
        "open_positions": [str(symbol) for symbol in positions[:12]],
    }


def _report_summary(portfolio: Dict[str, Any], risk_date: str, peak: float | None) -> Dict[str, Any]:
    reports = _d(portfolio.get("reports"))
    raw_rows = [
        row for row in _l(reports.get("intraday_history"))
        if isinstance(row, dict) and str(row.get("date") or "") == risk_date
    ]
    observations = [_report_observation(row) for row in raw_rows]

    headline_rows = [
        (index, row["headline_equity"])
        for index, row in enumerate(observations)
        if row.get("headline_equity") is not None
    ]
    max_headline_index = None
    max_headline_equity = None
    if headline_rows:
        max_headline_index, max_headline_equity = max(headline_rows, key=lambda row: row[1])

    first_peak_risk_index = None
    for index, row in enumerate(observations):
        if _same_money(row.get("risk_day_peak_equity"), peak):
            first_peak_risk_index = index
            break

    first_peak_risk = (
        observations[first_peak_risk_index] if first_peak_risk_index is not None else None
    )
    previous = (
        observations[first_peak_risk_index - 1]
        if first_peak_risk_index is not None and first_peak_risk_index > 0
        else None
    )

    previous_symbols = set((previous or {}).get("open_positions") or [])
    first_symbols = set((first_peak_risk or {}).get("open_positions") or [])
    candidate_symbols = sorted(previous_symbols | first_symbols)

    return {
        "reports_container_date": reports.get("date"),
        "current_day_report_count": len(observations),
        "maximum_headline_equity": max_headline_equity,
        "maximum_headline_generated_local": (
            observations[max_headline_index].get("generated_local")
            if max_headline_index is not None else None
        ),
        "current_peak_observed_in_headline": _same_money(max_headline_equity, peak),
        "first_report_carrying_current_risk_peak": first_peak_risk,
        "report_before_current_risk_peak_first_seen": previous,
        "candidate_symbols_at_peak_boundary": candidate_symbols,
        "symbols_added_at_boundary": sorted(first_symbols - previous_symbols),
        "symbols_removed_at_boundary": sorted(previous_symbols - first_symbols),
        "latest_observations": observations[-MAX_REPORT_ROWS:],
        "reference_caveat": (
            "headline equity is a copied historical scalar; embedded risk_controls may "
            "share the live risk dict until a save/reload, so headline chronology is "
            "stronger evidence than repeated embedded peak values"
        ),
    }


def _today_trades(portfolio: Dict[str, Any], core: Any, risk_date: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in _l(portfolio.get("trades")):
        if not isinstance(raw, dict):
            continue
        local = _trade_local(core, raw.get("time"))
        if not local or not local.startswith(risk_date):
            continue
        rows.append(
            {
                "local_time": local,
                "symbol": raw.get("symbol"),
                "action": raw.get("action"),
                "side": raw.get("side"),
                "price": _f(raw.get("price")),
                "shares": _f(raw.get("shares")),
                "execution_id": raw.get("execution_id"),
                "exit_reason": raw.get("exit_reason"),
            }
        )
    return rows[-MAX_TRADE_ROWS:]


def _current_positions(portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
    positions = _d(portfolio.get("positions"))
    rows: List[Dict[str, Any]] = []
    for symbol, raw in sorted(positions.items()):
        row = _d(raw)
        rows.append(
            {
                "symbol": str(symbol),
                "side": row.get("side"),
                "shares": _f(row.get("shares")),
                "entry": _f(row.get("entry")),
                "last_price": _f(row.get("last_price")),
                "peak": _f(row.get("peak")),
                "trough": _f(row.get("trough")),
                "entry_time_local": None,
            }
        )
        entry_time = row.get("entry_time")
        rows[-1]["entry_time_local"] = _trade_local(None, entry_time)
    return rows


def status_payload(core: Any = None) -> Dict[str, Any]:
    portfolio = _d(getattr(core, "portfolio", None)) if core is not None else {}
    risk = _d(portfolio.get("risk_controls"))
    risk_date = str(risk.get("date") or "")
    start = _f(risk.get("day_start_equity"))
    peak = _f(risk.get("day_peak_equity"))
    current = _f(portfolio.get("equity"))
    cash = _f(portfolio.get("cash"))

    history = _history_summary(portfolio, peak)
    reports = _report_summary(portfolio, risk_date, peak)

    peak_gain_fraction = None
    current_drawdown_fraction = None
    current_vs_start_fraction = None
    if start is not None and start > 0 and peak is not None:
        peak_gain_fraction = (peak - start) / start
    if peak is not None and peak > 0 and current is not None:
        current_drawdown_fraction = max(0.0, (peak - current) / peak)
    if start is not None and start > 0 and current is not None:
        current_vs_start_fraction = (current - start) / start

    history_has_peak = bool(history.get("current_peak_observed"))
    report_has_peak = bool(reports.get("current_peak_observed_in_headline"))
    first_peak_report = reports.get("first_report_carrying_current_risk_peak")
    first_peak_report_equity = _f(_d(first_peak_report).get("headline_equity"))

    if peak is None or start is None or current is None:
        diagnosis = "insufficient_current_risk_or_account_fields"
        overall = "warn"
    elif history_has_peak and report_has_peak:
        diagnosis = "current_day_peak_observed_in_equity_history_and_report_headline"
        overall = "pass"
    elif history_has_peak and not report_has_peak:
        diagnosis = "transient_equity_peak_observed_between_compiled_report_headlines"
        overall = "pass"
    elif first_peak_report and not _same_money(first_peak_report_equity, peak):
        diagnosis = "risk_peak_present_in_report_metadata_without_matching_headline_equity"
        overall = "warn"
    else:
        diagnosis = "current_risk_peak_not_proven_by_retained_equity_observations"
        overall = "warn"

    return {
        "status": "ok",
        "overall": overall,
        "type": "day_peak_provenance_status",
        "version": VERSION,
        "generated_local": _now(core),
        "diagnosis": diagnosis,
        "current_account": {
            "cash": cash,
            "equity": current,
            "positions_count": len(_d(portfolio.get("positions"))),
        },
        "risk": {
            "date": risk_date or None,
            "day_start_equity": start,
            "day_peak_equity": peak,
            "halted": bool(risk.get("halted")),
            "halt_reason": risk.get("halt_reason"),
            "intraday_drawdown_pct": _f(risk.get("intraday_drawdown_pct")),
            "peak_gain_from_day_start_pct": (
                round(peak_gain_fraction * 100.0, 6)
                if peak_gain_fraction is not None else None
            ),
            "current_drawdown_from_peak_pct": (
                round(current_drawdown_fraction * 100.0, 6)
                if current_drawdown_fraction is not None else None
            ),
            "current_change_from_day_start_pct": (
                round(current_vs_start_fraction * 100.0, 6)
                if current_vs_start_fraction is not None else None
            ),
        },
        "equity_history": history,
        "intraday_reports": reports,
        "current_positions": _current_positions(portfolio),
        "current_day_trades": _today_trades(portfolio, core, risk_date),
        "evidence_interpretation": {
            "history_peak_matches_risk_peak": history_has_peak,
            "report_headline_peak_matches_risk_peak": report_has_peak,
            "transient_between_reports": bool(history_has_peak and not report_has_peak),
            "does_not_prove_quote_source_or_symbol": True,
            "next_safe_step_if_transient": (
                "use the peak-boundary time/symbol set with independent historical market data; "
                "do not clear the halt or rewrite the peak from this probe alone"
            ),
        },
        "authority": {
            "reporting_only": True,
            "places_orders": False,
            "calls_market_data_providers": False,
            "writes_files": False,
            "saves_state": False,
            "updates_risk_controls": False,
            "rewrites_current_day_peak": False,
            "clears_hard_halt": False,
            "repairs_historical_state": False,
            "rewrites_or_relabels_canonical_ledger": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    # Deterministic startup registration only. Do not inspect portfolio/history here.
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "installed": True,
        "startup_reads_runtime_state": False,
        "startup_calls_market_data_providers": False,
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {
            "status": "pending",
            "overall": "warn",
            "version": VERSION,
            "reason": "flask_app_missing",
        }
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify

        try:
            existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        except Exception:
            existing = set()
        if ROUTE not in existing:
            flask_app.add_url_rule(
                ROUTE,
                "day_peak_provenance_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(app_id)
    return {
        "status": "ok",
        "overall": "pass",
        "version": VERSION,
        "route_registered": True,
        "startup_reads_runtime_state": False,
    }
