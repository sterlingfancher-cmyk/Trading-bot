import types

import pytest

import verified_v3_successor_epoch_migration as mod


def _make_core(dhr_qty, dhr_shares):
    pf = {
        "positions": {
            "DHR": {"side": "long", "qty": dhr_qty, "shares": dhr_shares},
            "SLS": {"side": "long", "qty": 1.0, "shares": 1.0},
        },
        "risk_controls": {"halted": True, "halt_reason": "canonical execution lifecycle integrity halt"},
        "paper_accounting_epoch": {},
    }
    return types.SimpleNamespace(portfolio=pf)


@pytest.fixture(autouse=True)
def stub_external_checks(monkeypatch):
    # Keep this focused: stub heavy external evidence checks so _preconditions
    # returns quickly and the terminal-state predicate is inspectable.
    monkeypatch.setattr(mod, "_baseline_snapshot", lambda pf: ({}, []))
    monkeypatch.setattr(mod, "_canonical_evidence", lambda core: ({}, False))
    monkeypatch.setattr(mod, "_state_trade_evidence", lambda pf: ({}, True))
    monkeypatch.setattr(mod, "_project", lambda core, snapshot, canonical: {"status": "fail", "issues": ["projection_preconditions_missing"]})
    monkeypatch.setattr(mod, "_accounting_cross_check", lambda core, projection: ({}, True))
    yield


def test_alias_divergence_accepts():
    # Production alias divergence: qty ~= EXPECTED_BASELINE_DHR_QTY, shares ~= EXPECTED_DHR_REMAINDER
    core = _make_core(mod.EXPECTED_BASELINE_DHR_QTY, mod.EXPECTED_DHR_REMAINDER)
    pre = mod._preconditions(core)
    assert pre["checks"]["canonical_only_terminal_dhr_state_shape_exact"] is True


def test_wrong_qty_fails():
    # qty wrong (set to remainder) while shares correct -> should fail
    core = _make_core(mod.EXPECTED_DHR_REMAINDER, mod.EXPECTED_DHR_REMAINDER)
    pre = mod._preconditions(core)
    assert pre["checks"]["canonical_only_terminal_dhr_state_shape_exact"] is False


def test_wrong_shares_fails():
    # qty correct but shares wrong (set to baseline qty) -> should fail
    core = _make_core(mod.EXPECTED_BASELINE_DHR_QTY, mod.EXPECTED_BASELINE_DHR_QTY)
    pre = mod._preconditions(core)
    assert pre["checks"]["canonical_only_terminal_dhr_state_shape_exact"] is False


def test_both_aliases_set_to_remainder_fails():
    # both qty and shares set to remainder (both alias identical to remainder) -> should fail
    core = _make_core(mod.EXPECTED_DHR_REMAINDER, mod.EXPECTED_DHR_REMAINDER)
    pre = mod._preconditions(core)
    assert pre["checks"]["canonical_only_terminal_dhr_state_shape_exact"] is False
