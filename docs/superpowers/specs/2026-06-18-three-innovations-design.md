# Three Innovations: Geospatial Barricades, Time-Banded Diversions, Duration Forecasting

**Date:** 2026-06-18
**Context:** GRIDLOCK 2.0 hackathon demo — three data-driven enhancements to recommendation and prediction layers
**Stack:** Python + scikit-learn + LightGBM + Streamlit

---

## Overview

Three independent enhancements to the existing system. Each is confined to its own layer with minimal interface changes. The severity classifier (LightGBM + CorridorStatsTransformer, macro F1 = 0.74) is not touched.

| Innovation | Files changed | Risk |
|---|---|---|
| 1 — Geospatial barricades | `src/recommender.py`, `app.py` | Low |
| 2 — Time-banded diversions | `src/recommender.py`, `app.py` | Low |
| 3 — Duration forecasting | `src/duration_model.py` (new), `src/pipeline.py`, `app.py` | Medium |

---

## Innovation 1: Geospatial-Proximity Barricade Routing

### Problem

`barricade_positions(train_df, corridor, top_n=4)` ranks junctions by road-closure frequency across the entire corridor. On a 15km corridor like ORR, it can recommend a junction 10km from the event epicenter.

### Algorithm

New signature:
```python
barricade_positions(
    train_df: pd.DataFrame,
    corridor: str,
    event_lat: float,
    event_lng: float,
    radius_km: float = 2.0,
    top_n: int = 4,
) -> list
```

Steps:
1. Filter `train_df` to rows where `corridor == corridor`, `requires_road_closure == True`, `junction != "unknown"`.
2. For each unique junction, compute its centroid `(lat, lng)` as the mean of all matching rows' `latitude`/`longitude`.
3. Compute haversine distance from `(event_lat, event_lng)` to each junction centroid.
4. Filter to junctions within `radius_km`. Rank survivors by frequency (value_counts), return top `top_n`.
5. **Fallback chain:**
   - If fewer than 2 junctions found within `radius_km` → expand to `radius_km * 2.5` (5km).
   - If still fewer than 2 → drop radius entirely and return corridor-wide top-N (original behavior).

### Haversine formula

```python
def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
```

### app.py change

`lat` and `lng` from `corridor_metadata()` are already in scope in `load_and_train()`'s results block. Pass them to `barricade_positions`:
```python
barricades = barricade_positions(train_df, corridor, lat, lng)
```

No form changes needed; `lat`/`lng` represent the corridor centroid, which serves as the event epicenter for inputs that don't have a precise pin.

### Data coverage

177 road-closure events with junction + lat/lng across 103 unique junctions on 19 corridors. The fallback chain ensures graceful degradation for corridors with sparse coverage.

---

## Innovation 2: Time-Banded Dynamic Diversion Graphs

### Problem

`build_diversion_graph()` precomputes a static `{corridor: [D1, D2]}` lookup. A corridor recommended as a diversion during morning peak may itself be gridlocked during evening peak.

### Algorithm

Change the graph key from `corridor` to `(corridor, hour_band)`.

During construction, each primary event's co-incident scan is unchanged. The result is stored under `(C, hour_band_of_C)`:

```python
result[(C, row["hour_band"])] = top2_diversions
# Graph type: dict[(str, str), list[str]]
```

`get_diversions` new signature:
```python
get_diversions(diversion_graph: dict, corridor: str, hour_band: str) -> list
```

Lookup order:
1. `(corridor, hour_band)` — exact match
2. Any other `(corridor, band)` key in the graph — return the first found (partial fallback)
3. `[]` — no data for this corridor at all

### app.py change

`hb` (hour_band) is already computed from the form's time input. Pass it:
```python
diversions = get_diversions(diversion_graph, corridor, hb)
```

### Note on `build_diversion_graph` call in `app.py`

Currently called with `pd.concat([train_df, val_df])`. This is unchanged — both splits contribute to graph construction. The graph just gains the `hour_band` dimension.

---

## Innovation 3: Duration Forecasting

### Problem

The system predicts severity (HOW BAD) but not duration (HOW LONG). Field commanders cannot plan officer shift lengths without a duration estimate.

### Data

- 2,456 events with valid `duration_h` in (0, 24] — computed as `(closed_datetime - start_datetime).total_seconds() / 3600`
- Events without `closed_datetime` are excluded from training but still get a prediction (model extrapolates)
- Distribution: median 0.76h, mean 1.65h, heavily right-skewed

### Duration labels (tertile-based, computed from training set only)

| Label | Approximate range | Meaning |
|---|---|---|
| SHORT | ≤ 33rd percentile (~0.47h) | Under ~30 min |
| MEDIUM | 33rd–67th percentile (~0.47–1.5h) | 30 min to 1.5h |
| LONG | > 67th percentile (~1.5h) | Over 1.5h |

Exact thresholds computed from `train_df` at training time (same tertile approach as severity labels).

### Model selection — benchmark three candidates

All trained on the same 70/15/15 split used by the severity model (same `split_data()` call), using only rows with valid `duration_h`.

| ID | Model | Target | Eval |
|---|---|---|---|
| A | LightGBM Classifier | Tertile labels (SHORT/MEDIUM/LONG) | macro F1 |
| B | LightGBM Regressor | `log1p(duration_h)` → back-transform → bucket | MAE (hours) |
| C | ExtraTreesRegressor (sklearn) | `log1p(duration_h)` → back-transform → bucket | MAE (hours) |

Selection rule:
- If A's macro F1 > 0.45 → use classifier (labels directly, no bucketing needed)
- Otherwise: compare B vs C on MAE; use whichever is lower
- Fallback if all models are poor (F1 < 0.35, MAE > 2h): use a simple "most-frequent-bucket" baseline and note it on the dashboard

Feature set: same `ALL_FEATURE_COLS` from `src/model.py` (13 features) — no new features needed. `CorridorStatsTransformer` is NOT used (duration model is a separate pipeline with its own preprocessing — OrdinalEncoder for categoricals is fine here since duration prediction tolerates ordinal encoding).

### New file: `src/duration_model.py`

```python
def compute_duration_labels(df, low_thresh, high_thresh) -> pd.Series:
    """Classify duration_h into SHORT/MEDIUM/LONG using training tertile thresholds."""

def duration_tertile_thresholds(train_df) -> tuple[float, float]:
    """Returns (low_thresh, high_thresh) from training duration_h distribution."""

def train_duration_model(train_df) -> Pipeline:
    """Benchmark A/B/C, pick winner, return fitted Pipeline."""

def predict_duration(pipeline, features: dict) -> str:
    """Returns 'SHORT', 'MEDIUM', or 'LONG'."""
```

### pipeline.py change

`load_raw()` adds `duration_h` column:
```python
df["duration_h"] = (df["closed_datetime"] - df["start_datetime"]).dt.total_seconds() / 3600
df["duration_h"] = df["duration_h"].where((df["duration_h"] > 0) & (df["duration_h"] <= 24))
# Rows without closed_datetime → NaN (excluded from training, ok for prediction)
```

### app.py changes

In `load_and_train()`:
```python
low_d, high_d = duration_tertile_thresholds(train_df)
train_df["duration_label"] = compute_duration_labels(train_df, low_d, high_d)
duration_pipeline = train_duration_model(train_df)
```

In results screen, below the severity badge:
```
Predicted Duration: MEDIUM (~30 min – 1.5h)
```
Each label carries a human-readable range derived from the training tertile thresholds (rounded to nearest 5 min).

---

## File Change Summary

| File | Change |
|---|---|
| `src/recommender.py` | `barricade_positions` gains `event_lat`, `event_lng`, `radius_km` args + haversine helper; `build_diversion_graph` keys by `(corridor, hour_band)`; `get_diversions` gains `hour_band` arg |
| `src/duration_model.py` | New — benchmarking, training, prediction for duration |
| `src/pipeline.py` | `load_raw()` adds `duration_h` column |
| `app.py` | Pass `lat`/`lng` to `barricade_positions`; pass `hb` to `get_diversions`; train + display duration model |
| `tests/test_recommender.py` | Update existing tests for new signatures; add duration model tests |
| `tests/test_duration_model.py` | New — benchmark, train, predict smoke tests |

**Not touched:** `src/model.py`, `src/baseline.py`, `src/map_builder.py`, `src/tuner.py`

---

## Success Criteria

| Feature | Pass condition |
|---|---|
| Geospatial barricades | Recommended junctions are within 2km of event epicenter when data is available; fallback returns corridor-wide results gracefully |
| Time-banded diversions | `get_diversions` returns different corridors for morning vs evening on at least one test corridor |
| Duration model | Best candidate macro F1 > 0.40 or MAE < 2h; result displayed on dashboard |
