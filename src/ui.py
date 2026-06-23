import streamlit as st


def inject_css() -> None:
    st.markdown("""<style>
    /* ── Metric cards ───────────────────────────────────── */
    [data-testid="stMetric"] {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px 16px !important;
    }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }

    /* ── Section header accent ──────────────────────────── */
    .section-header {
        border-left: 3px solid #3B82F6;
        padding-left: 10px;
        margin: 20px 0 10px 0;
        font-size: 1.05rem;
        font-weight: 600;
        color: #F1F5F9;
    }

    /* ── Page header ────────────────────────────────────── */
    .page-header-title {
        font-size: 1.8rem;
        font-weight: 700;
        color: #F1F5F9;
        margin-bottom: 2px;
        line-height: 1.2;
    }
    .page-header-sub {
        color: #94A3B8;
        font-size: 0.9rem;
        margin-bottom: 20px;
    }

    /* ── Severity badge ─────────────────────────────────── */
    .severity-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 99px;
        font-weight: 700;
        font-size: 0.9rem;
        letter-spacing: 0.06em;
        vertical-align: middle;
    }

    /* ── Dataframe header ───────────────────────────────── */
    [data-testid="stDataFrame"] th {
        background-color: #1E293B !important;
        color: #94A3B8 !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* ── Sidebar ─────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        border-right: 1px solid #334155;
    }

    /* ── Form container ─────────────────────────────────── */
    [data-testid="stForm"] {
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 20px !important;
    }

    /* ── Buttons ─────────────────────────────────────────── */
    .stButton > button {
        border-radius: 6px;
        border-color: #334155;
        font-weight: 500;
    }
    .stButton > button[kind="primary"] {
        background-color: #3B82F6 !important;
        border: none !important;
        font-weight: 600;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #2563EB !important;
    }

    /* ── Expander ────────────────────────────────────────── */
    [data-testid="stExpander"] {
        border: 1px solid #334155 !important;
        border-radius: 8px;
    }

    /* ── Tabs ────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px 6px 0 0;
        font-weight: 500;
    }

    /* ── Alert boxes ─────────────────────────────────────── */
    [data-testid="stAlert"] { border-radius: 8px; }

    /* ── Hide Streamlit chrome ───────────────────────────── */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    </style>""", unsafe_allow_html=True)


def severity_badge(severity: str) -> None:
    _styles = {
        "HIGH":   "background:#DC2626;color:#fff",
        "MEDIUM": "background:#D97706;color:#fff",
        "LOW":    "background:#16A34A;color:#fff",
    }
    style = _styles.get(severity, "background:#475569;color:#fff")
    st.markdown(
        f'<span class="severity-badge" style="{style}">{severity}</span>',
        unsafe_allow_html=True,
    )


def risk_gauge(label: str, prob: float) -> None:
    if prob < 0.33:
        level, color = "LOW", "#16A34A"
    elif prob < 0.66:
        level, color = "MEDIUM", "#D97706"
    else:
        level, color = "HIGH", "#DC2626"
    pct = int(prob * 100)
    st.markdown(
        f"**{label}** &nbsp;&nbsp;"
        f'<span style="color:{color};font-weight:700">{level}</span> '
        f'<span style="color:#94A3B8;font-size:0.85rem">({pct}%)</span>',
        unsafe_allow_html=True,
    )
    st.progress(prob)


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
