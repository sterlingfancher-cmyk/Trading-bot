import contextlib
import copy
import os
import sys
import types

import verified_v2_successor_epoch_migration as migration


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
        "coverage_issues": [{
            "symbol": "TEM", "action": "exit", "reason": "exit_exceeds_reconstructed_position",
            "requested_qty": migration.TEM_DUPLICATE_QTY, "price": migration.TEM_DUPLICATE_PRICE,
        }],
        "economic_issues": [{
            "symbol": "TEM", "action": "exit", "reason": "exit_exceeds_reconstructed_position",
            "requested_qty": migration.TEM_DUPLICATE_QTY, "price": migration.TEM_DUPLICATE_PRICE,
        }],
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
