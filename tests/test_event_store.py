# tests/test_event_store.py
import sqlite3
import pytest
from pathlib import Path
from src import event_store
from src import station_store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect DB_PATH to a temp file for isolation."""
    db = tmp_path / "test_events.db"
    monkeypatch.setattr(event_store, "DB_PATH", db)
    monkeypatch.setattr(station_store, "DB_PATH", db)
    return db


def test_init_db_creates_file(tmp_db):
    event_store.init_db()
    assert tmp_db.exists()


def test_init_db_creates_table(tmp_db):
    event_store.init_db()
    with sqlite3.connect(tmp_db) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )]
    assert "planned_events" in tables


def test_init_db_idempotent(tmp_db):
    event_store.init_db()
    event_store.init_db()   # must not raise


# ── Task 2: save_event / get_event ────────────────────────────────────────────

import json  # noqa: E402


def _make_event(**overrides) -> dict:
    base = {
        "event_name":  "Test Rally",
        "event_type":  "planned",
        "event_cause": "public_event",
        "corridor":    "MG Road",
        "zone":        "Central Division, Bangalore City",
        "event_date":  "2026-07-01",
        "event_time":  "14:00",
        "latitude":    12.975,
        "longitude":   77.607,
    }
    return {**base, **overrides}


def test_save_event_returns_uuid(tmp_db):
    event_store.init_db()
    eid = event_store.save_event(_make_event())
    assert len(eid) == 36
    assert eid.count("-") == 4


def test_get_event_round_trips(tmp_db):
    event_store.init_db()
    eid = event_store.save_event(_make_event(event_name="Dasara Parade"))
    fetched = event_store.get_event(eid)
    assert fetched is not None
    assert fetched["event_name"] == "Dasara Parade"
    assert fetched["event_id"] == eid
    assert fetched["status"] == "planned"


def test_get_event_missing_returns_none(tmp_db):
    event_store.init_db()
    assert event_store.get_event("does-not-exist") is None


def test_save_event_serializes_list_fields(tmp_db):
    event_store.init_db()
    eid = event_store.save_event(_make_event(
        barricades_json=["Junction A", "Junction B"],
        feature_vector_json={"corridor": "MG Road", "hour_of_day": 14},
    ))
    fetched = event_store.get_event(eid)
    assert json.loads(fetched["barricades_json"]) == ["Junction A", "Junction B"]
    assert json.loads(fetched["feature_vector_json"])["hour_of_day"] == 14


def test_save_event_does_not_double_serialize_strings(tmp_db):
    event_store.init_db()
    eid = event_store.save_event(_make_event(
        shap_drivers_json=json.dumps([{"feature": "corridor", "pct": 30}]),
    ))
    fetched = event_store.get_event(eid)
    drivers = json.loads(fetched["shap_drivers_json"])
    assert drivers[0]["feature"] == "corridor"


# ── Task 3: list_events / update_status ──────────────────────────────────────

def test_list_events_returns_all_unfiltered(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(event_name="A"))
    event_store.save_event(_make_event(event_name="B"))
    assert len(event_store.list_events()) == 2


def test_list_events_filters_by_corridor(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(corridor="MG Road"))
    event_store.save_event(_make_event(corridor="ORR East"))
    result = event_store.list_events(corridor="MG Road")
    assert len(result) == 1
    assert result[0]["corridor"] == "MG Road"


def test_list_events_filters_by_severity(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(severity="HIGH"))
    event_store.save_event(_make_event(severity="LOW"))
    assert len(event_store.list_events(severity="HIGH")) == 1


def test_list_events_filters_by_date_range(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(event_date="2026-07-01"))
    event_store.save_event(_make_event(event_date="2026-08-01"))
    result = event_store.list_events(date_from="2026-07-15", date_to="2026-08-31")
    assert len(result) == 1
    assert result[0]["event_date"] == "2026-08-01"


def test_list_events_ordered_by_date_time(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(event_date="2026-07-03", event_time="10:00"))
    event_store.save_event(_make_event(event_date="2026-07-01", event_time="18:00"))
    results = event_store.list_events()
    assert results[0]["event_date"] == "2026-07-01"


def test_update_status_persists(tmp_db):
    event_store.init_db()
    eid = event_store.save_event(_make_event())
    event_store.update_status(eid, "active")
    assert event_store.get_event(eid)["status"] == "active"


def test_update_status_invalid_raises(tmp_db):
    event_store.init_db()
    eid = event_store.save_event(_make_event())
    with pytest.raises(ValueError, match="Invalid status"):
        event_store.update_status(eid, "deleted")


# ── Task 4: check_conflicts ───────────────────────────────────────────────────

def test_conflict_branch1_corridor_match(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(
        event_date="2026-07-01", event_time="15:00", status="planned",
    ))
    conflicts, note = event_store.check_conflicts(
        _make_event(event_date="2026-07-01", event_time="14:00")
    )
    assert len(conflicts) == 1
    assert note == ""


def test_conflict_branch1_no_match_far_time(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(
        event_date="2026-07-01", event_time="08:00",
    ))
    conflicts, _ = event_store.check_conflicts(
        _make_event(event_date="2026-07-01", event_time="18:00")
    )
    assert conflicts == []


def test_conflict_branch1_excludes_cancelled(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(
        event_date="2026-07-01", event_time="14:30", status="cancelled",
    ))
    conflicts, _ = event_store.check_conflicts(
        _make_event(event_date="2026-07-01", event_time="14:00")
    )
    assert conflicts == []


def test_conflict_branch2_zone_no_centroid_returns_qualifier(tmp_db, monkeypatch):
    station_store.init_station_db()
    event_store.init_db()
    # Insert test zone centroid row
    with sqlite3.connect(tmp_db) as conn:
        # Do NOT insert any zone_centroid, leaving the table empty
        pass
    event_store.save_event(_make_event(
        corridor=None,
        event_date="2026-07-01", event_time="14:30",
    ))
    conflicts, note = event_store.check_conflicts({
        "event_date": "2026-07-01",
        "event_time": "14:00",
        "zone": "Central Division, Bangalore City",
    })
    assert len(conflicts) == 1
    assert "time-window only" in note


def test_conflict_branch2_distance_cap_filters_far_events(tmp_db, monkeypatch):
    station_store.init_station_db()
    event_store.init_db()
    # Insert test zone centroid row
    with sqlite3.connect(tmp_db) as conn:
        conn.execute(
            "INSERT INTO zone_centroids (dcp_zone, latitude, longitude) VALUES (?, ?, ?)",
            ("Central Division, Bangalore City", 12.975, 77.607),
        )
        conn.commit()
    event_store.save_event(_make_event(
        corridor=None,
        latitude=12.850, longitude=77.607,
        event_date="2026-07-01", event_time="14:30",
    ))
    conflicts, note = event_store.check_conflicts({
        "event_date": "2026-07-01",
        "event_time": "14:00",
        "zone": "Central Division, Bangalore City",
        "latitude": 12.975,
        "longitude": 77.607,
    })
    assert conflicts == []
    assert note == ""


def test_conflict_branch3_latlng_within_3km(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(
        corridor=None, zone=None,
        event_date="2026-07-01", event_time="14:30",
        latitude=12.975, longitude=77.607,
    ))
    conflicts, _ = event_store.check_conflicts({
        "event_date": "2026-07-01",
        "event_time": "14:00",
        "latitude": 12.984,
        "longitude": 77.607,
    })
    assert len(conflicts) == 1


def test_conflict_branch3_latlng_outside_3km(tmp_db):
    event_store.init_db()
    event_store.save_event(_make_event(
        corridor=None, zone=None,
        event_date="2026-07-01", event_time="14:30",
        latitude=12.975, longitude=77.607,
    ))
    conflicts, _ = event_store.check_conflicts({
        "event_date": "2026-07-01",
        "event_time": "14:00",
        "latitude": 13.047,
        "longitude": 77.607,
    })
    assert conflicts == []


def test_conflict_branch4_no_location_returns_empty(tmp_db, caplog):
    import logging
    event_store.init_db()
    event_store.save_event(_make_event(event_date="2026-07-01", event_time="14:30"))
    with caplog.at_level(logging.WARNING):
        conflicts, note = event_store.check_conflicts({
            "event_date": "2026-07-01",
            "event_time": "14:00",
        })
    assert conflicts == []
    assert note == ""
    assert "no location data" in caplog.text
