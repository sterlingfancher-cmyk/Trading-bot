import datetime

import pytest

import app


def _localize(year, month, day, hour=10, minute=0):
    tz = app.MARKET_TZ
    return tz.localize(datetime.datetime(year, month, day, hour, minute))


def test_labor_day_2026_closed(monkeypatch):
    """Labor Day 2026 (2026-09-07) should be treated as a holiday/closed."""
    dt = _localize(2026, 9, 7, 10, 0)
    monkeypatch.setattr(app, "now_local", lambda: dt)
    clock = app.market_clock()
    assert clock["is_open"] is False
    assert clock["reason"] == "holiday"


def test_2026_09_08_open(monkeypatch):
    """The next day 2026-09-08 at 10:00 should be regular session open."""
    dt = _localize(2026, 9, 8, 10, 0)
    monkeypatch.setattr(app, "now_local", lambda: dt)
    clock = app.market_clock()
    assert clock["is_open"] is True
    assert clock["reason"] == "regular_session"


def test_weekend_closed(monkeypatch):
    dt = _localize(2026, 9, 5, 10, 0)  # Saturday
    monkeypatch.setattr(app, "now_local", lambda: dt)
    clock = app.market_clock()
    assert clock["is_open"] is False
    assert clock["reason"] == "weekend"


def test_before_open_closed(monkeypatch):
    dt = _localize(2026, 9, 8, 7, 0)  # before 08:30
    monkeypatch.setattr(app, "now_local", lambda: dt)
    clock = app.market_clock()
    assert clock["is_open"] is False
    assert clock["reason"] == "before_regular_session"


def test_after_close_closed(monkeypatch):
    dt = _localize(2026, 9, 8, 16, 0)  # after 15:00
    monkeypatch.setattr(app, "now_local", lambda: dt)
    clock = app.market_clock()
    assert clock["is_open"] is False
    assert clock["reason"] == "after_regular_session"


def test_observed_fixed_date_holiday(monkeypatch):
    """When a fixed-date holiday falls on a Saturday, the previous Friday is observed.

    July 4, 2026 is a Saturday, so July 3, 2026 should be observed and closed.
    """
    dt = _localize(2026, 7, 3, 10, 0)
    monkeypatch.setattr(app, "now_local", lambda: dt)
    clock = app.market_clock()
    assert clock["is_open"] is False
    assert clock["reason"] == "holiday"
