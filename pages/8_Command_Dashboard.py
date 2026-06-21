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
