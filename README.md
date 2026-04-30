# M.A.R.E.E.

**M**ulti-classifier **A**daptive **R**ecognition, **E**xplainable **E**ngine

An open-source malware classifier for Windows Portable Executable files that does what current classifiers don't: it measures its own degradation as the threat landscape evolves, blocks files by default when uncertain, and explains every verdict in language an IT administrator can act on.

This repository is the Quantic MSSE capstone of Kenny Gordon and Wyatt [TBD], built on the Brazilian Malware Dataset (Ceschin et al., 2018) using the strict temporal evaluation methodology of Pendlebury et al. (TESSERACT, USENIX Security 2019).

## What's broken about today's malware classifiers

Every published malware classifier degrades silently in production. Researchers evaluate on randomly-shuffled train/test splits, which produce optimistic accuracy numbers (~0.97 AUC). Under honest temporal splits — train on data from before time T, evaluate on data from after T — the same classifiers collapse to ~0.65 AUC within a six-month evaluation horizon. The vendor blogs say "97% accuracy." The deployed reality is closer to a coin flip on novel families.

The industry retrains. The industry does not measure, does not surface uncertainty, does not maintain principled diversity, and does not trigger retraining adaptively. Between retraining cycles — which is most of the time — every deployed classifier is silently degrading and nobody can quantify by how much.

## What M.A.R.E.E. does differently

| Feature | What it means |
|---|---|
| **Multi-classifier ensemble** | A council of classifiers, each trained on a different temporal window, voting on each prediction |
| **Adaptive** | Per-model accuracy tracking, distribution-shift detection, ensemble-disagreement signals — automatic drift-driven retraining triggers |
| **Recognition** | Binary malware/goodware classification on Portable Executable static features |
| **Explainable** | Each verdict comes with an LLM-grounded MITRE ATT&CK explanation an IT administrator can act on |
| **Engine** | Production-grade Flask application, Docker self-host, free public hosted instance |

The decision logic is zero-trust:

```
Ensemble decision           →   System action
─────────────────────────────────────────────
HIGH-CONFIDENCE BENIGN          ALLOW
HIGH-CONFIDENCE MALWARE         BLOCK + LLM triage
LOW-CONFIDENCE (any direction)  BLOCK + LLM uncertainty explanation
```

The ensemble has to *affirmatively* allow. Silence, disagreement, and low confidence all yield the same answer: block.

## Why this matters

Today's IT administrator running Microsoft Defender at a school district sees one signal: "Defender is enabled. ✓". They cannot see how badly the classifier is degrading. They cannot see how confident the model is on any given file. They cannot see what to do when an alert fires.

M.A.R.E.E. surfaces all three. The drift indicator is on the wall. The confidence is on every prediction. The triage explanation is on every block. This is what defense looks like when the operator is treated as a partner instead of a passive consumer of "yes" / "no" verdicts.

## Project status

🟢 **Live:** https://maree-f8c8.onrender.com — CI/CD-gated deploy from `main`, end-to-end verified against the 5 published demo samples (5/5 correct verdicts; full prediction → triage round-trips). See `deployed.md` for the pipeline architecture.

Capstone submission for Quantic MSSE targeted for [submission date TBD]. See `ROADMAP.md` for the multi-year plan beyond the capstone.

## Companion artifact (Phase 2)

The reusable temporal evaluation framework — `temporal-malware-bench` — is planned as a Phase 2 (post-capstone) extraction so other researchers can apply the Pendlebury methodology to their own datasets and models. It is not part of the capstone submission. The current capstone ships M.A.R.E.E. itself; the abstraction follows once the methodology is field-tested. See `ROADMAP.md`.

## Getting started

See `docs/for-it-administrators.md` for the IT-admin deployment guide. See `docs/honest-evaluation.md` for the methodology explainer. See `evaluation-and-design.md` for the full technical report.

## Acknowledgments

Named in honor of Mary Jackson — NASA mathematician, aerospace engineer, and the woman who broke the engineering education system that excluded her so that a generation of Black women could enter it. M.A.R.E.E. carries her echo because the work she stood for — accessible, dependable, foundational — is what we want this tool to embody.

## License

MIT. See `LICENSE`.
