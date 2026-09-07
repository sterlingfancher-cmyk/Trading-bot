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


# --- New deterministic holiday helper (no network) ---
# Purpose: deterministic, no-network, full-day U.S. equity holiday guard.
# Only add the explicit, narrowly scoped dates required to fix Issue #181.
# Do not attempt to implement full holiday calendar or early-close semantics.


def is_us_equity_full_holiday(reference: Optional[dt.datetime] = None) -> bool:
    """Return True for deterministic, no-network, full-day U.S. equity holidays.

    Narrow, deterministic scope for the fix: include Labor Day 2026 (2026-09-07).
    The helper accepts an optional timezone-aware datetime. If a naive datetime
    is supplied, it is interpreted in the CENTRAL_TZ_NAME timezone.
    """
    now = reference or _central_now()

    # Normalize to date in central time for comparison.
    if ZoneInfo is not None:
        try:
            central = now.astimezone(ZoneInfo(CENTRAL_TZ_NAME))
        except Exception:
            central = now
    else:
        central = now

    y = central.year
    m = central.month
    d = central.day

    # Explicit single-date holiday: Labor Day 2026 => 2026-09-07
    if (y, m, d) == (2026, 9, 7):
        return True

    return False


# Update _is_regular_market_window to consult the holiday guard.
# Keep semantics otherwise identical (weekday and tighter entry window).

def _is_regular_market_window(now: Optional[dt.datetime] = None) -> bool:
    current = now or _central_now()

    # Full-day holiday closure has precedence over weekday/time.
    if is_us_equity_full_holiday(current):
        return False

    if current.weekday() >= 5:
        return False

    # US equities regular session in Central time is 8:30 AM to 3:00 PM.
    # Use a tighter entry window to avoid immediate open and close-lock entries.
    start = current.replace(hour=8, minute=40, second=0, microsecond=0)
    end = current.replace(hour=14, minute=45, second=0, microsecond=0)
    return start <= current <= end


# The rest of the module remains unchanged. The functions below still call
# _is_regular_market_window() internally and will now benefit from the
# deterministic holiday guard above.


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
        "bl": True,
    }
