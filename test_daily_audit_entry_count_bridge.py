import types

import daily_audit_entry_count_bridge as bridge


def _core(entries):
    return types.SimpleNamespace(
        portfolio={
            "auto_runner": {
                "last_result": {
                    "entries": entries,
                }
            }
        }
    )


def test_fills_missing_entry_count_from_latest_runner_cycle():
    payload = {
        "sections": {
            "05_scanner_signals_entries_rejections": {
                "signals_found": 38,
                "entries_count": None,
                "rejected_signals_count": 40,
            },
            "12_next_action": {
                "status": "required",
                "priority": "normal",
                "reason": "entry_count_missing",
                "action": "Compare scanner and decision-audit counts for the latest completed cycle.",
            },
        }
    }
    out = bridge.patch_payload(payload, _core([{"symbol": "CLSK"}]))
    scanner = out["sections"]["05_scanner_signals_entries_rejections"]
    assert scanner["entries_count"] == 1
    assert scanner["entries_count_source"] == "auto_runner.last_result.entries"
    assert out["sections"]["12_next_action"]["reason"] == "latest_cycle_entry_count_available"


def test_preserves_explicit_scanner_entry_count():
    payload = {
        "sections": {
            "05_scanner_signals_entries_rejections": {
                "signals_found": 10,
                "entries_count": 2,
                "rejected_signals_count": 8,
            },
            "12_next_action": {
                "reason": "entry_count_missing",
            },
        }
    }
    out = bridge.patch_payload(payload, _core([{"symbol": "A"}]))
    assert out["sections"]["05_scanner_signals_entries_rejections"]["entries_count"] == 2
    assert out["sections"]["12_next_action"]["reason"] == "entry_count_missing"


def test_does_not_fabricate_count_when_runner_entries_missing():
    core = types.SimpleNamespace(portfolio={"auto_runner": {"last_result": {}}})
    payload = {
        "sections": {
            "05_scanner_signals_entries_rejections": {"entries_count": None},
            "12_next_action": {"reason": "entry_count_missing"},
        }
    }
    out = bridge.patch_payload(payload, core)
    assert out["sections"]["05_scanner_signals_entries_rejections"]["entries_count"] is None
    assert out["sections"]["12_next_action"]["reason"] == "entry_count_missing"
