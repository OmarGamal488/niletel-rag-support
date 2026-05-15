"""In-memory request metrics — simple counters and a rolling latency average."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock


class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self.total = 0
        self.by_category: dict[str, int] = defaultdict(int)
        self._latency_sum_ms = 0.0

    def record(self, category: str, latency_ms: float) -> None:
        with self._lock:
            self.total += 1
            self.by_category[category] += 1
            self._latency_sum_ms += latency_ms

    def snapshot(self) -> dict:
        with self._lock:
            avg = self._latency_sum_ms / self.total if self.total else 0.0
            return {
                "total_queries": self.total,
                "by_category": dict(self.by_category),
                "avg_latency_ms": round(avg, 2),
            }


metrics = Metrics()
