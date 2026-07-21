"""Scanner v2 shadow universe, milestone 2.

Builds a broader candidate taxonomy for paper diagnostics only. It does not
mutate core.UNIVERSE, patch scan_signals, place orders, change thresholds,
change sizing, or grant ML/live authority.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, Iterable, List

VERSION = "scanner-v2-shadow-universe-2026-07-21-v2-leadership-clusters"
ENABLED = os.environ.get("SCANNER_V2_SHADOW_UNIVERSE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
REGISTERED_APP_IDS: set[int] = set()

SHADOW_BASKETS: Dict[str, List[str]] = {
    "ai_data_center_infrastructure": [
        "CRWV", "NVDA", "AMD", "AVGO", "SMCI", "VRT", "ANET", "DELL", "HPE", "CIEN",
        "ORCL", "NTNX", "DDOG", "NET", "MU", "STX", "WDC", "SNDK",
    ],
    "power_electrification": [
        "BE", "GEV", "VST", "CEG", "NRG", "ETN", "PWR", "EME", "FIX", "POWL", "IESC",
        "NUAI", "FLNC", "STEM", "EOSE",
    ],
    "semiconductor_power_and_components": [
        "NVTS", "ON", "MCHP", "MPWR", "ADI", "NXPI", "QCOM", "TXN", "WOLF", "ACLS", "UCTT",
        "AMAT", "LRCX", "KLAC", "ASML", "TER",
    ],
    "autonomy_drones_and_sensing": [
        "ONDS", "AVAV", "KTOS", "ACHR", "JOBY", "RKLB", "LUNR", "ASTS", "RDW", "BKSY",
        "CGNX", "SYM", "ZBRA",
    ],
    "robotics_automation": ["ROK", "TER", "CGNX", "PATH", "SYM", "ISRG", "ZBRA", "EMR", "HON", "ABB"],
    "defense_aerospace": ["LMT", "RTX", "NOC", "GD", "LHX", "HII", "KTOS", "AVAV", "LDOS", "BA"],
    "energy_leaders": ["XOM", "CVX", "COP", "EOG", "OXY", "SLB", "HAL", "FANG", "MPC", "VLO", "LNG", "XLE"],
    "precious_metals": ["GLD", "SLV", "GDX", "GDXJ", "IAU", "SIL", "NEM", "GOLD", "AEM", "WPM", "PAAS"],
    "healthcare_leaders": ["LLY", "UNH", "ABBV", "MRK", "AMGN", "GILD", "VRTX", "REGN", "TMO", "ISRG", "XLV"],
    "quantum_compute": ["IONQ", "RGTI", "QBTS", "QUBT", "ARQQ", "IBM", "GOOG", "MSFT"],
    "broad_index_liquid": ["SPY", "QQQ", "IWM", "DIA", "RSP", "SMH", "SOXX", "ARKK"],
}

CONFIRMED_MISSED_MOVERS = ["BE", "NVTS", "STX", "NUAI", "CRWV", "ONDS"]


def _unique(values: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values or []:
        symbol = str(value or "").upper().strip()
        if symbol and symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
    return output


def status_payload(core: Any = None) -> Dict[str, Any]:
    existing_universe = _unique(getattr(core, "UNIVERSE", []) or []) if core is not None else []
    shadow_symbols = _unique(symbol for symbols in SHADOW_BASKETS.values() for symbol in symbols)
    existing_set = set(existing_universe)
    overlap = [symbol for symbol in shadow_symbols if symbol in existing_set]
    new_shadow_candidates = [symbol for symbol in shadow_symbols if symbol not in existing_set]
    confirmed_overlap = [symbol for symbol in CONFIRMED_MISSED_MOVERS if symbol in existing_set]
    confirmed_outside = [symbol for symbol in CONFIRMED_MISSED_MOVERS if symbol not in existing_set]
    symbol_baskets = {
        symbol: [name for name, symbols in SHADOW_BASKETS.items() if symbol in symbols]
        for symbol in CONFIRMED_MISSED_MOVERS
    }
    return {
        "status": "ok",
        "overall": "pass",
        "type": "scanner_v2_shadow_universe_status",
        "version": VERSION,
        "generated_local": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "enabled": bool(ENABLED),
        "mode": "shadow_advisory_only",
        "basket_counts": {name: len(_unique(symbols)) for name, symbols in SHADOW_BASKETS.items()},
        "shadow_symbol_count": len(shadow_symbols),
        "current_universe_count": len(existing_universe),
        "overlap_count": len(overlap),
        "new_shadow_candidate_count": len(new_shadow_candidates),
        "overlap_symbols": overlap,
        "new_shadow_candidates": new_shadow_candidates,
        "confirmed_missed_movers": CONFIRMED_MISSED_MOVERS,
        "confirmed_missed_mover_baskets": symbol_baskets,
        "confirmed_missed_movers_in_universe": confirmed_overlap,
        "confirmed_missed_movers_outside_universe": confirmed_outside,
        "authority_changed": False,
        "core_universe_mutated": False,
        "scan_signals_patched": False,
        "does_not_trade": True,
        "does_not_lower_thresholds": True,
        "does_not_change_sizing": True,
        "does_not_change_risk_limits": True,
        "does_not_change_ml_authority": True,
        "does_not_grant_live_authority": True,
        "next_gate": "add shadow liquidity and opportunity scoring, then compare repeated post-close outcomes before any executable-universe promotion",
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return status_payload(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return status_payload(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/scanner-v2-shadow-universe-status" not in existing:
        flask_app.add_url_rule(
            "/paper/scanner-v2-shadow-universe-status",
            "scanner_v2_shadow_universe_status",
            lambda: jsonify(status_payload(core)),
        )
    REGISTERED_APP_IDS.add(id(flask_app))