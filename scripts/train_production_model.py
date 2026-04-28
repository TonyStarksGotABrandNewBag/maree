"""Train the M.A.R.E.E. production model and persist it for the Flask app.

Trains a M.A.R.E.E. ensemble (RF base by default — best AUC of the variants
in Phase E) on the FULL temporal-training portion and saves the fitted
ensemble plus a few demo samples drawn from the temporal hold-out.

Outputs (gitignored — re-create with `python scripts/train_production_model.py`):

    artifacts/maree_production.joblib       fitted MareeEnsemble
    artifacts/demo_samples.json             5 sample rows for the UI's
                                            "Try a demo sample" button
                                            (chosen from the temporal hold-out
                                            so they exhibit real drift)

Run from the repo root:
    .venv/bin/python scripts/train_production_model.py
"""

from __future__ import annotations

import json
import os
import sys

# Cap thread pools and avoid torch in the same process as gradient-boosting
# native libs (same pattern as src/run_one.py).
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import joblib
import numpy as np

from src import config
from src.data.loader import load_combined
from src.data.splits import temporal_density_split
from src.models.baselines import make_random_forest
from src.models.ensemble import MareeConfig, MareeEnsemble
from src.preprocessing import build_preprocessor

ARTIFACTS_DIR = config.PROJECT_ROOT / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = ARTIFACTS_DIR / "maree_production.joblib"
DEMO_PATH = ARTIFACTS_DIR / "demo_samples.json"


def main() -> int:
    print("Loading combined dataset…")
    df = load_combined()
    split = temporal_density_split(df)
    print(f"  {split.summary()}")

    print("\nFitting M.A.R.E.E. (RF base) on the temporal training portion…")
    cfg = MareeConfig(base_factory=make_random_forest)
    ensemble = MareeEnsemble(ensemble_config=cfg)
    ensemble.fit_from_dataframe(split.train, preprocessor_factory=build_preprocessor)
    print(f"  Active windows: {ensemble.n_active_}")
    print(f"  Per-window in-window accuracies: "
          f"{[f'{a:.3f}' for a in ensemble.in_window_accuracies_]}")

    print(f"\nSaving model to {MODEL_PATH}…")
    joblib.dump(ensemble, MODEL_PATH)
    size_mb = MODEL_PATH.stat().st_size / (1024 * 1024)
    print(f"  Wrote {MODEL_PATH} ({size_mb:.1f} MB)")

    print("\nSampling demo rows from temporal hold-out…")
    # Pick 3 likely-malicious + 2 likely-benign samples from the test set so the
    # UI's "Try a demo sample" picker exercises both decision paths.
    test = split.test.copy()
    rng = np.random.default_rng(config.GLOBAL_SEED)
    mw_pool = test[test[config.LABEL_COL] == 1]
    gw_pool = test[test[config.LABEL_COL] == 0]
    chosen_mw = mw_pool.sample(n=3, random_state=int(rng.integers(1, 10_000)))
    chosen_gw = gw_pool.sample(n=2, random_state=int(rng.integers(1, 10_000)))

    demo_rows = []
    for i, (_, row) in enumerate([*chosen_mw.iterrows(), *chosen_gw.iterrows()]):
        record: dict = {
            "demo_id": f"sample_{i+1}",
            "true_label": int(row[config.LABEL_COL]),
            "true_label_name": "malware" if int(row[config.LABEL_COL]) == 1 else "goodware",
        }
        # Persist all 27 raw schema columns + the engineering source columns
        # so the UI form can pre-fill the demo and the pipeline can preprocess.
        for col in (*config.RAW_NUMERIC_FEATURES, *config.STRING_FEATURE_SOURCES):
            if col in row:
                value = row[col]
                # Make JSON-serializable
                if hasattr(value, "item"):
                    value = value.item()
                record[col] = value
        demo_rows.append(record)

    DEMO_PATH.write_text(json.dumps(demo_rows, indent=2, default=str))
    print(f"  Wrote {DEMO_PATH} ({len(demo_rows)} samples)")

    print("\nDone. The Flask app loads these at startup; restart it after retraining.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
