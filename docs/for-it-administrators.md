# M.A.R.E.E. for IT administrators

This is the operator-facing guide. It assumes you run a small-to-medium IT environment (school district, nonprofit, small business) and want a malware classifier that *tells you what it doesn't know*, not just one that says "yes" or "no" with hidden uncertainty.

If you only have five minutes, read §1 (what M.A.R.E.E. tells you), §3 (the three verdicts), and §6 (what to do when you don't trust a verdict).

---

## 1. What M.A.R.E.E. tells you that Defender doesn't

A standard endpoint classifier surfaces one thing: *enabled* / *not enabled*. Behind that green check, the model is silently degrading as the threat landscape evolves, but the operator never sees that degradation. M.A.R.E.E. exposes three signals on every page of the UI:

| Signal | Where you see it | What to do with it |
|---|---|---|
| **Drift indicator** | Banner at the top of every page — `n_active_windows`, oldest/newest per-window calibrated accuracy | If the newest-window accuracy drops below the oldest by more than a few points, the threat distribution has shifted. Schedule a retrain (Phase 2 will automate this). |
| **Per-verdict confidence** | On every prediction — `probability` and `joint confidence` numbers next to the verdict pill | Confidence < 0.50 → the council of classifiers disagreed or the model is sitting near the decision boundary. Treat the verdict as "block + investigate", not "block + done". |
| **MITRE ATT&CK techniques** | On every blocked file — hyperlinks to attack.mitre.org for every technique the feature pattern matches | Lets you quickly cross-reference the verdict against your incident-response playbooks. |

The promise: when M.A.R.E.E. is wrong, the wrongness is *visible* before it bites.

## 2. Two ways to deploy

| Mode | When to pick it | What you do |
|---|---|---|
| **Hosted demo** (https://maree-f8c8.onrender.com) | Evaluating M.A.R.E.E.; quick triage of a sample file you cannot run on your own infrastructure | Just open the URL. First request after 15 min idle pays a ~30 s cold start (free tier). |
| **Self-hosted Docker** | Production use; sensitive samples that should not leave your network | One command: `docker run --rm -p 8080:8080 ghcr.io/.../maree:latest` (or build from source — see `deployed.md`) |

The self-hosted container is fully self-contained: it pulls the trained model from this repo's `model-latest` GitHub Release at build time, so no internet is required at runtime. **No file content or feature data leaves your machine** unless you have explicitly enabled the LLM triage backend (§5).

## 3. The three verdicts

Every prediction returns one of:

### `ALLOWED`
- Calibrated probability of malware < 0.5 **AND** joint confidence ≥ 0.50.
- Both conditions must hold. A file is only allowed if the council *affirmatively* agrees it is benign with high confidence.
- **Operator action**: release the file. The triage panel will still attach a brief confirmation summary so you have an audit trail.

### `BLOCKED_MALWARE`
- Calibrated probability of malware ≥ 0.5 **AND** joint confidence ≥ 0.50.
- Operator action: quarantine, then follow the incident-response steps in the triage panel (typically: capture host telemetry before reboot, hash the file, check email gateway / download logs for the same hash on other endpoints, open a ticket).
- The triage panel maps the feature pattern to specific MITRE ATT&CK techniques. Do not invent techniques; trust only what M.A.R.E.E. surfaces — every link is hand-curated against the MITRE matrix.

### `BLOCKED_UNCERTAIN`
- Joint confidence < 0.50, regardless of which side of 0.5 the probability lands on.
- This is the *interesting* verdict. The model is telling you it sees something it does not understand: a novel family, an unusual feature combination, or a decision sitting near the boundary.
- Operator action: **do not override the block based on user pressure alone.** Uncertain verdicts are exactly the cases where a fail-closed default is most valuable. Investigate via secondary tools (VirusTotal hash lookup, sandbox detonation in an isolated environment, vendor support) before any manual allow decision.
- The triage panel for `BLOCKED_UNCERTAIN` includes specific guidance on *why* the model is uncertain so you can decide which secondary check is most informative.

## 4. Reading the drift indicator

The banner at the top of every page reports four fields:

```
n_active_windows: 5
newest_window_accuracy: 0.967
oldest_window_accuracy: 0.985
per_window_accuracies: [0.985, 0.981, 0.974, 0.962, 0.967]
```

What these mean:
- **`n_active_windows`** — the ensemble votes from this many time-windowed classifiers, each trained on a different historical slice. A larger number = more diverse vote, but each member sees less data.
- **`oldest_window_accuracy` / `newest_window_accuracy`** — the calibrated in-window accuracy for the chronologically oldest and newest base classifiers. The newest is the one most representative of recent threats.
- **`per_window_accuracies`** — the full series. A smooth-decreasing series (oldest highest, newest lowest) is normal — recent malware is genuinely harder than older malware on this dataset. A sharp drop in the newest window (e.g., newest is 5pp below the second-newest) is a signal that the threat distribution has shifted *since training* and a retrain is overdue.

If the newest window's accuracy drops more than 0.05 below the historical mean of the older windows, treat that as a "retrain recommended" alert. (Phase 2 will trigger this automatically; today, it is operator-visible but operator-actioned.)

## 5. The triage panel and the LLM backend

Every verdict comes with a four-field triage report:

| Field | Length | Purpose |
|---|---|---|
| `summary` | 1–2 sentences | Plain-English statement of what just happened, including the probability and joint confidence numbers. |
| `why` | 2–5 bullets | Which features triggered the verdict (e.g., "file is packed", "imports `WinExec`/`VirtualAlloc`", "PE timestamp implausible"). Written for a generalist IT audience. |
| `attack_techniques` | 0–7 MITRE technique IDs | Hyperlinks to attack.mitre.org. Mapping is hand-curated — never invented by the model. |
| `recommended_actions` | 3–5 IR steps | Tailored to the verdict type. Includes the explicit "do not override under user pressure" warning for `BLOCKED_UNCERTAIN`. |

**Two backends exist**:
- **Template** (default) — deterministic, reproducible, no network calls, no third-party data sharing. The Quantic-submission demo runs this.
- **LLM (Claude Haiku 4.5)** — only active when `ANTHROPIC_API_KEY` is set in the environment. Produces more natural prose but sends the (numeric) feature vector + verdict to the Anthropic API. **No raw file contents are ever sent.** The LLM is given a system prompt with the curated MITRE mapping and the explicit instruction "never invent technique IDs"; it can only paraphrase fields the deterministic backend would already produce.

The fallback is unconditional: if the LLM call fails for any reason, the template-generated report is returned. The triage panel never appears empty.

## 6. When you don't trust the verdict

Three escalation paths, in order of cost:

1. **Cross-check via VirusTotal** with the file's SHA-256 hash (the hash is computed locally; only the hash is sent to VT). If multiple AV vendors flag it as malware and M.A.R.E.E. produced `BLOCKED_UNCERTAIN`, M.A.R.E.E. was conservatively right. If VT says benign and M.A.R.E.E. produced `BLOCKED_UNCERTAIN`, you may have a novel false positive — capture the sample for retrain feedback (§7).
2. **Sandbox detonation** in an isolated VM — produces dynamic-behavior evidence M.A.R.E.E.'s static features cannot see.
3. **Open an issue** at https://github.com/TonyStarksGotABrandNewBag/maree/issues with the (anonymized) feature vector and the verdict. Misclassifications are a research signal — the more we see, the better the next retrain.

## 7. Operational hygiene

- **Retrain cadence.** Today: manual, triggered by the operator when the drift indicator says so or per a calendar policy (every 90 days is a reasonable default for an environment that does not see novel families frequently). Phase 2 automates the trigger.
- **Audit trail.** Every prediction is rendered as HTML with the feature values, verdict, probability, confidence, triage, and timestamp visible. Save the page (or screenshot) for any verdict you act on; this is your defensible record.
- **Threshold tuning.** The deployment default `confidence_threshold = 0.50` was selected by a post-hoc validation-set sweep against the random hold-out (the original heuristic was 0.65; see `evaluation-and-design.md` §7.3 for the methodology and the FPR/recall tradeoff). High-throughput environments can lower it further to roughly 0.20–0.40 if FN cost is comparable to FP cost; high-stakes environments (finance, healthcare, critical infrastructure) can raise it back to 0.65 or higher. The setting is exposed in `src/models/ensemble.py::MareeConfig`.
- **What to do if M.A.R.E.E. itself is unavailable.** The classifier is one signal, not the only signal. Endpoint AV (Defender, etc.) should be running in parallel. M.A.R.E.E. is a second opinion specifically for the case where you want to *understand* the verdict, not replace your existing endpoint protection wholesale.

## 8. What this tool is not

Honest framing — these are out of scope, today:

- **Not a real-time on-access scanner.** M.A.R.E.E. classifies a file you submit; it does not hook into the filesystem to scan everything written to disk. Pair it with Defender (or equivalent) for that.
- **Not a dynamic-behavior analyzer.** Static features only — PE structural metadata, imports, entropy, packer detection. A sandbox or EDR is the right complement for runtime telemetry.
- **Not a substitute for patch management or endpoint hardening.** Classifier accuracy is one layer; reducing the attack surface in the first place dominates classifier sophistication.
- **Not certified for compliance use cases.** Use M.A.R.E.E. to *augment* your judgment, not to satisfy an audit checkbox. (The capstone is research-grade; certified deployments require Phase 2+ work.)

## 9. Where to ask questions

- The methodology behind the verdicts: `docs/honest-evaluation.md`.
- The full feature inventory: `docs/feature-inventory.md`.
- The deployment pipeline (CI/CD, Render, Docker): `deployed.md`.
- The technical evaluation report: `evaluation-and-design.md`.
- Bug reports and feature requests: GitHub issues at https://github.com/TonyStarksGotABrandNewBag/maree/issues.
