"""Smoke tests for the evaluation pipeline (no live LLM calls)."""

from __future__ import annotations

import json
from pathlib import Path

from src.evaluator import _retrieval_hit_rate, _routing_accuracy


def test_routing_accuracy():
    rows = [
        {"category": "INFO", "expected_category": "INFO"},
        {"category": "COMPLAINT", "expected_category": "INFO"},
        {"category": "GREETING", "expected_category": "GREETING"},
    ]
    out = _routing_accuracy(rows)
    assert out["n"] == 3
    assert abs(out["routing_accuracy"] - 2 / 3) < 1e-6


def test_retrieval_hit_rate_only_counts_items_with_expected_source():
    rows = [
        {"expected_source": "a.md", "retrieved_sources": ["a.md", "b.md"]},
        {"expected_source": "c.md", "retrieved_sources": ["d.md"]},
        {"expected_source": None, "retrieved_sources": ["x.md"]},
    ]
    out = _retrieval_hit_rate(rows)
    assert out["n"] == 2
    assert abs(out["retrieval_hit_rate"] - 0.5) < 1e-6


def test_testset_file_is_valid_json_with_required_keys():
    path = Path("eval/ragas_testset.json")
    assert path.exists(), "eval/ragas_testset.json missing"
    items = json.loads(path.read_text(encoding="utf-8"))
    assert len(items) >= 5
    for it in items:
        assert "question" in it
        assert "expected_category" in it
        assert it["expected_category"] in {"INFO", "COMPLAINT", "GREETING", "OUT_OF_SCOPE"}
