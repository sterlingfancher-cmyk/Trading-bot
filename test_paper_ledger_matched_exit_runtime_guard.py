import json
import types

import canonical_execution_ledger as ledger
import paper_ledger_matched_exit_guard as guard


class FakeCore:
    def __init__(self, *, symbol="TEM", side="long", shares=29.640567, entry=54.885):
        self.exit_calls = 0
        self.save_calls = 0
        self.portfolio = {
            "cash": 11500.0,
            "equity": 13000.0,
            "accounting_epoch_id": "stable-paper-v2-20260812-verified01",
            "paper_accounting_epoch": {
                "id": "stable-paper-v2-20260812-verified01",
                "epoch_id": "stable-paper-v2-20260812-verified01",
                "baseline_type": "verified_snapshot_with_open_position",
            },
            "positions": {
                symbol: {
                    "side": side,
                    "shares": shares,
                    "entry": entry,
                    "last_price": entry,
                }
            },
            "risk_controls": {"halted": False, "halt_reason": ""},
            "trades": [],
        }

    def local_ts_text(self):
        return "2026-08-18 13:30:00 CDT"

    def save_state(self, state=None):
        self.save_calls += 1

    def exit_position(self, symbol, px, reason, market_mode=None, extra=None):
        self.exit_calls += 1
        pos = self.portfolio["positions"].get(symbol)
        if not pos:
            return None
        shares = float(pos.get("shares", 0.0))
        if pos.get("side", "long") == "long":
            self.portfolio["cash"] += shares * float(px)
        del self.portfolio["positions"][symbol]
        return {"symbol": symbol, "price": px, "shares": shares, "reason": reason}


def _set_ledger(tmp_path, monkeypatch):
    path = tmp_path / "canonical_execution_ledger.jsonl"
    monkeypatch.setattr(ledger, "LEDGER_FILE", str(path))
    return path


def test_literal_tem_second_full_exit_is_blocked_before_any_state_mutation(tmp_path, monkeypatch):
    path = _set_ledger(tmp_path, monkeypatch)
    core = FakeCore()
    ids = iter([
        "d647d8a0580b44edbab0224e6c339bfd",
        "7b13d9194a23407f926667b2f48d4057",
    ])
    monkeypatch.setattr(ledger.uuid, "uuid4", lambda: types.SimpleNamespace(hex=next(ids)))

    ledger.append_execution("entry", "TEM", "long", 54.885, 29.640567, {}, core)
    ledger.append_execution("exit", "TEM", "long", 53.105, 29.640567, {}, core)

    rows_before = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["execution_id"] for row in rows_before] == [
        "d647d8a0580b44edbab0224e6c339bfd",
        "7b13d9194a23407f926667b2f48d4057",
    ]

    cash_before = core.portfolio["cash"]
    guard.apply(core)
    result = core.exit_position("TEM", 52.905, "stop_loss")

    assert result is None
    assert core.exit_calls == 0
    assert core.portfolio["cash"] == cash_before
    assert core.portfolio["positions"]["TEM"]["shares"] == 29.640567
    assert core.save_calls == 1

    rows_after = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows_after == rows_before

    risk = core.portfolio["risk_controls"]
    assert risk["halted"] is True
    block = risk["canonical_full_exit_preflight_block"]
    assert block["boundary"] == "exit_position_pre_mutation"
    assert block["symbol"] == "TEM"
    assert block["reason"] == "canonical_position_already_closed"
    assert block["canonical_remaining_qty"] == 0.0


def test_verified_snapshot_baseline_position_without_canonical_entry_remains_manageable(tmp_path, monkeypatch):
    path = _set_ledger(tmp_path, monkeypatch)
    path.write_text("")
    core = FakeCore(symbol="LRCX", shares=3.42486, entry=312.90)
    core.portfolio["paper_accounting_epoch"]["verified_snapshot_baseline"] = {
        "verified": True,
        "positions": {
            "LRCX": {
                "side": "long",
                "qty": 3.42486,
                "entry_price": 312.90,
            }
        },
    }

    guard.apply(core)
    result = core.exit_position("LRCX", 333.12, "target")

    assert result is not None
    assert core.exit_calls == 1
    assert "LRCX" not in core.portfolio["positions"]
    assert core.portfolio["risk_controls"].get("canonical_full_exit_preflight_block") is None


def test_malformed_canonical_ledger_fails_closed_before_full_exit(tmp_path, monkeypatch):
    path = _set_ledger(tmp_path, monkeypatch)
    path.write_text("{not-json}\n")
    core = FakeCore(symbol="QQQ", shares=2.218803, entry=730.92)
    cash_before = core.portfolio["cash"]

    guard.apply(core)
    result = core.exit_position("QQQ", 718.0, "stop_loss")

    assert result is None
    assert core.exit_calls == 0
    assert core.portfolio["cash"] == cash_before
    assert "QQQ" in core.portfolio["positions"]
    block = core.portfolio["risk_controls"]["canonical_full_exit_preflight_block"]
    assert block["reason"] == "canonical_execution_ledger_unreadable_for_full_exit"


def test_runtime_position_without_canonical_entry_or_verified_baseline_fails_closed(tmp_path, monkeypatch):
    path = _set_ledger(tmp_path, monkeypatch)
    path.write_text("")
    core = FakeCore(symbol="QQQ", shares=2.218803, entry=730.92)

    guard.apply(core)
    result = core.exit_position("QQQ", 718.0, "stop_loss")

    assert result is None
    assert core.exit_calls == 0
    block = core.portfolio["risk_controls"]["canonical_full_exit_preflight_block"]
    assert block["reason"] == "canonical_entry_missing_for_runtime_position"
