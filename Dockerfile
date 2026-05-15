# syntax=docker/dockerfile:1.7
#
# Multi-stage build for the NileTel RAG Customer Support system.
# Produces two runtime entry points from one base image:
#   * api       — FastAPI + LangGraph (uvicorn on :8000)
#   * streamlit — Chat UI (streamlit on :8501)
#
# Build a specific target with:
#   docker build --target api       -t niletel-api .
#   docker build --target streamlit -t niletel-streamlit .
#
# Or let docker compose build both via the compose file at repo root.

# ------------------------------------------------------------------ base
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    HF_HOME=/cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/cache/huggingface/sentence-transformers

# System deps:
#   - build-essential / git: some sentence-transformers wheels still need them
#   - libgomp1: required by faiss / numpy
#   - curl: healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libgomp1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Astral) — the project's mandated package manager.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app

# ------------------------------------------------------------------ deps
# Cache deps in a separate layer keyed on the lockfile only.
FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ------------------------------------------------------------------ source
FROM deps AS source
COPY src/ ./src/
COPY api/ ./api/
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/raw/ ./data/raw/

# Install the project itself (now that the source is in place).
RUN uv sync --frozen --no-dev

# Create a non-root user; chown only what it needs.
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && mkdir -p /cache/huggingface /app/data/chroma_db \
    && chown -R app:app /app /cache

USER app

# Shared env defaults — overridden by compose / runtime.
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app

# ------------------------------------------------------------------ api
FROM source AS api
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# 0.0.0.0 so prometheus-in-docker can scrape /metrics via host.docker.internal,
# and so streamlit (in a sibling container) can reach this service by name.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ------------------------------------------------------------------ streamlit
FROM source AS streamlit
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

# Streamlit's XSRF check breaks when proxied (ngrok / nginx) — disable for
# the demo container only. Re-enable behind real auth in production.
CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false"]
