from __future__ import annotations

"""Bounded read-only overrides for the required core status and root routes.

Issue #146 showed that the legacy Flask handlers for /paper/status and / can exceed
our 20-second read-only audit boundary even when the rest of the runtime is healthy.
These replacements deliberately read only already-materialized in-memory state.
They do not recalculate equity, fetch market data, scan journals, inspect the state
file, persist state, run a cycle, or change trading authority.
"""

import html
from typing import Any, Dict

from flask import Response, jsonify, request

VERSION = "readonly-core-status-override-2026-09-01-v1"


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _subset(row: Any, keys: tuple[str, ...]) -> Dict[str, Any]:
    source = _dict(row)
    return {key: source.get(key) for key in keys if key in source}


def _snapshot(core: Any) -> Dict[str, Any]:
    portfolio = _dict(getattr(core, "portfolio", {}))
    positions = _dict(portfolio.get("positions"))
    auto = _dict(portfolio.get("auto_runner"))
    market = _dict(portfolio.get("last_market"))
    risk = _dict(portfolio.get("risk_controls"))
    feedback = _dict(portfolio.get("feedback_loop"))
    performance = _dict(portfolio.get("performance"))
    realized = _dict(portfolio.get("realized_pnl"))
    reports = _dict(portfolio.get("reports"))
    scanner = _dict(portfolio.get("scanner_audit"))

    compact_positions: Dict[str, Any] = {}
    for symbol, raw in positions.items():
        pos = _dict(raw)
        compact_positions[str(symbol)] = _subset(
            pos,
            (
                "side",
                "entry",
                "shares",
                "qty",
                "last_price",
                "peak",
                "stop",
                "trailing_stop",
                "partial_taken",
                "opened_at",
                "opened_local",
            ),
        )

    last_result = _subset(
        auto.get("last_result"),
        (
            "market_mode",
            "regime",
            "risk_score",
            "trade_permission",
            "entries",
            "exits",
            "rotations",
            "entry_block_reason",
            "new_entries_allowed",
        ),
    )

    return {
        "status": "ok",
        "runtime_status": "running",
        "type": "read_only_core_status",
        "version": VERSION,
        "full_requested": str(request.args.get("full", "0")).lower()
        in {"1", "true", "yes", "on"},
        "cash": portfolio.get("cash"),
        "equity": portfolio.get("equity"),
        "peak": portfolio.get("peak"),
        "positions": compact_positions,
        "position_symbols": list(compact_positions.keys()),
        "performance": _subset(
            performance,
            (
                "realized_pnl_today",
                "realized_pnl_total",
                "wins_today",
                "losses_today",
                "wins_total",
                "losses_total",
                "unrealized_pnl",
            ),
        ),
        "realized_pnl": _subset(
            realized,
            (
                "date",
                "today",
                "total",
                "wins_today",
                "losses_today",
                "wins_total",
                "losses_total",
            ),
        ),
        "risk_controls": _subset(
            risk,
            (
                "date",
                "day_start_equity",
                "day_peak_equity",
                "halted",
                "halt_reason",
                "daily_drawdown_pct",
                "intraday_drawdown_pct",
                "profit_guard_active",
                "profit_guard_reason",
            ),
        ),
        "feedback_loop": _subset(
            feedback,
            (
                "self_defense_mode",
                "block_new_entries",
                "hard_halt",
                "reasons",
                "dynamic_min_long_score",
                "dynamic_min_short_score",
            ),
        ),
        "last_market": _subset(
            market,
            (
                "market_mode",
                "regime",
                "risk_score",
                "trade_permission",
                "bear_confirmed",
                "broad_market_soft",
                "growth_leadership",
                "defensive_rotation",
                "generated_local",
            ),
        ),
        "scanner_audit": _subset(
            scanner,
            (
                "last_updated_local",
                "signals_found",
                "entries_count",
                "rotations_count",
                "market_mode",
            ),
        ),
        "auto_runner": {
            **_subset(
                auto,
                (
                    "enabled",
                    "market_only",
                    "interval_seconds",
                    "market_open_now",
                    "thread_started",
                    "last_run_local",
                    "last_run_source",
                    "last_successful_run_local",
                    "last_successful_run_source",
                    "last_skip_local",
                    "last_skip_reason",
                    "last_error",
                ),
            ),
            "last_result": last_result,
        },
        "recent_trades": _list(portfolio.get("trades"))[-20:],
        "history_tail": _list(portfolio.get("history"))[-30:],
        "reports": {
            "date": reports.get("date"),
            "last_intraday_report_generated_local": _dict(
                reports.get("last_intraday_report")
            ).get("generated_local"),
            "last_end_of_day_report_generated_local": _dict(
                reports.get("last_end_of_day_report")
            ).get("generated_local"),
        },
        "authority": {
            "read_only": True,
            "places_orders": False,
            "changes_strategy": False,
            "changes_sizing": False,
            "changes_risk": False,
            "changes_live_authority": False,
            "changes_ml_authority": False,
            "persists_state": False,
        },
    }


def _paper_status(core: Any):
    return jsonify(_snapshot(core))


def _home(core: Any):
    row = _snapshot(core)
    positions = ", ".join(row.get("position_symbols", [])) or "none"
    body = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>Trading Bot Status</title></head>
<body>
<h1>Trading Bot</h1>
<p>Status: <strong>running</strong></p>
<p>Cash: {html.escape(str(row.get('cash')))} | Equity: {html.escape(str(row.get('equity')))}</p>
<p>Positions: {html.escape(positions)}</p>
<p>Read-only status override: {html.escape(VERSION)}</p>
<p><a href=\"/paper/status\">JSON status</a> · <a href=\"/paper/self-check\">Self-check</a> · <a href=\"/paper/daily-audit\">Daily audit</a></p>
</body></html>"""
    return Response(body, status=200, mimetype="text/html")


def install(core: Any) -> Dict[str, Any]:
    app = getattr(core, "app", None)
    if app is None or not hasattr(app, "view_functions"):
        return {"status": "pending", "version": VERSION, "reason": "flask_app_unavailable"}

    replaced = []

    if "paper_status" in app.view_functions:
        def paper_status_view():
            return _paper_status(core)

        paper_status_view._readonly_core_status_override_version = VERSION  # type: ignore[attr-defined]
        app.view_functions["paper_status"] = paper_status_view
        replaced.append("paper_status")

    if "home" in app.view_functions:
        def home_view():
            return _home(core)

        home_view._readonly_core_status_override_version = VERSION  # type: ignore[attr-defined]
        app.view_functions["home"] = home_view
        replaced.append("home")

    return {
        "status": "ok" if {"paper_status", "home"}.issubset(set(replaced)) else "pending",
        "version": VERSION,
        "replaced_endpoints": replaced,
        "read_only": True,
        "persists_state": False,
    }
