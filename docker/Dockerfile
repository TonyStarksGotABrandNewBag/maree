# M.A.R.E.E. — multi-stage Dockerfile.
#
# Prereq: produce artifacts/ first (the build COPYs them into the image so
# the deployed container is self-contained, no volume mount required):
#   python scripts/train_production_model.py
#
# Build:
#   docker build -f docker/Dockerfile -t maree:latest .
#
# Run:
#   docker run --rm -p 8080:8080 maree:latest
#
# Local dev with hot artifacts (overrides the baked-in copy via volume mount):
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
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
    OPENBLAS_NUM_THREADS=4 \
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
# Bake the trained production model + demo samples into the image so the
# deployed container starts fully loaded. CI runs train_production_model.py
# before `docker build`. docker-compose.yml mounts a volume here for local
# dev so `python scripts/train_production_model.py` retrains hot.
COPY artifacts ./artifacts

RUN chown -R maree:maree /app

USER maree
EXPOSE 8080

# gunicorn for production-grade serving (already in requirements.txt)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", \
     "--access-logfile", "-", "src.app.server:app"]
