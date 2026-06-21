# Phase 1: Event Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a SQLite persistence layer plus Event Calendar and Event Repository pages to GRIDLOCK 2.0 so planned events survive app restarts and are visible in calendar and tabular views.

**Architecture:** Option A — thin layer on top of the existing form. The Plan Event form stores extra fields in `st.session_state["save_data"]`; the Results page assembles the full record and writes it to SQLite on demand. Two new Streamlit pages (`4_Event_Calendar.py`, `5_Event_Repository.py`) read from SQLite. The ML training pipeline and `data/events.csv` are untouched.

**Tech Stack:** Python 3.10+, SQLite3 (stdlib), streamlit-calendar ≥ 0.6.0, pandas (already present), pytest (already present).

## Global Constraints

- `data/events.csv` and all ML training code must not be modified.
- All DB interaction goes through `src/event_store.py` only — no other file calls `sqlite3` directly.
- `DB_PATH = Path("data/events.db")` — add to `.gitignore`.
- All timestamps stored as ISO 8601 TEXT strings (`YYYY-MM-DDTHH:MM:SS`).
- `event_id` is UUID4 (36-char string).
- Valid status values: `planned`, `active`, `completed`, `cancelled`.
- `shap_drivers_json` is frozen at save time (audit trail). The UI offers a "Recompute with current model" button separately.
- Zone-centroid lookup is built only from stations where `location_source == "geocoded"`. If a zone has no geocoded stations, Branch 2 drops the distance cap and shows a precision qualifier. In Phase 1, this column does not yet exist in the CSV, so the centroid dict will be empty and Branch 2 will always show the qualifier — this is correct behavior.
- `streamlit-calendar >= 0.6.0` must be added to `requirements.txt`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/event_store.py` | Create | All SQLite: schema, CRUD, conflict check, centroid lookup |
| `src/app_cache.py` | Modify | Call `event_store.init_db()` once at startup |
| `pages/1_Plan_Event.py` | Modify | Store `save_data` dict in session state after prediction |
| `pages/2_Results.py` | Modify | Save button, conflict warning, double-save guard |
| `pages/4_Event_Calendar.py` | Create | Calendar view with month/week/day, detail panel, status actions |
| `pages/5_Event_Repository.py` | Create | Filterable table, row-select detail expander, status actions |
| `tests/test_event_store.py` | Create | All unit tests for event_store |
| `requirements.txt` | Modify | Add `streamlit-calendar>=0.6.0` |
| `.gitignore` | Modify | Add `data/events.db` |

---

## Task 1: DB Schema, `init_db()`, and App Wiring

**Files:**
- Create: `src/event_store.py`
- Modify: `src/app_cache.py`
- Modify: `.gitignore`
- Test: `tests/test_event_store.py`

**Interfaces:**
- Produces: `event_store.init_db() -> None`, `event_store.DB_PATH: Path`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to confirm it fails**

```
pytest tests/test_event_store.py -v
```
Expected: `ModuleNotFoundError` or `AttributeError` — `event_store` does not exist yet.

- [ ] **Step 3: Create `src/event_store.py` with schema and `init_db()`**

```python
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
```

- [ ] **Step 4: Add `event_store.init_db()` call to `src/app_cache.py`**

At the top of `load_and_train()` (before the `if` guard that checks whether training already ran), insert:

```python
from src import event_store as _event_store
_event_store.init_db()
```

- [ ] **Step 5: Add `data/events.db` to `.gitignore`**

Append to `.gitignore`:
```
data/events.db
```

- [ ] **Step 6: Run tests to confirm they pass**

```
pytest tests/test_event_store.py -v
```
Expected: 3 PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/event_store.py src/app_cache.py .gitignore tests/test_event_store.py
git commit -m "feat: add event_store module with SQLite schema and init_db"
```

---

## Task 2: `save_event()` and `get_event()`

**Files:**
- Modify: `src/event_store.py`
- Modify: `tests/test_event_store.py`

**Interfaces:**
- Consumes: `init_db()` from Task 1
- Produces:
  - `save_event(event_data: dict) -> str` — inserts row, returns UUID4 string, raises `ValueError` on duplicate `event_id`
  - `get_event(event_id: str) -> dict | None` — returns row as dict or `None`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_event_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_event_store.py::test_save_event_returns_uuid -v
```
Expected: `AttributeError: module 'src.event_store' has no attribute 'save_event'`

- [ ] **Step 3: Implement `save_event()` and `get_event()` in `src/event_store.py`**

Append after `init_db()`:

```python
def save_event(event_data: dict) -> str:
    """Insert a new event. Returns UUID4 event_id. Raises ValueError on duplicate."""
    event_id = str(uuid.uuid4())
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    # JSON-serialize any dict/list values in known JSON columns
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_event_store.py -v
```
Expected: all tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/event_store.py tests/test_event_store.py
git commit -m "feat: event_store save_event and get_event"
```

---

## Task 3: `list_events()` and `update_status()`

**Files:**
- Modify: `src/event_store.py`
- Modify: `tests/test_event_store.py`

**Interfaces:**
- Produces:
  - `list_events(date_from, date_to, corridor, event_type, severity, status) -> list[dict]`
  - `update_status(event_id: str, status: str) -> None` — raises `ValueError` for invalid status

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_event_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_event_store.py::test_list_events_returns_all_unfiltered -v
```
Expected: `AttributeError: module has no attribute 'list_events'`

- [ ] **Step 3: Implement `list_events()` and `update_status()` in `src/event_store.py`**

Append after `get_event()`:

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_event_store.py -v
```
Expected: all tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/event_store.py tests/test_event_store.py
git commit -m "feat: event_store list_events and update_status"
```

---

## Task 4: `check_conflicts()` — 4-Branch Conflict Detection

**Files:**
- Modify: `src/event_store.py`
- Modify: `tests/test_event_store.py`

**Interfaces:**
- Produces: `check_conflicts(event_data: dict) -> tuple[list[dict], str]`
  - Returns `(conflicts, precision_note)`. `conflicts` is a list of conflicting event dicts (empty = no conflicts). `precision_note` is `""` for full-precision checks or a human-readable qualifier for degraded branches.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_event_store.py`:

```python
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
        _make_event(event_date="2026-07-01", event_time="18:00")  # 10h apart
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
    event_store.init_db()
    monkeypatch.setattr(event_store, "_ZONE_CENTROIDS", {})
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
    event_store.init_db()
    monkeypatch.setattr(
        event_store, "_ZONE_CENTROIDS",
        {"Central Division, Bangalore City": (12.975, 77.607)},
    )
    # Existing event ~14km south — outside 8km cap
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
        latitude=12.975, longitude=77.607,
        event_date="2026-07-01", event_time="14:30",
    ))
    # ~1km north — within 3km cap
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
        latitude=12.975, longitude=77.607,
        event_date="2026-07-01", event_time="14:30",
    ))
    # ~8km away — outside 3km cap
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_event_store.py::test_conflict_branch1_corridor_match -v
```
Expected: `AttributeError: module has no attribute 'check_conflicts'`

- [ ] **Step 3: Implement `_haversine_km`, `_build_zone_centroids`, and `check_conflicts` in `src/event_store.py`**

Append after `update_status()`:

```python
def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_zone_centroids() -> dict[str, tuple[float, float]]:
    """Build zone centroid lookup from geocoded police stations only."""
    csv_path = Path("bangalore_city_police_stations_2012.csv")
    if not csv_path.exists():
        return {}
    try:
        df = pd.read_csv(csv_path)
        required = {"location_source", "latitude", "longitude", "DCP"}
        if not required.issubset(df.columns):
            return {}
        geocoded = df[df["location_source"] == "geocoded"].dropna(
            subset=["latitude", "longitude"]
        )
        if geocoded.empty:
            return {}
        return {
            division: (grp["latitude"].mean(), grp["longitude"].mean())
            for division, grp in geocoded.groupby("DCP")
        }
    except Exception:
        logger.warning("Failed to build zone centroids from police station CSV")
        return {}


_ZONE_CENTROIDS: dict[str, tuple[float, float]] = _build_zone_centroids()

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
            centroid = _ZONE_CENTROIDS.get(zone)
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
```

- [ ] **Step 4: Run all event_store tests**

```
pytest tests/test_event_store.py -v
```
Expected: all tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/event_store.py tests/test_event_store.py
git commit -m "feat: event_store conflict detection with 4-branch logic and zone centroid"
```

---

## Task 5: Store `save_data` in Session State (`pages/1_Plan_Event.py`)

**Files:**
- Modify: `pages/1_Plan_Event.py`

**Interfaces:**
- Produces: `st.session_state["save_data"]` dict with all fields needed by `save_event()`

- [ ] **Step 1: Locate the insertion point in `pages/1_Plan_Event.py`**

Find the block starting at line 186:
```python
    st.session_state["result_data"] = {
```

- [ ] **Step 2: Add `save_data` assignment immediately before `st.switch_page`**

After the closing `}` of `st.session_state["result_data"] = {...}` and before `st.switch_page(...)`, insert:

```python
    st.session_state["save_data"] = {
        "event_name":            event_name,
        "event_type":            event_type,
        "event_cause":           event_cause,
        "corridor":              corridor,
        "zone":                  zone,
        "police_station":        police,
        "junction":              "unknown",
        "event_date":            event_date.isoformat(),
        "event_time":            event_time.strftime("%H:%M"),
        "estimated_attendance":  int(estimated_attendance),
        "has_vip":               has_vip,
        "is_route_event":        is_route_event,
        "requires_road_closure": int(road_closure),
        "latitude":              lat,
        "longitude":             lng,
        "holiday_name":          holiday_name_input,
        "holiday_risk_tier":     holiday_risk_tier,
        "priority":              priority,
        "feature_vector_json":   features,   # Python dict — save_event serializes it
    }
```

The variables `zone`, `police`, `lat`, `lng` are already in scope from the `corridor_metadata()` call at line 139. `event_type`, `event_cause`, `corridor`, `priority`, `event_date`, `event_time`, `road_closure`, `estimated_attendance`, `has_vip`, `is_route_event`, `holiday_name_input`, `holiday_risk_tier`, and `features` are all in scope from the form block.

- [ ] **Step 3: Manual smoke test**

Start the app: `streamlit run app.py`
- Fill in the Event form and click "Predict Impact".
- On the Results page, open browser devtools → Application → Session Storage (or add `st.write(st.session_state.get("save_data"))` temporarily to 2_Results.py).
- Confirm `save_data` contains `event_date`, `event_type`, `corridor`, `latitude`, `feature_vector_json` dict.

- [ ] **Step 4: Commit**

```bash
git add pages/1_Plan_Event.py
git commit -m "feat: store save_data in session state for SQLite persistence"
```

---

## Task 6: Save Button and Conflict Warning (`pages/2_Results.py`)

**Files:**
- Modify: `pages/2_Results.py`

**Interfaces:**
- Consumes: `st.session_state["save_data"]` (Task 5), `st.session_state["result_data"]` (existing), `event_store.check_conflicts()`, `event_store.save_event()` (Tasks 1–4)

- [ ] **Step 1: Add imports at the top of `pages/2_Results.py`**

Add after the existing imports:
```python
import json
from src import event_store
```

- [ ] **Step 2: Add `_build_save_record()` helper function**

Insert before `st.set_page_config(...)`:

```python
def _build_save_record(sd: dict, r: dict) -> dict:
    """Merge form inputs (sd) with prediction outputs (r) into a save_event-ready dict."""
    risks    = r["risks"]
    officers = r["officers"]
    return {
        **sd,
        "severity":          r["severity"],
        "severity_conf":     r["confidence"].get(r["severity"], 0.0),
        "congestion_prob":   risks["congestion_prob"],
        "law_order_prob":    risks["law_order_prob"],
        "duration_label":    r.get("duration"),
        "officer_min":       officers["total_min"],
        "officer_max":       officers["total_max"],
        "barricades_json":   json.dumps(r["barricades"]),
        "diversions_json":   json.dumps(r["diversions"]),
        "shap_drivers_json": json.dumps(r["shap_severity"]),
    }
```

- [ ] **Step 3: Add save section at the bottom of `pages/2_Results.py`**

After the final `st.page_link("pages/3_Post_Event_Report.py", ...)` line, append:

```python
# ── Save to Event Calendar ────────────────────────────────────────────────────
st.markdown("---")
if "save_data" not in st.session_state:
    st.info("Return to the form and resubmit to enable saving this event.")
else:
    sd = st.session_state["save_data"]
    conflicts, note = event_store.check_conflicts(sd)

    show_save = False
    if conflicts:
        warn_msg = f"⚠ {len(conflicts)} event(s) already planned on the same corridor within 4 hours."
        if note:
            warn_msg += f"  \n_{note}_"
        st.warning(warn_msg)
        c1, c2 = st.columns(2)
        if c1.button("Save anyway"):
            show_save = True
        if c2.button("Review conflicts"):
            st.switch_page("pages/5_Event_Repository.py")
    else:
        show_save = True

    if show_save:
        if "event_saved_id" not in st.session_state:
            if st.button("💾 Save to Event Calendar"):
                record = _build_save_record(sd, r)
                eid = event_store.save_event(record)
                st.session_state["event_saved_id"] = eid
                st.success(f"Event saved — ID {eid[:8]}…")
        else:
            st.button("✓ Saved", disabled=True)
```

- [ ] **Step 4: Manual smoke test**

```
streamlit run app.py
```
1. Submit a planned event form → Results page loads.
2. Scroll to bottom — "💾 Save to Event Calendar" button appears.
3. Click it — success message with short UUID appears; button changes to "✓ Saved".
4. Reload the Results page — button still shows "✓ Saved" (session state persisted).
5. Submit the same event a second time, click save again — a **new** event is saved (each submission generates a new UUID), button shows "✓ Saved" again.
6. Open `data/events.db` with any SQLite viewer and confirm a row exists with correct fields.

- [ ] **Step 5: Commit**

```bash
git add pages/2_Results.py
git commit -m "feat: save button and conflict warning on Results page"
```

---

## Task 7: Event Calendar Page (`pages/4_Event_Calendar.py`)

**Files:**
- Create: `pages/4_Event_Calendar.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `event_store.list_events()`, `event_store.get_event()`, `event_store.update_status()`, `explain_severity()` (for recompute)

- [ ] **Step 1: Add `streamlit-calendar` to `requirements.txt`**

Append:
```
streamlit-calendar>=0.6.0
```

Install it: `pip install streamlit-calendar`

- [ ] **Step 2: Create `pages/4_Event_Calendar.py`**

```python
# pages/4_Event_Calendar.py
import json
from datetime import datetime, timedelta

import streamlit as st
from streamlit_calendar import calendar as st_calendar

from src import event_store
from src.app_cache import load_and_train
from src.explainer import explain_severity

st.set_page_config(page_title="Event Calendar", layout="wide")
st.title("Event Calendar")

_SEVERITY_COLOR = {
    "HIGH":   "#dc3545",
    "MEDIUM": "#fd7e14",
    "LOW":    "#28a745",
}


def _color(severity: str | None) -> str:
    return _SEVERITY_COLOR.get(severity or "", "#6c757d")


def _end_iso(event_date: str, event_time: str, duration_h: float | None) -> str:
    h = duration_h if duration_h else 2.0
    dt = datetime.fromisoformat(f"{event_date}T{event_time}:00")
    return (dt + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")


events_list = event_store.list_events()

cal_events = [
    {
        "title": e["event_name"],
        "start": f"{e['event_date']}T{e['event_time']}:00",
        "end":   _end_iso(e["event_date"], e["event_time"], e.get("expected_duration_h")),
        "color": _color(e.get("severity")),
        "id":    e["event_id"],
    }
    for e in events_list
]

calendar_options = {
    "headerToolbar": {
        "left":   "prev,next today",
        "center": "title",
        "right":  "dayGridMonth,timeGridWeek,timeGridDay",
    },
    "initialView": "dayGridMonth",
}

cal_result = st_calendar(events=cal_events, options=calendar_options, key="main_cal")

# ── Legend ────────────────────────────────────────────────────────────────────
st.caption(
    "🔴 HIGH &nbsp;&nbsp; 🟠 MEDIUM &nbsp;&nbsp; 🟢 LOW &nbsp;&nbsp; ⚫ Unpredicted"
)

# ── Detail panel on click ─────────────────────────────────────────────────────
if cal_result and cal_result.get("eventClick"):
    clicked_id = cal_result["eventClick"]["event"]["id"]
    ev = event_store.get_event(clicked_id)
    if ev:
        st.markdown("---")
        st.subheader(ev["event_name"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Severity",  ev.get("severity") or "—")
        c2.metric("Corridor",  ev.get("corridor") or "—")
        c3.metric("Date/Time", f"{ev['event_date']} {ev['event_time']}")
        c4.metric("Status",    ev["status"])

        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown(f"**Officers:** {ev.get('officer_min')}–{ev.get('officer_max')}")
            if ev.get("congestion_prob") is not None:
                st.markdown(f"**Congestion risk:** {ev['congestion_prob']*100:.0f}%")
            if ev.get("law_order_prob") is not None:
                st.markdown(f"**Law & order risk:** {ev['law_order_prob']*100:.0f}%")
        with col_r:
            st.markdown(f"**Duration:** {ev.get('duration_label') or '—'}")
            if ev.get("barricades_json"):
                barricades = json.loads(ev["barricades_json"])
                st.markdown(f"**Barricades:** {', '.join(barricades) or '—'}")

        # Frozen SHAP explanation
        if ev.get("shap_drivers_json"):
            drivers = json.loads(ev["shap_drivers_json"])
            st.markdown(f"**Why {ev.get('severity')}?** _(explanation frozen at save time)_")
            for d in drivers:
                arrow = "▲" if d["direction"] == "+" else "▼"
                st.markdown(f"{arrow} **{d['direction']}{d['pct']}%** &nbsp; {d['display']}")

        # Live recompute
        if ev.get("feature_vector_json") and st.button("Recompute with current model"):
            state = load_and_train()
            fv = json.loads(ev["feature_vector_json"]) \
                if isinstance(ev["feature_vector_json"], str) \
                else ev["feature_vector_json"]
            live = explain_severity(
                state["explainers"]["severity"],
                state["pipeline"],
                fv,
                ev.get("severity", "LOW"),
            )
            st.markdown("**Live explanation (current model):**")
            for d in live:
                arrow = "▲" if d["direction"] == "+" else "▼"
                st.markdown(f"{arrow} **{d['direction']}{d['pct']}%** &nbsp; {d['display']}")

        # Status actions
        st.markdown("---")
        sa, sb, sc = st.columns(3)
        if ev["status"] == "planned" and sa.button("Mark Active"):
            event_store.update_status(clicked_id, "active")
            st.rerun()
        if ev["status"] in ("planned", "active") and sb.button("Mark Completed"):
            event_store.update_status(clicked_id, "completed")
            st.rerun()
        if ev["status"] not in ("cancelled", "completed") and sc.button("Cancel Event"):
            event_store.update_status(clicked_id, "cancelled")
            st.rerun()
```

- [ ] **Step 3: Manual smoke test**

```
streamlit run app.py
```
1. Navigate to "Event Calendar" in the sidebar.
2. Confirm the calendar renders in month view with navigation arrows.
3. Save a predicted event from the form flow, return to calendar — event appears color-coded.
4. Click the event — detail panel appears with severity, officers, and frozen SHAP.
5. Switch to Week and Day views — event appears in correct time slot.
6. Click "Mark Active" — event status updates and calendar reflects it on rerun.

- [ ] **Step 4: Commit**

```bash
git add pages/4_Event_Calendar.py requirements.txt
git commit -m "feat: Event Calendar page with month/week/day views and detail panel"
```

---

## Task 8: Event Repository Page (`pages/5_Event_Repository.py`)

**Files:**
- Create: `pages/5_Event_Repository.py`

**Interfaces:**
- Consumes: `event_store.list_events()`, `event_store.update_status()`, `explain_severity()` (for recompute)

- [ ] **Step 1: Create `pages/5_Event_Repository.py`**

```python
# pages/5_Event_Repository.py
import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src import event_store
from src.app_cache import load_and_train
from src.explainer import explain_severity

st.set_page_config(page_title="Event Repository", layout="wide")
st.title("Event Repository")

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filters")
    today = date.today()
    date_range = st.date_input(
        "Date range",
        value=(today - timedelta(days=30), today + timedelta(days=90)),
    )
    date_from = date_range[0].isoformat() if len(date_range) > 0 else None
    date_to   = date_range[1].isoformat() if len(date_range) > 1 else None

    all_corridors = sorted({
        e["corridor"] for e in event_store.list_events()
        if e.get("corridor")
    })
    sel_corridors = st.multiselect("Corridor", all_corridors)
    sel_type      = st.selectbox("Event type", ["All", "planned", "unplanned"])
    sel_severity  = st.multiselect("Risk level", ["HIGH", "MEDIUM", "LOW"])
    sel_status    = st.multiselect(
        "Status",
        ["planned", "active", "completed", "cancelled"],
        default=["planned", "active"],
    )

# ── Fetch and filter ──────────────────────────────────────────────────────────
events = event_store.list_events(
    date_from=date_from,
    date_to=date_to,
    event_type=sel_type if sel_type != "All" else None,
)
if sel_corridors:
    events = [e for e in events if e.get("corridor") in sel_corridors]
if sel_severity:
    events = [e for e in events if e.get("severity") in sel_severity]
if sel_status:
    events = [e for e in events if e.get("status") in sel_status]

if not events:
    st.info("No events match the current filters.")
    st.stop()

# ── Table ─────────────────────────────────────────────────────────────────────
def _pct(val: float | None) -> str:
    return f"{val*100:.0f}%" if val is not None else "—"


display_df = pd.DataFrame([
    {
        "ID":         e["event_id"][:8],
        "Name":       e["event_name"],
        "Type":       e["event_type"],
        "Cause":      e["event_cause"],
        "Corridor":   e.get("corridor") or "—",
        "Date":       e["event_date"],
        "Time":       e["event_time"],
        "Severity":   e.get("severity") or "—",
        "Congestion": _pct(e.get("congestion_prob")),
        "L&O Risk":   _pct(e.get("law_order_prob")),
        "Status":     e["status"],
    }
    for e in events
])

selection = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ── Detail expander on row select ─────────────────────────────────────────────
sel_rows = selection["selection"]["rows"] if selection else []
if sel_rows:
    ev = events[sel_rows[0]]
    with st.expander(f"📋 {ev['event_name']} — Full Detail", expanded=True):
        d1, d2, d3 = st.columns(3)
        d1.metric("Severity",  ev.get("severity") or "—")
        d2.metric("Officers",  f"{ev.get('officer_min')}–{ev.get('officer_max')}"
                               if ev.get("officer_min") else "—")
        d3.metric("Duration",  ev.get("duration_label") or "—")

        e1, e2 = st.columns(2)
        with e1:
            if ev.get("congestion_prob") is not None:
                st.markdown(f"**Congestion risk:** {ev['congestion_prob']*100:.0f}%")
            if ev.get("barricades_json"):
                st.markdown(
                    f"**Barricades:** {', '.join(json.loads(ev['barricades_json']))}"
                )
        with e2:
            if ev.get("law_order_prob") is not None:
                st.markdown(f"**Law & order risk:** {ev['law_order_prob']*100:.0f}%")
            if ev.get("diversions_json"):
                st.markdown(
                    f"**Diversions:** {', '.join(json.loads(ev['diversions_json']))}"
                )

        # Frozen SHAP
        if ev.get("shap_drivers_json"):
            drivers = json.loads(ev["shap_drivers_json"])
            st.markdown(
                f"**Why {ev.get('severity')}?** _(frozen at save time)_"
            )
            for d in drivers:
                arrow = "▲" if d["direction"] == "+" else "▼"
                st.markdown(
                    f"{arrow} **{d['direction']}{d['pct']}%** &nbsp; {d['display']}"
                )

        # Live recompute
        if ev.get("feature_vector_json") and st.button(
            "Recompute with current model", key="repo_recompute"
        ):
            state = load_and_train()
            fv = (
                json.loads(ev["feature_vector_json"])
                if isinstance(ev["feature_vector_json"], str)
                else ev["feature_vector_json"]
            )
            live = explain_severity(
                state["explainers"]["severity"],
                state["pipeline"],
                fv,
                ev.get("severity", "LOW"),
            )
            st.markdown("**Live explanation (current model):**")
            for d in live:
                arrow = "▲" if d["direction"] == "+" else "▼"
                st.markdown(
                    f"{arrow} **{d['direction']}{d['pct']}%** &nbsp; {d['display']}"
                )

        # Status actions
        st.markdown("---")
        sa, sb, sc = st.columns(3)
        if ev["status"] == "planned" and sa.button("Mark Active", key="repo_active"):
            event_store.update_status(ev["event_id"], "active")
            st.rerun()
        if ev["status"] in ("planned", "active") and sb.button(
            "Mark Completed", key="repo_complete"
        ):
            event_store.update_status(ev["event_id"], "completed")
            st.rerun()
        if ev["status"] not in ("cancelled", "completed") and sc.button(
            "Cancel Event", key="repo_cancel"
        ):
            event_store.update_status(ev["event_id"], "cancelled")
            st.rerun()
```

- [ ] **Step 2: Manual smoke test**

```
streamlit run app.py
```
1. Navigate to "Event Repository".
2. Confirm the table appears with filters in the sidebar.
3. Apply a corridor filter — table narrows correctly.
4. Click a table row — detail expander opens with severity, officers, SHAP.
5. Click "Mark Completed" — status updates and table row reflects the change.
6. Apply "Status = completed" filter — the completed event now appears.
7. Test "Review conflicts" link from Results page navigates here without crashing.

- [ ] **Step 3: Run full test suite to confirm nothing regressed**

```
pytest tests/ -v
```
Expected: all previously passing tests still PASS; new `test_event_store.py` tests all PASS.

- [ ] **Step 4: Commit**

```bash
git add pages/5_Event_Repository.py
git commit -m "feat: Event Repository page with filters, row-select detail, and status actions"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| SQLite schema with all columns incl. `feature_vector_json`, `shap_drivers_json` | Task 1 |
| `init_db()` called at app startup via `app_cache.py` | Task 1 |
| `save_event()` + `get_event()` + JSON serialization | Task 2 |
| `list_events()` with all 5 filter dimensions | Task 3 |
| `update_status()` with validation | Task 3 |
| 4-branch conflict check | Task 4 |
| Zone centroid from geocoded-only stations | Task 4 |
| Distance cap dropped + qualifier when centroid absent | Task 4 |
| Branch 4 logs warning, returns empty | Task 4 |
| `save_data` stored in session state by Plan Event form | Task 5 |
| Save button on Results page | Task 6 |
| Frozen SHAP assembled at save time | Task 6 |
| Conflict warning with "Save anyway" / "Review conflicts" | Task 6 |
| Double-save guard | Task 6 |
| Calendar page month/week/day views | Task 7 |
| Color-coded events by severity | Task 7 |
| Calendar detail panel with frozen SHAP + recompute | Task 7 |
| Status actions on calendar | Task 7 |
| `streamlit-calendar` in requirements.txt | Task 7 |
| Repository filterable table | Task 8 |
| Row-select detail expander | Task 8 |
| Frozen SHAP + recompute in repository | Task 8 |
| Status actions in repository | Task 8 |
| `data/events.db` in `.gitignore` | Task 1 |

**All spec requirements covered. No placeholders. Type signatures are consistent across tasks.**

**One known simplification vs. spec:** The "Review conflicts" button navigates to the Repository page without pre-filtering by corridor+date (the spec mentioned query params). The operator can apply filters manually. This avoids Streamlit query-param complexity that adds no functional value in Phase 1.
