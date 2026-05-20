"""Loss-streak defensive governor and pattern-risk veto for the paper trading bot.

Purpose:
- Fix green-market underperformance caused by late/chase entries turning into full stop-outs.
- Treat repeated intraday losses as a trading-quality problem even before account-level loss limits are hit.
- Convert pattern-recognition chase-risk from a tiny score penalty into a true entry veto.

This module never exits existing positions by itself. It only blocks or annotates fresh entries.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import time
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "loss-streak-pattern-risk-governor-2026-05-20-v1"
PATCH_FLAG = "_loss_streak_defensive_governor_v1"
ROUTE_APP_IDS: set[int] = set()

ENABLED = os.environ.get("LOSS_STREAK_GOVERNOR_ENABLED", "true").lower() not in {"0", "false", "no", "off"}

# Count-based risk controls. These intentionally activate before account-level
# daily drawdown halts because several small failed entries in a green tape usually
# means the entry logic is mistimed or chasing.
CAUTION_LOSSES_TODAY = int(os.environ.get("LOSS_GOV_CAUTION_LOSSES_TODAY", "2"))
HARD_BLOCK_LOSSES_TODAY = int(os.environ.get("LOSS_GOV_HARD_BLOCK_LOSSES_TODAY", "3"))
CAUTION_STOP_LOSSES_TODAY = int(os.environ.get("LOSS_GOV_CAUTION_STOP_LOSSES_TODAY", "1"))
HARD_BLOCK_STOP_LOSSES_TODAY = int(os.environ.get("LOSS_GOV_HARD_BLOCK_STOP_LOSSES_TODAY", "2"))

# Score requirements after losses start stacking.
MIN_SCORE_AFTER_CAUTION = float(os.environ.get("LOSS_GOV_MIN_SCORE_AFTER_CAUTION", "0.0450"))
MIN_SCORE_AFTER_HARD_BLOCK = float(os.environ.get("LOSS_GOV_MIN_SCORE_AFTER_HARD_BLOCK", "0.0600"))
MAX_OPEN_POSITIONS_CAUTION = int(os.environ.get("LOSS_GOV_MAX_OPEN_POSITIONS_CAUTION", "2"))
MAX_OPEN_POSITIONS_HARD = int(os.environ.get("LOSS_GOV_MAX_OPEN_POSITIONS_HARD", "1"))

# Pattern-risk controls.
PATTERN_RISK_VETO_ENABLED = os.environ.get("PATTERN_RISK_VETO_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
CHASE_RISK_NAMES = {
    x.strip() for x in os.environ.get("PATTERN_RISK_VETO_NAMES", "overextension_chase_risk").split(",") if x.strip()
}
MIXED_PATTERN_BIASES = {
    x.strip() for x in os.environ.get("PATTERN_RISK_VETO_BIASES", "mixed_structure,chase_or_weak_structure").split(",") if x.strip()
}
CHASE_RISK_EXCEPTIONAL_SCORE = float(os.environ.get("PATTERN_RISK_EXCEPTIONAL_SCORE", "0.0600"))
ALLOW_EXCEPTIONAL_CLEAN_RETEST = os.environ.get("PATTERN_RISK_ALLOW_EXCEPTIONAL_RETEST", "true").lower() not in {"0", "false", "no", "off"}
RETEST_OR_RECLAIM_PATTERNS = {
    "breakout_retest_hold",
    "failed_breakdown_reclaim",
    "relative_strength_pullback",
}

# If enabled, blocked signals are removed from scan results before downstream
# entry/rotation code can act on them. The entry-quality wrapper still acts as
# a second safety net.
FILTER_SCAN_SIGNALS = os.environ.get("LOSS_GOV_FILTER_SCAN_SIGNALS", "true").lower() not in {"0", "false", "no", "off"}


def _now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _portfolio(m: Any) -> Dict[str, Any]:
    p = getattr(m, "portfolio", {})
    return p if isinstance(p, dict) else {}


def _today(m: Any) -> dt.date:
    try:
        tz = getattr(m, "MARKET_TZ", None)
        if tz is not None:
            return dt.datetime.now(tz).date()
    except Exception:
        pass
    return dt.datetime.now().date()


def _trade_date(m: Any, ts: Any) -> dt.date | None:
    try:
        value = float(ts)
        tz = getattr(m, "MARKET_TZ", None)
        if tz is not None:
            return dt.datetime.fromtimestamp(value, tz).date()
        return dt.datetime.fromtimestamp(value).date()
    except Exception:
        return None


def _realized_snapshot(m: Any) -> Dict[str, Any]:
    rp: Dict[str, Any] = {}
    try:
        fn = getattr(m, "get_realized_pnl", None)
        if callable(fn):
            maybe = fn()
            if isinstance(maybe, dict):
                rp = dict(maybe)
    except Exception:
        rp = {}
    perf = _portfolio(m).get("performance") or {}
    if isinstance(perf, dict):
        for key in ("wins_today", "losses_today", "wins_total", "losses_total"):
            if key not in rp and key in perf:
                rp[key] = perf.get(key)
        if "today" not in rp and "realized_pnl_today" in perf:
            rp["today"] = perf.get("realized_pnl_today")
        if "total" not in rp and "realized_pnl_total" in perf:
            rp["total"] = perf.get("realized_pnl_total")
    return rp


def _stop_losses_today(m: Any) -> int:
    today = _today(m)
    count = 0
    for t in list(_portfolio(m).get("trades", []) or []):
        if not isinstance(t, dict):
            continue
        if str(t.get("action", "")).lower() != "exit":
            continue
        reason = str(t.get("exit_reason") or t.get("reason") or "").lower()
        if "stop_loss" not in reason:
            continue
        d = _trade_date(m, t.get("time") or t.get("timestamp") or t.get("ts"))
        if d == today:
            count += 1
    return count


def _open_positions_count(m: Any) -> int:
    positions = _portfolio(m).get("positions") or {}
    return len(positions) if isinstance(positions, dict) else 0


def _pattern(signal: Dict[str, Any]) -> Dict[str, Any]:
    pat = signal.get("pattern_recognition") or signal.get("pattern_context") or {}
    return pat if isinstance(pat, dict) else {}


def _as_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Iterable):
        out = set()
        for x in value:
            sx = str(x).strip()
            if sx:
                out.add(sx)
        return out
    return set()


def _market_context(m: Any) -> Dict[str, Any]:
    try:
        lm = _portfolio(m).get("last_market")
        if isinstance(lm, dict):
            return lm
    except Exception:
        pass
    try:
        fn = getattr(m, "market_status", None)
        if callable(fn):
            maybe = fn(force=False)
            if isinstance(maybe, dict):
                return maybe
    except Exception:
        pass
    return {}


def _loss_state(m: Any) -> Dict[str, Any]:
    rp = _realized_snapshot(m)
    losses_today = int(_safe_float(rp.get("losses_today"), 0))
    realized_today = _safe_float(rp.get("today"), 0.0)
    stop_losses_today = _stop_losses_today(m)
    open_positions = _open_positions_count(m)

    level = "clear"
    reasons: List[str] = []
    if losses_today >= HARD_BLOCK_LOSSES_TODAY:
        level = "hard_block"
        reasons.append(f"losses_today>={HARD_BLOCK_LOSSES_TODAY}")
    if stop_losses_today >= HARD_BLOCK_STOP_LOSSES_TODAY:
        level = "hard_block"
        reasons.append(f"stop_losses_today>={HARD_BLOCK_STOP_LOSSES_TODAY}")
    if level != "hard_block":
        if losses_today >= CAUTION_LOSSES_TODAY:
            level = "caution"
            reasons.append(f"losses_today>={CAUTION_LOSSES_TODAY}")
        if stop_losses_today >= CAUTION_STOP_LOSSES_TODAY:
            level = "caution"
            reasons.append(f"stop_losses_today>={CAUTION_STOP_LOSSES_TODAY}")

    return {
        "level": level,
        "reasons": reasons,
        "losses_today": losses_today,
        "stop_losses_today": stop_losses_today,
        "realized_today": round(realized_today, 2),
        "open_positions": open_positions,
    }


def _pattern_veto(signal: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    if not PATTERN_RISK_VETO_ENABLED:
        return True, [], {"enabled": False}
    pat = _pattern(signal)
    risk_patterns = _as_set(pat.get("risk_patterns"))
    detected = _as_set(pat.get("patterns_detected"))
    bias = str(pat.get("pattern_bias") or "")
    score = _safe_float(signal.get("score"), 0.0)
    chase_hit = bool(risk_patterns.intersection(CHASE_RISK_NAMES))

    details = {
        "enabled": True,
        "pattern_bias": bias,
        "risk_patterns": sorted(risk_patterns),
        "patterns_detected": sorted(detected),
        "score": round(score, 6),
        "chase_hit": chase_hit,
    }
    if not chase_hit:
        return True, [], details

    exceptional_clean_retest = (
        ALLOW_EXCEPTIONAL_CLEAN_RETEST
        and score >= CHASE_RISK_EXCEPTIONAL_SCORE
        and bool(detected.intersection(RETEST_OR_RECLAIM_PATTERNS))
        and bias not in MIXED_PATTERN_BIASES
    )
    details["exceptional_clean_retest"] = bool(exceptional_clean_retest)
    details["required_exceptional_score"] = CHASE_RISK_EXCEPTIONAL_SCORE

    if exceptional_clean_retest:
        return True, [], details
    return False, ["pattern_chase_risk_veto"], details


def _govern_signal(m: Any, signal: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    score = _safe_float(signal.get("score"), 0.0)
    loss = _loss_state(m)
    ok = True
    reasons: List[str] = []

    pattern_ok, pattern_reasons, pattern_details = _pattern_veto(signal)
    if not pattern_ok:
        ok = False
        reasons.extend(pattern_reasons)

    level = loss.get("level")
    if level == "hard_block":
        if loss.get("open_positions", 0) >= MAX_OPEN_POSITIONS_HARD:
            ok = False
            reasons.append("hard_loss_state_max_positions_reached")
        if score < MIN_SCORE_AFTER_HARD_BLOCK:
            ok = False
            reasons.append("hard_loss_state_score_too_low")
        if pattern_details.get("chase_hit"):
            ok = False
            reasons.append("hard_loss_state_blocks_chase_risk")
    elif level == "caution":
        if loss.get("open_positions", 0) >= MAX_OPEN_POSITIONS_CAUTION:
            ok = False
            reasons.append("caution_state_max_positions_reached")
        if score < MIN_SCORE_AFTER_CAUTION:
            ok = False
            reasons.append("caution_state_score_too_low")
        if pattern_details.get("chase_hit"):
            ok = False
            reasons.append("caution_state_blocks_chase_risk")

    decision = {
        "version": VERSION,
        "ok": bool(ok),
        "reasons": sorted(set(reasons)),
        "score": round(score, 6),
        "loss_state": loss,
        "pattern_veto": pattern_details,
        "rules": {
            "min_score_after_caution": MIN_SCORE_AFTER_CAUTION,
            "min_score_after_hard_block": MIN_SCORE_AFTER_HARD_BLOCK,
            "max_open_positions_caution": MAX_OPEN_POSITIONS_CAUTION,
            "max_open_positions_hard": MAX_OPEN_POSITIONS_HARD,
            "chase_risk_exceptional_score": CHASE_RISK_EXCEPTIONAL_SCORE,
        },
    }
    return bool(ok), decision


def status_payload(m: Any) -> Dict[str, Any]:
    loss = _loss_state(m) if m is not None else {"level": "unknown"}
    return {
        "status": "ok",
        "type": "loss_streak_defensive_governor_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "enabled": bool(ENABLED),
        "patched": bool(getattr(m, PATCH_FLAG, False)) if m is not None else False,
        "loss_state": loss,
        "new_entry_policy": {
            "clear": "normal rules plus pattern chase-risk veto",
            "caution": "cap open positions, require stronger score, block chase-risk entries",
            "hard_block": "block most new entries after repeated losses/stop-outs unless later code explicitly disables this module",
        },
        "pattern_risk_veto_enabled": bool(PATTERN_RISK_VETO_ENABLED),
        "filter_scan_signals": bool(FILTER_SCAN_SIGNALS),
        "recommended_operator_action": "If losses continue while market breadth is green, keep this governor active and review pattern/entry timing before expanding exposure.",
    }


def pattern_veto_status_payload(m: Any) -> Dict[str, Any]:
    market = _market_context(m) if m is not None else {}
    rows = []
    try:
        scan = getattr(m, "_loss_gov_original_scan_signals", None) or getattr(m, "scan_signals", None)
        if callable(scan):
            longs, shorts, _rejected = scan(market)
            for sig in list(longs or [])[:30] + list(shorts or [])[:10]:
                if not isinstance(sig, dict):
                    continue
                ok, decision = _govern_signal(m, sig)
                rows.append({
                    "symbol": sig.get("symbol"),
                    "side": sig.get("side", "long"),
                    "score": sig.get("score"),
                    "ok": ok,
                    "reasons": decision.get("reasons", []),
                    "pattern_veto": decision.get("pattern_veto", {}),
                })
    except Exception as exc:
        rows.append({"symbol": "DIAGNOSTIC", "ok": False, "error": str(exc)})
    return {
        "status": "ok",
        "type": "pattern_risk_veto_status",
        "version": VERSION,
        "generated_local": _now_text(),
        "market_mode": market.get("market_mode"),
        "rows": rows,
    }


def apply(m: Any) -> Dict[str, Any]:
    if m is None:
        return {"status": "warn", "version": VERSION, "reason": "missing_core_module"}
    if getattr(m, PATCH_FLAG, False):
        return {"status": "ok", "version": VERSION, "already_applied": True}
    if not ENABLED:
        setattr(m, PATCH_FLAG, True)
        return {"status": "ok", "version": VERSION, "enabled": False}

    patched: List[str] = []

    original_scan = getattr(m, "scan_signals", None)
    if callable(original_scan):
        setattr(m, "_loss_gov_original_scan_signals", original_scan)

        def patched_scan_signals(market: Dict[str, Any]):
            long_signals, short_signals, rejected = original_scan(market)
            if not FILTER_SCAN_SIGNALS:
                return long_signals, short_signals, rejected
            rejected = list(rejected or [])

            def keep_or_reject(sig: Dict[str, Any], side: str) -> bool:
                if not isinstance(sig, dict):
                    return False
                ok, decision = _govern_signal(m, sig)
                sig["loss_streak_governor"] = decision
                if ok:
                    return True
                rejected.append({
                    "symbol": sig.get("symbol"),
                    "side": side,
                    "score": sig.get("score"),
                    "reason": "loss_streak_defensive_governor_block",
                    "governor_reasons": decision.get("reasons", []),
                    "loss_state": decision.get("loss_state", {}),
                    "pattern_veto": decision.get("pattern_veto", {}),
                    "version": VERSION,
                })
                return False

            long_kept = [s for s in list(long_signals or []) if keep_or_reject(s, "long")]
            short_kept = [s for s in list(short_signals or []) if keep_or_reject(s, "short")]
            return long_kept, short_kept, rejected

        m.scan_signals = patched_scan_signals
        patched.append("scan_signals")

    original_entry_quality = getattr(m, "entry_quality_check", None)
    if callable(original_entry_quality):
        setattr(m, "_loss_gov_original_entry_quality_check", original_entry_quality)

        def patched_entry_quality_check(signal: Dict[str, Any], params: Dict[str, Any], market: Dict[str, Any], exclude_symbol: str | None = None):
            ok, info = original_entry_quality(signal, params, market, exclude_symbol=exclude_symbol)
            if not isinstance(signal, dict):
                return ok, info
            gov_ok, decision = _govern_signal(m, signal)
            signal["loss_streak_governor"] = decision
            info = dict(info or {}) if isinstance(info, dict) else {"original_info": info}
            info["loss_streak_governor"] = decision
            if ok and not gov_ok:
                info["blocked_by"] = "loss_streak_defensive_governor"
                info["reason"] = ",".join(decision.get("reasons", [])) or "loss_streak_defensive_governor_block"
                return False, info
            return ok, info

        m.entry_quality_check = patched_entry_quality_check
        patched.append("entry_quality_check")

    original_enter = getattr(m, "enter_position", None)
    if callable(original_enter):
        setattr(m, "_loss_gov_original_enter_position", original_enter)

        def patched_enter_position(signal: Dict[str, Any], params: Dict[str, Any], market_mode: str | None = None):
            if isinstance(signal, dict):
                gov_ok, decision = _govern_signal(m, signal)
                signal["loss_streak_governor"] = decision
                if not gov_ok:
                    try:
                        rejected = (_portfolio(m)).setdefault("blocked_entries", [])
                        if isinstance(rejected, list):
                            rejected.append({
                                "symbol": signal.get("symbol"),
                                "side": signal.get("side", "long"),
                                "score": signal.get("score"),
                                "reason": "enter_position_loss_streak_governor_block",
                                "governor_reasons": decision.get("reasons", []),
                                "time": int(time.time()),
                                "version": VERSION,
                            })
                    except Exception:
                        pass
                    return {"entered": False, "blocked": True, "reason": "loss_streak_defensive_governor", "governor": decision}
            return original_enter(signal, params, market_mode=market_mode)

        m.enter_position = patched_enter_position
        patched.append("enter_position")

    setattr(m, PATCH_FLAG, True)
    return {"status": "ok", "version": VERSION, "enabled": True, "patched": patched}


def _add_self_check_endpoints() -> Dict[str, Any]:
    try:
        import self_check
        light = getattr(self_check, "LIGHT_ENDPOINTS", None)
        if not isinstance(light, list):
            return {"status": "warn", "reason": "LIGHT_ENDPOINTS_missing"}
        added = []
        for path, category, required in (
            ("/paper/loss-streak-governor-status", "governance", False),
            ("/paper/pattern-risk-veto-status", "governance", False),
        ):
            if not any(isinstance(row, dict) and row.get("path") == path for row in light):
                light.append({"path": path, "category": category, "required": required})
                added.append(path)
        return {"status": "ok", "added": added, "count": len(light)}
    except Exception as exc:
        return {"status": "warn", "error": str(exc)}


def register_routes(flask_app: Any, m: Any | None = None) -> Dict[str, Any]:
    if flask_app is None or id(flask_app) in ROUTE_APP_IDS:
        return {"status": "ok", "version": VERSION, "already_registered": True}
    from flask import jsonify

    core = m
    if core is not None:
        apply(core)

    try:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
    except Exception:
        existing = set()

    def _core() -> Any:
        return core

    if "/paper/loss-streak-governor-status" not in existing:
        flask_app.add_url_rule(
            "/paper/loss-streak-governor-status",
            "paper_loss_streak_governor_status",
            lambda: jsonify(status_payload(_core())),
        )
    if "/paper/pattern-risk-veto-status" not in existing:
        flask_app.add_url_rule(
            "/paper/pattern-risk-veto-status",
            "paper_pattern_risk_veto_status",
            lambda: jsonify(pattern_veto_status_payload(_core())),
        )

    ROUTE_APP_IDS.add(id(flask_app))
    return {
        "status": "ok",
        "version": VERSION,
        "registered": True,
        "routes": ["/paper/loss-streak-governor-status", "/paper/pattern-risk-veto-status"],
        "self_check": _add_self_check_endpoints(),
    }
