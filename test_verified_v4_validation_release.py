import copy
import types

import verified_v4_validation_release as release


def _core(state):
    saved = []
    return types.SimpleNamespace(
        portfolio=state,
        local_ts_text=lambda: "2026-09-02 13:15:00 CDT",
        save_state=lambda *args: saved.append(copy.deepcopy(state)),
        saved=saved,
    )


def _state():
    return {
        "cash": 13475.004711,
        "equity": 13475.0,
        "accounting_epoch_id": release.TARGET_EPOCH_ID,
        "paper_accounting_epoch": {
            "id": release.TARGET_EPOCH_ID,
            "historical_evidence_archived": True,
            "validation_hold": True,
            "validation_hold_reason": "issue 126 v4 clean-active-accounting validation hold",
            "validation_release_status": "blocked",
            "validation_released": False,
            "forward_validation_required": True,
        },
        "risk_controls": {"halted": False, "halt_reason": "", "self_defense_active": False},
    }


def _evidence(rows=19):
    return {
        "ledger": {
            "chain_valid": True,
            "authoritative_for_new_executions": True,
            "current_epoch_id": release.TARGET_EPOCH_ID,
            "current_epoch_rows": 9,
        },
        "accounting": {
            "coverage_complete": True,
            "coverage_issue_count": 0,
            "economic_issue_count": 0,
            "reconstructed": {
                "cash": 13475.004291,
                "equity": 13475.004291,
                "open_positions": {},
            },
        },
        "integrity": {
            "status": "pass",
            "forward_validation": {
                "promotion_evidence_eligible": True,
                "post_epoch_valid_exact_lifecycle_rows": rows,
            },
        },
    }


def test_releases_only_v4_validation_metadata(monkeypatch):
    state = _state()
    risk_before = copy.deepcopy(state["risk_controls"])
    core = _core(state)
    monkeypatch.setattr(release, "_evidence", lambda _core: _evidence())

    out = release.apply(core)

    assert out["status"] == "released"
    assert out["post_epoch_valid_exact_lifecycle_rows"] == 19
    assert state["paper_accounting_epoch"]["validation_hold"] is False
    assert state["paper_accounting_epoch"]["validation_release_status"] == "released"
    assert state["paper_accounting_epoch"]["validation_released"] is True
    assert state["paper_accounting_epoch"]["forward_validation_required"] is False
    assert state["risk_controls"] == risk_before
    assert len(core.saved) == 1


def test_blocks_when_forward_rows_are_missing(monkeypatch):
    state = _state()
    core = _core(state)
    monkeypatch.setattr(release, "_evidence", lambda _core: _evidence(rows=0))

    out = release.apply(core)

    assert out["status"] == "blocked"
    assert "post_epoch_rows_sufficient" in out["failed_checks"]
    assert state["paper_accounting_epoch"]["validation_hold"] is True
    assert not core.saved


def test_never_clears_an_active_risk_halt(monkeypatch):
    state = _state()
    state["risk_controls"].update({"halted": True, "halt_reason": "performance risk hard halt"})
    core = _core(state)
    monkeypatch.setattr(release, "_evidence", lambda _core: _evidence())

    out = release.apply(core)

    assert out["status"] == "blocked"
    assert "risk_not_halted" in out["failed_checks"]
    assert state["risk_controls"]["halted"] is True
    assert state["paper_accounting_epoch"]["validation_hold"] is True
    assert not core.saved


def test_fails_closed_on_canonical_or_accounting_defect(monkeypatch):
    for section, key, value in (
        ("ledger", "chain_valid", False),
        ("accounting", "coverage_issue_count", 1),
        ("accounting", "economic_issue_count", 1),
    ):
        state = _state()
        core = _core(state)
        evidence = _evidence()
        evidence[section][key] = value
        monkeypatch.setattr(release, "_evidence", lambda _core, evidence=evidence: evidence)
        out = release.apply(core)
        assert out["status"] == "blocked"
        assert state["paper_accounting_epoch"]["validation_hold"] is True
        assert not core.saved


def test_status_fails_closed_if_release_attempt_is_not_authoritative(monkeypatch):
    state = _state()
    core = _core(state)
    monkeypatch.setattr(release, "_LAST", {"status": "released", "already_released": False})

    out = release.status_payload(core)

    assert out["status"] == "blocked"
    assert out["overall"] == "fail"
    assert out["released"] is False
    assert out["reason"] == "release_attempt_not_reflected_in_authoritative_state"
