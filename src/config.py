from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Lightning AI hosts DeepSeek V4 Pro over an OpenAI-compatible endpoint.
    # Kept as a single-value literal so an accidental override in the env
    # surfaces as a validation error instead of silently breaking get_llm().
    llm_provider: Literal["lightning"] = "lightning"

    lightning_api_key: str = ""
    lightning_base_url: str = ""
    lightning_model: str = ""

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "niletel-rag-support"

    # ---- Langfuse (LLM observability) ----
    # Sign up at cloud.langfuse.com or self-host. With both keys populated,
    # every LangGraph invocation is traced (per-node spans, prompts, latency,
    # token cost). Falls back to a no-op handler when keys are missing.
    langfuse_enabled: bool = True
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"  # EU; use us.cloud.langfuse.com for US

    # ---- Prometheus metrics ----
    # Adds a `/metrics` endpoint in OpenMetrics text format for Prometheus
    # to scrape. The old JSON dashboard summary moves to `/stats`.
    prometheus_enabled: bool = True

    n8n_webhook_url: str = ""

    data_dir: Path = Path("./data/raw")
    chroma_dir: Path = Path("./data/chroma_db")
    bm25_path: Path = Path("./data/bm25_index.pkl")

    # Embedding model — bge-m3 is multilingual (incl. Arabic), 1024-dim, 8k ctx.
    # Re-run `python -m src.ingestion` after changing this — the Chroma index
    # is dim-specific.
    embedding_model: str = "BAAI/bge-m3"
    chunk_size: int = 500
    chunk_overlap: int = 80
    top_k: int = 4

    # Retrieval mode:
    #   "hybrid"     — dense + BM25 + RRF (default)
    #   "hyde"       — LLM-generated hypothetical doc as the dense query
    #   "rag_fusion" — LLM generates N paraphrases; each runs hybrid retrieval;
    #                  all result lists RRF-fused
    #                  (Rackauckas, RAG-Fusion 2024, arXiv:2402.03367)
    retrieval_mode: Literal["hybrid", "hyde", "rag_fusion"] = "hybrid"

    # Number of query variations used in rag_fusion mode (including the
    # original). 4 is the paper's sweet spot — enough diversity without
    # blowing up retrieval cost.
    rag_fusion_num_queries: int = 4

    # ---- Two-stage retrieval (wide pool → cross-encoder rerank → top-k) ----
    # Wider pool gives the reranker room to fix lexical-vs-semantic mismatches.
    retriever_top_n: int = 20
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # Lost-in-the-Middle mitigation: place strongest chunks at the ends of
    # the context window where the LLM attends most.
    long_context_reorder: bool = True

    # ---- Tier 2: ALCE inline citations ----
    # Force `[N]` markers in generated answers and parse them out into a
    # structured `citations` field. Off → answer is free-form prose.
    citations_enabled: bool = True

    # ---- Tier 2: Chain-of-Verification (CoVe) ----
    # 3-step verify-then-revise on INFO answers. Doubles LLM cost; off by
    # default. Toggle in the demo to show the hallucination-mitigation slide.
    chain_of_verification: bool = False

    # ---- Tier 2: Corrective RAG (CRAG) ----
    # Evaluate retrieved docs before generating. On `incorrect`, optionally
    # fall back to web search (Tavily); on `ambiguous`, add a hedging note;
    # on `correct`, proceed normally.
    crag_enabled: bool = False
    tavily_api_key: str = ""

    # ---- Tier 2: Contextual Retrieval (Anthropic, Sep 2024) ----
    # Pre-process each chunk at ingestion time by prepending a 1-sentence
    # LLM-generated summary situating it in its source doc. Re-run ingestion
    # after toggling this on.
    contextual_retrieval: bool = False

    # ---- Tier 3: PII redaction (Presidio-style) ----
    # Strip phone numbers, national IDs, emails, IBANs from queries before
    # they hit the LLM; restore them in the final answer.
    pii_redaction_enabled: bool = True

    # ---- Tier 3: Semantic cache (GPTCache-style) ----
    # Vector-similarity cache in front of the graph. On hit, the cached
    # answer is returned and the LLM is never called.
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.92
    semantic_cache_max_entries: int = 256

    # ---- Tier 3: Tool-calling ReAct agent ----
    # Adds an ACTION category to the router that hits a tools-equipped
    # agent (lookup balance, list tickets, escalate). Tools are backed by
    # the SQLite file at `crm_db_path` (auto-seeded on first use).
    tool_agent_enabled: bool = True
    crm_db_path: Path = Path("./data/fake_crm.sqlite")

    # ---- Tier 3: TruLens-style RAG Triad eval ----
    # Three feedback functions (context relevance, groundedness, answer
    # relevance) computed alongside RAGAS. Output goes to
    # `eval/triad_report.json`.
    triad_eval_enabled: bool = True


settings = Settings()
