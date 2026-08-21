from __future__ import annotations

import copy

import verified_v2_successor_replay_status as replay


def _trade(execution_id, action, symbol, price=100.0, shares=1.0):
    return {
        "execution_id": execution_id,
        "accounting_epoch_id": replay.TARGET_EPOCH_ID,
        "action": action,
        "symbol": symbol,
        "side": "long",
        "price": price,
        "shares": shares,
        "recorded_local": "2026-08-21 10:00:00 CDT",
        "exit_reason": "normal_exit" if action != "entry" else None,
        "event_hash": f"hash-{execution_id}",
    }


def test_state_only_exit_is_exposed_without_mutation():
    ledger_rows = [_trade("crwd-entry", "entry", "CRWD")]
    portfolio = {
        "positions": {},
        "trades": [
            _trade("crwd-entry", "entry", "CRWD"),
            _trade("crwd-state-only-exit", "exit", "CRWD", price=101.0),
        ],
    }
    before_portfolio = copy.deepcopy(portfolio)
    before_ledger = copy.deepcopy(ledger_rows)

    lineage = replay._unexplained_position_lineage(portfolio, ledger_rows, ["CRWD"])
    crwd = lineage["CRWD"]

    assert crwd["state_only_exit_present"] is True
    assert crwd["state_only_execution_ids"] == ["crwd-state-only-exit"]
    assert crwd["ledger_only_execution_ids"] == []
    assert crwd["interpretation"] == "state_contains_exit_execution_not_present_in_canonical_ledger"
    assert portfolio == before_portfolio
    assert ledger_rows == before_ledger


def test_ledger_only_execution_is_exposed_without_state_only_exit():
    ledger_rows = [_trade("panw-entry", "entry", "PANW")]
    portfolio = {"positions": {}, "trades": []}

    lineage = replay._unexplained_position_lineage(portfolio, ledger_rows, ["PANW"])
    panw = lineage["PANW"]

    assert panw["ledger_only_execution_present"] is True
    assert panw["ledger_only_execution_ids"] == ["panw-entry"]
    assert panw["state_only_exit_present"] is False
    assert panw["interpretation"] == "ledger_and_state_execution_sets_differ_without_state_only_exit"


def test_matching_execution_sets_but_missing_position_is_classified_separately():
    entry = _trade("path-entry", "entry", "PATH")
    ledger_rows = [entry]
    portfolio = {"positions": {}, "trades": [copy.deepcopy(entry)]}

    lineage = replay._unexplained_position_lineage(portfolio, ledger_rows, ["PATH"])
    path = lineage["PATH"]

    assert path["same_execution_id_sets"] is True
    assert path["state_only_execution_ids"] == []
    assert path["ledger_only_execution_ids"] == []
    assert path["interpretation"] == "execution_id_sets_match_but_position_state_differs"


def test_lineage_scope_is_only_requested_unexplained_symbols():
    ledger_rows = [
        _trade("snow-entry", "entry", "SNOW"),
        _trade("other-entry", "entry", "OTHER"),
    ]
    portfolio = {"positions": {}, "trades": []}

    lineage = replay._unexplained_position_lineage(portfolio, ledger_rows, ["SNOW"])

    assert set(lineage) == {"SNOW"}
    assert lineage["SNOW"]["ledger_execution_ids"] == ["snow-entry"]
