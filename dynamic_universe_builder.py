"""Dynamic Universe Builder v4 for the Railway paper-trading bot.

Purpose:
- Move beyond a tiny hand-built ticker list without attempting to scan every
  public symbol.
- Build a broad but capped candidate pool from theme baskets, existing universe,
  shadow/missed-mover observations, and configured extra symbols.
- Promote only liquid, valid, active, intraday-scannable candidates into the core
  scanner for the current session.
- Use a session-aware intraday gate so early-morning opportunity is not choked
  by a fixed 35-bar requirement.
- Apply source-level symbol hygiene before any yfinance batch download.
- Avoid heavy yfinance work during app boot, usercustomize registration, or
  ordinary self-check route registration.

Guardrails:
- Paper scanner expansion only.
- Does not place trades.
- Does not grant live authority.
- Does not change ML authority.
- Does not lower entry thresholds.
- Does not bypass quality/risk/regime/self-defense/cooldown/exposure controls.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Sequence, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

VERSION = "dynamic-universe-builder-2026-07-01-v4-source-symbol-hygiene"
ENABLED = os.environ.get("DYNAMIC_UNIVERSE_BUILDER_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("DYNAMIC_UNIVERSE_BUILDER_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
CACHE_TTL_SECONDS = int(os.environ.get("DYNAMIC_UNIVERSE_CACHE_TTL_SECONDS", "900"))
MAX_SEED_SYMBOLS = int(os.environ.get("DYNAMIC_UNIVERSE_MAX_SEED_SYMBOLS", "260"))
MAX_PROMOTED_SYMBOLS = int(os.environ.get("DYNAMIC_UNIVERSE_MAX_PROMOTED_SYMBOLS", "75"))
MAX_TOTAL_UNIVERSE = int(os.environ.get("DYNAMIC_UNIVERSE_MAX_TOTAL_UNIVERSE", "180"))
MAX_INTRADAY_CHECKS = int(os.environ.get("DYNAMIC_UNIVERSE_MAX_INTRADAY_CHECKS", "90"))
MIN_PRICE = float(os.environ.get("DYNAMIC_UNIVERSE_MIN_PRICE", "3.00"))
MIN_AVG_VOLUME = float(os.environ.get("DYNAMIC_UNIVERSE_MIN_AVG_VOLUME", "350000"))
MIN_DOLLAR_VOLUME = float(os.environ.get("DYNAMIC_UNIVERSE_MIN_DOLLAR_VOLUME", "5000000"))
MIN_PROMOTION_SCORE = float(os.environ.get("DYNAMIC_UNIVERSE_MIN_PROMOTION_SCORE", "0.28"))
MIN_MOVE_PCT = float(os.environ.get("DYNAMIC_UNIVERSE_MIN_MOVE_PCT", "1.25"))
MIN_VOLUME_RATIO = float(os.environ.get("DYNAMIC_UNIVERSE_MIN_VOLUME_RATIO", "1.15"))
REQUIRE_INTRADAY_DATA = os.environ.get("DYNAMIC_UNIVERSE_REQUIRE_INTRADAY_DATA", "true").lower() not in {"0", "false", "no", "off"}
MIN_INTRADAY_BARS = int(os.environ.get("DYNAMIC_UNIVERSE_MIN_INTRADAY_BARS", "35"))
ADAPTIVE_INTRADAY_GATE_ENABLED = os.environ.get("DYNAMIC_UNIVERSE_ADAPTIVE_INTRADAY_GATE_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MARKET_TIMEZONE = os.environ.get("DYNAMIC_UNIVERSE_MARKET_TIMEZONE", "America/Chicago")
MARKET_OPEN_HOUR = int(os.environ.get("DYNAMIC_UNIVERSE_MARKET_OPEN_HOUR", "8"))
MARKET_OPEN_MINUTE = int(os.environ.get("DYNAMIC_UNIVERSE_MARKET_OPEN_MINUTE", "30"))
OPENING_OBSERVATION_MINUTES = int(os.environ.get("DYNAMIC_UNIVERSE_OPENING_OBSERVATION_MINUTES", "15"))
EARLY_STARTER_UNTIL_MINUTES = int(os.environ.get("DYNAMIC_UNIVERSE_EARLY_STARTER_UNTIL_MINUTES", "45"))
MID_SESSION_UNTIL_MINUTES = int(os.environ.get("DYNAMIC_UNIVERSE_MID_SESSION_UNTIL_MINUTES", "90"))
EARLY_MIN_INTRADAY_BARS = int(os.environ.get("DYNAMIC_UNIVERSE_EARLY_MIN_INTRADAY_BARS", "8"))
MID_MIN_INTRADAY_BARS = int(os.environ.get("DYNAMIC_UNIVERSE_MID_MIN_INTRADAY_BARS", "20"))
EARLY_STARTER_ALLOC_FACTOR = float(os.environ.get("DYNAMIC_UNIVERSE_EARLY_STARTER_ALLOC_FACTOR", "0.35"))
ALLOW_LEVERAGED_ETFS = os.environ.get("DYNAMIC_UNIVERSE_ALLOW_LEVERAGED_ETFS", "true").lower() not in {"0", "false", "no", "off"}
LEVERAGED_MAX_PROMOTED = int(os.environ.get("DYNAMIC_UNIVERSE_LEVERAGED_MAX_PROMOTED", "2"))

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}
_BASE_UNIVERSE: Dict[int, List[str]] = {}
_LAST_SEED_REJECTIONS: List[Dict[str, str]] = []

_RESERVED_WORDS = {
    "LONG", "SHORT", "AUTO", "MANUAL", "BEARISH", "BULLISH", "CLEAR", "CLEAN", "RUN", "RUNNING",
    "PASS", "FAIL", "WARN", "ERROR", "OK", "OPEN", "CLOSE", "CLOSED", "ENTRY", "EXIT", "BUY", "SELL",
    "HOLD", "HELD", "CASH", "EQUITY", "POSITION", "POSITIONS", "TRADE", "TRADES", "SIGNAL", "SIGNALS",
    "BLOCKED", "REJECTED", "CANDIDATE", "CANDIDATES", "TODAY", "YESTERDAY", "TOMORROW", "DATE",
    "TRUE", "FALSE", "NONE", "NULL", "NAN", "INF", "LOSS", "WIN", "RISK", "QUALITY", "SCORE",
    "COOLDOWN", "CONSTRUCTIVE", "NEUTRAL", "DEFENSIVE", "REGIME", "MODE", "STATUS", "REASON", "SOURCE",
}
_KNOWN_NO_DATA = {
    s.strip().upper() for s in os.environ.get("DYNAMIC_UNIVERSE_KNOWN_NO_DATA_SYMBOLS", "CIFRW,SATS,BITF,SDIG,PSTG").split(",") if s.strip()
}
_ALLOWED_SPECIALS = {"^VIX", "^TNX", "ES=F", "NQ=F"}
_SYMBOL_RE = re.compile(r"^[A-Z]{1,6}([.-][A-Z])?$")
_DATE_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}$")
_NUMERIC_RE = re.compile(r"^\d+(\.\d+)?$")

THEME_BASKETS: Dict[str, List[str]] = {
    "semi_leaders": [
        "NVDA", "AMD", "AVGO", "TSM", "MU", "ARM", "MRVL", "LRCX", "AMAT", "KLAC", "ASML",
        "QCOM", "TXN", "ADI", "NXPI", "ON", "MCHP", "LSCC", "MPWR", "ALAB", "ACLS", "UCTT",
        "TER", "AMKR", "MTSI", "SITM", "CAMT", "AEHR", "VECO", "ENTG", "COHR", "WOLF",
    ],
    "memory_storage": ["MU", "WDC", "STX", "SNDK", "SIMO", "RMBS", "DRAM"],
    "data_center_infra": [
        "SMCI", "ANET", "DELL", "HPE", "CIEN", "GLW", "COHR", "LITE", "AAOI", "WDC", "STX", "TER",
        "VRT", "ETN", "PWR", "GEV", "VST", "CEG", "NRG", "MOD", "POWL", "IESC", "EME", "FIX",
        "ORCL", "IBM", "NTNX", "DDOG", "NET",
    ],
    "bitcoin_ai_compute": [
        "HIVE", "HUT", "IREN", "CIFR", "WULF", "CLSK", "MARA", "RIOT", "BTDR", "CORZ", "APLD",
        "COIN", "MSTR", "GLXY", "CAN",
    ],
    "ai_software_momentum": ["PLTR", "AI", "SOUN", "BBAI", "PATH", "DDOG", "APP", "DUOL", "SNOW", "NET", "CRWD", "PANW"],
    "space_stocks": ["RKLB", "LUNR", "ASTS", "RDW", "PL", "BKSY", "SATL", "SPIR", "SPCE", "IRDM", "GSAT", "VSAT", "SPCX"],
    "small_cap_momentum": ["SOUN", "RGTI", "QBTS", "IONQ", "RXRX", "TEM", "ACHR", "JOBY", "BBAI", "AI", "BE", "EOSE", "QS", "CHPT"],
    "biotech_speculative": ["RXRX", "TEM", "DNA", "EDIT", "CRSP", "NTLA", "BEAM", "TWST", "SDGR", "ABCL"],
    "industrial_power": ["GEV", "VRT", "ETN", "PWR", "EME", "FIX", "POWL", "IESC", "CEG", "VST", "NRG"],
    "leveraged_etf_watch": ["SOXL", "TQQQ", "QLD", "USD", "TECL", "FNGU", "ARKK", "SOXS", "SQQQ"],
}

SECTOR_BY_BUCKET = {
    "semi_leaders": "XLK",
    "memory_storage": "XLK",
    "data_center_infra": "XLK",
    "bitcoin_ai_compute": "XLK",
    "ai_software_momentum": "XLK",
    "space_stocks": "XLI",
    "small_cap_momentum": "XLK",
    "biotech_speculative": "XLV",
    "industrial_power": "XLI",
    "leveraged_etf_watch": "LEVERAGED_ETF",
}

BUCKET_CONFIG_DEFAULTS = {
    "memory_storage": {"alloc_factor": 0.65, "max_exposure_pct": 0.30, "max_positions": 2},
    "biotech_speculative": {"alloc_factor": 0.30, "max_exposure_pct": 0.10, "max_positions": 1},
    "industrial_power": {"alloc_factor": 0.60, "max_exposure_pct": 0.25, "max_positions": 2},
    "leveraged_etf_watch": {"alloc_factor": 0.25, "max_exposure_pct": 0.08, "max_positions": 1},
}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None:
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "scan_signals"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper_context() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _invalid_symbol_reason(value: Any) -> str | None:
    try:
        s = str(value or "").upper().strip()
        if s.startswith("$"):
            s = s[1:]
    except Exception:
        return "symbol_parse_error"
    if not s:
        return "blank_symbol"
    if s in _ALLOWED_SPECIALS:
        return None
    if s in _RESERVED_WORDS:
        return "reserved_state_word_not_ticker"
    if s in _KNOWN_NO_DATA:
        return "known_provider_no_data_symbol"
    if _DATE_RE.match(s):
        return "date_token_not_ticker"
    if _NUMERIC_RE.match(s):
        return "numeric_token_not_ticker"
    if any(ch.isspace() for ch in s) or "," in s or ":" in s or "/" in s:
        return "contains_non_ticker_separator"
    if s.endswith("W") and len(s) >= 5:
        return "probable_warrant_symbol"
    if not _SYMBOL_RE.match(s):
        return "ticker_format_rejected"
    return None


def _symbol(value: Any) -> str:
    try:
        s = str(value or "").upper().strip()
        if s.startswith("$"):
            s = s[1:]
        return s if _invalid_symbol_reason(s) is None else ""
    except Exception:
        return ""


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _unique(seq: Iterable[Any]) -> List[str]:
    global _LAST_SEED_REJECTIONS
    out: List[str] = []
    seen = set()
    rejected: List[Dict[str, str]] = []
    for item in seq or []:
        raw = str(item or "").upper().strip()
        s = _symbol(item)
        if s and s not in seen:
            seen.add(s)
            out.append(s)
        elif raw:
            reason = _invalid_symbol_reason(raw)
            if reason and len(rejected) < 150:
                rejected.append({"token": raw, "reason": reason})
    _LAST_SEED_REJECTIONS = rejected
    return out


def _base_universe(core: Any) -> List[str]:
    key = id(core)
    if key not in _BASE_UNIVERSE:
        try:
            _BASE_UNIVERSE[key] = _unique(getattr(core, "UNIVERSE", []) or [])
        except Exception:
            _BASE_UNIVERSE[key] = []
    return list(_BASE_UNIVERSE[key])


def _bucket_for_symbol(core: Any, symbol: str) -> str:
    symbol = _symbol(symbol)
    try:
        existing = getattr(core, "SYMBOL_BUCKET", {}) or {}
        if isinstance(existing, dict) and existing.get(symbol):
            return str(existing.get(symbol))
    except Exception:
        pass
    for bucket, members in THEME_BASKETS.items():
        if symbol in members:
            return bucket
    return "dynamic_discovery"


def _sector_for_symbol(core: Any, symbol: str, bucket: str) -> str:
    symbol = _symbol(symbol)
    try:
        existing = getattr(core, "SYMBOL_SECTOR", {}) or {}
        if isinstance(existing, dict) and existing.get(symbol):
            return str(existing.get(symbol))
    except Exception:
        pass
    return SECTOR_BY_BUCKET.get(bucket, "UNKNOWN")


def _flatten_symbols(obj: Any, max_items: int = 15000) -> List[str]:
    found: List[str] = []
    seen = 0

    def walk(value: Any) -> None:
        nonlocal seen
        if seen >= max_items:
            return
        seen += 1
        if isinstance(value, dict):
            # Only explicit market-symbol fields should be treated as symbols.
            # Do not scrape generic names/messages/status values.
            for key in ("symbol", "ticker", "asset"):
                if key in value:
                    s = _symbol(value.get(key))
                    if s:
                        found.append(s)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        # Intentionally ignore free-floating strings in state. They are where
        # LONG/SHORT/AUTO/BEARISH/CLEAR/date tokens leaked from.

    walk(obj)
    return _unique(found)


def _state_symbols(core: Any) -> List[str]:
    symbols: List[str] = []
    try:
        pf = getattr(core, "portfolio", {}) or {}
        symbols += _flatten_symbols(pf.get("scanner_audit", {}))
        symbols += _flatten_symbols(pf.get("speculative_momentum_last_observation", {}))
        journal = pf.get("ml_feature_journal", {}) if isinstance(pf.get("ml_feature_journal"), dict) else {}
        symbols += _flatten_symbols(journal.get("shadow_mover_observations", [])[-120:])
        symbols += list((pf.get("positions", {}) or {}).keys())
    except Exception:
        pass
    return _unique(symbols)


def _configured_extra_symbols() -> List[str]:
    raw = os.environ.get("DYNAMIC_UNIVERSE_EXTRA_SYMBOLS", "")
    return _unique(raw.split(","))


def _seed_symbols(core: Any) -> Tuple[List[str], Dict[str, Any]]:
    seeds: List[str] = []
    base = _base_universe(core)
    seeds += base
    for members in THEME_BASKETS.values():
        seeds += members
    seeds += _state_symbols(core)
    seeds += _configured_extra_symbols()
    if not ALLOW_LEVERAGED_ETFS:
        leveraged = set(THEME_BASKETS.get("leveraged_etf_watch", []))
        seeds = [s for s in seeds if _symbol(s) not in leveraged]
    seeds = _unique(seeds)
    if len(seeds) > MAX_SEED_SYMBOLS:
        base_set = set(base)
        base_part = [s for s in seeds if s in base_set]
        extra_part = [s for s in seeds if s not in base_set]
        seeds = _unique(base_part + extra_part[: max(0, MAX_SEED_SYMBOLS - len(base_part))])
    meta = {
        "base_universe_count": len(base),
        "seed_count": len(seeds),
        "max_seed_symbols": MAX_SEED_SYMBOLS,
        "theme_baskets": {k: len(v) for k, v in THEME_BASKETS.items()},
        "configured_extra_symbols": _configured_extra_symbols(),
        "source_hygiene_active": True,
        "reserved_words_count": len(_RESERVED_WORDS),
        "known_no_data_symbols": sorted(_KNOWN_NO_DATA),
        "recent_rejected_seed_tokens": _LAST_SEED_REJECTIONS[:50],
    }
    return seeds, meta


def _series_from_download(data: Any, symbol: str, column: str):
    try:
        if data is None or getattr(data, "empty", True):
            return None
        cols = getattr(data, "columns", None)
        if cols is None:
            return None
        if hasattr(cols, "nlevels") and cols.nlevels > 1:
            for col in cols:
                try:
                    if len(col) >= 2 and _symbol(col[0]) == symbol and str(col[1]).lower() == column.lower():
                        return data[col]
                    if len(col) >= 2 and str(col[0]).lower() == column.lower() and _symbol(col[1]) == symbol:
                        return data[col]
                except Exception:
                    pass
        if column in cols:
            series = data[column]
            if hasattr(series, "columns"):
                if symbol in series.columns:
                    return series[symbol]
                return series.iloc[:, 0]
            return series
    except Exception:
        return None
    return None


def _clean_values(series: Any) -> List[float]:
    values: List[float] = []
    try:
        if series is None:
            return values
        for raw in list(series):
            value = _safe_float(raw, None)
            if value is not None and value == value:
                values.append(float(value))
    except Exception:
        return []
    return values


def _download_daily(seeds: Sequence[str]) -> Tuple[Any, str | None]:
    clean_seeds = _unique(seeds)
    if not clean_seeds:
        return None, "no_valid_symbols_after_source_hygiene"
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        return None, f"yfinance_unavailable:{type(exc).__name__}"
    try:
        return yf.download(clean_seeds, period="30d", interval="1d", progress=False, auto_adjust=False, threads=True, group_by="ticker"), None
    except Exception as exc:
        return None, f"download_failed:{type(exc).__name__}: {exc}"


def _snapshot_from_data(core: Any, data: Any, symbol: str) -> Dict[str, Any]:
    symbol = _symbol(symbol)
    close_values = _clean_values(_series_from_download(data, symbol, "Close"))
    volume_values = _clean_values(_series_from_download(data, symbol, "Volume"))
    if len(close_values) < 6:
        return {"symbol": symbol, "data_available": False, "reason": "not_enough_close_rows"}
    price = close_values[-1]
    prev = close_values[-2] if len(close_values) >= 2 else price
    five_back = close_values[-6] if len(close_values) >= 6 else prev
    pct_1d = ((price - prev) / prev) * 100.0 if prev else 0.0
    pct_5d = ((price - five_back) / five_back) * 100.0 if five_back else 0.0
    avg_volume = None
    volume = None
    volume_ratio = None
    if len(volume_values) >= 6:
        volume = volume_values[-1]
        prior = [v for v in volume_values[:-1][-10:] if v and v > 0]
        if prior:
            avg_volume = sum(prior) / len(prior)
            if avg_volume > 0:
                volume_ratio = volume / avg_volume
    dollar_volume = (avg_volume or 0.0) * price
    bucket = _bucket_for_symbol(core, symbol)
    sector = _sector_for_symbol(core, symbol, bucket)
    leveraged = bucket == "leveraged_etf_watch" or symbol in set(THEME_BASKETS.get("leveraged_etf_watch", []))
    data_ok = bool(price >= MIN_PRICE and (avg_volume or 0.0) >= MIN_AVG_VOLUME and dollar_volume >= MIN_DOLLAR_VOLUME)
    return {
        "symbol": symbol,
        "data_available": True,
        "price": round(price, 4),
        "pct_change_1d": round(pct_1d, 4),
        "pct_change_5d": round(pct_5d, 4),
        "volume": int(volume) if volume is not None else None,
        "avg_volume": round(avg_volume, 2) if avg_volume is not None else None,
        "volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
        "dollar_volume": round(dollar_volume, 2),
        "bucket": bucket,
        "sector": sector,
        "leveraged_etf": bool(leveraged),
        "data_ok": bool(data_ok),
    }


def _promotion_score(row: Dict[str, Any]) -> float:
    if not row.get("data_available") or not row.get("data_ok"):
        return 0.0
    pct_1d = _safe_float(row.get("pct_change_1d"), 0.0) or 0.0
    pct_5d = _safe_float(row.get("pct_change_5d"), 0.0) or 0.0
    volume_ratio = _safe_float(row.get("volume_ratio"), 0.0) or 0.0
    dollar_volume = _safe_float(row.get("dollar_volume"), 0.0) or 0.0
    score = 0.0
    score += max(0.0, min(pct_1d, 15.0)) / 30.0
    score += max(0.0, min(pct_5d, 30.0)) / 90.0
    score += max(0.0, min(volume_ratio - 1.0, 4.0)) / 10.0
    score += min(max(dollar_volume, 0.0), 150_000_000.0) / 1_500_000_000.0
    bucket = str(row.get("bucket") or "")
    if bucket in {"semi_leaders", "memory_storage", "data_center_infra", "bitcoin_ai_compute", "industrial_power"}:
        score += 0.06
    elif bucket in {"small_cap_momentum", "space_stocks", "ai_software_momentum"}:
        score += 0.04
    elif bucket == "leveraged_etf_watch":
        score += 0.02
    return round(float(score), 6)


def _eligible_for_daily_promotion(row: Dict[str, Any]) -> Tuple[bool, str]:
    if not row.get("data_available"):
        return False, str(row.get("reason") or "data_unavailable")
    if not row.get("data_ok"):
        return False, "liquidity_or_price_filter"
    if bool(row.get("leveraged_etf")) and not ALLOW_LEVERAGED_ETFS:
        return False, "leveraged_etf_disabled"
    score = _safe_float(row.get("promotion_score"), 0.0) or 0.0
    pct_1d = _safe_float(row.get("pct_change_1d"), 0.0) or 0.0
    pct_5d = _safe_float(row.get("pct_change_5d"), 0.0) or 0.0
    volume_ratio = _safe_float(row.get("volume_ratio"), 0.0) or 0.0
    active_move = pct_1d >= MIN_MOVE_PCT or pct_5d >= max(MIN_MOVE_PCT * 1.75, 2.5)
    volume_confirmed = volume_ratio >= MIN_VOLUME_RATIO
    if not active_move and not volume_confirmed:
        return False, "no_active_move_or_volume_confirmation"
    if score < MIN_PROMOTION_SCORE:
        return False, "promotion_score_below_floor"
    return True, "daily_liquidity_move_promoted"


def _session_gate_policy() -> Dict[str, Any]:
    base = {
        "adaptive": bool(ADAPTIVE_INTRADAY_GATE_ENABLED),
        "market_timezone": MARKET_TIMEZONE,
        "minutes_since_open": None,
        "phase": "standard",
        "allow_dynamic_promotion": True,
        "early_starter": False,
        "required_bars": MIN_INTRADAY_BARS,
        "reason": "standard_full_intraday_gate",
    }
    if not ADAPTIVE_INTRADAY_GATE_ENABLED:
        return base
    try:
        tz = ZoneInfo(MARKET_TIMEZONE) if ZoneInfo is not None else None
        now_local = dt.datetime.now(tz) if tz is not None else dt.datetime.now()
        open_dt = now_local.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
        minutes = int((now_local - open_dt).total_seconds() // 60)
        base["minutes_since_open"] = minutes
        base["now_local"] = now_local.strftime("%Y-%m-%d %H:%M:%S %Z")
        if minutes < 0:
            base.update({"phase": "pre_market", "allow_dynamic_promotion": False, "required_bars": MIN_INTRADAY_BARS, "reason": "pre_market_observation_only"})
        elif minutes < OPENING_OBSERVATION_MINUTES:
            base.update({"phase": "opening_observation", "allow_dynamic_promotion": False, "required_bars": EARLY_MIN_INTRADAY_BARS, "reason": "first_minutes_observation_only_for_dynamic_symbols"})
        elif minutes < EARLY_STARTER_UNTIL_MINUTES:
            base.update({"phase": "early_starter", "allow_dynamic_promotion": True, "early_starter": True, "required_bars": EARLY_MIN_INTRADAY_BARS, "reason": "adaptive_early_starter_intraday_gate"})
        elif minutes < MID_SESSION_UNTIL_MINUTES:
            base.update({"phase": "mid_session_buildout", "allow_dynamic_promotion": True, "required_bars": MID_MIN_INTRADAY_BARS, "reason": "adaptive_mid_session_intraday_gate"})
        else:
            base.update({"phase": "standard", "allow_dynamic_promotion": True, "required_bars": MIN_INTRADAY_BARS, "reason": "standard_full_intraday_gate"})
    except Exception as exc:
        base.update({"reason": f"adaptive_gate_fallback:{type(exc).__name__}", "required_bars": MIN_INTRADAY_BARS})
    return base


def _intraday_from_df(core: Any, symbol: str, df: Any, required_bars: int) -> Dict[str, Any]:
    if df is None:
        return {"scannable": False, "reason": "no_intraday_data", "bars": 0, "required_bars": required_bars}
    try:
        if getattr(df, "empty", False):
            return {"scannable": False, "reason": "no_intraday_data", "bars": 0, "required_bars": required_bars}
    except Exception:
        pass
    closes: List[float] = []
    try:
        arrays_fn = getattr(core, "intraday_arrays", None)
        if callable(arrays_fn):
            arrays = arrays_fn(df)
            if isinstance(arrays, dict):
                raw = arrays.get("close")
                if raw is not None:
                    closes = [float(x) for x in list(raw) if x == x]
    except Exception:
        closes = []
    if not closes:
        try:
            if "Close" in df:
                series = df["Close"]
                if hasattr(series, "columns"):
                    series = series.iloc[:, 0]
                closes = [float(x) for x in list(series) if x == x]
        except Exception:
            closes = []
    bars = len(closes)
    if bars < required_bars:
        return {"scannable": False, "reason": "not_enough_intraday_bars", "bars": bars, "required_bars": required_bars}
    last_price = closes[-1] if closes else None
    if last_price is None or last_price <= 0:
        return {"scannable": False, "reason": "bad_intraday_last_price", "bars": bars, "required_bars": required_bars}
    return {"scannable": True, "reason": "intraday_data_ok", "bars": bars, "last_price": round(float(last_price), 4), "required_bars": required_bars}


def _intraday_check(core: Any, symbol: str, is_base_symbol: bool = False) -> Dict[str, Any]:
    symbol = _symbol(symbol)
    if not symbol:
        return {"scannable": False, "reason": "invalid_symbol_after_hygiene", "bars": 0}
    policy = _session_gate_policy()
    if not REQUIRE_INTRADAY_DATA:
        return {"scannable": True, "reason": "intraday_gate_disabled", "bars": None, "adaptive_session_gate": policy}
    if not is_base_symbol and not policy.get("allow_dynamic_promotion", True):
        return {"scannable": False, "reason": policy.get("reason", "dynamic_promotion_not_allowed_in_this_session_phase"), "bars": None, "adaptive_session_gate": policy}
    try:
        fetch = getattr(core, "fetch_intraday", None)
        if not callable(fetch):
            return {"scannable": False, "reason": "fetch_intraday_unavailable", "bars": 0, "adaptive_session_gate": policy}
        df = fetch(symbol)
        intraday = _intraday_from_df(core, symbol, df, int(policy.get("required_bars") or MIN_INTRADAY_BARS))
        intraday["adaptive_session_gate"] = policy
        return intraday
    except Exception as exc:
        return {"scannable": False, "reason": f"intraday_check_failed:{type(exc).__name__}", "bars": 0, "adaptive_session_gate": policy}


def _apply_dynamic_maps(core: Any, promoted: List[Dict[str, Any]]) -> None:
    sector_map = getattr(core, "SYMBOL_SECTOR", {})
    bucket_map = getattr(core, "SYMBOL_BUCKET", {})
    bucket_cfg = getattr(core, "BUCKET_CONFIG", {})
    if isinstance(sector_map, dict) and isinstance(bucket_map, dict):
        for row in promoted:
            symbol = _symbol(row.get("symbol"))
            bucket = row.get("bucket") or _bucket_for_symbol(core, symbol)
            sector = row.get("sector") or _sector_for_symbol(core, symbol, bucket)
            if symbol:
                sector_map.setdefault(symbol, sector)
                bucket_map.setdefault(symbol, bucket)
    if isinstance(bucket_cfg, dict):
        for bucket, cfg in BUCKET_CONFIG_DEFAULTS.items():
            bucket_cfg.setdefault(bucket, dict(cfg))
        bucket_cfg.setdefault("dynamic_discovery", {"alloc_factor": 0.40, "max_exposure_pct": 0.15, "max_positions": 2})


def build_dynamic_universe(core: Any = None, force: bool = False) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return {"status": "pending", "overall": "pending", "type": "dynamic_universe_builder_status", "version": VERSION, "reason": "core_not_ready"}
    now = time.time()
    if not force and _CACHE.get("payload") and now - float(_CACHE.get("ts", 0.0)) < CACHE_TTL_SECONDS:
        cached = dict(_CACHE["payload"])
        cached["cache_hit"] = True
        return cached
    if not (ENABLED and _paper_context()):
        payload = {"status": "ok", "overall": "pass", "type": "dynamic_universe_builder_status", "version": VERSION, "enabled": bool(ENABLED), "paper_context": bool(_paper_context()), "promotion_applied": False, "reason": "disabled_or_not_paper", "authority_changed": False}
        _CACHE.update({"ts": now, "payload": payload})
        return payload

    seeds, seed_meta = _seed_symbols(core)
    data, data_error = _download_daily(seeds)
    rows: List[Dict[str, Any]] = []
    daily_candidates: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    promoted: List[Dict[str, Any]] = []
    not_scannable: List[Dict[str, Any]] = []
    intraday_checked = 0
    leveraged_promoted = 0
    base = _base_universe(core)
    base_set = set(base)
    session_policy = _session_gate_policy()

    for symbol in seeds:
        row = _snapshot_from_data(core, data, symbol) if data_error is None else {"symbol": symbol, "data_available": False, "reason": data_error}
        row["promotion_score"] = _promotion_score(row)
        row["in_base_universe"] = str(row.get("symbol")) in base_set
        ok, reason = _eligible_for_daily_promotion(row)
        row["daily_promotion_reason"] = reason
        rows.append(row)
        if ok:
            daily_candidates.append(row)
        else:
            row["promotion_reason"] = reason
            rejected.append(row)

    daily_candidates.sort(key=lambda r: (_safe_float(r.get("promotion_score"), 0.0) or 0.0, _safe_float(r.get("pct_change_1d"), 0.0) or 0.0, _safe_float(r.get("volume_ratio"), 0.0) or 0.0), reverse=True)

    for row in daily_candidates:
        if intraday_checked >= MAX_INTRADAY_CHECKS:
            row["intraday"] = {"scannable": False, "reason": "intraday_check_cap", "bars": None, "adaptive_session_gate": session_policy}
            row["promotion_reason"] = "intraday_check_cap"
            not_scannable.append(row)
            rejected.append(row)
            continue
        intraday_checked += 1
        intraday = _intraday_check(core, str(row.get("symbol")), bool(row.get("in_base_universe")))
        row["intraday"] = intraday
        if not intraday.get("scannable"):
            row["promotion_reason"] = intraday.get("reason", "intraday_not_scannable")
            not_scannable.append(row)
            rejected.append(row)
            continue
        if bool(row.get("leveraged_etf")):
            if leveraged_promoted >= LEVERAGED_MAX_PROMOTED:
                row["promotion_reason"] = "leveraged_etf_promotion_cap"
                rejected.append(row)
                continue
            leveraged_promoted += 1
        gate = intraday.get("adaptive_session_gate", {}) if isinstance(intraday.get("adaptive_session_gate"), dict) else {}
        row["early_starter"] = bool(gate.get("early_starter")) and not bool(row.get("in_base_universe"))
        row["promotion_reason"] = "promoted_adaptive_early_starter" if row.get("early_starter") else "promoted_and_intraday_scannable"
        row["scannable"] = True
        promoted.append(row)
        if len(promoted) >= MAX_PROMOTED_SYMBOLS:
            break

    promoted.sort(key=lambda r: (bool(r.get("scannable")), _safe_float(r.get("promotion_score"), 0.0) or 0.0, _safe_float(r.get("pct_change_1d"), 0.0) or 0.0, _safe_float(r.get("volume_ratio"), 0.0) or 0.0), reverse=True)

    final_universe = _unique(base + [r["symbol"] for r in promoted])[:MAX_TOTAL_UNIVERSE]
    promoted_symbols = [s for s in [r["symbol"] for r in promoted] if s in final_universe]
    early_starter_symbols = [str(r.get("symbol")) for r in promoted if r.get("early_starter") and str(r.get("symbol")) in final_universe]

    try:
        core.UNIVERSE = final_universe
        _apply_dynamic_maps(core, promoted)
        try:
            pf = getattr(core, "portfolio", {})
            if isinstance(pf, dict):
                pf["dynamic_universe_builder"] = {
                    "version": VERSION,
                    "generated_local": _now(core),
                    "session_gate": session_policy,
                    "seed_count": len(seeds),
                    "base_universe_count": len(base),
                    "daily_candidate_count": len(daily_candidates),
                    "intraday_checked_count": intraday_checked,
                    "promoted_count": len(promoted_symbols),
                    "early_starter_count": len(early_starter_symbols),
                    "final_universe_count": len(final_universe),
                    "source_hygiene_active": True,
                    "recent_rejected_seed_tokens": _LAST_SEED_REJECTIONS[:50],
                    "promoted_symbols": promoted_symbols[:MAX_PROMOTED_SYMBOLS],
                    "early_starter_symbols": early_starter_symbols[:25],
                    "promoted_and_scannable": promoted[:25],
                    "daily_qualified_but_not_scannable": not_scannable[:25],
                    "top_rejected": sorted(rejected, key=lambda r: _safe_float(r.get("promotion_score"), 0.0) or 0.0, reverse=True)[:25],
                    "authority_changed": False,
                    "trade_authority": "scanner_only_existing_entry_pipeline",
                    "ml_authority": "shadow_only",
                }
        except Exception:
            pass
        promotion_applied = True
    except Exception as exc:
        promotion_applied = False
        data_error = f"promotion_apply_failed:{type(exc).__name__}: {exc}"

    no_intraday_count = sum(1 for row in not_scannable if str((row.get("intraday") or {}).get("reason")) == "no_intraday_data")
    not_enough_bars_count = sum(1 for row in not_scannable if str((row.get("intraday") or {}).get("reason")) == "not_enough_intraday_bars")
    stale_or_bad_price_count = sum(1 for row in not_scannable if "price" in str((row.get("intraday") or {}).get("reason")))
    observation_only_count = sum(1 for row in not_scannable if "observation" in str((row.get("intraday") or {}).get("reason")))

    payload = {
        "status": "ok" if promotion_applied else "warn",
        "overall": "pass" if promotion_applied else "warn",
        "type": "dynamic_universe_builder_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "paper_context": bool(_paper_context()),
        "cache_hit": False,
        "promotion_applied": bool(promotion_applied),
        "data_error": data_error,
        "session_gate": session_policy,
        "seed_meta": seed_meta,
        "source_hygiene_active": True,
        "recent_rejected_seed_tokens": _LAST_SEED_REJECTIONS[:50],
        "base_universe_count": len(base),
        "seed_count": len(seeds),
        "daily_candidate_count": len(daily_candidates),
        "intraday_checked_count": intraday_checked,
        "promoted_count": len(promoted_symbols),
        "early_starter_count": len(early_starter_symbols),
        "final_universe_count": len(final_universe),
        "promoted_symbols": promoted_symbols[:MAX_PROMOTED_SYMBOLS],
        "early_starter_symbols": early_starter_symbols[:25],
        "promoted_and_scannable": promoted[:25],
        "daily_qualified_but_not_scannable": not_scannable[:25],
        "top_rejected": sorted(rejected, key=lambda r: _safe_float(r.get("promotion_score"), 0.0) or 0.0, reverse=True)[:25],
        "diagnostics": {"not_scannable_count": len(not_scannable), "no_intraday_data_count": no_intraday_count, "not_enough_intraday_bars_count": not_enough_bars_count, "bad_intraday_price_count": stale_or_bad_price_count, "opening_observation_only_count": observation_only_count, "intraday_gate_required": bool(REQUIRE_INTRADAY_DATA), "adaptive_intraday_gate_enabled": bool(ADAPTIVE_INTRADAY_GATE_ENABLED)},
        "policy": {
            "max_seed_symbols": MAX_SEED_SYMBOLS,
            "max_promoted_symbols": MAX_PROMOTED_SYMBOLS,
            "max_total_universe": MAX_TOTAL_UNIVERSE,
            "max_intraday_checks": MAX_INTRADAY_CHECKS,
            "min_price": MIN_PRICE,
            "min_avg_volume": MIN_AVG_VOLUME,
            "min_dollar_volume": MIN_DOLLAR_VOLUME,
            "min_move_pct": MIN_MOVE_PCT,
            "min_volume_ratio": MIN_VOLUME_RATIO,
            "min_promotion_score": MIN_PROMOTION_SCORE,
            "require_intraday_data": bool(REQUIRE_INTRADAY_DATA),
            "adaptive_intraday_gate_enabled": bool(ADAPTIVE_INTRADAY_GATE_ENABLED),
            "opening_observation_minutes": OPENING_OBSERVATION_MINUTES,
            "early_starter_until_minutes": EARLY_STARTER_UNTIL_MINUTES,
            "mid_session_until_minutes": MID_SESSION_UNTIL_MINUTES,
            "early_min_intraday_bars": EARLY_MIN_INTRADAY_BARS,
            "mid_min_intraday_bars": MID_MIN_INTRADAY_BARS,
            "min_intraday_bars": MIN_INTRADAY_BARS,
            "early_starter_alloc_factor": EARLY_STARTER_ALLOC_FACTOR,
            "allow_leveraged_etfs": bool(ALLOW_LEVERAGED_ETFS),
            "leveraged_max_promoted": LEVERAGED_MAX_PROMOTED,
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "does_not_trade": True,
            "does_not_lower_thresholds": True,
            "does_not_change_ml_authority": True,
            "does_not_grant_live_authority": True,
            "existing_quality_risk_regime_filters_still_apply": True,
        },
    }
    _CACHE.update({"ts": now, "payload": payload})
    return payload


def _tag_early_starter_signals(result: Any, payload: Dict[str, Any]) -> Any:
    early_symbols = set(_symbol(s) for s in (payload.get("early_starter_symbols") or []))
    if not early_symbols:
        return result
    try:
        long_signals = result[0] if isinstance(result, tuple) and len(result) >= 1 else []
        if not isinstance(long_signals, list):
            return result
        for signal in long_signals:
            if not isinstance(signal, dict):
                continue
            sym = _symbol(signal.get("symbol"))
            if sym not in early_symbols:
                continue
            current_alloc = _safe_float(signal.get("alloc_factor"), 1.0) or 1.0
            signal["alloc_factor"] = min(float(current_alloc), EARLY_STARTER_ALLOC_FACTOR)
            signal["entry_context"] = signal.get("entry_context") or "dynamic_universe_adaptive_early_starter"
            signal["trade_class"] = signal.get("trade_class") or "dynamic_universe_starter"
            signal["dynamic_universe_early_starter"] = True
            signal["dynamic_universe_builder"] = {
                "version": VERSION,
                "reason": "adaptive_early_starter_sizing",
                "alloc_factor": EARLY_STARTER_ALLOC_FACTOR,
                "session_gate": payload.get("session_gate"),
            }
    except Exception:
        return result
    return result


def _patch_scan_signals(core: Any) -> bool:
    current = getattr(core, "scan_signals", None)
    if not callable(current) or getattr(current, "_dynamic_universe_builder_patched", False):
        return False
    original = current

    def patched_scan_signals(market):
        payload = {}
        try:
            payload = build_dynamic_universe(core, force=False)
        except Exception:
            payload = {}
        result = original(market)
        return _tag_early_starter_signals(result, payload if isinstance(payload, dict) else {})

    patched_scan_signals._dynamic_universe_builder_patched = True  # type: ignore[attr-defined]
    patched_scan_signals._dynamic_universe_builder_original = original  # type: ignore[attr-defined]
    core.scan_signals = patched_scan_signals
    return True


def lightweight_status(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "dynamic_universe_builder_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "paper_context": bool(_paper_context()),
        "source_hygiene_active": True,
        "startup_heavy_build_deferred": True,
        "promotion_applied": False,
        "reason": "startup_patch_only; build runs inside scan_signals or when force=1",
        "authority_changed": False,
        "does_not_trade": True,
        "does_not_lower_thresholds": True,
        "does_not_change_ml_authority": True,
        "does_not_grant_live_authority": True,
        "filters": {
            "reserved_words_count": len(_RESERVED_WORDS),
            "known_no_data_symbols": sorted(_KNOWN_NO_DATA),
            "allowed_special_symbols": sorted(_ALLOWED_SPECIALS),
        },
    }


def status_payload(core: Any = None, force: bool = False) -> Dict[str, Any]:
    if force:
        return build_dynamic_universe(core or _mod(), force=True)
    return lightweight_status(core or _mod())


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return lightweight_status(core)
    patched = _patch_scan_signals(core)
    PATCHED_MODULE_IDS.add(id(core))
    payload = lightweight_status(core)
    payload["patched_scan_signals"] = bool(getattr(getattr(core, "scan_signals", None), "_dynamic_universe_builder_patched", False))
    payload["patched_this_call"] = {"scan_signals": bool(patched)}
    return payload


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify, request
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes"}
        return jsonify(status_payload(core or _mod(), force=force))

    if "/paper/dynamic-universe-builder-status" not in existing:
        flask_app.add_url_rule("/paper/dynamic-universe-builder-status", "dynamic_universe_builder_status", status_route)
    if "/paper/dynamic-universe" not in existing:
        flask_app.add_url_rule("/paper/dynamic-universe", "dynamic_universe_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
