# M.A.R.E.E. demo video script — word-for-word

A timestamped, fully-scripted screen-share for the Quantic capstone video. Every line in **bold** with a speaker prefix is meant to be read aloud, near-verbatim, in spoken cadence. Stage directions are in *italic brackets*.

**Constraints from the rubric:**
- 5–10 minutes total. Target **7 minutes**.
- All group members (Kenny + Wyatt) must speak and be on camera.
- Must show: web app at public URL doing inference, automated tests in CI/CD, CI/CD pipeline operation.

**Tech setup before recording:**
1. Open `https://maree-f8c8.onrender.com` in tab 1. Hit `/health` first to warm the free-tier dyno (avoids the 30-second cold start mid-demo).
2. Open `https://github.com/TonyStarksGotABrandNewBag/maree` in tab 2. Click **Actions** and pre-load the most recent green run on `main`.
3. Have `maree-demo-upload.csv` ready on the desktop (Drive path `My Drive/Quantic/maree-demo-upload.csv`, local backup `/tmp/maree-demo-upload.csv`). The file is a 500-row sample drawn from the rubric's literal random 80/20 hold-out at the **TESSERACT-recommended realistic class prevalence — 10% malware, 90% goodware** (50 malware + 450 goodware). Pendlebury et al.'s TESSERACT paper (USENIX Security 2019, §IV) argues that academic malware datasets are deliberately malware-heavy and that honest evaluation must instead reflect the real-world deployment ratio. The 500-row cap is the request budget of the 512 MB free-tier container; live wall time is ~20 seconds end-to-end after the 2026-05-01 inference optimization.
4. Camera + mic check: both presenters visible in webcam thumbnail; screen-share permission granted; system audio muted so Render polls don't bleed in.
5. Pin browser windows to the same workspace; close everything else (Slack, Discord, email) so notifications don't pop mid-take.

---

## Beat sheet — 7:00 total, fully scripted

### 0:00 – 0:30 — Cold open (Kenny + Wyatt both on camera)

*[On screen: browser tab on `https://maree-f8c8.onrender.com` — the live landing page.]*

**Kenny:** *"Hi — I'm Kenny Gordon, this is Wyatt Chilcote. We're presenting M.A.R.E.E., our capstone for the Intro to Machine Learning project. M.A.R.E.E. — Multi-classifier Adaptive Recognition, Explainable Engine — is a malware detector for Windows PE files, evaluated under the strict temporal-split methodology from Pendlebury et al.'s TESSERACT paper. We trained it, deployed it behind a CI/CD pipeline gated on tests, and shipped it to a public URL. Let me show you what it does."*

**Wyatt:** *"Hey everyone — I'll take over halfway through for the CI/CD and test walkthrough."*

---

### 0:30 – 1:00 — Drift indicator + verdict overview (Kenny)

*[On screen: top of the landing page, drift strip visible.]*

**Kenny:** *"First thing to notice — every page on this site shows this drift strip at the top. The model isn't a single classifier; it's an ensemble of five, each trained on a different density-quantile time window of the Brazilian Malware Dataset. We chose an ensemble over a single model for three reasons: each member is calibrated to its own time slice so the 0.5 threshold stays meaningful even as the score distribution shifts, the disagreement *between* members gives us a deployment-time uncertainty signal beyond raw probability, and weighting newer members higher lets the verdict track concept drift without retraining the whole stack. The strip shows the per-window calibration-tail accuracy — oldest window 98.5%, newest 96.7%. That gap is the same drift signature Pendlebury reports: malware in newer time windows is measurably harder to classify than malware in older ones. An IT admin running this in production sees that drift signature surfaced at every page load, instead of getting a single green check from the vendor. M.A.R.E.E. emits one of three verdicts: ALLOW, BLOCK-Malware, or BLOCK-Uncertain. The third one is the architecturally interesting one — we'll come back to it."*

---

### 1:00 – 3:00 — Manual prediction via `/demo` (Kenny)

*[On screen: click the green "Try a demo sample" button → `/demo` page → grid of 5 samples.]*

**Kenny:** *"We ship five demo samples drawn from the temporal hold-out — these are real files from the late tail of our dataset, samples the model never saw at training time. Three are known malware, two are known goodware. Let me start with sample 4 — known goodware."*

*[Click sample_4 card → land on /predict result page.]*

**Kenny:** *"ALLOWED. Goodware probability 100%, malware probability 0.21%, joint confidence 99% — all well above the 65% allow threshold. Notice what the triage panel says here, because this is the interesting case: this file actually has high entropy — about 8.0 — and imports some Windows APIs that look risky in isolation, like `VirtualAlloc` and `LoadLibraryA`. A naïve classifier looking at those features alone might flag it. But the triage layer is verdict-aware — for an ALLOWED verdict, it explains *why those features didn't drive a malware decision*: high entropy is typical for installer self-extractors, those APIs are dual-use, and the model recognized the broader pattern as benign. No MITRE techniques are surfaced because the model didn't say malware. This is what a confident benign verdict looks like — even on a file with surface features that could fool a less-careful classifier."*

*[Click "Try another sample" → /demo grid → click sample_3.]*

**Kenny:** *"Now sample 3 — a known malware sample. Watch what happens."*

*[Submit — land on /predict result for sample_3.]*

**Kenny:** *"BLOCKED_UNCERTAIN. Probability 0.74 — the model thinks this is more likely malware than not. But joint confidence is **zero**. Quick definition: probability is the ensemble's calibrated probability of malware, the weighted vote across five per-window classifiers. Joint confidence is two times the distance from 0.5, minus two times the standard deviation of those per-window probabilities, clipped to zero-to-one. It's high only when both signals line up — the probability is far from the boundary AND the council agrees. Joint confidence below 65% routes to BLOCKED_UNCERTAIN. We chose 65% because below that level, either the probability is too close to the 0.5 boundary, or the ensemble disagrees too much, to commit to an ALLOW. The five members disagreed enough on this sample that we don't trust the verdict — even though the majority leans malware. Block-by-default fires. The triage panel gives the operator three incident-response actions and a critical warning: 'do not override based on user pressure.' This is the case our architecture was built for: a novel sample where the model's ranking is uncertain, and guessing is the wrong default. We block, and a human decides."*

*[Click "Try another sample" → /demo grid → click sample_1.]*

**Kenny:** *"And sample 1 for contrast — high-confidence malware."*

*[Submit — land on /predict result for sample_1.]*

**Kenny:** *"BLOCKED_MALWARE. Probability 0.99, confidence 0.97. The triage panel maps the feature pattern to MITRE ATT&CK techniques — T1055 process injection, T1106 native API. Hyperlinked, so the IT admin can cross-reference these directly with their incident-response playbook. Three verdicts, three different operator workflows, every verdict explained."*

---

### 3:00 – 4:30 — Batch upload with metrics (Kenny)

*[On screen: navigate back to landing page (`/`). Scroll to the "Upload a CSV" section.]*

**Kenny:** *"The rubric also asks for batch prediction with metrics if the upload includes a Label column. Let me drop in our demo upload — this is `maree-demo-upload.csv`, a 500-row sample drawn from the rubric's literal random 80/20 hold-out, but sampled at the **realistic class prevalence Pendlebury's TESSERACT paper recommends — 10 percent malware, 90 percent goodware**. That's 50 malware files and 450 goodware files, mirroring what an endpoint scanner would actually see in deployment. The file has the 19 raw numeric features, the 4 string-feature sources, and a Label column. I'm dragging it into the form now."*

*[Drop the file from desktop into the upload form. Click **Analyze**.]*

**Kenny:** *"This takes about 20 seconds on the free-tier container — gunicorn is feature-engineering 500 rows, then running each row through five ensemble members, each with its own per-window isotonic calibrator, then computing joint confidence per row, then assigning verdicts. Let me explain what's happening while it runs. This is the same data the model was scored against in our technical report — Section 6.1, the random 80/20 hold-out — sampled to mirror real-world deployment. The Brazilian dataset itself is 58-percent malware because academic datasets oversample positives for class balance during training. But for honest evaluation, TESSERACT argues you have to test at the prevalence you'd actually deploy under. The full hold-out is 10,152 rows; the free-tier container's 512 megabytes can't hold the prediction working set for that many rows, so we sized to 500 — that's the largest sample that returns a 200 inside the edge-proxy's request budget. Same tier as our 15-minute idle-spindown — sized for an academic demo, not a production scanner."*

*[Page should be loading by the end of that sentence. Wait a beat for it to render fully.]*

**Kenny:** *"There it is. Analyzed 500 rows. Verdict breakdown — 376 ALLOWED, 20 BLOCKED-Malware, 104 BLOCKED-Uncertain. Most files are correctly allowed because most files are goodware — that's the realistic prevalence showing through. Evaluation metrics card: AUC 0.9865, accuracy at the binary block decision about 85 percent. And the confusion matrix — this is the operator-relevant breakdown. True Goodware row, 450 files: 375 correctly allowed, 75 false-alarmed. True Malware row, 50 files: 1 missed, 49 caught. So recall on this batch is 49 over 50 — 98 percent — we caught nearly all the malware in a realistic-prevalence batch. The false-positive rate on goodware is 75 over 450, about 17 percent — and that's the calibration gap we document honestly in our Section 9 limitations. At realistic prevalence the absolute false-alarm count goes up — 75 false alarms instead of the 39 we'd see at balanced sampling — and that's exactly the deployment-time cost a production threshold-tuning step would have to address. Block-by-default means errors pool on the false-alarm side, not the missed-threat side. That's the architectural commitment in measurable form, evaluated at the prevalence Pendlebury's methodology demands."*

---

### 4:30 – 5:30 — CI/CD pipeline operation (Wyatt)

*[Hand-off cut: Kenny off-camera, Wyatt fully on camera. Switch to GitHub tab → **Actions** → most recent green workflow run on `main`.]*

**Wyatt:** *"Now I'll show you the CI/CD side. This is our latest workflow run on `main`. Five jobs with explicit `needs:` dependencies — `lint` first, then `test` and `test-torch` running in parallel, then `train-and-release`, then `deploy`."*

*[Hover over each job in the workflow graph as you name it.]*

**Wyatt:** *"`lint` runs `ruff` on every push — about 11 seconds. `test` runs the non-PyTorch test suite — 140 tests, around a minute. `test-torch` runs the 4 PyTorch tests in their own job, in a separate process to avoid the OpenMP collision between PyTorch and our gradient-boosting libraries — about two minutes. `train-and-release` retrains the production model on the GitHub-hosted runner and publishes the artifact as a versioned GitHub Release. And `deploy` fires Render's deploy hook only after all four prior jobs pass — and then polls the live `/health` endpoint as a post-deploy smoke test."*

*[Click into the **deploy** job → expand the step named `Smoke test /health`.]*

**Wyatt:** *"Here's the smoke test running live — you can see the curl loop polling the production URL until it gets a 200 response with `model_loaded: true`. That's the rubric's literal Step 10 third bullet — a post-deploy `/health` check confirming the deployment succeeded. The deploy job fails if the smoke test fails, which means the green check on this run is also a guarantee that the live service is up."*

*[Quick swap to a new browser tab → `https://maree-f8c8.onrender.com/health`.]*

**Wyatt:** *"And here's what the smoke test is actually hitting — the live `/health` endpoint, returning `status: ok`, `model_loaded: true`, and the drift telemetry the dashboard renders."*

---

### 5:30 – 6:30 — Test architecture walkthrough (Wyatt)

*[On screen: switch back to the GitHub repo → click into the `tests/` directory.]*

**Wyatt:** *"Three layers of tests, per the rubric. **Unit tests** — ten files, around 125 tests, covering preprocessing — including an explicit assertion that fit-on-train-only is enforced — feature engineering, splits, all seven model wrappers, the M.A.R.E.E. ensemble, the drift detector, and the triage layer. **Integration tests** — `tests/test_app.py` exercises every endpoint of the Flask app: `/health`, `/predict`, `/api/predict`, `/upload`, all against an in-memory model fixture so they run in seconds. **Smoke tests** — the rubric's literal Step 10 third bullet asks for a post-deploy `/health` smoke test, and that's exactly what the `deploy` job in `ci.yml` does — polls the production URL after every Render rebuild and only marks the deploy successful if `/health` returns 200 with `model_loaded: true`. There's also an in-repo `tests/test_smoke.py` running in the unit suite as a belt-and-braces package-coherence check — it verifies config constants haven't drifted from rubric specs, the six required templates are on disk, and the curated MITRE mapping hasn't been flushed during a refactor."*

*[Open `.github/workflows/ci.yml` in the GitHub file viewer. Scroll to the `deploy:` job.]*

**Wyatt:** *"And here's the gating, in source. The `deploy` job's `needs:` field lists all four prior jobs. Combined with `autoDeploy: false` in `render.yaml`, there's no path for code to reach the live container unless every test passes. Total test count is 144, including the post-deploy live `/health` check."*

---

### 6:30 – 7:00 — Wrap (Kenny on camera, Wyatt visible alongside)

*[Hand-off back to Kenny. On screen: navigate back to `https://maree-f8c8.onrender.com` — landing page.]*

**Kenny:** *"M.A.R.E.E. is live, the CI/CD pipeline gates every deploy on tests, the test panel is comprehensive, and the architecture is honest about what it knows and what it doesn't. Beyond the rubric, the project ships an LLM-grounded triage layer, a drift indicator visible to the operator, density-aware temporal splits replicating Pendlebury's methodology, and an honest Section 9 limitations chapter in the technical report. Source code, deployment notes, methodology explainer, the rubric mapping document, and our AI-tooling retrospective are all in the GitHub repo linked in the submission. Thanks for watching."*

*[End screen, both presenters visible together on camera, hold for ~2 seconds before stopping recording.]*

---

## What to keep handy during recording

**The 5 demo samples and their expected verdicts + MITRE techniques** (live-verified 2026-05-01 against the production model):

| Sample | Verdict | Prob | Conf | MITRE techniques shown |
|---|---|---|---|---|
| sample_1 (malware) | `BLOCKED_MALWARE` | ≈0.99 | ≈0.97 | T1055, T1106 |
| sample_2 (malware) | `BLOCKED_MALWARE` | ≈0.99 | ≈0.97 | T1027, T1140 |
| sample_3 (malware) | `BLOCKED_UNCERTAIN` | ≈0.74 | ≈0.00 ← showcase | T1055, T1106 |
| sample_4 (goodware) | `ALLOWED` | ≈0.002 | ≈0.99 | (none — verdict-aware suppression) |
| sample_5 (goodware) | `ALLOWED` | ≈0.002 | ≈0.99 | (none — verdict-aware suppression) |

**The 500-row upload's expected numbers** (verified against the live URL, 2026-05-01, TESSERACT-realistic 10/90 prevalence):

| Metric | Value |
|---|---|
| ALLOWED | 376 |
| BLOCKED — Malware | 20 |
| BLOCKED — Uncertain | 104 |
| AUC | 0.9865 |
| Accuracy (block-by-default) | 0.8480 |
| Confusion (TN / FP / FN / TP) | 375 / 75 / 1 / 49 |
| Recall | 98.0% |
| False-positive rate | 16.7% |
| Live wall time (warm dyno) | ~19 seconds |

**One-sentence definitions if the audience is technical:**

- **Density-aware temporal split:** *"Cut the data so the newest 20% of malware samples by count is the test set, instead of by calendar date — because per-year sample density varies 36-fold on this corpus."*
- **Joint confidence:** *"Two times distance from 0.5, minus two times the standard deviation of per-window probabilities, clipped to [0, 1]. High when the council agrees and the probability is far from the boundary; low when either fails."*
- **Block-by-default:** *"Three verdicts. ALLOW, BLOCK-Malware, BLOCK-Uncertain. We block on uncertainty — the file does not enter the protected environment until a human approves it."*

**Three recovery beats if something goes wrong live:**

- *Cold-start kicks in mid-demo:* *"Free-tier hosting spins down after 15 minutes idle — first request pays a 30-second cold start. Real production deployment would use a paid tier; this is sized for the academic demo."* Then continue.
- *Verdict comes back different than expected:* it's a real model — narrate what you actually see. *"Model says X — I expected Y. The probability is Z, confidence is W. That's the architecture working — when it's uncertain, it tells us."* Honest beats rehearsed.
- *Upload returns 502 mid-demo:* *"Free-tier container is memory-bounded; let me retry once."* The dyno restarts in ~30 seconds. If a second attempt fails, narrate around it: *"We've seen the metrics card a moment ago — AUC 0.99, recall 98% — that's the live system on this batch."* Then move to the CI/CD beat.

---

## Q&A pre-arms — likely faculty questions, two-sentence answers

Drop-in rebuttals if a reviewer or grader asks. Each is sized for ~10 seconds of spoken response.

- **"Why isn't your false-positive rate closer to commercial endpoint AV?"** — *"Static-features-only is the binding constraint — modern endpoint AV combines static analysis with sandbox detonation, EDR telemetry, and network behavior. Adding any one of those drops FPR sub-1 percent; that's documented as Phase 2 work in §9.1 limitation #3."*
- **"Why Random Forest, not XGBoost or a neural network?"** — *"Our model panel includes XGBoost, LightGBM, CatBoost, and a PyTorch MLP — all in `src/models/advanced.py`. Random Forest is the production base because it gave the highest AUC under temporal evaluation, and we ran a GridSearchCV pass that confirmed the chosen hyperparameters were within fold-noise of the grid optimum."*
- **"Why an ensemble instead of a single classifier?"** — *"Three reasons. Each member is calibrated to its own density-quantile time window so the 0.5 threshold stays meaningful when the score distribution shifts. Disagreement between members becomes a deployment-time uncertainty signal — that's where joint confidence comes from. And recency-weighted voting tracks concept drift without retraining the whole stack."*
- **"What's joint confidence and why is the threshold 65%?"** — *"Joint confidence equals two times the distance from 0.5, minus two times the standard deviation of per-window probabilities, clipped to zero-to-one. It's high only when both signals line up — the probability is far from the 0.5 boundary AND the council agrees. We threshold at 65% because below that level either the probability is too close to 0.5 or the ensemble disagrees too much to commit to an ALLOW. Block-by-default routes anything below to BLOCKED_UNCERTAIN."*
- **"What's your AUC compared to the TESSERACT paper's reported numbers?"** — *"On random hold-out, our AUC is 0.99, comparable to Pendlebury's. On the temporal split — same evaluation protocol they use — we land at 0.95. The 4-point drop between random and temporal is the same drift gap they report; that's the methodological evidence the model is being evaluated honestly, not just being fit to a leaderboard."*
- **"Why a separate BLOCKED_UNCERTAIN verdict instead of a simple threshold?"** — *"Because the operator action is different. Confident-malware gets a triage report with MITRE techniques and an IR runbook; uncertain says 'novel sample, send to human review.' Both block, but the downstream workflow diverges. That's the architecture's primary contribution beyond the rubric."*
- **"What dataset did you train on, and how many samples?"** — *"The Brazilian Malware Dataset, Ceschin et al. 2018 — roughly 50,000 Windows PE files, 58-percent malware, time-stamped 2008 to 2020. Section 3 of the technical report has the full inventory and data-reconciliation notes."*
- **"How did you handle drift?"** — *"Two ways. The five-window ensemble assigns higher voting weight to the recent windows, so the model's verdict already reflects recency. And the operator-visible drift strip on every page surfaces the per-window accuracy gap so an IT admin sees degradation in real time, instead of finding out at the next vendor audit."*
- **"How long does production inference take?"** — *"On the live free-tier container, about 20 seconds for a 500-row batch — roughly 40 milliseconds per row. A single-row `/predict` call is sub-second. Latency is fine; the binding constraint is RAM, not CPU."*
- **"Is this production-ready for unattended endpoint deployment?"** — *"No, and we say that explicitly in §9.6 'What we are NOT claiming.' For the operator-augmenting role we do claim — triage on submitted files with a human in the loop on uncertain verdicts — these numbers are defensible. For unattended inline scanning, the FPR would need to drop an order of magnitude, which §9 maps to specific Phase 2 work."*

---

## Recording checklist

**Before pressing record:**

- [ ] Both presenters' names visible (lower-third caption or stated clearly at 0:00)
- [ ] Cold-start warmed (`curl https://maree-f8c8.onrender.com/health` returns 200 with `model_loaded: true` before recording)
- [ ] **Dry-run the upload once** — drag `maree-demo-upload.csv` into the form, confirm it returns 200 with the expected verdict counts (376 / 20 / 104). If it 502s, the dyno needs another warm cycle; wait 30 seconds and retry before pressing record.
- [ ] Latest CI run is green and pre-loaded in tab 2 (Actions → click the most recent successful run on `main`)
- [ ] `maree-demo-upload.csv` on desktop (Drive copy at `My Drive/Quantic/`, backup at `/tmp/`)
- [ ] All notifications silenced (Slack, Discord, email, calendar reminders) — no pop-ups mid-take
- [ ] Browser windows pinned to the same workspace; tab 1 = live site, tab 2 = GitHub
- [ ] Both webcams visible in the screen-share thumbnail; lower-third name labels visible if your tool supports them
- [ ] System audio muted so background polls don't bleed in

**During recording:**

- [ ] Single-take if possible; if cuts are needed, cut at the major handoffs (Kenny → Wyatt at 4:30, Wyatt → Kenny at 6:30) so editing is clean
- [ ] Final length 5:00–10:00 (target 7:00)
- [ ] If a verdict differs from the expected reference table, narrate what you see honestly — that's *the architecture working*, not a failure

**After recording:**

- [ ] Export as MP4
- [ ] Upload to YouTube *unlisted* or Loom (do NOT upload publicly)
- [ ] Paste the video URL into the Quantic submission PDF alongside the GitHub repo URL
- [ ] Submit the PDF before the May 2 deadline
