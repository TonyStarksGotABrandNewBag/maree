# M.A.R.E.E. demo video script

A timestamped beat-by-beat for the Quantic capstone screen-share video.

**Constraints from the rubric:**
- 5–10 minutes total. Target **7 minutes**.
- All group members (Kenny + Wyatt) must speak and be on camera.
- Must show: web app at public URL doing inference, automated tests in CI/CD, CI/CD pipeline operation.

**Tech setup before recording:**
1. Open https://maree-f8c8.onrender.com in one browser tab. Hit `/health` first to warm the free-tier dyno (avoids the 30s cold-start mid-demo).
2. Open https://github.com/TonyStarksGotABrandNewBag/maree in a second tab. Pre-load the latest green CI run (Actions → click the most recent successful run on `main`).
3. Have a labeled-CSV ready for the upload demo. Easiest source: ~50–100 rows from `data/brazilian-malware-dataset/goodware-malware/malware-by-day/2020-09-01.csv` (or any late-period file) concatenated with ~50 rows from `goodware.csv`. Add a `Label` column (1 for malware rows, 0 for goodware rows). Save as `demo_upload.csv`.
4. Camera + mic check: both presenters visible in webcam thumbnail; screen-share permission granted; system audio off so Render polls don't bleed in.
5. Pin the browser windows to the same workspace; close everything else (Slack, Discord, email — anything that could pop a notification mid-recording).

---

## Beat sheet — 7:00 total

### 0:00 – 0:30 — Cold open + framing (Kenny on camera, Wyatt brief intro)

**On screen:** Browser tab on https://maree-f8c8.onrender.com (the live landing page).

**Kenny:** "Hi — I'm Kenny Gordon, this is Wyatt Chilcote. We're presenting M.A.R.E.E., our capstone for the Intro to Machine Learning project. M.A.R.E.E. is a multi-classifier malware detector for Windows PE files, evaluated under the strict temporal-split methodology from Pendlebury et al.'s TESSERACT paper. We trained and deployed it under a CI/CD pipeline gated on tests. Let me show you what it does."

**Wyatt** *(brief wave / hello on camera)*: "Hey everyone — I'll take over later for the CI/CD walkthrough."

### 0:30 – 1:00 — Drift indicator and verdict overview (Kenny)

**On screen:** Top of the landing page, drift banner visible.

**Kenny:** "First thing to notice — every page shows this drift banner. The model is an ensemble of 5 classifiers, each trained on a different temporal slice of the Brazilian Malware Dataset. The banner shows the per-window calibrated accuracy: oldest 98.5%, newest 96.7% — so the threat distribution is genuinely getting harder year over year, even within training. An IT admin running this in production sees that degradation in real time, instead of getting a single green check from the vendor. M.A.R.E.E. emits one of three verdicts: ALLOW, BLOCK-malware, or BLOCK-uncertain. The third one is the interesting one — we'll come back to it."

### 1:00 – 3:00 — Manual prediction via `/demo` (Kenny)

**On screen:** Click "Try a demo sample" → `/demo` → grid of 5 samples.

**Kenny:** "We ship 5 demo samples drawn from the temporal hold-out set — these are real files from late 2015 to 2020 that the model never saw at training time. Let me start with **sample 4** — known goodware."

**[Click sample_4 → /predict result]**

**Kenny:** "ALLOWED, probability of malware 0.002, joint confidence 0.99. The model is confident it's benign and confident in that confidence. Triage panel below shows the 'why' — low entropy, no dangerous API imports, no packer signature. Plain English."

**[Click "Try another sample" → pick sample_3 — the showcase]**

**Kenny:** "Now sample 3 — a known malware sample. Watch what happens."

**[Submit]**

**Kenny:** "BLOCKED_UNCERTAIN. Probability 0.74 — the model thinks this is more likely malware than not. But joint confidence is **zero**. The 5 ensemble members disagreed enough that we don't trust the verdict. Block-by-default fires. The triage panel — see this section — gives the operator three IR actions including the explicit 'do not override based on user pressure' warning. This is the case our architecture is built for: a novel sample where ranking is uncertain, and where 'guess' is the wrong default. We block, and the human decides."

**[Click sample_1 → BLOCKED_MALWARE for contrast]**

**Kenny:** "And sample 1 — high confidence malware. BLOCKED_MALWARE, p=0.99, confidence 0.97. Triage maps the feature pattern to MITRE ATT&CK techniques — T1027 obfuscation, T1106 native API. Hyperlinked. The IT admin can cross-reference these with their incident-response playbook."

### 3:00 – 4:30 — Batch upload with metrics (Kenny)

**On screen:** Back to landing page, click "Upload a CSV".

**Kenny:** "The rubric also asks for batch prediction with metrics if the upload has labels. Let me upload our `demo_upload.csv` — about 100 rows split between malware and goodware, with a Label column."

**[Drop file → submit]**

**Kenny:** "Per-row verdicts at the top — you can see the mix of ALLOWED, BLOCKED_MALWARE, BLOCKED_UNCERTAIN. And because the upload included Labels, M.A.R.E.E. ran an evaluation: **AUC**, **accuracy at the binary block decision**, and a **confusion matrix**. Note that the accuracy here is on late-period data the model never saw, so this is the honest temporal-evaluation number, not the inflated random-split number."

*(If the AUC/accuracy looks bad on the upload — that's expected and you can lean into it: "These numbers reflect the drift gap we documented in our technical report — late-period data is harder than the training distribution, and that's exactly the methodological point of the project.")*

### 4:30 – 5:30 — CI/CD pipeline operation (Wyatt)

*(Hand off — Wyatt on camera now)*

**On screen:** Switch to GitHub tab → Actions → most recent green run.

**Wyatt:** "Now I'll show you the CI/CD side. Here's our latest workflow run on `main`. Five jobs in sequence:"

**[Hover over each]**

**Wyatt:** "**lint** runs `ruff` on every push — 11 seconds. **test** runs the non-torch test suite, 133 tests, 52 seconds. **test-torch** runs the PyTorch tests in their own job — separate process to avoid the OpenMP collision between PyTorch and our gradient-boosting libs. About 2 minutes. **train-and-release** retrains the production model on the GitHub-hosted runner and publishes the artifact as a versioned GitHub Release. **deploy** fires Render's deploy hook only after all four prior jobs pass — and then polls the live `/health` endpoint as a post-deploy smoke test."

**[Click into the deploy job → expand "Smoke test /health"]**

**Wyatt:** "You can see the smoke test polling the live endpoint and getting a 200 with the model-loaded flag set. That's the rubric's fail-safe: deploy only if every test passes."

### 5:30 – 6:30 — Test architecture walkthrough (Wyatt)

**On screen:** Switch to GitHub repo → `tests/` directory.

**Wyatt:** "Three layers of tests, per the rubric. **Unit tests** — fourteen files, around 125 tests covering preprocessing (fit-on-train-only enforced by an explicit assertion), feature engineering, splits, all seven model wrappers, the M.A.R.E.E. ensemble itself, the drift detector, and the triage layer. **Integration tests** — `test_app.py` exercises every endpoint of the Flask app: `/health`, `/predict` form route, `/api/predict` JSON route, `/upload` file route, all against an in-memory model fixture so they run in seconds. **Smoke tests** — the rubric's literal Step 10 third bullet asks for a *post-deploy `/health` smoke test*, and that's exactly what the deploy job in `ci.yml` does — it polls the production URL after every Render rebuild and only marks the deploy successful if `/health` answers HTTP 200 with `model_loaded: true`. There's also `tests/test_smoke.py` running in the unit suite as a package-coherence belt-and-braces — it verifies config constants haven't drifted from the rubric's specs, the six required templates are on disk, and the curated MITRE mapping hasn't been flushed."

**[Open `.github/workflows/ci.yml` briefly to show the gating]**

**Wyatt:** "And here's the gating. The `deploy` job's `needs:` field lists all four prior jobs. Combined with `autoDeploy: false` in `render.yaml`, there's no path for code to reach Render unless every test passes."

### 6:30 – 7:00 — Wrap and where to read more (Kenny)

**On screen:** Back to https://maree-f8c8.onrender.com — landing page.

**Kenny:** "M.A.R.E.E. is live, the CI/CD pipeline is gating, the test panel is comprehensive. Beyond the rubric, the project ships an LLM-grounded triage layer, a drift indicator visible to the operator, density-aware temporal splits replicating the Pendlebury methodology, and an honest §9 limitations section in the technical report. Source code, deployment notes, methodology explainer, and the rubric mapping are all in the GitHub repo. Thanks for watching."

**[End screen, both presenters on camera]**

---

## What to keep handy during recording

- **The 5 demo samples and their expected verdicts** (so you can pick the showcase paths confidently):
  - sample_1 (malware) → `BLOCKED_MALWARE`, p≈0.99, conf≈0.97
  - sample_2 (malware) → `BLOCKED_MALWARE`, p≈0.99, conf≈0.97
  - sample_3 (malware) → `BLOCKED_UNCERTAIN`, p≈0.74, conf≈0.00 ← the showcase
  - sample_4 (goodware) → `ALLOWED`, p≈0.002, conf≈0.99
  - sample_5 (goodware) → `ALLOWED`, p≈0.002, conf≈0.99

- **One-sentence definitions you can grab if the audience is technical:**
  - **Density-aware temporal split:** "Cut the data so the newest 20% of malware samples by count is the test set, instead of by calendar date — because per-year sample density varies 36× on this corpus."
  - **Joint confidence:** "Two-times distance from 0.5, minus the standard deviation of per-window probabilities. High when the council agrees and the probability is far from the boundary; low when either fails."
  - **Block-by-default:** "Three verdicts. ALLOW, BLOCK-malware, BLOCK-uncertain. We block on uncertainty — the file does not enter the protected environment until a human approves it."

- **Two recovery beats** if something goes wrong live:
  - If the cold-start kicks in mid-demo: "Free-tier hosting spins down after 15 minutes idle — first request pays a 30-second cold start. Real production deployment would use a paid tier; this is sized for the academic demo." Then continue.
  - If a verdict comes back different than expected: it's a real model — just narrate what you actually see. "Model says X — I expected Y. The probability is Z, confidence is W. That's the architecture working — when it's uncertain, it tells us." Honest > rehearsed.

## Recording checklist

- [ ] Both presenters' names visible in the recording (lower-third caption or just say them clearly at the top — rubric requires both members on camera)
- [ ] Cold-start warmed (`curl https://maree-f8c8.onrender.com/health` returns 200 before recording starts)
- [ ] Latest CI run is green and pre-loaded in a second tab
- [ ] `demo_upload.csv` ready on desktop
- [ ] All notifications silenced
- [ ] Single-take if possible; if you cut, cut between the major handoffs (Kenny → Wyatt at 4:30, Wyatt → Kenny at 6:30) so editing is clean
- [ ] Final length 5:00–10:00 (target 7:00)
- [ ] Export as MP4, upload to YouTube *unlisted* or Loom — paste link into the submission PDF
