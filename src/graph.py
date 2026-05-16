"""LangGraph StateGraph wiring.

Topology (every Tier 2/3 node is gated by a config flag — when off, the
node is a pass-through so the trace stays identical):

    router → pii_redact ──┬─ INFO/COMPLAINT → retriever → crag_evaluator
                          │                                ├─ correct/ambig → generator
                          │                                └─ incorrect    → web_search
                          │                                └─→ verifier (CoVe)
                          │                                └─→ pii_restore → [ticketer?] → END
                          │
                          ├─ ACTION       → action_llm ─┬→ action_tools → action_llm (loop)
                          │                              └→ pii_restore → END
                          ├─ GREETING     → greeter      → pii_restore → END
                          └─ OUT_OF_SCOPE → rejector     → pii_restore → END

The ACTION branch is an outer-graph ReAct loop (action_llm + ToolNode).
This makes every `get_account_status` / `escalate_to_human`
tool call a first-class graph event the AG-UI adapter can stream — so
the Next.js + CopilotKit frontend's generative-UI cards render natively.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.config import settings
from src.nodes import (
    action_llm_node,
    contact_gate_node,
    crag_evaluator_node,
    generator_node,
    greeter_node,
    pii_redact_node,
    pii_restore_node,
    rejector_node,
    retriever_node,
    router_node,
    ticketer_node,
    verifier_node,
    web_search_node,
)
from src.state import SupportState
from src.tools import TOOLS


def _route_after_pii_redact(state: SupportState) -> str:
    return state.get("category", "OUT_OF_SCOPE")


def _route_after_crag(state: SupportState) -> str:
    rating = state.get("retrieval_quality", "correct")
    if rating == "incorrect" and settings.crag_enabled:
        return "web_search"
    return "generator"


def _route_after_verifier(state: SupportState) -> str:
    return "contact_gate" if state.get("category") == "COMPLAINT" else "done"


def _route_after_contact_gate(state: SupportState) -> str:
    # Skip the ticketer when we're still waiting for contact info — the
    # graph ends with the prompt-for-contact answer instead.
    return "skip" if state.get("awaiting_contact") else "ticket"


def _route_after_action_llm(state: SupportState) -> str:
    """LangGraph's `tools_condition` returns 'tools' or '__end__' based
    on whether the last AIMessage has tool_calls. We translate
    '__end__' to our own 'done' edge so the answer still flows through
    `pii_restore` before the run ends."""
    decision = tools_condition(state)
    return "tools" if decision == "tools" else "done"


@lru_cache(maxsize=2)
def build_graph(with_checkpointer: bool = False):
    """Compile the LangGraph StateGraph.

    `with_checkpointer=True` attaches an in-memory `MemorySaver`. This is
    required by integrations that call `graph.aget_state(config)` — for
    example CopilotKit's AG-UI adapter, which expects the graph to be
    thread-stateful. The default (stateless) compile is what the legacy
    /query endpoint, the in-process Streamlit fallback, the tracer, and
    the test suite all use.
    """
    graph = StateGraph(SupportState)

    graph.add_node("router", router_node)
    graph.add_node("pii_redact", pii_redact_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("crag_evaluator", crag_evaluator_node)
    graph.add_node("generator", generator_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("action_llm", action_llm_node)
    graph.add_node("action_tools", ToolNode(TOOLS))
    graph.add_node("contact_gate", contact_gate_node)
    graph.add_node("ticketer", ticketer_node)
    graph.add_node("greeter", greeter_node)
    graph.add_node("rejector", rejector_node)
    graph.add_node("pii_restore", pii_restore_node)

    graph.set_entry_point("router")
    graph.add_edge("router", "pii_redact")

    graph.add_conditional_edges(
        "pii_redact",
        _route_after_pii_redact,
        {
            "INFO": "retriever",
            "COMPLAINT": "retriever",
            "GREETING": "greeter",
            "OUT_OF_SCOPE": "rejector",
            "ACTION": "action_llm",
        },
    )

    graph.add_edge("retriever", "crag_evaluator")
    graph.add_conditional_edges(
        "crag_evaluator",
        _route_after_crag,
        {"generator": "generator", "web_search": "web_search"},
    )

    graph.add_edge("generator", "verifier")
    graph.add_edge("web_search", "verifier")

    graph.add_conditional_edges(
        "verifier",
        _route_after_verifier,
        {"contact_gate": "contact_gate", "done": "pii_restore"},
    )
    graph.add_conditional_edges(
        "contact_gate",
        _route_after_contact_gate,
        {"ticket": "ticketer", "skip": "pii_restore"},
    )

    # ACTION branch — the outer-graph tool-call loop.
    graph.add_conditional_edges(
        "action_llm",
        _route_after_action_llm,
        {"tools": "action_tools", "done": "pii_restore"},
    )
    graph.add_edge("action_tools", "action_llm")

    graph.add_edge("ticketer", "pii_restore")
    graph.add_edge("greeter", "pii_restore")
    graph.add_edge("rejector", "pii_restore")
    graph.add_edge("pii_restore", END)

    if with_checkpointer:
        from langgraph.checkpoint.memory import MemorySaver
        return graph.compile(checkpointer=MemorySaver())
    return graph.compile()
