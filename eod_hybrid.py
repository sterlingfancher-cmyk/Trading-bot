"""End-of-day hybrid allocation planner for the paper trading bot.

This module is intentionally registered from wsgi.py so it can be added without
rewriting the large app.py trading engine. It adds an EOD risk-on/risk-off core
allocator, strategy comparison endpoints, and ML-shadow/EOD plan logging.

The current trading engine remains the execution/risk-control authority. These
routes give a cleaner higher-timeframe plan so the next core-code pass can move
full-size entries toward late-session confirmation instead of 5-minute noise.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
from typing import Any, Dict, Iterable, List, Tuple

try:
    import pytz
except Exception:  # pragma: no cover
    pytz = None

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

try:
    from flask import jsonify
except Exception:  # pragma: no cover
    jsonify = None

VERSION = "eod-hybrid-allocator-2026-05-08"

# -----------------------------
# Config
# -----------------------------
MARKET_TZ_NAME = os.environ.get("MARKET_TZ", "America/Chicago")
REGULAR_OPEN_HOUR = int(os.environ.get("REGULAR_OPEN_HOUR", "8"))
REGULAR_OPEN_MINUTE = int(os.environ.get("REGULAR_OPEN_MINUTE", "30"))
REGULAR_CLOSE_HOUR = int(os.environ.get("REGULAR_CLOSE_HOUR", "15"))
REGULAR_CLOSE_MINUTE = int(os.environ.get("REGULAR_CLOSE_MINUTE", "0"))

EOD_HYBRID_ENABLED = os.environ.get("EOD_HYBRID_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
EOD_ALLOCATION_WINDOW_MINUTES = int(os.environ.get("EOD_ALLOCATION_WINDOW_MINUTES", "45"))
EOD_FULL_SIZE_ONLY_IN_WINDOW = os.environ.get("EOD_FULL_SIZE_ONLY_IN_WINDOW", "true").lower() not in ["0", "false", "no", "off"]
EOD_LOG_TO_STATE = os.environ.get("EOD_LOG_TO_STATE", "true").lower() not in ["0", "false", "no", "off"]
EOD_HISTORY_LIMIT = int(os.environ.get("EOD_HISTORY_LIMIT", "120"))

EOD_QQQ_DRAWDOWN_RISK_OFF = float(os.environ.get("EOD_QQQ_DRAWDOWN_RISK_OFF", "0.0175"))
EOD_IBIT_DRAWDOWN_RISK_OFF = float(os.environ.get("EOD_IBIT_DRAWDOWN_RISK_OFF", "0.0200"))
EOD_RISK_ON_QQQ_MIN_5D = float(os.environ.get("EOD_RISK_ON_QQQ_MIN_5D", "0.0100"))
EOD_RISK_ON_SPY_MIN_5D = float(os.environ.get("EOD_RISK_ON_SPY_MIN_5D", "0.0040"))
EOD_QQQ_SPY_LEADERSHIP_EDGE = float(os.environ.get("EOD_QQQ_SPY_LEADERSHIP_EDGE", "0.0050"))
EOD_METALS_SAFE_HAVEN_MIN_5D = float(os.environ.get("EOD_METALS_SAFE_HAVEN_MIN_5D", "0.0125"))
EOD_VIX_RISING_5D = float(os.environ.get("EOD_VIX_RISING_5D", "0.0250"))
EOD_MAX_PLAN_POSITIONS = int(os.environ.get("EOD_MAX_PLAN_POSITIONS", "12"))

STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME)) if STATE_DIR else STATE_FILENAME

# Baskets aligned with the user's existing expanded universe and Composer-style logic.
BASKETS: Dict[str, List[str]] = {
    "semi_leaders": ["NVDA", "AMD", "AVGO", "TSM", "MU", "ARM", "MRVL", "ON", "ALAB", "ACLS", "UCTT", "TER"],
    "mega_cap_ai": ["MSFT", "AMZN", "GOOGL", "META", "PLTR"],
    "data_center_infra": ["SMCI", "ANET", "DELL", "HPE", "CIEN", "GLW", "COHR", "LITE", "AAOI", "WDC", "STX", "VRT", "ETN", "PWR", "GEV"],
    "bitcoin_ai_compute": ["HUT", "IREN", "CIFR", "WULF", "CLSK", "MARA", "RIOT", "BTDR", "CORZ", "APLD"],
    "small_cap_momentum": ["SOUN", "RGTI", "QBTS", "IONQ", "RKLB", "JOBY", "ACHR", "RXRX", "TEM", "BBAI", "AI"],
    "precious_metals": ["GLD", "IAU", "PHYS", "SLV", "PSLV", "GDX", "GDXJ", "SIL", "SILJ", "NEM", "GOLD", "AEM", "WPM", "FNV", "RGLD", "PAAS", "AG", "HL", "CDE"],
    "dividend_defensive": ["SCHD", "VYM", "DGRO", "VIG", "SDY", "FDVV", "EYLD"],
    "defense_industrial": ["HWM", "BWXT", "KTOS", "MTZ", "CAT", "GEV", "PWR", "ETN"],
    "benchmark_etf": ["SPY", "QQQ"],
    "tactical_hedges": ["SQQQ", "SH", "PSQ", "RGTZ", "IONZ"],
}

CORE_SYMBOLS = list(dict.fromkeys(
    ["SPY", "QQQ", "IBIT", "^VIX", "UUP", "RSP", "IWM", "DIA", "ARKK", "GLD", "SLV", "GDX", "GDXJ"]
    + BASKETS["semi_leaders"][:8]
    + BASKETS["mega_cap_ai"]
    + BASKETS["data_center_infra"][:12]
    + BASKETS["bitcoin_ai_compute"][:8]
    + BASKETS["small_cap_momentum"][:8]
    + BASKETS["precious_metals"][:10]
    + BASKETS["dividend_defensive"]
    + BASKETS["defense_industrial"][:6]
))


def _tz_now() -> _dt.datetime:
    if pytz:
        tz = pytz.timezone(MARKET_TZ_NAME)
        return _dt.datetime.now(tz)
    return _dt.datetime.now()


def _fmt_now() -> str:
    try:
        return _tz_now().strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return _dt.datetime.now().isoformat(timespec="seconds")


def _today_key() -> str:
    return _tz_now().strftime("%Y-%m-%d")


def _market_clock() -> Dict[str, Any]:
    now = _tz_now()
    open_dt = now.replace(hour=REGULAR_OPEN_HOUR, minute=REGULAR_OPEN_MINUTE, second=0, microsecond=0)
    close_dt = now.replace(hour=REGULAR_CLOSE_HOUR, minute=REGULAR_CLOSE_MINUTE, second=0, microsecond=0)
    is_weekday = now.weekday() < 5
    is_open = bool(is_weekday and open_dt <= now <= close_dt)
    if not is_weekday:
        reason = "weekend"
    elif now < open_dt:
        reason = "before_regular_session"
    elif now > close_dt:
        reason = "after_regular_session"
    else:
        reason = "regular_session"
    minutes_to_close = max(0.0, (close_dt - now).total_seconds() / 60.0)
    minutes_since_open = max(0.0, (now - open_dt).total_seconds() / 60.0)
    in_eod_window = bool(is_open and minutes_to_close <= EOD_ALLOCATION_WINDOW_MINUTES)
    return {
        "is_open": is_open,
        "reason": reason,
        "now_local": _fmt_now(),
        "regular_open_local": open_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "regular_close_local": close_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "minutes_to_close": round(minutes_to_close, 2),
        "minutes_since_open": round(minutes_since_open, 2),
        "eod_allocation_window_minutes": EOD_ALLOCATION_WINDOW_MINUTES,
        "in_eod_allocation_window": in_eod_window,
        "timezone": MARKET_TZ_NAME,
    }


def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        directory = os.path.dirname(STATE_FILE)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def _clean_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        v = float(x)
        if v != v:  # nan
            return default
        return v
    except Exception:
        return default


def _safe_round(x: Any, ndigits: int = 4) -> float:
    return round(_clean_float(x), ndigits)


def _download_prices(symbols: Iterable[str], period: str = "3mo") -> Dict[str, List[float]]:
    if yf is None:
        return {}
    symbols = list(dict.fromkeys([s for s in symbols if s]))
    if not symbols:
        return {}
    out: Dict[str, List[float]] = {}
    try:
        data = yf.download(
            tickers=symbols,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
            group_by="ticker",
        )
        for sym in symbols:
            vals: List[float] = []
            try:
                # Multi-symbol group_by=ticker frame.
                if hasattr(data, "columns") and hasattr(data.columns, "levels") and sym in data.columns.get_level_values(0):
                    close = data[sym]["Close"]
                else:
                    close = data["Close"]
                for v in close.dropna().tolist():
                    vals.append(float(v))
            except Exception:
                vals = []
            if len(vals) >= 2:
                out[sym] = vals
    except Exception:
        # Fall back to individual calls so one failed symbol does not kill the endpoint.
        for sym in symbols:
            try:
                hist = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=True)
                vals = [float(v) for v in hist["Close"].dropna().tolist()]
                if len(vals) >= 2:
                    out[sym] = vals
            except Exception:
                continue
    return out


def _pct_change(vals: List[float], lookback_days: int) -> float:
    if not vals or len(vals) < 2:
        return 0.0
    idx = max(0, len(vals) - 1 - lookback_days)
    base = vals[idx]
    last = vals[-1]
    if base <= 0:
        return 0.0
    return (last / base) - 1.0


def _max_drawdown(vals: List[float], lookback_days: int) -> float:
    if not vals or len(vals) < 2:
        return 0.0
    window = vals[-max(2, lookback_days):]
    peak = window[0]
    max_dd = 0.0
    for v in window:
        peak = max(peak, v)
        if peak > 0:
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)
    return max_dd


def _basket_return(prices: Dict[str, List[float]], symbols: Iterable[str], lookback: int = 5) -> float:
    vals = []
    for sym in symbols:
        if sym in prices:
            vals.append(_pct_change(prices[sym], lookback))
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _rank_symbols(prices: Dict[str, List[float]], symbols: Iterable[str], lookback: int = 5, limit: int = 8) -> List[Dict[str, Any]]:
    rows = []
    for sym in symbols:
        vals = prices.get(sym)
        if not vals:
            continue
        ret = _pct_change(vals, lookback)
        dd = _max_drawdown(vals, min(lookback + 3, len(vals)))
        rows.append({"symbol": sym, "pct_5d": round(ret * 100, 2), "max_drawdown_pct": round(dd * 100, 2)})
    rows.sort(key=lambda r: (r["pct_5d"], -r["max_drawdown_pct"]), reverse=True)
    return rows[:limit]


def _risk_snapshot(prices: Dict[str, List[float]]) -> Dict[str, Any]:
    qqq_5d = _pct_change(prices.get("QQQ", []), 5)
    spy_5d = _pct_change(prices.get("SPY", []), 5)
    ibit_5d = _pct_change(prices.get("IBIT", []), 5)
    ibit_dd90 = _max_drawdown(prices.get("IBIT", []), 90)
    qqq_dd7 = _max_drawdown(prices.get("QQQ", []), 7)
    vix_5d = _pct_change(prices.get("^VIX", []), 5)
    uup_5d = _pct_change(prices.get("UUP", []), 5)
    rsp_5d = _pct_change(prices.get("RSP", []), 5)
    metals_5d = _basket_return(prices, ["GLD", "SLV", "GDX", "GDXJ"], 5)
    miners_5d = _basket_return(prices, ["GDX", "GDXJ"], 5)
    breadth_edge = qqq_5d - rsp_5d

    risk_on_score = 0
    risk_off_score = 0
    reasons_on: List[str] = []
    reasons_off: List[str] = []

    if qqq_5d >= EOD_RISK_ON_QQQ_MIN_5D:
        risk_on_score += 1
        reasons_on.append("QQQ 5-day trend positive")
    if spy_5d >= EOD_RISK_ON_SPY_MIN_5D:
        risk_on_score += 1
        reasons_on.append("SPY 5-day trend positive")
    if qqq_5d - spy_5d >= EOD_QQQ_SPY_LEADERSHIP_EDGE:
        risk_on_score += 1
        reasons_on.append("QQQ leading SPY")
    if breadth_edge >= EOD_QQQ_SPY_LEADERSHIP_EDGE:
        risk_on_score += 1
        reasons_on.append("tech/growth leadership confirmed")
    if ibit_5d > 0:
        risk_on_score += 1
        reasons_on.append("crypto/IBIT risk appetite positive")

    if qqq_dd7 >= EOD_QQQ_DRAWDOWN_RISK_OFF:
        risk_off_score += 2
        reasons_off.append("QQQ 7-day drawdown risk-off trigger")
    if ibit_dd90 >= EOD_IBIT_DRAWDOWN_RISK_OFF:
        risk_off_score += 1
        reasons_off.append("IBIT 90-day drawdown risk-off trigger")
    if vix_5d >= EOD_VIX_RISING_5D:
        risk_off_score += 1
        reasons_off.append("VIX rising")
    if metals_5d >= EOD_METALS_SAFE_HAVEN_MIN_5D and (uup_5d <= 0.002 or vix_5d > 0):
        risk_off_score += 1
        reasons_off.append("precious metals safe-haven bid")
    if qqq_5d < 0 and spy_5d < 0:
        risk_off_score += 2
        reasons_off.append("SPY/QQQ both negative")

    if risk_off_score >= 3 and risk_off_score > risk_on_score:
        regime = "risk_off"
    elif risk_on_score >= 3 and risk_on_score >= risk_off_score:
        regime = "risk_on"
    else:
        regime = "neutral"

    return {
        "regime": regime,
        "risk_on_score": risk_on_score,
        "risk_off_score": risk_off_score,
        "risk_on_reasons": reasons_on,
        "risk_off_reasons": reasons_off,
        "qqq_5d_pct": round(qqq_5d * 100, 2),
        "spy_5d_pct": round(spy_5d * 100, 2),
        "qqq_vs_spy_5d_pct": round((qqq_5d - spy_5d) * 100, 2),
        "rsp_5d_pct": round(rsp_5d * 100, 2),
        "qqq_vs_rsp_5d_pct": round(breadth_edge * 100, 2),
        "qqq_7d_max_drawdown_pct": round(qqq_dd7 * 100, 2),
        "ibit_5d_pct": round(ibit_5d * 100, 2),
        "ibit_90d_max_drawdown_pct": round(ibit_dd90 * 100, 2),
        "vix_5d_pct": round(vix_5d * 100, 2),
        "uup_5d_pct": round(uup_5d * 100, 2),
        "metals_5d_pct": round(metals_5d * 100, 2),
        "miners_5d_pct": round(miners_5d * 100, 2),
    }


def _allocation_for_regime(regime: str, clock: Dict[str, Any]) -> Dict[str, Any]:
    # Percentages are model targets, not orders. Existing risk controls remain authoritative.
    if regime == "risk_off":
        targets = {
            "precious_metals": 35.0,
            "dividend_defensive": 20.0,
            "defense_industrial": 10.0,
            "benchmark_etf": 5.0,
            "tactical_hedges": 5.0,
            "cash": 25.0,
        }
    elif regime == "risk_on":
        targets = {
            "semi_leaders": 22.0,
            "data_center_infra": 20.0,
            "mega_cap_ai": 18.0,
            "bitcoin_ai_compute": 8.0,
            "small_cap_momentum": 5.0,
            "benchmark_etf": 12.0,
            "precious_metals": 5.0,
            "cash": 10.0,
        }
    else:
        targets = {
            "semi_leaders": 12.5,
            "data_center_infra": 12.5,
            "mega_cap_ai": 10.0,
            "benchmark_etf": 12.5,
            "precious_metals": 22.5,
            "dividend_defensive": 12.5,
            "cash": 17.5,
        }

    if clock.get("is_open") and not clock.get("in_eod_allocation_window") and EOD_FULL_SIZE_ONLY_IN_WINDOW:
        return {
            "mode": "intraday_tactical_only",
            "targets_pct": {"tactical_intraday_starters": 15.0, "cash_reserved_for_eod_confirmation": 85.0},
            "execution_note": "Before the EOD allocation window, use only small tactical entries; reserve full-size basket allocation for closing confirmation.",
        }

    return {
        "mode": f"eod_core_{regime}",
        "targets_pct": targets,
        "execution_note": "Use the last 30-45 minutes or after-close review for basket allocation planning; existing risk controls still control entries/exits.",
    }


def _state_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    perf = state.get("performance", {}) or {}
    risk = state.get("risk_controls", {}) or {}
    feedback = state.get("feedback_loop", {}) or {}
    positions = state.get("positions", {}) or {}
    trades = state.get("trades", state.get("recent_trades", [])) or []
    return {
        "equity": _safe_round(state.get("equity", 10000.0), 2),
        "cash": _safe_round(state.get("cash", 0.0), 2),
        "open_positions": list(positions.keys()) if isinstance(positions, dict) else [],
        "position_count": len(positions) if isinstance(positions, dict) else 0,
        "trades_logged": len(trades) if isinstance(trades, list) else 0,
        "realized_pnl_today": _safe_round(perf.get("realized_pnl_today", state.get("realized_pnl", {}).get("today", 0.0)), 2),
        "unrealized_pnl": _safe_round(perf.get("unrealized_pnl", 0.0), 2),
        "wins_today": int(_clean_float(perf.get("wins_today", state.get("realized_pnl", {}).get("wins_today", 0)), 0)),
        "losses_today": int(_clean_float(perf.get("losses_today", state.get("realized_pnl", {}).get("losses_today", 0)), 0)),
        "day_pnl_pct": _safe_round(risk.get("day_pnl_pct", 0.0), 3),
        "intraday_drawdown_pct": _safe_round(risk.get("intraday_drawdown_pct", 0.0), 3),
        "self_defense_mode": bool(feedback.get("self_defense_mode") or risk.get("self_defense_active")),
        "profit_guard_active": bool(risk.get("profit_guard_active")),
        "risk_halted": bool(risk.get("halted")),
    }


def _build_action_plan(regime: str, clock: Dict[str, Any], risk: Dict[str, Any], state_summary: Dict[str, Any]) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []
    do_not_do = [
        "Do not let ML influence live trades until Phase 2/3 evidence exists.",
        "Do not chase names that are already extended above intraday moving averages.",
        "Do not override self-defense after clustered stop-losses.",
    ]

    if not clock.get("is_open"):
        actions.append({
            "priority": 10,
            "category": "market_clock",
            "action": "Use this period for review, EOD allocation planning, and next-session watchlist only.",
            "reason": f"Market is {clock.get('reason')}.",
            "urgency": "normal",
        })
    elif clock.get("in_eod_allocation_window"):
        actions.append({
            "priority": 10,
            "category": "eod_allocator",
            "action": "Allow the EOD core allocator to determine the main basket plan for the next session.",
            "reason": "Inside the late-session confirmation window.",
            "urgency": "high",
        })
    else:
        actions.append({
            "priority": 10,
            "category": "intraday_noise_control",
            "action": "Keep intraday entries tactical and smaller; reserve full allocation for EOD confirmation.",
            "reason": "Main underperformance has come from 5-minute noise and clustered stop-outs.",
            "urgency": "high",
        })

    if state_summary.get("self_defense_mode") or state_summary.get("losses_today", 0) >= 2:
        actions.append({
            "priority": 15,
            "category": "self_defense",
            "action": "Manage existing positions only; do not open fresh full-size entries until self-defense clears.",
            "reason": "Clustered stop-losses mean intraday execution quality is weak.",
            "urgency": "high",
        })

    if regime == "risk_on":
        actions.append({
            "priority": 20,
            "category": "risk_on_allocation",
            "action": "Favor semis, AI mega-cap, data-center infrastructure, and selected bitcoin/compute names at EOD confirmation.",
            "reason": ", ".join(risk.get("risk_on_reasons", [])[:3]) or "risk-on score leads risk-off score.",
            "urgency": "normal",
        })
    elif regime == "risk_off":
        actions.append({
            "priority": 20,
            "category": "risk_off_allocation",
            "action": "Favor precious metals, dividend/defensive baskets, cash, and limited tactical hedges.",
            "reason": ", ".join(risk.get("risk_off_reasons", [])[:3]) or "risk-off score leads risk-on score.",
            "urgency": "normal",
        })
    else:
        actions.append({
            "priority": 20,
            "category": "neutral_allocation",
            "action": "Use a balanced book: partial tech leadership, precious metals, dividend defense, and cash.",
            "reason": "Risk-on and risk-off evidence is mixed.",
            "urgency": "normal",
        })

    actions.append({
        "priority": 30,
        "category": "ml_phase",
        "action": "Keep ML in Phase 1 shadow logging; add EOD plan rows to the ML dataset for later Phase 2 missed-winner analysis.",
        "reason": "Live ML requires 100+ scanner opportunities and 2-4 weeks of paper evidence.",
        "urgency": "normal",
    })

    actions.sort(key=lambda a: a.get("priority", 999))
    return {
        "mode": "selective_eod_allocator" if not state_summary.get("self_defense_mode") else "manage_only_until_self_defense_clears",
        "top_actions": actions[:5],
        "all_actions": actions,
        "do_not_do": do_not_do,
        "watch_next": [
            "Does EOD regime match next-session opening behavior?",
            "Do stopped-out intraday names recover by the close, proving stops are too tight?",
            "Which buckets rank best at close: semis, data-center, bitcoin/compute, metals, or defensive dividends?",
            "Do ML feature rows include both intraday scanner decisions and EOD allocator plan rows?",
        ],
        "generated_local": _fmt_now(),
    }


def _build_plan(write_state: bool = True) -> Dict[str, Any]:
    clock = _market_clock()
    state = _load_state()
    prices = _download_prices(CORE_SYMBOLS, period="3mo")
    risk = _risk_snapshot(prices)
    allocation = _allocation_for_regime(risk["regime"], clock)
    state_sum = _state_summary(state)

    ranked = {
        "semi_leaders": _rank_symbols(prices, BASKETS["semi_leaders"], 5, 6),
        "data_center_infra": _rank_symbols(prices, BASKETS["data_center_infra"], 5, 6),
        "mega_cap_ai": _rank_symbols(prices, BASKETS["mega_cap_ai"], 5, 5),
        "bitcoin_ai_compute": _rank_symbols(prices, BASKETS["bitcoin_ai_compute"], 5, 5),
        "small_cap_momentum": _rank_symbols(prices, BASKETS["small_cap_momentum"], 5, 5),
        "precious_metals": _rank_symbols(prices, BASKETS["precious_metals"], 5, 6),
        "dividend_defensive": _rank_symbols(prices, BASKETS["dividend_defensive"], 5, 5),
        "defense_industrial": _rank_symbols(prices, BASKETS["defense_industrial"], 5, 5),
    }

    candidate_symbols: List[str] = []
    for bucket, pct in allocation.get("targets_pct", {}).items():
        if bucket == "cash" or bucket == "cash_reserved_for_eod_confirmation":
            continue
        for row in ranked.get(bucket, [])[:3]:
            candidate_symbols.append(row["symbol"])
    candidate_symbols = list(dict.fromkeys(candidate_symbols))[:EOD_MAX_PLAN_POSITIONS]

    action_plan = _build_action_plan(risk["regime"], clock, risk, state_sum)
    plan = {
        "status": "ok",
        "type": "eod_hybrid_allocation_plan",
        "version": VERSION,
        "enabled": EOD_HYBRID_ENABLED,
        "generated_local": _fmt_now(),
        "market_clock": clock,
        "risk_state": risk,
        "allocation": allocation,
        "candidate_symbols": candidate_symbols,
        "ranked_buckets": ranked,
        "state_summary": state_sum,
        "recommended_action_plan": action_plan,
        "implementation_note": "This is the higher-timeframe allocation brain. It is currently advisory/plan-first; existing app.py risk controls and trade engine remain authoritative until the next core-engine integration pass.",
        "risk_control_changes_for_next_session": [
            "Reserve full-size entries for the EOD allocation window or next-session confirmation.",
            "Keep intraday entries small and tactical unless a pullback/reclaim setup confirms.",
            "Use wider volatility-aware stops with smaller allocation for high-beta themes instead of tight flat stops.",
            "Log EOD allocator decisions into ML shadow data so Phase 2 can compare rules-only vs hybrid allocation.",
            "Compare daily performance against the Composer-style risk-on/risk-off benchmark before increasing automation authority.",
        ],
    }

    if EOD_LOG_TO_STATE and write_state:
        try:
            state.setdefault("eod_hybrid", {})["latest_plan"] = plan
            history = state.setdefault("eod_hybrid", {}).setdefault("history", [])
            slim = {
                "date": _today_key(),
                "generated_local": plan["generated_local"],
                "regime": risk["regime"],
                "allocation_mode": allocation.get("mode"),
                "risk_on_score": risk.get("risk_on_score"),
                "risk_off_score": risk.get("risk_off_score"),
                "candidate_symbols": candidate_symbols,
                "state_summary": state_sum,
            }
            history.append(slim)
            state["eod_hybrid"]["history"] = history[-EOD_HISTORY_LIMIT:]
            ml_log = state.setdefault("ml_eod_shadow_log", [])
            ml_log.append({
                "date": _today_key(),
                "generated_local": plan["generated_local"],
                "event": "eod_allocation_plan",
                "regime": risk["regime"],
                "targets_pct": allocation.get("targets_pct", {}),
                "candidate_symbols": candidate_symbols,
                "rule_system_snapshot": state_sum,
                "live_trade_decider": False,
                "ml_phase": "phase_1_shadow_logging",
            })
            state["ml_eod_shadow_log"] = ml_log[-EOD_HISTORY_LIMIT:]
            _save_state(state)
        except Exception:
            pass

    return plan


def _strategy_comparison() -> Dict[str, Any]:
    state = _load_state()
    latest = state.get("eod_hybrid", {}).get("latest_plan")
    if not latest:
        latest = _build_plan(write_state=False)
    state_sum = _state_summary(state)
    journal = state.get("journal", {}) if isinstance(state.get("journal"), dict) else {}
    scanner = state.get("scanner_audit", {}) if isinstance(state.get("scanner_audit"), dict) else {}
    comparison = {
        "status": "ok",
        "type": "strategy_comparison",
        "version": VERSION,
        "generated_local": _fmt_now(),
        "summary": {
            "rules_only_intraday_bot": "Current engine can find strong themes, but may get chopped by 5-minute path volatility and clustered stop-losses.",
            "eod_risk_on_risk_off_allocator": "Composer-style allocator waits for broader market confirmation and should reduce intraday noise exposure.",
            "hybrid_model": "Use intraday scanner for small tactical starters and EOD allocator for main basket planning.",
        },
        "current_rule_system_snapshot": state_sum,
        "latest_eod_plan": {
            "regime": latest.get("risk_state", {}).get("regime"),
            "allocation_mode": latest.get("allocation", {}).get("mode"),
            "candidate_symbols": latest.get("candidate_symbols", []),
            "targets_pct": latest.get("allocation", {}).get("targets_pct", {}),
        },
        "what_to_measure_next": [
            "Daily P/L of rules-only intraday trades vs EOD allocator candidate basket.",
            "Stop-loss rate during first half of day vs last 45 minutes.",
            "Missed-winner rate for blocked names that closed strong.",
            "Bucket profit factor by semis, data center, bitcoin/compute, metals, small caps, and defensive dividends.",
            "Drawdown difference between all-day scanner entries and EOD basket allocation.",
        ],
        "journal_context": journal,
        "scanner_context": scanner,
        "recommended_next_code_step": "After several EOD plans are logged, integrate the allocator into app.py so full-size entries are restricted to EOD confirmation while intraday remains tactical.",
    }
    return comparison


def register_routes(flask_app: Any) -> None:
    """Register EOD hybrid endpoints on an existing Flask app."""
    if jsonify is None:
        return

    existing_rules = {str(rule) for rule in flask_app.url_map.iter_rules()}

    if "/paper/eod-hybrid-status" not in existing_rules:
        @flask_app.route("/paper/eod-hybrid-status")
        def paper_eod_hybrid_status():  # type: ignore
            state = _load_state()
            return jsonify({
                "status": "ok",
                "version": VERSION,
                "enabled": EOD_HYBRID_ENABLED,
                "generated_local": _fmt_now(),
                "market_clock": _market_clock(),
                "state_file": STATE_FILE,
                "latest_plan_present": bool(state.get("eod_hybrid", {}).get("latest_plan")),
                "history_count": len(state.get("eod_hybrid", {}).get("history", [])) if isinstance(state.get("eod_hybrid", {}), dict) else 0,
                "ml_eod_shadow_rows": len(state.get("ml_eod_shadow_log", [])) if isinstance(state.get("ml_eod_shadow_log"), list) else 0,
                "mode": "advisory_planner_plus_shadow_logging",
            })

    if "/paper/eod-allocation-plan" not in existing_rules:
        @flask_app.route("/paper/eod-allocation-plan")
        def paper_eod_allocation_plan():  # type: ignore
            return jsonify(_build_plan(write_state=True))

    if "/paper/strategy-comparison" not in existing_rules:
        @flask_app.route("/paper/strategy-comparison")
        def paper_strategy_comparison():  # type: ignore
            return jsonify(_strategy_comparison())

    if "/paper/next-session-watchlist" not in existing_rules:
        @flask_app.route("/paper/next-session-watchlist")
        def paper_next_session_watchlist():  # type: ignore
            plan = _build_plan(write_state=True)
            return jsonify({
                "status": "ok",
                "type": "next_session_watchlist",
                "version": VERSION,
                "generated_local": _fmt_now(),
                "regime": plan.get("risk_state", {}).get("regime"),
                "allocation_mode": plan.get("allocation", {}).get("mode"),
                "candidate_symbols": plan.get("candidate_symbols", []),
                "ranked_buckets": plan.get("ranked_buckets", {}),
                "rules": [
                    "Prefer names that stay strong into the close.",
                    "Use intraday names as small tactical starters only before EOD confirmation.",
                    "Do not add full-size risk after self-defense or clustered stop-losses.",
                    "Let precious metals compete when the metals state is safe-haven bid or risk-off.",
                ],
            })

    if "/paper/eod-backtest-readiness" not in existing_rules:
        @flask_app.route("/paper/eod-backtest-readiness")
        def paper_eod_backtest_readiness():  # type: ignore
            state = _load_state()
            rows = state.get("ml_eod_shadow_log", []) if isinstance(state.get("ml_eod_shadow_log"), list) else []
            scanner_rows = 0
            try:
                ml_review = state.get("ml_shadow", {}) if isinstance(state.get("ml_shadow"), dict) else {}
                scanner_rows = int(ml_review.get("rows_logged", 0) or 0)
            except Exception:
                scanner_rows = 0
            return jsonify({
                "status": "ok",
                "type": "eod_backtest_readiness",
                "version": VERSION,
                "generated_local": _fmt_now(),
                "eod_shadow_rows": len(rows),
                "scanner_shadow_rows": scanner_rows,
                "ready_for_phase_2_review": bool(len(rows) >= 5 or scanner_rows >= 100),
                "ready_for_live_ml_decisions": False,
                "reason": "EOD allocator can be reviewed after several logged sessions; live ML still requires walk-forward evidence and 2-4 weeks of paper data.",
                "next_thresholds": {
                    "minimum_eod_sessions_for_review": 5,
                    "minimum_scanner_rows_for_phase_2": 100,
                    "preferred_paper_data_before_ml_scoring": "2-4 weeks",
                },
            })


def _register_routes(flask_app: Any) -> None:
    # Alias used by wsgi.py pattern.
    register_routes(flask_app)
