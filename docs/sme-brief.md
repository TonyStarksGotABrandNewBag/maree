# M.A.R.E.E. — subject-matter-expert brief

*Purpose.* Internal study guide for the M.A.R.E.E. capstone authors before the demo recording or any faculty defense.

*Reader model.* Strong cybersecurity background; first formal machine-learning course; abstract-verbal cognitive profile. Cybersecurity concepts (PE file structure, MITRE ATT&CK, OWASP, NIST SP 800-160, CISA Secure-by-Design, fail-closed defaults, Docker, REST APIs) are treated as already understood. Machine-learning concepts are introduced from first principles or grounded in cybersecurity intuition.

*Method.* Each chapter opens with the load-bearing definition or distinction. Subsequent sentences apply, justify, or differentiate from it. Recall is reconstruction from the framework, not memorisation of separate facts.

---

## 1. Two metrics, two failure modes

A *classifier* is a function from features (here, properties of a Windows executable file) to a number that represents how confidently the model believes the file is malware. By convention the number is a probability between 0 and 1. To turn the probability into an actual yes/no decision, the system compares it to a *threshold*, conventionally 0.5: above the threshold means malware, below means goodware. The threshold is the cut between *yes* and *no*.

Two metrics measure how well a classifier performs.

*AUC* (Area Under the Curve) measures **ranking quality** — the probability that, if you pick a random malware file and a random goodware file, the model scores the malware higher. AUC of 1.0 is perfect ranking; AUC of 0.5 is random. AUC depends only on the *order* of scores. A model that outputs 0.51 for malware and 0.49 for goodware has the same AUC as one that outputs 0.99 and 0.01. The cybersecurity analogy: AUC is *which alarm fires harder*. It cares about which file the sensor flags more loudly, not where the actual alarm threshold sits.

*Accuracy at threshold* measures **calibration quality** — the fraction of files the model classifies correctly when its score is compared to the 0.5 cutoff. This depends on the *absolute values* of the scores. Calibration is the cybersecurity intuition that a sensor's self-reported confidence numbers should actually mean what they say. A calibrated model that outputs "0.8 probability of malware" should be right 80% of the time at that score; a miscalibrated model can produce the same ordering but with the wrong numbers attached, so the 0.5 cutoff lands on the wrong side of every score.

These two metrics fail at different rates under *distribution drift* — the situation where the data the model encounters in deployment differs systematically from the data it was trained on. In the malware domain, drift is constant: attackers evolve, new families emerge, old families fade. After a year of drift, the file population a deployed defender sees is no longer the file population the model trained on.

Ranking is robust under drift. The features that historically indicated maliciousness still tend to indicate maliciousness; samples that look more malicious than baseline still score higher than samples that don't. AUC degrades slowly.

Calibration is brittle under drift. The score *distribution* shifts — the boundary between "scores typical of malware" and "scores typical of goodware" moves. The 0.5 threshold the model was trained against is no longer where the real boundary sits. The model still ranks correctly, but the cut-line is in the wrong place. Accuracy collapses.

This single distinction — ranking vs calibration, robust vs brittle — organises the entire project. Pendlebury et al. demonstrated it empirically in a 2019 USENIX Security paper called "TESSERACT" across most published malware classifiers. Random-shuffle evaluation hides the failure because the test set looks like the training set by construction. Temporal evaluation exposes it because train comes from before some date and test comes from after, mirroring the deployed reality. The malware-classifier industry reports the random-shuffle number. Deployed defenders experience the temporal-shuffle number. M.A.R.E.E. is engineered around the gap between the two — recovering calibration that drift breaks, and refusing to act on probabilities that cannot be trusted.

## 2. The drift gap

*Drift gap*: the difference between random-protocol metrics and temporal-protocol metrics for the same model on the same dataset.

*Random protocol*: shuffle all samples, take 80% for training and 20% as a hold-out test set. Train and test are drawn from the same statistical population; the test set looks like the training set, so calibration is preserved by construction. This is the standard "i.i.d." assumption in machine learning — *independent and identically distributed*, meaning every sample is drawn from the same underlying distribution and no sample's value depends on another's. Almost every ML evaluation tool assumes i.i.d. implicitly.

*Temporal protocol*: order samples by collection date, train on those before some cutoff, test on those after. Train and test are *not* drawn from the same distribution; the temporal split deliberately violates the i.i.d. assumption to simulate what a deployed defender actually faces — classifying tomorrow's files using yesterday's training data. Calibration is not preserved because the test population is genuinely different from training.

On Random Forest applied to this dataset, the random-protocol cross-validated AUC is 0.9975. Move to the temporal protocol and AUC drops to 0.9602 — a difference of 0.04. Now look at threshold accuracy. Random-protocol accuracy is 0.9833. Temporal-protocol accuracy is 0.6557 — a difference of 0.33, a 33-percentage-point collapse on the same model. Same training, same features, same sample set, only the protocol is different. AUC says the model barely degraded. Accuracy says it lost a third of its correct classifications.

The pattern is consistent across our seven-model panel. The gradient-boosting trio (XGBoost, LightGBM, CatBoost — three implementations of a technique that builds many small decision trees in sequence, each new tree trained to correct the errors of the trees before it) all collapse from ~99% random-protocol accuracy to 75–77% temporal. Logistic Regression — the simplest model in the panel, which fits a linear boundary through feature space — has the smallest drift gap because a linear boundary depends on the *relative weight* of features rather than specific feature values, and relative weights are more stable under drift. PyTorch MLP (a small feedforward neural network) is similarly robust because the regularization techniques that prevent it from overfitting to specific training features happen to also help against drift. Tree-based models suffer most because they encode specific feature splits ("if feature X exceeds value Y") that change as malware evolves.

Our AUC drift gap (0.04–0.10 across the panel) is smaller than Pendlebury's (~0.32). Three honest reasons.

*Dataset gentleness*: the Brazilian Malware Dataset's late-period samples are heavily family-recurrences of earlier malware rather than novel families. The deployment-era distribution does not diverge as sharply.

*Goodware bootstrapping*: this corpus's goodware lacks reliable per-sample collection timestamps (chapter 3 explains why), so we randomly distribute goodware across temporal folds rather than splitting it by date. AUC is computed across both classes; the in-distribution goodware portion of any test set anchors AUC upward and dilutes the malware-class drift signal.

*AUC's coarseness*: AUC is a coarse drift metric. Pendlebury also reports F1-malware (a metric that emphasizes catching positives at the cost of false positives) and per-class precision-at-k (the fraction of true positives among the top-k highest-scored samples). Both expose larger drift gaps than AUC. Our threshold-accuracy collapse (0.23–0.33 percentage points) is closer in spirit to Pendlebury's AUC drop than our AUC drop is.

The rubric asks for AUC plus accuracy. We report both because the contrast between them — small AUC drop, large accuracy drop — is the project's empirical headline.

## 3. Dataset structure as constraint

One demographic fact about the corpus drives much of the methodology: per-year malware sample density varies thirty-six-fold across the seven-and-a-half-year span (10,078 samples in 2013, fewer than 300 in 2020). Early years are abundant; late years are sparse. Four consequences follow.

*Calendar splits are unusable.* Splitting at a calendar boundary in the early years (say, train on 2013, test on 2014–2020) places almost all malware on the train side and produces a tiny test set; splitting in the late years produces the opposite. The cutoff is therefore chosen by sample-count quantile rather than calendar date: order all malware by date, count to the 80th percentile by sample count, and use *that date* as the cutoff. The newest 20% of malware *by count* falls after it. This lands on 2015-09-15. Train covers 2013 through 2015 H1 (most of the dataset by sample count); test covers 2015 H2 through 2020-11-29 (the remaining 20%, spanning more than five years).

*Density-quantile windowing.* M.A.R.E.E.'s five ensemble members are trained on five chunks of the training portion, partitioned by the same sample-count-quantile method. Each chunk holds roughly equal malware sample count rather than equal calendar duration. The earliest chunk covers a few months of 2013; the latest covers most of 2014 H2 through 2015 H1.

*Goodware bootstrapping.* The PE-embedded `FormatedTimeDateStamp` field in each goodware row claims to record when the executable was compiled, but values range from 1969 to 2100 — clearly forged or zeroed in many samples. Goodware on this corpus has no reliable per-sample collection timestamp. We therefore randomly distribute goodware across temporal folds, the standard CADE/Pendlebury practice when one class lacks timestamps. Downstream consequence: the drift signal is malware-class-driven; AUC dilutes it (chapter 2).

*Drift-signal conservatism.* Late-period samples are sparse and family-recurrent rather than novel, which is why our drift gap reads gentler than Pendlebury's PE corpus produced.

The corpus also satisfies the rubric's specification cleanly. After dropping four identifier columns (MD5, SHA1, Name, Fuzzy — these are file-identity fingerprints, not features that generalize across files), malware-day and goodware schemas share exactly 27 columns. Three columns (`Magic`, `PE_TYPE`, `SizeOfOptionalHeader`) take a single constant value across the entire corpus; we drop them as *near-zero variance* (a feature with no variation cannot help a classifier discriminate between classes). We then engineer eight new columns from four string-valued raw fields — counts of imported DLLs and symbols, a flag for dangerous Windows API calls (`LoadLibraryA`, `WinExec`, `VirtualAlloc`), a packer-signature flag derived from the `Identify` field, a PE-timestamp anomaly indicator. Final feature count: 19 raw numeric + 8 engineered = 27, matching the rubric exactly. Several size-related fields span nine or more orders of magnitude (`Size` ranges from 2,560 bytes to 3.9 GB) and would dominate any distance-based calculation; we apply `log1p` (a logarithmic transform that compresses these into a manageable range while preserving order) before *standard scaling* (a transform that re-centres each feature to mean zero and unit standard deviation, putting all features on a comparable scale). The remaining features get standard scaling alone.

## 4. The model panel

The rubric specifies four baseline models — Logistic Regression, Decision Tree, Random Forest, PyTorch MLP — plus at least three additional high-performing models spanning at least two algorithm families.

*Algorithm family*: a class of models that share an underlying structure or learning algorithm. Linear models (Logistic Regression) draw a flat boundary through feature space. Single-tree models (Decision Tree) repeatedly split feature space along axis-aligned cuts. *Bagging* ensembles (Random Forest) train many trees on randomly-sampled subsets of the data and average their votes — the term comes from "bootstrap aggregating", and the intuition is that averaging many weak independent estimators produces a strong one. Neural networks (MLP, multi-layer perceptron) compose layers of nonlinear transformations to fit complex shapes. *Boosting* ensembles build trees sequentially, each new tree explicitly trained to correct the mistakes of all the trees before it.

Our four baselines are exactly the rubric's required four. Our three additional models are all gradient-boosting implementations: XGBoost, LightGBM, and CatBoost. They are three different gradient-boosting libraries that differ in how each individual tree is constructed (level-wise, leaf-wise, and symmetric oblivious respectively — different splitting algorithms in the same family). Combined with the four baselines, our seven-model panel covers five algorithm families: linear, single-tree, bagging, neural, and three gradient-boosting variants.

Every model is evaluated under both random and temporal protocols. Within the training portion of each protocol, we run *10-fold cross-validation*: divide the training data into 10 equal-sized chunks; train on 9 chunks and evaluate on the 10th; rotate which chunk is held out so each chunk gets evaluated exactly once; report the mean and standard deviation of AUC across the 10 evaluations. Cross-validation gives us a more stable performance estimate than a single train/test split would, and the 10-fold spec is the rubric's required reporting format. We also run single-shot hold-out evaluation on the 20% test set that was reserved before any training started. The full per-(model × protocol × stage) results table is `evaluation-and-design.md` §4.4.

Random Forest produces the best baseline temporal-AUC (0.9602) and is therefore the base classifier for the production M.A.R.E.E. variant.

## 5. M.A.R.E.E. as recalibration response

If calibration is the failure mode under drift (chapter 1), the architecture's job is to recover calibration without sacrificing the ranking quality the baselines already have. M.A.R.E.E.'s contribution is exactly this recovery, achieved by four components.

*Component 1: sliding-window training.* The training portion of the temporal split is partitioned into K=5 density-quantile windows (chapter 3) — five chunks of roughly equal malware sample count, ordered chronologically. One Random Forest classifier is trained per window. The result is five base classifiers, each having seen a different temporal slice of the historical data. Earlier members have learned older malware patterns; later members have learned newer ones.

*Component 2: per-window calibration.* Inside each window, the latest 15% of malware samples by date are held out from the base classifier's training. This held-out portion is the *calibration tail*. The base classifier is trained on the remaining 85%; a *calibrator* is then fit on the calibration tail. The calibrator is a small post-processing function that maps the base classifier's raw probability output to a *calibrated* probability — a number whose value matches the empirical fraction of true positives at that score. (A calibrated 0.7 means *70 out of 100 files at this score are actually malware*; a raw 0.7 means whatever the model decided it means, which under drift is no longer trustworthy.)

The calibrator we use is *isotonic regression*. The word *isotonic* names the only constraint we put on the shape of the correction curve: the curve must go up and to the right, never doubling back. If the raw score increases, the calibrated score must also increase or stay flat. That is the only assumption. The fitting procedure then picks whichever up-and-to-the-right curve minimises squared error against the calibration-tail data. The alternative most ML courses teach is *Platt scaling*, which assumes the curve has the specific shape produced by logistic regression (an S-shaped sigmoid). Platt is fine when that shape happens to fit; under drift it often does not, and assuming it constrains the calibrator to corrections it cannot perform. Isotonic regression makes no shape commitment beyond monotonicity, so it survives whatever shape drift imposes.

*Component 3: adaptive weighted voting.* The ensemble's positive-class probability is a weighted sum of the K=5 calibrated per-model probabilities. Three signals contribute to each member's weight. *Recency*: newer windows get exponentially more weight, with the default decay constant placing the newest at 1.0× and the oldest at about 0.37×; the intuition is that the newest member has trained on the data closest to the deployment-era distribution. *In-window quality*: each member's accuracy on its own calibration tail; chronically weak windows get downweighted regardless of their age. *Decay penalty* (optional): when recent observed accuracy on production data is available, members whose accuracy has degraded since training get further downweighted.

*Component 4: drift signals.* *Population Stability Index* (PSI) is a standard statistical measure of how much one feature's distribution has shifted between two datasets. We compute it per feature between the training data and any new production data, expose it through the drift detector module, and surface the result in the deployed UI. The operator can therefore see, quantitatively, how much the input distribution has changed since training — which is the data they need to decide whether retraining is overdue.

Empirical result on the temporal hold-out: baseline RF scored 0.6557 threshold accuracy; M.A.R.E.E. with the same RF as its base classifier scores 0.8218, a 16.6-percentage-point recovery. With the verdict layer (chapter 6), accuracy rises to 0.8752, 22pp above baseline. The AUC sacrifice is one point (0.9602 → 0.9496). The CV-vs-hold-out gap, which read 0.99-to-0.66 for baseline RF, reads 0.99-to-0.95 for M.A.R.E.E., confirming the per-window calibration does what the framework predicted.

The 0.97 AUC stretch target was missed (we landed at 0.9496) because the windows do not extend past 2015-09-15 and the model cannot extrapolate to truly unseen periods. Continuous deployment with periodic retraining is the right answer; it is in the Phase 2 roadmap.

The ensemble is single-architecture-per-window (all five members are Random Forests) by deliberate design: we wanted to isolate the temporal-window contribution from the model-diversity contribution. Mixing architectures (RF + LightGBM + MLP per window, voting together) would conflate two effects, and the headline claim — windowing alone recovers 22pp accuracy — would be muddied. Mixed-architecture ensembling is a clean Phase 2 ablation.

## 6. Block-by-default verdict layer

*Joint confidence* is a single number per file, computed from the ensemble's outputs, that captures how much we trust this verdict. The formula is `2 · |p − 0.5| − ensemble_disagreement`, clipped to the 0-to-1 range. Two pieces compose it.

The first piece, `2 · |p − 0.5|`, measures distance from the decision boundary. A probability right on the cut (p = 0.5) gives 0; a probability of 0.95 or 0.05 gives 0.9. Decisive probabilities produce high confidence; near-boundary probabilities produce low confidence.

The second piece, `ensemble_disagreement`, is the *standard deviation* of the five members' calibrated probabilities for this file — a number measuring how spread-out the votes are. (Standard deviation is the stats-101 measure of spread: zero when everyone agrees on the same value, larger as the values disperse.) If all five members say 0.9, the standard deviation is near zero and this term contributes little. If two say 0.9 and three say 0.3, the standard deviation is large and this term subtracts substantially from confidence.

The composition: confidence is high when the probability is decisive *and* the council of models agrees. Confidence is low when either condition fails.

Three verdicts, with `confidence_threshold = 0.65` as the operating point.

*ALLOWED*: calibrated probability < 0.5 AND joint confidence ≥ 0.65. The model is confident the file is benign.

*BLOCKED_MALWARE*: calibrated probability ≥ 0.5 AND joint confidence ≥ 0.65. The model is confident the file is malware.

*BLOCKED_UNCERTAIN*: joint confidence < 0.65, regardless of which side of 0.5 the probability falls on. The model cannot affirmatively commit either way; the operator gets the fail-closed default.

The verdict layer is *fail-closed by design*. The system must affirmatively allow; silence, low confidence, and disagreement all yield block. This is familiar cybersecurity discipline — OWASP Secure Coding Practices, NIST SP 800-160, and CISA Secure-by-Design all call out fail-closed defaults as foundational for systems enforcing security boundaries — applied with an ML-specific twist. *Abstain* (some classifiers' alternative to a hard verdict) leaves the file's status unclear: does the file go through, get queued, get sent to a human, or just sit somewhere? Block-by-default makes the security posture unambiguous: the file does not enter the protected environment until a human approves it.

The 0.65 threshold is conservative. It produces about five percentage points more blocks than 0.5 would, which translates to the five-point accuracy gain on the temporal hold-out (0.8218 → 0.8752). It is exposed as a configuration knob. High-throughput environments can lower it to 0.55 (more allows, more risk); high-stakes environments can raise it to 0.75 (more uncertain-blocks, more friction).

## 7. The hyperparameter search and its null result

*Hyperparameter*: a configuration choice fixed before training rather than learned from data. For Random Forest: how many trees to grow, how deep each tree gets, the minimum number of samples required at each leaf node. For LightGBM: how many leaves per tree, the *learning rate* (a step-size parameter that controls how aggressively each new tree corrects the previous trees' errors), the number of boosting iterations. Hyperparameters are knobs the human sets; *parameters* are what the model learns once you've set the knobs. *Hyperparameter tuning* is the process of searching across knob-combinations to find the configuration that produces the best cross-validated performance.

The Quantic rubric Step 4 instructs that 10-fold cross-validation be used "for model selection AND hyperparameter tuning". Model selection picks M.A.R.E.E. (RF base) for production, justified in chapter 5. Hyperparameter tuning is `scripts/hyperparameter_search.py`.

*GridSearchCV* is the standard sklearn tool for the job: lay out a *grid* of hyperparameter combinations, train and evaluate the model under k-fold cross-validation for each combination, return the combination with the highest mean cross-validated score. We ran two grids on the random 80/20 split's training portion, scored by AUC.

Random Forest: 12 cells covering n_estimators (200, 400) × max_depth (10, 20, None) × min_samples_leaf (2, 5). Best cell scored 0.9980 mean CV AUC. The conservative default in `src/models/baselines.py` scores 0.9975. Improvement: +0.0005.

LightGBM: 12 cells covering num_leaves (31, 63, 127) × learning_rate (0.05, 0.10) × n_estimators (200, 400). Best cell scored 0.9984. Default scores 0.9984. Improvement: approximately zero.

*Null result*: an outcome statistically indistinguishable from the baseline, where the observed difference is smaller than the natural variation in the measurement itself. The relevant variation here is the spread of AUC values across the 10 cross-validation folds at the best-performing cell — the *across-fold standard deviation* — which is about 0.0004 for both models. Both observed improvements (+0.0005 and ~0) fall inside this noise floor. The conservative defaults are not statistically distinguishable from the grid optima.

Two implications.

*Architectural-contribution dominance.* M.A.R.E.E.'s per-window calibration recovers 22 percentage points of threshold accuracy under temporal evaluation (chapter 5). The hyperparameter search demonstrates that no Random Forest knob, varied across its plausible range, moves CV AUC by more than fold-noise. The architectural contribution is therefore at least two orders of magnitude larger than any available hyperparameter contribution; tuning is not the project's load-bearing variable. We have empirical evidence — not just an assertion — that the architecture is what matters.

*Caution against over-tuning the random protocol.* The hyperparameter search optimises a random-protocol metric (mean CV AUC under random-shuffle 10-fold). Chapter 2 established that random-protocol metrics over-report deployed performance by 23–33 percentage points of accuracy under drift. Squeezing additional AUC out of the random protocol is optimisation noise on a measurement the deployment context cannot trust. Absent a temporal-protocol tuning regimen (which is itself Phase 2 work — the i.i.d. assumption that GridSearchCV implicitly relies on breaks under temporal CV, and the dataset's density imbalance compounds the issue), the conservative defaults are the more honest choice.

M.A.R.E.E.-level hyperparameters — `n_windows`, `confidence_threshold`, `recency_alpha`, `decay_penalty` — remain conservative defaults rather than search-optimised. Tuning these is the correct further investment and is correctly scoped to Phase 2.

## 8. Deployment as resource boundary

*The architectural lesson.* When the serving environment is more resource-constrained than the training environment, training infrastructure and serving infrastructure must be separated. The M.A.R.E.E. deployment learned this through six fixes.

Render's free tier caps build RAM at 512 MB and build time at 15 minutes. The original architecture trained the M.A.R.E.E. ensemble inside the Docker container Render built on each deploy; both caps were exceeded immediately. The fix moves training out of Docker entirely. The GitHub-hosted runner has 7 GB RAM and no practical time limit, so training runs there as part of the CI workflow's `train-and-release` job. The trained model is published as a versioned GitHub Release, and Render's Docker build becomes pip-install plus curl — finishing in two minutes inside the free-tier envelope.

The same RAM constraint required dropping gunicorn (the production-grade Python application server we use to serve the Flask app) from two workers to one. Two workers in 512 MB with eager imports of xgboost, lightgbm, catboost, and scikit-learn native libraries (~250 MB resident per worker) OOM-kill during startup with no error in the log; the container hangs until the platform health check times out. We also raised gunicorn's startup timeout from 30s to 120s to accommodate the slower import path.

The deploy hook itself was the load-bearing diagnosis. Render distinguishes Blueprint deploy hooks (which only redeploy when `render.yaml` changes) from Service deploy hooks (which redeploy on demand). Our GitHub secret pointed at the Blueprint hook, so Render had not actually rebuilt after the first commit despite our pipeline reporting deploy successes. The deploy job's response payload showed a `blueprint/exs-...` URL rather than the expected `srv-...` prefix. Swapping the secret to the Service hook produced real deploy IDs.

The final failure was a worker boot crash with `OSError: libgomp.so.1: cannot open shared object file`. LightGBM and xgboost dynamically load the OpenMP runtime at import; `python:3.12-slim` (the Docker base image) does not ship `libgomp1`. A two-line `apt-get install` brought the library along.

*The CI/CD gate.* The deploy job in `.github/workflows/ci.yml` declares `needs: [lint, test, test-torch, train-and-release]`. `render.yaml` has `autoDeploy: false`, so Render never deploys outside the explicit hook fired by the deploy job. There is no path for failing-test code to ship. This is the rubric's Score-5 specifier — *deploy must occur if and only if tests pass* — enforced by the dependency chain plus the autoDeploy flag together.

## 9. Triage as operator-visible explanation

*Triage report*: a four-field structure attached to every M.A.R.E.E. verdict. The fields are `summary` (one or two sentences), `why` (two to five plain-English bullets identifying which features triggered the verdict), `attack_techniques` (MITRE ATT&CK technique IDs that match the feature pattern), and `recommended_actions` (three to five incident-response steps). The report transforms a binary classifier's output into operator-actionable information.

Two backends produce the same schema. *Template* (default) is deterministic, reproducible, and dependency-free. *LLM* (activated by setting an `ANTHROPIC_API_KEY` environment variable) calls Claude Haiku 4.5 to produce more natural prose; the system prompt includes the curated `ATTACK_MAPPING` and an explicit "never invent technique IDs" constraint, so the LLM can only paraphrase fields the deterministic backend would already produce. Any LLM-call failure falls back unconditionally to the template backend.

The MITRE mapping is hand-curated and conservative. It covers five features (`imports_dangerous_api`, `identify_is_packed`, `Entropy ≥ 7.5`, `time_alignment_anomaly`, and DLL count extremes) and seven distinct technique IDs (T1055, T1106, T1027, T1027.002, T1140, T1070.006, plus combinations). Every (feature → technique) link is verified against the current MITRE ATT&CK matrix. Many real malware behaviours — registry persistence, lateral movement, command-and-control — are not mapped because the static PE features available to us do not unambiguously imply them.

The triage layer's operational role mirrors the drift indicator's. The drift indicator surfaces model degradation; the triage layer surfaces the reasoning behind a verdict. Both treat the operator as a partner who needs information, not a passive consumer of yes/no decisions. This is what defense looks like under the project's central commitment: refuse to produce verdicts the operator cannot interrogate.

## 10. Limitations

The capstone is research-grade, not production-certified. The §9 limitations in the technical report are part of the project's argument, not concealed weaknesses.

*Dataset.* The Brazilian corpus's drift is gentler than Pendlebury's PE corpus because late-period samples are family-recurrent rather than novel. Goodware lacks reliable per-sample timestamps, so we bootstrap uniformly and the AUC drift signal is anchored upward. Static features only — runtime behaviour (process injection, network call-outs, filesystem actions) is invisible to M.A.R.E.E. and requires sandbox or EDR complement.

*Model.* The 0.97 AUC stretch target was not met (0.9496) because training windows end at 2015-09-15 and the model cannot extrapolate to truly unseen periods. Continuous deployment with periodic retraining is the right answer (Phase 2). The ensemble is single-architecture-per-window by design; mixed-architecture ablation is Phase 2. M.A.R.E.E.-level hyperparameters are conservative defaults rather than search-optimised; that search is Phase 2 (chapter 7). No *adversarial-robustness* evaluation. The distinction matters: *drift-robust* means robust against the threat distribution naturally evolving over time. *Adversary-robust* means robust against an attacker who deliberately crafts samples designed to fool this specific classifier — a stronger threat model that requires different evaluation methodology and different defenses (Madry et al., Pang et al., Cohen et al. lineage). Today's claim is drift-robust, not adversary-robust. Adversarial work is Phase 3.

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
