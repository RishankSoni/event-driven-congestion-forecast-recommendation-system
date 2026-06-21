# pages/4_Event_Calendar.py
import json
from datetime import datetime, timedelta

import streamlit as st
from streamlit_calendar import calendar as st_calendar

from src import event_store
from src.app_cache import load_and_train
from src.explainer import explain_severity

st.set_page_config(page_title="Event Calendar", layout="wide")
st.title("Event Calendar")

_SEVERITY_COLOR = {
    "HIGH":   "#dc3545",
    "MEDIUM": "#fd7e14",
    "LOW":    "#28a745",
}


def _color(severity: str | None) -> str:
    return _SEVERITY_COLOR.get(severity or "", "#6c757d")


def _end_iso(event_date: str, event_time: str, duration_h: float | None) -> str:
    h = duration_h if duration_h else 2.0
    dt = datetime.fromisoformat(f"{event_date}T{event_time}:00")
    return (dt + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S")


events_list = event_store.list_events()

cal_events = [
    {
        "title": e["event_name"],
        "start": f"{e['event_date']}T{e['event_time']}:00",
        "end":   _end_iso(e["event_date"], e["event_time"], e.get("expected_duration_h")),
        "color": _color(e.get("severity")),
        "id":    e["event_id"],
    }
    for e in events_list
]

calendar_options = {
    "headerToolbar": {
        "left":   "prev,next today",
        "center": "title",
        "right":  "dayGridMonth,timeGridWeek,timeGridDay",
    },
    "initialView": "dayGridMonth",
}

cal_result = st_calendar(events=cal_events, options=calendar_options, key="main_cal")

st.caption("🔴 HIGH &nbsp;&nbsp; 🟠 MEDIUM &nbsp;&nbsp; 🟢 LOW &nbsp;&nbsp; ⚫ Unpredicted")

# ── Detail panel on click ─────────────────────────────────────────────────────
if cal_result and cal_result.get("eventClick"):
    clicked_id = cal_result["eventClick"]["event"]["id"]
    ev = event_store.get_event(clicked_id)
    if ev:
        st.markdown("---")
        st.subheader(ev["event_name"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Severity",  ev.get("severity") or "—")
        c2.metric("Corridor",  ev.get("corridor") or "—")
        c3.metric("Date/Time", f"{ev['event_date']} {ev['event_time']}")
        c4.metric("Status",    ev["status"])

        col_l, col_r = st.columns(2)
        with col_l:
            if ev.get("officer_min") is not None:
                st.markdown(f"**Officers:** {ev['officer_min']}–{ev['officer_max']}")
            if ev.get("congestion_prob") is not None:
                st.markdown(f"**Congestion risk:** {ev['congestion_prob']*100:.0f}%")
            if ev.get("law_order_prob") is not None:
                st.markdown(f"**Law & order risk:** {ev['law_order_prob']*100:.0f}%")
        with col_r:
            st.markdown(f"**Duration:** {ev.get('duration_label') or '—'}")
            if ev.get("barricades_json"):
                barricades = json.loads(ev["barricades_json"])
                if barricades:
                    st.markdown(f"**Barricades:** {', '.join(barricades)}")

        # Frozen SHAP explanation
        if ev.get("shap_drivers_json"):
            drivers = json.loads(ev["shap_drivers_json"])
            st.markdown(f"**Why {ev.get('severity')}?** _(explanation frozen at save time)_")
            for d in drivers:
                arrow = "▲" if d["direction"] == "+" else "▼"
                st.markdown(f"{arrow} **{d['direction']}{d['pct']}%** &nbsp; {d['display']}")

        # Live recompute
        if ev.get("feature_vector_json") and st.button("Recompute with current model"):
            state = load_and_train()
            fv = (
                json.loads(ev["feature_vector_json"])
                if isinstance(ev["feature_vector_json"], str)
                else ev["feature_vector_json"]
            )
            live = explain_severity(
                state["explainers"]["severity"],
                state["pipeline"],
                fv,
                ev.get("severity", "LOW"),
            )
            st.markdown("**Live explanation (current model):**")
            for d in live:
                arrow = "▲" if d["direction"] == "+" else "▼"
                st.markdown(f"{arrow} **{d['direction']}{d['pct']}%** &nbsp; {d['display']}")

        # Status actions
        st.markdown("---")
        sa, sb, sc = st.columns(3)
        if ev["status"] == "planned" and sa.button("Mark Active"):
            event_store.update_status(clicked_id, "active")
            st.rerun()
        if ev["status"] in ("planned", "active") and sb.button("Mark Completed"):
            event_store.update_status(clicked_id, "completed")
            st.rerun()
        if ev["status"] not in ("cancelled", "completed") and sc.button("Cancel Event"):
            event_store.update_status(clicked_id, "cancelled")
            st.rerun()
