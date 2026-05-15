"""LLM-based intent router with Pydantic structured output."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.config import settings
from src.llm import get_llm
from src.state import Category

ROUTER_PROMPT = """You are an intent classifier for NileTel — an Egyptian telecom company.

Decide the **primary intent** of the customer message and pick exactly ONE label:

- **INFO**: the user is ASKING a question — wants information, explanation, or help.
  Includes "why is X slow?", "how do I cancel?", "what is 5G?", troubleshooting questions,
  policy questions. INFO covers questions about problems too — as long as they're framed
  as a question seeking help (ends in ؟ or starts with ليه/إزاي/كيف/why/how/what).
  Examples: "ليه النت بطيء؟", "إزاي أعمل refund؟", "How do I escalate?"

- **COMPLAINT**: a STATEMENT of frustration or a direct demand to fix something — NOT a
  question. The user is venting, threatening, or reporting that something is broken with
  emphasis. Often has exclamation marks or angry tone.
  Examples: "الانترنت مش شغال خالص!", "I want my money back NOW!", "هشتكي للـ NTRA"

- **GREETING**: pure greeting, thanks, or small-talk with no real request.
  Examples: "مرحبا", "شكرا", "hi", "good morning"
{action_section}
- **OUT_OF_SCOPE**: nothing to do with NileTel / telecom / customer support.
  Examples: "What is 2+2?", "tell me a joke", weather, other companies

Rule of thumb: **questions = INFO, exclamations/demands = COMPLAINT**.
If the user is genuinely asking *how* or *why*, even about a broken thing, it's INFO.

Respond ONLY with the structured object — no extra text.

Query: {query}
"""

_ACTION_SECTION = """
- **ACTION**: the user wants the system to PERFORM an account operation —
  look something up, change something, or trigger a workflow. Almost always
  references a specific identifier (phone number, account ID, ticket ID).
  Examples:
    - "check the balance for 01012345678"
    - "list my open tickets, account 1001"
    - "اعملي escalate للتذكرة TKT-42"
    - "what's the data balance on <PHONE_1>?"
"""


class RouteDecision(BaseModel):
    category: Category = Field(
        description="One of INFO, COMPLAINT, GREETING, OUT_OF_SCOPE, ACTION."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence between 0 and 1.")
    reason: str = Field(description="Short justification (one short sentence).")


def classify(query: str, config=None) -> RouteDecision:
    """Classify the user query into a route.

    `config` is forwarded to the structured-output LLM so callers can
    suppress AG-UI message emission (router output should never reach
    the user as visible chat — only `state["category"]` matters)."""
    action_section = _ACTION_SECTION if settings.tool_agent_enabled else ""
    structured_llm = get_llm(temperature=0.0).with_structured_output(RouteDecision)
    return structured_llm.invoke(
        ROUTER_PROMPT.format(query=query, action_section=action_section),
        config=config,
    )
