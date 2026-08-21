import entry_pipeline_xray as xray


class FakeCore:
    def __init__(self):
        self.portfolio = {
            "cash": 13200.0,
            "equity": 13200.0,
            "positions": {},
            "risk_controls": {
                "date": "2026-08-21",
                "day_start_equity": 13200.0,
                "day_peak_equity": 13200.0,
                "halted": False,
            },
        }
        self.load_state_calls = 0
        self.save_state_calls = 0

    def load_state(self):
        self.load_state_calls += 1
        return {
            "cash": -26064.308324919723,
            "equity": -26064.31,
            "positions": {},
            "risk_controls": {
                "date": "2026-08-20",
                "day_start_equity": -26064.31,
                "day_peak_equity": 0.01,
                "halted": True,
                "halt_reason": "daily loss limit hit (3.0%)",
                "fresh_day_reset_pending": True,
            },
        }

    def save_state(self, state):
        self.save_state_calls += 1


def _cycle():
    return {
        "generated_local": "2026-08-21 08:42:43 CDT",
        "bottleneck": "new_entries_not_allowed",
        "stage_counts": {
            "raw_total_signals": 27,
            "entries_returned": 0,
            "rotations_returned": 0,
            "blocked_rows_returned": 10,
        },
        "top_rejection_reasons": [],
        "symbol_paths": [],
        "wrapped_callable": {"name": "try_entries_and_rotations"},
        "composition": {"status": "ok"},
        "error": None,
    }


def test_xray_persist_never_reloads_or_replaces_live_portfolio():
    core = FakeCore()
    live = core.portfolio

    xray._persist(core, _cycle())

    assert core.portfolio is live
    assert core.portfolio["equity"] == 13200.0
    assert core.portfolio["risk_controls"]["date"] == "2026-08-21"
    assert core.portfolio["risk_controls"]["halted"] is False
    assert core.load_state_calls == 0
    assert core.save_state_calls == 0
    assert core.portfolio["entry_pipeline_xray"]["last_cycle"]["stage_counts"]["raw_total_signals"] == 27
