from __future__ import annotations

from unittest import mock

import canonical_execution_ledger as ledger
import verified_v2_successor_replay_status as replay
import verified_v2_successor_replay_tem_provenance as temprov


class FakeCore:
    def __init__(self):
        self.portfolio = {
            "cash": 12000.0,
            "equity": 12100.0,
            "realized_today": 368.68,
            "accounting_epoch_id": replay.TARGET_EPOCH_ID,
            "paper_accounting_epoch": {"id": replay.TARGET_EPOCH_ID},
            "trades": [],
            "risk_controls": {
                "date": "2026-08-21",
                "day_start_equity": 13166.470921819817,
                "day_peak_equity": 19150.437724108448,
                "halted": True,
                "halt_reason": "performance risk hard intraday drawdown halt (2.50%)",
                "intraday_drawdown_pct": 29.28,
            },
            "positions": {
                "SLS": {
                    "side": "long",
                    "shares": 4.353086829,
                    "entry": 14.335,
                    "last_price": 15.46,
                },
                "TOST": {
                    "side": "long",
                    "shares": 3.767684364,
                    "entry": 36.0501,
                    "last_price": 36.4,
                },
            },
        }

    def local_ts_text(self):
        return "2026-08-21 16:40:00 CDT"


def _row(
    execution_id,
    action,
    symbol,
    side,
    price,
    shares,
    recorded_local,
    exit_reason=None,
):
    return {
        "execution_id": execution_id,
        "accounting_epoch_id": replay.TARGET_EPOCH_ID,
        "action": action,
        "symbol": symbol,
        "side": side,
        "price": price,
        "shares": shares,
        "recorded_local": recorded_local,
        "exit_reason": exit_reason,
        "event_hash": f"hash-{execution_id}",
    }


def _rows(sls_bad_price=replay.SLS_BAD_PRICE, tost_bad_2_price=190.244995):
    return [
        _row(
            "lrcx-valid-exit",
            "exit",
            "LRCX",
            "long",
            333.12,
            replay.BASELINE_LRCX_QTY,
            "2026-08-14 09:18:46 CDT",
            "normal_exit",
        ),
        _row(
            "tem-entry",
            "entry",
            "TEM",
            "long",
            54.885,
            replay.TEM_DUPLICATE_QTY,
            "2026-08-13 10:16:38 CDT",
        ),
        _row(
            "tem-valid-exit",
            "exit",
            "TEM",
            "long",
            53.105,
            replay.TEM_DUPLICATE_QTY,
            "2026-08-14 08:41:03 CDT",
            "stop_loss",
        ),
        _row(
            replay.TEM_DUPLICATE_EXECUTION_ID,
            "exit",
            "TEM",
            "long",
            replay.TEM_DUPLICATE_PRICE,
            replay.TEM_DUPLICATE_QTY,
            "2026-08-14 08:48:37 CDT",
            "stop_loss",
        ),
        _row(
            "sls-entry",
            "entry",
            "SLS",
            "long",
            14.335,
            6.497144521,
            "2026-08-21 09:39:36 CDT",
        ),
        _row(
            replay.SLS_BAD_EXECUTION_ID,
            "partial_exit",
            "SLS",
            "long",
            sls_bad_price,
            replay.SLS_BAD_QTY,
            "2026-08-21 09:51:13 CDT",
            "partial_profit_long",
        ),
        _row(
            "tost-entry",
            "entry",
            "TOST",
            "long",
            36.0501,
            3.767684364,
            "2026-08-21 09:25:50 CDT",
        ),
        _row(
            replay.TOST_BAD_1_EXECUTION_ID,
            "partial_exit",
            "TOST",
            "long",
            73.940002,
            1.24333584,
            "2026-08-21 13:11:11 CDT",
            "partial_profit_long",
        ),
        _row(
            replay.TOST_BAD_2_EXECUTION_ID,
            "partial_exit",
            "TOST",
            "long",
            tost_bad_2_price,
            1.24333584,
            "2026-08-21 14:03:17 CDT",
            "partial_profit_long",
        ),
        _row(
            replay.TOST_BAD_3_EXECUTION_ID,
            "partial_exit",
            "TOST",
            "long",
            74.269997,
            1.24333584,
            "2026-08-21 14:35:20 CDT",
            "partial_profit_long",
        ),
    ]


def _payload(rows):
    with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(
        ledger, "_verify_rows", return_value=(True, [])
    ):
        return replay.status_payload(FakeCore())


def test_consolidated_gate_excludes_exact_five_invalid_rows_and_replays_everything_else():
    payload = _payload(_rows())

    assert payload["overall"] == "pass"
    assert payload["diagnosis"] == "verified_v2_consolidated_recovery_gate_mechanically_complete"
    assert payload["known_invalid_execution_count"] == 5
    assert payload["all_known_invalid_signatures_exact"] is True
    assert payload["latest_invalid_is_last_canonical_execution"] is True
    assert payload["canonical_rows_after_last_known_invalid_count"] == 0

    disposition = payload["known_invalid_execution_disposition"]
    assert set(disposition) == {
        "tem_duplicate",
        "sls_bad_partial_exit",
        "tost_bad_partial_exit_1",
        "tost_bad_partial_exit_2",
        "tost_bad_partial_exit_3",
    }
    assert all(item["signature_exact"] for item in disposition.values())
    assert all(item["immutable_row_retained"] for item in disposition.values())

    projection = payload["projection"]
    assert projection["projection_complete"] is True
    assert projection["applied_execution_count"] == 5
    assert projection["excluded_execution_count"] == 5
    projected = {row["symbol"]: row for row in projection["candidate_positions"]}
    assert abs(projected["SLS"]["shares"] - 6.497144521) < 1e-9
    assert abs(projected["TOST"]["shares"] - 3.767684364) < 1e-9

    comparison = payload["state_comparison"]
    assert comparison["unexplained_position_mismatches"] == []
    assert comparison["only_known_invalid_symbols_differ"] is True
    assert payload["recovery_readiness"]["mechanically_complete_for_successor_migration_design"] is True
    assert payload["recovery_readiness"]["manual_per_event_probe_required"] is False
    assert payload["recovery_readiness"]["state_write_authorized_by_this_probe"] is False
    assert payload["authority"]["rewrites_or_relabels_canonical_ledger"] is False


def test_tem_canonical_precision_is_exact_and_display_rounding_is_not_accepted_as_the_signature():
    rows = _rows()
    tem = next(row for row in rows if row["execution_id"] == replay.TEM_DUPLICATE_EXECUTION_ID)
    assert tem["price"] == 52.904999
    payload = _payload(rows)
    assert payload["known_invalid_execution_disposition"]["tem_duplicate"]["signature_exact"] is True

    rounded_rows = _rows()
    rounded_tem = next(
        row for row in rounded_rows if row["execution_id"] == replay.TEM_DUPLICATE_EXECUTION_ID
    )
    rounded_tem["price"] = 52.905
    rounded = _payload(rounded_rows)
    assert rounded["overall"] == "fail"
    assert rounded["known_invalid_execution_disposition"]["tem_duplicate"]["failed_checks"] == ["price"]


def test_sls_signature_mismatch_fails_closed_before_projection():
    payload = _payload(_rows(sls_bad_price=18.0))

    assert payload["overall"] == "fail"
    assert payload["diagnosis"] == "known_invalid_execution_signature_not_exact_recovery_gate_blocked"
    assert payload["known_invalid_execution_disposition"]["sls_bad_partial_exit"]["signature_exact"] is False
    assert payload["projection"]["projection_complete"] is False


def test_tost_signature_mismatch_fails_closed_before_projection():
    payload = _payload(_rows(tost_bad_2_price=36.45))

    assert payload["overall"] == "fail"
    assert payload["known_invalid_execution_disposition"]["tost_bad_partial_exit_2"]["signature_exact"] is False
    assert payload["known_invalid_execution_disposition"]["tost_bad_partial_exit_2"]["failed_checks"] == ["price"]
    assert payload["projection"]["projection_complete"] is False


def test_newer_valid_row_after_latest_known_invalid_requires_review_without_mutation():
    rows = _rows() + [
        _row(
            "later-valid-entry",
            "entry",
            "LATER",
            "long",
            10.0,
            1.0,
            "2026-08-21 14:45:00 CDT",
        )
    ]
    payload = _payload(rows)

    assert payload["overall"] == "warn"
    assert payload["diagnosis"] == "verified_v2_replay_complete_but_newer_canonical_rows_require_review"
    assert payload["canonical_rows_after_last_known_invalid_count"] == 1
    assert payload["recovery_readiness"]["state_write_authorized_by_this_probe"] is False


def test_unmatched_remaining_exit_fails_projection_without_mutation():
    rows = _rows() + [
        _row(
            "bad-successor-exit",
            "exit",
            "MISSING",
            "long",
            10.0,
            1.0,
            "2026-08-21 14:45:00 CDT",
            "normal_exit",
        )
    ]
    payload = _payload(rows)

    assert payload["overall"] == "fail"
    assert payload["diagnosis"] == "verified_v2_counterfactual_replay_failed_on_remaining_canonical_execution"
    assert payload["projection"]["errors"][0]["reason"] == "exit_exceeds_projected_position"
    assert payload["recovery_readiness"]["halt_clear_authorized_by_this_probe"] is False


def test_startup_apply_does_not_read_ledger_or_runtime_state():
    with mock.patch.object(ledger, "_read_rows", side_effect=AssertionError("must not read ledger")):
        payload = replay.apply(FakeCore())

    assert payload["status"] == "ok"
    assert payload["startup_reads_runtime_state"] is False
    assert payload["startup_reads_canonical_ledger"] is False
    assert payload["startup_writes_state_or_files"] is False
    assert payload["consolidates_manual_forensic_routes"] is True


def test_tem_provenance_now_matches_immutable_canonical_precision_without_mutation():
    rows = _rows()
    with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(
        ledger, "_verify_rows", return_value=(True, [])
    ):
        payload = temprov.tem_duplicate_provenance_payload(FakeCore())

    assert payload["overall"] == "pass"
    assert payload["signature_exact"] is True
    assert payload["failed_checks"] == []
    assert payload["observed_row"]["price"] == replay.TEM_DUPLICATE_PRICE
    assert payload["authority"]["writes_files"] is False
