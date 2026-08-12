import types

import daily_audit_accounting_issue_bridge as bridge
import final_daily_audit_compactor as compactor


def test_compact_audit_surfaces_first_accounting_issue(monkeypatch):
    def base(payload, core=None):
        return {"accounting_integrity": {"coverage_complete": False}}

    monkeypatch.setattr(compactor, "compact_payload", base)
    bridge._APPLIED = False
    result = bridge.apply(types.SimpleNamespace())
    assert result["status"] == "ok"

    payload = {
        "sections": {
            "10b_market_data_and_path_integrity": {
                "paper_accounting_integrity": {
                    "reconstructed": {
                        "parsed_trade_rows": 6,
                        "coverage_issues": [{"trade_index": 6, "reason": "unsupported_or_incomplete_trade_row", "symbol": "VST"}],
                        "economic_issues": [{"trade_index": 6, "reason": "entry_exceeds_available_cash", "symbol": "VST"}],
                        "open_positions": {"LRCX": {"qty": 1}},
                    }
                },
                "paper_ledger_economic_integrity": {
                    "economic_issues": [{"trade_index": 6, "reason": "entry_exceeds_available_cash", "symbol": "VST"}]
                },
            }
        }
    }

    out = compactor.compact_payload(payload, None)
    acct = out["accounting_integrity"]
    assert acct["parsed_trade_rows"] == 6
    assert acct["first_coverage_issue"]["trade_index"] == 6
    assert acct["first_coverage_issue"]["symbol"] == "VST"
    assert acct["first_economic_issue"]["reason"] == "entry_exceeds_available_cash"
    assert acct["reconstructed_open_positions"] == ["LRCX"]
