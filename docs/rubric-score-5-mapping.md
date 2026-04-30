# Quantic Score-5 rubric mapping

This document maps every rubric requirement annotated in the codebase to the deliverable that satisfies it. It is the reviewer's checklist: walk down the table, click each link, verify each row.

The rubric markers come from the Quantic capstone PDF (referenced in `src/preprocessing.py`, `src/models/baselines.py`, `src/models/advanced.py`, `src/features.py`, `src/data/splits.py`, `src/config.py`, and `deployed.md`).

> **Status flags in this document:**
> - ✅ = met and verified
> - ⚠️ = met but with a documented limitation (see `evaluation-and-design.md` §9)
> - ⏳ = open metadata placeholder (does not affect rubric score; flagged for the human author)

---

## 1. Dataset and feature scope

| Rubric requirement | Where the spec lives | Where we satisfy it | Status |
|---|---|---|---|
| Approximately 50,000 instances | Quantic PDF | `evaluation-and-design.md` §1.1 — final corpus is **51,162 samples** after schema reconciliation | ✅ |
| 27 input attributes | Quantic PDF; `src/features.py` line 5 | `src/config.py:86` — `FEATURE_COLUMNS = RAW_NUMERIC_FEATURES + ENGINEERED_FEATURES` is exactly 27 (19 raw + 8 engineered). Full mapping in `docs/feature-inventory.md` | ✅ |
| Reproducibility (fixed random seed) | Quantic PDF | `src/config.py:23` — `GLOBAL_SEED = 42`. Every stochastic step (split, CV, model factories) reads from `config.GLOBAL_SEED` / `SPLIT_SEED` / `CV_SEED` | ✅ |
| Single-command data acquisition | Quantic PDF (reproducibility) | `python scripts/download_data.py` clones the Brazilian Malware Dataset from its canonical GitHub source | ✅ |

## 2. Train/test split (Step 4)

| Rubric requirement | Where the spec lives | Where we satisfy it | Status |
|---|---|---|---|
| 80/20 stratified hold-out | Quantic PDF, Step 4 | `src/config.py:91` — `RANDOM_TEST_FRACTION = 0.20`. Implementation: `src/data/splits.py:random_stratified_split()` | ✅ |
| 10-fold stratified cross-validation on the training portion | Quantic PDF, Step 4 | `src/config.py:93` — `CV_FOLDS = 10`. Implementation: `src/train.py:cross_validate()` (StratifiedKFold with `random_state=config.CV_SEED`) | ✅ |
| Per-fold metrics reported | Quantic PDF, Step 4 | `evaluation-and-design.md` §4.4 — full per-(model × protocol) CV table with AUC mean ± std and accuracy mean ± std across all 10 folds | ✅ |

## 3. Preprocessing (Step 5)

| Rubric requirement | Where the spec lives | Where we satisfy it | Status |
|---|---|---|---|
| Apply scaling, encoding, imputation as needed | Quantic PDF, Step 5 (per `src/preprocessing.py:3-9`) | `src/preprocessing.py:build_preprocessor()` — `SimpleImputer(strategy="median")` → optional `log1p` for heavy-tailed size features → `StandardScaler`. Two parallel branches: log-then-scale (size/count features spanning 9+ orders of magnitude) and just-scale (everything else) | ✅ |
| Transformations fit on **training** only | Quantic PDF, Step 5 (verbatim quote in `src/preprocessing.py:5-8`) | `src/preprocessing.py:build_preprocessor()` returns a fresh, unfitted pipeline. The caller is responsible for `fit_transform(train)` then `transform(test)`. Discipline is enforced by unit test `tests/test_preprocessing.py:test_train_only_fit_then_transform_test` (verifies test-fold mean/std deviate from train's centered/scaled distribution — the empirical fingerprint of fit-on-train-only) | ✅ |
| Verified end-to-end on the real dataset | Implicit reproducibility expectation | `evaluation-and-design.md` §3.2 — train fold mean ≈ 0 / std ≈ 1; test fold deviates as expected; **0 NaN/Inf** in either fold | ✅ |

## 4. Models (Step 6)

| Rubric requirement | Where the spec lives | Where we satisfy it | Status |
|---|---|---|---|
| Four baseline classifiers | Quantic PDF, Step 6 (per `src/models/baselines.py:1-6`) | `src/models/baselines.py` — `make_logistic_regression()`, `make_decision_tree()`, `make_random_forest()`, `TorchMLPClassifier` (PyTorch MLP wrapped in sklearn-compatible interface) | ✅ |
| At least 3 additional high-performing models | Quantic PDF, Step 6 (per `src/models/advanced.py:3-7`) | `src/models/advanced.py` — `make_xgboost()`, `make_lightgbm()`, `make_catboost()` — three additional models | ✅ |
| Spanning at least 2 algorithm families | Quantic PDF, Step 6 | XGBoost (level-wise gradient boosting), LightGBM (leaf-wise gradient boosting), CatBoost (symmetric oblivious-tree boosting) — three distinct splitting algorithms within the gradient-boosting family. Combined with the four baselines, the full model panel covers: linear (LR), single-tree (DT), bagging (RF), neural (MLP), and three GBM families. Five distinct algorithm families total | ✅ |
| All models evaluated under the same protocol | Implicit | `evaluation-and-design.md` §4.1 / §4.4 — every one of the 7 models reports CV AUC, hold-out AUC, CV accuracy, hold-out accuracy under both protocols (random + temporal). 28 (model × protocol × stage) combinations total | ✅ |

## 5. Reporting and metrics

| Rubric requirement | Where the spec lives | Where we satisfy it | Status |
|---|---|---|---|
| AUC reported | Quantic PDF | `evaluation-and-design.md` §4.1, §4.4, §6 — every model | ✅ |
| Accuracy reported | Quantic PDF | Same — every model. We report accuracy *at the standard 0.5 threshold* (the calibration-sensitive metric) | ✅ |
| Confusion matrix | Quantic PDF | `evaluation-and-design.md` §6 — for the M.A.R.E.E. variants on the temporal hold-out (allowed/blocked-malware/blocked-uncertain breakdown plus the binary-decision confusion). The `/upload` endpoint also computes confusion matrices for any uploaded labeled CSV at runtime (`src/app/server.py:upload`) | ✅ |
| Cross-validated metrics with mean ± std | Quantic PDF, Step 4 | `evaluation-and-design.md` §4.4 — every (model × protocol) cell shows mean ± std across the 10 folds | ✅ |

## 6. CI/CD and deployment (Score 5 specific)

| Rubric requirement | Where the spec lives | Where we satisfy it | Status |
|---|---|---|---|
| Working Flask web app | Quantic PDF | `src/app/server.py` — Flask app with 7 routes (`/`, `/demo`, `/predict`, `/upload`, `/api/predict`, `/health`, plus static). Live at https://maree-f8c8.onrender.com | ✅ |
| Deployment to a publicly-accessible URL | Quantic PDF | Render Blueprint deployment (`render.yaml`) — service `maree-f8c8` serves at https://maree-f8c8.onrender.com. Verified end-to-end (5/5 demo samples produce correct verdicts via `/api/predict`) — see `deployed.md` "Live status" table | ✅ |
| **CI/CD pipeline that gates deploy on tests** ("deploy must occur if and only if tests pass" — Score 5) | Quantic PDF; `deployed.md:44-45` | `.github/workflows/ci.yml` — `deploy` job depends on `lint`, `test`, `test-torch`, AND `train-and-release`. `render.yaml` has `autoDeploy: false`, so Render only deploys when CI explicitly fires the hook (no path for "deploy without passing tests"). Verified by the entire deployment-debugging trail captured in commit history | ✅ |
| Reproducible training pipeline | Quantic PDF | `scripts/train_production_model.py` runs end-to-end on the GitHub-hosted runner during the `train-and-release` CI job; published artifact (`maree_production.joblib` + `demo_samples.json`) is the `model-latest` GitHub Release. Same script runs locally identically because seeds are fixed | ✅ |
| Test suite | Quantic PDF (implicit) | 14 test files in `tests/` covering features, preprocessing, splits, ensembles, models (CPU + torch), drift detector, triage, and the Flask app. Currently 133 non-torch tests + 4 torch tests, all green in the latest CI run | ✅ |

## 7. AI-tooling acknowledgment

| Quantic policy | Where we satisfy it | Status |
|---|---|---|
| AI tooling disclosure (Quantic plagiarism policy) | `ai-tooling.md` — primary collaborator (Claude / Anthropic) named, contribution patterns enumerated (code generation, design discussions, documentation drafts) | ⚠️ "What worked well" / "What didn't work as well" subsections are empty — should be filled with one paragraph each before submission. The acknowledgment itself is present and policy-compliant. |

## 8. Above-the-floor contributions (not strictly required by rubric)

The following are *contributions beyond what the rubric asks for*. They are what distinguishes this submission from "a malware classifier that meets the rubric":

| Contribution | Where it lives | Why it matters |
|---|---|---|
| Density-aware temporal split (Pendlebury / TESSERACT methodology) | `src/data/splits.py:temporal_density_split()`; `evaluation-and-design.md` §2.2 | Surfaces the drift-gap honest evaluators report and most published classifiers hide |
| Drift-gap measurement on every model | `evaluation-and-design.md` §4.1 (AUC); §4.2.1 (accuracy at threshold) | The headline empirical finding: 23–33pp accuracy collapse under temporal split for every gradient-boosting model |
| Drift-adaptive ensemble (M.A.R.E.E.) with per-window calibration | `src/models/ensemble.py`; `evaluation-and-design.md` §5–§6 | Recovers temporal-hold-out accuracy from 0.656 (RF baseline) to 0.875 (M.A.R.E.E. + block-by-default) |
| Block-by-default decision logic | `src/models/ensemble.py` — `MareePrediction` verdicts; `evaluation-and-design.md` §7 | Three verdicts (`ALLOWED`, `BLOCKED_MALWARE`, `BLOCKED_UNCERTAIN`) — fail-closed defaults aligned with OWASP / NIST SP 800-160 / CISA Secure-by-Design |
| Operator-visible drift indicator | `src/app/server.py:_drift_status` — banner on every page | The classifier surfaces its own degradation in real time; per-window calibrated accuracies visible to the IT-admin |
| LLM-grounded MITRE ATT&CK triage | `src/triage.py` — two backends (deterministic template + Claude Haiku 4.5), `ATTACK_MAPPING` hand-curated, "never invent technique IDs" constraint | Operator gets actionable IR steps + technique IDs on every blocked file |
| Operator-facing documentation | `docs/for-it-administrators.md`, `docs/honest-evaluation.md` | Translates the technical work into plain-language IT-admin and methodology guides |
| Honest §9 limitations | `evaluation-and-design.md` §9 | 13 enumerated limitations covering dataset, model, triage, operational, and companion-artifact gaps |

## 9. Open metadata placeholders (not rubric-blocking)

| Placeholder | Where | Status |
|---|---|---|
| `Wyatt [TBD]` co-author full last name | `README.md:7`, `LICENSE:3`, `ai-tooling.md:19` | ⏳ Author to resolve before submission. Does not affect rubric score; affects authorship attribution. |
| `[submission date TBD]` | `README.md:47` | ⏳ Author to fill once Quantic confirms the deadline window. Cosmetic; does not affect rubric score. |
| `ai-tooling.md` "What worked well" / "What didn't work as well" | `ai-tooling.md:11`, `ai-tooling.md:15` | ⏳ One paragraph each; honest reflective accounting. Recommended before submission for policy completeness. |

## 10. Verdict

Every rubric-floor requirement is met and verified. Every "Score 5" specifier (CI/CD-gated deploy, reproducibility, full model panel, honest evaluation reporting) is met and verified. The above-the-floor contributions in §8 are the substantive distinguishers.

The only items remaining before submission are the three ⏳ metadata placeholders in §9 — none of which affect the rubric score.
