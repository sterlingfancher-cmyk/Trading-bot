import copy

from src import paper_execution_guard as guard


def _make_entry_row(execution_id: str, symbol: str, size: float, price: float) -> dict:
    return {
        "execution_id": execution_id,
        "symbol": symbol,
        "type": "entry",
        "side": "long" if size > 0 else "short",
        "size": float(size),
        "price": float(price),
    }


def _make_exit_row(execution_id: str, entry_execution_id: str, symbol: str, size: float, price: float) -> dict:
    return {
        "execution_id": execution_id,
        "symbol": symbol,
        "type": "exit",
        "entry_execution_id": entry_execution_id,
        "size": float(size),
        "price": float(price),
    }


def test_prevent_duplicate_full_exit():
    """Regression reproduced and prevented:

    Scenario (exact numbers from the handoff):
    - One TEM long entry: 29.640567 @ 54.885. (execution_id 7b13...)
    - First full exit: -29.640567 @ 53.105. (execution_id 3530...)
    - Second full exit attempt: -29.640567 @ 52.905. (must NOT create a second canonical row)

    The naive append path will create two exit rows. append_trade_row_safe must
    accept the first exit and reject the second, preserving append-only history
    but avoiding a duplicate canonical close.
    """
    entry_exec = "7b13d9194a23407f926667b2f48d4057"
    first_exit_exec = "3530dbf965db4894ba93b7098cec3696"
    second_exit_exec = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    entry_row = _make_entry_row(entry_exec, "TEM", 29.640567, 54.885)
    exit_row_1 = _make_exit_row(first_exit_exec, entry_exec, "TEM", -29.640567, 53.105)
    exit_row_2 = _make_exit_row(second_exit_exec, entry_exec, "TEM", -29.640567, 52.905)

    # Naive scenario: both exits appended -> regression
    naive_state = {"trades": [copy.deepcopy(entry_row)]}
    guard.append_trade_row_naive(naive_state, copy.deepcopy(exit_row_1))
    guard.append_trade_row_naive(naive_state, copy.deepcopy(exit_row_2))
    # Expect 3 rows (entry + two exits) in the naive/unprotected path
    assert len(naive_state["trades"]) == 3
    ids = [r.get("execution_id") for r in naive_state["trades"]]
    assert entry_exec in ids and first_exit_exec in ids and second_exit_exec in ids

    # Safe scenario: first exit accepted, second exit rejected
    safe_state = {"trades": [copy.deepcopy(entry_row)]}
    appended_first = guard.append_trade_row_safe(safe_state, copy.deepcopy(exit_row_1))
    assert appended_first is True
    # second (duplicate full) should be rejected
    appended_second = guard.append_trade_row_safe(safe_state, copy.deepcopy(exit_row_2))
    assert appended_second is False
    # state should contain only entry and first exit
    assert len(safe_state["trades"]) == 2
    ids_safe = [r.get("execution_id") for r in safe_state["trades"]]
    assert entry_exec in ids_safe and first_exit_exec in ids_safe
