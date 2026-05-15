"""LLM factory — swap providers via the LLM_PROVIDER env var.

All three providers expose an OpenAI-compatible chat completions API,
so a single ChatOpenAI client (with the right base_url) handles them.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from src.config import settings

PROVIDER_DEFAULTS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.1-70b-versatile",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "lightning": {
        "base_url": None,  # user must set LIGHTNING_BASE_URL
        "default_model": None,  # user must set LIGHTNING_MODEL
    },
}


def _resolve() -> tuple[str, str, str]:
    p = settings.llm_provider
    if p == "groq":
        return (
            settings.groq_api_key,
            PROVIDER_DEFAULTS["groq"]["base_url"],
            settings.llm_model or PROVIDER_DEFAULTS["groq"]["default_model"],
        )
    if p == "deepseek":
        return (
            settings.deepseek_api_key,
            PROVIDER_DEFAULTS["deepseek"]["base_url"],
            settings.llm_model or PROVIDER_DEFAULTS["deepseek"]["default_model"],
        )
    if p == "lightning":
        if not settings.lightning_base_url or not settings.lightning_model:
            raise ValueError(
                "Lightning AI requires LIGHTNING_BASE_URL and LIGHTNING_MODEL in .env"
            )
        return (
            settings.lightning_api_key,
            settings.lightning_base_url,
            settings.lightning_model,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {p}")


@lru_cache(maxsize=1)
def get_llm(temperature: float = 0.2) -> ChatOpenAI:
    api_key, base_url, model = _resolve()
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )
