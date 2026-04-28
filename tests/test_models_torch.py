"""TorchMLPClassifier tests — isolated from other ML library tests.

On macOS, importing torch in the same Python process as XGBoost / LightGBM /
CatBoost causes libomp conflicts that segfault. We split the torch-using
tests into this file and run them as a separate pytest invocation.

To run all tests:
    .venv/bin/pytest tests/ --ignore=tests/test_models_torch.py
    .venv/bin/pytest tests/test_models_torch.py
"""

from __future__ import annotations

import numpy as np
import pytest

from src.models.baselines import TorchMLPClassifier, make_torch_mlp


@pytest.fixture()
def tiny_dataset() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    n_per_class = 50
    pos = rng.normal(loc=2.0, scale=0.8, size=(n_per_class, 27))
    neg = rng.normal(loc=-2.0, scale=0.8, size=(n_per_class, 27))
    X = np.vstack([pos, neg]).astype(np.float32)
    y = np.array([1] * n_per_class + [0] * n_per_class)
    perm = rng.permutation(len(y))
    return X[perm], y[perm]


class TestMakeTorchMlp:
    def test_factory_returns_fittable_model(self, tiny_dataset):
        X, y = tiny_dataset
        model = make_torch_mlp()
        model.fit(X, y)
        preds = model.predict(X)
        proba = model.predict_proba(X)
        assert preds.shape == (len(y),)
        assert proba.shape == (len(y), 2)
        np.testing.assert_array_equal(proba.argmax(axis=1), preds)


class TestTorchMLPClassifier:
    def test_seed_makes_predictions_reproducible(self, tiny_dataset):
        X, y = tiny_dataset
        a = TorchMLPClassifier(epochs=5, random_state=42).fit(X, y)
        b = TorchMLPClassifier(epochs=5, random_state=42).fit(X, y)
        np.testing.assert_array_equal(a.predict(X), b.predict(X))

    def test_raises_predict_proba_before_fit(self):
        m = TorchMLPClassifier()
        with pytest.raises(RuntimeError, match="fit"):
            m.predict_proba(np.zeros((5, 27)))

    def test_rejects_non_binary_labels(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(30, 27)).astype(np.float32)
        y = rng.integers(0, 3, size=30)
        with pytest.raises(ValueError, match="binary classification only"):
            TorchMLPClassifier(epochs=1).fit(X, y)
