"""Hyperparameter tuning via 10-fold stratified CV — rubric Step 4 deliverable.

Searches a small but informative grid for the two leading model families
(Random Forest, LightGBM) on the random-split training portion. The random
split is the rubric baseline; tuning on this protocol gives the cleanest
"would tighter hyperparameters help on the standard CV protocol?" answer.

Output: `results/hyperparameter_search.json` with best params, best CV AUC,
and the delta vs. the conservative defaults already documented in
`evaluation-and-design.md` §4.4.

Run from the repo root:
    .venv/bin/python scripts/hyperparameter_search.py
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Cap thread pools BEFORE importing native ML libs (same pattern as elsewhere)
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline

from src import config
from src.data.loader import load_combined
from src.data.splits import random_stratified_split
from src.models.advanced import make_lightgbm
from src.models.baselines import make_random_forest
from src.preprocessing import build_preprocessor


RESULTS_PATH = config.PROJECT_ROOT / "results" / "hyperparameter_search.json"

# Conservative-defaults CV AUC numbers, copied verbatim from
# `evaluation-and-design.md` §4.4 (random-protocol 10-fold CV mean).
DEFAULTS_BASELINE = {
    "random_forest": 0.9975,
    "lightgbm": 0.9984,
}


def _build_pipeline(estimator) -> Pipeline:
    return Pipeline([("pre", build_preprocessor()), ("clf", estimator)])


def search_random_forest(X, y, cv) -> dict:
    pipe = _build_pipeline(make_random_forest())
    grid = {
        "clf__n_estimators": [200, 400],
        "clf__max_depth": [10, 20, None],
        "clf__min_samples_leaf": [2, 5],
    }
    print(f"\n[RF] grid over {len(grid['clf__n_estimators']) * len(grid['clf__max_depth']) * len(grid['clf__min_samples_leaf'])} cells × {cv.get_n_splits()} folds")
    t0 = time.time()
    gs = GridSearchCV(
        pipe,
        param_grid=grid,
        scoring="roc_auc",
        cv=cv,
        n_jobs=2,           # outer parallelism over folds; inner RF n_jobs=4 → 8 total threads
        refit=False,        # we don't need the refit; we just report best params + score
        verbose=1,
        return_train_score=False,
    )
    gs.fit(X, y)
    elapsed = time.time() - t0
    return {
        "model": "random_forest",
        "grid": grid,
        "best_params": gs.best_params_,
        "best_cv_auc": float(gs.best_score_),
        "default_cv_auc": DEFAULTS_BASELINE["random_forest"],
        "delta_vs_default": float(gs.best_score_) - DEFAULTS_BASELINE["random_forest"],
        "elapsed_seconds": round(elapsed, 1),
        "all_cells": [
            {"params": dict(p), "mean_auc": float(s), "std_auc": float(sd)}
            for p, s, sd in zip(
                gs.cv_results_["params"],
                gs.cv_results_["mean_test_score"],
                gs.cv_results_["std_test_score"],
            )
        ],
    }


def search_lightgbm(X, y, cv) -> dict:
    pipe = _build_pipeline(make_lightgbm())
    grid = {
        "clf__num_leaves": [31, 63, 127],
        "clf__learning_rate": [0.05, 0.1],
        "clf__n_estimators": [200, 400],
    }
    print(f"\n[LGBM] grid over {len(grid['clf__num_leaves']) * len(grid['clf__learning_rate']) * len(grid['clf__n_estimators'])} cells × {cv.get_n_splits()} folds")
    t0 = time.time()
    gs = GridSearchCV(
        pipe,
        param_grid=grid,
        scoring="roc_auc",
        cv=cv,
        n_jobs=2,
        refit=False,
        verbose=1,
        return_train_score=False,
    )
    gs.fit(X, y)
    elapsed = time.time() - t0
    return {
        "model": "lightgbm",
        "grid": grid,
        "best_params": gs.best_params_,
        "best_cv_auc": float(gs.best_score_),
        "default_cv_auc": DEFAULTS_BASELINE["lightgbm"],
        "delta_vs_default": float(gs.best_score_) - DEFAULTS_BASELINE["lightgbm"],
        "elapsed_seconds": round(elapsed, 1),
        "all_cells": [
            {"params": dict(p), "mean_auc": float(s), "std_auc": float(sd)}
            for p, s, sd in zip(
                gs.cv_results_["params"],
                gs.cv_results_["mean_test_score"],
                gs.cv_results_["std_test_score"],
            )
        ],
    }


def main() -> int:
    print("Loading combined dataset…")
    df = load_combined()
    split = random_stratified_split(df)
    print(f"  {split.summary()}")

    train = split.train
    X = train.drop(columns=[config.LABEL_COL, config.SAMPLE_DATE_COL], errors="ignore")
    y = train[config.LABEL_COL].astype(int).to_numpy()

    cv = StratifiedKFold(n_splits=config.CV_FOLDS, shuffle=True, random_state=config.CV_SEED)

    rf_result = search_random_forest(X, y, cv)
    print(f"  [RF] best AUC = {rf_result['best_cv_auc']:.4f} "
          f"(default {rf_result['default_cv_auc']:.4f}; "
          f"Δ {rf_result['delta_vs_default']:+.4f})")
    print(f"  [RF] best params: {rf_result['best_params']}")

    lgbm_result = search_lightgbm(X, y, cv)
    print(f"  [LGBM] best AUC = {lgbm_result['best_cv_auc']:.4f} "
          f"(default {lgbm_result['default_cv_auc']:.4f}; "
          f"Δ {lgbm_result['delta_vs_default']:+.4f})")
    print(f"  [LGBM] best params: {lgbm_result['best_params']}")

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol": "random_stratified_80_20",
        "cv_folds": config.CV_FOLDS,
        "scoring": "roc_auc",
        "seed": config.GLOBAL_SEED,
        "n_train": int(len(train)),
        "results": [rf_result, lgbm_result],
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
