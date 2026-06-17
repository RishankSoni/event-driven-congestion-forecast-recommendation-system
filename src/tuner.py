# src/tuner.py
import pandas as pd
import optuna
from sklearn.model_selection import StratifiedKFold, cross_val_score

from src.model import _X, CorridorStatsTransformer, TARGET_COL, _build_pipeline

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
        pipeline = _build_pipeline(params)
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
