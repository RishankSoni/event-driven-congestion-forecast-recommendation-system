# Phase 2: Station Intelligence — Design Spec

## Overview

Phase 2 adds two capabilities to GRIDLOCK 2.0:

1. **Police Station Registry** — geocode all 110 Bengaluru police stations, enrich with BTP traffic PI signal, persist to SQLite with editable capacity fields.
2. **Station Ranking + Deployment Planning** — for any planned event, rank nearby stations by distance, workload, and BTP signal; generate a full operational deployment plan with narrative briefing.

This spec covers features 3 (Intelligent Station Ranking) and 4 (AI Resource Planning Engine) from the original 10-feature roadmap.

---

## Data Sources

| Source | Fields used | Provenance |
|---|---|---|
| `bangalore_city_police_stations_2012.csv` | station_code, Station (name+address+phone), Unit, DCP, ACP | Existing file in repo root |
| OpenCity BTP Officers CSV | Officer, Division, Subdivision, Traffic Police Station, Phone, Mobile, Email | Downloaded at geocoding time from OpenCity |
| `data/events.db` → `planned_events` | police_station, event_date, event_time, status | Phase 1 output |

No real capacity (personnel/vehicle count) data exists in any public dataset for these stations. Capacity fields are operator-maintained with synthetic defaults; see provenance rules below.

---

## New SQLite Tables

Both tables live in `data/events.db` alongside `planned_events`.

### `police_stations`

```sql
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
);
```

**`location_source`** values: `'pending'` | `'geocoded'` | `'zone_centroid_fallback'`

**`has_btp_pi`**: 1 if a "Police Inspector Traffic" row in the BTP Officers CSV matches this station. `btp_match_confidence` = 1.0 for exact name match, difflib ratio (0.7–1.0) for fuzzy match, NULL for no match. `has_btp_pi = 0` means "not confirmed in BTP CSV" — not "definitely absent."

**`capacity_source`** values: `'default'` | `'manual'`. Default capacity (25 officers, 3 vehicles) is synthetic — it must never silently constrain real allocation decisions. See allocation rules in Ranking Engine section.

### `zone_centroids`

```sql
CREATE TABLE IF NOT EXISTS zone_centroids (
    dcp_zone   TEXT PRIMARY KEY,
    latitude   REAL NOT NULL,
    longitude  REAL NOT NULL
);
```

Populated from `location_source = 'geocoded'` stations only (never from fallback stations, to avoid compounding approximation errors). Replaces the module-level `_ZONE_CENTROIDS` dict in `src/event_store.py` — `_build_zone_centroids()` reads from this table when it exists, falls back to empty dict otherwise (Phase 1 compatibility preserved).

---

## New Dependency

`geopy>=2.4.0` — added to `requirements.txt`. Used for `Nominatim` geocoder and `RateLimiter` wrapper only.

---

## Geocoding Pipeline (`src/station_store.py`)

### Address Cleaning

Each row's `Station` field contains name + address + phone embedded:
```
"Cubbon Park # 7 cubbon park police station kasturba road bangalore 560001Ph no. 080-22942675"
```

Two-pass cleaning:
1. Strip from `Ph no.` onward: `re.sub(r'Ph\s*no\..*', '', text, flags=re.IGNORECASE).strip()`
2. Station name = first token(s) before the address body. Heuristic: text before the first occurrence of a known address keyword (`road`, `nagar`, `main`, `cross`, `layout`, `colony`, `street`, `gate`, `circle`), lowercased. Falls back to the first two capitalised words if no keyword found.

Result for example above: `station_name = "Cubbon Park"`, `address_clean = "# 7 cubbon park police station kasturba road bangalore 560001"`

### Geocode Loop

```python
def geocode_all_stations(progress_callback=None) -> dict:
    """Returns {"geocoded": n, "fallback": n, "pending": n}"""
```

- Reads all stations where `location_source = 'pending'` from `police_stations` table
- For each: query Nominatim with `f"{address_clean}, Bangalore, India"`, 1 req/s via `RateLimiter`
- Hit → upsert `latitude`, `longitude`, `location_source = 'geocoded'`, `geocoded_at = now()`
- Miss → leave as `'pending'`; zone centroid applied in post-pass (see below)
- Calls `progress_callback(current, total)` each iteration for `st.progress` updates
- After all attempts: compute zone centroid from geocoded-only stations per DCP zone, apply to remaining pending stations as `location_source = 'zone_centroid_fallback'`
- Recomputes and upserts `zone_centroids` table from geocoded stations only

### BTP Enrichment

Run after geocode loop:
- Download BTP Officers CSV from OpenCity URL (hardcoded in `station_store.py`)
- Filter rows where `Officer == "Police Inspector Traffic"`
- For each BTP row, match `Traffic Police Station` to `station_name` using:
  1. Exact match (case-insensitive) → `has_btp_pi = 1`, `btp_match_confidence = 1.0`
  2. `difflib.SequenceMatcher` ratio > 0.7 → `has_btp_pi = 1`, `btp_match_confidence = ratio`
  3. No match → station keeps `has_btp_pi = 0`, `btp_match_confidence = NULL`

### Idempotency

`geocode_all_stations()` skips rows where `location_source != 'pending'`. Re-running only processes unresolved stations. A "Reset station" action in the admin UI sets `location_source = 'pending'` for a single row to allow re-geocoding.

### Initialisation

`init_station_db()` — called from `src/app_cache.py` alongside existing `event_store.init_db()`. Creates both tables and seeds `police_stations` from the CSV if the table is empty (all rows inserted with `location_source = 'pending'`).

---

## Ranking Engine (`src/station_store.py`)

### Scoring

```python
_RANK_WEIGHTS = {
    "btp_boost":       2.0,   # subtracted — BTP PI equiv. to being 2 km closer
    "workload_penalty": 1.5,  # added per active/planned event assigned to station
}

def rank_stations(
    event_lat: float,
    event_lng: float,
    event_date: str,    # ISO "YYYY-MM-DD"
    event_time: str,    # "HH:MM"
    top_n: int = 5,
) -> list[dict]
```

For each station where `latitude IS NOT NULL`:

```
distance_km = haversine(event_lat/lng, station_lat/lng)
workload    = COUNT(planned_events WHERE police_station = station_name
                    AND status IN ('planned', 'active')
                    AND event datetime within ±4h of input)
score       = distance_km
            - (has_btp_pi × btp_boost)
            + (workload × workload_penalty)
```

Lower score = better. Returns `[]` if fewer than 2 stations are geocoded (graceful degradation).

Each returned dict:
```python
{
    "station_name":         str,
    "station_code":         int,
    "dcp_zone":             str,
    "acp_zone":             str,
    "distance_km":          float,
    "workload":             int,
    "has_btp_pi":           int,          # 0 or 1
    "btp_match_confidence": float | None,
    "capacity_officers":    int,
    "capacity_vehicles":    int,
    "capacity_source":      str,          # 'default' | 'manual'
    "score":                float,
    "response_min":         int,          # round(distance_km / 30.0 * 60)
    "officers_allocated":   int,          # set by allocate_officers()
    "allocation_capped":    bool,         # True if cap was applied (manual only)
    "capacity_unconfirmed": bool,         # True if capacity_source == 'default'
}
```

### Officer Allocation

```python
def allocate_officers(stations: list[dict], total_officers: int) -> list[dict]:
```

Inverse-distance weighting:
```
weight_i = (1 / distance_i) / Σ(1 / distance_j)
raw_i    = round(total_officers × weight_i)
```

Capacity cap — applied only when `capacity_source == 'manual'`:
```python
if s["capacity_source"] == "manual":
    s["officers_allocated"]   = min(raw, s["capacity_officers"])
    s["allocation_capped"]    = raw > s["capacity_officers"]
    s["capacity_unconfirmed"] = False
else:
    s["officers_allocated"]   = raw     # no cap on unconfirmed defaults
    s["allocation_capped"]    = False
    s["capacity_unconfirmed"] = True    # triggers ⚠ badge in UI
```

Both branches always set all three keys — no `KeyError` risk on direct lookup downstream.

---

## Deployment Planning Engine (`src/deployment_planner.py`)

### Signature

```python
def build_deployment_plan(
    event: dict,              # name, type, severity, corridor, estimated_attendance,
                              # has_vip, is_route_event, law_order_prob,
                              # congestion_prob, event_date, event_time,
                              # expected_duration_h
    ranked_stations: list[dict],   # output of rank_stations + allocate_officers
    officers: dict,           # total_min, total_max from existing recommender
    barricades: list[str],    # from existing recommender
    diversions: list[str],    # from existing recommender
) -> dict
```

### Output Structure

```python
{
    "briefing":           str,          # narrative paragraph
    "stations":           list[dict],   # ranked_stations (top 5)
    "total_officers_min": int,
    "total_officers_max": int,
    "barricade_positions": list[str],
    "diversion_routes":   list[str],
    "qrt_recommended":    bool,
    "qrt_units":          int,          # 0, 1, or 2
    "medical_posts":      int,          # 0, 1, or 2
    "surveillance_points": list[str],   # barricade positions reused
    "vip_protocol":       bool,
    "timeline":           list[dict],   # {"offset_min": int, "label": str}
}
```

### Computed Fields

**QRT:**
- `qrt_recommended = law_order_prob > 0.5 or severity == "HIGH"`
- `qrt_units = 2 if severity == "HIGH" and attendance > 5000 else 1 if qrt_recommended else 0`

**Medical posts:**
- `0` if attendance < 500
- `1` if 500 ≤ attendance ≤ 2000
- `2` if attendance > 2000

**Surveillance:** barricade positions reused as observer/camera points (same locations).

**Timeline** — relative to event start:

| offset_min | label |
|---|---|
| −120 | Station briefing and resource assembly |
| −60 | Deploy barricades and route closures |
| −30 | All units in position, radio check |
| 0 | Event start — active monitoring |
| +duration | Begin staged withdrawal |

`duration = round(event.get("expected_duration_h", 2.0) * 60)`

### Narrative Generation (`_build_briefing`)

Assembles one paragraph from sentence templates. No LLM — deterministic, fully testable.

**Attendance bands:**
- `< 500` → "small gathering"
- `500–2000` → "moderate crowd"
- `2000–10000` → "large crowd"
- `> 10000` → "mass event"

**Template (all sentences conditionally included):**

```
[OPENER]    "For a {severity} severity {event_type} on {corridor} with an estimated
             {attendance_band} ({attendance:,} attendees),"
[DEPLOY]    "deploy {total_min}–{total_max} officers across {n_stations} station(s)."
[PRIMARY]   "Primary response from {s1.name} ({s1.distance_km:.1f} km,
             {s1.officers_allocated} officers, ETA {s1.response_min} min)"
[SECONDARY] "and {s2.name} ({s2.distance_km:.1f} km, {s2.officers_allocated} officers,
             ETA {s2.response_min} min)."  [only if len(stations) >= 2]
[BARRICADE] "Position {n} barricade(s) at key junctions."  [only if barricades]
[QRT]       "Law & order risk is elevated — {qrt_units} QRT unit(s) on standby."
             [only if qrt_recommended]
[MEDICAL]   "Establish {medical_posts} medical post(s) for crowd safety."
             [only if medical_posts > 0]
[VIP]       "VIP protocol active — route pre-clearance required."
             [only if vip_protocol]
```

---

## UI

### `pages/2_Results.py` — modification

After the existing "Action Plan" section, add "Recommended Stations" subsection:

- Calls `rank_stations()` + `allocate_officers()` using `save_data` lat/lng from session state
- If lat/lng absent: `st.caption("No location provided — station ranking unavailable")`
- If `rank_stations()` returns `[]`: `st.caption("Station geocoding not yet run — visit Station Registry")`
- Otherwise: `st.dataframe` of top 3 stations — columns: Station | Zone | Dist (km) | ETA (min) | Officers | ⚠
  - ⚠ cell: "Uncapped" if `capacity_unconfirmed`, "Capped" if `allocation_capped`, blank otherwise
- `st.page_link("pages/7_Deployment_Plan.py", label="View Full Deployment Plan →")`
- Stores `st.session_state["deployment_data"] = {"event": r, "stations": ranked, "plan": plan}` before link

### `pages/7_Deployment_Plan.py` — new page

Guard: if `"deployment_data"` not in `st.session_state` → warning + `st.page_link` back to Results.

Sections (full-width layout):
1. **Header** — event name, date/time, severity badge, corridor, status
2. **Briefing** — `st.info()` with narrative paragraph
3. **Station Deployment** — `st.dataframe`: Station | Zone | Dist (km) | ETA (min) | Officers | Vehicles | BTP PI | Capacity
   - Officers cell prefixed with `⚠` if `capacity_unconfirmed`
4. **Barricades & Diversions** — two columns, same display logic as Results page
5. **Support Requirements** — `st.metric` row: QRT units | Medical posts | Surveillance points | VIP protocol
6. **Timeline** — `st.table` of offset/label rows
7. **Footer** — `st.download_button` (full plan as CSV) + `st.page_link` back to Results

### `pages/6_Station_Registry.py` — new admin page

Three tabs:

**Tab 1 — Map**: Folium map of all 110 stations coloured by `location_source`:
- Green = `geocoded`, Orange = `zone_centroid_fallback`, Grey = `pending`
- Marker popup: station name, zone, capacity, BTP flag, match confidence

**Tab 2 — Stations Table**: `st.data_editor` — editable: `capacity_officers`, `capacity_vehicles`. Read-only: all other columns.
- `⚠ Default` badge in Capacity column when `capacity_source = 'default'`
- `✓ BTP` badge with match confidence decimal when `has_btp_pi = 1`
- On save: upserts changed rows to SQLite, sets `capacity_source = 'manual'`

**Tab 3 — Geocoding**: Summary metrics (geocoded / fallback / pending counts). "Geocode All Stations" button with `st.progress` bar and per-station `st.empty()` status line. Button disabled while running. Individual station reset available via row action in the table.

---

## Files Changed

| Action | File |
|---|---|
| Create | `src/station_store.py` |
| Create | `src/deployment_planner.py` |
| Create | `pages/6_Station_Registry.py` |
| Create | `pages/7_Deployment_Plan.py` |
| Modify | `pages/2_Results.py` |
| Modify | `src/event_store.py` |
| Modify | `src/app_cache.py` |
| Modify | `requirements.txt` |
| Create | `tests/test_station_store.py` |
| Create | `tests/test_deployment_planner.py` |

---

## Tests

### `tests/test_station_store.py`

| Test | Verifies |
|---|---|
| `test_init_creates_tables` | Both tables created idempotently |
| `test_seed_from_csv_inserts_110_rows` | All stations seeded from CSV |
| `test_address_clean_strips_phone` | `Ph no.` and everything after removed |
| `test_station_name_extraction` | "Cubbon Park" extracted from raw Station field |
| `test_geocode_skips_non_pending` | Already-geocoded station not re-queried |
| `test_zone_centroid_fallback_applied` | Ungeocoded station gets centroid lat/lng |
| `test_zone_centroid_from_geocoded_only` | Fallback stations excluded from centroid computation |
| `test_btp_exact_match_sets_flag` | Exact name match → `has_btp_pi = 1`, confidence = 1.0 |
| `test_btp_fuzzy_match_sets_flag` | Ratio > 0.7 → `has_btp_pi = 1`, confidence = ratio |
| `test_btp_no_match_leaves_zero` | No match → `has_btp_pi = 0`, confidence = NULL |
| `test_rank_stations_distance_ordering` | Nearer station ranked higher |
| `test_rank_stations_btp_boost` | BTP station ranked above equidistant non-BTP |
| `test_rank_stations_workload_penalty` | High-workload station ranked lower |
| `test_rank_stations_returns_empty_if_few_geocoded` | `[]` when < 2 geocoded |
| `test_allocate_officers_sums_to_total` | Allocated officers sum ≈ total (rounding ±1) |
| `test_allocate_cap_applied_only_for_manual` | Default stations uncapped; manual stations capped |
| `test_allocate_both_branches_set_all_keys` | `capacity_unconfirmed` and `allocation_capped` always present |
| `test_capacity_update_sets_source_manual` | Editing capacity sets `capacity_source = 'manual'` |

### `tests/test_deployment_planner.py`

| Test | Verifies |
|---|---|
| `test_briefing_contains_severity` | Narrative includes severity label |
| `test_briefing_contains_station_name` | Primary station name in paragraph |
| `test_briefing_qrt_above_threshold` | QRT sentence present when `law_order_prob > 0.5` |
| `test_briefing_no_qrt_below_threshold` | QRT sentence absent when low risk |
| `test_briefing_medical_large_crowd` | Medical sentence present when attendance > 2000 |
| `test_briefing_no_medical_small_crowd` | Medical sentence absent when < 500 |
| `test_briefing_vip_protocol` | VIP sentence present when `has_vip = 1` |
| `test_qrt_units_high_severity_large` | 2 units when HIGH + > 5000 |
| `test_qrt_units_high_severity_small` | 1 unit when HIGH + ≤ 5000 |
| `test_timeline_contains_five_entries` | Timeline has T−120/−60/−30/0/+duration |
| `test_plan_structure_keys` | All required keys present in output dict |

---

## Constraints

- Nominatim rate limit: 1 request/second (enforced by `geopy.extra.rate_limiter.RateLimiter`)
- Nominatim usage policy: user-agent must identify the application (`"gridlock2-geocoder"`)
- BTP CSV download uses `requests` (already available via existing dependencies)
- `geopy>=2.4.0` is the only new dependency
- `has_btp_pi = 0` means "not confirmed in BTP CSV data" — never display as "No BTP PI"
- Capacity defaults (25 officers, 3 vehicles) must never silently cap allocation — only `capacity_source = 'manual'` rows are capped
- Zone centroids are computed from `location_source = 'geocoded'` stations only
- `rank_stations()` returns `[]` (not an exception) when < 2 stations are geocoded
