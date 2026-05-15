"""Tier 2 unit tests: ALCE citations, CoVe, CRAG."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src import nodes as nodes_module
from src.config import settings
from src.nodes import (
    _extract_citations,
    crag_evaluator_node,
    generator_node,
    verifier_node,
    web_search_node,
)


@contextmanager
def _flags(**overrides):
    """Temporarily override Settings flags and restore on exit."""
    snapshot = {k: getattr(settings, k) for k in overrides}
    for k, v in overrides.items():
        setattr(settings, k, v)
    try:
        yield
    finally:
        for k, v in snapshot.items():
            setattr(settings, k, v)


# -------------------------------- ALCE citations --------------------------------


def test_extract_citations_pulls_unique_indices_in_range():
    assert _extract_citations("hello [1] world [2] and [1] again", max_idx=3) == [1, 2]


def test_extract_citations_drops_hallucinated_indices():
    """Model invented [9][12]; we only have 4 chunks → both must be dropped."""
    assert _extract_citations("a [9] b [12] c [3]", max_idx=4) == [3]


def test_extract_citations_empty_text():
    assert _extract_citations("", max_idx=5) == []


def test_generator_emits_citations_when_enabled():
    docs = [
        Document(page_content="c1", metadata={"source": "a.md"}),
        Document(page_content="c2", metadata={"source": "b.md"}),
    ]
    fake = FakeListChatModel(responses=["The data cap is 100GB [1][2]."])
    with _flags(citations_enabled=True), patch.object(
        nodes_module, "get_llm", return_value=fake
    ):
        out = generator_node({"query": "q", "context_docs": docs})
    assert "[1][2]" in out["answer"]
    assert out["citations"] == [1, 2]


def test_generator_skips_citations_when_disabled():
    docs = [Document(page_content="c1", metadata={"source": "a.md"})]
    fake = FakeListChatModel(responses=["plain answer [1]"])
    with _flags(citations_enabled=False), patch.object(
        nodes_module, "get_llm", return_value=fake
    ):
        out = generator_node({"query": "q", "context_docs": docs})
    assert "citations" not in out


# ---------------------------------- CoVe -----------------------------------


def test_verifier_is_noop_when_disabled():
    with _flags(chain_of_verification=False):
        out = verifier_node({"answer": "draft", "context_docs": [Document(page_content="x", metadata={})]})
    assert out == {}


def test_verifier_runs_three_step_pipeline_when_enabled():
    docs = [Document(page_content="c1", metadata={"source": "a.md"})]
    # 4 LLM calls in order: questions, ans for Q1, ans for Q2, revised answer.
    fake = FakeListChatModel(
        responses=[
            "What is the data cap?\nWhen was it set?",  # questions
            "100GB.",                                    # answer to Q1
            "Set in 2024.",                              # answer to Q2
            "Revised: cap is 100GB [1].",                # final revision
        ]
    )
    with _flags(chain_of_verification=True, citations_enabled=True), patch.object(
        nodes_module, "get_llm", return_value=fake
    ):
        out = verifier_node(
            {"query": "data cap?", "answer": "draft", "context_docs": docs}
        )
    assert out["answer"].startswith("Revised:")
    assert out["citations"] == [1]


def test_verifier_skips_when_no_context_or_no_draft():
    with _flags(chain_of_verification=True):
        # No context → skip.
        assert verifier_node({"query": "q", "answer": "draft", "context_docs": []}) == {}
        # No draft → skip.
        assert verifier_node({"query": "q", "answer": "", "context_docs": [Document(page_content="x", metadata={})]}) == {}


# ---------------------------------- CRAG -----------------------------------


def _stub_structured(rating: str):
    """Mimic the `.with_structured_output(...)` chain returning a fake CRAG
    decision. The structured-output chain must be a real `Runnable` because
    LangChain's `prompt | structured` wraps non-Runnables as `RunnableLambda`
    (which calls `__call__` instead of `.invoke`)."""
    from langchain_core.runnables import RunnableLambda

    class _Decision:
        def __init__(self, r: str) -> None:
            self.rating = r
            self.reason = "stub"

    structured = RunnableLambda(lambda _input: _Decision(rating))
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def test_crag_evaluator_disabled_short_circuits_to_correct():
    with _flags(crag_enabled=False):
        out = crag_evaluator_node(
            {"query": "q", "context_docs": [Document(page_content="x", metadata={})]}
        )
    assert out == {"retrieval_quality": "correct"}


def test_crag_evaluator_returns_incorrect_when_no_docs():
    with _flags(crag_enabled=True):
        out = crag_evaluator_node({"query": "q", "context_docs": []})
    assert out == {"retrieval_quality": "incorrect"}


def test_crag_evaluator_uses_llm_rating_when_enabled():
    docs = [Document(page_content="c1", metadata={"source": "a.md"})]
    with _flags(crag_enabled=True), patch.object(
        nodes_module, "get_llm", return_value=_stub_structured("ambiguous")
    ):
        out = crag_evaluator_node({"query": "q", "context_docs": docs})
    assert out == {"retrieval_quality": "ambiguous"}


def test_crag_evaluator_falls_back_to_correct_on_llm_failure():
    docs = [Document(page_content="c1", metadata={})]
    broken = MagicMock()
    broken.with_structured_output.side_effect = RuntimeError("LLM down")
    with _flags(crag_enabled=True), patch.object(
        nodes_module, "get_llm", return_value=broken
    ):
        out = crag_evaluator_node({"query": "q", "context_docs": docs})
    assert out == {"retrieval_quality": "correct"}


def test_web_search_node_without_tavily_returns_escalation_message():
    with _flags(tavily_api_key=""):
        out = web_search_node({"query": "out of corpus"})
    assert out["used_web_search"] is False
    assert "تذكرة" in out["answer"] or "ticket" in out["answer"].lower()
