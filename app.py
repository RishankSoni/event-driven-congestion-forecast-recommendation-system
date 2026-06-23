# app.py
import streamlit as st

st.set_page_config(
    page_title="Event Congestion Planner",
    page_icon="🚦",
    layout="wide",
)

pg = st.navigation(
    {
        "": [
            st.Page("pages/1_Plan_Event.py", title="Plan Event",   icon="📋"),
            st.Page("pages/2_Results.py",    title="Results",       url_path="results"),
        ],
        "OPERATIONS": [
            st.Page("pages/8_Command_Dashboard.py", title="Command Dashboard", icon="🎮"),
            st.Page("pages/7_Deployment_Plan.py",   title="Deployment Plan",   icon="📊"),
            st.Page("pages/6_Station_Registry.py",  title="Station Registry",  icon="🏢"),
        ],
        "EVENTS": [
            st.Page("pages/5_Event_Repository.py",  title="Event Repository",  icon="🗂️"),
            st.Page("pages/4_Event_Calendar.py",    title="Calendar",          icon="📅"),
            st.Page("pages/3_Post_Event_Report.py", title="Post-Event Report", url_path="post-event-report"),
        ],
        "ADVANCED": [
            st.Page("pages/9_Multi_Event_Optimizer.py", title="Multi-Event Optimizer", icon="🔀"),
        ],
    }
)
pg.run()
