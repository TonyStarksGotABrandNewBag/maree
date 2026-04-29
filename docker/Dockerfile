# M.A.R.E.E. — multi-stage Dockerfile.
#
# The trained production model is fetched from the GitHub Release that the
# `train-and-release` CI job publishes. This keeps Render's free-tier build
# fast (~2 min) and inside its 512-MB / 15-min envelope — the heavy model
# training happens once on the GH-hosted runner (7 GB RAM), not on every
# Render rebuild.
#
# Build:
#   docker build -f docker/Dockerfile -t maree:latest .
#
# Run:
#   docker run --rm -p 8080:8080 maree:latest
#
# Local dev with hot artifacts (overrides the fetched copy via volume mount,
# so `python scripts/train_production_model.py` on the host hot-reloads after
# a container restart):
#   docker compose -f docker/docker-compose.yml up

# ----- Stage 1: build deps + install Python wheels -----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir=/wheels -r requirements.txt

# ----- Stage 2: slim runtime image -----
FROM python:3.12-slim

LABEL org.opencontainers.image.title="M.A.R.E.E."
LABEL org.opencontainers.image.description="Multi-classifier Adaptive Recognition, Explainable Engine"
LABEL org.opencontainers.image.source="https://github.com/TonyStarksGotABrandNewBag/maree"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    KMP_DUPLICATE_LIB_OK=TRUE

# curl is used in the COPY-equivalent step below to fetch model artifacts from
# the GitHub Release. Cleaned up in the same RUN so it doesn't bloat the image.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Non-root user — security hygiene per CISA secure-by-design guidance
RUN groupadd --system maree && useradd --system --gid maree --create-home maree

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

# Copy only what the app needs at runtime
COPY src ./src
COPY scripts ./scripts

# Fetch the production model + demo samples from the `model-latest` GitHub
# Release published by the train-and-release CI job. This is the boundary
# where "training infra" hands off to "serving infra".
ARG MODEL_RELEASE_BASE_URL=https://github.com/TonyStarksGotABrandNewBag/maree/releases/download/model-latest
RUN mkdir -p artifacts && \
    curl -fsSL "${MODEL_RELEASE_BASE_URL}/maree_production.joblib" -o artifacts/maree_production.joblib && \
    curl -fsSL "${MODEL_RELEASE_BASE_URL}/demo_samples.json" -o artifacts/demo_samples.json && \
    test -s artifacts/maree_production.joblib && \
    test -s artifacts/demo_samples.json

RUN chown -R maree:maree /app

USER maree
EXPOSE 8080

# gunicorn for production-grade serving (already in requirements.txt)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", \
     "--access-logfile", "-", "src.app.server:app"]
