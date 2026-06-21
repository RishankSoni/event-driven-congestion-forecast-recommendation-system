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
# Deduplicate display labels for events sharing the same name
_name_counts: dict[str, int] = {}
for e in date_events:
    _name_counts[e["event_name"]] = _name_counts.get(e["event_name"], 0) + 1

_seen2: dict[str, int] = {}
_labels: list[str] = []
_label_to_id: dict[str, str] = {}
for e in date_events:
    name = e["event_name"]
    if _name_counts[name] > 1:
        _seen2[name] = _seen2.get(name, 0) + 1
        label = f"{name} ({_seen2[name]})"
    else:
        label = name
    _labels.append(label)
    _label_to_id[label] = e["event_id"]

selected_names = st.multiselect(
    f"Select 2–5 events for {selected_date.strftime('%d %B %Y')}",
    options=_labels,
    max_selections=5,
)

if len(selected_names) < 2:
    st.info("Select at least 2 events to optimize resource allocation.")
    st.stop()

selected_ids = [_label_to_id[n] for n in selected_names]

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
