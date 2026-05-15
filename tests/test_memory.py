"""Tests for the in-process conversation memory and history endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from api.main import app
from src import nodes as nodes_module
from src import router as router_module
from src.graph import build_graph
from src.memory import ConversationMemory, memory
from src.router import RouteDecision


def _stub_router(category: str):
    structured = MagicMock()
    structured.invoke.return_value = RouteDecision(
        category=category, confidence=0.9, reason="stub"
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


# ----------------------- ConversationMemory unit tests ----------------------

def test_memory_append_and_get_round_trip():
    mem = ConversationMemory(max_turns=4)
    mem.append("s1", "user", "hello")
    mem.append("s1", "assistant", "hi")
    turns = mem.get("s1")
    assert turns == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_memory_bounded_by_max_turns():
    mem = ConversationMemory(max_turns=3)
    for i in range(5):
        mem.append("s", "user", f"q{i}")
    contents = [t["content"] for t in mem.get("s")]
    assert contents == ["q2", "q3", "q4"]


def test_memory_clear_removes_session():
    mem = ConversationMemory()
    mem.append("s", "user", "x")
    assert mem.clear("s") is True
    assert mem.get("s") == []
    assert mem.clear("s") is False  # idempotent


def test_memory_sessions_are_isolated():
    mem = ConversationMemory()
    mem.append("a", "user", "for-a")
    mem.append("b", "user", "for-b")
    assert mem.get("a")[0]["content"] == "for-a"
    assert mem.get("b")[0]["content"] == "for-b"


def test_memory_ignores_empty_content():
    mem = ConversationMemory()
    mem.append("s", "user", "")
    assert mem.get("s") == []


# ----------------------- API integration tests ------------------------------

def _make_client(category: str = "INFO"):
    build_graph.cache_clear()
    memory.reset()
    patches = [
        patch.object(router_module, "get_llm", return_value=_stub_router(category)),
        patch.object(
            nodes_module,
            "get_llm",
            return_value=FakeListChatModel(responses=["ok-answer"]),
        ),
        patch.object(
            nodes_module,
            "retrieve",
            return_value=[Document(page_content="ctx", metadata={"source": "x.md"})],
        ),
        patch.object(nodes_module, "create_ticket", return_value="T-1"),
    ]
    for p in patches:
        p.start()
    return TestClient(app), patches


def _stop(patches):
    for p in patches:
        p.stop()


def test_query_persists_history_for_session():
    client, patches = _make_client()
    try:
        client.post("/query", json={"query": "first", "session_id": "demo"})
        r = client.get("/history/demo")
    finally:
        _stop(patches)
    body = r.json()
    assert r.status_code == 200
    assert body["session_id"] == "demo"
    # one user turn + one assistant turn
    roles = [t["role"] for t in body["turns"]]
    assert roles == ["user", "assistant"]
    assert body["turns"][0]["content"] == "first"
    assert body["turns"][1]["content"] == "ok-answer"


def test_delete_history_clears_session():
    client, patches = _make_client()
    try:
        client.post("/query", json={"query": "hi", "session_id": "ses"})
        r1 = client.delete("/history/ses")
        r2 = client.get("/history/ses")
    finally:
        _stop(patches)
    assert r1.status_code == 204
    assert r2.json()["turns"] == []


def test_history_is_per_session():
    client, patches = _make_client()
    try:
        client.post("/query", json={"query": "alpha", "session_id": "A"})
        client.post("/query", json={"query": "beta", "session_id": "B"})
        a = client.get("/history/A").json()["turns"]
        b = client.get("/history/B").json()["turns"]
    finally:
        _stop(patches)
    assert [t["content"] for t in a if t["role"] == "user"] == ["alpha"]
    assert [t["content"] for t in b if t["role"] == "user"] == ["beta"]
