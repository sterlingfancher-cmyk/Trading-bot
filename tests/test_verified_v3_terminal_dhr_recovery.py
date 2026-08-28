import copy
from types import SimpleNamespace

import pytest

import verified_v3_successor_epoch_migration as migration


def _canonical_row(expected):
    row = copy.deepcopy(expected)
    row.pop("economic_disposition", None)
    return row


def _mirrored_trade(expected):
    row = _canonical_row(expected)
    row["canonical_ledger_event_hash"] = row.pop("event_hash")
    return row


def _terminal_dhr_fixture_snapshot():
    return {
        "verified": True,
        "cash": migration.EXPECTED_BASELINE_CASH,
        "equity": migration.EXPECTED_BASELINE_EQUITY,
        "realized_today": 0.0,
        "realized_total": 0.0,
        "positions": {
            "SLS": {
                "side": "long",
                "qty": migration.EXPECTED_BASELINE_SLS_QTY,
                "entry_price": 14.0,
                "mark": 14.0,
            },
            "DHR": {
                "side": "long",
                "qty": migration.EXPECTED_BASELINE_DHR_QTY,
                "entry_price": 216.9600067138672,
                "mark": 203.0,
            },
        },
    }


def _canonical_payload():
    rows = [{} for _ in range(migration.EXPECTED_V3_START_INDEX)]
    rows.extend(_canonical_row(expected) for expected in migration.EXPECTED_V3_ROWS)
    return {"raw_rows": rows}


def _fake_portfolio(current_cash=None, dhr_qty=None):
    if current_cash is None:
        terminal = migration.EXPECTED_V3_ROWS[3]
        invalid = migration.EXPECTED_V3_ROWS[2]
        projection = migration._project(
            SimpleNamespace(portfolio={"positions": {}}),
            _terminal_dhr_fixture_snapshot(),
            _canonical_payload(),
        )
        current_cash = (
            float(projection["cash"])
            + float(invalid["shares"]) * float(invalid["price"])
            - float(terminal["shares"]) * float(terminal["price"])
        )
    if dhr_qty is None:
        dhr_qty = migration.EXPECTED_DHR_REMAINDER
    return {
        "cash": current_cash,
        "positions": {
            "DHR": {
                "side": "long",
                "qty": dhr_qty,
                "entry": 216.9600067138672,
                "last_price": 203.0,
            },
            "SLS": {
                "side": "long",
                "qty": 1.43651871,
                "entry": 14.0,
                "last_price": 16.04,
            },
        },
        "trades": [_mirrored_trade(expected) for expected in migration.MIRRORED_V3_ROWS],
        "risk_controls": {
            "halted": True,
            "halt_reason": "canonical execution lifecycle integrity halt",
        },
    }


def test_fourth_v3_row_is_exact_terminal_dhr_exit():
    expected = migration.EXPECTED_V3_ROWS[3]
    row = _canonical_row(expected)

    checks = migration._signature_checks(row, expected, int(expected["ledger_index"]))

    assert migration.EXPECTED_LEDGER_ROW_COUNT == 46
    assert len(migration.EXPECTED_V3_ROWS) == 4
    assert expected["execution_id"] == migration.TERMINAL_DHR_EXECUTION_ID
    assert all(checks.values())


def test_terminal_dhr_signature_fails_closed_on_event_hash_mismatch():
    expected = migration.EXPECTED_V3_ROWS[3]
    row = _canonical_row(expected)
    row["event_hash"] = "0" * 64

    checks = migration._signature_checks(row, expected, int(expected["ledger_index"]))

    assert checks["event_hash"] is False
    assert all(value for name, value in checks.items() if name != "event_hash")


def test_state_trade_evidence_requires_terminal_dhr_row_to_be_canonical_only():
    pf = {"trades": [_mirrored_trade(expected) for expected in migration.MIRRORED_V3_ROWS]}

    evidence, ready = migration._state_trade_evidence(pf)

    assert ready is True
    assert evidence["state_trade_count"] == 3
    assert evidence["terminal_dhr_execution_absent"] is True

    pf["trades"].append(_mirrored_trade(migration.EXPECTED_V3_ROWS[3]))
    evidence, ready = migration._state_trade_evidence(pf)

    assert ready is False
    assert evidence["terminal_dhr_execution_absent"] is False


def test_projection_replays_terminal_dhr_and_excludes_only_invalid_sls():
    core = SimpleNamespace(portfolio={"positions": {}})

    projection = migration._project(core, _terminal_dhr_fixture_snapshot(), _canonical_payload())

    assert projection["status"] == "ok"
    assert projection["open_symbols"] == []
    assert projection["positions"] == {}
    assert projection["excluded_execution_ids"] == [migration.INVALID_EXECUTION_ID]
    assert projection["valid_execution_ids"] == [
        migration.EXPECTED_V3_ROWS[0]["execution_id"],
        migration.EXPECTED_V3_ROWS[1]["execution_id"],
        migration.TERMINAL_DHR_EXECUTION_ID,
    ]
    assert projection["equity"] == pytest.approx(projection["cash"])


def test_successor_state_is_flat_and_preserves_halt_and_history():
    pf = _fake_portfolio()
    pf["history"] = [13500.0, 13600.0]
    projection = migration._project(
        SimpleNamespace(portfolio=pf),
        _terminal_dhr_fixture_snapshot(),
        _canonical_payload(),
    )

    successor = migration.build_successor_state(pf, projection, "/tmp/archive", "2026-08-28 14:00:00 CDT")

    assert successor["positions"] == {}
    assert successor["trades"] == []
    assert successor["cash"] == pytest.approx(successor["equity"])
    assert successor["risk_controls"] == pf["risk_controls"]
    assert successor["history"] == pf["history"]
    assert successor["paper_accounting_epoch"]["validation_hold"] is True
    assert successor["paper_accounting_epoch"]["terminal_valid_dhr_execution_id"] == migration.TERMINAL_DHR_EXECUTION_ID


def test_preconditions_require_exact_canonical_only_terminal_state_and_cash(monkeypatch):
    pf = _fake_portfolio()
    core = SimpleNamespace(portfolio=pf)
    projection = migration._project(core, _terminal_dhr_fixture_snapshot(), _canonical_payload())

    monkeypatch.setattr(migration, "_paper_only", lambda: True)
    monkeypatch.setattr(migration, "_baseline_snapshot", lambda _pf: (_terminal_dhr_fixture_snapshot(), []))
    monkeypatch.setattr(migration, "_canonical_evidence", lambda _core: (_canonical_payload(), True))
    monkeypatch.setattr(
        migration,
        "_state_trade_evidence",
        lambda _pf: ({"state_trade_count": 3, "state_trade_rows_exact": True, "terminal_dhr_execution_absent": True}, True),
    )
    monkeypatch.setattr(migration, "_project", lambda _core, _snapshot, _canonical: copy.deepcopy(projection))
    monkeypatch.setattr(migration, "_accounting_cross_check", lambda _core, _projection: ({"status": "partial"}, True))

    pre = migration._preconditions(core)
    assert pre["failed"] == []

    pf["cash"] += 1.0
    pre = migration._preconditions(core)
    assert pre["checks"]["canonical_only_terminal_cash_effect_absent"] is False

    pf["cash"] -= 1.0
    pf["positions"]["DHR"]["qty"] += 0.01
    pre = migration._preconditions(core)
    assert pre["checks"]["canonical_only_terminal_dhr_state_shape_exact"] is False
