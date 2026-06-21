# src/pipeline.py
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split

DATA_PATH = Path(__file__).parent.parent / "data" / "events_enriched.csv"

_HIGH_CAUSE = {"accident", "water_logging", "procession", "vip_movement", "protest"}

_NLP_PATTERNS = {
    "desc_traffic_slow": r"\b(?:slow|jam|standstill|heavy.?traffic|congestion|choked|crawling|gridlock)\b",
    "desc_breakdown":    r"\b(?:breakdown|break.?down|puncture|tyre|tire|wheel|stall(?:ed)?|broke(?:n)?)\b",
    "desc_waterlogging": r"\b(?:waterlog(?:ging)?|water.?log|flood(?:ing)?|rain.?water|inundat)\b",
    "desc_accident":     r"\b(?:accident|collision|crash|hit|pile.?up|mishap|bang)\b",
    "desc_construction": r"\b(?:construction|repair|work(?:ing)?|digging|pipe|maintenance|laying)\b",
    "desc_road_block":   r"\b(?:block(?:age)?|barricad|clos(?:ed|ure)|diverted?|diversion)\b",
}


def _add_nlp_features(df: pd.DataFrame) -> pd.DataFrame:
    desc = (
        df["description"].fillna("").str.lower()
        if "description" in df.columns
        else pd.Series("", index=df.index, dtype=str)
    )
    for col, pattern in _NLP_PATTERNS.items():
        df[col] = desc.str.contains(pattern, regex=True, na=False).astype(int)
    df["desc_word_count"] = desc.str.split().apply(len)

    rc = df["requires_road_closure"].astype(bool) if "requires_road_closure" in df.columns else pd.Series(False, index=df.index)
    has_cong = (df["desc_traffic_slow"].astype(bool) | df["desc_accident"].astype(bool))
    has_problem = desc.str.contains(r"\bproblem\b|\bheavy\b|\bblock\b", regex=True, na=False)
    df["new_severity_high"] = (
        df["event_cause"].isin(_HIGH_CAUSE) | (rc & (has_cong | has_problem))
    ).astype(int)
    return df


def _hour_to_band(hour: int) -> str:
    if hour < 6:   return "night"
    if hour < 12:  return "morning"
    if hour < 18:  return "afternoon"
    return "evening"

def load_raw(path=DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    for col in ["start_datetime", "closed_datetime", "end_datetime"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    df = df.dropna(subset=["start_datetime", "corridor"])
    df["hour_of_day"] = df["start_datetime"].dt.hour.astype(int)
    df["day_of_week"] = df["start_datetime"].dt.dayofweek.astype(int)
    df["hour_band"]   = df["hour_of_day"].apply(_hour_to_band)
    df["month"]      = df["start_datetime"].dt.month.astype(int)
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["requires_road_closure"] = (
        df["requires_road_closure"]
        .astype(str).str.strip().str.upper()
        .map({"TRUE": True, "FALSE": False, "1": True, "0": False})
        .fillna(False)
        .astype(bool)
        .astype(object)
    )
    if "closed_datetime" in df.columns:
        df["duration_h"] = (
            df["closed_datetime"] - df["start_datetime"]
        ).dt.total_seconds() / 3600
        df["duration_h"] = df["duration_h"].where(
            (df["duration_h"] > 0) & (df["duration_h"] <= 24)
        )
    else:
        df["duration_h"] = float("nan")
    for col in ["event_cause", "event_type", "corridor", "zone", "police_station", "junction", "priority"]:
        if col in df.columns:
            df[col] = df[col].fillna("unknown")

    # authenticated — "yes"/"no"/True/False → int
    if "authenticated" in df.columns:
        df["authenticated"] = (
            df["authenticated"].astype(str).str.lower()
            .isin(["yes", "true", "1", "t"])
            .astype(int)
        )
    else:
        df["authenticated"] = 0

    # veh_type — categorical, ~60% fill
    if "veh_type" in df.columns:
        df["veh_type"] = df["veh_type"].fillna("unknown").astype(str)
    else:
        df["veh_type"] = "unknown"

    # NLP features from description
    df = _add_nlp_features(df)

    # Calendar features — derived from event date
    from src.calendar_intel import get_holiday_info
    _dates = df["start_datetime"].dt.date
    _holiday_info = _dates.map(get_holiday_info)
    df["is_holiday"]        = _holiday_info.map(lambda x: int(x["is_holiday"]))
    df["holiday_risk_tier"] = _holiday_info.map(lambda x: x["risk_tier"]).astype(int)

    # Form-derived features — backfilled to 0 for all historical rows
    df["estimated_attendance"] = 0
    df["has_vip"]              = 0
    df["is_route_event"]       = 0

    # Weather features — use CSV values when present, fall back to dry/warm defaults
    if "rain_mm" in df.columns:
        df["rain_mm"] = pd.to_numeric(df["rain_mm"], errors="coerce").fillna(0.0)
    else:
        df["rain_mm"] = 0.0
    if "temperature_c" in df.columns:
        df["temperature_c"] = pd.to_numeric(df["temperature_c"], errors="coerce").fillna(25.0)
    else:
        df["temperature_c"] = 25.0

    return df.reset_index(drop=True)

def split_data(df: pd.DataFrame, train_frac=0.70, val_frac=0.15, random_state=42):
    """Returns (train_df, val_df, test_df). 70/15/15 random split."""
    test_size = 1.0 - train_frac - val_frac          # 0.15
    val_size  = val_frac / (train_frac + val_frac)    # 0.15 / 0.85 ≈ 0.1765

    train_val, test = train_test_split(df, test_size=test_size, random_state=random_state)
    train, val      = train_test_split(train_val, test_size=val_size, random_state=random_state)
    return train.copy(), val.copy(), test.copy()

def corridor_metadata(df: pd.DataFrame, corridor: str) -> tuple:
    """Returns (zone, police_station, mean_lat, mean_lng) for a corridor."""
    sub = df[df["corridor"] == corridor]
    if sub.empty:
        return ("unknown", "unknown", 12.97, 77.59)
    zone   = sub["zone"].mode().iloc[0]
    police = sub["police_station"].mode().iloc[0]
    lat    = sub["latitude"].mean()
    lng    = sub["longitude"].mean()
    return zone, police, lat, lng
