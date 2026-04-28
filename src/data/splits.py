"""Train/test splits — both random (rubric baseline) and temporal (M.A.R.E.E.).

Two protocols, evaluated side-by-side. The asymmetry between them is the
headline finding of the entire capstone (Pendlebury et al., USENIX 2019).

  RANDOM:    stratified 80/20 — what the rubric baseline expects
  TEMPORAL:  density-aware — train on the oldest 80% of malware (by sample
             count, not by calendar date), test on the newest 20%.
             Goodware is bootstrapped uniformly across both folds since it
             lacks per-sample collection timestamps.

Why density-aware temporal splits: per-year malware density varies 36× in
this dataset (10,078 in 2013 vs 279 in 2020). A naïve calendar-year split
puts almost all data on the train side and produces an artificially small
test set. Splitting by quantile of cumulative sample count gives both folds
meaningful size while preserving the train-before-test guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src import config


@dataclass(frozen=True)
class SplitResult:
    """Train and test partitions with metadata about how the split was made."""
    train: pd.DataFrame
    test: pd.DataFrame
    protocol: str  # "random" or "temporal"
    cutoff: pd.Timestamp | None = None  # populated for temporal splits
    n_train: int = 0
    n_test: int = 0

    def summary(self) -> str:
        m_train = int((self.train[config.LABEL_COL] == 1).sum())
        m_test = int((self.test[config.LABEL_COL] == 1).sum())
        g_train = int((self.train[config.LABEL_COL] == 0).sum())
        g_test = int((self.test[config.LABEL_COL] == 0).sum())
        cutoff = f", cutoff={self.cutoff.date()}" if self.cutoff is not None else ""
        return (
            f"{self.protocol} split{cutoff}: "
            f"train={self.n_train:,} ({m_train:,} mw / {g_train:,} gw), "
            f"test={self.n_test:,} ({m_test:,} mw / {g_test:,} gw)"
        )


def random_stratified_split(
    df: pd.DataFrame,
    *,
    test_fraction: float = config.RANDOM_TEST_FRACTION,
    seed: int = config.SPLIT_SEED,
) -> SplitResult:
    """Stratified 80/20 split — the rubric baseline."""
    if config.LABEL_COL not in df.columns:
        raise ValueError(f"Missing required column: {config.LABEL_COL!r}")

    train_df, test_df = train_test_split(
        df,
        test_size=test_fraction,
        stratify=df[config.LABEL_COL],
        random_state=seed,
        shuffle=True,
    )
    return SplitResult(
        train=train_df.reset_index(drop=True),
        test=test_df.reset_index(drop=True),
        protocol="random",
        n_train=len(train_df),
        n_test=len(test_df),
    )


def temporal_density_split(
    df: pd.DataFrame,
    *,
    test_fraction: float = config.TEMPORAL_TEST_FRACTION,
    seed: int = config.SPLIT_SEED,
) -> SplitResult:
    """Density-aware temporal split.

    Procedure:
      1. Compute the cutoff date such that exactly `test_fraction` of
         the malware samples (by count, not by calendar duration) fall
         after the cutoff.
      2. Train malware = samples with sample_date <= cutoff.
         Test  malware = samples with sample_date >  cutoff.
      3. Goodware (no per-sample dates) is randomly partitioned in the
         same ratio, with stratification preserved.

    This guarantees:
      - Strict no-look-ahead for malware (the methodologically critical class)
      - Both folds have meaningful malware sample sizes despite year imbalance
      - Goodware proportion matches between train and test
    """
    if config.LABEL_COL not in df.columns:
        raise ValueError(f"Missing required column: {config.LABEL_COL!r}")
    if config.SAMPLE_DATE_COL not in df.columns:
        raise ValueError(f"Missing required column: {config.SAMPLE_DATE_COL!r}")

    malware = df[df[config.LABEL_COL] == 1].copy()
    goodware = df[df[config.LABEL_COL] == 0].copy()

    if malware.empty:
        raise ValueError("Cannot do temporal split: no malware samples in df.")
    if malware[config.SAMPLE_DATE_COL].isna().any():
        raise ValueError(
            f"Some malware rows have NaT in {config.SAMPLE_DATE_COL!r}. "
            f"Loader should have populated all malware sample dates."
        )

    # Sort malware by date and find the cutoff such that the newest
    # `test_fraction` of rows fall in the test set.
    malware_sorted = malware.sort_values(config.SAMPLE_DATE_COL, kind="mergesort")
    n_test_mw = max(int(round(len(malware_sorted) * test_fraction)), 1)
    cutoff_idx = len(malware_sorted) - n_test_mw
    cutoff = malware_sorted[config.SAMPLE_DATE_COL].iloc[cutoff_idx]

    # All malware strictly before cutoff goes to train; cutoff and after to test.
    # (Edge case: many rows can share the cutoff date because daily files
    # batch many samples on the same day. We put cutoff-day rows in the
    # test set to honor "post-T" inclusively.)
    mw_train = malware_sorted[malware_sorted[config.SAMPLE_DATE_COL] < cutoff]
    mw_test = malware_sorted[malware_sorted[config.SAMPLE_DATE_COL] >= cutoff]

    # Goodware: stratified random split in the same ratio
    gw_train, gw_test = train_test_split(
        goodware,
        test_size=test_fraction,
        random_state=seed,
        shuffle=True,
    )

    train_df = pd.concat([mw_train, gw_train], ignore_index=True)
    test_df = pd.concat([mw_test, gw_test], ignore_index=True)

    return SplitResult(
        train=train_df,
        test=test_df,
        protocol="temporal",
        cutoff=cutoff,
        n_train=len(train_df),
        n_test=len(test_df),
    )


def temporal_window_quantiles(
    df: pd.DataFrame,
    n_windows: int = 5,
) -> list[pd.Timestamp]:
    """Compute quantile-based cutoff dates for the M.A.R.E.E. ensemble.

    The ensemble trains one classifier per temporal window. We use density-
    quantile cutoffs (each window contains ~equal malware sample count)
    rather than equal-calendar-duration windows, again because year density
    varies 36×.

    Returns:
        A list of (n_windows + 1) Timestamp values. Window i covers
        [cutoffs[i], cutoffs[i+1]).
    """
    malware = df[(df[config.LABEL_COL] == 1) & df[config.SAMPLE_DATE_COL].notna()]
    if malware.empty:
        raise ValueError("Cannot compute window quantiles: no malware with dates.")

    sorted_dates = malware[config.SAMPLE_DATE_COL].sort_values().reset_index(drop=True)
    quantiles = np.linspace(0, 1, n_windows + 1)
    cutoffs = sorted_dates.quantile(quantiles).to_list()
    return cutoffs
