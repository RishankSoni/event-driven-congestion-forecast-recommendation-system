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
    assert len(calls) == 109  # 110 seeded - 1 geocoded


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


# ── Ranking + allocation tests ────────────────────────────────────────────────

@pytest.fixture
def db_with_events(_patch_db):
    """DB with both police_stations and planned_events tables."""
    from src import event_store
    event_store.init_db()
    station_store.init_station_db()
    return _patch_db


def _insert_geocoded_station(conn, code, name, lat, lng, dcp="Central", has_btp=0, btp_conf=None):
    from src.station_store import _now
    conn.execute(
        """INSERT OR REPLACE INTO police_stations
           (station_code, station_name, address_clean, unit, dcp_zone, acp_zone,
            latitude, longitude, location_source, has_btp_pi, btp_match_confidence,
            capacity_officers, capacity_vehicles, capacity_source, phone,
            geocoded_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (code, name, f"addr {code}", None, dcp, "Cubbon",
         lat, lng, "geocoded", has_btp, btp_conf, 25, 3, "default", None,
         _now(), _now()),
    )


def test_rank_stations_distance_ordering(db_with_events):
    # Event at (12.97, 77.59); insert stations at 3km and 6km
    with sqlite3.connect(db_with_events) as conn:
        conn.execute("DELETE FROM police_stations")
        # ~3km north: 3/111 ≈ 0.027 degrees
        _insert_geocoded_station(conn, 1, "Near Station",  12.97 + 0.027, 77.59)
        # ~6km north
        _insert_geocoded_station(conn, 2, "Far Station",   12.97 + 0.054, 77.59)
        conn.commit()

    results = station_store.rank_stations(12.97, 77.59, "2026-07-15", "10:00", top_n=2)
    assert len(results) == 2
    assert results[0]["station_name"] == "Near Station"
    assert results[1]["station_name"] == "Far Station"


def test_rank_stations_btp_boost(db_with_events):
    # Station A: 3km, no BTP → score ≈ 3.0
    # Station B: 4.5km, has BTP → score ≈ 4.5 - 2.0 = 2.5 → B should rank first
    with sqlite3.connect(db_with_events) as conn:
        conn.execute("DELETE FROM police_stations")
        _insert_geocoded_station(conn, 1, "Station A No BTP", 12.97 + 0.027, 77.59, has_btp=0)
        _insert_geocoded_station(conn, 2, "Station B BTP",    12.97 + 0.040, 77.59, has_btp=1, btp_conf=1.0)
        conn.commit()

    results = station_store.rank_stations(12.97, 77.59, "2026-07-15", "10:00", top_n=2)
    assert results[0]["station_name"] == "Station B BTP"


def test_rank_stations_workload_penalty(db_with_events):
    # Station A: 3km, workload=0 → score ≈ 3.0
    # Station B: 1km, workload=2 → score ≈ 1.0 + 2*1.5 = 4.0 → A should rank first
    from src import event_store
    with sqlite3.connect(db_with_events) as conn:
        conn.execute("DELETE FROM police_stations")
        _insert_geocoded_station(conn, 1, "Station A",  12.97 + 0.027, 77.59)
        _insert_geocoded_station(conn, 2, "Station B",  12.97 + 0.009, 77.59)
        conn.commit()

    # Add 2 active events assigned to Station B on same day/time
    for i in range(2):
        event_store.save_event({
            "event_name":    f"Existing Event {i}",
            "event_type":    "planned",
            "event_cause":   "procession",
            "corridor":      "MG Road",
            "zone":          "Central",
            "police_station": "Station B",
            "event_date":    "2026-07-15",
            "event_time":    "10:00",
        })

    results = station_store.rank_stations(12.97, 77.59, "2026-07-15", "10:00", top_n=2)
    assert results[0]["station_name"] == "Station A"


def test_rank_stations_returns_empty_if_few_geocoded(db_with_events):
    with sqlite3.connect(db_with_events) as conn:
        conn.execute("DELETE FROM police_stations")
        _insert_geocoded_station(conn, 1, "Only Station", 12.97, 77.59)
        conn.commit()

    results = station_store.rank_stations(12.97, 77.59, "2026-07-15", "10:00")
    assert results == []


def test_allocate_officers_sums_to_total(db_with_events):
    stations = [
        {"station_name": "A", "distance_km": 2.0, "capacity_officers": 25,
         "capacity_source": "default", "officers_allocated": 0,
         "allocation_capped": False, "capacity_unconfirmed": False},
        {"station_name": "B", "distance_km": 4.0, "capacity_officers": 25,
         "capacity_source": "default", "officers_allocated": 0,
         "allocation_capped": False, "capacity_unconfirmed": False},
    ]
    result = station_store.allocate_officers(stations, 12)
    total_allocated = sum(s["officers_allocated"] for s in result)
    assert abs(total_allocated - 12) <= 1  # rounding tolerance of ±1


def test_allocate_cap_applied_only_for_manual(db_with_events):
    stations = [
        {"station_name": "Default", "distance_km": 1.0, "capacity_officers": 5,
         "capacity_source": "default", "officers_allocated": 0,
         "allocation_capped": False, "capacity_unconfirmed": False},
        {"station_name": "Manual",  "distance_km": 1.0, "capacity_officers": 5,
         "capacity_source": "manual",  "officers_allocated": 0,
         "allocation_capped": False, "capacity_unconfirmed": False},
    ]
    result = station_store.allocate_officers(stations, 20)
    default_s = next(s for s in result if s["station_name"] == "Default")
    manual_s  = next(s for s in result if s["station_name"] == "Manual")
    # Manual station: capped at 5
    assert manual_s["officers_allocated"] <= 5
    assert manual_s["allocation_capped"] is True
    assert manual_s["capacity_unconfirmed"] is False
    # Default station: NOT capped (raw ≈ 10, exceeds cap of 5 but cap not applied)
    assert default_s["officers_allocated"] > 5
    assert default_s["capacity_unconfirmed"] is True


def test_allocate_both_branches_set_all_keys(db_with_events):
    stations = [
        {"station_name": "D", "distance_km": 2.0, "capacity_officers": 25,
         "capacity_source": "default", "officers_allocated": 0,
         "allocation_capped": False, "capacity_unconfirmed": False},
        {"station_name": "M", "distance_km": 2.0, "capacity_officers": 25,
         "capacity_source": "manual",  "officers_allocated": 0,
         "allocation_capped": False, "capacity_unconfirmed": False},
    ]
    result = station_store.allocate_officers(stations, 10)
    for s in result:
        assert "officers_allocated"   in s
        assert "allocation_capped"    in s
        assert "capacity_unconfirmed" in s


def test_capacity_update_sets_source_manual(db_with_events):
    station_store.init_station_db()
    with sqlite3.connect(db_with_events) as conn:
        code = conn.execute(
            "SELECT station_code FROM police_stations LIMIT 1"
        ).fetchone()[0]

    station_store.update_station_capacity(code, officers=30, vehicles=5)

    with sqlite3.connect(db_with_events) as conn:
        row = conn.execute(
            "SELECT capacity_officers, capacity_vehicles, capacity_source "
            "FROM police_stations WHERE station_code=?",
            (code,),
        ).fetchone()
    assert row[0] == 30
    assert row[1] == 5
    assert row[2] == "manual"
