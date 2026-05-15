"""Semantic cache (Tier 3 #13).

Vector-similarity cache that sits in front of the LangGraph. Two queries
that mean the same thing — even worded differently or in different
languages — produce one LLM call instead of two.

Embeddings are reused from `src.retriever._embeddings()` (bge-m3, already
loaded), so cache lookups are cheap. Storage is in-process and bounded
by LRU: fine for a demo. For production, swap the backend for Redis /
Milvus / the real GPTCache library — the public interface (`lookup`,
`store`, `clear`) is identical.

Design notes:
  * Cache key = embedding of the (redacted) query. Storing the raw
    response means the cached answer was already produced *after* PII
    restoration, so it's safe to return verbatim.
  * COMPLAINT queries are *never* cached: each complaint must spawn its
    own ticket.
  * Match threshold defaults to 0.92 cosine — tuned empirically: lower
    threshholds (≤0.88) start leaking between distinct intents.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    query: str
    embedding: np.ndarray
    payload: dict[str, Any]
    created_at: float = field(default_factory=time.time)
    hits: int = 0


class SemanticCache:
    """LRU + cosine-similarity cache.

    Not thread-safe across processes — a single FastAPI worker is the
    intended deployment surface. For multi-worker setups, plug Redis.
    """

    # Categories that should never be cached: a complaint must always
    # open its own ticket, even if phrased identically to a past one.
    _SKIP_CATEGORIES = {"COMPLAINT", "ACTION"}

    def __init__(
        self,
        threshold: float | None = None,
        max_entries: int | None = None,
    ) -> None:
        self._threshold = threshold or settings.semantic_cache_threshold
        self._max_entries = max_entries or settings.semantic_cache_max_entries
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

    # ----------------------------------------------------------------
    def _embedder(self):
        from src.retriever import _embeddings

        return _embeddings()

    def _embed(self, text: str) -> np.ndarray:
        vec = np.asarray(self._embedder().embed_query(text), dtype=np.float32)
        n = np.linalg.norm(vec)
        return vec / n if n > 0 else vec

    # ----------------------------------------------------------------
    def lookup(self, query: str) -> dict[str, Any] | None:
        """Return the cached payload for the closest match above threshold,
        or None. Also increments the entry's hit counter."""
        if not settings.semantic_cache_enabled or not query:
            return None
        with self._lock:
            if not self._entries:
                return None
            qv = self._embed(query)
            best_key: str | None = None
            best_sim = -1.0
            for key, entry in self._entries.items():
                sim = float(qv @ entry.embedding)
                if sim > best_sim:
                    best_sim = sim
                    best_key = key
            if best_key is None or best_sim < self._threshold:
                return None
            entry = self._entries[best_key]
            entry.hits += 1
            self._entries.move_to_end(best_key)  # LRU touch
            logger.info(
                "semantic-cache HIT sim=%.3f age=%.0fs hits=%d",
                best_sim,
                time.time() - entry.created_at,
                entry.hits,
            )
            return {"_sim": best_sim, **entry.payload}

    def store(self, query: str, payload: dict[str, Any]) -> None:
        """Insert a (query, payload) pair. Caller is responsible for
        skipping uncacheable categories (we double-check below)."""
        if not settings.semantic_cache_enabled or not query:
            return
        cat = payload.get("category")
        if cat in self._SKIP_CATEGORIES:
            return
        with self._lock:
            qv = self._embed(query)
            key = f"k{len(self._entries)}_{int(time.time() * 1000)}"
            self._entries[key] = _CacheEntry(
                query=query, embedding=qv, payload=payload
            )
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)  # drop LRU

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "max_entries": self._max_entries,
                "threshold": self._threshold,
                "total_hits": sum(e.hits for e in self._entries.values()),
            }


cache = SemanticCache()
