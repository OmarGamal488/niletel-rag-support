#!/usr/bin/env bash
# demo_tunnel.sh — open a free public URL for the demo via Cloudflare Quick Tunnel.
#
# Unlike ngrok's free tier, Cloudflare's Quick Tunnel does NOT show an
# interstitial "Are you the developer?" warning page — perfect for recording
# a clean demo or sharing with a grader.
#
# Usage:
#   ./scripts/demo_tunnel.sh                  # tunnel Streamlit on :8501 (default)
#   ./scripts/demo_tunnel.sh api              # tunnel FastAPI on :8000
#   ./scripts/demo_tunnel.sh ui               # explicit alias for Streamlit
#   PORT=3000 ./scripts/demo_tunnel.sh        # tunnel an arbitrary local port
#
# First-time setup (install cloudflared once, no signup required):
#   Linux x86_64:
#     curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
#       -o ~/.local/bin/cloudflared && chmod +x ~/.local/bin/cloudflared
#   macOS:
#     brew install cloudflared
#
# Prints a https://<random>.trycloudflare.com URL and keeps the tunnel open
# until you Ctrl-C.

set -euo pipefail

target="${1:-ui}"
case "$target" in
    ui|streamlit) port="${PORT:-8501}"; label="Streamlit UI" ;;
    api|fastapi)  port="${PORT:-8000}"; label="FastAPI" ;;
    *)
        # Allow a raw port number as the first arg.
        if [[ "$target" =~ ^[0-9]+$ ]]; then
            port="$target"; label="port $port"
        else
            echo "Unknown target: $target (use 'ui', 'api', or a port number)" >&2
            exit 2
        fi
        ;;
esac

if ! command -v cloudflared >/dev/null 2>&1; then
    cat >&2 <<'EOF'
cloudflared is not installed.

Install it once:
  # Linux x86_64
  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
       -o ~/.local/bin/cloudflared && chmod +x ~/.local/bin/cloudflared
  # macOS
  brew install cloudflared

Then re-run this script.
EOF
    exit 127
fi

# Best-effort warning if the target port is not actually listening yet —
# the tunnel still starts, but visitors will get a 502 until your app is up.
if command -v ss >/dev/null 2>&1; then
    if ! ss -ltn "sport = :$port" 2>/dev/null | tail -n +2 | grep -q .; then
        echo "warning: nothing is listening on localhost:$port yet — start your app first" >&2
    fi
fi

echo "Opening Cloudflare Quick Tunnel for ${label} (localhost:${port})..."
echo "Look for the https://<...>.trycloudflare.com line below. Ctrl-C to stop."
echo
exec cloudflared tunnel --url "http://localhost:${port}" --no-autoupdate
