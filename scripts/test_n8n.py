"""Smoke-test the n8n ticket webhook end-to-end.

Sends a realistic complaint payload (matching what the LangGraph ticketer
emits) to the production webhook and validates the response shape, so you
can confirm Sheets / Gmail / Respond-to-Webhook are all wired up.

Usage:
    uv run python scripts/test_n8n.py
    uv run python scripts/test_n8n.py --url https://yourname.app.n8n.cloud/webhook/niletel-ticket
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"


def _read_webhook_url_from_env() -> str | None:
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith("N8N_WEBHOOK_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.getenv("N8N_WEBHOOK_URL") or _read_webhook_url_from_env(),
        help="Production webhook URL. Defaults to $N8N_WEBHOOK_URL or the value in .env.",
    )
    parser.add_argument("--name", default="Ahmed Test")
    parser.add_argument("--phone", default="01012345678")
    parser.add_argument("--email", default="gimyog48812@gmail.com")
    parser.add_argument(
        "--query",
        default="النت بطيء جداً من الصبح، عايز حد يحل المشكلة",
    )
    args = parser.parse_args()

    if not args.url:
        print(
            "✗ No webhook URL. Pass --url or set N8N_WEBHOOK_URL in .env.",
            file=sys.stderr,
        )
        return 1

    payload = {
        "query": args.query,
        "session_id": f"test-{int(time.time())}",
        "category": "COMPLAINT",
        "contact": {
            "name": args.name,
            "phone": args.phone,
            "email": args.email,
        },
    }

    print(f"→ POST  {args.url}")
    print(f"  body  {json.dumps(payload, ensure_ascii=False)}")

    try:
        r = httpx.post(args.url, json=payload, timeout=30.0)
    except httpx.RequestError as e:
        print(f"\n✗ Request failed: {e}", file=sys.stderr)
        return 2

    print(f"\n← {r.status_code}  {r.text[:500]}")

    if r.status_code != 200:
        print(
            "\n✗ Non-200 response.\n"
            "  • 404 → workflow isn't published yet (top-right Publish button)\n"
            "  • 500 → check n8n Executions tab for the failing node",
            file=sys.stderr,
        )
        return 3

    try:
        body = r.json()
    except json.JSONDecodeError:
        print(
            "\n✗ Response wasn't JSON. Check Respond to Webhook → Respond With = JSON\n"
            "  and the body expression: {{ { ticket_id: $('Issue ticket_id').item.json.ticket_id } }}",
            file=sys.stderr,
        )
        return 4

    ticket_id = body.get("ticket_id")
    if not ticket_id or not isinstance(ticket_id, str) or not ticket_id.startswith("TICKET-"):
        print(
            f"\n✗ Bad ticket_id in response: {body!r}\n"
            "  Expected something like {'ticket_id': 'TICKET-XXXXXXXX'}.\n"
            "  Check the Code node JS and the Respond Body expression.",
            file=sys.stderr,
        )
        return 5

    print(f"\n✓ Got ticket_id: {ticket_id}")
    print("\nNext checks:")
    print("  1. Open your Google Sheet — a new row should have all 8 columns populated.")
    print("  2. Open your Gmail inbox — the ticket email should be there.")
    print("  3. In n8n → Executions tab, the latest run should be all green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
