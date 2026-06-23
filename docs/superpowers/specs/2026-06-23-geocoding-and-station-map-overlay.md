# Geocoding All Stations + Results Map Overlay

**Date:** 2026-06-23  
**Status:** Approved

## Problem

110 police stations are seeded from CSV. Currently only 20 are geocoded, 36 have rough zone-centroid fallback coordinates, and 54 are still pending (no coordinates). The Results page map shows no station markers at all.

## Goals

1. Geocode all 54 pending stations using a multi-strategy Nominatim cascade.
2. Retry the 36 zone-centroid-fallback stations with the same cascade to replace rough centroids with real coordinates where possible.
3. Overlay all stations on the Results page Impact Map, highlighting the top-5 recommended stations.

## Geocoding Design

### Helper: `_try_geocode_strategies()`

New function in `src/station_store.py`. Tries up to 3 Nominatim queries per station in sequence, returning `(lat, lng)` on first success or `None` if all fail:

1. `"{station_name} Police Station, {acp_zone}, Bangalore, Karnataka, India"`
2. `"{station_name} Police Station, Bangalore, Karnataka, India"`
3. `"{station_name}, Bangalore, India"`

The cascade goes from most specific to least specific so Nominatim has the best chance of resolving each station unambiguously.

### Update: `geocode_all_stations()`

Replace the single-query call with `_try_geocode_strategies()`. Logic otherwise unchanged — successful geocodes are saved immediately, and `_apply_zone_centroid_fallback()` runs at the end for any that still fail all three queries.

### New: `_retry_fallback_stations(geocoder, progress_callback)`

Fetches all stations with `location_source='zone_centroid_fallback'`, runs `_try_geocode_strategies()` on each. On success, updates `latitude`, `longitude`, and `location_source='geocoded'`. Called at the end of `geocode_all_stations()` after the pending pass completes.

Rate limiting: same `RateLimiter(min_delay_seconds=1)` as the existing Nominatim setup. Worst case ~90 stations × 3 queries = ~4.5 minutes, typical much less since most succeed on first or second query.

The existing Geocoding tab in `6_Station_Registry.py` with its progress bar works unchanged.

## Map Overlay Design

### `src/map_builder.py` — `build_map()` signature

```python
def build_map(
    event_lat, event_lng, severity, barricade_junctions,
    diversion_corridors, officer_info, train_df, event_name, G,
    corridor="",
    stations=None,          # list[dict] from station_store.get_all_stations()
    ranked_stations=None,   # list[dict] from station_store.rank_stations()
) -> folium.Map:
```

### Station rendering

- **All stations** (those with coordinates): `CircleMarker` radius 5
  - Green `#28a745` — `geocoded`
  - Orange `#fd7e14` — `zone_centroid_fallback`
  - Gray `#6c757d` — anything else
  - Popup: station name, zone, location source
- **Top-5 ranked stations**: `Marker` with blue shield icon rendered on top
  - Popup: `#N — {station_name} | {distance_km} km | {response_min} min`
  - Tooltip: station name

Stations without coordinates are skipped silently.

### `pages/1_Plan_Event.py`

After `lat, lng = corridor_metadata(...)`:

```python
from src import station_store
_all_stations    = station_store.get_all_stations()
_ranked_stations = station_store.rank_stations(lat, lng, top_n=5)
fmap = build_map(..., stations=_all_stations, ranked_stations=_ranked_stations)
```

No changes to `pages/2_Results.py` — it renders the pre-built `fmap` from session state.

## Files Changed

| File | Change |
|---|---|
| `src/station_store.py` | Add `_try_geocode_strategies()`, update `geocode_all_stations()`, add `_retry_fallback_stations()` |
| `src/map_builder.py` | Add `stations` and `ranked_stations` params to `build_map()`, render station markers |
| `pages/1_Plan_Event.py` | Call `get_all_stations()` + `rank_stations()`, pass to `build_map()` |

## Non-Goals

- No changes to the geocoding UI in `6_Station_Registry.py`
- No hardcoded coordinate table
- No new external dependencies beyond `geopy` (already used)
