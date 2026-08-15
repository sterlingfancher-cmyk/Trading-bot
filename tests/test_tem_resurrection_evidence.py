import json
import os
from types import SimpleNamespace


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_state_persistence_apply_reaches_replace_portfolio(tmp_path, monkeypatch):
    """
    Evidence test for the state persistence apply path that exercises the real
    state_persistence_contract.apply(core) startup path.

    This test performs the minimal, non-invasive steps required by the project
    handoff to produce corrected evidence (retry after PR #72 rejection):

    - Create a temporary "mounted" state directory and write a root-level
      persisted state.json that contains the production-shaped portfolio root
      (positions.TEM with production keys and top-level trades list).
    - Create a canonical_execution_ledger.jsonl fixture in the same tempdir
      that contains exactly the TEM entry execution row d647d8a0580b44edbab0224e6c339bfd
      (price 54.885 shares 29.640567 time 1786647398) and only the first full
      exit 7b13d9194a23407f926667b2f48d4057 (price 53.105 shares 29.640567 time 1786714863).
      The erroneous second exit (3530dbf...) is intentionally omitted per
      the reproduction requirements.
    - Monkeypatch the state_persistence_contract._is_distinct_mount() to return
      True for this tempdir so apply(core) treats it as a real mounted volume.
    - Wrap the real state_persistence_contract._replace_portfolio(core, loaded)
      only to observe whether apply reaches it and whether the loaded root
      positions contains TEM. The wrapper calls the original implementation
      and does not swallow exceptions.
    - Call the real state_persistence_contract.apply(core) with a small fake
      core object that points state paths at our tempdir. If apply reaches
      replacement and the loaded state contains TEM, the test asserts proof;
      otherwise it fails with "insufficient evidence".

    Safety: this test only manipulates test fixtures and monkeypatches in-test;
    it does not change runtime code or alter any repository production logic.
    """
    # Import inside test so any top-level import-time behavior is avoided until needed
    try:
        import state_persistence_contract
    except Exception as exc:  # pragma: no cover - explicit failure if module not present
        raise AssertionError("state_persistence_contract module not importable: %s" % exc)

    # Prepare a temporary mounted-state directory and root-level persisted portfolio
    mounted = tmp_path / "mounted_state"
    mounted.mkdir()

    state_file = mounted / "state.json"

    # Root portfolio dict must contain positions.TEM using production keys and top-level trades
    persisted_portfolio = {
        "version": "test-evidence-root-1",
        "cash": 10768.497731,
        "equity": 11885.824057,
        "positions": {
            "TEM": {
                "symbol": "TEM",
                "side": "long",
                "entry": 54.885,
                "shares": 29.640567,
                "last_price": 54.885,
                "peak": 54.885,
                "entry_execution_id": "d647d8a0580b44edbab0224e6c339bfd",
                "entry_time": 1786647398,
            }
        },
        # trades list at root (snapshot may or may not be used by apply; present per requirement)
        "trades": [
            {
                "action": "entry",
                "symbol": "TEM",
                "execution_id": "d647d8a0580b44edbab0224e6c339bfd",
                "price": 54.885,
                "shares": 29.640567,
                "time": 1786647398,
            }
        ],
    }

    state_file.write_text(json.dumps(persisted_portfolio, ensure_ascii=False), encoding="utf-8")

    # Create canonical_execution_ledger.jsonl fixture with the two required rows
    canonical_file = mounted / "canonical_execution_ledger.jsonl"

    # The test uses a literal production-shaped row approximation containing the
    # key canonical fields. The contract is expected to parse the ledger file
    # format used in-production; if more fields are required they can be added
    # in later forensic iterations. Only the two required executions are present.
    entry_row = {
        "action": "entry",
        "symbol": "TEM",
        "side": "long",
        "execution_id": "d647d8a0580b44edbab0224e6c339bfd",
        "price": 54.885,
        "shares": 29.640567,
        "time": 1786647398,
        "epoch": "stable-paper-v2-20260812-verified01",
    }

    first_exit_row = {
        "action": "exit",
        "symbol": "TEM",
        "side": "long",
        "execution_id": "7b13d9194a23407f926667b2f48d4057",
        "price": 53.105,
        "shares": 29.640567,
        "time": 1786714863,
        "epoch": "stable-paper-v2-20260812-verified01",
    }

    _write_jsonl(str(canonical_file), [entry_row, first_exit_row])

    # Build a minimal fake core that points the contract at our test-mounted state
    fake_core = SimpleNamespace()
    # Many state persistence helpers inspect STATE_DIR / STATE_FILE on the core/module
    fake_core.STATE_DIR = str(mounted)
    fake_core.STATE_FILE = str(state_file)
    fake_core.STATE_PERSISTENCE_MODE = "persistent_volume"
    # minimal portfolio present before apply; apply may replace it
    fake_core.portfolio = {"boot": True}

    # If the contract expects a save_state callable, provide one that writes JSON
    def save_state(payload):
        try:
            with open(fake_core.STATE_FILE, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False))
        except Exception:
            # Let exceptions surface to test runner
            raise

    fake_core.save_state = save_state

    # Monkeypatch the contract to treat our tmpdir as a distinct mounted volume.
    # The production _is_distinct_mount(path) may examine mountpoints; we force True
    # only for the test-mounted directory path.
    orig_is_distinct = getattr(state_persistence_contract, "_is_distinct_mount", None)

    def _is_distinct_mount_for_test(path):
        try:
            # If the path matches our mounted tempdir, report True; otherwise defer
            if os.path.realpath(str(path)) == os.path.realpath(str(mounted)):
                return True
        except Exception:
            pass
        if callable(orig_is_distinct):
            return orig_is_distinct(path)
        return False

    monkeypatch.setattr(state_persistence_contract, "_is_distinct_mount", _is_distinct_mount_for_test)

    # Ensure the contract will find the canonical ledger we created by monkeypatching
    # a likely attribute name if present. This is defensive: if the contract exposes
    # a file-name constant we point it at our fixture. If the attribute isn't present
    # this has no effect.
    if hasattr(state_persistence_contract, "CANONICAL_EXECUTION_LEDGER_PATH"):
        monkeypatch.setattr(state_persistence_contract, "CANONICAL_EXECUTION_LEDGER_PATH", str(canonical_file))
    if hasattr(state_persistence_contract, "CANONICAL_EXECUTION_LEDGER_FILE"):
        monkeypatch.setattr(state_persistence_contract, "CANONICAL_EXECUTION_LEDGER_FILE", str(canonical_file))

    # Wrap the real _replace_portfolio(core, loaded) only to observe whether it is
    # called and whether loaded contains TEM. Call the original implementation
    # and do not swallow exceptions.
    if not hasattr(state_persistence_contract, "_replace_portfolio"):
        raise AssertionError("state_persistence_contract._replace_portfolio not found; cannot observe replacement path")

    orig_replace = state_persistence_contract._replace_portfolio

    observed = {"called": False, "loaded": None}

    def _observer_replace(core_arg, loaded):
        observed["called"] = True
        # Make a shallow copy of loaded for inspection to avoid mutation surprises
        observed["loaded"] = dict(loaded) if isinstance(loaded, dict) else loaded
        # Delegate to original implementation. Let exceptions propagate unchanged.
        return orig_replace(core_arg, loaded)

    monkeypatch.setattr(state_persistence_contract, "_replace_portfolio", _observer_replace)

    # Now call the real apply(core). Per requirements we must execute the real
    # state_persistence_contract.apply(core) startup path.
    try:
        # apply may return None or some status object; we only care about whether
        # it invoked _replace_portfolio with a loaded root that contains TEM.
        state_persistence_contract.apply(fake_core)
    except Exception:
        # Do not swallow exceptions: re-raise after capture so the test runner sees them.
        raise

    # After apply returns, assert whether the replacement path was exercised and
    # the loaded root portfolio contained the TEM position.
    if not observed["called"]:
        raise AssertionError("insufficient evidence: state_persistence_contract.apply did not reach _replace_portfolio")

    loaded = observed.get("loaded") or {}
    positions = loaded.get("positions") if isinstance(loaded, dict) else None
    if not isinstance(positions, dict) or "TEM" not in positions:
        raise AssertionError("insufficient evidence: _replace_portfolio was called but loaded root positions does not contain TEM")

    # If we reach here we have proof the apply path reached replacement and the
    # persisted root reintroduced TEM. The test passes and serves as non-invasive
    # forensic evidence for the resurrected TEM hypothesis.
    assert True
