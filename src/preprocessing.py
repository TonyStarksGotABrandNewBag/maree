"""Preprocessing pipeline — sklearn pipeline, fit on train only.

Rubric requirement (Quantic PDF, Step 5):
  > Apply scaling, encoding, and imputation as needed, ensuring
  > transformations are fit on training only.
  > Preprocessing steps must be fit only on training folds during
  > cross-validation, and then applied to the corresponding
  > validation/test folds.

This module exposes a single factory function `build_preprocessor()` that
returns a fresh sklearn Pipeline. The caller fits it on training data only
and reuses it for both transformations on test data and inside CV folds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src import config
from src.features import engineer_string_features

# Numeric features split into "log-then-scale" (heavy-tailed sizes) vs
# "just scale" (everything else). A few of the size-related fields span 9+
# orders of magnitude (e.g., Size: 2,560 to 3,986,103,808 bytes), so log1p
# is essential before standard scaling.
LOG_THEN_SCALE = (
    "BaseOfCode", "BaseOfData", "ImageBase",
    "NumberOfRvaAndSizes", "NumberOfSymbols", "PointerToSymbolTable",
    "Size", "SizeOfCode", "SizeOfHeaders", "SizeOfImage",
    "SizeOfInitializedData", "SizeOfUninitializedData",
    "n_imported_dlls", "n_imported_symbols", "identify_signature_count",
)

# Everything in FEATURE_COLUMNS that isn't in LOG_THEN_SCALE
PASSTHROUGH_SCALE = tuple(
    c for c in config.FEATURE_COLUMNS if c not in LOG_THEN_SCALE
)


def _log1p_safe(X: np.ndarray) -> np.ndarray:
    """log1p that handles negatives and infs gracefully (sets them to 0)."""
    X = np.asarray(X, dtype=np.float64)
    X = np.where(np.isfinite(X) & (X >= 0), X, 0.0)
    return np.log1p(X)


def build_preprocessor() -> Pipeline:
    """Fresh preprocessing pipeline. Caller fits on training data only.

    Returns:
        sklearn Pipeline that transforms a DataFrame with `config.FEATURE_COLUMNS`
        into an ndarray ready for any of the model-zoo classifiers.
    """
    from sklearn.preprocessing import FunctionTransformer

    log_then_scale = Pipeline(steps=[
        ("impute", SimpleImputer(strategy="median")),
        ("log1p", FunctionTransformer(_log1p_safe, validate=False)),
        ("scale", StandardScaler()),
    ])

    passthrough_scale = Pipeline(steps=[
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])

    column_transformer = ColumnTransformer(
        transformers=[
            ("log_then_scale", log_then_scale, list(LOG_THEN_SCALE)),
            ("passthrough_scale", passthrough_scale, list(PASSTHROUGH_SCALE)),
        ],
        remainder="drop",  # only the 27 known features; nothing else
    )

    return Pipeline(steps=[
        ("engineer", FunctionTransformer(engineer_string_features, validate=False)),
        ("columns", column_transformer),
    ])


def select_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return only the 27 feature columns + Label.

    The preprocessor's first step (`engineer`) needs the 4 string source
    columns to derive engineered features. So we keep those alongside the
    raw numerics. The ColumnTransformer drops the source strings via
    `remainder='drop'` after engineering produces the 8 numeric columns.
    """
    needed = (
        list(config.RAW_NUMERIC_FEATURES)
        + list(config.STRING_FEATURE_SOURCES)
        + [config.LABEL_COL]
    )
    have = [c for c in needed if c in df.columns]
    missing = set(needed) - set(have)
    if missing:
        raise ValueError(f"DataFrame missing required columns: {sorted(missing)}")
    return df[have].copy()
