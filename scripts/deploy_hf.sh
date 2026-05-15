#!/usr/bin/env bash
# deploy_hf.sh — sync the project into a Hugging Face Space clone.
#
# Usage:
#   ./scripts/deploy_hf.sh <path-to-cloned-space>
#
# Example:
#   # one-time setup
#   pip install --user huggingface_hub
#   huggingface-cli login
#   git clone https://huggingface.co/spaces/OmarGamal48812/niletel-rag-support ../space
#
#   # every deploy
#   ./scripts/deploy_hf.sh ../space
#   cd ../space && git add -A && git commit -m "deploy" && git push
#
# What it copies into the Space repo:
#   - huggingface/Dockerfile    → Dockerfile
#   - huggingface/README.md     → README.md  (contains the HF Spaces frontmatter)
#   - huggingface/start.sh      → start.sh
#   - src/  api/  app/  data/raw/  eval/  scripts/  pyproject.toml  uv.lock
#
# It deliberately does NOT copy: .env, .venv, data/chroma_db, data/bm25_index.pkl,
# CLAUDE.md, tests/, frontend/, infra/, .github/, docker-compose.yml, the host
# Dockerfile, or any other Claude/Docker-compose-only files. Set HF Space secrets
# in the Spaces UI (Settings → Repository secrets) — do not bake .env into git.

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 <path-to-cloned-space>" >&2
    exit 2
fi

DEST="$1"

if [ ! -d "$DEST/.git" ]; then
    echo "error: $DEST does not look like a git clone (no .git directory)" >&2
    echo "       clone your Space first:" >&2
    echo "       git clone https://huggingface.co/spaces/<user>/<space-name> $DEST" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Copying Space overlay (Dockerfile, README, start.sh)..."
cp "$ROOT/huggingface/Dockerfile" "$DEST/Dockerfile"
cp "$ROOT/huggingface/README.md"  "$DEST/README.md"
cp "$ROOT/huggingface/start.sh"   "$DEST/start.sh"
chmod +x "$DEST/start.sh"

echo "Copying application source..."
mkdir -p "$DEST/src" "$DEST/api" "$DEST/app" "$DEST/data/raw" "$DEST/scripts" "$DEST/eval"
# rsync gives us a clean mirror; --delete is intentionally scoped per-folder.
rsync -a --delete \
    --exclude '__pycache__/' --exclude '*.pyc' \
    "$ROOT/src/"  "$DEST/src/"
rsync -a --delete \
    --exclude '__pycache__/' --exclude '*.pyc' \
    "$ROOT/api/"  "$DEST/api/"
rsync -a --delete \
    --exclude '__pycache__/' --exclude '*.pyc' \
    "$ROOT/app/"  "$DEST/app/"
rsync -a --delete "$ROOT/data/raw/" "$DEST/data/raw/"
rsync -a --delete "$ROOT/eval/"     "$DEST/eval/"
# Only the scripts the Space actually needs at runtime.
cp "$ROOT/scripts/test_n8n.py"          "$DEST/scripts/" 2>/dev/null || true
cp "$ROOT/scripts/test_integration.py"  "$DEST/scripts/" 2>/dev/null || true

echo "Copying build files..."
cp "$ROOT/pyproject.toml" "$DEST/pyproject.toml"
cp "$ROOT/uv.lock"        "$DEST/uv.lock"

# Friendly .gitignore for the Space clone.
cat > "$DEST/.gitignore" <<'EOF'
__pycache__/
*.pyc
.venv/
.DS_Store
data/chroma_db/
data/bm25_index.pkl
data/processed/
.env
EOF

echo
echo "Sync complete. Next steps:"
echo "  cd $DEST"
echo "  git status"
echo "  git add -A && git commit -m 'deploy' && git push"
echo
echo "Then set Repository secrets in the Spaces UI:"
echo "  LLM_PROVIDER, LIGHTNING_API_KEY, LIGHTNING_BASE_URL, LIGHTNING_MODEL"
echo "  (plus TAVILY_API_KEY / LANGFUSE_* / N8N_WEBHOOK_URL if you want them)"
