# pages/7_Deployment_Plan.py
import pandas as pd
import streamlit as st

from src.ui import inject_css, page_header, section_header, severity_badge, ai_insight_card

st.set_page_config(page_title="Deployment Plan", layout="wide")
inject_css()
page_header("Deployment Plan")

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
col_ev, col_sev = st.columns([4, 1])
with col_ev:
    st.markdown(
        f"**{event.get('event_name', '—')}** &nbsp;|&nbsp; "
        f"{event.get('event_date', '')} {event.get('event_time', '')} &nbsp;|&nbsp; "
        f"{event.get('corridor', '—')}"
    )
with col_sev:
    severity_badge(sev)

# ── Section 1: Briefing ───────────────────────────────────────────────────────
section_header("Operational Briefing")
ai_insight_card(plan["briefing"])

# ── Section 2: Station Deployment ─────────────────────────────────────────────
section_header("Station Deployment")

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

# ── Section 3: Officers ───────────────────────────────────────────────────────
section_header("Officer Strength")
o1, o2 = st.columns(2)
o1.metric("Minimum Officers", plan["total_officers_min"])
o2.metric("Maximum Officers", plan["total_officers_max"])

# ── Section 4: Barricades & Diversions ────────────────────────────────────────
section_header("Barricades & Diversions")
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

# ── Section 5: Support Requirements ──────────────────────────────────────────
section_header("Support Requirements")
m1, m2, m3 = st.columns(3)
m1.metric("QRT Units",    plan["qrt_units"])
m2.metric("Medical Posts", plan["medical_posts"])
m3.metric("VIP Protocol",  "Yes" if plan["vip_protocol"] else "No")

# ── Section 6: Timeline ───────────────────────────────────────────────────────
section_header("Deployment Timeline")
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
