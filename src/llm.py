"""LLM factory — Lightning AI inference (DeepSeek V4 Pro).

Lightning exposes an OpenAI-compatible chat completions API at
`LIGHTNING_BASE_URL`, so a single LangChain `ChatOpenAI` client handles
it. The model is whatever `LIGHTNING_MODEL` points at — in this project,
`lightning-ai/deepseek-v4-pro`.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from src.config import settings


def _resolve() -> tuple[str, str, str]:
    if not settings.lightning_base_url or not settings.lightning_model:
        raise ValueError(
            "Lightning AI requires LIGHTNING_BASE_URL and LIGHTNING_MODEL in .env"
        )
    return (
        settings.lightning_api_key,
        settings.lightning_base_url,
        settings.lightning_model,
    )


@lru_cache(maxsize=1)
def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    api_key, base_url, model = _resolve()
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )
