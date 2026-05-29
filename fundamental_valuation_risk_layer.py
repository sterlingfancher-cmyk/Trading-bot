"""Fundamental / analyst valuation risk layer.

Adds a bounded analyst + valuation overlay to the paper bot:
- does not increase max positions,
- does not create trades by itself,
- does not bypass halts, stop losses, score floors, or state guards,
- adjusts long sizing and weak-position rotation only when cached evidence exists.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

VERSION = "fundamental-valuation-risk-2026-05-28-v1"

ENABLED = os.environ.get("FUNDAMENTAL_VALUATION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_SIZING = os.environ.get("FUNDAMENTAL_VALUATION_LIVE_SIZING", "true").lower() not in {"0", "false", "no", "off"}
FETCH_DURING_RUN = os.environ.get("FUNDAMENTAL_VALUATION_FETCH_DURING_RUN", "false").lower() in {"1", "true", "yes", "on"}
CACHE_TTL_SECONDS = int(os.environ.get("FUNDAMENTAL_VALUATION_CACHE_TTL_SECONDS", str(6 * 60 * 60)))
MAX_FETCH_SYMBOLS = int(os.environ.get("FUNDAMENTAL_VALUATION_MAX_FETCH_SYMBOLS", "8"))
HTTP_TIMEOUT_SECONDS = float(os.environ.get("FUNDAMENTAL_VALUATION_HTTP_TIMEOUT_SECONDS", "3.0"))
MAX_STATE_ROWS = int(os.environ.get("FUNDAMENTAL_VALUATION_MAX_STATE_ROWS", "220"))

MIN_MULTIPLIER = float(os.environ.get("FUNDAMENTAL_VALUATION_MIN_MULTIPLIER", "0.70"))
MAX_MULTIPLIER = float(os.environ.get("FUNDAMENTAL_VALUATION_MAX_MULTIPLIER", "1.20"))
ROTATION_PNL_CEILING = float(os.environ.get("FUNDAMENTAL_VALUATION_ROTATION_PNL_CEILING", "0.01"))

_MEM_CACHE: Dict[str, Any] = {"ts": 0.0, "profiles": {}}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
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
    return max(float(low), min(float(high), float(value)))


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


def _symbol(item: Any) -> str:
    if isinstance(item, str):
        return item.upper().strip()
    if isinstance(item, dict):
        value = item.get("symbol") or item.get("ticker")
        return str(value).upper().strip() if value else ""
    return ""


def _unique(items: Iterable[Any]) -> List[str]:
    out, seen = [], set()
    for item in items:
        sym = _symbol(item)
        if sym and sym not in seen:
            out.append(sym)
            seen.add(sym)
    return out


def _state(core: Any) -> Dict[str, Any]:
    return _safe_dict(getattr(core, "portfolio", {}))


def _bucket(core: Any, symbol: str) -> str:
    try:
        fn = getattr(core, "symbol_bucket", None)
        if callable(fn):
            return str(fn(symbol) or "default")
    except Exception:
        pass
    try:
        return str(getattr(core, "SYMBOL_BUCKET", {}).get(symbol, "default"))
    except Exception:
        return "default"


def _selected_symbols(core: Any, symbols: Optional[List[str]] = None, limit: int = 24) -> List[str]:
    if symbols:
        return _unique(symbols)[:limit]

    state = _state(core)
    auto = _safe_dict(state.get("auto_runner"))
    last = _safe_dict(auto.get("last_result"))
    scanner = _safe_dict(state.get("scanner_audit"))

    candidates: List[Any] = []
    candidates.extend(list(_safe_dict(state.get("positions")).keys()))
    for source in (last, scanner):
        for key in ("long_signals", "short_signals", "blocked_entries", "rejected_signals", "top_blocked_symbols"):
            candidates.extend(_safe_list(_safe_dict(source).get(key)))
    return _unique(candidates)[:limit]


def _fmp_key() -> str:
    for name in ("FMP_API_KEY", "FINANCIALMODELINGPREP_API_KEY", "FINANCIAL_MODELING_PREP_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    return ""


def _fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "trading-bot-fundamental-valuation-risk/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:  # nosec - provider URL built internally
        raw = response.read(1_000_000)
    return json.loads(raw.decode("utf-8"))


def _fmp_url(path: str, symbol: str, key: str) -> str:
    return f"https://financialmodelingprep.com/api/v3/{path}/{urllib.parse.quote(symbol)}?apikey={urllib.parse.quote(key)}"


def _first(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        return payload
    return {}


def _stored_profiles(core: Any) -> Dict[str, Dict[str, Any]]:
    rows = _safe_dict(_safe_dict(_state(core).get("fundamental_valuation_risk")).get("latest_by_symbol"))
    return {str(k).upper(): _safe_dict(v) for k, v in rows.items() if k}


def _is_fresh(row: Dict[str, Any]) -> bool:
    ts = _safe_float(row.get("ts"), 0.0)
    return bool(ts and time.time() - ts <= CACHE_TTL_SECONDS)


def _thresholds(bucket: str) -> Dict[str, float]:
    if bucket in {"small_cap_momentum", "bitcoin_ai_compute"}:
        return {"ps_high": 18.0, "ps_extreme": 30.0, "pe_high": 90.0}
    if bucket in {"semi_leaders", "data_center_infra", "cloud_cyber_software"}:
        return {"ps_high": 12.0, "ps_extreme": 22.0, "pe_high": 65.0}
    if bucket == "mega_cap_ai":
        return {"ps_high": 10.0, "ps_extreme": 18.0, "pe_high": 55.0}
    return {"ps_high": 8.0, "ps_extreme": 15.0, "pe_high": 45.0}


def _score_profile(core: Any, symbol: str, profile: Dict[str, Any], ratios: Dict[str, Any], rating: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    bucket = _bucket(core, symbol)
    th = _thresholds(bucket)
    reasons: List[str] = []

    price = _safe_float(profile.get("price") or profile.get("dcfDiff") or target.get("price"), 0.0)
    target_price = _safe_float(
        target.get("targetConsensus")
        or target.get("targetMean")
        or target.get("targetMedian")
        or target.get("targetPrice"),
        0.0,
    )
    target_upside = ((target_price / price) - 1.0) if price and target_price else None

    pe = _safe_float(profile.get("pe") or ratios.get("priceEarningsRatioTTM"), 0.0)
    ps = _safe_float(ratios.get("priceToSalesRatioTTM"), 0.0)
    roe = _safe_float(ratios.get("returnOnEquityTTM"), 0.0)
    margin = _safe_float(ratios.get("netProfitMarginTTM"), 0.0)
    current_ratio = _safe_float(ratios.get("currentRatioTTM"), 0.0)
    debt_equity = _safe_float(ratios.get("debtEquityRatioTTM"), 0.0)

    rating_score_raw = _safe_float(
        rating.get("ratingScore")
        or rating.get("ratingDetailsDCFScore")
        or rating.get("ratingDetailsROEScore"),
        0.0,
    )
    rating_rec = str(rating.get("ratingRecommendation") or rating.get("rating") or "").lower()

    analyst_score = 0.0
    if rating_score_raw >= 4:
        analyst_score += 14
        reasons.append("analyst_rating_supportive")
    elif 0 < rating_score_raw <= 2:
        analyst_score -= 12
        reasons.append("analyst_rating_cautious")
    if any(word in rating_rec for word in ("buy", "outperform", "positive")):
        analyst_score += 8
        reasons.append("analyst_recommendation_positive")
    if any(word in rating_rec for word in ("sell", "underperform", "negative")):
        analyst_score -= 10
        reasons.append("analyst_recommendation_negative")

    target_score = 0.0
    if target_upside is not None:
        if target_upside >= 0.25:
            target_score += 22
            reasons.append("large_target_upside")
        elif target_upside >= 0.10:
            target_score += 12
            reasons.append("positive_target_upside")
        elif target_upside <= -0.25:
            target_score -= 25
            reasons.append("price_far_above_target")
        elif target_upside <= -0.10:
            target_score -= 14
            reasons.append("price_above_target")

    valuation_score = 0.0
    if ps:
        if ps >= th["ps_extreme"]:
            valuation_score -= 18
            reasons.append("extreme_sales_multiple")
        elif ps >= th["ps_high"]:
            valuation_score -= 9
            reasons.append("high_sales_multiple")
        elif ps <= max(2.0, th["ps_high"] * 0.35):
            valuation_score += 6
            reasons.append("reasonable_sales_multiple")
    if pe:
        if pe >= th["pe_high"] * 1.5:
            valuation_score -= 12
            reasons.append("extreme_earnings_multiple")
        elif pe >= th["pe_high"]:
            valuation_score -= 6
            reasons.append("high_earnings_multiple")
        elif 0 < pe <= 30:
            valuation_score += 4
            reasons.append("reasonable_earnings_multiple")
        elif pe < 0:
            valuation_score -= 6
            reasons.append("negative_earnings_context")

    quality_score = 0.0
    if roe > 0.12:
        quality_score += 6
        reasons.append("positive_roe")
    elif roe < -0.05:
        quality_score -= 6
        reasons.append("negative_roe")
    if margin > 0.08:
        quality_score += 6
        reasons.append("positive_net_margin")
    elif margin < -0.05:
        quality_score -= 8
        reasons.append("negative_net_margin")
    if current_ratio >= 1.2:
        quality_score += 3
        reasons.append("adequate_current_ratio")
    elif 0 < current_ratio < 0.8:
        quality_score -= 4
        reasons.append("weak_current_ratio")
    if debt_equity > 3.0:
        quality_score -= 5
        reasons.append("elevated_debt_equity")

    score = _clamp(analyst_score + target_score + valuation_score + quality_score, -100, 100)

    if score >= 45:
        multiplier, label = 1.20, "supportive_high_conviction"
    elif score >= 25:
        multiplier, label = 1.12, "supportive"
    elif score >= 10:
        multiplier, label = 1.05, "slightly_supportive"
    elif score <= -45:
        multiplier, label = 0.70, "high_valuation_or_analyst_risk"
    elif score <= -25:
        multiplier, label = 0.80, "valuation_or_analyst_caution"
    elif score <= -10:
        multiplier, label = 0.90, "slight_caution"
    else:
        multiplier, label = 1.0, "neutral"

    if "price_far_above_target" in reasons and multiplier > 0.90:
        multiplier, label = 0.90, "target_overextension_caution"
    if "extreme_sales_multiple" in reasons and "large_target_upside" not in reasons and multiplier > 0.85:
        multiplier, label = 0.85, "valuation_multiple_caution"

    multiplier = round(_clamp(multiplier, MIN_MULTIPLIER, MAX_MULTIPLIER), 4)
    return {
        "symbol": symbol,
        "status": "ok",
        "ts": time.time(),
        "generated_local": _now_text(core),
        "bucket": bucket,
        "risk_multiplier": multiplier,
        "risk_label": label,
        "fundamental_score": round(score, 2),
        "overvaluation_risk": bool(multiplier < 1.0 or "price_far_above_target" in reasons or "extreme_sales_multiple" in reasons),
        "analyst_score_component": round(analyst_score, 2),
        "target_score_component": round(target_score, 2),
        "valuation_score_component": round(valuation_score, 2),
        "quality_score_component": round(quality_score, 2),
        "metrics": {
            "price": round(price, 4) if price else None,
            "target_price": round(target_price, 4) if target_price else None,
            "target_upside_pct": round(target_upside * 100, 2) if target_upside is not None else None,
            "pe": round(pe, 3) if pe else None,
            "price_to_sales_ttm": round(ps, 3) if ps else None,
            "roe_ttm": round(roe, 4) if roe else None,
            "net_margin_ttm": round(margin, 4) if margin else None,
            "current_ratio_ttm": round(current_ratio, 3) if current_ratio else None,
            "debt_equity_ttm": round(debt_equity, 3) if debt_equity else None,
            "rating_score": rating_score_raw or None,
            "rating_recommendation": rating_rec or None,
        },
        "reasons": reasons[:12] or ["neutral_or_insufficient_factor_edge"],
        "live_trade_authority_changed": False,
    }


def _neutral_profile(core: Any, symbol: str, status: str, reason: str) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "status": status,
        "ts": time.time(),
        "generated_local": _now_text(core),
        "bucket": _bucket(core, symbol),
        "risk_multiplier": 1.0,
        "risk_label": "neutral",
        "fundamental_score": 0.0,
        "overvaluation_risk": False,
        "reasons": [reason],
        "live_trade_authority_changed": False,
    }


def _fetch_profile(core: Any, symbol: str, fetch: bool = True) -> Dict[str, Any]:
    symbol = symbol.upper()
    if not ENABLED:
        return _neutral_profile(core, symbol, "disabled", "fundamental_valuation_disabled")
    if not fetch:
        stored = _stored_profiles(core).get(symbol)
        return dict(stored) if stored else _neutral_profile(core, symbol, "cache_miss", "no_cached_fundamental_profile")

    key = _fmp_key()
    if not key:
        return _neutral_profile(core, symbol, "missing_api_key", "missing_FMP_API_KEY")

    try:
        profile = _first(_fetch_json(_fmp_url("profile", symbol, key)))
        ratios = _first(_fetch_json(_fmp_url("ratios-ttm", symbol, key)))
        rating = _first(_fetch_json(_fmp_url("rating", symbol, key)))
        try:
            target = _first(_fetch_json(_fmp_url("price-target-consensus", symbol, key)))
        except Exception:
            target = {}
        if not (profile or ratios or rating or target):
            return _neutral_profile(core, symbol, "provider_empty", "provider_returned_no_data")
        return _score_profile(core, symbol, profile, ratios, rating, target)
    except Exception as exc:
        row = _neutral_profile(core, symbol, "provider_error", f"{type(exc).__name__}: {str(exc)[:120]}")
        return row


def _persist(core: Any, profiles: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    state = _state(core)
    if not state:
        return {"persisted": False, "reason": "state_missing"}

    existing = _stored_profiles(core)
    changed = False
    for sym, row in profiles.items():
        compact = dict(row)
        if existing.get(sym) != compact:
            existing[sym] = compact
            changed = True

    latest = sorted(existing.values(), key=lambda r: _safe_float(r.get("ts"), 0.0))[-max(1, MAX_STATE_ROWS):]
    latest_by_symbol = {str(r.get("symbol")).upper(): r for r in latest if r.get("symbol")}
    state["fundamental_valuation_risk"] = {
        "version": VERSION,
        "updated_local": _now_text(core),
        "latest_by_symbol": latest_by_symbol,
        "max_rows": MAX_STATE_ROWS,
        "policy": {
            "max_positions_unchanged": True,
            "technical_signal_required_first": True,
            "live_sizing_enabled": LIVE_SIZING,
            "fetch_during_run": FETCH_DURING_RUN,
            "risk_multiplier_range": [MIN_MULTIPLIER, MAX_MULTIPLIER],
        },
    }

    if changed:
        try:
            save = getattr(core, "save_state", None)
            if callable(save):
                save(state)
                return {"persisted": True, "rows": len(latest_by_symbol)}
        except Exception as exc:
            return {"persisted": False, "error": str(exc)[:160], "rows": len(latest_by_symbol)}
    return {"persisted": False, "reason": "no_change", "rows": len(latest_by_symbol)}


def build_status(core: Any, symbols: Optional[List[str]] = None, force_refresh: bool = False, fetch: bool = True) -> Dict[str, Any]:
    selected = _selected_symbols(core, symbols=symbols)
    stored = _stored_profiles(core)
    profiles: Dict[str, Dict[str, Any]] = {}
    fetched = 0
    cache_hits = 0

    for sym in selected:
        cached = stored.get(sym)
        if cached and _is_fresh(cached) and not force_refresh:
            profiles[sym] = dict(cached)
            cache_hits += 1
            continue
        can_fetch = bool(fetch and fetched < max(0, MAX_FETCH_SYMBOLS))
        profiles[sym] = _fetch_profile(core, sym, fetch=can_fetch)
        if can_fetch:
            fetched += 1

    persist = _persist(core, profiles) if profiles else {"persisted": False, "reason": "no_symbols"}

    rows = sorted(profiles.values(), key=lambda r: _safe_float(r.get("fundamental_score"), 0.0), reverse=True)
    supportive = [r for r in rows if _safe_float(r.get("risk_multiplier"), 1.0) > 1.0]
    caution = [r for r in rows if _safe_float(r.get("risk_multiplier"), 1.0) < 1.0]

    return {
        "status": "ok",
        "type": "fundamental_valuation_risk_status",
        "version": VERSION,
        "generated_local": _now_text(core),
        "date": _today(core),
        "enabled": ENABLED,
        "symbols_checked": selected,
        "profiles_by_symbol": profiles,
        "supportive_symbols": supportive[:12],
        "valuation_or_analyst_caution": caution[:12],
        "rotation_priority_candidates": [
            {
                "symbol": r.get("symbol"),
                "risk_multiplier": r.get("risk_multiplier"),
                "risk_label": r.get("risk_label"),
                "fundamental_score": r.get("fundamental_score"),
                "reason": "valuation_or_analyst_risk_can_prioritize_rotation_if_technically_weak",
            }
            for r in caution
            if _safe_float(r.get("risk_multiplier"), 1.0) <= 0.9
        ][:12],
        "risk_policy": {
            "max_positions_unchanged": True,
            "live_sizing_enabled": LIVE_SIZING,
            "live_fetch_during_run": FETCH_DURING_RUN,
            "run_cycle_lookup_mode": "cache_only" if not FETCH_DURING_RUN else "may_fetch",
            "risk_multiplier_range": [MIN_MULTIPLIER, MAX_MULTIPLIER],
            "technical_signal_required_first": True,
            "valuation_can_force_entry": False,
            "valuation_can_bypass_halts": False,
            "valuation_can_bypass_stop_losses": False,
        },
        "ml_feature_payload": {
            "phase": "phase_2_6_fundamental_analyst_advisory",
            "ready_for_live_ml_authority": False,
            "feature_names": [
                "analyst_score_component",
                "target_score_component",
                "valuation_score_component",
                "quality_score_component",
                "fundamental_score",
                "risk_multiplier",
                "overvaluation_risk",
                "target_upside_pct",
                "rating_score",
                "price_to_sales_ttm",
                "pe",
                "roe_ttm",
                "net_margin_ttm",
            ],
        },
        "provider": {
            "name": "financialmodelingprep",
            "configured": bool(_fmp_key()),
            "cache_hits": cache_hits,
            "fetched": fetched,
            "max_fetch_symbols": MAX_FETCH_SYMBOLS,
        },
        "persist": persist,
        "recommended_actions": [
            "Keep max positions capped at 14.",
            "Improve weak-position rotation before adding more slots.",
            "Use analyst/valuation as a risk multiplier only after a technical signal exists.",
            "Reduce size or rotate from technically weak names when valuation risk is high.",
        ],
    }


def _risk_for_symbol(core: Any, symbol: str, allow_fetch: bool = False) -> Dict[str, Any]:
    status = build_status(core, symbols=[symbol], force_refresh=False, fetch=allow_fetch)
    return _safe_dict(_safe_dict(status.get("profiles_by_symbol")).get(symbol.upper())) or _neutral_profile(core, symbol, "unavailable", "risk_profile_unavailable")


def _patch_enter_position(core: Any) -> bool:
    original = getattr(core, "enter_position", None)
    if not callable(original) or getattr(original, "_fundamental_valuation_risk_patched", False):
        return False

    def wrapped(signal: Dict[str, Any], params: Dict[str, Any], market_mode: Any = None):
        sig = dict(signal or {})
        symbol = str(sig.get("symbol") or "").upper()
        side = str(sig.get("side") or "long").lower()
        risk = _risk_for_symbol(core, symbol, allow_fetch=FETCH_DURING_RUN)
        multiplier = _safe_float(risk.get("risk_multiplier"), 1.0)
        if side == "long" and ENABLED and LIVE_SIZING:
            old_factor = _safe_float(sig.get("alloc_factor"), 1.0)
            sig["alloc_factor"] = _clamp(old_factor * multiplier, 0.05, MAX_MULTIPLIER)
            sig["fundamental_valuation_risk"] = {
                "risk_multiplier": round(multiplier, 4),
                "risk_label": risk.get("risk_label"),
                "fundamental_score": risk.get("fundamental_score"),
                "reasons": _safe_list(risk.get("reasons"))[:6],
            }

        result = original(sig, params, market_mode=market_mode)

        try:
            if isinstance(result, dict) and not result.get("blocked") and symbol:
                compact = {
                    "version": VERSION,
                    "risk_multiplier": round(multiplier, 4),
                    "risk_label": risk.get("risk_label"),
                    "fundamental_score": risk.get("fundamental_score"),
                    "overvaluation_risk": risk.get("overvaluation_risk"),
                    "reasons": _safe_list(risk.get("reasons"))[:6],
                    "cache_status": risk.get("status"),
                }
                result["fundamental_valuation_risk"] = compact
                pos = _safe_dict(getattr(core, "portfolio", {}).get("positions")).get(symbol)
                if isinstance(pos, dict):
                    pos["fundamental_valuation_risk"] = compact
        except Exception:
            pass
        return result

    wrapped._fundamental_valuation_risk_patched = True  # type: ignore[attr-defined]
    wrapped._fundamental_valuation_risk_original = original  # type: ignore[attr-defined]
    core.enter_position = wrapped
    return True


def _patch_weakest_position_for_rotation(core: Any) -> bool:
    original = getattr(core, "weakest_position_for_rotation", None)
    if not callable(original) or getattr(original, "_fundamental_valuation_risk_patched", False):
        return False

    def wrapped(new_signal: Dict[str, Any]):
        baseline = original(new_signal)
        try:
            positions = _safe_dict(getattr(core, "portfolio", {}).get("positions"))
            new_side = str(_safe_dict(new_signal).get("side") or "long")
            now = int(time.time())
            candidates = []
            for symbol, pos in positions.items():
                if symbol == _safe_dict(new_signal).get("symbol") or not isinstance(pos, dict):
                    continue
                if str(pos.get("side", "long")) != new_side:
                    continue
                px = _safe_float(pos.get("last_price", pos.get("entry", 0)), 0.0)
                try:
                    pnl_pct = float(core.position_pnl_pct(pos, px))
                except Exception:
                    entry = max(_safe_float(pos.get("entry"), px), 0.01)
                    pnl_pct = px / entry - 1.0
                score = _safe_float(pos.get("score"), 0.0)
                risk = _risk_for_symbol(core, str(symbol), allow_fetch=False)
                multiplier = _safe_float(risk.get("risk_multiplier"), 1.0)
                valuation_risk = bool(multiplier <= 0.90 or risk.get("overvaluation_risk"))
                technical_weak = pnl_pct <= ROTATION_PNL_CEILING
                priority_discount = (1.0 - min(multiplier, 1.0)) * 0.025 if valuation_risk and technical_weak else 0.0
                candidates.append({
                    "symbol": symbol,
                    "side": pos.get("side", "long"),
                    "score": max(0.0, score - priority_discount),
                    "raw_score": score,
                    "pnl_pct": pnl_pct,
                    "held_seconds": now - int(_safe_float(pos.get("entry_time"), now)),
                    "same_side": True,
                    "sector": pos.get("sector", getattr(core, "SYMBOL_SECTOR", {}).get(symbol, "UNKNOWN")),
                    "fundamental_valuation_risk": {
                        "risk_multiplier": round(multiplier, 4),
                        "risk_label": risk.get("risk_label"),
                        "fundamental_score": risk.get("fundamental_score"),
                        "rotation_priority_discount": round(priority_discount, 6),
                        "valuation_risk": valuation_risk,
                        "technical_weak": technical_weak,
                    },
                })
            if not candidates:
                return baseline
            candidate = sorted(candidates, key=lambda r: (r["score"], r["pnl_pct"]))[0]
            if isinstance(baseline, dict):
                base_score = _safe_float(baseline.get("score"), 0.0)
                base_pnl = _safe_float(baseline.get("pnl_pct"), 0.0)
                if (candidate["score"], candidate["pnl_pct"]) >= (base_score, base_pnl):
                    return baseline
            return candidate
        except Exception:
            return baseline

    wrapped._fundamental_valuation_risk_patched = True  # type: ignore[attr-defined]
    wrapped._fundamental_valuation_risk_original = original  # type: ignore[attr-defined]
    core.weakest_position_for_rotation = wrapped
    return True


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None:
        try:
            import app as core  # type: ignore[no-redef]
        except Exception:
            core = None
    if core is None:
        return {"status": "error", "type": "fundamental_valuation_risk_apply", "version": VERSION, "error": "core_missing"}

    return {
        "status": "ok",
        "type": "fundamental_valuation_risk_apply",
        "version": VERSION,
        "enabled": ENABLED,
        "patches": {
            "enter_position": _patch_enter_position(core),
            "weakest_position_for_rotation": _patch_weakest_position_for_rotation(core),
        },
        "risk_policy": {
            "max_positions_unchanged": True,
            "live_sizing_enabled": LIVE_SIZING,
            "fetch_during_run": FETCH_DURING_RUN,
            "risk_multiplier_range": [MIN_MULTIPLIER, MAX_MULTIPLIER],
            "technical_signal_required_first": True,
        },
    }


def _json_response(core: Any, payload: Dict[str, Any], endpoint: str):
    try:
        return core.json_response(payload, endpoint=endpoint)
    except Exception:
        from flask import jsonify
        return jsonify(payload)


def register_routes(flask_app: Any = None, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    if core is None:
        try:
            import app as core  # type: ignore[no-redef]
        except Exception:
            core = None
    if core is None:
        return {"status": "error", "version": VERSION, "error": "core_missing"}

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def _args():
        force = False
        fetch = True
        symbols = None
        try:
            from flask import request
            force = str(request.args.get("force", "0")).lower() in {"1", "true", "yes", "on"}
            fetch = str(request.args.get("fetch", "1")).lower() not in {"0", "false", "no", "off"}
            raw = request.args.get("symbols") or request.args.get("tickers")
            if raw:
                symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
        except Exception:
            pass
        return symbols, force, fetch

    if "/paper/fundamental-valuation-risk-status" not in existing:
        def fundamental_valuation_risk_status():
            symbols, force, fetch = _args()
            return _json_response(core, build_status(core, symbols=symbols, force_refresh=force, fetch=fetch), endpoint="paper_fundamental_valuation_risk_status")
        flask_app.add_url_rule("/paper/fundamental-valuation-risk-status", "paper_fundamental_valuation_risk_status", fundamental_valuation_risk_status)

    if "/paper/analyst-valuation-risk-status" not in existing:
        def analyst_valuation_risk_status():
            symbols, force, fetch = _args()
            payload = build_status(core, symbols=symbols, force_refresh=force, fetch=fetch)
            payload["type"] = "analyst_valuation_risk_status"
            payload["alias_for"] = "/paper/fundamental-valuation-risk-status"
            return _json_response(core, payload, endpoint="paper_analyst_valuation_risk_status")
        flask_app.add_url_rule("/paper/analyst-valuation-risk-status", "paper_analyst_valuation_risk_status", analyst_valuation_risk_status)

    return {
        "status": "ok",
        "type": "fundamental_valuation_risk_register_routes",
        "version": VERSION,
        "routes_installed": True,
        "routes": ["/paper/fundamental-valuation-risk-status", "/paper/analyst-valuation-risk-status"],
        "max_positions_unchanged": True,
        "live_trade_authority_changed": False,
        "state_safe": True,
    }
