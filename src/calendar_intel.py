import datetime

# Fixed holidays: (month, day) → (holiday_type, holiday_name, risk_tier)
_FIXED_ANNUAL: dict[tuple, tuple] = {
    (1,  1):  ("festival", "New Year",            3),
    (1,  26): ("national", "Republic Day",         2),
    (4,  14): ("national", "Ambedkar Jayanti",     2),
    (8,  15): ("national", "Independence Day",     2),
    (10, 2):  ("national", "Gandhi Jayanti",       2),
    (11, 1):  ("state",    "Rajyotsava",           1),
    (12, 25): ("national", "Christmas",            2),
    (12, 31): ("festival", "New Year's Eve",       3),
}

# Variable/lunar holidays: datetime.date → (holiday_type, holiday_name, risk_tier)
# Each day in a multi-day festival window is listed individually.
_VARIABLE_DATES: dict[datetime.date, tuple] = {
    # ── 2022 ──
    datetime.date(2022, 3, 17): ("festival", "Holi",            3),
    datetime.date(2022, 3, 18): ("festival", "Holi",            3),
    datetime.date(2022, 4, 2):  ("state",    "Ugadi",           1),
    datetime.date(2022, 5, 2):  ("festival", "Eid al-Fitr",     3),
    datetime.date(2022, 5, 3):  ("festival", "Eid al-Fitr",     3),
    datetime.date(2022, 5, 4):  ("festival", "Eid al-Fitr",     3),
    datetime.date(2022, 7, 9):  ("festival", "Eid al-Adha",     3),
    datetime.date(2022, 7, 10): ("festival", "Eid al-Adha",     3),
    datetime.date(2022, 7, 11): ("festival", "Eid al-Adha",     3),
    **{datetime.date(2022, 9, d): ("festival", "Dasara", 3) for d in range(26, 31)},
    datetime.date(2022, 10, 1): ("festival", "Dasara",          3),
    datetime.date(2022, 10, 2): ("festival", "Dasara",          3),  # also Gandhi Jayanti
    datetime.date(2022, 10, 9): ("state",    "Valmiki Jayanti", 1),
    datetime.date(2022, 10, 24): ("festival", "Diwali",         3),
    datetime.date(2022, 10, 25): ("festival", "Diwali",         3),
    datetime.date(2022, 10, 26): ("festival", "Diwali",         3),
    datetime.date(2022, 11, 19): ("state",   "Kanakadasa Jayanti", 1),

    # ── 2023 ──
    datetime.date(2023, 3, 7):  ("festival", "Holi",            3),
    datetime.date(2023, 3, 8):  ("festival", "Holi",            3),
    datetime.date(2023, 3, 22): ("state",    "Ugadi",           1),
    datetime.date(2023, 4, 21): ("festival", "Eid al-Fitr",     3),
    datetime.date(2023, 4, 22): ("festival", "Eid al-Fitr",     3),
    datetime.date(2023, 4, 23): ("festival", "Eid al-Fitr",     3),
    datetime.date(2023, 6, 28): ("festival", "Eid al-Adha",     3),
    datetime.date(2023, 6, 29): ("festival", "Eid al-Adha",     3),
    datetime.date(2023, 6, 30): ("festival", "Eid al-Adha",     3),
    **{datetime.date(2023, 10, d): ("festival", "Dasara", 3) for d in range(15, 25)},
    datetime.date(2023, 10, 28): ("state",   "Valmiki Jayanti", 1),
    datetime.date(2023, 11, 12): ("festival", "Diwali",         3),
    datetime.date(2023, 11, 13): ("festival", "Diwali",         3),
    datetime.date(2023, 11, 14): ("festival", "Diwali",         3),
    datetime.date(2023, 11, 27): ("state",   "Kanakadasa Jayanti", 1),

    # ── 2024 ──
    datetime.date(2024, 3, 25): ("festival", "Holi",            3),
    datetime.date(2024, 3, 26): ("festival", "Holi",            3),
    datetime.date(2024, 4, 9):  ("festival", "Eid al-Fitr",     3),  # also Ugadi
    datetime.date(2024, 4, 10): ("festival", "Eid al-Fitr",     3),
    datetime.date(2024, 4, 11): ("festival", "Eid al-Fitr",     3),
    datetime.date(2024, 6, 16): ("festival", "Eid al-Adha",     3),
    datetime.date(2024, 6, 17): ("festival", "Eid al-Adha",     3),
    datetime.date(2024, 6, 18): ("festival", "Eid al-Adha",     3),
    **{datetime.date(2024, 10, d): ("festival", "Dasara", 3) for d in range(3, 13)},
    datetime.date(2024, 10, 17): ("state",   "Valmiki Jayanti", 1),
    datetime.date(2024, 10, 31): ("festival", "Diwali",         3),
    datetime.date(2024, 11, 1):  ("festival", "Diwali",         3),  # also Rajyotsava
    datetime.date(2024, 11, 2):  ("festival", "Diwali",         3),
    datetime.date(2024, 11, 14): ("state",   "Kanakadasa Jayanti", 1),

    # ── 2025 ──
    datetime.date(2025, 3, 13): ("festival", "Holi",            3),
    datetime.date(2025, 3, 14): ("festival", "Holi",            3),
    datetime.date(2025, 3, 30): ("festival", "Eid al-Fitr",     3),  # also Ugadi
    datetime.date(2025, 3, 31): ("festival", "Eid al-Fitr",     3),
    datetime.date(2025, 6, 6):  ("festival", "Eid al-Adha",     3),
    datetime.date(2025, 6, 7):  ("festival", "Eid al-Adha",     3),
    datetime.date(2025, 6, 8):  ("festival", "Eid al-Adha",     3),
    **{datetime.date(2025, 9, d): ("festival", "Dasara", 3) for d in range(23, 30)},
    datetime.date(2025, 9, 30): ("festival", "Dasara",          3),
    datetime.date(2025, 10, 1): ("festival", "Dasara",          3),
    datetime.date(2025, 10, 2): ("festival", "Dasara",          3),  # also Gandhi Jayanti
    datetime.date(2025, 10, 6): ("state",    "Valmiki Jayanti", 1),
    datetime.date(2025, 10, 19): ("festival", "Diwali",         3),
    datetime.date(2025, 10, 20): ("festival", "Diwali",         3),
    datetime.date(2025, 10, 21): ("festival", "Diwali",         3),
    datetime.date(2025, 11, 3): ("state",    "Kanakadasa Jayanti", 1),

    # ── 2026 ──
    datetime.date(2026, 3, 2):  ("festival", "Holi",            3),
    datetime.date(2026, 3, 3):  ("festival", "Holi",            3),
    datetime.date(2026, 3, 20): ("festival", "Eid al-Fitr",     3),  # also Ugadi ~Mar 20
    datetime.date(2026, 3, 21): ("festival", "Eid al-Fitr",     3),
    datetime.date(2026, 3, 22): ("festival", "Eid al-Fitr",     3),
    datetime.date(2026, 5, 27): ("festival", "Eid al-Adha",     3),
    datetime.date(2026, 5, 28): ("festival", "Eid al-Adha",     3),
    datetime.date(2026, 5, 29): ("festival", "Eid al-Adha",     3),
    **{datetime.date(2026, 10, d): ("festival", "Dasara", 3) for d in range(13, 23)},
    datetime.date(2026, 10, 25): ("state",   "Valmiki Jayanti", 1),
    datetime.date(2026, 11, 7): ("festival", "Diwali",          3),
    datetime.date(2026, 11, 8): ("festival", "Diwali",          3),
    datetime.date(2026, 11, 9): ("festival", "Diwali",          3),
    datetime.date(2026, 11, 23): ("state",   "Kanakadasa Jayanti", 1),

    # ── 2027 ──
    datetime.date(2027, 3, 1):  ("festival", "Holi",            3),
    datetime.date(2027, 3, 2):  ("festival", "Holi",            3),
    datetime.date(2027, 3, 9):  ("state",    "Ugadi",           1),
    datetime.date(2027, 3, 10): ("festival", "Eid al-Fitr",     3),
    datetime.date(2027, 3, 11): ("festival", "Eid al-Fitr",     3),
    datetime.date(2027, 5, 17): ("festival", "Eid al-Adha",     3),
    datetime.date(2027, 5, 18): ("festival", "Eid al-Adha",     3),
    datetime.date(2027, 5, 19): ("festival", "Eid al-Adha",     3),
    **{datetime.date(2027, 10, d): ("festival", "Dasara", 3) for d in range(1, 11)},
    datetime.date(2027, 10, 26): ("festival", "Diwali",         3),
    datetime.date(2027, 10, 27): ("festival", "Diwali",         3),
    datetime.date(2027, 10, 28): ("festival", "Diwali",         3),
}


def _build_lookup() -> dict[datetime.date, tuple]:
    lookup: dict[datetime.date, tuple] = {}
    # Variable/lunar dates first
    for d, info in _VARIABLE_DATES.items():
        lookup[d] = info
    # Fixed annual dates: only overwrite if fixed holiday tier is equal or higher than existing variable entry
    for year in range(2022, 2028):
        for (month, day), info in _FIXED_ANNUAL.items():
            try:
                date = datetime.date(year, month, day)
            except ValueError:
                continue
            existing = lookup.get(date)
            if existing is None or info[2] >= existing[2]:
                lookup[date] = info
    return lookup


_LOOKUP: dict[datetime.date, tuple] = _build_lookup()


def get_holiday_info(date: datetime.date) -> dict:
    """Return holiday metadata for a given date.

    Checks the pre-built lookup table, then applies long-weekend detection
    for any Monday/Friday adjacent to a Tuesday/Thursday holiday.
    """
    entry = _LOOKUP.get(date)
    if entry:
        return {
            "is_holiday":   True,
            "holiday_type": entry[0],
            "holiday_name": entry[1],
            "risk_tier":    entry[2],
        }

    # Long weekend: Monday after a Tuesday holiday, or Friday before a Thursday holiday
    weekday = date.weekday()  # 0=Mon, 4=Fri
    if weekday == 0:  # Monday — check if Tuesday is a holiday
        neighbour = _LOOKUP.get(date + datetime.timedelta(days=1))
        if neighbour:
            return {"is_holiday": True, "holiday_type": "state",
                    "holiday_name": f"Long weekend ({neighbour[1]})", "risk_tier": 1}
    if weekday == 4:  # Friday — check if Thursday is a holiday
        neighbour = _LOOKUP.get(date - datetime.timedelta(days=1))
        if neighbour:
            return {"is_holiday": True, "holiday_type": "state",
                    "holiday_name": f"Long weekend ({neighbour[1]})", "risk_tier": 1}

    return {"is_holiday": False, "holiday_type": "none", "holiday_name": "", "risk_tier": 0}
