"""Retriever dispatch + RRF + HyDE + rerank + reorder tests (no Chroma, no
real LLM, no real cross-encoder — all heavy components are stubbed)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from src import retriever as retr_module
from src.config import settings
from src.retriever import _rrf_fuse


def _doc(text: str, source: str, start: int = 0) -> Document:
    return Document(
        page_content=text, metadata={"source": source, "start_index": start}
    )


@contextmanager
def _disable_heavy_stages():
    """Skip the cross-encoder + reorder for plain dispatch tests."""
    original_rerank = settings.reranker_enabled
    original_reorder = settings.long_context_reorder
    settings.reranker_enabled = False
    settings.long_context_reorder = False
    try:
        yield
    finally:
        settings.reranker_enabled = original_rerank
        settings.long_context_reorder = original_reorder


# ----------------------------- RRF -----------------------------

def test_rrf_fuse_ranks_consensus_doc_first():
    a, b, c = _doc("alpha", "a.md"), _doc("beta", "b.md"), _doc("gamma", "c.md")
    fused = _rrf_fuse([[a, b, c], [a, c, b]], k_top=3)
    assert fused[0].metadata["source"] == "a.md"
    assert {d.metadata["source"] for d in fused} == {"a.md", "b.md", "c.md"}


def test_rrf_fuse_dedupes_same_key():
    a = _doc("alpha", "a.md")
    fused = _rrf_fuse([[a], [a]], k_top=2)
    assert len(fused) == 1


# ----------------------------- HyDE dispatch -----------------------------

def test_hyde_mode_routes_through_hypothetical_doc():
    fake_dense = MagicMock()
    fake_dense.invoke.return_value = [_doc("dense-hit", "d.md")]
    fake_bm25 = MagicMock()
    fake_bm25.invoke.return_value = [_doc("bm25-hit", "b.md")]

    original_mode = settings.retrieval_mode
    settings.retrieval_mode = "hyde"
    try:
        with _disable_heavy_stages(), (
            patch.object(retr_module, "_generate_hypothetical_doc", return_value="hyp")
        ), (
            patch.object(retr_module, "_load_dense_retriever", return_value=fake_dense)
        ), (
            patch.object(retr_module, "_load_bm25_retriever", return_value=fake_bm25)
        ):
            docs = retr_module.retrieve("my query", k=2)
    finally:
        settings.retrieval_mode = original_mode

    fake_dense.invoke.assert_called_once_with("hyp")
    fake_bm25.invoke.assert_called_once_with("my query")
    assert {d.metadata["source"] for d in docs} == {"d.md", "b.md"}


def test_hyde_falls_back_to_raw_query_when_llm_fails():
    fake_dense = MagicMock()
    fake_dense.invoke.return_value = [_doc("d", "d.md")]
    fake_bm25 = MagicMock()
    fake_bm25.invoke.return_value = [_doc("b", "b.md")]

    original_mode = settings.retrieval_mode
    settings.retrieval_mode = "hyde"
    try:
        with _disable_heavy_stages(), (
            patch("src.llm.get_llm", side_effect=RuntimeError("LLM down"))
        ), (
            patch.object(retr_module, "_load_dense_retriever", return_value=fake_dense)
        ), (
            patch.object(retr_module, "_load_bm25_retriever", return_value=fake_bm25)
        ):
            retr_module.retrieve("raw-q", k=2)
    finally:
        settings.retrieval_mode = original_mode

    fake_dense.invoke.assert_called_once_with("raw-q")


# ----------------------------- Reranker -----------------------------

def test_rerank_orders_by_cross_encoder_score():
    docs = [
        _doc("docA", "a.md"),
        _doc("docB", "b.md"),
        _doc("docC", "c.md"),
    ]
    fake_ce = MagicMock()
    # Scores intentionally NOT in the input order — reranker should re-sort.
    fake_ce.predict.return_value = [0.1, 0.9, 0.5]

    original = settings.reranker_enabled
    settings.reranker_enabled = True
    try:
        with patch.object(retr_module, "_cross_encoder", return_value=fake_ce):
            top = retr_module._rerank("q", docs, k_top=2)
    finally:
        settings.reranker_enabled = original

    assert [d.metadata["source"] for d in top] == ["b.md", "c.md"]
    # Scores get persisted onto metadata for downstream display.
    assert top[0].metadata["rerank_score"] == 0.9
    assert top[1].metadata["rerank_score"] == 0.5


def test_rerank_disabled_passthrough():
    docs = [_doc("a", "a.md"), _doc("b", "b.md"), _doc("c", "c.md")]
    original = settings.reranker_enabled
    settings.reranker_enabled = False
    try:
        # _cross_encoder() must NOT be called when reranker is disabled.
        with patch.object(retr_module, "_cross_encoder", side_effect=AssertionError("ce loaded")):
            top = retr_module._rerank("q", docs, k_top=2)
    finally:
        settings.reranker_enabled = original
    assert [d.metadata["source"] for d in top] == ["a.md", "b.md"]


# ----------------------------- Reorder -----------------------------

def test_long_context_reorder_moves_top_docs_to_ends():
    """LongContextReorder folds the original ranked list so the highest-
    ranked items sit at the start and end."""
    docs = [_doc(f"d{i}", f"{i}.md") for i in range(5)]  # ranked best→worst

    original = settings.long_context_reorder
    settings.long_context_reorder = True
    try:
        retr_module._reorder.cache_clear()
        out = retr_module._apply_long_context_reorder(docs)
    finally:
        settings.long_context_reorder = original

    # Top-ranked (index 0) should end up at one of the ends of the list,
    # not in the middle.
    positions = {d.metadata["source"]: i for i, d in enumerate(out)}
    assert positions["0.md"] in (0, len(out) - 1)


def test_long_context_reorder_disabled_keeps_order():
    docs = [_doc("a", "a.md"), _doc("b", "b.md"), _doc("c", "c.md")]
    original = settings.long_context_reorder
    settings.long_context_reorder = False
    try:
        out = retr_module._apply_long_context_reorder(docs)
    finally:
        settings.long_context_reorder = original
    assert [d.metadata["source"] for d in out] == ["a.md", "b.md", "c.md"]


def test_long_context_reorder_skipped_for_short_lists():
    """Reorder is a no-op for <3 docs — nothing to reshuffle."""
    docs = [_doc("a", "a.md"), _doc("b", "b.md")]
    original = settings.long_context_reorder
    settings.long_context_reorder = True
    try:
        out = retr_module._apply_long_context_reorder(docs)
    finally:
        settings.long_context_reorder = original
    assert out == docs


# ----------------------------- RAG-Fusion -----------------------------


def test_generate_fusion_queries_parses_multiline_response():
    """The paraphrase prompt asks for one query per line — verify we strip
    numbering, junk lines, duplicates of the original."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    fake = FakeListChatModel(
        responses=[
            "Paraphrases:\n"
            "1. how fast is my fiber?\n"
            "  - what's wrong with my net?\n"
            "  why is internet slow?\n"
            "ليه النت بطيء؟\n"  # exact original — should be filtered
            "\n"
            "ok\n"  # too short — should be filtered
        ]
    )
    with patch("src.llm.get_llm", return_value=fake):
        out = retr_module._generate_fusion_queries("ليه النت بطيء؟", n=3)
    assert len(out) == 3
    assert "ليه النت بطيء؟" not in out
    assert all(len(q) >= 4 for q in out)


def test_generate_fusion_queries_falls_back_on_llm_failure():
    with patch("src.llm.get_llm", side_effect=RuntimeError("LLM down")):
        out = retr_module._generate_fusion_queries("anything", n=3)
    assert out == []


def test_rag_fusion_retrieve_calls_hybrid_per_variation():
    """Original + 2 paraphrases → hybrid retriever invoked 3 times → RRF
    fuses the 3 result lists."""
    a, b, c = _doc("a", "a.md"), _doc("b", "b.md"), _doc("c", "c.md")
    fake_hybrid = MagicMock()
    fake_hybrid.invoke.side_effect = [[a, b], [b, c], [a, c]]

    original_mode = settings.retrieval_mode
    original_n = settings.rag_fusion_num_queries
    settings.retrieval_mode = "rag_fusion"
    settings.rag_fusion_num_queries = 3  # original + 2 paraphrases
    try:
        with _disable_heavy_stages(), (
            patch.object(
                retr_module,
                "_generate_fusion_queries",
                return_value=["paraphrase 1", "paraphrase 2"],
            )
        ), patch.object(retr_module, "get_hybrid_retriever", return_value=fake_hybrid):
            docs = retr_module.retrieve("original query", k=3)
    finally:
        settings.retrieval_mode = original_mode
        settings.rag_fusion_num_queries = original_n

    # Hybrid retriever invoked once per variation (1 original + 2 paraphrases)
    assert fake_hybrid.invoke.call_count == 3
    # Fused output contains all 3 docs (every doc appeared in ≥1 list)
    assert {d.metadata["source"] for d in docs} == {"a.md", "b.md", "c.md"}


def test_rag_fusion_handles_empty_paraphrases_gracefully():
    """If the LLM step fails / returns nothing, we still retrieve once on
    the original query — never raise to the caller."""
    a = _doc("a", "a.md")
    fake_hybrid = MagicMock()
    fake_hybrid.invoke.return_value = [a]

    original_mode = settings.retrieval_mode
    settings.retrieval_mode = "rag_fusion"
    try:
        with _disable_heavy_stages(), (
            patch.object(retr_module, "_generate_fusion_queries", return_value=[])
        ), patch.object(retr_module, "get_hybrid_retriever", return_value=fake_hybrid):
            docs = retr_module.retrieve("q", k=3)
    finally:
        settings.retrieval_mode = original_mode

    assert fake_hybrid.invoke.call_count == 1
    assert [d.metadata["source"] for d in docs] == ["a.md"]
