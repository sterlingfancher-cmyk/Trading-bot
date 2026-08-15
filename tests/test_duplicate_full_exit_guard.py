import os
import json
import tempfile

from canonical_execution_ledger import apply as canonical_apply


class FakeCore:
    def __init__(self, state_path: str):
        self.portfolio = {"trades": []}
        self._record_calls = 0
        self._state_path = state_path

    def record_trade(self, row):
        # Mirror mutation the real system would do; increment a counter so tests
        # can assert whether it was called.
        self._record_calls += 1
        self.portfolio.setdefault("trades", []).append(dict(row))

    def save_state(self, payload):
        # Not used by test mirroring, but keep minimal parity.
        with open(self._state_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)


def _write_canonical_file(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_block_stale_second_full_exit(tmp_path):
    # Use a temp canonical JSONL and instruct module to use it.
    canonical_path = tmp_path / "canonical_executions.jsonl"
    os.environ["CANONICAL_EXECUTION_JSONL"] = str(canonical_path)

    # TEM canonical production rows (only entry + first exit present):
    entry = {
        "execution_id": "d647d8a0580b44edbab0224e6c339bfd",
        "action": "entry",
        "symbol": "TEM",
        "side": "long",
        "shares": 29.640567,
        "price": 54.885,
        "timestamp": 1786647398,
    }
    first_exit = {
        "execution_id": "7b13d9194a23407f926667b2f48d4057",
        "action": "exit",
        "symbol": "TEM",
        "side": "long",
        "shares": 29.640567,
        "price": 53.105,
        "timestamp": 1786714863,
    }
    _write_canonical_file(str(canonical_path), [entry, first_exit])

    # Prepare fake core that would be mirrored if canonical_apply allowed the candidate
    core_state_path = tmp_path / "state.json"
    core = FakeCore(str(core_state_path))

    # Candidate stale/resurrected second exit attempt (should be blocked)
    second_exit_attempt = {
        "execution_id": "3530dbf965db4894ba93b7098cec3696",
        "action": "exit",
        "symbol": "TEM",
        "side": "long",
        "shares": 29.640567,
        "price": 52.905,
        "timestamp": 1786715000,
    }

    result = canonical_apply(core, second_exit_attempt)

    # Expect the guard to block the duplicate full exit BEFORE any mirroring/mutation
    assert result.get("status") == "blocked_duplicate_full_exit", "second exit must be blocked by duplicate guard"
    # No state mutation via core.record_trade should have occurred
    assert core._record_calls == 0
    assert core.portfolio.get("trades") == []

    # The canonical file must remain unchanged (no third appended row)
    with open(str(canonical_path), "r", encoding="utf-8") as fh:
        lines = [l for l in fh if l.strip()]
    assert len(lines) == 2

    # A diagnostic marker should have been appended to the in-memory portfolio
    diag = core.portfolio.get("diagnostics", {})
    blocked = diag.get("blocked_duplicate_full_exits", [])
    assert len(blocked) == 1
    assert blocked[0].get("candidate_execution_id") == second_exit_attempt["execution_id"]

    # Cleanup environment override
    del os.environ["CANONICAL_EXECUTION_JSONL"]
