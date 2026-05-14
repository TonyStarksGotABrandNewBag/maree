"""Sweep the M.A.R.E.E. joint-confidence threshold to find an empirical optimum.

The 65% threshold was a design choice (above coin-flip with headroom for
calibration variance), not a tuning result. This script:

  1. Loads the production model + the full random 80/20 hold-out.
  2. Scores every sample once. Captures (probability, joint_confidence,
     true_label).
  3. Splits the hold-out indices 50/50 stratified into validation + test.
  4. Sweeps threshold in 0.05 steps from 0.20 to 0.90 on validation.
     At each threshold, re-buckets verdicts using the same rule the
     production code uses and computes FPR, FNR, recall, accuracy, and
     the percentage of files routed to BLOCKED_UNCERTAIN.
  5. Picks three "optima" against three different cost models:
       - Youden's J  (recall - FPR; equal-cost framing)
       - FPR <= 5%   (research-tool target)
       - FPR <= 1%   (commercial endpoint-AV target)
  6. Reports each optimum's performance on the held-out test split, so
     the chosen threshold isn't data-leaking from the same split it was
     selected on.

Honest framing for the LinkedIn post / report: any threshold change is
"post-design tuning" and we report both the heuristic 65% and the
tuned optimum side-by-side.
"""

from __future__ import annotations

import os
from pathlib import Path

# Cap thread pools BEFORE importing native ML libs.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src import config
from src.data.loader import load_combined
from src.data.splits import random_stratified_split

MODEL_PATH = Path("artifacts/maree_production.joblib")
SWEEP_STEP = 0.05
SWEEP_LO = 0.20
SWEEP_HI = 0.90
VAL_FRACTION = 0.5
SPLIT_SEED = config.GLOBAL_SEED


def _bucket(probs: np.ndarray, confs: np.ndarray, threshold: float) -> dict:
    """Re-bucket verdicts at a given threshold and return a metrics dict.

    Mirrors the verdict logic in src.models.ensemble.predict_with_uncertainty:
      - confidence < threshold  -> BLOCKED_UNCERTAIN (block)
      - prob >= 0.5             -> BLOCKED_MALWARE (block)
      - else                    -> ALLOWED (allow)
    """
    blocked_uncertain = confs < threshold
    blocked_malware = (~blocked_uncertain) & (probs >= 0.5)
    is_block = blocked_uncertain | blocked_malware
    return {
        "blocked_uncertain_mask": blocked_uncertain,
        "blocked_malware_mask": blocked_malware,
        "is_block_mask": is_block,
    }


def _metrics(probs: np.ndarray, confs: np.ndarray, labels: np.ndarray, threshold: float) -> dict:
    b = _bucket(probs, confs, threshold)
    is_block = b["is_block_mask"]
    n_pos = (labels == 1).sum()
    n_neg = (labels == 0).sum()
    tp = ((labels == 1) & is_block).sum()
    fn = ((labels == 1) & ~is_block).sum()
    fp = ((labels == 0) & is_block).sum()
    tn = ((labels == 0) & ~is_block).sum()
    return {
        "threshold": round(threshold, 3),
        "FPR": fp / n_neg if n_neg else 0.0,
        "FNR": fn / n_pos if n_pos else 0.0,
        "recall": tp / n_pos if n_pos else 0.0,
        "accuracy": (tp + tn) / len(labels),
        "BLOCKED_UNC_pct": b["blocked_uncertain_mask"].sum() / len(labels) * 100,
        "TN": int(tn),
        "FP": int(fp),
        "FN": int(fn),
        "TP": int(tp),
    }


def main() -> int:
    print("Loading model and random hold-out...")
    model = joblib.load(MODEL_PATH)
    df = load_combined()
    split = random_stratified_split(df)
    test = split.test.reset_index(drop=True)
    print(f"  Hold-out: {len(test):,} rows "
          f"({(test[config.LABEL_COL] == 1).sum():,} mal / "
          f"{(test[config.LABEL_COL] == 0).sum():,} good)")

    print("Scoring every hold-out sample through M.A.R.E.E. once...")
    preds = model.predict_with_uncertainty(test)
    probs = np.array([p.probability for p in preds])
    confs = np.array([p.confidence for p in preds])
    labels = test[config.LABEL_COL].to_numpy()
    print(f"  Probability range: [{probs.min():.4f}, {probs.max():.4f}]")
    print(f"  Joint confidence range: [{confs.min():.4f}, {confs.max():.4f}]")
    print(f"  Joint confidence == 0 (max disagreement): "
          f"{(confs == 0).sum():,} samples")
    print(f"  Joint confidence >= 0.65 (current threshold): "
          f"{(confs >= 0.65).sum():,} samples "
          f"({(confs >= 0.65).mean() * 100:.1f}%)")

    print("\nSplitting hold-out 50/50 into validation + test (stratified, seed=42)...")
    val_idx, test_idx = train_test_split(
        np.arange(len(test)),
        test_size=1.0 - VAL_FRACTION,
        stratify=labels,
        random_state=SPLIT_SEED,
    )
    print(f"  Validation: {len(val_idx):,} samples "
          f"({(labels[val_idx] == 1).sum():,} mal / "
          f"{(labels[val_idx] == 0).sum():,} good)")
    print(f"  Test:       {len(test_idx):,} samples "
          f"({(labels[test_idx] == 1).sum():,} mal / "
          f"{(labels[test_idx] == 0).sum():,} good)")

    print(f"\nSweeping threshold from {SWEEP_LO} to {SWEEP_HI} on validation...")
    thresholds = np.arange(SWEEP_LO, SWEEP_HI + 1e-9, SWEEP_STEP)
    rows = []
    for t in thresholds:
        m = _metrics(probs[val_idx], confs[val_idx], labels[val_idx], float(t))
        rows.append(m)
    val_df = pd.DataFrame(rows)
    print(val_df.to_string(index=False,
                          float_format=lambda x: f"{x:.4f}"))

    # Add current 65% baseline reference rows for both val + test (full split)
    print("\n--- Current heuristic 65% baseline ---")
    val_65 = _metrics(probs[val_idx], confs[val_idx], labels[val_idx], 0.65)
    test_65 = _metrics(probs[test_idx], confs[test_idx], labels[test_idx], 0.65)
    print(f"  val:  FPR={val_65['FPR']:.4f}  FNR={val_65['FNR']:.4f}  "
          f"recall={val_65['recall']:.4f}  acc={val_65['accuracy']:.4f}  "
          f"BLOCKED_UNC={val_65['BLOCKED_UNC_pct']:.1f}%")
    print(f"  test: FPR={test_65['FPR']:.4f}  FNR={test_65['FNR']:.4f}  "
          f"recall={test_65['recall']:.4f}  acc={test_65['accuracy']:.4f}  "
          f"BLOCKED_UNC={test_65['BLOCKED_UNC_pct']:.1f}%")

    # ---- pick optima against three cost models ----
    print("\n=== Optima picked on validation, verified on test ===")

    # 1. Youden's J on validation
    j = val_df["recall"] - val_df["FPR"]
    youden_t = float(val_df.loc[j.idxmax(), "threshold"])
    print("\n1. Youden's J optimum (recall - FPR), equal-cost framing")
    print(f"   threshold = {youden_t:.2f}")
    youden_test = _metrics(probs[test_idx], confs[test_idx], labels[test_idx], youden_t)
    print(f"   test:  FPR={youden_test['FPR']:.4f}  FNR={youden_test['FNR']:.4f}  "
          f"recall={youden_test['recall']:.4f}  acc={youden_test['accuracy']:.4f}  "
          f"BLOCKED_UNC={youden_test['BLOCKED_UNC_pct']:.1f}%")

    # 2. Lowest FPR with FPR <= 5%
    feasible_5 = val_df[val_df["FPR"] <= 0.05]
    if not feasible_5.empty:
        # Of feasible thresholds, pick the one with the highest recall
        chosen = feasible_5.loc[feasible_5["recall"].idxmax()]
        t5 = float(chosen["threshold"])
        print("\n2. FPR <= 5% (research-tool target), maximize recall subject to it")
        print(f"   threshold = {t5:.2f}")
        t5_test = _metrics(probs[test_idx], confs[test_idx], labels[test_idx], t5)
        print(f"   test:  FPR={t5_test['FPR']:.4f}  FNR={t5_test['FNR']:.4f}  "
              f"recall={t5_test['recall']:.4f}  acc={t5_test['accuracy']:.4f}  "
              f"BLOCKED_UNC={t5_test['BLOCKED_UNC_pct']:.1f}%")
    else:
        print(f"\n2. FPR <= 5% infeasible on any threshold in [{SWEEP_LO}, {SWEEP_HI}]")
        print(f"   (Lowest validation FPR across sweep: {val_df['FPR'].min():.4f} "
              f"at threshold {val_df.loc[val_df['FPR'].idxmin(), 'threshold']:.2f})")

    # 3. FPR <= 1% (commercial AV target)
    feasible_1 = val_df[val_df["FPR"] <= 0.01]
    if not feasible_1.empty:
        chosen = feasible_1.loc[feasible_1["recall"].idxmax()]
        t1 = float(chosen["threshold"])
        print("\n3. FPR <= 1% (commercial endpoint-AV target), maximize recall subject to it")
        print(f"   threshold = {t1:.2f}")
        t1_test = _metrics(probs[test_idx], confs[test_idx], labels[test_idx], t1)
        print(f"   test:  FPR={t1_test['FPR']:.4f}  FNR={t1_test['FNR']:.4f}  "
              f"recall={t1_test['recall']:.4f}  acc={t1_test['accuracy']:.4f}  "
              f"BLOCKED_UNC={t1_test['BLOCKED_UNC_pct']:.1f}%")
    else:
        print(f"\n3. FPR <= 1% infeasible on any threshold in [{SWEEP_LO}, {SWEEP_HI}]")
        print("   Implication: at this evaluation, the model cannot clear the "
              "commercial-AV bar with threshold tuning alone. Per-site fine-tuning "
              "or runtime-behavior fusion is needed.")

    # Save validation sweep for the report's §9 / future-work section.
    out_csv = Path("results/threshold_sweep.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    val_df.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
