import streamlit as st


def inject_css() -> None:
    st.markdown("""<style>

    /* ══════════════════════════════════════════════════
       ANIMATIONS
    ══════════════════════════════════════════════════ */
    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(12px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes riskPulse {
        0%, 100% { box-shadow: 0 0 6px rgba(239,68,68,0.4); }
        50%       { box-shadow: 0 0 18px rgba(239,68,68,0.8); }
    }
    @keyframes fillBar {
        from { transform: scaleX(0); transform-origin: left center; }
        to   { transform: scaleX(1); transform-origin: left center; }
    }

    /* ══════════════════════════════════════════════════
       GLOBAL
    ══════════════════════════════════════════════════ */
    .stApp {
        background: #0B1220 !important;
    }
    .main .block-container {
        animation: fadeInUp 380ms ease-out;
        padding-top: 2rem !important;
        max-width: 1400px;
    }

    /* ══════════════════════════════════════════════════
       SIDEBAR
    ══════════════════════════════════════════════════ */
    [data-testid="stSidebar"] {
        background: rgba(11,18,32,0.95) !important;
        backdrop-filter: blur(20px) !important;
        border-right: 1px solid rgba(255,255,255,0.06) !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        background: transparent !important;
    }
    [data-testid="stSidebarNavLink"],
    [data-testid="stSidebarNav"] a {
        border-radius: 8px !important;
        margin: 2px 6px !important;
        padding: 8px 14px !important;
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        color: #94A3B8 !important;
        transition: all 150ms ease-out !important;
        border-left: 3px solid transparent !important;
        text-decoration: none !important;
        display: block !important;
    }
    [data-testid="stSidebarNavLink"]:hover,
    [data-testid="stSidebarNav"] a:hover {
        background: rgba(255,255,255,0.04) !important;
        color: #E2E8F0 !important;
        border-left-color: rgba(59,130,246,0.4) !important;
    }
    [data-testid="stSidebarNavLink"][aria-current="page"],
    [data-testid="stSidebarNav"] a[aria-current="page"] {
        background: rgba(59,130,246,0.12) !important;
        color: #93C5FD !important;
        border-left-color: #3B82F6 !important;
        font-weight: 600 !important;
    }

    /* ══════════════════════════════════════════════════
       HIDE WORKFLOW-ONLY PAGES FROM SIDEBAR NAV
       Results and Post-Event-Report are accessed via
       st.switch_page only — not via the sidebar.
    ══════════════════════════════════════════════════ */
    [data-testid="stSidebarNavLink"][href="/results"],
    [data-testid="stSidebarNavLink"][href="/post-event-report"],
    li:has([data-testid="stSidebarNavLink"][href="/results"]),
    li:has([data-testid="stSidebarNavLink"][href="/post-event-report"]) {
        display: none !important;
    }

    /* Sidebar metric color cycling */
    [data-testid="stSidebar"] [data-testid="stMetric"]:nth-of-type(1) { border-top-color: #3B82F6 !important; }
    [data-testid="stSidebar"] [data-testid="stMetric"]:nth-of-type(2) { border-top-color: #22C55E !important; }
    [data-testid="stSidebar"] [data-testid="stMetric"]:nth-of-type(3) { border-top-color: #F59E0B !important; }
    [data-testid="stSidebar"] [data-testid="stMetric"]:nth-of-type(4) { border-top-color: #A78BFA !important; }

    /* ══════════════════════════════════════════════════
       PAGE HEADER
    ══════════════════════════════════════════════════ */
    .page-header-title {
        font-size: 2rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 4px;
        line-height: 1.15;
        letter-spacing: -0.01em;
    }
    .page-header-sub {
        color: #94A3B8;
        font-size: 0.9rem;
        margin-bottom: 28px;
        letter-spacing: 0.01em;
    }

    /* ══════════════════════════════════════════════════
       SECTION HEADER
    ══════════════════════════════════════════════════ */
    .section-header {
        border-left: 3px solid #3B82F6;
        padding-left: 10px;
        margin: 28px 0 12px 0;
        font-size: 0.78rem;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.09em;
    }

    /* ══════════════════════════════════════════════════
       GLASS CARDS — Forms & Expanders
    ══════════════════════════════════════════════════ */
    [data-testid="stForm"] {
        background: #162033 !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 16px !important;
        padding: 24px 28px !important;
        box-shadow: 0 4px 24px rgba(0,0,0,0.45), 0 1px 0 rgba(255,255,255,0.04) inset !important;
        transition: box-shadow 200ms ease-out !important;
    }
    [data-testid="stForm"]:hover {
        box-shadow: 0 6px 32px rgba(0,0,0,0.55), 0 1px 0 rgba(255,255,255,0.04) inset !important;
    }
    [data-testid="stExpander"] {
        background: #162033 !important;
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 14px !important;
        overflow: hidden !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.3) !important;
        transition: transform 200ms ease-out, box-shadow 200ms ease-out !important;
        margin-bottom: 8px !important;
    }
    [data-testid="stExpander"]:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.42) !important;
    }
    [data-testid="stExpander"] summary {
        padding: 14px 18px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
    }

    /* ══════════════════════════════════════════════════
       METRIC CARDS
    ══════════════════════════════════════════════════ */
    [data-testid="stMetric"] {
        background: #162033 !important;
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 14px !important;
        border-top: 2px solid #3B82F6 !important;
        padding: 16px 20px !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.3) !important;
        transition: transform 200ms ease-out, box-shadow 200ms ease-out !important;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(0,0,0,0.45) !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.7rem !important;
        font-weight: 700 !important;
        color: #F8FAFC !important;
        letter-spacing: -0.02em !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.07em !important;
        color: #94A3B8 !important;
        font-weight: 600 !important;
    }

    /* ══════════════════════════════════════════════════
       SEVERITY BADGE
    ══════════════════════════════════════════════════ */
    .severity-badge {
        display: inline-block;
        padding: 6px 18px;
        border-radius: 99px;
        font-weight: 700;
        font-size: 0.82rem;
        letter-spacing: 0.1em;
        vertical-align: middle;
        text-transform: uppercase;
    }

    /* ══════════════════════════════════════════════════
       RISK GAUGE
    ══════════════════════════════════════════════════ */
    .risk-gauge-wrap { margin: 8px 0 18px 0; }
    .risk-gauge-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
    }
    .risk-gauge-label {
        font-size: 0.875rem;
        font-weight: 500;
        color: #CBD5E1;
    }
    .risk-gauge-pill {
        display: inline-flex;
        align-items: center;
        padding: 3px 12px;
        border-radius: 99px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        gap: 6px;
    }
    .risk-pill-low    { background: rgba(22,163,74,0.18);  color: #4ADE80; }
    .risk-pill-medium { background: rgba(217,119,6,0.18);  color: #FCD34D; }
    .risk-pill-high   { background: rgba(220,38,38,0.18);  color: #F87171; animation: riskPulse 2s ease-in-out infinite; }
    .risk-bar-track {
        width: 100%;
        height: 7px;
        background: rgba(255,255,255,0.06);
        border-radius: 99px;
        overflow: hidden;
    }
    .risk-bar-fill {
        height: 100%;
        border-radius: 99px;
        animation: fillBar 700ms cubic-bezier(0.4,0,0.2,1);
    }
    .risk-bar-low    { background: linear-gradient(90deg,#16A34A,#22C55E); box-shadow: 0 0 8px rgba(34,197,94,0.45); }
    .risk-bar-medium { background: linear-gradient(90deg,#D97706,#F59E0B); box-shadow: 0 0 8px rgba(245,158,11,0.45); }
    .risk-bar-high   { background: linear-gradient(90deg,#DC2626,#EF4444); box-shadow: 0 0 10px rgba(239,68,68,0.55); }

    /* ══════════════════════════════════════════════════
       AI INSIGHT CARD
    ══════════════════════════════════════════════════ */
    .ai-insight-card {
        border-left: 3px solid #3B82F6;
        background: rgba(59,130,246,0.07);
        border-radius: 0 12px 12px 0;
        padding: 14px 18px;
        margin: 8px 0 16px 0;
        color: #CBD5E1;
        font-size: 0.9rem;
        line-height: 1.65;
    }
    .ai-insight-card strong { color: #E2E8F0; }

    /* ══════════════════════════════════════════════════
       KPI CARD (custom HTML metric)
    ══════════════════════════════════════════════════ */
    .kpi-card {
        background: #162033;
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 14px;
        border-top-width: 2px;
        border-top-style: solid;
        padding: 18px 22px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.3);
        transition: transform 200ms ease-out, box-shadow 200ms ease-out;
        height: 100%;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 22px rgba(0,0,0,0.42);
    }
    .kpi-label {
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        color: #64748B;
        margin-bottom: 10px;
    }
    .kpi-value {
        font-size: 2.1rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        line-height: 1;
    }
    .kpi-sub {
        font-size: 0.75rem;
        color: #64748B;
        margin-top: 6px;
    }

    /* ══════════════════════════════════════════════════
       BUTTONS
    ══════════════════════════════════════════════════ */
    .stButton > button,
    [data-testid="baseButton-secondary"] {
        border-radius: 10px !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        padding: 8px 20px !important;
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #E2E8F0 !important;
        transition: all 150ms ease-out !important;
    }
    .stButton > button:hover,
    [data-testid="baseButton-secondary"]:hover {
        background: rgba(255,255,255,0.09) !important;
        border-color: rgba(255,255,255,0.16) !important;
        transform: translateY(-1px) !important;
    }
    .stButton > button:active,
    [data-testid="baseButton-secondary"]:active {
        transform: translateY(0) !important;
    }
    .stButton > button[kind="primary"],
    [data-testid="baseButton-primary"] {
        background: linear-gradient(135deg,#3B82F6,#2563EB) !important;
        border: none !important;
        font-weight: 600 !important;
        color: #fff !important;
        box-shadow: 0 2px 10px rgba(59,130,246,0.32) !important;
    }
    .stButton > button[kind="primary"]:hover,
    [data-testid="baseButton-primary"]:hover {
        background: linear-gradient(135deg,#60A5FA,#3B82F6) !important;
        box-shadow: 0 4px 16px rgba(59,130,246,0.48) !important;
        transform: translateY(-1px) !important;
    }
    .stButton > button[kind="primary"]:active,
    [data-testid="baseButton-primary"]:active {
        transform: translateY(0) !important;
    }
    .stDownloadButton > button {
        border-radius: 10px !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #CBD5E1 !important;
        transition: all 150ms ease-out !important;
    }
    .stDownloadButton > button:hover {
        background: rgba(255,255,255,0.08) !important;
        transform: translateY(-1px) !important;
    }

    /* ══════════════════════════════════════════════════
       FORM INPUTS
    ══════════════════════════════════════════════════ */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 10px !important;
        color: #F1F5F9 !important;
        padding: 10px 14px !important;
        font-size: 0.9rem !important;
        transition: border-color 150ms, box-shadow 150ms !important;
    }
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 3px rgba(59,130,246,0.18) !important;
    }
    .stTextArea > div > div > textarea {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 10px !important;
        color: #F1F5F9 !important;
        font-size: 0.9rem !important;
        transition: border-color 150ms, box-shadow 150ms !important;
    }
    .stTextArea > div > div > textarea:focus {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 3px rgba(59,130,246,0.18) !important;
    }
    .stSelectbox > div > div,
    .stMultiSelect > div > div {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 10px !important;
        transition: border-color 150ms !important;
    }
    .stSelectbox > div > div:focus-within {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 3px rgba(59,130,246,0.18) !important;
    }
    .stDateInput > div > div > input,
    .stTimeInput > div > div > input {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 10px !important;
        color: #F1F5F9 !important;
    }

    /* ══════════════════════════════════════════════════
       RADIO — pill toggle
    ══════════════════════════════════════════════════ */
    [data-testid="stRadio"] > div {
        gap: 8px !important;
        flex-wrap: wrap !important;
    }
    [data-testid="stRadio"] label {
        border-radius: 99px !important;
        padding: 6px 18px !important;
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        cursor: pointer !important;
        transition: all 150ms ease-out !important;
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        color: #94A3B8 !important;
    }
    [data-testid="stRadio"] label:hover {
        background: rgba(255,255,255,0.08) !important;
        color: #E2E8F0 !important;
    }
    [data-testid="stRadio"] label:has(input:checked) {
        background: rgba(59,130,246,0.15) !important;
        border-color: rgba(59,130,246,0.4) !important;
        color: #93C5FD !important;
        font-weight: 600 !important;
    }

    /* ══════════════════════════════════════════════════
       TABLES
    ══════════════════════════════════════════════════ */
    [data-testid="stDataFrame"],
    [data-testid="stTable"] {
        border-radius: 12px !important;
        overflow: hidden !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25) !important;
    }
    [data-testid="stDataFrame"] th,
    [data-testid="stTable"] th {
        background: #1A2740 !important;
        color: #64748B !important;
        font-size: 0.7rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.07em !important;
        padding: 11px 16px !important;
        border-bottom: 1px solid rgba(255,255,255,0.06) !important;
    }
    [data-testid="stDataFrame"] td,
    [data-testid="stTable"] td {
        font-size: 0.875rem !important;
        color: #E2E8F0 !important;
        padding: 10px 16px !important;
        border-bottom: 1px solid rgba(255,255,255,0.03) !important;
    }
    [data-testid="stDataFrame"] tr:nth-child(even) td,
    [data-testid="stTable"] tr:nth-child(even) td {
        background: rgba(255,255,255,0.015) !important;
    }
    [data-testid="stDataFrame"] tr:hover td,
    [data-testid="stTable"] tr:hover td {
        background: rgba(59,130,246,0.07) !important;
    }

    /* ══════════════════════════════════════════════════
       TABS
    ══════════════════════════════════════════════════ */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255,255,255,0.03) !important;
        border-radius: 10px !important;
        padding: 4px !important;
        gap: 2px !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 7px !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        color: #94A3B8 !important;
        padding: 8px 18px !important;
        transition: all 150ms ease-out !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #E2E8F0 !important;
        background: rgba(255,255,255,0.04) !important;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(59,130,246,0.15) !important;
        color: #93C5FD !important;
        font-weight: 600 !important;
    }

    /* ══════════════════════════════════════════════════
       ALERTS
    ══════════════════════════════════════════════════ */
    [data-testid="stAlert"] {
        border-radius: 12px !important;
        border-left-width: 3px !important;
    }

    /* ══════════════════════════════════════════════════
       MAP / IFRAME CONTAINERS
    ══════════════════════════════════════════════════ */
    [data-testid="stCustomComponentV1"] > iframe,
    .stIFrame > iframe {
        border-radius: 14px !important;
    }
    [data-testid="stCustomComponentV1"] {
        border-radius: 14px !important;
        overflow: hidden !important;
    }

    /* ══════════════════════════════════════════════════
       PAGE LINKS
    ══════════════════════════════════════════════════ */
    [data-testid="stPageLink"] a {
        color: #60A5FA !important;
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        text-decoration: none !important;
        transition: color 150ms !important;
    }
    [data-testid="stPageLink"] a:hover { color: #93C5FD !important; }

    /* ══════════════════════════════════════════════════
       CAPTION
    ══════════════════════════════════════════════════ */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: #475569 !important;
        font-size: 0.78rem !important;
    }

    /* ══════════════════════════════════════════════════
       PROGRESS BAR
    ══════════════════════════════════════════════════ */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg,#3B82F6,#60A5FA) !important;
        border-radius: 99px !important;
    }
    .stProgress > div > div > div {
        background: rgba(255,255,255,0.06) !important;
        border-radius: 99px !important;
        height: 6px !important;
    }

    /* ══════════════════════════════════════════════════
       SCROLLBAR
    ══════════════════════════════════════════════════ */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 99px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.18); }

    /* ══════════════════════════════════════════════════
       HIDE STREAMLIT CHROME
    ══════════════════════════════════════════════════ */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }

    </style>""", unsafe_allow_html=True)


def severity_badge(severity: str) -> None:
    _styles = {
        "HIGH":   "background:rgba(220,38,38,0.2);color:#F87171;box-shadow:0 0 14px rgba(239,68,68,0.35)",
        "MEDIUM": "background:rgba(217,119,6,0.2);color:#FCD34D;box-shadow:0 0 10px rgba(245,158,11,0.28)",
        "LOW":    "background:rgba(22,163,74,0.2);color:#4ADE80;box-shadow:0 0 10px rgba(34,197,94,0.28)",
    }
    style = _styles.get(severity, "background:rgba(71,85,105,0.3);color:#94A3B8")
    st.markdown(
        f'<span class="severity-badge" style="{style}">{severity}</span>',
        unsafe_allow_html=True,
    )


def risk_gauge(label: str, prob: float) -> None:
    if prob < 0.33:
        level, css_level = "LOW", "low"
    elif prob < 0.66:
        level, css_level = "MEDIUM", "medium"
    else:
        level, css_level = "HIGH", "high"
    pct = int(prob * 100)
    st.markdown(
        f'<div class="risk-gauge-wrap">'
        f'<div class="risk-gauge-header">'
        f'<span class="risk-gauge-label">{label}</span>'
        f'<span class="risk-gauge-pill risk-pill-{css_level}">{level} &nbsp; {pct}%</span>'
        f'</div>'
        f'<div class="risk-bar-track">'
        f'<div class="risk-bar-fill risk-bar-{css_level}" style="width:{pct}%"></div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def section_header(title: str) -> None:
    st.markdown(
        f'<div class="section-header">{title}</div>',
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="page-header-title">{title}</div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(
            f'<div class="page-header-sub">{subtitle}</div>',
            unsafe_allow_html=True,
        )


def sidebar_metrics(state: dict) -> None:
    st.sidebar.markdown(
        '<div class="section-header" style="margin-top:4px">Model Performance</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.metric("CV macro-F1 (train)", f"{state['cv_f1']:.3f}")
    st.sidebar.metric("Test macro-F1",       f"{state['test_f1']:.3f}")
    st.sidebar.metric("Congestion AUC",      f"{state['risk_models']['congestion_auc']:.3f}")
    st.sidebar.metric("Law & Order AUC",     f"{state['risk_models']['law_order_auc']:.3f}")
    st.sidebar.caption("Baseline (majority class): ~0.22 on 3-class problem")


def ai_insight_card(text: str) -> None:
    """Render an AI-insight styled blue-bordered card."""
    st.markdown(
        f'<div class="ai-insight-card">{text}</div>',
        unsafe_allow_html=True,
    )


def kpi_metric(label: str, value, accent: str = "#3B82F6", subtitle: str = "") -> None:
    """Render a custom premium KPI card with colored accent."""
    sub_html = f'<div class="kpi-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="kpi-card" style="border-top-color:{accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value" style="color:{accent}">{value}</div>'
        f'{sub_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
