# pages/2_Results.py
import json

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src import event_store, station_store
from src.app_cache import load_and_train
from src.deployment_planner import build_deployment_plan
from src.ui import inject_css, page_header, section_header, severity_badge, risk_gauge, ai_insight_card, render_mappls_sidebar
import src.mappls_api as mappls_api



def _build_save_record(sd: dict, r: dict) -> dict:
    """Merge form inputs (sd) with prediction outputs (r) into a save_event-ready dict."""
    risks    = r["risks"]
    officers = r["officers"]
    return {
        **sd,
        "severity":          r["severity"],
        "severity_conf":     r["confidence"].get(r["severity"], 0.0),
        "congestion_prob":   risks["congestion_prob"],
        "law_order_prob":    risks["law_order_prob"],
        "duration_label":    r.get("duration"),
        "officer_min":       officers["total_min"],
        "officer_max":       officers["total_max"],
        "barricades_json":   json.dumps(r["barricades"]),
        "diversions_json":   json.dumps(r["diversions"]),
        "shap_drivers_json": json.dumps(r["shap_severity"]),
    }

st.set_page_config(page_title="Event Congestion Planner — Results", layout="wide")
inject_css()
render_mappls_sidebar()

state = load_and_train()   # hits the cache; no re-training

# ── Guard: redirect if navigated here directly without submitting form ───────
if "result_data" not in st.session_state:
    st.warning("No prediction data found. Please fill in the event form first.")
    st.page_link("pages/1_Plan_Event.py", label="← Back to form")
    st.stop()

r          = st.session_state["result_data"]
severity   = r["severity"]
confidence = r["confidence"]
officers   = r["officers"]
barricades = r["barricades"]
diversions = r["diversions"]
neighbors  = r["neighbors"]
fmap       = r["fmap"]
risks      = r["risks"]

# ── Build deployment_data (consumed by page 7) ────────────────────────────────
_ranked: list[dict] = []
if "save_data" in st.session_state:
    sd = st.session_state["save_data"]
    _dur_label = r.get("duration")
    _low_h  = state["dur_model"].get("low_thresh",  1.0)
    _high_h = state["dur_model"].get("high_thresh", 3.0)
    _dur_map = {"SHORT": _low_h, "MEDIUM": _high_h, "LONG": _high_h * 1.5}
    _duration_h = _dur_map.get(_dur_label, 2.0)
    _event_for_plan = {
        **sd,
        "severity":            severity,
        "law_order_prob":      risks["law_order_prob"],
        "expected_duration_h": _duration_h,
    }
    _ranked = station_store.rank_stations(
        sd.get("latitude", 12.97),
        sd.get("longitude", 77.59),
        sd.get("event_date", ""),
        sd.get("event_time", ""),
        top_n=5,
    )
    _ranked = station_store.allocate_officers(_ranked, officers["total_min"])
    _plan = build_deployment_plan(
        _event_for_plan, _ranked, officers, barricades, diversions
    )
    st.session_state["deployment_data"] = {
        "event":    _event_for_plan,
        "stations": _ranked,
        "plan":     _plan,
    }

# Rebuild map dynamically to reflect Mappls Tiles / Workmate settings updates
from src.map_builder import build_map
from src.app_cache import get_road_graph

graph = get_road_graph()
sd = st.session_state.get("save_data", {})
lat = sd.get("latitude", 12.97)
lng = sd.get("longitude", 77.59)
_all_stations = station_store.get_all_stations()
_ranked_map = _ranked if "_ranked" in locals() else station_store.rank_stations(lat, lng, top_n=5)

fmap = build_map(
    lat, lng, severity, barricades, diversions,
    officers, state["train_df"], r["event_name"], graph, corridor=r["corridor"],
    stations=_all_stations,
    ranked_stations=_ranked_map,
)


# ── Sidebar ──────────────────────────────────────────────────────────────────


# ── Header ────────────────────────────────────────────────────────────────────
st.page_link("pages/1_Plan_Event.py", label="← Back to form")
page_header(f"Deployment Plan — {r['event_name']}")

conf_pct = confidence.get(severity, 0.0) * 100

left, right = st.columns([1, 2])


def _render_shap_drivers(drivers: list[dict]) -> None:
    for d in drivers:
        if d["direction"] == "+":
            arrow_html = '<span style="color:#4ADE80;font-weight:700">▲</span>'
        else:
            arrow_html = '<span style="color:#F87171;font-weight:700">▼</span>'
        st.markdown(
            f'{arrow_html} <strong style="color:#E2E8F0">{d["direction"]}{d["pct"]}%</strong>'
            f' &nbsp;<span style="color:#94A3B8">{d["display"]}</span>',
            unsafe_allow_html=True,
        )


with left:
    severity_badge(severity)
    st.markdown(
        f'<span style="color:#94A3B8;font-size:0.85rem">'
        f'Confidence: {conf_pct:.0f}%  |  Corridor: {r["corridor"]}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    # Duration
    dur_model  = state["dur_model"]
    _low_min   = round(dur_model["low_thresh"]  * 60 / 5) * 5
    _high_min  = round(dur_model["high_thresh"] * 60 / 5) * 5
    _DUR_LABELS = {
        "SHORT":  f"SHORT (<{_low_min} min)",
        "MEDIUM": f"MEDIUM ({_low_min}–{_high_min} min)",
        "LONG":   f"LONG (>{_high_min} min)",
    }
    _dur = r.get("duration", "N/A")
    st.markdown(f"**Duration Forecast:** {_DUR_LABELS.get(_dur, _dur)}")

    # Weather context
    rain_mm = r.get("rain_mm", 0.0)
    temperature_c = r.get("temperature_c", 25.0)
    st.markdown("")
    wcol1, wcol2 = st.columns(2)
    with wcol1:
        st.metric(label="Temperature", value=f"{temperature_c:.1f} °C")
    with wcol2:
        st.metric(label="Rainfall", value=f"{rain_mm:.1f} mm")

    # ── Risk Forecast ─────────────────────────────────────────────────────────
    section_header("Risk Forecast")
    cong_prob = risks["congestion_prob"]
    law_prob  = risks["law_order_prob"]
    risk_gauge("Traffic Congestion", cong_prob)
    risk_gauge("Law & Order", law_prob)

    # ── Action Plan ───────────────────────────────────────────────────────────
    section_header("Action Plan")
    st.markdown(f"**Officers:** {officers['total_min']}–{officers['total_max']} total")
    st.markdown(
        f"  ({officers['primary_min']}–{officers['primary_max']} on primary corridor)"
    )
    st.markdown(f"**Barricades:** {len(barricades)} position(s)")
    for b in barricades:
        st.markdown(f"  - {b}")
    st.markdown(f"**Diversions:** {len(diversions)} route(s)")
    for d in diversions:
        st.markdown(f"  - {d}")

    # ── Recommended Stations ──────────────────────────────────────────────────
    section_header("Recommended Stations")

    _lat = st.session_state.get("save_data", {}).get("latitude")
    _lng = st.session_state.get("save_data", {}).get("longitude")

    if _lat is None or _lng is None:
        st.caption("No event location provided — station ranking unavailable.")
        _ranked_top3 = []
    else:
        _ranked_top3 = _ranked[:3]
        if not _ranked_top3:
            st.caption("Station geocoding not yet run — visit Station Registry to enable ranking.")
        else:
            _rows = []
            for _s in _ranked_top3:
                _off = str(_s["officers_allocated"])
                if _s.get("capacity_unconfirmed"):
                    _off = f"⚠ {_off}"
                elif _s.get("allocation_capped"):
                    _off = f"🔒 {_off}"
                _rows.append({
                    "Station":   _s["station_name"],
                    "Zone":      _s["dcp_zone"],
                    "Dist (km)": f"{_s['distance_km']:.1f}",
                    "ETA (min)": _s["response_min"],
                    "Officers":  _off,
                })
            st.dataframe(
                pd.DataFrame(_rows),
                use_container_width=True,
                hide_index=True,
            )

    # Always show Deployment Plan link regardless of station geocoding status
    st.page_link("pages/7_Deployment_Plan.py", label="View Full Deployment Plan →")

    # ── SHAP Explainability ────────────────────────────────────────────────────
    section_header(f"Why {severity}?")
    ai_insight_card(
        f"<strong>Top drivers for {severity} severity prediction.</strong> "
        f"Factors marked ▲ increase severity risk; ▼ decrease it."
    )
    _render_shap_drivers(r["shap_severity"])

    with st.expander(f"Why traffic congestion = {cong_prob*100:.0f}%?"):
        _render_shap_drivers(r["shap_congestion"])

    with st.expander(f"Why law & order risk = {law_prob*100:.0f}%?"):
        _render_shap_drivers(r["shap_law"])

    # ── Similar past events ───────────────────────────────────────────────────
    section_header("5 Similar Past Events")
    if not neighbors.empty:
        display = neighbors[
            ["corridor", "event_cause", "severity", "impact_score"]
        ].copy()
        display.columns = ["Corridor", "Cause", "Severity", "Excess Score"]
        display["Excess Score"] = display["Excess Score"].round(2)
        st.dataframe(display, use_container_width=True, hide_index=True)
    avg_excess = neighbors["impact_score"].mean() if not neighbors.empty else 0
    st.caption(
        f"Avg excess incidents in similar events: {avg_excess:+.1f} above baseline"
    )

with right:
    section_header("Impact Map")
    st_folium(fmap, width=700, height=520, returned_objects=[])

    # ── Workmate Task Dispatch ───────────────────────────────────────────────
    workmate_active = st.session_state.get("mappls_workmate_enabled", False)
    if workmate_active:
        section_header("Workmate Dispatch")
        st.markdown(
            "Dispatch deployment tasks directly to officers via MapmyIndia Workmate."
        )
        
        # Dispatch Status in session state
        if "workmate_dispatch_result" not in st.session_state:
            st.session_state["workmate_dispatch_result"] = None
            
        btn_label = "📤 Dispatch Tasks to Workmate"
        if st.session_state["workmate_dispatch_result"]:
            btn_label = "📤 Re-dispatch Tasks"
            
        if st.button(btn_label, type="primary"):
            with st.spinner("Dispatching tasks..."):
                tasks_created = []
                sd = st.session_state.get("save_data", {})
                
                # Create primary corridor deployment task
                task_desc = (
                    f"Deploy {officers['primary_min']}-{officers['primary_max']} officers "
                    f"on primary corridor: {r['corridor']}. "
                    f"Event: {r['event_name']} ({severity} severity)."
                )
                res1 = mappls_api.dispatch_workmate_task(
                    task_name=f"Patrol Corridor: {r['corridor']}",
                    description=task_desc,
                    due_date_str=f"{sd.get('event_date')} {sd.get('event_time')}:00"
                )
                tasks_created.append(res1)
                
                # Create barricade tasks
                for idx, bar in enumerate(barricades):
                    res = mappls_api.dispatch_workmate_task(
                        task_name=f"Setup Barricade: {bar}",
                        description=f"Establish traffic barricade at junction: {bar}. Event: {r['event_name']}.",
                        due_date_str=f"{sd.get('event_date')} {sd.get('event_time')}:00"
                    )
                    tasks_created.append(res)
                    
                st.session_state["workmate_dispatch_result"] = tasks_created
                
        # Show results
        dispatch_res = st.session_state["workmate_dispatch_result"]
        if dispatch_res:
            all_sim = all(t.get("mode") == "simulation" for t in dispatch_res)
            if all_sim:
                st.info(
                    "💡 **Simulation Mode**: Tasks were dispatched to mock officers. "
                    "Configure Client ID & Client Secret in the sidebar for live integration."
                )
            else:
                st.success("🟢 Dispatched: Tasks successfully published to Mappls Workmate!")
                
            for t in dispatch_res:
                st.markdown(
                    f"- `{t.get('task_id')[:12]}`: {t.get('message')} "
                    f"({t.get('mode').upper()})"
                )


# ── Export ────────────────────────────────────────────────────────────────────
section_header("Export")
export_rows = [
    ("Event",                r["event_name"]),
    ("Corridor",             r["corridor"]),
    ("Severity",             severity),
    ("Confidence",           f"{conf_pct:.0f}%"),
    ("Duration",             r.get("duration", "N/A")),
    ("Officers min",         str(officers["total_min"])),
    ("Officers max",         str(officers["total_max"])),
    ("Barricades",           "; ".join(barricades) if barricades else "None"),
    ("Diversions",           "; ".join(diversions) if diversions else "None"),
    ("Congestion prob",      f"{cong_prob*100:.0f}%"),
    ("Law & order prob",     f"{law_prob*100:.0f}%"),
    ("Holiday",              r.get("holiday_name", "")),
    ("Estimated attendance", str(r.get("estimated_attendance", 0))),
    ("VIP presence",         str(bool(r.get("has_vip", 0)))),
    ("Route event",          str(bool(r.get("is_route_event", 0)))),
]
export_df = pd.DataFrame(export_rows, columns=["Field", "Value"])
st.download_button(
    "Export Plan (CSV)",
    data=export_df.to_csv(index=False),
    file_name=f"plan_{r['event_name'].replace(' ', '_')}.csv",
    mime="text/csv",
)

st.page_link("pages/3_Post_Event_Report.py", label="File Post-Event Report")

# ── Save to Event Calendar ────────────────────────────────────────────────────
section_header("Save to Event Calendar")
if "save_data" not in st.session_state:
    st.info("Return to the form and resubmit to enable saving this event.")
else:
    sd = st.session_state["save_data"]
    conflicts, note = event_store.check_conflicts(sd)

    show_save = False
    if conflicts:
        warn_msg = f"⚠ {len(conflicts)} event(s) already planned on the same corridor within 4 hours."
        if note:
            warn_msg += f"  \n_{note}_"
        st.warning(warn_msg)
        c1, c2 = st.columns(2)
        if c1.button("Save anyway"):
            show_save = True
        if c2.button("Review conflicts"):
            st.switch_page("pages/5_Event_Repository.py")
    else:
        show_save = True

    if show_save:
        if "event_saved_id" not in st.session_state:
            if st.button("💾 Save to Event Calendar"):
                record = _build_save_record(sd, r)
                eid = event_store.save_event(record)
                st.session_state["event_saved_id"] = eid
                st.success(f"Event saved — ID {eid[:8]}…")
        else:
            st.button("✓ Saved", disabled=True)
