from __future__ import annotations

import copy
import json
import threading
import types

import canonical_execution_ledger as ledger
import entry_pipeline_composition_guard as composition
import final_daily_audit_compactor as compact
import state_io_hardening as state_io
import state_transaction_manager as transactions
import system_sentinel


EPOCH = "verified-v4-test"


def _trade(execution_id: str) -> dict:
    return {
        "execution_id": execution_id,
        "accounting_epoch_id": EPOCH,
        "action": "entry",
        "symbol": "GEV",
        "side": "short",
        "price": 920.93,
        "shares": 1.091006,
    }


def test_state_io_blocks_same_epoch_execution_regression(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    current = {"accounting_epoch_id": EPOCH, "trades": [_trade("gev-entry")], "cash": 9000.0}
    path.write_text(json.dumps(current), encoding="utf-8")
    core = types.SimpleNamespace(
        STATE_FILE=str(path),
        portfolio=copy.deepcopy(current),
        load_state=lambda: copy.deepcopy(current),
        save_state=lambda state: None,
    )
    monkeypatch.setattr(state_io, "STATE_LOCK_FILE", str(tmp_path / ".lock"))
    monkeypatch.setattr(state_io, "STATE_BACKUP_LATEST", str(tmp_path / "latest.json"))
    monkeypatch.setattr(state_io, "STATE_BACKUP_LARGEST", str(tmp_path / "largest.json"))
    monkeypatch.setattr(state_io, "STATE_BACKUP_PREWRITE", str(tmp_path / "prewrite.json"))
    monkeypatch.setattr(state_io, "STATE_IO_STATUS_FILE", str(tmp_path / "status.json"))

    state_io.install(core)
    stale = {"accounting_epoch_id": EPOCH, "trades": [], "cash": 10000.0}
    try:
        core.save_state(stale)
        assert False, "regressive save must fail closed"
    except RuntimeError as exc:
        assert "remove committed same-epoch execution ids" in str(exc)

    assert json.loads(path.read_text()) == current
    assert core.portfolio == current
    assert state_io.status_payload(core)["last_status_event"] == "execution_regression_blocked"


def test_state_io_allows_append_and_successor_epoch(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    current = {"accounting_epoch_id": EPOCH, "trades": [_trade("a")], "cash": 9000.0}
    path.write_text(json.dumps(current), encoding="utf-8")
    core = types.SimpleNamespace(
        STATE_FILE=str(path), portfolio=copy.deepcopy(current),
        load_state=lambda: copy.deepcopy(current), save_state=lambda state: None,
    )
    monkeypatch.setattr(state_io, "STATE_LOCK_FILE", str(tmp_path / ".lock"))
    monkeypatch.setattr(state_io, "STATE_BACKUP_LATEST", str(tmp_path / "latest.json"))
    monkeypatch.setattr(state_io, "STATE_BACKUP_LARGEST", str(tmp_path / "largest.json"))
    monkeypatch.setattr(state_io, "STATE_BACKUP_PREWRITE", str(tmp_path / "prewrite.json"))
    monkeypatch.setattr(state_io, "STATE_IO_STATUS_FILE", str(tmp_path / "status.json"))
    state_io.install(core)

    appended = copy.deepcopy(current)
    appended["trades"].append(_trade("b"))
    core.save_state(appended)
    assert len(json.loads(path.read_text())["trades"]) == 2

    successor = {"accounting_epoch_id": "successor", "trades": [], "cash": 10000.0}
    core.save_state(successor)
    assert json.loads(path.read_text())["accounting_epoch_id"] == "successor"


def test_composition_status_uses_transactional_update_without_stale_replacement():
    original_portfolio = {"accounting_epoch_id": EPOCH, "trades": [_trade("gev-entry")]}
    calls = []

    def update_state(updater, *, source):
        calls.append(source)
        updater(original_portfolio)
        return {"status": "ok", "written": True}

    core = types.SimpleNamespace(
        portfolio=original_portfolio,
        update_state=update_state,
        load_state=lambda: {"accounting_epoch_id": EPOCH, "trades": []},
        save_state=lambda state: (_ for _ in ()).throw(AssertionError("fallback save used")),
    )
    payload = {"status": "ok"}
    composition._save_payload(core, payload)
    assert calls == ["entry_pipeline_composition_guard"]
    assert core.portfolio["trades"][0]["execution_id"] == "gev-entry"
    assert core.portfolio["entry_pipeline_composition_guard"] == payload


def test_transaction_waits_for_cycle_lock_before_replacing_portfolio(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    state = {"accounting_epoch_id": EPOCH, "trades": [_trade("gev-entry")], "cash": 9000.0}
    path.write_text(json.dumps(state), encoding="utf-8")
    core = types.SimpleNamespace(STATE_FILE=str(path), portfolio=copy.deepcopy(state))
    monkeypatch.setattr(state_io, "STATE_LOCK_FILE", str(tmp_path / ".lock"))
    monkeypatch.setattr(state_io, "STATE_BACKUP_LATEST", str(tmp_path / "latest.json"))
    monkeypatch.setattr(state_io, "STATE_BACKUP_LARGEST", str(tmp_path / "largest.json"))
    monkeypatch.setattr(state_io, "STATE_BACKUP_PREWRITE", str(tmp_path / "prewrite.json"))
    transactions.install(core)

    finished = threading.Event()
    with state_io._RUN_LOCK:
        worker = threading.Thread(
            target=lambda: (core.update_state(lambda row: row.update({"telemetry": True}), source="test"), finished.set())
        )
        worker.start()
        assert not finished.wait(0.05)
    worker.join(timeout=1.0)
    assert finished.is_set()
    assert core.portfolio["trades"][0]["execution_id"] == "gev-entry"

    try:
        core.update_state(lambda row: {"accounting_epoch_id": EPOCH, "trades": []}, source="regressive-test")
        assert False, "transactional execution regression must fail closed"
    except RuntimeError as exc:
        assert "remove committed same-epoch execution ids" in str(exc)
    assert json.loads(path.read_text())["trades"][0]["execution_id"] == "gev-entry"


def test_ledger_parity_fails_audit_and_sentinel(monkeypatch):
    row = _trade("gev-entry")
    core = types.SimpleNamespace(
        portfolio={"accounting_epoch_id": EPOCH, "trades": []},
        record_trade=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(ledger, "_read_rows", lambda: ([row], []))
    monkeypatch.setattr(ledger, "_verify_rows", lambda rows: (True, []))
    ledger._APPLIED_CORE_IDS.add(id(core))
    core.record_trade._canonical_execution_ledger_version = ledger.VERSION

    status = ledger.status_payload(core)
    assert status["overall"] == "fail"
    assert status["state_projection_parity"] is False
    assert status["missing_from_state_execution_ids"] == ["gev-entry"]

    monkeypatch.setattr(compact, "_ledger_status", lambda core=None: status)
    monkeypatch.setattr(compact, "_journal_status", lambda core=None: {})
    audit = compact.compact_payload({"status": "ok", "overall": "pass", "sections": {}}, core)
    assert audit["overall"] == "fail"
    assert "canonical_state_projection_parity_failed" in audit["summary"]["reasons"]

    report = system_sentinel.report({"execution_ledger": status})
    assert report["status"] == "incident"
    assert report["incidents"][0]["reason_code"] == "execution_projection_divergence"
