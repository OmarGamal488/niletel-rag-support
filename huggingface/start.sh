#!/usr/bin/env bash
# Entrypoint for the Hugging Face Space container.
#
# Boots FastAPI on :8000 in the background, then Streamlit on :7860 in the
# foreground (Spaces only exposes the latter publicly). Streamlit talks to
# FastAPI over loopback via API_URL.
#
# On first boot data/chroma_db is empty, so the ingestion step is invoked
# lazily and the bge-m3 weights are downloaded into the HF cache volume.

set -euo pipefail

export API_URL="${API_URL:-http://localhost:8000}"
export PORT="${PORT:-7860}"

if [ ! -d /app/data/chroma_db ] || [ -z "$(ls -A /app/data/chroma_db 2>/dev/null)" ] \
   || [ ! -f /app/data/bm25_index.pkl ]; then
    echo "[start.sh] Building knowledge base index (first boot — this may take 1–2 min)..."
    python -m src.ingestion
fi

echo "[start.sh] Starting FastAPI on :8000..."
uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info &
API_PID=$!

# Wait up to 60 s for FastAPI to come up, otherwise give up gracefully.
for i in $(seq 1 60); do
    if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        echo "[start.sh] FastAPI is ready."
        break
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "[start.sh] FastAPI exited before becoming healthy — aborting." >&2
        exit 1
    fi
    sleep 1
done

echo "[start.sh] Starting Streamlit on :${PORT}..."
exec streamlit run app/streamlit_app.py \
    --server.address=0.0.0.0 \
    --server.port="${PORT}" \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
