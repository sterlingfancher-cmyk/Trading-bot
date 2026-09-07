import datetime
import pytz

import app

MARKET_TZ = app.MARKET_TZ


def dt_local(year, month, day, hour=12, minute=0):
    return MARKET_TZ.localize(datetime.datetime(year, month, day, hour, minute, 0))


def test_labor_day_2026_closed():
    # Labor Day 2026 is 2026-09-07 and should be treated as a holiday (closed)
    app.now_local = lambda: dt_local(2026, 9, 7, 10, 0)
    clock = app.market_clock()
    assert clock["is_open"] is False
    assert clock["reason"] == "holiday"


def test_normal_weekday_open():
    # A normal weekday during regular hours should be regular_session
    app.now_local = lambda: dt_local(2026, 9, 8, 10, 0)  # Tuesday after Labor Day
    clock = app.market_clock()
    assert clock["is_open"] is True
    assert clock["reason"] == "regular_session"


def test_weekend_closed():
    # Weekend should still be weekend
    app.now_local = lambda: dt_local(2026, 9, 5, 10, 0)  # Saturday
    clock = app.market_clock()
    assert clock["is_open"] is False
    assert clock["reason"] == "weekend"


def test_before_open():
    # Weekday before open
    app.now_local = lambda: dt_local(2026, 9, 8, 7, 0)
    clock = app.market_clock()
    assert clock["is_open"] is False
    assert clock["reason"] == "before_regular_session"


def test_after_close():
    # Weekday after close
    app.now_local = lambda: dt_local(2026, 9, 8, 16, 0)
    clock = app.market_clock()
    assert clock["is_open"] is False
    assert clock["reason"] == "after_regular_session"
