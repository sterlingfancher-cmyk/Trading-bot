"""Pure evidence contract for the exact latest governed exit abort."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence


ABORT_RECOVERY_VERSION = (
    "governed-v5-preappend-abort-recovery-2026-09-30-v2-pr282-successor"
)
PRIOR_WRAPPER_RECOVERY_VERSION = (
    "governed-v5-wrapper-stack-abort-recovery-2026-10-03-v2"
)
PRIOR_WRAPPER_INTENT_ID = (
    "1891cc36f31ac7eecba784676a506eed33f7b36bb53ede366a763268fd7bba41"
)
RECOVERY_DRIFT_HALT_REASON = "governed pre-append abort recovery evidence drift"
ERROR = (
    "TypeError: apply.<locals>.patched_exit_position() got an unexpected keyword "
    "argument '_governed'"
)
INTENT_ID = "659dc62bfb73bf6331d1cf38b3252a31f339ca54a16e0f4656ddc8b6a409b132"
INCIDENT_LOCAL = "2026-10-08 08:56:48 CDT"
LEDGER_ROWS = 99
LEDGER_SHA256 = "f06507675ad47f45d4a364358f095d690086f2d2a49c5ad23b49623401dca61f"
EVIDENCE_REFERENCE = "issue-84-comment-6061648816"
RECOVERY_VERSION = "governed-v5-runtime-full-exit-abort-recovery-2026-10-08-v4"
BASELINE_CURRENT_EPOCH_ROWS = 11
MAX_RISK_REDUCING_FORWARD_ROWS = 32
PREDECESSOR_FAILURE_VERSION = (
    "governed-v5-runtime-full-exit-abort-recovery-2026-10-08-v3"
)
PREDECESSOR_FAILED_CHECKS = (
    "canonical_digest_exact",
    "canonical_rows_exact",
    "last_execution_receipt_exact",
)
PREDECESSOR_CHECKS = frozenset(
    {
        "accounting_clean",
        "canonical_authoritative",
        "canonical_chain_valid",
        "canonical_digest_exact",
        "canonical_hook_active",
        "canonical_no_active_errors",
        "canonical_no_missing_rows",
        "canonical_rows_exact",
        "canonical_state_projection_parity",
        "exact_captured_abort",
        "exact_released_v5_lineage",
        "hard_risk_limits_unchanged",
        "last_execution_receipt_exact",
        "open_symbols_reconciled",
        "paper_runtime",
        "positive_valuation",
    }
)
FAILED_CHECKS = (
    "exact_preappend_abort_boundary",
    "exact_incident_time",
    "exact_entry_wrapper_error",
    "no_canonical_append_during_abort",
    "flat_state",
    "empty_v5_state_window",
    "no_governed_receipts",
    "positive_flat_valuation",
    "canonical_digest_unchanged",
    "canonical_rows_unchanged",
    "canonical_epoch_window_empty",
    "state_epoch_window_empty",
)


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _forward_rows_are_risk_reducing(
    trades: Sequence[Mapping[str, Any]], delta: int
) -> bool:
    if delta == 0:
        return True
    if delta < 0 or delta > MAX_RISK_REDUCING_FORWARD_ROWS or len(trades) < delta:
        return False
    rows = trades[-delta:]
    return all(
        row.get("action") in {"exit", "partial_exit"}
        and bool(str(row.get("execution_id") or ""))
        and bool(str(row.get("canonical_ledger_event_hash") or ""))
        and str(row.get("accounting_epoch_id") or "")
        == "stable-paper-v5-20260914-issue222-flat-successor01"
        for row in rows
    )


def matches_signature(
    risk: Mapping[str, Any], restart: Mapping[str, Any]
) -> bool:
    """Match only the independently captured active-era full-exit abort."""
    old = _dict(restart.get("preappend_abort_recovery"))
    prior = _dict(restart.get("post_recovery_wrapper_abort_recovery"))
    failure = _dict(restart.get("last_recovery_failure"))
    checks = _dict(failure.get("checks"))
    discrepancy = _dict(restart.get("last_discrepancy"))
    return bool(
        risk.get("halted") is True
        and risk.get("halt_reason") == RECOVERY_DRIFT_HALT_REASON
        and restart.get("status") == "halted"
        and old.get("status") == "recovered"
        and old.get("version") == ABORT_RECOVERY_VERSION
        and old.get("historical_discrepancy_preserved") is True
        and old.get("historical_discrepancy_rewritten") is False
        and prior.get("status") == "recovered"
        and prior.get("version") == PRIOR_WRAPPER_RECOVERY_VERSION
        and prior.get("incident_intent_id") == PRIOR_WRAPPER_INTENT_ID
        and prior.get("historical_discrepancy_preserved") is True
        and prior.get("historical_discrepancy_rewritten") is False
        and failure.get("version") == PREDECESSOR_FAILURE_VERSION
        and failure.get("status") == "not_applicable"
        and failure.get("overall") == "fail"
        and tuple(failure.get("failed_checks") or ()) == PREDECESSOR_FAILED_CHECKS
        and set(checks) == PREDECESSOR_CHECKS
        and all(
            checks.get(name) is False for name in PREDECESSOR_FAILED_CHECKS
        )
        and all(
            value is True
            for name, value in checks.items()
            if name not in PREDECESSOR_FAILED_CHECKS
        )
        and discrepancy.get("operation") == "full_exit"
        and discrepancy.get("intent_id") == INTENT_ID
        and discrepancy.get("error") == ERROR
        and discrepancy.get("state_restored") is True
        and discrepancy.get("canonical_rows_before")
        == discrepancy.get("canonical_rows_after")
        == LEDGER_ROWS
        and restart.get("last_discrepancy_local") == INCIDENT_LOCAL
        and _dict(risk.get("governed_restart_halt_details")) == failure
    )


def build_evidence(
    *,
    paper_runtime: bool,
    released_lineage: bool,
    risk: Mapping[str, Any],
    restart: Mapping[str, Any],
    canonical: Mapping[str, Any],
    accounting: Mapping[str, Any],
    positions: Mapping[str, Any],
    trades: Sequence[Mapping[str, Any]],
    cash: float,
    equity: float,
    expected_daily_loss: Any,
    expected_intraday_drawdown: Any,
) -> Dict[str, Any]:
    """Evaluate current projection without mutating runtime evidence."""
    accounting_positions = _dict(accounting.get("open_positions"))
    last_receipt = _dict(restart.get("last_execution_receipt"))
    last_checks = _dict(restart.get("last_execution_checks"))
    hard_limits = _dict(restart.get("hard_risk_limits"))
    current_rows = int(canonical.get("row_count") or -1)
    forward_delta = current_rows - LEDGER_ROWS
    forward_rows_valid = _forward_rows_are_risk_reducing(trades, forward_delta)
    checks = {
        "paper_runtime": paper_runtime,
        "exact_released_v5_lineage": released_lineage,
        "exact_captured_abort": matches_signature(risk, restart),
        "canonical_hook_active": canonical.get("hook_applied") is True,
        "canonical_authoritative": canonical.get(
            "authoritative_for_new_executions"
        )
        is True,
        "canonical_chain_valid": canonical.get("chain_valid") is True,
        "canonical_incident_boundary_or_risk_reducing_forward_chain": bool(
            (forward_delta == 0 and canonical.get("ledger_sha256") == LEDGER_SHA256)
            or (forward_delta > 0 and _sha256(canonical.get("ledger_sha256")))
        ),
        "canonical_rows_match_forward_delta": bool(
            0 <= forward_delta <= MAX_RISK_REDUCING_FORWARD_ROWS
            and canonical.get("current_epoch_rows")
            == BASELINE_CURRENT_EPOCH_ROWS + forward_delta
            and canonical.get("state_current_epoch_rows")
            == BASELINE_CURRENT_EPOCH_ROWS + forward_delta
        ),
        "post_incident_rows_risk_reducing_only": forward_rows_valid,
        "canonical_state_projection_parity": canonical.get(
            "state_projection_parity"
        )
        is True,
        "canonical_no_missing_rows": bool(
            canonical.get("missing_from_ledger_count") == 0
            and canonical.get("missing_from_state_count") == 0
        ),
        "canonical_no_active_errors": bool(
            not list(canonical.get("errors") or [])
            and risk.get("canonical_execution_ledger_error") in (None, "")
            and risk.get("canonical_state_projection_error") in (None, "")
        ),
        "accounting_clean": bool(
            accounting.get("status") == "ok"
            and accounting.get("coverage_complete") is True
            and accounting.get("coverage_issue_count") == 0
            and accounting.get("economic_issue_count") == 0
        ),
        "open_symbols_reconciled": set(positions) == set(accounting_positions),
        "positive_valuation": cash > 0.0 and equity > 0.0,
        "last_execution_receipt_exact": bool(
            last_receipt.get("canonical_row_count") == current_rows
            and last_receipt.get("operation") in {"partial_exit", "full_exit"}
            and isinstance(last_receipt.get("canonical_last_execution_id"), str)
            and bool(last_receipt.get("canonical_last_execution_id"))
            and last_checks
            and all(value is True for value in last_checks.values())
        ),
        "hard_risk_limits_unchanged": bool(
            hard_limits.get("max_daily_loss_pct") == expected_daily_loss
            and hard_limits.get("max_intraday_drawdown_pct")
            == expected_intraday_drawdown
        ),
    }
    return {
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "canonical": dict(canonical),
        "accounting": dict(accounting),
        "forward_row_delta": forward_delta,
    }
