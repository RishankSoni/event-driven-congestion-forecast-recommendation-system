# Phase 1: Foundation + Event Management

**Date:** 2026-06-21
**Context:** GRIDLOCK 2.0 — Phase 1 of a 4-phase product expansion
**Stack:** Python + SQLite + Streamlit + streamlit-calendar
**Scope:** SQLite persistence layer, Event Calendar page, Event Repository page

---

## Overview

Phase 1 adds a persistent event store (SQLite) and two new Streamlit pages — an Event Calendar and an Event Repository — on top of the existing prediction workflow. The ML training pipeline and CSV corpus are unchanged. The existing Plan Event form (pages/1_Plan_Event.py) and Results dashboard (pages/2_Results.py) are minimally modified: the Results page gains a Save button that writes to SQLite after prediction.

| Component | New / Modified | Risk |
|---|---|---|
| `src/event_store.py` | New | Medium |
| `planned_events` SQLite table | New | Low |
| `pages/2_Results.py` | Modified — Save button + conflict warning | Low |
| `pages/4_Event_Calendar.py` | New | Low |
| `pages/5_Event_Repository.py` | New | Low |

---

## Architecture

### Data flow

```
pages/1_Plan_Event.py
  └── user submits form → prediction runs (unchanged)
  └── st.switch_page("pages/2_Results.py")

pages/2_Results.py
  └── renders prediction results (unchanged)
  └── [Save to Event Calendar] button
        ├── event_store.check_conflicts(event_data) → conflict list
        ├── if conflicts → st.warning with "Save anyway" / "Review conflicts"
        └── event_store.save_event(event_data)     → event_id (UUID4)

pages/4_Event_Calendar.py
  └── event_store.list_events(date_from, date_to)
  └── streamlit-calendar component (month/week/day views)

pages/5_Event_Repository.py
  └── event_store.list_events(filters...)
  └── st.dataframe + sidebar filters + detail expander
```

### What stays unchanged

- `data/events.csv` — still the sole ML training corpus
- `src/app_cache.py` — `load_and_train()` unchanged
- `pages/1_Plan_Event.py` — form logic unchanged
- All existing src/ modules — untouched

### New dependency

```
streamlit-calendar>=0.6.0
```

Add to `requirements.txt`. This wraps FullCalendar.js and provides native month/week/day view switching with color-coded events.

---

## Component 1 — `src/event_store.py`

Single module owning all SQLite interaction. No other file touches the DB directly.

### DB location

```python
DB_PATH = Path("data/events.db")
```

Created on first call to `init_db()`.

### Schema

```sql
CREATE TABLE IF NOT EXISTS planned_events (
    event_id               TEXT PRIMARY KEY,
    event_name             TEXT NOT NULL,
    event_type             TEXT NOT NULL,        -- "planned" | "unplanned"
    event_cause            TEXT NOT NULL,
    event_category         TEXT,                 -- Rally, Religious, Sports, VIP, etc.
    corridor               TEXT,
    zone                   TEXT,
    police_station         TEXT,
    junction               TEXT,
    organizer_name         TEXT,
    event_date             TEXT NOT NULL,        -- YYYY-MM-DD
    event_time             TEXT NOT NULL,        -- HH:MM
    expected_duration_h    REAL,
    estimated_attendance   INTEGER,
    has_vip                INTEGER DEFAULT 0,    -- 0/1
    is_route_event         INTEGER DEFAULT 0,
    requires_road_closure  INTEGER DEFAULT 0,
    route_start            TEXT,
    route_end              TEXT,
    latitude               REAL,
    longitude              REAL,
    severity               TEXT,                 -- LOW / MEDIUM / HIGH
    severity_conf          REAL,
    congestion_prob        REAL,
    law_order_prob         REAL,
    duration_label         TEXT,
    officer_min            INTEGER,
    officer_max            INTEGER,
    barricades_json        TEXT,                 -- JSON array of junction names
    diversions_json        TEXT,                 -- JSON array of corridor names
    holiday_name           TEXT,
    holiday_risk_tier      INTEGER,
    feature_vector_json    TEXT,                 -- JSON dict of 20 prediction features
    shap_drivers_json      TEXT,                 -- JSON array of top-5 SHAP drivers (frozen at save)
    status                 TEXT DEFAULT 'planned', -- planned / active / completed / cancelled
    created_at             TEXT NOT NULL,        -- ISO 8601
    updated_at             TEXT NOT NULL
);
```

**Design decisions embedded in schema:**
- `feature_vector_json`: stores the 20-feature input dict so predictions can be recomputed against any future model version.
- `shap_drivers_json`: frozen top-5 SHAP drivers at save time for audit. The event detail view shows this by default with a "Recompute with current model" button that calls `explain_severity()` on demand.
- `latitude`/`longitude`: nullable. Used by the 4-branch conflict check.
- All timestamps are ISO 8601 TEXT strings — SQLite has no native datetime type.

### Public interface

```python
def init_db() -> None:
    """Create DB and tables if not exist. Called once at app startup in app_cache.py."""

def save_event(event_data: dict) -> str:
    """Insert event. Returns event_id (UUID4 string). Raises ValueError on duplicate."""

def get_event(event_id: str) -> dict | None:
    """Fetch single event by ID. Returns None if not found."""

def list_events(
    date_from: str | None = None,     # YYYY-MM-DD
    date_to: str | None = None,
    corridor: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """Return filtered events ordered by event_date ASC, event_time ASC."""

def update_status(event_id: str, status: str) -> None:
    """Update event status. Valid values: planned / active / completed / cancelled."""

def check_conflicts(event_data: dict) -> tuple[list[dict], str]:
    """
    4-branch conflict detection.
    Returns (conflicting_events, precision_note).
    precision_note is "" for full-precision checks,
    or a human-readable qualifier for degraded branches.
    """
```

### Conflict check — 4-branch logic

`check_conflicts` resolves location precision in order, then queries overlapping events within a ±4-hour window.

```
Branch 1 — corridor present:
  WHERE corridor = :corridor
    AND ABS(julianday(event_date || 'T' || event_time)
          - julianday(:event_date || 'T' || :event_time)) * 24 <= 4
  precision_note = ""

Branch 2 — zone present, no corridor:
  WHERE zone = :zone
    AND time_overlap (±4h, same as above)
  Post-filter in Python:
    keep only rows where haversine(row.lat, row.lng, event.lat, event.lng) <= 8.0 km
    if zone has no geocoded centroid → skip distance cap, set:
      precision_note = "Location precision unavailable for [zone] — conflict
                        detection is time-window only"

Branch 3 — lat/lng present, no corridor or zone:
  Query all events with lat/lng within the time window
  Post-filter: haversine distance <= 3.0 km
  precision_note = ""

Branch 4 — no location data:
  Return ([], "")
  Log: logger.warning("conflict check skipped — event has no location data")
```

**Zone centroid lookup** (used in Branch 2 when event has zone but no lat/lng):

Built at module load time from `bangalore_city_police_stations_2012.csv`, filtering to rows where `location_source = 'geocoded'` only. Grouped by DCP division. If a division has zero geocoded stations, it gets no entry — Branch 2 drops the distance cap for that division and surfaces the precision qualifier.

```python
_ZONE_CENTROIDS: dict[str, tuple[float, float]] = _build_zone_centroids()
# e.g. {"Central Division, Bangalore City": (12.978, 77.592), ...}
```

---

## Component 2 — `pages/2_Results.py` modifications

Two additions below the existing Export Plan (CSV) button:

### Conflict warning (conditional)

```python
conflicts, precision_note = event_store.check_conflicts(event_data)
if conflicts:
    msg = f"⚠ {len(conflicts)} event(s) already planned on this corridor within 4 hours."
    if precision_note:
        msg += f"\n_{precision_note}_"
    st.warning(msg)
    col1, col2 = st.columns(2)
    with col1:
        save_anyway = st.button("Save anyway")
    with col2:
        if st.button("Review conflicts"):
            st.switch_page("pages/5_Event_Repository.py")
            # Repository pre-filters to corridor + date on arrival via query params
else:
    save_anyway = True  # no conflicts, show save button directly
```

### Save button

```python
if save_anyway:
    if "event_saved_id" not in st.session_state:
        if st.button("💾 Save to Event Calendar"):
            eid = event_store.save_event(_build_event_data(st.session_state))
            st.session_state["event_saved_id"] = eid
            st.success(f"Event saved — ID {eid[:8]}…")
    else:
        st.button("✓ Saved", disabled=True)
```

`_build_event_data(session_state)` assembles the full dict from session state, including frozen SHAP drivers from `st.session_state["shap_drivers"]` (already computed and stored there by the existing prediction flow).

---

## Component 3 — `pages/4_Event_Calendar.py`

### Layout

```
┌─ Event Calendar ──────────────────────────────────────────────────────────┐
│  [← Month]  June 2026  [Month →]     [Month | Week | Day]                 │
│                                                                            │
│  streamlit-calendar component                                              │
│  (FullCalendar.js, color-coded events)                                     │
│                                                                            │
│  ── Event Detail (appears below calendar on click) ──                     │
│  Event Name     │  Severity  │  Corridor  │  Date/Time  │  Status         │
│  Officers       │  Congestion risk  │  Law & Order risk  │  Duration      │
│  Why HIGH? [frozen SHAP drivers — expanded]                               │
│  [Recompute with current model ▶]                                         │
│  [Mark Active]  [Mark Completed]  [Cancel Event]                          │
└────────────────────────────────────────────────────────────────────────────┘
```

### Color coding

| Condition | Color |
|---|---|
| severity = HIGH | `#dc3545` (red) |
| severity = MEDIUM | `#fd7e14` (orange) |
| severity = LOW | `#28a745` (green) |
| severity = None (not yet predicted) | `#6c757d` (grey) |

### Calendar event format (streamlit-calendar)

```python
{
    "title": event["event_name"],
    "start": f"{event['event_date']}T{event['event_time']}:00",
    "end":   _compute_end(event["event_date"], event["event_time"],
                          event["expected_duration_h"]),
    "color": _severity_color(event["severity"]),
    "id":    event["event_id"],
}
```

`_compute_end` adds `expected_duration_h` to start; defaults to +2h if duration is null.

### Conflict overlay

Events that share a corridor+date with another event are rendered with a dashed border (via `className: "conflict-event"` in the calendar options). A legend below the calendar explains: `░ Possible conflict with another event on same corridor`.

### Date range loading

Calendar loads events for the visible month on mount and re-fetches when the user navigates months. Uses `event_store.list_events(date_from, date_to)`.

---

## Component 4 — `pages/5_Event_Repository.py`

### Layout

```
┌─ Event Repository ─────────────────────────────────────────────────────────┐
│  SIDEBAR FILTERS                │  MAIN TABLE                              │
│  ─────────────────────          │  ──────────────────────────────────────  │
│  Date range                     │  st.dataframe (sortable, paginated)      │
│  Corridor (multiselect)         │  Columns:                                │
│  Event Type                     │    Event ID (short), Name, Type, Cause,  │
│  Risk Level (severity)          │    Corridor, Date, Time, Severity,       │
│  Status                         │    Congestion%, Law&Order%, Status       │
│                                 │                                          │
│                                 │  ── Detail Expander (on row select) ──  │
│                                 │  Full event record + frozen SHAP         │
│                                 │  [Recompute] [Mark Active/Complete/Cancel]│
└─────────────────────────────────┴──────────────────────────────────────────┘
```

### Filters

| Filter | Widget | Default |
|---|---|---|
| Date range | `st.date_input` (range) | last 30 days to +90 days |
| Corridor | `st.multiselect` | all |
| Event type | `st.selectbox` | All / Planned / Unplanned |
| Risk level | `st.multiselect` | all |
| Status | `st.multiselect` | planned, active |

### Row selection → detail

Streamlit's `st.dataframe` `on_select` callback (Streamlit ≥ 1.35). On row click, an `st.expander` below the table opens with the full event record, frozen SHAP explanation, and status action buttons.

---

## `app_cache.py` change

Add `event_store.init_db()` call at the top of `load_and_train()`:

```python
from src import event_store
event_store.init_db()   # no-op if DB already exists
```

---

## File Change Summary

| File | Change |
|---|---|
| `src/event_store.py` | New — DB init, CRUD, 4-branch conflict check |
| `data/events.db` | New — created at runtime, git-ignored |
| `pages/2_Results.py` | Save button, conflict warning, frozen SHAP assembly |
| `pages/4_Event_Calendar.py` | New — streamlit-calendar, color-coded, detail panel |
| `pages/5_Event_Repository.py` | New — filterable table, detail expander, status actions |
| `src/app_cache.py` | Add `event_store.init_db()` call |
| `requirements.txt` | Add `streamlit-calendar>=0.6.0` |
| `.gitignore` | Add `data/events.db` |

**Not touched:** `src/model.py`, `src/pipeline.py`, `src/recommender.py`, `src/risk_model.py`, `src/explainer.py`, `src/road_network.py`, `src/map_builder.py`, `src/duration_model.py`, `src/calendar_intel.py`, `pages/1_Plan_Event.py`, `pages/3_Post_Event_Report.py`

---

## Success Criteria

| Feature | Pass condition |
|---|---|
| DB init | `data/events.db` created on first app load; schema matches spec |
| Save event | Clicking Save on Results page writes all fields including `feature_vector_json` and `shap_drivers_json` |
| Double-save guard | Second click on Save produces no duplicate row |
| Conflict detection — corridor branch | Two events on same corridor within 2h → warning shown |
| Conflict detection — zone branch | Two events in same zone, 5km apart → warning shown |
| Conflict detection — zone branch distance cap | Two events in same zone, 20km apart → no warning |
| Conflict detection — zone qualifier | Zone with no geocoded stations → qualifier text shown |
| Conflict detection — no-location | Event with no corridor/zone/lat/lng → no warning, no crash |
| Calendar view | Events appear color-coded; month/week/day views switch correctly |
| Calendar detail | Clicking event shows frozen SHAP; Recompute button regenerates live SHAP |
| Repository filters | Date/corridor/type/risk/status filters each narrow the table correctly |
| Status update | Marking an event Active/Completed/Cancelled persists and refreshes both calendar and repository |

---

## Out of Scope (later phases)

- Police station registry and geocoding pipeline (Phase 2)
- Station ranking and resource allocation engine (Phase 2)
- Multi-event conflict resolution across corridors (Phase 3)
- Worst-case simulation mode (Phase 3)
- Dynamic resource reallocation (Phase 3)
- Command dashboard and AI decision support (Phase 4)
