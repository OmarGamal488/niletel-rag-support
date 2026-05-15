"""Router classification tests using a mocked LLM."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src import router as router_module
from src.router import RouteDecision, classify


def _mock_llm_returning(category: str, confidence: float = 0.95):
    structured = MagicMock()
    structured.invoke.return_value = RouteDecision(
        category=category, confidence=confidence, reason="mock"
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def test_classify_info():
    with patch.object(router_module, "get_llm", return_value=_mock_llm_returning("INFO")):
        out = classify("ليه النت بطيء؟")
    assert out.category == "INFO"


def test_classify_complaint():
    with patch.object(
        router_module, "get_llm", return_value=_mock_llm_returning("COMPLAINT")
    ):
        out = classify("الانترنت مش شغال خالص!")
    assert out.category == "COMPLAINT"


def test_classify_greeting():
    with patch.object(
        router_module, "get_llm", return_value=_mock_llm_returning("GREETING")
    ):
        out = classify("مرحبا")
    assert out.category == "GREETING"


def test_classify_out_of_scope():
    with patch.object(
        router_module, "get_llm", return_value=_mock_llm_returning("OUT_OF_SCOPE")
    ):
        out = classify("What is 2+2?")
    assert out.category == "OUT_OF_SCOPE"
