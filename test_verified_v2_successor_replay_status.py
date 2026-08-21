from __future__ import annotations

from unittest import mock

import canonical_execution_ledger as ledger
import verified_v2_successor_replay_status as replay


class FakeCore:
    def __init__(self):
        self.portfolio = {
            "cash": 11727.490311347749,
            "equity": 11864.0,
            "accounting_epoch_id": replay.TARGET_EPOCH_ID,
            "paper_accounting_epoch": {"id": replay.TARGET_EPOCH_ID},
            "trades": [],
            "positions": {
                "SLS": {
                    "side": "long",
                    "shares": 6.497145,
                    "entry": 14.335,
                    "last_price": 15.46,
                },
                "TOST": {
                    "side": "long",
                    "shares": 1.0,
                    "entry": 36.0,
                    "last_price": 36.4,
                },
            },
        }

    def local_ts_text(self):
        return "2026-08-21 16:00:00 CDT"


def _row(execution_id, action, symbol, side, price, shares, recorded_local):
    return {
        "execution_id": execution_id,
        "accounting_epoch_id": replay.TARGET_EPOCH_ID,
        "action": action,
        "symbol": symbol,
        "side": side,
        "price": price,
        "shares": shares,
        "recorded_local": recorded_local,
        "event_hash": f"hash-{execution_id}",
    }


def _rows(sls_bad_price=replay.SLS_BAD_PRICE):
    return [
        _row(
            "lrcx-valid-exit",
            "exit",
            "LRCX",
            "long",
            333.12,
            replay.BASELINE_LRCX_QTY,
            "2026-08-14 09:18:46 CDT",
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
        ),
        _row(
            replay.TEM_DUPLICATE_EXECUTION_ID,
            "exit",
            "TEM",
            "long",
            replay.TEM_DUPLICATE_PRICE,
            replay.TEM_DUPLICATE_QTY,
            "2026-08-14 08:48:37 CDT",
        ),
        _row(
            "sls-entry",
            "entry",
            "SLS",
            "long",
            14.335,
            6.497145,
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
        ),
        _row(
            "successor-entry",
            "entry",
            "TOST",
            "long",
            36.0,
            1.0,
            "2026-08-21 10:05:00 CDT",
        ),
    ]


def _payload(rows):
    with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(
        ledger, "_verify_rows", return_value=(True, [])
    ):
        return replay.status_payload(FakeCore())


def test_verified_v2_replay_excludes_only_two_exact_invalid_rows_and_replays_successor():
    payload = _payload(_rows())

    assert payload["overall"] == "pass"
    assert payload["diagnosis"] == "verified_v2_successor_replay_mechanically_complete"
    assert payload["successor_row_count"] == 1
    assert payload["successor_rows_after_sls_bad_execution"][0]["execution_id"] == "successor-entry"

    disposition = payload["known_invalid_execution_disposition"]
    assert disposition["tem_duplicate"]["signature_exact"] is True
    assert disposition["sls_bad_partial_exit"]["signature_exact"] is True
    assert disposition["tem_duplicate"]["immutable_row_retained"] is True
    assert disposition["sls_bad_partial_exit"]["immutable_row_retained"] is True

    projection = payload["projection"]
    assert projection["projection_complete"] is True
    assert projection["applied_execution_count"] == 5
    assert projection["excluded_execution_count"] == 2
    assert abs(projection["candidate_cash"] - 11727.490311348) < 1e-9
    assert abs(projection["candidate_realized_delta_from_verified_baseline"] - 16.49045994) < 1e-9
    assert abs(projection["candidate_realized_today_delta"]) < 1e-9
    projected = {row["symbol"]: row for row in projection["candidate_positions"]}
    assert abs(projected["SLS"]["shares"] - 6.497145) < 1e-9
    assert abs(projected["TOST"]["shares"] - 1.0) < 1e-9

    comparison = payload["state_comparison"]
    assert comparison["successor_execution_presence_in_state_trades"] == [
        {
            "execution_id": "successor-entry",
            "symbol": "TOST",
            "action": "entry",
            "present_in_state_trades": False,
        }
    ]
    assert comparison["all_projected_positions_match_current_quantity_side_entry"] is True
    assert payload["recovery_readiness"]["state_write_authorized_by_this_probe"] is False
    assert payload["authority"]["rewrites_or_relabels_canonical_ledger"] is False


def test_sls_signature_mismatch_fails_closed_before_projection():
    payload = _payload(_rows(sls_bad_price=18.0))

    assert payload["overall"] == "fail"
    assert payload["diagnosis"] == "known_invalid_execution_signature_not_exact_successor_replay_blocked"
    assert payload["known_invalid_execution_disposition"]["sls_bad_partial_exit"]["signature_exact"] is False
    assert payload["projection"]["projection_complete"] is False


def test_unmatched_remaining_exit_fails_projection_without_mutation():
    rows = _rows() + [
        _row(
            "bad-successor-exit",
            "exit",
            "MISSING",
            "long",
            10.0,
            1.0,
            "2026-08-21 10:10:00 CDT",
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
