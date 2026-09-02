import io
import os
import importlib
import paper_bidirectional_accounting_guard as guard


def test_source_line_uses_state_tolerance_constant():
    # Ensure the exact source-line substitution is present in the module source
    fpath = guard.__file__
    with open(fpath, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert "STATE_TRADE_QTY_SERIALIZATION_TOLERANCE" in src
    # The specific comprehension form must be present
    assert "open_sides = [side for side in (\"long\", \"short\") if sum(row[0] for row in side_books[side]) > STATE_TRADE_QTY_SERIALIZATION_TOLERANCE]" in src


def test_small_residual_considered_closed():
    # DELL: 2.323047 short entry + 0.766605 partial exit + 1.556441 exit
    # residual = 2.323047 - (0.766605 + 1.556441) = 0.000001 (1e-6) which is <= 5e-6
    side_books = {
        "long": [],
        # represent short side with entry (positive qty) and exits as negative quantities
        "short": [(2.323047,), (-0.766605,), (-1.556441,)],
    }
    opens = guard.reconstruct_open_sides_from_side_books(side_books)
    # residual is 1e-6 which is below the 5e-6 tolerance -> no open side reconstructed
    assert opens == []


def test_residual_just_above_tolerance_remains_open():
    # Construct a residual slightly above the tolerance (e.g., ~7e-6)
    # entry 2.323053 minus exits 0.766605 and 1.556441 gives residual 7e-6
    side_books = {
        "long": [],
        "short": [(2.323053,), (-0.766605,), (-1.556441,)],
    }
    opens = guard.reconstruct_open_sides_from_side_books(side_books)
    # residual ~7e-6 > STATE_TRADE_QTY_SERIALIZATION_TOLERANCE (5e-6)
    assert "short" in opens


def test_over_exit_regression_persists_behavior():
    # Over-exit scenario: exits exceed entries (sum negative)
    side_books = {
        "long": [],
        "short": [(2.0,), (-3.0,)],
    }
    opens = guard.reconstruct_open_sides_from_side_books(side_books)
    # Sum is -1.0 which is not greater than the tolerance; behavior remains the same
    assert opens == []
