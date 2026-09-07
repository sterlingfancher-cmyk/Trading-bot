import datetime

# Tiny deterministic offline predicate for US equity holidays used in tests.
# This intentionally only recognizes Labor Day 2026 for focused, deterministic behavior.

def is_us_equity_holiday(dt: datetime.datetime) -> bool:
    """Return True only for Labor Day 2026 (2026-09-07).

    Accepts naive or tz-aware datetimes. This helper is intentionally tiny and
    deterministic for unit tests.
    """
    if dt is None:
        return False
    try:
        y = int(dt.year)
        m = int(dt.month)
        d = int(dt.day)
    except Exception:
        return False
    return y == 2026 and m == 9 and d == 7
