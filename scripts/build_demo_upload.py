"""Build the labeled demo CSV for the recorded video's `/upload` beat.

Emits the *full natural-distribution* random 80/20 hold-out — the
rubric's literal "20% hold-out test file" — as a single CSV the demo
presenter drags into the live upload form. The full hold-out gives
tight error bars on AUC and accuracy and is the same data the model
was scored against in the technical report. The resulting file
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
and confusion-matrix display on the rubric's literal hold-out.
"""

from __future__ import annotations

import os
from pathlib import Path

# Cap thread pools BEFORE importing native ML libs.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from src import config
from src.data.loader import load_combined
from src.data.splits import random_stratified_split

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

    # Restrict to the columns the upload pipeline expects: raw numerics,
    # string-feature sources, and Label. The internal SAMPLE_DATE_COL is
    # dropped because the production /upload doesn't need it.
    keep_cols = (
        list(config.RAW_NUMERIC_FEATURES)
        + list(config.STRING_FEATURE_SOURCES)
        + [config.LABEL_COL]
    )
    sample = test[keep_cols]

    DRIVE_DIR.mkdir(parents=True, exist_ok=True)
    sample.to_csv(DRIVE_PATH, index=False)
    sample.to_csv(LOCAL_BACKUP, index=False)

    print(f"\nWrote {DRIVE_PATH} ({DRIVE_PATH.stat().st_size:,} bytes)")
    print(f"Wrote {LOCAL_BACKUP} ({LOCAL_BACKUP.stat().st_size:,} bytes)")
    n_malware = int((sample[config.LABEL_COL] == 1).sum())
    n_goodware = int((sample[config.LABEL_COL] == 0).sum())
    print(
        f"Sample composition: {n_malware:,} malware, "
        f"{n_goodware:,} goodware, {len(sample):,} total "
        f"(natural class ratio {n_malware / len(sample):.1%} malware)"
    )
    print(f"Columns ({len(sample.columns)}): {', '.join(sample.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
