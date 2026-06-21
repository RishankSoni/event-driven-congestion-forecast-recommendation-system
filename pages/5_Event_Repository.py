# pages/5_Event_Repository.py
import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src import event_store
from src.app_cache import load_and_train
from src.explainer import explain_severity

st.set_page_config(page_title="Event Repository", layout="wide")
st.title("Event Repository")

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filters")
    today = date.today()
    date_range = st.date_input(
        "Date range",
        value=(today - timedelta(days=30), today + timedelta(days=90)),
    )
    date_from = date_range[0].isoformat() if len(date_range) > 0 else None
    date_to   = date_range[1].isoformat() if len(date_range) > 1 else None

    all_corridors = sorted({
        e["corridor"] for e in event_store.list_events()
        if e.get("corridor")
    })
    sel_corridors = st.multiselect("Corridor", all_corridors)
    sel_type      = st.selectbox("Event type", ["All", "planned", "unplanned"])
    sel_severity  = st.multiselect("Risk level", ["HIGH", "MEDIUM", "LOW"])
    sel_status    = st.multiselect(
        "Status",
        ["planned", "active", "completed", "cancelled"],
        default=["planned", "active"],
    )

# ── Fetch and filter ──────────────────────────────────────────────────────────
events = event_store.list_events(
    date_from=date_from,
    date_to=date_to,
    event_type=sel_type if sel_type != "All" else None,
)
if sel_corridors:
    events = [e for e in events if e.get("corridor") in sel_corridors]
if sel_severity:
    events = [e for e in events if e.get("severity") in sel_severity]
if sel_status:
    events = [e for e in events if e.get("status") in sel_status]

if not events:
    st.info("No events match the current filters.")
    st.stop()

# ── Table ─────────────────────────────────────────────────────────────────────
def _pct(val: float | None) -> str:
    return f"{val*100:.0f}%" if val is not None else "—"


display_df = pd.DataFrame([
    {
        "ID":         e["event_id"][:8],
        "Name":       e["event_name"],
        "Type":       e["event_type"],
        "Cause":      e["event_cause"],
        "Corridor":   e.get("corridor") or "—",
        "Date":       e["event_date"],
        "Time":       e["event_time"],
        "Severity":   e.get("severity") or "—",
        "Congestion": _pct(e.get("congestion_prob")),
        "L&O Risk":   _pct(e.get("law_order_prob")),
        "Status":     e["status"],
    }
    for e in events
])

selection = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ── Detail expander on row select ─────────────────────────────────────────────
sel_rows = selection["selection"]["rows"] if selection else []
if sel_rows:
    ev = events[sel_rows[0]]
    with st.expander(f"📋 {ev['event_name']} — Full Detail", expanded=True):
        d1, d2, d3 = st.columns(3)
        d1.metric("Severity",  ev.get("severity") or "—")
        d2.metric("Officers",  f"{ev.get('officer_min')}–{ev.get('officer_max')}"
                               if ev.get("officer_min") is not None else "—")
        d3.metric("Duration",  ev.get("duration_label") or "—")

        e1, e2 = st.columns(2)
        with e1:
            if ev.get("congestion_prob") is not None:
                st.markdown(f"**Congestion risk:** {ev['congestion_prob']*100:.0f}%")
            if ev.get("barricades_json"):
                barricades = json.loads(ev["barricades_json"])
                if barricades:
                    st.markdown(f"**Barricades:** {', '.join(barricades)}")
        with e2:
            if ev.get("law_order_prob") is not None:
                st.markdown(f"**Law & order risk:** {ev['law_order_prob']*100:.0f}%")
            if ev.get("diversions_json"):
                diversions = json.loads(ev["diversions_json"])
                if diversions:
                    st.markdown(f"**Diversions:** {', '.join(diversions)}")

        # Frozen SHAP
        if ev.get("shap_drivers_json"):
            drivers = json.loads(ev["shap_drivers_json"])
            st.markdown(f"**Why {ev.get('severity')}?** _(frozen at save time)_")
            for d in drivers:
                arrow = "▲" if d["direction"] == "+" else "▼"
                st.markdown(f"{arrow} **{d['direction']}{d['pct']}%** &nbsp; {d['display']}")

        # Live recompute
        if ev.get("feature_vector_json") and st.button(
            "Recompute with current model", key="repo_recompute"
        ):
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
        if ev["status"] == "planned" and sa.button("Mark Active", key="repo_active"):
            event_store.update_status(ev["event_id"], "active")
            st.rerun()
        if ev["status"] in ("planned", "active") and sb.button(
            "Mark Completed", key="repo_complete"
        ):
            event_store.update_status(ev["event_id"], "completed")
            st.rerun()
        if ev["status"] not in ("cancelled", "completed") and sc.button(
            "Cancel Event", key="repo_cancel"
        ):
            event_store.update_status(ev["event_id"], "cancelled")
            st.rerun()
