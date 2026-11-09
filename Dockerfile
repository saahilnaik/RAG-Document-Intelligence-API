# ---- build stage: compile/install wheels, nothing from here ships except /install ----
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt


# ---- runtime stage: no compilers, non-root ----
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache \
    LOG_FORMAT=json \
    ENVIRONMENT=production

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

COPY --from=builder /install /usr/local

# Pre-download the embedding model so containers start fast and offline.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('BAAI/bge-small-en-v1.5'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')" \
    && chown -R app:app /opt/hf-cache

WORKDIR /app
COPY --chown=app:app . .
RUN mkdir -p /app/data/uploads /app/data/chroma && chown -R app:app /app/data

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Worker count comes from WEB_CONCURRENCY (see gunicorn.conf.py).
CMD ["gunicorn", "-c", "gunicorn.conf.py", "main:app"]
