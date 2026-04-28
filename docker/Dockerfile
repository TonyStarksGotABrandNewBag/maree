# M.A.R.E.E. — multi-stage Dockerfile.
#
# This Dockerfile is self-contained: it clones the Brazilian Malware Dataset
# during the build, trains the production M.A.R.E.E. ensemble, and bakes the
# trained model + demo samples into the final image. No volume mount or
# pre-built artifacts/ directory required.
#
# Build (~3-5 min on a modern machine — most of it is the train step):
#   docker build -f docker/Dockerfile -t maree:latest .
#
# Run:
#   docker run --rm -p 8080:8080 maree:latest
#
# Local dev with hot artifacts (overrides the baked-in copy via volume mount,
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

# ----- Stage 2: train the production model in an isolated layer -----
# Done in its own stage so the dataset (~30 MB) and dev tools never reach
# the runtime image. Only artifacts/ gets copied forward.
FROM python:3.12-slim AS trainer

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    KMP_DUPLICATE_LIB_OK=TRUE

RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-index --find-links=/wheels -r requirements.txt

COPY src ./src
COPY scripts ./scripts

# Clone the dataset, train, then drop the dataset — only artifacts/ moves on.
RUN python scripts/download_data.py && \
    python scripts/train_production_model.py && \
    rm -rf data/

# ----- Stage 3: slim runtime image -----
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
# Pull the freshly-trained model + demo samples from the trainer stage.
COPY --from=trainer /app/artifacts ./artifacts

RUN chown -R maree:maree /app

USER maree
EXPOSE 8080

# gunicorn for production-grade serving (already in requirements.txt)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", \
     "--access-logfile", "-", "src.app.server:app"]
