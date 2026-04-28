# M.A.R.E.E. — multi-stage Dockerfile.
#
# Build:
#   docker build -f docker/Dockerfile -t maree:latest .
#
# Run (after `python scripts/train_production_model.py` has produced
# the artifacts/ directory locally):
#   docker run --rm -p 8080:8080 -v "$(pwd)/artifacts:/app/artifacts:ro" maree:latest
#
# Or via compose:
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

RUN mkdir -p /app/artifacts && chown -R maree:maree /app

USER maree
EXPOSE 8080

# gunicorn for production-grade serving (already in requirements.txt)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", \
     "--access-logfile", "-", "src.app.server:app"]
