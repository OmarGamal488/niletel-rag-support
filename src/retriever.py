"""Two-stage retrieval pipeline (Tier 1 upgrade).

Stage 1 — candidate generation
  Either:
    * `hybrid` mode: dense (Chroma + bge-m3) + sparse (BM25) fused with RRF
    * `hyde`   mode: LLM writes a hypothetical answer; embed *that* for the
                     dense leg; BM25 still runs on the raw query; fused via RRF
  Returns up to `settings.retriever_top_n` candidates (wide pool, e.g. 20).

Stage 2 — cross-encoder reranking (bge-reranker-v2-m3, multilingual)
  Re-scores each (query, doc) pair with full self-attention. Drops the pool
  from top-N down to `settings.top_k` (e.g. 4) by precision.

Stage 3 — Long-context reordering
  Reshuffles the final k chunks so the highest-scoring ones sit at positions
  0 and k-1, weakest in the middle. Mitigates the "Lost in the Middle"
  attention bias (Liu et al., 2023).

Each stage is independently toggleable via the Settings flags.
"""

from __future__ import annotations

import logging
import pickle
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.document_transformers import LongContextReorder
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_huggingface import HuggingFaceEmbeddings

from src.config import settings

logger = logging.getLogger(__name__)

HYDE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a NileTel telecom support knowledge base. Given a customer "
            "question, write a SHORT plausible passage (2-4 sentences) that would "
            "answer it, using domain vocabulary (FTTH, ONT, throttling, splitter, "
            "VLR, BSS, ticket, etc.). The passage doesn't have to be factually "
            "perfect — its purpose is to embed near the right documents. Mirror "
            "the user's language (Arabic, English, or mixed).",
        ),
        ("human", "{query}"),
    ]
)

RAG_FUSION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You generate query variations for retrieval expansion in a NileTel "
            "(Egyptian telecom) customer-support knowledge base. Rewrite the "
            "user's question as {n} short paraphrases that approach the SAME "
            "telecom intent with different wording — use synonyms, domain "
            "vocabulary (FTTH, ONT, throttling, splitter, quota, plan, روتر, "
            "فايبر, باقة, تذكرة), and alternative phrasings. Treat Egyptian "
            "slang as telecom complaints ('نتي وحش' = slow internet, 'الموبايل "
            "مش راضي يشتغل' = phone service issue). Mirror the user's language "
            "(Arabic, English, or mixed). Output one paraphrase per line. No "
            "numbering, no preamble, no commentary.",
        ),
        ("human", "{query}"),
    ]
)


# ---------------------------------------------------------------- Stage 1 ----
@lru_cache(maxsize=1)
def _embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=settings.embedding_model)


def _load_dense_retriever(k: int | None = None) -> BaseRetriever:
    vs = Chroma(
        persist_directory=str(settings.chroma_dir),
        embedding_function=_embeddings(),
        collection_name="niletel_kb",
    )
    return vs.as_retriever(
        search_kwargs={"k": k or settings.retriever_top_n}
    )


def _load_bm25_retriever(k: int | None = None) -> BM25Retriever:
    with settings.bm25_path.open("rb") as f:
        payload = pickle.load(f)
    chunks: list[Document] = payload["chunks"]
    retriever = BM25Retriever.from_documents(chunks)
    retriever.k = k or settings.retriever_top_n
    return retriever


@lru_cache(maxsize=1)
def get_hybrid_retriever() -> EnsembleRetriever:
    """Dense + BM25 fused with RRF (0.5/0.5), wide pool for reranking."""
    return EnsembleRetriever(
        retrievers=[_load_bm25_retriever(), _load_dense_retriever()],
        weights=[0.5, 0.5],
    )


# RRF helpers used by HyDE mode (kept identical so unit tests still pass) ----
def _doc_key(doc: Document) -> str:
    src = doc.metadata.get("source", "?")
    start = doc.metadata.get("start_index", "")
    return f"{src}:{start}:{doc.page_content[:60]}"


def _rrf_fuse(
    ranked_lists: list[list[Document]],
    k_top: int,
    rrf_k: int = 60,
) -> list[Document]:
    scores: dict[str, float] = {}
    docs_by_key: dict[str, Document] = {}
    for ranking in ranked_lists:
        for rank, doc in enumerate(ranking):
            key = _doc_key(doc)
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)
            docs_by_key.setdefault(key, doc)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [docs_by_key[k] for k, _ in ordered[:k_top]]


def _generate_hypothetical_doc(query: str) -> str:
    """LLM-generated passage for HyDE embedding. Falls back to the raw query
    on any failure so retrieval still produces results."""
    try:
        from src.llm import get_llm  # local import so test stubs apply

        chain = HYDE_PROMPT | get_llm(temperature=0.2)
        out = chain.invoke({"query": query})
        text = (out.content or "").strip()
        return text or query
    except Exception:  # noqa: BLE001
        logger.warning("HyDE generation failed; falling back to raw query.")
        return query


def _hyde_retrieve(query: str, k_top: int) -> list[Document]:
    hyp_doc = _generate_hypothetical_doc(query)
    dense_docs = _load_dense_retriever().invoke(hyp_doc)
    bm25_docs = _load_bm25_retriever().invoke(query)
    return _rrf_fuse([dense_docs, bm25_docs], k_top=k_top)


# ------------------------------------ RAG-Fusion (Rackauckas 2024) ----


def _generate_fusion_queries(query: str, n: int) -> list[str]:
    """Ask the LLM for `n` paraphrases of the user's query. Falls back to
    an empty list (so the original query is still used) on any failure."""
    if n <= 0:
        return []
    try:
        from src.llm import get_llm  # local import for test stubability

        chain = RAG_FUSION_PROMPT | get_llm(temperature=0.4)
        out = chain.invoke({"query": query, "n": n})
        lines = [
            line.strip().lstrip("0123456789.-) ").strip()
            for line in (out.content or "").splitlines()
        ]
        # Drop empties, the original, and obvious junk like "Paraphrases:" headers.
        seen = {query.strip()}
        result: list[str] = []
        for line in lines:
            if not line or len(line) < 4 or line in seen:
                continue
            if line.endswith(":") and len(line.split()) <= 3:
                continue
            seen.add(line)
            result.append(line)
            if len(result) >= n:
                break
        return result
    except Exception:  # noqa: BLE001
        logger.warning("RAG-Fusion paraphrase step failed; using original query only.")
        return []


def _rag_fusion_retrieve(query: str, k_top: int) -> list[Document]:
    """Multi-query retrieval: original + paraphrases → each runs hybrid
    retrieval → all result lists RRF-fused into one ranked pool.

    The hybrid leg is reused per query, so each sub-retrieval is already
    dense+BM25+RRF. The outer fuse stitches across query variations.
    """
    # Original query is always one of the rankings → at most n-1 paraphrases.
    n_paraphrases = max(0, settings.rag_fusion_num_queries - 1)
    variations = [query] + _generate_fusion_queries(query, n=n_paraphrases)
    rankings: list[list[Document]] = []
    for q in variations:
        docs = get_hybrid_retriever().invoke(q)
        if docs:
            rankings.append(docs[:k_top])
    if not rankings:
        return []
    return _rrf_fuse(rankings, k_top=k_top)


def _stage1_candidates(query: str, top_n: int) -> list[Document]:
    """Wide candidate pool from hybrid, HyDE, or RAG-Fusion retrieval."""
    mode = settings.retrieval_mode
    if mode == "hyde":
        return _hyde_retrieve(query, k_top=top_n)
    if mode == "rag_fusion":
        return _rag_fusion_retrieve(query, k_top=top_n)
    # default: plain hybrid
    docs = get_hybrid_retriever().invoke(query)
    return docs[:top_n]


# ---------------------------------------------------------------- Stage 2 ----
@lru_cache(maxsize=1)
def _cross_encoder():
    """Multilingual cross-encoder for (query, doc) reranking.

    Lazily imported because `sentence_transformers` pulls torch — we want
    test runs that don't touch the reranker (e.g. existing graph tests
    that mock `retrieve`) to stay fast.
    """
    from sentence_transformers import CrossEncoder

    logger.info("Loading cross-encoder reranker: %s", settings.reranker_model)
    return CrossEncoder(settings.reranker_model)


def _rerank(query: str, docs: list[Document], k_top: int) -> list[Document]:
    """Score every (query, doc) pair and keep the top-`k_top` by relevance.

    Cross-encoders run full self-attention over the pair so they catch
    paraphrase + multilingual matches that bi-encoder cosine misses.
    Cost: one forward pass per candidate (linear in pool size) — fine for
    pools of 10–50 on CPU.
    """
    if not docs:
        return []
    if not settings.reranker_enabled:
        return docs[:k_top]
    pairs = [(query, d.page_content) for d in docs]
    scores = _cross_encoder().predict(pairs)
    ranked = sorted(
        zip(docs, scores, strict=True),
        key=lambda pair: float(pair[1]),
        reverse=True,
    )
    top = ranked[:k_top]
    # Stash the score in metadata so the UI / source cards can show it.
    for doc, score in top:
        doc.metadata = {**doc.metadata, "rerank_score": float(score)}
    return [d for d, _ in top]


# ---------------------------------------------------------------- Stage 3 ----
@lru_cache(maxsize=1)
def _reorder() -> LongContextReorder:
    return LongContextReorder()


def _apply_long_context_reorder(docs: list[Document]) -> list[Document]:
    """Move the most relevant chunks to the start and end of the context
    window — mitigates the U-shaped attention curve documented in
    "Lost in the Middle" (Liu et al., 2023, arXiv:2307.03172)."""
    if not settings.long_context_reorder or len(docs) < 3:
        return docs
    return list(_reorder().transform_documents(docs))


# ---------------------------------------------------------------- Public ----
def retrieve(query: str, k: int | None = None) -> list[Document]:
    """End-to-end retrieval: candidates → rerank → reorder → top-k."""
    k_top = k or settings.top_k
    top_n = max(settings.retriever_top_n, k_top)

    candidates = _stage1_candidates(query, top_n=top_n)
    reranked = _rerank(query, candidates, k_top=k_top)
    reordered = _apply_long_context_reorder(reranked)
    return reordered
