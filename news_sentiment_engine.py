"""News sentiment and catalyst visibility layer.

Advisory-only: this module summarizes ticker-level news/catalyst risk for the
paper bot. It does not place trades, resize positions, enable live authority, or
override price-action/risk controls.
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

VERSION = "news-sentiment-engine-2026-05-18-advisory-v1"

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
        elif sentiment == "neutral":
            score += 0.0
        reasoning = str(insight.get("sentiment_reasoning") or "")[:240]
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
        "title": article.get("title"),
        "publisher": _safe_dict(article.get("publisher")).get("name") or article.get("source") or article.get("publisher"),
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
            headlines.append(article.get("title"))
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
            "latest_headlines": [h for h in headlines if h][:5],
        }
    return out


def _latest_scores(core: Any) -> Dict[str, float]:
    state = _safe_dict(getattr(core, "portfolio", {}))
    last = _safe_dict(_safe_dict(state.get("auto_runner")).get("last_result"))
    out: Dict[str, float] = {}
    for key in ("blocked_entries", "rejected_signals"):
        for row in _safe_list(last.get(key)):
            if isinstance(row, dict):
                sym = _symbol(row)
                if sym:
                    out[sym] = max(out.get(sym, 0.0), _safe_float(row.get("score"), 0.0))
    return out


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
                "headlines": info.get("latest_headlines", [])[:3],
            })
        if score >= NEWS_SENTIMENT_POSITIVE_BONUS_THRESHOLD:
            advisory_bonuses.append({
                "symbol": symbol,
                "reason": "positive_catalyst_confirmed_by_news",
                "sentiment_score": score,
                "max_future_score_bonus": NEWS_SENTIMENT_MAX_SCORE_BONUS,
                "requires_technical_signal_first": True,
                "headlines": info.get("latest_headlines", [])[:3],
            })
            if technical and technical < NEWS_SENTIMENT_HYPE_ONLY_MAX_TECHNICAL_SCORE:
                hype_only_watch.append({
                    "symbol": symbol,
                    "reason": "positive_news_but_weak_technical_score",
                    "technical_score": technical,
                    "sentiment_score": score,
                })

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
        "policy": {
            "trade_authority": "advisory_only_phase_1",
            "negative_news_can_block_live_trades_now": False,
            "positive_news_can_force_live_entries_now": False,
            "future_bonus_requires_existing_technical_signal": True,
            "future_max_score_bonus": NEWS_SENTIMENT_MAX_SCORE_BONUS,
        },
        "recommended_actions": [
            "Keep news sentiment advisory-only until enough entry/exit outcomes are collected.",
            "Use negative headline risk as a future long-block candidate, not as an immediate live override.",
            "Only consider positive catalyst bonuses when technical score is already near the entry floor.",
        ],
        "cache": {"hit": False, "ttl_seconds": NEWS_SENTIMENT_CACHE_TTL_SECONDS},
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
            "latest_headlines": _safe_dict(info).get("latest_headlines", [])[:3],
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
        "provider_diagnostics": status.get("provider_diagnostics"),
    }


def build_news_risk_status(core: Any) -> Dict[str, Any]:
    status = build_news_sentiment_status(core, force_refresh=False)
    blocks = _safe_list(status.get("advisory_negative_headline_blocks"))
    bonuses = _safe_list(status.get("advisory_positive_catalyst_bonuses"))
    hype = _safe_list(status.get("hype_only_watchlist"))
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
        "provider_configured": bool(provider.get("provider_configured")),
        "provider_status_detail": provider.get("status_detail"),
        "recommended_actions": status.get("recommended_actions", []),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "type": "news_sentiment_engine_apply",
        "version": VERSION,
        "advisory_only": True,
        "live_trade_authority_changed": False,
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
    }
