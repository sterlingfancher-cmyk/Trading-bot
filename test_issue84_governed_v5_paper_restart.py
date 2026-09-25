import copy
import types

import issue84_governed_v5_paper_restart as restart


def _state():
    return {
        "accounting_epoch_id": restart.TARGET_EPOCH_ID,
        "cash": restart.EXPECTED_CASH,
        "equity": restart.EXPECTED_CASH,
        "positions": {},
        "trades": [],
        "paper_accounting_epoch": {
            "id": restart.TARGET_EPOCH_ID,
            "prior_epoch_id": restart.PRIOR_EPOCH_ID,
            "historical_recovery_decision": restart.SUCCESSOR_DECISION,
            "historical_evidence_archived": True,
            "validation_hold": True,
            "validation_hold_reason": "issue 222 v5 verified-flat successor validation hold",
            "validation_release_status": "blocked",
            "validation_released": False,
            "forward_validation_required": True,
            "prior_epoch_discrepancy_status": "unresolved_non_promotable",
            "prior_epoch_economics_promotable": False,
            "fabricated_exit_rows": 0,
        },
        "risk_controls": {
            "halted": True,
            "halt_reason": restart.RETAINED_HALT_REASON,
        },
        "feedback_loop": {"hard_halt": True, "block_new_entries": True},
        "issue222_verified_flat_successor": {
            "status": "validation_hold",
            "unresolved_prior_discrepancy": True,
            "prior_epoch_economics_promotable": False,
            "fabricated_exit_rows": 0,
            "canonical_history_rewritten": False,
        },
        "history": [10000.0, restart.EXPECTED_CASH],
    }


def _core(state, save=None):
    return types.SimpleNamespace(
        portfolio=state,
        local_ts_text=lambda *a, **k: "2026-09-25 15:00:00 CDT",
        save_state=save or (lambda *a, **k: None),
    )


def _evidence(monkeypatch):
    monkeypatch.setattr(
        restart,
        "_evidence",
        lambda core: {
            "ledger": {
                "chain_valid": True,
                "authoritative_for_new_executions": True,
                "current_epoch_id": restart.TARGET_EPOCH_ID,
                "row_count": restart.EXPECTED_LEDGER_ROWS,
                "current_epoch_rows": 0,
                "state_projection_parity": True,
                "missing_from_state_count": 0,
                "missing_from_ledger_count": 0,
            },
            "accounting": {
                "coverage_complete": True,
                "coverage_issue_count": 0,
                "economic_issue_count": 0,
            },
            "rebuilt": {
                "cash": restart.EXPECTED_CASH,
                "equity": restart.EXPECTED_CASH,
                "open_positions": {},
            },
        },
    )


def test_governed_restart_releases_only_v5_admin_gate(monkeypatch):
    _evidence(monkeypatch)
    state = _state()
    history_before = copy.deepcopy(state["history"])
    out = restart.apply(_core(state))
    assert out["status"] == "released"
    assert state["paper_accounting_epoch"]["validation_hold"] is False
    assert state["paper_accounting_epoch"]["validation_release_status"] == "released"
    assert state["paper_accounting_epoch"]["forward_validation_required"] is True
    assert state["risk_controls"]["halted"] is False
    assert state["history"] == history_before
    assert state["paper_accounting_epoch"]["prior_epoch_discrepancy_status"] == "unresolved_non_promotable"
    assert state["paper_accounting_epoch"]["prior_epoch_economics_promotable"] is False
    assert state["paper_accounting_epoch"]["fabricated_exit_rows"] == 0


def test_governed_restart_rejects_wrong_halt(monkeypatch):
    _evidence(monkeypatch)
    state = _state()
    state["risk_controls"]["halt_reason"] = "performance risk hard intraday drawdown halt"
    before = copy.deepcopy(state)
    out = restart.apply(_core(state))
    assert out["status"] == "blocked"
    assert "exact_retained_projection_halt" in out["failed_checks"]
    assert state == before


def test_governed_restart_rejects_any_v5_execution(monkeypatch):
    _evidence(monkeypatch)
    state = _state()
    state["trades"] = [{"execution_id": "new-v5-row"}]
    before = copy.deepcopy(state)
    out = restart.apply(_core(state))
    assert out["status"] == "blocked"
    assert "no_v5_state_trades" in out["failed_checks"]
    assert state == before


def test_governed_restart_rejects_projection_parity_failure(monkeypatch):
    _evidence(monkeypatch)
    original = restart._evidence
    def bad(core):
        evidence = original(core)
        evidence["ledger"]["state_projection_parity"] = False
        return evidence
    monkeypatch.setattr(restart, "_evidence", bad)
    state = _state()
    out = restart.apply(_core(state))
    assert out["status"] == "blocked"
    assert "canonical_state_projection_parity" in out["failed_checks"]


def test_governed_restart_rolls_back_in_memory_on_save_failure(monkeypatch):
    _evidence(monkeypatch)
    state = _state()
    before = copy.deepcopy(state)
    def fail(*args, **kwargs):
        raise RuntimeError("persist failed")
    out = restart.apply(_core(state, fail))
    assert out["status"] == "error"
    assert out["reason"] == "save_state_failed"
    assert state == before


def test_governed_restart_is_idempotent_after_persisted_release(monkeypatch):
    _evidence(monkeypatch)
    state = _state()
    first = restart.apply(_core(state))
    assert first["status"] == "released"
    second = restart.apply(_core(state))
    assert second["status"] == "released"
    assert second["already_released"] is True
