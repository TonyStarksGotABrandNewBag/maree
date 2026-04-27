# Evaluation and Design

This document captures the technical report for the M.A.R.E.E. capstone:
dataset choices, design decisions, preprocessing, model selection,
cross-validation results, hold-out evaluation, and ablations.

It is currently a stub. Sections will be populated as each phase of the
build completes.

---

## 1. Dataset

**Source:** Brazilian Malware Dataset (Ceschin et al., IEEE S&P 2018).
**Why this dataset:** purpose-built for temporal evaluation. Daily granularity
across multiple years. Documented by an author who is a recognized researcher
on concept drift in malware classification.

[Phase B (Week 1) findings to follow.]

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
