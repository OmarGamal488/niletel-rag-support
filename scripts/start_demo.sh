#!/usr/bin/env bash
# start_demo.sh — one-shot launcher for the NileTel demo.
#
# Brings up:
#   1. FastAPI backend (uvicorn) on port $API_PORT     (default 8000)
#   2. Streamlit UI               on port $UI_PORT     (default 8501)
#   3. Optionally the Next.js (CopilotKit) UI on $NEXT_PORT (default 3000)
#   4. ngrok tunnel               exposing whichever UI you chose
#
# Required: uv + ngrok. For the Next.js UI, also Node 20+ and `npm install`
# already run inside `frontend/`.
# Auth ngrok once with: ngrok config add-authtoken <YOUR_TOKEN>
#
# Usage:
#   ./scripts/start_demo.sh                        # tunnel Streamlit
#   FRONTEND=next ./scripts/start_demo.sh          # tunnel Next.js GenUI app
#   TUNNEL_TARGET=api ./scripts/start_demo.sh      # tunnel the FastAPI backend
#   ./scripts/start_demo.sh obs                    # bring up Prometheus + Grafana
#   ./scripts/start_demo.sh obs-stop               # tear them down
#   ./scripts/start_demo.sh stop                   # kill the API/UI processes

set -euo pipefail

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-8501}"
NEXT_PORT="${NEXT_PORT:-3000}"
FRONTEND="${FRONTEND:-streamlit}"          # "streamlit" | "next" | "both"
TUNNEL_TARGET="${TUNNEL_TARGET:-ui}"       # "ui" | "api"
LOG_DIR="${LOG_DIR:-/tmp/niletel}"

mkdir -p "$LOG_DIR"
API_LOG="$LOG_DIR/api.log"
UI_LOG="$LOG_DIR/ui.log"
NEXT_LOG="$LOG_DIR/next.log"
NGROK_LOG="$LOG_DIR/ngrok.log"
PID_FILE="$LOG_DIR/demo.pids"

stop_existing() {
  if [[ -f "$PID_FILE" ]]; then
    echo "› stopping previous demo processes…"
    while read -r pid; do
      [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done < "$PID_FILE"
    rm -f "$PID_FILE"
  fi
  pkill -f "uvicorn api.main:app"                  2>/dev/null || true
  pkill -f "streamlit run app/streamlit_app.py"    2>/dev/null || true
  pkill -f "next dev"                              2>/dev/null || true
  pkill -f "ngrok http"                            2>/dev/null || true
}

wait_port() {
  local name="$1" port="$2"
  for _ in $(seq 1 30); do
    if (echo > /dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
      echo "  ✓ $name ready on :$port"
      return 0
    fi
    sleep 1
  done
  echo "  ✗ $name did NOT come up on :$port — check $LOG_DIR for logs"
  return 1
}

OBS_COMPOSE="infra/observability/docker-compose.yml"

obs_up() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "✗ docker not in PATH — install Docker Desktop / docker-engine first."
    exit 1
  fi
  echo "› bringing up Prometheus + Grafana via $OBS_COMPOSE"
  docker compose -f "$OBS_COMPOSE" up -d
  cat <<EOF

✓ Observability stack is up:
  Prometheus : http://localhost:9090
  Grafana    : http://localhost:3001   (anonymous viewer; admin/admin to edit)
               → "NileTel" folder → "NileTel RAG — Overview" dashboard
  Make sure the API is running on :8000 so /metrics is scraped.
  Stop the stack: ./scripts/start_demo.sh obs-stop
EOF
}

obs_down() {
  if command -v docker >/dev/null 2>&1; then
    docker compose -f "$OBS_COMPOSE" down
    echo "✓ observability stack stopped."
  fi
}

case "${1:-}" in
  stop)
    stop_existing
    echo "✓ stopped."
    exit 0
    ;;
  obs)
    obs_up
    exit 0
    ;;
  obs-stop)
    obs_down
    exit 0
    ;;
esac

stop_existing
: > "$PID_FILE"

echo "› starting FastAPI on :$API_PORT  (log: $API_LOG)"
# Bind to 0.0.0.0 so the Prometheus container can reach /metrics via
# host.docker.internal (Linux: host-gateway → 172.17.0.1). 127.0.0.1
# only accepts loopback connections and Docker containers don't qualify.
uv run uvicorn api.main:app --host 0.0.0.0 --port "$API_PORT" > "$API_LOG" 2>&1 &
echo $! >> "$PID_FILE"

if [[ "$FRONTEND" == "streamlit" || "$FRONTEND" == "both" ]]; then
  echo "› starting Streamlit on :$UI_PORT (log: $UI_LOG)"
  uv run streamlit run app/streamlit_app.py \
    --server.port "$UI_PORT" --server.headless true > "$UI_LOG" 2>&1 &
  echo $! >> "$PID_FILE"
fi

# ----- Next.js (Path A / CopilotKit) — DISABLED -----
# The generative-UI frontend at `frontend/` is parked. Leave the launch
# block in source for future revival, but never execute it by default
# (any FRONTEND value other than "next" or "both" still avoids it).
# To bring it back: uncomment the block below AND re-enable
# `_COPILOTKIT_ENABLED` in api/main.py so the /copilotkit endpoint is
# served.
#
# if [[ "$FRONTEND" == "next" || "$FRONTEND" == "both" ]]; then
#   if [[ ! -d frontend/node_modules ]]; then
#     echo "✗ frontend/node_modules not found. Run 'cd frontend && npm install' first."
#     exit 1
#   fi
#   echo "› starting Next.js on :$NEXT_PORT (log: $NEXT_LOG)"
#   (
#     cd frontend
#     NEXT_PUBLIC_API_URL="http://localhost:$API_PORT" \
#       npx --no-install next dev -p "$NEXT_PORT"
#   ) > "$NEXT_LOG" 2>&1 &
#   echo $! >> "$PID_FILE"
# fi
if [[ "$FRONTEND" == "next" || "$FRONTEND" == "both" ]]; then
  echo "⚠ FRONTEND=$FRONTEND is disabled — Next.js launch is commented out in this script."
  echo "  Defaulting to streamlit-only (FRONTEND=streamlit)."
  FRONTEND="streamlit"
fi

wait_port "API" "$API_PORT" || true
[[ "$FRONTEND" == "streamlit" || "$FRONTEND" == "both" ]] && wait_port "Streamlit" "$UI_PORT" || true
[[ "$FRONTEND" == "next"      || "$FRONTEND" == "both" ]] && wait_port "Next.js"   "$NEXT_PORT" || true

# Pick tunnel port.
if [[ "$TUNNEL_TARGET" == "api" ]]; then
  TUNNEL_PORT="$API_PORT"
elif [[ "$FRONTEND" == "next" ]]; then
  TUNNEL_PORT="$NEXT_PORT"
else
  TUNNEL_PORT="$UI_PORT"
fi

if ! command -v ngrok >/dev/null 2>&1; then
  cat <<EOF

✗ ngrok not in PATH — install from https://ngrok.com/download
  Services are running locally:
    API       : http://localhost:$API_PORT
    Streamlit : ${FRONTEND:+http://localhost:$UI_PORT}
    Next.js   : ${FRONTEND:+http://localhost:$NEXT_PORT}
  Stop       : ./scripts/start_demo.sh stop
EOF
  exit 0
fi

echo "› opening ngrok tunnel to :$TUNNEL_PORT  (log: $NGROK_LOG)"
ngrok http "$TUNNEL_PORT" --log=stdout > "$NGROK_LOG" 2>&1 &
echo $! >> "$PID_FILE"

# Surface the public URL.
sleep 3
PUBLIC_URL="$(grep -oE 'https://[a-z0-9-]+\.ngrok-free\.app|https://[a-z0-9-]+\.ngrok\.io' "$NGROK_LOG" | head -n 1 || true)"
if [[ -z "$PUBLIC_URL" ]]; then
  PUBLIC_URL="$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | \
    python3 -c "import sys,json;d=json.load(sys.stdin);print(d['tunnels'][0]['public_url'])" 2>/dev/null || true)"
fi

cat <<EOF

────────────────────────────────────────────────
✓ NileTel demo is live
  Frontend  : $FRONTEND
  API       : http://localhost:$API_PORT
  Streamlit : http://localhost:$UI_PORT
  Next.js   : http://localhost:$NEXT_PORT
  Public    : ${PUBLIC_URL:-<check $NGROK_LOG / http://127.0.0.1:4040>}
  Logs      : $LOG_DIR/{api,ui,next,ngrok}.log
  Stop      : ./scripts/start_demo.sh stop
────────────────────────────────────────────────
EOF
