"""FastAPI service exposing the RAG support graph."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api.metrics import metrics
from api.schemas import (
    HealthResponse,
    HistoryResponse,
    HistoryTurn,
    MetricsResponse,
    QueryRequest,
    QueryResponse,
    SourceDoc,
    ToolCall,
    TraceEvent,
)
from src.cache import cache
from src.config import settings
from src.contact import format_missing, parse_contact
from src.graph import build_graph
from src.memory import memory
from src.observability import (
    langgraph_callbacks,
    record_cache,
    record_node_seconds,
    record_pii,
    record_query,
)
from src.tracer import run_traced, trace_for_cache_hit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    build_graph()  # cached compile so first request is fast
    logger.info("Graph compiled. Provider=%s model=%s", settings.llm_provider, settings.llm_model)
    yield


app = FastAPI(
    title="NileTel RAG Support API",
    version="0.1.0",
    description="Hybrid-RAG customer support backend (LangGraph + ChromaDB + BM25).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------- Prometheus -----------------------------
# Exposes /metrics in OpenMetrics text format. Default request metrics
# (count, latency, status) come from the instrumentator; our custom
# RAG-pipeline counters/histograms (cache hit-rate, retrieval latency,
# PII redactions) are defined in `src.observability` and update from
# inside `_invoke_graph`.
if settings.prometheus_enabled:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(
            should_group_status_codes=False,
            excluded_handlers=["/metrics", "/health"],
        ).instrument(app).expose(app, include_in_schema=False, should_gzip=True)
        logger.info("Prometheus /metrics endpoint mounted.")
    except ImportError:
        logger.warning(
            "prometheus_fastapi_instrumentator missing — /metrics will only "
            "serve the JSON snapshot. Run `uv add prometheus-fastapi-instrumentator`."
        )


# ------------------------- CopilotKit (Path A) — DISABLED -------------------------
# The Next.js + CopilotKit generative-UI work (frontend/) is parked.
# The /copilotkit AG-UI endpoint below stays in source for future reuse
# but is NOT mounted, so the backend serves only the Streamlit path
# (/query, /query/stream, /history, /health, /metrics).
#
# To re-enable: flip `_COPILOTKIT_ENABLED` to True, ensure the optional
# `copilotkit` + `ag-ui-langgraph` deps are installed, and restart.
_COPILOTKIT_ENABLED = False

if _COPILOTKIT_ENABLED:  # pragma: no cover — disabled by default
    try:
        from ag_ui_langgraph import add_langgraph_fastapi_endpoint
        from copilotkit import LangGraphAGUIAgent

        # CopilotKit's AG-UI adapter calls graph.aget_state(...) so it
        # needs a checkpointer attached. We use a dedicated compile
        # here so the stateless /query path stays untouched.
        add_langgraph_fastapi_endpoint(
            app=app,
            agent=LangGraphAGUIAgent(
                name="niletel",
                description="NileTel RAG customer-support agent (LangGraph + hybrid retrieval + tools).",
                graph=build_graph(with_checkpointer=True),
            ),
            path="/copilotkit",
        )
        logger.info("CopilotKit endpoint mounted at /copilotkit")
    except Exception as exc:  # noqa: BLE001
        logger.warning("CopilotKit endpoint NOT mounted (%s)", exc)


def _to_source_docs(state: dict) -> list[SourceDoc]:
    citations = set(state.get("citations") or [])
    return [
        SourceDoc(
            source=d.metadata.get("source", "unknown"),
            snippet=d.page_content[:300],
            rerank_score=d.metadata.get("rerank_score"),
            cited=(i + 1) in citations,
        )
        for i, d in enumerate(state.get("context_docs", []) or [])
    ]


def _invoke_graph(req: QueryRequest) -> dict:
    """Run the graph with prior history hydrated from memory, then persist
    the new user / assistant turns.

    Wraps the call in the semantic cache so repeated questions short-
    circuit before the graph runs. Uses `run_traced` instead of `.invoke`
    so the response can include a per-node execution trace."""
    # 0. Conversational ticket flow — if a previous turn was a COMPLAINT
    #    that we paused on for contact info, this turn IS the contact
    #    reply. Parse it, store on the session, and re-route as the
    #    original complaint so the graph reaches the ticketer.
    pending = memory.get_pending_complaint(req.session_id)
    if pending:
        parsed = parse_contact(req.query)
        if parsed.is_actionable():
            memory.set_contact(req.session_id, parsed.as_dict())
            memory.clear_pending_complaint(req.session_id)
            memory.append(req.session_id, "user", req.query)
            req = QueryRequest(query=pending, session_id=req.session_id)
        else:
            missing = format_missing(parsed) or "phone or email"
            ask_again = (
                "Thanks — I still need a way to reach you back. "
                f"Could you share your {missing}? "
                "(_e.g._ Ahmed, 0101 234 5678, ahmed@example.com)"
            )
            memory.append(req.session_id, "user", req.query)
            memory.append(req.session_id, "assistant", ask_again)
            return {
                "answer": ask_again,
                "category": "COMPLAINT",
                "confidence": 1.0,
                "trace": [
                    ev.to_dict() for ev in trace_for_cache_hit(0.0)
                ],
                "_total_elapsed_ms": 0.0,
                "awaiting_contact": True,
            }

    # 1. Semantic-cache lookup (skips entire graph on hit).
    t0 = time.perf_counter()
    cached = cache.lookup(req.query)
    if cached:
        record_cache(hit=True)
        elapsed = (time.perf_counter() - t0) * 1000.0
        memory.append(req.session_id, "user", req.query)
        if cached.get("answer"):
            memory.append(req.session_id, "assistant", cached["answer"])
        return {
            **cached,
            "used_cache": True,
            "trace": [ev.to_dict() for ev in trace_for_cache_hit(elapsed)],
            "_total_elapsed_ms": round(elapsed, 1),
        }
    record_cache(hit=False)

    # 2. Run the graph with per-node tracing + Langfuse callbacks.
    history = memory.get(req.session_id)
    callbacks = langgraph_callbacks()  # [] when Langfuse is disabled
    invoke_config = {
        "callbacks": callbacks,
        "metadata": {
            "session_id": req.session_id,
            "langfuse_session_id": req.session_id,
            "langfuse_user_id": req.session_id,
        },
        "tags": ["niletel", "rag"],
    } if callbacks else None

    # Hydrate any previously-captured contact for this session so a
    # second complaint in the same chat doesn't re-prompt the user.
    session_contact = memory.get_contact(req.session_id) or {}

    result, trace = run_traced(
        build_graph(),
        {
            "query": req.query,
            "session_id": req.session_id,
            "history": history,
            "contact": session_contact,
        },
        config=invoke_config,
    )

    # 3. Emit Prometheus metrics from the trace + state.
    for ev in trace:
        record_node_seconds(ev.node, ev.elapsed_ms / 1000.0)
    record_pii(result.get("pii_kinds") or [])

    # 3a. Conversational ticket flow — if the graph asked for contact
    #     info, remember the original complaint so the next user turn
    #     can be parsed as the reply.
    if result.get("awaiting_contact"):
        memory.set_pending_complaint(req.session_id, req.query)

    # 4. Persist memory + populate cache.
    memory.append(req.session_id, "user", req.query)
    answer = result.get("answer", "")
    if answer:
        memory.append(req.session_id, "assistant", answer)
    cache.store(
        req.query,
        {
            "answer": answer,
            "category": result.get("category"),
            "confidence": result.get("confidence"),
            "citations": result.get("citations") or [],
            "retrieval_quality": result.get("retrieval_quality"),
            "context_docs": result.get("context_docs") or [],
        },
    )
    result["trace"] = [ev.to_dict() for ev in trace]
    return result


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if settings.llm_provider == "lightning" and settings.lightning_model:
        active_model = settings.lightning_model
    else:
        active_model = settings.llm_model
    return HealthResponse(
        status="ok",
        provider=settings.llm_provider,
        model=active_model,
    )


@app.get("/stats", response_model=MetricsResponse)
def get_stats() -> MetricsResponse:
    """JSON snapshot for the Streamlit dashboard.

    The Prometheus scrape endpoint lives at `/metrics` (text-format,
    served by the instrumentator above). This route is the small JSON
    summary consumed by the Streamlit sidebar.
    """
    return MetricsResponse(**metrics.snapshot())


@app.post("/query", response_model=QueryResponse)
def query_endpoint(req: QueryRequest) -> QueryResponse:
    start = time.perf_counter()
    try:
        result = _invoke_graph(req)
    except Exception as exc:
        logger.exception("graph invocation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error: {exc}",
        ) from exc

    latency_ms = (time.perf_counter() - start) * 1000
    category = result.get("category", "UNKNOWN")
    metrics.record(category, latency_ms)
    record_query(category)

    return QueryResponse(
        answer=result.get("answer", ""),
        category=result["category"],
        confidence=result.get("confidence"),
        ticket_id=result.get("ticket_id"),
        source_docs=_to_source_docs(result),
        citations=result.get("citations") or [],
        retrieval_quality=result.get("retrieval_quality"),
        used_web_search=bool(result.get("used_web_search")),
        used_cache=bool(result.get("used_cache")),
        pii_kinds=result.get("pii_kinds") or [],
        tool_calls=[ToolCall(**tc) for tc in (result.get("tool_calls") or [])],
        awaiting_contact=bool(result.get("awaiting_contact")),
        trace=[TraceEvent(**ev) for ev in (result.get("trace") or [])],
        total_elapsed_ms=result.get("_total_elapsed_ms"),
    )


@app.post("/query/stream")
async def query_stream(req: QueryRequest) -> StreamingResponse:
    """SSE stream — emits the final answer in chunks. (Token-level streaming
    requires the LLM client to support it; this implementation is a simple
    chunked replay so downstream UIs can hook in immediately.)"""

    async def event_gen():
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: _invoke_graph(req))
        answer = result.get("answer", "")
        chunk_size = 40
        for i in range(0, len(answer), chunk_size):
            yield f"data: {answer[i : i + chunk_size]}\n\n"
            await asyncio.sleep(0.02)
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/history/{session_id}", response_model=HistoryResponse)
def get_history(session_id: str) -> HistoryResponse:
    turns = memory.get(session_id)
    return HistoryResponse(
        session_id=session_id,
        turns=[HistoryTurn(**t) for t in turns],
    )


@app.delete("/history/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(session_id: str) -> None:
    cleared = memory.clear(session_id)
    logger.info(
        "clear_history session=%s cleared=%s", session_id, cleared
    )
    return None


