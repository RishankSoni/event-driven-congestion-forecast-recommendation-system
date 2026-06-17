# Model Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sklearn GBT classifier with a LightGBM pipeline using expanded features and Optuna tuning to push macro F1 from 0.65 toward 0.73–0.82.

**Architecture:** A custom `CorridorStatsTransformer` is the first step of a two-step sklearn `Pipeline`; it fits per-corridor HIGH-rate and event-count stats from training data and joins them at transform time. The second step is `LGBMClassifier` with native categorical support (pandas `category` dtype) and `class_weight="balanced"`. A separate `src/tuner.py` module runs Optuna search and returns a best-params dict that `train_model()` accepts as an optional argument.

**Tech Stack:** lightgbm, optuna, scikit-learn, pandas

## Global Constraints

- All sklearn `Pipeline` and `train_model` / `predict` / `evaluate_cv` / `evaluate_test` / `get_knn_neighbors` public signatures stay backward-compatible with `app.py` (except `train_model` gaining an optional `params` arg and the features dict gaining four new keys).
- `TARGET_COL = "severity"` with classes `"LOW"`, `"MEDIUM"`, `"HIGH"`.
- Macro F1 is the sole evaluation metric throughout.
- No changes to `baseline.py`, `recommender.py`, or `map_builder.py`.
- Run tests with: `pytest tests/ -v`

---

### Task 1: Add `month`, `is_weekend`, and `priority` to `load_raw()`

**Files:**
- Modify: `src/pipeline.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `load_raw()` returns a DataFrame with columns `month` (int, 1–12), `is_weekend` (int, 0 or 1), `priority` (str, "High"/"Low"/"unknown") in addition to existing columns. `junction` is already fillna'd by existing code.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
def test_load_raw_adds_month_and_weekend(tmp_path):
    csv = tmp_path / "events.csv"
    csv.write_text(
        "id,event_type,event_cause,latitude,longitude,corridor,zone,police_station,"
        "junction,start_datetime,closed_datetime,requires_road_closure,priority,status\n"
        "E1,planned,public_event,12.97,77.59,CBD 2,Central Zone 2,Cubbon Park,"
        ",2024-02-12 18:00:00+00:00,2024-02-12 20:00:00+00:00,FALSE,High,closed\n"
        "E2,unplanned,accident,12.95,77.58,ORR East 1,East Zone 1,Bellandur,"
        ",2024-01-06 09:00:00+00:00,2024-01-06 11:00:00+00:00,FALSE,Low,closed\n"
    )
    df = load_raw(path=csv)
    assert df.iloc[0]["month"] == 2
    assert df.iloc[0]["is_weekend"] == 0   # Monday
    assert df.iloc[1]["month"] == 1
    assert df.iloc[1]["is_weekend"] == 1   # Saturday

def test_load_raw_normalises_priority(tmp_path):
    csv = tmp_path / "events.csv"
    csv.write_text(
        "id,event_type,event_cause,latitude,longitude,corridor,zone,police_station,"
        "junction,start_datetime,closed_datetime,requires_road_closure,priority,status\n"
        "E1,planned,public_event,12.97,77.59,CBD 2,Central Zone 2,Cubbon Park,"
        ",2024-02-12 18:00:00+00:00,2024-02-12 20:00:00+00:00,FALSE,,closed\n"
        "E2,unplanned,accident,12.95,77.58,ORR East 1,East Zone 1,Bellandur,"
        ",2024-01-06 09:00:00+00:00,2024-01-06 11:00:00+00:00,FALSE,High,closed\n"
    )
    df = load_raw(path=csv)
    assert df.iloc[0]["priority"] == "unknown"
    assert df.iloc[1]["priority"] == "High"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_pipeline.py::test_load_raw_adds_month_and_weekend tests/test_pipeline.py::test_load_raw_normalises_priority -v
```

Expected: FAIL — `KeyError: 'month'` or similar.

- [ ] **Step 3: Implement in `src/pipeline.py`**

Inside `load_raw()`, after the line `df["hour_band"] = df["hour_of_day"].apply(_hour_to_band)`, add:

```python
    df["month"]      = df["start_datetime"].dt.month.astype(int)
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
```

In the existing `for col in [...]` fillna loop, `"junction"` is already present. Add `"priority"` to that same list AND handle it separately to normalize nulls to `"unknown"`:

Replace the existing loop:
```python
    for col in ["event_cause", "event_type", "corridor", "zone", "police_station", "junction"]:
        if col in df.columns:
            df[col] = df[col].fillna("unknown")
```

With:
```python
    for col in ["event_cause", "event_type", "corridor", "zone", "police_station", "junction", "priority"]:
        if col in df.columns:
            df[col] = df[col].fillna("unknown")
```

(No case normalization — keep "High"/"Low"/"unknown" as-is; LightGBM treats them as opaque categories.)

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_pipeline.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline.py tests/test_pipeline.py
git commit -m "feat: load_raw — add month, is_weekend, priority columns"
```

---

### Task 2: Update test fixture and add `CorridorStatsTransformer` tests

**Files:**
- Modify: `tests/test_model.py`

**Interfaces:**
- Consumes: `CorridorStatsTransformer` from `src.model` (not yet implemented — tests will fail until Task 3)
- Produces: updated `_prepare()` fixture that adds `month`, `is_weekend`, `priority`, `junction` to the sample dataframe; updated `features` dicts throughout; new `test_corridor_stats_transformer` test.

- [ ] **Step 1: Update `_prepare()` to add the four new columns**

Replace the entire `_prepare` function in `tests/test_model.py`:

```python
def _prepare(sample_df):
    """Add all columns needed for model training."""
    def _hour_to_band(h):
        if h < 6:   return "night"
        if h < 12:  return "morning"
        if h < 18:  return "afternoon"
        return "evening"
    df = pd.concat([sample_df] * 15, ignore_index=True)
    df["day_of_week"] = df["start_datetime"].dt.dayofweek.astype(int)
    df["hour_of_day"] = df["start_datetime"].dt.hour.astype(int)
    df["hour_band"]   = df["hour_of_day"].apply(_hour_to_band)
    df["month"]       = df["start_datetime"].dt.month.astype(int)
    df["is_weekend"]  = (df["day_of_week"] >= 5).astype(int)
    df["priority"]    = df["priority"].fillna("unknown").astype(str)
    df["junction"]    = df["junction"].fillna("unknown").astype(str)
    df["requires_road_closure"] = (
        df["requires_road_closure"].astype(str).str.upper()
        .map({"TRUE": True, "FALSE": False}).fillna(False)
    )
    df["window_count"] = compute_window_counts(df)
    baselines = compute_corridor_baselines(df, min_obs=1)
    df["impact_score"] = compute_excess_scores(df, baselines)
    low_t, high_t = compute_tertile_thresholds(df)
    df["severity"] = label_severity(df, low_t, high_t)
    return df
```

- [ ] **Step 2: Update features dicts in existing tests**

In `test_predict_returns_valid_severity`, replace the `features` dict:

```python
    features = {
        "event_cause":           "public_event",
        "event_type":            "planned",
        "corridor":              "CBD 2",
        "zone":                  "Central Zone 2",
        "police_station":        "Cubbon Park",
        "hour_band":             "evening",
        "hour_of_day":           18,
        "day_of_week":           0,
        "requires_road_closure": False,
        "priority":              "High",
        "junction":              "unknown",
        "month":                 2,
        "is_weekend":            0,
    }
```

In `test_knn_neighbors_returns_k_rows`, replace the `query` dict:

```python
    query = {
        "event_cause":           "public_event",
        "event_type":            "planned",
        "corridor":              "CBD 2",
        "zone":                  "Central Zone 2",
        "police_station":        "Cubbon Park",
        "hour_band":             "evening",
        "hour_of_day":           18,
        "day_of_week":           0,
        "requires_road_closure": False,
        "priority":              "High",
        "junction":              "unknown",
        "month":                 2,
        "is_weekend":            0,
    }
```

- [ ] **Step 3: Add import and `CorridorStatsTransformer` test**

Add `CorridorStatsTransformer` to the import line at the top of `tests/test_model.py`:

```python
from src.model import train_model, evaluate_cv, evaluate_test, predict, get_knn_neighbors, CorridorStatsTransformer
```

Add the new test at the end of the file:

```python
def test_corridor_stats_transformer(labeled_df):
    from src.model import _X, TARGET_COL
    transformer = CorridorStatsTransformer()
    X = _X(labeled_df)
    transformer.fit(X, labeled_df[TARGET_COL])
    out = transformer.transform(X)
    assert "corridor_high_rate" in out.columns
    assert "corridor_event_count" in out.columns
    assert out["corridor_high_rate"].between(0.0, 1.0).all()
    assert (out["corridor_event_count"] > 0).all()
    # unseen corridor gets fallback values, not NaN
    unseen = X.copy()
    unseen["corridor"] = unseen["corridor"].cat.add_categories("Unseen Road") if hasattr(unseen["corridor"], "cat") else unseen["corridor"]
    unseen["corridor"] = "Unseen Road"
    out2 = transformer.transform(unseen)
    assert out2["corridor_high_rate"].notna().all()
    assert out2["corridor_event_count"].notna().all()
```

- [ ] **Step 4: Run tests (expect FAIL on new import and transformer test — that's correct)**

```
pytest tests/test_model.py -v
```

Expected: failures on `CorridorStatsTransformer` import and `test_corridor_stats_transformer` — that's the red phase. Existing tests may also fail because `ALL_FEATURE_COLS` doesn't include the new columns yet. All of this is intentional — Task 3 fixes it.

- [ ] **Step 5: Commit the test updates**

```bash
git add tests/test_model.py
git commit -m "test: update model fixture and add CorridorStatsTransformer test (red)"
```

---

### Task 3: Replace GBT pipeline with LightGBM in `src/model.py`

**Files:**
- Modify: `src/model.py`

**Interfaces:**
- Consumes: labeled `train_df` with columns `event_cause`, `event_type`, `corridor`, `zone`, `police_station`, `hour_band`, `priority`, `junction`, `hour_of_day`, `day_of_week`, `requires_road_closure`, `month`, `is_weekend`, `severity`
- Produces:
  - `CorridorStatsTransformer` — sklearn transformer class (exported for tests)
  - `train_model(train_df, params=None) -> Pipeline`
  - `predict(pipeline, features) -> tuple[str, dict[str, float]]` — features dict must include all 13 keys
  - `evaluate_cv(train_df, n_splits=5) -> float`
  - `evaluate_test(pipeline, test_df) -> float`
  - `get_knn_neighbors(train_df, query_features, k=5) -> pd.DataFrame`
  - `ALL_FEATURE_COLS`, `CAT_COLS`, `NUM_COLS`, `TARGET_COL` module-level constants

- [ ] **Step 1: Rewrite `src/model.py` in full**

Replace the entire file content with:

```python
# src/model.py
import pandas as pd
import numpy as np
from typing import Optional
from lightgbm import LGBMClassifier
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import OrdinalEncoder
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import f1_score, pairwise_distances

CAT_COLS = [
    "event_cause", "event_type", "corridor", "zone",
    "police_station", "hour_band", "priority", "junction",
]
NUM_COLS = [
    "hour_of_day", "day_of_week", "requires_road_closure",
    "month", "is_weekend",
]
ALL_FEATURE_COLS = CAT_COLS + NUM_COLS
TARGET_COL = "severity"

_LGBM_DEFAULTS: dict = {
    "n_estimators": 300,
    "num_leaves": 63,
    "learning_rate": 0.05,
    "min_child_samples": 20,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}


class CorridorStatsTransformer(BaseEstimator, TransformerMixin):
    """Fits per-corridor HIGH-rate and event-count stats; joins them at transform time.
    Also converts CAT_COLS to pandas category dtype for LightGBM native categorical support."""

    def fit(self, X: pd.DataFrame, y=None) -> "CorridorStatsTransformer":
        df = X.copy()
        df["_y"] = y
        stats = df.groupby("corridor").agg(
            corridor_high_rate=("_y", lambda s: (s == "HIGH").mean()),
            corridor_event_count=("_y", "count"),
        )
        self.stats_: pd.DataFrame = stats
        self.fallback_high_rate_: float = float((df["_y"] == "HIGH").mean())
        self.fallback_event_count_: float = float(df.groupby("corridor").size().median())
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        out = X.copy()
        out = out.join(self.stats_, on="corridor", how="left")
        out["corridor_high_rate"] = out["corridor_high_rate"].fillna(self.fallback_high_rate_)
        out["corridor_event_count"] = out["corridor_event_count"].fillna(self.fallback_event_count_)
        for col in CAT_COLS:
            out[col] = out[col].astype("category")
        return out


def _build_pipeline(params: Optional[dict] = None) -> Pipeline:
    lgbm_params = {**_LGBM_DEFAULTS, **(params or {})}
    return Pipeline([
        ("corridor_stats", CorridorStatsTransformer()),
        ("lgbm", LGBMClassifier(**lgbm_params)),
    ])


def _X(df: pd.DataFrame) -> pd.DataFrame:
    out: pd.DataFrame = df[ALL_FEATURE_COLS].copy()  # type: ignore[assignment]
    out["requires_road_closure"] = out["requires_road_closure"].astype(int)
    out["is_weekend"] = out["is_weekend"].astype(int)
    out["month"] = out["month"].astype(int)
    for col in CAT_COLS:
        col_s: pd.Series = out[col]  # type: ignore[assignment]
        out[col] = col_s.fillna("unknown").astype(str)
    return out


def train_model(train_df: pd.DataFrame, params: Optional[dict] = None) -> Pipeline:
    pipeline = _build_pipeline(params)
    pipeline.fit(_X(train_df), train_df[TARGET_COL])
    return pipeline


def evaluate_cv(train_df: pd.DataFrame, n_splits: int = 5) -> float:
    """Mean macro-F1 from stratified k-fold CV on the training set."""
    pipeline = _build_pipeline()
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scores = cross_val_score(
        pipeline, _X(train_df), train_df[TARGET_COL],
        cv=cv, scoring="f1_macro",
    )
    return float(scores.mean())


def evaluate_test(pipeline: Pipeline, test_df: pd.DataFrame) -> float:
    """Macro-F1 on the held-out test set. Call exactly once."""
    y_pred = pipeline.predict(_X(test_df))
    return float(f1_score(test_df[TARGET_COL], y_pred, average="macro"))


def predict(pipeline: Pipeline, features: dict) -> tuple:
    """Returns (severity_class: str, confidence: dict[str, float]).

    features must include: event_cause, event_type, corridor, zone,
    police_station, hour_band, priority, junction, hour_of_day,
    day_of_week, requires_road_closure, month, is_weekend.
    """
    row = pd.DataFrame([features])
    row["requires_road_closure"] = row["requires_road_closure"].astype(int)
    row["is_weekend"] = row["is_weekend"].astype(int)
    row["month"] = row["month"].astype(int)
    for col in CAT_COLS:
        col_s: pd.Series = row[col]  # type: ignore[assignment]
        row[col] = col_s.fillna("unknown").astype(str)
    severity = str(pipeline.predict(row[ALL_FEATURE_COLS])[0])
    proba = pipeline.predict_proba(row[ALL_FEATURE_COLS])[0]
    confidence = {str(c): float(p) for c, p in zip(pipeline.classes_, proba)}
    return severity, confidence


def get_knn_neighbors(train_df: pd.DataFrame, query_features: dict, k: int = 5) -> pd.DataFrame:
    """Return k most similar historical events for the evidence panel."""
    # Mirror CorridorStatsTransformer to enrich both train and query with corridor stats
    stats = train_df.groupby("corridor").agg(
        corridor_high_rate=(TARGET_COL, lambda s: (s == "HIGH").mean()),
        corridor_event_count=(TARGET_COL, "count"),
    )
    global_high_rate = float((train_df[TARGET_COL] == "HIGH").mean())
    global_event_count = float(train_df.groupby("corridor").size().median())

    feature_df = _X(train_df).join(stats, on="corridor", how="left")
    feature_df["corridor_high_rate"] = feature_df["corridor_high_rate"].fillna(global_high_rate)
    feature_df["corridor_event_count"] = feature_df["corridor_event_count"].fillna(global_event_count)

    knn_cols = ALL_FEATURE_COLS + ["corridor_high_rate", "corridor_event_count"]
    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
    X_train = enc.fit_transform(feature_df[knn_cols])

    query_row = _X(pd.DataFrame([query_features]))
    corridor = str(query_features.get("corridor", "unknown"))
    if corridor in stats.index:
        query_row["corridor_high_rate"] = float(stats.loc[corridor, "corridor_high_rate"])
        query_row["corridor_event_count"] = float(stats.loc[corridor, "corridor_event_count"])
    else:
        query_row["corridor_high_rate"] = global_high_rate
        query_row["corridor_event_count"] = global_event_count

    X_query = enc.transform(query_row[knn_cols])
    dists = pairwise_distances(X_query, X_train)[0]
    top_k = np.argsort(dists)[:k]
    result: pd.DataFrame = train_df.iloc[top_k][
        ["corridor", "start_datetime", TARGET_COL, "impact_score", "event_cause"]
    ].copy()
    result["distance"] = dists[top_k]
    return result.reset_index(drop=True)
```

- [ ] **Step 2: Run the full test suite**

```
pytest tests/test_model.py -v
```

Expected: all tests PASS including `test_corridor_stats_transformer`.

- [ ] **Step 3: Run all tests to check nothing else broke**

```
pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add src/model.py
git commit -m "feat: replace GBT with LightGBM pipeline — CorridorStatsTransformer + expanded features"
```

---

### Task 4: Write `src/tuner.py` with Optuna hyperparameter search

**Files:**
- Create: `src/tuner.py`
- Create: `tests/test_tuner.py`

**Interfaces:**
- Consumes: labeled `train_df` (same as `train_model`)
- Produces: `tune_lgbm(train_df, n_trials=75) -> dict` — keys match `_LGBM_DEFAULTS` keys in `src/model.py`

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_tuner.py`:

```python
# tests/test_tuner.py
import pytest
from src.tuner import tune_lgbm
from tests.test_model import _prepare


def test_tune_lgbm_returns_param_dict(sample_df):
    labeled = _prepare(sample_df)
    params = tune_lgbm(labeled, n_trials=2)
    assert isinstance(params, dict)
    for key in ["n_estimators", "num_leaves", "learning_rate", "min_child_samples"]:
        assert key in params
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_tuner.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.tuner'`.

- [ ] **Step 3: Create `src/tuner.py`**

```python
# src/tuner.py
import pandas as pd
import optuna
from sklearn.model_selection import StratifiedKFold, cross_val_score
from lightgbm import LGBMClassifier
from sklearn.pipeline import Pipeline

from src.model import _X, CorridorStatsTransformer, TARGET_COL

optuna.logging.set_verbosity(optuna.logging.WARNING)


def tune_lgbm(train_df: pd.DataFrame, n_trials: int = 75) -> dict:
    """Run Optuna TPE study; return best LightGBM params dict."""
    X = _X(train_df)
    y = train_df[TARGET_COL]
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators":      trial.suggest_int("n_estimators", 100, 800),
            "num_leaves":        trial.suggest_int("num_leaves", 20, 200),
            "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
            "reg_alpha":         trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda":        trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "class_weight": "balanced",
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
        }
        pipeline = Pipeline([
            ("corridor_stats", CorridorStatsTransformer()),
            ("lgbm", LGBMClassifier(**params)),
        ])
        scores = cross_val_score(pipeline, X, y, cv=cv, scoring="f1_macro")
        return float(scores.mean())

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=10),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    return study.best_params


if __name__ == "__main__":
    from src.pipeline import load_raw, split_data
    from src.baseline import (
        compute_window_counts, compute_corridor_baselines,
        compute_excess_scores, compute_tertile_thresholds, label_severity,
    )

    df = load_raw()
    df["window_count"] = compute_window_counts(df)
    train_df, _, _ = split_data(df)
    baselines = compute_corridor_baselines(train_df)
    train_df["impact_score"] = compute_excess_scores(train_df, baselines)
    low_t, high_t = compute_tertile_thresholds(train_df)
    train_df["severity"] = label_severity(train_df, low_t, high_t)

    best = tune_lgbm(train_df, n_trials=75)
    print("\nBest params:", best)
    print("Pass to train_model(train_df, params=best) in app.py load_and_train().")
```

- [ ] **Step 4: Run smoke test**

```
pytest tests/test_tuner.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```
pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tuner.py tests/test_tuner.py
git commit -m "feat: Optuna tuner — tune_lgbm() with TPE search over LightGBM hyperparams"
```

---

### Task 5: Update `app.py` — add `priority` to form, pass new fields to `predict()`

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `predict(pipeline, features)` where features now requires `priority`, `junction`, `month`, `is_weekend`

- [ ] **Step 1: Add `priority` selectbox to the event form**

In `app.py`, inside the `with st.form("event_form"):` block, after the `road_closure` checkbox line, add:

```python
        with col1:
```

Replace the entire `with st.form("event_form"):` block (lines ~84–97) with:

```python
    with st.form("event_form"):
        col1, col2 = st.columns(2)
        with col1:
            event_name  = st.text_input("Event name", value="Public Rally")
            event_type  = st.selectbox("Event type", event_types)
            default_cause_idx = event_causes.index("public_event") if "public_event" in event_causes else 0
            event_cause = st.selectbox("Event cause", event_causes, index=default_cause_idx)
            corridor    = st.selectbox("Primary corridor", corridors)
            priority    = st.selectbox("Priority", ["High", "Low"], index=0)
        with col2:
            event_date   = st.date_input("Date", value=datetime.date.today())
            event_time   = st.time_input("Start time", value=datetime.time(18, 0))
            road_closure = st.checkbox("Requires road closure?", value=False)

        submitted = st.form_submit_button("Predict Impact", type="primary")
```

- [ ] **Step 2: Pass new fields in the `features` dict**

Replace the `features` dict construction (lines ~109–119) with:

```python
        features = {
            "event_cause":           event_cause,
            "event_type":            event_type,
            "corridor":              corridor,
            "zone":                  zone,
            "police_station":        police,
            "hour_band":             hb,
            "hour_of_day":           hour,
            "day_of_week":           dow,
            "requires_road_closure": road_closure,
            "priority":              priority,
            "junction":              "unknown",
            "month":                 event_date.month,
            "is_weekend":            int(dow >= 5),
        }
```

- [ ] **Step 3: Run the app and verify manually**

```
streamlit run app.py
```

- Open the app in the browser.
- Verify "Priority" selectbox appears between "Primary corridor" and the date inputs.
- Submit a prediction; confirm severity, confidence, and map all render as before.
- Check the sidebar still shows CV F1 and Test F1 metrics.
- Close with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: app — priority selectbox, pass month/is_weekend/junction to predict()"
```

---

### Task 6: Run Optuna tuning and wire best params into the app

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `tune_lgbm(train_df, n_trials=75) -> dict`; `train_model(train_df, params=dict) -> Pipeline`

- [ ] **Step 1: Run the tuner**

```
python -m src.tuner
```

This takes ~5–15 minutes. It prints best params when done, e.g.:

```
Best params: {'n_estimators': 542, 'num_leaves': 87, 'learning_rate': 0.042, ...}
```

- [ ] **Step 2: Wire best params into `load_and_train()` in `app.py`**

In `app.py`, replace the `load_and_train` function's `train_model` call:

```python
    # Paste the printed best_params dict here
    best_params = {
        "n_estimators": 542,       # replace with your actual output
        "num_leaves": 87,          # replace with your actual output
        "learning_rate": 0.042,    # replace with your actual output
        "min_child_samples": 18,   # replace with your actual output
        "reg_alpha": 0.003,        # replace with your actual output
        "reg_lambda": 0.012,       # replace with your actual output
        "subsample": 0.85,         # replace with your actual output
        "colsample_bytree": 0.78,  # replace with your actual output
    }
    pipeline = train_model(train_df, params=best_params)
```

- [ ] **Step 3: Print and check final test F1**

```
python - <<'EOF'
from src.pipeline import load_raw, split_data
from src.baseline import (
    compute_window_counts, compute_corridor_baselines,
    compute_excess_scores, compute_tertile_thresholds, label_severity,
)
from src.model import train_model, evaluate_test
from sklearn.metrics import classification_report
import pandas as pd

df = load_raw()
df["window_count"] = compute_window_counts(df)
train_df, val_df, test_df = split_data(df)
baselines = compute_corridor_baselines(train_df)
for split in [train_df, val_df, test_df]:
    split["impact_score"] = compute_excess_scores(split, baselines)
low_t, high_t = compute_tertile_thresholds(train_df)
for split in [train_df, val_df, test_df]:
    split["severity"] = label_severity(split, low_t, high_t)

from src.model import _X, TARGET_COL
best_params = {}  # paste your best_params dict here
pipeline = train_model(train_df, params=best_params or None)
y_pred = pipeline.predict(_X(test_df))
print(classification_report(test_df[TARGET_COL], y_pred))
EOF
```

Expected: macro F1 clearly above 0.65, HIGH recall improved from 0.51.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "perf: wire Optuna best params into load_and_train for production inference"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Add priority, junction, month, is_weekend to load_raw | Task 1 |
| Corridor historical stats (high_rate, event_count) | Task 3 — CorridorStatsTransformer |
| Replace OrdinalEncoder + GBT with LightGBM native categoricals | Task 3 |
| class_weight="balanced" for HIGH recall | Task 3 — _LGBM_DEFAULTS |
| train_model(params=None) backward-compatible signature | Task 3 |
| Optuna tuner src/tuner.py | Task 4 |
| app.py priority selectbox + new feature fields | Task 5 |
| Wire best params | Task 6 |
| test_model.py fixture and CorridorStatsTransformer test | Task 2 |

**Placeholder scan:** No TBDs. Task 6 Step 2 has placeholder values marked "replace with your actual output" — this is intentional since the values come from running the tuner, which cannot be known in advance.

**Type consistency:** `CorridorStatsTransformer` defined in Task 3, imported in Task 2 tests and Task 4 tuner — consistent. `_X`, `TARGET_COL`, `ALL_FEATURE_COLS` used across Tasks 3/4 — all defined in Task 3's `src/model.py`. `tune_lgbm` defined in Task 4, consumed in Task 6 — consistent signature.
