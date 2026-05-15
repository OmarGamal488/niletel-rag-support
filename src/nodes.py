"""Pure-function nodes used by the LangGraph StateGraph.

Tier 2 upgrades wired here:
  * ALCE-style citations         (Gao et al., 2023, arXiv:2305.14627)
  * Chain-of-Verification (CoVe) (Dhuliawala et al., 2023, arXiv:2309.11495)

Both toggleable via `settings.citations_enabled` and
`settings.chain_of_verification`.
"""

from __future__ import annotations

import logging
import re

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from src.config import settings
from src.llm import get_llm
from src.pii import found_kinds, redact, restore
from src.retriever import retrieve
from src.router import classify
from src.state import SupportState
from src.ticketer import create_ticket


# --------------------- AG-UI / CopilotKit emission control ---------------
def _silent_config(config):
    """Return a copy of `config` that tells the CopilotKit AG-UI adapter
    NOT to surface this node's intermediate LLM output as visible chat
    text. Falls back to the raw config if copilotkit isn't installed,
    so the legacy /query path keeps working untouched.
    """
    try:
        from copilotkit.langgraph import copilotkit_customize_config

        return copilotkit_customize_config(
            config or {},
            emit_messages=False,
            emit_tool_calls=False,
        )
    except Exception:
        return config

logger = logging.getLogger(__name__)

# ----------------------------------------------------------- Prompts ----

_ANSWER_SYSTEM_BASE = (
    "You are a NileTel customer support assistant. Answer ONLY using the "
    "provided context. If the answer is not in the context, say you don't "
    "know and offer to escalate. Reply in the same language the user used "
    "(Arabic, English, or mixed). Be concise and helpful. Use prior turns "
    "to resolve references like 'the second one' or 'and after that?'."
)

_CITATION_INSTRUCTIONS = (
    " Every factual claim in your answer MUST end with the chunk number(s) "
    "in square brackets, e.g. '...the data cap is 100 GB [2][4]'. If you "
    "synthesise across multiple chunks, list them. Do NOT invent chunk "
    "numbers; cite only from the provided context."
)


def _answer_system_prompt() -> str:
    if settings.citations_enabled:
        return _ANSWER_SYSTEM_BASE + _CITATION_INSTRUCTIONS
    return _ANSWER_SYSTEM_BASE


def _answer_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", _answer_system_prompt()),
            MessagesPlaceholder("history", optional=True),
            (
                "human",
                "Context:\n{context}\n\nUser question: {query}\n\nAnswer:",
            ),
        ]
    )


GREETING_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are NileTel's friendly support assistant. Reply briefly to greetings "
            "or thanks. Mirror the user's language (Arabic, English, or mixed).",
        ),
        MessagesPlaceholder("history", optional=True),
        ("human", "{query}"),
    ]
)

REJECT_MESSAGE = (
    "يا فندم، أنا مساعد NileTel وبقدر أساعدك بس في حاجات تخص خدمات NileTel "
    "(الإنترنت، الفواتير، الباقات، إلخ). ممكن تسألني سؤال يخص الخدمة؟"
)


def _format_docs(docs: list[Document]) -> str:
    return "\n\n".join(
        f"[{i + 1}] (source: {d.metadata.get('source', 'unknown')})\n{d.page_content}"
        for i, d in enumerate(docs)
    )


def _history_messages(state: SupportState) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for turn in state.get("history") or []:
        role = turn.get("role")
        content = turn.get("content") or ""
        if not content:
            continue
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
    return out


_CITATION_RE = re.compile(r"\[(\d+)\]")


def _extract_citations(text: str, max_idx: int) -> list[int]:
    """Parse `[N]` markers out of an answer; drop indices that exceed the
    available chunk count (a sign the model hallucinated a citation)."""
    if not text:
        return []
    found = {int(m) for m in _CITATION_RE.findall(text)}
    return sorted(i for i in found if 1 <= i <= max_idx)


# ------------------------------------------------------------- Nodes ----


def _extract_user_query(state: SupportState) -> str:
    """Return the user's text from either:
      * `state["query"]` — legacy /query endpoint (Streamlit)
      * the last 'user' / 'human' message in `state["messages"]` — set by
        CopilotKit's AG-UI adapter.
    Keeps the rest of the graph unchanged (everything else reads `query`).
    """
    q = state.get("query")
    if q:
        return q
    msgs = state.get("messages") or []
    for m in reversed(msgs):
        # Handles both dict shape and LangChain message objects.
        content = None
        role = None
        if isinstance(m, dict):
            role = m.get("role") or m.get("type")
            content = m.get("content")
        else:
            role = getattr(m, "type", None) or getattr(m, "role", None)
            content = getattr(m, "content", None)
        if role in {"user", "human"} and content:
            return content if isinstance(content, str) else str(content)
    return ""


def router_node(state: SupportState, config=None) -> SupportState:
    query = _extract_user_query(state)
    # `classify` issues a `.with_structured_output(...)` call; without
    # suppression CopilotKit would stream that JSON as visible chat text.
    decision = classify(query, config=_silent_config(config))
    # Populate `query` so every downstream node can keep reading state["query"].
    return {
        "query": query,
        "category": decision.category,
        "confidence": decision.confidence,
    }


def pii_redact_node(state: SupportState) -> SupportState:
    """Strip PII from the query before any downstream node sees it.
    Preserves the original in `query_original` so the ticketer can still
    log real numbers for the support agent."""
    if not settings.pii_redaction_enabled:
        return {}
    query = state.get("query", "")
    redacted, mapping = redact(query)
    update: SupportState = {"query_original": query}
    if mapping:
        update.update(
            {
                "query": redacted,
                "pii_map": mapping,
                "pii_kinds": found_kinds(mapping),
            }
        )
    return update


def pii_restore_node(state: SupportState) -> SupportState:
    """Restore any redacted PII inside the final answer."""
    if not settings.pii_redaction_enabled:
        return {}
    mapping = state.get("pii_map") or {}
    if not mapping:
        return {}
    answer = state.get("answer", "")
    return {"answer": restore(answer, mapping)}


def retriever_node(state: SupportState) -> SupportState:
    docs = retrieve(state["query"])
    return {"context_docs": docs}


def action_agent_node(state: SupportState) -> SupportState:
    """Legacy entry point retained for backward compatibility (kept off
    the new graph, but still callable from tests / scripts).

    The graph now uses the `action_llm_node` + `action_tools` (ToolNode)
    pair so each tool call is a first-class outer-graph event visible to
    AG-UI and the trace panel. This older function still routes the
    query through `src.agent.run_agent` (nested ReAct) so it remains a
    valid one-shot synchronous fallback when wired manually.
    """
    if not settings.tool_agent_enabled:
        return {
            "answer": (
                "يا فندم، الـ tool agent متعطل دلوقتي. ممكن أرفع تذكرة لمختص؟"
            ),
            "context_docs": [],
        }
    from src.agent import run_agent

    raw_query = state.get("query_original") or state.get("query", "")
    result = run_agent(raw_query)
    return {
        "answer": result["answer"],
        "context_docs": [],
        "tool_calls": result["tool_calls"],
    }


# ---------------- Outer-graph action loop (Path A / AG-UI fix) -----------

_ACTION_SYSTEM_PROMPT = (
    "You are NileTel's account-action agent. The user wants to look "
    "something up or trigger an operation on their account.\n"
    "Available tools:\n"
    "  - get_balance(msisdn): credit + data balance for a phone number\n"
    "  - list_open_tickets(account_id): open / escalated tickets\n"
    "  - escalate_to_human(account_id, reason, priority): file a ticket\n\n"
    "Plan, call tools as needed, then reply briefly in the user's "
    "language (Arabic, English, or mixed). When you use a tool, "
    "summarise the result conversationally — do not dump raw JSON."
)


def _build_action_messages(state: SupportState) -> list:
    """Assemble the running [system + user + tool] messages list for the
    action LLM call. We always reuse what's already in state["messages"]
    if it exists (the AG-UI adapter populates it); otherwise we seed
    from state["query"] for legacy /query callers."""
    from langchain_core.messages import HumanMessage, SystemMessage

    existing = list(state.get("messages") or [])

    # Inject the system prompt if it's not already at the front.
    if not existing or (
        getattr(existing[0], "type", None) != "system"
        and (existing[0].get("role") if isinstance(existing[0], dict) else None)
        != "system"
    ):
        existing = [SystemMessage(content=_ACTION_SYSTEM_PROMPT), *existing]

    # If there's no human turn yet (legacy /query path), add one.
    has_human = any(
        getattr(m, "type", None) == "human"
        or (isinstance(m, dict) and m.get("role") in {"user", "human"})
        for m in existing
    )
    if not has_human:
        raw = state.get("query_original") or state.get("query") or ""
        if raw:
            existing.append(HumanMessage(content=raw))
    return existing


def action_llm_node(state: SupportState) -> SupportState:
    """One step of the outer-graph ReAct loop.

    Binds the three CRM tools to the LLM and lets it either:
      * call a tool (then `action_tools` runs and we loop back here), or
      * emit a final answer (then we fall through to pii_restore).

    Returns the new AIMessage via the `add_messages` reducer so the
    running message list accumulates across loop iterations.
    """
    if not settings.tool_agent_enabled:
        return {
            "answer": (
                "يا فندم، الـ tool agent متعطل دلوقتي. ممكن أرفع تذكرة لمختص؟"
            ),
            "context_docs": [],
            "messages": [],
        }
    from src.tools import TOOLS

    llm = get_llm(temperature=0.0).bind_tools(TOOLS)
    msgs = _build_action_messages(state)
    response = llm.invoke(msgs)

    update: SupportState = {"messages": [response]}
    # If this turn is the final one (no more tool calls), surface the
    # text into `answer` so downstream nodes (pii_restore) and the
    # legacy /query response shape both pick it up.
    if not getattr(response, "tool_calls", None):
        content = response.content
        update["answer"] = (
            content if isinstance(content, str) else str(content or "")
        )
        # Also extract a structured tool_calls history from the running
        # messages so the legacy /query JSON keeps populating
        # `tool_calls` (cards + observability in the Streamlit app).
        update["tool_calls"] = _extract_tool_history(msgs + [response])
    return update


def _extract_tool_history(messages: list) -> list[dict]:
    """Walk the messages list and pull out a flat history of tool calls
    + their results, in the shape `api/schemas.py:ToolCall` expects."""
    import json

    def _try_parse(text: str):
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            try:
                import ast

                v = ast.literal_eval(text)
                if isinstance(v, (dict, list)):
                    return v
            except Exception:
                return None
        return None

    pending: dict[str, dict] = {}
    out: list[dict] = []
    for m in messages:
        t = getattr(m, "type", None) or (
            m.get("role") if isinstance(m, dict) else None
        )
        if t == "ai":
            for tc in getattr(m, "tool_calls", []) or []:
                pending[tc["id"]] = {
                    "name": tc["name"],
                    "args": tc.get("args") or {},
                }
        elif t == "tool":
            tc_id = getattr(m, "tool_call_id", None) or (
                m.get("tool_call_id") if isinstance(m, dict) else None
            )
            if tc_id in pending:
                entry = pending.pop(tc_id)
                raw = getattr(m, "content", None) or (
                    m.get("content") if isinstance(m, dict) else ""
                )
                if not isinstance(raw, str):
                    raw = str(raw or "")
                entry["result"] = raw
                entry["data"] = _try_parse(raw)
                out.append(entry)
    return out


def generator_node(state: SupportState) -> SupportState:
    docs = state.get("context_docs", [])
    chain = _answer_prompt() | get_llm()
    msg = chain.invoke(
        {
            "context": _format_docs(docs),
            "query": state["query"],
            "history": _history_messages(state),
        }
    )
    answer = msg.content
    update: SupportState = {"answer": answer}
    if settings.citations_enabled:
        update["citations"] = _extract_citations(answer, max_idx=len(docs))
    return update


def greeter_node(state: SupportState) -> SupportState:
    chain = GREETING_PROMPT | get_llm(temperature=0.5)
    msg = chain.invoke(
        {"query": state["query"], "history": _history_messages(state)}
    )
    return {"answer": msg.content, "context_docs": []}


def rejector_node(state: SupportState) -> SupportState:
    return {"answer": REJECT_MESSAGE, "context_docs": []}


def contact_gate_node(state: SupportState) -> SupportState:
    """Decide whether we have enough contact info to file the ticket.

    Reads `state["contact"]` (the API layer hydrates this from session
    memory, parsing the current turn if we were awaiting it). If we
    still don't have at least a phone or email, we replace the draft
    answer with a prompt asking for it and set `awaiting_contact=True`
    so the graph short-circuits past the ticketer.

    The original RAG answer is kept around as `state["draft_answer"]`
    so the API can stitch it into the follow-up reply once contact
    info arrives.
    """
    contact = state.get("contact") or {}
    has_reachable = bool(contact.get("phone") or contact.get("email"))
    if has_reachable:
        return {"awaiting_contact": False}

    draft = state.get("answer") or ""
    prompt = (
        "Before I open a ticket for you, please share your **name** and "
        "either a **phone number** or **email** so our support team can "
        "follow up.\n\n"
        "_Example:_  Ahmed Mohamed, 0101 234 5678, ahmed@example.com"
    )
    # Keep the helpful RAG answer as a preface — but lead with the ask
    # so the user notices it.
    if draft:
        prompt = f"{prompt}\n\n---\n\n{draft}"
    return {"answer": prompt, "awaiting_contact": True}


def ticketer_node(state: SupportState) -> SupportState:
    # Skip ticket creation when the contact gate flagged the turn as
    # awaiting contact info — we'll get here again on the next user
    # message once the contact has been captured.
    if state.get("awaiting_contact"):
        return {}
    # Prefer the pre-redaction query so the human agent receives the real
    # phone numbers / IDs they need to action the ticket.
    raw_query = state.get("query_original") or state["query"]
    ticket_id = create_ticket(
        query=raw_query,
        session_id=state.get("session_id", "default"),
        contact=state.get("contact") or None,
    )
    return {"ticket_id": ticket_id}


# ----------------------------------------------------- Chain-of-Verification

_COVE_QUESTIONS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You audit support answers. Given a draft answer and the context "
            "it was meant to summarise, list up to 4 short FACTUAL questions "
            "that, if answered independently, would verify the draft's "
            "specific claims (numbers, names, procedures). Output one "
            "question per line. No preamble.",
        ),
        ("human", "Context:\n{context}\n\nDraft answer:\n{draft}"),
    ]
)

_COVE_ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Answer the question briefly using ONLY the provided context. "
            "If the answer is not in the context, reply 'NOT IN CONTEXT'.",
        ),
        ("human", "Context:\n{context}\n\nQuestion: {question}"),
    ]
)

_COVE_REVISE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are revising a draft support answer for the user's "
            "question. Use the verification Q/A pairs to correct any "
            "unsupported claims in the draft. Drop facts marked 'NOT IN "
            "CONTEXT'. Preserve the user's language and tone. Keep "
            "ALCE-style [N] citations from the context where present.",
        ),
        (
            "human",
            "User question: {query}\n\nContext:\n{context}\n\n"
            "Draft:\n{draft}\n\nVerification Q/A:\n{verifications}\n\n"
            "Revised answer:",
        ),
    ]
)


def _cove_pipeline(
    query: str,
    draft: str,
    context: str,
    history: list[BaseMessage],
    config=None,
) -> str:
    """Three-step verify-then-revise — independent answering avoids the
    anchoring bias of joint verification (Dhuliawala et al., 2023).

    All three intermediate LLM calls run with emission suppressed so
    CopilotKit doesn't surface verification questions / answers as
    visible chat text — only `state["answer"]` (the final revised
    text) appears to the user."""
    llm = get_llm(temperature=0.0)
    silent = _silent_config(config)

    # 1. Generate verification questions.
    qs_msg = (_COVE_QUESTIONS_PROMPT | llm).invoke(
        {"context": context, "draft": draft},
        config=silent,
    )
    questions = [
        q.strip("- •*").strip()
        for q in (qs_msg.content or "").splitlines()
        if q.strip()
    ][:4]
    if not questions:
        return draft  # nothing to verify → trust the draft

    # 2. Answer each independently (NOT seeing the draft).
    qa_lines: list[str] = []
    for q in questions:
        a_msg = (_COVE_ANSWER_PROMPT | llm).invoke(
            {"context": context, "question": q},
            config=silent,
        )
        qa_lines.append(f"Q: {q}\nA: {(a_msg.content or '').strip()}")

    # 3. Revise the draft using the verifications.
    revised = (_COVE_REVISE_PROMPT | llm).invoke(
        {
            "query": query,
            "context": context,
            "draft": draft,
            "verifications": "\n\n".join(qa_lines),
        },
        config=silent,
    )
    return revised.content or draft


def verifier_node(state: SupportState, config=None) -> SupportState:
    """CoVe pass over the generator's draft answer. No-op if the flag is
    off or if there are no context docs to verify against."""
    if not settings.chain_of_verification:
        return {}
    draft = state.get("answer", "")
    docs = state.get("context_docs", []) or []
    if not draft or not docs:
        return {}
    revised = _cove_pipeline(
        query=state["query"],
        draft=draft,
        context=_format_docs(docs),
        history=_history_messages(state),
        config=config,
    )
    update: SupportState = {"answer": revised}
    if settings.citations_enabled:
        update["citations"] = _extract_citations(revised, max_idx=len(docs))
    return update


# ------------------------------------------------------ Corrective RAG ----

from pydantic import BaseModel, Field  # noqa: E402 — kept near consumer


class RetrievalAssessment(BaseModel):
    """Structured output for the CRAG evaluator."""

    rating: str = Field(
        description="One of: correct, ambiguous, incorrect"
    )
    reason: str = Field(description="One short sentence")


_CRAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You judge whether the retrieved chunks actually answer the "
            "user's question. Output exactly one rating:\n"
            "  - 'correct'   : at least one chunk directly answers the query\n"
            "  - 'ambiguous' : chunks are related but don't answer it fully\n"
            "  - 'incorrect' : chunks are off-topic / irrelevant\n",
        ),
        (
            "human",
            "Query: {query}\n\nRetrieved chunks:\n{context}\n\nRating:",
        ),
    ]
)


def crag_evaluator_node(state: SupportState, config=None) -> SupportState:
    """Assess retrieval quality. Adds `retrieval_quality` to state."""
    if not settings.crag_enabled:
        return {"retrieval_quality": "correct"}
    docs = state.get("context_docs", []) or []
    if not docs:
        return {"retrieval_quality": "incorrect"}
    try:
        structured = get_llm(temperature=0.0).with_structured_output(
            RetrievalAssessment
        )
        # CRAG's structured-output JSON is internal scaffolding — never
        # show it as chat text.
        decision = (_CRAG_PROMPT | structured).invoke(
            {"query": state["query"], "context": _format_docs(docs)},
            config=_silent_config(config),
        )
        rating = (decision.rating or "correct").lower().strip()
        if rating not in {"correct", "ambiguous", "incorrect"}:
            rating = "correct"
    except Exception:  # noqa: BLE001
        logger.warning("CRAG evaluator failed; assuming correct.")
        rating = "correct"
    return {"retrieval_quality": rating}


def web_search_node(state: SupportState) -> SupportState:
    """CRAG fallback: pull web results via Tavily when retrieval was rated
    'incorrect'. Skips silently if the API key isn't configured."""
    if not settings.tavily_api_key:
        return {
            "answer": (
                "يا فندم، مفيش معلومة دقيقة في قاعدة البيانات بتاعتي "
                "للسؤال ده. ممكن أرفع تذكرة لمختص يتواصل معاك؟"
            ),
            "context_docs": [],
            "used_web_search": False,
        }
    try:
        from tavily import TavilyClient  # type: ignore

        client = TavilyClient(api_key=settings.tavily_api_key)
        result = client.search(state["query"], max_results=4)
        web_docs = [
            Document(
                page_content=r.get("content", "")[:800],
                metadata={"source": r.get("url", "web"), "via": "tavily"},
            )
            for r in result.get("results", [])
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tavily search failed: %s", exc)
        web_docs = []

    if not web_docs:
        return {
            "answer": (
                "يا فندم، السؤال ده خارج قاعدة البيانات بتاعتي ومش لاقي "
                "نتايج من البحث. هرفع تذكرة للمختص."
            ),
            "context_docs": [],
            "used_web_search": True,
        }
    # Re-run generation against the web context.
    chain = _answer_prompt() | get_llm()
    msg = chain.invoke(
        {
            "context": _format_docs(web_docs),
            "query": state["query"],
            "history": _history_messages(state),
        }
    )
    update: SupportState = {
        "answer": msg.content,
        "context_docs": web_docs,
        "used_web_search": True,
    }
    if settings.citations_enabled:
        update["citations"] = _extract_citations(
            msg.content, max_idx=len(web_docs)
        )
    return update
