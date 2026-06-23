# Geocoding + Station Map Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Geocode all 110 police stations using a multi-strategy Nominatim cascade, retry the 36 zone-centroid-fallback stations, and overlay all stations on the Results page Impact Map.

**Architecture:** Add `_try_geocode_strategies()` to `station_store.py` for a 3-query cascade; add `_retry_fallback_stations()` to re-attempt fallback stations; extend `build_map()` with optional `stations`/`ranked_stations` parameters; wire up the new params in `1_Plan_Event.py`.

**Tech Stack:** Python, SQLite (via `sqlite3`), `geopy` (Nominatim + RateLimiter), `folium`, Streamlit

## Global Constraints

- Rate limit: Nominatim at 1 request/second (already enforced by existing `RateLimiter`)
- DB schema unchanged — no new columns, no migrations
- `build_map()` signature is backward-compatible (new params are optional with `None` defaults)
- All tests use injectable `_geocoder` — no live Nominatim calls in tests

---

## File Map

| File | Change |
|---|---|
| `src/station_store.py` | Add `_try_geocode_strategies()`, update `geocode_all_stations()` (new SQL + cascade), add `_retry_fallback_stations()` |
| `src/map_builder.py` | Add `stations` and `ranked_stations` optional params to `build_map()`, render circle + pin markers |
| `pages/1_Plan_Event.py` | Import `station_store`, call `get_all_stations()` + `rank_stations()`, pass to `build_map()` |
| `tests/test_geocoding_cascade.py` | New test file for geocoding cascade logic |
| `tests/test_map_station_overlay.py` | New test file for station overlay rendering |

---

### Task 1: Geocoding cascade helper + update pending geocoding

**Files:**
- Modify: `src/station_store.py`
- Create: `tests/test_geocoding_cascade.py`

**Interfaces:**
- Produces: `_try_geocode_strategies(station_name: str, acp_zone: str, geocoder) -> tuple[float, float] | None`
  - `geocoder` is any callable `(query: str) -> location | None` where `location.latitude` and `location.longitude` are floats
  - Returns `(lat, lng)` on first successful query, `None` if all 3 fail

- [ ] **Step 1: Write failing tests**

Create `tests/test_geocoding_cascade.py`:

```python
# tests/test_geocoding_cascade.py
import pytest
from src.station_store import _try_geocode_strategies


class _FakeLoc:
    def __init__(self, lat=12.97, lng=77.59):
        self.latitude = lat
        self.longitude = lng


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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_geocoding_cascade.py -v
```
Expected: FAIL with `ImportError: cannot import name '_try_geocode_strategies'`

- [ ] **Step 3: Add `_try_geocode_strategies()` to `src/station_store.py`**

Add this function after the `_NAME_STOPWORDS` block (around line 57), before `_now()`:

```python
def _try_geocode_strategies(
    station_name: str,
    acp_zone: str,
    geocoder,
) -> tuple[float, float] | None:
    """Try 3 progressively simpler Nominatim queries. Returns (lat, lng) or None."""
    queries = [
        f"{station_name} Police Station, {acp_zone}, Bangalore, Karnataka, India",
        f"{station_name} Police Station, Bangalore, Karnataka, India",
        f"{station_name}, Bangalore, India",
    ]
    for q in queries:
        loc = geocoder(q)
        if loc is not None:
            return (loc.latitude, loc.longitude)
    return None
```

Then update `geocode_all_stations()`. Replace the existing `pending` query and loop (lines ~162–184):

Old SQL:
```python
pending = conn.execute(
    "SELECT station_code, station_name, address_clean FROM police_stations "
    "WHERE location_source = 'pending'"
).fetchall()
```

New SQL (add `acp_zone`):
```python
pending = conn.execute(
    "SELECT station_code, station_name, address_clean, acp_zone FROM police_stations "
    "WHERE location_source = 'pending'"
).fetchall()
```

Old loop body:
```python
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
    if progress_callback:
        progress_callback(i + 1, total)
```

New loop body:
```python
for i, row in enumerate(pending):
    result = _try_geocode_strategies(row["station_name"], row["acp_zone"], _geocoder)
    now = _now()
    if result is not None:
        lat, lng = result
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE police_stations SET latitude=?, longitude=?, "
                "location_source='geocoded', geocoded_at=?, updated_at=? "
                "WHERE station_code=?",
                (lat, lng, now, now, row["station_code"]),
            )
            conn.commit()
    if progress_callback:
        progress_callback(i + 1, total)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_geocoding_cascade.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/station_store.py tests/test_geocoding_cascade.py
git commit -m "feat: add 3-strategy Nominatim cascade for pending station geocoding"
```

---

### Task 2: Retry zone-centroid-fallback stations

**Files:**
- Modify: `src/station_store.py`
- Modify: `tests/test_geocoding_cascade.py`

**Interfaces:**
- Consumes: `_try_geocode_strategies()` from Task 1
- Produces: `_retry_fallback_stations(geocoder, progress_callback=None) -> int` — returns count of stations upgraded from fallback to geocoded

- [ ] **Step 1: Write failing tests**

Append to `tests/test_geocoding_cascade.py`:

```python
import sqlite3
import src.station_store as _ss


def _make_test_db(tmp_path, stations: list[dict]) -> object:
    """Create a minimal police_stations table and return its Path."""
    db = tmp_path / "test.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE police_stations (
                station_code    INTEGER PRIMARY KEY,
                station_name    TEXT,
                acp_zone        TEXT,
                latitude        REAL,
                longitude       REAL,
                location_source TEXT,
                geocoded_at     TEXT,
                updated_at      TEXT NOT NULL
            )
        """)
        for s in stations:
            conn.execute(
                "INSERT INTO police_stations VALUES (?,?,?,?,?,?,?,?)",
                (s["station_code"], s["station_name"], s["acp_zone"],
                 s.get("latitude"), s.get("longitude"),
                 s["location_source"], None, "2024-01-01"),
            )
        conn.commit()
    return db


def test_retry_fallback_updates_successful_geocodes(tmp_path, monkeypatch):
    db = _make_test_db(tmp_path, [
        {"station_code": 1, "station_name": "Cubbon Park", "acp_zone": "Cubbon Park",
         "latitude": 12.5, "longitude": 77.5, "location_source": "zone_centroid_fallback"},
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
        {"station_code": 2, "station_name": "Unknown", "acp_zone": "Nowhere",
         "latitude": 12.5, "longitude": 77.5, "location_source": "zone_centroid_fallback"},
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
        {"station_code": 3, "station_name": "Already Good", "acp_zone": "Central",
         "latitude": 12.97, "longitude": 77.59, "location_source": "geocoded"},
    ])
    monkeypatch.setattr(_ss, "DB_PATH", db)

    improved = _ss._retry_fallback_stations(lambda q: _FakeLoc())
    assert improved == 0


def test_geocode_all_stations_calls_retry_fallback(tmp_path, monkeypatch):
    db = _make_test_db(tmp_path, [
        {"station_code": 10, "station_name": "Fallback PS", "acp_zone": "East",
         "latitude": 12.5, "longitude": 77.5, "location_source": "zone_centroid_fallback"},
    ])
    monkeypatch.setattr(_ss, "DB_PATH", db)

    # geocode_all_stations with injectable geocoder that always succeeds
    _ss.geocode_all_stations(_geocoder=lambda q: _FakeLoc(12.97, 77.59))

    with sqlite3.connect(db) as conn:
        src = conn.execute(
            "SELECT location_source FROM police_stations WHERE station_code=10"
        ).fetchone()[0]
    assert src == "geocoded"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_geocoding_cascade.py::test_retry_fallback_updates_successful_geocodes -v
```
Expected: FAIL with `AttributeError: module 'src.station_store' has no attribute '_retry_fallback_stations'`

- [ ] **Step 3: Add `_retry_fallback_stations()` and call it from `geocode_all_stations()`**

In `src/station_store.py`, add this function just before `_apply_zone_centroid_fallback()`:

```python
def _retry_fallback_stations(geocoder, progress_callback=None) -> int:
    """Re-attempt geocoding for zone_centroid_fallback stations using the cascade.
    Returns the count of stations upgraded to 'geocoded'."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        fallback = conn.execute(
            "SELECT station_code, station_name, acp_zone FROM police_stations "
            "WHERE location_source = 'zone_centroid_fallback'"
        ).fetchall()

    improved = 0
    total = len(fallback)
    for i, row in enumerate(fallback):
        result = _try_geocode_strategies(row["station_name"], row["acp_zone"], geocoder)
        if result is not None:
            lat, lng = result
            now = _now()
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "UPDATE police_stations SET latitude=?, longitude=?, "
                    "location_source='geocoded', geocoded_at=?, updated_at=? "
                    "WHERE station_code=?",
                    (lat, lng, now, now, row["station_code"]),
                )
                conn.commit()
            improved += 1
        if progress_callback:
            progress_callback(i + 1, total)
    return improved
```

Then in `geocode_all_stations()`, add the retry call just before `_apply_zone_centroid_fallback()`:

```python
    # ... existing pending loop ends here ...
    _retry_fallback_stations(_geocoder)
    _apply_zone_centroid_fallback()
    _compute_and_store_zone_centroids()
    _enrich_btp()

    return get_geocode_summary()
```

- [ ] **Step 4: Run all geocoding tests**

```
pytest tests/test_geocoding_cascade.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add src/station_store.py tests/test_geocoding_cascade.py
git commit -m "feat: retry zone-centroid-fallback stations with geocoding cascade"
```

---

### Task 3: Station overlay in map_builder.py

**Files:**
- Modify: `src/map_builder.py`
- Create: `tests/test_map_station_overlay.py`

**Interfaces:**
- Consumes: `stations: list[dict]` — each dict has keys `station_code` (int), `station_name` (str), `latitude` (float|None), `longitude` (float|None), `location_source` (str), `dcp_zone` (str)
- Consumes: `ranked_stations: list[dict]` — each dict has keys `station_code` (int), `station_name` (str), `distance_km` (float), `response_min` (int)
- Produces: updated `build_map()` signature with two new optional kwargs

- [ ] **Step 1: Write failing tests**

Create `tests/test_map_station_overlay.py`:

```python
# tests/test_map_station_overlay.py
import folium
import pandas as pd
from unittest.mock import MagicMock

from src.map_builder import build_map


def _officer_info():
    return {"total_min": 4, "total_max": 6, "primary_min": 2, "primary_max": 4}


def _empty_df():
    return pd.DataFrame({
        "junction": pd.Series([], dtype=str),
        "latitude": pd.Series([], dtype=float),
        "longitude": pd.Series([], dtype=float),
        "corridor": pd.Series([], dtype=str),
        "requires_road_closure": pd.Series([], dtype=bool),
    })


def _mock_graph():
    return MagicMock()


def _call_build_map(**kwargs):
    defaults = dict(
        event_lat=12.97, event_lng=77.59, severity="LOW",
        barricade_junctions=[], diversion_corridors=[],
        officer_info=_officer_info(), train_df=_empty_df(),
        event_name="Test Event", G=_mock_graph(),
    )
    defaults.update(kwargs)
    return build_map(**defaults)


def test_build_map_no_stations_renders_only_event_marker():
    m = _call_build_map()
    pin_markers = [c for c in m._children.values() if isinstance(c, folium.Marker)]
    assert len(pin_markers) == 1  # event epicenter only


def test_build_map_station_with_coords_renders_circle_marker():
    stations = [
        {"station_code": 1, "station_name": "Cubbon Park PS", "latitude": 12.96,
         "longitude": 77.58, "location_source": "geocoded", "dcp_zone": "Central"},
    ]
    m = _call_build_map(stations=stations)
    circle_markers = [c for c in m._children.values() if isinstance(c, folium.CircleMarker)]
    assert len(circle_markers) == 1


def test_build_map_station_without_coords_is_skipped():
    stations = [
        {"station_code": 2, "station_name": "No Coords PS", "latitude": None,
         "longitude": None, "location_source": "pending", "dcp_zone": "North"},
    ]
    m = _call_build_map(stations=stations)
    circle_markers = [c for c in m._children.values() if isinstance(c, folium.CircleMarker)]
    assert len(circle_markers) == 0


def test_build_map_ranked_station_renders_as_pin_marker():
    stations = [
        {"station_code": 1, "station_name": "Cubbon Park PS", "latitude": 12.96,
         "longitude": 77.58, "location_source": "geocoded", "dcp_zone": "Central"},
    ]
    ranked = [
        {"station_code": 1, "station_name": "Cubbon Park PS", "distance_km": 1.2, "response_min": 3},
    ]
    m = _call_build_map(stations=stations, ranked_stations=ranked)
    pin_markers = [c for c in m._children.values() if isinstance(c, folium.Marker)]
    # event epicenter + 1 ranked station = 2 pin markers
    assert len(pin_markers) == 2


def test_build_map_ranked_station_not_rendered_as_circle():
    stations = [
        {"station_code": 1, "station_name": "Cubbon Park PS", "latitude": 12.96,
         "longitude": 77.58, "location_source": "geocoded", "dcp_zone": "Central"},
    ]
    ranked = [
        {"station_code": 1, "station_name": "Cubbon Park PS", "distance_km": 1.2, "response_min": 3},
    ]
    m = _call_build_map(stations=stations, ranked_stations=ranked)
    circle_markers = [c for c in m._children.values() if isinstance(c, folium.CircleMarker)]
    assert len(circle_markers) == 0  # ranked station shown as pin, not circle


def test_build_map_existing_call_without_stations_still_works():
    # Verify backward compatibility — no stations arg
    m = _call_build_map()
    assert isinstance(m, folium.Map)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_map_station_overlay.py -v
```
Expected: FAIL on tests expecting circle/pin markers (signature doesn't have stations param yet)

- [ ] **Step 3: Extend `build_map()` in `src/map_builder.py`**

Change the function signature from:
```python
def build_map(
    event_lat: float,
    event_lng: float,
    severity: str,
    barricade_junctions: list,
    diversion_corridors: list,
    officer_info: dict,
    train_df: pd.DataFrame,
    event_name: str,
    G: nx.MultiDiGraph,
    corridor: str = "",
) -> folium.Map:
```
to:
```python
def build_map(
    event_lat: float,
    event_lng: float,
    severity: str,
    barricade_junctions: list,
    diversion_corridors: list,
    officer_info: dict,
    train_df: pd.DataFrame,
    event_name: str,
    G: nx.MultiDiGraph,
    corridor: str = "",
    stations: list | None = None,
    ranked_stations: list | None = None,
) -> folium.Map:
```

Then add the station overlay block at the end of `build_map()`, just before the `if len(all_coords) > 1:` fit_bounds call:

```python
    # ── Station overlay ───────────────────────────────────────────────────────
    if stations:
        _SOURCE_COLOR = {
            "geocoded":               "#28a745",
            "zone_centroid_fallback": "#fd7e14",
        }
        _coords = {
            s["station_code"]: (s["latitude"], s["longitude"])
            for s in stations
            if s["latitude"] is not None
        }
        ranked_codes = {s["station_code"] for s in (ranked_stations or [])}

        for s in stations:
            if s["latitude"] is None or s["station_code"] in ranked_codes:
                continue
            folium.CircleMarker(
                location=[s["latitude"], s["longitude"]],
                radius=5,
                color=_SOURCE_COLOR.get(s["location_source"], "#6c757d"),
                fill=True,
                fill_opacity=0.7,
                popup=folium.Popup(
                    f"<b>{s['station_name']}</b><br>{s['dcp_zone']}<br>{s['location_source']}",
                    max_width=200,
                ),
                tooltip=s["station_name"],
            ).add_to(m)

        for rank_idx, s in enumerate(ranked_stations or []):
            coords = _coords.get(s["station_code"])
            if coords is None:
                continue
            folium.Marker(
                location=list(coords),
                popup=folium.Popup(
                    f"<b>#{rank_idx + 1} {s['station_name']}</b><br>"
                    f"{s['distance_km']} km | {s['response_min']} min",
                    max_width=200,
                ),
                tooltip=f"#{rank_idx + 1} {s['station_name']}",
                icon=folium.Icon(color="blue", icon="home"),
            ).add_to(m)
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_map_station_overlay.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add src/map_builder.py tests/test_map_station_overlay.py
git commit -m "feat: add station circle and ranked pin markers to Results map"
```

---

### Task 4: Wire up Plan Event page

**Files:**
- Modify: `pages/1_Plan_Event.py`

**Interfaces:**
- Consumes: `station_store.get_all_stations() -> list[dict]` — all 110 stations with coords
- Consumes: `station_store.rank_stations(lat, lng, top_n=5) -> list[dict]` — top-5 scored stations
- Consumes: `build_map(..., stations=..., ranked_stations=...)` from Task 3

No unit tests for this task — the wiring is a two-line change to a Streamlit page. Verify manually by running the app.

- [ ] **Step 1: Add `station_store` import to `pages/1_Plan_Event.py`**

The file already imports from `src`. Add `station_store` to the existing imports block at the top:

Change:
```python
from src.app_cache import get_road_graph, load_and_train
from src.calendar_intel import get_holiday_info
from src.duration_model import predict_duration
from src.explainer import explain_risk, explain_severity
from src.map_builder import build_map
from src.model import get_knn_neighbors, predict
from src.pipeline import corridor_metadata
from src.recommender import barricade_positions, get_diversions, officer_count
from src.risk_model import predict_risks
```

To:
```python
from src import station_store
from src.app_cache import get_road_graph, load_and_train
from src.calendar_intel import get_holiday_info
from src.duration_model import predict_duration
from src.explainer import explain_risk, explain_severity
from src.map_builder import build_map
from src.model import get_knn_neighbors, predict
from src.pipeline import corridor_metadata
from src.recommender import barricade_positions, get_diversions, officer_count
from src.risk_model import predict_risks
```

- [ ] **Step 2: Pass stations to `build_map()` inside the `if submitted:` block**

In `pages/1_Plan_Event.py`, find the `build_map()` call (around line 181):

```python
    fmap       = build_map(
        lat, lng, severity, barricades, diversions,
        officers, train_df, event_name, graph, corridor=corridor
    )
```

Replace with:

```python
    _all_stations    = station_store.get_all_stations()
    _ranked_stations = station_store.rank_stations(lat, lng, top_n=5)
    fmap             = build_map(
        lat, lng, severity, barricades, diversions,
        officers, train_df, event_name, graph, corridor=corridor,
        stations=_all_stations,
        ranked_stations=_ranked_stations,
    )
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```
pytest tests/ -v
```
Expected: all previously passing tests still pass

- [ ] **Step 4: Commit**

```bash
git add pages/1_Plan_Event.py
git commit -m "feat: overlay all police stations and top-5 ranked on Results Impact Map"
```
