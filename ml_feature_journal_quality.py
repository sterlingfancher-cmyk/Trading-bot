"""ML feature journal quality and regime tagging.

Advisory-only enrichment layer for ML Phase 2 feature rows. This improves the
quality of the shadow-learning dataset without changing trade execution,
risk controls, ML authority, or post-harvest thresholds.

Responsibilities:
- Normalize regime labels on ML2 feature rows when they are missing or vague.
- Add richer regime-family, risk-state, signal-cluster, and feature-quality tags.
- Preserve original regime/source values for auditability.
- Publish feature-journal quality summary for readiness diagnostics.
- Never invent trade outcomes or synthetic MAE/MFE values.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import sys
from collections import Counter
from typing import Any, Dict, List, Tuple

VERSION = "ml-feature-journal-quality-2026-06-04-v1-regime-tags"
ENABLED = os.environ.get("ML_FEATURE_JOURNAL_QUALITY_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
LIVE_DECIDER = False
REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()
_PATCHING = False

REQUIRED_FIELDS = ("symbol", "side", "decision", "bucket", "sector", "rule_score", "entry_floor", "score_edge", "date")

PRECIOUS_METALS = {"GLD", "IAU", "PHYS", "GDX", "GDXJ", "SIL", "SILJ", "SLV", "NEM", "AEM", "FNV", "PAAS", "HL", "CDE"}
MEGA_CAP_GROWTH = {"AAPL", "MSFT", "AMZN", "META", "GOOGL", "GOOG", "NVDA", "TSLA", "AVGO", "NFLX"}
AI_COMPUTE = {"AMD", "NVDA", "MU", "ARM", "MRVL", "DELL", "SMCI", "HPE", "ANET", "CIEN", "CRDO", "COHR", "WDC", "STX", "SNDK"}
BITCOIN_COMPUTE = {"BTDR", "HUT", "CLSK", "RIOT", "MARA", "WULF", "IREN", "CORZ", "CIFR", "WGMI"}
BIOTECH_HEALTH = {"RXRX", "TEM", "XLV", "UNH", "LLY", "NVO", "MRK", "PFE"}
BENCHMARKS = {"SPY", "QQQ", "IWM", "DIA"}
ENERGY = {"XLE", "XOM", "CVX", "OXY", "COP", "SLB"}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        value = float(x)
        return default if math.isnan(value) or math.isinf(value) else value
    except Exception:
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "app", None) is not None:
            return mod
    for mod in list(sys.modules.values()):
        if mod is not None and getattr(mod, "app", None) is not None and hasattr(mod, "load_state"):
            return mod
    return None


def _now(mod: Any = None) -> str:
    try:
        return mod.local_ts_text()
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_state(mod: Any = None) -> Tuple[Dict[str, Any], Any]:
    mod = mod or _mod()
    try:
        state = mod.load_state() if mod is not None and hasattr(mod, "load_state") else {}
    except Exception:
        state = {}
    return (state if isinstance(state, dict) else {}), mod


def _market(state: Dict[str, Any]) -> Dict[str, Any]:
    auto_last = _dict(_dict(state.get("auto_runner")).get("last_result"))
    return _dict(state.get("last_market")) or auto_last or _dict(state.get("market"))


def _cash_pct(state: Dict[str, Any]) -> float:
    cash = _f(state.get("cash"), 0.0)
    equity = _f(state.get("equity"), 0.0)
    return cash / equity if equity > 0 else 0.0


def _positions_count(state: Dict[str, Any]) -> int:
    positions = state.get("positions")
    return len(positions) if isinstance(positions, dict) else 0


def _risk_state(row: Dict[str, Any], state: Dict[str, Any]) -> str:
    risk = _dict(state.get("risk_controls"))
    self_defense = bool(row.get("self_defense_active") or risk.get("self_defense_active") or risk.get("halted"))
    drawdown = max(_f(row.get("intraday_drawdown_pct"), 0.0), _f(risk.get("intraday_drawdown_pct"), 0.0), _f(risk.get("daily_loss_pct"), 0.0))
    if self_defense:
        return "protected"
    if drawdown >= 1.0:
        return "drawdown_watch"
    if _cash_pct(state) >= 0.75 and _positions_count(state) <= 3:
        return "underdeployed_clean"
    return "clean"


def _symbol_cluster(symbol: str, bucket: str = "", sector: str = "") -> str:
    sym = symbol.upper()
    text = f"{bucket} {sector}".lower()
    if sym in PRECIOUS_METALS or "gold" in text or "silver" in text or "metal" in text:
        return "precious_metals_defensive"
    if sym in BITCOIN_COMPUTE or "bitcoin" in text or "crypto" in text:
        return "bitcoin_ai_compute"
    if sym in AI_COMPUTE or "semi" in text or "data_center" in text or "ai" in text:
        return "ai_data_center_compute"
    if sym in MEGA_CAP_GROWTH or "mega" in text or "growth" in text:
        return "mega_cap_growth"
    if sym in BIOTECH_HEALTH or "health" in text or "biotech" in text:
        return "healthcare_biotech"
    if sym in BENCHMARKS or "benchmark" in text or sym in {"SPY", "QQQ"}:
        return "benchmark_index"
    if sym in ENERGY or "energy" in text or sector == "XLE":
        return "energy_inflation"
    if sector in {"XLI", "XLB"} or "industrial" in text:
        return "industrial_cyclical"
    return "unclassified"


def _normalize_existing_regime(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"bull", "risk_on", "risk-on", "uptrend", "growth", "riskon"}:
        return "bull"
    if raw in {"bear", "risk_off", "risk-off", "downtrend", "defensive", "riskoff"}:
        return "bear"
    if raw in {"neutral", "mixed", "sideways", "range", "chop"}:
        return "neutral"
    return ""


def _derive_regime(row: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    original = row.get("regime")
    normalized = _normalize_existing_regime(original)
    source = "existing_regime" if normalized else "derived_from_context"
    market = _market(state)
    market_mode = str(row.get("market_mode") or market.get("market_mode") or state.get("market_mode") or "").lower()
    futures_action = str(row.get("futures_action") or "").lower()
    cluster = str(row.get("signal_cluster") or _symbol_cluster(str(row.get("symbol") or ""), str(row.get("bucket") or ""), str(row.get("sector") or "")))
    risk_state = str(row.get("risk_state") or _risk_state(row, state))

    if not normalized:
        if market_mode in {"risk_on", "risk-on", "bull", "growth_leadership"}:
            normalized = "bull"
        elif market_mode in {"risk_off", "risk-off", "bear", "defensive"}:
            normalized = "bear"
        elif futures_action in {"risk_off", "bearish_caution", "gap_chase_protection"}:
            normalized = "neutral" if cluster != "precious_metals_defensive" else "bear"
        elif risk_state in {"protected", "drawdown_watch"}:
            normalized = "neutral"
        else:
            normalized = "neutral"

    if normalized == "bull":
        family = "risk_on"
    elif normalized == "bear":
        family = "risk_off"
    else:
        family = "neutral_mixed"

    if cluster == "precious_metals_defensive" and normalized in {"bear", "neutral"}:
        subregime = "defensive_rotation"
    elif cluster in {"ai_data_center_compute", "mega_cap_growth", "bitcoin_ai_compute"} and normalized == "bull":
        subregime = "growth_leadership"
    elif risk_state == "underdeployed_clean":
        subregime = "underdeployed_selective"
    else:
        subregime = f"{family}_{risk_state}"

    return {
        "regime": normalized,
        "original_regime": original,
        "regime_source": source,
        "regime_family": family,
        "regime_subtype": subregime,
        "regime_signature": f"{normalized}|{family}|{subregime}|{cluster}",
    }


def _feature_quality(row: Dict[str, Any]) -> Dict[str, Any]:
    missing = []
    for field in REQUIRED_FIELDS:
        value = row.get(field)
        if value is None or value == "" or value == "unknown":
            missing.append(field)
    score = 1.0 - (len(missing) / max(1, len(REQUIRED_FIELDS)))
    if row.get("regime") in {None, "", "unknown"}:
        score -= 0.08
    if row.get("bucket") == "unknown" or row.get("sector") == "unknown":
        score -= 0.08
    if row.get("reason"):
        score += 0.04
    if row.get("mae_mfe_feature_enriched") or _dict(row.get("mae_mfe_features")):
        score += 0.05
    score = max(0.0, min(1.0, score))
    if score >= 0.88:
        label = "high_quality"
    elif score >= 0.68:
        label = "usable"
    else:
        label = "sparse"
    return {"feature_quality_score": round(score, 4), "feature_quality": label, "feature_missing_fields": missing[:12]}


def _enrich_row(row: Dict[str, Any], state: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    if not isinstance(row, dict):
        return row, False
    before = dict(row)
    symbol = str(row.get("symbol") or "").upper()
    bucket = str(row.get("bucket") or "unknown")
    sector = str(row.get("sector") or "unknown")
    row["symbol"] = symbol
    row["bucket"] = bucket or "unknown"
    row["sector"] = sector or "unknown"
    row["journal_schema_version"] = VERSION
    row["signal_cluster"] = row.get("signal_cluster") or _symbol_cluster(symbol, bucket, sector)
    row["risk_state"] = _risk_state(row, state)
    row["cash_pct_at_log"] = round(_cash_pct(state), 4)
    row["positions_count_at_log"] = _positions_count(state)
    row["underdeployed_at_log"] = bool(row["cash_pct_at_log"] >= 0.75 and row["positions_count_at_log"] <= 3)
    row["market_clean_for_entries"] = bool(row.get("risk_state") not in {"protected", "drawdown_watch"})

    regime = _derive_regime(row, state)
    if not row.get("regime") or str(row.get("regime")).lower() in {"unknown", "mixed"}:
        row["regime"] = regime["regime"]
    row["original_regime"] = row.get("original_regime", regime.get("original_regime"))
    row["regime_source"] = row.get("regime_source") or regime["regime_source"]
    row["regime_family"] = row.get("regime_family") or regime["regime_family"]
    row["regime_subtype"] = row.get("regime_subtype") or regime["regime_subtype"]
    row["regime_signature"] = row.get("regime_signature") or regime["regime_signature"]

    q = _feature_quality(row)
    row.update(q)
    row["feature_journal_enriched"] = True
    return row, row != before


def _summary(rows: List[Dict[str, Any]], changed: int) -> Dict[str, Any]:
    quality = Counter(str(row.get("feature_quality") or "unknown") for row in rows if isinstance(row, dict))
    regimes = Counter(str(row.get("regime") or "unknown") for row in rows if isinstance(row, dict))
    families = Counter(str(row.get("regime_family") or "unknown") for row in rows if isinstance(row, dict))
    clusters = Counter(str(row.get("signal_cluster") or "unknown") for row in rows if isinstance(row, dict))
    risk_states = Counter(str(row.get("risk_state") or "unknown") for row in rows if isinstance(row, dict))
    missing = Counter()
    scores = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        scores.append(_f(row.get("feature_quality_score"), 0.0))
        for field in _list(row.get("feature_missing_fields")):
            missing[str(field)] += 1
    avg_quality = round(sum(scores) / max(1, len(scores)), 4)
    return {
        "rows_total": len(rows),
        "rows_enriched_or_refreshed": changed,
        "average_feature_quality_score": avg_quality,
        "quality_counts": dict(quality.most_common()),
        "regimes_seen": sorted([k for k in regimes if k and k != "unknown"]),
        "regime_counts": dict(regimes.most_common()),
        "regime_family_counts": dict(families.most_common()),
        "signal_cluster_counts": dict(clusters.most_common(12)),
        "risk_state_counts": dict(risk_states.most_common()),
        "top_missing_fields": dict(missing.most_common(12)),
        "phase3a_support": {
            "regime_tags_available": bool(len([k for k in regimes if k and k != "unknown"]) >= 1),
            "feature_quality_available": bool(len(scores) > 0),
            "authority_changed": False,
        },
    }


def enrich_state(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    if not ENABLED or not isinstance(state, dict):
        return {}
    ml2 = _dict(state.get("ml_phase2"))
    dataset = _list(ml2.get("dataset"))
    changed = 0
    enriched_rows = []
    for row in dataset:
        if isinstance(row, dict):
            enriched, row_changed = _enrich_row(row, state)
            changed += 1 if row_changed else 0
            enriched_rows.append(enriched)
        else:
            enriched_rows.append(row)
    if isinstance(ml2, dict):
        ml2["dataset"] = enriched_rows
        model = _dict(ml2.get("model"))
        summary = _summary([r for r in enriched_rows if isinstance(r, dict)], changed)
        model["feature_journal_quality"] = summary
        ml2["model"] = model
        ml2["feature_journal_quality"] = summary
        ml2["feature_journal_quality_version"] = VERSION
        ml2["feature_journal_last_enriched_local"] = _now(mod)
        predictions = []
        for pred in _list(ml2.get("last_predictions")):
            if not isinstance(pred, dict):
                continue
            key = str(pred.get("symbol") or "").upper()
            match = next((r for r in reversed(enriched_rows) if isinstance(r, dict) and str(r.get("symbol") or "").upper() == key), None)
            if match:
                pred = dict(pred)
                for k in ("regime", "regime_family", "regime_subtype", "signal_cluster", "feature_quality", "risk_state"):
                    pred[k] = match.get(k)
            predictions.append(pred)
        if predictions:
            ml2["last_predictions"] = predictions
    else:
        summary = _summary([], 0)
    section = state.setdefault("ml_feature_journal_quality", {})
    section.update({
        "status": "ok",
        "type": "ml_feature_journal_quality_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "advisory_only": True,
        "live_trade_decider": False,
        "authority_changed": False,
        "summary": summary,
        "recommended_actions": [
            "Use enriched regime and feature-quality tags for ML diagnostics only; keep ML shadow-only.",
            "Do not treat derived regime tags as proof of Phase 3A readiness by themselves.",
            "Continue collecting executions and observed outcomes before live ML weighting.",
        ],
    })
    return section


def payload(state: Dict[str, Any], mod: Any = None) -> Dict[str, Any]:
    section = enrich_state(state, mod) if ENABLED else _dict(state.get("ml_feature_journal_quality"))
    return {
        "status": "ok",
        "type": "ml_feature_journal_quality_status",
        "version": VERSION,
        "generated_local": _now(mod),
        "enabled": ENABLED,
        "advisory_only": True,
        "authority_changed": False,
        "live_trade_decider": False,
        "summary": section.get("summary", {}),
        "recommended_actions": section.get("recommended_actions", []),
    }


def apply(module: Any = None) -> Dict[str, Any]:
    global _PATCHING
    module = module or _mod()
    if module is None:
        return {"status": "not_applied", "version": VERSION, "reason": "module_missing"}
    if id(module) in PATCHED_MODULE_IDS:
        return {"status": "ok", "version": VERSION, "already_patched": True, "live_trade_decider": False}
    try:
        original = getattr(module, "save_state", None)
        if callable(original):
            def patched_save_state(state):
                global _PATCHING
                if _PATCHING:
                    return original(state)
                try:
                    _PATCHING = True
                    if ENABLED and isinstance(state, dict):
                        enrich_state(state, module)
                except Exception as exc:
                    try:
                        state.setdefault("ml_feature_journal_quality", {})["last_error"] = str(exc)
                    except Exception:
                        pass
                finally:
                    _PATCHING = False
                return original(state)
            patched_save_state._ml_feature_journal_quality_patched = True  # type: ignore[attr-defined]
            module.save_state = patched_save_state
    except Exception:
        pass
    try:
        setattr(module, "ML_FEATURE_JOURNAL_QUALITY_VERSION", VERSION)
    except Exception:
        pass
    PATCHED_MODULE_IDS.add(id(module))
    return {"status": "ok", "version": VERSION, "enabled": ENABLED, "live_trade_decider": False}


def register_routes(flask_app: Any, module: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "version": VERSION, "error": "flask_app_missing"}
    module = module or _mod()
    apply(module)
    if id(flask_app) in REGISTERED_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def status_route():
        state, mod = _load_state(module)
        return jsonify(payload(state, mod))

    if "/paper/ml-feature-journal-status" not in existing:
        flask_app.add_url_rule("/paper/ml-feature-journal-status", "paper_ml_feature_journal_status", status_route)
    if "/paper/regime-tagging-status" not in existing:
        flask_app.add_url_rule("/paper/regime-tagging-status", "paper_regime_tagging_status", status_route)

    REGISTERED_APP_IDS.add(id(flask_app))
    return {"status": "ok", "version": VERSION, "routes": ["/paper/ml-feature-journal-status", "/paper/regime-tagging-status"], "live_trade_decider": False}


try:
    apply(_mod())
except Exception:
    pass
