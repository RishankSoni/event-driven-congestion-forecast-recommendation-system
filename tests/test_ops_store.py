# tests/test_ops_store.py
from datetime import date, timedelta

import pytest

from src import event_store, ops_store, station_store


@pytest.fixture(autouse=True)
def _patch_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr("src.event_store.DB_PATH", db)
    monkeypatch.setattr("src.station_store.DB_PATH", db)
    event_store.init_db()
    station_store.init_station_db()
    return db


def _save(name, corridor="MG Road", zone="Central", date_str=None,
          time_str="10:00", lat=12.97, lng=77.59,
          attendance=500, officer_min=5, officer_max=8):
    today = date_str or date.today().strftime("%Y-%m-%d")
    return event_store.save_event({
        "event_name": name,
        "event_type": "planned",
        "event_cause": "public_event",
        "corridor": corridor,
        "zone": zone,
        "event_date": today,
        "event_time": time_str,
        "latitude": lat,
        "longitude": lng,
        "estimated_attendance": attendance,
        "has_vip": 0,
        "officer_min": officer_min,
        "officer_max": officer_max,
    })


# ── get_today_events ──────────────────────────────────────────────────────────

def test_get_today_events_returns_list():
    result = ops_store.get_today_events()
    assert isinstance(result, list)


def test_get_today_events_filters_status():
    eid = _save("Rally")
    event_store.update_status(eid, "cancelled")
    result = ops_store.get_today_events()
    assert all(e["event_id"] != eid for e in result)


# ── get_week_events ───────────────────────────────────────────────────────────

def test_get_week_events_respects_days_param():
    today = date.today()
    far_date = (today + timedelta(days=8)).strftime("%Y-%m-%d")
    _save("Far Event", date_str=far_date)
    result = ops_store.get_week_events(days=7)
    assert all(e["event_date"] != far_date for e in result)


# ── detect_conflict_pairs ─────────────────────────────────────────────────────

def test_detect_conflict_pairs_requires_two_events():
    eid = _save("Solo")
    ev = event_store.get_event(eid)
    assert ops_store.detect_conflict_pairs([ev]) == []


def test_detect_conflict_pairs_same_corridor():
    eid1 = _save("Event A", corridor="MG Road", time_str="10:00")
    eid2 = _save("Event B", corridor="MG Road", time_str="12:00")
    ev1 = event_store.get_event(eid1)
    ev2 = event_store.get_event(eid2)
    pairs = ops_store.detect_conflict_pairs([ev1, ev2])
    assert len(pairs) == 1


def test_detect_conflict_pairs_far_apart_not_flagged():
    # 20 km apart, different corridors
    eid1 = _save("North Event", corridor="Tumkur Road", lat=13.10, lng=77.55)
    eid2 = _save("South Event", corridor="Hosur Road",  lat=12.90, lng=77.65)
    ev1 = event_store.get_event(eid1)
    ev2 = event_store.get_event(eid2)
    pairs = ops_store.detect_conflict_pairs([ev1, ev2])
    assert pairs == []


def test_detect_conflict_pairs_different_day_not_flagged():
    today = date.today()
    tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    eid1 = _save("Today Event",    date_str=today.strftime("%Y-%m-%d"), corridor="MG Road")
    eid2 = _save("Tomorrow Event", date_str=tomorrow,                   corridor="MG Road")
    ev1 = event_store.get_event(eid1)
    ev2 = event_store.get_event(eid2)
    pairs = ops_store.detect_conflict_pairs([ev1, ev2])
    assert pairs == []


# ── get_zone_utilization ──────────────────────────────────────────────────────

def test_get_zone_utilization_counts_active():
    _save("Event 1", zone="Central")
    _save("Event 2", zone="Central")
    result = ops_store.get_zone_utilization()
    assert result.get("Central", 0) == 2


# ── optimize_multi_event ──────────────────────────────────────────────────────

def test_optimize_multi_event_empty_returns_empty():
    result = ops_store.optimize_multi_event([])
    assert result["events"] == []
    assert result["total_officers_min"] == 0
    assert result["total_officers_max"] == 0
    assert result["per_event"] == []
    assert result["station_conflicts"] == []
    assert result["unresolvable"] is False


def test_optimize_multi_event_sums_officers():
    eid1 = _save("Event A", officer_min=5, officer_max=8)
    eid2 = _save("Event B", officer_min=5, officer_max=8)
    result = ops_store.optimize_multi_event([eid1, eid2])
    assert result["total_officers_min"] == 10
    assert result["total_officers_max"] == 16
