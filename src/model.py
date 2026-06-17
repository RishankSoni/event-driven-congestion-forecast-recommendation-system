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
