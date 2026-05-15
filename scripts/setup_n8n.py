"""Auto-provision the NileTel ticket workflow on n8n Cloud.

Creates a 3-node workflow inside your n8n project:

    [Webhook]  →  [Code: issue ticket_id]  →  [Respond to Webhook]

…then activates it and writes the production webhook URL back into
`.env` as `N8N_WEBHOOK_URL`. After that, every COMPLAINT routed through
the graph hits this webhook and the response's `ticket_id` becomes the
user-facing ticket number.

Once the workflow is live in n8n's UI, add downstream nodes (Google
Sheets, Gmail, Slack) by clicking the `+` after the Code node — the
ticket_id propagates downstream automatically.

Usage:
    # one-time: fill these in (or pass --api-key/--base-url)
    export N8N_API_KEY="<from n8n Settings → API → Create API Key>"
    export N8N_BASE_URL="https://<your-subdomain>.app.n8n.cloud"

    uv run python scripts/setup_n8n.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
WEBHOOK_PATH = "niletel-ticket"
WORKFLOW_NAME = "NileTel Tickets"


# A 3-node workflow JSON. Position values keep the canvas tidy in the UI.
WORKFLOW = {
    "name": WORKFLOW_NAME,
    "nodes": [
        {
            "parameters": {
                "httpMethod": "POST",
                "path": WEBHOOK_PATH,
                "responseMode": "responseNode",
                "options": {},
            },
            "id": "webhook-1",
            "name": "Webhook",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [240, 300],
            "webhookId": WEBHOOK_PATH,
        },
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": (
                    "// Issue a short ticket id and pass the original payload "
                    "through so downstream nodes can fan out to Gmail / "
                    "Sheets / etc.\n"
                    "const ticket_id = 'TICKET-' + "
                    "Date.now().toString(36).toUpperCase().slice(-8);\n"
                    "return [{ json: { ticket_id, ...$input.first().json } }];"
                ),
            },
            "id": "code-1",
            "name": "Issue ticket_id",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [520, 300],
        },
        {
            "parameters": {
                "respondWith": "json",
                "responseBody": "={{ { ticket_id: $json.ticket_id } }}",
                "options": {},
            },
            "id": "respond-1",
            "name": "Respond to Webhook",
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1,
            "position": [800, 300],
        },
    ],
    "connections": {
        "Webhook": {
            "main": [[{"node": "Issue ticket_id", "type": "main", "index": 0}]]
        },
        "Issue ticket_id": {
            "main": [
                [{"node": "Respond to Webhook", "type": "main", "index": 0}]
            ]
        },
    },
    "settings": {"executionOrder": "v1"},
}


def _api(base_url: str, key: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url.rstrip("/") + "/api/v1",
        headers={
            "X-N8N-API-KEY": key,
            "accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


def _find_existing(client: httpx.Client) -> dict | None:
    r = client.get("/workflows", params={"limit": 250})
    r.raise_for_status()
    for wf in r.json().get("data", []):
        if wf.get("name") == WORKFLOW_NAME:
            return wf
    return None


def _create(client: httpx.Client) -> dict:
    r = client.post("/workflows", json=WORKFLOW)
    if r.status_code >= 400:
        raise RuntimeError(
            f"create workflow failed: {r.status_code}  body={r.text[:400]}"
        )
    return r.json()


def _activate(client: httpx.Client, wf_id: str) -> None:
    r = client.post(f"/workflows/{wf_id}/activate")
    if r.status_code >= 400:
        raise RuntimeError(
            f"activate failed: {r.status_code}  body={r.text[:400]}"
        )


def _patch_env(webhook_url: str) -> None:
    """Replace or append N8N_WEBHOOK_URL in .env (preserves other vars)."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text(f"N8N_WEBHOOK_URL={webhook_url}\n")
        return
    text = ENV_PATH.read_text()
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("N8N_WEBHOOK_URL"):
            lines[i] = f"N8N_WEBHOOK_URL={webhook_url}"
            found = True
            break
    if not found:
        lines.append(f"N8N_WEBHOOK_URL={webhook_url}")
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-key",
        default=os.getenv("N8N_API_KEY"),
        help="n8n API key (or set $N8N_API_KEY).",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("N8N_BASE_URL"),
        help="n8n instance URL, e.g. https://yourname.app.n8n.cloud "
        "(or set $N8N_BASE_URL).",
    )
    parser.add_argument(
        "--no-env-write",
        action="store_true",
        help="Print the webhook URL but don't touch .env.",
    )
    args = parser.parse_args()

    if not args.api_key or not args.base_url:
        print(
            "✗ Missing credentials. Set N8N_API_KEY + N8N_BASE_URL "
            "(or pass --api-key / --base-url).",
            file=sys.stderr,
        )
        print(
            "  - API key: n8n UI → Settings → n8n API → Create an API key",
            file=sys.stderr,
        )
        print(
            "  - Base URL: the part before /home in your n8n URL, "
            "e.g. https://yourname.app.n8n.cloud",
            file=sys.stderr,
        )
        return 1

    base = args.base_url.rstrip("/")
    with _api(base, args.api_key) as client:
        # 1. Don't double-create — reuse if a workflow with this name exists.
        existing = _find_existing(client)
        if existing:
            wf = existing
            print(f"› Found existing workflow id={wf['id']} — reusing.")
        else:
            wf = _create(client)
            print(f"✓ Created workflow id={wf['id']}")

        # 2. Activate (idempotent: re-activating an active workflow is fine).
        if not wf.get("active"):
            _activate(client, wf["id"])
            print("✓ Activated workflow")
        else:
            print("› Workflow already active.")

    webhook_url = f"{base}/webhook/{WEBHOOK_PATH}"
    print(f"✓ Webhook URL: {webhook_url}")

    if not args.no_env_write:
        _patch_env(webhook_url)
        print(f"✓ Wrote N8N_WEBHOOK_URL → {ENV_PATH}")

    print(
        "\nNext steps:\n"
        "  1. Restart the API:  ./scripts/start_demo.sh stop && "
        "./scripts/start_demo.sh\n"
        "  2. Submit a complaint in Streamlit (provide a contact when "
        "asked).\n"
        "  3. Open n8n → Executions tab — you'll see one execution per "
        "ticket.\n"
        "  4. Add Gmail / Google Sheets / Slack nodes after "
        "'Issue ticket_id' in the n8n UI."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
