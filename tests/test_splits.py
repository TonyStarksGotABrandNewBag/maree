"""Unit tests for src.data.splits — random and temporal split protocols."""

from __future__ import annotations

import pandas as pd
import pytest

from src import config
from src.data.splits import (
    SplitResult,
    random_stratified_split,
    temporal_density_split,
    temporal_window_quantiles,
)


class TestRandomStratifiedSplit:
    def test_returns_split_result(self, tiny_combined):
        result = random_stratified_split(tiny_combined)
        assert isinstance(result, SplitResult)
        assert result.protocol == "random"
        assert result.cutoff is None

    def test_train_test_sizes_add_up(self, tiny_combined):
        result = random_stratified_split(tiny_combined)
        assert result.n_train + result.n_test == len(tiny_combined)

    def test_test_fraction_is_respected(self, tiny_combined):
        result = random_stratified_split(tiny_combined, test_fraction=0.2)
        # Allow ±1 row tolerance for small samples
        expected_test = round(len(tiny_combined) * 0.2)
        assert abs(result.n_test - expected_test) <= 1

    def test_class_balance_preserved(self, tiny_combined):
        result = random_stratified_split(tiny_combined)
        train_pos = (result.train[config.LABEL_COL] == 1).mean()
        test_pos = (result.test[config.LABEL_COL] == 1).mean()
        full_pos = (tiny_combined[config.LABEL_COL] == 1).mean()
        # Stratification should keep class proportions within ~5pp
        assert abs(train_pos - full_pos) < 0.05
        assert abs(test_pos - full_pos) < 0.05

    def test_seed_makes_split_reproducible(self, tiny_combined):
        a = random_stratified_split(tiny_combined, seed=42)
        b = random_stratified_split(tiny_combined, seed=42)
        pd.testing.assert_frame_equal(a.train, b.train)
        pd.testing.assert_frame_equal(a.test, b.test)

    def test_different_seeds_produce_different_splits(self, tiny_combined):
        a = random_stratified_split(tiny_combined, seed=1)
        b = random_stratified_split(tiny_combined, seed=2)
        # Almost certainly different at this size
        assert not a.train.equals(b.train)

    def test_raises_on_missing_label(self):
        df = pd.DataFrame({"x": [1, 2, 3]})
        with pytest.raises(ValueError, match="Label"):
            random_stratified_split(df)


class TestTemporalDensitySplit:
    def test_returns_split_result_with_cutoff(self, tiny_combined):
        result = temporal_density_split(tiny_combined)
        assert result.protocol == "temporal"
        assert result.cutoff is not None
        assert isinstance(result.cutoff, pd.Timestamp)

    def test_no_lookahead_for_malware(self, tiny_combined):
        """Train malware must all be strictly before cutoff; test malware at/after."""
        result = temporal_density_split(tiny_combined)
        train_mw = result.train[result.train[config.LABEL_COL] == 1]
        test_mw = result.test[result.test[config.LABEL_COL] == 1]

        if not train_mw.empty:
            assert train_mw[config.SAMPLE_DATE_COL].max() < result.cutoff
        if not test_mw.empty:
            assert test_mw[config.SAMPLE_DATE_COL].min() >= result.cutoff

    def test_goodware_is_split_proportionally(self, tiny_combined):
        result = temporal_density_split(tiny_combined, test_fraction=0.2)
        gw_total = (tiny_combined[config.LABEL_COL] == 0).sum()
        gw_test = (result.test[config.LABEL_COL] == 0).sum()
        # ±1 row tolerance for small samples
        assert abs(gw_test - round(gw_total * 0.2)) <= 1

    def test_raises_on_missing_label(self, tiny_combined):
        bad = tiny_combined.drop(columns=[config.LABEL_COL])
        with pytest.raises(ValueError, match="Label"):
            temporal_density_split(bad)

    def test_raises_on_missing_sample_date(self, tiny_combined):
        bad = tiny_combined.drop(columns=[config.SAMPLE_DATE_COL])
        with pytest.raises(ValueError, match="__sample_date"):
            temporal_density_split(bad)

    def test_raises_when_malware_dates_missing(self, tiny_combined):
        # Null out one malware date — must raise
        bad = tiny_combined.copy()
        first_mw_idx = bad[bad[config.LABEL_COL] == 1].index[0]
        bad.loc[first_mw_idx, config.SAMPLE_DATE_COL] = pd.NaT
        with pytest.raises(ValueError, match="malware rows have NaT"):
            temporal_density_split(bad)

    def test_seed_makes_goodware_split_reproducible(self, tiny_combined):
        a = temporal_density_split(tiny_combined, seed=42)
        b = temporal_density_split(tiny_combined, seed=42)
        pd.testing.assert_frame_equal(
            a.train.sort_values(by=list(a.train.columns)).reset_index(drop=True),
            b.train.sort_values(by=list(b.train.columns)).reset_index(drop=True),
        )


class TestTemporalWindowQuantiles:
    def test_returns_n_plus_one_cutoffs(self, tiny_combined):
        cutoffs = temporal_window_quantiles(tiny_combined, n_windows=5)
        assert len(cutoffs) == 6

    def test_cutoffs_are_monotonic(self, tiny_combined):
        cutoffs = temporal_window_quantiles(tiny_combined, n_windows=5)
        for i in range(len(cutoffs) - 1):
            assert cutoffs[i] <= cutoffs[i + 1]
