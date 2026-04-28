"""M.A.R.E.E. — the drift-adaptive ensemble.

Multi-classifier Adaptive Recognition, Explainable Engine.

Architecture:

  1. SLIDING-WINDOW TRAINING.
     The training portion of the temporal split is partitioned into K
     density-quantile windows (each window contains roughly equal malware
     sample count). One base classifier is trained per window. The newest
     window's model is fresh; the oldest window's model is the most stale.

  2. PER-WINDOW CALIBRATION.
     Each base classifier is calibrated on a held-out tail of its own
     window using isotonic regression. The 0.5 threshold becomes
     meaningful again, per-model, even after the underlying score
     distribution shifts.

  3. ADAPTIVE WEIGHTED VOTING.
     The ensemble's positive-class probability is a weighted sum of the
     calibrated per-model probabilities. Weights are computed by
     drift_detector.compute_weights() from each model's in-window
     accuracy and (optionally) its recent observed accuracy. Newer +
     more-accurate + less-decayed models vote louder.

  4. BLOCK-BY-DEFAULT DECISION.
     Three verdicts: ALLOWED, BLOCKED-malware, BLOCKED-uncertain.
     The ensemble must AFFIRMATIVELY allow — silence, disagreement, or
     low confidence all yield BLOCK. This is the zero-trust failure mode
     locked in earlier.

The class is sklearn-compatible (.fit / .predict / .predict_proba) so it
slots into the existing train/eval orchestrator unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import accuracy_score

from src import config
from src.data.splits import temporal_window_quantiles
from src.models.advanced import make_lightgbm
from src.models.baselines import make_random_forest
from src.models.drift_detector import (
    WeightingConfig,
    compute_weights,
    ensemble_disagreement,
)


# ---------------------------------------------------------------------------
# Verdict enum-equivalent (using strings for serializability)
# ---------------------------------------------------------------------------

VERDICT_ALLOWED = "ALLOWED"
VERDICT_BLOCKED_MALWARE = "BLOCKED_MALWARE"
VERDICT_BLOCKED_UNCERTAIN = "BLOCKED_UNCERTAIN"


@dataclass
class MareePrediction:
    """Per-sample output: verdict + supporting probabilities."""
    verdict: str
    probability: float          # calibrated ensemble probability of malware
    confidence: float           # 1 - 2*(disagreement std), in [0, 1]
    is_malware_decision: bool   # what predict() returns


@dataclass
class MareeConfig:
    """Hyperparameters for the M.A.R.E.E. ensemble."""
    n_windows: int = 5
    base_factory: Callable = field(default=make_random_forest)
    calibration_tail_fraction: float = 0.15  # last 15% of each window for calibration
    confidence_threshold: float = 0.65       # max(p_malware, 1-p_malware) must exceed this
    weighting: WeightingConfig = field(default_factory=WeightingConfig)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_window_into_train_and_calibration(
    window_df: pd.DataFrame,
    *,
    tail_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split one temporal window into a fit-portion and a calibration tail.

    The calibration tail is the *latest* tail_fraction of the window's malware
    samples (by date), with goodware partitioned in the same ratio. This
    keeps the calibrator's distribution as close as possible to deployment.
    """
    if window_df.empty:
        return window_df, window_df

    malware = window_df[window_df[config.LABEL_COL] == 1].sort_values(config.SAMPLE_DATE_COL)
    goodware = window_df[window_df[config.LABEL_COL] == 0]

    n_cal_mw = max(int(round(len(malware) * tail_fraction)), 1) if len(malware) > 0 else 0
    n_cal_gw = max(int(round(len(goodware) * tail_fraction)), 0) if len(goodware) > 0 else 0

    cal_mw = malware.tail(n_cal_mw) if n_cal_mw > 0 else malware.iloc[:0]
    fit_mw = malware.iloc[:-n_cal_mw] if n_cal_mw > 0 else malware

    rng = np.random.default_rng(config.GLOBAL_SEED)
    if n_cal_gw > 0:
        cal_idx = rng.choice(len(goodware), size=n_cal_gw, replace=False)
        cal_gw = goodware.iloc[cal_idx]
        fit_gw = goodware.drop(goodware.index[cal_idx])
    else:
        cal_gw = goodware.iloc[:0]
        fit_gw = goodware

    fit_df = pd.concat([fit_mw, fit_gw], ignore_index=True)
    cal_df = pd.concat([cal_mw, cal_gw], ignore_index=True)
    return fit_df, cal_df


def _partition_into_windows(
    train_df: pd.DataFrame,
    n_windows: int,
) -> list[pd.DataFrame]:
    """Split the temporal training portion into n_windows by malware quantile.

    Goodware (no per-sample dates) is randomly partitioned into the same
    number of windows in the same proportions, so each window has both
    classes for fitting.
    """
    cutoffs = temporal_window_quantiles(train_df, n_windows=n_windows)
    malware = train_df[train_df[config.LABEL_COL] == 1].copy()
    goodware = train_df[train_df[config.LABEL_COL] == 0].copy()

    # Goodware: shuffle and split into n_windows
    rng = np.random.default_rng(config.GLOBAL_SEED)
    gw_idx = rng.permutation(len(goodware))
    gw_chunks = np.array_split(gw_idx, n_windows)

    windows: list[pd.DataFrame] = []
    for w in range(n_windows):
        lo, hi = cutoffs[w], cutoffs[w + 1]
        # Last window inclusive on the right edge
        if w == n_windows - 1:
            mw_chunk = malware[(malware[config.SAMPLE_DATE_COL] >= lo)
                               & (malware[config.SAMPLE_DATE_COL] <= hi)]
        else:
            mw_chunk = malware[(malware[config.SAMPLE_DATE_COL] >= lo)
                               & (malware[config.SAMPLE_DATE_COL] < hi)]
        gw_chunk = goodware.iloc[gw_chunks[w]]
        windows.append(pd.concat([mw_chunk, gw_chunk], ignore_index=True))
    return windows


# ---------------------------------------------------------------------------
# The ensemble itself
# ---------------------------------------------------------------------------

class MareeEnsemble(BaseEstimator, ClassifierMixin):
    """M.A.R.E.E. — drift-adaptive ensemble with calibrated abstention.

    Unlike the baseline classifiers, fit() needs the original DataFrame
    (not just the preprocessed feature matrix) so it can read sample
    dates and partition the training data into temporal windows.
    Preprocessing is applied per-window inside fit().

    A small adapter (fit_from_dataframe / predict_proba_from_dataframe)
    reads the DataFrame directly. The standard sklearn .fit(X, y) /
    .predict_proba(X) paths still work but assume the caller has already
    done the windowing — they're useful only for tests, not the main
    eval pipeline.
    """

    def __init__(self, *, ensemble_config: MareeConfig | None = None):
        self.ensemble_config = ensemble_config or MareeConfig()

    def get_params(self, deep: bool = True) -> dict:
        return {"ensemble_config": self.ensemble_config}

    # ----- main training entry point used by the eval pipeline -----

    def fit_from_dataframe(
        self,
        train_df: pd.DataFrame,
        preprocessor_factory: Callable,
    ) -> "MareeEnsemble":
        """Fit K base classifiers on K temporal windows.

        Args:
            train_df: the training portion of a temporal split. Must
                contain Label and __sample_date columns.
            preprocessor_factory: callable returning a fresh sklearn
                Pipeline. Each window gets its own fitted preprocessor.

        Returns:
            self.
        """
        cfg = self.ensemble_config
        windows = _partition_into_windows(train_df, n_windows=cfg.n_windows)

        self.preprocessors_ = []
        self.base_models_ = []
        self.calibrators_ = []
        self.in_window_accuracies_ = np.zeros(cfg.n_windows)
        self.window_dates_ = []

        for w, window_df in enumerate(windows):
            mw_in_window = (window_df[config.LABEL_COL] == 1).sum()
            gw_in_window = (window_df[config.LABEL_COL] == 0).sum()
            if mw_in_window == 0 or gw_in_window == 0:
                # Degenerate window — skip; we will exclude it from voting
                self.preprocessors_.append(None)
                self.base_models_.append(None)
                self.calibrators_.append(None)
                self.window_dates_.append(None)
                continue

            fit_df, cal_df = _split_window_into_train_and_calibration(
                window_df, tail_fraction=cfg.calibration_tail_fraction,
            )
            # Need both classes in both portions
            if cal_df.empty or (cal_df[config.LABEL_COL] == 1).sum() == 0:
                # Calibration tail too small or single-class; skip calibration,
                # use the model uncalibrated.
                cal_df = pd.DataFrame()

            # --- preprocess + fit base ---
            from src.preprocessing import select_features  # avoid circular
            sel_fit = select_features(fit_df)
            X_fit = sel_fit.drop(columns=[config.LABEL_COL])
            y_fit = sel_fit[config.LABEL_COL].to_numpy()

            preprocessor = preprocessor_factory()
            Xt_fit = preprocessor.fit_transform(X_fit)
            base = cfg.base_factory()
            base.fit(Xt_fit, y_fit)

            # --- calibrate on the held-out tail ---
            if not cal_df.empty:
                sel_cal = select_features(cal_df)
                X_cal = sel_cal.drop(columns=[config.LABEL_COL])
                y_cal = sel_cal[config.LABEL_COL].to_numpy()
                Xt_cal = preprocessor.transform(X_cal)
                raw_proba = base.predict_proba(Xt_cal)[:, 1]
                calibrator = IsotonicRegression(out_of_bounds="clip")
                calibrator.fit(raw_proba, y_cal)
                # Compute calibrated in-window accuracy as the model's
                # baseline against which deployment-time accuracy is measured.
                cal_proba = calibrator.transform(raw_proba)
                cal_preds = (cal_proba >= 0.5).astype(int)
                self.in_window_accuracies_[w] = accuracy_score(y_cal, cal_preds)
            else:
                calibrator = None
                # Fall back to in-fit accuracy as the baseline
                fit_proba = base.predict_proba(Xt_fit)[:, 1]
                fit_preds = (fit_proba >= 0.5).astype(int)
                self.in_window_accuracies_[w] = accuracy_score(y_fit, fit_preds)

            self.preprocessors_.append(preprocessor)
            self.base_models_.append(base)
            self.calibrators_.append(calibrator)
            self.window_dates_.append(window_df[config.SAMPLE_DATE_COL].max())

        self.classes_ = np.array([0, 1])
        self.n_active_ = sum(b is not None for b in self.base_models_)
        return self

    # ----- prediction with full uncertainty info -----

    def predict_with_uncertainty(
        self,
        df: pd.DataFrame,
        recent_accuracies: np.ndarray | None = None,
    ) -> list[MareePrediction]:
        """Per-sample verdict with full supporting info."""
        per_model_proba = self._stack_per_model_proba(df)  # shape (K, N)
        weights = compute_weights(
            self.in_window_accuracies_,
            recent_accuracies=recent_accuracies,
            config=self.ensemble_config.weighting,
        )

        # Mask out skipped windows (their per-model row is all NaN; weight to 0)
        active = np.array([b is not None for b in self.base_models_])
        masked_weights = weights.copy()
        masked_weights[~active] = 0.0
        if masked_weights.sum() <= 0:
            raise RuntimeError("M.A.R.E.E. has no active windows; refusing to predict.")
        masked_weights /= masked_weights.sum()

        # Replace NaN rows with neutral 0.5 (they get weight 0 anyway, but
        # the matmul should not produce NaN)
        clean_proba = np.where(np.isnan(per_model_proba), 0.5, per_model_proba)
        ensemble_proba = masked_weights @ clean_proba   # shape (N,)

        # Disagreement only across active windows
        active_proba = clean_proba[active]
        disagree = ensemble_disagreement(active_proba)
        # Confidence = how decisively the ensemble committed away from 0.5
        confidence = 2.0 * np.abs(ensemble_proba - 0.5)
        # Joint confidence: penalize high disagreement
        joint = np.clip(confidence - disagree, 0.0, 1.0)

        threshold = self.ensemble_config.confidence_threshold
        verdicts: list[MareePrediction] = []
        for i in range(len(ensemble_proba)):
            p = float(ensemble_proba[i])
            c = float(joint[i])
            if c < threshold:
                verdict = VERDICT_BLOCKED_UNCERTAIN
                is_malware = True  # block-by-default ⇒ counted as positive
            elif p >= 0.5:
                verdict = VERDICT_BLOCKED_MALWARE
                is_malware = True
            else:
                verdict = VERDICT_ALLOWED
                is_malware = False
            verdicts.append(MareePrediction(
                verdict=verdict,
                probability=p,
                confidence=c,
                is_malware_decision=is_malware,
            ))
        return verdicts

    # ----- sklearn-compatible interface (used by eval.py) -----

    def predict_proba_from_dataframe(self, df: pd.DataFrame) -> np.ndarray:
        """Return calibrated ensemble probability of [class 0, class 1]."""
        per_model_proba = self._stack_per_model_proba(df)
        weights = compute_weights(
            self.in_window_accuracies_,
            recent_accuracies=None,
            config=self.ensemble_config.weighting,
        )
        active = np.array([b is not None for b in self.base_models_])
        masked = weights.copy()
        masked[~active] = 0.0
        masked /= max(masked.sum(), 1e-12)
        clean = np.where(np.isnan(per_model_proba), 0.5, per_model_proba)
        p1 = masked @ clean
        return np.column_stack([1.0 - p1, p1])

    def predict_from_dataframe(self, df: pd.DataFrame) -> np.ndarray:
        """Block-by-default verdict as a 0/1 array (1 = malware OR uncertain)."""
        verdicts = self.predict_with_uncertainty(df)
        return np.array([int(v.is_malware_decision) for v in verdicts])

    # ----- internal -----

    def _stack_per_model_proba(self, df: pd.DataFrame) -> np.ndarray:
        """For each ensemble member, predict_proba on df (or NaN if skipped)."""
        from src.preprocessing import select_features  # avoid circular
        sel = select_features(df)
        X = sel.drop(columns=[config.LABEL_COL])

        K = self.ensemble_config.n_windows
        N = len(X)
        out = np.full((K, N), np.nan, dtype=np.float64)
        for i in range(K):
            if self.base_models_[i] is None:
                continue
            Xt = self.preprocessors_[i].transform(X)
            raw = self.base_models_[i].predict_proba(Xt)[:, 1]
            if self.calibrators_[i] is not None:
                out[i] = self.calibrators_[i].transform(raw)
            else:
                out[i] = raw
        return out


# ---------------------------------------------------------------------------
# Convenience factories — match the BASELINE_FACTORIES interface
# ---------------------------------------------------------------------------

def make_maree_random_forest() -> MareeEnsemble:
    """M.A.R.E.E. with Random Forest base classifiers (the AUC leader)."""
    return MareeEnsemble(ensemble_config=MareeConfig(base_factory=make_random_forest))


def make_maree_lightgbm() -> MareeEnsemble:
    """M.A.R.E.E. with LightGBM base classifiers (fast + similar AUC)."""
    return MareeEnsemble(ensemble_config=MareeConfig(base_factory=make_lightgbm))
