from __future__ import annotations

import math

import ml_recommendation_counterfactual_ledger as ledger


def _base_state():
    return {
        "ml_phase2": {
            "last_predictions": [
                {
                    "symbol": "AAA",
                    "side": "long",
                    "ml2_shadow_probability": 0.72,
                    "ml2_shadow_edge": 0.22,
                    "shadow_action": "rank_higher",
                    "confidence": "shadow",
                    "rule_score": 0.055,
                    "bucket": "growth",
                    "sector": "TECH",
                },
                {
                    "symbol": "BBB",
                    "side": "long",
                    "ml2_shadow_probability": 0.32,
                    "ml2_shadow_edge": -0.18,
                    "shadow_action": "rank_lower",
                    "confidence": "shadow",
                    "rule_score": 0.052,
                    "bucket": "industrial",
                    "sector": "INDUSTRIALS",
                },
            ]
        },
        "scanner_audit": {
            "accepted_entries": [
                {
                    "symbol": "AAA",
                    "side": "long",
                    "score": 0.055,
                    "reason": "rules_passed",
                    "eligible": True,
                    "price": 100.0,
                }
            ],
            "blocked_entries": [
                {
                    "symbol": "BBB",
                    "side": "long",
                    "score": 0.052,
                    "reason": "sector_cap",
                    "blocked": True,
                    "price": 50.0,
                }
            ],
        },
        "auto_runner": {"last_result": {"cycle_id": "cycle-test", "market_mode": "constructive"}},
        "trades": [],
    }


def test_capture_records_independent_ml_and_rules_decisions():
    state = _base_state()
    ledger.capture_recommendations(state, now_epoch=1_785_852_000)
    events = state["ml_counterfactual_recommendation_ledger"]["events"]
    assert len(events) == 2
    by_symbol = {event["symbol"]: event for event in events}

    assert by_symbol["AAA"]["ml_recommendation"] == "recommend_enter"
    assert by_symbol["AAA"]["rules_allow_execution"] is True
    assert by_symbol["AAA"]["decision_class"] == "rules_allow__ml_recommends"

    assert by_symbol["BBB"]["ml_recommendation"] == "recommend_avoid"
    assert by_symbol["BBB"]["rules_allow_execution"] is False
    assert by_symbol["BBB"]["decision_class"] == "rules_block__ml_opposes"

    assert all(event["ml_execution_authority"] is False for event in events)
    assert all(event["execution_authority"] == "rules_only" for event in events)


def test_counterfactual_bar_labels_and_path_metrics():
    event = {
        "event_id": "x",
        "event_epoch": 1_785_852_000,
        "symbol": "AAA",
        "side": "long",
        "reference_price": 100.0,
        "outcomes": {},
        "outcome_pending": True,
        "actual_outcome_available": False,
        "stop_loss_pct": 0.02,
        "profit_target_pct": 0.05,
    }
    bars = [
        {"epoch": 1_785_852_000, "open": 100, "high": 101, "low": 99.5, "close": 100.5},
        {"epoch": 1_785_852_900, "open": 100.5, "high": 102, "low": 100, "close": 101.5},
        {"epoch": 1_785_855_600, "open": 101.5, "high": 106, "low": 101, "close": 104.0},
    ]
    updated = ledger.apply_bars_to_event(
        event, bars, now_epoch=1_785_855_700
    )
    assert math.isclose(updated["outcomes"]["15m"]["return_pct"], 0.015, abs_tol=1e-6)
    assert math.isclose(updated["outcomes"]["60m"]["return_pct"], 0.04, abs_tol=1e-6)
    assert math.isclose(updated["outcomes"]["mfe_pct"], 0.06, abs_tol=1e-6)
    assert math.isclose(updated["outcomes"]["mae_pct"], -0.005, abs_tol=1e-6)
    assert updated["outcomes"]["stop_target_sequence"]["first_hit"] == "target"
    assert updated["training_label_horizon"] == "60m"
    assert updated["label_quality"] == "counterfactual_market_path"
    assert updated["training_weight"] == ledger.COUNTERFACTUAL_WEIGHT_60M


def test_training_rows_keep_counterfactual_discounted():
    state = _base_state()
    ledger.capture_recommendations(state, now_epoch=1_785_852_000)
    section = state["ml_counterfactual_recommendation_ledger"]
    first = section["events"][0]
    first.update(
        {
            "outcome_pending": False,
            "training_eligible": True,
            "training_weight": 0.35,
            "training_return_pct": 0.025,
            "training_win": True,
            "label_quality": "counterfactual_market_path",
            "training_label_horizon": "eod",
        }
    )
    rows = ledger.training_rows(state)
    assert len(rows) == 1
    assert rows[0]["counterfactual"] is True
    assert rows[0]["training_weight"] == 0.35
    assert rows[0]["future_win"] is True


def test_weighted_group_uses_effective_rows():
    rows = [
        {
            "bucket": "growth",
            "future_outcome_pending": False,
            "future_win": True,
            "future_pnl_pct": 0.02,
            "training_weight": 1.0,
        },
        {
            "bucket": "growth",
            "future_outcome_pending": False,
            "future_win": False,
            "future_pnl_pct": -0.01,
            "training_weight": 0.25,
        },
    ]
    group = ledger._weighted_group(rows, "bucket")["growth"]
    assert group["rows"] == 2
    assert math.isclose(group["effective_rows"], 1.25)
    assert math.isclose(group["win_rate"], 0.8)
