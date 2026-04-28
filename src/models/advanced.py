"""Additional high-performing models — three gradient-boosting families.

Quantic rubric (Step 6):
  > Additional models: evaluate at least 3 further high-performing models,
  > spanning at least two different algorithm families
  > (e.g., XGBoost, LightGBM, CatBoost).

XGBoost, LightGBM, and CatBoost are three distinct gradient-boosting
implementations with different splitting algorithms (level-wise vs leaf-
wise vs symmetric oblivious trees) and different default categorical
handling. Picking all three satisfies the "≥3 additional, ≥2 families"
requirement and gives the M.A.R.E.E. ensemble (Phase E) genuine diversity
in failure modes.
"""

from __future__ import annotations

from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier

from src import config


def make_xgboost() -> XGBClassifier:
    return XGBClassifier(
        n_estimators=300,
        max_depth=8,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=config.GLOBAL_SEED,
        n_jobs=4,  # capped (see baselines.py make_random_forest)
        eval_metric="auc",
        verbosity=0,
        tree_method="hist",
    )


def make_lightgbm() -> LGBMClassifier:
    return LGBMClassifier(
        n_estimators=300,
        max_depth=-1,  # let num_leaves drive complexity (LightGBM idiom)
        num_leaves=63,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=config.GLOBAL_SEED,
        n_jobs=4,  # capped (see baselines.py make_random_forest)
        verbose=-1,
        force_col_wise=True,  # avoids a noisy auto-detection warning
    )


def make_catboost() -> CatBoostClassifier:
    return CatBoostClassifier(
        iterations=300,
        depth=8,
        learning_rate=0.1,
        random_state=config.GLOBAL_SEED,
        thread_count=4,
        verbose=False,
        loss_function="Logloss",
        eval_metric="AUC",
        allow_writing_files=False,  # don't litter cwd with catboost_info/
    )


ADVANCED_FACTORIES = {
    "xgboost": make_xgboost,
    "lightgbm": make_lightgbm,
    "catboost": make_catboost,
}
