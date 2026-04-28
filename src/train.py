"""Cross-validation orchestrator — runs all 7 model factories under both
split protocols (random and temporal) and produces the headline result table.

This is where Pendlebury's claim becomes a number for THIS dataset:
the gap between random-split AUC and temporal-split AUC, per model.

Usage (script form):
    .venv/bin/python -m src.train

Usage (programmatic):
    from src.train import run_full_evaluation
    results = run_full_evaluation()
"""

from __future__ import annotations

# Cap OpenMP / BLAS thread pools BEFORE importing numpy/sklearn/xgboost/etc.
# Multiple libraries (scikit-learn via OpenBLAS, XGBoost, LightGBM, CatBoost)
# each try to spawn n_jobs=-1 worker pools; on macOS this can cause OpenMP
# library conflicts (libomp loaded twice) and segfaults. Explicit limits
# avoid the collision and keep the run reproducible.
import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "4")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "4")
# Catch the macOS multiple-OpenMP-runtime issue cleanly rather than crashing.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# NOTE: src.train is imported by src.run_one. We must NOT eagerly import
# torch here — torch's bundled libomp conflicts with the libomp that
# XGBoost / LightGBM / CatBoost use, and that conflict crashes any
# subprocess that loads torch alongside those libraries. The torch_mlp
# baseline lives behind a deferred import in src.models.baselines and is
# only triggered when its factory is actually instantiated.

import json
import time
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from src import config
from src.data.loader import load_combined
from src.data.splits import SplitResult, random_stratified_split, temporal_density_split
from src.models.advanced import ADVANCED_FACTORIES
from src.models.baselines import BASELINE_FACTORIES
from src.preprocessing import build_preprocessor, select_features

ALL_FACTORIES = {**BASELINE_FACTORIES, **ADVANCED_FACTORIES}

RESULTS_DIR = config.PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class FoldResult:
    model_name: str
    protocol: str
    fold: int
    auc: float
    accuracy: float
    n_train: int
    n_val: int
    fit_seconds: float


@dataclass
class HoldOutResult:
    model_name: str
    protocol: str
    auc: float
    accuracy: float
    n_train: int
    n_test: int
    fit_seconds: float


def _prepare_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    selected = select_features(df)
    y = selected[config.LABEL_COL].to_numpy()
    X = selected.drop(columns=[config.LABEL_COL])
    return X, y


def _fit_score(
    factory_name: str,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
) -> tuple[float, float, float]:
    """Fit a fresh preprocessor + model on train, score on val. Returns (auc, acc, fit_seconds)."""
    pipeline = build_preprocessor()
    Xt_train = pipeline.fit_transform(X_train)
    Xt_val = pipeline.transform(X_val)

    factory = ALL_FACTORIES[factory_name]
    model = factory()

    t0 = time.perf_counter()
    model.fit(Xt_train, y_train)
    fit_s = time.perf_counter() - t0

    proba = model.predict_proba(Xt_val)[:, 1]
    preds = (proba >= 0.5).astype(int)
    return roc_auc_score(y_val, proba), accuracy_score(y_val, preds), fit_s


def cv_for_protocol(
    train_df: pd.DataFrame,
    protocol: str,
    *,
    factories: dict | None = None,
    n_splits: int = config.CV_FOLDS,
    verbose: bool = True,
) -> list[FoldResult]:
    """10-fold stratified CV on the training portion of a split.

    Important: cross-validation here is stratified-on-Label even for the
    *temporal* protocol's training portion. The temporal no-look-ahead
    invariant is enforced at the outer split level (we never CV across
    the train/test boundary). Within the training fold, k-fold CV is the
    rubric standard for hyperparameter selection.
    """
    factories = factories or ALL_FACTORIES
    X, y = _prepare_xy(train_df)
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=config.CV_SEED)

    all_results: list[FoldResult] = []
    for name in factories:
        if verbose:
            print(f"  [{protocol}] {name} — 10-fold CV")
        for fold_i, (train_idx, val_idx) in enumerate(skf.split(X, y)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]
            auc, acc, fit_s = _fit_score(name, X_train, y_train, X_val, y_val)
            all_results.append(FoldResult(
                model_name=name,
                protocol=protocol,
                fold=fold_i,
                auc=auc,
                accuracy=acc,
                n_train=len(train_idx),
                n_val=len(val_idx),
                fit_seconds=fit_s,
            ))
            if verbose:
                print(f"    fold {fold_i+1:>2}/{n_splits}: AUC={auc:.4f} ACC={acc:.4f} fit={fit_s:.1f}s")
    return all_results


def hold_out_eval(
    split: SplitResult,
    *,
    factories: dict | None = None,
    verbose: bool = True,
) -> list[HoldOutResult]:
    """Train on the full split.train; score on split.test. One fit per model."""
    factories = factories or ALL_FACTORIES
    X_train, y_train = _prepare_xy(split.train)
    X_test, y_test = _prepare_xy(split.test)

    results: list[HoldOutResult] = []
    for name in factories:
        if verbose:
            print(f"  [{split.protocol} hold-out] {name}")
        auc, acc, fit_s = _fit_score(name, X_train, y_train, X_test, y_test)
        results.append(HoldOutResult(
            model_name=name,
            protocol=split.protocol,
            auc=auc,
            accuracy=acc,
            n_train=len(X_train),
            n_test=len(X_test),
            fit_seconds=fit_s,
        ))
        if verbose:
            print(f"    AUC={auc:.4f} ACC={acc:.4f} fit={fit_s:.1f}s")
    return results


def run_full_evaluation(*, factories: dict | None = None, verbose: bool = True) -> dict:
    """The complete Phase D experiment: CV + hold-out under both protocols."""
    print("=== M.A.R.E.E. Phase D — full evaluation ===")
    print("Loading combined dataset...")
    df = load_combined()
    print(f"  {len(df):,} rows ({(df[config.LABEL_COL] == 1).sum():,} mw / "
          f"{(df[config.LABEL_COL] == 0).sum():,} gw)")

    print("\nSplitting (random stratified)...")
    rand_split = random_stratified_split(df)
    print(f"  {rand_split.summary()}")

    print("\nSplitting (density-aware temporal)...")
    temp_split = temporal_density_split(df)
    print(f"  {temp_split.summary()}")

    print("\n--- CV under random split ---")
    cv_random = cv_for_protocol(rand_split.train, "random", factories=factories, verbose=verbose)

    print("\n--- CV under temporal split ---")
    cv_temporal = cv_for_protocol(temp_split.train, "temporal", factories=factories, verbose=verbose)

    print("\n--- Hold-out eval (random) ---")
    holdout_random = hold_out_eval(rand_split, factories=factories, verbose=verbose)

    print("\n--- Hold-out eval (temporal) ---")
    holdout_temporal = hold_out_eval(temp_split, factories=factories, verbose=verbose)

    results = {
        "cv_random": [asdict(r) for r in cv_random],
        "cv_temporal": [asdict(r) for r in cv_temporal],
        "holdout_random": [asdict(r) for r in holdout_random],
        "holdout_temporal": [asdict(r) for r in holdout_temporal],
        "metadata": {
            "n_combined": len(df),
            "random_cutoff": None,
            "temporal_cutoff": str(temp_split.cutoff.date()),
            "n_models": len(factories or ALL_FACTORIES),
            "cv_folds": config.CV_FOLDS,
            "global_seed": config.GLOBAL_SEED,
        },
    }

    # Persist raw results for downstream eval.py to render the report table
    out = RESULTS_DIR / "phase_d_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out}")
    return results


if __name__ == "__main__":
    run_full_evaluation()
