"""Read-only evidence calculations for Performance Audit V2.

This module operates only on in-memory research simulations. It has no runtime,
state, broker, credential, or order surface.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Sequence


COST_SENSITIVITY_BPS = (4.0, 8.0, 15.0, 25.0)
DELAY_SENSITIVITY_SESSIONS = (1, 2, 3)
CAPACITY_PARTICIPATION_LIMIT_PCT = 1.0
CAPACITY_STRESS_CAPITALS = (10_000.0, 100_000.0, 1_000_000.0)

SECTOR_GROUPS = {
    "SPY": "broad_market", "QQQ": "broad_market", "IWM": "broad_market",
    "RSP": "broad_market", "SH": "inverse_index", "PSQ": "inverse_index",
    "XLK": "technology", "MSFT": "technology", "AMZN": "mega_cap_growth",
    "META": "mega_cap_growth", "GOOGL": "mega_cap_growth", "PLTR": "technology",
    "SMH": "semiconductors", "NVDA": "semiconductors", "AMD": "semiconductors",
    "AVGO": "semiconductors", "MU": "semiconductors", "STX": "hardware",
    "WDC": "hardware", "DELL": "hardware", "HPE": "hardware", "ANET": "hardware",
    "VRT": "infrastructure", "GEV": "infrastructure", "PWR": "infrastructure",
    "CIEN": "communications", "XLE": "energy", "XLV": "healthcare",
    "XLU": "utilities", "XLP": "consumer_defensive", "GLD": "precious_metals",
    "SLV": "precious_metals", "GDX": "precious_metals", "TLT": "rates",
    "IEF": "rates", "RKLB": "space", "ASTS": "space", "CIFR": "crypto_equity",
    "IREN": "crypto_equity", "CLSK": "crypto_equity", "MARA": "crypto_equity",
    "RIOT": "crypto_equity", "IBIT": "crypto_asset",
}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _percentile(np: Any, values: Sequence[float], percentile: float) -> float:
    if np is None or not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=float), percentile))


def add_liquidity_features(features: Dict[str, Any], pd: Any) -> None:
    """Add signal-time ADV without changing eligibility or ranking input."""
    if pd is None:
        return
    for frame in features.values():
        if not all(column in frame.columns for column in ("Close", "Volume")):
            frame["adv20_dollars"] = float("nan")
            continue
        dollar_volume = frame["Close"].astype(float) * frame["Volume"].astype(float)
        frame["adv20_dollars"] = dollar_volume.rolling(20).mean()


def _concentration(values: Dict[str, float]) -> Dict[str, Any]:
    total_abs = sum(abs(value) for value in values.values())
    rows = sorted(values.items(), key=lambda item: abs(item[1]), reverse=True)
    shares = [abs(value) / total_abs for _, value in rows] if total_abs > 0 else []
    return {
        "contributors": len(rows),
        "net_pnl": round(sum(values.values()), 2),
        "absolute_pnl": round(total_abs, 2),
        "top_contributor": rows[0][0] if rows else None,
        "top_contributor_pnl": round(rows[0][1], 2) if rows else 0.0,
        "top_contributor_abs_share_pct": round(shares[0] * 100, 2) if shares else 0.0,
        "top_five_abs_share_pct": round(sum(shares[:5]) * 100, 2) if shares else 0.0,
        "herfindahl_index": round(sum(value * value for value in shares), 4),
        "ranking": [
            {
                "name": name,
                "pnl": round(value, 2),
                "absolute_share_pct": round(abs(value) / total_abs * 100, 2)
                if total_abs > 0 else 0.0,
            }
            for name, value in rows
        ],
    }


def _concentration_report(exits: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    symbol_pnl: Dict[str, float] = {}
    sector_pnl: Dict[str, float] = {}
    for row in exits:
        symbol = str(row.get("symbol") or "unknown")
        pnl = _f(row.get("pnl"))
        symbol_pnl[symbol] = symbol_pnl.get(symbol, 0.0) + pnl
        sector = SECTOR_GROUPS.get(symbol, "other")
        sector_pnl[sector] = sector_pnl.get(sector, 0.0) + pnl
    return {
        "symbol": _concentration(symbol_pnl),
        "sector_group": _concentration(sector_pnl),
    }


def _capacity_report(
    np: Any,
    entries: Sequence[Dict[str, Any]],
    initial_capital: float,
) -> Dict[str, Any]:
    participations = sorted(
        _f(row.get("adv_participation_pct"))
        for row in entries
        if row.get("adv_participation_pct") is not None
        and _f(row.get("adv_participation_pct")) >= 0
    )
    stress = []
    for capital in CAPACITY_STRESS_CAPITALS:
        scale = capital / max(initial_capital, 0.01)
        projected = [value * scale for value in participations]
        stress.append(
            {
                "account_capital": capital,
                "max_adv_participation_pct": round(max(projected, default=0.0), 6),
                "p95_adv_participation_pct": round(_percentile(np, projected, 95), 6),
                "entries_over_limit": sum(
                    1 for value in projected if value > CAPACITY_PARTICIPATION_LIMIT_PCT
                ),
                "entry_count": len(projected),
            }
        )
    limits = [
        initial_capital * CAPACITY_PARTICIPATION_LIMIT_PCT / value
        for value in participations if value > 0
    ]
    complete = len(participations) == len(entries)
    return {
        "status": "complete" if complete else "incomplete",
        "adv_basis": "signal_close_20_session_average_dollar_volume",
        "participation_limit_pct": CAPACITY_PARTICIPATION_LIMIT_PCT,
        "entry_count": len(entries),
        "entries_with_adv": len(participations),
        "max_observed_adv_participation_pct": round(max(participations, default=0.0), 6),
        "p95_observed_adv_participation_pct": round(_percentile(np, participations, 95), 6),
        "estimated_max_account_capital_at_limit": round(min(limits), 2) if limits else None,
        "stress": stress,
    }


def execution_diagnostics(
    sim: Dict[str, Any],
    *,
    np: Any,
    initial_capital: float,
) -> Dict[str, Any]:
    trades = _l(sim.get("trades"))
    entries = [row for row in trades if row.get("action") == "entry"]
    exits = [row for row in trades if row.get("action") == "exit"]
    curve = [_f(value) for value in _l(sim.get("equity_curve"))]
    dates = _l(sim.get("dates"))
    if not entries or not exits or not curve:
        return {"status": "insufficient_data", "entry_count": len(entries), "exit_count": len(exits)}
    entry_notional = sum(_f(row.get("gross_notional")) for row in entries)
    exit_notional = sum(_f(row.get("gross_notional")) for row in exits)
    gross_notional = entry_notional + exit_notional
    average_equity = sum(curve) / max(1, len(curve))
    years = max(1.0 / 252.0, len(dates) / 252.0)
    capacity = _capacity_report(np, entries, initial_capital)
    return {
        "status": capacity["status"],
        "entry_count": len(entries),
        "exit_count": len(exits),
        "transaction_cost_bps_per_side": _d(sim.get("assumptions")).get(
            "transaction_cost_bps_per_side"
        ),
        "total_fees": round(sum(_f(row.get("fee")) for row in trades), 2),
        "gross_entry_notional": round(entry_notional, 2),
        "gross_exit_notional": round(exit_notional, 2),
        "gross_traded_notional": round(gross_notional, 2),
        "average_equity": round(average_equity, 2),
        "full_period_turnover_x": round(gross_notional / max(average_equity, 0.01), 3),
        "annualized_turnover_x": round(gross_notional / max(average_equity, 0.01) / years, 3),
        "capacity": capacity,
        "concentration": _concentration_report(exits),
    }


def _metric_snapshot(sim: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _d(sim.get("metrics"))
    return {
        key: metrics.get(key)
        for key in (
            "status", "total_return_pct", "cagr_pct", "max_drawdown_pct",
            "sharpe", "profit_factor", "win_rate_pct", "trades",
            "average_exposure_pct", "time_in_market_pct",
        )
    }


def sensitivity_report(
    simulate: Callable[..., Dict[str, Any]],
    features: Dict[str, Any],
    dates: Sequence[Any],
    regime_map: Dict[str, Dict[str, Any]],
    *,
    baseline_cost_bps: float,
    baseline_sim: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    baseline = baseline_sim or simulate(features, regime_map, dates)
    costs = []
    for bps in COST_SENSITIVITY_BPS:
        sim = baseline if bps == baseline_cost_bps else simulate(
            features, regime_map, dates, transaction_cost_bps=bps
        )
        costs.append({"transaction_cost_bps_per_side": bps, **_metric_snapshot(sim)})
    delays = []
    for sessions in DELAY_SENSITIVITY_SESSIONS:
        sim = baseline if sessions == 1 else simulate(
            features, regime_map, dates, execution_delay_sessions=sessions
        )
        delays.append({"execution_delay_sessions": sessions, **_metric_snapshot(sim)})
    return {
        "status": "complete",
        "cost_scenarios": costs,
        "delay_scenarios": delays,
        "interpretation": (
            "Costs are charged per side. Delay scenarios preserve the signal and "
            "execute at a later session open; they do not refresh the signal."
        ),
    }


def validation_verdict(
    result: Dict[str, Any],
    *,
    profile_names: Sequence[str],
) -> Dict[str, Any]:
    missing: list[str] = []
    profiles = _d(result.get("profiles"))
    for name in profile_names:
        payload = _d(profiles.get(name))
        diagnostics = _d(payload.get("execution_diagnostics"))
        sensitivity = _d(payload.get("sensitivity"))
        if diagnostics.get("status") != "complete":
            missing.append(f"profiles.{name}.execution_diagnostics")
        if _d(diagnostics.get("capacity")).get("status") != "complete":
            missing.append(f"profiles.{name}.capacity")
        if len(_l(sensitivity.get("cost_scenarios"))) < len(COST_SENSITIVITY_BPS):
            missing.append(f"profiles.{name}.cost_sensitivity")
        if len(_l(sensitivity.get("delay_scenarios"))) < len(DELAY_SENSITIVITY_SESSIONS):
            missing.append(f"profiles.{name}.delay_sensitivity")
    ablation = _d(result.get("ablation"))
    if ablation.get("status") != "ok":
        missing.append("ablation")
    if _d(_d(ablation.get("best_variant")).get("execution_diagnostics")).get("status") != "complete":
        missing.append("ablation.best_variant.execution_diagnostics")
    if _d(ablation.get("best_variant_sensitivity")).get("status") != "complete":
        missing.append("ablation.best_variant_sensitivity")
    candidate = _d(ablation.get("best_variant_validation"))
    if candidate.get("status") != "complete":
        missing.append("ablation.best_variant_validation")
    if _d(candidate.get("walk_forward")).get("status") != "complete":
        missing.append("ablation.best_variant_validation.walk_forward")
    if not _d(candidate.get("calendar_years")):
        missing.append("ablation.best_variant_validation.calendar_years")
    if not _d(candidate.get("regime_report")):
        missing.append("ablation.best_variant_validation.regime_report")
    complete = not missing
    return {
        "status": "complete" if complete else "incomplete",
        "candidate_selection_evidence_complete": complete,
        "candidate_historical_validation_complete": complete,
        "automatic_strategy_promotion": False,
        "requires_forward_shadow_confirmation": True,
        "missing_or_incomplete": missing,
        "warning": (
            "Evidence completeness permits bounded candidate review only. It does not "
            "overcome survivorship, daily-bar, or inverse-ETF proxy limitations and does "
            "not authorize a runtime change."
        ),
    }
