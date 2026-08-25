import copy
import types

import verified_v2_successor_epoch_migration as migration
import verified_v2_successor_epoch_migration_precondition_compatibility as compat


def _core():
    return types.SimpleNamespace(portfolio={
        "cash": 13357.87,
        "equity": 13535.92,
        "positions": {},
        "trades": [{"execution_id": "historical-row"}],
        "accounting_epoch_id": migration.OLD_EPOCH_ID,
        "paper_accounting_epoch": {"id": migration.OLD_EPOCH_ID, "validation_hold": True},
    })


def _completed_marker():
    return {
        "status": "completed",
        "target_epoch_id": migration.TARGET_EPOCH_ID,
        "prior_epoch_id": migration.OLD_EPOCH_ID,
        "canonical_ledger_unchanged": True,
        "archive_dir": "/archive/issue82",
    }


def _migration_error():
    return {
        "status": "error",
        "overall": "fail",
        "reason": "completed_marker_present_but_successor_epoch_not_active",
    }


def test_exact_completed_marker_v2_reversion_is_deferred_to_finalizer(monkeypatch):
    core = _core()
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(_completed_marker()))

    result = compat._defer_exact_interrupted_completion_error(
        migration, core, _migration_error()
    )

    assert result["status"] == "pending_finalizer"
    assert result["overall"] == "warn"
    assert result["reason"] == "exact_interrupted_completion_deferred_to_finalizer"
    assert result["active_epoch_id"] == migration.OLD_EPOCH_ID
    assert result["target_epoch_id"] == migration.TARGET_EPOCH_ID
    assert result["canonical_ledger_unchanged"] is True
    assert result["finalizer_retry_owner"] == "verified_v2_successor_epoch_migration_finalizer"
    assert result["writes_state"] is False


def test_any_marker_mismatch_leaves_original_startup_error_fail_closed(monkeypatch):
    core = _core()
    fields = {
        "status": "cutover_started",
        "target_epoch_id": "wrong-target",
        "prior_epoch_id": "wrong-prior",
        "canonical_ledger_unchanged": False,
    }
    for field, value in fields.items():
        marker = _completed_marker()
        marker[field] = value
        monkeypatch.setattr(migration, "_marker", lambda row=marker: copy.deepcopy(row))
        result = compat._defer_exact_interrupted_completion_error(
            migration, core, _migration_error()
        )
        assert result["status"] == "error"
        assert result["reason"] == "completed_marker_present_but_successor_epoch_not_active"


def test_non_v2_active_epoch_leaves_original_error_fail_closed(monkeypatch):
    core = _core()
    core.portfolio["accounting_epoch_id"] = "unexpected-epoch"
    core.portfolio["paper_accounting_epoch"]["id"] = "unexpected-epoch"
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(_completed_marker()))

    result = compat._defer_exact_interrupted_completion_error(
        migration, core, _migration_error()
    )
    assert result["status"] == "error"


def test_unrelated_migration_error_is_never_deferred(monkeypatch):
    core = _core()
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(_completed_marker()))
    original = {"status": "error", "overall": "fail", "reason": "different_failure"}

    result = compat._defer_exact_interrupted_completion_error(migration, core, original)
    assert result == original


def test_apply_wrapper_is_observational_and_defers_only_result(monkeypatch):
    core = _core()
    marker = _completed_marker()
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(marker))
    calls = {"original": 0}

    def original(runtime_core=None):
        calls["original"] += 1
        assert runtime_core is core
        return _migration_error()

    monkeypatch.setattr(migration, "apply", original)
    compat._install_migration_apply_compatibility(migration)
    before = copy.deepcopy(core.portfolio)
    result = migration.apply(core)

    assert result["status"] == "pending_finalizer"
    assert calls["original"] == 1
    assert core.portfolio == before


def test_compatibility_declares_zero_state_risk_or_trading_authority():
    status = compat.status_payload(None)
    authority = status["authority"]
    assert authority["writes_state"] is False
    assert authority["defers_only_exact_completed_v3_marker_with_verified_v2_reversion"] is True
    assert authority["finalizer_remains_only_retry_owner"] is True
    assert authority["edits_or_deletes_canonical_rows"] is False
    assert authority["rewrites_current_day_peak"] is False
    assert authority["clears_hard_halt"] is False
    assert authority["places_orders"] is False
    assert authority["changes_strategy"] is False
    assert authority["changes_thresholds"] is False
    assert authority["changes_risk_or_sizing"] is False
    assert authority["changes_live_or_ml_authority"] is False
