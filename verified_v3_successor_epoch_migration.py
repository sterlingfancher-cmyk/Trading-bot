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
PRICE_TOLERANCE = 1e-9
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
            exact = False
            continue
        index, row = v3_rows[offset]
        checks = _signature_checks(row, expected, index)
        row_exact = all(checks.values())
        exact = exact and row_exact
        exact_rows.append({
            "ledger_index": index,
            "execution_id": row.get("execution_id"),
            "event_hash": row.get("event_hash"),
            "checks": checks,
            "exact": row_exact,
            "economic_disposition": expected["economic_disposition"],
        })
    payload = {
        "status": "ok" if not parse_errors and chain_valid and exact else "fail",
        "row_count": len(rows),
        "expected_row_count": EXPECTED_LEDGER_ROW_COUNT,
        "parse_errors": parse_errors[:5],
        "chain_valid": bool(chain_valid),
        "chain_errors": chain_errors[:5],
        "v3_row_count": len(v3_rows),
        "v3_rows_exact": bool(exact),
        "rows": exact_rows,
        "all_execution_ids_unique": len({str(row.get("execution_id") or "") for row in rows}) == len(rows),
    }
    ready = bool(not parse_errors and chain_valid and exact and payload["all_execution_ids_unique"])
    if ready:
        payload["raw_rows"] = rows
    return payload, ready


def _state_trade_evidence(pf: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    trades = [row for row in _l(pf.get("trades")) if isinstance(row, dict)]
    checks: List[Dict[str, Any]] = []
    exact = len(trades) == len(EXPECTED_V3_ROWS)
    for index, expected in enumerate(EXPECTED_V3_ROWS):
        row = trades[index] if index < len(trades) else {}
        row_checks = {
            "execution_id": str(row.get("execution_id") or "") == str(expected["execution_id"]),
            "accounting_epoch_id": str(row.get("accounting_epoch_id") or "") == OLD_EPOCH_ID,
            "action": str(row.get("action") or "").lower() == str(expected["action"]),
            "symbol": str(row.get("symbol") or "").upper() == str(expected["symbol"]),
            "side": str(row.get("side") or "long").lower() == str(expected["side"]),
            "price": _close(row.get("price"), float(expected["price"]), 1e-6),
            "canonical_ledger_event_hash": str(row.get("canonical_ledger_event_hash") or "") == str(expected["event_hash"]),
        }
        row_exact = bool(row and all(row_checks.values()))
        exact = exact and row_exact
        checks.append({"trade_index": index, "execution_id": row.get("execution_id"), "checks": row_checks, "exact": row_exact})
    return {"state_trade_count": len(trades), "state_trade_rows_exact": bool(exact), "rows": checks}, bool(exact)


def _opening_books(snapshot: Dict[str, Any]) -> Tuple[float, Dict[str, Dict[str, float]], float, float, List[str]]:
    issues: List[str] = []
    cash = _f(snapshot.get("cash"))
    if cash is None or cash <= 0:
        return 0.0, {}, 0.0, 0.0, ["baseline_cash_invalid"]
    books: Dict[str, Dict[str, float]] = {}
    for raw_symbol, raw in _d(snapshot.get("positions")).items():
        pos = _d(raw)
        symbol = str(raw_symbol or "").upper().strip()
        side = str(pos.get("side") or "long").lower().strip()
        qty = _f(pos.get("qty", pos.get("shares")))
        entry = _f(pos.get("entry_price", pos.get("entry")))
        if not symbol or side not in {"long", "short"} or qty is None or qty <= 0 or entry is None or entry <= 0:
            issues.append(f"invalid_baseline_position:{symbol or 'unknown'}")
            continue
        books[symbol] = {"side": side, "qty": qty, "entry_price": entry}
    realized_today = float(_f(snapshot.get("realized_today")) or 0.0)
    realized_total = float(_f(snapshot.get("realized_total")) or 0.0)
    return float(cash), books, realized_today, realized_total, issues


def _apply_execution(cash: float, books: Dict[str, Dict[str, float]], realized_today: float, realized_total: float, row: Dict[str, Any]) -> Tuple[float, float, float, List[str]]:
    issues: List[str] = []
    action = str(row.get("action") or "").lower().strip()
    symbol = str(row.get("symbol") or "").upper().strip()
    side = str(row.get("side") or "long").lower().strip()
    qty = _f(row.get("shares"))
    price = _f(row.get("price"))
    if action not in {"entry", "exit", "partial_exit"} or not symbol or side not in {"long", "short"} or qty is None or qty <= 0 or price is None or price <= 0:
        return cash, realized_today, realized_total, [f"unsupported_execution:{row.get('execution_id')}"]

    if action == "entry":
        if symbol in books and books[symbol].get("qty", 0.0) > QTY_TOLERANCE:
            return cash, realized_today, realized_total, [f"entry_against_open_position:{symbol}"]
        cash -= qty * price
        if cash < -MONEY_TOLERANCE:
            issues.append(f"negative_cash_after_entry:{symbol}")
        books[symbol] = {"side": side, "qty": qty, "entry_price": price}
        return cash, realized_today, realized_total, issues

    pos = books.get(symbol)
    if not pos:
        return cash, realized_today, realized_total, [f"exit_without_open_position:{symbol}"]
    if str(pos.get("side") or "") != side:
        return cash, realized_today, realized_total, [f"exit_side_mismatch:{symbol}"]
    available = float(pos.get("qty") or 0.0)
    if qty > available + QTY_TOLERANCE:
        return cash, realized_today, realized_total, [f"exit_exceeds_open_quantity:{symbol}"]
    used = min(qty, available)
    entry = float(pos.get("entry_price") or 0.0)
    if side == "long":
        pnl = (price - entry) * used
        cash += price * used
    else:
        pnl = (entry - price) * used
        cash += (entry * used) + pnl
    realized_today += pnl
    realized_total += pnl
    remaining = available - used
    if remaining <= QTY_TOLERANCE:
        books.pop(symbol, None)
    else:
        pos["qty"] = remaining
        books[symbol] = pos
    return cash, realized_today, realized_total, issues


def _project(core: Any, snapshot: Dict[str, Any], canonical: Dict[str, Any]) -> Dict[str, Any]:
    cash, books, realized_today, realized_total, issues = _opening_books(snapshot)
    rows = _l(canonical.get("raw_rows"))
    valid_ids: List[str] = []
    excluded_ids: List[str] = []
    for index in range(EXPECTED_V3_START_INDEX, EXPECTED_LEDGER_ROW_COUNT):
        row = _d(rows[index]) if index < len(rows) else {}
        execution_id = str(row.get("execution_id") or "")
        if execution_id == INVALID_EXECUTION_ID:
            excluded_ids.append(execution_id)
            continue
        cash, realized_today, realized_total, row_issues = _apply_execution(cash, books, realized_today, realized_total, row)
        issues.extend(row_issues)
        valid_ids.append(execution_id)

    current_positions = _d(_portfolio(core).get("positions"))
    projected_positions: Dict[str, Dict[str, Any]] = {}
    market_value = 0.0
    unrealized = 0.0
    for symbol, economic in sorted(books.items()):
        current = _d(current_positions.get(symbol))
        baseline = _d(_d(snapshot.get("positions")).get(symbol))
        mark = _f(current.get("last_price", current.get("mark")))
        if mark is None or mark <= 0:
            mark = _f(baseline.get("mark", baseline.get("last_price")))
        if mark is None or mark <= 0:
            issues.append(f"projected_mark_missing:{symbol}")
            continue
        side = str(economic.get("side") or "long")
        qty = float(economic.get("qty") or 0.0)
        entry = float(economic.get("entry_price") or 0.0)
        if side == "short":
            upnl = (entry - mark) * qty
            value = (entry * qty) + upnl
            pnl_pct = ((entry - mark) / entry * 100.0) if entry else 0.0
        else:
            upnl = (mark - entry) * qty
            value = mark * qty
            pnl_pct = ((mark - entry) / entry * 100.0) if entry else 0.0
        template = copy.deepcopy(current or baseline)
        for stale in ("accounting_integrity_quarantined", "accounting_integrity_reason"):
            template.pop(stale, None)
        template.update({
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "shares": qty,
            "entry": entry,
            "entry_price": entry,
            "last_price": mark,
            "cost_basis": entry * qty,
            "market_value": value,
            "unrealized_pnl": upnl,
            "pnl_dollars": upnl,
            "unrealized_pnl_pct": pnl_pct,
            "pnl_pct": pnl_pct,
        })
        if side == "short":
            template["margin"] = entry * qty
        projected_positions[symbol] = template
        market_value += value
        unrealized += upnl

    equity = cash + market_value
    return {
        "status": "ok" if not issues else "fail",
        "issues": issues,
        "cash": cash,
        "equity": equity,
        "market_value": market_value,
        "unrealized_pnl": unrealized,
        "realized_today": realized_today,
        "realized_total": realized_total,
        "positions": projected_positions,
        "open_symbols": sorted(projected_positions),
        "valid_execution_ids": valid_ids,
        "excluded_execution_ids": excluded_ids,
    }


def _accounting_cross_check(core: Any, projection: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    try:
        import paper_bidirectional_accounting_guard as accounting
        result = accounting.analyze_ledger(_portfolio(core), core)
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}, False
    coverage = [row for row in _l(result.get("coverage_issues")) if isinstance(row, dict)]
    economics = [row for row in _l(result.get("economic_issues")) if isinstance(row, dict)]
    all_issues = coverage + economics

    def exact_issue(row: Dict[str, Any]) -> bool:
        return bool(
            str(row.get("reason") or "") == "exit_exceeds_reconstructed_position"
            and str(row.get("symbol") or "").upper() == "SLS"
            and str(row.get("action") or "").lower() == "partial_exit"
            and _close(row.get("requested_qty", row.get("shares")), 1.436519, QTY_TOLERANCE)
            and _close(row.get("price"), 16.04, 1e-6)
        )

    issue_shape = bool(len(coverage) == 1 and all(exact_issue(row) for row in all_issues) and len(economics) <= 1)
    rebuilt_cash = _f(result.get("cash", result.get("reconstructed_cash")))
    rebuilt_equity = _f(result.get("equity", result.get("reconstructed_equity")))
    rebuilt_positions = _d(result.get("open_positions"))
    if not rebuilt_positions:
        rebuilt_symbols = sorted(str(value).upper() for value in _l(result.get("reconstructed_open_positions")))
    else:
        rebuilt_symbols = sorted(str(value).upper() for value in rebuilt_positions)
    projected_positions = _d(projection.get("positions"))
    qty_match = True
    if rebuilt_positions and set(rebuilt_positions) == set(projected_positions):
        for symbol, expected in projected_positions.items():
            observed = _d(rebuilt_positions.get(symbol))
            if not _close(observed.get("qty", observed.get("shares")), float(expected.get("shares") or 0.0), QTY_TOLERANCE):
                qty_match = False
    elif rebuilt_symbols != sorted(projected_positions):
        qty_match = False
    ready = bool(
        issue_shape
        and rebuilt_cash is not None and abs(rebuilt_cash - float(projection.get("cash") or 0.0)) <= MONEY_TOLERANCE
        and rebuilt_equity is not None and abs(rebuilt_equity - float(projection.get("equity") or 0.0)) <= EQUITY_TOLERANCE
        and rebuilt_symbols == sorted(projected_positions)
        and qty_match
    )
    return result, ready


def _preconditions(core: Any) -> Dict[str, Any]:
    pf = _portfolio(core)
    snapshot, baseline_issues = _baseline_snapshot(pf)
    canonical, canonical_ready = _canonical_evidence(core)
    state_trades, state_trades_ready = _state_trade_evidence(pf)
    projection = _project(core, snapshot, canonical) if canonical_ready and not baseline_issues else {"status": "fail", "issues": ["projection_preconditions_missing"]}
    cross, cross_ready = _accounting_cross_check(core, projection) if projection.get("status") == "ok" else ({}, False)
    risk = _d(pf.get("risk_controls"))
    risk_exact = bool(risk.get("halted") and str(risk.get("halt_reason") or "") == "canonical execution lifecycle integrity halt")
    projected_symbols = sorted(_d(projection.get("positions")))
    projected_shape = projection.get("status") == "ok" and projected_symbols == ["DHR"] and projection.get("excluded_execution_ids") == [INVALID_EXECUTION_ID]
    current_cash = _f(pf.get("cash"))
    projected_cash = _f(projection.get("cash"))
    invalid_notional = float(EXPECTED_V3_ROWS[2]["shares"]) * float(EXPECTED_V3_ROWS[2]["price"])
    invalid_cash_effect_exact = bool(
        current_cash is not None and projected_cash is not None
        and abs((current_cash - projected_cash) - invalid_notional) <= MONEY_TOLERANCE
    )
    checks = {
        "paper_runtime": _paper_only(),
        "baseline_exact": not baseline_issues,
        "canonical_chain_and_exact_three_v3_rows": canonical_ready,
        "state_trade_mirror_exact_three_v3_rows": state_trades_ready,
        "existing_lifecycle_halt_preserved": risk_exact,
        "deterministic_projection_clean": bool(projected_shape),
        "invalid_partial_cash_effect_exact": invalid_cash_effect_exact,
        "legacy_accounting_cross_check_exact": cross_ready,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "checks": checks,
        "failed": failed,
        "baseline_issues": baseline_issues,
        "canonical": canonical,
        "state_trades": state_trades,
        "projection": projection,
        "accounting_cross_check": cross,
        "invalid_partial_cash_effect_dollars": invalid_notional,
    }


def _archive_state(core: Any, pre: Dict[str, Any], ledger_path: str, ledger_digest: str | None) -> Dict[str, Any]:
    os.makedirs(ARCHIVE_ROOT, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = os.path.join(ARCHIVE_ROOT, f"{stamp}_{DECISION_ID}")
    os.makedirs(archive_dir, exist_ok=False)
    root_abs = os.path.abspath(ARCHIVE_ROOT)
    copied: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(STATE_DIR)):
        src = os.path.join(STATE_DIR, name)
        src_abs = os.path.abspath(src)
        if src_abs == root_abs or src_abs.startswith(root_abs + os.sep):
            continue
        dst = os.path.join(archive_dir, name)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
                copied.append({"name": name, "type": "directory"})
            elif os.path.isfile(src):
                shutil.copy2(src, dst)
                copied.append({"name": name, "type": "file", "size_bytes": os.path.getsize(dst), "sha256": _sha256(dst)})
        except Exception as exc:
            copied.append({"name": name, "type": "copy_error", "error": f"{type(exc).__name__}: {exc}"})
    projection = _d(pre.get("projection"))
    manifest = {
        "status": "ok",
        "type": "issue126_v3_successor_archive",
        "version": VERSION,
        "decision_id": DECISION_ID,
        "prior_epoch_id": OLD_EPOCH_ID,
        "target_epoch_id": TARGET_EPOCH_ID,
        "created_local": _now(core),
        "archive_dir": archive_dir,
        "evidence": {
            "authoritative_snapshot_workflow_run": 33001743744,
            "authoritative_snapshot_artifact_id": 9619045572,
            "prospective_fix_main_sha": "71c3e0777f82f3b1521b3ab17df53a25fb1d91d1",
            "canonical_row_count": _d(pre.get("canonical")).get("row_count"),
            "canonical_v3_rows": _d(pre.get("canonical")).get("rows"),
            "invalid_execution_id": INVALID_EXECUTION_ID,
            "invalid_event_hash": INVALID_EVENT_HASH,
            "invalid_row_retained_immutably": True,
            "invalid_row_economic_effect_excluded_only_in_successor_projection": True,
        },
        "canonical_ledger": {
            "path": ledger_path,
            "sha256_before_cutover": ledger_digest,
            "immutable_history_retained_in_place": True,
            "rotated_or_truncated": False,
            "chain_valid": _d(pre.get("canonical")).get("chain_valid"),
        },
        "projection": {
            "cash": projection.get("cash"),
            "equity": projection.get("equity"),
            "open_symbols": projection.get("open_symbols"),
            "valid_execution_ids": projection.get("valid_execution_ids"),
            "excluded_execution_ids": projection.get("excluded_execution_ids"),
        },
        "pre_cutover_account": copy.deepcopy(_portfolio(core)),
        "copied_entries": copied,
    }
    _atomic_json(os.path.join(archive_dir, "issue126_v3_successor_archive_manifest.json"), manifest)
    return manifest


def build_successor_state(pf: Dict[str, Any], projection: Dict[str, Any], archive_dir: str, started_local: str) -> Dict[str, Any]:
    state = copy.deepcopy(pf)
    risk_before = copy.deepcopy(_d(state.get("risk_controls")))
    positions = copy.deepcopy(_d(projection.get("positions")))
    cash = float(projection.get("cash") or 0.0)
    equity = float(projection.get("equity") or 0.0)
    if cash <= 0 or equity <= 0 or sorted(positions) != ["DHR"]:
        raise RuntimeError("deterministic successor projection is not sane")
    if not bool(risk_before.get("halted")) or str(risk_before.get("halt_reason") or "") != "canonical execution lifecycle integrity halt":
        raise RuntimeError("expected lifecycle halt is not active")

    state["cash"] = cash
    state["equity"] = equity
    state["positions"] = positions
    state["trades"] = []
    realized = _d(state.setdefault("realized_pnl", {}))
    realized["today"] = float(projection.get("realized_today") or 0.0)
    realized["total"] = float(projection.get("realized_total") or 0.0)
    state["realized_pnl"] = realized
    perf = _d(state.setdefault("performance", {}))
    perf["open_positions"] = copy.deepcopy(positions)
    perf["unrealized_pnl"] = float(projection.get("unrealized_pnl") or 0.0)
    perf["realized_pnl_today"] = float(projection.get("realized_today") or 0.0)
    perf["realized_pnl_total"] = float(projection.get("realized_total") or 0.0)
    state["performance"] = perf
    state["risk_controls"] = risk_before

    snapshot_positions: Dict[str, Dict[str, Any]] = {}
    for symbol, raw in positions.items():
        pos = _d(raw)
        snapshot_positions[symbol] = {
            "side": str(pos.get("side") or "long"),
            "qty": float(pos.get("shares", pos.get("qty")) or 0.0),
            "entry_price": float(pos.get("entry", pos.get("entry_price")) or 0.0),
            "mark": float(pos.get("last_price") or 0.0),
        }
    snapshot = {
        "verified": True,
        "version": VERSION,
        "started_local": started_local,
        "cash": cash,
        "equity": equity,
        "realized_today": float(projection.get("realized_today") or 0.0),
        "realized_total": float(projection.get("realized_total") or 0.0),
        "positions": snapshot_positions,
        "source": "deterministic_v3_verified_snapshot_plus_exact_valid_canonical_replay",
        "invalid_execution_retained_but_excluded_from_successor_economics": INVALID_EXECUTION_ID,
    }
    state["accounting_epoch_id"] = TARGET_EPOCH_ID
    state["paper_accounting_epoch"] = {
        "version": VERSION,
        "id": TARGET_EPOCH_ID,
        "decision_id": DECISION_ID,
        "started_local": started_local,
        "starting_cash": cash,
        "starting_equity": equity,
        "clean_start": False,
        "zero_trade_baseline": False,
        "baseline_type": "verified_snapshot_with_open_position",
        "verified_snapshot_baseline": snapshot,
        "historical_recovery_decision": HISTORICAL_DECISION,
        "prior_epoch_id": OLD_EPOCH_ID,
        "prior_epoch_disposition": "archived_with_exact_issue126_sls_reentrant_artifact_disposition_and_immutable_canonical_ledger_retained",
        "historical_evidence_archived": True,
        "forensic_archive_dir": archive_dir,
        "validation_hold": True,
        "validation_hold_reason": "issue 126 v4 clean-active-accounting validation hold",
        "validation_release_status": "blocked",
        "validation_released": False,
        "validation_released_local": None,
        "forward_validation_required": True,
        "valid_path_rows_baseline": 0,
        "invalid_execution_id": INVALID_EXECUTION_ID,
        "invalid_event_hash": INVALID_EVENT_HASH,
        "canonical_history_retained_immutably": True,
    }
    return state


def _rotate_journal_for_successor() -> None:
    try:
        import trade_journal as tj
        factory = getattr(tj, "_empty_journal", None)
        journal = factory() if callable(factory) else {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
        if not isinstance(journal, dict):
            journal = {"trades": [], "recent_trades": [], "snapshots": [], "event_hook_events": []}
        journal["accounting_epoch_id"] = TARGET_EPOCH_ID
        journal["issue126_successor_epoch_started_local"] = _now()
        journal["issue126_successor_version"] = VERSION
        for attr in ("TRADE_JOURNAL_FILE", "TRADE_JOURNAL_BACKUP_FILE"):
            path = str(getattr(tj, attr, "") or "")
            if path:
                _atomic_json(path, journal)
    except Exception:
        return


def _complete_marker(started: Dict[str, Any], core: Any, state_file: str, successor: Dict[str, Any], digest_after: str | None, *, retried: bool) -> Dict[str, Any]:
    completed = dict(started)
    completed.update({
        "status": "completed",
        "overall": "pass",
        "completed_local": _now(core),
        "state_file": state_file,
        "validation_hold": True,
        "canonical_ledger_sha256_after": digest_after,
        "canonical_ledger_unchanged": digest_after == started.get("canonical_ledger_sha256_before"),
        "successor_cash": successor.get("cash"),
        "successor_equity": successor.get("equity"),
        "successor_positions": sorted(_d(successor.get("positions"))),
        "successor_trade_rows": len(_l(successor.get("trades"))),
        "lifecycle_halt_preserved": bool(_d(successor.get("risk_controls")).get("halted")),
        "lifecycle_halt_reason": _d(successor.get("risk_controls")).get("halt_reason"),
        "interrupted_completion_retry_performed": retried,
    })
    _atomic_json(MARKER_FILE, completed)
    return completed


def _cutover(core: Any, pre: Dict[str, Any], *, retried: bool = False) -> Dict[str, Any]:
    global _LAST
    import canonical_execution_ledger as ledger
    import clean_accounting_epoch as clean
    ledger_path = str(getattr(ledger, "LEDGER_FILE", "") or "")
    digest_before = _sha256(ledger_path)
    archive = _archive_state(core, pre, ledger_path, digest_before)
    started_local = _now(core)
    started = {
        "status": "cutover_started",
        "version": VERSION,
        "decision_id": DECISION_ID,
        "prior_epoch_id": OLD_EPOCH_ID,
        "target_epoch_id": TARGET_EPOCH_ID,
        "archive_dir": archive.get("archive_dir"),
        "started_local": started_local,
        "canonical_ledger_sha256_before": digest_before,
        "invalid_execution_id": INVALID_EXECUTION_ID,
        "invalid_event_hash": INVALID_EVENT_HASH,
    }
    _atomic_json(MARKER_FILE, started)
    successor = build_successor_state(_portfolio(core), _d(pre.get("projection")), str(archive.get("archive_dir") or ""), started_local)
    risk_before = copy.deepcopy(_d(_portfolio(core).get("risk_controls")))
    history_before = copy.deepcopy(_portfolio(core).get("history"))
    with clean._runtime_locks():
        state_file = clean._write_clean_state_and_backups(core, successor)
        _rotate_journal_for_successor()
        clean._reset_snapshot_archive(successor, state_file)
        pf = _portfolio(core)
        pf.clear()
        pf.update(successor)
    digest_after = _sha256(ledger_path)
    if digest_before != digest_after:
        raise RuntimeError("canonical ledger changed during Issue #126 successor cutover")
    if _d(successor.get("risk_controls")) != risk_before:
        raise RuntimeError("risk controls changed during Issue #126 successor cutover")
    if successor.get("history") != history_before:
        raise RuntimeError("historical equity series changed during Issue #126 successor cutover")
    completed = _complete_marker(started, core, state_file, successor, digest_after, retried=retried)
    _LAST = completed
    return completed


def _active_status(core: Any) -> Dict[str, Any]:
    pf = _portfolio(core)
    epoch = _d(pf.get("paper_accounting_epoch"))
    marker = _marker()
    risk = _d(pf.get("risk_controls"))
    return {
        "status": "validation_hold",
        "overall": "pass",
        "version": VERSION,
        "epoch_id": TARGET_EPOCH_ID,
        "prior_epoch_id": OLD_EPOCH_ID,
        "historical_evidence_archived": bool(epoch.get("historical_evidence_archived", False)),
        "forensic_archive_dir": epoch.get("forensic_archive_dir") or marker.get("archive_dir"),
        "validation_hold": bool(epoch.get("validation_hold", False)),
        "canonical_ledger_unchanged": bool(marker.get("canonical_ledger_unchanged", False)),
        "invalid_execution_retained_immutably": str(epoch.get("invalid_execution_id") or "") == INVALID_EXECUTION_ID,
        "state_trade_rows": len(_l(pf.get("trades"))),
        "positions": sorted(_d(pf.get("positions"))),
        "cash": pf.get("cash"),
        "equity": pf.get("equity"),
        "lifecycle_halt_preserved": bool(risk.get("halted")),
        "lifecycle_halt_reason": risk.get("halt_reason"),
        "interrupted_completion_retry_performed": bool(marker.get("interrupted_completion_retry_performed", False)),
    }


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    if core is None:
        return {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    if not _paper_only():
        return {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "paper_runtime_only"}
    with _LOCK:
        pf = _portfolio(core)
        active_epoch = _epoch_id(pf)
        marker = _marker()
        if active_epoch == TARGET_EPOCH_ID:
            result = _active_status(core)
            if marker.get("status") != "completed":
                result.update({"status": "error", "overall": "fail", "reason": "v4_active_without_completed_issue126_marker"})
            _LAST = result
            return result
        if active_epoch != OLD_EPOCH_ID:
            result = {
                "status": "not_applicable",
                "overall": "pass",
                "version": VERSION,
                "reason": "issue126_v3_epoch_not_active",
                "active_epoch_id": active_epoch,
            }
            _LAST = result
            return result
        retry = marker.get("status") in {"cutover_started", "completed"}
        if retry and not (
            str(marker.get("prior_epoch_id") or "") == OLD_EPOCH_ID
            and str(marker.get("target_epoch_id") or "") == TARGET_EPOCH_ID
            and str(marker.get("invalid_execution_id") or "") == INVALID_EXECUTION_ID
            and str(marker.get("invalid_event_hash") or "") == INVALID_EVENT_HASH
        ):
            result = {"status": "blocked", "overall": "fail", "version": VERSION, "reason": "issue126_successor_marker_mismatch"}
            _LAST = result
            return result

        pre = _preconditions(core)
        if pre["failed"]:
            result = {
                "status": "blocked",
                "overall": "fail",
                "version": VERSION,
                "reason": "issue126_successor_preconditions_not_met",
                "failed_checks": pre["failed"],
                "checks": pre["checks"],
                "baseline_issues": pre.get("baseline_issues"),
                "canonical": {key: value for key, value in _d(pre.get("canonical")).items() if key != "raw_rows"},
                "projection": {key: value for key, value in _d(pre.get("projection")).items() if key != "positions"},
            }
            _LAST = result
            return result
        try:
            return _cutover(core, pre, retried=bool(retry))
        except Exception as exc:
            result = {"status": "error", "overall": "fail", "version": VERSION, "reason": "issue126_successor_cutover_failed", "error": f"{type(exc).__name__}: {exc}"}
            _LAST = result
            return result


def status_payload(core: Any = None) -> Dict[str, Any]:
    if core is None:
        result = dict(_LAST) if _LAST else {"status": "pending", "overall": "warn", "version": VERSION, "reason": "runtime_missing"}
    elif _epoch_id(_portfolio(core)) == TARGET_EPOCH_ID:
        result = _active_status(core)
    else:
        result = dict(_LAST) if _LAST else {
            "status": "pending",
            "overall": "warn",
            "version": VERSION,
            "active_epoch_id": _epoch_id(_portfolio(core)),
        }
    return {
        **result,
        "type": "verified_v3_successor_epoch_migration_status",
        "status_reads_are_observational": True,
        "authority": {
            "paper_only": True,
            "one_time_accounting_epoch_rollforward": True,
            "deterministic_verified_snapshot_plus_canonical_replay": True,
            "archives_prior_v3_evidence": True,
            "clears_active_state_trade_window": True,
            "retains_invalid_canonical_row_immutably": True,
            "excludes_only_exact_invalid_row_from_successor_economics": True,
            "edits_or_deletes_canonical_rows": False,
            "rotates_or_truncates_canonical_ledger": False,
            "rewrites_current_day_peak": False,
            "rewrites_history": False,
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
        path = "/paper/verified-v3-successor-epoch-status"
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if path not in existing:
            flask_app.add_url_rule(path, "verified_v3_successor_epoch_status", lambda: jsonify(status_payload(core)))
        _REGISTERED_APP_IDS.add(app_id)
    return status_payload(core)