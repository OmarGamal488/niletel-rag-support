"""Pydantic models for the FastAPI request/response layer."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.state import Category


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    session_id: str = "default"


class SourceDoc(BaseModel):
    source: str
    snippet: str
    rerank_score: Optional[float] = None
    cited: bool = False  # set True if this chunk appears in `citations`


class ToolCall(BaseModel):
    name: str
    args: dict = {}
    result: str = ""
    # Parsed result (when JSON-able) — frontends use this to pick a
    # generative-UI renderer per tool.
    data: Optional[dict | list] = None


class TraceEvent(BaseModel):
    """One node firing inside the LangGraph pipeline."""

    step: int
    node: str
    elapsed_ms: float
    delta_keys: list[str] = []
    summary: str = ""


class QueryResponse(BaseModel):
    answer: str
    category: Category
    confidence: Optional[float] = None
    ticket_id: Optional[str] = None
    source_docs: list[SourceDoc] = []
    # ALCE: 1-indexed chunk numbers referenced inline as [N] in `answer`.
    citations: list[int] = []
    # CRAG: "correct" | "ambiguous" | "incorrect" — empty when feature is off.
    retrieval_quality: Optional[str] = None
    used_web_search: bool = False
    # Tier 3 — observability fields:
    used_cache: bool = False
    pii_kinds: list[str] = []  # types of PII redacted from the query, e.g. ["EG_PHONE"]
    tool_calls: list[ToolCall] = []
    # Conversational ticket flow — True when the graph paused on a
    # COMPLAINT to collect the user's contact info. The UI can use this
    # to highlight that the next message should be name/phone/email.
    awaiting_contact: bool = False
    # Under-the-hood trace — one entry per LangGraph node that fired.
    trace: list[TraceEvent] = []
    total_elapsed_ms: Optional[float] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    provider: str
    model: str


class MetricsResponse(BaseModel):
    total_queries: int
    by_category: dict[str, int]
    avg_latency_ms: float


class HistoryTurn(BaseModel):
    role: str
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    turns: list[HistoryTurn] = []
