"""Expansion impact monitor.

Read-only monitor for the paper-only controlled expansion.

It answers:
- Did open positions move toward the new target?
- Did execution rows increase after expansion?
- Were new entries tagged as core vs paper research?
- Did drawdown, losses, state size, or ML authority warnings increase?

This module does not trade, resize, change risk controls, change ML authority,
or modify strategy behavior.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, List

VERSION = "expansion-impact-monitor-2026-06-04-v2-observed-outcome-fix"
REGISTERED_APP_IDS: set[int] = set()

BASELINE_EXECUTION_ROWS = int(os.environ.get("EXPANSION_BASELINE_EXECUTION_ROWS", "82"))
BASELINE_OBSERVED_OUTCOMES = int(os.environ.get("EXPANSION_BASELINE_OBSERVED_OUTCOMES", "49"))
BASELINE_OPEN_POSITIONS = int(os.environ.get("EXPANSION_BASELINE_OPEN_POSITIONS", "3"))
BASELINE_STATE_SIZE_BYTES = int(os.environ.get("EXPANSION_BASELINE_STATE_SIZE_BYTES", "14499209"))

TARGET_OPEN_POSITIONS = int(os.environ.get("EXPANSION_TARGET_OPEN_POSITIONS", "8"))
MAX_POSITIONS = int(os.environ.get("EXPANSION_MAX_POSITIONS", "16"))
MAX_NEW_ENTRIES_PER_CYCLE = int(os.environ.get("EXPANSION_MAX_NEW_ENTRIES_PER_CYCLE", "2"))
STATE_SIZE_WARN_DELTA_BYTES = int(os.environ.get("EXPANSION_STATE_SIZE_WARN_DELTA_BYTES", "7000000"))
DRAWDOWN_WARN_PCT = float(os.environ.get("EXPANSION_DRAWDOWN_WARN_PCT", "1.25"))


def _now(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state(core: Any = None) -> Dict[str, Any]:
    try:
        state = core.load_state()
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _state_size_bytes(core: Any = None) -> int:
    path = "/data/state.json"
    try:
        for key in ("STATE_FILE", "STATE_PATH"):
            value = getattr(core, key, None)
            if value:
                path = str(value)
                break
    except Exception:
        pass

    try:
        return os.path.getsize(path) if os.path.exists(path) else 0
    except Exception:
        return 0


def _portfolio(core: Any = None) -> Dict[str, Any]:
    try:
        pf = getattr(core, "portfolio", {})
        return pf if isinstance(pf, dict) else {}
    except Exception:
        return {}


def _positions(state: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core)
    live_positions = pf.get("positions", {})
    if isinstance(live_positions, dict):
        return live_positions

    positions = state.get("positions", {})
    return positions if isinstance(positions, dict) else {}


def _trades(state: Dict[str, Any], core: Any = None) -> List[Dict[str, Any]]:
    pf = _portfolio(core)
    live_trades = pf.get("trades", [])
    if isinstance(live_trades, list):
        return [row for row in live_trades if isinstance(row, dict)]

    trades = state.get("trades", [])
    return [row for row in trades if isinstance(row, dict)] if isinstance(trades, list) else []


def _is_entry(row: Dict[str, Any]) -> bool:
    action = str(row.get("action", row.get("type", ""))).lower()
    return action in {"entry", "buy", "open", "entered"} or bool(row.get("entry_time"))


def _is_exit(row: Dict[str, Any]) -> bool:
    action = str(row.get("action", row.get("type", ""))).lower()
    return action in {"exit", "sell", "close", "closed"} or bool(row.get("exit_time"))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _summary_totals_from_dict(data: Any) -> int | None:
    if not isinstance(data, dict):
        return None

    wins = data.get("wins_total")
    losses = data.get("losses_total")

    if wins is not None or losses is not None:
        return max(0, _safe_int(wins) + _safe_int(losses))

    nested_keys = (
        "journal_summary",
        "performance",
        "execution_summary",
        "truth_summary",
        "trade_journal",
    )

    for key in nested_keys:
        nested = data.get(key)
        total = _summary_totals_from_dict(nested)
        if total is not None:
            return total

    return None


def _observed_outcomes(state: Dict[str, Any], core: Any = None, trades: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Return observed outcome count using source-of-truth summaries first.

    Priority:
    1. portfolio/performance or state/performance wins_total + losses_total
    2. trade journal/truth summary wins_total + losses_total
    3. execution summary wins + losses
    4. fallback explicit exit-row heuristic
    """

    trades = trades or []

    pf = _portfolio(core)
    candidates = [
        pf.get("performance"),
        pf.get("trade_journal"),
        pf.get("truth_summary"),
        state.get("performance"),
        state.get("trade_journal"),
        state.get("journal_summary"),
        state.get("truth_summary"),
        state.get("ml_phase25"),
        state.get("ml_readiness"),
    ]

    for candidate in candidates:
        total = _summary_totals_from_dict(candidate)
        if total is not None:
            return {
                "count": max(BASELINE_OBSERVED_OUTCOMES, total),
                "source": "summary_wins_plus_losses",
                "raw_count": total,
            }

    # Some summaries use wins/losses instead of wins_total/losses_total.
    for candidate in candidates:
        if isinstance(candidate, dict):
            wins = candidate.get("wins")
            losses = candidate.get("losses")
            if wins is not None or losses is not None:
                total = max(0, _safe_int(wins) + _safe_int(losses))
                return {
                    "count": max(BASELINE_OBSERVED_OUTCOMES, total),
                    "source": "summary_wins_losses",
                    "raw_count": total,
                }

    fallback_count = sum(1 for row in trades if _is_exit(row))
    return {
        "count": max(BASELINE_OBSERVED_OUTCOMES, fallback_count),
        "source": "exit_row_fallback",
        "raw_count": fallback_count,
    }


def _ml_live_authority(state: Dict[str, Any]) -> bool:
    for key in ("ml_phase2", "ml_phase25", "ml2_summary", "ml_readiness"):
        section = state.get(key)
        if isinstance(section, dict) and section.get("live_trade_decider") is True:
            return True
    return False


def _risk_controls(state: Dict[str, Any], core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core)
    rc = pf.get("risk_controls", {})
    if isinstance(rc, dict):
        return rc

    rc = state.get("risk_controls", {})
    return rc if isinstance(rc, dict) else {}


def build_payload(core: Any = None) -> Dict[str, Any]:
    state = _load_state(core)
    positions = _positions(state, core)
    trades = _trades(state, core)
    risk_controls = _risk_controls(state, core)

    execution_rows = len(trades)
    observed = _observed_outcomes(state, core, trades)
    observed_outcomes = int(observed.get("count") or BASELINE_OBSERVED_OUTCOMES)

    open_positions = len(positions)

    new_rows = trades[BASELINE_EXECUTION_ROWS:] if execution_rows > BASELINE_EXECUTION_ROWS else []
    new_entries = [row for row in new_rows if _is_entry(row)]

    tagged_entries = []
    untagged_entries = []
    research_entries = []
    core_entries = []

    for row in new_entries:
        paper_learning = row.get("paper_learning")
        if isinstance(paper_learning, dict):
            tagged_entries.append(row)
            if paper_learning.get("research_slot"):
                research_entries.append(row)
            else:
                core_entries.append(row)
        else:
            untagged_entries.append(row)

    state_size = _state_size_bytes(core)
    state_size_delta = state_size - BASELINE_STATE_SIZE_BYTES if state_size else 0

    daily_drawdown = float(
        risk_controls.get("intraday_drawdown_pct")
        or risk_controls.get("daily_drawdown_pct")
        or risk_controls.get("daily_loss_pct")
        or 0.0
    )

    losses_today = int(risk_controls.get("losses_today") or 0)
    ml_live = _ml_live_authority(state)

    execution_rows_delta = max(0, execution_rows - BASELINE_EXECUTION_ROWS)
    observed_outcomes_delta = max(0, observed_outcomes - BASELINE_OBSERVED_OUTCOMES)
    open_positions_delta = open_positions - BASELINE_OPEN_POSITIONS

    positions_to_target = max(0, TARGET_OPEN_POSITIONS - open_positions)
    moved_toward_target = open_positions > BASELINE_OPEN_POSITIONS

    warnings = []

    if ml_live:
        warnings.append({
            "code": "ml_authority_changed",
            "message": "ML live authority appears enabled; expected shadow-only.",
        })

    if untagged_entries:
        warnings.append({
            "code": "untagged_expansion_entries",
            "message": f"{len(untagged_entries)} post-expansion entries are missing paper_learning tags.",
        })

    if daily_drawdown >= DRAWDOWN_WARN_PCT:
        warnings.append({
            "code": "drawdown_watch",
            "message": f"Drawdown {daily_drawdown:.3f}% is above expansion monitor watch threshold.",
        })

    if state_size_delta > STATE_SIZE_WARN_DELTA_BYTES:
        warnings.append({
            "code": "state_size_growth_watch",
            "message": "State size increased materially after expansion.",
        })

    if losses_today > 0:
        warnings.append({
            "code": "losses_today_present",
            "message": f"Losses today: {losses_today}. Monitor expansion quality.",
        })

    if ml_live or daily_drawdown >= DRAWDOWN_WARN_PCT * 2:
        health = "fail"
    elif warnings:
        health = "warn"
    else:
        health = "pass"

    if not new_entries and open_positions < TARGET_OPEN_POSITIONS:
        interpretation = (
            "No post-expansion entries yet. This is acceptable if candidates did not qualify; "
            "do not lower thresholds blindly."
        )
    elif untagged_entries:
        interpretation = "Expansion generated entries, but some are missing learning tags."
    elif new_entries:
        interpretation = "Expansion generated tagged entries for ML observation."
    else:
        interpretation = "Expansion is stable."

    payload = {
        "status": "ok" if health == "pass" else "warn" if health == "warn" else "fail",
        "overall": health,
        "type": "expansion_impact_monitor_status",
        "version": VERSION,
        "generated_local": _now(core),
        "advisory_only": True,
        "authority_changed": False,
        "baseline": {
            "execution_rows": BASELINE_EXECUTION_ROWS,
            "observed_outcomes": BASELINE_OBSERVED_OUTCOMES,
            "open_positions": BASELINE_OPEN_POSITIONS,
            "state_size_bytes": BASELINE_STATE_SIZE_BYTES,
            "target_open_positions": TARGET_OPEN_POSITIONS,
            "max_positions": MAX_POSITIONS,
            "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE,
        },
        "current": {
            "execution_rows": execution_rows,
            "observed_outcomes": observed_outcomes,
            "observed_outcomes_source": observed.get("source"),
            "observed_outcomes_raw_count": observed.get("raw_count"),
            "open_positions": open_positions,
            "positions_to_target": positions_to_target,
            "state_size_bytes": state_size,
            "state_size_delta_bytes": state_size_delta,
            "daily_drawdown_pct": daily_drawdown,
            "losses_today": losses_today,
            "ml_live_authority": ml_live,
        },
        "deltas": {
            "execution_rows_delta": execution_rows_delta,
            "observed_outcomes_delta": observed_outcomes_delta,
            "open_positions_delta": open_positions_delta,
        },
        "entry_tagging": {
            "new_entries_since_expansion": len(new_entries),
            "tagged_entries": len(tagged_entries),
            "untagged_entries": len(untagged_entries),
            "research_slot_entries": len(research_entries),
            "core_entries": len(core_entries),
        },
        "expansion_policy": {
            "max_positions": MAX_POSITIONS,
            "target_open_positions": TARGET_OPEN_POSITIONS,
            "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE,
            "ml_authority_expected": "shadow_only",
            "risk_controls_expected": "unchanged",
            "score_thresholds_expected": "unchanged",
        },
        "positions_moving_toward_target": moved_toward_target,
        "warnings": warnings,
        "interpretation": interpretation,
        "next_actions": [
            "Keep ML shadow-only.",
            "Do not lower entry thresholds just to fill slots.",
            "Watch whether execution rows increase without drawdown or state-size warnings.",
            "Investigate only if entries occur without paper_learning tags.",
        ],
    }

    try:
        pf = _portfolio(core)
        if pf is not None:
            pf["expansion_impact_monitor"] = {
                "status": payload["status"],
                "overall": payload["overall"],
                "version": VERSION,
                "current": payload["current"],
                "deltas": payload["deltas"],
                "entry_tagging": payload["entry_tagging"],
                "authority_changed": False,
            }
    except Exception:
        pass

    return payload


def apply(core: Any = None) -> Dict[str, Any]:
    return build_payload(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    from flask import jsonify

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        return jsonify(build_payload(core))

    if "/paper/expansion-impact-status" not in existing:
        flask_app.add_url_rule(
            "/paper/expansion-impact-status",
            "expansion_impact_status",
            status_route,
        )

    if "/paper/expansion-impact-monitor" not in existing:
        flask_app.add_url_rule(
            "/paper/expansion-impact-monitor",
            "expansion_impact_monitor",
            status_route,
        )

    REGISTERED_APP_IDS.add(id(flask_app))
