# src/event_store.py
import json
import logging
import math
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DB_PATH = Path("data/events.db")

_DDL = """
CREATE TABLE IF NOT EXISTS planned_events (
    event_id               TEXT PRIMARY KEY,
    event_name             TEXT NOT NULL,
    event_type             TEXT NOT NULL,
    event_cause            TEXT NOT NULL,
    event_category         TEXT,
    corridor               TEXT,
    zone                   TEXT,
    police_station         TEXT,
    junction               TEXT,
    organizer_name         TEXT,
    event_date             TEXT NOT NULL,
    event_time             TEXT NOT NULL,
    expected_duration_h    REAL,
    estimated_attendance   INTEGER,
    has_vip                INTEGER DEFAULT 0,
    is_route_event         INTEGER DEFAULT 0,
    requires_road_closure  INTEGER DEFAULT 0,
    route_start            TEXT,
    route_end              TEXT,
    latitude               REAL,
    longitude              REAL,
    severity               TEXT,
    severity_conf          REAL,
    congestion_prob        REAL,
    law_order_prob         REAL,
    duration_label         TEXT,
    officer_min            INTEGER,
    officer_max            INTEGER,
    barricades_json        TEXT,
    diversions_json        TEXT,
    holiday_name           TEXT,
    holiday_risk_tier      INTEGER,
    feature_vector_json    TEXT,
    shap_drivers_json      TEXT,
    status                 TEXT DEFAULT 'planned',
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);
"""

_COLUMNS = [
    "event_id", "event_name", "event_type", "event_cause", "event_category",
    "corridor", "zone", "police_station", "junction", "organizer_name",
    "event_date", "event_time", "expected_duration_h", "estimated_attendance",
    "has_vip", "is_route_event", "requires_road_closure", "route_start", "route_end",
    "latitude", "longitude",
    "severity", "severity_conf", "congestion_prob", "law_order_prob", "duration_label",
    "officer_min", "officer_max", "barricades_json", "diversions_json",
    "holiday_name", "holiday_risk_tier", "feature_vector_json", "shap_drivers_json",
    "status", "created_at", "updated_at",
]


def init_db() -> None:
    """Create DB file and tables if they do not exist. Safe to call repeatedly."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(_DDL)
        conn.commit()
