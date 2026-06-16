# src/baseline.py
import pandas as pd
import numpy as np

PRE_WINDOW_H  = 1.0
POST_WINDOW_H = 2.0
MIN_OBS       = 10


def compute_window_counts(df: pd.DataFrame, pre_h=PRE_WINDOW_H, post_h=POST_WINDOW_H) -> pd.Series:
    """
    For each event, count OTHER incidents on the same corridor within [t-pre_h, t+post_h].
    Groups by corridor first to avoid O(n^2) cross-corridor comparisons.
    """
    pre  = pd.Timedelta(hours=pre_h)
    post = pd.Timedelta(hours=post_h)
    result = pd.Series(0, index=df.index, name="window_count", dtype=int)

    for corridor, grp in df.groupby("corridor"):
        times = grp["start_datetime"]
        for idx in grp.index:
            t    = times[idx]
            mask = (times.index != idx) & (times >= t - pre) & (times <= t + post)
            result[idx] = int(mask.sum())

    return result


def compute_corridor_baselines(train_df: pd.DataFrame, min_obs: int = MIN_OBS) -> dict:
    """
    Returns {(corridor, hour_band, day_of_week): mean_window_count}.
    Falls back to zone-level baseline when corridor observations < min_obs.
    Falls back to global mean when zone baseline is also unavailable.
    """
    global_mean = train_df["window_count"].mean()

    # Zone-level baselines
    zone_bl = {}
    for (zone, hb, dow), grp in train_df.groupby(["zone", "hour_band", "day_of_week"]):
        zone_bl[(zone, hb, dow)] = grp["window_count"].mean()

    baselines = {}
    for corridor in train_df["corridor"].unique():
        corr_rows = train_df[train_df["corridor"] == corridor]
        zone = corr_rows["zone"].mode().iloc[0] if not corr_rows.empty else "unknown"

        for hb in train_df["hour_band"].unique():
            for dow in range(7):
                grp = corr_rows[
                    (corr_rows["hour_band"] == hb) & (corr_rows["day_of_week"] == dow)
                ]
                if len(grp) >= min_obs:
                    baselines[(corridor, hb, dow)] = grp["window_count"].mean()
                else:
                    baselines[(corridor, hb, dow)] = zone_bl.get(
                        (zone, hb, dow), global_mean
                    )

    return baselines


def compute_excess_scores(df: pd.DataFrame, baselines: dict) -> pd.Series:
    """impact_score = window_count - baseline for each event."""
    global_mean = df["window_count"].mean()
    scores = df.apply(
        lambda row: row["window_count"] - baselines.get(
            (row["corridor"], row["hour_band"], row["day_of_week"]), global_mean
        ),
        axis=1,
    )
    return scores.rename("impact_score")


def compute_tertile_thresholds(train_df: pd.DataFrame) -> tuple:
    """Returns (low_thresh, high_thresh) from training impact_score distribution."""
    low  = float(train_df["impact_score"].quantile(1 / 3))
    high = float(train_df["impact_score"].quantile(2 / 3))
    return low, high


def label_severity(df: pd.DataFrame, low_thresh: float, high_thresh: float) -> pd.Series:
    """Classifies each event as LOW / MEDIUM / HIGH using training tertile thresholds."""
    def _classify(score):
        if score <= low_thresh:
            return "LOW"
        if score <= high_thresh:
            return "MEDIUM"
        return "HIGH"
    return df["impact_score"].apply(_classify).rename("severity")
