# tests/test_baseline.py
import pandas as pd
import pytest
from src.baseline import (
    compute_window_counts,
    compute_corridor_baselines,
    compute_excess_scores,
    compute_tertile_thresholds,
    label_severity,
)


def _add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add hour_band and day_of_week columns that load_raw() normally provides."""

    def _hour_to_band(hour: int) -> str:
        if hour < 6:
            return "night"
        if hour < 12:
            return "morning"
        if hour < 18:
            return "afternoon"
        return "evening"

    df = df.copy()
    df["day_of_week"] = df["start_datetime"].dt.dayofweek.astype(int)
    df["hour_band"] = df["start_datetime"].dt.hour.apply(_hour_to_band)
    return df


def test_window_count_counts_same_corridor_events(sample_df):
    # E1 (CBD 2, 18:00) and E6 (CBD 2, 19:00) are within 2h of each other
    # E3 (CBD 2, 17:30) is 30min before E1 — within 1h pre-window
    df = _add_time_features(sample_df)
    counts = compute_window_counts(df)
    # E1 at 18:00: E3 at 17:30 (30min before, same corridor) + E6 at 19:00 (1h after) = 2
    e1_idx = df[df["id"] == "E1"].index[0]
    assert counts[e1_idx] == 2


def test_window_count_excludes_other_corridors(sample_df):
    df = _add_time_features(sample_df)
    counts = compute_window_counts(df)
    # E2 on ORR East 1 should not count E1 on CBD 2
    e2_idx = df[df["id"] == "E2"].index[0]
    e5_idx = df[df["id"] == "E5"].index[0]
    # E2 at 09:00, E5 at 09:30 — same corridor, within window → count = 1 each
    assert counts[e2_idx] == 1
    assert counts[e5_idx] == 1


def test_corridor_baseline_returns_float(sample_df):
    df = _add_time_features(sample_df)
    df["window_count"] = compute_window_counts(df)
    baselines = compute_corridor_baselines(df)
    assert isinstance(baselines, dict)
    cbd_keys = [k for k in baselines if k[0] == "CBD 2"]
    assert len(cbd_keys) > 0


def test_thin_corridor_falls_back_to_zone(sample_df):
    df = _add_time_features(sample_df)
    df["window_count"] = compute_window_counts(df)
    # "Tumkur Road" has only 1 event — below min_obs=2
    baselines = compute_corridor_baselines(df, min_obs=2)
    tumkur_keys = [k for k in baselines if k[0] == "Tumkur Road"]
    assert len(tumkur_keys) > 0


def test_excess_scores_subtract_baseline(sample_df):
    df = _add_time_features(sample_df)
    df["window_count"] = compute_window_counts(df)
    baselines = compute_corridor_baselines(df, min_obs=1)
    df["impact_score"] = compute_excess_scores(df, baselines)
    assert "impact_score" in df.columns
    assert df["impact_score"].dtype in [float, "float64"]


def test_tertile_thresholds_from_train_only(sample_df):
    df = _add_time_features(sample_df)
    df = pd.concat([df] * 10, ignore_index=True)
    df["window_count"] = compute_window_counts(df)
    baselines = compute_corridor_baselines(df, min_obs=1)
    df["impact_score"] = compute_excess_scores(df, baselines)
    low_t, high_t = compute_tertile_thresholds(df)
    assert low_t <= high_t


def test_label_severity_covers_all_classes(sample_df):
    df = _add_time_features(sample_df)
    df = pd.concat([df] * 10, ignore_index=True)
    df["window_count"] = compute_window_counts(df)
    baselines = compute_corridor_baselines(df, min_obs=1)
    df["impact_score"] = compute_excess_scores(df, baselines)
    low_t, high_t = compute_tertile_thresholds(df)
    df["severity"] = label_severity(df, low_t, high_t)
    assert set(df["severity"].unique()).issubset({"LOW", "MEDIUM", "HIGH"})
