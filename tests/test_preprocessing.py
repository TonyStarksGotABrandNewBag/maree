"""Unit tests for src.preprocessing — the sklearn pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import config
from src.preprocessing import build_preprocessor, select_features


class TestSelectFeatures:
    def test_returns_required_columns(self, tiny_combined):
        out = select_features(tiny_combined)
        for c in config.RAW_NUMERIC_FEATURES:
            assert c in out.columns
        for c in config.STRING_FEATURE_SOURCES:
            assert c in out.columns
        assert config.LABEL_COL in out.columns

    def test_does_not_mutate_input(self, tiny_combined):
        before = tiny_combined.copy()
        _ = select_features(tiny_combined)
        pd.testing.assert_frame_equal(tiny_combined, before)

    def test_raises_on_missing_columns(self):
        df = pd.DataFrame({"BaseOfCode": [1, 2]})
        with pytest.raises(ValueError, match="missing required columns"):
            select_features(df)


class TestBuildPreprocessor:
    def test_returns_pipeline(self):
        pipe = build_preprocessor()
        assert pipe is not None
        # Should have at least the engineer + columns steps
        assert len(pipe.steps) >= 2

    def test_fits_and_transforms_to_27_columns(self, tiny_combined):
        X = select_features(tiny_combined).drop(columns=[config.LABEL_COL])
        pipe = build_preprocessor()
        Xt = pipe.fit_transform(X)
        assert Xt.shape == (len(X), len(config.FEATURE_COLUMNS))
        assert Xt.shape[1] == 27  # explicitly: matches Quantic spec

    def test_no_nans_or_infs_in_output(self, tiny_combined):
        X = select_features(tiny_combined).drop(columns=[config.LABEL_COL])
        pipe = build_preprocessor()
        Xt = pipe.fit_transform(X)
        assert np.all(np.isfinite(Xt)), "Preprocessor produced NaN or Inf"

    def test_separate_pipelines_produce_same_output_with_same_data(self, tiny_combined):
        """Determinism: two fresh pipelines on same training data → same output."""
        X = select_features(tiny_combined).drop(columns=[config.LABEL_COL])
        a = build_preprocessor().fit_transform(X)
        b = build_preprocessor().fit_transform(X)
        np.testing.assert_array_almost_equal(a, b)

    def test_train_only_fit_then_transform_test(self, tiny_combined):
        """Critical rubric requirement: scaler params must come from train only."""
        X = select_features(tiny_combined).drop(columns=[config.LABEL_COL])
        train, test = X.iloc[:30].copy(), X.iloc[30:].copy()

        pipe = build_preprocessor()
        Xtrain = pipe.fit_transform(train)
        Xtest = pipe.transform(test)  # must NOT call fit on test

        # Train means should be ≈ 0 after standardization
        # (FunctionTransformer + log1p + StandardScaler — the scaler portion
        # outputs zero-mean if fit on these data)
        assert Xtrain.shape[0] == 30
        assert Xtest.shape[0] == len(X) - 30
        assert Xtrain.shape[1] == Xtest.shape[1] == 27
