"""Action-first paper trade semantics and controlled accounting recovery.

The runtime's canonical trade rows contain both ``action`` (entry/exit/partial_exit)
and ``side`` (long/short). The accounting incident occurred because reconciliation
read ``side`` first, causing long exits to be interpreted as additional buys.

This overlay makes ``action`` authoritative. Historical recovery behavior remains
available for the contaminated pre-epoch state, but once a deliberate clean
accounting epoch exists it installs semantics only and does not create another
historical-recovery snapshot or replay reconciliation.
"""
from __future__ import annotations

import copy
import datetime as dt
from typing import Any, Dict, Tuple

VERSION = "paper-trade-action-semantics-recovery-2026-08-10-v2-clean-epoch"
_REGISTERED_APP_IDS: set[int] = set()
_APPLIED = False


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


def _clean_epoch(core: Any) -> Dict[str, Any]:
    pf = _portfolio(core)
    row = pf.get("paper_accounting_epoch")
    return row if isinstance(row, dict) and row.get("clean_start") else {}


def action_first_trade_fields(row: Dict[str, Any]) -> Tuple[str, str, float, float, str]:
    """Return symbol, economic event, qty, price, timestamp.

    ``action`` is authoritative when present. Long entry/exit rows map to buy/sell.
    Short lifecycle rows are deliberately returned as unsupported event types so
    the legacy long-lot reconciler cannot silently mis-reconstruct them.
    Direct legacy rows that use side=buy/sell without action remain supported.
    """
    symbol = _sym(row.get("symbol") or row.get("ticker"))
    action = str(row.get("action") or "").lower().strip()
    direction = str(row.get("side") or "").lower().strip()
    qty = _f(row.get("qty", row.get("shares", row.get("quantity"))), 0.0)
    price = _f(row.get("price", row.get("fill_price", row.get("entry_price", row.get("exit_price")))), 0.0)
    timestamp = str(row.get("timestamp") or row.get("time") or row.get("ts_local") or row.get("created_at") or "")

    entry_actions = {"entry", "buy", "open", "open_long", "b"}
    exit_actions = {"exit", "partial_exit", "sell", "close", "close_long", "s"}

    if action in entry_actions:
        event = "unsupported_short_entry" if direction == "short" else "buy"
    elif action in exit_actions:
        event = "unsupported_short_exit" if direction == "short" else "sell"
    elif direction in {"buy", "b"}:
        event = "buy"
    elif direction in {"sell", "s"}:
        event = "sell"
    elif direction in {"long", "entry", "open_long"}:
        event = "buy"
    elif direction == "short":
        event = "unsupported_short_entry"
    else:
        event = action or direction

    return symbol, event, qty, price, timestamp


def _install_action_semantics() -> Dict[str, Any]:
    try:
        import paper_accounting_integrity_guard as accounting
        import paper_ledger_economic_integrity as economics
        accounting._trade_fields = action_first_trade_fields
        economics._trade_fields = action_first_trade_fields
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _archive_before_repair(core: Any) -> Dict[str, Any]:
    pf = _portfolio(core)
    existing = pf.get("paper_accounting_semantics_recovery")
    if isinstance(existing, dict) and existing.get("version") == VERSION:
        return existing

    trades = pf.get("trades") if isinstance(pf.get("trades"), list) else []
    snapshot = {
        "version": VERSION,
        "recovery_started_local": _now(core),
        "pre_repair": {
            "cash": pf.get("cash"),
            "equity": pf.get("equity"),
            "positions": copy.deepcopy(pf.get("positions") if isinstance(pf.get("positions"), dict) else {}),
            "realized_pnl": copy.deepcopy(pf.get("realized_pnl") if isinstance(pf.get("realized_pnl"), dict) else {}),
            "performance": copy.deepcopy(pf.get("performance") if isinstance(pf.get("performance"), dict) else {}),
            "risk_controls": copy.deepcopy(pf.get("risk_controls") if isinstance(pf.get("risk_controls"), dict) else {}),
            "trade_count": len(trades),
            "trades": copy.deepcopy(trades),
        },
        "hard_halt_preserved": bool((pf.get("risk_controls") or {}).get("halted", False)) if isinstance(pf.get("risk_controls"), dict) else False,
        "recovery_epoch_valid_path_rows_baseline": 0,
        "post_recovery_validation_required": True,
    }
    pf["paper_accounting_semantics_recovery"] = snapshot
    return snapshot


def _current_valid_path_rows() -> int:
    try:
        import intratrade_path_capture as path
        status = path.status_payload() if callable(getattr(path, "status_payload", None)) else {}
        return int((status or {}).get("training_eligible_rows") or 0)
    except Exception:
        return 0


def apply(core: Any = None) -> Dict[str, Any]:
    global _APPLIED
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}

    semantics = _install_action_semantics()
    if semantics.get("status") != "ok":
        return {"status": "error", "overall": "fail", "version": VERSION, "error": semantics.get("error")}

    clean = _clean_epoch(core)
    if clean:
        _APPLIED = True
        return status_payload(core)

    archive = _archive_before_repair(core)

    if int(archive.get("recovery_epoch_valid_path_rows_baseline") or 0) <= 0:
        archive["recovery_epoch_valid_path_rows_baseline"] = _current_valid_path_rows()

    before_halt = bool((_portfolio(core).get("risk_controls") or {}).get("halted", False)) if isinstance(_portfolio(core).get("risk_controls"), dict) else False
    try:
        import paper_accounting_integrity_guard as accounting
        result = accounting.reconcile(core, persist=True)
    except Exception as exc:
        result = {"status": "error", "overall": "fail", "error": f"{type(exc).__name__}: {exc}"}

    pf = _portfolio(core)
    risk = pf.get("risk_controls") if isinstance(pf.get("risk_controls"), dict) else {}
    after_halt = bool(risk.get("halted", False))
    archive["recovery_applied_local"] = _now(core)
    archive["hard_halt_before"] = before_halt
    archive["hard_halt_after"] = after_halt
    archive["hard_halt_preserved"] = (not before_halt) or after_halt
    archive["post_repair"] = {
        "cash": pf.get("cash"),
        "equity": pf.get("equity"),
        "open_positions_count": len(pf.get("positions") or {}) if isinstance(pf.get("positions"), dict) else 0,
        "reconcile_status": copy.deepcopy(result),
    }

    try:
        save = getattr(core, "save_state", None)
        if callable(save):
            try:
                save(pf)
            except TypeError:
                save()
    except Exception:
        pass

    _APPLIED = True
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    pf = _portfolio(core) if core is not None else {}
    clean = _clean_epoch(core) if core is not None else {}
    row = pf.get("paper_accounting_semantics_recovery") if isinstance(pf.get("paper_accounting_semantics_recovery"), dict) else {}
    if clean:
        return {
            "status": "ok" if _APPLIED else "pending",
            "overall": "pass" if _APPLIED else "warn",
            "type": "paper_trade_action_semantics_recovery_status",
            "version": VERSION,
            "applied": _APPLIED,
            "mode": "clean_epoch_semantics_only",
            "clean_epoch_id": clean.get("id"),
            "historical_recovery_replayed": False,
            "post_recovery_validation_required": bool(clean.get("forward_validation_required", True)),
            "hard_halt_preserved": bool((pf.get("risk_controls") or {}).get("halted", False)) if isinstance(pf.get("risk_controls"), dict) else True,
            "pre_repair_trade_count": 0,
            "post_repair": {},
            "authority": {
                "paper_state_reconciliation_only": True,
                "places_orders": False,
                "clears_hard_halt": False,
                "changes_strategy": False,
                "changes_thresholds": False,
                "changes_risk_or_sizing": False,
                "changes_live_or_ml_authority": False,
            },
        }
    return {
        "status": "ok" if _APPLIED and row else "pending",
        "overall": "pass" if _APPLIED and row and row.get("hard_halt_preserved", True) else "warn",
        "type": "paper_trade_action_semantics_recovery_status",
        "version": VERSION,
        "applied": _APPLIED,
        "mode": "historical_recovery",
        "recovery_epoch_valid_path_rows_baseline": int(row.get("recovery_epoch_valid_path_rows_baseline") or 0),
        "post_recovery_validation_required": bool(row.get("post_recovery_validation_required", True)),
        "hard_halt_preserved": bool(row.get("hard_halt_preserved", True)),
        "pre_repair_trade_count": int(((row.get("pre_repair") or {}).get("trade_count")) or 0) if isinstance(row, dict) else 0,
        "post_repair": copy.deepcopy(row.get("post_repair") or {}) if isinstance(row, dict) else {},
        "authority": {
            "paper_state_reconciliation_only": True,
            "places_orders": False,
            "clears_hard_halt": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    if flask_app is None:
        return apply(core)
    from flask import jsonify
    if id(flask_app) not in _REGISTERED_APP_IDS:
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        path = "/paper/accounting-semantics-recovery-status"
        if path not in existing:
            flask_app.add_url_rule(path, "paper_accounting_semantics_recovery_status", lambda: jsonify(status_payload(core)))
        _REGISTERED_APP_IDS.add(id(flask_app))
    return apply(core)
