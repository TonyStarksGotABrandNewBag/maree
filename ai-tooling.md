# AI tooling

Per the Quantic project guidelines (page 2: *"you are highly encouraged to utilize leading AI code generation models/AI IDEs to assist in rapidly producing your solution"*), this document records how AI tools were used during the build.

## Tools used

- **Claude (Anthropic)** — primary collaborator. Used via Claude Code (CLI) for repository scaffolding, code generation, code review, technical writing (README, docs, evaluation report), and design discussions throughout the project.

## What worked well

The collaboration was strongest on **specific, well-scoped technical translations** where we could describe the target precisely and Claude could produce working code or prose against that target. Concrete examples from this build:

- **Translating academic methodology into working code.** Pendlebury et al.'s TESSERACT methodology specifies temporal splits but the paper does not provide reference code. We described "density-aware quarter-or-month boundaries chosen so each window contains roughly equal malware sample count, because per-year density varies 36×" and Claude produced `src/data/splits.py:temporal_density_split()` and `temporal_window_quantiles()` against that brief. The implementation correctly chose the `2015-09-15` cutoff from the data itself rather than a preset calendar boundary — exactly the methodological intent. Same pattern for the per-window isotonic-regression calibration in `src/models/ensemble.py`.

- **Generating the rubric-required model panel consistently.** Four baselines (LR, DT, RF, PyTorch MLP) plus three gradient-boosting families (XGBoost, LightGBM, CatBoost) all conform to the same `.fit()` / `.predict()` / `.predict_proba()` interface. Claude scaffolded all seven with consistent hyperparameter conventions, OpenMP thread-cap discipline (`n_jobs=4` everywhere — see `src/models/baselines.py:make_random_forest`), and lazy torch import (the deferred import in `TorchMLPClassifier` to avoid OpenMP collisions when XGBoost/LightGBM/CatBoost run in the same process). This boilerplate-with-discipline is exactly the kind of work AI is fastest at.

- **Test scaffolding at scale.** 14 test files and ~137 tests in `tests/` covering features, preprocessing, splits, ensembles, models (CPU and torch), drift detector, triage, and the Flask app. We described what each module's invariants were; Claude wrote the assertions. The fit-on-train-only discipline test (`tests/test_preprocessing.py:test_train_only_fit_then_transform_test`) is a good example — we said "the test should verify that test-fold mean/std deviates from train's centered/scaled distribution, because that deviation is the empirical fingerprint of correctly-fit-on-train-only scaling," and the resulting test caught a real preprocessing bug during one refactor.

- **Diagnosis from sparse evidence during the deployment crisis.** The Render deployment took six sequential architectural fixes to land green: in-container training → out-of-Docker training, full-pip wheels → slim deps, model-baked-into-image → model-via-GitHub-Release, two gunicorn workers → one (free-tier RAM), 30s timeout → 120s, and finally `libgomp1` for LightGBM's OpenMP runtime. The standout moment was Claude spotting the **Blueprint-vs-Service deploy-hook bug** from a single line in the deploy hook's response (`https://dashboard.render.com/blueprint/exs-...`) — the URL contained `blueprint` rather than the expected `srv-` prefix, which Claude flagged as "the hook is the wrong type, that's why Render hasn't actually rebuilt the last several pushes." Recognizing that signal in noise was load-bearing for the eventual fix.

- **Wholesale documentation prose.** The capstone documentation pass — `docs/for-it-administrators.md`, `docs/honest-evaluation.md`, `docs/rubric-score-5-mapping.md`, `evaluation-and-design.md` §9 Limitations — was drafted by Claude against detailed scope briefs (target audience, what to cover, what to honestly disclaim) and then edited by us for voice and accuracy. The IT-admin guide's "what this tool is not" section is an example: Claude produced an honest scope-disclaimer paragraph without us having to ask for the negative framing — the right reflex for a defender's documentation.

- **Pre-emptive surfacing of methodological pitfalls.** Several non-obvious decisions came from Claude flagging an issue we would otherwise have hit later: goodware lacking reliable per-sample timestamps (the `FormatedTimeDateStamp` field spans 1969–2100), and the resulting decision to bootstrap goodware uniformly across folds per CADE/Pendlebury convention. Same for the calibration-vs-ranking distinction (AUC stays high under temporal split, but accuracy at threshold collapses) — Claude proposed reporting both and the resulting §4.2.1 table is the sharpest drift signal in the entire technical report.

## What didn't work as well

The collaboration was weakest in three categories — and in each, the failure mode was specific enough to be useful as a guideline rather than a fatal flaw.

- **Claude could not see external systems and would generate plausible-but-wrong fixes when blocked on visibility.** The most expensive instance was the deployment debugging: Render's dashboard was the source of truth for what was actually happening on the platform, and Claude could not see it. So when `/health` kept timing out, Claude proposed slim requirements, then 1-worker gunicorn, then larger timeouts — each plausible, each landing on a different layer of the problem. The actual issue (wrong deploy-hook URL → Render had not been rebuilding at all for the previous several pushes) only surfaced once the human pasted enough Render UI evidence for Claude to recognize the pattern. Lesson: when AI is debugging an opaque external system, **the human's job is to be the eyes; don't let the AI keep speculating without dashboard evidence.** The four pre-Blueprint-discovery fixes were not wasted (each was a real improvement), but the order would have been better if we had paused for dashboard evidence sooner.

- **Verbosity bias.** Claude's default response style is more detailed than this project warranted. We had to explicitly steer toward terse responses, drop trailing summaries, skip narration of internal reasoning, and avoid adding "future-proofing" abstractions that the immediate task did not need. The repository's CLAUDE.md eventually included explicit instructions on this, and adherence improved markedly afterward — but the early commits show the trace of the unmoderated style, with longer-than-necessary commit messages and over-commented code that we cleaned up in subsequent passes.

- **AI peer review missed bugs the test suite caught.** Twice during the build, Claude generated code that passed Claude's own review but was caught by the test suite. The most memorable was a calibration bug introduced during a refactor of `src/models/drift_detector.py:compute_weights()` — the recency-weight exponential was off-by-one in how it indexed the window list, which Claude did not flag on review but `tests/test_drift_detector.py` immediately failed on. **Tests catch what review does not.** This is true for human reviewers too, of course, but it is worth saying explicitly: do not skip writing tests on the assumption that AI code review substitutes for them.

- **Tendency to over-engineer when the brief was vague.** Several early commits added feature flags, fallback layers, or error-handling branches for failure modes that could not actually occur given the surrounding code. We had to add a CLAUDE.md instruction ("don't add error handling, fallbacks, or validation for scenarios that can't happen") and the pattern improved, but not before some unnecessary `try/except Exception` blocks crept in — most of which were removed during code-review passes.

- **Convention drift across files.** Claude correctly inferred most of the project's conventions (module docstrings open with a one-line summary, type hints everywhere, `from __future__ import annotations` at the top, etc.), but occasionally drifted — e.g., switching import ordering style between commits, or using `Optional[X]` in one file and `X | None` in another. Lint (`ruff`) caught the syntactic version of this; the stylistic version required human review.

- **AI cannot read the Quantic rubric PDF directly.** The rubric requirements landed in the codebase as comments in `src/preprocessing.py`, `src/models/baselines.py`, etc., based on us paraphrasing the PDF to Claude. This worked, but it is one more place where the human is the bottleneck — an integration that read the rubric directly would have been faster.

## Honest accounting

Following Quantic's plagiarism policy, every contribution from AI tools is acknowledged. Code, documentation, and design decisions originated through collaboration between the human authors (Kenny Gordon and Wyatt Chilcote) and Claude. Specific patterns:

- Code generation: AI-assisted, human-reviewed and tested.
- Architecture and design decisions: human-driven, AI used as a sounding board.
- Documentation drafts: AI-assisted, human-edited for accuracy.
- Final commits and submissions: human-authored.
