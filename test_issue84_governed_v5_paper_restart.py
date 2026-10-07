from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path
import types
import pytest

import canonical_execution_ledger as ledger
import clean_epoch_successor_compatibility as clean_compat
import governed_v5_paper_restart as restart
import governed_v5_runtime_exit_recovery as exit_recovery
import issue222_verified_flat_successor as successor
import market_surge_canonical_execution_bridge as surge_bridge
import market_surge_deployment_mode as surge_deployment
import market_surge_queue_canonical_execution_bridge as queue_bridge
import market_surge_queue_executor as surge_queue
import paper_accounting_integrity_guard as accounting
import paper_bidirectional_accounting_guard as bidirectional
import paper_participation_allocator as participation_allocator
import paper_underdeployment_repair as underdeployment_repair
import risk_reward_structure
import multi_timeframe_swing
import fundamental_valuation_risk_layer
import loss_streak_defensive_governor
import paper_controlled_expansion
import pattern_recognition_layer
import regime_flip_entry_guard
import theme_starter_exception


def _state() -> dict:
    state = successor.build_successor_state(
        {
            "cash": 13429.13048559457,
            "equity": 13429.13,
            "positions": {},
            "trades": [],
            "history": [13429.13],
            "realized_pnl": {
                "date": "2026-09-25",
                "today": 0.0,
                "total": -514.18,
                "wins_today": 0,
                "losses_today": 0,
                "wins_total": 15,
                "losses_total": 32,
            },
            "performance": {"open_positions": {}, "unrealized_pnl": 0.0},
            "risk_controls": {
                "date": "2026-09-25",
                "day_start_equity": 13429.13048559457,
                "day_peak_equity": 13429.13048559457,
                "halted": True,
                "halt_reason": restart.RETAINED_HALT_REASON,
                "daily_loss_pct": 0.0,
                "intraday_drawdown_pct": 0.0,
            },
        },
        "/immutable/issue222-forensic-archive",
        "2026-09-14 16:00:00 CDT",
        [],
    )
    state["issue222_verified_flat_successor"] = {
        "version": successor.VERSION,
        "status": "validation_hold",
        "prior_epoch_id": successor.OLD_EPOCH_ID,
        "target_epoch_id": successor.TARGET_EPOCH_ID,
        "unresolved_prior_discrepancy": True,
        "prior_epoch_economics_promotable": False,
        "fabricated_exit_rows": 0,
        "risk_halt_cleared": False,
        "canonical_history_rewritten": False,
    }
    return state


class FakeCore(types.SimpleNamespace):
    MAX_DAILY_LOSS_PCT = 0.03
    MAX_INTRADAY_DRAWDOWN_PCT = 0.025
    GOVERNED_V5_STATIC_EXECUTION_BOUNDARIES = True

    def __init__(self, state: dict, persisted_path: Path):
        super().__init__()
        self.portfolio = state
        self.persisted_path = persisted_path
        self.local_ts_text = lambda *args, **kwargs: "2026-09-25 10:00:00 CDT"

        def save_state(value=None):
            payload = value if isinstance(value, dict) else self.portfolio
            self.persisted_path.write_text(json.dumps(payload), encoding="utf-8")

        self.save_state = save_state

        def record_trade(action, symbol, side, px, shares, extra=None):
            row = {
                "time": 1790359200,
                "action": action,
                "symbol": symbol,
                "side": side,
                "price": round(float(px), 4),
                "shares": round(float(shares), 6),
            }
            row.update(extra or {})
            self.portfolio.setdefault("trades", []).append(row)
            return row

        self.record_trade = record_trade

        def enter_position(signal, params, market_mode=None):
            symbol = signal["symbol"]
            if symbol in self.portfolio["positions"]:
                return {"symbol": symbol, "blocked": True, "reason": "already_held"}
            side = signal["side"]
            px = float(signal["price"])
            shares = float(signal.get("shares", 1.0))
            notional = px * shares
            self.portfolio["cash"] -= notional
            self.portfolio["positions"][symbol] = {
                "side": side,
                "entry": px,
                "last_price": px,
                "shares": shares,
                "entry_time": int(signal.get("entry_time", 1790359200)),
                **({"margin": notional, "trough": px} if side == "short" else {"peak": px}),
            }
            self.portfolio["equity"] = round(
                self.portfolio["cash"] + _position_value(self.portfolio["positions"][symbol], px),
                2,
            )
            self.record_trade("entry", symbol, side, px, shares, {"market_mode": market_mode})
            return {"symbol": symbol, "side": side, "entry": px, "shares": shares}

        def exit_position(symbol, px, reason, market_mode=None, extra=None):
            pos = self.portfolio["positions"].get(symbol)
            if not pos:
                return None
            qty = float(pos["shares"])
            entry = float(pos["entry"])
            if pos["side"] == "short":
                pnl = (entry - float(px)) * qty
                self.portfolio["cash"] += float(pos["margin"]) + pnl
            else:
                pnl = (float(px) - entry) * qty
                self.portfolio["cash"] += float(px) * qty
            del self.portfolio["positions"][symbol]
            self.portfolio["equity"] = round(self.portfolio["cash"], 2)
            self.record_trade(
                "exit",
                symbol,
                pos["side"],
                px,
                qty,
                {"exit_reason": reason, "pnl_dollars": pnl},
            )
            return {"symbol": symbol, "shares": qty, "pnl_dollars": pnl}

        self.enter_position = enter_position
        self.exit_position = exit_position

    def reduce_position(
        self, symbol, px, fraction, reason, market_mode=None, extra=None
    ):
        pos = self.portfolio["positions"].get(symbol)
        if not pos:
            return None
        total = float(pos["shares"])
        qty = total * float(fraction)
        entry = float(pos["entry"])
        if pos["side"] == "short":
            margin_release = float(pos["margin"]) * float(fraction)
            pnl = (entry - float(px)) * qty
            pos["margin"] -= margin_release
            self.portfolio["cash"] += margin_release + pnl
        else:
            pnl = (float(px) - entry) * qty
            self.portfolio["cash"] += float(px) * qty
        pos["shares"] -= qty
        pos["last_price"] = float(px)
        self.portfolio["equity"] = round(
            self.portfolio["cash"] + _position_value(pos, float(px)), 2
        )
        self.record_trade(
            "partial_exit",
            symbol,
            pos["side"],
            px,
            qty,
            {"exit_reason": reason, "pnl_dollars": pnl},
        )
        return {
            "symbol": symbol,
            "shares_closed": qty,
            "remaining_shares": pos["shares"],
        }


def _position_value(pos: dict, px: float) -> float:
    if pos["side"] == "short":
        return float(pos["margin"]) + (float(pos["entry"]) - px) * float(pos["shares"])
    return px * float(pos["shares"])


def _wire_static_boundaries(monkeypatch, core: FakeCore) -> None:
    for name, operation in (
        ("enter_position", "entry"),
        ("reduce_position", "partial_exit"),
        ("exit_position", "full_exit"),
    ):
        prior = getattr(core, name)

        def governed(*args, _prior=prior, _operation=operation, **kwargs):
            return restart.execute_single_operation(
                core,
                _operation,
                lambda: _prior(*args, **kwargs),
                args,
                kwargs,
            )

        monkeypatch.setattr(core, name, governed)


def _activate(monkeypatch, tmp_path: Path, state: dict | None = None) -> FakeCore:
    ledger_path = tmp_path / "canonical.jsonl"
    monkeypatch.setattr(ledger, "LEDGER_FILE", str(ledger_path))
    monkeypatch.setattr(restart, "LOCK_FILE", str(tmp_path / ".execution.lock"))
    monkeypatch.setattr(restart, "EXPECTED_PRESTART_LEDGER_ROWS", 0)
    monkeypatch.setattr(restart, "EXPECTED_PRESTART_LEDGER_SHA256", sha256(b"").hexdigest())
    core = FakeCore(state or _state(), tmp_path / "state.json")
    ledger.apply(core)
    monkeypatch.setattr(
        surge_deployment,
        "_append_trade_rows",
        surge_deployment._append_trade_rows,
    )
    monkeypatch.setattr(
        surge_queue,
        "execute_surge_queue",
        surge_queue.execute_surge_queue,
    )
    surge_bridge.apply(core)
    queue_bridge.apply(core)
    result = restart.apply(core)
    assert result["status"] == "active", result
    _wire_static_boundaries(monkeypatch, core)
    return core


def test_governed_release_requires_exact_prestart_evidence(monkeypatch, tmp_path):
    state = _state()
    state["cash"] += 1.0
    core = FakeCore(state, tmp_path / "state.json")
    monkeypatch.setattr(ledger, "LEDGER_FILE", str(tmp_path / "canonical.jsonl"))
    ledger.apply(core)
    result = restart.apply(core)
    assert result["status"] == "blocked"
    assert "positive_flat_valuation" in result["failed_checks"]
    assert state["paper_accounting_epoch"]["validation_hold"] is True
    assert state["risk_controls"]["halted"] is True


def test_governed_entry_flag_crosses_runtime_allocation_wrappers(monkeypatch):
    calls = []

    def base_enter(signal, params, market_mode=None, _governed=False):
        calls.append(
            {
                "signal": signal,
                "params": params,
                "market_mode": market_mode,
                "governed": _governed,
            }
        )
        return {"symbol": signal["symbol"], "blocked": False}

    core = types.SimpleNamespace(
        enter_position=base_enter,
        portfolio={"positions": {}, "trades": [], "risk_controls": {}},
    )
    monkeypatch.setattr(
        participation_allocator,
        "_target_alloc_for_signal",
        lambda signal, params, runtime: (None, {}),
    )

    assert participation_allocator._patch_enter(core) is True
    assert underdeployment_repair._patch_enter(core) is True

    result = core.enter_position(
        {"symbol": "QQQ", "side": "long"},
        {},
        market_mode="risk_on",
        _governed=True,
    )

    assert result == {"symbol": "QQQ", "blocked": False}
    assert calls == [
        {
            "signal": {"symbol": "QQQ", "side": "long"},
            "params": {},
            "market_mode": "risk_on",
            "governed": True,
        }
    ]


def test_governed_entry_flag_crosses_full_runtime_wrapper_stack(monkeypatch):
    calls = []

    def base_enter(signal, params, market_mode=None, _governed=False):
        calls.append(_governed)
        return {"symbol": signal["symbol"], "blocked": False}

    core = types.SimpleNamespace(
        enter_position=base_enter,
        portfolio={"positions": {}, "trades": [], "risk_controls": {}},
    )
    core.enter_position = risk_reward_structure._wrap_enter(
        core, core.enter_position
    )
    monkeypatch.setitem(
        multi_timeframe_swing._ORIGINALS,
        "enter_position",
        core.enter_position,
    )
    multi_timeframe_swing._wrap_enter(core)
    monkeypatch.setattr(
        fundamental_valuation_risk_layer,
        "_risk_for_symbol",
        lambda *args, **kwargs: {"risk_multiplier": 1.0},
    )
    assert fundamental_valuation_risk_layer._patch_enter_position(core) is True
    monkeypatch.setattr(
        loss_streak_defensive_governor,
        "_govern_signal",
        lambda *args, **kwargs: (True, {}),
    )
    assert loss_streak_defensive_governor.apply(core)["status"] == "ok"
    assert pattern_recognition_layer.apply(core)["status"] == "ok"
    assert paper_controlled_expansion._patch_enter_position(core) is True
    assert theme_starter_exception._patch_enter_position(core) is True
    monkeypatch.setattr(
        regime_flip_entry_guard,
        "_entry_guard",
        lambda *args, **kwargs: (True, {}),
    )
    assert regime_flip_entry_guard._patch_enter_position(core) is True

    core.enter_position(
        {"symbol": "QQQ", "side": "long"},
        {},
        market_mode="risk_on",
        _governed=True,
    )
    assert calls == [True]


def test_governed_exit_flag_crosses_full_runtime_wrapper_stack(monkeypatch):
    calls = []

    def base_exit(
        symbol, px, reason, market_mode=None, extra=None, _governed=False
    ):
        calls.append(
            {
                "symbol": symbol,
                "market_mode": market_mode,
                "extra": extra,
                "governed": _governed,
            }
        )
        return {"symbol": symbol, "blocked": False}

    core = types.SimpleNamespace(
        exit_position=base_exit,
        portfolio={"positions": {}, "last_market": {}},
    )
    monkeypatch.setitem(
        multi_timeframe_swing._ORIGINALS,
        "exit_position",
        core.exit_position,
    )
    multi_timeframe_swing._wrap_exit(core)
    assert pattern_recognition_layer.apply(core)["status"] == "ok"

    result = core.exit_position(
        "QQQ",
        101.0,
        "target",
        market_mode="risk_on",
        extra={"source": "governed_test"},
        _governed=True,
    )

    assert result == {"symbol": "QQQ", "blocked": False}
    assert calls == [
        {
            "symbol": "QQQ",
            "market_mode": "risk_on",
            "extra": {"source": "governed_test"},
            "governed": True,
        }
    ]


def _set_exact_restored_wrapper_abort(
    core, *, state_restored=True, intent_id=restart.RECOVERABLE_ENTRY_WRAPPER_INTENT_ID
):
    details = {
        "operation": "entry",
        "intent_id": intent_id,
        "error": restart.RECOVERABLE_ENTRY_WRAPPER_ERROR,
        "canonical_rows_before": 0,
        "canonical_rows_after": 0,
        "state_restored": state_restored,
    }
    risk = core.portfolio["risk_controls"]
    risk.update(
        {
            "halted": True,
            "halt_reason": restart.PREAPPEND_ABORT_HALT_REASON,
            "governed_restart_halt_version": restart.VERSION,
            "governed_restart_halt_local": (
                restart.RECOVERABLE_ENTRY_WRAPPER_INCIDENT_LOCAL
            ),
            "governed_restart_halt_details": copy.deepcopy(details),
        }
    )
    governed = core.portfolio["governed_v5_paper_restart"]
    governed.update(
        {
            "status": "halted",
            "last_discrepancy": copy.deepcopy(details),
            "last_discrepancy_local": (
                restart.RECOVERABLE_ENTRY_WRAPPER_INCIDENT_LOCAL
            ),
        }
    )
    return details


def test_exact_restored_wrapper_abort_recovers_without_evidence_change(
    monkeypatch, tmp_path
):
    core = _activate(monkeypatch, tmp_path)
    details = _set_exact_restored_wrapper_abort(core)
    canonical_before = copy.deepcopy(ledger.status_payload(core))
    epoch_before = copy.deepcopy(core.portfolio["paper_accounting_epoch"])
    history_before = copy.deepcopy(core.portfolio["history"])
    day_start_before = core.portfolio["risk_controls"]["day_start_equity"]
    day_peak_before = core.portfolio["risk_controls"]["day_peak_equity"]

    result = restart.apply(core)

    assert result["status"] == "active"
    assert result["risk_halted"] is False
    assert core.portfolio["risk_controls"]["halted"] is False
    assert core.portfolio["risk_controls"]["halt_reason"] == ""
    recovery = result["preappend_abort_recovery"]
    assert recovery["status"] == "recovered"
    assert recovery["version"] == restart.ABORT_RECOVERY_VERSION
    assert all(recovery["checks"].values())
    assert recovery["historical_discrepancy_preserved"] is True
    assert result["last_discrepancy"] == details
    assert ledger.status_payload(core) == canonical_before
    assert core.portfolio["paper_accounting_epoch"] == epoch_before
    assert core.portfolio["history"] == history_before
    assert core.portfolio["risk_controls"]["day_start_equity"] == day_start_before
    assert core.portfolio["risk_controls"]["day_peak_equity"] == day_peak_before
    assert accounting._issue222_verified_flat_zero_trade_baseline(core.portfolio)[
        "coverage_complete"
    ] is True


def test_exact_abort_consumed_by_fresh_day_reset_is_reconciled_with_receipt(
    monkeypatch, tmp_path
):
    core = _activate(monkeypatch, tmp_path)
    details = _set_exact_restored_wrapper_abort(core)
    risk = core.portfolio["risk_controls"]
    risk.clear()
    risk.update(
        {
            "date": restart.RECOVERABLE_FRESH_DAY_RESET_DATE,
            "day_start_equity": core.portfolio["equity"],
            "day_peak_equity": core.portfolio["equity"],
            "halted": False,
            "halt_reason": "",
        }
    )
    canonical_before = copy.deepcopy(ledger.status_payload(core))

    result = restart.apply(core)

    assert result["status"] == "active"
    assert result["risk_halted"] is False
    recovery = result["preappend_abort_recovery"]
    assert recovery["status"] == "recovered"
    assert recovery["recovery_mode"] == "fresh_day_reset_consumed_halt"
    assert recovery["historical_discrepancy_preserved"] is True
    assert result["last_discrepancy"] == details
    assert risk["governed_restart_prior_halt_reason"] == restart.RETAINED_HALT_REASON
    assert risk["governed_restart_release_version"] == restart.VERSION
    assert ledger.status_payload(core) == canonical_before
    assert accounting._issue222_verified_flat_zero_trade_baseline(core.portfolio)[
        "coverage_complete"
    ] is True


def test_preappend_abort_recovery_rejects_non_exact_incident(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    _set_exact_restored_wrapper_abort(core, state_restored=False)

    result = restart.apply(core)

    assert result["status"] == "halted"
    assert result["risk_halted"] is True
    assert result["preappend_abort_recovery"] is None
    evidence = restart._preappend_abort_recovery_evidence(core)
    assert "exact_entry_wrapper_error" in evidence["failed_checks"]


def test_fresh_day_consumed_abort_drift_relatches_fail_closed(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    details = _set_exact_restored_wrapper_abort(
        core, intent_id="different-intent"
    )
    risk = core.portfolio["risk_controls"]
    risk.clear()
    risk.update(
        {
            "date": restart.RECOVERABLE_FRESH_DAY_RESET_DATE,
            "day_start_equity": core.portfolio["equity"],
            "day_peak_equity": core.portfolio["equity"],
            "halted": False,
            "halt_reason": "",
        }
    )

    result = restart.apply(core)

    assert result["status"] == "halted"
    assert result["risk_halted"] is True
    assert risk["halt_reason"] == "governed pre-append abort recovery evidence drift"
    assert result["preappend_abort_recovery"] is None
    governed = core.portfolio["governed_v5_paper_restart"]
    assert governed["last_discrepancy"] == details
    assert governed["last_recovery_failure"]["status"] == "not_applicable"
    assert governed["last_recovery_failure"]["failed_checks"] == [
        "exact_entry_wrapper_error"
    ]
    second = restart.apply(core)
    assert second["status"] == "halted"
    assert second["risk_halted"] is True


def _set_exact_pr282_failed_recovery(core):
    _set_exact_restored_wrapper_abort(core)
    passing = restart._preappend_abort_recovery_evidence(core)
    checks = copy.deepcopy(passing["checks"])
    checks.pop("recorded_incident_reference_exact")
    for name in restart.PR282_FAILED_RECOVERY_CHECKS:
        checks[name] = False
    failure = {
        "status": "not_applicable",
        "overall": "fail",
        "version": restart.PR282_FAILED_RECOVERY_VERSION,
        "failed_checks": list(restart.PR282_FAILED_RECOVERY_CHECKS),
        "checks": checks,
    }
    risk = core.portfolio["risk_controls"]
    risk.update(
        {
            "halted": True,
            "halt_reason": restart.RECOVERY_DRIFT_HALT_REASON,
            "governed_restart_halt_local": "2026-09-30 14:04:12 CDT",
            "governed_restart_halt_details": copy.deepcopy(failure),
        }
    )
    governed = core.portfolio["governed_v5_paper_restart"]
    governed.update(
        {
            "status": "halted",
            "last_discrepancy": copy.deepcopy(failure),
            "last_discrepancy_local": "2026-09-30 14:04:12 CDT",
        }
    )
    governed.pop("preappend_abort_recovery", None)
    return failure


def test_exact_pr282_failed_recovery_successor_recovers_without_rewrite(
    monkeypatch, tmp_path
):
    core = _activate(monkeypatch, tmp_path)
    failure = _set_exact_pr282_failed_recovery(core)
    canonical_before = copy.deepcopy(ledger.status_payload(core))
    epoch_before = copy.deepcopy(core.portfolio["paper_accounting_epoch"])
    history_before = copy.deepcopy(core.portfolio["history"])
    day_start_before = core.portfolio["risk_controls"]["day_start_equity"]
    day_peak_before = core.portfolio["risk_controls"]["day_peak_equity"]

    result = restart.apply(core)

    assert result["status"] == "active"
    assert result["risk_halted"] is False
    recovery = result["preappend_abort_recovery"]
    assert recovery["status"] == "recovered"
    assert recovery["recovery_mode"] == "pr282_failed_recovery_successor"
    assert recovery["incident_evidence_reference"] == (
        restart.RECOVERABLE_INCIDENT_EVIDENCE_REFERENCE
    )
    assert recovery["historical_discrepancy_rewritten"] is False
    assert result["last_discrepancy"] == failure
    assert ledger.status_payload(core) == canonical_before
    assert core.portfolio["paper_accounting_epoch"] == epoch_before
    assert core.portfolio["history"] == history_before
    assert core.portfolio["risk_controls"]["day_start_equity"] == day_start_before
    assert core.portfolio["risk_controls"]["day_peak_equity"] == day_peak_before


@pytest.mark.parametrize(
    ("intent_id", "incident_local"),
    [
        (
            restart.SUCCESSOR_WRAPPER_ABORT_INTENT_ID,
            restart.SUCCESSOR_WRAPPER_ABORT_INCIDENT_LOCAL,
        ),
        (
            restart.LATEST_WRAPPER_ABORT_INTENT_ID,
            restart.LATEST_WRAPPER_ABORT_INCIDENT_LOCAL,
        ),
    ],
)
def test_exact_post_recovery_wrapper_abort_preserves_prior_receipt(
    monkeypatch, tmp_path, intent_id, incident_local
):
    core = _activate(monkeypatch, tmp_path)
    _set_exact_pr282_failed_recovery(core)
    first = restart.apply(core)
    prior_receipt = copy.deepcopy(first["preappend_abort_recovery"])
    governed = core.portfolio["governed_v5_paper_restart"]
    rows = governed["prestart_ledger_rows"]
    discrepancy = {
        "operation": "entry",
        "intent_id": intent_id,
        "error": restart.RECOVERABLE_WRAPPER_STACK_ERROR,
        "canonical_rows_before": rows,
        "canonical_rows_after": rows,
        "state_restored": True,
    }
    checks = copy.deepcopy(prior_receipt["checks"])
    for name in restart.PR282_FAILED_RECOVERY_CHECKS:
        checks[name] = False
    failure = {
        "status": "not_applicable",
        "overall": "fail",
        "version": restart.ABORT_RECOVERY_VERSION,
        "failed_checks": list(restart.PR282_FAILED_RECOVERY_CHECKS),
        "checks": checks,
    }
    governed.update(
        {
            "status": "halted",
            "last_discrepancy": discrepancy,
            "last_discrepancy_local": incident_local,
            "last_recovery_failure": copy.deepcopy(failure),
        }
    )
    core.portfolio["risk_controls"].update(
        {
            "halted": True,
            "halt_reason": restart.RECOVERY_DRIFT_HALT_REASON,
            "governed_restart_halt_details": copy.deepcopy(failure),
        }
    )

    result = restart.apply(core)

    assert result["status"] == "active"
    assert result["risk_halted"] is False
    assert result["preappend_abort_recovery"] == prior_receipt
    successor_receipt = result["post_recovery_wrapper_abort_recovery"]
    assert successor_receipt["status"] == "recovered"
    assert successor_receipt["version"] == (
        restart.SUCCESSOR_WRAPPER_ABORT_RECOVERY_VERSION
    )
    assert successor_receipt["recovery_mode"] == (
        "post_recovery_wrapper_stack_abort"
    )
    assert governed["last_discrepancy"] == discrepancy
    assert accounting._issue222_verified_flat_zero_trade_baseline(core.portfolio)[
        "coverage_complete"
    ] is True


def test_post_recovery_wrapper_abort_rejects_near_match(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    _set_exact_pr282_failed_recovery(core)
    first = restart.apply(core)
    governed = core.portfolio["governed_v5_paper_restart"]
    rows = governed["prestart_ledger_rows"]
    discrepancy = {
        "operation": "entry",
        "intent_id": "near-match-intent",
        "error": restart.RECOVERABLE_WRAPPER_STACK_ERROR,
        "canonical_rows_before": rows,
        "canonical_rows_after": rows,
        "state_restored": True,
    }
    checks = copy.deepcopy(first["preappend_abort_recovery"]["checks"])
    for name in restart.PR282_FAILED_RECOVERY_CHECKS:
        checks[name] = False
    failure = {
        "status": "not_applicable",
        "overall": "fail",
        "version": restart.ABORT_RECOVERY_VERSION,
        "failed_checks": list(restart.PR282_FAILED_RECOVERY_CHECKS),
        "checks": checks,
    }
    governed.update(
        {
            "status": "halted",
            "last_discrepancy": discrepancy,
            "last_discrepancy_local": restart.SUCCESSOR_WRAPPER_ABORT_INCIDENT_LOCAL,
            "last_recovery_failure": copy.deepcopy(failure),
        }
    )
    core.portfolio["risk_controls"].update(
        {
            "halted": True,
            "halt_reason": restart.RECOVERY_DRIFT_HALT_REASON,
            "governed_restart_halt_details": copy.deepcopy(failure),
        }
    )

    result = restart.apply(core)

    assert result["status"] == "halted"
    assert result["risk_halted"] is True
    assert result["post_recovery_wrapper_abort_recovery"] is None


def test_exact_runtime_wrapper_abort_preserves_both_prior_recovery_receipts(
    monkeypatch, tmp_path
):
    # Bind the recovery to the independently captured incident timestamp, not
    # the later failed-recovery evaluation / halt timestamp.
    assert restart.RUNTIME_WRAPPER_ABORT_INCIDENT_LOCAL == (
        "2026-10-05 08:47:12 CDT"
    )
    assert restart.RUNTIME_WRAPPER_ABORT_EVIDENCE_REFERENCE == (
        "issue-84-comment-6001396224"
    )
    core = _activate(monkeypatch, tmp_path)
    _set_exact_pr282_failed_recovery(core)
    first = restart.apply(core)
    governed = core.portfolio["governed_v5_paper_restart"]
    rows = governed["prestart_ledger_rows"]
    first_receipt = copy.deepcopy(first["preappend_abort_recovery"])

    wrapper_discrepancy = {
        "operation": "entry",
        "intent_id": restart.LATEST_WRAPPER_ABORT_INTENT_ID,
        "error": restart.RECOVERABLE_WRAPPER_STACK_ERROR,
        "canonical_rows_before": rows,
        "canonical_rows_after": rows,
        "state_restored": True,
    }
    failed_checks = copy.deepcopy(first_receipt["checks"])
    for name in restart.PR282_FAILED_RECOVERY_CHECKS:
        failed_checks[name] = False
    failure = {
        "status": "not_applicable",
        "overall": "fail",
        "version": restart.ABORT_RECOVERY_VERSION,
        "failed_checks": list(restart.PR282_FAILED_RECOVERY_CHECKS),
        "checks": failed_checks,
    }
    governed.update(
        {
            "status": "halted",
            "last_discrepancy": wrapper_discrepancy,
            "last_discrepancy_local": restart.LATEST_WRAPPER_ABORT_INCIDENT_LOCAL,
            "last_recovery_failure": copy.deepcopy(failure),
        }
    )
    core.portfolio["risk_controls"].update(
        {
            "halted": True,
            "halt_reason": restart.RECOVERY_DRIFT_HALT_REASON,
            "governed_restart_halt_details": copy.deepcopy(failure),
        }
    )
    second = restart.apply(core)
    second_receipt = copy.deepcopy(
        second["post_recovery_wrapper_abort_recovery"]
    )

    runtime_discrepancy = {
        "operation": "entry",
        "intent_id": restart.RUNTIME_WRAPPER_ABORT_INTENT_ID,
        "error": restart.RUNTIME_WRAPPER_ABORT_ERROR,
        "canonical_rows_before": rows,
        "canonical_rows_after": rows,
        "state_restored": True,
    }
    governed.update(
        {
            "status": "halted",
            "last_discrepancy": runtime_discrepancy,
            "last_discrepancy_local": restart.RUNTIME_WRAPPER_ABORT_INCIDENT_LOCAL,
            "last_recovery_failure": copy.deepcopy(failure),
            "last_recovery_failure_local": "2026-10-05 09:07:42 CDT",
        }
    )
    core.portfolio["risk_controls"].update(
        {
            "halted": True,
            "halt_reason": restart.RECOVERY_DRIFT_HALT_REASON,
            "governed_restart_halt_details": copy.deepcopy(failure),
        }
    )

    result = restart.apply(core)

    assert result["status"] == "active"
    assert result["risk_halted"] is False
    assert result["preappend_abort_recovery"] == first_receipt
    assert result["post_recovery_wrapper_abort_recovery"] == second_receipt
    recovery = result["post_recovery_runtime_wrapper_abort_recovery"]
    assert recovery["status"] == "recovered"
    assert recovery["version"] == restart.RUNTIME_WRAPPER_ABORT_RECOVERY_VERSION
    assert recovery["recovery_mode"] == "post_recovery_runtime_wrapper_abort"
    assert recovery["incident_intent_id"] == restart.RUNTIME_WRAPPER_ABORT_INTENT_ID
    assert recovery["incident_evidence_reference"] == (
        restart.RUNTIME_WRAPPER_ABORT_EVIDENCE_REFERENCE
    )
    assert governed["last_discrepancy"] == runtime_discrepancy


def test_runtime_wrapper_abort_rejects_later_recovery_failure_timestamp(
    monkeypatch, tmp_path
):
    core = _activate(monkeypatch, tmp_path)
    _set_exact_pr282_failed_recovery(core)
    first = restart.apply(core)
    governed = core.portfolio["governed_v5_paper_restart"]
    rows = governed["prestart_ledger_rows"]

    wrapper_discrepancy = {
        "operation": "entry",
        "intent_id": restart.LATEST_WRAPPER_ABORT_INTENT_ID,
        "error": restart.RECOVERABLE_WRAPPER_STACK_ERROR,
        "canonical_rows_before": rows,
        "canonical_rows_after": rows,
        "state_restored": True,
    }
    failed_checks = copy.deepcopy(first["preappend_abort_recovery"]["checks"])
    for name in restart.PR282_FAILED_RECOVERY_CHECKS:
        failed_checks[name] = False
    failure = {
        "status": "not_applicable",
        "overall": "fail",
        "version": restart.ABORT_RECOVERY_VERSION,
        "failed_checks": list(restart.PR282_FAILED_RECOVERY_CHECKS),
        "checks": failed_checks,
    }
    governed.update(
        {
            "status": "halted",
            "last_discrepancy": wrapper_discrepancy,
            "last_discrepancy_local": restart.LATEST_WRAPPER_ABORT_INCIDENT_LOCAL,
            "last_recovery_failure": copy.deepcopy(failure),
        }
    )
    core.portfolio["risk_controls"].update(
        {
            "halted": True,
            "halt_reason": restart.RECOVERY_DRIFT_HALT_REASON,
            "governed_restart_halt_details": copy.deepcopy(failure),
        }
    )
    second = restart.apply(core)
    governed.update(
        {
            "status": "halted",
            "last_discrepancy": {
                "operation": "entry",
                "intent_id": restart.RUNTIME_WRAPPER_ABORT_INTENT_ID,
                "error": restart.RUNTIME_WRAPPER_ABORT_ERROR,
                "canonical_rows_before": rows,
                "canonical_rows_after": rows,
                "state_restored": True,
            },
            "last_discrepancy_local": "2026-10-05 09:07:42 CDT",
            "last_recovery_failure": copy.deepcopy(failure),
        }
    )
    core.portfolio["risk_controls"].update(
        {
            "halted": True,
            "halt_reason": restart.RECOVERY_DRIFT_HALT_REASON,
            "governed_restart_halt_details": copy.deepcopy(failure),
        }
    )

    result = restart.apply(core)

    assert second["post_recovery_wrapper_abort_recovery"]["status"] == "recovered"
    assert result["status"] == "halted"
    assert result["risk_halted"] is True
    assert result["post_recovery_runtime_wrapper_abort_recovery"] is None


def _set_exact_active_full_exit_abort(monkeypatch, core):
    governed = core.portfolio["governed_v5_paper_restart"]
    risk = core.portfolio["risk_controls"]
    core.portfolio.update(
        {
            "positions": {
                "QQQ": {
                    "side": "long",
                    "entry": 100.0,
                    "last_price": 101.0,
                    "shares": 1.0,
                }
            },
            "trades": [{"action": "entry", "symbol": "QQQ"}],
            "cash": 10000.0,
            "equity": 10101.0,
        }
    )
    governed["preappend_abort_recovery"] = {
        "status": "recovered",
        "version": restart.ABORT_RECOVERY_VERSION,
        "historical_discrepancy_preserved": True,
        "historical_discrepancy_rewritten": False,
    }
    governed["post_recovery_wrapper_abort_recovery"] = {
        "status": "recovered",
        "version": restart.SUCCESSOR_WRAPPER_ABORT_RECOVERY_VERSION,
        "incident_intent_id": restart.LATEST_WRAPPER_ABORT_INTENT_ID,
        "historical_discrepancy_preserved": True,
        "historical_discrepancy_rewritten": False,
    }
    governed["last_execution_receipt"] = {
        "operation": "partial_exit",
        "canonical_row_count": exit_recovery.LEDGER_ROWS,
        "canonical_last_execution_id": "latest-execution-id",
    }
    governed["last_execution_checks"] = {
        "canonical_chain_valid": True,
        "canonical_state_projection_parity": True,
        "accounting_coverage_complete": True,
    }
    discrepancy = {
        "operation": "full_exit",
        "intent_id": exit_recovery.INTENT_ID,
        "error": exit_recovery.ERROR,
        "canonical_rows_before": exit_recovery.LEDGER_ROWS,
        "canonical_rows_after": exit_recovery.LEDGER_ROWS,
        "state_restored": True,
    }
    checks = {
        name: True
        for name in restart.PR282_FAILED_RECOVERY_ALL_CHECKS
    }
    checks["recorded_incident_reference_exact"] = True
    for name in exit_recovery.FAILED_CHECKS:
        checks[name] = False
    failure = {
        "status": "not_applicable",
        "overall": "fail",
        "version": restart.ABORT_RECOVERY_VERSION,
        "failed_checks": list(exit_recovery.FAILED_CHECKS),
        "checks": checks,
    }
    governed.update(
        {
            "status": "halted",
            "last_discrepancy": discrepancy,
            "last_discrepancy_local": (
                exit_recovery.INCIDENT_LOCAL
            ),
            "last_recovery_failure": copy.deepcopy(failure),
        }
    )
    risk.update(
        {
            "halted": True,
            "halt_reason": restart.RECOVERY_DRIFT_HALT_REASON,
            "governed_restart_halt_details": copy.deepcopy(failure),
        }
    )
    canonical = {
        "hook_applied": True,
        "authoritative_for_new_executions": True,
        "chain_valid": True,
        "ledger_sha256": exit_recovery.LEDGER_SHA256,
        "row_count": exit_recovery.LEDGER_ROWS,
        "current_epoch_rows": 11,
        "state_current_epoch_rows": 11,
        "state_projection_parity": True,
        "missing_from_ledger_count": 0,
        "missing_from_state_count": 0,
        "errors": [],
    }
    accounting_payload = {
        "status": "ok",
        "coverage_complete": True,
        "coverage_issue_count": 0,
        "economic_issue_count": 0,
        "open_positions": {"QQQ": {"qty": 1.0}},
    }
    monkeypatch.setattr(restart, "_canonical", lambda unused: canonical)
    monkeypatch.setattr(
        restart, "_accounting", lambda unused: accounting_payload
    )
    return discrepancy


def test_exact_active_full_exit_abort_recovers_without_evidence_rewrite(
    monkeypatch, tmp_path
):
    core = _activate(monkeypatch, tmp_path)
    discrepancy = _set_exact_active_full_exit_abort(monkeypatch, core)
    history_before = copy.deepcopy(core.portfolio["history"])
    trades_before = copy.deepcopy(core.portfolio["trades"])
    positions_before = copy.deepcopy(core.portfolio["positions"])

    result = restart.apply(core)

    assert result["status"] == "active"
    assert result["risk_halted"] is False
    recovery = result["post_start_full_exit_abort_recovery"]
    assert recovery["status"] == "recovered"
    assert recovery["version"] == (
        exit_recovery.RECOVERY_VERSION
    )
    assert recovery["incident_evidence_reference"] == (
        exit_recovery.EVIDENCE_REFERENCE
    )
    assert result["last_discrepancy"] == discrepancy
    assert core.portfolio["history"] == history_before
    assert core.portfolio["trades"] == trades_before
    assert core.portfolio["positions"] == positions_before


def test_active_full_exit_abort_rejects_canonical_digest_drift(
    monkeypatch, tmp_path
):
    core = _activate(monkeypatch, tmp_path)
    _set_exact_active_full_exit_abort(monkeypatch, core)
    monkeypatch.setattr(
        restart,
        "_canonical",
        lambda unused: {
            "hook_applied": True,
            "authoritative_for_new_executions": True,
            "chain_valid": True,
            "ledger_sha256": "different",
            "row_count": exit_recovery.LEDGER_ROWS,
            "current_epoch_rows": 11,
            "state_current_epoch_rows": 11,
            "state_projection_parity": True,
            "missing_from_ledger_count": 0,
            "missing_from_state_count": 0,
            "errors": [],
        },
    )

    result = restart.apply(core)

    assert result["status"] == "halted"
    assert result["risk_halted"] is True
    assert result["post_start_full_exit_abort_recovery"] is None


def test_pr282_successor_rejects_near_match(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    _set_exact_pr282_failed_recovery(core)
    governed = core.portfolio["governed_v5_paper_restart"]
    governed["last_discrepancy"]["checks"]["canonical_digest_unchanged"] = False
    core.portfolio["risk_controls"].update(
        {
            "governed_restart_halt_details": copy.deepcopy(
                governed["last_discrepancy"]
            )
        }
    )

    result = restart.apply(core)

    assert result["status"] == "halted"
    assert result["risk_halted"] is True
    assert result["preappend_abort_recovery"] is None


def test_preappend_abort_recovery_rolls_back_when_persistence_fails(
    monkeypatch, tmp_path
):
    core = _activate(monkeypatch, tmp_path)
    details = _set_exact_restored_wrapper_abort(core)

    def fail_save(*args, **kwargs):
        raise OSError("state persistence unavailable")

    monkeypatch.setattr(core, "save_state", fail_save)
    result = restart.apply(core)

    assert result["status"] == "error"
    assert result["reason"] == "preappend_abort_recovery_failed"
    assert core.portfolio["risk_controls"]["halted"] is True
    assert core.portfolio["risk_controls"]["halt_reason"] == (
        restart.PREAPPEND_ABORT_HALT_REASON
    )
    governed = core.portfolio["governed_v5_paper_restart"]
    assert governed["status"] == "halted"
    assert governed["last_discrepancy"] == details
    assert "preappend_abort_recovery" not in governed


def test_release_preserves_lineage_limits_and_accepts_restart_compatibility(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    epoch = core.portfolio["paper_accounting_epoch"]
    assert epoch["validation_hold"] is False
    assert epoch["prior_epoch_discrepancy_status"] == "unresolved_non_promotable"
    assert epoch["fabricated_exit_rows"] == 0
    assert core.portfolio["risk_controls"]["halted"] is False
    assert core.portfolio["governed_v5_paper_restart"]["hard_risk_limits"] == {
        "max_daily_loss_pct": 0.03,
        "max_intraday_drawdown_pct": 0.025,
    }
    assert clean_compat._successor_epoch(core) == restart.TARGET_EPOCH_ID
    rebuilt = accounting._issue222_verified_flat_zero_trade_baseline(core.portfolio)
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["initial_cash"] == round(13429.13048559457, 6)


def test_long_short_partial_full_lifecycle_and_duplicate_rejection(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)

    core.enter_position({"symbol": "QQQ", "side": "long", "price": 100, "shares": 2}, {}, "risk_on")
    first = core.reduce_position("QQQ", 105, 0.5, "target", "risk_on")
    duplicate = core.reduce_position("QQQ", 105, 0.5, "target", "risk_on")
    assert first["remaining_shares"] == 1.0
    assert duplicate["blocked"] is True
    assert duplicate["reason"] == "duplicate_execution_intent"
    core.exit_position("QQQ", 110, "target", "risk_on")

    core.enter_position({"symbol": "CRWD", "side": "short", "price": 200, "shares": 2}, {}, "risk_off")
    core.reduce_position("CRWD", 190, 0.5, "target", "risk_off")
    core.exit_position("CRWD", 180, "target", "risk_off")

    status = ledger.status_payload(core)
    rebuilt = bidirectional.analyze_ledger(core.portfolio, core)
    assert status["row_count"] == 6
    assert status["current_epoch_rows"] == 6
    assert status["state_projection_parity"] is True
    assert rebuilt["coverage_complete"] is True
    assert rebuilt["coverage_issue_count"] == 0
    assert rebuilt["economic_issue_count"] == 0
    assert rebuilt["open_positions"] == {}
    assert abs(rebuilt["cash"] - core.portfolio["cash"]) <= 0.01
    assert core.portfolio["risk_controls"]["halted"] is False


def test_restart_preserves_state_and_duplicate_intent_receipts(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    core.enter_position({"symbol": "QQQ", "side": "long", "price": 100, "shares": 2}, {}, "risk_on")
    core.reduce_position("QQQ", 105, 0.5, "target", "risk_on")
    persisted = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))

    restarted = FakeCore(persisted, tmp_path / "state.json")
    ledger.apply(restarted)
    result = restart.apply(restarted)
    assert result["status"] == "active"
    _wire_static_boundaries(monkeypatch, restarted)
    assert restarted.portfolio["positions"]["QQQ"]["shares"] == 1.0
    duplicate = restarted.reduce_position("QQQ", 105, 0.5, "target", "risk_on")
    assert duplicate["reason"] == "duplicate_execution_intent"
    assert ledger.status_payload(restarted)["state_projection_parity"] is True


def test_append_failure_restores_uncommitted_state_and_halts(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    before = copy.deepcopy(core.portfolio)

    def fail_append(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(ledger, "append_execution", fail_append)
    try:
        core.enter_position({"symbol": "QQQ", "side": "long", "price": 100, "shares": 2}, {}, "risk_on")
    except RuntimeError as exc:
        assert "canonical execution append failed" in str(exc)
    else:
        raise AssertionError("append failure must propagate")

    assert core.portfolio["cash"] == before["cash"]
    assert core.portfolio["positions"] == before["positions"]
    assert core.portfolio["trades"] == before["trades"]
    assert core.portfolio["risk_controls"]["halted"] is True
    assert core.portfolio["risk_controls"]["halt_reason"] == (
        "governed paper execution aborted before canonical append"
    )
    assert ledger.status_payload(core)["row_count"] == 0
    status = restart.status_payload(core)
    assert status["status_schema_version"] == restart.STATUS_SCHEMA_VERSION
    assert status["risk_halt_local"] == "2026-09-25 10:00:00 CDT"
    assert status["last_discrepancy_local"] == "2026-09-25 10:00:00 CDT"
    assert status["last_discrepancy"] == {
        "operation": "entry",
        "intent_id": status["last_discrepancy"]["intent_id"],
        "error": "RuntimeError: canonical execution append failed; state projection forbidden",
        "error_chain": [
            "RuntimeError: canonical execution append failed; state projection forbidden",
            "OSError: disk unavailable",
        ],
        "canonical_rows_before": 0,
        "canonical_rows_after": 0,
        "state_restored": True,
    }
    assert status["canonical_execution_ledger_error"] is None
    assert status["canonical_execution_ledger_error_local"] is None


def test_projection_discrepancy_stops_after_committed_execution(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    core.enter_position({"symbol": "QQQ", "side": "long", "price": 100, "shares": 2}, {}, "risk_on")
    core.portfolio["trades"].clear()
    core.enter_position({"symbol": "CRWD", "side": "short", "price": 200, "shares": 1}, {}, "risk_off")
    assert core.portfolio["risk_controls"]["halted"] is True
    assert core.portfolio["risk_controls"]["halt_reason"] == (
        "governed paper execution lifecycle discrepancy"
    )
    assert ledger.status_payload(core)["row_count"] == 2
    assert ledger.status_payload(core)["state_projection_parity"] is False
    blocked = core.enter_position({"symbol": "AMD", "side": "long", "price": 100, "shares": 1}, {}, "risk_on")
    assert blocked["blocked"] is True
    assert blocked["reason"] == "risk_halted"


def test_surge_queue_fails_closed_while_risk_halt_is_retained():
    state = _state()
    state["paper_surge_candidate_queue"] = [
        {
            "symbol": "QQQ",
            "price": 100.0,
            "eligible_for_paper_surge": True,
        }
    ]
    state["market_surge_aggression"] = {"eligible_mode": True, "surge_level": 2}
    preview = surge_queue.preview_surge_queue_execution(
        types.SimpleNamespace(portfolio=state)
    )
    assert preview["can_execute"] is False
    assert "risk_halted" in preview["validation_failures"]
    assert preview["context"]["risk_halted"] is True


def test_batch_coordinator_requires_exact_canonical_delta(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)

    def execute_two(*args, **kwargs):
        rows = []
        for symbol, price in (("QQQ", 100.0), ("SPY", 200.0)):
            rows.append(
                core.enter_position(
                    {"symbol": symbol, "side": "long", "price": price, "shares": 1},
                    {},
                    "risk_on",
                )
            )
        return {"executed": True, "executed_entries": rows}

    result = restart.execute_batch_operation(core, "test_batch", execute_two)
    assert result["executed"] is True
    assert ledger.status_payload(core)["row_count"] == 2
    assert core.portfolio["risk_controls"]["halted"] is False
    receipt = core.portfolio["governed_v5_paper_restart"]["last_execution_receipt"]
    assert receipt["operation"] == "test_batch"
    assert receipt["executed_count"] == 2


def test_surge_queue_bridge_commits_inside_governed_batch(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    core.portfolio.update(
        {
            "paper_surge_candidate_queue": [
                {
                    "symbol": "QQQ",
                    "price": 100.0,
                    "eligible_for_paper_surge": True,
                    "allocation_hint_pct_of_equity": 2.0,
                    "tier": "tier_1_broad_risk_on",
                }
            ],
            "market_surge_aggression": {
                "eligible_mode": True,
                "surge_level": 2,
            },
        }
    )
    result = surge_queue.execute_surge_queue(core, explicit_confirm=True)
    assert result["executed"] is True
    assert result["canonical_execution_bridge"]["canonicalized_count"] == 1
    assert ledger.status_payload(core)["row_count"] == 1
    assert ledger.status_payload(core)["state_projection_parity"] is True
    assert core.portfolio["risk_controls"]["halted"] is False
    receipt = core.portfolio["governed_v5_paper_restart"]["last_execution_receipt"]
    assert receipt["operation"] == "market_surge_queue"
    assert receipt["executed_count"] == 1


def test_batch_failure_restores_only_before_any_canonical_append(monkeypatch, tmp_path):
    core = _activate(monkeypatch, tmp_path)
    cash_before = core.portfolio["cash"]

    def fail_before_append(*args, **kwargs):
        core.portfolio["cash"] -= 100.0
        core.portfolio["positions"].update({"QQQ": {"shares": 1.0}})
        raise OSError("batch persistence unavailable")

    try:
        restart.execute_batch_operation(core, "test_batch", fail_before_append)
    except OSError as exc:
        assert "batch persistence unavailable" in str(exc)
    else:
        raise AssertionError("batch failure must propagate")
    assert core.portfolio["cash"] == cash_before
    assert core.portfolio["positions"] == {}
    assert core.portfolio["risk_controls"]["halted"] is True
    assert core.portfolio["risk_controls"]["halt_reason"] == (
        "governed paper batch aborted before canonical append"
    )
