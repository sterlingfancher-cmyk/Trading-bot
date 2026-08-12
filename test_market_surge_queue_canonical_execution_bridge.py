import types

import market_surge_queue_canonical_execution_bridge as bridge
import market_surge_queue_executor as queue


def _core():
    state = {
        "cash": 9000.0,
        "equity": 10000.0,
        "positions": {},
        "trades": [],
        "risk_controls": {},
    }
    calls = []

    def record_trade(action, symbol, side, px, shares, extra=None):
        calls.append((action, symbol, side, px, shares, extra or {}))
        state["trades"].append({
            "action": action,
            "symbol": symbol,
            "side": side,
            "price": px,
            "shares": shares,
            "execution_id": "canonical-test-id",
            **(extra or {}),
        })

    return types.SimpleNamespace(
        portfolio=state,
        record_trade=record_trade,
        save_state=lambda *args, **kwargs: None,
        calls=calls,
    )


def test_new_queue_row_is_replaced_by_canonical_record_trade(monkeypatch):
    core = _core()

    def legacy_execute(runtime_core=None, *, explicit_confirm=False):
        pf = runtime_core.portfolio
        pf["positions"]["LRCX"] = {
            "symbol": "LRCX",
            "side": "long",
            "qty": 2.0,
            "entry_price": 100.0,
        }
        pf["trades"].append({
            "timestamp": "2026-08-12 10:00:00 CDT",
            "symbol": "LRCX",
            "side": "buy",
            "qty": 2.0,
            "price": 100.0,
            "source": "market_surge_queue_executor",
            "entry_tag": "paper_surge_entry",
        })
        return {"executed": True, "executed_entries": [{"symbol": "LRCX"}]}

    monkeypatch.setattr(queue, "execute_surge_queue", legacy_execute)
    assert bridge.apply(core)["status"] == "ok"

    out = queue.execute_surge_queue(core, explicit_confirm=True)

    assert out["canonical_execution_bridge"]["status"] == "ok"
    assert out["canonical_execution_bridge"]["canonicalized_count"] == 1
    assert len(core.calls) == 1
    action, symbol, side, px, shares, extra = core.calls[0]
    assert (action, symbol, side, px, shares) == ("entry", "LRCX", "long", 100.0, 2.0)
    assert extra["source"] == "market_surge_queue_executor"
    assert extra["legacy_queue_row_replaced"] is True

    assert len(core.portfolio["trades"]) == 1
    assert core.portfolio["trades"][0]["execution_id"] == "canonical-test-id"
    assert core.portfolio["positions"]["LRCX"]["shares"] == 2.0
    assert core.portfolio["positions"]["LRCX"]["entry"] == 100.0


def test_unrelated_new_trade_row_is_not_removed(monkeypatch):
    core = _core()
    core.portfolio["trades"].append({"action": "entry", "symbol": "OLD", "execution_id": "old"})

    def legacy_execute(runtime_core=None, *, explicit_confirm=False):
        runtime_core.portfolio["trades"].append({
            "action": "entry",
            "symbol": "OTHER",
            "side": "long",
            "price": 50.0,
            "shares": 1.0,
            "execution_id": "already-canonical",
            "source": "other_component",
        })
        return {"executed": True}

    monkeypatch.setattr(queue, "execute_surge_queue", legacy_execute)
    assert bridge.apply(core)["status"] == "ok"
    out = queue.execute_surge_queue(core, explicit_confirm=True)

    assert out["canonical_execution_bridge"]["status"] == "no_legacy_rows"
    assert [row["symbol"] for row in core.portfolio["trades"]] == ["OLD", "OTHER"]
    assert core.calls == []


def test_existing_persisted_legacy_queue_row_is_not_rewritten(monkeypatch):
    core = _core()
    existing = {
        "timestamp": "2026-08-11 10:00:00 CDT",
        "symbol": "SPY",
        "side": "buy",
        "qty": 1.0,
        "price": 700.0,
        "source": "market_surge_queue_executor",
    }
    core.portfolio["trades"].append(existing)

    def no_execution(runtime_core=None, *, explicit_confirm=False):
        return {"executed": False, "execution_reason": "no_new_entry"}

    monkeypatch.setattr(queue, "execute_surge_queue", no_execution)
    assert bridge.apply(core)["status"] == "ok"
    out = queue.execute_surge_queue(core, explicit_confirm=True)

    assert out["executed"] is False
    assert core.portfolio["trades"] == [existing]
    assert core.calls == []
