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


# ── CRUD ──────────────────────────────────────────────────────────────────────

def save_event(event_data: dict) -> str:
    """Insert a new event. Returns UUID4 event_id. Raises ValueError on duplicate."""
    event_id = str(uuid.uuid4())
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    serialized = dict(event_data)
    for field in ("barricades_json", "diversions_json", "feature_vector_json", "shap_drivers_json"):
        if field in serialized and not isinstance(serialized[field], str):
            serialized[field] = json.dumps(serialized[field])

    row = {
        **{col: None for col in _COLUMNS},
        **serialized,
        "event_id":   event_id,
        "status":     serialized.get("status", "planned"),
        "created_at": now,
        "updated_at": now,
    }

    col_str      = ", ".join(_COLUMNS)
    placeholders = ", ".join(f":{col}" for col in _COLUMNS)

    with sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute(
                f"INSERT INTO planned_events ({col_str}) VALUES ({placeholders})",
                {col: row.get(col) for col in _COLUMNS},
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Duplicate event_id: {event_id}") from exc

    return event_id


def get_event(event_id: str) -> dict | None:
    """Fetch a single event by ID. Returns None if not found."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM planned_events WHERE event_id = ?", (event_id,)
        ).fetchone()
    return dict(row) if row else None


_VALID_STATUSES = frozenset({"planned", "active", "completed", "cancelled"})


def list_events(
    date_from: str | None = None,
    date_to: str | None = None,
    corridor: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """Return filtered events ordered by event_date ASC, event_time ASC."""
    conditions: list[str] = []
    params: dict = {}

    if date_from:
        conditions.append("event_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("event_date <= :date_to")
        params["date_to"] = date_to
    if corridor:
        conditions.append("corridor = :corridor")
        params["corridor"] = corridor
    if event_type:
        conditions.append("event_type = :event_type")
        params["event_type"] = event_type
    if severity:
        conditions.append("severity = :severity")
        params["severity"] = severity
    if status:
        conditions.append("status = :status")
        params["status"] = status

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM planned_events {where} "
            "ORDER BY event_date ASC, event_time ASC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def update_status(event_id: str, status: str) -> None:
    """Update event status. Raises ValueError for unrecognised status values."""
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"Invalid status: {status!r}. Must be one of {sorted(_VALID_STATUSES)}"
        )
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE planned_events SET status = ?, updated_at = ? WHERE event_id = ?",
            (status, now, event_id),
        )


# ── Conflict detection ────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_zone_centroids() -> dict[str, tuple[float, float]]:
    """Read zone centroids from SQLite (populated by station_store geocoding pipeline).
    Returns empty dict if table missing or empty (Phase 1 / pre-geocoding)."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT dcp_zone, latitude, longitude FROM zone_centroids"
            ).fetchall()
        if rows:
            return {r[0]: (r[1], r[2]) for r in rows}
    except Exception:
        pass
    # Return empty dict when zone_centroids not available
    return {}

_TIME_OVERLAP_SQL = """
    AND ABS(
        julianday(:event_date || 'T' || :event_time)
        - julianday(event_date || 'T' || event_time)
    ) * 24 <= 4
    AND status NOT IN ('cancelled', 'completed')
"""


def check_conflicts(event_data: dict) -> tuple[list[dict], str]:
    """
    4-branch conflict detection.
    Returns (conflicting_events, precision_note).
    precision_note is empty string for full-precision results.
    """
    corridor = event_data.get("corridor")
    zone     = event_data.get("zone")
    lat      = event_data.get("latitude")
    lng      = event_data.get("longitude")
    base     = {"event_date": event_data["event_date"], "event_time": event_data["event_time"]}

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        if corridor:
            rows = conn.execute(
                f"SELECT * FROM planned_events WHERE corridor = :corridor {_TIME_OVERLAP_SQL}",
                {**base, "corridor": corridor},
            ).fetchall()
            return [dict(r) for r in rows], ""

        if zone:
            rows = [
                dict(r) for r in conn.execute(
                    f"SELECT * FROM planned_events WHERE zone = :zone {_TIME_OVERLAP_SQL}",
                    {**base, "zone": zone},
                ).fetchall()
            ]
            centroid = _build_zone_centroids().get(zone)
            if centroid is None:
                note = (
                    f"Location precision unavailable for {zone} — "
                    "conflict detection is time-window only"
                )
                return rows, note
            ev_lat = lat if lat is not None else centroid[0]
            ev_lng = lng if lng is not None else centroid[1]
            filtered = [
                r for r in rows
                if _haversine_km(
                    ev_lat, ev_lng,
                    r["latitude"] if r["latitude"] is not None else centroid[0],
                    r["longitude"] if r["longitude"] is not None else centroid[1],
                ) <= 8.0
            ]
            return filtered, ""

        if lat is not None and lng is not None:
            rows = [
                dict(r) for r in conn.execute(
                    f"SELECT * FROM planned_events "
                    f"WHERE latitude IS NOT NULL AND longitude IS NOT NULL {_TIME_OVERLAP_SQL}",
                    base,
                ).fetchall()
            ]
            return [
                r for r in rows
                if _haversine_km(lat, lng, r["latitude"], r["longitude"]) <= 3.0
            ], ""

        logger.warning("conflict check skipped — event has no location data")
        return [], ""
