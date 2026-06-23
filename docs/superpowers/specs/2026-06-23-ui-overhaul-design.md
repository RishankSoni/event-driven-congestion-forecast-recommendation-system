# UI Overhaul Design — Professional Dark Command Center
Date: 2026-06-23

## Overview
Overhaul all 9 pages of the Event Congestion Planner to a professional dark command-center aesthetic. No external branding change. Scope: all pages. Approach: Streamlit theme config + shared `src/ui.py` CSS/component module + page-by-page updates.

---

## Section 1 — Streamlit Theme Config

File: `.streamlit/config.toml`

```toml
[theme]
base = "dark"
primaryColor = "#3B82F6"
backgroundColor = "#0F172A"
secondaryBackgroundColor = "#1E293B"
textColor = "#F1F5F9"
font = "sans serif"
```

Rationale: dark slate base with blue accent gives an operations-room feel. All Streamlit widgets inherit these colors automatically with no per-widget overrides needed.

---

## Section 2 — Shared `src/ui.py` Module

New file providing reusable helpers called at the top of every page.

### `inject_css()`
Injects a single `<style>` block via `st.markdown(..., unsafe_allow_html=True)` covering:
- `.stMetric` containers: border, rounded corners, subtle background, padding
- Dataframe headers: dark background, consistent font
- Form section backgrounds: slightly lighter than page background
- `.stButton > button`: rounded, proper padding, hover states
- Sidebar: border-right, padding adjustments
- Colored progress bar overrides for risk gauges
- Section header left-accent border style (`.section-header` class)

### `severity_badge(severity: str) -> None`
Renders an HTML `<span>` pill with:
- HIGH → red background (`#DC2626`) white text
- MEDIUM → amber background (`#D97706`) white text
- LOW → green background (`#16A34A`) white text

### `risk_gauge(label: str, prob: float) -> None`
Replaces `_risk_bar()` text-art. Renders:
1. Label + percentage in one line
2. `st.progress(prob)` bar
3. LOW / MEDIUM / HIGH colored caption below

### `section_header(title: str) -> None`
Renders a styled `<div>` with left blue accent border and semibold title text. Replaces raw `st.markdown("### ...")` calls throughout.

### `page_header(title: str, subtitle: str = "") -> None`
Renders a top-of-page block: large title + optional muted subtitle/caption line. Replaces `st.title()` + `st.caption()` / `st.markdown()` combos.

### `sidebar_metrics(state: dict) -> None`
Shared sidebar block rendering model performance metrics (CV macro-F1, Test macro-F1, Congestion AUC, Law & Order AUC). Removes duplication between pages 1 and 2.

---

## Section 3 — Page-by-Page Changes

All pages: add `from src.ui import inject_css, page_header, section_header` imports and call `inject_css()` + `page_header()` at the top, replacing `st.title()`.

### Page 1 — Plan Event
- `sidebar_metrics(state)` replaces duplicated sidebar markdown block
- `section_header()` for "Calendar context", "Planned event details", "Incident details"
- Remove raw `st.markdown("---")` dividers between sections (CSS spacing handles it)

### Page 2 — Results
- `severity_badge(severity)` replaces `st.markdown(f"## {severity}")`
- `risk_gauge()` replaces `_risk_bar()` text-art function (function removed)
- `section_header()` for: Risk Forecast, Action Plan, Recommended Stations, Explainability, Similar Past Events
- `sidebar_metrics(state)` replaces duplicated sidebar block
- Barricade and diversion lists rendered with `st.markdown("- ...")` inside a styled container

### Page 3 — Post-Event Report
- `section_header()` for "Event Identity", "Actual Deployment", "Actual Outcomes", "Officer Observations"
- Pre-fill info banner uses `st.info()` (already used, stays)
- Remove raw `st.markdown("---")` dividers

### Page 4 — Event Calendar
- `page_header("Event Calendar", subtitle)` replaces `st.title()`
- Legend caption styled more cleanly inline

### Page 5 — Event Repository
- `page_header()` + `section_header()` throughout
- Remove raw dividers

### Page 6 — Station Registry
- `page_header()` + `section_header()` throughout

### Page 7 — Deployment Plan
- `severity_badge(sev)` in the event header line
- `section_header()` for all 6 sections (Briefing, Station Deployment, Officer Strength, Barricades & Diversions, Support Requirements, Timeline)
- Officer strength metrics styled as cards via CSS

### Page 8 — Command Dashboard
- `page_header("Command Dashboard", subtitle=today_date_string)` replaces title + caption
- `section_header()` for Today's Events and Upcoming 7 Days
- Metric row (Events Today / HIGH Severity / Conflict Pairs / Geocoded Stations) benefits from `.stMetric` card CSS

### Page 9 — Multi-Event Optimizer
- `page_header()` + `section_header()` throughout

---

## Out of Scope
- No changes to business logic, model code, or data pipelines
- No layout restructuring (column splits stay as-is)
- No external fonts or CDN dependencies
- No removal or addition of features
