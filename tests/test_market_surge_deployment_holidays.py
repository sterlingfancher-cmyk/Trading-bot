import datetime as dt

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

import market_surge_deployment_mode as ms


CENTRAL = ZoneInfo(ms.CENTRAL_TZ_NAME) if ZoneInfo is not None else None


def _tz(dtobj):
    if CENTRAL is None:
        return dtobj
    if dtobj.tzinfo is None:
        return dtobj.replace(tzinfo=CENTRAL)
    return dtobj.astimezone(CENTRAL)


def test_labor_day_2026_closed():
    # Labor Day 2026 is 2026-09-07 and should be treated as a full-day holiday.
    ref = _tz(dt.datetime(2026, 9, 7, 10, 0, 0))
    assert ms.is_us_equity_full_holiday(ref) is True
    assert ms._is_regular_market_window(ref) is False


def test_regular_weekday_open():
    # A normal weekday during the regular window should be open.
    ref = _tz(dt.datetime(2026, 9, 8, 10, 0, 0))  # 2026-09-08 is a Tuesday
    assert ms.is_us_equity_full_holiday(ref) is False
    # _is_regular_market_window uses 8:40-14:45 central as entry window
    assert ms._is_regular_market_window(ref) is True


def test_weekend_closed():
    # Weekend day should be closed regardless of time
    ref = _tz(dt.datetime(2026, 9, 12, 12, 0, 0))  # Saturday
    assert ms.is_us_equity_full_holiday(ref) is False
    assert ms._is_regular_market_window(ref) is False


def test_before_open_closed():
    ref = _tz(dt.datetime(2026, 9, 9, 7, 0, 0))  # Before open on a normal weekday
    assert ms.is_us_equity_full_holiday(ref) is False
    assert ms._is_regular_market_window(ref) is False


def test_after_close_closed():
    ref = _tz(dt.datetime(2026, 9, 9, 16, 0, 0))  # After close on a normal weekday
    assert ms.is_us_equity_full_holiday(ref) is False
    assert ms._is_regular_market_window(ref) is False
