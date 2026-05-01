"""Build a labeled demo CSV for the recorded video's `/upload` beat.

Pulls a balanced sample from the random 80/20 hold-out (the rubric's
"20% hold-out test file") and writes it as a CSV the demo presenter
can drag-and-drop into the live upload form. The resulting file
contains the 19 raw numeric features, the 4 string-feature sources,
and the `Label` column — the schema the production model expects on
upload. Engineered features are computed at predict time, so they
are not in this CSV.

Output: `My Drive/Quantic/maree-demo-upload.csv` (and a local copy
under `/tmp/` as a backup if Drive sync is slow).

Run from the repo root:
    .venv/bin/python scripts/build_demo_upload.py

The presenter then drags this CSV into the upload form on the live
site during the demo's 3:00-4:30 beat to demonstrate AUC, accuracy,
and confusion-matrix display on a labeled batch.
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

# How many rows to sample from the hold-out. The /upload page caps the
# rendered table at 200 rows; 100 is enough to compute a statistically
# meaningful confusion matrix while keeping the page from scrolling
# off-screen during the demo.
SAMPLE_SIZE = 100

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
    test = split.test
    print(f"  Hold-out test set: {len(test):,} rows")

    # Balanced sample: half the SAMPLE_SIZE from each class so the
    # confusion matrix is not dominated by one class.
    half = SAMPLE_SIZE // 2
    malware = test[test[config.LABEL_COL] == 1].sample(n=half, random_state=config.GLOBAL_SEED)
    goodware = test[test[config.LABEL_COL] == 0].sample(n=half, random_state=config.GLOBAL_SEED)
    # Interleave the two classes so the per-row table in the UI alternates
    # verdicts visibly rather than showing 50 of one and then 50 of the other.
    malware_paired = malware.reset_index(drop=True).assign(_pair=range(half))
    goodware_paired = goodware.reset_index(drop=True).assign(_pair=range(half))
    sample = (
        pd.concat([malware_paired, goodware_paired], ignore_index=True)
        .sort_values("_pair")
        .drop(columns=["_pair"])
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
    print(f"Sample composition: {(sample[config.LABEL_COL] == 1).sum()} malware, "
          f"{(sample[config.LABEL_COL] == 0).sum()} goodware, "
          f"{len(sample)} total")
    print(f"Columns ({len(sample.columns)}): {', '.join(sample.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
