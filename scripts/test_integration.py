"""End-to-end integration test: API → LangGraph → n8n → ticket.

Exercises the full two-turn flow against a running FastAPI instance:

    Turn 1:  POST /query  with a complaint
             ↳ expects awaiting_contact=True, ticket_id=None
                (graph asks for name/phone/email)

    Turn 2:  POST /query  with contact info on the SAME session_id
             ↳ expects awaiting_contact=False, ticket_id starts with "TICKET-"
                which proves the response came from n8n
                (not "LOCAL-..." or "FAILED-..." fallbacks)

After this passes, your Streamlit demo will end-to-end produce real
n8n-issued tickets, write Google Sheet rows, and send Gmail emails.

Usage:
    # 1. Start the API in a separate terminal:
    #    ./scripts/start_demo.sh   (or: uv run uvicorn api.main:app --port 8000)
    # 2. Run this:
    uv run python scripts/test_integration.py
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

DEFAULT_API = "http://127.0.0.1:8000"


def _post(client: httpx.Client, body: dict) -> dict:
    r = client.post("/query", json=body, timeout=60.0)
    r.raise_for_status()
    return r.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=DEFAULT_API, help="FastAPI base URL")
    parser.add_argument(
        "--complaint",
        default="الانترنت مش شغال خالص من ساعتين، عايز حد يصلح المشكلة",
        help="Complaint message for turn 1.",
    )
    parser.add_argument("--name", default="Sara Integration")
    parser.add_argument("--phone", default="01098765432")
    parser.add_argument("--email", default="sara.integration@test.com")
    args = parser.parse_args()

    session_id = f"integration-{int(time.time())}"
    print(f"→ API   {args.api}")
    print(f"  sid   {session_id}\n")

    with httpx.Client(base_url=args.api) as client:
        # ---- Health gate ---------------------------------------------------
        try:
            h = client.get("/health", timeout=5.0)
            h.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"✗ API not reachable at {args.api}: {exc}", file=sys.stderr)
            print(
                "  Start it first:  ./scripts/start_demo.sh",
                file=sys.stderr,
            )
            return 1
        print(f"✓ Health: {h.json().get('status')} ({h.json().get('provider')})\n")

        # ---- Turn 1 — complaint without contact ----------------------------
        print("── Turn 1: complaint, no contact yet ──")
        r1 = _post(client, {"query": args.complaint, "session_id": session_id})
        print(f"  category        = {r1.get('category')}")
        print(f"  awaiting_contact= {r1.get('awaiting_contact')}")
        print(f"  ticket_id       = {r1.get('ticket_id')}")
        print(f"  answer (excerpt)= {(r1.get('answer') or '')[:120]}...\n")

        if r1.get("category") != "COMPLAINT":
            print(
                f"✗ Expected category=COMPLAINT, got {r1.get('category')!r}.\n"
                "  The router classified the query differently — try a stronger "
                "complaint phrasing.",
                file=sys.stderr,
            )
            return 2
        if not r1.get("awaiting_contact"):
            print(
                "✗ Expected awaiting_contact=True on turn 1, "
                "but the graph went straight to ticketing.\n"
                "  Check src/nodes.py contact_gate_node and src/graph.py routing.",
                file=sys.stderr,
            )
            return 3
        if r1.get("ticket_id"):
            print(
                f"✗ Turn 1 should NOT have a ticket_id, got {r1.get('ticket_id')!r}.\n"
                "  Ticket should only be filed after contact is captured.",
                file=sys.stderr,
            )
            return 4

        # ---- Turn 2 — contact reply triggers ticketing --------------------
        print("── Turn 2: contact reply, ticket should be filed ──")
        contact_msg = f"{args.name}, {args.phone}, {args.email}"
        r2 = _post(client, {"query": contact_msg, "session_id": session_id})
        print(f"  category        = {r2.get('category')}")
        print(f"  awaiting_contact= {r2.get('awaiting_contact')}")
        print(f"  ticket_id       = {r2.get('ticket_id')}")

        tid = r2.get("ticket_id") or ""
        if not tid:
            print(
                "\n✗ Turn 2 returned no ticket_id. The graph didn't reach the "
                "ticketer.",
                file=sys.stderr,
            )
            return 5
        if tid.startswith("LOCAL-"):
            print(
                f"\n✗ Got LOCAL-* ticket ({tid}) — N8N_WEBHOOK_URL is unset or "
                ".env wasn't loaded.\n"
                "  Check niletel-rag-support/.env contains N8N_WEBHOOK_URL=https://...",
                file=sys.stderr,
            )
            return 6
        if tid.startswith("FAILED-"):
            print(
                f"\n✗ Got FAILED-* ticket ({tid}) — the n8n webhook call raised.\n"
                "  Run  scripts/test_n8n.py  to isolate the n8n side.",
                file=sys.stderr,
            )
            return 7
        if not tid.startswith("TICKET-"):
            print(
                f"\n✗ Unexpected ticket prefix in {tid!r}. The webhook responded but "
                "didn't return a 'ticket_id' key.\n"
                "  Check Respond to Webhook → Response Body in n8n.",
                file=sys.stderr,
            )
            return 8

        print(f"\n✓ Got real n8n ticket: {tid}")
        print("\nNext manual checks:")
        print(f"  • Google Sheet — last row should have ticket {tid}")
        print(f"    name='{args.name}', phone='{args.phone}', email='{args.email}',")
        print("    category='COMPLAINT', and the original complaint in Query.")
        print("  • Gmail inbox — styled email with the same ticket id.")
        print("  • n8n → Executions tab — the latest run should be all green.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
