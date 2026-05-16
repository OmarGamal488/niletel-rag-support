"""RAGAS-based evaluation for the support pipeline.

Runs the full LangGraph against a small QA testset, then scores each
INFO/COMPLAINT response with RAGAS metrics:
  - faithfulness        (answer grounded in retrieved context)
  - answer_relevancy    (answer actually addresses the question)
  - context_precision   (retrieved context relevant to ground truth)
  - context_recall      (retrieved context covers the ground truth)

Usage:
    uv run python -m src.evaluator
    uv run python -m src.evaluator --quick   # 3 items only, faster

Outputs: eval/ragas_report.json with per-item and aggregate scores.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import settings
from src.graph import build_graph
from src.llm import get_llm

logger = logging.getLogger(__name__)

DEFAULT_TESTSET = Path("eval/ragas_testset.json")
DEFAULT_REPORT = Path("eval/ragas_report.json")
RAG_CATEGORIES = {"INFO", "COMPLAINT"}


def _load_testset(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _run_graph_on_testset(
    items: list[dict[str, Any]], throttle_s: float = 1.5
) -> list[dict[str, Any]]:
    graph = build_graph()
    rows = []
    for i, item in enumerate(items, 1):
        logger.info("[%d/%d] %s", i, len(items), item["question"][:60])
        if i > 1:
            time.sleep(throttle_s)

        # Exponential-backoff retry — Lightning's free tier rate-limits
        # sporadically and one transient 429 used to kill the whole run.
        result: dict[str, Any] | None = None
        delay = 4.0
        for attempt in range(4):
            try:
                result = graph.invoke({"query": item["question"]})
                break
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                transient = (
                    "rate" in msg
                    or "429" in msg
                    or "timeout" in msg
                    or "503" in msg
                    or "overload" in msg
                )
                if attempt == 3 or not transient:
                    logger.warning(
                        "[%d/%d] giving up after %d attempts (%s) — skipping",
                        i, len(items), attempt + 1, exc.__class__.__name__,
                    )
                    result = {"_error": str(exc)[:200]}
                    break
                logger.warning(
                    "[%d/%d] %s — sleeping %.0fs then retrying",
                    i, len(items), exc.__class__.__name__, delay,
                )
                time.sleep(delay)
                delay *= 2  # 4 → 8 → 16 → 32 s

        rows.append(
            {
                "question": item["question"],
                "category": result.get("category"),
                "expected_category": item.get("expected_category"),
                "answer": result.get("answer", ""),
                "contexts": [
                    d.page_content for d in result.get("context_docs", []) or []
                ],
                "retrieved_sources": [
                    d.metadata.get("source", "?")
                    for d in result.get("context_docs", []) or []
                ],
                "expected_source": item.get("expected_source"),
                "ground_truth": item.get("ground_truth", ""),
                "ticket_id": result.get("ticket_id"),
                "error": result.get("_error"),
            }
        )
    return rows


def _routing_accuracy(rows: list[dict[str, Any]]) -> dict[str, float]:
    total = len(rows)
    correct = sum(1 for r in rows if r["category"] == r.get("expected_category"))
    return {"routing_accuracy": correct / total if total else 0.0, "n": total}


def _retrieval_hit_rate(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Of items with an expected_source, fraction where it appears in top-K."""
    rated = [r for r in rows if r.get("expected_source")]
    if not rated:
        return {"retrieval_hit_rate": 0.0, "n": 0}
    hits = sum(
        1 for r in rated if r["expected_source"] in r["retrieved_sources"]
    )
    return {"retrieval_hit_rate": hits / len(rated), "n": len(rated)}


def _ragas_evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Run RAGAS metrics on the rows that did real RAG (INFO + COMPLAINT)."""
    rag_rows = [r for r in rows if r["category"] in RAG_CATEGORIES and r["contexts"]]
    if not rag_rows:
        return {"note": "No RAG rows to evaluate (all were greetings or rejected)."}

    try:
        from datasets import Dataset
        from langchain_huggingface import HuggingFaceEmbeddings
        from ragas import evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError as exc:
        return {"error": f"RAGAS dependencies missing: {exc}"}

    ds = Dataset.from_list(
        [
            {
                "question": r["question"],
                "answer": r["answer"],
                "contexts": r["contexts"],
                "ground_truth": r["ground_truth"] or r["answer"],
            }
            for r in rag_rows
        ]
    )

    judge_llm = LangchainLLMWrapper(get_llm(temperature=0.0))
    embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name=settings.embedding_model)
    )

    metrics = [faithfulness, answer_relevancy]
    has_ground_truth = any(r["ground_truth"] for r in rag_rows)
    if has_ground_truth:
        metrics.extend([context_precision, context_recall])

    result = evaluate(
        dataset=ds,
        metrics=metrics,
        llm=judge_llm,
        embeddings=embeddings,
        raise_exceptions=False,
    )
    return {
        "n_evaluated": len(rag_rows),
        "scores": {k: float(v) for k, v in result._repr_dict.items()}
        if hasattr(result, "_repr_dict")
        else dict(result),
    }


def run_evaluation(
    testset_path: Path = DEFAULT_TESTSET,
    quick: bool = False,
    throttle_s: float = 1.5,
) -> dict:
    items = _load_testset(testset_path)
    if quick:
        items = items[:3]
    logger.info("Running graph on %d items...", len(items))
    rows = _run_graph_on_testset(items, throttle_s=throttle_s)

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "provider": settings.llm_provider,
        "model": settings.lightning_model,
        "n_items": len(rows),
        "routing": _routing_accuracy(rows),
        "retrieval": _retrieval_hit_rate(rows),
        "ragas": _ragas_evaluate(rows),
        "items": rows,
    }
    return report


def _enable_eval_mode() -> None:
    """Flip on the validation flags (triad_eval + CoVe + CRAG) for one run.

    Live demo runs leave these off to keep COMPLAINT latency at ~5–10 s;
    RAGAS evaluation runs flip them on for the highest quality numbers
    in the report. Direct mutation works because the relevant nodes read
    `settings.X` at call time rather than caching the values at import.
    """
    from src.config import settings

    settings.triad_eval_enabled = True
    settings.chain_of_verification = True
    settings.crag_enabled = True
    logger.info(
        "EVAL_MODE: triad_eval + chain_of_verification + crag → ON for this run"
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Run only 3 items.")
    parser.add_argument(
        "--testset", type=Path, default=DEFAULT_TESTSET, help="Path to QA JSON."
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_REPORT, help="Where to save report."
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=1.5,
        help="Seconds to wait between items (avoids API rate limits).",
    )
    parser.add_argument(
        "--eval-mode",
        action="store_true",
        help=(
            "Enable triad_eval + chain_of_verification + CRAG for this run "
            "only (best RAGAS numbers but slower)."
        ),
    )
    args = parser.parse_args()

    # Honour either the CLI flag or the EVAL_MODE env var so the eval can
    # be run in two-mode style without code changes.
    if args.eval_mode or os.environ.get("EVAL_MODE", "").lower() in {"1", "true", "yes"}:
        _enable_eval_mode()

    report = run_evaluation(
        testset_path=args.testset, quick=args.quick, throttle_s=args.throttle
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print("\n=== Evaluation Summary ===")
    print(f"Items:               {report['n_items']}")
    print(f"Routing accuracy:    {report['routing']['routing_accuracy']:.0%}")
    print(
        f"Retrieval hit rate:  {report['retrieval']['retrieval_hit_rate']:.0%} "
        f"(over {report['retrieval']['n']} items with expected source)"
    )
    if "scores" in report["ragas"]:
        for k, v in report["ragas"]["scores"].items():
            print(f"  RAGAS {k:20s} {v:.3f}")
    elif "error" in report["ragas"]:
        print(f"  RAGAS error: {report['ragas']['error']}")
    elif "note" in report["ragas"]:
        print(f"  {report['ragas']['note']}")
    print(f"\nReport written to {args.out}")


if __name__ == "__main__":
    main()
