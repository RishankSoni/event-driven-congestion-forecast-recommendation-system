import datetime
import pytest
from src.calendar_intel import get_holiday_info


def test_non_holiday_returns_tier_zero():
    result = get_holiday_info(datetime.date(2024, 6, 5))   # random Wednesday
    assert result["is_holiday"] is False
    assert result["holiday_type"] == "none"
    assert result["risk_tier"] == 0
    assert result["holiday_name"] == ""


def test_republic_day_is_national():
    result = get_holiday_info(datetime.date(2024, 1, 26))
    assert result["is_holiday"] is True
    assert result["holiday_type"] == "national"
    assert result["holiday_name"] == "Republic Day"
    assert result["risk_tier"] == 2


def test_independence_day_is_national():
    result = get_holiday_info(datetime.date(2025, 8, 15))
    assert result["is_holiday"] is True
    assert result["holiday_type"] == "national"
    assert result["risk_tier"] == 2


def test_rajyotsava_is_state():
    result = get_holiday_info(datetime.date(2024, 11, 1))
    # Nov 1 2024 is also within Diwali window — festival tier wins
    assert result["is_holiday"] is True
    assert result["risk_tier"] >= 1


def test_dasara_window_2024():
    # Vijayadashami 2024: Oct 12. Window Oct 3–12.
    for day in range(3, 13):
        r = get_holiday_info(datetime.date(2024, 10, day))
        assert r["is_holiday"] is True, f"Oct {day} 2024 should be Dasara"
        assert r["risk_tier"] == 3


def test_outside_dasara_window_2024():
    result = get_holiday_info(datetime.date(2024, 10, 2))  # day before window
    # Oct 2 is Gandhi Jayanti (national, tier 2) — still a holiday, just not Dasara
    assert result["is_holiday"] is True
    assert result["risk_tier"] == 2


def test_diwali_2024_window():
    for d in [datetime.date(2024, 10, 31), datetime.date(2024, 11, 1), datetime.date(2024, 11, 2)]:
        r = get_holiday_info(d)
        assert r["is_holiday"] is True
        assert r["risk_tier"] == 3


def test_new_years_eve():
    result = get_holiday_info(datetime.date(2025, 12, 31))
    assert result["is_holiday"] is True
    assert result["risk_tier"] == 3


def test_return_type_structure():
    result = get_holiday_info(datetime.date(2024, 3, 15))
    assert set(result.keys()) == {"is_holiday", "holiday_type", "holiday_name", "risk_tier"}
    assert isinstance(result["is_holiday"], bool)
    assert isinstance(result["risk_tier"], int)
