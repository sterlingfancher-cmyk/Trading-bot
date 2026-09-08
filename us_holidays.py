from datetime import date, timedelta


def _easter_date(year: int) -> date:
    # Anonymous Gregorian algorithm (Meeus/Jones) for Easter Sunday
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    # weekday: Monday=0 .. Sunday=6 ; returns nth weekday of month
    d = date(year, month, 1)
    add = (weekday - d.weekday() + 7) % 7
    d = d + timedelta(days=add)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    # last given weekday in month
    if month == 12:
        d = date(year, 12, 31)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    back = (d.weekday() - weekday + 7) % 7
    return d - timedelta(days=back)


def _observed(d: date) -> date:
    # If holiday falls on Saturday -> observed Friday; Sunday -> observed Monday
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def holidays_for_year(year: int):
    out = set()

    # New Year's Day
    nyd = date(year, 1, 1)
    out.add(_observed(nyd))

    # Martin Luther King Jr. Day: third Monday in January
    out.add(_nth_weekday(year, 1, 0, 3))

    # Presidents' Day (Washington's Birthday): third Monday in February
    out.add(_nth_weekday(year, 2, 0, 3))

    # Good Friday: two days before Easter Sunday
    easter = _easter_date(year)
    good_friday = easter - timedelta(days=2)
    out.add(good_friday)

    # Memorial Day: last Monday in May
    out.add(_last_weekday(year, 5, 0))

    # Juneteenth (federal, observed): June 19
    juneteenth = date(year, 6, 19)
    out.add(_observed(juneteenth))

    # Independence Day: July 4
    indep = date(year, 7, 4)
    out.add(_observed(indep))

    # Labor Day: first Monday in September
    out.add(_nth_weekday(year, 9, 0, 1))

    # Thanksgiving: fourth Thursday in November
    out.add(_nth_weekday(year, 11, 3, 4))

    # Christmas Day: December 25
    xmas = date(year, 12, 25)
    out.add(_observed(xmas))

    return out


def is_us_equity_holiday(dt) -> bool:
    """Return True if the given datetime or date falls on a standard full-day US equity holiday.

    This function is intentionally offline and deterministic. It calculates standard
    full-day holidays (no early-close handling) and accounts for observed rules.
    It checks the holiday sets for the year, previous year, and next year to
    cover cross-year observations (e.g., Jan 1 observed on Dec 31 previous year).
    """
    if dt is None:
        return False
    if hasattr(dt, "date"):
        d = dt.date()
    else:
        d = dt
    try:
        year = d.year
    except Exception:
        return False

    candidates = set()
    candidates.update(holidays_for_year(year - 1))
    candidates.update(holidays_for_year(year))
    candidates.update(holidays_for_year(year + 1))

    return d in candidates
