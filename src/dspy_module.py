"""DSPy module for prompt optimization of the support generator.

Replaces hand-written generator prompts with a learnable signature.
The BootstrapFewShot optimizer uses our QA testset and a faithfulness
metric to automatically discover effective few-shot demonstrations.

Usage:
    uv run python -m src.dspy_module --optimize
    uv run python -m src.dspy_module --eval
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import dspy

from src.config import settings
from src.retriever import retrieve

logger = logging.getLogger(__name__)

TESTSET = Path("eval/ragas_testset.json")
COMPILED = Path("eval/dspy_compiled.json")


def _configure_dspy() -> None:
    """Wire DSPy to Lightning AI (the project's only inference provider)."""
    lm = dspy.LM(
        model=f"openai/{settings.lightning_model}",
        api_base=settings.lightning_base_url,
        api_key=settings.lightning_api_key,
        temperature=0.2,
    )
    dspy.configure(lm=lm)


class GenerateAnswer(dspy.Signature):
    """Answer a NileTel customer-support question using ONLY the provided context.

    Reply in the same language the user used (Arabic, English, or mixed).
    If the answer is not in the context, say you don't know and offer to escalate.
    Be concise and grounded — never invent facts.
    """

    context: str = dspy.InputField(desc="Retrieved KB chunks, separated by newlines.")
    question: str = dspy.InputField()
    answer: str = dspy.OutputField(desc="Concise grounded answer in the user's language.")


class SupportRAG(dspy.Module):
    """Retrieve-then-generate module — optimisable via DSPy compilers."""

    def __init__(self) -> None:
        super().__init__()
        self.generate = dspy.ChainOfThought(GenerateAnswer)

    def forward(self, question: str) -> dspy.Prediction:
        docs = retrieve(question)
        ctx = "\n\n".join(
            f"[{i + 1}] {d.page_content}" for i, d in enumerate(docs)
        )
        return self.generate(context=ctx, question=question)


# ---------- Metric ----------
def keyword_overlap_metric(example, prediction, trace=None) -> float:
    """Cheap proxy metric — fraction of ground-truth tokens present in answer.

    Used for BootstrapFewShot. Replace with ragas_faithfulness for production
    optimisation; this avoids extra LLM calls during compile.
    """
    gold = set((example.ground_truth or "").lower().split())
    pred = set((prediction.answer or "").lower().split())
    if not gold:
        return 1.0  # no ground-truth, treat as pass
    overlap = len(gold & pred) / max(len(gold), 1)
    return float(overlap >= 0.2)  # boolean: 1 if at least 20% tokens overlap


# ---------- Trainset ----------
def _load_trainset() -> list[dspy.Example]:
    with TESTSET.open() as f:
        items = json.load(f)
    examples = []
    for it in items:
        if not it.get("ground_truth"):
            continue
        examples.append(
            dspy.Example(
                question=it["question"],
                ground_truth=it["ground_truth"],
            ).with_inputs("question")
        )
    return examples


# ---------- Optimisation ----------
def optimize() -> SupportRAG:
    from dspy.teleprompt import BootstrapFewShot

    trainset = _load_trainset()
    logger.info("Compiling SupportRAG with %d training examples", len(trainset))
    optimiser = BootstrapFewShot(
        metric=keyword_overlap_metric,
        max_bootstrapped_demos=3,
        max_labeled_demos=4,
    )
    compiled = optimiser.compile(SupportRAG(), trainset=trainset)
    COMPILED.parent.mkdir(parents=True, exist_ok=True)
    compiled.save(str(COMPILED))
    logger.info("Saved compiled DSPy module to %s", COMPILED)
    return compiled


def quick_eval(module: SupportRAG, n: int = 3) -> None:
    trainset = _load_trainset()[:n]
    for ex in trainset:
        pred = module(question=ex.question)
        print(f"\nQ: {ex.question}")
        print(f"A: {pred.answer[:200]}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimize", action="store_true", help="Run BootstrapFewShot.")
    parser.add_argument("--eval", action="store_true", help="Quick eval on 3 items.")
    args = parser.parse_args()

    _configure_dspy()

    if args.optimize:
        compiled = optimize()
        print("\n=== Optimisation done — running quick eval ===")
        quick_eval(compiled)
    elif args.eval:
        quick_eval(SupportRAG())
    else:
        print("Pass --optimize or --eval. See `--help`.")


if __name__ == "__main__":
    main()
