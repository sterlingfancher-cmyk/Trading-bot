import contextlib
import copy
import os
import sys
import types

import verified_v2_successor_epoch_migration as migration
import verified_v2_successor_epoch_migration_precondition_compatibility as compat


def _portfolio():
    return {
        "cash": 13357.874520862653,
        "equity": 13537.44,
        "positions": {
            "DHR": {"side": "long", "shares": 0.540748758, "entry": 216.960007, "last_price": 215.79},
            "SLS": {"side": "long", "shares": 4.353086829, "entry": 14.335, "last_price": 14.45},
        },
        "trades": [{"execution_id": "historical-row"}],
        "history": [13500.0, 13537.44],
        "realized_pnl": {"today": 1.83, "total": 42.0},
        "performance": {"realized_pnl_today": 1.83, "realized_pnl_total": 42.0},
        "risk_controls": {
            "date": "2026-08-25",
            "day_start_equity": 13536.430460509137,
            "day_peak_equity": 13546.272788435168,
            "halted": False,
            "halt_reason": None,
            "intraday_drawdown_pct": 0.059,
        },
        "accounting_epoch_id": migration.OLD_EPOCH_ID,
        "paper_accounting_epoch": {
            "id": migration.OLD_EPOCH_ID,
            "validation_hold": True,
            "historical_evidence_archived": True,
        },
    }


def _tem_issue():
    return {
        "symbol": "TEM",
        "action": "exit",
        "reason": "exit_exceeds_reconstructed_position",
        "requested_qty": migration.TEM_DUPLICATE_QTY,
        "price": migration.TEM_DUPLICATE_PRICE,
    }


def _production_portfolio():
    pf = _portfolio()
    pf["equity"] = 13535.92
    pf["positions"]["DHR"]["last_price"] = 215.62
    pf["positions"]["SLS"]["last_price"] = 13.995
    return pf


def _production_accounting_result():
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


def test_successor_state_preserves_current_economics_and_risk_exactly():
    before = _portfolio()
    original = copy.deepcopy(before)
    after = migration.build_successor_state(before, "/archive/evidence", "2026-08-25 15:05:00 CDT")

    assert before == original
    for key in ("cash", "equity", "positions", "history", "realized_pnl", "performance", "risk_controls"):
        assert after[key] == original[key]
    assert after["trades"] == []
    assert after["accounting_epoch_id"] == migration.TARGET_EPOCH_ID
    epoch = after["paper_accounting_epoch"]
    assert epoch["id"] == migration.TARGET_EPOCH_ID
    assert epoch["prior_epoch_id"] == migration.OLD_EPOCH_ID
    assert epoch["validation_hold"] is True
    assert epoch["historical_evidence_archived"] is True
    assert epoch["forensic_archive_dir"] == "/archive/evidence"
    assert epoch["baseline_type"] == "verified_snapshot_with_open_position"
    snap = epoch["verified_snapshot_baseline"]
    assert snap["cash"] == original["cash"]
    assert snap["equity"] == original["equity"]
    assert snap["realized_today"] == 1.83
    assert snap["positions"]["DHR"]["qty"] == original["positions"]["DHR"]["shares"]


def test_exact_tem_duplicate_is_the_only_allowed_active_accounting_issue(monkeypatch):
    result = {
        "coverage_issues": [_tem_issue()],
        "economic_issues": [_tem_issue()],
        "coverage_issue_count": 1,
        "economic_issue_count": 1,
        "reconstructed_cash": 13357.87452,
        "reconstructed_equity": 13537.44,
        "reconstructed_open_positions": ["DHR", "SLS"],
    }
    fake = types.SimpleNamespace(analyze_ledger=lambda pf, core: copy.deepcopy(result))
    monkeypatch.setitem(sys.modules, "paper_bidirectional_accounting_guard", fake)
    core = types.SimpleNamespace(portfolio=_portfolio())
    observed, ready = migration._active_accounting_evidence(core)
    assert ready is True
    assert observed["coverage_issue_count"] == 1

    bad = copy.deepcopy(result)
    bad["coverage_issues"].append({"symbol": "TOST", "action": "exit", "reason": "exit_exceeds_reconstructed_position", "requested_qty": 1.0, "price": 36.0})
    fake.analyze_ledger = lambda pf, core: copy.deepcopy(bad)
    _, ready = migration._active_accounting_evidence(core)
    assert ready is False


def test_production_accounting_shape_allows_exact_tem_coverage_issue_only(monkeypatch):
    result = _production_accounting_result()
    fake = types.SimpleNamespace(analyze_ledger=lambda pf, core: copy.deepcopy(result))
    monkeypatch.setitem(sys.modules, "paper_bidirectional_accounting_guard", fake)
    core = types.SimpleNamespace(portfolio=_production_portfolio())

    observed, ready = compat._production_active_accounting_evidence(migration, core)

    assert ready is True
    assert observed["coverage_issue_count"] == 1
    assert observed["economic_issue_count"] == 0


def test_production_precondition_fails_closed_on_any_second_issue(monkeypatch):
    result = _production_accounting_result()
    result["economic_issues"] = [{
        "symbol": "TOST", "action": "exit", "reason": "exit_exceeds_reconstructed_position",
        "requested_qty": 1.0, "price": 36.0,
    }]
    result["economic_issue_count"] = 1
    fake = types.SimpleNamespace(analyze_ledger=lambda pf, core: copy.deepcopy(result))
    monkeypatch.setitem(sys.modules, "paper_bidirectional_accounting_guard", fake)

    _, ready = compat._production_active_accounting_evidence(
        migration, types.SimpleNamespace(portfolio=_production_portfolio())
    )
    assert ready is False


def test_production_precondition_fails_closed_on_state_mismatch(monkeypatch):
    fake = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "paper_bidirectional_accounting_guard", fake)
    core = types.SimpleNamespace(portfolio=_production_portfolio())

    cash_bad = _production_accounting_result(); cash_bad["cash"] += 0.02
    equity_bad = _production_accounting_result(); equity_bad["equity"] -= compat.EQUITY_MARK_DRIFT_TOLERANCE + 1.0
    qty_bad = _production_accounting_result(); qty_bad["open_positions"]["SLS"]["qty"] += 0.001
    for result in (cash_bad, equity_bad, qty_bad):
        fake.analyze_ledger = lambda pf, runtime_core, row=result: copy.deepcopy(row)
        _, ready = compat._production_active_accounting_evidence(migration, core)
        assert ready is False


def test_production_compatibility_adds_no_state_or_trading_authority():
    status = compat.status_payload(None)
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


def test_exact_completed_v3_marker_with_verified_v2_reversion_defers_only_to_finalizer(monkeypatch):
    marker = {
        "status": "completed",
        "target_epoch_id": migration.TARGET_EPOCH_ID,
        "prior_epoch_id": migration.OLD_EPOCH_ID,
        "canonical_ledger_unchanged": True,
        "archive_dir": "/archive/issue82",
    }
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(marker))
    core = types.SimpleNamespace(portfolio=_portfolio())
    original = {
        "status": "error",
        "overall": "fail",
        "reason": "completed_marker_present_but_successor_epoch_not_active",
    }

    result = compat._defer_exact_interrupted_completion_error(migration, core, original)

    assert result["status"] == "pending_finalizer"
    assert result["overall"] == "warn"
    assert result["reason"] == "exact_interrupted_completion_deferred_to_finalizer"
    assert result["active_epoch_id"] == migration.OLD_EPOCH_ID
    assert result["target_epoch_id"] == migration.TARGET_EPOCH_ID
    assert result["canonical_ledger_unchanged"] is True
    assert result["finalizer_retry_owner"] == "verified_v2_successor_epoch_migration_finalizer"
    assert result["writes_state"] is False


def test_successor_startup_deferral_fails_closed_on_marker_epoch_or_error_mismatch(monkeypatch):
    exact = {
        "status": "completed",
        "target_epoch_id": migration.TARGET_EPOCH_ID,
        "prior_epoch_id": migration.OLD_EPOCH_ID,
        "canonical_ledger_unchanged": True,
    }
    startup_error = {
        "status": "error",
        "overall": "fail",
        "reason": "completed_marker_present_but_successor_epoch_not_active",
    }
    core = types.SimpleNamespace(portfolio=_portfolio())
    for field, value in (
        ("status", "cutover_started"),
        ("target_epoch_id", "wrong-target"),
        ("prior_epoch_id", "wrong-prior"),
        ("canonical_ledger_unchanged", False),
    ):
        marker = {**exact, field: value}
        monkeypatch.setattr(migration, "_marker", lambda row=marker: copy.deepcopy(row))
        result = compat._defer_exact_interrupted_completion_error(migration, core, startup_error)
        assert result == startup_error

    unexpected_epoch = {
        **_portfolio(),
        "accounting_epoch_id": "unexpected-epoch",
        "paper_accounting_epoch": {"id": "unexpected-epoch", "validation_hold": True},
    }
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(exact))
    result = compat._defer_exact_interrupted_completion_error(
        migration, types.SimpleNamespace(portfolio=unexpected_epoch), startup_error
    )
    assert result == startup_error

    unrelated = {"status": "error", "overall": "fail", "reason": "different_failure"}
    result = compat._defer_exact_interrupted_completion_error(migration, core, unrelated)
    assert result == unrelated


def test_successor_startup_apply_wrapper_does_not_write_state(monkeypatch):
    marker = {
        "status": "completed",
        "target_epoch_id": migration.TARGET_EPOCH_ID,
        "prior_epoch_id": migration.OLD_EPOCH_ID,
        "canonical_ledger_unchanged": True,
    }
    monkeypatch.setattr(migration, "_marker", lambda: copy.deepcopy(marker))
    core = types.SimpleNamespace(portfolio=_portfolio())
    before = copy.deepcopy(core.portfolio)
    calls = {"original": 0}

    def original(runtime_core=None):
        calls["original"] += 1
        assert runtime_core is core
        return {
            "status": "error",
            "overall": "fail",
            "reason": "completed_marker_present_but_successor_epoch_not_active",
        }

    monkeypatch.setattr(migration, "apply", original)
    compat._install_migration_apply_compatibility(migration)
    result = migration.apply(core)

    assert result["status"] == "pending_finalizer"
    assert calls["original"] == 1
    assert core.portfolio == before


def test_successor_startup_compatibility_keeps_finalizer_as_only_retry_owner():
    authority = compat.status_payload(None)["authority"]
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


def test_recovery_gate_must_be_exact_and_mechanically_complete(monkeypatch):
    payload = {
        "overall": "pass",
        "all_known_invalid_signatures_exact": True,
        "known_invalid_execution_count": 11,
        "ledger": {"chain_valid": True, "epoch_ids": [migration.OLD_EPOCH_ID], "row_count": 42},
        "recovery_readiness": {
            "counterfactual_successor_projection_mechanically_reproducible": True,
            "all_canonical_rows_accounted_for": True,
            "mechanically_complete_for_successor_migration_design": True,
        },
    }
    fake = types.SimpleNamespace(status_payload=lambda core: copy.deepcopy(payload))
    monkeypatch.setitem(sys.modules, "verified_v2_successor_replay_status", fake)
    _, ready = migration._gate_evidence(types.SimpleNamespace())
    assert ready is True

    payload["known_invalid_execution_count"] = 10
    _, ready = migration._gate_evidence(types.SimpleNamespace())
    assert ready is False


def test_cutover_never_changes_or_rotates_canonical_ledger(monkeypatch, tmp_path):
    ledger_path = tmp_path / "canonical_execution_ledger.jsonl"
    ledger_bytes = b'{"event_hash":"immutable-row"}\n'
    ledger_path.write_bytes(ledger_bytes)

    fake_ledger = types.SimpleNamespace(LEDGER_FILE=str(ledger_path))
    saved = {}

    def write_state(core, state):
        saved["state"] = copy.deepcopy(state)
        return str(tmp_path / "state.json")

    fake_clean = types.SimpleNamespace(
        _runtime_locks=lambda: contextlib.nullcontext(),
        _write_clean_state_and_backups=write_state,
        _reset_snapshot_archive=lambda state, path: None,
    )
    monkeypatch.setitem(sys.modules, "canonical_execution_ledger", fake_ledger)
    monkeypatch.setitem(sys.modules, "clean_accounting_epoch", fake_clean)
    monkeypatch.setattr(migration, "_archive_state", lambda *args, **kwargs: {"archive_dir": str(tmp_path / "archive")})
    monkeypatch.setattr(migration, "_rotate_journal_for_successor", lambda state: None)
    marker = tmp_path / "marker.json"
    monkeypatch.setattr(migration, "MARKER_FILE", str(marker))

    core = types.SimpleNamespace(portfolio=_portfolio(), local_ts_text=lambda: "2026-08-25 15:05:00 CDT")
    result = migration._cutover(core, {"ledger": {"row_count": 42}}, {})

    assert ledger_path.read_bytes() == ledger_bytes
    assert result["canonical_ledger_unchanged"] is True
    assert core.portfolio["accounting_epoch_id"] == migration.TARGET_EPOCH_ID
    assert saved["state"]["trades"] == []
    assert saved["state"]["risk_controls"] == _portfolio()["risk_controls"]


def test_status_declares_no_trading_or_risk_authority(monkeypatch, tmp_path):
    core = types.SimpleNamespace(portfolio=_portfolio())
    monkeypatch.setattr(migration, "MARKER_FILE", str(tmp_path / "missing.json"))
    payload = migration.status_payload(core)
    authority = payload["authority"]
    assert authority["edits_or_deletes_canonical_rows"] is False
    assert authority["rotates_or_truncates_canonical_ledger"] is False
    assert authority["rewrites_current_day_peak"] is False
    assert authority["clears_hard_halt"] is False
    assert authority["places_orders"] is False
    assert authority["changes_strategy"] is False
    assert authority["changes_thresholds"] is False
    assert authority["changes_risk_or_sizing"] is False
    assert authority["changes_live_or_ml_authority"] is False
