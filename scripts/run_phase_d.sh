#!/usr/bin/env bash
#
# Phase D — runs every (model, protocol, stage) in its own Python subprocess
# so that a crash in one model does not kill the whole experiment.
#
# Each invocation writes to results/parts/{stage}_{protocol}_{model}.json
# Idempotent: skips combinations whose part-file already exists.
#
# Usage:
#   ./scripts/run_phase_d.sh
#
# Then assemble:
#   .venv/bin/python -m src.eval

set -u

cd "$(dirname "$0")/.."

PYTHON=".venv/bin/python"
LOG="results/run.log"
mkdir -p results/parts
: > "$LOG"   # truncate log

MODELS=(logistic_regression decision_tree random_forest torch_mlp xgboost lightgbm catboost)
PROTOCOLS=(random temporal)
STAGES=(cv holdout)

ok=0
fail=0
skip=0

for model in "${MODELS[@]}"; do
  for protocol in "${PROTOCOLS[@]}"; do
    for stage in "${STAGES[@]}"; do
      out="results/parts/${stage}_${protocol}_${model}.json"
      if [ -f "$out" ]; then
        echo "SKIP: $out exists" | tee -a "$LOG"
        skip=$((skip+1))
        continue
      fi
      echo "================================================================" | tee -a "$LOG"
      echo "RUN : stage=$stage protocol=$protocol model=$model" | tee -a "$LOG"
      echo "================================================================" | tee -a "$LOG"
      if PYTHONUNBUFFERED=1 "$PYTHON" -u -m src.run_one \
            --model "$model" --protocol "$protocol" --stage "$stage" 2>&1 | tee -a "$LOG"; then
        # Confirm the part file was written
        if [ -f "$out" ]; then
          echo "OK  : $out" | tee -a "$LOG"
          ok=$((ok+1))
        else
          echo "FAIL: $model/$protocol/$stage exited 0 but no part file" | tee -a "$LOG"
          fail=$((fail+1))
        fi
      else
        rc=$?
        echo "FAIL: $model/$protocol/$stage exited $rc" | tee -a "$LOG"
        fail=$((fail+1))
      fi
    done
  done
done

echo "" | tee -a "$LOG"
echo "Phase D summary: ok=$ok fail=$fail skip=$skip" | tee -a "$LOG"
exit 0
