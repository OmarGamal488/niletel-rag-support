"""NileTel Support — Streamlit chat UI rendered with the v2 Vibrant design.

Layout: topbar / metrics / transcript / composer / insights, all rendered
as semantic HTML with the Inter + IBM Plex Sans Arabic typography pair.
Streamlit widgets handle interactivity; everything else is HTML/CSS so we
can match the design exactly.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

# Make the project root importable when Streamlit runs this file directly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import html as _html

import httpx
import streamlit as st
from styles import (
    BRAND_CSS,
    render_assistant_message,
    render_empty_state,
    render_insights_body,
    render_metrics,
    render_status,
    render_topbar,
    render_user_message,
)

# ---------- React-style HTML components (bonus deliverable #4) ----------
# Each component lives in app/components/*.html with CSS scoped via a
# `nt-` class prefix, so we can drop the markup straight into the
# transcript markdown stream — no iframe needed.
_COMPONENTS_DIR = Path(__file__).parent / "components"


_HTML_COMMENT_RE = __import__("re").compile(r"<!--.*?-->", flags=__import__("re").DOTALL)


def _load_component(name: str) -> str:
    """Read an HTML component and strip leading documentation comments
    so Streamlit's markdown parser doesn't render them as text."""
    raw = (_COMPONENTS_DIR / name).read_text(encoding="utf-8")
    return _HTML_COMMENT_RE.sub("", raw).strip()


def render_typing_indicator() -> str:
    """HTML for the animated 'typing' dots, shown while we wait for a reply."""
    return _load_component("typing_indicator.html")


def render_ticket_badge_html(
    ticket_id: str, status_label: str = "open"
) -> str:
    tpl = _load_component("ticket_badge.html")
    return (
        tpl.replace("{{TICKET_ID}}", _html.escape(ticket_id))
        .replace("{{STATUS}}", _html.escape(status_label))
    )


def render_source_cards_html(sources: list[dict]) -> str:
    if not sources:
        return ""
    tpl = _load_component("source_card.html")
    cards = "".join(
        tpl.replace("{{INDEX}}", str(i))
        .replace("{{SOURCE}}", _html.escape(src.get("source", "?")))
        .replace("{{SCORE}}", _html.escape(str(src.get("score", "kb"))))
        .replace("{{SNIPPET}}", _html.escape(src.get("snippet", "")[:600]))
        for i, src in enumerate(sources, start=1)
    )
    return f'<div class="nt-src-list">{cards}</div>'


# Note: the under-the-hood "trace" visualizations (styled HTML card,
# native Streamlit-widget expander, and the animated horizontal pipeline)
# were removed at the user's request — the chat is the only surface now.
# The backend still attaches a `trace` field to each /query response, but
# it is intentionally ignored by this UI. To reintroduce the panel later,
# revive `render_pipeline_panel_html` and friends from git history.

DEFAULT_API = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="NileTel Support",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(BRAND_CSS, unsafe_allow_html=True)


# ---------- Session state ----------
def _init_state() -> None:
    defaults = {
        "messages": [],
        "session_id": uuid.uuid4().hex[:12],
        "api_url": DEFAULT_API,
        "use_backend": True,
        "latencies": deque(maxlen=50),
        "category_counts": {},
        "_pending_query": None,
        "_health": None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


_init_state()


# ---------- Backend ----------
def call_backend(query: str) -> dict:
    r = httpx.post(
        f"{st.session_state.api_url}/query",
        json={"query": query, "session_id": st.session_state.session_id},
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json()


def call_backend_streaming(query: str, placeholder) -> dict:
    """Use the SSE /query/stream endpoint and update `placeholder` as the
    answer flows in. Returns the same dict shape as `call_backend` once
    the closing `done` event lands.

    Handles three terminal states the server may emit:
      * `done`  — happy path, full metadata included
      * `error` — graph raised (rate limit, timeout, etc.); shows the
                  error to the user instead of silently hanging
      * exception during the stream — falls back to the non-streaming
                  POST so the message still lands in the transcript
    """
    import json as _json

    answer_so_far = ""
    metadata: dict = {}
    server_error: str | None = None
    try:
        with httpx.stream(
            "POST",
            f"{st.session_state.api_url}/query/stream",
            json={"query": query, "session_id": st.session_state.session_id},
            timeout=120.0,
        ) as r:
            r.raise_for_status()
            for raw in r.iter_lines():
                if not raw or not raw.startswith("data: "):
                    continue
                try:
                    payload = _json.loads(raw[6:])
                except _json.JSONDecodeError:
                    continue
                kind = payload.get("type")
                if kind == "chunk":
                    answer_so_far += payload.get("text", "")
                    placeholder.markdown(answer_so_far + " ▌")
                elif kind == "error":
                    server_error = payload.get("message", "unknown server error")
                    break
                elif kind == "done":
                    metadata = payload
                    break
    except Exception:
        # Stream broke at the transport layer — fall back to blocking.
        return call_backend(query)

    if server_error is not None:
        msg = f"⚠️ Backend error: {server_error}"
        placeholder.markdown(msg)
        return {
            "answer": msg,
            "category": "OUT_OF_SCOPE",
            "ticket_id": None,
            "awaiting_contact": False,
            "source_docs": [],
        }

    # If the stream closed without a `done` event the server hung up
    # mid-response (proxy timeout, etc.). Surface that explicitly rather
    # than rendering an empty bubble.
    if not metadata:
        msg = answer_so_far or "⚠️ No response received from backend."
        placeholder.markdown(msg)
        return {
            "answer": msg,
            "category": "OUT_OF_SCOPE",
            "ticket_id": None,
            "awaiting_contact": False,
            "source_docs": [],
        }

    placeholder.markdown(answer_so_far)
    return {
        "answer": answer_so_far,
        "category": metadata.get("category", "INFO"),
        "ticket_id": metadata.get("ticket_id"),
        "awaiting_contact": metadata.get("awaiting_contact", False),
        "source_docs": metadata.get("source_docs", []),
    }


def call_graph_direct(query: str) -> dict:
    """In-process fallback used when the Backend toggle is OFF.
    Stateless invoke — we no longer need the per-node trace because the
    under-the-hood visualizations have been removed."""
    from src.graph import build_graph

    result = build_graph().invoke(
        {"query": query, "session_id": st.session_state.session_id}
    )
    return {
        "answer": result.get("answer", ""),
        "category": result.get("category", "INFO"),
        "ticket_id": result.get("ticket_id"),
        "source_docs": [
            {"source": d.metadata.get("source", "?"), "snippet": d.page_content[:400]}
            for d in result.get("context_docs", []) or []
        ],
    }


def ask(query: str) -> dict:
    if st.session_state.use_backend:
        try:
            return call_backend(query)
        except Exception:
            st.toast("Backend offline — using in-process graph", icon="🔁")
    return call_graph_direct(query)


def fetch_health() -> dict | None:
    if not st.session_state.use_backend:
        return None
    try:
        return httpx.get(f"{st.session_state.api_url}/health", timeout=2.0).json()
    except Exception:
        return None


def fetch_metrics() -> dict | None:
    if not st.session_state.use_backend:
        return None
    try:
        return httpx.get(f"{st.session_state.api_url}/stats", timeout=2.0).json()
    except Exception:
        return None


def load_ragas_scores() -> dict | None:
    try:
        report = json.loads(Path("eval/ragas_report.json").read_text())
        return report.get("ragas", {}).get("scores")
    except Exception:
        return None


# =========================================================================
# Sidebar
# =========================================================================
with st.sidebar:
    st.markdown('<span class="nt-side-label">Connection</span>', unsafe_allow_html=True)
    st.session_state.use_backend = st.toggle(
        "Backend",
        value=st.session_state.use_backend,
        help="Off = run the graph in-process (no API needed).",
    )
    st.session_state.api_url = st.text_input(
        "API URL", st.session_state.api_url, label_visibility="collapsed"
    )

    health = fetch_health()
    st.session_state._health = health
    if health:
        st.markdown(
            f'<div class="nt-health"><span class="nt-dot success"></span>'
            f'<span class="lbl">Connected</span>'
            f'<span class="meta">{health.get("model", "")[:20]}</span></div>',
            unsafe_allow_html=True,
        )
    elif st.session_state.use_backend:
        st.markdown(
            '<div class="nt-health"><span class="nt-dot destructive"></span>'
            '<span class="lbl">Offline</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="nt-health"><span class="nt-dot muted"></span>'
            '<span class="lbl">In-process mode</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<span class="nt-side-label">Retrieval</span>', unsafe_allow_html=True
    )
    mode = st.radio(
        "Retrieval mode",
        options=["hybrid", "hyde", "rag_fusion"],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        help=(
            "hybrid     — dense + BM25 + RRF (baseline).\n"
            "hyde       — LLM hypothetical doc for dense leg (Gao 2022).\n"
            "rag_fusion — LLM paraphrases × hybrid × RRF (Rackauckas 2024)."
        ),
    )
    # Push the choice into the in-process settings so the next call picks it up.
    # (For the FastAPI backend, set RETRIEVAL_MODE in .env — this toggle only
    # affects the in-process fallback.)
    try:
        from src.config import settings as _settings
        _settings.retrieval_mode = mode  # type: ignore[assignment]
    except Exception:
        pass

    st.markdown(
        '<span class="nt-side-label">Conversation</span>', unsafe_allow_html=True
    )
    if st.button("⌫  Clear conversation", key="clear_btn"):
        st.session_state.messages = []
        st.session_state.latencies.clear()
        st.session_state.category_counts = {}
        if st.session_state.use_backend:
            try:
                httpx.delete(
                    f"{st.session_state.api_url}/history/{st.session_state.session_id}",
                    timeout=5.0,
                )
            except Exception:
                pass
        st.rerun()



# =========================================================================
# Main
# =========================================================================
# --- Topbar ----------------------------------------------------------------
connected = bool(st.session_state._health)
queries = len([m for m in st.session_state.messages if m["role"] == "user"])
st.markdown(render_topbar(connected, queries), unsafe_allow_html=True)


# --- Metrics ---------------------------------------------------------------
metrics_data = fetch_metrics() or {
    "total_queries": queries,
    "by_category": st.session_state.category_counts,
    "avg_latency_ms": (
        sum(st.session_state.latencies) / len(st.session_state.latencies)
        if st.session_state.latencies
        else 0.0
    ),
}
ticket_count = sum(
    1 for m in st.session_state.messages
    if m.get("role") == "assistant" and m.get("ticket_id")
)
complaint_count = metrics_data.get("by_category", {}).get(
    "COMPLAINT", st.session_state.category_counts.get("COMPLAINT", 0)
)
st.markdown(
    render_metrics(
        total=metrics_data.get("total_queries", 0),
        latency_ms=metrics_data.get("avg_latency_ms", 0.0),
        complaints=complaint_count,
        tickets=ticket_count,
    ),
    unsafe_allow_html=True,
)


# --- Transcript ------------------------------------------------------------
# All chat bubbles are buffered into a single HTML blob and rendered with
# one st.markdown() call. The only thing that breaks the buffer is the
# native-widget trace panel, which has to use Streamlit primitives —
# when we hit one of those, we close the transcript div, flush the
# buffer, render the widget, then reopen the div in a fresh buffer.
#
# Why bother? Each st.markdown() call wraps in its own Streamlit
# container with a default ~1rem vertical gap. Many small markdown
# calls stack up into visible empty whitespace between the metrics row
# and the first message. Single-buffer rendering eliminates that.

def _render_assistant_html(msg: dict) -> str:
    """HTML for one assistant turn: bubble + ticket badge + source cards.
    Trace panels are handled separately by the caller."""
    parts = [
        render_assistant_message(
            text=msg.get("content", ""),
            category=msg.get("category", "INFO"),
            latency_ms=msg.get("latency_ms"),
            ticket_id=None,
            sources=None,
            time_str=msg.get("time"),
        )
    ]
    if msg.get("ticket_id"):
        parts.append(render_ticket_badge_html(msg["ticket_id"]))
    if msg.get("source_docs"):
        parts.append(render_source_cards_html(msg["source_docs"]))
    return "".join(parts)


# Build the full transcript as one HTML blob and render it in a single
# st.markdown call — no per-message containers, no trace widgets to
# interleave. Simplest possible flow now that under-the-hood views are
# gone.
html_chunks: list[str] = []

if not st.session_state.messages:
    html_chunks.append(render_empty_state())
else:
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            html_chunks.append(
                render_user_message(msg["content"], time_str=msg.get("time"))
            )
        else:
            html_chunks.append(_render_assistant_html(msg))

# Pending query (from sidebar example chips) → user msg + typing indicator.
pending = st.session_state.pop("_pending_query", None)
if pending:
    html_chunks.append(render_user_message(pending))
    html_chunks.append(
        render_status("Routing query · retrieving sources · generating answer…")
    )
    html_chunks.append(render_typing_indicator())

import re as _re

body = "".join(html_chunks)
# Collapse whitespace between adjacent tags (i.e. `>\s+<` → `><`). Newlines
# left over from the triple-quoted HTML templates were causing Streamlit's
# CommonMark parser to split the transcript into multiple HTML blocks,
# which made orphan closing tags like `</div></div>` render as visible
# text right before the source cards. Text content inside elements
# (snippets, message bodies) is untouched because the pattern only
# matches between consecutive tags.
body = _re.sub(r">\s+<", "><", body)
if body.strip():
    st.markdown(
        f'<div class="nt-transcript">{body}</div>',
        unsafe_allow_html=True,
    )


# --- Inline composer (form, not the docked chat_input) -------------------
with st.form("composer", clear_on_submit=True, border=False):
    col_text, col_send = st.columns([20, 1], gap="small")
    with col_text:
        composer_text = st.text_input(
            "ask",
            placeholder="Ask a question · اسأل سؤال",
            label_visibility="collapsed",
        )
    with col_send:
        sent = st.form_submit_button("➤", use_container_width=True)

prompt = pending or (composer_text.strip() if sent and composer_text else None)


# --- Instant-feedback rerun: when the user submits via the composer, push
# the text into the `_pending_query` slot and immediately rerun so the
# next render shows the bubble + typing indicator BEFORE the backend
# call (~3 s) blocks. Sidebar chips already use this path natively, this
# just makes the composer behave the same way.
if prompt and not pending:
    st.session_state["_pending_query"] = prompt
    st.rerun()


# --- Process the pending prompt (after rendering, so user sees status first)
if prompt:
    user_time = datetime.now().strftime("%H:%M")
    st.session_state.messages.append(
        {"role": "user", "content": prompt, "time": user_time}
    )

    t0 = time.perf_counter()
    # Streaming preferred when backend is on — token-flow UX is significantly
    # better-perceived than the blocking 5–15 s spinner. Falls back to the
    # non-streaming path if backend toggle is OFF or the stream errors.
    stream_target = st.empty() if st.session_state.use_backend else None
    try:
        if stream_target is not None:
            resp = call_backend_streaming(prompt, stream_target)
        else:
            resp = ask(prompt)
    except Exception as exc:  # noqa: BLE001
        resp = {
            "answer": f"⚠️ Error contacting LLM: {exc}",
            "category": "OUT_OF_SCOPE",
            "source_docs": [],
        }
    if stream_target is not None:
        stream_target.empty()  # clear placeholder — re-rendered below on rerun
    latency_ms = (time.perf_counter() - t0) * 1000

    st.session_state.latencies.append(latency_ms)
    cat = resp.get("category", "INFO")
    st.session_state.category_counts[cat] = (
        st.session_state.category_counts.get(cat, 0) + 1
    )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": resp.get("answer", ""),
            "category": cat,
            "ticket_id": resp.get("ticket_id"),
            "latency_ms": latency_ms,
            "source_docs": resp.get("source_docs", []),
            "time": datetime.now().strftime("%H:%M"),
        }
    )

    if resp.get("ticket_id"):
        st.balloons()

    st.rerun()


# --- Insights --------------------------------------------------------------
ragas_scores = load_ragas_scores()
with st.expander(
    f"Insights — category distribution & RAGAS · last {queries} queries",
    expanded=False,
):
    st.markdown(
        render_insights_body(
            category_counts=st.session_state.category_counts
            or metrics_data.get("by_category", {}),
            ragas_scores=ragas_scores,
        ),
        unsafe_allow_html=True,
    )


# --- Auto-scroll to latest message ---------------------------------------
# Inject a tiny iframe (height 0) whose script reaches up to the parent
# document and scrolls the Streamlit container to the bottom on every
# rerun. Mirrors the ChatGPT/Claude behaviour — the user always sees
# their newest message + the assistant's reply without manual scrolling.
# We tie the iframe `key` to the message count + pending flag so each
# new message forces a fresh iframe render (and thus a fresh scroll).
import streamlit.components.v1 as _components

_scroll_key = (
    len(st.session_state.messages),
    bool(st.session_state.get("_pending_query")),
)
_components.html(
    f"""
    <script>
      // Run twice: once on the next animation frame to catch a quick
      // re-layout, then again ~250ms later so any post-render content
      // (source cards, ticket badges, insights expander, etc.) is
      // already laid out by the time we scroll.
      (function() {{
        const k = "{_scroll_key}";
        const doScroll = () => {{
          try {{
            const doc = window.parent.document;
            const main =
              doc.querySelector('section.main')
              || doc.querySelector('[data-testid="stMain"]')
              || doc.querySelector('.main')
              || doc.scrollingElement
              || doc.documentElement;
            if (main) main.scrollTop = main.scrollHeight;
            // Belt-and-braces: scroll the window itself too.
            window.parent.scrollTo({{ top: 99999999, behavior: 'instant' }});
          }} catch (e) {{ /* cross-origin or DOM gone — silent */ }}
        }};
        requestAnimationFrame(doScroll);
        setTimeout(doScroll, 250);
      }})();
    </script>
    """,
    height=0,
)
