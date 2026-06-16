"""Hybrid paper-only market surge deployment mode.

Routes:
- /paper/market-surge-deployment-status
- /paper/market-surge-deployment-plan
- /paper/market-surge-deployment-execute?confirm=1
- /paper/market-surge-deployment-auto-fire
- /paper/market-surge-deployment-autofire

This module does not execute live trades, does not change ML authority, and
does not bypass risk controls. It allows larger paper-only deployment during
confirmed broad market surge conditions while requiring hard stops, trailing
stops, clean risk controls, and explicit execution controls.

The surge model is hybrid:
- individual stock leaders from the scanner get priority during surge windows
- ETFs remain as a broad-market anchor and fallback
- if no stock leader clears quality/price filters, the module falls back to
  the ETF surge basket instead of forcing weak single-name entries

Auto-fire is paper-only and intentionally narrow:
- regular market entry window only
- clean risk controls only
- confirmed broad market surge only
- high cash percentage only
- one successful auto-fire event per local trading day
- no averaging down and no live broker calls
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None  # type: ignore


VERSION = "market-surge-deployment-mode-2026-06-16-v3-hybrid-stock-leaders"
REGISTERED_APP_IDS: set[int] = set()

MAX_ACCOUNT_RISK_PER_ENTRY_PCT = 0.80
MAX_TOTAL_SURGE_DEPLOYMENT_TIER_2_PCT = 35.0
MAX_TOTAL_SURGE_DEPLOYMENT_TIER_3_PCT = 55.0

# Surge deployment now uses a stock-leader sleeve first, then an ETF anchor.
# If no stock leaders clear the filters, ETFs can still use the full surge cap
# as the safe broad-market fallback.
TIER_2_STOCK_LEADER_SHARE = 0.60
TIER_3_STOCK_LEADER_SHARE = 0.70
MAX_STOCK_LEADERS_TIER_2 = 4
MAX_STOCK_LEADERS_TIER_3 = 5
MIN_STOCK_LEADER_PRICE = 3.00
MIN_STOCK_LEADER_SCORE = 0.038
MIN_STOCK_LEADER_FALLBACK_SCORE = 0.032

MIN_CASH_PCT_FOR_SURGE_DEPLOYMENT = 55.0
MAX_OPEN_POSITIONS_AFTER_SURGE = 5

DEFAULT_STOP_LOSS_PCT = 3.5
DEFAULT_TRAILING_STOP_PCT = 2.25
DEFAULT_PROFIT_ACTIVATION_PCT = 1.5
DEFAULT_PROFIT_LOCK_PCT = 0.75

AUTO_FIRE_ENABLED = True
AUTO_FIRE_MAX_SUCCESSFUL_FIRES_PER_DAY = 1
AUTO_FIRE_ROUTE = "/paper/market-surge-deployment-auto-fire"
AUTO_FIRE_ALIAS_ROUTE = "/paper/market-surge-deployment-autofire"

CENTRAL_TZ_NAME = "America/Chicago"

SURGE_ETF_SYMBOLS = {"QQQ", "SPY", "SMH", "IWM", "IWO"}
ETF_EXCLUSION_UNIVERSE = {
    "SPY",
    "QQQ",
    "SMH",
    "IWM",
    "IWO",
    "DIA",
    "VTI",
    "VOO",
    "XLK",
    "XLF",
    "XLE",
    "XLI",
    "XLV",
    "XLY",
    "XLP",
    "XLC",
    "XLU",
    "XLB",
    "XLRE",
    "ARKK",
    "SOXX",
    "IBB",
    "GLD",
    "SLV",
    "TLT",
}


def _central_now() -> dt.datetime:
    if ZoneInfo is not None:
        return dt.datetime.now(ZoneInfo(CENTRAL_TZ_NAME))
    return dt.datetime.now()


def _now_text(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return _central_now().strftime("%Y-%m-%d %H:%M:%S %Z")


def _today(core: Any = None) -> str:
    text = _now_text(core)
    if text:
        return str(text).split(" ")[0]
    return _central_now().strftime("%Y-%m-%d")


def _is_regular_market_window(now: Optional[dt.datetime] = None) -> bool:
    current = now or _central_now()
    if current.weekday() >= 5:
        return False

    # US equities regular session in Central time is 8:30 AM to 3:00 PM.
    # Use a tighter entry window to avoid immediate open and close-lock entries.
    start = current.replace(hour=8, minute=40, second=0, microsecond=0)
    end = current.replace(hour=14, minute=45, second=0, microsecond=0)
    return start <= current <= end


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return int(float(value))
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _portfolio(core: Any = None) -> Dict[str, Any]:
    try:
        pf = getattr(core, "portfolio", None)
        if isinstance(pf, dict):
            return pf
    except Exception:
        pass

    try:
        state = core.load_state()
        if isinstance(state, dict):
            return state
    except Exception:
        pass

    return {}


def _load_state(core: Any = None) -> Dict[str, Any]:
    try:
        state = core.load_state()
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _positions(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    obj = pf.get("positions")
    if not isinstance(obj, dict):
        obj = state.get("positions")
    if not isinstance(obj, dict):
        obj = {}
    pf["positions"] = obj
    return obj


def _performance(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    obj = pf.get("performance")
    if not isinstance(obj, dict):
        obj = state.get("performance")
    if not isinstance(obj, dict):
        obj = {}
    pf["performance"] = obj
    return obj


def _risk_controls(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    obj = pf.get("risk_controls")
    if not isinstance(obj, dict):
        obj = state.get("risk_controls")
    if not isinstance(obj, dict):
        obj = {}
    pf["risk_controls"] = obj
    return obj


def _scanner_audit(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    obj = pf.get("scanner_audit")
    if not isinstance(obj, dict):
        obj = state.get("scanner_audit")
    return obj if isinstance(obj, dict) else {}


def _market_surge_state(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        pf.get("market_surge_aggression"),
        state.get("market_surge_aggression"),
        pf.get("paper_market_surge_aggression"),
        state.get("paper_market_surge_aggression"),
        pf.get("market_surge"),
        state.get("market_surge"),
    ]
    for obj in candidates:
        if isinstance(obj, dict):
            return obj
    return {}


def _save(core: Any, pf: Dict[str, Any]) -> Dict[str, Any]:
    attempted = False
    ok = False
    error = None

    try:
        save_fn = getattr(core, "save_state", None)
        if callable(save_fn):
            attempted = True
            try:
                save_fn(pf)
            except TypeError:
                save_fn()
            ok = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    return {
        "save_attempted": attempted,
        "save_ok": ok,
        "save_error": error,
    }


def _cash_equity(pf: Dict[str, Any], state: Dict[str, Any]) -> Tuple[float, float]:
    cash = _safe_float(pf.get("cash", state.get("cash", 0.0)))
    equity = _safe_float(pf.get("equity", state.get("equity", 0.0)))
    if equity <= 0.0:
        equity = cash
    return cash, equity


def _cash_pct(pf: Dict[str, Any], state: Dict[str, Any]) -> float:
    cash, equity = _cash_equity(pf, state)
    if equity <= 0.0:
        return 0.0
    return round((cash / equity) * 100.0, 4)


def _risk_clean(pf: Dict[str, Any], state: Dict[str, Any]) -> Tuple[bool, List[str]]:
    risk = _risk_controls(pf, state)
    perf = _performance(pf, state)
    reasons: List[str] = []

    daily_loss_pct = _safe_float(risk.get("daily_loss_pct"))
    daily_drawdown_pct = _safe_float(risk.get("daily_drawdown_pct"))
    intraday_drawdown_pct = _safe_float(risk.get("intraday_drawdown_pct"))

    if daily_loss_pct > 0.25:
        reasons.append(f"daily_loss_pct_not_clean:{daily_loss_pct}")
    if daily_drawdown_pct > 0.75:
        reasons.append(f"daily_drawdown_pct_not_clean:{daily_drawdown_pct}")
    if intraday_drawdown_pct > 0.75:
        reasons.append(f"intraday_drawdown_pct_not_clean:{intraday_drawdown_pct}")
    if _safe_bool(risk.get("halted"), False):
        reasons.append("risk_halted")
    if _safe_bool(risk.get("self_defense_active"), False):
        reasons.append("self_defense_active")

    losses_today = _safe_int(perf.get("losses_today"), 0)
    if losses_today >= 2:
        reasons.append(f"too_many_losses_today:{losses_today}")

    return len(reasons) == 0, reasons


def _get_price_from_mapping(symbol: str, obj: Any) -> float:
    if not isinstance(obj, dict):
        return 0.0

    raw = obj.get(symbol)
    if isinstance(raw, dict):
        for key in ("last_price", "price", "close", "last", "mark"):
            px = _safe_float(raw.get(key))
            if px > 0.0:
                return px
    else:
        px = _safe_float(raw)
        if px > 0.0:
            return px

    return 0.0


def _get_price(core: Any, pf: Dict[str, Any], state: Dict[str, Any], symbol: str) -> Tuple[float, str]:
    for name in (
        "get_latest_price",
        "get_last_price",
        "get_current_price",
        "get_price",
        "latest_price",
        "price",
    ):
        try:
            fn = getattr(core, name, None)
            if callable(fn):
                raw = fn(symbol)
                if isinstance(raw, dict):
                    for key in ("last_price", "price", "close", "last", "mark"):
                        px = _safe_float(raw.get(key))
                        if px > 0.0:
                            return px, f"core.{name}.{key}"
                else:
                    px = _safe_float(raw)
                    if px > 0.0:
                        return px, f"core.{name}"
        except Exception:
            continue

    for container_name, container in (("portfolio", pf), ("state", state)):
        for key in (
            "prices",
            "last_prices",
            "latest_prices",
            "quotes",
            "quote_cache",
            "market_prices",
            "latest_market_prices",
        ):
            px = _get_price_from_mapping(symbol, container.get(key))
            if px > 0.0:
                return px, f"{container_name}.{key}"

    surge = _market_surge_state(pf, state)
    for key in ("broad_context", "market_context", "symbol_context", "quotes", "prices"):
        px = _get_price_from_mapping(symbol, surge.get(key))
        if px > 0.0:
            return px, f"market_surge.{key}"

    return 0.0, "unavailable"


def _infer_surge_level(pf: Dict[str, Any], state: Dict[str, Any]) -> Tuple[int, List[str]]:
    surge = _market_surge_state(pf, state)
    scanner = _scanner_audit(pf, state)
    reasons: List[str] = []

    explicit_level = _safe_int(
        surge.get("surge_level", surge.get("level", surge.get("market_surge_level", 0))),
        0,
    )
    eligible_mode = _safe_bool(surge.get("eligible_mode"), False)

    if explicit_level >= 2 and eligible_mode:
        reasons.append(f"explicit_surge_level:{explicit_level}")
        reasons.append("eligible_mode:true")
        return min(explicit_level, 3), reasons
    if explicit_level >= 2:
        reasons.append(f"explicit_surge_level:{explicit_level}")
        return min(explicit_level, 3), reasons

    market_mode = str(surge.get("market_mode", "") or "").lower()
    regime = str(surge.get("regime", "") or "").lower()

    if "risk_on" in market_mode or "bull" in regime:
        reasons.append(f"market_mode:{market_mode or regime}")
        return 2, reasons

    signals_found = _safe_int(
        scanner.get("signals_found", scanner.get("total_signals", scanner.get("signals", 0))),
        0,
    )
    blocked_entries = _safe_int(
        scanner.get("blocked_entries_count", scanner.get("blocked_entries", 0)),
        0,
    )

    if signals_found >= 35 and blocked_entries == 0:
        reasons.append(f"scanner_activity:{signals_found}")
        return 2, reasons

    reasons.append("no_confirmed_broad_surge")
    return 0, reasons


def _max_total_deployment_pct(surge_level: int) -> float:
    if surge_level >= 3:
        return MAX_TOTAL_SURGE_DEPLOYMENT_TIER_3_PCT
    if surge_level >= 2:
        return MAX_TOTAL_SURGE_DEPLOYMENT_TIER_2_PCT
    return 0.0


def _stock_leader_share(surge_level: int) -> float:
    if surge_level >= 3:
        return TIER_3_STOCK_LEADER_SHARE
    if surge_level >= 2:
        return TIER_2_STOCK_LEADER_SHARE
    return 0.0


def _max_stock_leaders(surge_level: int) -> int:
    if surge_level >= 3:
        return MAX_STOCK_LEADERS_TIER_3
    if surge_level >= 2:
        return MAX_STOCK_LEADERS_TIER_2
    return 0


def _base_symbol_weights(surge_level: int) -> List[Tuple[str, float]]:
    if surge_level >= 3:
        return [
            ("QQQ", 20.0),
            ("SPY", 15.0),
            ("SMH", 10.0),
            ("IWM", 7.5),
        ]

    if surge_level >= 2:
        return [
            ("QQQ", 20.0),
            ("SPY", 10.0),
            ("SMH", 5.0),
        ]

    return []


def _scaled_etf_anchor_weights(surge_level: int, stock_leaders_available: bool) -> List[Tuple[str, float]]:
    base = _base_symbol_weights(surge_level)
    if not base:
        return []

    max_total = _max_total_deployment_pct(surge_level)
    if max_total <= 0.0:
        return []

    # If no individual stock leader clears filters, ETFs can use the original
    # surge basket as a fallback. Otherwise ETFs are intentionally smaller.
    if not stock_leaders_available:
        return base

    stock_share = _stock_leader_share(surge_level)
    anchor_target = max_total * max(0.0, min(1.0, 1.0 - stock_share))
    base_total = sum(weight for _, weight in base)
    if base_total <= 0.0:
        return []

    scale = anchor_target / base_total
    return [(symbol, round(weight * scale, 4)) for symbol, weight in base]


def _signal_symbol(signal: Dict[str, Any]) -> str:
    for key in ("symbol", "ticker", "asset", "name"):
        value = str(signal.get(key, "") or "").upper().strip()
        if value:
            return value
    return ""


def _signal_score(signal: Dict[str, Any]) -> float:
    keys = (
        "score",
        "signal_score",
        "quality_score",
        "rank_score",
        "composite_score",
        "momentum_score",
        "relative_strength_score",
        "rs_score",
    )
    return max(_safe_float(signal.get(key), 0.0) for key in keys)


def _signal_flag(signal: Dict[str, Any], *keys: str) -> bool:
    for key in keys:
        if _safe_bool(signal.get(key), False):
            return True
    return False


def _normalise_signal_item(item: Any, source: str) -> Dict[str, Any] | None:
    if isinstance(item, dict):
        signal = dict(item)
    elif isinstance(item, str):
        signal = {"symbol": item}
    else:
        return None

    symbol = _signal_symbol(signal)
    if not symbol:
        return None
    signal["symbol"] = symbol
    signal.setdefault("source", source)
    return signal


def _extend_signal_pool(pool: List[Dict[str, Any]], obj: Any, source: str) -> None:
    if isinstance(obj, list):
        for item in obj:
            signal = _normalise_signal_item(item, source)
            if signal:
                pool.append(signal)
        return

    if isinstance(obj, tuple):
        for item in obj:
            signal = _normalise_signal_item(item, source)
            if signal:
                pool.append(signal)
        return

    if isinstance(obj, dict):
        # Some containers are symbol->metadata maps.
        for key, value in obj.items():
            if isinstance(value, dict):
                signal = dict(value)
                signal.setdefault("symbol", key)
                signal.setdefault("source", source)
                normalised = _normalise_signal_item(signal, source)
                if normalised:
                    pool.append(normalised)


def _scanner_signal_pool(pf: Dict[str, Any], state: Dict[str, Any]) -> List[Dict[str, Any]]:
    pool: List[Dict[str, Any]] = []
    scanner = _scanner_audit(pf, state)
    surge = _market_surge_state(pf, state)

    containers = [
        ("portfolio", pf),
        ("state", state),
        ("scanner_audit", scanner),
        ("market_surge", surge),
    ]

    keys = (
        "long_signals",
        "short_signals",
        "scanner_signals",
        "signals",
        "ranked_signals",
        "candidate_signals",
        "candidates",
        "top_candidates",
        "top_scanner_candidates",
        "top_blocked_candidates",
        "blocked_candidates",
        "blocked_entries",
        "top_blocked_symbols",
        "candidate_symbols",
        "leader_symbols",
        "surge_leaders",
        "relative_strength_leaders",
        "breakout_candidates",
    )

    for source, container in containers:
        if not isinstance(container, dict):
            continue
        for key in keys:
            _extend_signal_pool(pool, container.get(key), f"{source}.{key}")

    # Dedupe by symbol, keeping the highest-score version when possible.
    deduped: Dict[str, Dict[str, Any]] = {}
    for signal in pool:
        symbol = _signal_symbol(signal)
        if not symbol:
            continue
        prev = deduped.get(symbol)
        if prev is None or _signal_score(signal) > _signal_score(prev):
            deduped[symbol] = signal

    return list(deduped.values())


def _compact_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "symbol",
        "source",
        "score",
        "signal_score",
        "quality_score",
        "momentum_score",
        "relative_strength_score",
        "rs_score",
        "volume_ratio",
        "relative_volume",
        "change_pct",
        "pct_change",
        "sector",
        "reason",
    )
    return {key: signal.get(key) for key in keys if key in signal}


def _rank_stock_leaders(
    core: Any,
    pf: Dict[str, Any],
    state: Dict[str, Any],
    existing_symbols: set[str],
    surge_level: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    reviewed: List[Dict[str, Any]] = []
    leaders: List[Dict[str, Any]] = []

    for signal in _scanner_signal_pool(pf, state):
        symbol = _signal_symbol(signal)
        if not symbol:
            continue

        reason = ""
        if symbol in existing_symbols:
            reason = "already_open"
        elif symbol in ETF_EXCLUSION_UNIVERSE:
            reason = "etf_anchor_or_etf_excluded_from_stock_leaders"
        elif not symbol.replace(".", "").replace("-", "").isalnum():
            reason = "invalid_symbol_format"

        price, price_source = _get_price(core, pf, state, symbol)
        score = _signal_score(signal)
        relative_strength = _signal_flag(
            signal,
            "relative_strength",
            "rs_leader",
            "relative_strength_leader",
            "is_relative_strength",
        )
        breakout = _signal_flag(
            signal,
            "breakout",
            "is_breakout",
            "breakout_signal",
            "is_breakout_signal",
        )
        volume_confirmed = _signal_flag(
            signal,
            "volume_confirmed",
            "relative_volume_confirmed",
            "volume_surge",
            "volume_breakout",
        )

        if not reason and price <= 0.0:
            reason = "missing_price"
        if not reason and price < MIN_STOCK_LEADER_PRICE:
            reason = f"price_below_minimum:{price}"

        quality_ok = (
            score >= MIN_STOCK_LEADER_SCORE
            or (
                score >= MIN_STOCK_LEADER_FALLBACK_SCORE
                and (relative_strength or breakout or volume_confirmed)
            )
            or (
                surge_level >= 3
                and score >= MIN_STOCK_LEADER_FALLBACK_SCORE
                and (relative_strength or breakout)
            )
        )

        if not reason and not quality_ok:
            reason = "stock_leader_quality_not_confirmed"

        row = {
            "symbol": symbol,
            "price": round(price, 6),
            "price_source": price_source,
            "score": round(score, 6),
            "relative_strength": relative_strength,
            "breakout": breakout,
            "volume_confirmed": volume_confirmed,
            "source": signal.get("source"),
            "reason": "selected_stock_surge_leader" if not reason else reason,
            "signal": _compact_signal(signal),
        }
        reviewed.append(row)

        if not reason:
            leaders.append(row)

    leaders = sorted(
        leaders,
        key=lambda row: (
            _safe_float(row.get("score")),
            1 if row.get("relative_strength") else 0,
            1 if row.get("breakout") else 0,
            1 if row.get("volume_confirmed") else 0,
        ),
        reverse=True,
    )

    reviewed = sorted(
        reviewed,
        key=lambda row: (
            1 if row.get("reason") == "selected_stock_surge_leader" else 0,
            _safe_float(row.get("score")),
        ),
        reverse=True,
    )

    return leaders, reviewed[:20]


def _planned_entry(
    core: Any,
    pf: Dict[str, Any],
    state: Dict[str, Any],
    symbol: str,
    allocation_pct: float,
    total_equity: float,
    remaining_cash: float,
    *,
    bucket: str,
    selection_reason: str,
    score: float = 0.0,
    source_signal: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    price, price_source = _get_price(core, pf, state, symbol)
    stop_loss_pct = DEFAULT_STOP_LOSS_PCT

    max_allocation_by_risk = round(
        MAX_ACCOUNT_RISK_PER_ENTRY_PCT / (stop_loss_pct / 100.0),
        4,
    )

    capped_by_risk = False
    if allocation_pct > max_allocation_by_risk:
        allocation_pct = max_allocation_by_risk
        capped_by_risk = True

    allocation_dollars = round(total_equity * (allocation_pct / 100.0), 2)
    if allocation_dollars > remaining_cash:
        allocation_dollars = round(max(0.0, remaining_cash), 2)

    qty = round(allocation_dollars / price, 6) if price > 0.0 else 0.0
    account_risk_pct = round(allocation_pct * (stop_loss_pct / 100.0), 4)

    return {
        "symbol": symbol,
        "side": "long",
        "bucket": bucket,
        "selection_reason": selection_reason,
        "score": round(score, 6),
        "source_signal": source_signal or {},
        "allocation_pct": round(allocation_pct, 4),
        "allocation_dollars": allocation_dollars,
        "price": round(price, 6),
        "price_source": price_source,
        "qty": qty,
        "stop_loss_pct": stop_loss_pct,
        "trailing_stop_pct": DEFAULT_TRAILING_STOP_PCT,
        "profit_activation_pct": DEFAULT_PROFIT_ACTIVATION_PCT,
        "profit_lock_pct": DEFAULT_PROFIT_LOCK_PCT,
        "account_risk_pct": account_risk_pct,
        "capped_by_risk": capped_by_risk,
        "eligible": price > 0.0 and qty > 0.0 and allocation_dollars > 0.0,
    }


def _auto_fire_ledger(pf: Dict[str, Any]) -> Dict[str, Any]:
    ledger = pf.get("market_surge_deployment_auto_fire_ledger")
    if not isinstance(ledger, dict):
        ledger = {}
    pf["market_surge_deployment_auto_fire_ledger"] = ledger
    return ledger


def _auto_fire_today_row(pf: Dict[str, Any], today: str) -> Dict[str, Any]:
    ledger = _auto_fire_ledger(pf)
    row = ledger.get(today)
    if not isinstance(row, dict):
        row = {
            "date": today,
            "successful_fires": 0,
            "attempts": 0,
            "fired_symbols": [],
            "last_attempt_local": None,
            "last_success_local": None,
        }
    ledger[today] = row
    return row


def _append_planned_entry(
    planned_entries: List[Dict[str, Any]],
    entry: Dict[str, Any],
    remaining_cash: float,
    planned_total_pct: float,
) -> Tuple[float, float]:
    if entry["eligible"]:
        planned_entries.append(entry)
        remaining_cash = round(remaining_cash - _safe_float(entry.get("allocation_dollars")), 4)
        planned_total_pct = round(planned_total_pct + _safe_float(entry.get("allocation_pct")), 4)
    return remaining_cash, planned_total_pct


def _build_plan(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core)
    state = _load_state(core)
    positions = _positions(pf, state)

    cash, equity = _cash_equity(pf, state)
    cash_pct = _cash_pct(pf, state)
    risk_ok, risk_reasons = _risk_clean(pf, state)
    surge_level, surge_reasons = _infer_surge_level(pf, state)
    regular_market = _is_regular_market_window()

    existing_symbols = {str(symbol).upper() for symbol in positions.keys()}
    max_total_pct = _max_total_deployment_pct(surge_level)

    blockers: List[str] = []

    if not regular_market:
        blockers.append("outside_regular_market_execution_window")
    if not risk_ok:
        blockers.extend(risk_reasons)
    if cash_pct < MIN_CASH_PCT_FOR_SURGE_DEPLOYMENT:
        blockers.append(f"cash_pct_below_minimum:{cash_pct}")
    if len(existing_symbols) >= MAX_OPEN_POSITIONS_AFTER_SURGE:
        blockers.append(f"max_positions_reached:{len(existing_symbols)}")
    if surge_level < 2:
        blockers.extend(surge_reasons)

    deployment_allowed = len(blockers) == 0

    planned_entries: List[Dict[str, Any]] = []
    stock_leader_entries: List[Dict[str, Any]] = []
    etf_anchor_entries: List[Dict[str, Any]] = []
    remaining_cash = cash
    planned_total_pct = 0.0

    stock_leaders, stock_leaders_reviewed = _rank_stock_leaders(core, pf, state, existing_symbols, surge_level)
    max_leaders = _max_stock_leaders(surge_level)
    stock_target_pct = round(max_total_pct * _stock_leader_share(surge_level), 4)
    stock_leader_slots = max(0, min(max_leaders, MAX_OPEN_POSITIONS_AFTER_SURGE - len(existing_symbols)))

    if deployment_allowed and stock_target_pct > 0.0 and stock_leader_slots > 0:
        leaders_to_consider = stock_leaders[:stock_leader_slots]
        per_leader_pct = round(stock_target_pct / max(1, len(leaders_to_consider)), 4) if leaders_to_consider else 0.0

        for leader in leaders_to_consider:
            if len(existing_symbols) + len(planned_entries) >= MAX_OPEN_POSITIONS_AFTER_SURGE:
                break

            remaining_pct_capacity = max_total_pct - planned_total_pct
            if remaining_pct_capacity <= 0.0:
                break

            symbol = str(leader.get("symbol", "")).upper()
            alloc_pct = min(per_leader_pct, remaining_pct_capacity)
            entry = _planned_entry(
                core=core,
                pf=pf,
                state=state,
                symbol=symbol,
                allocation_pct=alloc_pct,
                total_equity=equity,
                remaining_cash=remaining_cash,
                bucket="surge_stock_leader",
                selection_reason="ranked_scanner_leader_during_market_surge",
                score=_safe_float(leader.get("score")),
                source_signal=leader,
            )

            before_count = len(planned_entries)
            remaining_cash, planned_total_pct = _append_planned_entry(
                planned_entries,
                entry,
                remaining_cash,
                planned_total_pct,
            )
            if len(planned_entries) > before_count:
                stock_leader_entries.append(entry)

    stock_leaders_available = len(stock_leader_entries) > 0
    etf_weights = _scaled_etf_anchor_weights(surge_level, stock_leaders_available)

    if deployment_allowed:
        for symbol, desired_pct in etf_weights:
            if symbol.upper() in existing_symbols:
                continue

            if len(existing_symbols) + len(planned_entries) >= MAX_OPEN_POSITIONS_AFTER_SURGE:
                break

            remaining_pct_capacity = max_total_pct - planned_total_pct
            if remaining_pct_capacity <= 0.0:
                break

            alloc_pct = min(desired_pct, remaining_pct_capacity)
            bucket = "benchmark_etf" if symbol in {"QQQ", "SPY", "IWM", "IWO"} else "surge_sector_etf"
            entry = _planned_entry(
                core=core,
                pf=pf,
                state=state,
                symbol=symbol,
                allocation_pct=alloc_pct,
                total_equity=equity,
                remaining_cash=remaining_cash,
                bucket=bucket,
                selection_reason=(
                    "etf_anchor_after_stock_leaders"
                    if stock_leaders_available
                    else "etf_fallback_no_stock_leader_qualified"
                ),
            )

            before_count = len(planned_entries)
            remaining_cash, planned_total_pct = _append_planned_entry(
                planned_entries,
                entry,
                remaining_cash,
                planned_total_pct,
            )
            if len(planned_entries) > before_count:
                etf_anchor_entries.append(entry)

    if deployment_allowed and not planned_entries:
        blockers.append("no_price_backed_eligible_entries")
        deployment_allowed = False

    return {
        "status": "ok",
        "overall": "pass" if deployment_allowed else "stand_down",
        "type": "market_surge_deployment_plan",
        "version": VERSION,
        "generated_local": _now_text(core),
        "advisory_only": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
        "paper_only": True,
        "deployment_allowed": deployment_allowed,
        "blockers": blockers,
        "surge_level": surge_level,
        "surge_reasons": surge_reasons,
        "regular_market_window": regular_market,
        "cash": round(cash, 4),
        "equity": round(equity, 4),
        "cash_pct": cash_pct,
        "open_positions_count": len(existing_symbols),
        "existing_positions": sorted(existing_symbols),
        "max_total_deployment_pct": max_total_pct,
        "planned_total_deployment_pct": planned_total_pct,
        "planned_entries": planned_entries,
        "surge_model": {
            "mode": "hybrid_etf_anchor_plus_stock_leaders",
            "stock_leaders_prioritized": True,
            "etfs_are_anchor_and_fallback": True,
            "stock_leader_share": _stock_leader_share(surge_level),
            "stock_target_deployment_pct": stock_target_pct,
            "max_stock_leaders": max_leaders,
            "stock_leaders_selected_count": len(stock_leader_entries),
            "etf_anchor_selected_count": len(etf_anchor_entries),
            "stock_entries": stock_leader_entries,
            "etf_anchor_entries": etf_anchor_entries,
            "stock_leaders_reviewed": stock_leaders_reviewed,
            "etf_weights_used": etf_weights,
            "fallback_rule": "if_no_stock_leader_qualifies_use_price_backed_etf_surge_basket",
        },
        "auto_fire": {
            "enabled": AUTO_FIRE_ENABLED,
            "route": AUTO_FIRE_ROUTE,
            "alias_route": AUTO_FIRE_ALIAS_ROUTE,
            "max_successful_fires_per_day": AUTO_FIRE_MAX_SUCCESSFUL_FIRES_PER_DAY,
            "requires_confirm_query_param": False,
            "paper_only": True,
        },
        "guardrails": {
            "does_not_execute_without_confirm": True,
            "auto_fire_has_separate_daily_ledger": True,
            "auto_fire_regular_market_only": True,
            "does_not_enable_live_trading": True,
            "does_not_change_ml_authority": True,
            "does_not_bypass_risk_controls": True,
            "hard_stop_required": True,
            "trailing_stop_required": True,
            "no_averaging_down": True,
            "stock_leaders_must_clear_quality_filters": True,
            "etf_only_is_fallback_not_ceiling": True,
        },
    }


def _position_from_entry(entry: Dict[str, Any], now_text: str) -> Dict[str, Any]:
    symbol = str(entry["symbol"]).upper()
    price = _safe_float(entry.get("price"))
    qty = _safe_float(entry.get("qty"))
    allocation = _safe_float(entry.get("allocation_dollars"))

    stop_loss_pct = _safe_float(entry.get("stop_loss_pct"), DEFAULT_STOP_LOSS_PCT)
    trailing_stop_pct = _safe_float(entry.get("trailing_stop_pct"), DEFAULT_TRAILING_STOP_PCT)
    profit_activation_pct = _safe_float(
        entry.get("profit_activation_pct"),
        DEFAULT_PROFIT_ACTIVATION_PCT,
    )
    profit_lock_pct = _safe_float(entry.get("profit_lock_pct"), DEFAULT_PROFIT_LOCK_PCT)

    planned_stop = round(price * (1.0 - stop_loss_pct / 100.0), 4)
    initial_trailing_stop = round(price * (1.0 - trailing_stop_pct / 100.0), 4)

    bucket = str(entry.get("bucket") or ("benchmark_etf" if symbol in {"QQQ", "SPY", "IWM", "IWO"} else "surge_stock_leader"))
    setup_family = "hybrid_market_surge_stock_leader" if bucket == "surge_stock_leader" else "hybrid_market_surge_etf_anchor"

    return {
        "symbol": symbol,
        "side": "long",
        "bucket": bucket,
        "sector": symbol,
        "source": "market_surge_deployment_mode",
        "entry_tag": "hybrid_market_surge_deployment",
        "entry_context": "broad_market_surge",
        "entry_model": "market_surge_deployment_mode",
        "exit_model": "hard_stop_trailing_profit_lock",
        "risk_model": "account_risk_capped_hybrid_surge_basket",
        "setup_family": setup_family,
        "trade_authority": "paper_only_state_entry",
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "selection_reason": entry.get("selection_reason"),
        "source_signal": entry.get("source_signal", {}),
        "entry": round(price, 4),
        "entry_price": round(price, 4),
        "last_price": round(price, 4),
        "shares": round(qty, 6),
        "qty": round(qty, 6),
        "cost_basis": round(allocation, 4),
        "market_value": round(allocation, 4),
        "allocation_pct_of_equity": _safe_float(entry.get("allocation_pct")),
        "account_risk_pct": _safe_float(entry.get("account_risk_pct")),
        "stop_loss_pct": stop_loss_pct,
        "planned_stop": planned_stop,
        "trailing_stop_pct": trailing_stop_pct,
        "trailing_stop": initial_trailing_stop,
        "trailing_stop_active": False,
        "profit_activation_pct": profit_activation_pct,
        "profit_lock_pct": profit_lock_pct,
        "profit_lock_active": False,
        "take_profit_pct": 8.0,
        "partial_taken": False,
        "adds": 0,
        "score": _safe_float(entry.get("score")),
        "entry_time": int(dt.datetime.now().timestamp()),
        "opened_at": now_text,
        "peak": round(price, 4),
        "pnl_dollars": 0.0,
        "pnl_pct": 0.0,
        "unrealized_pnl": 0.0,
        "unrealized_pnl_pct": 0.0,
        "auto_fire_eligible": True,
        "version": VERSION,
    }


def _append_trade_rows(pf: Dict[str, Any], executed_entries: List[Dict[str, Any]], now_text: str) -> None:
    if not executed_entries:
        return

    trades = pf.get("trades")
    if not isinstance(trades, list):
        trades = []

    for row in executed_entries:
        trades.append(
            {
                "time": now_text,
                "symbol": row.get("symbol"),
                "side": "buy",
                "type": "paper_market_surge_deployment",
                "source": "market_surge_deployment_mode",
                "bucket": row.get("bucket"),
                "selection_reason": row.get("selection_reason"),
                "entry": row.get("entry"),
                "shares": row.get("shares"),
                "allocation_dollars": row.get("allocation_dollars"),
                "allocation_pct": row.get("allocation_pct"),
                "live_trade_authority": "none",
                "ml_authority": "shadow_only",
                "version": VERSION,
            }
        )

    pf["trades"] = trades[-1000:]


def _recompute_portfolio_totals(pf: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    positions = _positions(pf, state)
    cash = _safe_float(pf.get("cash", state.get("cash", 0.0)))

    market_value = 0.0
    unrealized = 0.0

    for pos in positions.values():
        if not isinstance(pos, dict):
            continue

        shares = _safe_float(pos.get("shares"), _safe_float(pos.get("qty")))
        entry = _safe_float(pos.get("entry"), _safe_float(pos.get("entry_price")))
        last_price = _safe_float(pos.get("last_price"), entry)

        if shares > 0.0 and last_price > 0.0:
            market_value += shares * last_price

        if shares > 0.0 and entry > 0.0 and last_price > 0.0:
            unrealized += (last_price - entry) * shares

    pf["equity"] = round(cash + market_value, 4)

    perf = _performance(pf, state)
    perf["open_positions"] = positions
    perf["unrealized_pnl"] = round(unrealized, 4)
    pf["performance"] = perf

    return {
        "cash": round(cash, 4),
        "market_value": round(market_value, 4),
        "equity": pf["equity"],
        "unrealized_pnl": perf["unrealized_pnl"],
    }


def _execute_confirmed(
    core: Any,
    plan: Dict[str, Any],
    *,
    auto_fire: bool = False,
    trigger: str = "manual_confirm",
) -> Dict[str, Any]:
    if not plan.get("deployment_allowed"):
        plan["executed"] = False
        plan["message"] = "No execution. Deployment is not allowed by current guardrails."
        plan["auto_fire_trigger"] = trigger if auto_fire else None
        return plan

    pf = _portfolio(core)
    state = _load_state(core)
    positions = _positions(pf, state)

    cash = _safe_float(pf.get("cash", state.get("cash", 0.0)))
    now_text = _now_text(core)

    executed_entries: List[Dict[str, Any]] = []
    skipped_entries: List[Dict[str, Any]] = []

    for entry in plan.get("planned_entries", []):
        symbol = str(entry.get("symbol", "")).upper()
        allocation = _safe_float(entry.get("allocation_dollars"))
        qty = _safe_float(entry.get("qty"))
        price = _safe_float(entry.get("price"))

        if symbol in positions:
            skipped_entries.append({"symbol": symbol, "reason": "already_open"})
            continue

        if allocation <= 0.0 or qty <= 0.0 or price <= 0.0:
            skipped_entries.append({"symbol": symbol, "reason": "invalid_entry"})
            continue

        if allocation > cash:
            skipped_entries.append({"symbol": symbol, "reason": "insufficient_cash"})
            continue

        position = _position_from_entry(entry, now_text)
        position["auto_fire"] = bool(auto_fire)
        position["auto_fire_trigger"] = trigger if auto_fire else None
        positions[symbol] = position
        cash = round(cash - allocation, 4)

        executed_entries.append(
            {
                "symbol": symbol,
                "bucket": entry.get("bucket"),
                "selection_reason": entry.get("selection_reason"),
                "allocation_dollars": allocation,
                "allocation_pct": entry.get("allocation_pct"),
                "entry": round(price, 4),
                "shares": round(qty, 6),
                "account_risk_pct": entry.get("account_risk_pct"),
                "planned_stop": position["planned_stop"],
                "trailing_stop": position["trailing_stop"],
                "auto_fire": bool(auto_fire),
            }
        )

    pf["positions"] = positions
    pf["cash"] = round(cash, 4)

    _append_trade_rows(pf, executed_entries, now_text)

    deployment_journal = pf.get("market_surge_deployment_journal")
    if not isinstance(deployment_journal, list):
        deployment_journal = []

    journal_row = {
        "time": now_text,
        "version": VERSION,
        "auto_fire": bool(auto_fire),
        "auto_fire_trigger": trigger if auto_fire else None,
        "executed_entries": executed_entries,
        "skipped_entries": skipped_entries,
        "surge_level": plan.get("surge_level"),
        "surge_model": plan.get("surge_model"),
        "planned_total_deployment_pct": plan.get("planned_total_deployment_pct"),
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
    }
    deployment_journal.append(journal_row)
    pf["market_surge_deployment_journal"] = deployment_journal[-100:]

    if auto_fire:
        today = _today(core)
        row = _auto_fire_today_row(pf, today)
        row["attempts"] = _safe_int(row.get("attempts"), 0) + 1
        row["last_attempt_local"] = now_text
        if executed_entries:
            row["successful_fires"] = _safe_int(row.get("successful_fires"), 0) + 1
            row["last_success_local"] = now_text
            fired_symbols = row.get("fired_symbols")
            if not isinstance(fired_symbols, list):
                fired_symbols = []
            for item in executed_entries:
                symbol = str(item.get("symbol", "")).upper()
                if symbol and symbol not in fired_symbols:
                    fired_symbols.append(symbol)
            row["fired_symbols"] = fired_symbols
        _auto_fire_ledger(pf)[today] = row

    totals = _recompute_portfolio_totals(pf, state)
    save_result = _save(core, pf)

    return {
        "status": "ok",
        "overall": "pass" if executed_entries else "stand_down",
        "type": "market_surge_deployment_execution",
        "version": VERSION,
        "generated_local": now_text,
        "advisory_only": True,
        "paper_only": True,
        "live_trade_authority": "none",
        "ml_authority": "shadow_only",
        "authority_changed": False,
        "auto_fire": bool(auto_fire),
        "auto_fire_trigger": trigger if auto_fire else None,
        "executed": bool(executed_entries),
        "message": (
            "Executed paper-only hybrid market surge deployment."
            if executed_entries
            else "No eligible entries were executed."
        ),
        "executed_entries": executed_entries,
        "skipped_entries": skipped_entries,
        "post_execution_totals": totals,
        "persistence": save_result,
        "guardrails": plan.get("guardrails", {}),
    }


def _execute(core: Any = None, confirm: bool = False) -> Dict[str, Any]:
    plan = _build_plan(core)

    if not confirm:
        plan["executed"] = False
        plan["message"] = "Preview only. Add confirm=1 to execute paper-only surge deployment."
        return plan

    return _execute_confirmed(core, plan, auto_fire=False, trigger="manual_confirm")


def _auto_fire(core: Any = None, trigger: str = "auto_fire_route") -> Dict[str, Any]:
    plan = _build_plan(core)
    pf = _portfolio(core)
    state = _load_state(core)
    today = _today(core)
    now_text = _now_text(core)

    plan["auto_fire_trigger"] = trigger
    plan["auto_fire_requested_local"] = now_text

    if not AUTO_FIRE_ENABLED:
        plan["executed"] = False
        plan["auto_fire_blocked"] = True
        plan["blockers"] = list(plan.get("blockers", [])) + ["auto_fire_disabled"]
        plan["overall"] = "stand_down"
        plan["message"] = "Auto-fire is disabled."
        return plan

    row = _auto_fire_today_row(pf, today)
    successful_fires = _safe_int(row.get("successful_fires"), 0)

    if successful_fires >= AUTO_FIRE_MAX_SUCCESSFUL_FIRES_PER_DAY:
        plan["executed"] = False
        plan["auto_fire_blocked"] = True
        plan["blockers"] = list(plan.get("blockers", [])) + ["auto_fire_daily_limit_reached"]
        plan["overall"] = "stand_down"
        plan["message"] = "Auto-fire daily limit already reached."
        return plan

    if not plan.get("deployment_allowed"):
        row["attempts"] = _safe_int(row.get("attempts"), 0) + 1
        row["last_attempt_local"] = now_text
        _auto_fire_ledger(pf)[today] = row
        _save(core, pf)

        plan["executed"] = False
        plan["auto_fire_blocked"] = True
        plan["message"] = "Auto-fire stood down because deployment guardrails are not clear."
        return plan

    existing_symbols = {str(symbol).upper() for symbol in _positions(pf, state).keys()}
    planned_symbols = [str(item.get("symbol", "")).upper() for item in plan.get("planned_entries", [])]
    new_symbols = [symbol for symbol in planned_symbols if symbol and symbol not in existing_symbols]

    if not new_symbols:
        plan["executed"] = False
        plan["auto_fire_blocked"] = True
        plan["blockers"] = list(plan.get("blockers", [])) + ["auto_fire_no_new_symbols"]
        plan["overall"] = "stand_down"
        plan["message"] = "Auto-fire found no new symbols to deploy."
        return plan

    return _execute_confirmed(core, plan, auto_fire=True, trigger=trigger)


def apply(core: Any = None) -> Dict[str, Any]:
    return _build_plan(core)


def auto_fire(core: Any = None) -> Dict[str, Any]:
    return _auto_fire(core, trigger="module_auto_fire")


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return

    from flask import jsonify, request

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    if "/paper/market-surge-deployment-status" not in existing:
        flask_app.add_url_rule(
            "/paper/market-surge-deployment-status",
            "market_surge_deployment_status",
            lambda: jsonify(_build_plan(core)),
        )

    if "/paper/market-surge-deployment-plan" not in existing:
        flask_app.add_url_rule(
            "/paper/market-surge-deployment-plan",
            "market_surge_deployment_plan",
            lambda: jsonify(_build_plan(core)),
        )

    if "/paper/market-surge-deployment-execute" not in existing:

        def execute_route():
            confirm = str(request.args.get("confirm", "0")).lower() in {
                "1",
                "true",
                "yes",
            }
            return jsonify(_execute(core, confirm=confirm))

        flask_app.add_url_rule(
            "/paper/market-surge-deployment-execute",
            "market_surge_deployment_execute",
            execute_route,
        )

    if AUTO_FIRE_ROUTE not in existing:

        def auto_fire_route():
            return jsonify(_auto_fire(core, trigger="route:auto-fire"))

        flask_app.add_url_rule(
            AUTO_FIRE_ROUTE,
            "market_surge_deployment_auto_fire",
            auto_fire_route,
        )

    if AUTO_FIRE_ALIAS_ROUTE not in existing:

        def autofire_route():
            return jsonify(_auto_fire(core, trigger="route:autofire"))

        flask_app.add_url_rule(
            AUTO_FIRE_ALIAS_ROUTE,
            "market_surge_deployment_autofire",
            autofire_route,
        )

    REGISTERED_APP_IDS.add(id(flask_app))
