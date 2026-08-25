import copy
import types

import verified_v2_successor_epoch_migration as migration
import verified_v2_successor_epoch_migration_finalizer as finalizer


def _v2_portfolio():
    return {
        "cash": 13357.87,
        "equity": 13535.92,
        "positions": {
            "DHR": {"side": "long", "shares": 0.540748758, "entry": 216.960007, "last_price": 215.62},
            "SLS": {"side": "long", "shares": 4.353086829, "entry": 14.335, "last_price": 13.995},
        },
        "trades": [{"execution_id": "historical-row"}],
        "accounting_epoch_id": migration.OLD_EPOCH_ID,
        "paper_accounting_epoch": {"id": migration.OLD_EPOCH_ID, "validation_hold": True},
    }


def _completed_marker():
    return {
        "status": "completed",
        "target_epoch_id": migration.TARGET_EPOCH_ID,
        "prior_epoch_id": migration.OLD_EPOCH_ID,
        "canonical_ledger_unchanged": True,
        "archive_dir": "/archive/issue82",
    }


def _core():
    return types.SimpleNamespace(portfolio=_v2_portfolio())


def test_status_payload_is_observational_and_never_retries(monkeypatch):
    core = _core()
    calls = {"cutover": 0, "gate": 0, "accounting": 0}
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(_completed_marker()))
    monkeypatch.setattr(migration, "_cutover", lambda *args, **kwargs: calls.__setitem__("cutover", calls["cutover"] + 1))
    monkeypatch.setattr(migration, "_gate_evidence", lambda *args, **kwargs: calls.__setitem__("gate", calls["gate"] + 1))
    monkeypatch.setattr(migration, "_active_accounting_evidence", lambda *args, **kwargs: calls.__setitem__("accounting", calls["accounting"] + 1))

    payload = finalizer.status_payload(core)

    assert payload["status_reads_are_observational"] is True
    assert payload["authority"]["status_reads_write_state"] is False
    assert payload["active_epoch_id"] == migration.OLD_EPOCH_ID
    assert calls == {"cutover": 0, "gate": 0, "accounting": 0}


def test_apply_retries_only_exact_completed_marker_and_proven_preconditions(monkeypatch):
    core = _core()
    monkeypatch.setattr(migration, "_paper_only", lambda: True)
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(_completed_marker()))
    monkeypatch.setattr(migration, "_gate_evidence", lambda runtime: ({"known_invalid_execution_count": 11}, True))
    monkeypatch.setattr(migration, "_active_accounting_evidence", lambda runtime: ({"coverage_issue_count": 1, "economic_issue_count": 0}, True))

    def cutover(runtime, gate, accounting):
        runtime.portfolio["accounting_epoch_id"] = migration.TARGET_EPOCH_ID
        runtime.portfolio["paper_accounting_epoch"] = {
            "id": migration.TARGET_EPOCH_ID,
            "validation_hold": True,
            "historical_evidence_archived": True,
            "forensic_archive_dir": "/archive/issue82-retry",
        }
        runtime.portfolio["trades"] = []
        return {"completed_local": "2026-08-25 15:55:00 CDT"}

    monkeypatch.setattr(migration, "_cutover", cutover)
    result = finalizer.apply(core)

    assert result["overall"] == "pass"
    assert result["status"] == "validation_hold"
    assert result["interrupted_completion_retry_performed"] is True
    assert core.portfolio["accounting_epoch_id"] == migration.TARGET_EPOCH_ID
    assert core.portfolio["trades"] == []


def test_apply_fails_closed_when_marker_or_preconditions_are_not_exact(monkeypatch):
    core = _core()
    monkeypatch.setattr(migration, "_paper_only", lambda: True)
    bad_marker = _completed_marker()
    bad_marker["canonical_ledger_unchanged"] = False
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(bad_marker))
    called = {"cutover": False}
    monkeypatch.setattr(migration, "_cutover", lambda *args, **kwargs: called.__setitem__("cutover", True))

    result = finalizer.apply(core)

    assert result["overall"] == "warn"
    assert result["reason"] == "successor_finalizer_not_applicable"
    assert called["cutover"] is False

    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(_completed_marker()))
    monkeypatch.setattr(migration, "_gate_evidence", lambda runtime: ({"known_invalid_execution_count": 10}, False))
    monkeypatch.setattr(migration, "_active_accounting_evidence", lambda runtime: ({"coverage_issue_count": 1, "economic_issue_count": 0}, True))
    result = finalizer.apply(core)
    assert result["overall"] == "fail"
    assert result["reason"] == "interrupted_successor_retry_preconditions_not_met"
    assert called["cutover"] is False


def test_startup_bridge_keeps_finalizer_last():
    import data_integrity_startup_bridge as bridge
    assert bridge.MODULES[-1] == "verified_v2_successor_epoch_migration_finalizer"
