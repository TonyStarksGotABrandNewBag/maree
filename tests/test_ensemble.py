"""Unit tests for src.models.ensemble (the M.A.R.E.E. ensemble itself).

Synthetic-fixture tests that verify:
  - The ensemble fits, produces probabilities, and votes via the block-by-
    default rule.
  - Per-window calibration runs and stores in_window_accuracies.
  - The three-verdict output is exhaustive (every prediction is one of
    ALLOWED / BLOCKED_MALWARE / BLOCKED_UNCERTAIN).
  - The fit/predict pipeline composes against the real preprocessing
    pipeline (build_preprocessor).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.models.ensemble import (
    VERDICT_ALLOWED,
    VERDICT_BLOCKED_MALWARE,
    VERDICT_BLOCKED_UNCERTAIN,
    MareeConfig,
    MareeEnsemble,
)
from src.models.baselines import make_logistic_regression
from src.preprocessing import build_preprocessor


class TestMareeEnsembleFit:
    def test_fit_runs_on_tiny_combined(self, tiny_combined: pd.DataFrame):
        # Use LR as the base model (fastest) and 3 windows so we exercise
        # multi-window training without spending CV time.
        ens = MareeEnsemble(ensemble_config=MareeConfig(
            n_windows=3,
            base_factory=make_logistic_regression,
        ))
        ens.fit_from_dataframe(tiny_combined, preprocessor_factory=build_preprocessor)
        assert hasattr(ens, "base_models_")
        assert len(ens.base_models_) == 3
        # At least one window must have produced an active model
        assert ens.n_active_ >= 1

    def test_in_window_accuracies_recorded(self, tiny_combined: pd.DataFrame):
        ens = MareeEnsemble(ensemble_config=MareeConfig(
            n_windows=3,
            base_factory=make_logistic_regression,
        ))
        ens.fit_from_dataframe(tiny_combined, preprocessor_factory=build_preprocessor)
        # All recorded accuracies should be in [0, 1]
        for acc in ens.in_window_accuracies_:
            assert 0.0 <= acc <= 1.0


class TestMareeEnsemblePredict:
    def test_predict_proba_shape(self, tiny_combined: pd.DataFrame):
        ens = MareeEnsemble(ensemble_config=MareeConfig(
            n_windows=3,
            base_factory=make_logistic_regression,
        ))
        ens.fit_from_dataframe(tiny_combined, preprocessor_factory=build_preprocessor)
        proba = ens.predict_proba_from_dataframe(tiny_combined)
        assert proba.shape == (len(tiny_combined), 2)
        # Rows should sum to 1
        np.testing.assert_array_almost_equal(proba.sum(axis=1), 1.0)

    def test_predict_returns_binary(self, tiny_combined: pd.DataFrame):
        ens = MareeEnsemble(ensemble_config=MareeConfig(
            n_windows=3,
            base_factory=make_logistic_regression,
        ))
        ens.fit_from_dataframe(tiny_combined, preprocessor_factory=build_preprocessor)
        preds = ens.predict_from_dataframe(tiny_combined)
        assert preds.shape == (len(tiny_combined),)
        assert set(np.unique(preds)).issubset({0, 1})

    def test_three_verdict_categories_are_exhaustive(self, tiny_combined: pd.DataFrame):
        ens = MareeEnsemble(ensemble_config=MareeConfig(
            n_windows=3,
            base_factory=make_logistic_regression,
        ))
        ens.fit_from_dataframe(tiny_combined, preprocessor_factory=build_preprocessor)
        verdicts = ens.predict_with_uncertainty(tiny_combined)
        valid = {VERDICT_ALLOWED, VERDICT_BLOCKED_MALWARE, VERDICT_BLOCKED_UNCERTAIN}
        for v in verdicts:
            assert v.verdict in valid

    def test_block_by_default_invariant(self, tiny_combined: pd.DataFrame):
        """Every BLOCKED_* verdict must map to is_malware_decision=True;
        only ALLOWED verdicts may map to False."""
        ens = MareeEnsemble(ensemble_config=MareeConfig(
            n_windows=3,
            base_factory=make_logistic_regression,
        ))
        ens.fit_from_dataframe(tiny_combined, preprocessor_factory=build_preprocessor)
        verdicts = ens.predict_with_uncertainty(tiny_combined)
        for v in verdicts:
            if v.verdict == VERDICT_ALLOWED:
                assert v.is_malware_decision is False
            else:
                assert v.is_malware_decision is True

    def test_high_confidence_threshold_increases_blocks(self, tiny_combined: pd.DataFrame):
        """A more demanding confidence threshold should produce at least as
        many blocks as a lenient one."""
        lenient = MareeEnsemble(ensemble_config=MareeConfig(
            n_windows=3, base_factory=make_logistic_regression,
            confidence_threshold=0.0,
        ))
        strict = MareeEnsemble(ensemble_config=MareeConfig(
            n_windows=3, base_factory=make_logistic_regression,
            confidence_threshold=0.99,
        ))
        lenient.fit_from_dataframe(tiny_combined, preprocessor_factory=build_preprocessor)
        strict.fit_from_dataframe(tiny_combined, preprocessor_factory=build_preprocessor)
        n_blocks_lenient = lenient.predict_from_dataframe(tiny_combined).sum()
        n_blocks_strict = strict.predict_from_dataframe(tiny_combined).sum()
        assert n_blocks_strict >= n_blocks_lenient
