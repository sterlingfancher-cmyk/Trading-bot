import math

from paper_bidirectional_accounting_guard import analyze_ledger


def test_dell_style_reconstructs_flat_using_serialization_tolerance():
    # DELL-style: 2.323047 entry - 0.766605 partial - 1.556441 exit = 1e-6 residue
    trades = [
        {"action": "entry", "symbol": "DELL", "side": "long", "price": 10.0, "shares": 2.323047},
        {"action": "partial_exit", "symbol": "DELL", "side": "long", "price": 11.0, "shares": 0.766605},
        {"action": "exit", "symbol": "DELL", "side": "long", "price": 12.0, "shares": 1.556441},
    ]
    pf = {"trades": trades}
    result = analyze_ledger(pf)
    # The 1e-6 terminal residue should be forgiven by the serialization tolerance
    assert "DELL" not in result.get("open_positions", {}), "Tiny 1e-6 residue should not leave a phantom open lot"
    assert result.get("status") == "ok", "Reconstruction of exact-serial residue should be considered clean"


def test_residue_greater_than_5e6_remains_open_and_fails():
    # Create a residue slightly larger than QTY_TOLERANCE (5e-6)
    trades = [
        {"action": "entry", "symbol": "XYZ", "side": "long", "price": 5.0, "shares": 1.00001},
        {"action": "exit", "symbol": "XYZ", "side": "long", "price": 5.5, "shares": 1.0},
    ]
    pf = {"trades": trades}
    result = analyze_ledger(pf)
    # Residue is 1e-5 which is > 5e-6; must remain an open position and reconstruction should be flagged fail
    assert "XYZ" in result.get("open_positions", {}), "Residue > 5e-6 should remain open"
    assert result.get("status") == "fail", "Non-zero reconstructed positions should mark reconstruction as fail"


def test_exit_exceeds_position_behavior_triggers_coverage_issue():
    # Exit more than available by more than QTY_TOLERANCE (5e-6) should be reported
    trades = [
        {"action": "entry", "symbol": "ABC", "side": "long", "price": 2.0, "shares": 1.0},
        {"action": "exit", "symbol": "ABC", "side": "long", "price": 2.5, "shares": 1.0002},
    ]
    pf = {"trades": trades}
    result = analyze_ledger(pf)
    coverage = result.get("coverage_issues") or []
    assert any(c.get("reason") == "exit_exceeds_reconstructed_position" and c.get("symbol") == "ABC" for c in coverage), "Exit exceeding open quantity must be flagged"
