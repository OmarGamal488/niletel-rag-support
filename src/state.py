"""Shared state types for the LangGraph pipeline."""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.documents import Document
from langgraph.graph.message import add_messages

Category = Literal["INFO", "COMPLAINT", "GREETING", "OUT_OF_SCOPE", "ACTION"]


class SupportState(TypedDict, total=False):
    query: str  # current (possibly PII-redacted) query the LLM sees
    query_original: str  # pre-redaction copy, used by the ticketer
    category: Category
    confidence: float
    context_docs: list[Document]
    answer: str
    ticket_id: str | None
    session_id: str
    history: list[dict]  # prior turns: [{"role": "user"|"assistant", "content": str}]
    citations: list[int]  # ALCE: 1-indexed chunk numbers cited by the answer
    retrieval_quality: str  # CRAG: "correct" | "ambiguous" | "incorrect"
    used_web_search: bool  # CRAG: True if web fallback was triggered
    pii_map: dict[str, str]  # placeholder → original PII span
    pii_kinds: list[str]  # entity kinds redacted from this turn
    used_cache: bool  # semantic cache served this query
    tool_calls: list[dict]  # ReAct agent tool invocations
    # ---- Conversational ticket flow ----
    # `contact` is populated by the API layer from session memory (or
    # parsed from the current turn). `awaiting_contact` is set by the
    # contact_gate node when we still need the user's details; the
    # ticketer is skipped in that case so the run can end cleanly with
    # the prompt-for-contact answer.
    contact: dict
    awaiting_contact: bool
    # `messages` is what CopilotKit / AG-UI hand us, AND what our ACTION
    # tool-loop appends to. `add_messages` is the LangGraph reducer that
    # APPENDS instead of replacing — so multiple action_llm rounds stack
    # cleanly into one running message list.
    messages: Annotated[list, add_messages]
