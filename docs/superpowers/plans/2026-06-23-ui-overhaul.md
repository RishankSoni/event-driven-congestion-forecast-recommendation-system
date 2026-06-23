# UI Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply a professional dark command-center aesthetic to all 9 pages of the Event Congestion Planner via a shared `src/ui.py` helper module and `.streamlit/config.toml` theme.

**Architecture:** One Streamlit theme config sets the dark base colors app-wide. A new `src/ui.py` module provides `inject_css()`, `severity_badge()`, `risk_gauge()`, `section_header()`, `page_header()`, and `sidebar_metrics()`. Every page imports and calls these helpers, replacing raw markdown headers, text-art bars, and duplicated sidebar blocks.

**Tech Stack:** Python, Streamlit, HTML/CSS via `st.markdown(unsafe_allow_html=True)`.

## Global Constraints

- No changes to business logic, model code, or data pipelines
- No external fonts, CDN dependencies, or JS injection
- All CSS injected via `st.markdown(..., unsafe_allow_html=True)` in `inject_css()`
- `inject_css()` called once at the top of every page (after `st.set_page_config`)
- `page_header()` replaces `st.title()` on every page
- `section_header()` replaces `st.markdown("### ...")` section titles throughout
- Raw `st.markdown("---")` dividers between major sections are removed (CSS spacing handles separation)

---

### Task 1: Create `.streamlit/config.toml` and `src/ui.py`

**Files:**
- Create: `.streamlit/config.toml`
- Create: `src/ui.py`

**Interfaces:**
- Produces:
  - `inject_css() -> None`
  - `severity_badge(severity: str) -> None`
  - `risk_gauge(label: str, prob: float) -> None`
  - `section_header(title: str) -> None`
  - `page_header(title: str, subtitle: str = "") -> None`
  - `sidebar_metrics(state: dict) -> None`

- [ ] **Step 1: Create `.streamlit/config.toml`**

```toml
[theme]
base = "dark"
primaryColor = "#3B82F6"
backgroundColor = "#0F172A"
secondaryBackgroundColor = "#1E293B"
textColor = "#F1F5F9"
font = "sans serif"
```

- [ ] **Step 2: Create `src/ui.py`**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add .streamlit/config.toml src/ui.py
git commit -m "feat: add dark theme config and shared ui.py helper module"
```

---

### Task 2: Update Page 1 — Plan Event

**Files:**
- Modify: `pages/1_Plan_Event.py`

**Interfaces:**
- Consumes: `inject_css`, `page_header`, `section_header`, `sidebar_metrics` from `src.ui`

- [ ] **Step 1: Replace imports and sidebar block**

At the top of `pages/1_Plan_Event.py`, add the import:
```python
from src.ui import inject_css, page_header, section_header, sidebar_metrics
```

After `st.set_page_config(...)`, add `inject_css()`.

Replace:
```python
st.sidebar.markdown("### Model Performance")
st.sidebar.metric("CV macro-F1 (train)", f"{state['cv_f1']:.3f}")
st.sidebar.metric("Test macro-F1",       f"{state['test_f1']:.3f}")
st.sidebar.metric("Congestion AUC",      f"{state['risk_models']['congestion_auc']:.3f}")
st.sidebar.metric("Law & Order AUC",     f"{state['risk_models']['law_order_auc']:.3f}")
st.sidebar.caption("Baseline (majority class): ~0.22 on 3-class problem")
```
With:
```python
sidebar_metrics(state)
```

- [ ] **Step 2: Replace title and section markers**

Replace:
```python
st.title("Event Congestion Planner")
st.markdown(
    "Enter details of an upcoming event to forecast traffic impact "
    "and generate a deployment plan."
)
```
With:
```python
page_header(
    "Event Congestion Planner",
    subtitle="Enter details of an upcoming event to forecast traffic impact and generate a deployment plan.",
)
```

Replace `st.markdown("**Calendar context**")` with `section_header("Calendar Context")`.

Replace `st.markdown("**Planned event details**")` with `section_header("Planned Event Details")`.

Replace `st.markdown("**Incident details**")` with `section_header("Incident Details")`.

Remove all `st.markdown("---")` lines inside the form.

- [ ] **Step 3: Commit**

```bash
git add pages/1_Plan_Event.py
git commit -m "feat: apply dark UI theme to Plan Event page"
```

---

### Task 3: Update Page 2 — Results

**Files:**
- Modify: `pages/2_Results.py`

**Interfaces:**
- Consumes: `inject_css`, `page_header`, `section_header`, `sidebar_metrics`, `severity_badge`, `risk_gauge` from `src.ui`
- `_risk_bar()` and `_risk_label()` functions are removed entirely (replaced by `risk_gauge`)

- [ ] **Step 1: Add import, inject CSS, update sidebar**

Add import:
```python
from src.ui import inject_css, page_header, section_header, sidebar_metrics, severity_badge, risk_gauge
```

After `st.set_page_config(...)` call `inject_css()`.

Replace sidebar block (same pattern as page 1): replace raw sidebar metrics with `sidebar_metrics(state)`.

- [ ] **Step 2: Update header and severity display**

Replace:
```python
st.page_link("pages/1_Plan_Event.py", label="← Back to form")
st.title(f"Deployment Plan — {r['event_name']}")
```
With:
```python
st.page_link("pages/1_Plan_Event.py", label="← Back to form")
page_header(f"Deployment Plan — {r['event_name']}")
```

In the `with left:` block, replace:
```python
    st.markdown(f"## {severity}")
    st.caption(f"Confidence: {conf_pct:.0f}%  |  Corridor: {r['corridor']}")
```
With:
```python
    severity_badge(severity)
    st.markdown(
        f'<span style="color:#94A3B8;font-size:0.85rem">'
        f'Confidence: {conf_pct:.0f}%  |  Corridor: {r["corridor"]}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("")
```

- [ ] **Step 3: Replace risk bars and section headers**

Remove the `_risk_bar()` and `_risk_label()` functions entirely.

Replace:
```python
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
```
With:
```python
    section_header("Risk Forecast")
    cong_prob = risks["congestion_prob"]
    law_prob  = risks["law_order_prob"]
    risk_gauge("Traffic Congestion", cong_prob)
    risk_gauge("Law & Order", law_prob)
```

- [ ] **Step 4: Update remaining section headers**

Replace every `st.markdown("---")\n    st.markdown("### Action Plan")` pattern with `section_header("Action Plan")` (removing the `---` line).

Replace `st.markdown("### Recommended Stations")` with `section_header("Recommended Stations")`.

Replace `st.markdown(f"### Why {severity}?")` with `section_header(f"Why {severity}?")`.

Replace `st.markdown("### 5 Similar Past Events")` with `section_header("5 Similar Past Events")`.

Remove all remaining bare `st.markdown("---")` divider lines in this file.

- [ ] **Step 5: Update map section header**

In the `with right:` block, replace:
```python
    st.markdown("### Impact Map")
```
With:
```python
    section_header("Impact Map")
```

- [ ] **Step 6: Commit**

```bash
git add pages/2_Results.py
git commit -m "feat: apply dark UI theme to Results page; replace text-art risk bars"
```

---

### Task 4: Update Pages 3, 4, 5

**Files:**
- Modify: `pages/3_Post_Event_Report.py`
- Modify: `pages/4_Event_Calendar.py`
- Modify: `pages/5_Event_Repository.py`

**Interfaces:**
- Consumes: `inject_css`, `page_header`, `section_header` from `src.ui`

- [ ] **Step 1: Update Page 3 — Post-Event Report**

Add import: `from src.ui import inject_css, page_header, section_header`

After `st.set_page_config(...)` call `inject_css()`.

Replace:
```python
st.title("Post-Event Report")
st.markdown("File an after-action report to improve future predictions.")
```
With:
```python
page_header("Post-Event Report", subtitle="File an after-action report to improve future predictions.")
```

Inside the form, replace:
- `st.markdown("### Event Identity")` → `section_header("Event Identity")`
- `st.markdown("---")\n    st.markdown("### Actual Deployment")` → `section_header("Actual Deployment")`
- `st.markdown("---")\n    st.markdown("### Actual Outcomes")` → `section_header("Actual Outcomes")`
- `st.markdown("---")\n    st.markdown("### Officer Observations")` → `section_header("Officer Observations")`

Replace `st.markdown(f"### Report History ({len(past)} reports)")` with `section_header(f"Report History ({len(past)} reports)")`.

Remove all remaining `st.markdown("---")` divider lines.

- [ ] **Step 2: Update Page 4 — Event Calendar**

Add import: `from src.ui import inject_css, page_header, section_header`

After `st.set_page_config(...)` call `inject_css()`.

Replace `st.title("Event Calendar")` with `page_header("Event Calendar", subtitle="Saved events by date — click an event to view details.")`.

- [ ] **Step 3: Update Page 5 — Event Repository**

Add import: `from src.ui import inject_css, page_header`

After `st.set_page_config(...)` call `inject_css()`.

Replace `st.title("Event Repository")` with `page_header("Event Repository", subtitle="Search and manage all saved events.")`.

In the sidebar, replace `st.markdown("### Filters")` with:
```python
st.markdown('<div class="section-header" style="margin-top:4px">Filters</div>', unsafe_allow_html=True)
```

Remove `st.markdown("---")` inside the detail expander.

- [ ] **Step 4: Commit**

```bash
git add pages/3_Post_Event_Report.py pages/4_Event_Calendar.py pages/5_Event_Repository.py
git commit -m "feat: apply dark UI theme to Post-Event Report, Calendar, Repository pages"
```

---

### Task 5: Update Pages 6, 7, 8, 9

**Files:**
- Modify: `pages/6_Station_Registry.py`
- Modify: `pages/7_Deployment_Plan.py`
- Modify: `pages/8_Command_Dashboard.py`
- Modify: `pages/9_Multi_Event_Optimizer.py`

**Interfaces:**
- Consumes: `inject_css`, `page_header`, `section_header`, `severity_badge` from `src.ui`

- [ ] **Step 1: Update Page 6 — Station Registry**

Add import: `from src.ui import inject_css, page_header, section_header`

After `st.set_page_config(...)` call `inject_css()`.

Replace `st.title("Station Registry")` with `page_header("Station Registry", subtitle="Manage police station capacities and geocoding.")`.

Inside the Geocoding tab, replace `st.markdown("---")` dividers with nothing (remove them).

- [ ] **Step 2: Update Page 7 — Deployment Plan**

Add import: `from src.ui import inject_css, page_header, section_header, severity_badge`

After `st.set_page_config(...)` call `inject_css()`.

Replace `st.title("Deployment Plan")` with `page_header("Deployment Plan")`.

Replace the event header block:
```python
sev = event.get("severity", "—")
sev_color = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}.get(sev, "⚫")
st.markdown(
    f"**{event.get('event_name', '—')}** &nbsp; {sev_color} {sev} &nbsp;|&nbsp; "
    f"{event.get('event_date', '')} {event.get('event_time', '')} &nbsp;|&nbsp; "
    f"{event.get('corridor', '—')}"
)
```
With:
```python
sev = event.get("severity", "—")
col_ev, col_sev = st.columns([3, 1])
with col_ev:
    st.markdown(
        f"**{event.get('event_name', '—')}** &nbsp;|&nbsp; "
        f"{event.get('event_date', '')} {event.get('event_time', '')} &nbsp;|&nbsp; "
        f"{event.get('corridor', '—')}"
    )
with col_sev:
    severity_badge(sev)
```

Replace all `st.subheader(...)` calls with `section_header(...)`:
- `st.subheader("Operational Briefing")` → `section_header("Operational Briefing")`
- `st.subheader("Station Deployment")` → `section_header("Station Deployment")`
- `st.subheader("Officer Strength")` → `section_header("Officer Strength")`
- `st.subheader("Barricades & Diversions")` → `section_header("Barricades & Diversions")`
- `st.subheader("Support Requirements")` → `section_header("Support Requirements")`
- `st.subheader("Deployment Timeline")` → `section_header("Deployment Timeline")`

Remove all `st.markdown("---")` dividers.

- [ ] **Step 3: Update Page 8 — Command Dashboard**

Add import: `from src.ui import inject_css, page_header, section_header`

After `st.set_page_config(...)` call `inject_css()`.

Replace:
```python
st.title("Command Dashboard")
st.caption(f"Today: {date.today().strftime('%A, %d %B %Y')}")
```
With:
```python
page_header("Command Dashboard", subtitle=date.today().strftime("%A, %d %B %Y"))
```

Replace `st.markdown("### Today's Events")` with `section_header("Today's Events")`.

Replace `st.markdown("### Upcoming 7 Days")` with `section_header("Upcoming 7 Days")`.

Remove all `st.markdown("---")` dividers.

- [ ] **Step 4: Update Page 9 — Multi-Event Optimizer**

Add import: `from src.ui import inject_css, page_header, section_header`

After `st.set_page_config(...)` call `inject_css()`.

Replace:
```python
st.title("Multi-Event Optimizer")
st.caption("Plan officer and station assignments for multiple concurrent events.")
```
With:
```python
page_header("Multi-Event Optimizer", subtitle="Plan officer and station assignments for multiple concurrent events.")
```

Replace `st.markdown("### Combined Resource Summary")` with `section_header("Combined Resource Summary")`.

Replace `st.markdown("### Per-Event Station Assignments")` with `section_header("Per-Event Station Assignments")`.

Remove all `st.markdown("---")` dividers.

- [ ] **Step 5: Commit**

```bash
git add pages/6_Station_Registry.py pages/7_Deployment_Plan.py pages/8_Command_Dashboard.py pages/9_Multi_Event_Optimizer.py
git commit -m "feat: apply dark UI theme to Station Registry, Deployment Plan, Dashboard, Optimizer"
```
