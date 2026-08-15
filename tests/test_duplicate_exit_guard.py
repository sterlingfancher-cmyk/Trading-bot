from __future__ import annotations

import json
import os
import tempfile

import canonical_exit_guard as ceg


class FakeModule:
    def __init__(self, portfolio: dict, ledger_file: str):
        self.portfolio = portfolio
        self._ledger_file = ledger_file

    def exit_position(self, core, symbol: str = None, side: str = "long", qty: float = 0.0, price: float = 0.0):
        """
        Minimal stand-in for a real exit_position implementation.
        It mutates core.portfolio and appends a canonical row to the ledger file.
        The guard should wrap this and prevent it from being called for duplicate exits.
        """
        # Mutate the in-memory portfolio: remove position if present
        try:
            positions = self.portfolio.setdefault("positions", {})
            positions.pop(symbol, None)
        except Exception:
            pass
        # Append a canonical-like exit row
        row = {
            "action": "exit",
            "symbol": symbol,
            "side": side,
            "qty": float(qty),
            "price": float(price),
            "exec_id": "simulated-exit",
        }
        with open(self._ledger_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        return {"status": "exited", "symbol": symbol}


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_tem_duplicate_full_exit_blocking_flow():
    # Create a temporary ledger file
    tmpdir = tempfile.mkdtemp()
    ledger = os.path.join(tmpdir, "canonical_execution_ledger.jsonl")

    # TEM canonical sequence: entry then first full exit
    entry_row = {"action": "entry", "symbol": "TEM", "side": "long", "qty": 29.640567, "price": 54.885, "exec_id": "d647d8a0580b44edbab0224e6c339bfd"}
    first_exit_row = {"action": "exit", "symbol": "TEM", "side": "long", "qty": 29.640567, "price": 53.105, "exec_id": "7b13d9194a23407f926667b2f48d4057"}

    # Start ledger with only entry -> guard should allow an exit
    _write_jsonl(ledger, [entry_row])

    portfolio = {"positions": {"TEM": {"qty": 29.640567}}, "cash": 10000.0}
    mod = FakeModule(portfolio, ledger)

    # Install guard into our fake module using the test ledger
    install_meta = ceg.install_into_module(mod, ledger_file=ledger)
    assert install_meta.get("status") == "ok"

    # First exit attempt should be allowed (original exit_position will run)
    res1 = mod.exit_position(mod, symbol="TEM", side="long", qty=29.640567, price=53.105)
    assert isinstance(res1, dict) and res1.get("status") == "exited"

    # Ledger should now contain both the entry and the first exit
    with open(ledger, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    assert len(lines) == 2
    parsed = [json.loads(l) for l in lines]
    assert any(p.get("action") == "entry" for p in parsed)
    assert any(p.get("action") == "exit" for p in parsed)

    # Second stale/resurrected exit attempt should be blocked by the guard
    res2 = mod.exit_position(mod, symbol="TEM", side="long", qty=29.640567, price=52.905)
    # Guard returns a diagnostic dict when blocking
    assert isinstance(res2, dict) and res2.get("status") == "blocked_duplicate_full_exit"

    # Ledger file must be unchanged (still 2 rows)
    with open(ledger, "r", encoding="utf-8") as f:
        lines_after = [l.strip() for l in f if l.strip()]
    assert len(lines_after) == 2

    # Portfolio should remain without the TEM position (it was removed by the first exit)
    assert "TEM" not in portfolio.get("positions", {})

    # And the module should have stored a diagnostic marker
    assert portfolio.get("duplicate_exit_guard_last", {}).get("status") == "blocked_duplicate_full_exit"


def test_guard_does_not_infer_closure_for_verified_snapshot_without_canonical_entry():
    # If the canonical ledger has no entries for the symbol, the guard must NOT block.
    tmpdir = tempfile.mkdtemp()
    ledger = os.path.join(tmpdir, "canonical_execution_ledger.jsonl")

    # Empty ledger
    _write_jsonl(ledger, [])

    portfolio = {"positions": {"FOO": {"qty": 10.0}}, "cash": 10000.0}
    mod = FakeModule(portfolio, ledger)

    ceg.install_into_module(mod, ledger_file=ledger)

    # Attempt to exit FOO: guard should allow because there is no canonical entry history
    res = mod.exit_position(mod, symbol="FOO", side="long", qty=10.0, price=5.0)
    assert isinstance(res, dict) and res.get("status") == "exited"

    # Ledger should have one row now (the exit we just appended)
    with open(ledger, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    assert len(lines) == 1
