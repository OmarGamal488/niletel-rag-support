#!/usr/bin/env python3
"""Provision a Hugging Face Space's Variables + Secrets from this repo's .env.

Why:
    The HF Spaces UI requires clicking through 20+ separate "Add" forms to
    configure runtime env vars. This script does the same thing in one shot
    by reading values from `.env` and pushing them via the HF Hub API.

Usage:
    # 1. Install the SDK (one-time):
    uv pip install huggingface_hub python-dotenv

    # 2. Authenticate (either way works):
    uv run hf auth login                         # interactive
    # or
    export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxx  # write-scoped token

    # 3. Run:
    uv run python scripts/setup_hf_space.py OmarGamal48812/niletel-rag-support
    # or to preview without writing:
    uv run python scripts/setup_hf_space.py OmarGamal48812/niletel-rag-support --dry-run

    # 4. Optional flags:
    --env .env.production    # use a different env file
    --restart                # restart the Space after applying

Behavior:
    * Variables (public, visible to anyone) are set for everything in
      VARIABLE_KEYS.
    * Secrets (masked, never returned by the API after writing) are set for
      everything in SECRET_KEYS.
    * Keys present in .env but absent from both lists are skipped with a
      warning — that protects against accidentally exposing something
      unexpected as a public variable.
    * Empty / placeholder values like `gsk_...` are skipped automatically.
    * Re-runs are idempotent; existing variables/secrets are overwritten.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import dotenv_values
except ImportError:
    sys.exit(
        "missing dependency: dotenv\n"
        "install it with: uv pip install python-dotenv"
    )

try:
    from huggingface_hub import HfApi
    from huggingface_hub.utils import HfHubHTTPError
except ImportError:
    sys.exit(
        "missing dependency: huggingface_hub\n"
        "install it with: uv pip install huggingface_hub"
    )

# Anything safe to expose publicly — feature flags, model names, endpoints.
VARIABLE_KEYS = {
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LIGHTNING_BASE_URL",
    "LIGHTNING_MODEL",
    "EMBEDDING_MODEL",
    "RERANKER_MODEL",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "RETRIEVAL_MODE",
    "CONTEXTUAL_RETRIEVAL",
    "LONG_CONTEXT_REORDER",
    "RERANKER_ENABLED",
    "PII_REDACTION_ENABLED",
    "SEMANTIC_CACHE_ENABLED",
    "CITATIONS_ENABLED",
    "TOOL_AGENT_ENABLED",
    "TRIAD_EVAL_ENABLED",
    "LANGFUSE_ENABLED",
    "LANGFUSE_HOST",
    "PROMETHEUS_ENABLED",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_PROJECT",
}

# Anything that must NEVER appear in plain text — API keys, webhook URLs
# that grant write access, etc.
SECRET_KEYS = {
    "LIGHTNING_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGCHAIN_API_KEY",
    "N8N_WEBHOOK_URL",
}

# Values that look like the placeholder text in .env.example. Don't push these.
PLACEHOLDER_HINTS = {"", "gsk_...", "sk-...", "your-key-here", "TODO", "<your-key>"}


def is_placeholder(value: str) -> bool:
    v = (value or "").strip()
    if v in PLACEHOLDER_HINTS:
        return True
    # Heuristic: anything that's just a prefix with ellipsis.
    return v.endswith("...") and len(v) <= 12


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("space_id", help="<username>/<space-name>, e.g. OmarGamal48812/niletel-rag-support")
    parser.add_argument("--env", default=".env", help="path to env file (default: .env)")
    parser.add_argument("--dry-run", action="store_true", help="print what would be set, don't write")
    parser.add_argument("--restart", action="store_true", help="restart the Space after applying changes")
    parser.add_argument("--create", action="store_true", help="create the Space if it doesn't exist (Docker SDK, public)")
    parser.add_argument("--private", action="store_true", help="when used with --create, create the Space as private")
    parser.add_argument("--token", default=None, help="HF token (defaults to $HF_TOKEN or the CLI login)")
    args = parser.parse_args()

    env_path = Path(args.env)
    if not env_path.exists():
        print(f"error: {env_path} not found", file=sys.stderr)
        return 2

    values = dotenv_values(env_path)
    # Strip surrounding quotes if dotenv left them.
    values = {
        k: (v.strip().strip('"').strip("'") if isinstance(v, str) else v)
        for k, v in values.items()
    }

    # Treat empty strings as unset — otherwise httpx ships a Bearer header with
    # no value and the request fails with LocalProtocolError before it even
    # leaves the machine.
    env_token = os.getenv("HF_TOKEN") or None
    token = (args.token or env_token) or None
    api = HfApi(token=token)

    if not args.dry_run:
        # Verify auth + repo exist before making 20 separate requests.
        try:
            api.space_info(args.space_id)
        except HfHubHTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                if args.create:
                    print(f"Space '{args.space_id}' not found — creating it (Docker SDK)...")
                    try:
                        url = api.create_repo(
                            repo_id=args.space_id,
                            repo_type="space",
                            space_sdk="docker",
                            private=args.private,
                            exist_ok=False,
                        )
                        print(f"  ✓ Space created at {url}")
                    except HfHubHTTPError as create_exc:
                        print(
                            f"error: failed to create the Space.\n  HTTP details: {create_exc}",
                            file=sys.stderr,
                        )
                        return 4
                else:
                    print(
                        f"error: Space '{args.space_id}' does not exist.\n"
                        f"  Re-run with --create to provision it (Docker SDK, public),\n"
                        f"  or create it manually at https://huggingface.co/new-space.",
                        file=sys.stderr,
                    )
                    return 3
            else:
                print(
                    f"error: cannot reach Space '{args.space_id}'.\n"
                    f"  HTTP details: {exc}\n"
                    f"  Authentication: 'hf auth login' or export HF_TOKEN.",
                    file=sys.stderr,
                )
                return 3

    set_vars: list[tuple[str, str]] = []
    set_secrets: list[str] = []
    skipped_placeholder: list[str] = []
    unrecognised: list[str] = []

    for key, value in values.items():
        if not isinstance(value, str):
            continue
        is_secret = key in SECRET_KEYS
        is_var = key in VARIABLE_KEYS
        if not (is_secret or is_var):
            unrecognised.append(key)
            continue
        if is_placeholder(value):
            skipped_placeholder.append(key)
            continue
        if is_secret:
            set_secrets.append(key)
            if args.dry_run:
                masked = value[:4] + "…" + value[-2:] if len(value) > 8 else "…"
                print(f"  SECRET   {key:30s} = {masked}")
            else:
                api.add_space_secret(args.space_id, key=key, value=value)
                print(f"  ✓ secret   {key}")
        else:
            set_vars.append((key, value))
            if args.dry_run:
                print(f"  VARIABLE {key:30s} = {value}")
            else:
                api.add_space_variable(args.space_id, key=key, value=value)
                print(f"  ✓ variable {key} = {value}")

    print()
    print(f"  variables to set: {len(set_vars)}")
    print(f"  secrets to set:   {len(set_secrets)}")
    if skipped_placeholder:
        print(f"  skipped placeholders: {', '.join(skipped_placeholder)}")
    if unrecognised:
        print(
            f"  skipped (not in VARIABLE_KEYS or SECRET_KEYS — edit this script to opt in): "
            f"{', '.join(unrecognised)}"
        )

    if args.dry_run:
        print("\nDry run — nothing written. Drop --dry-run to apply.")
        return 0

    if args.restart:
        print("\nRestarting the Space to pick up the new environment...")
        api.restart_space(args.space_id)
        print(f"  ✓ restart requested for {args.space_id}")
    else:
        print(
            "\nDone. Restart the Space (UI: Settings → Factory rebuild, or pass --restart) "
            "so the new env takes effect."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
