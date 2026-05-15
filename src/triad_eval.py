"""TruLens-style RAG Triad evaluator (Tier 3 #12).

Computes three claim-level feedback functions over the same dataset
RAGAS uses, so we have two independent eval lenses.

The triad (Reka & Bukharin, "The RAG Triad", TruLens 2024):

  1. **Context Relevance** — for each (query, chunk), how relevant is
     the chunk?  Computed per-chunk; reported as the mean.
  2. **Groundedness** — for each sentence in the answer, is it supported
     by at least one retrieved chunk?  Reported as the mean over
     sentences.
  3. **Answer Relevance** — given the query and the final answer alone,
     does the answer actually address the query?

All three are computed with the configured LLM as a calibrated judge
(temperature=0) using small structured-output prompts. This is the
mechanism TruLens uses under the hood (`OpenAI.relevance_with_cot_reasons`
et al.); we keep it framework-free so the dependency surface stays flat.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.config import settings
from src.llm import get_llm
from src.retriever import retrieve

logger = logging.getLogger(__name__)


# ----------------------------------------------------- LLM judges ----


class Score(BaseModel):
    score: float = Field(ge=0.0, le=1.0, description="0=bad, 1=good.")
    reason: str = Field(description="One sentence justification.")


_CTX_REL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You rate how RELEVANT a retrieved chunk is to a user query "
            "in a customer-support setting. 1.0 = chunk directly answers "
            "the query, 0.5 = topically related but not answering, "
            "0.0 = off-topic. Output exactly the Score object.",
        ),
        ("human", "Query: {query}\n\nChunk:\n{chunk}\n\nRate:"),
    ]
)

_GROUNDED_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You judge whether a SENTENCE from a support answer is "
            "supported by at least one of the provided context chunks. "
            "1.0 = directly supported (paraphrase counts), 0.5 = partial / "
            "weak support, 0.0 = unsupported or contradicted.",
        ),
        (
            "human",
            "Context:\n{context}\n\nSentence: {sentence}\n\nRate:",
        ),
    ]
)

_ANS_REL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You judge whether an answer actually addresses the user's "
            "query. 1.0 = answers it directly, 0.5 = related but evasive, "
            "0.0 = off-topic or non-answer.",
        ),
        ("human", "Query: {query}\n\nAnswer: {answer}\n\nRate:"),
    ]
)


_SENT_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n+")


def _split_sentences(text: str) -> list[str]:
    out = [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]
    # ALCE citation markers like [1] are noise for the judge — strip them.
    return [re.sub(r"\s*\[\d+\]", "", s).strip() for s in out if len(s) > 4]


def _safe_score(chain, params: dict[str, Any]) -> float:
    """Run a judge chain; return 0.5 on any failure (neutral signal)."""
    try:
        result: Score = chain.invoke(params)
        return float(max(0.0, min(1.0, result.score)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("triad judge failed: %s", exc)
        return 0.5


def _judges():
    llm = get_llm(temperature=0.0).with_structured_output(Score)
    return (
        _CTX_REL_PROMPT | llm,
        _GROUNDED_PROMPT | llm,
        _ANS_REL_PROMPT | llm,
    )


def evaluate_triad(
    query: str, answer: str, chunks: list[str]
) -> dict[str, Any]:
    """Compute the three triad scores for a single (query, answer, chunks)
    record. Returns per-metric mean + the underlying per-item samples."""
    ctx_rel_chain, grounded_chain, ans_rel_chain = _judges()

    # 1. Context relevance: one score per retrieved chunk.
    ctx_scores = [
        _safe_score(ctx_rel_chain, {"query": query, "chunk": c})
        for c in chunks
    ]
    ctx_relevance = (
        sum(ctx_scores) / len(ctx_scores) if ctx_scores else 0.0
    )

    # 2. Groundedness: one score per sentence in the answer.
    context_blob = "\n\n".join(
        f"[{i + 1}] {c}" for i, c in enumerate(chunks)
    )
    sentences = _split_sentences(answer)
    sent_scores = [
        _safe_score(
            grounded_chain, {"context": context_blob, "sentence": s}
        )
        for s in sentences
    ]
    groundedness = (
        sum(sent_scores) / len(sent_scores) if sent_scores else 0.0
    )

    # 3. Answer relevance — single score.
    answer_relevance = _safe_score(
        ans_rel_chain, {"query": query, "answer": answer}
    )

    return {
        "context_relevance": ctx_relevance,
        "groundedness": groundedness,
        "answer_relevance": answer_relevance,
        "samples": {
            "ctx_scores": ctx_scores,
            "sentence_scores": sent_scores,
            "n_sentences": len(sentences),
            "n_chunks": len(chunks),
        },
    }


# ------------------------------------------------------ CLI driver ----


def _load_testset(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run(
    testset_path: Path,
    out_path: Path,
    throttle_sec: float = 0.5,
    limit: int | None = None,
) -> dict[str, Any]:
    cases = _load_testset(testset_path)
    if limit:
        cases = cases[:limit]

    print(f"Evaluating {len(cases)} cases (throttle={throttle_sec}s)...")
    per_case: list[dict[str, Any]] = []
    means = {"context_relevance": 0.0, "groundedness": 0.0, "answer_relevance": 0.0}

    from src.graph import build_graph

    graph = build_graph()
    for i, case in enumerate(cases, start=1):
        query = case["question"]
        # Use the graph end-to-end so the eval reflects the real pipeline.
        result = graph.invoke({"query": query, "session_id": f"triad-{i}"})
        answer = result.get("answer", "")
        chunks = [
            d.page_content for d in (result.get("context_docs") or [])
        ]

        triad = evaluate_triad(query, answer, chunks)
        per_case.append(
            {
                "question": query,
                "answer": answer[:400],
                "scores": {k: triad[k] for k in means},
                "samples": triad["samples"],
            }
        )
        for k in means:
            means[k] += triad[k]
        print(
            f"  [{i:>3}/{len(cases)}]  ctx={triad['context_relevance']:.2f} "
            f"gnd={triad['groundedness']:.2f} "
            f"ans={triad['answer_relevance']:.2f}"
        )
        if throttle_sec:
            time.sleep(throttle_sec)

    means = {k: v / max(len(per_case), 1) for k, v in means.items()}
    report = {
        "n_cases": len(per_case),
        "means": means,
        "per_case": per_case,
        "config": {
            "embedding_model": settings.embedding_model,
            "retrieval_mode": settings.retrieval_mode,
            "reranker": settings.reranker_model if settings.reranker_enabled else None,
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_path}")
    print(
        f"  context_relevance: {means['context_relevance']:.3f}\n"
        f"  groundedness     : {means['groundedness']:.3f}\n"
        f"  answer_relevance : {means['answer_relevance']:.3f}"
    )
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="TruLens-style RAG Triad eval.")
    ap.add_argument("--testset", default="eval/ragas_testset.json")
    ap.add_argument("--out", default="eval/triad_report.json")
    ap.add_argument("--throttle", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    run(
        testset_path=Path(args.testset),
        out_path=Path(args.out),
        throttle_sec=args.throttle,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
