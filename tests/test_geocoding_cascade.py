# tests/test_geocoding_cascade.py
import sqlite3

import pytest

from src.station_store import _try_geocode_strategies


class _FakeLoc:
    def __init__(self, lat=12.97, lng=77.59):
        self.latitude = lat
        self.longitude = lng


# ── _try_geocode_strategies unit tests ───────────────────────────────────────

def test_cascade_stops_on_first_success():
    calls = []

    def geocoder(q):
        calls.append(q)
        return _FakeLoc() if len(calls) == 1 else None

    result = _try_geocode_strategies("Cubbon Park", "Cubbon Park", geocoder)
    assert result == (12.97, 77.59)
    assert len(calls) == 1


def test_cascade_falls_through_to_second_strategy():
    calls = []

    def geocoder(q):
        calls.append(q)
        return _FakeLoc() if len(calls) == 2 else None

    result = _try_geocode_strategies("Cubbon Park", "Cubbon Park", geocoder)
    assert result == (12.97, 77.59)
    assert len(calls) == 2


def test_cascade_falls_through_to_third_strategy():
    calls = []

    def geocoder(q):
        calls.append(q)
        return _FakeLoc() if len(calls) == 3 else None

    result = _try_geocode_strategies("Cubbon Park", "Cubbon Park", geocoder)
    assert result == (12.97, 77.59)
    assert len(calls) == 3


def test_cascade_returns_none_when_all_fail():
    result = _try_geocode_strategies("Unknown Station", "Unknown Zone", lambda q: None)
    assert result is None


def test_cascade_query_strings_are_correct():
    queries = []

    def geocoder(q):
        queries.append(q)
        return None

    _try_geocode_strategies("Cubbon Park", "Seshadripuram", geocoder)
    assert queries[0] == "Cubbon Park Police Station, Seshadripuram, Bangalore, Karnataka, India"
    assert queries[1] == "Cubbon Park Police Station, Bangalore, Karnataka, India"
    assert queries[2] == "Cubbon Park, Bangalore, India"


# ── _retry_fallback_stations tests ───────────────────────────────────────────

import src.station_store as _ss


def _make_test_db(tmp_path, stations: list):
    """Create a minimal test DB with police_stations and zone_centroids tables."""
    db = tmp_path / "test.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE police_stations (
                station_code    INTEGER PRIMARY KEY,
                station_name    TEXT,
                address_clean   TEXT,
                acp_zone        TEXT,
                dcp_zone        TEXT,
                latitude        REAL,
                longitude       REAL,
                location_source TEXT,
                geocoded_at     TEXT,
                updated_at      TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE zone_centroids (
                dcp_zone  TEXT PRIMARY KEY,
                latitude  REAL NOT NULL,
                longitude REAL NOT NULL
            )
        """)
        for s in stations:
            conn.execute(
                "INSERT INTO police_stations "
                "(station_code, station_name, address_clean, acp_zone, dcp_zone, latitude, longitude, "
                "location_source, geocoded_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    s["station_code"], s["station_name"], s.get("address_clean", ""),
                    s["acp_zone"], s.get("dcp_zone", "Central"),
                    s.get("latitude"), s.get("longitude"),
                    s["location_source"], None, "2024-01-01",
                ),
            )
        conn.commit()
    return db


def test_retry_fallback_updates_successful_geocodes(tmp_path, monkeypatch):
    db = _make_test_db(tmp_path, [
        {
            "station_code": 1, "station_name": "Cubbon Park", "acp_zone": "Cubbon Park",
            "latitude": 12.5, "longitude": 77.5, "location_source": "zone_centroid_fallback",
        },
    ])
    monkeypatch.setattr(_ss, "DB_PATH", db)

    improved = _ss._retry_fallback_stations(lambda q: _FakeLoc(12.97, 77.59))
    assert improved == 1

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT location_source, latitude FROM police_stations WHERE station_code=1"
        ).fetchone()
    assert row[0] == "geocoded"
    assert abs(row[1] - 12.97) < 0.001


def test_retry_fallback_skips_when_geocoding_fails(tmp_path, monkeypatch):
    db = _make_test_db(tmp_path, [
        {
            "station_code": 2, "station_name": "Unknown", "acp_zone": "Nowhere",
            "latitude": 12.5, "longitude": 77.5, "location_source": "zone_centroid_fallback",
        },
    ])
    monkeypatch.setattr(_ss, "DB_PATH", db)

    improved = _ss._retry_fallback_stations(lambda q: None)
    assert improved == 0

    with sqlite3.connect(db) as conn:
        src = conn.execute(
            "SELECT location_source FROM police_stations WHERE station_code=2"
        ).fetchone()[0]
    assert src == "zone_centroid_fallback"


def test_retry_fallback_returns_zero_when_no_fallback_stations(tmp_path, monkeypatch):
    db = _make_test_db(tmp_path, [
        {
            "station_code": 3, "station_name": "Already Good", "acp_zone": "Central",
            "latitude": 12.97, "longitude": 77.59, "location_source": "geocoded",
        },
    ])
    monkeypatch.setattr(_ss, "DB_PATH", db)

    improved = _ss._retry_fallback_stations(lambda q: _FakeLoc())
    assert improved == 0


def test_geocode_all_stations_calls_retry_fallback(tmp_path, monkeypatch):
    """Integration: geocode_all_stations() upgrades fallback stations via retry."""
    db = _make_test_db(tmp_path, [
        {
            "station_code": 10, "station_name": "Fallback PS", "acp_zone": "East",
            "latitude": 12.5, "longitude": 77.5, "location_source": "zone_centroid_fallback",
        },
    ])
    monkeypatch.setattr(_ss, "DB_PATH", db)
    # Patch side-effect functions that need full DB schema or network
    monkeypatch.setattr(_ss, "_apply_zone_centroid_fallback", lambda: None)
    monkeypatch.setattr(_ss, "_compute_and_store_zone_centroids", lambda: None)
    monkeypatch.setattr(_ss, "_enrich_btp", lambda: None)

    _ss.geocode_all_stations(_geocoder=lambda q: _FakeLoc(12.97, 77.59))

    with sqlite3.connect(db) as conn:
        src = conn.execute(
            "SELECT location_source FROM police_stations WHERE station_code=10"
        ).fetchone()[0]
    assert src == "geocoded"
