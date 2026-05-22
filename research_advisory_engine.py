"""Research advisory scoring layer for scanner candidates.

Advisory-only Phase 1:
- Combines existing news/catalyst sentiment with optional FMP fundamentals.
- Produces ranking context for scanner candidates and blocked candidates.
- Persists compact research outcome rows for future ML validation.
- Does not place trades, resize positions, change max positions, or override risk controls.

This module intentionally uses only standard-library HTTP calls so it does not add
new deployment dependencies. Fundamental scoring is optional and is skipped when
FMP_API_KEY/FINANCIALMODELINGPREP_API_KEY is not configured.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "research-advisory-engine-2026-05-21-v1"

RESEARCH_ADVISORY_ENABLED = os.environ.get("RESEARCH_ADVISORY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
RESEARCH_ADVISORY_MAX_SYMBOLS = int(os.environ.get("RESEARCH_ADVISORY_MAX_SYMBOLS", "14"))
RESEARCH_ADVISORY_LOG_ENABLED = os.environ.get("RESEARCH_ADVISORY_LOG_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
RESEARCH_ADVISORY_PERSIST_LOG = os.environ.get("RESEARCH_ADVISORY_PERSIST_LOG", "true").lower() not in {"0", "false", "no", "off"}
RESEARCH_ADVISORY_MAX_STATE_ROWS = int(os.environ.get("RESEARCH_ADVISORY_MAX_STATE_ROWS", "300"))

RESEARCH_FUNDAMENTALS_ENABLED = os.environ.get("RESEARCH_FUNDAMENTALS_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
RESEARCH_FUNDAMENTAL_PROVIDER = os.environ.get("RESEARCH_FUNDAMENTAL_PROVIDER", "fmp").lower().strip() or "fmp"
RESEARCH_FUNDAMENTAL_MAX_SYMBOLS = int(os.environ.get("RESEARCH_FUNDAMENTAL_MAX_SYMBOLS", "8"))
RESEARCH_FUNDAMENTAL_TIMEOUT_SECONDS = float(os.environ.get("RESEARCH_FUNDAMENTAL_TIMEOUT_SECONDS", "3.0"))
RESEARCH_FUNDAMENTAL_CACHE_TTL_SECONDS = int(os.environ.get("RESEARCH_FUNDAMENTAL_CACHE_TTL_SECONDS", "3600"))

RESEARCH_SENTIMENT_WEIGHT = float(os.environ.get("RESEARCH_SENTIMENT_WEIGHT", "0.0012"))
RESEARCH_CATALYST_TAG_BONUS = float(os.environ.get("RESEARCH_CATALYST_TAG_BONUS", "0.00035"))
RESEARCH_MAX_NEWS_CATALYST_SCORE = float(os.environ.get("RESEARCH_MAX_NEWS_CATALYST_SCORE", "0.0050"))
RESEARCH_MIN_NEWS_CATALYST_SCORE = float(os.environ.get("RESEARCH_MIN_NEWS_CATALYST_SCORE", "-0.0060"))
RESEARCH_FUNDAMENTAL_WEIGHT = float(os.environ.get("RESEARCH_FUNDAMENTAL_WEIGHT", "0.0010"))
RESEARCH_VALUATION_WEIGHT = float(os.environ.get("RESEARCH_VALUATION_WEIGHT", "0.0010"))
RESEARCH_MAX_TOTAL_SCORE = float(os.environ.get("RESEARCH_MAX_TOTAL_SCORE", "0.0080"))
RESEARCH_MIN_TOTAL_SCORE = float(os.environ.get("RESEARCH_MIN_TOTAL_SCORE", "-0.0090"))
RESEARCH_RANK_BOOST_THRESHOLD = float(os.environ.get("RESEARCH_RANK_BOOST_THRESHOLD", "0.0030"))
RESEARCH_CAUTION_THRESHOLD = float(os.environ.get("RESEARCH_CAUTION_THRESHOLD", "-0.0030"))

_FUND_CACHE: Dict[str, Any] = {"ts": 0.0, "key": "", "payload": None}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _symbol(item: Any) -> str:
    if isinstance(item, str):
        return item.upper().strip()
    if isinstance(item, dict):
        value = item.get("symbol") or item.get("ticker")
        return str(value).upper().strip() if value else ""
    return ""


def _unique(items: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        sym = _symbol(item)
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def _now_text(core: Any = None) -> str:
    try:
        return core.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today(core: Any = None) -> str:
    try:
        return core.today_key()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d")


def _json_response(core: Any, payload: Dict[str, Any], endpoint: str):
    try:
        return core.json_response(payload, endpoint=endpoint)
    except Exception:
        from flask import jsonify
        return jsonify(payload)


def _state(core: Any) -> Dict[str, Any]:
    return _safe_dict(getattr(core, "portfolio", {}))


def _append_source(row: Dict[str, Any], source: str) -> None:
    sources = row.setdefault("sources", [])
    if source and source not in sources:
        sources.append(source)


def _candidate_rows(core: Any, limit: int = RESEARCH_ADVISORY_MAX_SYMBOLS) -> List[Dict[str, Any]]:
    state = _state(core)
    auto = _safe_dict(state.get("auto_runner"))
    last = _safe_dict(auto.get("last_result"))
    scanner = _safe_dict(state.get("scanner_audit"))
    perf = _safe_dict(state.get("performance"))
    positions = _safe_dict(state.get("positions"))
    open_positions = _safe_dict(perf.get("open_positions"))

    rows: Dict[str, Dict[str, Any]] = {}

    def ensure(sym: str, source: str = "", score: float = 0.0, sector: str | None = None) -> None:
        if not sym:
            return
        row = rows.setdefault(sym, {"symbol": sym, "technical_score": 0.0, "sector": None, "sources": []})
        if score:
            row["technical_score"] = max(_safe_float(row.get("technical_score"), 0.0), score)
        if sector and not row.get("sector"):
            row["sector"] = sector
        _append_source(row, source)

    for key in ("long_signals", "short_signals"):
        for item in _safe_list(last.get(key)) + _safe_list(scanner.get(key)):
            ensure(_symbol(item), key, _safe_float(_safe_dict(item).get("score"), 0.0) if isinstance(item, dict) else 0.0)

    for key in ("blocked_entries", "rejected_signals", "top_blocked", "top_rejected"):
        for item in _safe_list(last.get(key)) + _safe_list(scanner.get(key)):
            if isinstance(item, dict):
                ensure(_symbol(item), key, _safe_float(item.get("score"), 0.0), item.get("sector"))
            else:
                ensure(_symbol(item), key)

    for item in _safe_list(scanner.get("top_blocked_symbols")):
        ensure(_symbol(item), "top_blocked_symbols")

    for sym, pdata in positions.items():
        if isinstance(pdata, dict):
            ensure(str(sym).upper(), "open_position", _safe_float(pdata.get("score"), 0.0), pdata.get("sector"))
        else:
            ensure(str(sym).upper(), "open_position")

    for sym, pdata in open_positions.items():
        if isinstance(pdata, dict):
            ensure(str(sym).upper(), "open_position_performance", _safe_float(pdata.get("score"), 0.0), pdata.get("sector"))
        else:
            ensure(str(sym).upper(), "open_position_performance")

    if not rows:
        try:
            for sym in list(getattr(core, "UNIVERSE", []))[:limit]:
                ensure(str(sym).upper(), "universe_fallback")
        except Exception:
            pass

    ranked = sorted(rows.values(), key=lambda x: (_safe_float(x.get("technical_score"), 0.0), len(_safe_list(x.get("sources")))), reverse=True)
    return ranked[: max(1, limit)]


def _fmp_key() -> str:
    for name in ("FMP_API_KEY", "FINANCIALMODELINGPREP_API_KEY", "FINANCIAL_MODELING_PREP_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    return ""


def _fetch_json(url: str, timeout: float) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-research-advisory/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec - provider URL built internally
        raw = response.read(1_000_000)
    return json.loads(raw.decode("utf-8"))


def _fmp_url(path: str, symbol: str, key: str) -> str:
    return f"https://financialmodelingprep.com/api/v3/{path}/{urllib.parse.quote(symbol)}?apikey={urllib.parse.quote(key)}"


def _first_row(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        return payload
    return {}


def _score_fundamentals(profile: Dict[str, Any], ratios: Dict[str, Any]) -> Tuple[float, float, List[str], Dict[str, Any]]:
    reasons: List[str] = []
    quality = 0.0
    valuation = 0.0

    market_cap = _safe_float(profile.get("mktCap") or profile.get("marketCap"), 0.0)
    pe = _safe_float(profile.get("pe") or ratios.get("priceEarningsRatioTTM"), 0.0)
    ps = _safe_float(ratios.get("priceToSalesRatioTTM"), 0.0)
    roe = _safe_float(ratios.get("returnOnEquityTTM"), 0.0)
    margin = _safe_float(ratios.get("netProfitMarginTTM"), 0.0)
    current_ratio = _safe_float(ratios.get("currentRatioTTM"), 0.0)
    debt_equity = _safe_float(ratios.get("debtEquityRatioTTM"), 0.0)

    if market_cap >= 10_000_000_000:
        quality += 0.25
        reasons.append("large/liquid market cap")
    elif 0 < market_cap < 500_000_000:
        quality -= 0.35
        reasons.append("micro/small-cap fragility risk")

    if roe > 0.12:
        quality += 0.35
        reasons.append("positive ROE")
    elif roe < -0.05:
        quality -= 0.35
        reasons.append("negative ROE")

    if margin > 0.08:
        quality += 0.25
        reasons.append("positive net margin")
    elif margin < -0.05:
        quality -= 0.35
        reasons.append("negative net margin")

    if current_ratio >= 1.2:
        quality += 0.15
        reasons.append("adequate current ratio")
    elif 0 < current_ratio < 0.8:
        quality -= 0.20
        reasons.append("weak current ratio")

    if 0 < debt_equity <= 1.5:
        quality += 0.10
        reasons.append("manageable debt/equity")
    elif debt_equity > 3.0:
        quality -= 0.25
        reasons.append("elevated debt/equity")

    if 0 < pe <= 35:
        valuation += 0.30
        reasons.append("reasonable P/E context")
    elif pe > 80:
        valuation -= 0.30
        reasons.append("high P/E risk")
    elif pe < 0:
        valuation -= 0.30
        reasons.append("negative earnings context")

    if 0 < ps <= 8:
        valuation += 0.15
        reasons.append("reasonable P/S context")
    elif ps > 25:
        valuation -= 0.20
        reasons.append("high P/S risk")

    metrics = {
        "market_cap": market_cap or None,
        "pe": pe or None,
        "price_to_sales_ttm": ps or None,
        "roe_ttm": roe or None,
        "net_margin_ttm": margin or None,
        "current_ratio_ttm": current_ratio or None,
        "debt_equity_ttm": debt_equity or None,
    }
    return round(_clamp(quality, -1.5, 1.5), 4), round(_clamp(valuation, -1.0, 1.0), 4), reasons[:8], metrics


def _fetch_fundamentals(symbols: List[str], force_refresh: bool = False) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    selected = _unique(symbols)[: max(1, RESEARCH_FUNDAMENTAL_MAX_SYMBOLS)]
    key = _fmp_key()
    cache_key = ",".join(selected)
    now = time.time()
    diagnostics: Dict[str, Any] = {
        "enabled": bool(RESEARCH_FUNDAMENTALS_ENABLED),
        "provider": RESEARCH_FUNDAMENTAL_PROVIDER,
        "provider_configured": bool(key),
        "symbols_requested": selected,
        "symbols_loaded": 0,
        "cache_hit": False,
        "errors": [],
    }

    if not RESEARCH_FUNDAMENTALS_ENABLED:
        diagnostics["status_detail"] = "disabled_by_env"
        return {}, diagnostics
    if RESEARCH_FUNDAMENTAL_PROVIDER != "fmp":
        diagnostics["status_detail"] = "unsupported_provider"
        return {}, diagnostics
    if not key:
        diagnostics["status_detail"] = "missing_api_key"
        diagnostics["recommended_env_keys"] = ["FMP_API_KEY", "FINANCIALMODELINGPREP_API_KEY"]
        return {}, diagnostics
    if not force_refresh and _FUND_CACHE.get("payload") is not None and _FUND_CACHE.get("key") == cache_key and now - _safe_float(_FUND_CACHE.get("ts"), 0.0) < RESEARCH_FUNDAMENTAL_CACHE_TTL_SECONDS:
        diagnostics["cache_hit"] = True
        diagnostics["status_detail"] = "ok_cached"
        payload = _safe_dict(_FUND_CACHE.get("payload"))
        diagnostics["symbols_loaded"] = len(payload)
        return payload, diagnostics

    out: Dict[str, Dict[str, Any]] = {}
    for symbol in selected:
        try:
            profile = _first_row(_fetch_json(_fmp_url("profile", symbol, key), RESEARCH_FUNDAMENTAL_TIMEOUT_SECONDS))
            ratios = _first_row(_fetch_json(_fmp_url("ratios-ttm", symbol, key), RESEARCH_FUNDAMENTAL_TIMEOUT_SECONDS))
            quality, valuation, reasons, metrics = _score_fundamentals(profile, ratios)
            out[symbol] = {
                "symbol": symbol,
                "provider": "fmp",
                "loaded": bool(profile or ratios),
                "fundamental_quality_raw": quality,
                "valuation_context_raw": valuation,
                "fundamental_reasons": reasons,
                "metrics": metrics,
                "company_name": profile.get("companyName") or profile.get("company_name"),
                "sector": profile.get("sector"),
                "industry": profile.get("industry"),
            }
        except Exception as exc:
            diagnostics["errors"].append({"symbol": symbol, "error": f"{type(exc).__name__}: {str(exc)[:180]}"})
    diagnostics["symbols_loaded"] = len(out)
    diagnostics["status_detail"] = "ok" if out else "provider_returned_no_fundamentals"
    _FUND_CACHE.update({"ts": now, "key": cache_key, "payload": out})
    return out, diagnostics


def _news_status(core: Any, symbols: List[str], force_refresh: bool = False) -> Dict[str, Any]:
    try:
        import news_sentiment_engine
        return _safe_dict(news_sentiment_engine.build_news_sentiment_status(core, symbols=symbols, force_refresh=force_refresh))
    except Exception as exc:
        return {
            "status": "warn",
            "type": "news_sentiment_status_unavailable",
            "version": VERSION,
            "error": f"{type(exc).__name__}: {str(exc)[:180]}",
            "sentiment_by_symbol": {},
            "provider_diagnostics": {"status_detail": "news_module_unavailable"},
        }


def _compose_research_rows(
    candidates: List[Dict[str, Any]],
    sentiment_by_symbol: Dict[str, Any],
    fundamentals_by_symbol: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for candidate in candidates:
        symbol = str(candidate.get("symbol") or "").upper()
        if not symbol:
            continue
        sentiment = _safe_dict(sentiment_by_symbol.get(symbol))
        fundamental = _safe_dict(fundamentals_by_symbol.get(symbol))
        raw_sentiment = _safe_float(sentiment.get("sentiment_score"), 0.0)
        tags = _safe_list(sentiment.get("catalyst_tags"))
        news_catalyst_score = _clamp(
            raw_sentiment * RESEARCH_SENTIMENT_WEIGHT + min(len(tags), 6) * RESEARCH_CATALYST_TAG_BONUS,
            RESEARCH_MIN_NEWS_CATALYST_SCORE,
            RESEARCH_MAX_NEWS_CATALYST_SCORE,
        )
        fundamental_quality_score = _clamp(_safe_float(fundamental.get("fundamental_quality_raw"), 0.0) * RESEARCH_FUNDAMENTAL_WEIGHT, -0.003, 0.003)
        valuation_context_score = _clamp(_safe_float(fundamental.get("valuation_context_raw"), 0.0) * RESEARCH_VALUATION_WEIGHT, -0.0025, 0.0025)
        retail_attention_score = 0.0
        research_advisory_score = _clamp(
            news_catalyst_score + fundamental_quality_score + valuation_context_score + retail_attention_score,
            RESEARCH_MIN_TOTAL_SCORE,
            RESEARCH_MAX_TOTAL_SCORE,
        )
        technical_score = _safe_float(candidate.get("technical_score"), 0.0)
        combined = technical_score + research_advisory_score

        reasons: List[str] = []
        if raw_sentiment:
            reasons.append(f"news_sentiment={round(raw_sentiment, 3)}")
        if tags:
            reasons.append("catalyst_tags=" + ",".join(str(t) for t in tags[:4]))
        reasons.extend(_safe_list(fundamental.get("fundamental_reasons"))[:4])
        if not fundamental.get("loaded"):
            reasons.append("fundamentals_not_loaded_or_not_configured")

        if research_advisory_score >= RESEARCH_RANK_BOOST_THRESHOLD and technical_score > 0:
            advisory = "rank_boost_candidate"
        elif research_advisory_score <= RESEARCH_CAUTION_THRESHOLD:
            advisory = "caution_or_reduce_future_phase"
        elif research_advisory_score > 0 and technical_score <= 0:
            advisory = "watch_only_wait_for_technical_confirmation"
        else:
            advisory = "neutral_collect_data"

        rows.append({
            "symbol": symbol,
            "sector": candidate.get("sector") or fundamental.get("sector"),
            "sources": _safe_list(candidate.get("sources")),
            "technical_score": round(technical_score, 6),
            "news_catalyst_score": round(news_catalyst_score, 6),
            "fundamental_quality_score": round(fundamental_quality_score, 6),
            "valuation_context_score": round(valuation_context_score, 6),
            "retail_attention_score": round(retail_attention_score, 6),
            "research_advisory_score": round(research_advisory_score, 6),
            "technical_plus_research_score": round(combined, 6),
            "sentiment_bias": sentiment.get("sentiment_bias") or "not_available",
            "raw_sentiment_score": round(raw_sentiment, 3),
            "catalyst_tags": tags[:8],
            "fundamental_provider": fundamental.get("provider"),
            "fundamental_loaded": bool(fundamental.get("loaded")),
            "fundamental_metrics": _safe_dict(fundamental.get("metrics")),
            "research_reasons": reasons[:10],
            "advisory_action": advisory,
            "live_trade_authority_changed": False,
        })
    return sorted(rows, key=lambda x: (_safe_float(x.get("technical_plus_research_score"), 0.0), _safe_float(x.get("research_advisory_score"), 0.0)), reverse=True)


def _persist_research_log(core: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = {
        "enabled": bool(RESEARCH_ADVISORY_LOG_ENABLED),
        "persist_enabled": bool(RESEARCH_ADVISORY_PERSIST_LOG),
        "rows_added_or_updated": 0,
        "state_rows_after": 0,
        "max_rows": RESEARCH_ADVISORY_MAX_STATE_ROWS,
        "headlines_stored_in_state": False,
        "fundamental_details_stored_in_state": False,
        "persisted": False,
        "status": "skipped",
    }
    if not RESEARCH_ADVISORY_LOG_ENABLED:
        return summary
    state = _state(core)
    if not state:
        summary["status"] = "no_state"
        return summary

    existing_rows = _safe_list(_safe_dict(state.get("research_advisory_log")).get("rows"))
    existing: Dict[str, Dict[str, Any]] = {}
    for row in existing_rows:
        if isinstance(row, dict) and row.get("key"):
            existing[str(row.get("key"))] = row

    generated = str(payload.get("generated_local") or _now_text(core))
    cycle_key = generated[:16]
    changed = 0
    for row in _safe_list(payload.get("research_rows")):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if not symbol:
            continue
        key = f"{cycle_key}|{symbol}"
        compact = {
            "key": key,
            "time_local": generated,
            "date": payload.get("date"),
            "symbol": symbol,
            "technical_score": row.get("technical_score"),
            "news_catalyst_score": row.get("news_catalyst_score"),
            "fundamental_quality_score": row.get("fundamental_quality_score"),
            "valuation_context_score": row.get("valuation_context_score"),
            "research_advisory_score": row.get("research_advisory_score"),
            "technical_plus_research_score": row.get("technical_plus_research_score"),
            "sentiment_bias": row.get("sentiment_bias"),
            "advisory_action": row.get("advisory_action"),
            "fundamental_loaded": row.get("fundamental_loaded"),
            "live_trade_authority_changed": False,
        }
        if existing.get(key) != compact:
            existing[key] = compact
            changed += 1

    trimmed = sorted(existing.values(), key=lambda x: str(x.get("key") or ""))[-max(1, RESEARCH_ADVISORY_MAX_STATE_ROWS):]
    state["research_advisory_log"] = {
        "version": VERSION,
        "updated_local": generated,
        "rows": trimmed,
        "max_rows": RESEARCH_ADVISORY_MAX_STATE_ROWS,
        "headlines_stored_in_state": False,
        "fundamental_details_stored_in_state": False,
        "notes": [
            "Advisory-only scanner ranking telemetry for validation before any live authority.",
            "Compact scores only; no headlines, article URLs, or full fundamental payloads are persisted.",
        ],
    }
    summary.update({"rows_added_or_updated": changed, "state_rows_after": len(trimmed), "status": "ok"})
    if changed and RESEARCH_ADVISORY_PERSIST_LOG:
        try:
            save = getattr(core, "save_state", None)
            if callable(save):
                save(state)
                summary["persisted"] = True
        except Exception as exc:
            summary["persist_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    return summary


def build_research_advisory_status(core: Any, symbols: List[str] | None = None, force_refresh: bool = False) -> Dict[str, Any]:
    if symbols:
        candidates = [{"symbol": sym, "technical_score": 0.0, "sector": None, "sources": ["manual_query"]} for sym in _unique(symbols)[:RESEARCH_ADVISORY_MAX_SYMBOLS]]
    else:
        candidates = _candidate_rows(core, RESEARCH_ADVISORY_MAX_SYMBOLS)
    selected = [str(row.get("symbol") or "").upper() for row in candidates if row.get("symbol")]

    news = _news_status(core, selected, force_refresh=force_refresh)
    fundamentals, fundamental_diag = _fetch_fundamentals(selected, force_refresh=force_refresh)
    research_rows = _compose_research_rows(candidates, _safe_dict(news.get("sentiment_by_symbol")), fundamentals)

    payload = {
        "status": "ok" if RESEARCH_ADVISORY_ENABLED else "disabled",
        "type": "research_advisory_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "date": _today(core),
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "enabled": bool(RESEARCH_ADVISORY_ENABLED),
        "symbols_checked": selected,
        "research_rows": research_rows,
        "top_ranked": research_rows[:20],
        "score_components": {
            "news_catalyst_score": "derived from news sentiment and catalyst tags",
            "fundamental_quality_score": "optional FMP quality metrics when API key is configured",
            "valuation_context_score": "optional FMP valuation metrics when API key is configured",
            "retail_attention_score": "reserved for a future retail/social sentiment provider",
        },
        "provider_diagnostics": {
            "news": news.get("provider_diagnostics"),
            "fundamentals": fundamental_diag,
        },
        "policy": {
            "trade_authority": "advisory_only_phase_1",
            "changes_live_entries_now": False,
            "changes_position_size_now": False,
            "changes_risk_controls_now": False,
            "future_use": "ranking boost/penalty only after enough paper outcomes validate it",
        },
        "recommended_actions": [
            "Use top_ranked to compare scanner candidates, not to force trades.",
            "Keep negative research rows as future caution flags until outcome data validates them.",
            "Configure FMP_API_KEY later if fundamental scoring should use live FMP metrics.",
        ],
    }
    payload["outcome_logger"] = _persist_research_log(core, payload)
    payload["state_protection"] = {
        "active": True,
        "headlines_stored_in_state": False,
        "fundamental_details_stored_in_state": False,
        "max_state_rows": RESEARCH_ADVISORY_MAX_STATE_ROWS,
        "state_rows_after": payload["outcome_logger"].get("state_rows_after"),
        "live_trade_authority_changed": False,
    }
    return payload


def build_scanner_research_ranking(core: Any, symbols: List[str] | None = None, force_refresh: bool = False) -> Dict[str, Any]:
    status = build_research_advisory_status(core, symbols=symbols, force_refresh=force_refresh)
    rows = _safe_list(status.get("research_rows"))
    boost = [r for r in rows if isinstance(r, dict) and r.get("advisory_action") == "rank_boost_candidate"]
    caution = [r for r in rows if isinstance(r, dict) and r.get("advisory_action") == "caution_or_reduce_future_phase"]
    watch = [r for r in rows if isinstance(r, dict) and r.get("advisory_action") == "watch_only_wait_for_technical_confirmation"]
    return {
        "status": "ok",
        "type": "scanner_research_ranking",
        "version": VERSION,
        "generated_local": _now_text(core),
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "ranked_candidates": rows[:25],
        "rank_boost_candidates": boost[:15],
        "caution_candidates": caution[:15],
        "watch_only_candidates": watch[:15],
        "provider_diagnostics": status.get("provider_diagnostics"),
        "policy": status.get("policy"),
        "state_protection": status.get("state_protection"),
    }


def build_fundamental_score_status(core: Any, symbols: List[str] | None = None, force_refresh: bool = False) -> Dict[str, Any]:
    selected = _unique(symbols or [row.get("symbol") for row in _candidate_rows(core, RESEARCH_FUNDAMENTAL_MAX_SYMBOLS)])[:RESEARCH_FUNDAMENTAL_MAX_SYMBOLS]
    fundamentals, diagnostics = _fetch_fundamentals(selected, force_refresh=force_refresh)
    return {
        "status": "ok",
        "type": "fundamental_score_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "symbols_checked": selected,
        "fundamentals_by_symbol": fundamentals,
        "provider_diagnostics": diagnostics,
        "policy": {
            "trade_authority": "advisory_only",
            "missing_api_key_is_not_a_failure": True,
            "recommended_env_keys": ["FMP_API_KEY", "FINANCIALMODELINGPREP_API_KEY"],
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "research_advisory_engine_apply",
        "version": VERSION,
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "state_safe": True,
        "enabled": bool(RESEARCH_ADVISORY_ENABLED),
    }


def register_routes(flask_app: Any = None, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    if core is None:
        try:
            import app as core  # type: ignore[no-redef]
        except Exception:
            core = None
    if core is None:
        return {"status": "error", "version": VERSION, "error": "core_module_missing"}

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def _parse_request():
        force = False
        symbols = None
        try:
            from flask import request
            force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes", "on"}
            raw = request.args.get("symbols") or request.args.get("tickers")
            if raw:
                symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
        except Exception:
            pass
        return symbols, force

    if "/paper/research-advisory-status" not in existing:
        def research_advisory_status():
            symbols, force = _parse_request()
            return _json_response(core, build_research_advisory_status(core, symbols=symbols, force_refresh=force), endpoint="paper_research_advisory_status")
        flask_app.add_url_rule("/paper/research-advisory-status", "paper_research_advisory_status", research_advisory_status)

    if "/paper/scanner-research-ranking" not in existing:
        def scanner_research_ranking():
            symbols, force = _parse_request()
            return _json_response(core, build_scanner_research_ranking(core, symbols=symbols, force_refresh=force), endpoint="paper_scanner_research_ranking")
        flask_app.add_url_rule("/paper/scanner-research-ranking", "paper_scanner_research_ranking", scanner_research_ranking)

    if "/paper/fundamental-score-status" not in existing:
        def fundamental_score_status():
            symbols, force = _parse_request()
            return _json_response(core, build_fundamental_score_status(core, symbols=symbols, force_refresh=force), endpoint="paper_fundamental_score_status")
        flask_app.add_url_rule("/paper/fundamental-score-status", "paper_fundamental_score_status", fundamental_score_status)

    return {
        "status": "ok",
        "type": "research_advisory_engine_register_routes",
        "version": VERSION,
        "routes_installed": True,
        "routes": [
            "/paper/research-advisory-status",
            "/paper/scanner-research-ranking",
            "/paper/fundamental-score-status",
        ],
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "state_safe": True,
    }
