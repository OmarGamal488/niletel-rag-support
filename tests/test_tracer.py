"""Tracer tests — exercise run_traced and the per-node summarisers."""

from __future__ import annotations

from langchain_core.documents import Document

from src.tracer import _summary_for, run_traced, trace_for_cache_hit


class _FakeGraph:
    """Minimal stand-in for a compiled LangGraph — yields scripted updates."""

    def __init__(self, updates: list[dict]):
        self._updates = updates

    def stream(self, initial: dict, stream_mode: str = "updates"):
        for u in self._updates:
            yield u


# ----------------------------- run_traced -----------------------------


def test_run_traced_captures_events_in_order():
    graph = _FakeGraph(
        [
            {"router": {"category": "INFO", "confidence": 0.95}},
            {"retriever": {"context_docs": [Document(page_content="x", metadata={"source": "a.md"})]}},
            {"generator": {"answer": "hello [1]", "citations": [1]}},
        ]
    )
    state, trace = run_traced(graph, {"query": "q"})

    # Final state is the merge of all deltas.
    assert state["category"] == "INFO"
    assert state["answer"] == "hello [1]"
    assert state["citations"] == [1]
    assert "_total_elapsed_ms" in state

    # Trace is one event per node, ordered.
    assert [ev.node for ev in trace] == ["router", "retriever", "generator"]
    assert [ev.step for ev in trace] == [1, 2, 3]

    # Summaries are populated and non-empty for every node.
    for ev in trace:
        assert ev.summary
        assert ev.elapsed_ms >= 0


def test_run_traced_handles_empty_delta():
    """Pass-through nodes (CoVe-off, CRAG-off) often emit empty deltas;
    the tracer must record them with the correct keys=[] state."""
    graph = _FakeGraph(
        [
            {"router": {"category": "GREETING"}},
            {"verifier": {}},  # CoVe disabled → no-op
        ]
    )
    state, trace = run_traced(graph, {"query": "hi"})

    assert state["category"] == "GREETING"
    nodes = [ev.node for ev in trace]
    assert "verifier" in nodes
    verifier_ev = next(ev for ev in trace if ev.node == "verifier")
    assert verifier_ev.delta_keys == []


def test_trace_for_cache_hit_is_single_event():
    events = trace_for_cache_hit(elapsed_ms=42.5)
    assert len(events) == 1
    assert events[0].node == "semantic_cache"
    assert events[0].elapsed_ms == 42.5
    assert "HIT" in events[0].summary


# ----------------------------- summarisers -----------------------------


def test_summary_router_includes_confidence():
    s = _summary_for("router", {"category": "INFO", "confidence": 0.92})
    assert "INFO" in s and "0.92" in s


def test_summary_pii_redact_reports_kinds():
    s = _summary_for("pii_redact", {"pii_kinds": ["EG_PHONE", "EMAIL"]})
    assert "EG_PHONE" in s and "EMAIL" in s


def test_summary_pii_redact_reports_no_pii():
    s = _summary_for("pii_redact", {})
    assert "no pii" in s.lower()


def test_summary_retriever_includes_chunk_count_and_top_source():
    docs = [
        Document(
            page_content="a",
            metadata={"source": "x.md", "rerank_score": 0.92},
        ),
        Document(
            page_content="b",
            metadata={"source": "y.md", "rerank_score": 0.50},
        ),
    ]
    s = _summary_for("retriever", {"context_docs": docs})
    assert "2 chunks" in s
    assert "x.md" in s
    assert "0.92" in s


def test_summary_generator_reports_citations():
    s = _summary_for("generator", {"answer": "abc [1][3]", "citations": [1, 3]})
    assert "10 chars" in s
    assert "[1, 3]" in s


def test_summary_crag_evaluator():
    assert "ambiguous" in _summary_for("crag_evaluator", {"retrieval_quality": "ambiguous"})


def test_summary_action_agent_reports_tool_calls():
    s = _summary_for(
        "action_agent",
        {"tool_calls": [{"name": "get_balance"}, {"name": "list_open_tickets"}]},
    )
    assert "get_balance" in s
    assert "list_open_tickets" in s


def test_summary_unknown_node_falls_back_to_keys():
    s = _summary_for("mystery", {"foo": 1, "bar": 2})
    assert "foo" in s and "bar" in s
