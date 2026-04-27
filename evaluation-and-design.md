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

**Random split (rubric baseline):** stratified 80/20 train / hold-out.
**Temporal split (our differentiator):** strict pre-T / post-T per Pendlebury et al. (TESSERACT, USENIX Security 2019).

We report results under BOTH protocols, side by side. The asymmetry IS the headline finding.

[Phase C (Week 2) details to follow.]

## 3. Preprocessing

[Phase C (Week 2) — to follow.]

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
