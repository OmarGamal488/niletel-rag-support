---
title: NileTel RAG Customer Support
emoji: 📞
colorFrom: red
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Bilingual Arabic/English RAG support bot for NileTel
tags:
  - rag
  - langgraph
  - langchain
  - chromadb
  - bm25
  - arabic
  - egyptian-arabic
  - telecom
  - customer-support
  - fastapi
  - streamlit
  - dspy
  - n8n
  - iti
---

# NileTel RAG Customer Support — Hugging Face Space

A bilingual (Egyptian Arabic + English) Retrieval-Augmented Generation customer-support assistant for the fictional **NileTel** telecom.

- Routes queries into INFO / COMPLAINT / GREETING / OUT_OF_SCOPE
- Hybrid retrieval (ChromaDB + BM25 + Reciprocal Rank Fusion) over a 35-document knowledge base
- Generates grounded answers with inline citations
- Files complaints into a real n8n workflow (Google Sheets + Gmail + Telegram + duplicate detection)

**Author** — Omar Gamal ElKady · ITI Advanced AI Program · Intake 46 (May 2026)
**Repo** — <https://github.com/OmarGamal488/niletel-rag-support>

## Try it

Just type a question. Examples:

- `ليه النت بطيء أوي بعد تفعيل الـ FTTH؟`  *(why is my fiber slow?)*
- `How do I migrate from prepaid to postpaid?`
- `الـ 5G مش شغال على موبايلي`  *(5G not working)*
- `My internet is broken!`  *(triggers ticket flow)*

## Required Space Secrets

In **Settings → Repository secrets**, add at minimum:

| Key | Notes |
|---|---|
| `LIGHTNING_API_KEY` | or use a Groq/DeepSeek key instead |
| `LIGHTNING_BASE_URL` | `https://lightning.ai/api/v1/` |
| `LIGHTNING_MODEL` | e.g. `lightning-ai/deepseek-v4-pro` |
| `LLM_PROVIDER` | `lightning` (or `groq`, `deepseek`) |

Optional but recommended:

| Key | Purpose |
|---|---|
| `TAVILY_API_KEY` | web-search fallback when KB has no answer |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | LLM tracing |
| `N8N_WEBHOOK_URL` | ticket creation; omit to use the local fallback |

Toggles (all default sensibly if unset):

```
PII_REDACTION_ENABLED=true
CONTEXTUAL_RETRIEVAL=true
LONG_CONTEXT_REORDER=true
RERANKER_ENABLED=false
LANGFUSE_ENABLED=true
PROMETHEUS_ENABLED=false
```

## What runs inside the container

The Docker image starts two processes:

1. **FastAPI** on internal port `:8000` (LangGraph + retrieval + LLM)
2. **Streamlit** on the public port `:7860` (the chat UI Spaces exposes)

The KB index is built lazily on first boot from `data/raw/` if `data/chroma_db/` is missing, so the first request takes ~1–2 minutes while the bge-m3 embeddings are downloaded.

## License

MIT. Built for the ITI Advanced AI Program final project.
