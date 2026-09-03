import os
import json
import pytest

from canonical_execution_ledger import append, reconcile, LEDGER_FILENAME, PENDING_META, COMMITTED_META


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_append_and_mirror_success(tmp_path):
    ledger_dir = str(tmp_path)
    appended = []
    seen_exec = set()

    def mirror_fn(row):
        # idempotent by execution_id: do not double-add
        exec_id = row.get("execution_id")
        if exec_id in seen_exec:
            return
        seen_exec.add(exec_id)
        appended.append(row)

    row = {
        "execution_id": "exec-0001",
        "action": "entry",
        "symbol": "FOO",
        "side": "long",
        "price": 12.34,
        "shares": 1.23,
    }

    # Should not raise
    append(row, mirror_fn, ledger_dir=ledger_dir)

    ledger_path = os.path.join(ledger_dir, LEDGER_FILENAME)
    pending_path = os.path.join(ledger_dir, PENDING_META)
    committed_path = os.path.join(ledger_dir, COMMITTED_META)

    # Ledger contains the row
    assert os.path.exists(ledger_path)
    content = read_file(ledger_path).strip().splitlines()
    assert len(content) == 1
    loaded = json.loads(content[0])
    assert loaded["execution_id"] == "exec-0001"

    # Pending should be cleaned up and committed recorded
    assert not os.path.exists(pending_path)
    assert os.path.exists(committed_path)

    # Mirror function was called exactly once
    assert len(appended) == 1
    assert appended[0]["symbol"] == "FOO"


def test_interruption_after_append_and_restart_reconciles(tmp_path):
    ledger_dir = str(tmp_path)
    appended = []
    seen_exec = set()

    # First mirror will simulate a crash (raise) to leave pending
    def mirror_fn_raise(row):
        raise RuntimeError("simulated crash during mirror")

    row = {
        "execution_id": "exec-0002",
        "action": "entry",
        "symbol": "BAR",
        "side": "long",
        "price": 23.45,
        "shares": 2.34,
    }

    # append should raise because mirror_fn_raise raises; pending metadata should remain
    with pytest.raises(RuntimeError):
        append(row, mirror_fn_raise, ledger_dir=ledger_dir)

    ledger_path = os.path.join(ledger_dir, LEDGER_FILENAME)
    pending_path = os.path.join(ledger_dir, PENDING_META)
    committed_path = os.path.join(ledger_dir, COMMITTED_META)

    # Ledger contains the row and pending metadata exists
    assert os.path.exists(ledger_path)
    content = read_file(ledger_path).strip().splitlines()
    assert len(content) == 1
    loaded = json.loads(content[0])
    assert loaded["execution_id"] == "exec-0002"
    assert os.path.exists(pending_path)

    # Now simulate restart: use a safe, idempotent mirror_fn to reconcile
    def mirror_fn_reconciler(row):
        exec_id = row.get("execution_id")
        if exec_id in seen_exec:
            return
        seen_exec.add(exec_id)
        appended.append(row)

    # reconcile should succeed and remove pending metadata and record committed metadata
    reconcile(mirror_fn_reconciler, ledger_dir=ledger_dir)

    assert not os.path.exists(pending_path)
    assert os.path.exists(committed_path)

    # Mirror should have been applied exactly once after reconciliation
    assert len(appended) == 1
    assert appended[0]["symbol"] == "BAR"


def test_reconcile_fails_when_not_safe(tmp_path):
    ledger_dir = str(tmp_path)

    # Append a row that lacks execution_id to simulate unsafe canonical row
    appended = []

    def mirror_fn_ok(row):
        appended.append(row)

    row = {
        # no execution_id => unsafe for automatic reconciliation
        "action": "entry",
        "symbol": "BAZ",
        "side": "long",
        "price": 34.56,
        "shares": 3.45,
    }

    # append should write the ledger and pending metadata but then call mirror
    # We make mirror_fn_ok succeed so append completes and pending cleared.
    # To test the unsafe path we need to create pending metadata manually to mimic
    # the interrupted state where reconcile_safe == False.
    append(row, mirror_fn_ok, ledger_dir=ledger_dir)

    # Manually craft a pending file with reconcile_safe False to mimic interruption
    pending_path = os.path.join(ledger_dir, PENDING_META)
    ledger_path = os.path.join(ledger_dir, LEDGER_FILENAME)

    # Read last row and create pending metadata with reconcile_safe False
    last = json.loads(read_file(ledger_path).strip().splitlines()[-1])
    meta = {
        "execution_id": last.get("execution_id"),
        "row_digest": json.dumps(last, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        "timestamp": 1234567890,
        "reconcile_safe": False,
    }

    # But row_digest must be the sha256; build properly to match code expectations
    import hashlib
    digest = hashlib.sha256(json.dumps(last, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    meta["row_digest"] = digest

    # Write pending
    with open(pending_path, "w", encoding="utf-8") as f:
        json.dump(meta, f)

    # reconcile should raise because reconcile_safe is False (fail-closed)
    with pytest.raises(RuntimeError):
        reconcile(mirror_fn_ok, ledger_dir=ledger_dir)

    # Pending should remain so operator can inspect
    assert os.path.exists(pending_path)
