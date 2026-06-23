# pages/3_Post_Event_Report.py
import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src.ui import inject_css, page_header, section_header

REPORT_FILE = Path("data/reports/post_event_reports.csv")

_COLS = [
    "report_datetime", "event_name", "corridor", "predicted_severity",
    "predicted_congestion_prob", "predicted_law_order_prob", "predicted_duration",
    "actual_attendance", "officers_deployed", "vehicles_used",
    "actual_congestion", "law_order_incidents", "actual_duration_h",
    "avg_response_time_min", "deployment_accuracy",
    "deployment_effectiveness", "public_safety_score",
    "challenges", "recommendations",
]

st.set_page_config(page_title="Post-Event Report", layout="wide")
inject_css()
st.page_link("pages/1_Plan_Event.py", label="← Back to form")
st.page_link("pages/2_Results.py",    label="← Back to results")
page_header("Post-Event Report", subtitle="File an after-action report to improve future predictions.")

# ── Pre-fill from session state if available ─────────────────────────────────
r     = st.session_state.get("result_data", {})
risks = r.get("risks", {}) if r else {}

if r:
    st.info(
        f"Pre-filling from last prediction: **{r.get('event_name', '')}** "
        f"on **{r.get('corridor', '')}** — predicted **{r.get('severity', '')}**"
    )

prefill_name     = r.get("event_name", "")      if r else ""
prefill_corridor = r.get("corridor", "")        if r else ""
prefill_severity = r.get("severity", "N/A")     if r else "N/A"
pred_cong_prob   = risks.get("congestion_prob", "") if risks else ""
pred_law_prob    = risks.get("law_order_prob",  "") if risks else ""
pred_duration    = r.get("duration", "")        if r else ""

# ── Report form ───────────────────────────────────────────────────────────────
with st.form("post_event_form"):
    section_header("Event Identity")
    id1, id2 = st.columns(2)
    with id1:
        event_name = st.text_input("Event name", value=prefill_name)
        corridor   = st.text_input("Corridor",   value=prefill_corridor)
    with id2:
        pred_sev_disp = st.text_input(
            "Predicted severity (from system)", value=prefill_severity, disabled=True
        )
        event_date = st.date_input("Event date", value=datetime.date.today())

    section_header("Actual Deployment")
    d1, d2, d3 = st.columns(3)
    with d1:
        actual_attendance  = st.number_input("Actual attendance",        min_value=0, value=0, step=50)
        officers_deployed  = st.number_input("Officers deployed (total)", min_value=0, value=0, step=1)
    with d2:
        vehicles_used      = st.number_input("Vehicles used",            min_value=0, value=0, step=1)
        avg_response_time  = st.number_input(
            "Avg response time to incident (min)", min_value=0.0, value=0.0, step=1.0
        )
    with d3:
        actual_duration_h  = st.number_input(
            "Actual event duration (hours)", min_value=0.0, value=2.0, step=0.5
        )
        deployment_accuracy = st.selectbox(
            "Officers vs requirement",
            ["accurate", "over-deployed", "under-deployed"],
        )

    section_header("Actual Outcomes")
    o1, o2 = st.columns(2)
    with o1:
        actual_congestion = st.selectbox(
            "Actual traffic congestion", ["none", "low", "medium", "high"]
        )
        law_order_incidents = st.number_input(
            "Law & order incidents", min_value=0, value=0
        )
    with o2:
        deployment_effectiveness = st.slider(
            "Deployment effectiveness (1 = poor, 5 = excellent)", 1, 5, 3
        )
        public_safety_score = st.slider(
            "Public safety outcome (1 = poor, 5 = excellent)", 1, 5, 3
        )

    section_header("Officer Observations")
    challenges      = st.text_area("Operational challenges faced", value="", height=100)
    recommendations = st.text_area("Recommendations for next time", value="", height=100)

    submitted = st.form_submit_button("Submit Report", type="primary")

# ── Save report ───────────────────────────────────────────────────────────────
if submitted:
    if not event_name.strip():
        st.error("Event name is required.")
    else:
        row = {
            "report_datetime":        datetime.datetime.now().isoformat(timespec="seconds"),
            "event_name":             event_name,
            "corridor":               corridor,
            "predicted_severity":     prefill_severity,
            "predicted_congestion_prob": f"{pred_cong_prob:.2f}" if isinstance(pred_cong_prob, float) else pred_cong_prob,
            "predicted_law_order_prob":  f"{pred_law_prob:.2f}"  if isinstance(pred_law_prob,  float) else pred_law_prob,
            "predicted_duration":     pred_duration,
            "actual_attendance":      actual_attendance,
            "officers_deployed":      officers_deployed,
            "vehicles_used":          vehicles_used,
            "actual_congestion":      actual_congestion,
            "law_order_incidents":    law_order_incidents,
            "actual_duration_h":      actual_duration_h,
            "avg_response_time_min":  avg_response_time,
            "deployment_accuracy":    deployment_accuracy,
            "deployment_effectiveness": deployment_effectiveness,
            "public_safety_score":    public_safety_score,
            "challenges":             challenges,
            "recommendations":        recommendations,
        }
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        new_row = pd.DataFrame([row])
        if REPORT_FILE.exists():
            new_row.to_csv(REPORT_FILE, mode="a", header=False, index=False)
        else:
            new_row.to_csv(REPORT_FILE, index=False)
        st.success(f"Report saved for '{event_name}'.")

# ── Past reports ──────────────────────────────────────────────────────────────
if REPORT_FILE.exists():
    past = pd.read_csv(REPORT_FILE)
    if not past.empty:
        section_header(f"Report History ({len(past)} reports)")

        # Prediction vs actual comparison for severity predictions
        sev_map = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        cong_map = {"none": 0, "low": 1, "medium": 2, "high": 3}

        st.dataframe(
            past.sort_values("report_datetime", ascending=False)[[
                "report_datetime", "event_name", "corridor",
                "predicted_severity", "actual_congestion",
                "actual_attendance", "officers_deployed",
                "deployment_effectiveness", "public_safety_score",
            ]].rename(columns={
                "report_datetime":         "Filed",
                "event_name":              "Event",
                "corridor":                "Corridor",
                "predicted_severity":      "Pred. Severity",
                "actual_congestion":       "Actual Congestion",
                "actual_attendance":       "Attendance",
                "officers_deployed":       "Officers",
                "deployment_effectiveness":"Effectiveness",
                "public_safety_score":     "Safety Score",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Download full history
        st.download_button(
            "Download Full Report History (CSV)",
            data=past.to_csv(index=False),
            file_name="post_event_reports.csv",
            mime="text/csv",
        )
