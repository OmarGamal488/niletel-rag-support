"""FastAPI endpoint tests with the graph fully stubbed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from api.main import app
from src import nodes as nodes_module
from src import router as router_module
from src.graph import build_graph
from src.router import RouteDecision


def _stub_router(category: str):
    structured = MagicMock()
    structured.invoke.return_value = RouteDecision(
        category=category, confidence=0.9, reason="stub"
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def _client_with_stubs(category: str, answer_text: str = "stub answer"):
    """Return a (client, contextmanagers) for a graph fully stubbed for `category`."""
    build_graph.cache_clear()
    patches = [
        patch.object(router_module, "get_llm", return_value=_stub_router(category)),
        patch.object(nodes_module, "get_llm", return_value=FakeListChatModel(responses=[answer_text])),
        patch.object(
            nodes_module,
            "retrieve",
            return_value=[Document(page_content="ctx", metadata={"source": "x.md"})],
        ),
        patch.object(nodes_module, "create_ticket", return_value="TICKET-T1"),
    ]
    for p in patches:
        p.start()
    return TestClient(app), patches


def _stop(patches):
    for p in patches:
        p.stop()


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "provider" in body and "model" in body


def test_query_info_returns_answer_and_sources():
    client, patches = _client_with_stubs("INFO", "the answer")
    try:
        r = client.post("/query", json={"query": "ليه النت بطيء؟"})
    finally:
        _stop(patches)
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "INFO"
    assert body["answer"] == "the answer"
    assert body["ticket_id"] is None
    assert len(body["source_docs"]) == 1
    assert body["source_docs"][0]["source"] == "x.md"


def test_complaint_without_contact_prompts_for_it():
    """First COMPLAINT turn with no contact yields an `awaiting_contact`
    response and NO ticket — the bot is asking for name/phone/email."""
    from src.memory import memory

    memory.reset()
    client, patches = _client_with_stubs("COMPLAINT", "sorry to hear")
    try:
        r = client.post(
            "/query",
            json={"query": "الانترنت مش شغال!", "session_id": "complaint-1"},
        )
    finally:
        _stop(patches)
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "COMPLAINT"
    assert body["ticket_id"] is None
    assert body["awaiting_contact"] is True


def test_complaint_followup_with_contact_creates_ticket():
    """Second turn provides contact info → ticket gets filed and the
    session-stored contact persists for future complaints."""
    from src.memory import memory

    memory.reset()
    client, patches = _client_with_stubs("COMPLAINT", "sorry to hear")
    try:
        # Turn 1 — complaint, gate asks for contact.
        r1 = client.post(
            "/query",
            json={"query": "internet broken", "session_id": "complaint-2"},
        )
        assert r1.json()["awaiting_contact"] is True

        # Turn 2 — contact reply, ticket should be created.
        r2 = client.post(
            "/query",
            json={
                "query": "Ahmed, 01012345678, ahmed@example.com",
                "session_id": "complaint-2",
            },
        )
    finally:
        _stop(patches)
    body = r2.json()
    assert body["ticket_id"] == "TICKET-T1"
    assert body["awaiting_contact"] is False
    # And contact is now stored on the session for future complaints.
    assert memory.get_contact("complaint-2") == {
        "name": "Ahmed",
        "phone": "01012345678",
        "email": "ahmed@example.com",
    }


def test_query_validation_rejects_empty_query():
    client = TestClient(app)
    r = client.post("/query", json={"query": ""})
    assert r.status_code == 422


def test_metrics_increments_after_query():
    client, patches = _client_with_stubs("INFO", "ok")
    try:
        before = client.get("/stats").json()["total_queries"]
        client.post("/query", json={"query": "test"})
        after = client.get("/stats").json()["total_queries"]
    finally:
        _stop(patches)
    assert after == before + 1


def test_prometheus_metrics_endpoint():
    """`/metrics` should return OpenMetrics text format for Prometheus."""
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # Instrumentator emits these defaults.
    assert "http_request_duration_seconds" in body or "http_requests_total" in body
    # Our custom RAG metrics are registered (zero observations is fine).
    assert "niletel_cache_lookups_total" in body


def test_clear_history_is_204():
    client = TestClient(app)
    r = client.delete("/history/abc")
    assert r.status_code == 204
