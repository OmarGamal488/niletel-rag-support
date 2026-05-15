"""n8n webhook caller for ticket creation."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


def create_ticket(
    query: str,
    session_id: str = "default",
    contact: dict | None = None,
) -> str:
    """POST the complaint to the n8n webhook and return the issued ticket_id.

    Falls back to a locally-generated UUID if the webhook is not configured
    or is unreachable, so the rest of the pipeline keeps working.

    `contact` carries name/phone/email captured by the conversational
    contact-collection flow. It is included as a nested object so n8n
    can fan out to the right fields in Google Sheets / email.
    """
    payload = {
        "query": query,
        "session_id": session_id,
        "category": "COMPLAINT",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if contact:
        payload["contact"] = contact
    if not settings.n8n_webhook_url:
        fallback = f"LOCAL-{uuid.uuid4().hex[:8].upper()}"
        logger.warning("N8N_WEBHOOK_URL not set; issuing local ticket %s", fallback)
        return fallback
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(settings.n8n_webhook_url, json=payload)
            r.raise_for_status()
            return r.json().get("ticket_id", f"N8N-{uuid.uuid4().hex[:8].upper()}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("n8n webhook failed: %s", exc)
        return f"FAILED-{uuid.uuid4().hex[:8].upper()}"
