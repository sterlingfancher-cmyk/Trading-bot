from __future__ import annotations

import copy
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
        return "2026-08-25 10:45:00 CDT"


def _row(
    execution_id,
    action,
    symbol,
    side,
    price,
    shares,
    recorded_local,
    exit_reason=None,
    event_hash=None,
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
        "event_hash": event_hash or f"hash-{execution_id}",
    }


def _ledger_only_rows():
    return [
        _row(
            replay.PATH_LEDGER_ONLY_EXECUTION_ID,
            "entry",
            "PATH",
            "long",
            15.515,
            23.575864641,
            "2026-08-13 13:23:32 CDT",
            event_hash="e7e3a5d8222fcf5c597388f3ed09a3d5473fd72f1af7bfa0e2a138415cbb0f36",
        ),
        _row(
            replay.PANW_LEDGER_ONLY_EXECUTION_ID,
            "entry",
            "PANW",
            "long",
            393.570007,
            4.130616789,
            "2026-08-13 13:23:48 CDT",
            event_hash="8b7ce33541caf4b9a381fcffc799afd7e9e83163dac26838fbb5b440c7622a2f",
        ),
        _row(
            replay.SNOW_LEDGER_ONLY_EXECUTION_ID,
            "entry",
            "SNOW",
            "long",
            339.554993,
            3.638969198,
            "2026-08-13 13:46:28 CDT",
            event_hash="469096a1e7d682769ebfafb47dca04e2ea988b738a6d8d7df9ecde25967dbc91",
        ),
        _row(
            replay.CRWD_LEDGER_ONLY_EXECUTION_ID,
            "entry",
            "CRWD",
            "long",
            226.5,
            5.455320793,
            "2026-08-13 13:46:49 CDT",
            event_hash="2641f3fc1a7d8631246987546edb5ca201c6eae3c84d0799e3c9c9880147c156",
        ),
    ]


def _rows(
    sls_bad_price=replay.SLS_BAD_PRICE,
    tost_bad_2_price=190.244995,
    uctt_partial_price=337.540009,
    uctt_partial_shares=5.74554981,
    uctt_partial_hash="c7e23d77ecc86e6521f702b814828815a9f17e8f697c9baf07490be0e96ee41b",
):
    return (
        _ledger_only_rows()
        + [
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
                "uctt-entry",
                "entry",
                "UCTT",
                "long",
                93.22,
                17.410757,
                "2026-08-13 11:01:06 CDT",
            ),
            _row(
                replay.UCTT_BAD_PARTIAL_EXECUTION_ID,
                "partial_exit",
                "UCTT",
                "long",
                uctt_partial_price,
                uctt_partial_shares,
                "2026-08-13 14:37:13 CDT",
                "partial_profit_long",
                uctt_partial_hash,
            ),
            _row(
                "uctt-valid-exit",
                "exit",
                "UCTT",
                "long",
                94.025,
                11.665207,
                "2026-08-13 14:45:10 CDT",
                "normal_exit",
            ),
            _row(
                replay.UCTT_BAD_DUPLICATE_EXIT_EXECUTION_ID,
                "exit",
                "UCTT",
                "long",
                39.145,
                11.665207,
                "2026-08-13 14:59:04 CDT",
                "stop_loss",
                "d928b227f1f800b38e1b31fed9c35c9e62f2417f58c28b2d602a7c4104b71812",
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
    )


def _payload(rows):
    with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(
        ledger, "_verify_rows", return_value=(True, [])
    ):
        return replay.status_payload(FakeCore())


def test_consolidated_gate_excludes_exact_eleven_invalid_rows_and_replays_everything_else():
    rows = _rows()
    before = copy.deepcopy(rows)
    payload = _payload(rows)

    assert rows == before
    assert payload["overall"] == "pass"
    assert payload["diagnosis"] == "verified_v2_consolidated_recovery_gate_mechanically_complete"
    assert payload["known_invalid_execution_count"] == 11
    assert payload["all_known_invalid_signatures_exact"] is True
    assert payload["latest_invalid_is_last_canonical_execution"] is True
    assert payload["canonical_rows_after_last_known_invalid_count"] == 0

    disposition = payload["known_invalid_execution_disposition"]
    assert set(disposition) == {
        "path_ledger_only_entry_artifact",
        "panw_ledger_only_entry_artifact",
        "snow_ledger_only_entry_artifact",
        "crwd_ledger_only_entry_artifact",
        "tem_duplicate",
        "uctt_bad_partial_exit",
        "uctt_bad_duplicate_exit",
        "sls_bad_partial_exit",
        "tost_bad_partial_exit_1",
        "tost_bad_partial_exit_2",
        "tost_bad_partial_exit_3",
    }
    assert all(item["signature_exact"] for item in disposition.values())
    assert all(item["immutable_row_retained"] for item in disposition.values())

    projection = payload["projection"]
    assert projection["projection_complete"] is True
    assert projection["applied_execution_count"] == 7
    assert projection["excluded_execution_count"] == 11
    projected = {row["symbol"]: row for row in projection["candidate_positions"]}
    assert all(symbol not in projected for symbol in ("PATH", "PANW", "SNOW", "CRWD"))
    assert abs(projected["UCTT"]["shares"] - 5.74555) < 1e-9
    assert abs(projected["SLS"]["shares"] - 6.497144521) < 1e-9
    assert abs(projected["TOST"]["shares"] - 3.767684364) < 1e-9

    comparison = payload["state_comparison"]
    assert comparison["unexplained_position_mismatches"] == []
    assert comparison["only_known_invalid_symbols_differ"] is True
    readiness = payload["recovery_readiness"]
    assert readiness["all_eleven_known_invalid_rows_exact"] is True
    assert readiness["latest_known_invalid_must_be_terminal"] is False
    assert readiness["mechanically_complete_for_successor_migration_design"] is True
    assert readiness["manual_per_event_probe_required"] is False
    assert readiness["state_write_authorized_by_this_probe"] is False
    assert payload["authority"]["rewrites_or_relabels_canonical_ledger"] is False


def test_ledger_only_entry_signature_mismatch_fails_closed():
    rows = _rows()
    path = next(row for row in rows if row["execution_id"] == replay.PATH_LEDGER_ONLY_EXECUTION_ID)
    path["event_hash"] = "wrong-hash"

    payload = _payload(rows)

    assert payload["overall"] == "fail"
    assert payload["diagnosis"] == "known_invalid_execution_signature_not_exact_recovery_gate_blocked"
    item = payload["known_invalid_execution_disposition"]["path_ledger_only_entry_artifact"]
    assert item["signature_exact"] is False
    assert item["failed_checks"] == ["event_hash"]
    assert payload["projection"]["projection_complete"] is False


def test_exact_artifact_does_not_create_broad_symbol_exclusion():
    rows = _rows() + [
        _row(
            "later-valid-path-entry",
            "entry",
            "PATH",
            "long",
            16.0,
            1.0,
            "2026-08-24 10:00:00 CDT",
        )
    ]

    projection = replay._project(rows)

    assert projection["projection_complete"] is True
    assert any(row["execution_id"] == "later-valid-path-entry" for row in projection["applied_executions"])
    projected = {row["symbol"]: row for row in projection["candidate_positions"]}
    assert projected["PATH"]["shares"] == 1.0


def test_tem_canonical_precision_is_exact_and_display_rounding_is_not_accepted_as_the_signature():
    rows = _rows()
    tem = next(row for row in rows if row["execution_id"] == replay.TEM_DUPLICATE_EXECUTION_ID)
    assert tem["price"] == 52.904999
    assert _payload(rows)["known_invalid_execution_disposition"]["tem_duplicate"]["signature_exact"] is True

    rounded_rows = _rows()
    rounded_tem = next(row for row in rounded_rows if row["execution_id"] == replay.TEM_DUPLICATE_EXECUTION_ID)
    rounded_tem["price"] = 52.905
    rounded = _payload(rounded_rows)
    assert rounded["overall"] == "fail"
    assert rounded["known_invalid_execution_disposition"]["tem_duplicate"]["failed_checks"] == ["price"]


def test_uctt_partial_uses_exact_canonical_precision_and_event_hash():
    payload = _payload(_rows())
    uctt = payload["known_invalid_execution_disposition"]["uctt_bad_partial_exit"]
    assert uctt["signature_exact"] is True
    assert uctt["failed_checks"] == []
    assert uctt["observed_row"]["price"] == 337.540009
    assert uctt["observed_row"]["shares"] == 5.74554981

    rounded = _payload(_rows(uctt_partial_price=337.54, uctt_partial_shares=5.74555))
    assert rounded["overall"] == "fail"
    assert rounded["known_invalid_execution_disposition"]["uctt_bad_partial_exit"]["failed_checks"] == ["price", "shares"]

    changed_hash = _payload(_rows(uctt_partial_hash="wrong-hash"))
    assert changed_hash["overall"] == "fail"
    assert changed_hash["known_invalid_execution_disposition"]["uctt_bad_partial_exit"]["failed_checks"] == ["event_hash"]
    assert changed_hash["projection"]["projection_complete"] is False


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


def test_newer_valid_rows_after_latest_invalid_are_replayed_and_do_not_block_gate():
    rows = _rows() + [
        _row(
            "later-valid-entry",
            "entry",
            "LATER",
            "long",
            10.0,
            1.0,
            "2026-08-24 14:45:00 CDT",
        )
    ]
    core = FakeCore()
    core.portfolio["positions"].update(
        {
            "LATER": {
                "side": "long",
                "shares": 1.0,
                "entry": 10.0,
                "last_price": 10.0,
            }
        }
    )
    with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(
        ledger, "_verify_rows", return_value=(True, [])
    ):
        payload = replay.status_payload(core)

    assert payload["overall"] == "pass"
    assert payload["diagnosis"] == "verified_v2_consolidated_recovery_gate_mechanically_complete"
    assert payload["latest_invalid_is_last_canonical_execution"] is False
    assert payload["canonical_rows_after_last_known_invalid_count"] == 1
    assert payload["canonical_rows_after_last_known_invalid"][0]["execution_id"] == "later-valid-entry"
    assert payload["recovery_readiness"]["latest_known_invalid_must_be_terminal"] is False
    assert payload["recovery_readiness"]["later_canonical_rows_replayed_in_original_order"] is True
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
            "2026-08-24 14:45:00 CDT",
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
