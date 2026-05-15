# Hugging Face Spaces — single-image build that runs both the FastAPI
# backend (internal :8000) and the Streamlit UI (public :7860).
#
# Spaces builds and runs this Dockerfile from the repo root after the
# files in this folder are copied alongside src/ api/ app/ data/raw/
# pyproject.toml uv.lock (see ../README.md for the push workflow).

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    HF_HOME=/cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/cache/huggingface/sentence-transformers \
    PYTHONPATH=/app

# System deps for sentence-transformers, faiss, healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git libgomp1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv (Astral) — the project's mandated package manager.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first so the layer caches well.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the application code (and the raw KB so ingestion can run on first boot).
COPY src/ ./src/
COPY api/ ./api/
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/raw/ ./data/raw/
COPY start.sh ./start.sh

RUN uv sync --frozen --no-dev

# Spaces runs as UID 1000 by convention; carve out writable cache + data dirs.
RUN groupadd --system app && useradd --system --gid app --home /app -u 1000 app \
    && mkdir -p /cache/huggingface /app/data/chroma_db \
    && chmod +x /app/start.sh \
    && chown -R app:app /app /cache

USER app

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 7860

CMD ["/app/start.sh"]
