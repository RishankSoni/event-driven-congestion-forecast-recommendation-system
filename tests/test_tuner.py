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
