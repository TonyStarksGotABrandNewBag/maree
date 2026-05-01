"""Build the labeled demo CSV for the recorded video's `/upload` beat.

Emits a stratified subsample of the random 80/20 hold-out (the
rubric's literal "20% hold-out test file"), preserving the natural
class ratio (~58% malware on the Brazilian corpus). The on-camera
sample size is capped at 500 rows because the live free-tier Render
container has 512 MB of RAM and the predict-with-uncertainty pass
on the full 10,152-row hold-out OOMs the worker (empirically
confirmed: 500 returns 200 in ~48s, 800 OOMs at ~70s, 1,500 OOMs at
~92s, 10,152 OOMs at ~67s). 500 rows is sufficient for ±5%
confidence intervals on FPR/FNR and for the rubric's batch-metrics
display (AUC, accuracy, confusion matrix).

The CSV contains the 19 raw numeric features, the 4 string-feature
sources, and the `Label` column — the schema the production model
expects on upload. Engineered features are computed at predict time,
so they are not in this CSV.

Output: `My Drive/Quantic/maree-demo-upload.csv` (and a local copy
under `/tmp/` as a backup if Drive sync is slow).

Run from the repo root:
    PYTHONPATH=. .venv/bin/python scripts/build_demo_upload.py

The presenter drags this CSV into the upload form on the live site
during the demo's 3:00-4:30 beat to demonstrate AUC, accuracy, and
confusion-matrix display on a labeled batch from the rubric's
literal hold-out.
"""

from __future__ import annotations

import os
from pathlib import Path

# Cap thread pools BEFORE importing native ML libs.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import pandas as pd

from src import config
from src.data.loader import load_combined
from src.data.splits import random_stratified_split

# Empirically the largest sample the 512 MB free-tier container can
# predict on inside the Render edge proxy's request budget.
SAMPLE_SIZE = 500

DRIVE_DIR = Path(
    "/Users/jarvis/Library/CloudStorage/"
    "GoogleDrive-kenny.gordon@cornerstone-innovations.com/"
    "My Drive/Quantic"
)
DRIVE_PATH = DRIVE_DIR / "maree-demo-upload.csv"
LOCAL_BACKUP = Path("/tmp/maree-demo-upload.csv")


def main() -> int:
    print("Loading combined dataset...")
    df = load_combined()

    print("Computing random 80/20 stratified split (the rubric hold-out)...")
    split = random_stratified_split(df)
    test = split.test.reset_index(drop=True)
    print(f"  Hold-out test set: {len(test):,} rows")

    malware = test[test[config.LABEL_COL] == 1]
    goodware = test[test[config.LABEL_COL] == 0]
    natural_ratio = len(malware) / len(test)
    n_mal = int(round(SAMPLE_SIZE * natural_ratio))
    n_good = SAMPLE_SIZE - n_mal

    mal_s = malware.sample(n=n_mal, random_state=config.GLOBAL_SEED)
    good_s = goodware.sample(n=n_good, random_state=config.GLOBAL_SEED)
    sample = (
        pd.concat([mal_s, good_s], ignore_index=True)
        .sample(frac=1, random_state=config.GLOBAL_SEED)
        .reset_index(drop=True)
    )

    # Restrict to the columns the upload pipeline expects: raw numerics,
    # string-feature sources, and Label. The internal SAMPLE_DATE_COL is
    # dropped because the production /upload doesn't need it.
    keep_cols = (
        list(config.RAW_NUMERIC_FEATURES)
        + list(config.STRING_FEATURE_SOURCES)
        + [config.LABEL_COL]
    )
    sample = sample[keep_cols]

    DRIVE_DIR.mkdir(parents=True, exist_ok=True)
    sample.to_csv(DRIVE_PATH, index=False)
    sample.to_csv(LOCAL_BACKUP, index=False)

    print(f"\nWrote {DRIVE_PATH} ({DRIVE_PATH.stat().st_size:,} bytes)")
    print(f"Wrote {LOCAL_BACKUP} ({LOCAL_BACKUP.stat().st_size:,} bytes)")
    print(
        f"Sample composition: {n_mal:,} malware, {n_good:,} goodware, "
        f"{len(sample):,} total (natural class ratio "
        f"{natural_ratio:.1%} malware preserved from full hold-out)"
    )
    print(f"Columns ({len(sample.columns)}): {', '.join(sample.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
