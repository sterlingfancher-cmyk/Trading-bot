"""Exact-evidence Issue #126 v3 -> v4 successor accounting migration.

The active v3 paper epoch contains one proven immutable lifecycle artifact. A
valid SLS full exit was followed by a re-entrant legacy accounting read before
its canonical row was mirrored into state. That read restored the just-closed
SLS position, allowing one later SLS partial exit that cannot be matched to any
remaining canonical quantity.

This module never changes the append-only canonical ledger. It requires the
exact three-row v3 canonical shape proven by the post-PR-127 Splendid snapshot,
excludes only the exact invalid SLS partial row from successor economics, replays
the two valid rows from the verified v3 snapshot baseline, archives the complete
v3 persistence, and starts a v4 verified-snapshot accounting epoch.

The existing canonical lifecycle halt and current-day risk peak are preserved.
The v4 epoch remains under validation hold. No strategy, signal, sizing, risk
threshold, live authority, ML authority, or order authority is changed.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import os
import shutil
import threading
from typing import Any, Dict, List, Tuple

VERSION = "verified-v3-successor-epoch-migration-2026-08-26-v1-issue126-sls-disposition"
OLD_EPOCH_ID = "stable-paper-v3-20260825-successor01"
TARGET_EPOCH_ID = "stable-paper-v4-20260826-successor01"
PRIOR_EPOCH_ID = "stable-paper-v2-20260812-verified01"
DECISION_ID = "issue-126-sls-reentrant-accounting-disposition-2026-08-26"
HISTORICAL_DECISION = "issue126_sls_reentrant_accounting_successor_rollforward"
EXPECTED_LEDGER_ROW_COUNT = 45
EXPECTED_V3_START_INDEX = 42
EXPECTED_BASELINE_CASH = 13357.874520862653
EXPECTED_BASELINE_EQUITY = 13535.962581344369
EXPECTED_BASELINE_SLS_QTY = 4.353086829
QTY_TOLERANCE = 5e-6
PRICE_TOLERANCE = 5e-6
MONEY_TOLERANCE = 0.01
EQUITY_TOLERANCE = 0.05
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "."
ARCHIVE_ROOT = os.path.join(STATE_DIR, "forensic_archives")
MARKER_FILE = os.path.join(STATE_DIR, f"successor_epoch_{DECISION_ID}.json")
_LOCK = threading.RLock()
_REGISTERED_APP_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}

EXPECTED_V3_ROWS: tuple[dict[str, Any], ...] = (
    {
        "ledger_index": 42,
        "execution_id": "9ab93335faff4e3293d24ebe0bad4e87",
        "accounting_epoch_id": OLD_EPOCH_ID,
        "action": "exit",
        "symbol": "SLS",
        "side": "long",
        "price": 13.62,
        "shares": EXPECTED_BASELINE_SLS_QTY,
        "event_hash": "d4564210ff39029aeea4727ccc121a18445fe7c79c21fa96bc5f4a8874e4b725",
        "economic_disposition": "valid_replay",
    },
    {
        "ledger_index": 43,
        "execution_id": "26702f252870490c8f1ddab86ce794f5",
        "accounting_epoch_id": OLD_EPOCH_ID,
        "action": "partial_exit",
        "symbol": "DHR",
        "side": "long",
        "price": 242.4872,
        "shares": 0.178447,
        "event_hash": "f29532b852bca42c7ee690643e167d9c2a1229a8b44d6dcc9eb1089a1939ddd2",
        "economic_disposition": "valid_replay",
    },
    {
        "ledger_index": 44,
        "execution_id": "90b22aad76074031906e0c6459dfa0bc",
        "accounting_epoch_id": OLD_EPOCH_ID,
        "action": "partial_exit",
        "symbol": "SLS",
        "side": "long",
        "price": 16.04,
        "shares": 1.43651871,
        "event_hash": "d39e877f34bcf9d5a720a8bfd94a66ebace9d8cfa30987bedce29a1112db8774",
        "economic_disposition": "exclude_exact_invalid_reentrant_artifact",
    },
)
INVALID_EXECUTION_ID = EXPECTED_V3_ROWS[2]["execution_id"]
INVALID_EVENT_HASH = EXPECTED_V3_ROWS[2]["event_hash"]


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _close(value: Any, expected: float, tolerance: float) -> bool:
    number = _f(value)
    if number is None:
        return False
    return abs(number - expected) <= tolerance


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paper_only() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {"live", "real", "production"}
    return not live and not broker_live


def _portfolio(core: Any) -> Dict[str, Any]:
    pf = getattr(core, "portfolio", None) if core is not None else None
    return pf if isinstance(pf, dict) else {}


def _atomic_json(path: str, payload: Dict[str, Any]) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _sha256(path: str) -> str | None:
    if not path or not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _marker() -> Dict[str, Any]:
    try:
        with open(MARKER_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _epoch_id(pf: Dict[str, Any]) -> str:
    epoch = _d(pf.get("paper_accounting_epoch"))
    return str(epoch.get("id") or epoch.get("epoch_id") or pf.get("accounting_epoch_id") or "")


def _baseline_snapshot(pf: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    issues: List[str] = []
    epoch = _d(pf.get("paper_accounting_epoch"))
    snap = _d(epoch.get("verified_snapshot_baseline"))
    if _epoch_id(pf) != OLD_EPOCH_ID:
        issues.append("active_epoch_not_exact_v3")
    if str(epoch.get("prior_epoch_id") or "") != PRIOR_EPOCH_ID:
        issues.append("v3_prior_epoch_mismatch")
    if str(epoch.get("historical_recovery_decision") or "") != "verified_v2_historical_disposition_successor_rollforward":
        issues.append("v3_historical_decision_mismatch")
    if not bool(epoch.get("historical_evidence_archived", False)):
        issues.append("v3_historical_evidence_not_archived")
    if not bool(epoch.get("validation_hold", False)):
        issues.append("v3_validation_hold_not_active")
    if str(epoch.get("baseline_type") or "") != "verified_snapshot_with_open_position":
        issues.append("v3_baseline_type_mismatch")
    if not bool(snap.get("verified", False)):
        issues.append("v3_verified_snapshot_missing")
    if not _close(snap.get("cash", epoch.get("starting_cash")), EXPECTED_BASELINE_CASH, MONEY_TOLERANCE):
        issues.append("v3_baseline_cash_mismatch")
    if not _close(snap.get("equity", epoch.get("starting_equity")), EXPECTED_BASELINE_EQUITY, EQUITY_TOLERANCE):
        issues.append("v3_baseline_equity_mismatch")

    positions = _d(snap.get("positions"))
    if set(str(symbol).upper() for symbol in positions) != {"DHR", "SLS"}:
        issues.append("v3_baseline_position_set_mismatch")
    sls = _d(positions.get("SLS"))
    if str(sls.get("side") or "long").lower() != "long":
        issues.append("v3_baseline_sls_side_mismatch")
    if not _close(sls.get("qty", sls.get("shares")), EXPECTED_BASELINE_SLS_QTY, QTY_TOLERANCE):
        issues.append("v3_baseline_sls_qty_mismatch")
    return snap, issues


def _signature_checks(row: Dict[str, Any], expected: Dict[str, Any], index: int) -> Dict[str, bool]:
    checks = {
        "ledger_index": index == int(expected["ledger_index"]),
        "execution_id": str(row.get("execution_id") or "") == str(expected["execution_id"]),
        "accounting_epoch_id": str(row.get("accounting_epoch_id") or "") == OLD_EPOCH_ID,
        "action": str(row.get("action") or "").lower() == str(expected["action"]),
        "symbol": str(row.get("symbol") or "").upper() == str(expected["symbol"]),
        "side": str(row.get("side") or "long").lower() == str(expected["side"]),
        "price": _close(row.get("price"), float(expected["price"]), PRICE_TOLERANCE),
        "event_hash": str(row.get("event_hash") or "") == str(expected["event_hash"]),
    }
    if "shares" in expected:
        checks["shares"] = _close(row.get("shares"), float(expected["shares"]), QTY_TOLERANCE)
    return checks


def _canonical_evidence(core: Any) -> Tuple[Dict[str, Any], bool]:
    try:
        import canonical_execution_ledger as ledger
        with ledger._LOCK:
            rows, parse_errors = ledger._read_rows()
            chain_valid, chain_errors = ledger._verify_rows(rows)
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}, False

    v3_rows = [(index, row) for index, row in enumerate(rows) if str(row.get("accounting_epoch_id") or "") == OLD_EPOCH_ID]
    exact_rows: List[Dict[str, Any]] = []
    exact = len(rows) == EXPECTED_LEDGER_ROW_COUNT and len(v3_rows) == len(EXPECTED_V3_ROWS)
    for offset, expected in enumerate(EXPECTED_V3_ROWS):
        if offset >= len(v3_rows):
            exact_rows.append({"expected": dict(expected), "checks": {}, "exact": False})
        else:
            index, row = v3_rows[offset]
            checks = _signature_checks(row, expected, expected["ledger_index"])
            exact_rows.append({"expected": dict(expected), "observed": _d(row), "checks": checks, "exact": all(checks.values())})
            if not all(checks.values()):
                exact = False

    meta = {
        "status": "ok",
        "chain_valid": bool(chain_valid and not parse_errors),
        "parse_errors": list(parse_errors),
        "chain_errors": list(chain_errors),
        "exact_ledger_row_count": len(rows) == EXPECTED_LEDGER_ROW_COUNT,
        "expected_v3_row_count": len(v3_rows) == len(EXPECTED_V3_ROWS),
        "exact_v3_rows": exact_rows,
        "exact": exact,
        "ledger_file": str(getattr(ledger, "LEDGER_FILE", "") or ""),
    }
    return meta, exact
