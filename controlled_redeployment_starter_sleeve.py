from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, List, Tuple

VERSION = "controlled-redeployment-starter-sleeve-2026-06-29-v1"
ENABLED = os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
MAX_REVIEWED_RANK = int(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MAX_REVIEWED_RANK", "5"))
MAX_REVIEWED = int(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MAX_REVIEWED", "30"))
MAX_ENTRIES_PER_DAY = int(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MAX_ENTRIES_PER_DAY", "1"))
MIN_CASH_PCT = float(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MIN_CASH_PCT", "80.0"))
ALLOC_FACTOR = float(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_ALLOC_FACTOR", "0.22"))
MIN_RAW_SCORE = float(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MIN_RAW_SCORE", "0.0135"))
MIN_RANK_SCORE = float(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MIN_RANK_SCORE", "0.0190"))
MAX_DAILY_LOSS_PCT = float(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MAX_DAILY_LOSS_PCT", "0.00"))
MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_MAX_INTRADAY_DRAWDOWN_PCT", "0.10"))
ALLOWED_MODES = {s.strip().lower() for s in os.environ.get("CONTROLLED_REDEPLOYMENT_STARTER_ALLOWED_MODES", "risk_on,constructive").split(",") if s.strip()}
ALLOWED_BLOCKERS = {"post_harvest_controlled_redeployment_candidates", "post_harvest_redeploy_blocked_by_market_mode", "post_harvest_controller_blocked", "post_harvest_underdeployed_block"}

REGISTERED_APP_IDS: set[int] = set()
_PATCHED = False
_ORIGINAL_CORE_FN = None
_LAST_STATUS: Dict[str, Any] = {}


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    for module in list(sys.modules.values()):
        if module is not None and getattr(module, "app", None) is not None and hasattr(module, "try_entries_and_rotations"):
            return module
    return None


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper_context() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not (live or broker_live)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _portfolio(core: Any) -> Dict[str, Any]:
    try:
        pf = getattr(core, "portfolio", {}) or {}
        return pf if isinstance(pf, dict) else {}
    except Exception:
        return {}


def _positions(core: Any) -> Dict[str, Any]:
    positions = _portfolio(core).get("positions", {}) or {}
    return positions if isinstance(positions, dict) else {}


def _cash_pct(core: Any) -> float:
    pf = _portfolio(core)
    cash = _safe_float(pf.get("cash"), 0.0)
    equity = _safe_float(pf.get("equity"), 0.0) or cash
    return round((cash / equity) * 100.0, 4) if equity > 0 else 0.0


def _risk_controls(core: Any) -> Dict[str, Any]:
    try:
        fn = getattr(core, "get_risk_controls", None)
        if callable(fn):
            rc = fn()
            return rc if isinstance(rc, dict) else {}
    except Exception:
        pass
    rc = _portfolio(core).get("risk_controls", {}) or {}
    return rc if isinstance(rc, dict) else {}


def _blockers(entry_block_reason: Any) -> set[str]:
    text = str(entry_block_reason or "")
    out = set()
    for sep in (",", "|", ";"):
        if sep in text:
            out.update(part.strip() for part in text.split(sep) if part.strip())
            return out
    return {text.strip()} if text.strip() else set()


def _symbol(signal: Dict[str, Any]) -> str:
    return str(signal.get("symbol") or signal.get("ticker") or "").upper().strip()


def _side(signal: Dict[str, Any]) -> str:
    return str(signal.get("side") or "long").lower().strip() or "long"


def _entries_today(core: Any) -> int:
    try:
        import core_entry_pipeline as cep
        fn = getattr(cep, "_entries_today_with_context", None)
        return int(fn(core, "controlled_redeployment_starter")) if callable(fn) else 0
    except Exception:
        return 0


def _context_ok(core: Any, market: Dict[str, Any], entry_block_reason: Any) -> Tuple[bool, Dict[str, Any]]:
    blockers = _blockers(entry_block_reason)
    text = " ".join(sorted(blockers)).lower()
    if not ENABLED:
        return False, {"reason": "controlled_redeployment_starter_disabled"}
    if not _paper_context():
        return False, {"reason": "controlled_redeployment_not_paper_context"}
    if not (blockers & ALLOWED_BLOCKERS or "post_harvest" in text):
        return False, {"reason": "not_post_harvest_redeployment_block", "entry_block_reason": entry_block_reason, "blockers": sorted(blockers)}
    mode = str((market or {}).get("market_mode") or "").lower()
    if mode not in ALLOWED_MODES or bool((market or {}).get("bear_confirmed")):
        return False, {"reason": "controlled_redeployment_market_not_clean", "market_mode": mode, "allowed_modes": sorted(ALLOWED_MODES)}
    futures = (market or {}).get("futures_bias", {}) or {}
    if str(futures.get("action") or "").lower() == "block_opening_longs":
        return False, {"reason": "controlled_redeployment_futures_block_opening_longs", "futures_bias": futures}
    if len(_positions(core)) > 0:
        return False, {"reason": "controlled_redeployment_open_positions_not_empty", "open_positions": len(_positions(core))}
    cash_pct = _cash_pct(core)
    if cash_pct < MIN_CASH_PCT:
        return False, {"reason": "controlled_redeployment_cash_not_high_enough", "cash_pct": cash_pct, "min_cash_pct": MIN_CASH_PCT}
    rc = _risk_controls(core)
    if bool(rc.get("halted", False)) or bool(rc.get("self_defense_active", False)):
        return False, {"reason": "controlled_redeployment_risk_state_not_clean", "risk_controls": rc}
    if _safe_float(rc.get("daily_loss_pct"), 0.0) > MAX_DAILY_LOSS_PCT:
        return False, {"reason": "controlled_redeployment_daily_loss_not_clean", "risk_controls": rc}
    if _safe_float(rc.get("intraday_drawdown_pct"), 0.0) > MAX_INTRADAY_DRAWDOWN_PCT:
        return False, {"reason": "controlled_redeployment_intraday_drawdown_too_high", "risk_controls": rc}
    used = _entries_today(core)
    if used >= MAX_ENTRIES_PER_DAY:
        return False, {"reason": "controlled_redeployment_daily_limit", "entries_today": used}
    return True, {"reason": "controlled_redeployment_context_ok", "cash_pct": cash_pct, "entry_block_reason": entry_block_reason, "blockers": sorted(blockers), "entries_today": used}


def _block_rows(candidates: List[Dict[str, Any]], reason: str, max_rows: int = 10) -> List[Dict[str, Any]]:
    return [{"symbol": c.get("symbol"), "side": c.get("side"), "score": c.get("score"), "rank_score": c.get("core_entry_rank_score"), "reason": reason} for c in list(candidates or [])[:max_rows]]


def _try_starter(core: Any, candidates: List[Dict[str, Any]], params: Dict[str, Any], market: Dict[str, Any], entry_block_reason: Any):
    entries: List[Dict[str, Any]] = []
    rotations: List[Dict[str, Any]] = []
    ok, context = _context_ok(core, market, entry_block_reason)
    payload: Dict[str, Any] = {"version": VERSION, "mode": "controlled_redeployment_starter", "status": "checked", "context": context, "candidate_count": len(candidates), "reviewed_count": 0, "eligible_count": 0}
    if not ok:
        payload.update({"status": "blocked", "reason": context.get("reason")})
        return entries, rotations, _block_rows(candidates, payload["reason"]), payload
    try:
        import core_entry_pipeline as cep
    except Exception as exc:
        payload.update({"status": "blocked", "reason": "core_entry_pipeline_import_failed", "error": str(exc)})
        return entries, rotations, _block_rows(candidates, payload["reason"]), payload
    rejected: List[Dict[str, Any]] = []
    selected = None
    quality_info: Any = {}
    valve_entries = 0
    for rank_index, signal in enumerate(candidates[:MAX_REVIEWED], start=1):
        payload["reviewed_count"] += 1
        symbol = _symbol(signal)
        side = _side(signal)
        score = _safe_float(signal.get("score"), 0.0)
        rank_score = _safe_float(signal.get("core_entry_rank_score"), score)
        row = {"symbol": symbol, "side": side, "score": round(score, 6), "rank_score": round(rank_score, 6), "rank_index": rank_index}
        if side != "long" or rank_index > MAX_REVIEWED_RANK or symbol in _positions(core):
            rejected.append({**row, "reason": "controlled_redeployment_candidate_not_allowed"})
            continue
        try:
            if callable(getattr(core, "is_in_cooldown", None)) and core.is_in_cooldown(symbol):
                rejected.append({**row, "reason": "cooldown"})
                continue
        except Exception:
            pass
        if score < MIN_RAW_SCORE or rank_score < MIN_RANK_SCORE:
            rejected.append({**row, "reason": "controlled_redeployment_score_too_low", "min_raw_score": MIN_RAW_SCORE, "min_rank_score": MIN_RANK_SCORE})
            continue
        candidate = dict(signal)
        candidate["alloc_factor"] = min(_safe_float(candidate.get("alloc_factor"), 1.0), ALLOC_FACTOR)
        candidate["entry_context"] = "controlled_redeployment_starter"
        candidate["trade_class"] = "controlled_redeployment_starter"
        try:
            quality_ok, quality_info = core.entry_quality_check(candidate, dict(params or {}), market)
        except Exception as exc:
            rejected.append({**row, "reason": "entry_quality_check_error", "error": str(exc)})
            continue
        if not quality_ok:
            valve_fn = getattr(cep, "_participation_valve_ok", None)
            valve_ok = False
            valve_info: Dict[str, Any] = {"reason": "participation_valve_missing"}
            if callable(valve_fn):
                try:
                    valve_ok, valve_info = valve_fn(core, candidate, dict(params or {}), market, quality_info, rank_index, 0, valve_entries)
                except Exception as exc:
                    valve_info = {"reason": "participation_valve_error", "error": str(exc)}
            if not valve_ok:
                rejected.append({**row, "reason": "entry_quality_block", "quality_info": quality_info, "participation_valve": valve_info})
                continue
            candidate["core_participation_valve"] = valve_info
            candidate["alloc_factor"] = min(_safe_float(candidate.get("alloc_factor"), 1.0), _safe_float(valve_info.get("alloc_factor"), ALLOC_FACTOR))
            valve_entries += 1
        selected = candidate
        payload["selected_candidate"] = {**row, "reason": "selected_controlled_redeployment_starter"}
        break
    payload["rejected_preview"] = rejected[:15]
    if selected is None:
        payload.update({"status": "no_eligible_candidate", "reason": "controlled_redeployment_no_candidate_passed_quality_or_valve"})
        return entries, rotations, rejected[:15] or _block_rows(candidates, payload["reason"]), payload
    entry = core.enter_position(selected, dict(params or {}), market_mode=(market or {}).get("market_mode", "neutral"))
    if entry and not entry.get("blocked"):
        entry["quality_info"] = quality_info
        entry["core_entry_pipeline"] = {"version": VERSION, "mode": "controlled_redeployment_starter", "alloc_factor": selected.get("alloc_factor")}
        entries.append(entry)
        payload.update({"status": "allowed", "reason": "controlled_redeployment_starter_opened", "eligible_count": 1, "entries_returned_count": 1})
    else:
        blocked = [entry] if isinstance(entry, dict) else []
        payload.update({"status": "attempted_no_entry", "reason": "enter_position_blocked_controlled_redeployment_starter", "enter_position_result": entry})
        return entries, rotations, blocked, payload
    return entries, rotations, [], payload


def _patched_core_try_entries_and_rotations(core: Any, long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
    global _LAST_STATUS
    try:
        import core_entry_pipeline as cep
        candidates = cep._prepare_candidates(core, long_signals or [], short_signals or [], dict(params or {}), dict(market or {}))
    except Exception:
        candidates = []
    if not bool(new_entries_allowed):
        ok, _context = _context_ok(core, dict(market or {}), entry_block_reason)
        if ok:
            entries, rotations, blocked, payload = _try_starter(core, candidates, dict(params or {}), dict(market or {}), entry_block_reason)
            _LAST_STATUS = payload
            try:
                _portfolio(core)["controlled_redeployment_starter_sleeve"] = payload
                _portfolio(core)["core_entry_pipeline"] = {"version": VERSION, **payload}
            except Exception:
                pass
            return entries, rotations, blocked[:15]
    original = _ORIGINAL_CORE_FN
    if callable(original):
        return original(core, long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)
    return [], [], _block_rows(candidates, "controlled_redeployment_original_core_missing")


def apply(core: Any = None) -> Dict[str, Any]:
    global _PATCHED, _ORIGINAL_CORE_FN
    core = core or _mod()
    if not (ENABLED and _paper_context()):
        return status_payload(core)
    try:
        import core_entry_pipeline as cep
        current = getattr(cep, "_core_try_entries_and_rotations", None)
        if getattr(current, "_controlled_redeployment_starter_version", None) == VERSION:
            _PATCHED = True
        else:
            _ORIGINAL_CORE_FN = current
            _patched_core_try_entries_and_rotations._controlled_redeployment_starter_version = VERSION  # type: ignore[attr-defined]
            cep._core_try_entries_and_rotations = _patched_core_try_entries_and_rotations
            _PATCHED = True
            try:
                cep.apply(core)
            except Exception:
                pass
    except Exception as exc:
        _LAST_STATUS["apply_error"] = f"{type(exc).__name__}: {exc}"
    return status_payload(core)


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def policy() -> Dict[str, Any]:
    return {"enabled": bool(ENABLED), "patches_core_function_pointer_only": True, "does_not_wrap_app_try_entries": True, "sits_after_post_harvest_before_entry_quality": True, "hands_candidate_to_existing_entry_quality_check": True, "hands_failed_quality_to_existing_participation_valve": True, "max_entries_per_day": MAX_ENTRIES_PER_DAY, "max_reviewed_rank": MAX_REVIEWED_RANK, "alloc_factor": ALLOC_FACTOR, "min_cash_pct": MIN_CASH_PCT, "min_raw_score": MIN_RAW_SCORE, "min_rank_score": MIN_RANK_SCORE, "allowed_modes": sorted(ALLOWED_MODES), "does_not_bypass_cooldowns": True, "does_not_bypass_self_defense": True, "does_not_bypass_risk_halts": True, "live_trade_authority": "none", "ml_authority": "shadow_only", "authority_changed": False}


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    latest = dict(_LAST_STATUS)
    if not latest and core is not None:
        latest = dict(_portfolio(core).get("controlled_redeployment_starter_sleeve") or {})
    return {"status": "ok" if core is not None else "pending", "overall": "pass" if core is not None else "pending", "type": "controlled_redeployment_starter_sleeve_status", "version": VERSION, "generated_local": _now(core), "enabled": bool(ENABLED), "paper_context": bool(_paper_context()), "patched": bool(_PATCHED), "latest": latest, "policy": policy()}


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    def status_route():
        return jsonify(apply(core or _mod()))
    if "/paper/controlled-redeployment-starter-sleeve-status" not in existing:
        flask_app.add_url_rule("/paper/controlled-redeployment-starter-sleeve-status", "controlled_redeployment_starter_sleeve_status", status_route)
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
