# M.A.R.E.E. — subject-matter-expert brief

*Purpose.* Internal study guide for the M.A.R.E.E. capstone authors before the demo recording or any faculty defense.

*Method.* Each chapter opens with the load-bearing definition or distinction. Subsequent sentences apply, justify, or differentiate from it. Recall is reconstruction from the framework, not memorisation of separate facts.

---

## 1. Two metrics. Two failure modes.

*AUC* measures **ranking**: the probability that a randomly-chosen malware sample is scored higher than a randomly-chosen goodware sample. It is invariant to absolute score values; only relative ordering matters.

*Accuracy at threshold* measures **calibration**: the fraction of samples whose scores fall on the correct side of a fixed decision boundary, conventionally 0.5. It depends entirely on absolute score values.

Under distribution drift, the two metrics fail at different rates. Ranking is robust: a model that learned which features indicate maliciousness retains that knowledge as the threat distribution shifts; samples more malicious than baseline still score higher than samples that are not. Calibration is brittle: the score distribution itself shifts, so the 0.5 threshold the model was trained against no longer marks the actual decision boundary. The model ranks correctly and classifies wrongly.

This distinction organises the entire project. Pendlebury et al. ("TESSERACT", USENIX Security 2019) demonstrated it empirically across published malware classifiers; the random-shuffle protocol preserves calibration by construction and hides the failure, while the temporal-shuffle protocol exposes it. Industry practice reports the former. Deployed reality is the latter. M.A.R.E.E. is engineered around the gap between the two — recovering calibration that drift breaks, and refusing to act on probabilities that cannot be trusted.

## 2. The drift gap

*Drift gap*: the difference between random-protocol metrics and temporal-protocol metrics on the same model and dataset.

The random protocol shuffles samples, takes 80% for training and 20% for hold-out testing. Train and test are independent and identically distributed by construction; calibration is preserved. The temporal protocol orders samples by collection date, trains on those before some cutoff, tests on those after; train and test are not identically distributed, and calibration is not preserved.

On Random Forest applied to this dataset, AUC drops 0.04 (from 0.9975 random-CV to 0.9602 temporal hold-out); threshold accuracy drops 0.33 (from 0.9833 to 0.6557). The same pattern holds across the gradient-boosting trio (XGBoost, LightGBM, CatBoost): all collapse from ~0.99 random-protocol accuracy to 0.75–0.77 temporal. Logistic Regression is gentlest because its linear decision boundary is nearly invariant to specific feature values; PyTorch MLP is nearly as gentle because regularisation smooths the boundary. Tree-based models suffer most because they encode specific feature splits that change as malware evolves.

Our AUC drift gap (0.04–0.10 across the panel) is smaller than Pendlebury's (~0.32). Three reasons. *Dataset gentleness*: the Brazilian corpus's late-period samples are heavily family-recurrences of earlier malware, not novel families, so the test-time distribution does not diverge as sharply. *Goodware bootstrapping*: this corpus's goodware lacks reliable per-sample timestamps, so we bootstrap goodware uniformly across temporal folds; AUC mixes both classes, and the in-distribution goodware portion anchors AUC upward. *AUC's coarseness*: AUC is a coarse drift metric — Pendlebury also reports F1-malware and per-class precision-at-k, both of which expose larger gaps. Our threshold-accuracy collapse (0.23–0.33pp) is closer in spirit to his AUC drop than our AUC drop is.

The rubric asks for AUC plus accuracy. We report both because the contrast — small AUC drop, large accuracy drop — is the project's empirical headline.

## 3. Dataset structure as constraint

One demographic fact about the corpus drives much of the methodology: per-year malware sample density varies thirty-six-fold across the seven-and-a-half-year span (10,078 samples in 2013, fewer than 300 in 2020). Early years are abundant; late years are sparse. Four consequences follow.

*Calendar splits are unusable.* Splitting at a boundary in the early years places almost all malware on the train side and produces a tiny test set; splitting in the late years produces the opposite. The cutoff is therefore chosen by sample-count quantile rather than calendar date: the newest 20% of malware *by count* falls after the cutoff, which lands on 2015-09-15. Train covers 2013 through 2015 H1; test covers 2015 H2 through 2020-11-29.

*Density-quantile windowing.* M.A.R.E.E.'s five ensemble windows are partitioned by the same method, so each window contains roughly equal malware sample count rather than equal calendar duration.

*Goodware bootstrapping.* The PE-embedded `FormatedTimeDateStamp` field shows values from 1969 to 2100, routinely forged or zeroed; goodware on this corpus has no reliable per-sample collection timestamp. Goodware is therefore bootstrapped uniformly across temporal folds, the standard CADE/Pendlebury practice when one class lacks timestamps. Downstream consequence: the drift signal is malware-class-driven; AUC dilutes it (chapter 2).

*Drift-signal conservatism.* Late-period samples are sparse and family-recurrent rather than novel, which is why our drift gap reads gentler than Pendlebury's PE corpus produced.

The corpus also satisfies the rubric's specification cleanly. After dropping four identifier columns (MD5, SHA1, Name, Fuzzy), malware-day and goodware schemas share exactly 27 columns. Three (`Magic`, `PE_TYPE`, `SizeOfOptionalHeader`) are constants on this corpus, so we drop them as near-zero-variance and feature-engineer eight columns from the four string sources (DLL counts, dangerous-API flag, packer signature from `Identify`, PE-timestamp anomaly indicator), landing back at 27. Total corpus is 51,162 samples, about 59% malware. Several size-related fields span nine or more orders of magnitude — `Size` ranges from 2,560 bytes to 3.9 GB — so they receive a `log1p` transform before standard scaling; the rest receive standard scaling alone.

## 4. The model panel

The rubric specifies four baseline models — Logistic Regression, Decision Tree, Random Forest, PyTorch MLP — plus at least three additional high-performing models spanning at least two algorithm families.

Our four baselines are exactly these. Our three additional models are XGBoost, LightGBM, and CatBoost — three gradient-boosting implementations differing in splitting algorithm (level-wise, leaf-wise, and symmetric oblivious trees respectively). The seven-model panel covers five algorithm families: linear, single-tree, bagging, neural, and three GBM variants.

Every model is evaluated under both random and temporal protocols, with 10-fold stratified cross-validation on the training portion plus single-shot hold-out evaluation. The full per-(model × protocol × stage) table is `evaluation-and-design.md` §4.4. Random Forest produces the best baseline temporal-AUC (0.9602) and is therefore the base classifier for the production M.A.R.E.E. variant.

## 5. M.A.R.E.E. as recalibration response

If calibration is the failure mode under drift (chapter 1), the architecture's job is to recover calibration without sacrificing the ranking quality the baselines already have. M.A.R.E.E.'s contribution is exactly this recovery, achieved by four components.

*Sliding-window training.* The training portion of the temporal split is partitioned into K=5 density-quantile windows; one base classifier (Random Forest by default) is fit per window. Each window holds roughly equal malware sample count.

*Per-window calibration.* Inside each window, the latest 15% of malware samples by date are held out from the base classifier's training and used to fit an isotonic regression calibrator on the base classifier's raw probability output. Isotonic over Platt because the score-distribution shift between train and calibration tail is non-parametric; no logistic-shape assumption is available. The 15% choice is a standard rule of thumb: large enough to fit a monotonic curve, small enough to leave most of each window for the base classifier.

*Adaptive weighted voting.* The ensemble's positive-class probability is a weighted sum of the K calibrated per-model probabilities. Weights combine three signals: recency (newer windows get exponentially more weight, default decay placing newest at 1.0× and oldest at ~0.37×); in-window quality (each model's accuracy on its own calibration tail); and an optional decay penalty when recent observed accuracy is available.

*Drift signals.* Population Stability Index per feature is exposed by the drift detector module so the deployed system can quantify input-distribution shift to the operator.

Empirical result on the temporal hold-out: baseline RF scored 0.6557 threshold accuracy; M.A.R.E.E. with the same RF base scores 0.8218, a 16.6-percentage-point recovery. With the verdict layer (chapter 6), accuracy rises to 0.8752, 22pp above baseline. AUC sacrifice is one point (0.9602 → 0.9496). The CV-vs-hold-out gap, which read 0.99-to-0.66 for baseline RF, reads 0.99-to-0.95 for M.A.R.E.E., confirming per-window calibration does what the framework predicted.

The 0.97 AUC stretch target was missed (we landed at 0.9496) because the windows do not extend past 2015-09-15 and the model cannot extrapolate to truly unseen periods. Continuous deployment with periodic retraining is the right answer; it is in the Phase 2 roadmap.

The ensemble is single-architecture-per-window by design: we wanted to isolate the temporal-window contribution from the model-diversity contribution. Mixing architectures (RF + LightGBM + MLP per window, voting together) would conflate two effects, and the headline claim — windowing alone recovers 22pp accuracy — would be muddied. Mixed-architecture ensembling is a clean Phase 2 ablation.

## 6. Block-by-default verdict layer

*Joint confidence*: `2|p − 0.5| − ensemble_disagreement`, clipped to [0, 1]. The first term measures distance from the decision boundary; the second is the standard deviation of per-window calibrated probabilities. Confidence is high when the probability is decisive *and* the council of models agrees. Confidence is low when either condition fails.

Three verdicts, with `confidence_threshold = 0.65` as the operating point.

*ALLOWED*: calibrated probability < 0.5 AND joint confidence ≥ 0.65.

*BLOCKED_MALWARE*: calibrated probability ≥ 0.5 AND joint confidence ≥ 0.65.

*BLOCKED_UNCERTAIN*: joint confidence < 0.65, regardless of which side of 0.5 the probability falls on.

The verdict layer is fail-closed by design. The system must affirmatively allow; silence, low confidence, and disagreement all yield block. This is not the same as abstain. Abstain leaves the file's status unclear; block-by-default makes the security posture unambiguous, the file does not enter the protected environment until a human approves it. OWASP Secure Coding Practices, NIST SP 800-160, and CISA Secure-by-Design all call out fail-closed defaults as foundational for systems enforcing security boundaries.

The 0.65 threshold is conservative. It produces about five percentage points more blocks than 0.5 would, which translates to the five-point accuracy gain on the temporal hold-out (0.8218 → 0.8752). It is exposed as a tunable. High-throughput environments can lower it to 0.55; high-stakes environments can raise it to 0.75.

## 7. The hyperparameter search and its null result

The Quantic rubric Step 4 instructs cross-validation to be used "for model selection AND hyperparameter tuning". Model selection picks M.A.R.E.E. (RF base) for production, justified in chapter 5. Hyperparameter tuning is `scripts/hyperparameter_search.py`: GridSearchCV over the two leading model families on the rubric's 10-fold StratifiedKFold protocol, scoring by ROC-AUC.

Random Forest grid: 12 cells over `n_estimators × max_depth × min_samples_leaf`. Best CV AUC: 0.9980. Default CV AUC: 0.9975. Δ = +0.0005, smaller than the across-fold standard deviation of ~0.0004.

LightGBM grid: 12 cells over `num_leaves × learning_rate × n_estimators`. Best CV AUC: 0.9984. Default CV AUC: 0.9984. Δ ≈ 0.

The result is a null. Conservative defaults are inside the noise floor of the search.

Two implications. *Architectural-contribution dominance.* M.A.R.E.E.'s per-window calibration recovers 22pp threshold accuracy (chapter 5); no conceivable RF hyperparameter tweak moves that number by anything close, and the search confirms it cannot move it by more than fold-noise. *Methodological caution.* Random-CV over-reports deployed performance by 23–33pp under drift (chapter 2); squeezing 0.05% more AUC out of the random protocol is optimisation noise on a metric the deployment context cannot trust.

M.A.R.E.E.-level hyperparameters (`n_windows`, `confidence_threshold`, `recency_alpha`, `decay_penalty`) remain conservative defaults rather than search-optimised. Tuning these is the right place for further effort and is correctly scoped to Phase 2.

## 8. Deployment as resource boundary

*The architectural lesson.* When the serving environment is more resource-constrained than the training environment, training infrastructure and serving infrastructure must be separated. The M.A.R.E.E. deployment learned this through six fixes.

Render's free tier caps build RAM at 512 MB and build time at 15 minutes. The original architecture trained the M.A.R.E.E. ensemble inside the Docker container Render built on each deploy; both caps were exceeded. The fix moves training out of Docker entirely. The GitHub-hosted runner has 7 GB RAM and no practical time limit, so training runs there as part of the CI workflow's `train-and-release` job. The trained model is published as a versioned GitHub Release, and Render's Docker build becomes pip-install plus curl — finishing in two minutes inside the free-tier envelope.

The same RAM constraint required dropping gunicorn from two workers to one. Two workers in 512 MB with eager imports of xgboost, lightgbm, catboost, and scikit-learn native libraries (~250 MB resident per worker) OOM-kill during startup with no error in the log; the container hangs until the platform health check times out. We also raised gunicorn's startup timeout from 30s to 120s to accommodate the slower import path.

The deploy hook itself was the load-bearing diagnosis. Render distinguishes Blueprint deploy hooks (which only redeploy when `render.yaml` changes) from Service deploy hooks (which redeploy on demand). Our GitHub secret pointed at the Blueprint hook, so Render had not actually rebuilt after the first commit despite our pipeline reporting deploy successes. The deploy job's response payload showed a `blueprint/exs-...` URL rather than the expected `srv-...` prefix. Swapping the secret to the Service hook produced real deploy IDs.

The final failure was a worker boot crash with `OSError: libgomp.so.1: cannot open shared object file`. LightGBM and xgboost dlopen the OpenMP runtime at import; `python:3.12-slim` does not ship `libgomp1`. A two-line `apt-get install` brought the library along.

*The CI/CD gate.* The deploy job in `.github/workflows/ci.yml` declares `needs: [lint, test, test-torch, train-and-release]`. `render.yaml` has `autoDeploy: false`, so Render never deploys outside the explicit hook fired by the deploy job. There is no path for failing-test code to ship. This is the rubric's Score-5 specifier — *deploy must occur if and only if tests pass* — enforced by the dependency chain plus the autoDeploy flag together.

## 9. Triage as operator-visible explanation

*Triage report*: a four-field structure attached to every M.A.R.E.E. verdict. The fields are `summary` (one or two sentences), `why` (two to five plain-English bullets identifying which features triggered the verdict), `attack_techniques` (MITRE ATT&CK technique IDs that match the feature pattern), and `recommended_actions` (three to five incident-response steps). The report's role is to transform a binary classifier's output into operator-actionable information.

Two backends produce the same schema. *Template* (default) is deterministic, reproducible, and dependency-free. *LLM* (activated by `ANTHROPIC_API_KEY`) calls Claude Haiku 4.5 to produce more natural prose; the system prompt includes the curated `ATTACK_MAPPING` and an explicit "never invent technique IDs" constraint, so the LLM can only paraphrase fields the deterministic backend would already produce. Any LLM-call failure falls back unconditionally to the template backend.

The MITRE mapping is hand-curated and conservative. It covers five features (`imports_dangerous_api`, `identify_is_packed`, `Entropy ≥ 7.5`, `time_alignment_anomaly`, and DLL count extremes) and seven distinct technique IDs (T1055, T1106, T1027, T1027.002, T1140, T1070.006, plus combinations). Every (feature → technique) link is verified against the current MITRE ATT&CK matrix. Many real malware behaviours — registry persistence, lateral movement, command-and-control — are not mapped because the static PE features available to us do not unambiguously imply them.

The triage layer's operational role mirrors the drift indicator's. The drift indicator surfaces model degradation; the triage layer surfaces the reasoning behind a verdict. Both treat the operator as a partner who needs information, not a passive consumer of yes/no decisions. This is what defense looks like under the project's central commitment: refuse to produce verdicts the operator cannot interrogate.

## 10. Limitations

The capstone is research-grade, not production-certified. The §9 limitations in the technical report are part of the project's argument, not concealed weaknesses.

*Dataset.* The Brazilian corpus's drift is gentler than Pendlebury's PE corpus because late-period samples are family-recurrent rather than novel. Goodware lacks reliable per-sample timestamps, so we bootstrap uniformly and the AUC drift signal is anchored upward. Static features only — runtime behaviour (process injection, network call-outs, filesystem actions) is invisible to M.A.R.E.E. and requires sandbox or EDR complement.

*Model.* The 0.97 AUC stretch target was not met (0.9496) because training windows end at 2015-09-15 and the model cannot extrapolate to truly unseen periods. Continuous deployment with periodic retraining is the right answer (Phase 2). The ensemble is single-architecture-per-window by design; mixed-architecture ablation is Phase 2. M.A.R.E.E.-level hyperparameters are conservative defaults rather than search-optimised; that search is Phase 2 (chapter 7). No adversarial-robustness evaluation; today's claim is *drift-robust*, not *adversary-robust*. Adversarial work — Madry et al., Pang et al., Cohen et al. lineage — is Phase 3.

*Triage.* The MITRE mapping is conservative-but-narrow because static PE features do not unambiguously imply most malware behaviour. The LLM backend introduces a network dependency for organisations that activate it; the deterministic template is the air-gapped-compatible default.

*Operational.* Retraining is operator-actioned today, not automated. M.A.R.E.E. is not a real-time on-access scanner; it classifies submitted files. Free-tier hosting has 15-minute idle spindown; cold-start latency is roughly 30 seconds.

The limitations are documented honestly because honesty is part of the methodological argument. Other defenders hide their failure modes; the project's central commitment — *make degradation visible* — would be hollow if we hid our own.

## 11. What the demo articulates

The demo is articulation, not script. Each beat makes one conceptual move visible. The words are the presenter's; the conceptual moves are fixed.

*Open*: identify presenters; state what M.A.R.E.E. is in one sentence. Live URL on screen.

*Drift indicator*: make degradation visible. Standard products surface a green check; M.A.R.E.E. surfaces per-window calibrated accuracies.

*Three-verdict walkthrough via /demo*: make the failure mode of trust-without-uncertainty operationally visible. The goodware sample (sample_4) sets the high-confidence-allow baseline. Sample_3 shows BLOCKED_UNCERTAIN with probability 0.74 — high enough to suggest malware, but joint confidence collapsed; block-by-default fires. Sample_1 shows BLOCKED_MALWARE for high-confidence contrast. The MITRE technique panel on at least one BLOCK is the operator-actionable payoff.

*Batch upload*: make the temporal-evaluation methodology visible at the data level. A labeled CSV from late-period samples produces per-row verdicts and the AUC / accuracy / confusion-matrix block at the bottom. Land the line: these are the honest temporal numbers, not the inflated random-split benchmark.

*CI/CD walkthrough*: make the rubric's Score-5 gate concrete. Walk the five jobs (lint, test, test-torch, train-and-release, deploy). The deploy job's smoke test is the literal proof: it polls /health after Render rebuilds and only marks success if the live endpoint answers 200.

*Test architecture*: show the three-layer rubric structure (unit, integration, smoke).

*Wrap*: state the closing sentence (chapter 12).

## 12. Closing

*M.A.R.E.E. is the malware classifier that admits when it's wrong, blocks on uncertainty rather than guessing, and tells the operator how to act on every verdict.*

Each clause derives from a chapter. *Admits when it's wrong* derives from chapter 1's calibration-vs-ranking distinction and chapter 2's drift-gap measurement. *Blocks on uncertainty rather than guessing* derives from chapter 6's verdict layer. *Tells the operator how to act* derives from chapter 9's triage layer. The closing is the framework compressed into fifteen words. Recovery from forgetting any clause is reconstruction from the chapter that earns it.
