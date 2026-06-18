# tests/test_duration_model.py
import numpy as np
import pandas as pd

from src.duration_model import (
    compute_duration_labels,
    duration_tertile_thresholds,
    predict_duration,
    train_duration_model,
)


def _make_duration_df(n: int = 120) -> pd.DataFrame:
    np.random.seed(42)
    return pd.DataFrame({
        "event_cause":           ["public_event"] * n,
        "event_type":            ["planned"] * (n // 2) + ["unplanned"] * (n // 2),
        "corridor":              ["CBD 2"] * (n // 2) + ["ORR"] * (n // 2),
        "zone":                  ["Central Zone"] * n,
        "police_station":        ["Cubbon Park"] * n,
        "hour_band":             (
            ["morning"] * (n // 4) + ["afternoon"] * (n // 4)
            + ["evening"] * (n // 4) + ["night"] * (n // 4)
        ),
        "priority":              ["High"] * (n // 2) + ["Low"] * (n // 2),
        "junction":              ["unknown"] * n,
        "hour_of_day":           np.random.randint(0, 24, n).tolist(),
        "day_of_week":           np.random.randint(0, 7, n).tolist(),
        "requires_road_closure": [False] * n,
        "month":                 np.random.randint(1, 13, n).tolist(),
        "is_weekend":            np.random.randint(0, 2, n).tolist(),
        "duration_h":            np.random.exponential(1.5, n).clip(0.01, 24).tolist(),
    })


def test_duration_tertile_thresholds():
    df = _make_duration_df()
    low, high = duration_tertile_thresholds(df)
    assert 0 < low < high < 24


def test_compute_duration_labels_covers_all_classes():
    df = _make_duration_df()
    low, high = duration_tertile_thresholds(df)
    labels = compute_duration_labels(df, low, high)
    valid = labels.dropna()
    assert set(valid.unique()) == {"SHORT", "MEDIUM", "LONG"}


def test_compute_duration_labels_nan_for_null_duration():
    df = _make_duration_df()
    df.loc[0, "duration_h"] = np.nan
    low, high = duration_tertile_thresholds(df)
    labels = compute_duration_labels(df, low, high)
    assert pd.isna(labels.iloc[0])


def test_train_duration_model_returns_valid_dict():
    df = _make_duration_df()
    dur_model = train_duration_model(df)
    assert isinstance(dur_model, dict)
    assert set(dur_model.keys()) == {"pipeline", "kind", "low_thresh", "high_thresh"}
    assert dur_model["kind"] in ("classifier", "regressor", "baseline")
    assert dur_model["low_thresh"] < dur_model["high_thresh"]


def test_predict_duration_returns_valid_label():
    df = _make_duration_df()
    dur_model = train_duration_model(df)
    features = {
        "event_cause":           "public_event",
        "event_type":            "planned",
        "corridor":              "CBD 2",
        "zone":                  "Central Zone",
        "police_station":        "Cubbon Park",
        "hour_band":             "morning",
        "priority":              "High",
        "junction":              "unknown",
        "hour_of_day":           9,
        "day_of_week":           1,
        "requires_road_closure": False,
        "month":                 6,
        "is_weekend":            0,
    }
    result = predict_duration(dur_model, features)
    assert result in ("SHORT", "MEDIUM", "LONG")


def test_predict_duration_handles_unseen_corridor():
    """Model must not crash on a corridor not seen during training."""
    df = _make_duration_df()
    dur_model = train_duration_model(df)
    features = {
        "event_cause":           "accident",
        "event_type":            "unplanned",
        "corridor":              "UNSEEN_CORRIDOR",
        "zone":                  "Unknown Zone",
        "police_station":        "Unknown Station",
        "hour_band":             "night",
        "priority":              "Low",
        "junction":              "unknown",
        "hour_of_day":           23,
        "day_of_week":           6,
        "requires_road_closure": True,
        "month":                 1,
        "is_weekend":            1,
    }
    result = predict_duration(dur_model, features)
    assert result in ("SHORT", "MEDIUM", "LONG")
