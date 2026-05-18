"""News sentiment and catalyst visibility layer.

Advisory-only: this module summarizes ticker-level news/catalyst risk for the
paper bot. It does not place trades, resize positions, enable live authority, or
override price-action/risk controls.

2026-05-18 v2 adds:
- bounded payload/headline handling so news data does not inflate state reports;
- compact outcome logging under state["news_sentiment_research"] with a hard row cap;
- shadow-only catalyst bonus candidates that require a near-qualified technical signal.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "news-sentiment-engine-2026-05-18-advisory-v2-state-safe"

NEWS_SENTIMENT_ENABLED = os.environ.get("NEWS_SENTIMENT_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
NEWS_SENTIMENT_PROVIDER = os.environ.get("NEWS_SENTIMENT_PROVIDER", "polygon").lower().strip() or "polygon"
NEWS_SENTIMENT_MAX_SYMBOLS = int(os.environ.get("NEWS_SENTIMENT_MAX_SYMBOLS", "12"))
NEWS_SENTIMENT_ARTICLES_PER_SYMBOL = int(os.environ.get("NEWS_SENTIMENT_ARTICLES_PER_SYMBOL", "3"))
NEWS_SENTIMENT_LOOKBACK_HOURS = int(os.environ.get("NEWS_SENTIMENT_LOOKBACK_HOURS", "48"))
NEWS_SENTIMENT_TIMEOUT_SECONDS = float(os.environ.get("NEWS_SENTIMENT_TIMEOUT_SECONDS", "4.0"))
NEWS_SENTIMENT_CACHE_TTL_SECONDS = int(os.environ.get("NEWS_SENTIMENT_CACHE_TTL_SECONDS", "600"))
NEWS_SENTIMENT_NEGATIVE_BLOCK_THRESHOLD = float(os.environ.get("NEWS_SENTIMENT_NEGATIVE_BLOCK_THRESHOLD", "-1.50"))
NEWS_SENTIMENT_POSITIVE_BONUS_THRESHOLD = float(os.environ.get("NEWS_SENTIMENT_POSITIVE_BONUS_THRESHOLD", "1.25"))
NEWS_SENTIMENT_HYPE_ONLY_MAX_TECHNICAL_SCORE = float(os.environ.get("NEWS_SENTIMENT_HYPE_ONLY_MAX_TECHNICAL_SCORE", "0.010"))
NEWS_SENTIMENT_MAX_SCORE_BONUS = float(os.environ.get("NEWS_SENTIMENT_MAX_SCORE_BONUS", "0.0015"))

NEWS_SENTIMENT_MAX_HEADLINES_PER_SYMBOL = int(os.environ.get("NEWS_SENTIMENT_MAX_HEADLINES_PER_SYMBOL", "3"))
NEWS_SENTIMENT_MAX_ARTICLE_TEXT_CHARS = int(os.environ.get("NEWS_SENTIMENT_MAX_ARTICLE_TEXT_CHARS", "220"))
NEWS_SENTIMENT_MAX_STATE_OUTCOME_ROWS = int(os.environ.get("NEWS_SENTIMENT_MAX_STATE_OUTCOME_ROWS", "250"))
NEWS_SENTIMENT_MAX_STATE_SYMBOL_ROWS_PER_CYCLE = int(os.environ.get("NEWS_SENTIMENT_MAX_STATE_SYMBOL_ROWS_PER_CYCLE", "20"))
NEWS_SENTIMENT_OUTCOME_LOG_ENABLED = os.environ.get("NEWS_SENTIMENT_OUTCOME_LOG_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
NEWS_SENTIMENT_PERSIST_OUTCOME_LOG = os.environ.get("NEWS_SENTIMENT_PERSIST_OUTCOME_LOG", "true").lower() not in {"0", "false", "no", "off"}
NEWS_SENTIMENT_NEAR_FLOOR_GAP = float(os.environ.get("NEWS_SENTIMENT_NEAR_FLOOR_GAP", "0.005"))
NEWS_SENTIMENT_SHADOW_BONUS_ENABLED = os.environ.get("NEWS_SENTIMENT_SHADOW_BONUS_ENABLED", "true").lower() not in {"0", "false", "no", "off"}

_CACHE: Dict[str, Any] = {"ts": 0.0, "key": "", "payload": None}

POSITIVE_WORDS = {
    "upgrade", "raises", "raised", "outperform", "beat", "beats", "surge", "surges", "rally", "record",
    "contract", "wins", "partnership", "partners", "guidance", "expands", "approval", "approved", "buyback",
    "acquisition", "merger", "strong", "growth", "profit", "profitable", "launch", "orders", "backlog",
}
NEGATIVE_WORDS = {
    "downgrade", "cuts", "cut", "miss", "misses", "lawsuit", "probe", "investigation", "sec", "doj",
    "recall", "halt", "halts", "delay", "delays", "bankruptcy", "fraud", "short-seller", "short seller",
    "weak", "loss", "losses", "guidance cut", "slump", "falls", "drops", "selloff", "sanctions",
}
CATALYST_PATTERNS = {
    "earnings": re.compile(r"\b(earnings|eps|revenue|quarter|guidance|profit|margin)\b", re.I),
    "analyst": re.compile(r"\b(upgrade|downgrade|price target|outperform|underperform|buy rating|sell rating)\b", re.I),
    "regulatory_legal": re.compile(r"\b(sec|doj|ftc|lawsuit|probe|investigation|regulator|sanction|compliance)\b", re.I),
    "deal_partner": re.compile(r"\b(acquisition|merger|deal|contract|partnership|partners|customer|orders|supply)\b", re.I),
    "ai_data_center": re.compile(r"\b(ai|artificial intelligence|data center|datacenter|gpu|semiconductor|chip|server|power demand)\b", re.I),
    "crypto": re.compile(r"\b(bitcoin|crypto|mining|mining rig|hashrate|ethereum|blockchain)\b", re.I),
    "energy_power": re.compile(r"\b(energy|power|utility|nuclear|grid|electricity|natural gas|oil|lng)\b", re.I),
    "precious_metals": re.compile(r"\b(gold|silver|miner|miners|bullion|precious metals|royalty|streaming)\b", re.I),
}


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


def _trim_text(value: Any, limit: int = NEWS_SENTIMENT_MAX_ARTICLE_TEXT_CHARS) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


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


def _provider_key() -> str:
    for name in ("MASSIVE_API_KEY", "POLYGON_API_KEY", "POLYGON_KEY", "MARKET_DATA_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    return ""


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


def _extract_symbols(core: Any, limit: int = NEWS_SENTIMENT_MAX_SYMBOLS) -> List[str]:
    state = _safe_dict(getattr(core, "portfolio", {}))
    auto = _safe_dict(state.get("auto_runner"))
    last = _safe_dict(auto.get("last_result"))
    scanner = _safe_dict(state.get("scanner_audit"))

    candidates: List[Any] = []
    for key in ("long_signals", "short_signals"):
        candidates.extend(_safe_list(last.get(key)))
        candidates.extend(_safe_list(scanner.get(key)))
    for key in ("blocked_entries", "rejected_signals"):
        candidates.extend(_safe_list(last.get(key)))
        candidates.extend(_safe_list(scanner.get(key)))
    candidates.extend(_safe_list(scanner.get("top_blocked_symbols")))

    if not candidates:
        try:
            candidates.extend(list(getattr(core, "UNIVERSE", []))[:limit])
        except Exception:
            pass
    return _unique(candidates)[:max(1, limit)]


def _article_text(article: Dict[str, Any]) -> str:
    parts = [
        str(article.get("title") or ""),
        str(article.get("description") or ""),
        str(article.get("summary") or ""),
        " ".join(str(x) for x in _safe_list(article.get("keywords"))),
    ]
    return " ".join(parts).strip()


def _tags_for_text(text: str) -> List[str]:
    tags = []
    for tag, pattern in CATALYST_PATTERNS.items():
        if pattern.search(text or ""):
            tags.append(tag)
    return tags


def _keyword_score(text: str) -> float:
    lower = (text or "").lower()
    pos = sum(1 for word in POSITIVE_WORDS if word in lower)
    neg = sum(1 for word in NEGATIVE_WORDS if word in lower)
    return float(pos - neg) * 0.35


def _insight_score(article: Dict[str, Any], symbol: str) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []
    for insight in _safe_list(article.get("insights")):
        if not isinstance(insight, dict):
            continue
        ticker = str(insight.get("ticker") or "").upper()
        if ticker and ticker != symbol.upper():
            continue
        sentiment = str(insight.get("sentiment") or "").lower()
        if sentiment == "positive":
            score += 1.0
        elif sentiment == "negative":
            score -= 1.0
        reasoning = _trim_text(insight.get("sentiment_reasoning"), 180)
        if reasoning:
            reasons.append(reasoning)
    return score, reasons[:3]


def _compact_article(article: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    text = _article_text(article)
    insight_score, insight_reasons = _insight_score(article, symbol)
    keyword_score = _keyword_score(text)
    score = round(insight_score + keyword_score, 3)
    if score > 0.25:
        sentiment = "positive"
    elif score < -0.25:
        sentiment = "negative"
    else:
        sentiment = "neutral"
    return {
        "symbol": symbol,
        "title": _trim_text(article.get("title"), NEWS_SENTIMENT_MAX_ARTICLE_TEXT_CHARS),
        "publisher": _trim_text(_safe_dict(article.get("publisher")).get("name") or article.get("source") or article.get("publisher"), 80),
        "published_utc": article.get("published_utc") or article.get("published_at") or article.get("date"),
        "article_url": article.get("article_url") or article.get("url"),
        "sentiment": sentiment,
        "sentiment_score": score,
        "catalyst_tags": _tags_for_text(text),
        "sentiment_reasons": insight_reasons,
    }


def _polygon_news_url(symbol: str, key: str) -> str:
    start = (dt.datetime.utcnow() - dt.timedelta(hours=NEWS_SENTIMENT_LOOKBACK_HOURS)).strftime("%Y-%m-%d")
    params = {
        "ticker": symbol,
        "published_utc.gte": start,
        "order": "desc",
        "limit": str(max(1, NEWS_SENTIMENT_ARTICLES_PER_SYMBOL)),
        "sort": "published_utc",
        "apiKey": key,
    }
    return "https://api.polygon.io/v2/reference/news?" + urllib.parse.urlencode(params)


def _fetch_json(url: str, timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-news-sentiment/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec - trusted provider URL built internally
        raw = response.read(1_000_000)
    return json.loads(raw.decode("utf-8"))


def _fetch_provider_news(symbols: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    key = _provider_key()
    diagnostics: Dict[str, Any] = {
        "enabled": NEWS_SENTIMENT_ENABLED,
        "provider": NEWS_SENTIMENT_PROVIDER,
        "provider_configured": bool(key),
        "articles_per_symbol": NEWS_SENTIMENT_ARTICLES_PER_SYMBOL,
        "lookback_hours": NEWS_SENTIMENT_LOOKBACK_HOURS,
        "symbols_requested": symbols,
        "errors": [],
    }
    if not NEWS_SENTIMENT_ENABLED:
        diagnostics["status_detail"] = "disabled_by_env"
        return [], diagnostics
    if NEWS_SENTIMENT_PROVIDER not in {"polygon", "massive"}:
        diagnostics["status_detail"] = "unsupported_provider"
        return [], diagnostics
    if not key:
        diagnostics["status_detail"] = "missing_api_key"
        diagnostics["recommended_env_keys"] = ["MASSIVE_API_KEY", "POLYGON_API_KEY"]
        return [], diagnostics

    rows: List[Dict[str, Any]] = []
    for symbol in symbols:
        try:
            payload = _fetch_json(_polygon_news_url(symbol, key), NEWS_SENTIMENT_TIMEOUT_SECONDS)
            for article in _safe_list(payload.get("results")):
                if isinstance(article, dict):
                    rows.append(_compact_article(article, symbol))
        except Exception as exc:
            diagnostics["errors"].append({"symbol": symbol, "error": f"{type(exc).__name__}: {str(exc)[:180]}"})
    diagnostics["articles_loaded"] = len(rows)
    diagnostics["status_detail"] = "ok" if rows else ("provider_returned_no_articles" if key else "missing_api_key")
    return rows, diagnostics


def _score_by_symbol(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        sym = _symbol(row)
        if sym:
            grouped.setdefault(sym, []).append(row)
    out: Dict[str, Dict[str, Any]] = {}
    for symbol, articles in grouped.items():
        total = round(sum(_safe_float(a.get("sentiment_score"), 0.0) for a in articles), 3)
        tags: List[str] = []
        headlines = []
        for article in articles:
            if article.get("title"):
                headlines.append(_trim_text(article.get("title"), NEWS_SENTIMENT_MAX_ARTICLE_TEXT_CHARS))
            for tag in _safe_list(article.get("catalyst_tags")):
                if tag not in tags:
                    tags.append(tag)
        if total >= NEWS_SENTIMENT_POSITIVE_BONUS_THRESHOLD:
            bias = "positive_catalyst"
        elif total <= NEWS_SENTIMENT_NEGATIVE_BLOCK_THRESHOLD:
            bias = "negative_headline_risk"
        else:
            bias = "mixed_or_neutral"
        out[symbol] = {
            "symbol": symbol,
            "article_count": len(articles),
            "sentiment_score": total,
            "sentiment_bias": bias,
            "catalyst_tags": tags[:8],
            "latest_headlines": headlines[: max(0, NEWS_SENTIMENT_MAX_HEADLINES_PER_SYMBOL)],
        }
    return out


def _latest_scores(core: Any) -> Dict[str, float]:
    state = _safe_dict(getattr(core, "portfolio", {}))
    last = _safe_dict(_safe_dict(state.get("auto_runner")).get("last_result"))
    scanner = _safe_dict(state.get("scanner_audit"))
    out: Dict[str, float] = {}
    for source in (last, scanner):
        for key in ("blocked_entries", "rejected_signals", "top_blocked", "top_rejected"):
            for row in _safe_list(_safe_dict(source).get(key)):
                if isinstance(row, dict):
                    sym = _symbol(row)
                    if sym:
                        out[sym] = max(out.get(sym, 0.0), _safe_float(row.get("score"), 0.0))
    return out


def _active_min_long_score(core: Any) -> float:
    default = float(os.environ.get("MIN_ENTRY_SCORE_NEUTRAL", "0.033"))
    state = _safe_dict(getattr(core, "portfolio", {}))
    last = _safe_dict(_safe_dict(state.get("auto_runner")).get("last_result"))
    feedback = _safe_dict(state.get("feedback_loop"))
    runtime_controls = _safe_dict(state.get("runtime_controls"))
    for source in (last, feedback, runtime_controls, _safe_dict(last.get("permission_snapshot"))):
        for key in ("active_min_long_score", "dynamic_min_long_score", "min_long_score", "min_entry_score"):
            value = _safe_float(_safe_dict(source).get(key), 0.0)
            if value > 0:
                return value
    return default


def _payload_size_bytes(payload: Dict[str, Any]) -> int:
    try:
        return len(json.dumps(payload, default=str).encode("utf-8"))
    except Exception:
        return 0


def _persist_core_state(core: Any, state: Dict[str, Any]) -> bool:
    if not NEWS_SENTIMENT_PERSIST_OUTCOME_LOG:
        return False
    try:
        save = getattr(core, "save_state", None)
        if callable(save):
            save(state)
            return True
    except Exception:
        return False
    return False


def _update_news_research_log(core: Any, payload: Dict[str, Any], technical_scores: Dict[str, float], active_floor: float) -> Dict[str, Any]:
    summary = {
        "enabled": bool(NEWS_SENTIMENT_OUTCOME_LOG_ENABLED),
        "persist_enabled": bool(NEWS_SENTIMENT_PERSIST_OUTCOME_LOG),
        "state_rows_before": 0,
        "state_rows_after": 0,
        "rows_added_or_updated": 0,
        "max_rows": NEWS_SENTIMENT_MAX_STATE_OUTCOME_ROWS,
        "headlines_stored_in_state": False,
        "persisted": False,
        "status": "skipped",
    }
    if not NEWS_SENTIMENT_OUTCOME_LOG_ENABLED:
        return summary

    state = _safe_dict(getattr(core, "portfolio", {}))
    if not state:
        summary["status"] = "no_state"
        return summary

    research = _safe_dict(state.get("news_sentiment_research"))
    rows = _safe_list(research.get("rows"))
    summary["state_rows_before"] = len(rows)

    generated = str(payload.get("generated_local") or _now_text(core))
    cycle_key = generated[:16]
    sentiment = _safe_dict(payload.get("sentiment_by_symbol"))
    shadow_symbols = {str(row.get("symbol")) for row in _safe_list(payload.get("shadow_bonus_candidates")) if isinstance(row, dict)}
    block_symbols = {str(row.get("symbol")) for row in _safe_list(payload.get("advisory_negative_headline_blocks")) if isinstance(row, dict)}

    existing: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict):
            key = str(row.get("key") or "")
            if key:
                existing[key] = row

    changed = 0
    for symbol in list(sentiment.keys())[: max(1, NEWS_SENTIMENT_MAX_STATE_SYMBOL_ROWS_PER_CYCLE)]:
        info = _safe_dict(sentiment.get(symbol))
        technical = round(_safe_float(technical_scores.get(symbol), 0.0), 6)
        sentiment_score = round(_safe_float(info.get("sentiment_score"), 0.0), 3)
        gap = round(active_floor - technical, 6) if technical > 0 else None
        row_key = f"{cycle_key}|{symbol}"
        row = {
            "key": row_key,
            "time_local": generated,
            "date": payload.get("date"),
            "symbol": symbol,
            "sentiment_score": sentiment_score,
            "sentiment_bias": info.get("sentiment_bias"),
            "article_count": _safe_int(info.get("article_count"), 0),
            "catalyst_tags": _safe_list(info.get("catalyst_tags"))[:8],
            "technical_score": technical,
            "active_min_long_score": round(active_floor, 6),
            "gap_to_floor": gap,
            "near_floor": bool(gap is not None and 0 <= gap <= NEWS_SENTIMENT_NEAR_FLOOR_GAP),
            "shadow_bonus_candidate": symbol in shadow_symbols,
            "negative_risk_candidate": symbol in block_symbols,
            "live_trade_authority_changed": False,
        }
        prior = existing.get(row_key)
        if prior != row:
            existing[row_key] = row
            changed += 1

    trimmed = sorted(existing.values(), key=lambda x: str(x.get("key") or ""))[-max(1, NEWS_SENTIMENT_MAX_STATE_OUTCOME_ROWS):]
    research = {
        "version": VERSION,
        "updated_local": generated,
        "rows": trimmed,
        "max_rows": NEWS_SENTIMENT_MAX_STATE_OUTCOME_ROWS,
        "headlines_stored_in_state": False,
        "notes": [
            "Compact research log only; headlines and article URLs are intentionally excluded from persistent state.",
            "Rows support future validation of whether catalyst bonuses improve outcomes before live authority is considered.",
        ],
    }
    state["news_sentiment_research"] = research

    summary.update({
        "state_rows_after": len(trimmed),
        "rows_added_or_updated": changed,
        "persisted": _persist_core_state(core, state) if changed else False,
        "status": "ok",
    })
    return summary


def _build_shadow_bonus_candidates(score_map: Dict[str, Dict[str, Any]], technical_scores: Dict[str, float], active_floor: float) -> List[Dict[str, Any]]:
    if not NEWS_SENTIMENT_SHADOW_BONUS_ENABLED:
        return []
    out: List[Dict[str, Any]] = []
    for symbol, info in score_map.items():
        sentiment_score = _safe_float(_safe_dict(info).get("sentiment_score"), 0.0)
        if sentiment_score < NEWS_SENTIMENT_POSITIVE_BONUS_THRESHOLD:
            continue
        technical = _safe_float(technical_scores.get(symbol), 0.0)
        if technical <= 0:
            continue
        gap = active_floor - technical
        if gap < 0 or gap > NEWS_SENTIMENT_NEAR_FLOOR_GAP:
            continue
        out.append({
            "symbol": symbol,
            "reason": "positive_news_near_existing_technical_floor",
            "sentiment_score": round(sentiment_score, 3),
            "technical_score": round(technical, 6),
            "active_min_long_score": round(active_floor, 6),
            "gap_to_floor": round(gap, 6),
            "shadow_bonus": NEWS_SENTIMENT_MAX_SCORE_BONUS,
            "would_reach_floor_after_shadow_bonus": bool(technical + NEWS_SENTIMENT_MAX_SCORE_BONUS >= active_floor),
            "live_trade_authority_changed": False,
        })
    return sorted(out, key=lambda x: (not bool(x.get("would_reach_floor_after_shadow_bonus")), x.get("gap_to_floor", 999)))


def build_news_sentiment_status(core: Any, symbols: List[str] | None = None, force_refresh: bool = False) -> Dict[str, Any]:
    selected = _unique(symbols or _extract_symbols(core))[:NEWS_SENTIMENT_MAX_SYMBOLS]
    cache_key = ",".join(selected)
    now = time.time()
    if not force_refresh and _CACHE.get("payload") is not None and _CACHE.get("key") == cache_key and now - _safe_float(_CACHE.get("ts"), 0.0) < NEWS_SENTIMENT_CACHE_TTL_SECONDS:
        payload = dict(_CACHE["payload"])
        payload["cache"] = {"hit": True, "ttl_seconds": NEWS_SENTIMENT_CACHE_TTL_SECONDS}
        return payload

    rows, provider = _fetch_provider_news(selected)
    score_map = _score_by_symbol(rows)
    technical_scores = _latest_scores(core)
    active_floor = _active_min_long_score(core)

    advisory_blocks = []
    advisory_bonuses = []
    hype_only_watch = []
    for symbol, info in score_map.items():
        score = _safe_float(info.get("sentiment_score"), 0.0)
        technical = _safe_float(technical_scores.get(symbol), 0.0)
        if score <= NEWS_SENTIMENT_NEGATIVE_BLOCK_THRESHOLD:
            advisory_blocks.append({
                "symbol": symbol,
                "reason": "negative_headline_risk",
                "sentiment_score": score,
                "recommended_action": "block_or_reduce_longs_in_future_phase_after_validation",
                "headlines": info.get("latest_headlines", [])[:NEWS_SENTIMENT_MAX_HEADLINES_PER_SYMBOL],
            })
        if score >= NEWS_SENTIMENT_POSITIVE_BONUS_THRESHOLD:
            advisory_bonuses.append({
                "symbol": symbol,
                "reason": "positive_catalyst_confirmed_by_news",
                "sentiment_score": score,
                "max_future_score_bonus": NEWS_SENTIMENT_MAX_SCORE_BONUS,
                "requires_technical_signal_first": True,
                "headlines": info.get("latest_headlines", [])[:NEWS_SENTIMENT_MAX_HEADLINES_PER_SYMBOL],
            })
            if technical and technical < NEWS_SENTIMENT_HYPE_ONLY_MAX_TECHNICAL_SCORE:
                hype_only_watch.append({
                    "symbol": symbol,
                    "reason": "positive_news_but_weak_technical_score",
                    "technical_score": technical,
                    "sentiment_score": score,
                })

    shadow_bonus_candidates = _build_shadow_bonus_candidates(score_map, technical_scores, active_floor)

    payload = {
        "status": "ok",
        "type": "news_sentiment_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "date": _today(core),
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "symbols_checked": selected,
        "provider_diagnostics": provider,
        "article_rows_count": len(rows),
        "sentiment_by_symbol": score_map,
        "advisory_negative_headline_blocks": advisory_blocks[:20],
        "advisory_positive_catalyst_bonuses": advisory_bonuses[:20],
        "hype_only_watchlist": hype_only_watch[:20],
        "shadow_bonus_candidates": shadow_bonus_candidates[:20],
        "shadow_bonus_policy": {
            "enabled": NEWS_SENTIMENT_SHADOW_BONUS_ENABLED,
            "advisory_only": True,
            "live_bonus_applied": False,
            "near_floor_gap": NEWS_SENTIMENT_NEAR_FLOOR_GAP,
            "max_shadow_bonus": NEWS_SENTIMENT_MAX_SCORE_BONUS,
            "requires_existing_technical_signal": True,
            "requires_positive_catalyst": True,
        },
        "policy": {
            "trade_authority": "advisory_only_phase_1_state_safe",
            "negative_news_can_block_live_trades_now": False,
            "positive_news_can_force_live_entries_now": False,
            "positive_news_bonus_live_now": False,
            "future_bonus_requires_existing_technical_signal": True,
            "future_max_score_bonus": NEWS_SENTIMENT_MAX_SCORE_BONUS,
        },
        "recommended_actions": [
            "Keep news sentiment advisory-only until enough entry/exit outcomes are collected.",
            "Use negative headline risk as a future long-block candidate, not as an immediate live override.",
            "Only consider positive catalyst bonuses when technical score is already near the entry floor.",
            "Keep persistent state compact: store outcome facts only, not full article text or URLs.",
        ],
        "cache": {"hit": False, "ttl_seconds": NEWS_SENTIMENT_CACHE_TTL_SECONDS},
    }

    research_summary = _update_news_research_log(core, payload, technical_scores, active_floor)
    payload["outcome_logger"] = research_summary
    payload["state_protection"] = {
        "active": True,
        "version": VERSION,
        "headlines_stored_in_state": False,
        "max_headlines_per_symbol_in_response": NEWS_SENTIMENT_MAX_HEADLINES_PER_SYMBOL,
        "max_state_outcome_rows": NEWS_SENTIMENT_MAX_STATE_OUTCOME_ROWS,
        "state_rows_after": research_summary.get("state_rows_after"),
        "payload_size_bytes": _payload_size_bytes(payload),
        "live_trade_authority_changed": False,
    }

    _CACHE.update({"ts": now, "key": cache_key, "payload": payload})
    return payload


def build_catalyst_watchlist(core: Any) -> Dict[str, Any]:
    status = build_news_sentiment_status(core, force_refresh=False)
    sentiment = _safe_dict(status.get("sentiment_by_symbol"))
    positive = []
    negative = []
    mixed = []
    for symbol, info in sentiment.items():
        score = _safe_float(_safe_dict(info).get("sentiment_score"), 0.0)
        row = {
            "symbol": symbol,
            "sentiment_score": score,
            "sentiment_bias": _safe_dict(info).get("sentiment_bias"),
            "catalyst_tags": _safe_dict(info).get("catalyst_tags", []),
            "latest_headlines": _safe_dict(info).get("latest_headlines", [])[:NEWS_SENTIMENT_MAX_HEADLINES_PER_SYMBOL],
        }
        if score >= NEWS_SENTIMENT_POSITIVE_BONUS_THRESHOLD:
            positive.append(row)
        elif score <= NEWS_SENTIMENT_NEGATIVE_BLOCK_THRESHOLD:
            negative.append(row)
        else:
            mixed.append(row)
    return {
        "status": "ok",
        "type": "catalyst_watchlist",
        "version": VERSION,
        "generated_local": _now_text(core),
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "positive_catalysts": sorted(positive, key=lambda x: x["sentiment_score"], reverse=True),
        "negative_headline_risk": sorted(negative, key=lambda x: x["sentiment_score"]),
        "mixed_or_neutral": sorted(mixed, key=lambda x: abs(x["sentiment_score"]), reverse=True)[:20],
        "shadow_bonus_candidates": status.get("shadow_bonus_candidates", []),
        "state_protection": status.get("state_protection", {}),
        "provider_diagnostics": status.get("provider_diagnostics"),
    }


def build_news_risk_status(core: Any) -> Dict[str, Any]:
    status = build_news_sentiment_status(core, force_refresh=False)
    blocks = _safe_list(status.get("advisory_negative_headline_blocks"))
    bonuses = _safe_list(status.get("advisory_positive_catalyst_bonuses"))
    hype = _safe_list(status.get("hype_only_watchlist"))
    shadow = _safe_list(status.get("shadow_bonus_candidates"))
    provider = _safe_dict(status.get("provider_diagnostics"))
    risk_level = "normal"
    if len(blocks) >= 3:
        risk_level = "headline_risk_elevated"
    elif len(blocks) > 0:
        risk_level = "headline_risk_present"
    if not provider.get("provider_configured"):
        risk_level = "news_feed_not_configured"
    return {
        "status": "ok",
        "type": "news_risk_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "risk_level": risk_level,
        "negative_headline_blocks_count": len(blocks),
        "positive_catalyst_count": len(bonuses),
        "hype_only_count": len(hype),
        "shadow_bonus_candidate_count": len(shadow),
        "provider_configured": bool(provider.get("provider_configured")),
        "provider_status_detail": provider.get("status_detail"),
        "outcome_logger": status.get("outcome_logger", {}),
        "state_protection": status.get("state_protection", {}),
        "recommended_actions": status.get("recommended_actions", []),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "news_sentiment_engine_apply",
        "version": VERSION,
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "state_safe": True,
        "outcome_logger_enabled": NEWS_SENTIMENT_OUTCOME_LOG_ENABLED,
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

    if "/paper/news-sentiment-status" not in existing:
        def news_sentiment_status():
            force = False
            symbols = None
            try:
                from flask import request
                force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes", "on"}
                raw_symbols = request.args.get("symbols") or request.args.get("tickers")
                if raw_symbols:
                    symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
            except Exception:
                pass
            return _json_response(core, build_news_sentiment_status(core, symbols=symbols, force_refresh=force), endpoint="paper_news_sentiment_status")
        flask_app.add_url_rule("/paper/news-sentiment-status", "paper_news_sentiment_status", news_sentiment_status)

    if "/paper/catalyst-watchlist" not in existing:
        def catalyst_watchlist():
            return _json_response(core, build_catalyst_watchlist(core), endpoint="paper_catalyst_watchlist")
        flask_app.add_url_rule("/paper/catalyst-watchlist", "paper_catalyst_watchlist", catalyst_watchlist)

    if "/paper/news-risk-status" not in existing:
        def news_risk_status():
            return _json_response(core, build_news_risk_status(core), endpoint="paper_news_risk_status")
        flask_app.add_url_rule("/paper/news-risk-status", "paper_news_risk_status", news_risk_status)

    return {
        "status": "ok",
        "type": "news_sentiment_engine_register_routes",
        "version": VERSION,
        "routes_installed": True,
        "routes": [
            "/paper/news-sentiment-status",
            "/paper/catalyst-watchlist",
            "/paper/news-risk-status",
        ],
        "advisory_only": True,
        "live_trade_authority_changed": False,
        "state_safe": True,
    }
