# Roadmap

M.A.R.E.E. is the load-bearing first stone of a multi-year research program on adversarially-robust, drift-aware, federated malware defense. The capstone is Phase 1; the broader program plays out over years 1-5.

## Phase 1 — Capstone (now → submission)

The deliverable described in `README.md`: drift-adaptive ensemble classifier on the Brazilian Malware Dataset, evaluated under strict temporal splits (Pendlebury et al., USENIX 2019), with LLM-grounded triage layer, block-by-default failure mode, free hosted version, and CI/CD-gated deployment. Plus the companion `temporal-malware-bench` package.

## Phase 2 — Year 1 (post-capstone, months 2-12)

- Submit drift-adaptive paper to **AISec** (co-located with CCS) or **DLS** (co-located with IEEE S&P).
- Extract `temporal-malware-bench` as a standalone package: density-aware temporal splits, drift-gap metric harness, and the Pendlebury-vs-random comparison protocol generalized off the Brazilian dataset so other researchers can apply the methodology to their own corpora.
- Extend M.A.R.E.E. to additional file formats: Office documents (`.docx`, `.xlsx` with macros), PDFs.
- First non-Quantic deployment: pilot at a friendly nonprofit / school district.
- Publish blog series on degradation findings.

## Phase 3 — Year 2

- **Diverse-ensemble approximation of mixed-strategy defense**. Convert the deterministic ensemble into a mixed-strategy approximation following Pang et al. 2021 lineage. Lifts the formal game-theoretic framing from existence-only to constructive.
- **Federated drift adaptation across multiple organizations**. Differential-privacy gradient sharing protocol; first cross-node detection paper.
- Memory-forensic runtime layer (CIC-MalMem-2022 + thin sensor agent).

## Phase 4 — Years 3-5

- **K-means++-style initialization guarantees for adversarial training in non-convex games**. Theoretical contribution targeting top-tier venue (USENIX Security, NDSS, IEEE S&P).
- Mary Protocol consortium formalization. Multi-organization governance, shared infrastructure.
- Mary Protocol referenced in NIST / CISA guidance.

## Why this trajectory

Each phase builds on the previous. The capstone produces a working defender; Year 1 makes it broadly useful; Year 2 makes the field fundamentally different by changing the game's structural rules; Years 3-5 make the contributions theoretically defensible and institutionally adopted.

The capstone is not trying to be the whole vision. It is trying to be the foundation that makes the whole vision possible.
