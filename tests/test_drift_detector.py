"""Unit tests for src.models.drift_detector."""

from __future__ import annotations

import numpy as np
import pytest

from src.models.drift_detector import (
    WeightingConfig,
    average_psi,
    compute_weights,
    ensemble_disagreement,
    per_model_accuracy_decay,
    population_stability_index,
)


class TestPerModelAccuracyDecay:
    def test_no_decay_when_recent_matches_window(self):
        d = per_model_accuracy_decay(
            in_window_accuracies=np.array([0.95, 0.92, 0.93]),
            recent_accuracies=np.array([0.95, 0.92, 0.93]),
        )
        np.testing.assert_array_almost_equal(d, [0, 0, 0])

    def test_full_decay_when_recent_is_zero(self):
        d = per_model_accuracy_decay(
            in_window_accuracies=np.array([1.0, 1.0]),
            recent_accuracies=np.array([0.0, 0.0]),
        )
        np.testing.assert_array_almost_equal(d, [1.0, 1.0])

    def test_partial_decay(self):
        d = per_model_accuracy_decay(
            in_window_accuracies=np.array([0.9]),
            recent_accuracies=np.array([0.6]),
        )
        # (0.9 - 0.6) / 0.9 = 0.333...
        np.testing.assert_array_almost_equal(d, [1 / 3], decimal=4)

    def test_recent_above_window_clamps_to_zero(self):
        d = per_model_accuracy_decay(
            in_window_accuracies=np.array([0.8]),
            recent_accuracies=np.array([0.95]),
        )
        np.testing.assert_array_almost_equal(d, [0.0])

    def test_zero_baseline_does_not_divide_by_zero(self):
        d = per_model_accuracy_decay(
            in_window_accuracies=np.array([0.0]),
            recent_accuracies=np.array([0.5]),
        )
        # Should not crash; zero baseline → zero decay
        np.testing.assert_array_almost_equal(d, [0.0])

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            per_model_accuracy_decay(
                in_window_accuracies=np.array([0.9, 0.8]),
                recent_accuracies=np.array([0.9]),
            )


class TestEnsembleDisagreement:
    def test_zero_when_all_models_agree(self):
        proba = np.array([[0.8, 0.2, 0.9],
                          [0.8, 0.2, 0.9]])
        d = ensemble_disagreement(proba)
        np.testing.assert_array_almost_equal(d, [0, 0, 0])

    def test_high_when_models_split(self):
        proba = np.array([[1.0, 0.0],
                          [0.0, 1.0]])
        d = ensemble_disagreement(proba)
        # std = 0.5 → rescaled to 1.0
        np.testing.assert_array_almost_equal(d, [1.0, 1.0])

    def test_intermediate(self):
        proba = np.array([[0.9, 0.5],
                          [0.7, 0.5]])
        d = ensemble_disagreement(proba)
        # std for col 0 = 0.1; rescaled = 0.2
        np.testing.assert_array_almost_equal(d, [0.2, 0.0])

    def test_rejects_non_2d(self):
        with pytest.raises(ValueError):
            ensemble_disagreement(np.array([0.5, 0.7]))


class TestPopulationStabilityIndex:
    def test_zero_when_distributions_identical(self):
        rng = np.random.default_rng(0)
        x = rng.normal(size=5000)
        psi = population_stability_index(x, x.copy())
        assert psi < 0.01

    def test_large_when_distributions_differ(self):
        rng = np.random.default_rng(0)
        train = rng.normal(loc=0, scale=1, size=5000)
        deploy = rng.normal(loc=3, scale=1, size=5000)  # heavily shifted
        psi = population_stability_index(train, deploy)
        assert psi > 0.5

    def test_returns_zero_for_constant_column(self):
        psi = population_stability_index(
            np.zeros(100), np.zeros(100),
        )
        assert psi == 0.0

    def test_handles_empty_inputs(self):
        psi = population_stability_index(np.array([]), np.array([1, 2, 3]))
        assert psi == 0.0


class TestAveragePSI:
    def test_zero_for_identical(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(1000, 5))
        assert average_psi(X, X.copy()) < 0.01

    def test_large_for_shifted(self):
        rng = np.random.default_rng(0)
        train = rng.normal(loc=0, size=(1000, 5))
        deploy = rng.normal(loc=2, size=(1000, 5))
        assert average_psi(train, deploy) > 0.3

    def test_feature_dim_mismatch_raises(self):
        with pytest.raises(ValueError):
            average_psi(np.zeros((10, 3)), np.zeros((10, 5)))


class TestComputeWeights:
    def test_weights_sum_to_one(self):
        w = compute_weights(np.array([0.9, 0.92, 0.95]))
        np.testing.assert_almost_equal(w.sum(), 1.0)

    def test_newest_model_weighted_highest_with_equal_quality(self):
        w = compute_weights(np.array([0.9, 0.9, 0.9]))
        assert w[-1] > w[0]

    def test_higher_quality_weighted_higher(self):
        w = compute_weights(
            np.array([0.5, 0.5, 0.99]),
            config=WeightingConfig(recency_alpha=0.0),  # neutralize recency
        )
        assert w[-1] > w[0]

    def test_decay_penalizes(self):
        no_decay = compute_weights(
            np.array([0.9, 0.9, 0.9]),
            recent_accuracies=np.array([0.9, 0.9, 0.9]),
        )
        with_decay = compute_weights(
            np.array([0.9, 0.9, 0.9]),
            recent_accuracies=np.array([0.5, 0.9, 0.9]),  # first model decayed
        )
        # The decayed model gets a lower weight than its no-decay version
        assert with_decay[0] < no_decay[0]

    def test_falls_back_to_uniform_on_degenerate(self):
        w = compute_weights(np.zeros(4))
        np.testing.assert_array_almost_equal(w, [0.25, 0.25, 0.25, 0.25])
