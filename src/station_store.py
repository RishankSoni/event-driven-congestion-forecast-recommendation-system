# src/station_store.py
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.event_store import DB_PATH

_CSV_PATH = Path("bangalore_city_police_stations_2012.csv")
_BTP_CSV_URL = (
    "https://data.opencity.in/dataset/e3444619-12c5-43bd-9fc5-a54e83cc162f"
    "/resource/8521e8fb-168b-46fa-9faa-00faf2f2daa6"
    "/download/570ea599-d0af-4d1d-a659-381204a3d918.csv"
)

_DDL_STATIONS = """
CREATE TABLE IF NOT EXISTS police_stations (
    station_code          INTEGER PRIMARY KEY,
    station_name          TEXT NOT NULL,
    address_clean         TEXT,
    unit                  TEXT,
    dcp_zone              TEXT NOT NULL,
    acp_zone              TEXT NOT NULL,
    latitude              REAL,
    longitude             REAL,
    location_source       TEXT DEFAULT 'pending',
    has_btp_pi            INTEGER DEFAULT 0,
    btp_match_confidence  REAL,
    capacity_officers     INTEGER DEFAULT 25,
    capacity_vehicles     INTEGER DEFAULT 3,
    capacity_source       TEXT DEFAULT 'default',
    phone                 TEXT,
    geocoded_at           TEXT,
    updated_at            TEXT NOT NULL
)
"""

_DDL_CENTROIDS = """
CREATE TABLE IF NOT EXISTS zone_centroids (
    dcp_zone   TEXT PRIMARY KEY,
    latitude   REAL NOT NULL,
    longitude  REAL NOT NULL
)
"""

_NAME_STOPWORDS = {
    "ps", "p.s", "road", "main", "cross", "beedi", "layout",
    "colony", "street", "gate", "circle", "halli", "puram", "nagara",
}


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def _clean_station_field(raw: str) -> tuple[str, str]:
    """Return (station_name, address_clean) from raw Station CSV field."""
    cleaned = re.sub(r"Ph\s*no\..*", "", raw, flags=re.IGNORECASE).strip()
    tokens = cleaned.split()
    name_tokens: list[str] = []
    for t in tokens:
        if not t:
            continue
        if t[0].isdigit() or t[0] in "#@":
            break
        if t.lower().strip(".,") in _NAME_STOPWORDS:
            break
        name_tokens.append(t)
        if len(name_tokens) == 2:
            break
    station_name = " ".join(name_tokens) if name_tokens else (tokens[0] if tokens else "Unknown")
    return station_name, cleaned


def _count_stations() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT COUNT(*) FROM police_stations").fetchone()[0]


def init_station_db() -> None:
    """Create tables and seed from CSV if empty. Idempotent."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(_DDL_STATIONS)
        conn.execute(_DDL_CENTROIDS)
        conn.commit()
    if _count_stations() == 0:
        _seed_from_csv()


def _seed_from_csv() -> None:
    df = pd.read_csv(_CSV_PATH)
    now = _now()
    rows = []
    for _, row in df.iterrows():
        raw = str(row["Station"])
        station_name, address_clean = _clean_station_field(raw)
        phone_m = re.search(r"Ph\s*no\.\s*([\d\s\-,]+)", raw, re.IGNORECASE)
        phone = phone_m.group(1).strip() if phone_m else None
        sc = row["Station Code"]
        station_code = int(sc) if pd.notna(sc) else int(row["Sl"])
        rows.append((
            station_code,
            station_name,
            address_clean,
            str(row["Unit"]) if pd.notna(row["Unit"]) else None,
            str(row["DCP"]),
            str(row["ACP"]),
            None, None,      # latitude, longitude
            "pending",       # location_source
            0, None,         # has_btp_pi, btp_match_confidence
            25, 3,           # capacity_officers, capacity_vehicles
            "default",       # capacity_source
            phone,
            None,            # geocoded_at
            now,             # updated_at
        ))
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO police_stations
               (station_code, station_name, address_clean, unit, dcp_zone, acp_zone,
                latitude, longitude, location_source, has_btp_pi, btp_match_confidence,
                capacity_officers, capacity_vehicles, capacity_source, phone,
                geocoded_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
