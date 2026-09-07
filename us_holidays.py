import datetime

"""Deterministic, no-network US equity full-day holiday predicate.
This tiny helper returns True for dates when US equities are closed for a
full regular session. It is intentionally minimal and deterministic; only
explicit full-day closures are included. Additions must remain deterministic
and offline.

Currently includes:
- Labor Day 2026 (2026-09-07)

The predicate accepts either a datetime.datetime or datetime.date. If a
timezone-aware datetime is provided, its date() is used.
"""

_FULL_DAY_HOLIDAYS = {
    # year-month-day tuples
    (2026, 9, 7),  # Labor Day 2026
}


def is_us_equity_holiday(value):
    """Return True if the provided date/datetime is a full-day US equity holiday.

    Args:
        value: datetime.date or datetime.datetime (timezone-aware allowed)
    Returns:
        bool
    """
    if value is None:
        return False
    if isinstance(value, datetime.datetime):
        d = value.date()
    elif isinstance(value, datetime.date):
        d = value
    else:
        return False

    return (d.year, d.month, d.day) in _FULL_DAY_HOLIDAYS
