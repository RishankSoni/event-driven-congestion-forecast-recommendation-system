# pages/2_Results.py
import json

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src import event_store, station_store
from src.app_cache import load_and_train
from src.deployment_planner import build_deployment_plan


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
if "save_data" in st.session_state:
    sd = st.session_state["save_data"]
    _event_for_plan = {
        **sd,
        "severity":          severity,
        "law_order_prob":    risks["law_order_prob"],
        "expected_duration_h": 2.0,
    }
    _ranked = station_store.rank_stations(
        sd.get("latitude", 12.97),
        sd.get("longitude", 77.59),
        sd.get("event_date", ""),
        sd.get("event_time", ""),
        top_n=5,
    )
    from src.station_store import allocate_officers as _alloc
    _ranked = _alloc(_ranked, officers["total_min"])
    _plan = build_deployment_plan(
        _event_for_plan, _ranked, officers, barricades, diversions
    )
    st.session_state["deployment_data"] = {
        "event":    _event_for_plan,
        "stations": _ranked,
        "plan":     _plan,
    }

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("### Model Performance")
st.sidebar.metric("CV macro-F1 (train)", f"{state['cv_f1']:.3f}")
st.sidebar.metric("Test macro-F1",       f"{state['test_f1']:.3f}")
st.sidebar.metric("Congestion AUC",      f"{state['risk_models']['congestion_auc']:.3f}")
st.sidebar.metric("Law & Order AUC",     f"{state['risk_models']['law_order_auc']:.3f}")

# ── Header ────────────────────────────────────────────────────────────────────
st.page_link("pages/1_Plan_Event.py", label="← Back to form")
st.title(f"Deployment Plan — {r['event_name']}")

conf_pct = confidence.get(severity, 0.0) * 100

left, right = st.columns([1, 2])


def _risk_bar(prob: float) -> str:
    filled = int(round(prob * 10))
    return "█" * filled + "░" * (10 - filled)


def _risk_label(prob: float) -> str:
    if prob < 0.33:  return "LOW"
    if prob < 0.66:  return "MEDIUM"
    return "HIGH"


def _render_shap_drivers(drivers: list[dict]) -> None:
    for d in drivers:
        arrow = "▲" if d["direction"] == "+" else "▼"
        st.markdown(
            f"{arrow} **{d['direction']}{d['pct']}%** &nbsp; {d['display']}"
        )


with left:
    st.markdown(f"## {severity}")
    st.caption(f"Confidence: {conf_pct:.0f}%  |  Corridor: {r['corridor']}")

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

    # ── Risk Forecast ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Risk Forecast")
    cong_prob = risks["congestion_prob"]
    law_prob  = risks["law_order_prob"]
    st.markdown(
        f"**Traffic Congestion** &nbsp; "
        f"`{_risk_bar(cong_prob)}` &nbsp; "
        f"{cong_prob*100:.0f}% — **{_risk_label(cong_prob)}**"
    )
    st.markdown(
        f"**Law & Order** &nbsp; "
        f"`{_risk_bar(law_prob)}` &nbsp; "
        f"{law_prob*100:.0f}% — **{_risk_label(law_prob)}**"
    )

    # ── Action Plan ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Action Plan")
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
    st.markdown("---")
    st.markdown("### Recommended Stations")

    _lat = st.session_state.get("save_data", {}).get("latitude")
    _lng = st.session_state.get("save_data", {}).get("longitude")
    _edate = st.session_state.get("save_data", {}).get("event_date", "")
    _etime = st.session_state.get("save_data", {}).get("event_time", "")

    if _lat is None or _lng is None:
        st.caption("No event location provided — station ranking unavailable.")
        _ranked_top3 = []
    else:
        _ranked_top3 = station_store.rank_stations(_lat, _lng, _edate, _etime, top_n=3)
        if not _ranked_top3:
            st.caption("Station geocoding not yet run — visit Station Registry to enable ranking.")
        else:
            from src.station_store import allocate_officers as _alloc_top3
            _ranked_top3 = _alloc_top3(_ranked_top3, officers["total_min"])
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
            st.page_link("pages/7_Deployment_Plan.py", label="View Full Deployment Plan →")

    # ── SHAP Explainability ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### Why {severity}?")
    _render_shap_drivers(r["shap_severity"])

    with st.expander(f"Why traffic congestion = {cong_prob*100:.0f}%?"):
        _render_shap_drivers(r["shap_congestion"])

    with st.expander(f"Why law & order risk = {law_prob*100:.0f}%?"):
        _render_shap_drivers(r["shap_law"])

    # ── Similar past events ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 5 Similar Past Events")
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
    st.markdown("### Impact Map")
    st_folium(fmap, width=700, height=520, returned_objects=[])

# ── Export ────────────────────────────────────────────────────────────────────
st.markdown("---")
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

st.markdown("---")
st.page_link("pages/3_Post_Event_Report.py", label="File Post-Event Report")

# ── Save to Event Calendar ────────────────────────────────────────────────────
st.markdown("---")
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
