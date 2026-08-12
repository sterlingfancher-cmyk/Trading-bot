"""Canonicalize paper Market Surge Queue executions after the legacy state mutation.

`market_surge_queue_executor` predates the Stable Core execution ledger and still
appends its own entry rows directly to ``state.trades``.  It also creates
positions with ``qty`` / ``entry_price`` aliases only.  This bridge preserves the
queue executor's existing selection, sizing, cash mutation, and risk gates, but
replaces each newly appended queue trade row with the same entry recorded through
``core.record_trade`` so the canonical append-only execution ledger owns the
execution boundary.

Only newly created, narrowly identified queue rows are canonicalized. Existing
persisted rows are not fabricated or rewritten. Position aliases are completed
from their already-recorded qty/entry values without changing economic state.
"""
from __future__ import annotations

import functools
from typing import Any, Dict, List

VERSION = "market-surge-queue-canonical-execution-bridge-2026-08-12-v1"
_APPLIED_CORE_IDS: set[int] = set()


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


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _mark_failure(core: Any, reason: str) -> None:
    pf = _portfolio(core)
    risk = _d(pf.setdefault("risk_controls", {}))
    risk["surge_queue_canonicalization_error"] = str(reason)
    if not bool(risk.get("halted", False)):
        risk["halted"] = True
        risk["halt_reason"] = "market surge queue canonical execution failed"
    pf["risk_controls"] = risk


def _save(core: Any, pf: Dict[str, Any]) -> None:
    save = getattr(core, "save_state", None)
    if not callable(save):
        return
    try:
        save(pf)
    except TypeError:
        save()


def _is_legacy_new_queue_entry(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    return (
        str(row.get("source") or "").strip().lower() == "market_surge_queue_executor"
        and str(row.get("side") or "").strip().lower() in {"buy", "b", "long"}
        and not str(row.get("execution_id") or "").strip()
        and _f(row.get("qty", row.get("shares")), 0.0) > 0.0
        and _f(row.get("price", row.get("entry_price")), 0.0) > 0.0
        and bool(str(row.get("symbol") or "").strip())
    )


def _canonical_extra(row: Dict[str, Any]) -> Dict[str, Any]:
    blocked = {
        "action", "symbol", "side", "price", "fill_price", "entry_price",
        "qty", "shares", "quantity", "execution_id", "accounting_epoch_id",
        "canonical_ledger_event_hash", "canonical_ledger_version",
    }
    extra = {str(k): v for k, v in row.items() if k not in blocked}
    extra["source"] = "market_surge_queue_executor"
    extra["canonical_surge_queue_bridge_version"] = VERSION
    extra["legacy_queue_row_replaced"] = True
    return extra


def _complete_position_aliases(pf: Dict[str, Any], symbol: str, qty: float, price: float) -> None:
    positions = _d(pf.get("positions"))
    pos = _d(positions.get(symbol))
    if not pos:
        return
    if _f(pos.get("shares"), 0.0) <= 0.0 and qty > 0.0:
        pos["shares"] = round(qty, 9)
    if _f(pos.get("qty"), 0.0) <= 0.0 and qty > 0.0:
        pos["qty"] = round(qty, 9)
    if _f(pos.get("entry"), 0.0) <= 0.0 and price > 0.0:
        pos["entry"] = round(price, 6)
    if _f(pos.get("entry_price"), 0.0) <= 0.0 and price > 0.0:
        pos["entry_price"] = round(price, 6)
    pos["canonical_surge_queue_bridge_version"] = VERSION
    positions[symbol] = pos
    pf["positions"] = positions


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    try:
        import market_surge_queue_executor as queue
    except Exception as exc:
        return {"status": "error", "overall": "fail", "version": VERSION, "error": f"{type(exc).__name__}: {exc}"}

    record_trade = getattr(core, "record_trade", None)
    if not callable(record_trade):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "core.record_trade_missing"}

    current = getattr(queue, "execute_surge_queue", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "queue_executor_missing"}
    if getattr(current, "_canonical_surge_queue_bridge_version", None) == VERSION:
        _APPLIED_CORE_IDS.add(id(core))
        return status_payload(core)

    prior = getattr(current, "_canonical_surge_queue_bridge_prior", current)

    @functools.wraps(prior)
    def canonical_execute(runtime_core: Any = None, *, explicit_confirm: bool = False):
        active = runtime_core or core
        pf = _portfolio(active)
        before_trades = _l(pf.get("trades"))
        before_len = len(before_trades)

        result = prior(active, explicit_confirm=explicit_confirm)
        if not isinstance(result, dict) or not bool(result.get("executed")):
            return result

        trades = _l(pf.get("trades"))
        newly_appended = list(trades[before_len:]) if len(trades) >= before_len else []
        targets = [row for row in newly_appended if _is_legacy_new_queue_entry(row)]
        if not targets:
            result["canonical_execution_bridge"] = {"status": "no_legacy_rows", "version": VERSION}
            return result

        # Remove only the newly appended legacy queue rows. Preserve every older
        # row and any unrelated row appended by another component.
        target_ids = {id(row) for row in targets}
        kept_tail = [row for row in newly_appended if id(row) not in target_ids]
        pf["trades"] = list(trades[:before_len]) + kept_tail

        canonicalized: List[str] = []
        try:
            for raw in targets:
                row = _d(raw)
                symbol = str(row.get("symbol") or "").upper().strip()
                qty = _f(row.get("qty", row.get("shares")), 0.0)
                price = _f(row.get("price", row.get("entry_price")), 0.0)
                if not symbol or qty <= 0.0 or price <= 0.0:
                    raise RuntimeError("malformed newly executed surge queue row")
                _complete_position_aliases(pf, symbol, qty, price)
                record_trade("entry", symbol, "long", price, qty, _canonical_extra(row))
                canonicalized.append(symbol)
            _save(active, pf)
        except Exception as exc:
            _mark_failure(active, f"{type(exc).__name__}: {exc}")
            try:
                _save(active, pf)
            except Exception:
                pass
            raise

        result["canonical_execution_bridge"] = {
            "status": "ok",
            "version": VERSION,
            "canonicalized_count": len(canonicalized),
            "canonicalized_symbols": canonicalized,
            "legacy_rows_retained": False,
        }
        return result

    canonical_execute._canonical_surge_queue_bridge_version = VERSION  # type: ignore[attr-defined]
    canonical_execute._canonical_surge_queue_bridge_prior = prior  # type: ignore[attr-defined]
    queue.execute_surge_queue = canonical_execute
    _APPLIED_CORE_IDS.add(id(core))
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    try:
        import market_surge_queue_executor as queue
        hooked = getattr(getattr(queue, "execute_surge_queue", None), "_canonical_surge_queue_bridge_version", None) == VERSION
    except Exception:
        hooked = False
    return {
        "status": "ok" if hooked else "pending",
        "overall": "pass" if hooked else "warn",
        "type": "market_surge_queue_canonical_execution_bridge_status",
        "version": VERSION,
        "hook_applied": bool(hooked),
        "future_queue_entries_use_record_trade": bool(hooked),
        "rewrites_existing_history": False,
        "authority": {
            "paper_execution_integrity_only": True,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_sizing": False,
            "changes_risk_limits": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    return apply(core)
