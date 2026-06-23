# Phase 3: Command Dashboard & Multi-Event Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a TMC Command Dashboard (today's events + conflicts + station load) and a Multi-Event Optimizer (combined resource planning for 2–5 concurrent events) on top of the Phase 1 event store and Phase 2 station intelligence.

**Architecture:** A new backend module `src/ops_store.py` owns all cross-event queries and the multi-event optimization algorithm; it references `event_store.DB_PATH` through the module so that tests can monkeypatch it without importing DB_PATH at ops_store module-load time. Two new Streamlit pages consume ops_store and station_store with no modifications to existing files.

**Tech Stack:** Python 3.13, SQLite (stdlib `sqlite3`), Streamlit, pandas, pytest. No new pip dependencies.

## Global Constraints

- No new pip dependencies — only stdlib + already-installed packages
- No new SQLite tables — read from existing `planned_events` and `police_stations` tables
- `status NOT IN ('cancelled', 'completed')` is the active-event filter everywhere (matches Phase 1 pattern)
- Conflict thresholds: time ≤ 4 hours apart, distance ≤ 8.0 km OR same corridor string (matches `check_conflicts()` in `src/event_store.py`)
- `ops_store.py` must NOT import `DB_PATH` at module level — always reference `event_store.DB_PATH` inside functions so monkeypatching works in tests
- Multi-event priority = `estimated_attendance` descending (ties broken by `event_time` ascending)
- All timestamps use `datetime.utcnow().strftime("%Y-%m-%d")` for today's date
- Page files: `pages/8_Command_Dashboard.py`, `pages/9_Multi_Event_Optimizer.py`
- Test file: `tests/test_ops_store.py`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `src/ops_store.py` | All cross-event queries + multi-event optimization |
| Create | `pages/8_Command_Dashboard.py` | TMC home screen |
| Create | `pages/9_Multi_Event_Optimizer.py` | Multi-event resource planner |
| Create | `tests/test_ops_store.py` | 10 unit tests for ops_store |

---

### Task 1: ops_store — Core Backend

**Files:**
- Create: `src/ops_store.py`
- Create: `tests/test_ops_store.py`

**Interfaces:**
- Consumes:
  - `src.event_store.DB_PATH` (referenced as `event_store.DB_PATH` inside functions)
  - `src.event_store._haversine_km(lat1, lng1, lat2, lng2) -> float`
  - `src.station_store.rank_stations(lat, lng, date, time, top_n=5) -> list[dict]`
  - `src.station_store.allocate_officers(stations, total_officers) -> list[dict]`
  - `src.event_store.init_db() -> None` (called in test fixtures)
  - `src.station_store.init_station_db() -> None` (called in test fixtures)
  - `src.event_store.save_event(event_data: dict) -> str`
- Produces:
  - `get_today_events() -> list[dict]`
  - `get_week_events(days: int = 7) -> list[dict]`
  - `detect_conflict_pairs(events: list[dict]) -> list[tuple[dict, dict]]`
  - `get_zone_utilization() -> dict[str, int]`
  - `optimize_multi_event(event_ids: list[str]) -> dict`

- [ ] **Step 1: Write all 10 failing tests**

Create `tests/test_ops_store.py`:

```python
# tests/test_ops_store.py
import sqlite3
from datetime import date, timedelta

import pytest

from src import event_store, ops_store, station_store


@pytest.fixture(autouse=True)
def _patch_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr("src.event_store.DB_PATH", db)
    monkeypatch.setattr("src.station_store.DB_PATH", db)
    event_store.init_db()
    station_store.init_station_db()
    return db


def _save(name, corridor="MG Road", zone="Central", date_str=None,
          time_str="10:00", lat=12.97, lng=77.59, status="planned",
          attendance=500, officer_min=5, officer_max=8):
    today = date_str or date.today().strftime("%Y-%m-%d")
    return event_store.save_event({
        "event_name": name,
        "event_type": "planned",
        "event_cause": "public_event",
        "corridor": corridor,
        "zone": zone,
        "event_date": today,
        "event_time": time_str,
        "latitude": lat,
        "longitude": lng,
        "estimated_attendance": attendance,
        "has_vip": 0,
        "officer_min": officer_min,
        "officer_max": officer_max,
    })


# ── get_today_events ──────────────────────────────────────────────────────────

def test_get_today_events_returns_list():
    result = ops_store.get_today_events()
    assert isinstance(result, list)


def test_get_today_events_filters_status():
    eid = _save("Rally")
    event_store.update_status(eid, "cancelled")
    result = ops_store.get_today_events()
    assert all(e["event_id"] != eid for e in result)


# ── get_week_events ───────────────────────────────────────────────────────────

def test_get_week_events_respects_days_param():
    today = date.today()
    far_date = (today + timedelta(days=8)).strftime("%Y-%m-%d")
    _save("Far Event", date_str=far_date)
    result = ops_store.get_week_events(days=7)
    assert all(e["event_date"] != far_date for e in result)


# ── detect_conflict_pairs ─────────────────────────────────────────────────────

def test_detect_conflict_pairs_requires_two_events():
    eid = _save("Solo")
    ev = event_store.get_event(eid)
    assert ops_store.detect_conflict_pairs([ev]) == []


def test_detect_conflict_pairs_same_corridor():
    eid1 = _save("Event A", corridor="MG Road", time_str="10:00")
    eid2 = _save("Event B", corridor="MG Road", time_str="12:00")
    ev1 = event_store.get_event(eid1)
    ev2 = event_store.get_event(eid2)
    pairs = ops_store.detect_conflict_pairs([ev1, ev2])
    assert len(pairs) == 1


def test_detect_conflict_pairs_far_apart_not_flagged():
    # 20 km apart, different corridors
    eid1 = _save("North Event", corridor="Tumkur Road", lat=13.10, lng=77.55)
    eid2 = _save("South Event", corridor="Hosur Road",  lat=12.90, lng=77.65)
    ev1 = event_store.get_event(eid1)
    ev2 = event_store.get_event(eid2)
    pairs = ops_store.detect_conflict_pairs([ev1, ev2])
    assert pairs == []


def test_detect_conflict_pairs_different_day_not_flagged():
    today = date.today()
    tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    eid1 = _save("Today Event",    date_str=today.strftime("%Y-%m-%d"), corridor="MG Road")
    eid2 = _save("Tomorrow Event", date_str=tomorrow,                   corridor="MG Road")
    ev1 = event_store.get_event(eid1)
    ev2 = event_store.get_event(eid2)
    pairs = ops_store.detect_conflict_pairs([ev1, ev2])
    assert pairs == []


# ── get_zone_utilization ──────────────────────────────────────────────────────

def test_get_zone_utilization_counts_active():
    _save("Event 1", zone="Central")
    _save("Event 2", zone="Central")
    result = ops_store.get_zone_utilization()
    assert result.get("Central", 0) == 2


# ── optimize_multi_event ──────────────────────────────────────────────────────

def test_optimize_multi_event_empty_returns_empty():
    result = ops_store.optimize_multi_event([])
    assert result["events"] == []
    assert result["total_officers_min"] == 0
    assert result["total_officers_max"] == 0
    assert result["per_event"] == []
    assert result["station_conflicts"] == []
    assert result["unresolvable"] is False


def test_optimize_multi_event_sums_officers():
    eid1 = _save("Event A", officer_min=5, officer_max=8)
    eid2 = _save("Event B", officer_min=5, officer_max=8)
    result = ops_store.optimize_multi_event([eid1, eid2])
    assert result["total_officers_min"] == 10
    assert result["total_officers_max"] == 16
```

- [ ] **Step 2: Run tests to verify they all fail**

```
cd C:\Users\HP\OneDrive\Desktop\random\theme2
python -m pytest tests/test_ops_store.py -v 2>&1 | tail -15
```

Expected: all 10 FAILED with "cannot import name 'ops_store'" or similar.

- [ ] **Step 3: Implement `src/ops_store.py`**

Create `src/ops_store.py`:

```python
# src/ops_store.py
import sqlite3
from datetime import date, datetime, timedelta

from src import event_store, station_store
from src.event_store import _haversine_km


def get_today_events() -> list[dict]:
    """Return all non-cancelled/completed events for today (UTC date), ordered by time."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with sqlite3.connect(event_store.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM planned_events "
            "WHERE event_date = ? AND status NOT IN ('cancelled', 'completed') "
            "ORDER BY event_time",
            (today,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_week_events(days: int = 7) -> list[dict]:
    """Return all active events in the next `days` days (today inclusive),
    ordered by date then time."""
    today = date.today()
    end = today + timedelta(days=days - 1)
    with sqlite3.connect(event_store.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM planned_events "
            "WHERE event_date BETWEEN ? AND ? "
            "AND status NOT IN ('cancelled', 'completed') "
            "ORDER BY event_date, event_time",
            (today.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()
    return [dict(r) for r in rows]


def _parse_time_hours(t: str) -> float:
    """Parse 'HH:MM' string to fractional hours. Returns 0.0 on failure."""
    try:
        h, m = t.split(":")
        return int(h) + int(m) / 60.0
    except Exception:
        return 0.0


def detect_conflict_pairs(events: list[dict]) -> list[tuple[dict, dict]]:
    """Return (event_A, event_B) pairs where both conditions hold:
    1. Same date AND |time_A - time_B| <= 4 hours
    2. Same corridor string OR haversine distance <= 8.0 km
    Each pair appears once (lower index first). Returns [] if < 2 events."""
    if len(events) < 2:
        return []
    pairs = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            if a.get("event_date") != b.get("event_date"):
                continue
            if abs(_parse_time_hours(a.get("event_time", "00:00"))
                   - _parse_time_hours(b.get("event_time", "00:00"))) > 4.0:
                continue
            # Spatial check
            spatial = False
            if a.get("corridor") and a.get("corridor") == b.get("corridor"):
                spatial = True
            elif (a.get("latitude") is not None and a.get("longitude") is not None
                  and b.get("latitude") is not None and b.get("longitude") is not None):
                if _haversine_km(
                    a["latitude"], a["longitude"], b["latitude"], b["longitude"]
                ) <= 8.0:
                    spatial = True
            if spatial:
                pairs.append((a, b))
    return pairs


def get_zone_utilization() -> dict[str, int]:
    """Return {zone: active_event_count} for today's active events, non-null zones only."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with sqlite3.connect(event_store.DB_PATH) as conn:
        rows = conn.execute(
            "SELECT zone, COUNT(*) FROM planned_events "
            "WHERE event_date = ? AND status NOT IN ('cancelled', 'completed') "
            "AND zone IS NOT NULL GROUP BY zone",
            (today,),
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def optimize_multi_event(event_ids: list[str]) -> dict:
    """Given event IDs, return combined resource plan with station conflict resolution.

    Priority = estimated_attendance descending (ties: event_time ascending).
    Higher-priority events get first pick of stations.
    Station conflicts: same station in original top-3 of 2+ events.
    Resolution: lower-priority event gets next available (unclaimed) station.
    unresolvable=True if any event ends up with 0 stations after filtering.
    """
    _empty = {
        "events": [], "total_officers_min": 0, "total_officers_max": 0,
        "per_event": [], "station_conflicts": [], "unresolvable": False,
    }
    if not event_ids:
        return _empty

    with sqlite3.connect(event_store.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(event_ids))
        rows = conn.execute(
            f"SELECT * FROM planned_events WHERE event_id IN ({placeholders})",
            event_ids,
        ).fetchall()
    if not rows:
        return _empty

    events = sorted(
        [dict(r) for r in rows],
        key=lambda e: (-(e.get("estimated_attendance") or 0), e.get("event_time", "")),
    )

    total_min = sum(e.get("officer_min") or 0 for e in events)
    total_max = sum(e.get("officer_max") or 0 for e in events)

    claimed: dict[int, str] = {}        # station_code → event_id that claimed it
    original_top3: dict[str, list[int]] = {}  # event_id → original top-3 station codes

    per_event = []
    unresolvable = False

    for ev in events:
        eid = ev["event_id"]
        lat, lng = ev.get("latitude"), ev.get("longitude")

        if lat is None or lng is None:
            per_event.append({
                "event_id": eid, "event_name": ev.get("event_name", ""),
                "stations": [], "conflict_with": [],
            })
            original_top3[eid] = []
            continue

        all_ranked = station_store.rank_stations(
            lat, lng, ev.get("event_date", ""), ev.get("event_time", ""), top_n=5
        )
        original_top3[eid] = [s["station_code"] for s in all_ranked[:3]]

        available = [s for s in all_ranked if s["station_code"] not in claimed]
        assigned = available[:3]

        if not assigned and all_ranked:
            unresolvable = True

        if assigned:
            assigned = station_store.allocate_officers(assigned, ev.get("officer_min") or 0)
            for s in assigned:
                claimed[s["station_code"]] = eid

        per_event.append({
            "event_id": eid, "event_name": ev.get("event_name", ""),
            "stations": assigned, "conflict_with": [],
        })

    # Build station_conflicts from original top-3 overlaps
    station_event_map: dict[int, list[str]] = {}
    for eid, codes in original_top3.items():
        for code in codes:
            station_event_map.setdefault(code, []).append(eid)

    conflict_codes = [c for c, eids in station_event_map.items() if len(eids) >= 2]
    station_conflicts: list[dict] = []
    conflict_partners: dict[str, set[str]] = {}

    if conflict_codes:
        with sqlite3.connect(event_store.DB_PATH) as conn:
            ph = ",".join("?" * len(conflict_codes))
            name_rows = conn.execute(
                f"SELECT station_code, station_name FROM police_stations "
                f"WHERE station_code IN ({ph})",
                conflict_codes,
            ).fetchall()
        names = {r[0]: r[1] for r in name_rows}
        for code in conflict_codes:
            claiming = station_event_map[code]
            station_conflicts.append({
                "station_name": names.get(code, str(code)),
                "claimed_by": claiming,
            })
            for eid in claiming:
                conflict_partners.setdefault(eid, set()).update(
                    e for e in claiming if e != eid
                )

    for pe in per_event:
        pe["conflict_with"] = list(conflict_partners.get(pe["event_id"], set()))

    return {
        "events": events,
        "total_officers_min": total_min,
        "total_officers_max": total_max,
        "per_event": per_event,
        "station_conflicts": station_conflicts,
        "unresolvable": unresolvable,
    }
```

- [ ] **Step 4: Run tests to verify they all pass**

```
python -m pytest tests/test_ops_store.py -v 2>&1 | tail -15
```

Expected: 10 passed.

- [ ] **Step 5: Run full suite to check for regressions**

```
python -m pytest tests/ -q --ignore=tests/test_road_network.py 2>&1 | tail -5
```

Expected: 125 passed (115 pre-existing + 10 new).

- [ ] **Step 6: Commit**

```
git add src/ops_store.py tests/test_ops_store.py
git commit -m "feat: ops_store — cross-event queries, conflict detection, multi-event optimizer"
```

---

### Task 2: Command Dashboard Page

**Files:**
- Create: `pages/8_Command_Dashboard.py`

**Interfaces:**
- Consumes:
  - `ops_store.get_today_events() -> list[dict]`
  - `ops_store.get_week_events(days=7) -> list[dict]`
  - `ops_store.detect_conflict_pairs(events) -> list[tuple[dict, dict]]`
  - `ops_store.get_zone_utilization() -> dict[str, int]`
  - `station_store.get_geocode_summary() -> dict` — key `"geocoded"` gives count
  - `app_cache.load_and_train()` — for st.set_page_config pattern only; NOT called on this page (no ML needed)
- Produces: nothing (UI page only)
- No tests required (Streamlit UI page)

- [ ] **Step 1: Create `pages/8_Command_Dashboard.py`**

```python
# pages/8_Command_Dashboard.py
from datetime import date

import pandas as pd
import streamlit as st

from src import ops_store, station_store

st.set_page_config(page_title="GRIDLOCK — Command Dashboard", layout="wide")

st.title("Command Dashboard")
st.caption(f"Today: {date.today().strftime('%A, %d %B %Y')}")

col_refresh, _ = st.columns([1, 8])
with col_refresh:
    if st.button("↻ Refresh"):
        st.rerun()

st.markdown("---")

# ── Load data ─────────────────────────────────────────────────────────────────
today_events   = ops_store.get_today_events()
conflict_pairs = ops_store.detect_conflict_pairs(today_events)
geo_summary    = station_store.get_geocode_summary()

# ── Row 1: Summary metrics ─────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Events Today",        len(today_events))
m2.metric("HIGH Severity",       sum(1 for e in today_events if e.get("severity") == "HIGH"))
m3.metric("Conflict Pairs",      len(conflict_pairs))
m4.metric("Geocoded Stations",   geo_summary.get("geocoded", 0))

st.markdown("---")

# ── Row 2: Today's events table ────────────────────────────────────────────────
st.markdown("### Today's Events")

if not today_events:
    st.info("No events planned for today.")
else:
    # Build conflict count per event
    conflict_count: dict[str, int] = {}
    for a, b in conflict_pairs:
        conflict_count[a["event_id"]] = conflict_count.get(a["event_id"], 0) + 1
        conflict_count[b["event_id"]] = conflict_count.get(b["event_id"], 0) + 1

    rows = []
    for e in today_events:
        eid = e["event_id"]
        n_conflicts = conflict_count.get(eid, 0)
        rows.append({
            "Event":      e.get("event_name", ""),
            "Corridor":   e.get("corridor", ""),
            "Time":       e.get("event_time", ""),
            "Severity":   e.get("severity", "—"),
            "Attendance": e.get("estimated_attendance") or 0,
            "Conflicts":  f"⚠ {n_conflicts}" if n_conflicts else "",
            "Status":     e.get("status", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if conflict_pairs:
        st.markdown("**Active conflicts:**")
        for a, b in conflict_pairs:
            st.markdown(
                f"- ⚠ **{a.get('event_name')}** ↔ **{b.get('event_name')}** "
                f"({a.get('corridor', '?')} / {b.get('corridor', '?')})"
            )

st.markdown("---")

# ── Row 3: 7-day pipeline ─────────────────────────────────────────────────────
st.markdown("### Upcoming 7 Days")
week_events = ops_store.get_week_events(days=7)

if not week_events:
    st.info("No upcoming events in the next 7 days.")
else:
    week_rows = [
        {
            "Date":      e.get("event_date", ""),
            "Event":     e.get("event_name", ""),
            "Corridor":  e.get("corridor", ""),
            "Severity":  e.get("severity", "—"),
            "Status":    e.get("status", ""),
        }
        for e in week_events
    ]
    st.dataframe(pd.DataFrame(week_rows), use_container_width=True, hide_index=True)

st.markdown("---")
st.page_link("pages/9_Multi_Event_Optimizer.py", label="Multi-Event Optimizer →")
st.page_link("pages/1_Plan_Event.py",            label="Plan New Event →")
```

- [ ] **Step 2: Verify the page loads**

```
streamlit run app.py --server.port 8502 --server.headless true &
```

Navigate to the sidebar and click "Command Dashboard". Expected: page loads showing metrics row + events table (may be empty if no events saved yet).

Stop the server with Ctrl+C.

- [ ] **Step 3: Commit**

```
git add pages/8_Command_Dashboard.py
git commit -m "feat: Command Dashboard — today's events, conflicts, 7-day pipeline"
```

---

### Task 3: Multi-Event Optimizer Page

**Files:**
- Create: `pages/9_Multi_Event_Optimizer.py`

**Interfaces:**
- Consumes:
  - `ops_store.get_week_events(days=30) -> list[dict]` — to populate the date picker
  - `ops_store.optimize_multi_event(event_ids: list[str]) -> dict`
  - `ops_store.detect_conflict_pairs(events) -> list[tuple[dict,dict]]`
- Produces: nothing (UI page only)
- No tests required (Streamlit UI page)

- [ ] **Step 1: Create `pages/9_Multi_Event_Optimizer.py`**

```python
# pages/9_Multi_Event_Optimizer.py
from datetime import date

import pandas as pd
import streamlit as st

from src import ops_store

st.set_page_config(page_title="GRIDLOCK — Multi-Event Optimizer", layout="wide")

st.title("Multi-Event Optimizer")
st.caption("Plan officer and station assignments for multiple concurrent events.")

st.markdown("---")

# ── Step 1: Date picker ───────────────────────────────────────────────────────
selected_date = st.date_input("Select event date", value=date.today())
date_str = selected_date.strftime("%Y-%m-%d")

# Load all non-cancelled events for the next 30 days, then filter to selected date
all_events = ops_store.get_week_events(days=30)
date_events = [e for e in all_events if e.get("event_date") == date_str]

if not date_events:
    st.info(f"No saved events found for {selected_date.strftime('%d %B %Y')}. "
            "Plan events on the Plan Event page first.")
    st.page_link("pages/1_Plan_Event.py", label="← Plan New Event")
    st.stop()

# ── Step 2: Event selector ────────────────────────────────────────────────────
event_options = {e["event_name"]: e["event_id"] for e in date_events}
selected_names = st.multiselect(
    f"Select 2–5 events for {selected_date.strftime('%d %B %Y')}",
    options=list(event_options.keys()),
    max_selections=5,
)

if len(selected_names) < 2:
    st.info("Select at least 2 events to optimize resource allocation.")
    st.stop()

selected_ids = [event_options[n] for n in selected_names]

# ── Step 3: Optimize ──────────────────────────────────────────────────────────
if st.button("Optimize Resource Allocation", type="primary"):
    with st.spinner("Running multi-event optimization…"):
        result = ops_store.optimize_multi_event(selected_ids)

    st.markdown("---")

    # Combined summary
    st.markdown("### Combined Resource Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Officers (min)", result["total_officers_min"])
    c2.metric("Total Officers (max)", result["total_officers_max"])
    c3.metric("Events Optimized",     len(result["per_event"]))

    # Conflict summary
    if result["unresolvable"]:
        st.error(
            "⚠ Insufficient geocoded stations to resolve all conflicts. "
            "Run geocoding from the Station Registry page first."
        )
    elif result["station_conflicts"]:
        st.warning(
            f"⚠ {len(result['station_conflicts'])} station conflict(s) detected and resolved."
        )
        for sc in result["station_conflicts"]:
            names = ", ".join(
                next((e.get("event_name", eid) for e in result["events"] if e["event_id"] == eid), eid)
                for eid in sc["claimed_by"]
            )
            st.markdown(f"  - **{sc['station_name']}** → originally requested by: {names}")
    else:
        st.success("✓ No station conflicts — all events can be staffed independently.")

    st.markdown("---")

    # Per-event station assignments
    st.markdown("### Per-Event Station Assignments")
    for pe in result["per_event"]:
        ev_data = next((e for e in result["events"] if e["event_id"] == pe["event_id"]), {})
        sev = ev_data.get("severity", "—")
        badge = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(sev, "⚪")

        with st.expander(f"{badge} {pe['event_name']} — {sev}", expanded=True):
            if not pe["stations"]:
                st.caption("No geocoded stations available for this event's location.")
                continue

            rows = []
            for s in pe["stations"]:
                off = str(s["officers_allocated"])
                if s.get("capacity_unconfirmed"):
                    off = f"⚠ {off}"
                elif s.get("allocation_capped"):
                    off = f"🔒 {off}"
                rows.append({
                    "Station":   s["station_name"],
                    "Zone":      s["dcp_zone"],
                    "Dist (km)": f"{s['distance_km']:.1f}",
                    "ETA (min)": s["response_min"],
                    "Officers":  off,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if pe["conflict_with"]:
                conflict_names = ", ".join(
                    next((e.get("event_name", eid) for e in result["events"] if e["event_id"] == eid), eid)
                    for eid in pe["conflict_with"]
                )
                st.caption(f"⚠ Shared station conflict with: {conflict_names}")

    st.markdown("---")
    st.page_link("pages/8_Command_Dashboard.py", label="← Command Dashboard")
    st.page_link("pages/7_Deployment_Plan.py",   label="View Deployment Plan →")
```

- [ ] **Step 2: Verify the page loads**

```
streamlit run app.py --server.port 8502 --server.headless true &
```

Navigate to "Multi-Event Optimizer" in the sidebar. Expected: date picker shown; if no events saved, info message displayed. Stop the server.

- [ ] **Step 3: Run full test suite — no regressions**

```
python -m pytest tests/ -q --ignore=tests/test_road_network.py 2>&1 | tail -5
```

Expected: 125 passed.

- [ ] **Step 4: Commit**

```
git add pages/9_Multi_Event_Optimizer.py
git commit -m "feat: Multi-Event Optimizer page — date picker, combined resources, conflict resolution"
```

---

## Self-Review Checklist (completed inline)

**Spec coverage:**
- ✓ `get_today_events()` → Task 1
- ✓ `get_week_events(days)` → Task 1
- ✓ `detect_conflict_pairs(events)` → Task 1 (4h + 8km thresholds, same-date guard)
- ✓ `get_zone_utilization()` → Task 1
- ✓ `optimize_multi_event(event_ids)` → Task 1 (attendance-priority, claimed-station filtering, conflict map)
- ✓ Command Dashboard (4 metrics, today table, 7-day pipeline, refresh button) → Task 2
- ✓ Multi-Event Optimizer (date picker, multiselect, optimize, per-event expanders, conflict summary) → Task 3
- ✓ 10 tests matching spec list → Task 1
- ✓ No new dependencies anywhere
- ✓ `ops_store.DB_PATH` NOT imported at module level — always `event_store.DB_PATH` inside functions

**Placeholder scan:** No TBDs, no "implement later", all code blocks complete. ✓

**Type consistency:**
- `optimize_multi_event` returns dict with keys `events, total_officers_min, total_officers_max, per_event, station_conflicts, unresolvable` — same keys consumed in Task 3. ✓
- `detect_conflict_pairs` returns `list[tuple[dict, dict]]` — Task 2 unpacks as `for a, b in conflict_pairs`. ✓
- `get_week_events` returns `list[dict]` with `event_date` key — Task 3 filters by `e.get("event_date") == date_str`. ✓
