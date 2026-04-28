# Evaluation and Design

This document captures the technical report for the M.A.R.E.E. capstone:
dataset choices, design decisions, preprocessing, model selection,
cross-validation results, hold-out evaluation, and ablations.

It is currently a stub. Sections will be populated as each phase of the
build completes.

---

## 1. Dataset

**Source:** Brazilian Malware Dataset (Ceschin et al., IEEE S&P 2018) — https://github.com/fabriciojoc/brazilian-malware-dataset

**Why this dataset:** purpose-built for temporal evaluation. Daily granularity across multiple years. Documented by an author who is a recognized researcher on concept drift in malware classification.

### 1.1 Scale

| Metric | Value |
|---|---|
| Total malware samples | **30,046** |
| Total goodware samples | **21,116** |
| Combined sample count | **51,162** |
| Class balance | 58.7% malware / 41.3% goodware |
| Time span | **2013-01-01 → 2020-11-29** (~7.9 years) |
| Daily malware files | 2,797 (1,501 are empty placeholders) |

The total of 51,162 samples aligns with the Quantic PDF's "approximately 50,000 instances" specification.

### 1.2 Per-year malware distribution

The dataset is heavily front-loaded: 2013 contributed 33% of all malware samples; 2020 contributed less than 1%.

| Year | Days covered | Empty days | Malware samples | % empty days |
|---|---|---|---|---|
| 2013 | 365 | 119 | 10,078 | 32.6% |
| 2014 | 365 | 122 | 8,690 | 33.4% |
| 2015 | 365 | 135 | 6,466 | 37.0% |
| 2016 | 366 | 291 | 822 | 79.5% |
| 2017 | 365 | 147 | 2,885 | 40.3% |
| 2018 | 282 | 201 | 307 | 71.3% |
| 2019 | 359 | 229 | 519 | 63.8% |
| 2020 | 330 | 257 | 279 | 77.9% |

**Methodological implication:** temporal splits must account for sample-density variation across years. We cannot simply split at a year boundary — early-year windows have orders of magnitude more samples than late-year windows. We will use **density-aware quarter or month boundaries** rather than fixed-size windows.

### 1.3 Schema reconciliation with Quantic spec

The dataset has no explicit `Label` column — class is encoded by file location. We construct the label: `1` for samples from `malware-by-day/`, `0` for samples from `goodware.csv`.

After dropping non-feature identifier columns (`MD5`, `SHA1`, `Name`, `Fuzzy`), the intersection of malware/goodware schemas is **exactly 27 columns** — matching the Quantic PDF's "27 input attributes" specification precisely.

| Feature class | Count | Examples |
|---|---|---|
| Numeric (raw) | 22 | `BaseOfCode`, `Entropy`, `SizeOfImage`, `Characteristics`, `TimeDateStamp`, ... |
| String (engineered downstream) | 4 | `ImportedDlls`, `ImportedSymbols`, `Identify`, `FormatedTimeDateStamp` |
| Constructed label | 1 | `Label` ∈ {0, 1} |

3 of the 22 numeric features are near-zero variance (`Magic`, `PE_TYPE`, `SizeOfOptionalHeader` are constants in this dataset) and will be dropped. The 19 retained numeric features are augmented by 8 engineered features from string columns (DLL counts, dangerous-API flags, packer detection, etc.) to land at the rubric's 27-feature target. See `docs/feature-inventory.md` for the full mapping.

### 1.4 Temporal positioning of goodware — known limitation

For Pendlebury-style temporal evaluation, every sample needs a known collection date.

- **Malware** has a high-confidence per-sample collection date (the file basename: `2013-01-02.csv` means all rows in that file were collected 2013-01-02).
- **Goodware** has no per-sample collection date. The only available temporal signal is `FormatedTimeDateStamp`, the PE-embedded compile timestamp. We confirmed this field is **unreliable in this dataset** — values range from 1969-12-31 to 2100-02-26, well outside any plausible collection window. PE timestamps are routinely forged or zeroed.

**Decision:** for temporal evaluation, we treat goodware as bootstrapped uniformly across each train/test window. This is the standard treatment in the Pendlebury and CADE literature when one class lacks per-sample timestamps. The drift signal therefore comes principally from the malware distribution, which is methodologically appropriate: in production, drift is dominated by attacker evolution, not by the goodware corpus rotating.

### 1.5 Reproducibility

Acquisition is one command: `python scripts/download_data.py`. EDA is reproducible via `notebooks/02_eda.py` (per-day, per-month counts) and `notebooks/03_features.py` (feature inventory, missingness, distributions). All EDA artifacts are written to `notebooks/eda_outputs/` for inspection.

## 2. Train / validation / test protocol

We evaluate every classifier under TWO split protocols, side by side. The asymmetry between them is the headline finding of the entire capstone (Pendlebury et al., USENIX Security 2019, established that this asymmetry is large and that almost no published malware classifier reports it honestly).

### 2.1 Random stratified split — the rubric baseline

- 80% train / 20% hold-out test, stratified on `Label`.
- `random_state=42` (`config.SPLIT_SEED`) for reproducibility.
- Within the training portion, 10-fold stratified cross-validation per the Quantic PDF (Step 4).
- Implementation: `src.data.splits.random_stratified_split()`.

This is the protocol the Quantic rubric expects. We report results under it for every model so the rubric is satisfied directly.

### 2.2 Density-aware temporal split — M.A.R.E.E.'s rigor differentiator

The naïve temporal split would be "train on everything before year T, test on everything after." That fails on this dataset because per-year malware density varies 36×: 10,078 malware samples in 2013 vs 279 in 2020. Splitting at any calendar boundary in the early years puts almost all data on the train side and produces a tiny test set. Splitting at any boundary in the late years puts almost all data on the test side.

**Density-aware temporal split**: choose the cutoff date such that exactly the newest 20% of malware *by sample count* falls after the cutoff. This guarantees:

- Strict no-look-ahead for malware (the methodologically critical class).
- Both folds have meaningful malware sample sizes despite year imbalance.
- The cutoff date emerges from the data, not from an a priori calendar choice.

For our dataset, the cutoff lands on **2015-09-15** — the train window covers 2013-2015 H1 with the highest-density years, the test window covers 2015 H2 → 2020-11-10 with five+ years of unseen drift.

- Implementation: `src.data.splits.temporal_density_split()`.
- Goodware is randomly partitioned in the same 80/20 ratio, since it lacks per-sample collection timestamps (see §1.4). Drift is therefore measured as malware-driven, which is methodologically appropriate and matches CADE/Pendlebury practice when one class lacks reliable timestamps.

### 2.3 Window-quantile cutoffs for the M.A.R.E.E. ensemble

The drift-adaptive ensemble trains one base classifier per temporal window. We use density-quantile cutoffs (each window contains ~equal malware sample count) rather than equal-calendar-duration windows, again because of the 36× density variation.

- Implementation: `src.data.splits.temporal_window_quantiles()`.
- Default `n_windows=5`, but tunable.
- For the M.A.R.E.E. ensemble in Phase E, window cutoffs are computed on the *training portion only* — never on the held-out test set — to maintain strict no-look-ahead.

## 3. Preprocessing

The preprocessing pipeline (`src/preprocessing.py`) is a single sklearn `Pipeline` with two stages:

1. **`engineer`** — `FunctionTransformer(engineer_string_features)` turns the 4 string source columns into 8 engineered numeric features (count of imported DLLs, dangerous-API flag, packer detection from `Identify`, PE-timestamp anomaly flag, etc.). See `docs/feature-inventory.md` for the full mapping.
2. **`columns`** — a `ColumnTransformer` that:
   - Splits the 27 numeric features into "log-then-scale" (size/count features that span 9+ orders of magnitude — `Size` ranges from 2,560 to 3,986,103,808 bytes) and "just scale" (everything else).
   - Each branch: `SimpleImputer(strategy="median")` → optional `log1p` → `StandardScaler`.
   - `remainder="drop"` ensures only the 27 known features survive.

### 3.1 Critical methodological discipline: fit-on-train-only

Per the Quantic PDF (Step 5):
> *Preprocessing steps must be fit only on training folds during cross-validation, and then applied to the corresponding validation/test folds.*

This is enforced two ways:
- The factory `build_preprocessor()` returns a fresh, unfitted pipeline. The caller is responsible for `fit_transform(train)` then `transform(test)` — never `fit_transform(test)`.
- A unit test (`tests/test_preprocessing.py::test_train_only_fit_then_transform_test`) verifies that test-set means and stds deviate from training's (mean≈0, std≈1) — the fingerprint of a correctly-fit-on-train-only scaler.

End-to-end smoke test on the real dataset confirms zero NaN/Inf in either fold's transformed output.

### 3.2 Verified output

A full end-to-end run on the real Brazilian dataset (50,758 rows) produces:

| | Train | Test |
|---|---|---|
| Rows | 40,601 | 10,157 |
| Output columns | 27 | 27 |
| Mean (first 5 cols) | ≈ 0 | -0.13, 0.06, 0.04, -0.03, -0.01 |
| Std (first 5 cols) | ≈ 1 | 0.83, 1.10, 0.97, 0.00, 0.98 |
| NaN/Inf count | 0 | 0 |

The test-fold mean/std deviation from train's centered/scaled distribution is the empirical proof of fit-on-train-only discipline.

## 4. Cross-validation results

[Phase D (Week 3) — to follow. Will include CV table with mean ± std AUC and accuracy under both random and temporal splits, for all 7 model architectures.]

## 5. The drift-adaptive ensemble (M.A.R.E.E.)

[Phase E (Weeks 4-5) — to follow. Method description, hyperparameter choices, ablations.]

## 6. Hold-out test results

[Phase E (Week 5) — to follow.]

## 7. Block-by-default decision logic

Three-state output: ALLOW / BLOCK-malware / BLOCK-uncertain. Rationale and threshold tuning to follow.

## 8. LLM triage layer

[Phase F (Week 6) — to follow.]

## 9. Limitations

[To be enumerated honestly as the build progresses.]

## References

- Pendlebury et al., "TESSERACT: Eliminating Experimental Bias in Malware Classification across Space and Time," USENIX Security 2019.
- Ceschin et al., "The Need for Speed: An Analysis of Brazilian Malware Classifiers," IEEE Security & Privacy 2018.
- Madry et al., "Towards Deep Learning Models Resistant to Adversarial Attacks," ICLR 2018.
- Pierazzi et al., "Intriguing Properties of Adversarial ML Attacks in the Problem Space," IEEE S&P 2020.
- Cohen, Rosenfeld, Kolter, "Certified Adversarial Robustness via Randomized Smoothing," ICML 2019.
- Pang et al., "Improving Adversarial Robustness via Promoting Ensemble Diversity," 2021.
