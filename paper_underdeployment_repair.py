"""Paper-only repair for chronic capital underdeployment.

Approved starter trades are sized to a final 12-18% notional target instead of
multiplying the intended starter allocation by the portfolio allocation again.
The existing quality gates, cooldowns, sector/bucket caps, stop loss, daily-loss
limit, drawdown halt, and execution path remain authoritative.
"""
from __future__ import annotations

import collections
import datetime as dt
import math
import os
import sys
import threading
import time
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "paper-underdeployment-repair-2026-08-03-v1"
ENABLED = os.environ.get("PAPER_UNDERDEPLOYMENT_REPAIR_ENABLED", "true").lower() not in {"0", "false", "no", "off"}
PAPER_ONLY = os.environ.get("PAPER_UNDERDEPLOYMENT_REPAIR_PAPER_ONLY", "true").lower() not in {"0", "false", "no", "off"}
TARGETS = {
    "risk_on": float(os.environ.get("UNDERDEPLOYMENT_RISK_ON_TARGET_PCT", "0.18")),
    "constructive": float(os.environ.get("UNDERDEPLOYMENT_CONSTRUCTIVE_TARGET_PCT", "0.16")),
    "neutral": float(os.environ.get("UNDERDEPLOYMENT_NEUTRAL_TARGET_PCT", "0.15")),
    "late_neutral": float(os.environ.get("UNDERDEPLOYMENT_LATE_NEUTRAL_TARGET_PCT", "0.12")),
}
MAX_COMBINED = float(os.environ.get("UNDERDEPLOYMENT_MAX_COMBINED_EXPOSURE_PCT", "0.36"))
MAX_OPEN = int(os.environ.get("UNDERDEPLOYMENT_MAX_OPEN_POSITIONS", "2"))
MAX_DAILY = int(os.environ.get("UNDERDEPLOYMENT_MAX_STARTER_ENTRIES_PER_DAY", "2"))
MIN_SPACING = int(os.environ.get("UNDERDEPLOYMENT_MIN_SECONDS_BETWEEN_STARTERS", "900"))
MIN_FIRST_PNL = float(os.environ.get("UNDERDEPLOYMENT_SECOND_POSITION_MIN_FIRST_PNL_PCT", "-0.005"))
CASH_RESERVE = float(os.environ.get("UNDERDEPLOYMENT_CASH_RESERVE_PCT", "0.20"))
MAX_TRADE_RISK = float(os.environ.get("UNDERDEPLOYMENT_MAX_TRADE_RISK_PCT", "0.02"))
STARTER_MIN_CASH = float(os.environ.get("UNDERDEPLOYMENT_STARTER_MIN_CASH_PCT", "75.0"))
WARN_MINUTES = int(os.environ.get("UNDERDEPLOYMENT_WARNING_MINUTES", "120"))
WARN_SIGNALS = int(os.environ.get("UNDERDEPLOYMENT_WARNING_MIN_SIGNALS", "20"))
WARN_CASH = float(os.environ.get("UNDERDEPLOYMENT_WARNING_MIN_CASH_PCT", "0.80"))
WARN_DEPLOYED = float(os.environ.get("UNDERDEPLOYMENT_WARNING_MAX_DEPLOYED_PCT", "0.10"))
WATCHDOG_SECONDS = int(os.environ.get("UNDERDEPLOYMENT_WATCHDOG_SECONDS", "10"))
_STARTER = ("core_participation_valve", "risk_on_starter_participation", "neutral_starter", "neutral_momentum_starter")
_LOCK = threading.RLock()
_APPS: set[int] = set()
_WATCHDOGS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _d(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if hasattr(v, "item"):
            v = v.item()
        n = float(v)
        return default if math.isnan(n) or math.isinf(n) else n
    except Exception:
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _mod() -> Any | None:
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and getattr(m, "app", None) is not None and hasattr(m, "portfolio"):
            return m
    return None


def _paper() -> bool:
    if not PAPER_ONLY:
        return True
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker


def _state(c: Any) -> Dict[str, Any]:
    return _d(getattr(c, "portfolio", {}))


def _positions(c: Any) -> Dict[str, Any]:
    return _d(_state(c).get("positions"))


def _now(c: Any = None) -> str:
    try:
        return str(c.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _now_dt(c: Any = None) -> dt.datetime:
    try:
        x = c.now_local()
        if isinstance(x, dt.datetime):
            return x
    except Exception:
        pass
    return dt.datetime.now()


def _section(c: Any) -> Dict[str, Any]:
    s = _state(c).setdefault("paper_underdeployment_repair", {})
    if not isinstance(s, dict):
        s = {}
        _state(c)["paper_underdeployment_repair"] = s
    s["version"] = VERSION
    return s


def _save(c: Any) -> None:
    try:
        if callable(getattr(c, "save_state", None)):
            c.save_state(_state(c))
    except Exception:
        pass


def _market(c: Any) -> Dict[str, Any]:
    s = _state(c)
    out: Dict[str, Any] = {}
    for src in (_d(_d(s.get("auto_runner")).get("last_result")), _d(s.get("last_market"))):
        for k, v in src.items():
            out.setdefault(k, v)
    restart = _d(_d(s.get("feedback_loop")).get("controlled_restart"))
    out.setdefault("market_mode", restart.get("market_mode"))
    return out


def _risk(c: Any) -> Dict[str, Any]:
    s = _state(c)
    r, f = _d(s.get("risk_controls")), _d(s.get("feedback_loop"))
    return {
        "halted": bool(r.get("halted")), "profit_guard": bool(r.get("profit_guard_active")),
        "self_defense": bool(r.get("self_defense_active")), "self_defense_reason": str(r.get("self_defense_reason") or ""),
        "daily_loss": _f(r.get("daily_loss_pct")), "drawdown": _f(r.get("intraday_drawdown_pct")),
        "feedback_block": bool(f.get("block_new_entries") or f.get("hard_halt")),
        "restart": _d(f.get("controlled_restart")),
    }


def _clock(c: Any) -> Dict[str, Any]:
    try:
        return _d(c.market_clock())
    except Exception:
        return {}


def _minutes(c: Any) -> float:
    x = _clock(c)
    if x.get("minutes_since_open") is not None:
        return max(0.0, _f(x.get("minutes_since_open")))
    try:
        now = _now_dt(c)
        return max(0.0, (now - c.regular_open_datetime(now)).total_seconds() / 60.0)
    except Exception:
        return 9999.0


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def _sector(c: Any, symbol: str, row: Dict[str, Any]) -> str:
    return str(row.get("sector") or (getattr(c, "SYMBOL_SECTOR", {}) or {}).get(symbol, "UNKNOWN")).upper().strip()


def _bucket(c: Any, symbol: str, row: Dict[str, Any]) -> str:
    if row.get("bucket") or row.get("symbol_bucket"):
        return str(row.get("bucket") or row.get("symbol_bucket")).lower().strip()
    try:
        return str(c.symbol_bucket(symbol)).lower().strip()
    except Exception:
        return "unknown"


def _is_starter(signal: Any) -> bool:
    if not isinstance(signal, dict):
        return False
    text = " ".join(str(signal.get(k) or "").lower() for k in ("entry_context", "trade_class", "reason"))
    if isinstance(signal.get("core_participation_valve"), dict):
        text += " core_participation_valve"
    return any(token in text for token in _STARTER)


def _position_value(row: Dict[str, Any]) -> float:
    for k in ("market_value", "position_value", "value", "notional", "cost_basis"):
        if abs(_f(row.get(k))) > 0:
            return abs(_f(row.get(k)))
    shares = abs(_f(row.get("shares") or row.get("qty") or row.get("quantity")))
    px = _f(row.get("last_price") or row.get("current_price") or row.get("mark") or row.get("entry"))
    return abs(_f(row.get("margin"), shares * px)) if str(row.get("side") or "long").lower() == "short" else shares * px


def _pnl(row: Dict[str, Any]) -> float | None:
    entry = _f(row.get("entry") or row.get("entry_price") or row.get("avg_price"))
    mark = _f(row.get("last_price") or row.get("current_price") or row.get("mark"))
    if entry > 0 and mark > 0:
        move = mark / entry - 1.0
        return -move if str(row.get("side") or "long").lower() == "short" else move
    return None


def _exposure(c: Any) -> Dict[str, Any]:
    s = _state(c)
    equity = max(_f(s.get("equity"), _f(s.get("cash"))), 0.01)
    cash = max(_f(s.get("cash")), 0.0)
    values = {k: _position_value(_d(v)) for k, v in _positions(c).items()}
    deployed = max(sum(values.values()), max(0.0, equity - cash))
    return {"equity": equity, "cash": cash, "cash_pct": cash / equity, "deployed": deployed,
            "deployed_pct": deployed / equity, "position_values": values, "positions_count": len(values)}


def _parse_time(v: Any) -> dt.datetime | None:
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(v))
        except Exception:
            return None
    text = str(v or "").replace("T", " ").replace("Z", "").split(" CDT")[0].split(" CST")[0]
    for candidate in (text, text[:19]):
        try:
            return dt.datetime.fromisoformat(candidate)
        except Exception:
            pass
    return None


def _latest_entry(c: Any) -> dt.datetime | None:
    found: List[dt.datetime] = []

    def collect(row: Any) -> None:
        if not isinstance(row, dict):
            return
        for k in ("entry_time", "opened_at", "entry_timestamp", "timestamp", "created_at"):
            x = _parse_time(row.get(k))
            if x is not None:
                found.append(x)
                return

    for row in _positions(c).values():
        collect(row)
    for row in list(_state(c).get("trades") or [])[-100:]:
        if isinstance(row, dict) and str(row.get("action") or "").lower() == "entry":
            collect(row)
    return max(found) if found else None


def _scanner_count(c: Any) -> int:
    s = _state(c)
    return max(_i(_d(s.get("scanner_audit")).get("signals_found")), _i(_d(s.get("decision_audit")).get("signals_found")),
               _i(_d(_d(s.get("auto_runner")).get("last_result")).get("signals_found")),
               _i(_d(_d(s.get("auto_runner")).get("last_result")).get("scanner_signals_found")))


def _today(c: Any) -> str:
    try:
        return str(c.today_key())
    except Exception:
        return _now_dt(c).strftime("%Y-%m-%d")


def _starter_entries_today(c: Any) -> int:
    try:
        trades = c.trades_for_date(_today(c)) if callable(getattr(c, "trades_for_date", None)) else _state(c).get("trades") or []
    except Exception:
        trades = _state(c).get("trades") or []
    count = 0
    for row in trades if isinstance(trades, list) else []:
        if not isinstance(row, dict) or str(row.get("action") or "").lower() != "entry":
            continue
        text = " ".join(str(row.get(k) or "").lower() for k in ("entry_context", "trade_class", "reason"))
        if any(token in text for token in _STARTER):
            count += 1
    return count


def _recent_session(c: Any) -> bool:
    a = _d(_state(c).get("auto_runner"))
    x = _parse_time(a.get("last_success") or a.get("last_successful_run_local") or a.get("last_run"))
    if x is None:
        return False
    now = _now_dt(c)
    if getattr(now, "tzinfo", None) is not None and getattr(x, "tzinfo", None) is None:
        x = x.replace(tzinfo=now.tzinfo)
    try:
        return x.date() == now.date() and 0 <= (now - x).total_seconds() <= 5400
    except Exception:
        return False


def underdeployment_status(c: Any) -> Dict[str, Any]:
    e, m, r, clock = _exposure(c), _market(c), _risk(c), _clock(c)
    mode, signals, minutes = str(m.get("market_mode") or m.get("regime") or "").lower(), _scanner_count(c), _minutes(c)
    late_only = r["self_defense"] and "minutes before close" in r["self_defense_reason"].lower()
    clean = not r["halted"] and not r["profit_guard"] and r["daily_loss"] <= 0 and r["drawdown"] <= .50 and (not r["self_defense"] or late_only)
    checks = {
        "session_evidence": bool(clock.get("is_open") or _recent_session(c)),
        "after_observation_window": minutes >= WARN_MINUTES,
        "eligible_market_mode": mode in {"neutral", "constructive", "risk_on"},
        "risk_clean": clean,
        "broad_signal_set": signals >= WARN_SIGNALS,
        "cash_too_high": e["cash_pct"] >= WARN_CASH,
        "deployment_too_low": e["deployed_pct"] < WARN_DEPLOYED,
        "position_count_low": e["positions_count"] <= 1,
    }
    active = all(checks.values())
    return {"active": active, "reason": "healthy_signal_rich_account_materially_underdeployed" if active else "not_active",
            "generated_local": _now(c), "market_mode": mode, "minutes_since_open": round(minutes, 2),
            "signals_found": signals, "cash_pct": round(e["cash_pct"] * 100, 2),
            "deployed_pct": round(e["deployed_pct"] * 100, 2), "open_positions_count": e["positions_count"],
            "late_cutoff_only_self_defense": late_only, "checks": checks}


def _target_pct(c: Any) -> Tuple[float, Dict[str, Any]]:
    m, r, minutes = _market(c), _risk(c), _minutes(c)
    mode = str(m.get("market_mode") or m.get("regime") or "neutral").lower()
    key = "late_neutral" if mode == "neutral" and minutes > 180 else mode if mode in TARGETS else "neutral"
    target, adjustments = TARGETS[key], []
    if str(_d(m.get("futures_bias")).get("action") or "") in {"gap_chase_protection", "reduce_aggression", "tech_caution"}:
        target, adjustments = max(TARGETS["late_neutral"], target * .85), ["futures_caution"]
    if str(_d(m.get("breadth")).get("action") or "") in {"reduce_aggression", "tech_caution"}:
        target, adjustments = max(TARGETS["late_neutral"], target * .90), adjustments + ["breadth_caution"]
    restart = _d(r.get("restart"))
    if restart.get("active"):
        factor = max(.05, min(1.0, _f(restart.get("alloc_factor"), .5)))
        target, adjustments = target * factor, adjustments + ["controlled_restart"]
    return target, {"market_mode": mode, "minutes_since_open": round(minutes, 2), "adjustments": adjustments}


def _gate(c: Any, signal: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    positions, r, symbol = _positions(c), _risk(c), _symbol(signal)
    entries_today = _starter_entries_today(c)
    base = {"symbol": symbol, "open_positions_count": len(positions), "maximum_open_positions": MAX_OPEN,
            "starter_entries_today": entries_today, "maximum_starter_entries_per_day": MAX_DAILY}
    if r["halted"] or r["profit_guard"] or r["feedback_block"]:
        return False, {**base, "reason": "existing_risk_or_profit_guard_blocks"}
    if entries_today >= MAX_DAILY:
        return False, {**base, "reason": "underdeployment_daily_starter_limit"}
    if len(positions) >= MAX_OPEN:
        return False, {**base, "reason": "underdeployment_two_position_limit"}
    latest = _latest_entry(c)
    if positions and latest is not None:
        now = _now_dt(c)
        if getattr(now, "tzinfo", None) is not None and getattr(latest, "tzinfo", None) is None:
            latest = latest.replace(tzinfo=now.tzinfo)
        age = max(0.0, (now - latest).total_seconds())
        if age < MIN_SPACING:
            return False, {**base, "reason": "second_starter_spacing_not_met", "seconds_since_last_entry": round(age, 1)}
    sector, bucket = _sector(c, symbol, signal), _bucket(c, symbol, signal)
    sectors, buckets, first = set(), set(), []
    for sym, raw in positions.items():
        row = _d(raw); sectors.add(_sector(c, str(sym).upper(), row)); buckets.add(_bucket(c, str(sym).upper(), row))
        pnl = _pnl(row); first.append({"symbol": str(sym).upper(), "pnl_pct": None if pnl is None else round(pnl * 100, 4)})
        if pnl is not None and pnl < MIN_FIRST_PNL:
            return False, {**base, "reason": "first_position_materially_losing", "first_positions": first}
    if positions and sector in sectors and bucket in buckets:
        return False, {**base, "reason": "second_starter_not_diversified", "candidate_sector": sector, "candidate_bucket": bucket}
    return True, {**base, "reason": "starter_gate_allowed", "candidate_sector": sector, "candidate_bucket": bucket, "first_positions": first}


def _size(c: Any, signal: Dict[str, Any], params: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    e, target_info = _exposure(c), _target_pct(c)
    pct, info = target_info
    stop = abs(_f(params.get("stop_loss"), .012)) or .012
    requested = e["equity"] * pct
    risk_cap = e["equity"] * MAX_TRADE_RISK / max(stop, .0001)
    cash_cap = max(0.0, e["cash"] - e["equity"] * CASH_RESERVE)
    combined_remaining = max(0.0, e["equity"] * MAX_COMBINED - e["deployed"])
    target = min(requested, risk_cap, cash_cap, combined_remaining, e["cash"])
    try:
        bucket_factor = max(.05, _f(c.bucket_alloc_factor(_symbol(signal)), 1.0))
    except Exception:
        bucket_factor = 1.0
    audit = {"version": VERSION, "sizing_model": "absolute_final_notional_target", "symbol": _symbol(signal),
             "target_context": info, "equity": round(e["equity"], 2), "cash": round(e["cash"], 2),
             "current_deployed_pct": round(e["deployed_pct"] * 100, 2), "intended_target_pct": round(pct * 100, 4),
             "intended_target_notional": round(requested, 2), "original_long_alloc_pct": round(_f(params.get("long_alloc_pct")) * 100, 4),
             "original_signal_alloc_factor": round(_f(signal.get("alloc_factor"), 1.0), 6), "bucket_alloc_factor": round(bucket_factor, 6),
             "configured_stop_loss_pct": round(stop * 100, 4), "maximum_trade_risk_pct": round(MAX_TRADE_RISK * 100, 4),
             "risk_cap_notional": round(risk_cap, 2), "cash_cap_notional": round(cash_cap, 2),
             "combined_exposure_remaining": round(combined_remaining, 2), "final_target_notional": round(target, 2),
             "final_target_pct": round(target / e["equity"] * 100, 4), "estimated_loss_at_stop": round(target * stop, 2),
             "allocation_factor_compounding_removed": True}
    return target, audit


def _exposure_gate(c: Any, signal: Dict[str, Any], target: float) -> Tuple[bool, Dict[str, Any]]:
    symbol, sector, bucket, equity = _symbol(signal), _sector(c, _symbol(signal), signal), _bucket(c, _symbol(signal), signal), _exposure(c)["equity"]
    try:
        _, values, counts = c.portfolio_sector_stats(); values, counts = _d(values), _d(counts)
        cap = _f(c.effective_sector_exposure_cap(_market(c), sector), 1.0)
        limit = _i(c.effective_max_positions_per_sector(_market(c), sector), 99)
        if _i(counts.get(sector)) >= limit:
            return False, {"reason": "target_sector_position_limit", "sector": sector}
        if (_f(values.get(sector)) + target) / equity > cap:
            return False, {"reason": "target_sector_exposure_cap", "sector": sector}
    except Exception:
        pass
    try:
        _, values, counts = c.portfolio_bucket_stats(); values, counts, cfg = _d(values), _d(counts), _d(c.bucket_config(bucket))
        if _i(counts.get(bucket)) >= _i(cfg.get("max_positions"), 99):
            return False, {"reason": "target_bucket_position_limit", "bucket": bucket}
        if (_f(values.get(bucket)) + target) / equity > _f(cfg.get("max_exposure_pct"), 1.0):
            return False, {"reason": "target_bucket_exposure_cap", "bucket": bucket}
    except Exception:
        pass
    return True, {"reason": "target_exposure_checks_passed", "symbol": symbol, "sector": sector, "bucket": bucket}


def _persist_size(c: Any, audit: Dict[str, Any], result: Dict[str, Any]) -> None:
    row = dict(audit); row["generated_local"] = _now(c)
    executed = _f(result.get("alloc")); target = _f(row.get("final_target_notional")); equity = max(_f(row.get("equity")), .01)
    row.update({"executed_notional": round(executed, 2), "executed_pct": round(executed / equity * 100, 4),
                "execution_shortfall": round(max(0.0, target - executed), 2), "blocked": bool(result.get("blocked")),
                "execution_reason": result.get("reason")})
    s = _section(c); s["last_sizing_audit"] = row
    recent = s.get("recent_sizing_audits") if isinstance(s.get("recent_sizing_audits"), list) else []
    recent.append(row); s["recent_sizing_audits"] = recent[-30:]; _save(c)


def _linked(fn: Any) -> Iterable[Any]:
    out = []
    for attr in ("_paper_underdeployment_prior", "_paper_participation_original", "__wrapped__"):
        x = getattr(fn, attr, None)
        if callable(x): out.append(x)
    return out


def _has(fn: Any, attr: str) -> bool:
    q, seen = [fn], set()
    while q and len(seen) < 32:
        x = q.pop(0)
        if not callable(x) or id(x) in seen: continue
        seen.add(id(x))
        if getattr(x, attr, None) == VERSION: return True
        q.extend(_linked(x))
    return False


def _patch_enter(c: Any) -> bool:
    current = getattr(c, "enter_position", None)
    if not callable(current) or _has(current, "_paper_underdeployment_version"):
        return False
    prior = current
    def enter(signal: Dict[str, Any], params: Dict[str, Any], market_mode: Any = None, __prior=prior):
        if not ENABLED or not _paper() or not _is_starter(signal) or _d(_risk(c).get("restart")).get("active"):
            return __prior(signal, params, market_mode=market_mode)
        sig, par = dict(signal or {}), dict(params or {})
        ok, gate = _gate(c, sig)
        if not ok:
            result = {"symbol": _symbol(sig), "side": sig.get("side", "long"), "blocked": True, "reason": gate["reason"], "paper_underdeployment_repair": gate}
            _persist_size(c, {"version": VERSION, "equity": _exposure(c)["equity"], "final_target_notional": 0, "gate": gate}, result); return result
        target, audit = _size(c, sig, par)
        ok, exposure_gate = _exposure_gate(c, sig, target)
        if target <= 0 or not ok:
            reason = "no_safe_target_capacity" if target <= 0 else exposure_gate["reason"]
            result = {"symbol": _symbol(sig), "side": sig.get("side", "long"), "blocked": True, "reason": reason, "paper_underdeployment_repair": {"gate": gate, "sizing": audit, "exposure_gate": exposure_gate}}
            _persist_size(c, {**audit, "gate": gate, "exposure_gate": exposure_gate}, result); return result
        equity, bucket_factor = max(_f(audit.get("equity")), .01), max(_f(audit.get("bucket_alloc_factor")), .05)
        sig["underdeployment_original_alloc_factor"] = sig.get("alloc_factor"); sig["alloc_factor"] = 1.0
        sig["paper_underdeployment_target_notional"] = round(target, 2); sig["paper_underdeployment_repair_version"] = VERSION
        par["long_alloc_pct"] = target / (equity * bucket_factor)
        result = __prior(sig, par, market_mode=market_mode)
        if isinstance(result, dict):
            result["paper_underdeployment_repair"] = {**audit, "gate": gate, "exposure_gate": exposure_gate}
            symbol = result.get("symbol") or _symbol(sig); pos = _d(_positions(c).get(symbol))
            if pos: pos["allocation_model"] = "paper_underdeployment_absolute_target"; pos["paper_underdeployment_repair"] = result["paper_underdeployment_repair"]
            trades = _state(c).get("trades") or []
            if isinstance(trades, list) and trades and isinstance(trades[-1], dict) and trades[-1].get("action") == "entry":
                trades[-1]["allocation_model"] = "paper_underdeployment_absolute_target"; trades[-1]["paper_underdeployment_repair"] = result["paper_underdeployment_repair"]
            _persist_size(c, result["paper_underdeployment_repair"], result)
        return result
    enter._paper_underdeployment_version = VERSION; enter._paper_underdeployment_prior = prior
    enter._paper_participation_patched = True; enter._paper_participation_original = getattr(prior, "_paper_participation_original", prior); enter.__wrapped__ = prior
    c.enter_position = enter; return True


def _flatten(row: Any) -> Dict[str, Any]:
    row = row if isinstance(row, dict) else {"reason": str(row)}; q, v, u = _d(row.get("quality_info")), _d(row.get("participation_valve")), _d(row.get("paper_underdeployment_repair"))
    outer = str(row.get("reason") or "")
    nested = u.get("reason") or q.get("reason") or v.get("reason")
    reason = nested if nested and outer in {"entry_quality_block", "participation_valve_enter_position_returned_empty", "enter_position_returned_empty"} else outer or nested or "unknown"
    return {"symbol": row.get("symbol"), "side": row.get("side"), "score": row.get("score"),
            "rank_score": row.get("rank_score") or row.get("core_entry_rank_score"), "final_reason": reason,
            "outer_reason": outer or None, "quality_reason": q.get("reason"), "participation_reason": v.get("reason")}


def _patch_cycle(c: Any) -> bool:
    try: import core_entry_pipeline as p
    except Exception: return False
    current = getattr(p, "_core_try_entries_and_rotations", None)
    if not callable(current) or getattr(current, "_paper_underdeployment_cycle_version", None) == VERSION: return False
    prior = current
    def cycle(runtime: Any, longs: Any, shorts: Any, params: Any, market: Any, new_entries_allowed: bool = True, entry_block_reason: Any = None, __prior=prior):
        result = __prior(runtime, longs, shorts, params, market, new_entries_allowed=new_entries_allowed, entry_block_reason=entry_block_reason)
        try:
            entries, rotations, blocked = (list(result) + [[], [], []])[:3] if isinstance(result, tuple) else ([], [], [])
            flat = [_flatten(x) for x in (blocked if isinstance(blocked, list) else [])[:30]]
            counts = collections.Counter(str(x.get("final_reason") or "unknown") for x in flat)
            candidates = [{"symbol": _symbol(x), "side": x.get("side", "long"), "score": x.get("score"), "rank_score": x.get("core_entry_rank_score") or x.get("rank_score")} for x in list(longs or []) + list(shorts or []) if isinstance(x, dict)]
            candidates.sort(key=lambda x: _f(x.get("rank_score"), _f(x.get("score"))), reverse=True)
            row = {"generated_local": _now(runtime), "market_mode": _d(market).get("market_mode"), "candidate_count": len(candidates),
                   "entries_count": len(entries) if isinstance(entries, list) else 0, "rotations_count": len(rotations) if isinstance(rotations, list) else 0,
                   "blocked_count": len(blocked) if isinstance(blocked, list) else 0, "top_candidates": candidates[:15],
                   "top_rejected_candidates": flat[:15], "rejection_reason_counts": dict(counts.most_common(15)),
                   "underdeployment_warning": underdeployment_status(runtime)}
            _section(runtime)["last_candidate_cycle"] = row
            if row["underdeployment_warning"]["active"]: _section(runtime)["last_underdeployment_warning"] = row["underdeployment_warning"]
            _save(runtime)
        except Exception as exc: _section(runtime)["last_cycle_audit_error"] = f"{type(exc).__name__}: {exc}"
        return result
    cycle._paper_underdeployment_cycle_version = VERSION; cycle.__wrapped__ = prior; p._core_try_entries_and_rotations = cycle; return True


def _patch_starter_policy() -> Dict[str, Any]:
    try:
        import risk_on_starter_participation_valve as s
        before = _f(getattr(s, "MIN_CASH_PCT", 85), 85); s.MIN_CASH_PCT = min(before, STARTER_MIN_CASH)
        s.MAX_ENTRIES_PER_DAY = max(_i(getattr(s, "MAX_ENTRIES_PER_DAY", 1), 1), MAX_DAILY); s.MAX_OPEN_POSITIONS = MAX_OPEN
        return {"minimum_cash_pct_before": before, "minimum_cash_pct_after": s.MIN_CASH_PCT, "maximum_entries_per_day": s.MAX_ENTRIES_PER_DAY, "maximum_open_positions": s.MAX_OPEN_POSITIONS}
    except Exception as exc: return {"error": f"{type(exc).__name__}: {exc}"}


def _patch_self_check(c: Any) -> Dict[str, bool]:
    changed = {"components": False, "payload": False}
    try: import fast_self_check_override as sc
    except Exception: return changed
    current = getattr(sc, "_component_checks", None)
    if callable(current) and getattr(current, "_paper_underdeployment_version", None) != VERSION:
        prior = current
        def components(runtime: Any, __prior=prior):
            out = dict(__prior(runtime)); row = status_payload(runtime, install_first=False); w = _d(row.get("underdeployment_warning"))
            out["underdeployment_participation"] = {"name": "underdeployment_participation", "overall": "warn" if w.get("active") or not row.get("active") else "pass",
                "version": VERSION, "active": row.get("active"), "warning_active": w.get("active"), "warning_reason": w.get("reason"),
                "cash_pct": w.get("cash_pct"), "deployed_pct": w.get("deployed_pct"), "signals_found": w.get("signals_found"),
                "open_positions_count": w.get("open_positions_count"), "sizing_model": "absolute_final_notional_target",
                "starter_target_range_pct": [12.0, 18.0], "maximum_combined_exposure_pct": round(MAX_COMBINED * 100, 2),
                "last_sizing_audit": _d(row.get("telemetry")).get("last_sizing_audit"), "last_candidate_cycle": _d(row.get("telemetry")).get("last_candidate_cycle")}
            return out
        components._paper_underdeployment_version = VERSION
        neutral_version = getattr(prior, "_neutral_late_session_version", None)
        if neutral_version:
            components._neutral_late_session_version = neutral_version
            components._neutral_late_session_prior = getattr(prior, "_neutral_late_session_prior", prior)
        components.__wrapped__ = prior; sc._component_checks = components; changed["components"] = True
    current = getattr(sc, "build_payload", None)
    if callable(current) and getattr(current, "_paper_underdeployment_version", None) != VERSION:
        prior = current
        def payload(runtime: Any = None, __prior=prior):
            out = __prior(runtime)
            if isinstance(out, dict):
                a = out.setdefault("authority", {}); a.update({"changes_risk_or_sizing": True, "changes_thresholds": True,
                    "changes_paper_sizing": True, "changes_paper_participation_thresholds": True,
                    "changes_global_signal_thresholds": False, "changes_hard_risk_limits": False,
                    "changes_live_authority": False, "changes_ml_authority": False, "places_orders": False,
                    "trading_authority_unchanged": True, "paper_underdeployment_repair_version": VERSION})
                out.setdefault("links", {})["underdeployment_participation"] = "/paper/underdeployment-participation-status"
            return out
        payload._paper_underdeployment_version = VERSION; payload.__wrapped__ = prior; sc.build_payload = payload; changed["payload"] = True
    return changed


def install(c: Any = None) -> Dict[str, Any]:
    global _LAST
    c = c or _mod()
    if c is None: return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "core_missing"}
    with _LOCK:
        policy = _patch_starter_policy(); enter_changed = _patch_enter(c); cycle_changed = _patch_cycle(c); self_changed = _patch_self_check(c)
        enter_active = _has(getattr(c, "enter_position", None), "_paper_underdeployment_version")
        try:
            import core_entry_pipeline as p; cycle_active = getattr(getattr(p, "_core_try_entries_and_rotations", None), "_paper_underdeployment_cycle_version", None) == VERSION
        except Exception: cycle_active = False
        try:
            import fast_self_check_override as sc; self_active = getattr(getattr(sc, "_component_checks", None), "_paper_underdeployment_version", None) == VERSION
        except Exception: self_active = False
        active = bool(ENABLED and _paper() and enter_active and cycle_active and self_active)
        _LAST = {"status": "ok" if active else "warn", "overall": "pass" if active else "warn", "version": VERSION,
                 "generated_local": _now(c), "active": active, "enter_wrapper_active": enter_active,
                 "cycle_audit_active": cycle_active, "self_check_patch_active": self_active, "starter_policy": policy,
                 "patched_this_call": {"enter_position": enter_changed, "candidate_cycle": cycle_changed, **self_changed}}
        setattr(c, "PAPER_UNDERDEPLOYMENT_REPAIR_VERSION", VERSION); _section(c)["last_install"] = dict(_LAST); _save(c); return dict(_LAST)


def status_payload(c: Any = None, install_first: bool = True) -> Dict[str, Any]:
    c = c or _mod()
    if c is None: return {"status": "pending", "overall": "pending", "version": VERSION, "reason": "core_missing"}
    base = install(c) if install_first else dict(_LAST); w = underdeployment_status(c); s = _section(c); s["underdeployment_warning"] = w
    e = _exposure(c)
    return {**base, "type": "paper_underdeployment_repair_status", "underdeployment_warning": w,
            "exposure": {"equity": round(e["equity"], 2), "cash": round(e["cash"], 2), "cash_pct": round(e["cash_pct"] * 100, 2),
                         "deployed": round(e["deployed"], 2), "deployed_pct": round(e["deployed_pct"] * 100, 2), "positions_count": e["positions_count"]},
            "telemetry": {"last_sizing_audit": s.get("last_sizing_audit"), "recent_sizing_audits": s.get("recent_sizing_audits") or [],
                          "last_candidate_cycle": s.get("last_candidate_cycle"), "last_underdeployment_warning": s.get("last_underdeployment_warning"),
                          "last_cycle_audit_error": s.get("last_cycle_audit_error")},
            "settings": {"risk_on_target_pct": TARGETS["risk_on"] * 100, "constructive_target_pct": TARGETS["constructive"] * 100,
                         "neutral_target_pct": TARGETS["neutral"] * 100, "late_neutral_target_pct": TARGETS["late_neutral"] * 100,
                         "maximum_combined_exposure_pct": MAX_COMBINED * 100, "maximum_open_positions": MAX_OPEN,
                         "maximum_starter_entries_per_day": MAX_DAILY, "minimum_seconds_between_starters": MIN_SPACING, "maximum_trade_risk_pct": MAX_TRADE_RISK * 100,
                         "starter_minimum_cash_pct": STARTER_MIN_CASH, "cash_reserve_pct": CASH_RESERVE * 100},
            "authority": {"paper_only": True, "changes_paper_sizing": True, "changes_paper_participation_thresholds": True,
                          "changes_global_signal_thresholds": False, "changes_hard_risk_limits": False, "places_orders_directly": False,
                          "changes_live_authority": False, "changes_ml_authority": False, "preserves_existing_entry_quality_checks": True,
                          "preserves_cooldowns": True, "preserves_sector_and_bucket_caps": True}}


def register_routes(flask_app: Any, c: Any = None) -> Dict[str, Any]:
    if flask_app is None: return {"status": "pending", "version": VERSION, "reason": "flask_app_missing"}
    c = c or _mod(); install(c)
    if id(flask_app) not in _APPS:
        from flask import jsonify
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if "/paper/underdeployment-participation-status" not in existing:
            flask_app.add_url_rule("/paper/underdeployment-participation-status", "underdeployment_participation_status", lambda: jsonify(status_payload(c or _mod())))
        _APPS.add(id(flask_app))
    return status_payload(c, install_first=False)


def start_watchdog(c: Any = None) -> Dict[str, Any]:
    c = c or _mod()
    if c is None: return {"status": "pending", "version": VERSION, "reason": "core_missing"}
    install(c)
    if id(c) not in _WATCHDOGS:
        _WATCHDOGS.add(id(c))
        def worker():
            while True:
                try: install(c)
                except Exception as exc: _section(c)["watchdog_error"] = f"{type(exc).__name__}: {exc}"
                time.sleep(max(5, WATCHDOG_SECONDS))
        threading.Thread(target=worker, name="paper-underdeployment-repair", daemon=True).start()
    return status_payload(c, install_first=False)


try: install(_mod())
except Exception: pass
