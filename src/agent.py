"""Tool-calling ReAct agent (Tier 3 #9).

Wraps LangGraph's prebuilt `create_react_agent` around the three CRM
tools in `src.tools`. The agent is the handler for the `ACTION` route —
queries like "check the balance for 01012345678" go here instead of the
retriever/generator path.

Why a separate node instead of folding tools into the generator?
  * Tools shouldn't run on every INFO query (cost + latency).
  * The router gives us a clean intent signal; ACTION → tools is a
    one-to-one mapping that's easy to reason about and trace.
  * Keeping the tool agent isolated also means we can A/B with the
    flag off and demonstrate the "pure RAG" baseline on the same query.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from src.llm import get_llm
from src.tools import TOOLS

logger = logging.getLogger(__name__)

_AGENT_SYSTEM = (
    "You are NileTel's account-action agent. The user wants to look "
    "something up or trigger an operation on their account. "
    "Available tools:\n"
    "  - get_account_status(msisdn): one-call view of identity, plan, "
    "balance, and open tickets for a phone number\n"
    "  - escalate_to_human(msisdn, reason, priority): file a ticket "
    "(P1 critical / P2 high / P3 normal / P4 low)\n\n"
    "Plan, call tools, and reply briefly in the user's language "
    "(Arabic, English, or mixed). When you use a tool, summarise the "
    "result conversationally — do not dump raw JSON."
)


@lru_cache(maxsize=1)
def _agent():
    """Cached compiled ReAct agent."""
    return create_react_agent(
        model=get_llm(temperature=0.0),
        tools=TOOLS,
        prompt=_AGENT_SYSTEM,
    )


def run_agent(query: str) -> dict:
    """Execute the agent on a single query. Returns:

        {
          "answer":     final assistant text,
          "tool_calls": [{name, args, result}, ...],
        }
    """
    try:
        result = _agent().invoke({"messages": [HumanMessage(content=query)]})
    except Exception as exc:  # noqa: BLE001
        logger.warning("ReAct agent failed: %s", exc)
        return {
            "answer": (
                "يا فندم، حصل خطأ تقني وأنا بحاول أنفذ العملية. "
                "ممكن أرفع تذكرة وأكلمك تاني؟"
            ),
            "tool_calls": [],
        }

    messages = result.get("messages", [])
    # Final assistant message → answer.
    answer = ""
    for m in reversed(messages):
        if getattr(m, "type", "") == "ai" and getattr(m, "content", ""):
            answer = m.content
            break

    # Walk messages to extract tool calls and their results.
    # Each entry gets both:
    #   * result — raw string (legacy, what the LLM saw)
    #   * data   — parsed JSON dict/list when possible (for generative UI)
    import json

    def _try_parse(text: str):
        if not text:
            return None
        try:
            # Tool results are often Python repr → swap single → double quotes
            return json.loads(text)
        except Exception:
            try:
                # LangChain wraps dict tool results in repr() — try ast.literal_eval
                import ast
                v = ast.literal_eval(text)
                if isinstance(v, (dict, list)):
                    return v
            except Exception:
                pass
        return None

    tool_calls: list[dict] = []
    pending: dict[str, dict] = {}
    for m in messages:
        t = getattr(m, "type", "")
        if t == "ai":
            for call in getattr(m, "tool_calls", []) or []:
                pending[call["id"]] = {
                    "name": call["name"],
                    "args": call.get("args", {}),
                }
        elif t == "tool":
            tc_id = getattr(m, "tool_call_id", None)
            if tc_id in pending:
                entry = pending.pop(tc_id)
                raw = getattr(m, "content", "")
                entry["result"] = raw
                entry["data"] = _try_parse(raw)
                tool_calls.append(entry)
    return {"answer": answer, "tool_calls": tool_calls}
