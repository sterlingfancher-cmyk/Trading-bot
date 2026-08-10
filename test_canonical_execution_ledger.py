import json
import types

import canonical_execution_ledger as ledger
import final_daily_audit_compactor as compact


def _core():
    calls = []

    def record_trade(action, symbol, side, px, shares, extra=None):
        calls.append({
            "action": action,
            "symbol": symbol,
            "side": side,
            "price": px,
            "shares": shares,
            **(extra or {}),
        })

    core = types.SimpleNamespace(
        portfolio={"risk_controls": {"halted": False}, "accounting_epoch_id": "epoch-test"},
        record_trade=record_trade,
        local_ts_text=lambda: "2026-08-10 13:00:00 CDT",
    )
    return core, calls


def test_records_hash_chained_execution_and_links_state_trade(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_FILE", str(tmp_path / "ledger.jsonl"))
    core, calls = _core()
    out = ledger.apply(core)
    assert out["hook_applied"] is True

    core.record_trade("entry", "qqq", "long", 100, 2, {"alloc": 200})
    core.record_trade("exit", "QQQ", "long", 105, 2, {"exit_reason": "target"})

    status = ledger.status_payload(core)
    assert status["chain_valid"] is True
    assert status["row_count"] == 2
    assert status["current_epoch_rows"] == 2
    assert status["authoritative_for_new_executions"] is True
    assert calls[0]["execution_id"]
    assert calls[0]["canonical_ledger_event_hash"]
    assert calls[0]["accounting_epoch_id"] == "epoch-test"

    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert rows[1]["previous_event_hash"] == rows[0]["event_hash"]


def test_tamper_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_FILE", str(tmp_path / "ledger.jsonl"))
    core, _ = _core()
    ledger.apply(core)
    core.record_trade("entry", "QQQ", "long", 100, 2, {})

    path = tmp_path / "ledger.jsonl"
    row = json.loads(path.read_text().strip())
    row["price"] = 999
    path.write_text(json.dumps(row) + "\n")

    status = ledger.status_payload(core)
    assert status["chain_valid"] is False
    assert status["overall"] == "fail"


def test_ledger_failure_halts_without_overwriting_existing_halt(monkeypatch):
    core, calls = _core()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ledger, "append_execution", boom)
    ledger.apply(core)
    core.record_trade("entry", "QQQ", "long", 100, 1, {})
    assert core.portfolio["risk_controls"]["halted"] is True
    assert core.portfolio["risk_controls"]["halt_reason"] == "canonical execution ledger write failed"
    assert "canonical_execution_ledger_error" in calls[0]

    core2, _ = _core()
    core2.portfolio["risk_controls"] = {"halted": True, "halt_reason": "existing accounting halt"}
    ledger.apply(core2)
    core2.record_trade("entry", "QQQ", "long", 100, 1, {})
    assert core2.portfolio["risk_controls"]["halt_reason"] == "existing accounting halt"


def test_compact_daily_audit_exposes_canonical_ledger(monkeypatch):
    monkeypatch.setattr(
        compact,
        "_ledger_status",
        lambda core=None: {
            "status": "ok",
            "chain_valid": True,
            "row_count": 4,
            "current_epoch_id": "epoch-test",
            "current_epoch_rows": 4,
            "authoritative_for_new_executions": True,
        },
    )
    monkeypatch.setattr(compact, "_journal_status", lambda core=None: {})
    out = compact.compact_payload({"sections": {}}, None)
    assert out["execution_ledger"]["status"] == "ok"
    assert out["execution_ledger"]["chain_valid"] is True
    assert out["execution_ledger"]["row_count"] == 4
