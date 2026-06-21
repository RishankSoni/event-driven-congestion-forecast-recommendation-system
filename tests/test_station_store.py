# tests/test_station_store.py
import sqlite3
import pytest
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
