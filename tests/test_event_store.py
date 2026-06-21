# tests/test_event_store.py
import sqlite3
import pytest
from pathlib import Path
from src import event_store


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect DB_PATH to a temp file for isolation."""
    db = tmp_path / "test_events.db"
    monkeypatch.setattr(event_store, "DB_PATH", db)
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
