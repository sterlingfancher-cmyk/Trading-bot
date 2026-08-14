import inspect
import json
import os
import tempfile
from pathlib import Path

import pytest

import state_persistence_contract as spc


# This test executes the real state_persistence_contract.apply(core) path
# using a realistic core-like object and a temporary mounted state directory.
# It intentionally does not modify runtime modules other than temporarily
# wrapping the real _replace_portfolio helper to observe whether it is
# reached and whether the resurrected loaded snapshot contains the TEM
# position.


class CoreStub:
    def __init__(self, state_path: Path):
        self._state_path = state_path
        # start with an empty in-memory portfolio (real code may replace it)
        self.portfolio = {}

    # production code often calls core.load_state(); provide it
    def load_state(self):
        try:
            with open(self._state_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    # production code often calls core.save_state(portfolio); provide it
    def save_state(self, portfolio):
        # mirror to the same file to emulate a realistic save
        try:
            with open(self._state_path, "w", encoding="utf-8") as fh:
                json.dump(portfolio, fh)
        except Exception:
            pass

    # some modules reference STATE_FILE/STATE_PATH attributes
    @property
    def STATE_FILE(self):
        return str(self._state_path)

    def local_ts_text(self):
        # minimal stub to satisfy any logging usage
        return "2026-08-14 00:00:00"


def _write_jsonl(path: Path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _make_canonical_rows():
    # Canonical JSONL MUST contain TEM entry execution d647... and ONLY first full exit 7b13...
    entry = {
        "execution_id": "d647d8a0580b44edbab0224e6c339bfd",
        "action": "entry",
        "symbol": "TEM",
        "side": "long",
        "size": 29.640567,
        "qty": 29.640567,
        "filled_qty": 29.640567,
        "price": 54.885,
        "entry_price": 54.885,
        "time": "2026-06-01T14:30:00Z",
        "timestamp": 1717266600.0,
        "note": "canonical-entry"
    }
    first_full_exit = {
        "execution_id": "7b13d9194a23407f926667b2f48d4057",
        "action": "exit",
        "symbol": "TEM",
        "side": "long",
        "size": 29.640567,
        "qty": 29.640567,
        "price": 53.105,
        "pnl_dollars": round((53.105 - 54.885) * 29.640567, 6),
        "pnl_pct": round((53.105 / 54.885 - 1.0) * 100.0, 6),
        "time": "2026-06-01T15:00:00Z",
        "timestamp": 1717268400.0,
        "exit_reason": "filled",
        "note": "canonical-first-exit"
    }
    return [entry, first_full_exit]


def _make_persisted_state_with_stale_tem(state_path: Path):
    # The persisted snapshot should still contain TEM (the stale position)
    persisted = {
        "portfolio": {
            "version": "stable-paper-v2-20260812-verified01",
            "cash": 10768.497731,
            "equity": 11885.824057,
            "positions": {
                "TEM": {
                    "symbol": "TEM",
                    "side": "long",
                    "size": 29.640567,
                    "qty": 29.640567,
                    "entry_execution_id": "d647d8a0580b44edbab0224e6c339bfd",
                    "entry_price": 54.885,
                    "entry_time": "2026-06-01T14:30:00Z",
                    "unrealized_pnl": 0.0
                }
            },
            "trades": [
                # include the historical entry trade row here to mimic persisted mirror
                {
                    "execution_id": "d647d8a0580b44edbab0224e6c339bfd",
                    "action": "entry",
                    "symbol": "TEM",
                    "side": "long",
                    "size": 29.640567,
                    "qty": 29.640567,
                    "price": 54.885,
                    "time": "2026-06-01T14:30:00Z",
                    "timestamp": 1717266600.0
                }
            ]
        }
    }
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump(persisted, fh)
    return persisted


@pytest.mark.parametrize("call_apply_with_core", [True])
def test_apply_reaches_replace_portfolio_and_resurrects_tem(tmp_path, monkeypatch, call_apply_with_core):
    # prepare temporary files
    mount = tmp_path / "mounted_state"
    mount.mkdir()

    canonical_path = mount / "canonical_execution_ledger.jsonl"
    state_path = mount / "state.json"

    # write canonical JSONL fixture with only the entry and first full exit
    canonical_rows = _make_canonical_rows()
    _write_jsonl(canonical_path, canonical_rows)

    # persisted snapshot which still contains TEM (stale persisted portfolio)
    persisted = _make_persisted_state_with_stale_tem(state_path)

    core = CoreStub(state_path)

    # Arrange to point the persistence module to our temporary files.
    # Try multiple likely module-level variable names that the real module might use.
    for varname in (
        "CANONICAL_EXECUTION_JSONL",
        "CANONICAL_EXECUTION_LEDGER",
        "CANONICAL_EXECUTION_LEDGER_FILE",
        "CANONICAL_EXECUTION_JOURNAL",
        "CANONICAL_EXECUTION_PATH",
        "EXECUTION_CANONICAL_JSONL",
        "EXECUTION_LEDGER_FILE",
        "CANONICAL_LEDGER_FILE",
    ):
        if hasattr(spc, varname):
            try:
                setattr(spc, varname, str(canonical_path))
            except Exception:
                pass

    # Also export a fallback file into the CWD if the module uses a literal name.
    # This avoids guessing every literal; many implementations look for
    # 'canonical_execution_ledger.jsonl' in the working directory.
    cwd_fallback = Path.cwd() / "canonical_execution_ledger.jsonl"
    if not cwd_fallback.exists():
        try:
            _write_jsonl(cwd_fallback, canonical_rows)
            created_cwd_fallback = True
        except Exception:
            created_cwd_fallback = False
    else:
        created_cwd_fallback = False

    # Point environment variables often used for state path resolution
    monkeypatch.setenv("STATE_DIR", str(mount))
    monkeypatch.setenv("STATE_FILE", str(state_path))

    # Wrap the real _replace_portfolio to observe calls
    called = {"hit": False, "loaded_arg": None}

    original_replace = getattr(spc, "_replace_portfolio", None)

    def _observer_replace(core_arg, loaded_arg):
        called["hit"] = True
        called["loaded_arg"] = loaded_arg
        # call original to preserve behavior if available
        if callable(original_replace):
            try:
                return original_replace(core_arg, loaded_arg)
            except Exception:
                # swallow to avoid test crash; we only need the evidence
                return None
        return None

    # Install observer
    setattr(spc, "_replace_portfolio", _observer_replace)

    # Attempt to call apply(core) exactly as requested. If the signature differs,
    # also attempt apply() as a fallback (some modules take no args and read module
    # state instead).
    apply_fn = getattr(spc, "apply", None)
    assert callable(apply_fn), "state_persistence_contract.apply must exist and be callable"

    apply_error = None
    try:
        # prefer the explicit core form
        apply_fn(core)
    except TypeError:
        # signature mismatch — try no-arg form
        try:
            apply_fn()
        except Exception as exc:
            apply_error = exc
    except Exception as exc:
        apply_error = exc

    # restore original replace helper to avoid side-effects for other tests
    if original_replace is not None:
        setattr(spc, "_replace_portfolio", original_replace)

    # cleanup cwd fallback if we created it
    if created_cwd_fallback and cwd_fallback.exists():
        try:
            cwd_fallback.unlink()
        except Exception:
            pass

    # Now assert whether we observed the replacement call and whether the loaded
    # snapshot included TEM when replacement was invoked.
    if not called["hit"]:
        # If we couldn't prove the path reached _replace_portfolio, fail with
        # detailed diagnostic so maintainers can iterate (per handoff instructions).
        reason = (
            "Insufficient evidence: state_persistence_contract._replace_portfolio was not invoked "
            "during apply(core)."
        )
        if apply_error:
            reason += f" apply() raised: {apply_error!r}"
        # Attach some introspection to help debugging
        src = inspect.getsource(spc)
        diagnostic = {
            "module_has_replace_portfolio": hasattr(spc, "_replace_portfolio"),
            "apply_callable": True,
            "apply_signature": str(inspect.signature(apply_fn)),
            "module_source_snippet_first_400": src[:400],
        }
        pytest.fail(reason + " Diagnostic: " + json.dumps(diagnostic))

    # If called, verify the loaded snapshot resurrected TEM (stale persisted state
    # should already contain TEM; the test's purpose is to check whether apply()
    # reintroduced TEM into the loaded snapshot used for replacement).
    loaded = called.get("loaded_arg")
    # loaded may be the raw portfolio dict or a wrapper containing 'portfolio'
    if loaded is None:
        pytest.fail("Observed _replace_portfolio call but the loaded argument was None")

    # normalize to portfolio dict
    if isinstance(loaded, dict) and "portfolio" in loaded and isinstance(loaded.get("portfolio"), dict):
        portfolio_section = loaded.get("portfolio")
    elif isinstance(loaded, dict) and ("positions" in loaded or "trades" in loaded):
        portfolio_section = loaded
    else:
        # might be the raw positions map
        portfolio_section = loaded

    positions = portfolio_section.get("positions") if isinstance(portfolio_section, dict) else None
    if not positions or not isinstance(positions, dict) or "TEM" not in positions:
        pytest.fail(
            "_replace_portfolio was invoked but the loaded snapshot did not contain TEM in positions. "
            f"Loaded keys: {list(portfolio_section.keys()) if isinstance(portfolio_section, dict) else type(portfolio_section)}"
        )

    # confirm TEM position matches expected size and entry id
    tem = positions.get("TEM")
    assert isinstance(tem, dict), "TEM position must be a dict"
    assert round(float(tem.get("size") or tem.get("qty") or 0.0), 6) == 29.640567
    assert str(tem.get("entry_execution_id") or tem.get("execution_id") or tem.get("entry_id") or "").startswith(
        "d647d8a0580b44ed"
    )

    # If we reach here, we proved that apply() reached _replace_portfolio and
    # the loaded snapshot included TEM (i.e. resurrection evidence for this run).
