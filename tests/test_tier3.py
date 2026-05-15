"""Tier 3 tests: PII, semantic cache, tool agent, triad eval."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src import cache as cache_module
from src import nodes as nodes_module
from src import tools as tools_module
from src.config import settings


@contextmanager
def _flags(**overrides):
    snapshot = {k: getattr(settings, k) for k in overrides}
    for k, v in overrides.items():
        setattr(settings, k, v)
    try:
        yield
    finally:
        for k, v in snapshot.items():
            setattr(settings, k, v)


# =========================== PII redaction ===========================


def test_pii_redact_egyptian_phone():
    from src.pii import redact, restore

    text = "أهلاً، رصيدي على 01012345678 كام؟"
    redacted, mapping = redact(text)
    assert "01012345678" not in redacted
    assert "<EG_PHONE_1>" in redacted
    assert restore(redacted, mapping) == text


def test_pii_redact_multiple_kinds_and_dedup():
    from src.pii import found_kinds, redact

    text = (
        "Phones 01012345678 and 01098765432, "
        "national id 29801011234567, email a@b.com"
    )
    redacted, mapping = redact(text)
    kinds = set(found_kinds(mapping))
    assert {"EG_PHONE", "EG_NATIONAL_ID", "EMAIL"}.issubset(kinds)
    # Same phone in a follow-up should reuse the placeholder.
    redacted2, mapping2 = redact("call me on 01012345678 again, 01012345678 still works")
    placeholders = [v for v in mapping2.values()]
    # only 1 unique phone → only 1 placeholder mapped
    assert sum(1 for v in mapping2.values() if v == "01012345678") == 1


def test_pii_restore_handles_double_digit_indices():
    """Sorting longest-first guards against `<EG_PHONE_10>` getting
    half-matched by `<EG_PHONE_1>` during restore."""
    from src.pii import restore

    mapping = {f"<EG_PHONE_{i}>": f"010{i:08d}" for i in range(1, 12)}
    answer = "Try <EG_PHONE_10> first, then <EG_PHONE_1>."
    restored = restore(answer, mapping)
    assert "010" + "0" * 7 + "10" not in restored  # no broken concat
    assert mapping["<EG_PHONE_10>"] in restored
    assert mapping["<EG_PHONE_1>"] in restored


def test_pii_redact_node_writes_state_correctly():
    with _flags(pii_redaction_enabled=True):
        out = nodes_module.pii_redact_node({"query": "balance on 01012345678?"})
    assert out["query_original"] == "balance on 01012345678?"
    assert "<EG_PHONE_1>" in out["query"]
    assert out["pii_map"]["<EG_PHONE_1>"] == "01012345678"
    assert out["pii_kinds"] == ["EG_PHONE"]


def test_pii_redact_node_skipped_when_disabled():
    with _flags(pii_redaction_enabled=False):
        out = nodes_module.pii_redact_node({"query": "01012345678"})
    assert out == {}


def test_pii_restore_node_round_trips():
    state = {
        "answer": "Your balance on <EG_PHONE_1> is 47 EGP.",
        "pii_map": {"<EG_PHONE_1>": "01012345678"},
    }
    with _flags(pii_redaction_enabled=True):
        out = nodes_module.pii_restore_node(state)
    assert "01012345678" in out["answer"]


# =========================== Semantic cache ===========================


class _FakeEmbedder:
    """Deterministic embedder: each unique text gets a fixed unit vector.
    Two inputs that share the same first token map to the same vector
    (cosine = 1.0) — perfect for triggering cache hits in tests."""

    def __init__(self) -> None:
        self._vecs: dict[str, np.ndarray] = {}

    def embed_query(self, text: str) -> list[float]:
        key = text.strip().split()[0].lower() if text.strip() else ""
        if key not in self._vecs:
            rng = np.random.default_rng(abs(hash(key)) % (2**32))
            v = rng.normal(size=64).astype(np.float32)
            v /= np.linalg.norm(v)
            self._vecs[key] = v
        return self._vecs[key].tolist()


@pytest.fixture
def fake_cache(monkeypatch):
    c = cache_module.SemanticCache(threshold=0.99)
    monkeypatch.setattr(c, "_embedder", lambda: _FakeEmbedder())
    return c


def test_cache_miss_returns_none_when_empty(fake_cache):
    with _flags(semantic_cache_enabled=True):
        assert fake_cache.lookup("balance please") is None


def test_cache_hit_on_paraphrase(fake_cache):
    """Same first token → same embedding → cosine=1 → above threshold."""
    with _flags(semantic_cache_enabled=True):
        fake_cache.store(
            "balance check please",
            {"answer": "47 EGP", "category": "INFO"},
        )
        hit = fake_cache.lookup("balance now")
    assert hit is not None
    assert hit["answer"] == "47 EGP"
    assert "_sim" in hit


def test_cache_skips_complaint(fake_cache):
    with _flags(semantic_cache_enabled=True):
        fake_cache.store(
            "internet broken now",
            {"answer": "sorry", "category": "COMPLAINT"},
        )
    assert fake_cache.lookup("internet please") is None


def test_cache_disabled_returns_none(fake_cache):
    with _flags(semantic_cache_enabled=False):
        fake_cache.store("x", {"answer": "y", "category": "INFO"})
        assert fake_cache.lookup("x") is None


# =========================== Tool agent ===========================


def test_get_balance_returns_seeded_customer(tmp_path):
    db = tmp_path / "crm.sqlite"
    with _flags(crm_db_path=db):
        result = tools_module.get_balance.invoke({"msisdn": "01012345678"})
    assert result["name"] == "Ahmed Hassan"
    assert result["credit_egp"] == pytest.approx(47.25)


def test_get_balance_normalises_international_format(tmp_path):
    db = tmp_path / "crm.sqlite"
    with _flags(crm_db_path=db):
        result = tools_module.get_balance.invoke({"msisdn": "+20 1012345678"})
    assert result.get("name") == "Ahmed Hassan"


def test_get_balance_missing_customer(tmp_path):
    db = tmp_path / "crm.sqlite"
    with _flags(crm_db_path=db):
        result = tools_module.get_balance.invoke({"msisdn": "01999999999"})
    assert "error" in result


def test_list_open_tickets_filters_by_status(tmp_path):
    db = tmp_path / "crm.sqlite"
    with _flags(crm_db_path=db):
        rows = tools_module.list_open_tickets.invoke({"account_id": "1004"})
    # 1004 only has TKT-2004 which is closed → list should be empty.
    assert rows == []


def test_escalate_creates_new_ticket(tmp_path):
    db = tmp_path / "crm.sqlite"
    with _flags(crm_db_path=db):
        new = tools_module.escalate_to_human.invoke(
            {"account_id": "1001", "reason": "test", "priority": "P2"}
        )
        # And it shows up on subsequent reads.
        rows = tools_module.list_open_tickets.invoke({"account_id": "1001"})
    assert new["ticket_id"].startswith("TKT-ESC-")
    assert any(r["ticket_id"] == new["ticket_id"] for r in rows)


def test_action_agent_node_disabled_returns_friendly_fallback():
    """Legacy `action_agent_node` (the nested-ReAct fallback) is still
    callable for backward compatibility. With the feature flag off it
    should produce a friendly text fallback rather than crashing."""
    with _flags(tool_agent_enabled=False):
        out = nodes_module.action_agent_node({"query": "balance please"})
    assert out["context_docs"] == []
    assert "tool" in out["answer"] or "تذكرة" in out["answer"]


def test_action_llm_node_disabled_returns_friendly_fallback():
    """The new outer-graph entry point should also short-circuit gracefully
    when the feature is disabled."""
    with _flags(tool_agent_enabled=False):
        out = nodes_module.action_llm_node({"query": "balance please"})
    assert out["context_docs"] == []
    assert out["messages"] == []
    assert "tool" in out["answer"] or "تذكرة" in out["answer"]


def test_action_llm_node_extracts_tool_history_on_final_answer():
    """When the LLM finishes (no more tool calls) the outer-graph node
    should populate `answer` AND extract a structured `tool_calls`
    history from prior messages — preserving the legacy /query
    response shape used by the Streamlit UI."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    # The outer-graph node binds tools then invokes — both calls must
    # work, so we mock the LLM as: get_llm() → mock; .bind_tools(...) →
    # mock_bound; .invoke(...) → final AIMessage.
    final_response = AIMessage(content="Your balance is 47 EGP.")
    bound = MagicMock()
    bound.invoke.return_value = final_response
    llm = MagicMock()
    llm.bind_tools.return_value = bound

    prior_msgs = [
        HumanMessage(content="check balance for 01012345678"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "tc1",
                    "name": "get_balance",
                    "args": {"msisdn": "01012345678"},
                }
            ],
        ),
        ToolMessage(
            content='{"name": "Ahmed Hassan", "credit_egp": 47.25}',
            tool_call_id="tc1",
        ),
    ]

    with _flags(tool_agent_enabled=True), patch.object(
        nodes_module, "get_llm", return_value=llm
    ):
        out = nodes_module.action_llm_node(
            {"query": "check balance for 01012345678", "messages": prior_msgs}
        )

    assert len(out["messages"]) == 1
    assert out["answer"] == "Your balance is 47 EGP."
    assert len(out["tool_calls"]) == 1
    assert out["tool_calls"][0]["name"] == "get_balance"
    assert out["tool_calls"][0]["data"] == {
        "name": "Ahmed Hassan",
        "credit_egp": 47.25,
    }


# =========================== Triad eval ===========================


def test_triad_split_sentences_strips_citation_markers():
    from src.triad_eval import _split_sentences

    text = "The cap is 100GB [1][2]. Reset on the 1st [3]!"
    sents = _split_sentences(text)
    assert all("[" not in s for s in sents)
    assert len(sents) == 2


def test_triad_safe_score_returns_neutral_on_failure():
    from src.triad_eval import _safe_score

    broken = MagicMock()
    broken.invoke.side_effect = RuntimeError("LLM down")
    assert _safe_score(broken, {}) == 0.5
