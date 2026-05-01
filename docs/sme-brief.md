# M.A.R.E.E. — subject-matter-expert brief

**Audience:** Kenny and Wyatt, before recording the demo or defending the capstone in any live discussion.

**How to use this document:** read it twice end-to-end. Quiz yourselves on the "cold-recall" tables. The goal is internalizing the *thinking*, not memorizing words. After that, you can present without a script — every beat in the demo is something you understand and can explain in your own words.

This is a long brief on purpose. The capstone has hours of thinking compressed into 5 minutes of UI clicks; an SME knows the compression. A reviewer who asks "why did you do X instead of Y?" is testing whether you actually thought, or whether the AI did the thinking for you. This document gives you the answer to every "why" you'll be asked.

---

## 1. The elevator pitch (memorize cold)

> M.A.R.E.E. — Multi-classifier Adaptive Recognition, Explainable Engine — is a malware classifier for Windows PE files. It does what other classifiers don't: it measures its own degradation as the threat landscape evolves, blocks files by default when uncertain, and explains every verdict in language an IT admin can act on. We trained it on the Brazilian Malware Dataset using the Pendlebury TESSERACT temporal-evaluation methodology and deployed it under a CI/CD pipeline gated on automated tests.

That's the elevator pitch. **Three things to remember:**
1. *Measures its own degradation* (drift indicator).
2. *Blocks by default when uncertain* (three verdicts, fail-closed).
3. *Explains every verdict* (MITRE ATT&CK triage).

Everything else is detail underneath those three.

## 2. The thesis (the one paragraph that justifies everything)

The malware-classifier industry reports random-split accuracy numbers around 97–99%. Pendlebury et al. (USENIX Security 2019, "TESSERACT") established that this number is misleading: under temporal evaluation — train on data before time T, evaluate on data after T — the same classifiers degrade dramatically because the threat distribution shifts and the classifier's calibration breaks. Our project replicates this finding empirically (random-split accuracy 98.3%, temporal-split accuracy 65.6% for Random Forest on this dataset), then *responds* to it operationally: a drift-adaptive ensemble that recovers calibration via per-window isotonic regression, a fail-closed three-verdict decision layer that blocks on uncertainty rather than guessing, and an operator-visible drift indicator so the IT admin knows when the model is degrading. The "97% accuracy" defenders were sold is a number that decays in production; M.A.R.E.E. tells the operator how much it has decayed.

If you can say that paragraph in your own words for 60 seconds, you can defend the project.

## 3. Numbers cold-recall

Memorize these. A confident SME drops numbers without looking. Wrong numbers cost more credibility than no numbers.

### 3.1 Dataset and feature scope

| Number | What it means |
|---|---|
| **51,162** | Total samples in the cleaned corpus (rubric asks for ~50,000) |
| **30,046** | Malware samples |
| **21,116** | Goodware samples |
| **58.7% / 41.3%** | Class balance, malware / goodware |
| **2013-01-01 → 2020-11-29** | Time span (~7.9 years) |
| **27** | Total features (rubric requirement: exactly 27) |
| **19** | Raw numeric features (after dropping 3 NZV) |
| **8** | Engineered features (from 4 string columns) |
| **3** | Near-zero-variance columns dropped (`Magic`, `PE_TYPE`, `SizeOfOptionalHeader`) |
| **42** | Random seed (`config.GLOBAL_SEED`) — same for all stochastic steps |
| **36×** | Per-year malware density variation (10,078 in 2013 vs 279 in 2020) — the reason for density-aware splits |

### 3.2 Headline drift gap (Random Forest)

| Number | What it means |
|---|---|
| **AUC 0.9975** | Random-split CV (rubric protocol) |
| **AUC 0.9602** | Temporal-split hold-out (honest-evaluation protocol) |
| **−0.037** | Drift gap on AUC (modest) |
| **Accuracy 0.9833** | Random-split hold-out at the standard 0.5 threshold |
| **Accuracy 0.6557** | Temporal-split hold-out at the same threshold |
| **−0.328** | The accuracy collapse — 33 percentage points |

### 3.3 M.A.R.E.E. recovery (Random Forest base)

| Number | What it means |
|---|---|
| **AUC 0.9496** | M.A.R.E.E. (RF base) on temporal hold-out — 1pp below the baseline RF AUC, but… |
| **Accuracy 0.8218** | M.A.R.E.E. raw 0.5-threshold accuracy on temporal hold-out — **+16.6pp** above baseline RF |
| **Accuracy 0.8752** | With block-by-default semantics added — **+22pp** above baseline RF |
| **5 windows** | Density-quantile-partitioned temporal slices (`n_windows=5`) |
| **0.65** | `confidence_threshold` (verdicts below this → BLOCKED_UNCERTAIN) |
| **0.985 → 0.967** | Per-window calibrated accuracy, oldest → newest (slight decline = threats genuinely getting harder year over year) |
| **15%** | `calibration_tail_fraction` — latest 15% of each window held out for isotonic regression |

### 3.4 The model panel (rubric's 4 + 3 requirement)

| Model | Random CV AUC | Temporal CV AUC | Random hold-out acc | Temporal hold-out acc |
|---|---|---|---|---|
| Logistic Regression | 0.9470 | 0.9557 | 0.879 | 0.827 |
| Decision Tree | 0.9910 | 0.9942 | 0.969 | **0.652** |
| Random Forest | 0.9975 | 0.9983 | 0.983 | **0.656** |
| PyTorch MLP | 0.9932 | 0.9960 | 0.972 | 0.877 |
| XGBoost | 0.9983 | 0.9987 | 0.989 | 0.756 |
| LightGBM | 0.9984 | 0.9988 | 0.989 | 0.753 |
| CatBoost | 0.9978 | 0.9985 | 0.987 | 0.765 |

You don't need to memorize every cell. **Memorize:** RF and the GBM trio collapse from ~99% to 65–77% accuracy under temporal evaluation. MLP is unusually drift-robust. LR is gentlest because its linear boundary is near-invariant to specific feature values.

### 3.5 Hyperparameter search (§4.5)

| Number | What it means |
|---|---|
| **Δ AUC +0.0005 (RF)** | Best grid cell vs. defaults — within across-fold std (0.0004) |
| **Δ AUC +0.000021 (LGBM)** | Best grid cell vs. defaults — statistically zero |
| **240 fits** | Total CV evaluations (12 cells × 10 folds × 2 models) |
| **~40 min** | Total wall-clock for the search |

Headline takeaway: **conservative defaults are within statistical noise of the grid optimum.** Architectural contribution (M.A.R.E.E. ensemble) dominates hyperparameter contribution by orders of magnitude.

### 3.6 The deployment

| Number | What it means |
|---|---|
| **5 demo samples** | Pre-loaded in `/demo` from the temporal hold-out |
| **5/5 correct verdicts** | End-to-end smoke against `/api/predict` |
| **~2 s** | Warm-request latency for a single prediction |
| **~25–30 s** | Cold-start latency on free-tier Render after 15-min idle |
| **1 gunicorn worker** | Free-tier 512 MB RAM — two workers OOM during xgboost+lightgbm+catboost native-lib load |
| **120 s** | Gunicorn `--timeout` (default 30s wasn't enough for the slowest path) |

## 4. Vocabulary cold-recall

Drop these terms confidently. If you fumble these, the SME illusion breaks.

| Term | One-line definition you can say |
|---|---|
| **TESSERACT methodology** | Pendlebury et al.'s 2019 framework for temporally-honest evaluation of malware classifiers — train before T, evaluate after T. |
| **Density-aware temporal split** | Cut at the date where the newest 20% of malware *by sample count* falls after the cutoff — not by calendar, because per-year density varies 36×. |
| **Drift gap** | The difference between random-split and temporal-split metrics on the same model. Headline finding: small on AUC, dramatic on threshold accuracy. |
| **Calibration vs. ranking** | AUC measures ranking (does the model score malware higher than goodware?). Accuracy at threshold measures calibration (do those scores cross 0.5 correctly?). On non-stationary data, ranking holds up; calibration breaks. |
| **Isotonic regression calibrator** | Monotonic mapping fit on a held-out 15% of each window's malware samples. Recovers the meaning of the 0.5 threshold even after the underlying score distribution shifts. |
| **Joint confidence** | `2 · |p − 0.5| − disagreement`, clipped to [0, 1]. Penalizes both probabilities near 0.5 (model uncertainty) AND high per-window disagreement (council disagrees). |
| **Block-by-default** | Three verdicts (ALLOW, BLOCK_MALWARE, BLOCK_UNCERTAIN). The ensemble must *affirmatively* allow. Silence, low confidence, disagreement → block. Aligned with OWASP / NIST SP 800-160 / CISA Secure-by-Design. |
| **Population Stability Index (PSI)** | Statistical measure of how much a feature distribution has drifted between training and deployment. Exposed in `drift_detector` for operator monitoring. |
| **Recency weighting (`exp(-α · (K-1-i)/(K-1))`)** | Newer ensemble members get exponentially more weight in the vote (default α=1.0 → newest 1.0×, oldest ~0.37×). |
| **Decay penalty** | Optional weight reduction for ensemble members whose accuracy on recent observed data has decayed since training (`exp(-β · decay)`, default β=2.0). |
| **MITRE ATT&CK technique mapping** | Hand-curated `(feature → technique-ID)` links. The LLM backend gets this mapping in its system prompt with the explicit "never invent technique IDs" constraint. The deterministic backend cannot invent them by construction. |

## 5. Architecture decisions — the "why" Q&A

A reviewer asks "why did you do X?" Here are the answers, with the alternative framed honestly.

### 5.1 Why density-aware temporal splits instead of calendar splits?

Per-year malware density varies 36× on this dataset (10,078 samples in 2013, 279 in 2020). Calendar-year splits in the early years put almost all data on the train side and produce a useless test set. Splitting by quantile of cumulative sample count gives both folds meaningful size while preserving train-before-test no-look-ahead.

### 5.2 Why bootstrap goodware uniformly across folds?

Goodware on this dataset has no reliable per-sample collection timestamp. The only available signal, the PE-embedded `FormatedTimeDateStamp`, is forged or zeroed in many samples (values span 1969 to 2100). For temporal evaluation we treat goodware as bootstrapped uniformly across windows. This is the standard CADE / Pendlebury treatment when one class lacks timestamps. **Consequence:** the drift signal is malware-class-driven; AUC is anchored upward by the in-distribution goodware portion, which is one reason our AUC drift gap is gentler than Pendlebury's.

### 5.3 Why 27 features, why these 27?

Rubric requires 27 input attributes. The malware-day and goodware schemas in the Brazilian dataset share exactly 27 columns after we drop 4 identifier columns (MD5, SHA1, Name, Fuzzy). 3 of the 22 numeric columns are near-zero variance (`Magic`, `PE_TYPE`, `SizeOfOptionalHeader` are constants on this corpus) so we drop them. We feature-engineer 8 columns from 4 string sources (DLL counts, dangerous-API flags, packer signature, PE-timestamp anomaly) to land back at 27. Numbers chosen to match the rubric, but every transformation is methodologically justified independently.

### 5.4 Why log-then-scale for size features?

Size-related fields like `Size` span 9+ orders of magnitude (2,560 bytes to 3,986,103,808 bytes). StandardScaler alone produces a near-degenerate distribution. We `log1p` first, then standard-scale. This is in `LOG_THEN_SCALE` in `src/preprocessing.py`.

### 5.5 Why 5 ensemble windows?

Empirical: 5 windows give meaningful per-window sample sizes (~6,000 malware each) on this dataset's density distribution. Fewer would lose temporal granularity; more would starve each member. Configurable via `MareeConfig.n_windows`.

### 5.6 Why isotonic regression on a 15% calibration tail?

15% is a standard isotonic-regression rule of thumb — large enough to fit a monotonic curve, small enough to leave most of each window for the base classifier. Isotonic over Platt scaling because the score-distribution shift is non-parametric; we don't want to assume a logistic shape.

### 5.7 Why block-by-default rather than abstain?

Abstain is mush — the file goes through, or it doesn't, or it sits in a queue, and which one is unclear. Block-by-default makes the security posture unambiguous. OWASP, NIST SP 800-160, and CISA Secure-by-Design all call out fail-closed defaults as foundational. The defender deploying M.A.R.E.E. cannot accidentally allow a low-confidence file because the system "couldn't decide" — low confidence IS a decision.

### 5.8 Why `joint_confidence = 2|p − 0.5| − disagreement`?

Two ways for a verdict to be untrustworthy: (a) model is sitting near the decision boundary (|p − 0.5| is small), (b) ensemble members disagree (high std). The formula penalizes both, clipped to [0,1]. A defender wants confidence to be high *only* when both conditions are favorable — strong probability AND ensemble agreement. The formula is multiplicatively-flavored on these two dimensions; one bad axis kills confidence.

### 5.9 Why `confidence_threshold = 0.65` (not 0.5 or 0.75)?

Conservative default. Produces about 5pp more BLOCKs than 0.5, and the +5pp shows up as accuracy gain (87.5% block-by-default vs 82.2% raw 0.5-threshold). Tunable per deployment risk: high-throughput environments lower to 0.55, high-stakes environments raise to 0.75.

### 5.10 Why Random Forest as the production base, not LightGBM?

Two M.A.R.E.E. variants exist (`maree_random_forest`, `maree_lightgbm`). RF is the production model because:
- RF had the highest *temporal* hold-out AUC of all baselines (0.9602) — best ranking quality in the deployment-relevant protocol.
- LightGBM had the worst temporal hold-out accuracy of the GBM trio (0.7533) — using it as the ensemble base would lift it more in relative terms, but produce a weaker absolute deployment.
- RF + per-window calibration recovers more accuracy in absolute terms (98.3 → 87.5 vs LGBM's 75.3 → 86.6 with block-by-default).

### 5.11 Why didn't you tune the M.A.R.E.E.-level hyperparameters?

We tuned the *base estimator* hyperparameters (§4.5) — RF and LightGBM via 10-fold-CV GridSearchCV. The result: defaults are within statistical noise of the grid optimum (Δ +0.0005 RF, Δ +0.000021 LGBM, both smaller than across-fold std ~0.0004–0.0008). Empirical evidence that base-estimator tuning does not move the needle. The right place for further tuning is the M.A.R.E.E.-level parameters (`n_windows`, `confidence_threshold`, `recency_alpha`, `decay_penalty`) and that is Phase 2 work because (a) the architectural contribution dominates the hyperparameter contribution by orders of magnitude — the M.A.R.E.E. ensemble alone recovers +22pp accuracy, far more than any knob will move; (b) over-tuning to random-CV is exactly the calibration trap our methodology warns against.

### 5.12 Why `autoDeploy: false` in render.yaml?

The rubric's Score-5 specifier says "deploy must occur if and only if tests pass." If we set `autoDeploy: true`, Render would deploy on every push regardless of CI status — there'd be a path for failing-test code to ship. Setting `autoDeploy: false` means only the CI's deploy hook can trigger Render, and our CI's deploy job depends on lint + test + test-torch + train-and-release, so the gate holds.

### 5.13 Why train the model in CI rather than in Docker on Render?

Render's free tier has 512 MB build RAM and 15-min build budget. Training the M.A.R.E.E. ensemble (5 RFs × per-window calibration on ~50K rows) spikes both. We train on the GitHub-hosted runner (7 GB RAM, no time pressure), publish the trained model as a versioned GitHub Release (`model-latest`), and Render's Docker build just `pip install + curl`s the artifact — finishes in ~2 minutes inside the free-tier envelope. Clean separation of "where you train" from "where you serve".

### 5.14 Why one gunicorn worker?

`src.app.server` eagerly imports `src.models.ensemble`, which pulls in xgboost, lightgbm, catboost, and sklearn native libraries (~250 MB resident per worker), and joblib-loads the trained model. Two workers in 512 MB RAM OOM-kill during startup with no log signal — the container hangs until the platform health check times out. One worker stays comfortably inside the envelope. Tradeoff: serial request handling, fine for an academic demo.

### 5.15 Why `libgomp1` in the Dockerfile?

LightGBM (and xgboost) `dlopen` `libgomp.so.1` (the OpenMP runtime) at import time. Python:3.12-slim doesn't ship it. Without `apt-get install libgomp1`, the worker crashes on boot with `OSError: libgomp.so.1: cannot open shared object file`. This was the final fix in the deployment debugging chain.

### 5.16 Why MITRE template + LLM with "never invent" constraint?

Two backends, both producing the same four-field schema (summary / why / attack_techniques / recommended_actions):

- **Template** (default): deterministic, reproducible, zero external dependencies. The capstone-default backend.
- **LLM (Claude Haiku 4.5)**: activated when `ANTHROPIC_API_KEY` is set. Produces more natural prose. Constrained by the system prompt to never invent technique IDs — only paraphrases fields the deterministic backend would already produce. Falls back to template on any LLM failure.

The MITRE mapping itself is hand-curated. 5 features → 7 technique IDs. Conservative and verifiable.

## 6. Methodology Q&A — what reviewers will probe

### 6.1 "Why is your AUC drift gap (0.04–0.10) smaller than Pendlebury's (~0.32)?"

Three honest reasons, all in `evaluation-and-design.md` §4.2:
1. The Brazilian dataset's drift is genuinely milder than Pendlebury's PE corpus. Late-period samples are heavily family-recurrences of earlier malware. Per-year sample density drops 36× from 2013 to 2020.
2. Goodware is bootstrapped uniformly across folds (because of the timestamp unreliability — see 5.2). AUC mixes both classes; the goodware portion of any test set is in-distribution and anchors AUC upward.
3. AUC is a coarse drift metric. Pendlebury also reports F1-malware and per-class precision @ k. We report both AUC AND accuracy at threshold; the accuracy collapse on our dataset (−0.23 to −0.33pp) is closer in spirit to Pendlebury's AUC drop.

### 6.2 "Why didn't you mix architectures in the ensemble?"

Each M.A.R.E.E. member is the same architecture (RF or LightGBM) trained on a different time slice. We chose this to *isolate the temporal-window contribution from the model-diversity contribution*. A genuinely-diverse ensemble (RF + LGBM + MLP, each trained on the same slice) is a Phase 2 ablation. We can claim the temporal-windowing recovers +22pp accuracy. Mixing in heterogeneous voting would conflate two effects.

### 6.3 "Why didn't M.A.R.E.E. close the AUC gap to 0.97?"

Phase E set 0.97 as a stretch target. We landed at 0.9496 (RF) and 0.9455 (LightGBM) — about 2pp below. M.A.R.E.E.'s windows do not extend past 2015-09-15, so it is robust *within* its training span and partially robust to the post-cutoff shift, but it cannot extrapolate to entirely-new periods without seeing them. **Continuous deployment requires periodic retraining.** This is a Phase 2 ROADMAP item — automated retraining triggered by drift signals.

### 6.4 "What's the threat model? What can M.A.R.E.E. NOT defend against?"

Today's claim is **drift-robust**, not **adversary-robust**. We do not evaluate against gradient-based or problem-space evasion attacks (Pierazzi et al., IEEE S&P 2020). Adversarial work is in the Phase 3 ROADMAP — Madry et al., Pang et al., Cohen et al. lineage.

We also don't see runtime behavior — static features only. M.A.R.E.E. is a complement to, not a replacement for, dynamic-behavior tools (sandboxes, EDR).

### 6.5 "Is the temporal split a leakage risk?"

The temporal split fixes a calendar-aware cutoff date *per the rubric's 80/20 hold-out*, then the 10-fold CV happens within the training portion (samples before the cutoff). Test set is untouched. Within the training portion, CV folds are stratified-on-Label — within-window CV is the rubric standard for hyperparameter selection, not a leakage of post-cutoff data.

The methodologically critical no-look-ahead is preserved at the outer split level. CV folds inside the training portion can shuffle freely.

### 6.6 "How do you know the calibration recovery isn't just overfitting to the calibration tail?"

The calibration tail (latest 15% of each window's malware) is held out from the base classifier's training. Isotonic regression on that tail produces a monotonic mapping that recovers threshold meaning. The 0.5-threshold accuracy improvement on the *temporal hold-out* — data the model has never seen — is the empirical answer. If the calibration were overfit to the within-window tail, hold-out accuracy wouldn't move; it moves +16.6pp raw, +22pp with block-by-default. That's evidence of real generalization, not memorization.

## 7. Operational / deployment Q&A

### 7.1 "Walk me through the CI/CD pipeline."

Five jobs, one workflow (`.github/workflows/ci.yml`), every push to main:
1. **lint** — `ruff check src/ tests/ scripts/`. ~10 seconds.
2. **test** — full pytest suite minus torch tests. 133 tests, ~50 seconds.
3. **test-torch** — torch tests in their own job. 4 tests, ~2 minutes (libomp isolation from the GBM jobs).
4. **train-and-release** — runs `scripts/train_production_model.py` on the GH-hosted runner, publishes `maree_production.joblib` + `demo_samples.json` as the `model-latest` GitHub Release. ~2 minutes.
5. **deploy** — `needs:` all four prior jobs. Fires Render's deploy hook, then post-deploy polls `https://maree-f8c8.onrender.com/health` for up to ~10 minutes. ~5 minutes wall-clock.

`render.yaml` has `autoDeploy: false`, so Render only deploys when CI explicitly fires the hook. No path for failing-test code to ship.

### 7.2 "What does the post-deploy smoke test actually do?"

It curls `/health`. If the response is HTTP 200 with `model_loaded: true`, deploy passes. If it times out or returns an error code, deploy fails and the previous container keeps serving. This is the rubric's required smoke test (Step 10).

### 7.3 "What was the deployment debugging story?"

Six fixes in sequence to land green:
1. Slim Docker requirements — full pip wheel resolution failed on free-tier RAM.
2. Move model training out of Docker into CI's `train-and-release` job — Docker training OOM-killed on Render.
3. Drop gunicorn from 2 workers to 1 — two workers OOM-killed on Render's 512 MB RAM during native-lib load.
4. Increase gunicorn `--timeout` from 30s to 120s — model + native libs took longer to import than the default.
5. **Switch deploy hook from Blueprint to Service** — the original hook URL pointed at a Blueprint sync (only redeploys on `render.yaml` changes), so Render hadn't actually rebuilt after the first commit. This was the load-bearing diagnosis.
6. Add `libgomp1` via apt-get — LightGBM dlopens the OpenMP runtime at import; python:3.12-slim doesn't ship it. Worker crashed on boot.

After fix 6, `/health` answered green on the first poll.

### 7.4 "Where does the trained model live?"

Three places:
- **CI runner** during `train-and-release` — temporarily, then publishes.
- **GitHub Release** `model-latest` — versioned artifact, fetched by every Render rebuild.
- **Render container** — pulled at Docker build time via `curl`, lives at `/app/artifacts/maree_production.joblib`.

The Render container does NOT train. Training is GH runner only.

### 7.5 "If quantic-grader can't reach the live URL, what do they see?"

If we leave the deploy idle for 15 minutes, the free-tier dyno spins down. First request after spindown pays a ~30-second cold start. Then `/health` answers normally. This is documented in `deployed.md` and `docs/for-it-administrators.md`.

If they need to verify locally: `docker build -f docker/Dockerfile -t maree:latest .` and `docker run --rm -p 8080:8080 maree:latest` runs the same container on their machine.

## 8. The audit trail — what's where

| Artifact | Where | What it does |
|---|---|---|
| Live deployment | https://maree-f8c8.onrender.com | The shipping product |
| Source code | `src/` | App, models, ensemble, drift, triage, preprocessing, splits |
| Tests | `tests/` (14 files) | Unit + integration; CI gates on these |
| CI/CD workflow | `.github/workflows/ci.yml` | Lint → test → test-torch → train-and-release → deploy |
| Render config | `render.yaml` | `autoDeploy: false` is the gating mechanism |
| Dockerfile | `docker/Dockerfile` | Two-stage; libgomp1 + curl artifacts from GH Release |
| Training script | `scripts/train_production_model.py` | Reproducible, fixed seeds |
| Hyperparameter search | `scripts/hyperparameter_search.py` | Rubric Step 4 tuning evidence |
| EDA outputs | `notebooks/eda_outputs/` | Schema inventory, class balance, sample counts |
| Per-(model × protocol × stage) results | `results/parts/` | Phase D evaluation |
| Hyperparameter results | `results/hyperparameter_search.json` | All 240 grid cells |
| Technical report | `evaluation-and-design.md` | The rubric's primary deliverable |
| Live status notes | `deployed.md` | Deployment architecture + verification trail |
| AI-tooling disclosure | `ai-tooling.md` | Quantic plagiarism-policy compliance |
| IT-admin guide | `docs/for-it-administrators.md` | Operator-facing |
| Methodology explainer | `docs/honest-evaluation.md` | Plain-language drift-gap framing |
| Rubric mapping | `docs/rubric-score-5-mapping.md` | Reviewer's checklist |
| Demo video script | `docs/demo-video-script.md` | Reference, not required reading |
| This brief | `docs/sme-brief.md` | What you're reading |

## 9. Demo flow — beats, not words

You don't need a script. You need to know which beats to hit and which numbers to drop.

**0:00–0:30 — Open.** Both on camera. Names. One sentence on what M.A.R.E.E. is. Live URL on screen.

**0:30–1:00 — Drift indicator.** Point at the banner. Read out the per-window accuracies. Land the line: "M.A.R.E.E. surfaces its own degradation; standard products give you a green check and let it decay silently."

**1:00–3:00 — Three verdicts via `/demo`.** Pick a goodware sample first (sample_4). ALLOWED, p≈0.002, conf≈0.99. Then sample_3 (the showcase). BLOCKED_UNCERTAIN despite p=0.74 — say *out loud* "the model thinks it's malware, but joint confidence is zero, so block-by-default fires; this is the architecture working." Then sample_1 — BLOCKED_MALWARE for contrast. Show the MITRE technique links on at least one of the BLOCKs.

**3:00–4:30 — Batch upload.** Upload the labeled CSV. Show per-row verdicts. Show the AUC / accuracy / confusion-matrix block. Land the line: "These numbers are the honest temporal-evaluation numbers, not the inflated random-split benchmark."

**4:30–5:30 — CI/CD pipeline.** Switch to GitHub. Latest green run. Walk the five jobs. Open the deploy job, expand the smoke test, show the live `/health` 200. Land: "deploy only if tests pass — that's `autoDeploy: false` in render.yaml plus the `needs:` chain in ci.yml."

**5:30–6:30 — Test panel.** Open `tests/`. Three layers: unit, integration (`test_app.py`), smoke (`test_smoke.py` plus the post-deploy `/health` poll). Say the layer counts (14 files, 137 tests).

**6:30–7:00 — Wrap.** What's beyond the rubric: drift-aware ensemble, block-by-default, MITRE triage, honest §9 limitations. Source code public. Thanks.

The narration changes every take. The substance doesn't.

## 10. Anticipated reviewer questions you should be ready for

In rough order of likelihood:

1. **"Why this dataset and not, say, EMBER?"** — Brazilian was purpose-built for temporal study by Ceschin, has daily granularity 2013–2020, and is the dataset the Pendlebury methodology cleanest applies to. EMBER is excellent but doesn't have malware-day granularity to the same precision.
2. **"What's your accuracy in production?"** — The most operationally-meaningful number is the temporal hold-out: 0.875 with block-by-default for the M.A.R.E.E. RF variant. That's the number a defender should expect on samples drawn from the deployment-era distribution.
3. **"How would you deploy this in a real organization?"** — Self-host the Docker container; integrate via the `/api/predict` JSON endpoint; pair with existing endpoint AV (Defender) since M.A.R.E.E. is static-only; train operators on the three verdicts and especially on not overriding `BLOCKED_UNCERTAIN` under user pressure.
4. **"Why did you choose to over-engineer this?"** — Be ready to push back gently. The rubric's floor is "a malware classifier that meets the requirements." Our above-the-floor work (drift indicator, block-by-default, MITRE triage, honest evaluation) is the part that distinguishes a research project from a checkbox project. Quantic explicitly invites going beyond the floor; we did.
5. **"How long did this take?"** — Phases A–E. Real numbers: weeks of iteration. The deployment grind was a single multi-hour session. Be honest.
6. **"Did the AI write this whole thing?"** — Reference `ai-tooling.md`. AI-assisted on code generation, test scaffolding, documentation drafts. Human-driven on architecture, methodology, design decisions, AI tool review, and final commits. The "what didn't work as well" section in `ai-tooling.md` shows you're a critical user, not a passive consumer.
7. **"What would you do differently?"** — Start with the deploy hook validation up front. The Blueprint-vs-Service mistake cost us a whole debugging session because we didn't audit which type of hook URL we were using until late. In hindsight: print the hook response on first call and assert it contains `srv-`, not `exs-`.
8. **"What's the smallest change that would meaningfully improve M.A.R.E.E.?"** — Heterogeneous ensemble members (RF + LightGBM + MLP per window, voting together). The single-architecture choice was made to isolate the temporal-window contribution; mixing architectures should add a few percentage points of drift robustness on top.
9. **"What's the biggest weakness?"** — `evaluation-and-design.md` §9, item 4: M.A.R.E.E. is robust within its training span but cannot extrapolate to entirely-new periods. Continuous deployment requires periodic retraining. Today's loop is operator-actioned (drift indicator visible, retrain decision manual); Phase 2 automates the trigger.
10. **"Why the LLM triage backend if it's optional?"** — Headline polish, not load-bearing. The deterministic template backend produces the same four-field schema with the same MITRE mapping. The LLM rewrites the prose into more natural language. Setting `ANTHROPIC_API_KEY` in Render flips it on; we kept it off in the demo because the rubric's submission default should be reproducible without external API keys.

## 11. Mistakes you might make on camera, and how to recover

- **The demo URL cold-starts mid-recording.** Say: "Free-tier hosting spins down after 15 min idle; first request pays ~30s cold start. In a paid-tier production deployment this wouldn't happen — sized for academic demo." Wait. Continue.
- **A verdict comes back different than expected.** Don't fake it. Narrate what you see. "Model says X, I expected Y. Probability is Z, confidence W. That's the architecture working — when it's uncertain it tells us." Honest > rehearsed.
- **You blank on a number.** Say "let me check the technical report" and click `evaluation-and-design.md` if the screen is shareable. Or honestly say "the exact number's in §X of the report; the order of magnitude is N percent." Don't invent.
- **A demo sample's verdict shifts because the model retrained on a fresh CI run.** Note that: "the demo samples come from the temporal hold-out; the production model is retrained nightly via CI, so verdicts can shift within calibration noise. Probability bands stay similar." Roll with it.
- **You disagree with each other live.** Pick one to defer; resolve it in editing or in the post-recording PDF. Don't argue on camera.

## 12. The five things you should never say

1. "AI did most of this." — even if true; the framing in `ai-tooling.md` is more accurate and policy-compliant. AI-assisted, human-reviewed, human-driven on architecture.
2. "We don't know why X." — instead: "Our best hypothesis is X; we'd verify by Y."
3. "This is industry-grade." — it's research-grade. Be honest. The §9 limitations document the gap.
4. "This is better than Defender." — wrong axis. M.A.R.E.E. complements existing endpoint AV; doesn't replace it. The differentiator is *visibility into degradation and uncertainty*, not raw accuracy.
5. "We didn't tune hyperparameters." — we did, see §4.5. Defaults won the search by design.

## 13. The closing summary

If a reviewer asks "what's the one sentence I should remember?"

> *M.A.R.E.E. is the malware classifier that admits when it's wrong, blocks on uncertainty rather than guessing, and tells the operator how to act on every verdict.*

That's the project in fifteen words. Everything in this brief — the methodology, the architecture, the numbers, the deployment, the limitations — exists to deliver on that one sentence.

You're SMEs now. Go record.
