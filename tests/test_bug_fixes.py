# tests/test_bug_fixes.py
# Failing-first tests for bugs identified in stress test 2026-06-22.
# Each test documents the expected (fixed) behavior.

import pandas as pd
import pytest


# ── CRITICAL-3: corridor_metadata ignores 'unknown' zone values ───────────────

def test_corridor_metadata_prefers_named_zone_over_unknown():
    """When most rows have zone='unknown' but some have a real name,
    corridor_metadata must return the real name, not 'unknown'."""
    from src.pipeline import corridor_metadata
    df = pd.DataFrame({
        "corridor":       ["CBD 2"] * 10,
        "zone":           ["unknown"] * 6 + ["Central Zone 2"] * 4,
        "police_station": ["Cubbon Park"] * 10,
        "latitude":       [12.97] * 10,
        "longitude":      [77.59] * 10,
    })
    zone, _, _, _ = corridor_metadata(df, "CBD 2")
    assert zone == "Central Zone 2", (
        f"Expected 'Central Zone 2', got {zone!r}. "
        "corridor_metadata must skip 'unknown' rows before computing mode."
    )


def test_corridor_metadata_prefers_named_police_station_over_unknown():
    """Same logic applies to police_station field."""
    from src.pipeline import corridor_metadata
    df = pd.DataFrame({
        "corridor":       ["ORR North 1"] * 8,
        "zone":           ["North Zone 1"] * 8,
        "police_station": ["unknown"] * 5 + ["Hebbal"] * 3,
        "latitude":       [13.03] * 8,
        "longitude":      [77.60] * 8,
    })
    _, police, _, _ = corridor_metadata(df, "ORR North 1")
    assert police == "Hebbal", (
        f"Expected 'Hebbal', got {police!r}. "
        "corridor_metadata must skip 'unknown' before computing police station mode."
    )


# ── BUG-4: split_data must support stratification ─────────────────────────────

def test_split_data_stratify_col_preserves_class_in_all_splits():
    """When stratify_col is given, every class present in the full set
    must appear in train, val, and test."""
    from src.pipeline import split_data
    df = pd.DataFrame({
        "event_cause": (["public_event"] * 40 + ["accident"] * 40 +
                        ["construction"] * 40),
        "corridor":    ["CBD 2"] * 120,
    })
    train, val, test = split_data(df, stratify_col="event_cause")
    for cls in ["public_event", "accident", "construction"]:
        assert (train["event_cause"] == cls).any(), f"{cls} missing from train"
        assert (val["event_cause"]   == cls).any(), f"{cls} missing from val"
        assert (test["event_cause"]  == cls).any(), f"{cls} missing from test"


def test_split_data_without_stratify_col_still_works():
    """Default call with no stratify_col must not raise."""
    from src.pipeline import split_data
    df = pd.DataFrame({"corridor": ["CBD 2"] * 100})
    train, val, test = split_data(df)
    assert len(train) + len(val) + len(test) == 100


# ── BUG-5: officer_count must not raise KeyError for unknown severity ─────────

def test_officer_count_unknown_severity_falls_back_to_medium():
    """officer_count must return a valid result for any unexpected severity string."""
    from src.recommender import officer_count
    result = officer_count("UNEXPECTED_VALUE", n_adjacent_junctions=2)
    assert isinstance(result, dict)
    assert result["primary_min"] == 4   # MEDIUM fallback
    assert result["primary_max"] == 6
    assert result["total_min"] > 0


def test_officer_count_none_severity_falls_back_to_medium():
    """None severity must not crash either."""
    from src.recommender import officer_count
    result = officer_count(None, n_adjacent_junctions=0)
    assert isinstance(result, dict)
    assert result["primary_min"] == 4


# ── BUG-6: Law & Order risk model must not include event_cause in features ────

def test_law_order_feature_set_excludes_event_cause():
    """event_cause must not appear in the law & order model's feature list.
    Including it makes the model trivially predict its own label (AUC=1.0)."""
    from src.risk_model import _LAW_ORDER_FEATURES
    assert "event_cause" not in _LAW_ORDER_FEATURES, (
        "event_cause is in _LAW_ORDER_FEATURES — the label is derived from "
        "event_cause so including it as a feature causes trivial leakage."
    )


def test_law_order_auc_is_not_perfect_on_real_data():
    """AUC must be strictly less than 1.0 after removing the leaky feature."""
    pytest.importorskip("lightgbm")
    from src.pipeline import load_raw, split_data
    from src.baseline import (
        compute_window_counts, compute_corridor_baselines,
        compute_excess_scores, compute_tertile_thresholds, label_severity,
    )
    from src.risk_model import train_risk_models
    df = load_raw()
    df["window_count"] = compute_window_counts(df)
    train_df, _, _ = split_data(df)
    baselines = compute_corridor_baselines(train_df)
    train_df["impact_score"] = compute_excess_scores(train_df, baselines)
    low_t, high_t = compute_tertile_thresholds(train_df)
    train_df["severity"] = label_severity(train_df, low_t, high_t)
    risk_models = train_risk_models(train_df)
    assert risk_models["law_order_auc"] < 1.0, (
        f"Law & Order AUC={risk_models['law_order_auc']:.4f}; "
        "still at 1.0 after fix — event_cause may still be leaking."
    )


# ── BUG-7: load_raw must exclude 'Non-corridor' rows ─────────────────────────

def test_load_raw_excludes_non_corridor_rows():
    """Rows with corridor='Non-corridor' must not be present after load_raw()."""
    from src.pipeline import load_raw
    df = load_raw()
    assert "Non-corridor" not in df["corridor"].values, (
        f"Found {(df['corridor'] == 'Non-corridor').sum()} 'Non-corridor' rows — "
        "load_raw() must filter these out."
    )


def test_load_raw_non_corridor_filtered_in_csv(tmp_path):
    """Even when CSV contains Non-corridor rows, load_raw() must drop them."""
    from src.pipeline import load_raw
    csv = tmp_path / "events.csv"
    csv.write_text(
        "id,event_type,event_cause,latitude,longitude,corridor,zone,police_station,"
        "junction,start_datetime,closed_datetime,requires_road_closure,priority,status\n"
        "E1,planned,public_event,12.97,77.59,Non-corridor,Central Zone 2,Cubbon Park,"
        ",2024-02-12 18:00:00+00:00,2024-02-12 20:00:00+00:00,FALSE,High,closed\n"
        "E2,unplanned,accident,12.95,77.58,ORR East 1,East Zone 1,Bellandur,"
        ",2024-01-30 09:00:00+00:00,2024-01-30 11:00:00+00:00,FALSE,High,closed\n"
    )
    df = load_raw(path=csv)
    assert len(df) == 1
    assert df.iloc[0]["corridor"] == "ORR East 1"
