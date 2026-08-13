import verified_snapshot_accounting_baseline as vsab


class NonCopyableTelemetry:
    def __deepcopy__(self, memo):
        raise RuntimeError("unrelated telemetry must not be deep-copied")


class DummyCore:
    portfolio = {}

    def local_ts_text(self):
        return "2026-08-13 09:30:00"


def test_verified_snapshot_wrapper_avoids_unrelated_telemetry(monkeypatch):
    import paper_bidirectional_accounting_guard as bidirectional
    import paper_accounting_integrity_guard as accounting
    import paper_ledger_matched_exit_guard as matched

    captured = {}

    def prior(working, runtime_core=None):
        captured["working"] = working
        return {
            "status": "ok",
            "parsed_trade_rows": len(working.get("trades", [])),
            "coverage_issues": [],
            "economic_issues": [],
            "realized_today": 1.25,
            "realized_total": 2.5,
        }

    monkeypatch.setattr(bidirectional, "analyze_ledger", prior)
    monkeypatch.setattr(accounting, "reconstruct_from_ledger", prior)
    monkeypatch.setattr(matched, "analyze_ledger", prior)
    monkeypatch.setattr(vsab, "_APPLIED", False)

    telemetry = NonCopyableTelemetry()
    portfolio = {
        "cash": 10768.497731,
        "equity": 11885.824057,
        "positions": {
            "LRCX": {
                "side": "long",
                "qty": 3.42486,
                "entry_price": 312.9,
                "last_price": 334.96,
            }
        },
        "trades": [
            {
                "action": "exit",
                "symbol": "LRCX",
                "side": "long",
                "shares": 1.0,
                "price": 340.0,
                "timestamp": "2026-08-13 09:30:00",
            }
        ],
        "paper_accounting_epoch": {
            "epoch_id": "stable-paper-v2-20260812-verified01",
            "baseline_type": "verified_snapshot_with_open_position",
            "verified_snapshot_baseline": {
                "verified": True,
                "cash": 10768.497731,
                "equity": 11885.824057,
                "realized_today": 32.81327,
                "realized_total": -1413.69673,
                "started_local": "2026-08-12 15:00:00",
                "positions": {
                    "LRCX": {
                        "side": "long",
                        "qty": 3.42486,
                        "entry_price": 312.9,
                    }
                },
            },
        },
        "auto_runner": {"last_result": telemetry},
        "scanner_runtime": telemetry,
    }
    core = DummyCore()
    core.portfolio = portfolio

    installed = vsab.apply(core)
    assert installed["status"] == "ok"

    rebuilt = bidirectional.analyze_ledger(portfolio, core)
    working = captured["working"]

    assert "auto_runner" not in working
    assert "scanner_runtime" not in working
    assert len(working["trades"]) == 2
    assert working["trades"][0]["verified_snapshot_synthetic_opening_lot"] is True
    assert working["trades"][1]["action"] == "exit"
    assert working["positions"]["LRCX"]["qty"] == 3.42486
    assert rebuilt["baseline_type"] == "verified_snapshot_with_open_position"
    assert rebuilt["verified_snapshot_epoch"] is True
    assert rebuilt["baseline_cash"] == 10768.497731
    assert rebuilt["parsed_trade_rows"] == 1
    assert rebuilt["coverage_complete"] is True
