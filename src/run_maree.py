"""Run a single M.A.R.E.E. evaluation in this process.

Mirrors src/run_one.py for the ensemble. The M.A.R.E.E. classifier needs
the original DataFrame (not just preprocessed arrays) at fit time so it can
read sample dates and partition into temporal windows. A dedicated runner
keeps the API differences from infecting the baseline pipeline.

Usage:
    python -m src.run_maree --base random_forest --stage cv
    python -m src.run_maree --base lightgbm --stage holdout

Writes results to results/parts/{stage}_temporal_maree_{base}.json
(Random splits don't make sense for M.A.R.E.E. — the whole point is the
temporal split — so we only produce temporal-protocol numbers.)
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "4")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "4")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import argparse
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from src import config
from src.data.loader import load_combined
from src.data.splits import temporal_density_split
from src.models.advanced import make_lightgbm
from src.models.baselines import make_random_forest
from src.models.ensemble import MareeConfig, MareeEnsemble
from src.preprocessing import build_preprocessor

PARTS_DIR = config.PROJECT_ROOT / "results" / "parts"
PARTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_FACTORIES = {
    "random_forest": make_random_forest,
    "lightgbm": make_lightgbm,
}


def _eval_maree(
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    base_name: str,
) -> dict:
    """Train M.A.R.E.E. on train_df, score on eval_df. Return AUC + accuracy."""
    cfg = MareeConfig(base_factory=BASE_FACTORIES[base_name])
    ensemble = MareeEnsemble(ensemble_config=cfg)
    t0 = time.perf_counter()
    ensemble.fit_from_dataframe(train_df, preprocessor_factory=build_preprocessor)
    fit_seconds = time.perf_counter() - t0

    proba = ensemble.predict_proba_from_dataframe(eval_df)[:, 1]
    block_decision = ensemble.predict_from_dataframe(eval_df)
    y_true = eval_df[config.LABEL_COL].to_numpy()
    auc = roc_auc_score(y_true, proba)
    # Accuracy is computed on the BLOCK decision (block-by-default semantics)
    acc = accuracy_score(y_true, block_decision)
    # Also compute the "p >= 0.5" accuracy for direct comparison vs baseline
    raw_preds = (proba >= 0.5).astype(int)
    raw_acc = accuracy_score(y_true, raw_preds)

    return {
        "auc": float(auc),
        "accuracy_block_by_default": float(acc),
        "accuracy_raw_threshold": float(raw_acc),
        "n_train": int(len(train_df)),
        "n_eval": int(len(eval_df)),
        "n_active_windows": int(ensemble.n_active_),
        "in_window_accuracies": ensemble.in_window_accuracies_.tolist(),
        "fit_seconds": float(fit_seconds),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True, choices=list(BASE_FACTORIES))
    p.add_argument("--stage", required=True, choices=["cv", "holdout"])
    args = p.parse_args()

    print(f"[{args.stage} temporal] maree_{args.base}")

    df = load_combined()
    split = temporal_density_split(df)
    print(f"  {split.summary()}")

    if args.stage == "holdout":
        record = _eval_maree(split.train, split.test, args.base)
        record["model_name"] = f"maree_{args.base}"
        record["protocol"] = "temporal"
        record["fold"] = -1
        out = PARTS_DIR / f"holdout_temporal_maree_{args.base}.json"
        out.write_text(json.dumps([record], indent=2))
        print(f"  AUC={record['auc']:.4f} "
              f"ACC(block-by-default)={record['accuracy_block_by_default']:.4f} "
              f"ACC(raw 0.5)={record['accuracy_raw_threshold']:.4f} "
              f"fit={record['fit_seconds']:.1f}s")
        print(f"Wrote {out}")
        return 0

    # CV stage: 10-fold stratified within split.train. Each fold trains a
    # fresh M.A.R.E.E. on 9/10 of the training portion (preserving sample
    # dates) and scores on the held-out fold.
    skf = StratifiedKFold(n_splits=config.CV_FOLDS, shuffle=True, random_state=config.CV_SEED)
    train_df = split.train.reset_index(drop=True)
    y = train_df[config.LABEL_COL].to_numpy()

    fold_records: list[dict] = []
    for fold_i, (tr_idx, val_idx) in enumerate(skf.split(np.zeros(len(y)), y)):
        fold_train = train_df.iloc[tr_idx]
        fold_val = train_df.iloc[val_idx]
        # M.A.R.E.E. needs sample dates on malware in its training portion.
        # The CV slice may drop entire windows — recover by skipping folds
        # whose surviving malware spans only one window.
        try:
            metrics = _eval_maree(fold_train, fold_val, args.base)
        except (ValueError, RuntimeError) as e:
            print(f"  fold {fold_i+1:>2}/{config.CV_FOLDS}: SKIPPED — {e}")
            continue
        record = {
            "model_name": f"maree_{args.base}",
            "protocol": "temporal",
            "fold": fold_i,
            "auc": metrics["auc"],
            "accuracy": metrics["accuracy_block_by_default"],
            "accuracy_raw_threshold": metrics["accuracy_raw_threshold"],
            "n_train": metrics["n_train"],
            "n_val": metrics["n_eval"],
            "n_active_windows": metrics["n_active_windows"],
            "fit_seconds": metrics["fit_seconds"],
        }
        fold_records.append(record)
        print(f"  fold {fold_i+1:>2}/{config.CV_FOLDS}: "
              f"AUC={record['auc']:.4f} "
              f"ACC={record['accuracy']:.4f} "
              f"active_windows={record['n_active_windows']} "
              f"fit={record['fit_seconds']:.1f}s")

    out = PARTS_DIR / f"cv_temporal_maree_{args.base}.json"
    out.write_text(json.dumps(fold_records, indent=2))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
