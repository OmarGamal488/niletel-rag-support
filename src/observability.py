"""Observability surface: Langfuse tracing + Prometheus metrics.

Two independent pieces that both turn into no-ops when their keys / deps
are missing, so the demo still boots cleanly without them.

Langfuse
--------
`get_langfuse_handler()` returns a singleton LangChain `CallbackHandler`.
Pass it via `config={"callbacks": [handler]}` on graph `.invoke(...)`. The
handler captures per-node spans, prompts, completions, token usage and
latency, and ships them to the Langfuse project keyed by
`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`.

Prometheus
----------
We expose four custom metric families on top of the default request-level
ones produced by `prometheus-fastapi-instrumentator`:

* `niletel_cache_lookups_total{result}`  — semantic-cache hit/miss
* `niletel_retrieval_seconds`            — retrieval-node latency histogram
* `niletel_node_seconds{node}`           — per-LangGraph-node latency
* `niletel_pii_redactions_total{kind}`   — PII categories stripped

The names follow the Prom convention (`<namespace>_<subsystem>_<unit>`)
so they slot into any existing Grafana dashboard.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from prometheus_client import Counter, Histogram

from src.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- Langfuse
@lru_cache(maxsize=1)
def get_langfuse_handler() -> Any | None:
    """Return a singleton Langfuse CallbackHandler, or None when disabled.

    Lazy-imported so the dep is optional: a fresh checkout without
    `langfuse` installed still boots, just without tracing.
    """
    if not settings.langfuse_enabled:
        return None
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("Langfuse keys missing — tracing disabled.")
        return None

    # Langfuse uses an OpenTelemetry OTLP exporter under the hood whose
    # default HTTP timeout is 5s. Langfuse Cloud (especially the free tier)
    # routinely exceeds that, producing noisy `Read timed out` ERROR logs.
    # Bump to 30s + drop the exporter log level so failed exports no longer
    # bubble up as ERROR. Both can be overridden via env.
    import logging as _logging
    import os as _os

    _os.environ.setdefault("OTEL_EXPORTER_OTLP_TIMEOUT", "30")
    _logging.getLogger(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter"
    ).setLevel(_logging.CRITICAL)
    try:
        # New SDK (>=2.0) layout
        from langfuse.langchain import CallbackHandler  # type: ignore
    except ImportError:
        try:  # older SDK fallback
            from langfuse.callback import CallbackHandler  # type: ignore
        except ImportError:
            logger.warning("`langfuse` package not installed — tracing disabled.")
            return None

    try:
        handler = CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except TypeError:
        # Newest SDKs read keys from env only; constructor takes no args.
        import os

        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
        os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
        handler = CallbackHandler()

    logger.info("Langfuse tracing enabled — host=%s", settings.langfuse_host)
    return handler


def langgraph_callbacks() -> list:
    """Convenience: list to splat into `config={"callbacks": [...]}`."""
    handler = get_langfuse_handler()
    return [handler] if handler is not None else []


# -------------------------------------------------------------- Prometheus
CACHE_LOOKUPS = Counter(
    "niletel_cache_lookups_total",
    "Semantic cache lookups by result.",
    labelnames=("result",),  # hit | miss
)

RETRIEVAL_SECONDS = Histogram(
    "niletel_retrieval_seconds",
    "Time spent in the retrieval node (hybrid + rerank + reorder).",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)

NODE_SECONDS = Histogram(
    "niletel_node_seconds",
    "Per-LangGraph-node wall-clock latency.",
    labelnames=("node",),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

PII_REDACTIONS = Counter(
    "niletel_pii_redactions_total",
    "PII items redacted from user queries.",
    labelnames=("kind",),  # EG_PHONE | EG_NATIONAL_ID | EMAIL | IBAN
)

QUERIES = Counter(
    "niletel_queries_total",
    "Total /query requests routed by category.",
    labelnames=("category",),  # INFO | COMPLAINT | ACTION | GREETING | OUT_OF_SCOPE | UNKNOWN
)


def record_cache(hit: bool) -> None:
    CACHE_LOOKUPS.labels("hit" if hit else "miss").inc()


def record_retrieval_seconds(seconds: float) -> None:
    RETRIEVAL_SECONDS.observe(seconds)


def record_node_seconds(node: str, seconds: float) -> None:
    NODE_SECONDS.labels(node).observe(seconds)


def record_pii(kinds: list[str]) -> None:
    for k in kinds:
        PII_REDACTIONS.labels(k).inc()


def record_query(category: str) -> None:
    QUERIES.labels(category or "UNKNOWN").inc()
