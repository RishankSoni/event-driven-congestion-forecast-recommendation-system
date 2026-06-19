# Phase 1: Enhanced Police Event Planning System

**Date:** 2026-06-20
**Context:** GRIDLOCK 2.0 — Phase 1 enhancements to the existing Streamlit congestion planner
**Stack:** Python + scikit-learn + LightGBM + SHAP + Streamlit multi-page
**Scope:** Category A enhancements only (no database, no Phase 2 features)

---

## Overview

Four enhancements to the existing single-page Streamlit app:

| Feature | New files | Risk |
|---|---|---|
| 1 — Multi-page restructure | `src/app_cache.py`, `pages/1_Plan_Event.py`, `pages/2_Results.py` | Medium |
| 2 — Calendar intelligence | `src/calendar_intel.py` | Low |
| 3 — Adaptive input form | `pages/1_Plan_Event.py` | Low |
| 4 — Risk models | `src/risk_model.py` | Medium |
| 5 — SHAP explainability | `src/explainer.py` | Low |

The severity classifier (`LGBMClassifier` + `CorridorStatsTransformer`, macro F1 ≈ 0.74) is extended with new features but not otherwise restructured.

---

## Architecture

### File Structure

```
app.py                        ← gutted to ~15-line st.navigation router
pages/
  1_Plan_Event.py             ← adaptive input form
  2_Results.py                ← results dashboard
src/
  app_cache.py                ← NEW: all @st.cache_data / @st.cache_resource
  calendar_intel.py           ← NEW: holiday/festival detection
  risk_model.py               ← NEW: congestion + law-and-order models
  explainer.py                ← NEW: SHAP explanation generation
  pipeline.py                 ← modified: 2 calendar + 3 form columns in load_raw()
  model.py                    ← modified: 5 new entries in NUM_COLS
  # all other src/ files unchanged
```

### State Flow

```
pages/1_Plan_Event.py
  └── user submits form
        ├── predict(pipeline, features)          → severity, confidence
        ├── predict_duration(dur_model, features) → duration
        ├── predict_risks(risk_models, features)  → congestion_prob, law_order_prob
        ├── explain_prediction(explainers, ...)   → shap_drivers (3 models)
        ├── get_knn_neighbors(train_df, features) → neighbors
        ├── barricade_positions(...)              → barricades
        ├── get_diversions(...)                   → diversions
        ├── officer_count(...)                    → officers
        └── build_map(...)                        → fmap
  └── stores all results in st.session_state
  └── st.switch_page("pages/2_Results.py")

pages/2_Results.py
  └── reads st.session_state, renders dashboard
```

### Shared Cache (`src/app_cache.py`)

```python
@st.cache_data
def load_and_train() -> dict:
    # Returns: train_df, pipeline, dur_model, risk_models,
    #          explainers, diversion_graph, baselines,
    #          low_t, high_t, cv_f1, test_f1

@st.cache_resource
def get_road_graph() -> nx.MultiDiGraph:
    ...
```

Both pages import from `src.app_cache`. Training runs once on first load; subsequent page switches are instant.

---

## Feature 1: Calendar Intelligence (`src/calendar_intel.py`)

### Purpose

Label every event (historical and new) with holiday/festival context so the severity and risk models train on real calendar signal.

### Module Interface

```python
get_holiday_info(date: datetime.date) -> dict
# Returns:
{
  "is_holiday":    bool,
  "holiday_type":  "national" | "state" | "festival" | "none",
  "holiday_name":  str,   # e.g. "Dasara", "Republic Day", ""
  "risk_tier":     int,   # 0=none, 1=state, 2=national, 3=major_festival
}
```

### Bundled Calendar

**National holidays (risk_tier=2):**
Republic Day (Jan 26), Independence Day (Aug 15), Gandhi Jayanti (Oct 2),
Christmas (Dec 25), Ambedkar Jayanti (Apr 14)

**Karnataka state holidays (risk_tier=1):**
Rajyotsava (Nov 1), Ugadi (lunar — pre-computed for 2023–2027),
Valmiki Jayanti (lunar — pre-computed), Kanakadasa Jayanti (Nov)

**Major festivals with multi-day windows (risk_tier=3):**
- Dasara: 10-day window ending Vijayadashami (lunar, pre-computed)
- Diwali: ±1 day around main day (lunar, pre-computed)
- Eid al-Fitr: ±1 day (lunar, pre-computed for 2023–2027)
- Eid al-Adha: ±1 day (pre-computed)
- Holi: main day + day before
- New Year's Eve/Day: Dec 31 + Jan 1

**Long weekend detection (risk_tier=1):**
Any Monday/Friday adjacent to a Tuesday/Thursday holiday.

### Integration with `pipeline.py`

`load_raw()` gains two new columns derived from `start_datetime.date()`:
```python
df["is_holiday"]       = df["start_datetime"].dt.date.map(lambda d: get_holiday_info(d)["is_holiday"]).astype(int)
df["holiday_risk_tier"] = df["start_datetime"].dt.date.map(lambda d: get_holiday_info(d)["risk_tier"]).astype(int)
```

### Integration with `model.py`

```python
NUM_COLS = [
    "hour_of_day", "day_of_week", "requires_road_closure",
    "month", "is_weekend",
    "desc_traffic_slow", "desc_breakdown",
    "is_holiday",          # NEW
    "holiday_risk_tier",   # NEW
    "estimated_attendance", # NEW (from form)
    "has_vip",              # NEW (from form)
    "is_route_event",       # NEW (from form)
]
```

Historical rows get `estimated_attendance=0`, `has_vip=0`, `is_route_event=0` as backfilled defaults in `load_raw()`.

---

## Feature 2: Adaptive Input Form (`pages/1_Plan_Event.py`)

### Conditional Logic

```
event_type = st.radio(["Planned", "Unplanned"])

Core block (always visible):
  event_name, event_cause, corridor, priority, date, time, road_closure

Calendar strip (always visible, auto-filled):
  st.selectbox("Holiday context", auto_value, officer_can_override=True)

if event_type == "Planned":
  show: event_category, estimated_attendance, expected_duration_h,
        has_vip, organizer_name (optional)
  show: Route vs Venue toggle
    if route:
      show: start_checkpoint, end_checkpoint, intermediate_stops

if event_type == "Unplanned":
  show: incident_subtype, medical_support_needed
  hide: all planned-only fields
  set defaults: estimated_attendance=0, has_vip=0, is_route_event=0
```

### New Features Written to `features` Dict

| Feature | Type | Default (unplanned) |
|---|---|---|
| `estimated_attendance` | int | 0 |
| `has_vip` | int 0/1 | 0 |
| `is_route_event` | int 0/1 | 0 |
| `holiday_risk_tier` | int 0–3 | from calendar (officer can override) |
| `is_holiday` | int 0/1 | from calendar |

---

## Feature 3: Risk Models (`src/risk_model.py`)

### Model 1 — Traffic Congestion Probability

**Target label:**
```python
p75 = train_df.groupby("corridor")["window_count"].transform("quantile", 0.75)
congestion_label = (train_df["window_count"] > p75).astype(int)
```

**Model:** `LGBMClassifier(class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1)`
**Preprocessing:** Same `ColumnTransformer` as `duration_model.py` (OrdinalEncoder for cats, float passthrough for nums)
**Features:** All 20 features (15 existing + 3 form + 2 calendar)
**Eval metric:** ROC-AUC (reported in sidebar)

### Model 2 — Law & Order Incident Probability

**Target label:**
```python
HIGH_RISK_CAUSES = {"riot", "protest", "procession", "public_event", "vip_movement"}
law_order_label = train_df["event_cause"].isin(HIGH_RISK_CAUSES).astype(int)
```

**Model:** `LGBMClassifier(class_weight="balanced", random_state=42, n_jobs=-1, verbose=-1)`
**Features:** Same 20 features
**Eval metric:** ROC-AUC

### Module Interface

```python
train_risk_models(train_df: pd.DataFrame) -> dict
# Returns: {"congestion": pipeline_a, "law_order": pipeline_b,
#           "congestion_auc": float, "law_order_auc": float}

predict_risks(risk_models: dict, features: dict) -> dict
# Returns: {"congestion_prob": float, "law_order_prob": float}
```

### Display Thresholds

| Probability | Label | Colour |
|---|---|---|
| < 0.33 | LOW | green |
| 0.33–0.66 | MEDIUM | orange |
| > 0.66 | HIGH | red |

---

## Feature 4: SHAP Explainability (`src/explainer.py`)

### Library

`shap.TreeExplainer` — native LightGBM support, no sampling, ~0.3s per prediction.

### Module Interface

```python
build_explainers(trained_models: dict) -> dict
# Called once in app_cache.py alongside model training
# Returns: {"severity": TreeExplainer, "congestion": TreeExplainer, "law_order": TreeExplainer}
# Note: explainer is built on the lgbm step extracted from the pipeline

explain_prediction(
    explainer: shap.TreeExplainer,
    pipeline,
    feature_row: pd.DataFrame,
    predicted_class: str,
) -> list[dict]
# Returns top-5 SHAP drivers sorted by abs(shap_value):
# [{"feature": str, "display": str, "raw_value": any,
#   "shap": float, "direction": "+" | "-", "pct": float}, ...]
```

### Feature Display Name Map

```python
FEATURE_DISPLAY = {
    "corridor_high_rate":     "Historical HIGH-severity rate on this corridor",
    "corridor_event_count":   "Historical event volume on corridor",
    "corridor_auth_rate":     "Authenticated incident rate",
    "corridor_closure_rate":  "Road closure frequency on corridor",
    "is_weekend":             "Weekend event",
    "is_holiday":             "Public holiday",
    "holiday_risk_tier":      "Holiday / festival severity tier",
    "estimated_attendance":   "Expected attendance",
    "has_vip":                "VIP presence",
    "is_route_event":         "Route-based event",
    "hour_band":              "Time of day band",
    "hour_of_day":            "Hour of day",
    "day_of_week":            "Day of week",
    "month":                  "Month",
    "requires_road_closure":  "Road closure required",
    "desc_traffic_slow":      "Congestion keywords in description",
    "desc_breakdown":         "Breakdown keywords in description",
    "event_cause":            "Event cause",
    "event_type":             "Event type",
    "corridor":               "Corridor",
    "priority":               "Priority level",
    "zone":                   "Zone",
    "police_station":         "Police station",
    "junction":               "Junction",
}
```

### UI Rendering (`pages/2_Results.py`)

**Severity explanation (always expanded):**
```
Why HIGH?
▲ +31%  Historical HIGH-severity rate on this corridor  (0.82)
▲ +20%  Weekend event
▲ +14%  Festival period (Dasara, tier 3)
▼  −9%  Low priority flag
▼  −6%  Morning time band
```

**Risk explanations (collapsed by default):**
```
[▶ Why traffic congestion = 73%?]
[▶ Why law & order risk = 41%?]
```

Percentages are normalised SHAP values: `abs(shap_i) / sum(abs(shap_all)) * 100`.

---

## Results Dashboard Layout (`pages/2_Results.py`)

```
┌─ Deployment Plan — {event_name} ──────────────────────────────────────┐
│ [← Back to form]                                                       │
│                                                                        │
│  LEFT (1/3)                  │  RIGHT (2/3)                           │
│  ──────────────────────────  │  ───────────────────────────────────── │
│  ## {SEVERITY}  {conf}%      │  ### Impact Map                        │
│  Corridor: {corridor}        │  [Folium map — unchanged]              │
│  Duration: {label} ({range}) │                                        │
│                              │                                        │
│  ── Risk Forecast ──         │                                        │
│  Traffic Congestion          │                                        │
│    {bar}  {pct}%  {label}    │                                        │
│  Law & Order                 │                                        │
│    {bar}  {pct}%  {label}    │                                        │
│                              │                                        │
│  ── Action Plan ──           │                                        │
│  Officers: {min}–{max} total │                                        │
│  Barricades: {n} positions   │                                        │
│  Diversions: {n} routes      │                                        │
│                              │                                        │
│  ── Why this prediction? ──  │                                        │
│  [SHAP drivers — expanded]   │                                        │
│  [▶ Why congestion = {pct}%] │                                        │
│  [▶ Why law & order = {pct}%]│                                        │
│                              │                                        │
│  ── 5 Similar Past Events ── │                                        │
│  [KNN table — unchanged]     │                                        │
│                              │                                        │
├──────────────────────────────────────────────────────────────────────  │
│  [Export Plan (CSV)]                                                   │
└────────────────────────────────────────────────────────────────────────┘
```

**Sidebar additions:**
```
Model Performance
  CV macro-F1 (train)    {cv_f1}
  Test macro-F1          {test_f1}
  Congestion AUC         {auc}     ← new
  Law & Order AUC        {auc}     ← new
```

**CSV export additions:** `congestion_prob`, `law_order_prob`, `holiday_name`, `holiday_risk_tier`, `has_vip`, `estimated_attendance`, `is_route_event`

---

## File Change Summary

| File | Change |
|---|---|
| `app.py` | Gutted to ~15-line `st.navigation` router |
| `src/app_cache.py` | NEW — `load_and_train()` + `get_road_graph()` |
| `src/calendar_intel.py` | NEW — `get_holiday_info()` with bundled Karnataka/India calendar |
| `src/risk_model.py` | NEW — `train_risk_models()`, `predict_risks()` |
| `src/explainer.py` | NEW — `build_explainers()`, `explain_prediction()`, `FEATURE_DISPLAY` |
| `src/pipeline.py` | `load_raw()` adds `is_holiday`, `holiday_risk_tier`, `estimated_attendance`, `has_vip`, `is_route_event` (backfilled defaults) |
| `src/model.py` | `NUM_COLS` gains 5 new columns |
| `pages/1_Plan_Event.py` | NEW — adaptive form with planned/unplanned conditional rendering |
| `pages/2_Results.py` | NEW — extended results dashboard |
| `tests/test_calendar_intel.py` | NEW |
| `tests/test_risk_model.py` | NEW |
| `tests/test_explainer.py` | NEW |

**Not touched:** `src/baseline.py`, `src/duration_model.py`, `src/recommender.py`, `src/road_network.py`, `src/map_builder.py`, `src/tuner.py`

---

## Success Criteria

| Feature | Pass condition |
|---|---|
| Multi-page restructure | Both pages load; training runs once and is shared; Back button returns to form |
| Calendar intelligence | `get_holiday_info(date(2024,10,12))` returns Dasara tier-3; non-holiday returns tier-0 |
| Adaptive form | Planned fields hidden when Unplanned selected; calendar strip pre-fills from date |
| Congestion model | ROC-AUC > 0.60 on held-out test set |
| Law & order model | ROC-AUC > 0.60 on held-out test set |
| SHAP explainability | Top-5 drivers displayed for severity; expanders work for both risk models |
| Results dashboard | All existing panels preserved; risk + SHAP panels appear in correct positions |

---

## Out of Scope (Phase 2)

- Post-event report form and continuous learning
- Police station recommendation engine (requires station registry database)
- Multi-event conflict resolution dashboard
- SQLite/Postgres persistence layer
- Live GPS or CCTV integration
