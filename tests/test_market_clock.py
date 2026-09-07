import datetime

import pytz
import app


def test_labor_day_2026(monkeypatch):
    tz = app.MARKET_TZ
    dt = tz.localize(datetime.datetime(2026, 9, 7, 10, 0, 0))
    monkeypatch.setattr(app, "now_local", lambda: dt)
    clk = app.market_clock()
    assert clk["reason"] == "holiday"
    assert clk["is_open"] is False


def test_weekend(monkeypatch):
    tz = app.MARKET_TZ
    dt = tz.localize(datetime.datetime(2026, 9, 5, 10, 0, 0))
    monkeypatch.setattr(app, "now_local", lambda: dt)
    clk = app.market_clock()
    assert clk["reason"] == "weekend"
    assert clk["is_open"] is False


def test_regular_session(monkeypatch):
    tz = app.MARKET_TZ
    dt = tz.localize(datetime.datetime(2026, 9, 8, 10, 0, 0))
    monkeypatch.setattr(app, "now_local", lambda: dt)
    clk = app.market_clock()
    assert clk["reason"] == "regular_session"
    assert clk["is_open"] is True
