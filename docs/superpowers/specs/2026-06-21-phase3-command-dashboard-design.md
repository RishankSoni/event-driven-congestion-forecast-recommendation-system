# Phase 3: Command Dashboard & Multi-Event Resource Optimizer — Design Spec

**Date:** 2026-06-21
**Context:** GRIDLOCK 2.0 — Phase 3 of a 4-phase product expansion
**Stack:** Python + SQLite + Streamlit + pandas
**Scope:** Cross-event operations dashboard and multi-event station/officer optimizer

---

## Overview

Phase 3 adds operational situational awareness on top of the single-event prediction (Phases 0–1) and station intelligence (Phase 2) layers. A TMC operator running a busy day — multiple rallies, VIP movements, festivals — currently has no unified view. They must open each event individually. Phase 3 fixes this with two pages backed by a new backend module.

| Deliverable | File | Purpose |
|---|---|---|
| Operations store | `src/ops_store.py` | Cross-event queries, conflict detection, multi-event optimization |
| Command Dashboard | `pages/8_Command_Dashboard.py` | TMC home screen — live event overview, conflicts, station load |
| Multi-Event Optimizer | `pages/9_Multi_Event_Optimizer.py` | Pick a date + events → combined deployment with conflict resolution |
| Tests | `tests/test_ops_store.py` | 10 unit tests for ops_store functions |

**No new dependencies. No new SQLite tables.** All data comes from existing `planned_events` and `police_stations` tables.

---

## Data Model (existing tables, no changes)

### `planned_events` columns used by Phase 3
- `event_id`, `event_name`, `corridor`, `zone`, `event_date`, `event_time`
- `latitude`, `longitude`
- `severity`, `congestion_prob`, `law_order_prob`
- `estimated_attendance`, `has_vip`
- `officer_min`, `officer_max`
- `status` — filter: `status NOT IN ('cancelled', 'completed')`

### `police_stations` columns used by Phase 3
- `station_code`, `station_name`, `dcp_zone`, `latitude`, `longitude`, `location_source`
- `capacity_officers`, `capacity_source`

---

## Component 1: `src/ops_store.py`

Single responsibility: cross-event queries and multi-event optimization. No UI code. Reads from `data/events.db` via `DB_PATH` imported from `src.event_store`.

### Functions

```python
def get_today_events() -> list[dict]:
    """Return all non-cancelled/completed events for today (UTC date).
    Each dict is a row from planned_events."""

def get_week_events(days: int = 7) -> list[dict]:
    """Return all non-cancelled/completed events in the next `days` days
    (today inclusive), ordered by event_date, event_time."""

def detect_conflict_pairs(events: list[dict]) -> list[tuple[dict, dict]]:
    """Return all (event_A, event_B) pairs where:
    - |time_A − time_B| ≤ 4 hours (same-day; cross-day not checked), AND
    - haversine(A.lat, A.lng, B.lat, B.lng) ≤ 8.0 km OR A.corridor == B.corridor
    Each pair appears once (A < B by event_id). Events without lat/lng fall back
    to corridor match only. Returns [] if fewer than 2 events provided."""

def get_zone_utilization() -> dict[str, int]:
    """Return {dcp_zone: active_event_count} for all zones with at least one
    non-cancelled/completed event today."""

def optimize_multi_event(event_ids: list[str]) -> dict:
    """Given a list of event_ids, return a combined resource plan:
    {
      "events": [list of event dicts in attendance-desc order],
      "total_officers_min": int,
      "total_officers_max": int,
      "per_event": [
          {
              "event_id": str,
              "event_name": str,
              "stations": [ranked station dicts with allocation],
              "conflict_with": [event_ids of events sharing a top station],
          }
      ],
      "station_conflicts": [
          {
              "station_name": str,
              "claimed_by": [event_ids],
          }
      ],
      "unresolvable": bool,   # True if any conflict couldn't be resolved
    }
    Returns {"events": [], ...} for empty input.
    Events ranked by estimated_attendance descending (highest priority gets first pick of stations).
    Station conflict resolution: when station S appears in top-3 of event A and event B,
    promote the next available station for the lower-priority (lower attendance) event.
    Re-rank the lower-priority event's stations excluding already-claimed stations.
    If fewer than 2 geocoded stations exist, mark unresolvable=True and skip re-ranking."""
```

### Conflict detection detail

`detect_conflict_pairs` uses the same thresholds as `check_conflicts()` in `event_store.py` for consistency:
- Time window: ±4 hours
- Distance cap: 8.0 km haversine
- Corridor match: exact string equality (fallback when lat/lng missing)

The function imports `_haversine_km` from `src.event_store` (already present).

### Multi-event optimization detail

`optimize_multi_event` algorithm:
1. Load full event dicts from DB for given `event_ids`.
2. Sort events by `estimated_attendance` descending (ties broken by `event_time`).
3. For each event in priority order:
   a. Call `station_store.rank_stations(lat, lng, event_date, event_time, top_n=5)`.
   b. Skip the call (return `[]`) if the event has no lat/lng.
   c. Filter out stations already claimed by a higher-priority event.
   d. Call `station_store.allocate_officers(remaining_stations[:3], event.officer_min)`.
   e. Record which stations are now claimed.
4. Build `station_conflicts` list: any station appearing in the *original* top-3 of two or more events.
5. Set `unresolvable=True` if any event ends up with 0 stations after filtering.

---

## Component 2: `pages/8_Command_Dashboard.py`

The TMC operator's opening screen. Shows the state of today's operations at a glance.

### Layout

**Header:** "Command Dashboard — {today's date}"

**Row 1 — 4 metrics (st.columns):**
- Total events today (non-cancelled/completed)
- HIGH severity events today
- Conflict pairs detected (from `detect_conflict_pairs`)
- Geocoded stations available (location_source = 'geocoded' count from police_stations)

**Row 2 — Today's events table:**
`st.dataframe` with columns:

| Column | Source | Notes |
|---|---|---|
| Event | event_name | — |
| Corridor | corridor | — |
| Time | event_time | — |
| Severity | severity | Displayed as text; no color (st.dataframe doesn't support per-cell color) |
| Attendance | estimated_attendance | — |
| Conflicts | derived | Count of conflict pairs involving this event; "⚠ N" if N>0, else "" |
| Status | status | — |

**Row 3 — 7-day pipeline:**
`st.dataframe` of `get_week_events(7)` with columns: Date | Event | Corridor | Severity | Status. Title: "Upcoming 7 Days".

**Refresh:** Single `st.button("↻ Refresh")` at top right — triggers `st.rerun()`. No automatic polling.

**Empty state:** If no events today, show `st.info("No events planned for today.")` in place of the events table.

---

## Component 3: `pages/9_Multi_Event_Optimizer.py`

Answers: "We have three events on Tuesday — how do we staff them?"

### Flow

1. **Date picker** (`st.date_input`) → loads all saved events for that date via `get_week_events` filtered to date.
2. If no events for that date: `st.info("No saved events for this date.")` → stop.
3. **Event selector** (`st.multiselect`) showing event names. User picks 2–5 events.
4. **"Optimize" button** → calls `optimize_multi_event(selected_event_ids)`.
5. **Results — two panels:**

**Panel A: Per-Event Station Assignments**
One expander per event (default expanded). Shows:
- Event name + severity badge
- Table: Station | Zone | Dist (km) | ETA (min) | Officers | ⚠ flag

**Panel B: Combined Summary**
- Total officers min/max (sum across all events)
- Station conflicts list: "⚠ [Station Name] claimed by Event A and Event B — reassigned for Event B"
- If `unresolvable=True`: `st.error("⚠ Insufficient geocoded stations to resolve all conflicts. Run geocoding from Station Registry.")`
- If no conflicts: `st.success("✓ No station conflicts — all events can be staffed independently.")`

### Guard

If fewer than 2 events selected: `st.info("Select at least 2 events to optimize.")` — no Optimize button shown.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| No events saved at all | Dashboard shows "No events planned for today." info box |
| Event has no lat/lng | Excluded from haversine conflict check; corridor-match still applies |
| Geocoding not yet run | Optimizer shows stations=[] per event + unresolvable warning |
| `optimize_multi_event([])` | Returns `{"events": [], "total_officers_min": 0, "total_officers_max": 0, "per_event": [], "station_conflicts": [], "unresolvable": False}` |

---

## Testing: `tests/test_ops_store.py`

10 unit tests. Use the same `_patch_db` + `init_db` + `init_station_db` fixture pattern from existing test files. Insert events via `event_store.save_event()`.

| Test | What it asserts |
|---|---|
| `test_get_today_events_returns_list` | Returns list (may be empty); does not raise |
| `test_get_today_events_filters_status` | Cancelled events excluded |
| `test_get_week_events_respects_days_param` | Event 8 days out excluded when days=7 |
| `test_detect_conflict_pairs_same_corridor` | Two events same corridor, 2h apart → 1 pair |
| `test_detect_conflict_pairs_far_apart_not_flagged` | Two events 20km apart, no shared corridor → 0 pairs |
| `test_detect_conflict_pairs_different_day_not_flagged` | Events on different dates → 0 pairs |
| `test_detect_conflict_pairs_requires_two_events` | Single event → 0 pairs |
| `test_get_zone_utilization_counts_active` | Zone with 2 events today → count=2 |
| `test_optimize_multi_event_empty_returns_empty` | `optimize_multi_event([])` → unresolvable=False, empty lists |
| `test_optimize_multi_event_sums_officers` | Two events with officer_min=5, officer_max=8 each → total_min=10, total_max=16 |

---

## File Map Summary

| Action | File | Notes |
|---|---|---|
| Create | `src/ops_store.py` | Backend only — no Streamlit imports |
| Create | `pages/8_Command_Dashboard.py` | Reads from ops_store + station_store |
| Create | `pages/9_Multi_Event_Optimizer.py` | Reads from ops_store + station_store |
| Create | `tests/test_ops_store.py` | 10 unit tests |

No modifications to existing files except `src/app_cache.py` is NOT touched — `ops_store` has no init function (reads on demand).

---

## What's Explicitly Out of Scope

- Historical analytics / trend charts (no time dimension in current SQLite data beyond event dates)
- Shift/duty roster generation (requires personnel availability data not in the system)
- Real-time polling / auto-refresh (Streamlit threading limitations; manual refresh is correct for demo)
- Push notifications or alerts
- Any new pip dependencies
