"""Read-only economic plausibility checks for the cash-only paper ledger.

This module does not repair state or place orders. It exists to prevent a
syntactically complete execution ledger from being treated as trustworthy when
its economics are impossible (for example, a buy larger than available cash or
negative reconstructed cash).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Tuple

VERSION = "paper-ledger-economic-integrity-2026-08-10-v1"
_REGISTERED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def _sym(value: Any) -> str:
    return str(value or "").upper().strip()


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _trade_fields(row: Dict[str, Any]) -> Tuple[str, str, float, float, str]:
    symbol = _sym(row.get("symbol") or row.get("ticker"))
    side = str(row.get("side") or row.get("action") or "").lower().strip()
    if side in {"b", "open_long", "long", "entry"}:
        side = "buy"
    elif side in {"s", "close_long", "exit"}:
        side = "sell"
    qty = _f(row.get("qty", row.get("shares", row.get("quantity"))), 0.0)
    price = _f(row.get("price", row.get("fill_price", row.get("entry_price", row.get("exit_price")))), 0.0)
    timestamp = str(row.get("timestamp") or row.get("time") or row.get("ts_local") or row.get("created_at") or "")
    return symbol, side, qty, price, timestamp


def _baseline_candidates(pf: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key in ("initial_cash", "starting_cash", "starting_equity", "initial_equity"):
        value = _f(pf.get(key), 0.0)
        if value > 0:
            out[key] = value
    history = _l(pf.get("history"))
    if history:
        value = _f(history[0], 0.0)
        if value > 0:
            out["history_first"] = value
    return out


def _initial_cash(pf: Dict[str, Any]) -> float:
    candidates = _baseline_candidates(pf)
    for key in ("initial_cash", "starting_cash", "starting_equity", "initial_equity", "history_first"):
        if candidates.get(key, 0.0) > 0:
            return candidates[key]
    return 10000.0


def status_payload(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}

    pf = _portfolio(core)
    trades = _l(pf.get("trades"))
    baselines = _baseline_candidates(pf)
    initial = _initial_cash(pf)
    cash = initial
    issues: List[Dict[str, Any]] = []
    parsed = 0

    if len(baselines) >= 2:
        vals = list(baselines.values())
        lo, hi = min(vals), max(vals)
        if lo > 0 and (hi - lo) / lo > 0.10:
            issues.append({
                "reason": "baseline_provenance_disagreement",
                "candidates": {key: round(value, 6) for key, value in baselines.items()},
            })

    for index, raw in enumerate(trades):
        if not isinstance(raw, dict):
            continue
        symbol, side, qty, price, timestamp = _trade_fields(raw)
        if not symbol or side not in {"buy", "sell"} or qty <= 0 or price <= 0:
            continue
        parsed += 1
        notional = qty * price
        before = cash
        if side == "buy":
            tolerance = max(2.0, abs(before) * 0.0025)
            if notional > before + tolerance:
                issues.append({
                    "reason": "buy_exceeds_available_cash",
                    "trade_index": index,
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "cash_before": round(before, 6),
                    "buy_notional": round(notional, 6),
                    "overspend": round(notional - before, 6),
                    "source": raw.get("source"),
                    "entry_tag": raw.get("entry_tag"),
                })
            cash -= notional
        else:
            cash += notional

        if cash < -max(2.0, initial * 0.0025):
            issues.append({
                "reason": "negative_cash_after_trade",
                "trade_index": index,
                "symbol": symbol,
                "timestamp": timestamp,
                "cash_after": round(cash, 6),
                "source": raw.get("source"),
                "entry_tag": raw.get("entry_tag"),
            })

    # Deduplicate repeated negative-cash rows while retaining the first offending
    # trade and all distinct overspend/baseline issues.
    compact: List[Dict[str, Any]] = []
    seen_negative = False
    for issue in issues:
        if issue.get("reason") == "negative_cash_after_trade":
            if seen_negative:
                continue
            seen_negative = True
        compact.append(issue)

    economic_ok = parsed > 0 and not compact
    return {
        "status": "ok" if economic_ok else "fail",
        "overall": "pass" if economic_ok else "fail",
        "type": "paper_ledger_economic_integrity_status",
        "version": VERSION,
        "generated_local": _now(core),
        "cash_only_assumption": True,
        "parsed_trade_rows": parsed,
        "baseline_candidates": {key: round(value, 6) for key, value in baselines.items()},
        "selected_initial_cash": round(initial, 6),
        "reconstructed_cash_after_ledger": round(cash, 6),
        "economic_issue_count": len(compact),
        "economic_issues": compact[:20],
        "promotion_evidence_eligible": bool(economic_ok),
        "authority": {
            "reporting_only": True,
            "repairs_state": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def apply(core: Any = None) -> Dict[str, Any]:
    return status_payload(core)


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return {"status": "error", "overall": "fail", "version": VERSION, "reason": "flask_app_missing"}
    if id(flask_app) not in _REGISTERED_APP_IDS:
        from flask import jsonify
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if "/paper/ledger-economic-integrity-status" not in existing:
            flask_app.add_url_rule(
                "/paper/ledger-economic-integrity-status",
                "paper_ledger_economic_integrity_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(id(flask_app))
    return status_payload(core)
