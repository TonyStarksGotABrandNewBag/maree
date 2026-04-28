"""Lightweight tests for src/train.py and src/eval.py.

We do NOT run the full real-data CV here (it would dominate test time).
We test the orchestration logic with a tiny synthetic split + a single
fast model factory, and we test the report renderer with a synthetic
results dict.
"""

from __future__ import annotations

import pytest

from src import config
from src.data.splits import random_stratified_split, temporal_density_split
from src.eval import cv_summary, headline_table, holdout_summary, render_report
from src.models.baselines import make_logistic_regression
from src.train import _fit_score, cv_for_protocol, hold_out_eval

# A "fast factories" dict using only logistic regression keeps these tests
# under a few seconds. The full suite runs only via `python -m src.train`.
FAST = {"logistic_regression": make_logistic_regression}


class TestFitScore:
    def test_returns_three_values(self, tiny_combined):
        from src.preprocessing import select_features
        sel = select_features(tiny_combined)
        X = sel.drop(columns=[config.LABEL_COL])
        y = sel[config.LABEL_COL].to_numpy()
        # Use first 30 as train, rest as val
        auc, acc, fit_s = _fit_score(
            "logistic_regression",
            X.iloc[:30], y[:30],
            X.iloc[30:], y[30:],
        )
        assert 0.0 <= auc <= 1.0
        assert 0.0 <= acc <= 1.0
        assert fit_s >= 0.0


class TestCVForProtocol:
    def test_produces_n_folds_per_model(self, tiny_combined):
        results = cv_for_protocol(
            tiny_combined, "random",
            factories=FAST, n_splits=3, verbose=False,
        )
        assert len(results) == 3  # 1 model × 3 folds
        for r in results:
            assert r.model_name == "logistic_regression"
            assert r.protocol == "random"
            assert 0.0 <= r.auc <= 1.0
            assert 0.0 <= r.accuracy <= 1.0


class TestHoldOutEval:
    def test_random_split_holdout(self, tiny_combined):
        split = random_stratified_split(tiny_combined)
        results = hold_out_eval(split, factories=FAST, verbose=False)
        assert len(results) == 1
        assert results[0].protocol == "random"
        assert results[0].n_train == split.n_train
        assert results[0].n_test == split.n_test

    def test_temporal_split_holdout(self, tiny_combined):
        split = temporal_density_split(tiny_combined)
        results = hold_out_eval(split, factories=FAST, verbose=False)
        assert len(results) == 1
        assert results[0].protocol == "temporal"


# ---------------------------------------------------------------------------
# Report renderer tests use a hand-built results dict
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_results() -> dict:
    """A synthetic results dict that exercises every column of the report."""
    cv_random = [
        {"model_name": m, "protocol": "random", "fold": f,
         "auc": 0.97 - 0.001 * f, "accuracy": 0.95, "n_train": 100, "n_val": 20, "fit_seconds": 1.2}
        for m in ("logistic_regression", "xgboost") for f in range(10)
    ]
    cv_temporal = [
        {"model_name": m, "protocol": "temporal", "fold": f,
         "auc": 0.65 - 0.002 * f, "accuracy": 0.70, "n_train": 100, "n_val": 20, "fit_seconds": 1.3}
        for m in ("logistic_regression", "xgboost") for f in range(10)
    ]
    holdout_random = [
        {"model_name": m, "protocol": "random",
         "auc": 0.96, "accuracy": 0.94, "n_train": 200, "n_test": 50, "fit_seconds": 2.0}
        for m in ("logistic_regression", "xgboost")
    ]
    holdout_temporal = [
        {"model_name": m, "protocol": "temporal",
         "auc": 0.62, "accuracy": 0.68, "n_train": 200, "n_test": 50, "fit_seconds": 2.0}
        for m in ("logistic_regression", "xgboost")
    ]
    return {
        "cv_random": cv_random,
        "cv_temporal": cv_temporal,
        "holdout_random": holdout_random,
        "holdout_temporal": holdout_temporal,
    }


class TestHeadlineTable:
    def test_columns_present(self, fake_results):
        df = headline_table(fake_results)
        for c in (
            "random_cv_auc", "random_cv_std", "temporal_cv_auc", "temporal_cv_std",
            "drift_gap_cv_auc",
            "random_holdout_auc", "temporal_holdout_auc", "drift_gap_holdout_auc",
            "random_holdout_acc", "temporal_holdout_acc", "drift_gap_holdout_acc",
        ):
            assert c in df.columns

    def test_drift_gap_is_positive(self, fake_results):
        df = headline_table(fake_results)
        # Random eval over-reports vs honest temporal eval, so the drift gap
        # (random − temporal) should be positive across all metrics.
        assert (df["drift_gap_cv_auc"] > 0).all()
        assert (df["drift_gap_holdout_auc"] > 0).all()
        assert (df["drift_gap_holdout_acc"] > 0).all()


class TestRenderReport:
    def test_returns_markdown_with_required_sections(self, fake_results):
        md = render_report(fake_results)
        assert "Headline finding" in md
        assert "Full CV statistics" in md
        assert "logistic_regression" in md
        assert "xgboost" in md


class TestSummaryHelpers:
    def test_cv_summary_has_mean_and_std(self, fake_results):
        s = cv_summary(fake_results["cv_random"] + fake_results["cv_temporal"])
        assert "auc_mean" in s.columns
        assert "auc_std" in s.columns

    def test_holdout_summary_indexed_by_model_protocol(self, fake_results):
        s = holdout_summary(fake_results["holdout_random"] + fake_results["holdout_temporal"])
        assert s.index.names == ["model_name", "protocol"]
