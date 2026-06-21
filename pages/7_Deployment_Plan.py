# pages/7_Deployment_Plan.py
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Deployment Plan", layout="wide")
st.title("Deployment Plan")

if "deployment_data" not in st.session_state:
    st.warning("No deployment plan found. Please run a prediction first.")
    st.page_link("pages/1_Plan_Event.py", label="← Back to form")
    st.stop()

dd       = st.session_state["deployment_data"]
event    = dd["event"]
stations = dd["stations"]
plan     = dd["plan"]

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
            "Station":   s["station_name"],
            "Zone":      s["dcp_zone"],
            "Dist (km)": f"{s['distance_km']:.1f}",
            "ETA (min)": s["response_min"],
            "Officers":  officers_cell,
            "Vehicles":  s["capacity_vehicles"],
            "BTP PI":    "✓" if s["has_btp_pi"] else "—",
            "Capacity":  "⚠ Default" if s.get("capacity_unconfirmed") else "✓ Confirmed",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("⚠ = uncapped default capacity &nbsp;&nbsp; 🔒 = capped at confirmed capacity")
else:
    st.info("No stations ranked — geocoding not yet run. Visit Station Registry.")

st.markdown("---")

# ── Section 3: Officers ───────────────────────────────────────────────────────
st.subheader("Officer Strength")
o1, o2 = st.columns(2)
o1.metric("Minimum Officers", plan["total_officers_min"])
o2.metric("Maximum Officers", plan["total_officers_max"])

st.markdown("---")

# ── Section 4: Barricades & Diversions ────────────────────────────────────────
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

# ── Section 5: Support Requirements ──────────────────────────────────────────
st.subheader("Support Requirements")
m1, m2, m3, m4 = st.columns(4)
m1.metric("QRT Units",        plan["qrt_units"])
m2.metric("Medical Posts",    plan["medical_posts"])
m3.metric("Surveillance Pts", len(plan["surveillance_points"]))
m4.metric("VIP Protocol",     "Yes" if plan["vip_protocol"] else "No")

st.markdown("---")

# ── Section 6: Timeline ───────────────────────────────────────────────────────
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

# ── Section 7: Export / Print ─────────────────────────────────────────────────
export_rows = (
    [("Event", event.get("event_name", ""))]
    + [(f"Station {i+1}", s["station_name"]) for i, s in enumerate(stations)]
    + [("Officers min", plan["total_officers_min"]),
       ("Officers max", plan["total_officers_max"]),
       ("QRT units",    plan["qrt_units"]),
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
