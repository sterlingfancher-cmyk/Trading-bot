import copy
import sys
import types

import verified_v2_successor_epoch_migration as migration
import verified_v2_successor_epoch_precondition_compatibility as compat


def _portfolio():
    return {
        "cash": 13357.874520862653,
        "equity": 13535.92,
        "positions": {
            "DHR": {"side": "long", "shares": 0.540748758, "entry": 216.960007, "last_price": 215.62},
            "SLS": {"side": "long", "shares": 4.353086829, "entry": 14.335, "last_price": 13.995},
        },
        "accounting_epoch_id": migration.OLD_EPOCH_ID,
        "paper_accounting_epoch": {"id": migration.OLD_EPOCH_ID},
    }


def _tem_issue():
    return {
        "symbol": "TEM",
        "action": "exit",
        "reason": "exit_exceeds_reconstructed_position",
        "requested_qty": migration.TEM_DUPLICATE_QTY,
        "price": migration.TEM_DUPLICATE_PRICE,
    }


def _production_result():
    return {
        "status": "partial",
        "coverage_complete": False,
        "coverage_issues": [_tem_issue()],
        "coverage_issue_count": 1,
        "economic_issues": [],
        "economic_issue_count": 0,
        "cash": 13357.874573,
        "equity": 13535.392322,
        "open_positions": {
            "DHR": {"side": "long", "qty": 0.540749, "entry_price": 216.96, "last_price": 215.6199951171875},
            "SLS": {"side": "long", "qty": 4.353087, "entry_price": 14.335, "last_price": 13.994999885559082},
        },
    }


def _core():
    return types.SimpleNamespace(portfolio=_portfolio())


def test_authoritative_production_shape_allows_only_exact_tem_issue(monkeypatch):
    result = _production_result()
    fake = types.SimpleNamespace(analyze_ledger=lambda pf, core: copy.deepcopy(result))
    monkeypatch.setitem(sys.modules, "paper_bidirectional_accounting_guard", fake)

    observed, ready = compat._production_active_accounting_evidence(migration, _core())

    assert ready is True
    assert observed["coverage_issue_count"] == 1
    assert observed["economic_issue_count"] == 0


def test_same_exact_tem_issue_may_be_mirrored_once_in_each_collection(monkeypatch):
    result = _production_result()
    result["economic_issues"] = [_tem_issue()]
    result["economic_issue_count"] = 1
    fake = types.SimpleNamespace(analyze_ledger=lambda pf, core: copy.deepcopy(result))
    monkeypatch.setitem(sys.modules, "paper_bidirectional_accounting_guard", fake)

    _, ready = compat._production_active_accounting_evidence(migration, _core())
    assert ready is True


def test_any_additional_or_non_tem_issue_fails_closed(monkeypatch):
    result = _production_result()
    result["economic_issues"] = [{
        "symbol": "TOST",
        "action": "exit",
        "reason": "exit_exceeds_reconstructed_position",
        "requested_qty": 1.0,
        "price": 36.0,
    }]
    result["economic_issue_count"] = 1
    fake = types.SimpleNamespace(analyze_ledger=lambda pf, core: copy.deepcopy(result))
    monkeypatch.setitem(sys.modules, "paper_bidirectional_accounting_guard", fake)

    _, ready = compat._production_active_accounting_evidence(migration, _core())
    assert ready is False


def test_cash_position_or_material_equity_mismatch_fails_closed(monkeypatch):
    cases = []
    cash_bad = _production_result(); cash_bad["cash"] += 0.02; cases.append(cash_bad)
    equity_bad = _production_result(); equity_bad["equity"] -= compat.EQUITY_MARK_DRIFT_TOLERANCE + 1.0; cases.append(equity_bad)
    qty_bad = _production_result(); qty_bad["open_positions"]["SLS"]["qty"] += 0.001; cases.append(qty_bad)

    fake = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "paper_bidirectional_accounting_guard", fake)
    for result in cases:
        fake.analyze_ledger = lambda pf, core, row=result: copy.deepcopy(row)
        _, ready = compat._production_active_accounting_evidence(migration, _core())
        assert ready is False


def test_apply_changes_only_successor_evidence_reader(monkeypatch):
    original = migration._active_accounting_evidence
    monkeypatch.setattr(migration, "_active_accounting_evidence", original)
    compat._APPLIED = False

    status = compat.apply(_core())

    assert status["overall"] == "pass"
    assert getattr(migration._active_accounting_evidence, "_production_shape_compatibility_version", None) == compat.VERSION
    authority = status["authority"]
    assert authority["writes_state"] is False
    assert authority["edits_or_deletes_canonical_rows"] is False
    assert authority["rewrites_current_day_peak"] is False
    assert authority["clears_hard_halt"] is False
    assert authority["places_orders"] is False
    assert authority["changes_strategy"] is False
    assert authority["changes_thresholds"] is False
    assert authority["changes_risk_or_sizing"] is False
    assert authority["changes_live_or_ml_authority"] is False
