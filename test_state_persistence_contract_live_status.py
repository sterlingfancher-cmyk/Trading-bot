from __future__ import annotations

import json
from types import SimpleNamespace

import state_persistence_contract as contract


def test_status_refreshes_memory_and_disk_richness_without_apply_side_effects(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    backup = tmp_path / "state.json.bak"
    state_file.write_text(
        json.dumps({"positions": {"AI": {}}, "trades": [{}, {}], "history": [1], "equity": 9999.0}),
        encoding="utf-8",
    )
    backup.write_text("{}", encoding="utf-8")
    core = SimpleNamespace(
        STATE_FILE=str(state_file),
        STATE_DIR=str(tmp_path),
        portfolio={"positions": {"AI": {}}, "trades": [{}, {}], "history": [1], "equity": 9999.0},
    )
    monkeypatch.setattr(contract, "_is_distinct_mount", lambda path: True)
    contract._APPLIED.add(id(core))
    contract._LAST = {
        "migration": {"performed": False, "source": None, "reason": None},
        "reloaded_richer_persistent_state": False,
    }

    first = contract.status_payload(core)
    assert first["in_memory_richness"] == first["on_disk_richness"]
    assert first["status_refresh_is_read_only"] is True

    core.portfolio["positions"]["CRWD"] = {}
    core.portfolio["trades"].append({})
    state_file.write_text(json.dumps(core.portfolio), encoding="utf-8")
    second = contract.status_payload(core)
    assert second["in_memory_richness"][0] == 2
    assert second["in_memory_richness"][1] == 3
    assert second["in_memory_richness"] == second["on_disk_richness"]
    assert second["richness_match"] is True


def test_status_authority_is_observational():
    authority = contract._authority()
    assert authority["status_reads_are_observational"] is True
    assert authority["fabricates_missing_state"] is False
    assert authority["changes_strategy"] is False
    assert authority["changes_thresholds"] is False
    assert authority["changes_risk_or_sizing"] is False
    assert authority["places_orders"] is False
