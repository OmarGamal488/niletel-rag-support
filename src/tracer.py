"""Per-node execution tracer for the LangGraph pipeline.

`graph.stream(initial)` yields one dict per node firing — `{node: delta}`.
We walk those events, time each one, and produce a list of TraceEvent
objects the UI can render as a timeline. The summariser knows about
every node in the graph so the trace is human-readable, not a JSON
dump of state deltas.

This gives the user a "what happened under the hood" view that's much
more digestible than a full LangSmith trace, and is always available
locally (no external service / network round trip).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from langchain_core.documents import Document


@dataclass
class TraceEvent:
    step: int
    node: str
    elapsed_ms: float
    delta_keys: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------- Summarisers ----


def _docs_summary(docs: list[Document]) -> str:
    if not docs:
        return "0 chunks"
    sources = sorted({d.metadata.get("source", "?") for d in docs})
    n = len(docs)
    top_score = max(
        (d.metadata.get("rerank_score") or 0.0 for d in docs), default=0.0
    )
    src_preview = ", ".join(sources[:3])
    more = f" +{len(sources) - 3} more" if len(sources) > 3 else ""
    if top_score:
        return f"{n} chunks  ·  top src: {src_preview}{more}  ·  rerank max={top_score:.2f}"
    return f"{n} chunks  ·  {src_preview}{more}"


def _summary_for(node: str, delta: dict[str, Any]) -> str:
    """One-line, demo-friendly summary for each node's delta."""
    if node == "router":
        cat = delta.get("category", "?")
        conf = delta.get("confidence")
        return (
            f"category={cat}"
            + (f"  ·  confidence={conf:.2f}" if conf is not None else "")
        )

    if node == "pii_redact":
        kinds = delta.get("pii_kinds") or []
        if not kinds:
            return "no PII detected"
        return f"redacted {kinds}"

    if node == "retriever":
        return _docs_summary(delta.get("context_docs") or [])

    if node == "crag_evaluator":
        return f"rating={delta.get('retrieval_quality', '?')}"

    if node == "generator":
        ans = delta.get("answer", "") or ""
        cites = delta.get("citations") or []
        return f"answer ({len(ans)} chars)" + (
            f"  ·  cites {cites}" if cites else ""
        )

    if node == "web_search":
        if delta.get("used_web_search"):
            return _docs_summary(delta.get("context_docs") or [])
        return "no fallback (no Tavily key)"

    if node == "verifier":
        if "answer" in delta:
            return f"revised → {len(delta['answer'])} chars"
        return "skipped (CoVe off or no context)"

    if node == "action_agent":
        calls = delta.get("tool_calls") or []
        names = [tc["name"] for tc in calls]
        if names:
            return f"called {names}"
        return "no tool calls"

    if node == "ticketer":
        tid = delta.get("ticket_id")
        return f"ticket {tid}" if tid else "no ticket"

    if node == "greeter":
        return "direct greeting reply"

    if node == "rejector":
        return "polite out-of-scope rejection"

    if node == "pii_restore":
        if "answer" in delta:
            return "restored PII placeholders in answer"
        return "no placeholders to restore"

    # Unknown node — show which keys changed.
    return f"keys updated: {sorted(delta.keys())}"


# --------------------------------------------------------- Runner ----


def run_traced(
    graph,
    initial: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[TraceEvent]]:
    """Drive `graph.stream` and accumulate both the final state and a
    timeline of node-level events.

    Args:
        graph: compiled LangGraph
        initial: starting state dict
        config: optional LangGraph runnable config — used here to pass
                Langfuse callbacks + session metadata down to every node.

    Returns:
        final_state — the accumulated state dict (same shape as
                      `graph.invoke(initial)` would return).
        trace       — ordered list of TraceEvent.
    """
    trace: list[TraceEvent] = []
    accumulated: dict[str, Any] = {}
    overall_start = time.perf_counter()
    last_t = overall_start
    step_idx = 0

    stream_kwargs: dict[str, Any] = {"stream_mode": "updates"}
    if config:
        stream_kwargs["config"] = config

    for step in graph.stream(initial, **stream_kwargs):
        # `step` is {node_name: delta} (or possibly empty for parallel forks)
        for node_name, delta in step.items():
            if delta is None:
                continue
            now = time.perf_counter()
            elapsed_ms = round((now - last_t) * 1000.0, 1)
            last_t = now
            step_idx += 1
            trace.append(
                TraceEvent(
                    step=step_idx,
                    node=node_name,
                    elapsed_ms=elapsed_ms,
                    delta_keys=sorted(delta.keys()),
                    summary=_summary_for(node_name, delta),
                )
            )
            accumulated.update(delta)

    accumulated["_total_elapsed_ms"] = round(
        (time.perf_counter() - overall_start) * 1000.0, 1
    )
    return accumulated, trace


def trace_for_cache_hit(elapsed_ms: float) -> list[TraceEvent]:
    """Synthetic single-event trace when the semantic cache served the
    query without invoking the graph."""
    return [
        TraceEvent(
            step=1,
            node="semantic_cache",
            elapsed_ms=round(elapsed_ms, 1),
            delta_keys=[],
            summary="cache HIT — graph skipped",
        )
    ]
