# tests/test_station_store.py
import sqlite3
import pytest
import pandas as pd
from src import station_store


@pytest.fixture(autouse=True)
def _patch_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr("src.station_store.DB_PATH", db)
    monkeypatch.setattr("src.event_store.DB_PATH", db)
    yield db


def test_init_creates_tables(_patch_db):
    station_store.init_station_db()
    with sqlite3.connect(_patch_db) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "police_stations" in tables
    assert "zone_centroids" in tables


def test_init_idempotent(_patch_db):
    station_store.init_station_db()
    station_store.init_station_db()
    assert station_store._count_stations() == 110


def test_seed_from_csv_inserts_110_rows(_patch_db):
    station_store.init_station_db()
    assert station_store._count_stations() == 110


def test_address_clean_strips_phone():
    _, addr = station_store._clean_station_field(
        "Cubbon Park # 7 cubbon park police station kasturba road bangalore 560001"
        "Ph no. 080-22942675"
    )
    assert "Ph no" not in addr
    assert "080-22942675" not in addr


def test_station_name_extraction():
    name, _ = station_store._clean_station_field(
        "Cubbon Park # 7 cubbon park police station kasturba road bangalore 560001"
        "Ph no. 080-22942675"
    )
    assert name == "Cubbon Park"


# ── Geocoding + BTP tests ─────────────────────────────────────────────────────

def _insert_station(conn, code, name, dcp, acp, lat=None, lng=None,
                    loc_src="pending", has_btp=0, btp_conf=None):
    """Helper: insert a minimal station row."""
    from src.station_store import _now
    conn.execute(
        """INSERT OR REPLACE INTO police_stations
           (station_code, station_name, address_clean, unit, dcp_zone, acp_zone,
            latitude, longitude, location_source, has_btp_pi, btp_match_confidence,
            capacity_officers, capacity_vehicles, capacity_source, phone,
            geocoded_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (code, name, f"addr {code}", None, dcp, acp,
         lat, lng, loc_src, has_btp, btp_conf, 25, 3, "default", None,
         _now() if lat else None, _now()),
    )


def test_geocode_skips_non_pending(_patch_db):
    station_store.init_station_db()
    # Mark first station as already geocoded
    with sqlite3.connect(_patch_db) as conn:
        code = conn.execute(
            "SELECT station_code FROM police_stations LIMIT 1"
        ).fetchone()[0]
        conn.execute(
            "UPDATE police_stations SET location_source='geocoded', latitude=12.97, longitude=77.59 WHERE station_code=?",
            (code,),
        )
        conn.commit()

    calls: list[str] = []
    def mock_geocoder(query):
        calls.append(query)
        return None

    station_store.geocode_all_stations(_geocoder=mock_geocoder)
    assert len(calls) == 109  # 110 total minus 1 already geocoded


def test_zone_centroid_fallback_applied(_patch_db):
    from src import event_store
    event_store.init_db()
    station_store.init_station_db()
    with sqlite3.connect(_patch_db) as conn:
        conn.execute("DELETE FROM police_stations")
        # One geocoded station in zone "Central"
        _insert_station(conn, 1, "Station A", "Central", "Cubbon",
                        lat=12.97, lng=77.59, loc_src="geocoded")
        # One pending station in same zone
        _insert_station(conn, 2, "Station B", "Central", "Cubbon")
        conn.commit()

    def mock_geocoder(query):
        return None  # all geocode attempts fail

    station_store.geocode_all_stations(_geocoder=mock_geocoder)

    with sqlite3.connect(_patch_db) as conn:
        row = conn.execute(
            "SELECT location_source, latitude, longitude FROM police_stations WHERE station_code=2"
        ).fetchone()
    assert row[0] == "zone_centroid_fallback"
    assert abs(row[1] - 12.97) < 0.001
    assert abs(row[2] - 77.59) < 0.001


def test_zone_centroid_from_geocoded_only(_patch_db):
    from src import event_store
    event_store.init_db()
    station_store.init_station_db()
    with sqlite3.connect(_patch_db) as conn:
        conn.execute("DELETE FROM police_stations")
        _insert_station(conn, 1, "S1", "East", "Frazer",
                        lat=13.0, lng=77.6, loc_src="geocoded")
        _insert_station(conn, 2, "S2", "East", "Frazer",
                        lat=99.0, lng=99.0, loc_src="zone_centroid_fallback")
        _insert_station(conn, 3, "S3", "East", "Frazer")
        conn.commit()

    def mock_geocoder(query):
        return None

    station_store.geocode_all_stations(_geocoder=mock_geocoder)

    with sqlite3.connect(_patch_db) as conn:
        centroid = conn.execute(
            "SELECT latitude, longitude FROM zone_centroids WHERE dcp_zone='East'"
        ).fetchone()
    # centroid must come from station 1 only (not the 99.0 fallback station)
    assert centroid is not None
    assert abs(centroid[0] - 13.0) < 0.001


def test_btp_exact_match_sets_flag(_patch_db):
    station_store.init_station_db()
    with sqlite3.connect(_patch_db) as conn:
        conn.execute("DELETE FROM police_stations")
        _insert_station(conn, 1, "Cubbon Park", "Central", "Cubbon")
        conn.commit()

    btp_df = pd.DataFrame([{
        "Officer": "Police Inspector Traffic",
        "Division": "East",
        "Subdivision": "Central",
        "Traffic Police Station": "Cubbon Park Police Station",
        "Phone": "080-123",
        "Mobile": "",
        "Email": "",
    }])
    station_store._enrich_btp_from_df(btp_df)

    with sqlite3.connect(_patch_db) as conn:
        row = conn.execute(
            "SELECT has_btp_pi, btp_match_confidence FROM police_stations WHERE station_code=1"
        ).fetchone()
    assert row[0] == 1
    assert row[1] == 1.0


def test_btp_fuzzy_match_sets_flag(_patch_db):
    station_store.init_station_db()
    with sqlite3.connect(_patch_db) as conn:
        conn.execute("DELETE FROM police_stations")
        _insert_station(conn, 1, "Indiranagar", "East", "Ulsoor")
        conn.commit()

    btp_df = pd.DataFrame([{
        "Officer": "Police Inspector Traffic",
        "Division": "East",
        "Subdivision": "Ulsoor",
        "Traffic Police Station": "Indira Nagar Police Station",
        "Phone": "080-456",
        "Mobile": "",
        "Email": "",
    }])
    station_store._enrich_btp_from_df(btp_df)

    with sqlite3.connect(_patch_db) as conn:
        row = conn.execute(
            "SELECT has_btp_pi, btp_match_confidence FROM police_stations WHERE station_code=1"
        ).fetchone()
    assert row[0] == 1
    assert 0.7 <= row[1] < 1.0


def test_btp_no_match_leaves_zero(_patch_db):
    station_store.init_station_db()
    with sqlite3.connect(_patch_db) as conn:
        conn.execute("DELETE FROM police_stations")
        _insert_station(conn, 1, "Remote Station", "North", "J.C.Nagar")
        conn.commit()

    btp_df = pd.DataFrame([{
        "Officer": "Police Inspector Traffic",
        "Division": "South",
        "Subdivision": "Chickpet",
        "Traffic Police Station": "Completely Different PS",
        "Phone": "",
        "Mobile": "",
        "Email": "",
    }])
    station_store._enrich_btp_from_df(btp_df)

    with sqlite3.connect(_patch_db) as conn:
        row = conn.execute(
            "SELECT has_btp_pi, btp_match_confidence FROM police_stations WHERE station_code=1"
        ).fetchone()
    assert row[0] == 0
    assert row[1] is None
