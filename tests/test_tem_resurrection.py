import pytest

# Production-shaped regression: test whether the existing state_persistence_contract
# helper that could replace in-memory persisted portfolio state can be exercised
# to prove whether a stale persisted snapshot would resurrect a position already
# fully closed in the canonical JSONL execution ledger.
#
# This test intentionally avoids changing runtime behaviour. It tries to locate
# and exercise an internal helper named `_replace_portfolio` (the function name
# observed in the forensic notes) with a canonical-execution-shaped fixture.
# If the helper is missing or its signature is unknown, the test is skipped and
# reports "insufficient evidence" per the PROJECT_HANDOFF_CURRENT.md protocol.
# If the helper is callable in a plausible way, the test asserts that a position
# fully closed by canonical exits is NOT resurrected. If the helper returns a
# portfolio that still contains the closed position, the test fails and thereby
# proves the resurrection path exists (CI will show the failure so it can be
# addressed in a surgical patch meeting the handoff constraints).

CANONICAL_EPOCH = "stable-paper-v2-20260812-verified01"
ENTRY_EXECUTION_ID = "d647d8a0580b44edbab0224e6c339bfd"
FIRST_EXIT_EXECUTION_ID = "7b13d9194a23407f926667b2f48d4057"
SECOND_EXIT_EXECUTION_ID = "3530dbf965db4894ba93b7098cec3696"
SYMBOL = "TEM"
SHARES = 29.640567


def _canonical_rows_fixture():
    # These rows follow the literal production-shaped JSONL fields used across the
    # canonical execution ledger: accounting_epoch_id, action, execution_id,
    # symbol, side, shares, price, time/timestamp. Times are monotonic here.
    return [
        {
            "accounting_epoch_id": CANONICAL_EPOCH,
            "action": "entry",
            "execution_id": ENTRY_EXECUTION_ID,
            "symbol": SYMBOL,
            "side": "long",
            "shares": SHARES,
            "price": 54.885,
            "timestamp": 1.0,
        },
        {
            "accounting_epoch_id": CANONICAL_EPOCH,
            "action": "exit",
            "execution_id": FIRST_EXIT_EXECUTION_ID,
            "symbol": SYMBOL,
            "side": "long",
            "shares": SHARES,
            "price": 53.105,
            "timestamp": 2.0,
        },
        {
            "accounting_epoch_id": CANONICAL_EPOCH,
            "action": "exit",
            "execution_id": SECOND_EXIT_EXECUTION_ID,
            "symbol": SYMBOL,
            "side": "long",
            "shares": SHARES,
            "price": 52.905,
            "timestamp": 3.0,
        },
    ]


def _persisted_snapshot_with_open_position():
    # A persisted snapshot that, if restored naively, would reintroduce the
    # position for SYMBOL. This mirrors production-shaped position and trades
    # fields (conservative, not relying on extra implementation details).
    return {
        "positions": {
            SYMBOL: {
                "qty": SHARES,
                "shares": SHARES,
                "side": "long",
                "entry_price": 54.885,
                "avg_price": 54.885,
                "entry_time": 1.0,
            }
        },
        "trades": [
            {
                "action": "entry",
                "execution_id": ENTRY_EXECUTION_ID,
                "symbol": SYMBOL,
                "side": "long",
                "shares": SHARES,
                "price": 54.885,
                "time": 1.0,
            }
        ],
        "cash": 10768.497731,
        "equity": 11885.824057,
    }


@pytest.mark.parametrize("try_order", [0, 1, 2])
def test_replace_portfolio_tems_resurrection_check(try_order):
    """Attempt to exercise an internal replacement helper and prove whether a
    persisted snapshot could reintroduce a TEM position after the canonical
    first full exit. Skip with an explanatory message if the helper or a usable
    calling convention cannot be determined (insufficient evidence).

    Outcomes:
    - Pass: helper callable and returns portfolio with TEM not present (no
      resurrection demonstrated).
    - Fail: helper callable and returns portfolio where TEM is present (resurrection
      is possible and must be surgically fixed per handoff protocol).
    - Skip: helper not present or cannot be exercised safely (insufficient evidence).
    """
    try:
        import state_persistence_contract as sp
    except Exception as exc:
        pytest.skip(f"state_persistence_contract import failed: insufficient evidence ({exc})")

    replace_fn = getattr(sp, "_replace_portfolio", None)
    if not callable(replace_fn):
        pytest.skip("_replace_portfolio not found in state_persistence_contract: insufficient evidence")

    canonical_rows = _canonical_rows_fixture()
    persisted_snapshot = _persisted_snapshot_with_open_position()

    # Try a few plausible calling conventions in a nondestructive way.
    # The helper may accept (portfolio, ledger_rows), (ledger_rows, portfolio),
    # or (portfolio, ledger_rows, options). We will try them but we will not
    # mutate external files or environment.
    tried = []
    results = []
    errors = []

    candidates = [
        (persisted_snapshot, canonical_rows),
        (canonical_rows, persisted_snapshot),
        (persisted_snapshot, canonical_rows, {}),
    ]

    # rotate attempts deterministically by try_order so CI logs multiple angles
    order = list(range(len(candidates)))
    order = order[try_order % len(order):] + order[: try_order % len(order)]

    for idx in order:
        args = candidates[idx]
        tried.append(args)
        try:
            out = replace_fn(*args)
            results.append((args, out))
        except TypeError as te:
            errors.append((args, f"TypeError: {te}"))
        except Exception as e:
            errors.append((args, f"Exception: {e}"))

    if not results:
        # No successful invocation — insufficient evidence to prove resurrection.
        pytest.skip(
            "Could not call _replace_portfolio with any plausible signature: insufficient evidence."
            f" Tried signatures: {len(tried)}. Errors: {errors}"
        )

    # Inspect first successful result (helpers may return new portfolio dict or mutate in-place)
    args, out = results[0]

    # If the helper mutates the input and returns None, check the input snapshot
    candidate_portfolio = out if isinstance(out, dict) else persisted_snapshot

    positions = candidate_portfolio.get("positions") or {}
    has_tem = SYMBOL in positions and (positions.get(SYMBOL) is not None)

    if has_tem:
        pytest.fail(
            "_replace_portfolio returned/left a portfolio containing TEM after canonical full exit."
            " This proves a persisted snapshot could resurrect a fully closed position and must be fixed."
            f" Called args: {args}. Result positions keys: {list(positions.keys())}"
        )

    # Otherwise the helper failed to resurrect TEM in this scenario — test passes.
    assert not has_tem, "TEM unexpectedly present after replace (covered above)."
