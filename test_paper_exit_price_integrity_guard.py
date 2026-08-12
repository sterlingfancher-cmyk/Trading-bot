import types

import paper_exit_price_integrity_guard as guard


def _core():
    calls = []
    state = {
        "positions": {
            "LRCX": {
                "symbol": "LRCX",
                "side": "long",
                "entry": 312.9,
                "shares": 3.42486,
                "last_price": 326.0,
            }
        },
        "risk_controls": {
            "halted": False,
            "halt_reason": "",
            "self_defense_active": False,
            "self_defense_reason": "",
        },
    }

    def exit_position(symbol, px, *args, **kwargs):
        calls.append(("exit", symbol, px))
        return {"symbol": symbol, "price": px}

    def reduce_position(symbol, px, *args, **kwargs):
        calls.append(("partial", symbol, px))
        return {"symbol": symbol, "price": px}

    return types.SimpleNamespace(
        portfolio=state,
        exit_position=exit_position,
        reduce_position=reduce_position,
        save_state=lambda *args, **kwargs: None,
        calls=calls,
    )


def test_catastrophic_long_bad_tick_is_blocked_and_halts():
    core = _core()
    result = guard.apply(core)
    assert result["status"] == "ok"

    before = dict(core.portfolio["positions"]["LRCX"])
    out = core.exit_position("LRCX", 36.26, "stop_loss")
    assert out is None
    assert core.calls == []
    assert core.portfolio["positions"]["LRCX"] == before

    risk = core.portfolio["risk_controls"]
    assert risk["halted"] is True
    assert risk["self_defense_active"] is True
    block = risk["paper_exit_price_integrity_block"]
    assert block["symbol"] == "LRCX"
    assert block["reason"] == "catastrophic_long_exit_price_outlier"
    assert block["price"] == 36.26
    assert block["entry"] == 312.9


def test_normal_full_and_partial_exits_are_unchanged():
    core = _core()
    guard.apply(core)

    full = core.exit_position("LRCX", 305.0, "normal_stop")
    partial = core.reduce_position("LRCX", 327.1188, 0.33, "partial_profit")

    assert full == {"symbol": "LRCX", "price": 305.0}
    assert partial == {"symbol": "LRCX", "price": 327.1188}
    assert core.calls == [
        ("exit", "LRCX", 305.0),
        ("partial", "LRCX", 327.1188),
    ]


def test_existing_halt_reason_is_preserved_when_bad_tick_is_blocked():
    core = _core()
    core.portfolio["risk_controls"]["halted"] = True
    core.portfolio["risk_controls"]["halt_reason"] = "absolute daily equity loss halt (3.00%)"
    guard.apply(core)

    assert core.exit_position("LRCX", 36.26, "stop_loss") is None
    risk = core.portfolio["risk_controls"]
    assert risk["halt_reason"] == "absolute daily equity loss halt (3.00%)"
    assert risk["paper_exit_price_integrity_active"] is True
