"""Best-of-cycle entry arbitration overlay.

Paper-only advisory/ranking layer for the limited new-entry slots in a cycle.

Problem addressed:
- The core entry pipeline can consume a limited per-cycle entry slot as soon as a
  candidate passes, then later candidates are blocked by max_new_entries_per_cycle.
- On broad green momentum days, that can make a lower-conviction passing name take
  the slot before the strongest theme/relative-strength candidates are compared.

Design:
- Preview the visible candidate pool with the normal entry_quality_check.
- Do not lower score floors.
- Do not bypass cooldown, held-symbol, max-position, risk, self-defense, or market gates.
- Rank only candidates that pass the existing quality check.
- Pass only the top-ranked candidates into the normal try_entries_and_rotations.
- Append non-selected passable candidates to blocked_entries as
  not_best_of_cycle_candidate for audit visibility.

No live authority is granted here. ML remains shadow-only.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "best-of-cycle-entry-arbitration-2026-06-17-v1"
ENABLED = os.environ.get("BEST_OF_CYCLE_ENTRY_ARBITRATION_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("BEST_OF_CYCLE_ENTRY_ARBITRATION_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
MAX_REVIEWED = int(os.environ.get("BEST_OF_CYCLE_MAX_REVIEWED", "40"))
MAX_NOT_SELECTED_ROWS = int(os.environ.get("BEST_OF_CYCLE_MAX_NOT_SELECTED_ROWS", "15"))

REGISTERED_APP_IDS: set[int] = set()
PATCHED_MODULE_IDS: set[int] = set()

THEME_PRIORITY = {
    "space_stocks": 0.006,
    "bitcoin_ai_compute": 0.005,
    "semi_leaders": 0.0045,
    "data_center_infra": 0.004,
    "small_cap_momentum": 0.0035,
    "mega_cap_ai": 0.003,
    "cloud_cyber_software": 0.0025,
    "precious_metals": 0.0015,
}

PREFERRED_SYMBOLS = {
    "RKLB", "RDW", "LUNR", "ASTS", "SPCX", "SATL",
    "AMD", "AVGO", "MU", "LRCX", "NVTS", "NBIS", "GEV", "STX", "WDC", "DELL", "HPE",
    "CIFR", "CLSK", "RIOT", "HIVE", "HUT", "BTDR", "WULF", "CORZ", "IREN", "MARA",
}


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
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


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


def _symbol(signal: Dict[str, Any]) -> str:
    return str(signal.get("symbol") or signal.get("ticker") or "").upper().strip()


def _side(signal: Dict[str, Any]) -> str:
    return str(signal.get("side") or "long").lower().strip() or "long"


def _positions(core: Any) -> Dict[str, Any]:
    try:
        positions = core.portfolio.get("positions", {}) or {}
        return positions if isinstance(positions, dict) else {}
    except Exception:
        return {}


def _bucket(core: Any, symbol: str, signal: Dict[str, Any]) -> str:
    value = signal.get("bucket") or signal.get("symbol_bucket")
    if value:
        return str(value)
    try:
        fn = getattr(core, "symbol_bucket", None)
        if callable(fn):
            return str(fn(symbol))
    except Exception:
        pass
    try:
        bucket_map = getattr(core, "SYMBOL_BUCKET", {}) or {}
        if isinstance(bucket_map, dict):
            return str(bucket_map.get(symbol, "unknown"))
    except Exception:
        pass
    return "unknown"


def _sector(core: Any, symbol: str, signal: Dict[str, Any]) -> str:
    value = signal.get("sector")
    if value:
        return str(value)
    try:
        sector_map = getattr(core, "SYMBOL_SECTOR", {}) or {}
        if isinstance(sector_map, dict):
            return str(sector_map.get(symbol, "UNKNOWN"))
    except Exception:
        pass
    return "UNKNOWN"


def _quality_reason(quality_info: Dict[str, Any]) -> str:
    if not isinstance(quality_info, dict):
        return "unknown"
    reason = str(quality_info.get("reason") or "")
    if reason:
        return reason
    controlled = quality_info.get("controlled_pullback_info")
    if isinstance(controlled, dict):
        return str(controlled.get("reason") or "controlled_pullback")
    return "unknown"


def _signal_text(signal: Dict[str, Any], quality_info: Dict[str, Any]) -> str:
    parts = []
    for obj in (signal, quality_info):
        if isinstance(obj, dict):
            for key in ("entry_context", "trade_class", "reason", "signal_type", "selection_reason"):
                if obj.get(key):
                    parts.append(str(obj.get(key)).lower())
    return " ".join(parts)


def _is_relative_strength(signal: Dict[str, Any], quality_info: Dict[str, Any]) -> bool:
    text = _signal_text(signal, quality_info)
    if "relative_strength" in text or "relative strength" in text or "leader" in text:
        return True
    for key in ("relative_strength", "relative_strength_score", "rs_score", "rs_rank", "momentum_rank"):
        value = signal.get(key)
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, (int, float)) and _safe_float(value) > 0:
            return True
    return False


def _is_breakout(signal: Dict[str, Any], quality_info: Dict[str, Any]) -> bool:
    text = _signal_text(signal, quality_info)
    if "breakout" in text or "reclaim" in text:
        return True
    for key in ("breakout", "is_breakout", "breakout_signal"):
        if bool(signal.get(key)):
            return True
    return False


def _theme_confirmed(signal: Dict[str, Any]) -> bool:
    theme = signal.get("theme_confirmation")
    catalyst = signal.get("catalyst")
    if isinstance(theme, dict) and theme.get("active"):
        return True
    if isinstance(catalyst, dict) and catalyst.get("active"):
        return True
    return False


def _normal_entry_floor(core: Any, market: Dict[str, Any], side: str) -> float:
    try:
        fn = getattr(core, "min_entry_score_for_market", None)
        if callable(fn):
            return _safe_float(fn(market or {}, side), 0.0)
    except Exception:
        pass
    return 0.0


def _entry_limit(core: Any, params: Dict[str, Any], positions_count: int) -> int:
    max_new = _safe_int(getattr(core, "MAX_NEW_ENTRIES_PER_CYCLE", None), 1)
    if max_new <= 0:
        max_new = 1
    max_positions = _safe_int((params or {}).get("max_positions"), 0)
    slots = max(0, max_positions - positions_count) if max_positions > 0 else max_new
    return max(0, min(max_new, slots if slots > 0 else max_new))


def _quality_preview(core: Any, signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
    symbol = _symbol(signal)
    positions = _positions(core)
    if not symbol:
        return False, {"reason": "missing_symbol"}, dict(signal)
    if symbol in positions:
        return False, {"reason": "already_held"}, dict(signal)
    try:
        cooldown_fn = getattr(core, "is_in_cooldown", None)
        if callable(cooldown_fn) and cooldown_fn(symbol):
            return False, {"reason": "cooldown"}, dict(signal)
    except Exception:
        pass

    preview_signal = dict(signal)
    preview_signal.setdefault("bucket", _bucket(core, symbol, preview_signal))
    preview_signal.setdefault("sector", _sector(core, symbol, preview_signal))

    try:
        quality_fn = getattr(core, "entry_quality_check", None)
        if callable(quality_fn):
            ok, info = quality_fn(preview_signal, params or {}, market or {})
            return bool(ok), info if isinstance(info, dict) else {"reason": str(info)}, preview_signal
    except Exception as exc:
        return False, {"reason": f"entry_quality_preview_error:{type(exc).__name__}"}, preview_signal

    return True, {"reason": "entry_quality_unavailable_assume_original_pipeline"}, preview_signal


def _arbitration_score(core: Any, signal: Dict[str, Any], quality_info: Dict[str, Any], market: Dict[str, Any]) -> float:
    symbol = _symbol(signal)
    side = _side(signal)
    raw_score = _safe_float(signal.get("score"), 0.0)
    bucket = _bucket(core, symbol, signal)
    reason = _quality_reason(quality_info)
    score = raw_score

    # Reward normal quality passes more than controlled/research pullbacks. This keeps
    # opportunistic starter trades from beating cleaner leaders unless no leader passes.
    if reason == "entry_quality_ok":
        score += 0.012
    elif "controlled_pullback" in reason:
        score += 0.002
    else:
        score += 0.004

    if _is_relative_strength(signal, quality_info):
        score += 0.006
    if _is_breakout(signal, quality_info):
        score += 0.005
    if _theme_confirmed(signal):
        score += 0.004
    score += THEME_PRIORITY.get(bucket, 0.0)
    if symbol in PREFERRED_SYMBOLS:
        score += 0.002

    # Penalize explicit extension/chase evidence if a signal somehow still passed.
    text = _signal_text(signal, quality_info)
    if "extended" in text or "near_high" in text or "chase" in text:
        score -= 0.006

    # Do not let score modifications make a below-floor signal look like a normal
    # above-floor pass. Controlled-pullback candidates can still be selected only if
    # the normal entry_quality_check explicitly allowed them.
    floor = _normal_entry_floor(core, market, side)
    if floor > 0 and raw_score < floor and "controlled_pullback" not in reason:
        score = min(score, raw_score)

    return round(float(score), 8)


def _summary(core: Any, signal: Dict[str, Any], quality_info: Dict[str, Any], passed: bool, arbitration_score: float | None = None) -> Dict[str, Any]:
    symbol = _symbol(signal)
    return {
        "symbol": symbol,
        "side": _side(signal),
        "score": round(_safe_float(signal.get("score"), 0.0), 6),
        "arbitration_score": arbitration_score,
        "quality_passed": bool(passed),
        "quality_reason": _quality_reason(quality_info),
        "bucket": _bucket(core, symbol, signal),
        "sector": _sector(core, symbol, signal),
        "relative_strength": _is_relative_strength(signal, quality_info),
        "breakout": _is_breakout(signal, quality_info),
        "theme_confirmed": _theme_confirmed(signal),
        "entry_context": signal.get("entry_context"),
        "trade_class": signal.get("trade_class"),
    }


def _split_signals(signals: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    longs: List[Dict[str, Any]] = []
    shorts: List[Dict[str, Any]] = []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        if _side(signal) == "short":
            shorts.append(signal)
        else:
            longs.append(signal)
    return longs, shorts


def _patch_try_entries(core: Any) -> bool:
    current = getattr(core, "try_entries_and_rotations", None)
    if not callable(current) or getattr(current, "_best_of_cycle_arbitration_patched", False):
        return False
    original = current

    def patched_try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
        if not (ENABLED and _paper_context() and bool(new_entries_allowed)):
            return original(long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

        params_dict = params or {}
        market_dict = market or {}
        try:
            positions_count = len(_positions(core))
            limit = _entry_limit(core, params_dict, positions_count)
            if limit <= 0:
                return original(long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

            raw_candidates: List[Dict[str, Any]] = []
            if params_dict.get("allow_longs", False):
                raw_candidates.extend([s for s in (long_signals or []) if isinstance(s, dict)])
            if params_dict.get("allow_shorts", False):
                raw_candidates.extend([s for s in (short_signals or []) if isinstance(s, dict)])
            raw_candidates = raw_candidates[:MAX_REVIEWED]
            if not raw_candidates:
                return original(long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

            reviewed: List[Dict[str, Any]] = []
            eligible: List[Dict[str, Any]] = []
            rejected: List[Dict[str, Any]] = []
            for signal in raw_candidates:
                ok, quality_info, preview_signal = _quality_preview(core, signal, params_dict, market_dict)
                arb_score = _arbitration_score(core, preview_signal, quality_info, market_dict) if ok else None
                row = _summary(core, preview_signal, quality_info, ok, arb_score)
                reviewed.append(row)
                if ok:
                    candidate = dict(preview_signal)
                    candidate["best_of_cycle_arbitration"] = {
                        "version": VERSION,
                        "arbitration_score": arb_score,
                        "quality_reason": row.get("quality_reason"),
                        "raw_score": row.get("score"),
                        "bucket": row.get("bucket"),
                        "relative_strength": row.get("relative_strength"),
                        "breakout": row.get("breakout"),
                        "theme_confirmed": row.get("theme_confirmed"),
                    }
                    eligible.append({"signal": candidate, "summary": row, "arbitration_score": arb_score or 0.0})
                else:
                    rejected.append(row)

            if not eligible:
                try:
                    core.portfolio["best_of_cycle_entry_arbitration"] = {
                        "status": "no_eligible_preview_candidates",
                        "version": VERSION,
                        "generated_local": _now(core),
                        "reviewed_count": len(reviewed),
                        "eligible_count": 0,
                        "rejected_preview": rejected[:MAX_NOT_SELECTED_ROWS],
                        "authority_changed": False,
                        "live_trade_authority": "none",
                        "ml_authority": "shadow_only",
                    }
                except Exception:
                    pass
                return original(long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

            ranked = sorted(eligible, key=lambda row: row.get("arbitration_score", 0.0), reverse=True)
            selected_rows = ranked[:limit]
            selected_symbols = {_symbol(row["signal"]) for row in selected_rows}
            selected_signals = [row["signal"] for row in selected_rows]
            not_selected = [row for row in ranked[limit:]]

            call_longs, call_shorts = _split_signals(selected_signals)
            entries, rotations, blocked_entries = original(call_longs, call_shorts, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

            extra_blocked = []
            for row in not_selected[:MAX_NOT_SELECTED_ROWS]:
                summary = row.get("summary", {})
                extra_blocked.append({
                    "symbol": summary.get("symbol"),
                    "side": summary.get("side"),
                    "score": summary.get("score"),
                    "reason": "not_best_of_cycle_candidate",
                    "arbitration_score": summary.get("arbitration_score"),
                    "selected_symbols": sorted(selected_symbols),
                    "quality_reason": summary.get("quality_reason"),
                    "bucket": summary.get("bucket"),
                    "relative_strength": summary.get("relative_strength"),
                    "breakout": summary.get("breakout"),
                    "theme_confirmed": summary.get("theme_confirmed"),
                    "version": VERSION,
                })

            try:
                if isinstance(blocked_entries, list):
                    blocked_entries.extend(extra_blocked)
            except Exception:
                pass

            try:
                core.portfolio["best_of_cycle_entry_arbitration"] = {
                    "status": "ok",
                    "version": VERSION,
                    "generated_local": _now(core),
                    "reviewed_count": len(reviewed),
                    "eligible_count": len(eligible),
                    "selection_limit": limit,
                    "selected_candidates": [row.get("summary") for row in selected_rows],
                    "not_selected_count": len(not_selected),
                    "not_selected_sample": [row.get("summary") for row in not_selected[:MAX_NOT_SELECTED_ROWS]],
                    "rejected_preview": rejected[:MAX_NOT_SELECTED_ROWS],
                    "entries_returned_count": len(entries or []),
                    "rotations_returned_count": len(rotations or []),
                    "authority_changed": False,
                    "live_trade_authority": "none",
                    "ml_authority": "shadow_only",
                    "guardrails": {
                        "does_not_raise_max_positions": True,
                        "does_not_bypass_risk_controls": True,
                        "does_not_bypass_self_defense": True,
                        "does_not_lower_score_thresholds": True,
                        "normal_entry_quality_check_required": True,
                    },
                }
            except Exception:
                pass
            return entries, rotations, blocked_entries
        except Exception as exc:
            try:
                core.portfolio["best_of_cycle_entry_arbitration"] = {
                    "status": "error_fallback_to_original",
                    "version": VERSION,
                    "generated_local": _now(core),
                    "error": f"{type(exc).__name__}: {exc}",
                    "authority_changed": False,
                }
            except Exception:
                pass
            return original(long_signals, short_signals, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)

    patched_try_entries_and_rotations._best_of_cycle_arbitration_patched = True  # type: ignore[attr-defined]
    patched_try_entries_and_rotations._best_of_cycle_original = original  # type: ignore[attr-defined]
    core.try_entries_and_rotations = patched_try_entries_and_rotations
    return True


def status_payload(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    latest = {}
    if core is not None:
        try:
            latest = core.portfolio.get("best_of_cycle_entry_arbitration") or {}
        except Exception:
            latest = {}
    current = getattr(core, "try_entries_and_rotations", None) if core is not None else None
    return {
        "status": "ok" if core is not None else "pending",
        "overall": "pass" if core is not None else "pending",
        "type": "best_of_cycle_entry_arbitration_status",
        "version": VERSION,
        "generated_local": _now(core),
        "enabled": bool(ENABLED),
        "paper_context": bool(_paper_context()),
        "patched_try_entries": bool(getattr(current, "_best_of_cycle_arbitration_patched", False)),
        "latest": latest,
        "policy": {
            "max_reviewed": MAX_REVIEWED,
            "max_not_selected_rows": MAX_NOT_SELECTED_ROWS,
            "theme_priority": THEME_PRIORITY,
            "preferred_symbols": sorted(PREFERRED_SYMBOLS),
            "does_not_raise_max_positions": True,
            "does_not_bypass_risk_controls": True,
            "does_not_bypass_self_defense": True,
            "does_not_lower_score_thresholds": True,
            "normal_entry_quality_check_required": True,
            "live_trade_authority": "none",
            "ml_authority": "shadow_only",
            "authority_changed": False,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    core = core or _mod()
    if core is None:
        return status_payload(core)
    patched = _patch_try_entries(core)
    PATCHED_MODULE_IDS.add(id(core))
    payload = status_payload(core)
    payload["patched_this_call"] = {"try_entries_and_rotations": bool(patched)}
    return payload


def apply_runtime_overrides(core: Any = None) -> Dict[str, Any]:
    return apply(core)


def register_routes(flask_app: Any, core: Any = None) -> None:
    if flask_app is None or id(flask_app) in REGISTERED_APP_IDS:
        return
    from flask import jsonify
    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if "/paper/best-of-cycle-entry-arbitration-status" not in existing:
        flask_app.add_url_rule(
            "/paper/best-of-cycle-entry-arbitration-status",
            "best_of_cycle_entry_arbitration_status",
            lambda: jsonify(apply(core or _mod())),
        )
    REGISTERED_APP_IDS.add(id(flask_app))
    apply(core or _mod())


try:
    apply(_mod())
except Exception:
    pass
