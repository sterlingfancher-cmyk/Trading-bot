# Bidirectional accounting guard (focused surgical helper)
# Minimal, focused module for quantity-tolerance guard tests.
# VERSION retained as a marker for test inspection.
VERSION = "paper-bidirectional-accounting-guard-2026-09-01-v1"

# Serialization tolerance (must remain exactly 5e-6 per handoff contract)
STATE_TRADE_QTY_SERIALIZATION_TOLERANCE = 5e-6


def reconstruct_open_sides_from_side_books(side_books):
    """
    Given side_books mapping {"long": [(qty, ...), ...], "short": [(qty, ...), ...]}
    compute which sides appear open using the same single-line predicate under test.

    This function intentionally mirrors the exact comprehension under test so the
    unit tests can validate the threshold behavior in isolation.
    """
    # The single guarded source line below is the exact substitution required by the change request.
    open_sides = [side for side in ("long", "short") if sum(row[0] for row in side_books[side]) > STATE_TRADE_QTY_SERIALIZATION_TOLERANCE]
    return open_sides
