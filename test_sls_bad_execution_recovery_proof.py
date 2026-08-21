from __future__ import annotations

from unittest import mock

import canonical_execution_ledger as ledger
import sls_bad_execution_recovery_proof as proof


class FakeCore:
    def __init__(self):
        current_qty = proof.ENTRY_SHARES - proof.BAD_SHARES
        self.portfolio = {
            "cash": 13159.073498029464,
            "equity": 13541.73,
            "accounting_epoch_id": proof.TARGET_EPOCH_ID,
            "paper_accounting_epoch": {"id": proof.TARGET_EPOCH_ID},
            "positions": {
                "SLS": {
                    "side": "long",
                    "shares": current_qty,
                    "entry": proof.ENTRY_PRICE,
                    "last_price": 15.48,
                    "peak": proof.BAD_PRICE,
                }
            },
            "realized_pnl": {
                "today": (proof.BAD_PRICE - proof.ENTRY_PRICE) * proof.BAD_SHARES,
                "total": -406.58,
            },
            "trades": [
                {
                    "execution_id": proof.ENTRY_EXECUTION_ID,
                    "accounting_epoch_id": proof.TARGET_EPOCH_ID,
                    "action": "entry",
                    "symbol": "SLS",
                    "side": "long",
                    "price": proof.ENTRY_PRICE,
                    "shares": proof.ENTRY_SHARES,
                    "time": 1787323176,
                },
                {
                    "execution_id": proof.BAD_EXECUTION_ID,
                    "accounting_epoch_id": proof.TARGET_EPOCH_ID,
                    "action": "partial_exit",
                    "symbol": "SLS",
                    "side": "long",
                    "price": proof.BAD_PRICE,
                    "shares": proof.BAD_SHARES,
                    "time": 1787323873,
                    "exit_reason": "partial_profit_long",
                },
            ],
        }

    def local_ts_text(self):
        return "2026-08-21 14:30:00 CDT"


def _ledger_rows(extra_after_bad=False):
    rows = [
        {
            "execution_id": proof.ENTRY_EXECUTION_ID,
            "accounting_epoch_id": proof.TARGET_EPOCH_ID,
            "action": "entry",
            "symbol": "SLS",
            "side": "long",
            "price": proof.ENTRY_PRICE,
            "shares": proof.ENTRY_SHARES,
            "recorded_local": "2026-08-21 09:39:36 CDT",
            "event_hash": "entry-hash",
        },
        {
            "execution_id": proof.BAD_EXECUTION_ID,
            "accounting_epoch_id": proof.TARGET_EPOCH_ID,
            "action": "partial_exit",
            "symbol": "SLS",
            "side": "long",
            "price": proof.BAD_PRICE,
            "shares": proof.BAD_SHARES,
            "recorded_local": "2026-08-21 09:51:13 CDT",
            "exit_reason": "partial_profit_long",
            "event_hash": "bad-hash",
        },
    ]
    if extra_after_bad:
        rows.append(
            {
                "execution_id": "later-valid-execution",
                "accounting_epoch_id": proof.TARGET_EPOCH_ID,
                "action": "entry",
                "symbol": "TOST",
                "side": "long",
                "price": 36.5,
                "shares": 1.0,
                "recorded_local": "2026-08-21 10:05:00 CDT",
                "event_hash": "later-hash",
            }
        )
    return rows


def _payload(extra_after_bad=False):
    core = FakeCore()
    rows = _ledger_rows(extra_after_bad=extra_after_bad)
    with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(
        ledger, "_verify_rows", return_value=(True, [])
    ):
        return proof.status_payload(core)


def test_exact_terminal_bad_execution_counterfactual_is_proven():
    payload = _payload(extra_after_bad=False)

    assert payload["overall"] == "pass"
    assert payload["diagnosis"] == "exact_invalid_terminal_sls_execution_counterfactual_proven"
    assert payload["exact_execution_proven"] is True
    assert payload["no_later_canonical_execution"] is True

    ledger_evidence = payload["canonical_ledger_evidence"]
    assert ledger_evidence["chain_valid"] is True
    assert ledger_evidence["bad_is_last_canonical_execution"] is True
    assert ledger_evidence["canonical_rows_after_bad"] == 0

    economics = payload["economic_counterfactual"]
    bad = economics["exact_bad_execution_economics"]
    assert abs(bad["cash_proceeds"] - 399.416779226) < 1e-9
    assert abs(bad["realized_pnl"] - 368.681707796) < 1e-9

    candidate = economics["counterfactual_if_exact_bad_partial_exit_is_reversed"]
    assert abs(candidate["cash"] - 12759.656718804) < 1e-9
    assert abs(candidate["sls_shares"] - proof.ENTRY_SHARES) < 1e-9
    assert abs(candidate["equity_using_current_stored_sls_mark"] - 13175.503238614) < 1e-9
    assert abs(candidate["realized_today"]) < 1e-9

    assert economics["not_proven_or_not_rewritten"]["day_peak_equity"] is None
    assert payload["recovery_readiness"]["state_write_authorized_by_this_probe"] is False
    assert payload["authority"]["rewrites_or_relabels_canonical_ledger"] is False


def test_later_canonical_execution_requires_successor_replay():
    payload = _payload(extra_after_bad=True)

    assert payload["overall"] == "warn"
    assert payload["diagnosis"] == "exact_invalid_sls_execution_proven_but_successor_replay_required"
    assert payload["exact_execution_proven"] is True
    assert payload["no_later_canonical_execution"] is False
    assert payload["canonical_ledger_evidence"]["canonical_rows_after_bad"] == 1
    assert payload["canonical_ledger_evidence"]["canonical_execution_ids_after_bad"] == [
        "later-valid-execution"
    ]


def test_quantity_mismatch_blocks_exact_counterfactual_proof():
    core = FakeCore()
    core.portfolio["positions"]["SLS"]["shares"] = 1.0
    rows = _ledger_rows(extra_after_bad=False)

    with mock.patch.object(ledger, "_read_rows", return_value=(rows, [])), mock.patch.object(
        ledger, "_verify_rows", return_value=(True, [])
    ):
        payload = proof.status_payload(core)

    assert payload["overall"] == "warn"
    assert payload["diagnosis"] == "sls_bad_execution_counterfactual_not_fully_proven"
    assert payload["exact_execution_proven"] is False
    assert (
        payload["economic_counterfactual"]["position_consistency"]
        ["current_plus_bad_exit_qty_matches_original_entry_qty"]
        is False
    )


def test_startup_apply_does_not_scan_ledger_or_runtime_state():
    with mock.patch.object(ledger, "_read_rows", side_effect=AssertionError("must not read ledger")):
        payload = proof.apply(FakeCore())

    assert payload["status"] == "ok"
    assert payload["startup_reads_runtime_state"] is False
    assert payload["startup_reads_canonical_ledger"] is False
