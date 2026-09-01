import pytest

from runtime_research_snapshot import evaluate_snapshot


def mk_ok():
    return {"overall": "pass"}


def mk_fail():
    return {"overall": "fail"}


def mk_warn():
    return {"overall": "warn"}


def test_active_v2_failed_verified_v2_gate_warns():
    snapshot = {
        "daily_audit": {"epoch_id": "stable-paper-v2-20260812-verified01", "overall": "pass"},
        "paper_status": mk_ok(),
        "self_check": mk_ok(),
        "bootstrap_listener": mk_ok(),
        "app_ready": mk_ok(),
        "verified_v2_recovery_gate": mk_fail(),
        "root": mk_ok(),
    }

    out = evaluate_snapshot(snapshot)
    assert out["active_epoch_version"] == 2
    assert out["overall"] == "warn"
    # verified_v2_recovery_gate should appear in warnings
    assert "verified_v2_recovery_gate" in out["warnings"]


def test_active_v4_failed_legacy_v2_gate_is_superseded_and_ignored():
    snapshot = {
        "daily_audit": {"epoch_id": "stable-paper-v4-20260826-successor01", "overall": "pass"},
        "paper_status": mk_ok(),
        "self_check": mk_ok(),
        "bootstrap_listener": mk_ok(),
        "app_ready": mk_ok(),
        "verified_v2_recovery_gate": mk_fail(),
        "root": mk_ok(),
    }

    out = evaluate_snapshot(snapshot)
    assert out["active_epoch_version"] == 4
    # The legacy v2 gate failure must NOT warn when active epoch is v4.
    assert out["overall"] == "pass"
    assert "verified_v2_recovery_gate" not in out["warnings"]


def test_optional_root_failure_with_healthy_bootstrap_and_paper_or_self_check_does_not_warn():
    # root fails, but bootstrap/app_ready + paper_status are healthy -> root optional
    snapshot = {
        "daily_audit": {"epoch_id": "stable-paper-v4-20260826-successor01", "overall": "pass"},
        "paper_status": mk_ok(),
        "self_check": mk_ok(),
        "bootstrap_listener": mk_ok(),
        "app_ready": mk_ok(),
        "root": mk_fail(),
    }

    out = evaluate_snapshot(snapshot)
    # root failure should be ignored due to readiness
    assert out["overall"] == "pass"
    assert "root" not in out["warnings"]


def test_required_daily_audit_self_check_fresh_day_failure_still_warns():
    # self_check failing should cause overall warn
    snapshot = {
        "daily_audit": {"epoch_id": "stable-paper-v4-20260826-successor01", "overall": "pass"},
        "paper_status": mk_ok(),
        "self_check": mk_fail(),
        "bootstrap_listener": mk_ok(),
        "app_ready": mk_ok(),
        "root": mk_ok(),
    }

    out = evaluate_snapshot(snapshot)
    assert out["overall"] == "warn"
    assert "self_check" in out["errors"] or "self_check" in out["warnings"]
