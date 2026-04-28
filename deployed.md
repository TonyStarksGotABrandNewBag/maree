# Deployment

The live M.A.R.E.E. instance is hosted at:

> https://maree.fly.dev

Source code: this repository. CI/CD pipeline: `.github/workflows/ci.yml`.

## Pipeline

Every push to `main` triggers:

1. **lint** — `ruff check src/ tests/ scripts/`
2. **test** — full pytest suite minus the torch tests
3. **test-torch** — torch tests in their own job (libomp isolation)
4. **deploy** — only on `main`, only if all checks pass:
   1. Clone the Brazilian Malware Dataset
   2. Train the production M.A.R.E.E. model (RF base) → `artifacts/`
   3. `flyctl deploy --remote-only` (Fly builders compile the image)
   4. Smoke-test `https://maree.fly.dev/health` (retries for up to ~60s for cold start)

## One-time Fly.io setup (Sir does this once)

```bash
# 1. Install flyctl locally (one time)
brew install flyctl

# 2. Sign in / create account
flyctl auth signup    # or: flyctl auth login

# 3. Create the app (matches the `app` name in fly.toml)
flyctl apps create maree

# 4. Mint a CI token and copy it
flyctl tokens create deploy --app maree --name github-ci
#    Copy the printed `FlyV1 fm2_…` token.

# 5. Add it as a GitHub repo secret
#    Settings → Secrets and variables → Actions → New repository secret
#      Name:  FLY_API_TOKEN
#      Value: <paste the token from step 4>

# 6. (Optional) enable LLM triage by setting the Anthropic key as a Fly secret
flyctl secrets set ANTHROPIC_API_KEY=sk-ant-... --app maree
#    Without this, M.A.R.E.E. uses the deterministic template triage backend
#    — still produces verdicts and recommendations, just without LLM prose.
```

After step 5, every push to `main` deploys automatically. The first deploy
is the only one that needs `flyctl apps create`; subsequent deploys reuse
the same app.

## Self-host (no Fly.io)

```bash
python scripts/train_production_model.py
docker compose -f docker/docker-compose.yml up
# → http://localhost:8080
```

## Fly free tier notes

- The machine auto-stops when idle (`auto_stop_machines = "stop"` in
  `fly.toml`). First request after idle pays a ~2-3s cold start.
- `min_machines_running = 0` keeps us inside the free allowance even if
  the app is unused for days.
- 1 GB memory is provisioned — enough for the RF ensemble with a comfortable
  margin. If logs show OOM, bump `[[vm]] memory` to `"2gb"`.
