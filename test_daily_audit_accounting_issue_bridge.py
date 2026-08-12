import types

import daily_audit_accounting_issue_bridge as bridge
import final_daily_audit_compactor as compactor


def test_compact_audit_surfaces_bounded_accounting_evidence(monkeypatch):
    def base(payload, core=None):
        return {"accounting_integrity": {"coverage_complete": False}}

    monkeypatch.setattr(compactor, "compact_payload", base)
    bridge._APPLIED = False
    state = {
        "trades": [
            {
                "time": "2026-08-11 14:50:00 CDT",
                "symbol": "CLSK",
                "side": "buy",
                "type": "paper_market_surge_deployment",
                "source": "market_surge_deployment_mode",
                "entry": 12.25,
                "shares": 134.680133,
                "execution_id": "entry-1",
            },
            {
                "time": 1786460500,
                "action": "exit",
                "symbol": "CLSK",
                "side": "long",
                "price": 11.5223,
                "shares": 134.680133,
                "source": "legacy_exit_mirror",
            },
            {
                "time": 1786460578,
                "action": "exit",
                "symbol": "CLSK",
                "side": "long",
                "price": 11.5223,
                "shares": 134.680133,
                "execution_id": "exit-1",
                "canonical_ledger_version": "canonical-execution-ledger-2026-08-10-v1",
            },
        ]
    }
    core = types.SimpleNamespace(portfolio=state)
    result = bridge.apply(core)
    assert result["status"] == "ok"

    issue = {
        "trade_index": 2,
        "reason": "exit_exceeds_reconstructed_position",
        "symbol": "CLSK",
        "action": "exit",
        "side": "long",
        "requested_qty": 134.680133,
        "matched_qty": 0.0,
    }
    payload = {
        "sections": {
            "10b_market_data_and_path_integrity": {
                "paper_accounting_integrity": {
                    "reconstructed": {
                        "parsed_trade_rows": 2,
                        "coverage_issues": [issue],
                        "economic_issues": [issue],
                        "open_positions": {},
                    }
                },
                "paper_ledger_economic_integrity": {
                    "economic_issues": [issue]
                },
            }
        }
    }

    out = compactor.compact_payload(payload, core)
    acct = out["accounting_integrity"]
    assert acct["parsed_trade_rows"] == 2
    assert acct["first_coverage_issue"]["symbol"] == "CLSK"
    assert acct["coverage_issues"] == [issue]
    evidence = acct["unmatched_exit_entry_evidence"][0]
    assert evidence["issue"]["trade_index"] == 2
    candidates = evidence["prior_same_symbol_entry_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["trade_index"] == 0
    assert candidates[0]["source"] == "market_surge_deployment_mode"
    assert candidates[0]["entry"] == 12.25
    assert candidates[0]["shares"] == 134.680133

    window = acct["trade_row_window"]
    assert [row["trade_index"] for row in window] == [0, 1, 2]
    assert window[1]["source"] == "legacy_exit_mirror"
    assert window[2]["execution_id"] == "exit-1"
    assert window[2]["canonical_ledger_version"] == "canonical-execution-ledger-2026-08-10-v1"
