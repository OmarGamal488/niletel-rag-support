"""End-to-end graph routing tests with a stubbed LLM."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src import nodes as nodes_module
from src import router as router_module
from src.router import RouteDecision


def _stub_router(category: str):
    """Mock the structured-output LLM used by router.classify."""
    structured = MagicMock()
    structured.invoke.return_value = RouteDecision(
        category=category, confidence=0.99, reason="stub"
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def _fake_chat(text: str):
    """A real Runnable LLM that always returns `text` — works in LCEL pipes."""
    return FakeListChatModel(responses=[text])


def test_graph_info_path_skips_ticketer():
    from src.graph import build_graph

    build_graph.cache_clear()
    with (
        patch.object(router_module, "get_llm", return_value=_stub_router("INFO")),
        patch.object(nodes_module, "get_llm", return_value=_fake_chat("answer")),
        patch.object(
            nodes_module,
            "retrieve",
            return_value=[Document(page_content="ctx", metadata={"source": "x.md"})],
        ),
    ):
        result = build_graph().invoke({"query": "ليه النت بطيء؟"})
    assert result["category"] == "INFO"
    assert result["answer"] == "answer"
    assert result.get("ticket_id") is None


def test_graph_complaint_with_contact_creates_ticket():
    """Complaint path with contact info pre-populated → ticketer runs."""
    from src.graph import build_graph

    build_graph.cache_clear()
    with (
        patch.object(router_module, "get_llm", return_value=_stub_router("COMPLAINT")),
        patch.object(nodes_module, "get_llm", return_value=_fake_chat("sorry")),
        patch.object(
            nodes_module,
            "retrieve",
            return_value=[Document(page_content="ctx", metadata={"source": "x.md"})],
        ),
        patch.object(nodes_module, "create_ticket", return_value="TICKET-123"),
    ):
        result = build_graph().invoke({
            "query": "الانترنت مش شغال!",
            "contact": {"name": "Ahmed", "phone": "01012345678"},
        })
    assert result["category"] == "COMPLAINT"
    assert result["ticket_id"] == "TICKET-123"
    assert not result.get("awaiting_contact")


def test_graph_complaint_without_contact_asks_and_skips_ticket():
    """Complaint path without contact info → contact_gate sets the
    prompt-for-contact answer and skips the ticketer."""
    from src.graph import build_graph

    build_graph.cache_clear()
    with (
        patch.object(router_module, "get_llm", return_value=_stub_router("COMPLAINT")),
        patch.object(nodes_module, "get_llm", return_value=_fake_chat("sorry")),
        patch.object(
            nodes_module,
            "retrieve",
            return_value=[Document(page_content="ctx", metadata={"source": "x.md"})],
        ),
        patch.object(nodes_module, "create_ticket", return_value="TICKET-123"),
    ):
        result = build_graph().invoke({"query": "الانترنت مش شغال!"})
    assert result["category"] == "COMPLAINT"
    assert result.get("ticket_id") is None
    assert result.get("awaiting_contact") is True
    assert "phone" in result["answer"].lower() or "email" in result["answer"].lower()


def test_graph_greeting_skips_retrieval():
    from src.graph import build_graph

    build_graph.cache_clear()
    with (
        patch.object(router_module, "get_llm", return_value=_stub_router("GREETING")),
        patch.object(nodes_module, "get_llm", return_value=_fake_chat("أهلاً")),
    ):
        result = build_graph().invoke({"query": "مرحبا"})
    assert result["category"] == "GREETING"
    assert result["answer"] == "أهلاً"
    assert result.get("context_docs") == []


def test_graph_out_of_scope_uses_static_message():
    from src.graph import build_graph

    build_graph.cache_clear()
    with patch.object(
        router_module, "get_llm", return_value=_stub_router("OUT_OF_SCOPE")
    ):
        result = build_graph().invoke({"query": "What is 2+2?"})
    assert result["category"] == "OUT_OF_SCOPE"
    assert "NileTel" in result["answer"]
