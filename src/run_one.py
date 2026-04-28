"""Run a single (model, protocol, stage) combination in this process.

Designed to be invoked as a subprocess by src/train.py so that each native
library (PyTorch / XGBoost / LightGBM / CatBoost / sklearn) gets a fresh
Python interpreter and a clean OpenMP / BLAS load. Crashes in one model
no longer take down the whole run.

Usage:
    python -m src.run_one --model xgboost --protocol random --stage cv
    python -m src.run_one --model torch_mlp --protocol temporal --stage holdout

Writes results to results/parts/{stage}_{protocol}_{model}.json
"""

from __future__ import annotations

# Cap thread pools BEFORE importing any native ML libs.
import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "4")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "4")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# IMPORTANT: We intentionally do NOT eagerly import torch here.
# On macOS Apple Silicon, torch's bundled libomp.dylib conflicts with the
# libomp that XGBoost / LightGBM / CatBoost link against — importing torch
# in the same process as those libraries reliably segfaults (exit 139).
# Each subprocess gets a fresh interpreter, so we only import torch when
# the requested model actually needs it (model == "torch_mlp"). The
# argparse parse below decides which import path to take.

import argparse

_arg_parser = argparse.ArgumentParser()
_arg_parser.add_argument("--model", required=True)
_arg_parser.add_argument("--protocol", required=True, choices=["random", "temporal"])
_arg_parser.add_argument("--stage", required=True, choices=["cv", "holdout"])
_args, _ = _arg_parser.parse_known_args()

if _args.model == "torch_mlp":
    import torch  # noqa: F401  pylint: disable=unused-import

import json
from dataclasses import asdict

from src import config
from src.data.loader import load_combined
from src.data.splits import random_stratified_split, temporal_density_split
from src.models.advanced import ADVANCED_FACTORIES
from src.models.baselines import BASELINE_FACTORIES
from src.train import cv_for_protocol, hold_out_eval

ALL_FACTORIES = {**BASELINE_FACTORIES, **ADVANCED_FACTORIES}

PARTS_DIR = config.PROJECT_ROOT / "results" / "parts"
PARTS_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, choices=list(ALL_FACTORIES))
    p.add_argument("--protocol", required=True, choices=["random", "temporal"])
    p.add_argument("--stage", required=True, choices=["cv", "holdout"])
    args = p.parse_args()

    factory = {args.model: ALL_FACTORIES[args.model]}
    print(f"[{args.stage} {args.protocol}] {args.model}")

    df = load_combined()
    if args.protocol == "random":
        split = random_stratified_split(df)
    else:
        split = temporal_density_split(df)

    if args.stage == "cv":
        results = cv_for_protocol(split.train, args.protocol, factories=factory, verbose=True)
        records = [asdict(r) for r in results]
    else:  # holdout
        results = hold_out_eval(split, factories=factory, verbose=True)
        records = [asdict(r) for r in results]

    out = PARTS_DIR / f"{args.stage}_{args.protocol}_{args.model}.json"
    out.write_text(json.dumps(records, indent=2))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
