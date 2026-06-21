# Phase 2: Station Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Geocode 110 Bengaluru police stations, rank them by distance/workload/BTP signal for any planned event, and generate a full AI-assisted deployment plan with narrative briefing.

**Architecture:** A new `src/station_store.py` owns all station SQLite I/O (two new tables: `police_stations`, `zone_centroids`), geocoding via Nominatim, BTP enrichment, ranking, allocation, and capacity updates. A new `src/deployment_planner.py` assembles the structured deployment plan dict and rule-based narrative paragraph. Two new Streamlit pages expose these to operators; the existing Results page gains a compact top-3 station summary.

**Tech Stack:** Python 3.13, SQLite (via stdlib `sqlite3`), `geopy>=2.4.0` (Nominatim + RateLimiter), `difflib` (stdlib, BTP fuzzy matching), `requests` (already present), Streamlit, Folium, pandas, pytest.

## Global Constraints

- `geopy>=2.4.0` is the only new dependency — add to `requirements.txt`
- Nominatim user-agent must be `"gridlock2-geocoder"` (usage policy compliance)
- Nominatim rate limit: 1 request/second via `RateLimiter(min_delay_seconds=1)`
- `has_btp_pi = 0` means "not confirmed in BTP CSV" — never display as "No BTP PI assigned"
- `capacity_source = 'default'` stations: allocation cap NEVER applied; `capacity_unconfirmed = True` always set
- `capacity_source = 'manual'` stations: allocation cap applied; both `allocation_capped` and `capacity_unconfirmed` always set (never missing keys)
- Zone centroids computed from `location_source = 'geocoded'` stations only
- `rank_stations()` returns `[]` (not exception) when fewer than 2 stations are geocoded
- DB file: `data/events.db` (same file as Phase 1 `planned_events` table)
- BTP CSV URL constant: `_BTP_CSV_URL` in `src/station_store.py`
- All timestamps: `datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `src/station_store.py` | Tables DDL, CSV seeding, address cleaning, geocoding, BTP enrichment, ranking, allocation, capacity update, get_all_stations |
| Create | `src/deployment_planner.py` | build_deployment_plan(), _build_briefing(), _attendance_band() |
| Create | `pages/6_Station_Registry.py` | Admin UI: map tab, stations table tab, geocoding tab |
| Create | `pages/7_Deployment_Plan.py` | Full deployment plan page |
| Modify | `pages/2_Results.py` | Add compact top-3 station summary + page_link |
| Modify | `src/event_store.py` | _build_zone_centroids() reads SQLite first; check_conflicts() calls it fresh |
| Modify | `src/app_cache.py` | Call init_station_db() alongside init_db() |
| Modify | `requirements.txt` | Add geopy>=2.4.0 |
| Create | `tests/test_station_store.py` | 18 unit tests |
| Create | `tests/test_deployment_planner.py` | 11 unit tests |

---

### Task 1: station_store Foundation — Tables, CSV Seeding, Address Cleaning

**Files:**
- Create: `src/station_store.py`
- Modify: `requirements.txt`
- Modify: `src/app_cache.py`
- Test: `tests/test_station_store.py`

**Interfaces:**
- Produces:
  - `init_station_db() -> None`
  - `_count_stations() -> int`
  - `_clean_station_field(raw: str) -> tuple[str, str]` — returns `(station_name, address_clean)`
  - `_now() -> str` — UTC ISO timestamp string
  - `_seed_from_csv() -> None`

- [ ] **Step 1: Add geopy to requirements.txt**

Open `requirements.txt` and append:
```
geopy>=2.4.0
```

Run: `pip install geopy`
Expected: installs without error.

- [ ] **Step 2: Write failing tests**

Create `tests/test_station_store.py`:

```python
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
```

Run: `pytest tests/test_station_store.py -v`
Expected: 5 failures (ImportError — module doesn't exist yet).

- [ ] **Step 3: Create src/station_store.py with foundation**

```python
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
        rows.append((
            int(row["Station Code"]),
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
```

- [ ] **Step 4: Wire init_station_db into app_cache.py**

In `src/app_cache.py`, inside `load_and_train()`, after the existing `_event_store.init_db()` line add:

```python
    from src import station_store as _station_store
    _station_store.init_station_db()
```

The relevant block becomes:
```python
def load_and_train() -> dict:
    from src import event_store as _event_store
    _event_store.init_db()
    from src import station_store as _station_store
    _station_store.init_station_db()
    df = load_raw()
    ...
```

- [ ] **Step 5: Run tests — expect all 5 to pass**

Run: `pytest tests/test_station_store.py -v`
Expected: 5 passed.

- [ ] **Step 6: Run full suite to confirm no regressions**

Run: `pytest --tb=short -q`
Expected: 92 passed (existing) + 5 new = 97 passed.

- [ ] **Step 7: Commit**

```bash
git add src/station_store.py tests/test_station_store.py src/app_cache.py requirements.txt
git commit -m "feat: station_store foundation — tables, CSV seeding, address cleaning"
```

---

### Task 2: Geocoding Pipeline + BTP Enrichment + Zone Centroids

**Files:**
- Modify: `src/station_store.py` — add geocode_all_stations, _enrich_btp_from_df, _enrich_btp, _compute_and_store_zone_centroids, reset_station_geocode, get_geocode_summary
- Modify: `src/event_store.py` — update _build_zone_centroids to read SQLite first; make check_conflicts call it fresh
- Test: `tests/test_station_store.py` — add 6 tests

**Interfaces:**
- Consumes: `init_station_db()`, `_now()`, `DB_PATH` from Task 1
- Produces:
  - `geocode_all_stations(progress_callback=None, _geocoder=None) -> dict` — returns `{"geocoded": n, "fallback": n, "pending": n}`
  - `_enrich_btp_from_df(btp_df: pd.DataFrame) -> None`
  - `_compute_and_store_zone_centroids() -> None`
  - `reset_station_geocode(station_code: int) -> None`
  - `get_geocode_summary() -> dict` — `{"geocoded": n, "fallback": n, "pending": n, "total": n}`

- [ ] **Step 1: Write failing tests (append to tests/test_station_store.py)**

```python
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
```

Run: `pytest tests/test_station_store.py::test_geocode_skips_non_pending -v`
Expected: FAIL with AttributeError (geocode_all_stations not defined).

- [ ] **Step 2: Add geocoding + BTP functions to src/station_store.py**

Append to `src/station_store.py`:

```python
import difflib
import logging
import math

import requests

logger = logging.getLogger(__name__)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode_all_stations(
    progress_callback=None,
    _geocoder=None,
) -> dict:
    """
    Geocode all pending stations via Nominatim, then apply zone centroid fallback,
    then enrich BTP flags. Returns summary dict.
    _geocoder: callable(query) -> location|None — injectable for testing.
    """
    if _geocoder is None:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
        nom = Nominatim(user_agent="gridlock2-geocoder")
        _geocoder = RateLimiter(nom.geocode, min_delay_seconds=1)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        pending = conn.execute(
            "SELECT station_code, station_name, address_clean FROM police_stations "
            "WHERE location_source = 'pending'"
        ).fetchall()

    total = len(pending)
    geocoded_count = 0

    for i, row in enumerate(pending):
        query = f"{row['address_clean']}, Bangalore, India"
        loc = _geocoder(query)
        now = _now()
        if loc is not None:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "UPDATE police_stations SET latitude=?, longitude=?, "
                    "location_source='geocoded', geocoded_at=?, updated_at=? "
                    "WHERE station_code=?",
                    (loc.latitude, loc.longitude, now, now, row["station_code"]),
                )
                conn.commit()
            geocoded_count += 1
        if progress_callback:
            progress_callback(i + 1, total)

    _apply_zone_centroid_fallback()
    _compute_and_store_zone_centroids()
    _enrich_btp()

    return get_geocode_summary()


def _apply_zone_centroid_fallback() -> None:
    """Set zone centroid lat/lng for stations that failed geocoding."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        geocoded = conn.execute(
            "SELECT dcp_zone, latitude, longitude FROM police_stations "
            "WHERE location_source = 'geocoded'"
        ).fetchall()

    # Build centroid map from geocoded-only rows
    zone_lats: dict[str, list[float]] = {}
    zone_lngs: dict[str, list[float]] = {}
    for row in geocoded:
        zone_lats.setdefault(row["dcp_zone"], []).append(row["latitude"])
        zone_lngs.setdefault(row["dcp_zone"], []).append(row["longitude"])

    centroids = {
        z: (sum(zone_lats[z]) / len(zone_lats[z]),
            sum(zone_lngs[z]) / len(zone_lngs[z]))
        for z in zone_lats
    }

    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        pending = conn.execute(
            "SELECT station_code, dcp_zone FROM police_stations "
            "WHERE location_source = 'pending'"
        ).fetchall()
        for row in pending:
            c = centroids.get(row["dcp_zone"])
            if c:
                conn.execute(
                    "UPDATE police_stations SET latitude=?, longitude=?, "
                    "location_source='zone_centroid_fallback', updated_at=? "
                    "WHERE station_code=?",
                    (c[0], c[1], now, row["station_code"]),
                )
        conn.commit()


def _compute_and_store_zone_centroids() -> None:
    """Persist DCP zone centroids from geocoded-only stations to zone_centroids table."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT dcp_zone, latitude, longitude FROM police_stations "
            "WHERE location_source = 'geocoded'"
        ).fetchall()

    zone_lats: dict[str, list[float]] = {}
    zone_lngs: dict[str, list[float]] = {}
    for row in rows:
        zone_lats.setdefault(row["dcp_zone"], []).append(row["latitude"])
        zone_lngs.setdefault(row["dcp_zone"], []).append(row["longitude"])

    with sqlite3.connect(DB_PATH) as conn:
        for zone, lats in zone_lats.items():
            lat = sum(lats) / len(lats)
            lng = sum(zone_lngs[zone]) / len(zone_lngs[zone])
            conn.execute(
                "INSERT OR REPLACE INTO zone_centroids (dcp_zone, latitude, longitude) "
                "VALUES (?, ?, ?)",
                (zone, lat, lng),
            )
        conn.commit()


def _enrich_btp_from_df(btp_df: pd.DataFrame) -> None:
    """Enrich police_stations with BTP PI flags from a loaded BTP DataFrame."""
    pi_rows = btp_df[btp_df["Officer"].str.strip() == "Police Inspector Traffic"]

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        stations = conn.execute(
            "SELECT station_code, station_name FROM police_stations"
        ).fetchall()

    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        for station in stations:
            sname = station["station_name"].lower().strip()
            best_score = 0.0
            for _, brow in pi_rows.iterrows():
                bname = str(brow["Traffic Police Station"]).lower().strip()
                # Remove common suffixes for matching
                bname_clean = re.sub(
                    r"\b(police\s+station|ps|p\.s\.?)\b", "", bname
                ).strip()
                ratio = difflib.SequenceMatcher(None, sname, bname_clean).ratio()
                if ratio > best_score:
                    best_score = ratio

            if best_score == 1.0:
                conn.execute(
                    "UPDATE police_stations SET has_btp_pi=1, btp_match_confidence=1.0, "
                    "updated_at=? WHERE station_code=?",
                    (now, station["station_code"]),
                )
            elif best_score >= 0.7:
                conn.execute(
                    "UPDATE police_stations SET has_btp_pi=1, btp_match_confidence=?, "
                    "updated_at=? WHERE station_code=?",
                    (round(best_score, 3), now, station["station_code"]),
                )
        conn.commit()


def _enrich_btp() -> None:
    """Download BTP CSV and enrich stations. Logs warning on download failure."""
    try:
        resp = requests.get(_BTP_CSV_URL, timeout=10)
        resp.raise_for_status()
        import io
        btp_df = pd.read_csv(io.StringIO(resp.text))
        _enrich_btp_from_df(btp_df)
    except Exception as exc:
        logger.warning("BTP data unavailable — traffic PI flags not set: %s", exc)


def reset_station_geocode(station_code: int) -> None:
    """Reset a station to pending so it can be re-geocoded."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE police_stations SET location_source='pending', latitude=NULL, "
            "longitude=NULL, geocoded_at=NULL, updated_at=? WHERE station_code=?",
            (_now(), station_code),
        )
        conn.commit()


def get_geocode_summary() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT location_source, COUNT(*) FROM police_stations GROUP BY location_source"
        ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    return {
        "geocoded": counts.get("geocoded", 0),
        "fallback": counts.get("zone_centroid_fallback", 0),
        "pending":  counts.get("pending", 0),
        "total":    sum(counts.values()),
    }
```

- [ ] **Step 3: Update src/event_store.py — read zone centroids from SQLite**

In `src/event_store.py`, replace the `_build_zone_centroids` function (lines 195–216) with:

```python
def _build_zone_centroids() -> dict[str, tuple[float, float]]:
    """Read zone centroids from SQLite (populated by station_store geocoding pipeline).
    Falls back to empty dict when table missing or empty (Phase 1 / pre-geocoding)."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT dcp_zone, latitude, longitude FROM zone_centroids"
            ).fetchall()
        if rows:
            return {r[0]: (r[1], r[2]) for r in rows}
    except Exception:
        pass
    return {}
```

Also in `src/event_store.py`, in `check_conflicts()`, replace the line:
```python
centroid = _ZONE_CENTROIDS.get(zone)
```
with:
```python
centroid = _build_zone_centroids().get(zone)
```

This ensures zone centroids are always fresh after geocoding without requiring an app restart. The module-level `_ZONE_CENTROIDS` line (line 219) can remain for backward compatibility but `check_conflicts` no longer reads it.

- [ ] **Step 4: Run the 6 new geocoding/BTP tests**

Run: `pytest tests/test_station_store.py -v -k "geocode or btp or centroid"`
Expected: 6 passed.

- [ ] **Step 5: Run full suite**

Run: `pytest --tb=short -q`
Expected: 103 passed (97 + 6 new).

- [ ] **Step 6: Commit**

```bash
git add src/station_store.py src/event_store.py tests/test_station_store.py
git commit -m "feat: geocoding pipeline, BTP enrichment, zone centroid persistence"
```

---

### Task 3: Ranking Engine + Officer Allocation + Capacity Update

**Files:**
- Modify: `src/station_store.py` — add rank_stations, allocate_officers, update_station_capacity, get_all_stations
- Test: `tests/test_station_store.py` — add 8 tests

**Interfaces:**
- Consumes: `_haversine_km`, `_now`, `DB_PATH` from Tasks 1–2
- Produces:
  - `rank_stations(event_lat, event_lng, event_date, event_time, top_n=5) -> list[dict]`
  - `allocate_officers(stations: list[dict], total_officers: int) -> list[dict]`
  - `update_station_capacity(station_code: int, officers: int, vehicles: int) -> None`
  - `get_all_stations() -> list[dict]`

Each station dict in rank_stations output contains exactly these keys:
`station_name, station_code, dcp_zone, acp_zone, distance_km, workload, has_btp_pi,
btp_match_confidence, capacity_officers, capacity_vehicles, capacity_source, score,
response_min, officers_allocated, allocation_capped, capacity_unconfirmed`

- [ ] **Step 1: Write failing tests (append to tests/test_station_store.py)**

```python
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
```

Run: `pytest tests/test_station_store.py -v -k "rank or allocate or capacity"`
Expected: 8 failures (rank_stations not defined yet).

- [ ] **Step 2: Add ranking + allocation + capacity functions to src/station_store.py**

Append to `src/station_store.py`:

```python
_RANK_WEIGHTS = {
    "btp_boost":        2.0,
    "workload_penalty": 1.5,
}

_WORKLOAD_SQL = """
    SELECT COUNT(*) FROM planned_events
    WHERE police_station = :station
      AND status IN ('planned', 'active')
      AND ABS(
            julianday(:date || 'T' || :time)
            - julianday(event_date || 'T' || event_time)
          ) * 24 <= 4
"""


def rank_stations(
    event_lat: float,
    event_lng: float,
    event_date: str,
    event_time: str,
    top_n: int = 5,
) -> list[dict]:
    """Rank geocoded stations by score = distance - btp_boost + workload_penalty.
    Returns [] if fewer than 2 stations are geocoded."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM police_stations WHERE latitude IS NOT NULL"
        ).fetchall()

    if len(rows) < 2:
        return []

    scored: list[dict] = []
    with sqlite3.connect(DB_PATH) as conn:
        for row in rows:
            dist = _haversine_km(event_lat, event_lng, row["latitude"], row["longitude"])
            workload = conn.execute(
                _WORKLOAD_SQL,
                {"station": row["station_name"], "date": event_date, "time": event_time},
            ).fetchone()[0]
            score = (
                dist
                - row["has_btp_pi"] * _RANK_WEIGHTS["btp_boost"]
                + workload * _RANK_WEIGHTS["workload_penalty"]
            )
            scored.append({
                "station_name":         row["station_name"],
                "station_code":         row["station_code"],
                "dcp_zone":             row["dcp_zone"],
                "acp_zone":             row["acp_zone"],
                "distance_km":          round(dist, 2),
                "workload":             workload,
                "has_btp_pi":           row["has_btp_pi"],
                "btp_match_confidence": row["btp_match_confidence"],
                "capacity_officers":    row["capacity_officers"],
                "capacity_vehicles":    row["capacity_vehicles"],
                "capacity_source":      row["capacity_source"],
                "score":                round(score, 3),
                "response_min":         round(dist / 30.0 * 60),
                "officers_allocated":   0,
                "allocation_capped":    False,
                "capacity_unconfirmed": False,
            })

    scored.sort(key=lambda x: x["score"])
    return scored[:top_n]


def allocate_officers(stations: list[dict], total_officers: int) -> list[dict]:
    """Inverse-distance weighted officer allocation.
    Cap only applied for capacity_source == 'manual'. Both branches set all 3 keys."""
    if not stations:
        return stations

    dists   = [max(s["distance_km"], 0.1) for s in stations]
    weights = [1.0 / d for d in dists]
    total_w = sum(weights)

    for s, w in zip(stations, weights):
        raw = round(total_officers * w / total_w)
        if s["capacity_source"] == "manual":
            s["officers_allocated"]   = min(raw, s["capacity_officers"])
            s["allocation_capped"]    = raw > s["capacity_officers"]
            s["capacity_unconfirmed"] = False
        else:
            s["officers_allocated"]   = raw
            s["allocation_capped"]    = False
            s["capacity_unconfirmed"] = True

    return stations


def update_station_capacity(station_code: int, officers: int, vehicles: int) -> None:
    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """UPDATE police_stations
               SET capacity_officers=?, capacity_vehicles=?,
                   capacity_source='manual', updated_at=?
               WHERE station_code=?""",
            (officers, vehicles, now, station_code),
        )
        conn.commit()


def get_all_stations() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM police_stations ORDER BY dcp_zone, station_name"
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 3: Run the 8 new ranking tests**

Run: `pytest tests/test_station_store.py -v -k "rank or allocate or capacity"`
Expected: 8 passed.

- [ ] **Step 4: Run full suite**

Run: `pytest --tb=short -q`
Expected: 111 passed (103 + 8 new).

- [ ] **Step 5: Commit**

```bash
git add src/station_store.py tests/test_station_store.py
git commit -m "feat: station ranking engine, officer allocation, capacity update"
```

---

### Task 4: Deployment Planning Engine

**Files:**
- Create: `src/deployment_planner.py`
- Create: `tests/test_deployment_planner.py`

**Interfaces:**
- Consumes: nothing from station_store (takes pre-computed dicts as arguments)
- Produces:
  - `build_deployment_plan(event, ranked_stations, officers, barricades, diversions) -> dict`
  - Output dict keys: `briefing, stations, total_officers_min, total_officers_max, barricade_positions, diversion_routes, qrt_recommended, qrt_units, medical_posts, surveillance_points, vip_protocol, timeline`
  - `_attendance_band(n: int) -> str`

- [ ] **Step 1: Write failing tests**

Create `tests/test_deployment_planner.py`:

```python
# tests/test_deployment_planner.py
import pytest
from src import deployment_planner


def _ev(**overrides):
    base = {
        "event_name": "Test Rally", "event_type": "procession",
        "severity": "MEDIUM", "corridor": "MG Road",
        "estimated_attendance": 1000, "has_vip": 0,
        "law_order_prob": 0.3, "congestion_prob": 0.4,
        "event_date": "2026-07-15", "event_time": "10:00",
        "expected_duration_h": 2.0,
    }
    base.update(overrides)
    return base


def _station(name="Test PS", dist=2.0, alloc=8):
    return {
        "station_name": name, "station_code": 1,
        "dcp_zone": "Central Division, Bangalore City", "acp_zone": "Cubbon Park",
        "distance_km": dist, "workload": 0, "has_btp_pi": 0,
        "btp_match_confidence": None, "capacity_officers": 25, "capacity_vehicles": 3,
        "capacity_source": "default", "score": dist, "response_min": round(dist / 30.0 * 60),
        "officers_allocated": alloc, "allocation_capped": False, "capacity_unconfirmed": True,
    }


def _officers(lo=8, hi=12):
    return {"total_min": lo, "total_max": hi,
            "primary_min": 4, "primary_max": 6, "adjacent_total": 4}


def test_briefing_contains_severity():
    plan = deployment_planner.build_deployment_plan(
        _ev(severity="HIGH"), [_station()], _officers(), [], []
    )
    assert "HIGH" in plan["briefing"]


def test_briefing_contains_station_name():
    plan = deployment_planner.build_deployment_plan(
        _ev(), [_station(name="Cubbon Park PS")], _officers(), [], []
    )
    assert "Cubbon Park PS" in plan["briefing"]


def test_briefing_qrt_above_threshold():
    plan = deployment_planner.build_deployment_plan(
        _ev(law_order_prob=0.7), [_station()], _officers(), [], []
    )
    assert "QRT" in plan["briefing"]


def test_briefing_no_qrt_below_threshold():
    plan = deployment_planner.build_deployment_plan(
        _ev(severity="LOW", law_order_prob=0.2), [_station()], _officers(), [], []
    )
    assert "QRT" not in plan["briefing"]


def test_briefing_medical_large_crowd():
    plan = deployment_planner.build_deployment_plan(
        _ev(estimated_attendance=5000), [_station()], _officers(), [], []
    )
    assert "medical post" in plan["briefing"].lower()


def test_briefing_no_medical_small_crowd():
    plan = deployment_planner.build_deployment_plan(
        _ev(estimated_attendance=200), [_station()], _officers(), [], []
    )
    assert "medical post" not in plan["briefing"].lower()


def test_briefing_vip_protocol():
    plan = deployment_planner.build_deployment_plan(
        _ev(has_vip=1), [_station()], _officers(), [], []
    )
    assert "VIP" in plan["briefing"]


def test_qrt_units_high_severity_large():
    plan = deployment_planner.build_deployment_plan(
        _ev(severity="HIGH", estimated_attendance=6000, law_order_prob=0.9),
        [_station()], _officers(), [], []
    )
    assert plan["qrt_units"] == 2


def test_qrt_units_high_severity_small():
    plan = deployment_planner.build_deployment_plan(
        _ev(severity="HIGH", estimated_attendance=1000, law_order_prob=0.9),
        [_station()], _officers(), [], []
    )
    assert plan["qrt_units"] == 1


def test_timeline_contains_five_entries():
    plan = deployment_planner.build_deployment_plan(
        _ev(expected_duration_h=3.0), [], _officers(), [], []
    )
    assert len(plan["timeline"]) == 5
    offsets = [t["offset_min"] for t in plan["timeline"]]
    assert -120 in offsets
    assert 0 in offsets
    assert 180 in offsets  # 3h = 180 min


def test_plan_structure_keys():
    plan = deployment_planner.build_deployment_plan(_ev(), [], _officers(), [], [])
    required = {
        "briefing", "stations", "total_officers_min", "total_officers_max",
        "barricade_positions", "diversion_routes", "qrt_recommended", "qrt_units",
        "medical_posts", "surveillance_points", "vip_protocol", "timeline",
    }
    assert required.issubset(plan.keys())
```

Run: `pytest tests/test_deployment_planner.py -v`
Expected: 11 failures (ImportError).

- [ ] **Step 2: Create src/deployment_planner.py**

```python
# src/deployment_planner.py

_ATTENDANCE_BANDS = [
    (500,   "small gathering"),
    (2000,  "moderate crowd"),
    (10000, "large crowd"),
]


def _attendance_band(n: int) -> str:
    for threshold, label in _ATTENDANCE_BANDS:
        if n < threshold:
            return label
    return "mass event"


def build_deployment_plan(
    event: dict,
    ranked_stations: list[dict],
    officers: dict,
    barricades: list[str],
    diversions: list[str],
) -> dict:
    """Assemble full deployment plan dict with narrative briefing."""
    attendance  = int(event.get("estimated_attendance") or 0)
    severity    = event.get("severity", "LOW")
    law_prob    = float(event.get("law_order_prob") or 0.0)
    duration_m  = round(float(event.get("expected_duration_h") or 2.0) * 60)

    qrt_recommended = law_prob > 0.5 or severity == "HIGH"
    qrt_units = (
        2 if severity == "HIGH" and attendance > 5000
        else 1 if qrt_recommended
        else 0
    )
    medical_posts = (
        2 if attendance > 2000
        else 1 if attendance >= 500
        else 0
    )
    timeline = [
        {"offset_min": -120, "label": "Station briefing and resource assembly"},
        {"offset_min": -60,  "label": "Deploy barricades and route closures"},
        {"offset_min": -30,  "label": "All units in position, radio check"},
        {"offset_min": 0,    "label": "Event start — active monitoring"},
        {"offset_min": duration_m, "label": "Begin staged withdrawal"},
    ]

    return {
        "briefing": _build_briefing(
            event, ranked_stations, officers, barricades,
            qrt_recommended, qrt_units, medical_posts,
        ),
        "stations":            ranked_stations,
        "total_officers_min":  officers["total_min"],
        "total_officers_max":  officers["total_max"],
        "barricade_positions": barricades,
        "diversion_routes":    diversions,
        "qrt_recommended":     qrt_recommended,
        "qrt_units":           qrt_units,
        "medical_posts":       medical_posts,
        "surveillance_points": barricades,
        "vip_protocol":        bool(event.get("has_vip", 0)),
        "timeline":            timeline,
    }


def _build_briefing(
    event: dict,
    stations: list[dict],
    officers: dict,
    barricades: list[str],
    qrt_recommended: bool,
    qrt_units: int,
    medical_posts: int,
) -> str:
    attendance = int(event.get("estimated_attendance") or 0)
    severity   = event.get("severity", "LOW")
    band       = _attendance_band(attendance)
    corridor   = event.get("corridor") or "unspecified corridor"
    evt_type   = event.get("event_type", "event")
    n_stations = len(stations)

    sentences = [
        f"For a {severity} severity {evt_type} on {corridor} with an estimated "
        f"{band} ({attendance:,} attendees),",
        f"deploy {officers['total_min']}–{officers['total_max']} officers "
        f"across {n_stations} station(s).",
    ]

    if stations:
        s1 = stations[0]
        primary = (
            f"Primary response from {s1['station_name']} "
            f"({s1['distance_km']:.1f} km, {s1['officers_allocated']} officers, "
            f"ETA {s1['response_min']} min)"
        )
        if len(stations) >= 2:
            s2 = stations[1]
            primary += (
                f" and {s2['station_name']} "
                f"({s2['distance_km']:.1f} km, {s2['officers_allocated']} officers, "
                f"ETA {s2['response_min']} min)."
            )
        else:
            primary += "."
        sentences.append(primary)

    if barricades:
        sentences.append(f"Position {len(barricades)} barricade(s) at key junctions.")
    if qrt_recommended:
        sentences.append(f"Law and order risk is elevated — {qrt_units} QRT unit(s) on standby.")
    if medical_posts > 0:
        sentences.append(f"Establish {medical_posts} medical post(s) for crowd safety.")
    if event.get("has_vip"):
        sentences.append("VIP protocol active — route pre-clearance required.")

    return " ".join(sentences)
```

- [ ] **Step 3: Run all 11 deployment planner tests**

Run: `pytest tests/test_deployment_planner.py -v`
Expected: 11 passed.

- [ ] **Step 4: Run full suite**

Run: `pytest --tb=short -q`
Expected: 122 passed (111 + 11).

- [ ] **Step 5: Commit**

```bash
git add src/deployment_planner.py tests/test_deployment_planner.py
git commit -m "feat: deployment planning engine with rule-based narrative briefing"
```

---

### Task 5: Station Registry Admin Page

**Files:**
- Create: `pages/6_Station_Registry.py`

**Interfaces:**
- Consumes:
  - `station_store.init_station_db()`
  - `station_store.get_all_stations() -> list[dict]`
  - `station_store.geocode_all_stations(progress_callback) -> dict`
  - `station_store.update_station_capacity(station_code, officers, vehicles) -> None`
  - `station_store.reset_station_geocode(station_code) -> None`
  - `station_store.get_geocode_summary() -> dict`
- Produces: nothing (UI only)

- [ ] **Step 1: Create pages/6_Station_Registry.py**

```python
# pages/6_Station_Registry.py
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
import folium

from src import station_store
from src.app_cache import load_and_train

st.set_page_config(page_title="Station Registry", layout="wide")
st.title("Station Registry")

load_and_train()  # ensures init_station_db() has been called

stations = station_store.get_all_stations()

tab_map, tab_table, tab_geocoding = st.tabs(["Map", "Stations Table", "Geocoding"])

# ── Tab 1: Map ────────────────────────────────────────────────────────────────
with tab_map:
    _COLOR = {
        "geocoded":               "#28a745",
        "zone_centroid_fallback": "#fd7e14",
        "pending":                "#6c757d",
    }
    m = folium.Map(location=[12.97, 77.59], zoom_start=11)
    for s in stations:
        if s["latitude"] is None:
            continue
        btp_txt = f" | ✓ BTP ({s['btp_match_confidence']:.2f})" if s["has_btp_pi"] else ""
        cap_txt = f"⚠ Default" if s["capacity_source"] == "default" else "✓ Confirmed"
        popup = (
            f"<b>{s['station_name']}</b><br>"
            f"{s['dcp_zone']}<br>"
            f"Capacity: {s['capacity_officers']} officers, {s['capacity_vehicles']} vehicles "
            f"({cap_txt}){btp_txt}"
        )
        folium.CircleMarker(
            location=[s["latitude"], s["longitude"]],
            radius=6,
            color=_COLOR.get(s["location_source"], "#6c757d"),
            fill=True,
            fill_opacity=0.8,
            popup=folium.Popup(popup, max_width=250),
            tooltip=s["station_name"],
        ).add_to(m)
    st_folium(m, width=900, height=550, returned_objects=[])
    st.caption("🟢 Geocoded &nbsp;&nbsp; 🟠 Zone centroid fallback &nbsp;&nbsp; ⚫ Pending")

# ── Tab 2: Stations Table ─────────────────────────────────────────────────────
with tab_table:
    st.markdown("Edit **capacity_officers** and **capacity_vehicles** then click Save.")

    df = pd.DataFrame(stations)
    display_cols = [
        "station_code", "station_name", "dcp_zone", "acp_zone",
        "location_source", "has_btp_pi", "btp_match_confidence",
        "capacity_officers", "capacity_vehicles", "capacity_source",
    ]
    df_display = df[display_cols].copy()
    df_display["capacity_label"] = df_display["capacity_source"].map(
        {"default": "⚠ Default", "manual": "✓ Confirmed"}
    )
    df_display["btp_label"] = df_display.apply(
        lambda r: f"✓ BTP ({r['btp_match_confidence']:.2f})" if r["has_btp_pi"] else "",
        axis=1,
    )

    edited = st.data_editor(
        df_display,
        use_container_width=True,
        hide_index=True,
        disabled=[
            "station_code", "station_name", "dcp_zone", "acp_zone",
            "location_source", "has_btp_pi", "btp_match_confidence",
            "capacity_source", "capacity_label", "btp_label",
        ],
        column_config={
            "capacity_officers": st.column_config.NumberColumn("Officers", min_value=1, max_value=200),
            "capacity_vehicles": st.column_config.NumberColumn("Vehicles", min_value=0, max_value=50),
        },
    )

    if st.button("💾 Save capacity changes"):
        changed = 0
        for i, row in edited.iterrows():
            orig = df_display.iloc[i]
            if (row["capacity_officers"] != orig["capacity_officers"] or
                    row["capacity_vehicles"] != orig["capacity_vehicles"]):
                station_store.update_station_capacity(
                    int(row["station_code"]),
                    int(row["capacity_officers"]),
                    int(row["capacity_vehicles"]),
                )
                changed += 1
        if changed:
            st.success(f"Saved {changed} station(s).")
            st.rerun()
        else:
            st.info("No changes detected.")

# ── Tab 3: Geocoding ──────────────────────────────────────────────────────────
with tab_geocoding:
    summary = station_store.get_geocode_summary()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total",    summary["total"])
    c2.metric("Geocoded", summary["geocoded"])
    c3.metric("Fallback", summary["fallback"])
    c4.metric("Pending",  summary["pending"])

    st.markdown("---")
    if summary["pending"] == 0 and summary["total"] > 0:
        st.success("All stations have coordinates.")
    else:
        if "geocoding_running" not in st.session_state:
            st.session_state["geocoding_running"] = False

        if not st.session_state["geocoding_running"]:
            if st.button("🌐 Geocode All Stations", disabled=st.session_state["geocoding_running"]):
                st.session_state["geocoding_running"] = True
                st.rerun()
        else:
            progress_bar = st.progress(0.0)
            status_txt   = st.empty()

            def _cb(current, total):
                progress_bar.progress(current / total)
                status_txt.text(f"Geocoding {current}/{total}…")

            result = station_store.geocode_all_stations(progress_callback=_cb)
            st.session_state["geocoding_running"] = False
            st.success(
                f"Done — {result['geocoded']} geocoded, "
                f"{result['fallback']} zone fallbacks, "
                f"{result['pending']} still pending."
            )
            st.rerun()

    st.markdown("---")
    st.markdown("**Reset individual station** (sets back to pending for re-geocoding):")
    reset_code = st.number_input("Station code", min_value=1, step=1, value=None)
    if st.button("Reset") and reset_code:
        station_store.reset_station_geocode(int(reset_code))
        st.success(f"Station {reset_code} reset to pending.")
        st.rerun()
```

- [ ] **Step 2: Verify page loads**

Run the app: `streamlit run app.py --server.port 8501`

Navigate to "Station Registry" in the sidebar. Expected:
- Three tabs visible: Map, Stations Table, Geocoding
- Map tab: Folium map centred on Bengaluru with 110 grey (pending) markers
- Stations Table tab: data_editor with 110 rows, all showing "⚠ Default" capacity label
- Geocoding tab: Total=110, Geocoded=0, Fallback=0, Pending=110; "Geocode All Stations" button visible

- [ ] **Step 3: Commit**

```bash
git add pages/6_Station_Registry.py
git commit -m "feat: Station Registry admin page with map, table, geocoding tabs"
```

---

### Task 6: Deployment Plan Page

**Files:**
- Create: `pages/7_Deployment_Plan.py`

**Interfaces:**
- Consumes: `st.session_state["deployment_data"]` dict with keys: `event` (dict), `stations` (list[dict]), `plan` (dict from build_deployment_plan)
- Produces: nothing (UI only)

- [ ] **Step 1: Create pages/7_Deployment_Plan.py**

```python
# pages/7_Deployment_Plan.py
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Deployment Plan", layout="wide")
st.title("Deployment Plan")

if "deployment_data" not in st.session_state:
    st.warning("No deployment plan found. Please run a prediction first.")
    st.page_link("pages/1_Plan_Event.py", label="← Back to form")
    st.stop()

dd      = st.session_state["deployment_data"]
event   = dd["event"]
stations = dd["stations"]
plan    = dd["plan"]

# ── Header ─────────────────────────────────────────────────────────────────────
sev = event.get("severity", "—")
sev_color = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}.get(sev, "⚫")
st.markdown(
    f"**{event.get('event_name', '—')}** &nbsp; {sev_color} {sev} &nbsp;|&nbsp; "
    f"{event.get('event_date', '')} {event.get('event_time', '')} &nbsp;|&nbsp; "
    f"{event.get('corridor', '—')}"
)

st.markdown("---")

# ── Section 1: Briefing ───────────────────────────────────────────────────────
st.subheader("Operational Briefing")
st.info(plan["briefing"])

st.markdown("---")

# ── Section 2: Station Deployment ─────────────────────────────────────────────
st.subheader("Station Deployment")

if stations:
    rows = []
    for s in stations:
        officers_cell = str(s["officers_allocated"])
        if s.get("capacity_unconfirmed"):
            officers_cell = f"⚠ {officers_cell}"
        elif s.get("allocation_capped"):
            officers_cell = f"🔒 {officers_cell}"
        rows.append({
            "Station":    s["station_name"],
            "Zone":       s["dcp_zone"],
            "Dist (km)":  f"{s['distance_km']:.1f}",
            "ETA (min)":  s["response_min"],
            "Officers":   officers_cell,
            "Vehicles":   s["capacity_vehicles"],
            "BTP PI":     "✓" if s["has_btp_pi"] else "—",
            "Capacity":   "⚠ Default" if s.get("capacity_unconfirmed") else "✓ Confirmed",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("⚠ = uncapped default capacity &nbsp;&nbsp; 🔒 = capped at confirmed capacity")
else:
    st.info("No stations ranked — geocoding not yet run. Visit Station Registry.")

st.markdown("---")

# ── Section 3: Barricades & Diversions ────────────────────────────────────────
st.subheader("Barricades & Diversions")
col_b, col_d = st.columns(2)
with col_b:
    st.markdown("**Barricade positions**")
    if plan["barricade_positions"]:
        for b in plan["barricade_positions"]:
            st.markdown(f"- {b}")
    else:
        st.caption("None identified.")
with col_d:
    st.markdown("**Diversion routes**")
    if plan["diversion_routes"]:
        for d in plan["diversion_routes"]:
            st.markdown(f"- {d}")
    else:
        st.caption("None identified.")

st.markdown("---")

# ── Section 4: Support Requirements ──────────────────────────────────────────
st.subheader("Support Requirements")
m1, m2, m3, m4 = st.columns(4)
m1.metric("QRT Units",         plan["qrt_units"])
m2.metric("Medical Posts",     plan["medical_posts"])
m3.metric("Surveillance Pts",  len(plan["surveillance_points"]))
m4.metric("VIP Protocol",      "Yes" if plan["vip_protocol"] else "No")

st.markdown("---")

# ── Section 5: Timeline ───────────────────────────────────────────────────────
st.subheader("Deployment Timeline")
tl_df = pd.DataFrame([
    {
        "Time (relative)": (
            f"T{t['offset_min']:+d} min" if t["offset_min"] != 0
            else "T+0 (event start)"
        ),
        "Action": t["label"],
    }
    for t in plan["timeline"]
])
st.table(tl_df)

st.markdown("---")

# ── Footer ────────────────────────────────────────────────────────────────────
export_rows = (
    [("Event", event.get("event_name", ""))]
    + [(f"Station {i+1}", s["station_name"]) for i, s in enumerate(stations)]
    + [("Officers min", plan["total_officers_min"]),
       ("Officers max", plan["total_officers_max"]),
       ("QRT units", plan["qrt_units"]),
       ("Medical posts", plan["medical_posts"]),
       ("VIP protocol", plan["vip_protocol"])]
    + [("Barricade", b) for b in plan["barricade_positions"]]
    + [("Diversion", d) for d in plan["diversion_routes"]]
)
export_df = pd.DataFrame(export_rows, columns=["Field", "Value"])
st.download_button(
    "Export Deployment Plan (CSV)",
    data=export_df.to_csv(index=False),
    file_name=f"deployment_{event.get('event_name', 'plan').replace(' ', '_')}.csv",
    mime="text/csv",
)
st.page_link("pages/2_Results.py", label="← Back to Results")
```

- [ ] **Step 2: Commit**

```bash
git add pages/7_Deployment_Plan.py
git commit -m "feat: Deployment Plan page with briefing, stations table, timeline, export"
```

---

### Task 7: Results Page — Compact Station Summary

**Files:**
- Modify: `pages/2_Results.py`

**Interfaces:**
- Consumes:
  - `station_store.rank_stations(lat, lng, date, time, top_n=3) -> list[dict]`
  - `station_store.allocate_officers(stations, total_min) -> list[dict]`
  - `deployment_planner.build_deployment_plan(event, stations, officers, barricades, diversions) -> dict`
- Produces: `st.session_state["deployment_data"]` dict

- [ ] **Step 1: Add imports to pages/2_Results.py**

At the top of `pages/2_Results.py`, after the existing imports, add:

```python
from src import station_store
from src import deployment_planner
```

- [ ] **Step 2: Add station summary section**

In `pages/2_Results.py`, after the existing "Action Plan" section (after the last diversion `st.markdown` line, before the "SHAP Explainability" section), insert:

```python
    # ── Recommended Stations ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Recommended Stations")

    _lat = st.session_state.get("save_data", {}).get("latitude")
    _lng = st.session_state.get("save_data", {}).get("longitude")
    _edate = st.session_state.get("save_data", {}).get("event_date", "")
    _etime = st.session_state.get("save_data", {}).get("event_time", "")

    if _lat is None or _lng is None:
        st.caption("No event location provided — station ranking unavailable.")
        _ranked = []
    else:
        _ranked = station_store.rank_stations(_lat, _lng, _edate, _etime, top_n=3)
        if not _ranked:
            st.caption("Station geocoding not yet run — visit Station Registry to enable ranking.")
        else:
            station_store.allocate_officers(_ranked, officers["total_min"])
            _rows = []
            for _s in _ranked:
                _off = str(_s["officers_allocated"])
                if _s.get("capacity_unconfirmed"):
                    _off = f"⚠ {_off}"
                elif _s.get("allocation_capped"):
                    _off = f"🔒 {_off}"
                _rows.append({
                    "Station":   _s["station_name"],
                    "Zone":      _s["dcp_zone"],
                    "Dist (km)": f"{_s['distance_km']:.1f}",
                    "ETA (min)": _s["response_min"],
                    "Officers":  _off,
                    "⚠":        ("Uncapped" if _s.get("capacity_unconfirmed")
                                  else "Capped" if _s.get("allocation_capped") else ""),
                })
            st.dataframe(
                pd.DataFrame(_rows),
                use_container_width=True,
                hide_index=True,
            )

    # Build and store full deployment plan for Deployment Plan page
    _sd = st.session_state.get("save_data", {})
    _dep_event = {
        **r,
        "corridor":            r.get("corridor"),
        "estimated_attendance": _sd.get("estimated_attendance", 0),
        "has_vip":             _sd.get("has_vip", 0),
        "law_order_prob":      risks.get("law_order_prob", 0.0),
        "congestion_prob":     risks.get("congestion_prob", 0.0),
        "event_date":          _sd.get("event_date", ""),
        "event_time":          _sd.get("event_time", ""),
        "expected_duration_h": None,
    }
    _top5 = station_store.rank_stations(
        _lat or 0.0, _lng or 0.0, _edate, _etime, top_n=5
    ) if (_lat and _lng) else []
    if _top5:
        station_store.allocate_officers(_top5, officers["total_min"])
    _plan = deployment_planner.build_deployment_plan(
        _dep_event, _top5, officers, barricades, diversions
    )
    st.session_state["deployment_data"] = {
        "event":    _dep_event,
        "stations": _top5,
        "plan":     _plan,
    }
    if _ranked:
        st.page_link("pages/7_Deployment_Plan.py", label="View Full Deployment Plan →")
```

- [ ] **Step 3: Run full test suite**

Run: `pytest --tb=short -q`
Expected: 122 passed (no regressions — Results page changes are UI-only, no new tests needed).

- [ ] **Step 4: Verify end-to-end in browser**

Start app: `streamlit run app.py --server.port 8501`

1. Fill Plan Event form with a corridor event + lat/lng (e.g. MG Road, lat 12.9716, lng 77.5946)
2. Submit → Results page
3. Scroll to "Recommended Stations" — expect: "Station geocoding not yet run" caption (no geocoding done yet)
4. Navigate to Station Registry → Geocoding tab — verify Total=110, Pending=110
5. Navigate back to Results → "View Full Deployment Plan →" link NOT shown (no ranked stations)
6. After first geocoding run completes, resubmit form → Results shows top-3 table and link

- [ ] **Step 5: Commit**

```bash
git add pages/2_Results.py
git commit -m "feat: Results page station summary + deployment plan link"
```
