"""Unit tests for src.models.baselines and src.models.advanced.

Each test trains the model on a tiny synthetic dataset, verifies it
produces sensible predictions and proba shapes. Avoids brittle assertions
about specific accuracy values — the contract is "fit and predict work".

Note: TorchMLPClassifier tests live in tests/test_models_torch.py because
loading torch in the same process as XGBoost / LightGBM / CatBoost
segfaults on macOS (libomp conflict). Run them separately.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.models.advanced import ADVANCED_FACTORIES, make_catboost, make_lightgbm, make_xgboost
from src.models.baselines import (
    BASELINE_FACTORIES,
    make_decision_tree,
    make_logistic_regression,
    make_random_forest,
)


@pytest.fixture()
def tiny_dataset() -> tuple[np.ndarray, np.ndarray]:
    """A linearly-separable synthetic 2-class problem, easy enough that
    every model in the zoo should learn it cleanly."""
    rng = np.random.default_rng(0)
    n_per_class = 50
    pos = rng.normal(loc=2.0, scale=0.8, size=(n_per_class, 27))
    neg = rng.normal(loc=-2.0, scale=0.8, size=(n_per_class, 27))
    X = np.vstack([pos, neg]).astype(np.float32)
    y = np.array([1] * n_per_class + [0] * n_per_class)
    # Shuffle
    perm = rng.permutation(len(y))
    return X[perm], y[perm]


class TestBaselineFactories:
    @pytest.mark.parametrize("factory", [
        make_logistic_regression, make_decision_tree, make_random_forest,
    ])
    def test_factory_returns_fittable_model(self, factory, tiny_dataset):
        X, y = tiny_dataset
        model = factory()
        model.fit(X, y)
        preds = model.predict(X)
        proba = model.predict_proba(X)
        assert preds.shape == (len(y),)
        assert proba.shape == (len(y), 2)
        # Predictions match argmax of probabilities (sanity)
        np.testing.assert_array_equal(proba.argmax(axis=1), preds)

    def test_baseline_registry_has_four_models(self):
        assert len(BASELINE_FACTORIES) == 4
        assert set(BASELINE_FACTORIES) == {
            "logistic_regression", "decision_tree", "random_forest", "torch_mlp",
        }


class TestAdvancedFactories:
    @pytest.mark.parametrize("factory", [make_xgboost, make_lightgbm, make_catboost])
    def test_factory_returns_fittable_model(self, factory, tiny_dataset):
        X, y = tiny_dataset
        model = factory()
        model.fit(X, y)
        preds = model.predict(X)
        proba = model.predict_proba(X)
        assert preds.shape == (len(y),)
        assert proba.shape == (len(y), 2)

    def test_advanced_registry_has_three_models(self):
        assert len(ADVANCED_FACTORIES) == 3
        assert set(ADVANCED_FACTORIES) == {"xgboost", "lightgbm", "catboost"}


# TorchMLPClassifier tests live in tests/test_models_torch.py — see that
# file's module docstring for why they must run in a separate pytest invocation.
