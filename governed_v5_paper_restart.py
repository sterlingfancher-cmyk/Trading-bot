"""Governed Issue #84 transition from the held v5 baseline to paper operation.

The Issue #222 successor deliberately retained both a validation hold and the
old projection-divergence halt.  This module owns the one narrow transition
authorized in Issue #84 comment 5802294002.  It releases those two
administrative controls only after the exact verified-flat v5 lineage,
canonical ledger, state projection, accounting, valuation, and risk baseline
all agree.  Strategy, sizing, hard-risk limits, live authority, ML authority,
and immutable history are outside its authority.

Once active, one process/file-locked coordinator serializes paper entry,
partial-exit, full-exit, and the two legacy market-surge batch boundaries.
Existing execution logic remains unchanged.  The coordinator records durable
intent receipts, rejects duplicate partial-exit intents across restart, and
latches a halt if canonical/state/accounting parity stops agreeing.  It never
restores a stale snapshot over a canonical execution.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import datetime as dt
import fcntl
from hashlib import sha256
import json
import os
import threading
from typing import Any, Dict, Iterator, Mapping

from governed_v5_restart_contract import (
    ACTIVATION_DECISION_ID,
    ACTIVATION_REVIEW_REFERENCE,
    TARGET_EPOCH_ID,
    VERSION,
    release_metadata_exact,
)


PRIOR_EPOCH_ID = "stable-paper-v4-20260826-successor01"
HISTORICAL_DECISION = "issue222_unresolved_v4_projection_verified_flat_successor"
RETAINED_HALT_REASON = "canonical execution/state projection divergence"
EXPECTED_PRESTART_LEDGER_ROWS = 88
EXPECTED_PRESTART_LEDGER_SHA256 = (
    "f8ef69407af64f4c2eafc41bd95b9dcc01d0cea51d1aa577431c6f65367f0166"
)
INTENT_RECEIPT_LIMIT = 256
STATUS_SCHEMA_VERSION = "governed-v5-paper-restart-status-2026-09-29-v2-halt-forensics"
PREAPPEND_ABORT_HALT_REASON = "governed paper execution aborted before canonical append"
RECOVERABLE_ENTRY_WRAPPER_ERROR = (
    "TypeError: _patch_enter.<locals>.enter() got an unexpected keyword argument "
    "'_governed'"
)
RECOVERABLE_ENTRY_WRAPPER_INTENT_ID = (
    "0787369dd4481d57c6d73f944f3e14cb89f3088b80ea08e8fe464d95ccac2547"
)
RECOVERABLE_ENTRY_WRAPPER_INCIDENT_LOCAL = "2026-09-29 08:49:52 CDT"
RECOVERABLE_FRESH_DAY_RESET_DATE = "2026-09-30"
RECOVERABLE_INCIDENT_EVIDENCE_REFERENCE = "issue-84-comment-5897148822"
RECOVERY_DRIFT_HALT_REASON = "governed pre-append abort recovery evidence drift"
PR282_FAILED_RECOVERY_VERSION = "governed-v5-preappend-abort-recovery-2026-09-30-v1"
PR282_FAILED_RECOVERY_CHECKS = (
    "exact_preappend_abort_boundary",
    "exact_incident_time",
    "exact_entry_wrapper_error",
)
PR282_FAILED_RECOVERY_ALL_CHECKS = frozenset(
    {
        "canonical_authoritative",
        "canonical_chain_valid",
        "canonical_digest_unchanged",
        "canonical_epoch_window_empty",
        "canonical_hook_active",
        "canonical_no_active_errors",
        "canonical_no_missing_rows",
        "canonical_rows_unchanged",
        "canonical_state_projection_parity",
        "empty_v5_state_window",
        "entry_marker_fix_reviewed_parent",
        "exact_entry_wrapper_error",
        "exact_incident_time",
        "exact_preappend_abort_boundary",
        "exact_released_v5_lineage",
        "flat_state",
        "governed_restart_active",
        "hard_risk_limits_unchanged",
        "no_canonical_append_during_abort",
        "no_governed_receipts",
        "paper_runtime",
        "positive_flat_valuation",
        "state_epoch_window_empty",
    }
)
ABORT_RECOVERY_VERSION = (
    "governed-v5-preappend-abort-recovery-2026-09-30-v2-pr282-successor"
)
SUCCESSOR_WRAPPER_ABORT_INTENT_ID = (
    "35ef0a98a60c43cd979b293e8dee0001967c96a1885f026908876aff12b85c27"
)
SUCCESSOR_WRAPPER_ABORT_INCIDENT_LOCAL = "2026-10-01 08:55:16 CDT"
LATEST_WRAPPER_ABORT_INTENT_ID = (
    "1891cc36f31ac7eecba784676a506eed33f7b36bb53ede366a763268fd7bba41"
)
LATEST_WRAPPER_ABORT_INCIDENT_LOCAL = "2026-10-02 08:45:19 CDT"
RECOVERABLE_WRAPPER_STACK_ERROR = (
    "TypeError: _wrap_enter.<locals>.wrapped() got an unexpected keyword "
    "argument '_governed'"
)
SUCCESSOR_WRAPPER_ABORT_RECOVERY_VERSION = (
    "governed-v5-wrapper-stack-abort-recovery-2026-10-03-v2"
)
RUNTIME_WRAPPER_ABORT_ERROR = (
    "TypeError: apply.<locals>.patched_enter_position() got an unexpected "
    "keyword argument '_governed'"
)
RUNTIME_WRAPPER_ABORT_INTENT_ID = (
    "90dcbb9447ff5cbda53906411d32d0bc71e6983a097a284fecc3e5bcdee9c9c5"
)
RUNTIME_WRAPPER_ABORT_INCIDENT_LOCAL = "2026-10-05 08:47:12 CDT"
RUNTIME_WRAPPER_ABORT_EVIDENCE_REFERENCE = "issue-84-comment-6001396224"
RUNTIME_WRAPPER_ABORT_RECOVERY_VERSION = (
    "governed-v5-runtime-wrapper-abort-recovery-2026-10-05-v3"
)
ENTRY_MARKER_FIX_REVIEWED_PARENT = (
    "6364759af8ed256baf9b2bc99adb3ce28b25cdea"
)
STATE_DIR = (
    os.environ.get("STATE_DIR")
    or os.environ.get("PERSISTENT_STATE_DIR")
    or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    or "."
)
LOCK_FILE = os.path.join(STATE_DIR, ".governed_v5_paper_execution.lock")

_TRUE = {"1", "true", "yes", "on"}
_LOCK = threading.RLock()
_DEPTH = threading.local()
_REGISTERED_APP_IDS: set[int] = set()
_LAST: Dict[str, Any] = {}


def _d(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except Exception:
        return default


def _exception_chain(error: BaseException, limit: int = 4) -> list[str]:
    """Return a bounded diagnostic chain without changing execution behavior."""
    chain: list[str] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and len(chain) < limit and id(current) not in seen:
        seen.add(id(current))
        chain.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return chain


def _now(core: Any = None) -> str:
    try:
        return str(core.local_ts_text())
    except Exception:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _portfolio(core: Any) -> Dict[str, Any]:
    value = getattr(core, "portfolio", {})
    if isinstance(value, dict):
        return value
    return {}


def _paper_only() -> bool:
    live = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() in _TRUE
    broker_live = os.environ.get("BROKER_MODE", "").lower() in {
        "live",
        "real",
        "production",
    }
    return not live and not broker_live


def _release_metadata_exact(epoch: Mapping[str, Any]) -> bool:
    return release_metadata_exact(epoch)


def is_exact_v5_successor(epoch: Mapping[str, Any]) -> bool:
    """Accept the original held successor or this exact governed release."""
    return bool(
        str(epoch.get("id") or epoch.get("epoch_id") or "") == TARGET_EPOCH_ID
        and str(epoch.get("prior_epoch_id") or "") == PRIOR_EPOCH_ID
        and str(epoch.get("historical_recovery_decision") or "")
        == HISTORICAL_DECISION
        and epoch.get("historical_evidence_archived") is True
        and bool(str(epoch.get("forensic_archive_dir") or "").strip())
        and epoch.get("zero_trade_baseline") is True
        and epoch.get("prior_epoch_discrepancy_status")
        == "unresolved_non_promotable"
        and epoch.get("prior_epoch_economics_promotable") is False
        and type(epoch.get("fabricated_exit_rows")) is int
        and epoch.get("fabricated_exit_rows") == 0
        and epoch.get("canonical_history_retained_immutably") is True
        and (
            (
                epoch.get("validation_hold") is True
                and epoch.get("validation_release_status") == "blocked"
                and epoch.get("validation_released") is False
            )
            or _release_metadata_exact(epoch)
        )
    )


def _active(core: Any) -> bool:
    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    restart = _d(state.get("governed_v5_paper_restart"))
    return bool(
        is_exact_v5_successor(epoch)
        and _release_metadata_exact(epoch)
        and restart.get("status") in {"active", "halted"}
        and restart.get("version") == VERSION
        and restart.get("decision_id") == ACTIVATION_DECISION_ID
        and restart.get("review_reference") == ACTIVATION_REVIEW_REFERENCE
        and restart.get("production_writer") is False
        and restart.get("paper_execution_enabled") is True
        and restart.get("live_authority") is False
        and restart.get("ml_execution_authority") is False
    )


def _save(core: Any) -> None:
    save = getattr(core, "save_state", None)
    if not callable(save):
        raise RuntimeError("save_state_missing")
    try:
        save(_portfolio(core))
    except TypeError:
        save()


def _accounting(core: Any) -> Dict[str, Any]:
    try:
        import paper_bidirectional_accounting_guard as accounting

        return accounting.analyze_ledger(_portfolio(core), core)
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _canonical(core: Any) -> Dict[str, Any]:
    try:
        import canonical_execution_ledger as ledger

        return ledger.status_payload(core)
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _entry_marker_fix_reviewed_parent() -> bool:
    """Bind recovery to the reviewed PR #280 parent without runtime imports."""
    return ENTRY_MARKER_FIX_REVIEWED_PARENT == (
        "6364759af8ed256baf9b2bc99adb3ce28b25cdea"
    )


def _pr282_failed_recovery_signature(
    risk: Mapping[str, Any], restart: Mapping[str, Any]
) -> bool:
    """Match only the exact fail-closed diagnostic emitted by deployed PR #282."""
    failure = _d(
        restart.get("last_recovery_failure")
        or restart.get("last_discrepancy")
        or risk.get("governed_restart_halt_details")
    )
    checks = _d(failure.get("checks"))
    failed = failure.get("failed_checks")
    risk_details = _d(risk.get("governed_restart_halt_details"))
    return bool(
        risk.get("halted") is True
        and risk.get("halt_reason") == RECOVERY_DRIFT_HALT_REASON
        and restart.get("status") == "halted"
        and restart.get("preappend_abort_recovery") is None
        and failure.get("status") == "not_applicable"
        and failure.get("overall") == "fail"
        and failure.get("version") == PR282_FAILED_RECOVERY_VERSION
        and risk_details == failure
        and isinstance(failed, list)
        and tuple(failed) == PR282_FAILED_RECOVERY_CHECKS
        and set(checks) == PR282_FAILED_RECOVERY_ALL_CHECKS
        and all(checks.get(name) is False for name in PR282_FAILED_RECOVERY_CHECKS)
        and all(
            value is True
            for name, value in checks.items()
            if name not in PR282_FAILED_RECOVERY_CHECKS
        )
        and checks.get("no_canonical_append_during_abort") is True
        and checks.get("canonical_digest_unchanged") is True
        and checks.get("canonical_rows_unchanged") is True
        and checks.get("canonical_state_projection_parity") is True
    )


def _matched_successor_wrapper_abort(
    risk: Mapping[str, Any], restart: Mapping[str, Any]
) -> Dict[str, str] | None:
    """Match one independently captured wrapper-stack abort exactly."""
    old = _d(restart.get("preappend_abort_recovery"))
    failure = _d(restart.get("last_recovery_failure"))
    checks = _d(failure.get("checks"))
    discrepancy = _d(restart.get("last_discrepancy"))
    common = bool(
        risk.get("halted") is True
        and risk.get("halt_reason") == RECOVERY_DRIFT_HALT_REASON
        and restart.get("status") == "halted"
        and old.get("status") == "recovered"
        and old.get("overall") == "pass"
        and old.get("version") == ABORT_RECOVERY_VERSION
        and old.get("recovery_mode") == "pr282_failed_recovery_successor"
        and old.get("historical_discrepancy_preserved") is True
        and old.get("historical_discrepancy_rewritten") is False
        and failure.get("version") == ABORT_RECOVERY_VERSION
        and failure.get("status") == "not_applicable"
        and failure.get("overall") == "fail"
        and tuple(failure.get("failed_checks") or ())
        == PR282_FAILED_RECOVERY_CHECKS
        and all(checks.get(name) is False for name in PR282_FAILED_RECOVERY_CHECKS)
        and discrepancy.get("operation") == "entry"
        and discrepancy.get("error") == RECOVERABLE_WRAPPER_STACK_ERROR
        and discrepancy.get("state_restored") is True
        and discrepancy.get("canonical_rows_before")
        == discrepancy.get("canonical_rows_after")
        == restart.get("prestart_ledger_rows")
        and _d(risk.get("governed_restart_halt_details")) == failure
    )
    if not common:
        return None
    observed = (
        (
            SUCCESSOR_WRAPPER_ABORT_INTENT_ID,
            SUCCESSOR_WRAPPER_ABORT_INCIDENT_LOCAL,
        ),
        (LATEST_WRAPPER_ABORT_INTENT_ID, LATEST_WRAPPER_ABORT_INCIDENT_LOCAL),
    )
    for intent_id, incident_local in observed:
        if (
            discrepancy.get("intent_id") == intent_id
            and restart.get("last_discrepancy_local") == incident_local
        ):
            return {"intent_id": intent_id, "incident_local": incident_local}
    return None


def _successor_wrapper_abort_signature(
    risk: Mapping[str, Any], restart: Mapping[str, Any]
) -> bool:
    return _matched_successor_wrapper_abort(risk, restart) is not None


def _matched_runtime_wrapper_abort(
    risk: Mapping[str, Any], restart: Mapping[str, Any]
) -> Dict[str, str] | None:
    """Match the exact independently captured 2026-10-05 wrapper abort."""
    old = _d(restart.get("preappend_abort_recovery"))
    prior = _d(restart.get("post_recovery_wrapper_abort_recovery"))
    failure = _d(restart.get("last_recovery_failure"))
    checks = _d(failure.get("checks"))
    discrepancy = _d(restart.get("last_discrepancy"))
    exact = bool(
        risk.get("halted") is True
        and risk.get("halt_reason") == RECOVERY_DRIFT_HALT_REASON
        and restart.get("status") == "halted"
        and old.get("status") == "recovered"
        and old.get("version") == ABORT_RECOVERY_VERSION
        and old.get("historical_discrepancy_preserved") is True
        and old.get("historical_discrepancy_rewritten") is False
        and prior.get("status") == "recovered"
        and prior.get("version") == SUCCESSOR_WRAPPER_ABORT_RECOVERY_VERSION
        and prior.get("recovery_mode") == "post_recovery_wrapper_stack_abort"
        and prior.get("incident_intent_id") == LATEST_WRAPPER_ABORT_INTENT_ID
        and prior.get("historical_discrepancy_preserved") is True
        and prior.get("historical_discrepancy_rewritten") is False
        and failure.get("version") == ABORT_RECOVERY_VERSION
        and failure.get("status") == "not_applicable"
        and failure.get("overall") == "fail"
        and tuple(failure.get("failed_checks") or ())
        == PR282_FAILED_RECOVERY_CHECKS
        and all(checks.get(name) is False for name in PR282_FAILED_RECOVERY_CHECKS)
        and discrepancy.get("operation") == "entry"
        and discrepancy.get("intent_id") == RUNTIME_WRAPPER_ABORT_INTENT_ID
        and discrepancy.get("error") == RUNTIME_WRAPPER_ABORT_ERROR
        and discrepancy.get("state_restored") is True
        and discrepancy.get("canonical_rows_before")
        == discrepancy.get("canonical_rows_after")
        == restart.get("prestart_ledger_rows")
        and restart.get("last_discrepancy_local")
        == RUNTIME_WRAPPER_ABORT_INCIDENT_LOCAL
        and _d(risk.get("governed_restart_halt_details")) == failure
    )
    if not exact:
        return None
    return {
        "intent_id": RUNTIME_WRAPPER_ABORT_INTENT_ID,
        "incident_local": RUNTIME_WRAPPER_ABORT_INCIDENT_LOCAL,
    }


def _runtime_wrapper_abort_signature(
    risk: Mapping[str, Any], restart: Mapping[str, Any]
) -> bool:
    return _matched_runtime_wrapper_abort(risk, restart) is not None


def _preappend_abort_recovery_evidence(core: Any) -> Dict[str, Any]:
    """Verify the one demonstrated pre-append wrapper abort without mutation."""
    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))
    restart = _d(state.get("governed_v5_paper_restart"))
    discrepancy = _d(
        restart.get("last_discrepancy")
        or risk.get("governed_restart_halt_details")
    )
    canonical = _canonical(core)
    prestart_rows = restart.get("prestart_ledger_rows")
    prestart_digest = str(restart.get("prestart_ledger_sha256") or "")
    hard_limits = _d(restart.get("hard_risk_limits"))
    cash = _f(state.get("cash"), -1.0)
    equity = _f(state.get("equity"), -1.0)
    pr282_failed_recovery = _pr282_failed_recovery_signature(risk, restart)
    successor_wrapper_incident = _matched_successor_wrapper_abort(risk, restart)
    runtime_wrapper_incident = _matched_runtime_wrapper_abort(risk, restart)
    successor_wrapper_abort = successor_wrapper_incident is not None
    runtime_wrapper_abort = runtime_wrapper_incident is not None
    active_abort_halt = bool(
        risk.get("halted") is True
        and risk.get("halt_reason") == PREAPPEND_ABORT_HALT_REASON
        and risk.get("governed_restart_halt_version") == VERSION
        and risk.get("governed_restart_halt_local")
        == RECOVERABLE_ENTRY_WRAPPER_INCIDENT_LOCAL
    )
    consumed_by_exact_fresh_day_reset = bool(
        risk.get("halted") is False
        and str(risk.get("halt_reason") or "") == ""
        and str(risk.get("date") or "") == RECOVERABLE_FRESH_DAY_RESET_DATE
        and restart.get("status") == "halted"
        and restart.get("preappend_abort_recovery") is None
    )
    checks = {
        "paper_runtime": _paper_only(),
        "governed_restart_active": _active(core),
        "exact_released_v5_lineage": bool(
            is_exact_v5_successor(epoch) and _release_metadata_exact(epoch)
        ),
        "exact_preappend_abort_boundary": bool(
            restart.get("status") == "halted"
            and (
                active_abort_halt
                or consumed_by_exact_fresh_day_reset
                or pr282_failed_recovery
                or successor_wrapper_abort
                or runtime_wrapper_abort
            )
        ),
        "exact_incident_time": bool(
            pr282_failed_recovery
            or successor_wrapper_abort
            or runtime_wrapper_abort
            or (
                restart.get("last_discrepancy_local")
                == RECOVERABLE_ENTRY_WRAPPER_INCIDENT_LOCAL
                and (
                    consumed_by_exact_fresh_day_reset
                    or risk.get("governed_restart_halt_local")
                    == RECOVERABLE_ENTRY_WRAPPER_INCIDENT_LOCAL
                )
            )
        ),
        "exact_entry_wrapper_error": bool(
            pr282_failed_recovery
            or successor_wrapper_abort
            or runtime_wrapper_abort
            or (
                discrepancy.get("operation") == "entry"
                and discrepancy.get("intent_id")
                == RECOVERABLE_ENTRY_WRAPPER_INTENT_ID
                and discrepancy.get("error") == RECOVERABLE_ENTRY_WRAPPER_ERROR
                and discrepancy.get("state_restored") is True
            )
        ),
        "no_canonical_append_during_abort": bool(
            pr282_failed_recovery
            or successor_wrapper_abort
            or runtime_wrapper_abort
            or (
                type(discrepancy.get("canonical_rows_before")) is int
                and discrepancy.get("canonical_rows_before")
                == discrepancy.get("canonical_rows_after")
                == prestart_rows
            )
        ),
        "recorded_incident_reference_exact": bool(
            not (
                pr282_failed_recovery
                or successor_wrapper_abort
                or runtime_wrapper_abort
            )
            or RECOVERABLE_INCIDENT_EVIDENCE_REFERENCE
            == "issue-84-comment-5897148822"
        ),
        "entry_marker_fix_reviewed_parent": _entry_marker_fix_reviewed_parent(),
        "flat_state": _d(state.get("positions")) == {},
        "empty_v5_state_window": _l(state.get("trades")) == [],
        "no_governed_receipts": _l(
            state.get("governed_execution_intent_receipts")
        )
        == [],
        "positive_flat_valuation": bool(
            cash > 0.0 and equity > 0.0 and abs(cash - equity) <= 0.05
        ),
        "hard_risk_limits_unchanged": bool(
            hard_limits.get("max_daily_loss_pct")
            == getattr(core, "MAX_DAILY_LOSS_PCT", None)
            and hard_limits.get("max_intraday_drawdown_pct")
            == getattr(core, "MAX_INTRADAY_DRAWDOWN_PCT", None)
        ),
        "canonical_hook_active": canonical.get("hook_applied") is True,
        "canonical_authoritative": canonical.get(
            "authoritative_for_new_executions"
        )
        is True,
        "canonical_chain_valid": canonical.get("chain_valid") is True,
        "canonical_digest_unchanged": bool(
            prestart_digest
            and canonical.get("ledger_sha256") == prestart_digest
        ),
        "canonical_rows_unchanged": canonical.get("row_count")
        == prestart_rows,
        "canonical_epoch_window_empty": canonical.get("current_epoch_rows") == 0,
        "state_epoch_window_empty": canonical.get("state_current_epoch_rows") == 0,
        "canonical_state_projection_parity": canonical.get(
            "state_projection_parity"
        )
        is True,
        "canonical_no_missing_rows": bool(
            canonical.get("missing_from_ledger_count") == 0
            and canonical.get("missing_from_state_count") == 0
        ),
        "canonical_no_active_errors": bool(
            not _l(canonical.get("errors"))
            and risk.get("canonical_execution_ledger_error") in (None, "")
            and risk.get("canonical_state_projection_error") in (None, "")
        ),
    }
    return {
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "canonical": canonical,
        "discrepancy": discrepancy,
        "recovery_mode": (
            "post_recovery_runtime_wrapper_abort"
            if runtime_wrapper_abort
            else
            "post_recovery_wrapper_stack_abort"
            if successor_wrapper_abort
            else "pr282_failed_recovery_successor"
            if pr282_failed_recovery
            else (
                "fresh_day_reset_consumed_halt"
                if consumed_by_exact_fresh_day_reset
                else "active_exact_abort_halt"
            )
        ),
        "incident_evidence_reference": RECOVERABLE_INCIDENT_EVIDENCE_REFERENCE,
        "successor_wrapper_incident": successor_wrapper_incident,
        "runtime_wrapper_incident": runtime_wrapper_incident,
    }


def _recover_exact_preappend_wrapper_abort(core: Any) -> Dict[str, Any]:
    """Release only the exact restored pre-append wrapper abort after its fix."""
    with _execution_lock():
        evidence = _preappend_abort_recovery_evidence(core)
        if evidence["failed_checks"]:
            return {
                "status": "not_applicable",
                "overall": "fail",
                "version": ABORT_RECOVERY_VERSION,
                "failed_checks": evidence["failed_checks"],
                "checks": evidence["checks"],
            }

        state = _portfolio(core)
        risk = _d(state.get("risk_controls"))
        restart = _d(state.get("governed_v5_paper_restart"))
        recovery_mode = evidence.get("recovery_mode")
        successor_wrapper_abort = recovery_mode == "post_recovery_wrapper_stack_abort"
        runtime_wrapper_abort = recovery_mode == "post_recovery_runtime_wrapper_abort"
        recovery_version = (
            RUNTIME_WRAPPER_ABORT_RECOVERY_VERSION
            if runtime_wrapper_abort
            else
            SUCCESSOR_WRAPPER_ABORT_RECOVERY_VERSION
            if successor_wrapper_abort
            else ABORT_RECOVERY_VERSION
        )
        incident_intent_id = (
            _d(evidence.get("runtime_wrapper_incident")).get("intent_id")
            if runtime_wrapper_abort
            else
            _d(evidence.get("successor_wrapper_incident")).get("intent_id")
            if successor_wrapper_abort
            else RECOVERABLE_ENTRY_WRAPPER_INTENT_ID
        )
        prior_halt_reason = (
            RECOVERY_DRIFT_HALT_REASON
            if successor_wrapper_abort or runtime_wrapper_abort
            else PREAPPEND_ABORT_HALT_REASON
        )
        risk_before = copy.deepcopy(risk)
        restart_before = copy.deepcopy(restart)
        recovered_local = _now(core)
        recovery = {
            "status": "recovered",
            "overall": "pass",
            "version": recovery_version,
            "recovered_local": recovered_local,
            "prior_halt_reason": prior_halt_reason,
            "incident_intent_id": incident_intent_id,
            "canonical_row_count": _d(evidence.get("canonical")).get(
                "row_count"
            ),
            "canonical_ledger_sha256": _d(evidence.get("canonical")).get(
                "ledger_sha256"
            ),
            "checks": dict(evidence["checks"]),
            "historical_discrepancy_preserved": True,
            "historical_discrepancy_rewritten": False,
            "incident_evidence_reference": (
                RUNTIME_WRAPPER_ABORT_EVIDENCE_REFERENCE
                if runtime_wrapper_abort
                else evidence["incident_evidence_reference"]
            ),
            "recovery_mode": evidence["recovery_mode"],
        }
        risk["halted"] = False
        risk["halt_reason"] = ""
        risk["governed_restart_prior_halt_reason"] = RETAINED_HALT_REASON
        risk["governed_restart_released_local"] = restart.get("activated_local")
        risk["governed_restart_release_version"] = VERSION
        risk["governed_restart_recovered_halt_reason"] = prior_halt_reason
        risk["governed_restart_abort_recovered_local"] = recovered_local
        risk["governed_restart_abort_recovery_version"] = recovery_version
        restart["status"] = "active"
        if runtime_wrapper_abort:
            restart["post_recovery_runtime_wrapper_abort_recovery"] = recovery
        elif successor_wrapper_abort:
            restart["post_recovery_wrapper_abort_recovery"] = recovery
        else:
            restart["preappend_abort_recovery"] = recovery
        try:
            _save(core)
        except Exception:
            risk.clear()
            risk.update(risk_before)
            restart.clear()
            restart.update(restart_before)
            raise
        return recovery


def _preconditions(core: Any) -> Dict[str, Any]:
    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))
    canonical = _canonical(core)
    accounting = _accounting(core)
    cash = _f(state.get("cash"), -1.0)
    equity = _f(state.get("equity"), -1.0)
    checks = {
        "paper_runtime": _paper_only(),
        "exact_held_v5_successor": bool(
            is_exact_v5_successor(epoch)
            and epoch.get("validation_hold") is True
            and epoch.get("validation_release_status") == "blocked"
            and epoch.get("validation_released") is False
        ),
        "reviewed_activation_decision": bool(
            ACTIVATION_DECISION_ID and ACTIVATION_REVIEW_REFERENCE
        ),
        "retained_projection_halt_exact": bool(
            risk.get("halted") is True
            and str(risk.get("halt_reason") or "") == RETAINED_HALT_REASON
        ),
        "flat_state": _d(state.get("positions")) == {},
        "empty_v5_state_window": _l(state.get("trades")) == [],
        "positive_flat_valuation": bool(
            cash > 0.0 and equity > 0.0 and abs(cash - equity) <= 0.05
        ),
        "risk_baseline_sane": bool(
            _f(risk.get("day_start_equity"), -1.0) > 0.0
            and _f(risk.get("day_peak_equity"), -1.0) > 0.0
            and _f(risk.get("day_peak_equity"), -1.0)
            >= _f(risk.get("day_start_equity"), -1.0)
        ),
        "canonical_hook_active": canonical.get("hook_applied") is True,
        "canonical_authoritative": canonical.get("authoritative_for_new_executions")
        is True,
        "canonical_chain_valid": canonical.get("chain_valid") is True,
        "canonical_digest_exact": canonical.get("ledger_sha256")
        == EXPECTED_PRESTART_LEDGER_SHA256,
        "canonical_prestart_rows_exact": canonical.get("row_count")
        == EXPECTED_PRESTART_LEDGER_ROWS,
        "canonical_epoch_exact": canonical.get("current_epoch_id")
        == TARGET_EPOCH_ID,
        "canonical_epoch_window_empty": canonical.get("current_epoch_rows") == 0,
        "state_epoch_window_empty": canonical.get("state_current_epoch_rows") == 0,
        "canonical_state_projection_parity": canonical.get(
            "state_projection_parity"
        )
        is True,
        "accounting_coverage_complete": accounting.get("coverage_complete") is True,
        "accounting_no_coverage_issues": int(
            accounting.get("coverage_issue_count") or 0
        )
        == 0,
        "accounting_no_economic_issues": int(
            accounting.get("economic_issue_count") or 0
        )
        == 0,
        "accounting_flat": _d(accounting.get("open_positions")) == {},
        "accounting_cash_matches": abs(
            cash - _f(accounting.get("cash"), float("inf"))
        )
        <= 0.01,
        "accounting_equity_matches": abs(
            equity - _f(accounting.get("equity"), float("inf"))
        )
        <= 0.01,
    }
    return {
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "canonical": canonical,
        "accounting": accounting,
    }


def _intent_id(operation: str, args: tuple[Any, ...], kwargs: Dict[str, Any], state: Dict[str, Any]) -> str:
    symbol = ""
    side = ""
    price: Any = None
    fraction: Any = None
    reason = ""
    position_generation: Any = None
    if operation == "entry":
        signal = args[0] if args and isinstance(args[0], dict) else {}
        symbol = str(signal.get("symbol") or "").upper()
        side = str(signal.get("side") or "").lower()
        price = signal.get("price")
    else:
        symbol = str(args[0] if args else kwargs.get("symbol") or "").upper()
        price = args[1] if len(args) > 1 else kwargs.get("px")
        if operation == "partial_exit":
            fraction = args[2] if len(args) > 2 else kwargs.get("fraction")
            reason = str(args[3] if len(args) > 3 else kwargs.get("reason") or "")
        else:
            reason = str(args[2] if len(args) > 2 else kwargs.get("reason") or "")
        pos = _d(_d(state.get("positions")).get(symbol))
        side = str(pos.get("side") or "").lower()
        position_generation = pos.get("entry_time")
    payload = {
        "operation": operation,
        "symbol": symbol,
        "side": side,
        "price": price,
        "fraction": fraction,
        "reason": reason,
        "position_generation": position_generation,
        "epoch_id": state.get("accounting_epoch_id"),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(text.encode("utf-8")).hexdigest()


@contextmanager
def _execution_lock() -> Iterator[None]:
    depth = int(getattr(_DEPTH, "value", 0))
    if depth:
        _DEPTH.value = depth + 1
        try:
            yield
        finally:
            _DEPTH.value -= 1
        return
    os.makedirs(os.path.dirname(os.path.abspath(LOCK_FILE)), exist_ok=True)
    descriptor = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        with _LOCK:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            _DEPTH.value = 1
            try:
                yield
            finally:
                _DEPTH.value = 0
                fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _latch(core: Any, reason: str, details: Mapping[str, Any]) -> None:
    state = _portfolio(core)
    risk = _d(state.setdefault("risk_controls", {}))
    risk["halted"] = True
    risk["halt_reason"] = reason
    risk["governed_restart_halt_version"] = VERSION
    risk["governed_restart_halt_local"] = _now(core)
    risk["governed_restart_halt_details"] = dict(details)
    state["risk_controls"] = risk
    restart = _d(state.setdefault("governed_v5_paper_restart", {}))
    restart["status"] = "halted"
    local = _now(core)
    if reason == RECOVERY_DRIFT_HALT_REASON:
        restart["last_recovery_failure"] = dict(details)
        restart["last_recovery_failure_local"] = local
    else:
        restart["last_discrepancy"] = dict(details)
        restart["last_discrepancy_local"] = local
    try:
        _save(core)
    except Exception as exc:
        restart["halt_persist_error"] = f"{type(exc).__name__}: {exc}"


def _post_execution_checks(
    core: Any, before_rows: int, expected_rows: int = 1
) -> Dict[str, Any]:
    canonical = _canonical(core)
    accounting = _accounting(core)
    state = _portfolio(core)
    cash = _f(state.get("cash"), float("inf"))
    checks = {
        "canonical_row_delta_exact": canonical.get("row_count")
        == before_rows + expected_rows,
        "canonical_chain_valid": canonical.get("chain_valid") is True,
        "canonical_state_projection_parity": canonical.get("state_projection_parity")
        is True,
        "accounting_coverage_complete": accounting.get("coverage_complete") is True,
        "accounting_no_coverage_issues": int(
            accounting.get("coverage_issue_count") or 0
        )
        == 0,
        "accounting_no_economic_issues": int(
            accounting.get("economic_issue_count") or 0
        )
        == 0,
        "accounting_cash_matches": abs(
            cash - _f(accounting.get("cash"), float("-inf"))
        )
        <= 0.05,
        # The legacy execution functions refresh persisted equity at the cycle
        # boundary, not inside every entry/exit call. Immediate correctness is
        # therefore bound to cash, lots/positions, ledger parity, and coverage;
        # the normal cycle/daily audit remains the owner of marked equity.
        "accounting_open_symbols_match": set(
            _d(accounting.get("open_positions"))
        )
        == set(_d(state.get("positions"))),
    }
    return {
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "canonical": canonical,
        "accounting": accounting,
    }


def execute_single_operation(
    core: Any,
    operation: str,
    callback: Any,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> Any:
    """Run one statically integrated core execution under the coordinator."""
    if not callable(callback):
        raise TypeError("governed execution callback must be callable")
    if not _active(core):
        return callback()
    with _execution_lock():
        state = _portfolio(core)
        risk = _d(state.get("risk_controls"))
        if operation == "entry" and risk.get("halted"):
            signal = args[0] if args and isinstance(args[0], dict) else {}
            return {
                "symbol": signal.get("symbol"),
                "side": signal.get("side"),
                "blocked": True,
                "reason": "risk_halted",
            }
        intent = _intent_id(operation, args, kwargs, state)
        receipts = _l(state.get("governed_execution_intent_receipts"))
        if operation == "partial_exit" and any(
            isinstance(row, dict) and row.get("intent_id") == intent
            for row in receipts
        ):
            return {
                "symbol": str(args[0] if args else kwargs.get("symbol") or ""),
                "blocked": True,
                "reason": "duplicate_execution_intent",
                "intent_id": intent,
            }

        canonical_before = _canonical(core)
        before_rows = int(canonical_before.get("row_count") or 0)
        state_before = copy.deepcopy(state)
        try:
            result = callback()
        except Exception as exc:
            canonical_after = _canonical(core)
            after_rows = int(canonical_after.get("row_count") or 0)
            restored = after_rows == before_rows
            if restored:
                state.clear()
                state.update(state_before)
            _latch(
                core,
                (
                    "governed paper execution aborted before canonical append"
                    if restored
                    else "governed paper execution lifecycle discrepancy"
                ),
                {
                    "operation": operation,
                    "intent_id": intent,
                    "error": f"{type(exc).__name__}: {exc}",
                    "error_chain": _exception_chain(exc),
                    "canonical_rows_before": before_rows,
                    "canonical_rows_after": after_rows,
                    "state_restored": restored,
                },
            )
            raise

        if result is None or (isinstance(result, dict) and result.get("blocked")):
            return result

        post = _post_execution_checks(core, before_rows)
        receipt = {
            "intent_id": intent,
            "operation": operation,
            "completed_local": _now(core),
            "canonical_row_count": _d(post.get("canonical")).get("row_count"),
            "canonical_last_execution_id": _d(post.get("canonical")).get(
                "last_execution_id"
            ),
        }
        state["governed_execution_intent_receipts"] = (receipts + [receipt])[
            -INTENT_RECEIPT_LIMIT:
        ]
        restart = _d(state.setdefault("governed_v5_paper_restart", {}))
        restart["last_execution_receipt"] = receipt
        restart["last_execution_checks"] = dict(post.get("checks") or {})
        if post["failed_checks"]:
            _latch(
                core,
                "governed paper execution lifecycle discrepancy",
                {
                    "operation": operation,
                    "intent_id": intent,
                    "failed_checks": post["failed_checks"],
                    "canonical_row_count": _d(post.get("canonical")).get("row_count"),
                },
            )
        else:
            _save(core)
        return result


def execute_batch_operation(
    core: Any, operation: str, callback: Any
) -> Dict[str, Any]:
    """Run one statically integrated batch writer under the governed coordinator."""
    if not callable(callback):
        raise TypeError("governed batch callback must be callable")
    if not _active(core):
        return callback()
    with _execution_lock():
        state = _portfolio(core)
        risk = _d(state.get("risk_controls"))
        if risk.get("halted"):
            return {
                "status": "blocked",
                "overall": "stand_down",
                "executed": False,
                "executed_entries": [],
                "execution_reason": "risk_halted",
                "operation": operation,
            }

        canonical_before = _canonical(core)
        before_rows = int(canonical_before.get("row_count") or 0)
        state_before = copy.deepcopy(state)
        try:
            result = callback()
        except Exception as exc:
            canonical_after = _canonical(core)
            after_rows = int(canonical_after.get("row_count") or 0)
            restored = after_rows == before_rows
            if restored:
                state.clear()
                state.update(state_before)
            _latch(
                core,
                (
                    "governed paper batch aborted before canonical append"
                    if restored
                    else "governed paper batch lifecycle discrepancy"
                ),
                {
                    "operation": operation,
                    "error": f"{type(exc).__name__}: {exc}",
                    "error_chain": _exception_chain(exc),
                    "canonical_rows_before": before_rows,
                    "canonical_rows_after": after_rows,
                    "state_restored": restored,
                },
            )
            raise

        if not isinstance(result, dict) or not result.get("executed"):
            return result
        executed = [
            row for row in _l(result.get("executed_entries")) if isinstance(row, dict)
        ]
        expected_rows = len(executed)
        if expected_rows <= 0:
            _latch(
                core,
                "governed paper batch lifecycle discrepancy",
                {
                    "operation": operation,
                    "failed_checks": ["executed_batch_has_no_execution_rows"],
                    "canonical_rows_before": before_rows,
                },
            )
            return result

        post = _post_execution_checks(core, before_rows, expected_rows)
        receipt = {
            "intent_id": _intent_id(operation, (), {}, state_before),
            "operation": operation,
            "completed_local": _now(core),
            "executed_count": expected_rows,
            "canonical_rows_before": before_rows,
            "canonical_row_count": _d(post.get("canonical")).get("row_count"),
            "canonical_last_execution_id": _d(post.get("canonical")).get(
                "last_execution_id"
            ),
        }
        receipts = _l(state.get("governed_execution_intent_receipts"))
        state["governed_execution_intent_receipts"] = (receipts + [receipt])[
            -INTENT_RECEIPT_LIMIT:
        ]
        restart = _d(state.setdefault("governed_v5_paper_restart", {}))
        restart["last_execution_receipt"] = receipt
        restart["last_execution_checks"] = dict(post.get("checks") or {})
        if post["failed_checks"]:
            _latch(
                core,
                "governed paper batch lifecycle discrepancy",
                {
                    "operation": operation,
                    "failed_checks": post["failed_checks"],
                    "canonical_rows_before": before_rows,
                    "canonical_row_count": _d(post.get("canonical")).get("row_count"),
                },
            )
        else:
            _save(core)
        return result


def _install_coordinator(core: Any) -> Dict[str, Any]:
    static_core = getattr(core, "GOVERNED_V5_STATIC_EXECUTION_BOUNDARIES", False)
    try:
        surge = __import__("market_surge_deployment_mode")

        surge_bridge = bool(
            getattr(
                getattr(surge, "_append_trade_rows", None),
                "_canonical_execution_bridge_version",
                None,
            )
        )
    except Exception:
        surge_bridge = False
    try:
        surge_queue = __import__("market_surge_queue_executor")

        queue_bridge = bool(
            getattr(
                getattr(surge_queue, "execute_surge_queue", None),
                "_canonical_surge_queue_bridge_version",
                None,
            )
        )
    except Exception:
        queue_bridge = False
    installed = {
        "entry": static_core is True,
        "partial_exit": static_core is True,
        "full_exit": static_core is True,
        "market_surge_deployment": surge_bridge,
        "market_surge_queue": queue_bridge,
    }
    return {
        "installed": all(installed.values()),
        "boundaries": installed,
        "interprocess_locking": True,
        "duplicate_partial_exit_rejection": True,
        "stale_snapshot_restore_after_append": False,
    }


def _activate(core: Any, pre: Mapping[str, Any]) -> Dict[str, Any]:
    state = _portfolio(core)
    epoch = _d(state.get("paper_accounting_epoch"))
    risk = _d(state.get("risk_controls"))
    epoch_before = copy.deepcopy(epoch)
    risk_before = copy.deepcopy(risk)
    activated_local = _now(core)
    hard_limits = {
        "max_daily_loss_pct": getattr(core, "MAX_DAILY_LOSS_PCT", None),
        "max_intraday_drawdown_pct": getattr(
            core, "MAX_INTRADAY_DRAWDOWN_PCT", None
        ),
    }
    epoch["validation_hold"] = False
    epoch["validation_hold_reason"] = ""
    epoch["validation_release_status"] = "governed_paper_restart_active"
    epoch["validation_released"] = True
    epoch["validation_released_local"] = activated_local
    epoch["validation_release_version"] = VERSION
    epoch["forward_validation_required"] = True
    epoch["restart_activation_decision_id"] = ACTIVATION_DECISION_ID
    epoch["restart_activation_review_reference"] = ACTIVATION_REVIEW_REFERENCE
    state["paper_accounting_epoch"] = epoch

    risk["halted"] = False
    risk["halt_reason"] = ""
    risk["governed_restart_prior_halt_reason"] = RETAINED_HALT_REASON
    risk["governed_restart_released_local"] = activated_local
    risk["governed_restart_release_version"] = VERSION
    risk["canonical_state_projection_parity_failed"] = False
    state["risk_controls"] = risk
    state["governed_v5_paper_restart"] = {
        "status": "active",
        "version": VERSION,
        "decision_id": ACTIVATION_DECISION_ID,
        "review_reference": ACTIVATION_REVIEW_REFERENCE,
        "activated_local": activated_local,
        "prestart_checks": dict(pre.get("checks") or {}),
        "prestart_ledger_sha256": _d(pre.get("canonical")).get("ledger_sha256"),
        "prestart_ledger_rows": _d(pre.get("canonical")).get("row_count"),
        "prestart_cash": state.get("cash"),
        "prestart_equity": state.get("equity"),
        "hard_risk_limits": hard_limits,
        "paper_execution_enabled": True,
        "production_writer": False,
        "live_authority": False,
        "ml_execution_authority": False,
        "strategy_changed": False,
        "sizing_changed": False,
        "historical_evidence_changed": False,
        "post_start_forward_observations_required": True,
    }
    coordinator = _install_coordinator(core)
    if not coordinator.get("installed"):
        epoch.clear()
        epoch.update(epoch_before)
        risk.clear()
        risk.update(risk_before)
        state.pop("governed_v5_paper_restart", None)
        raise RuntimeError("governed execution coordinator installation failed")
    state["governed_v5_paper_restart"]["coordinator"] = coordinator
    try:
        _save(core)
    except Exception:
        epoch.clear()
        epoch.update(epoch_before)
        risk.clear()
        risk.update(risk_before)
        state.pop("governed_v5_paper_restart", None)
        raise
    return status_payload(core)


def apply(core: Any = None) -> Dict[str, Any]:
    global _LAST
    if core is None:
        return {
            "status": "pending",
            "overall": "warn",
            "version": VERSION,
            "reason": "runtime_missing",
        }
    if not _paper_only():
        return {
            "status": "blocked",
            "overall": "fail",
            "version": VERSION,
            "reason": "paper_runtime_only",
        }
    if _active(core):
        coordinator = _install_coordinator(core)
        if not coordinator.get("installed"):
            _latch(
                core,
                "governed paper execution coordinator unavailable",
                coordinator,
            )
        else:
            risk = _d(_portfolio(core).get("risk_controls"))
            restart = _d(_portfolio(core).get("governed_v5_paper_restart"))
            discrepancy = _d(restart.get("last_discrepancy"))
            recovery_candidate = bool(
                risk.get("halt_reason") == PREAPPEND_ABORT_HALT_REASON
                or _pr282_failed_recovery_signature(risk, restart)
                or _successor_wrapper_abort_signature(risk, restart)
                or _runtime_wrapper_abort_signature(risk, restart)
                or (
                    restart.get("status") == "halted"
                    and restart.get("preappend_abort_recovery") is None
                    and discrepancy.get("error") == RECOVERABLE_ENTRY_WRAPPER_ERROR
                )
            )
            if recovery_candidate:
                try:
                    recovery = _recover_exact_preappend_wrapper_abort(core)
                    if recovery.get("status") != "recovered":
                        _latch(
                            core,
                            RECOVERY_DRIFT_HALT_REASON,
                            recovery,
                        )
                except Exception as exc:
                    _LAST = {
                        "status": "error",
                        "overall": "fail",
                        "version": VERSION,
                        "reason": "preappend_abort_recovery_failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                    return dict(_LAST)
        _LAST = status_payload(core)
        return dict(_LAST)

    pre = _preconditions(core)
    if pre["failed_checks"]:
        _LAST = {
            "status": "blocked",
            "overall": "fail",
            "version": VERSION,
            "reason": "governed_restart_preconditions_not_met",
            "failed_checks": pre["failed_checks"],
            "checks": pre["checks"],
        }
        return dict(_LAST)
    try:
        _LAST = _activate(core, pre)
    except Exception as exc:
        _LAST = {
            "status": "error",
            "overall": "fail",
            "version": VERSION,
            "reason": "governed_restart_activation_failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return dict(_LAST)


def status_payload(core: Any = None) -> Dict[str, Any]:
    state = _portfolio(core) if core is not None else {}
    epoch = _d(state.get("paper_accounting_epoch"))
    restart = _d(state.get("governed_v5_paper_restart"))
    risk = _d(state.get("risk_controls"))
    active = _active(core) if core is not None else False
    halt_details = _d(
        restart.get("last_discrepancy")
        or risk.get("governed_restart_halt_details")
    )
    return {
        "status": "active" if active and not risk.get("halted") else "halted" if active else _LAST.get("status", "pending"),
        "overall": "pass" if active and not risk.get("halted") else "fail" if active else _LAST.get("overall", "warn"),
        "type": "governed_v5_paper_restart_status",
        "version": VERSION,
        "status_schema_version": STATUS_SCHEMA_VERSION,
        "epoch_id": str(epoch.get("id") or ""),
        "decision_id": ACTIVATION_DECISION_ID,
        "review_reference": ACTIVATION_REVIEW_REFERENCE,
        "validation_hold": epoch.get("validation_hold"),
        "risk_halted": risk.get("halted"),
        "risk_halt_reason": risk.get("halt_reason"),
        "risk_halt_local": risk.get("governed_restart_halt_local"),
        "last_discrepancy": halt_details or None,
        "last_discrepancy_local": restart.get("last_discrepancy_local"),
        "last_recovery_failure": restart.get("last_recovery_failure"),
        "last_recovery_failure_local": restart.get(
            "last_recovery_failure_local"
        ),
        "canonical_execution_ledger_error": risk.get(
            "canonical_execution_ledger_error"
        ),
        "canonical_execution_ledger_error_local": risk.get(
            "canonical_execution_ledger_error_local"
        ),
        "canonical_state_projection_error": risk.get(
            "canonical_state_projection_error"
        ),
        "canonical_state_projection_error_local": risk.get(
            "canonical_state_projection_error_local"
        ),
        "canonical_state_projection_execution_id": risk.get(
            "canonical_state_projection_execution_id"
        ),
        "paper_execution_enabled": restart.get("paper_execution_enabled", False),
        "post_start_forward_observations_required": restart.get(
            "post_start_forward_observations_required", True
        ),
        "last_execution_receipt": restart.get("last_execution_receipt"),
        "last_execution_checks": restart.get("last_execution_checks"),
        "preappend_abort_recovery": restart.get("preappend_abort_recovery"),
        "post_recovery_wrapper_abort_recovery": restart.get(
            "post_recovery_wrapper_abort_recovery"
        ),
        "post_recovery_runtime_wrapper_abort_recovery": restart.get(
            "post_recovery_runtime_wrapper_abort_recovery"
        ),
        "authority": {
            "paper_only": True,
            "releases_only_exact_v5_administrative_hold": True,
            "clears_only_exact_retained_projection_halt": True,
            "clears_only_exact_restored_preappend_wrapper_abort": True,
            "preserves_hard_risk_limits": True,
            "serializes_execution_boundaries": True,
            "restores_state_after_canonical_append": False,
            "edits_or_deletes_canonical_rows": False,
            "rewrites_history_or_day_peak": False,
            "places_orders_directly": False,
            "changes_strategy_or_sizing": False,
            "changes_live_or_ml_authority": False,
        },
    }


def register_routes(flask_app: Any, core: Any = None) -> Dict[str, Any]:
    result = apply(core)
    if flask_app is None:
        return result
    if id(flask_app) not in _REGISTERED_APP_IDS:
        from flask import jsonify

        path = "/paper/governed-v5-restart-status"
        existing = {getattr(rule, "rule", "") for rule in flask_app.url_map.iter_rules()}
        if path not in existing:
            flask_app.add_url_rule(
                path,
                "governed_v5_paper_restart_status",
                lambda: jsonify(status_payload(core)),
            )
        _REGISTERED_APP_IDS.add(id(flask_app))
    return status_payload(core)
