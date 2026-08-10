"""Canonical append-only execution ledger for the paper trading runtime.

This module wraps the core ``record_trade`` boundary so every entry, exit, and
partial exit receives a durable execution id and is written to an append-only,
hash-chained JSONL ledger before it is mirrored into ``state.trades``.

The current contaminated account remains halted. This module does not repair
historical state, clear halts, place orders, or change strategy/risk/sizing/live/
ML authority. It establishes the immutable execution source of truth required by
Stable Core going forward.
"""
from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
import os
import threading
import uuid
from typing import Any, Dict, List, Tuple

VERSION = "canonical-execution-ledger-2026-08-10-v1"
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
LEDGER_FILE = os.path.join(STATE_DIR, "canonical_execution_ledger.jsonl")

_LOCK = threading.RLock()
_APPLIED_CORE_IDS: set[int] = set()
_REGISTERED_APP_IDS: set[int] = set()


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _portfolio(core: Any = None) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _epoch_id(core: Any = None) -> str:
    pf = _portfolio(core)
    direct = str(pf.get("accounting_epoch_id") or "").strip()
    if direct:
        return direct
    epoch = _d(pf.get("paper_accounting_epoch"))
    nested = str(epoch.get("id") or epoch.get("epoch_id") or "").strip()
    return nested or "legacy-pre-stable-core"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    try:
        if hasattr(value, "item"):
            return _json_safe(value.item())
    except Exception:
        pass
    return str(value)


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _read_rows() -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    if not os.path.exists(LEDGER_FILE):
        return rows, errors
    try:
        with open(LEDGER_FILE, "r", encoding="utf-8") as handle:
            for index, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except Exception as exc:
                    errors.append(f"line_{index}:{type(exc).__name__}")
                    continue
                if not isinstance(obj, dict):
                    errors.append(f"line_{index}:non_dict")
                    continue
                rows.append(obj)
    except Exception as exc:
        errors.append(f"read:{type(exc).__name__}:{exc}")
    return rows, errors


def _verify_rows(rows: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    prev_hash = ""
    for index, row in enumerate(rows, start=1):
        expected_prev = str(row.get("previous_event_hash") or "")
        if expected_prev != prev_hash:
            errors.append(f"line_{index}:previous_hash_mismatch")
        body = dict(row)
        stored_hash = str(body.pop("event_hash", "") or "")
        body.pop("previous_event_hash", None)
        expected_hash = hashlib.sha256((prev_hash + "|" + _canonical_json(body)).encode("utf-8")).hexdigest()
        if not stored_hash or stored_hash != expected_hash:
            errors.append(f"line_{index}:event_hash_mismatch")
        prev_hash = stored_hash
    return not errors, errors


def append_execution(action: str, symbol: str, side: str, px: Any, shares: Any, extra: Dict[str, Any] | None = None, core: Any = None) -> Dict[str, Any]:
    with _LOCK:
        rows, parse_errors = _read_rows()
        if parse_errors:
            raise RuntimeError("canonical execution ledger is not parseable: " + ";".join(parse_errors[:3]))
        chain_valid, chain_errors = _verify_rows(rows)
        if rows and not chain_valid:
            raise RuntimeError("canonical execution ledger hash chain is invalid: " + ";".join(chain_errors[:3]))

        previous_hash = str(rows[-1].get("event_hash") or "") if rows else ""
        payload: Dict[str, Any] = {
            "execution_id": uuid.uuid4().hex,
            "ledger_version": VERSION,
            "recorded_local": _now(core),
            "accounting_epoch_id": _epoch_id(core),
            "action": str(action or "").lower().strip(),
            "symbol": str(symbol or "").upper().strip(),
            "side": str(side or "").lower().strip(),
            "price": round(_f(px), 6),
            "shares": round(_f(shares), 9),
        }
        for key, value in _d(extra).items():
            if key not in payload and key not in {"event_hash", "previous_event_hash"}:
                payload[str(key)] = _json_safe(value)

        event_hash = hashlib.sha256((previous_hash + "|" + _canonical_json(payload)).encode("utf-8")).hexdigest()
        row = dict(payload)
        row["previous_event_hash"] = previous_hash
        row["event_hash"] = event_hash

        folder = os.path.dirname(LEDGER_FILE)
        if folder:
            os.makedirs(folder, exist_ok=True)
        line = _canonical_json(row) + "\n"
        with open(LEDGER_FILE, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return row


def _mark_ledger_failure(core: Any, error: Exception) -> None:
    pf = _portfolio(core)
    risk = _d(pf.setdefault("risk_controls", {}))
    risk["canonical_execution_ledger_error"] = f"{type(error).__name__}: {error}"
    risk["canonical_execution_ledger_error_local"] = _now(core)
    if not bool(risk.get("halted", False)):
        risk["halted"] = True
        risk["halt_reason"] = "canonical execution ledger write failed"
    pf["risk_controls"] = risk


def apply(core: Any = None) -> Dict[str, Any]:
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    core_id = id(core)
    current = getattr(core, "record_trade", None)
    if not callable(current):
        return {"status": "error", "overall": "fail", "version": VERSION, "error": "core.record_trade_missing"}
    if getattr(current, "_canonical_execution_ledger_version", None) == VERSION:
        _APPLIED_CORE_IDS.add(core_id)
        return status_payload(core)

    prior = getattr(current, "_canonical_execution_ledger_prior", current)

    @functools.wraps(prior)
    def wrapped(action, symbol, side, px, shares, extra=None):
        linked_extra = dict(extra) if isinstance(extra, dict) else {}
        try:
            event = append_execution(action, symbol, side, px, shares, linked_extra, core)
            linked_extra["execution_id"] = event.get("execution_id")
            linked_extra["accounting_epoch_id"] = event.get("accounting_epoch_id")
            linked_extra["canonical_ledger_event_hash"] = event.get("event_hash")
            linked_extra["canonical_ledger_version"] = VERSION
        except Exception as exc:
            _mark_ledger_failure(core, exc)
            linked_extra["canonical_execution_ledger_error"] = f"{type(exc).__name__}: {exc}"
        return prior(action, symbol, side, px, shares, linked_extra)

    wrapped._canonical_execution_ledger_version = VERSION  # type: ignore[attr-defined]
    wrapped._canonical_execution_ledger_prior = prior  # type: ignore[attr-defined]
    core.record_trade = wrapped
    _APPLIED_CORE_IDS.add(core_id)
    return status_payload(core)


def status_payload(core: Any = None) -> Dict[str, Any]:
    rows, parse_errors = _read_rows()
    chain_valid, chain_errors = _verify_rows(rows)
    current_epoch = _epoch_id(core) if core is not None else None
    current_epoch_rows = sum(1 for row in rows if str(row.get("accounting_epoch_id") or "") == current_epoch) if current_epoch else 0
    hooked = core is not None and getattr(getattr(core, "record_trade", None), "_canonical_execution_ledger_version", None) == VERSION
    healthy = not parse_errors and chain_valid
    return {
        "status": "ok" if healthy and hooked else ("ready" if healthy else "fail"),
        "overall": "pass" if healthy and hooked else ("warn" if healthy else "fail"),
        "type": "canonical_execution_ledger_status",
        "version": VERSION,
        "ledger_file": LEDGER_FILE,
        "hook_applied": bool(hooked),
        "append_only": True,
        "hash_chain_enabled": True,
        "chain_valid": bool(chain_valid),
        "row_count": len(rows),
        "current_epoch_id": current_epoch,
        "current_epoch_rows": current_epoch_rows,
        "last_execution_id": rows[-1].get("execution_id") if rows else None,
        "parse_error_count": len(parse_errors),
        "chain_error_count": len(chain_errors),
        "errors": (parse_errors + chain_errors)[:5],
        "historical_recovery_source": False,
        "authoritative_for_new_executions": bool(hooked and healthy),
        "authority": {
            "records_execution_events": True,
            "repairs_historical_state": False,
            "clears_hard_halt": False,
            "places_orders": False,
            "changes_strategy": False,
            "changes_thresholds": False,
            "changes_risk_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    app_id = id(flask_app)
    if app_id not in _REGISTERED_APP_IDS:
        from flask import jsonify
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        path = "/paper/canonical-execution-ledger-status"
        if path not in existing:
            flask_app.add_url_rule(path, "canonical_execution_ledger_status", lambda: jsonify(status_payload(core)))
        _REGISTERED_APP_IDS.add(app_id)
    return status_payload(core)
