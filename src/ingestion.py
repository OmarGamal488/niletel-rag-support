"""Load Markdown KB, chunk, optionally contextualise, build ChromaDB + BM25.

Tier 2 add-on: when `settings.contextual_retrieval` is True, each chunk is
prefixed with a 1-sentence LLM-generated summary that situates it inside
its parent document (Anthropic's "Contextual Retrieval", Sep 2024). The
augmented chunk is what gets embedded *and* what BM25 indexes — both legs
of the hybrid retriever benefit. The original `page_content` is preserved
in `metadata["raw"]` so downstream code can still display the unaltered
text to users.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

from src.config import settings

logger = logging.getLogger(__name__)


# ----------------------------------------------------- Load + chunk ----

def load_documents(data_dir: Path) -> list[Document]:
    loader = DirectoryLoader(
        str(data_dir),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=True,
    )
    docs = loader.load()
    for d in docs:
        d.metadata["source"] = Path(d.metadata.get("source", "")).name
    return docs


def chunk_documents(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )
    return splitter.split_documents(docs)


# ----------------------------------------- Contextual Retrieval (#4) ----

_CONTEXT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You write retrieval context prefixes. Given the full document "
            "and one of its chunks, produce ONE short sentence (max 25 words) "
            "that situates the chunk inside the document so it makes sense "
            "out of context. Mirror the language of the chunk (Arabic / "
            "English / mixed). Reply with only the sentence — no preamble.",
        ),
        (
            "human",
            "<document>\n{document}\n</document>\n\n"
            "<chunk>\n{chunk}\n</chunk>\n\n"
            "Context sentence:",
        ),
    ]
)


def _contextualise_one(
    chain, document: str, chunk_text: str, *, max_retries: int = 4
) -> str:
    """Single LLM call with exponential backoff for rate-limited providers."""
    import time

    delay = 1.0
    for attempt in range(max_retries):
        try:
            ctx_msg = chain.invoke({"document": document, "chunk": chunk_text})
            return (ctx_msg.content or "").strip().splitlines()[0][:200]
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            transient = (
                "rate" in msg
                or "429" in msg
                or "timeout" in msg
                or "503" in msg
                or "overload" in msg
            )
            if attempt == max_retries - 1 or not transient:
                raise
            time.sleep(delay)
            delay *= 2  # 1s → 2s → 4s → 8s
    return ""  # unreachable


def _contextualise_chunks(
    chunks: list[Document],
    full_docs: dict[str, str],
    throttle_per_sec: float = 2.0,
) -> list[Document]:
    """Prefix each chunk with an LLM-generated 1-sentence context line
    (Anthropic Contextual Retrieval, Sep 2024).

    `throttle_per_sec` keeps the call rate below the provider's limit —
    Lightning AI in this repo allows ~4 RPS, so 2 is a safe default. Bump
    via env if your provider is more generous.
    """
    import time

    from src.llm import get_llm

    llm = get_llm(temperature=0.0)
    chain = _CONTEXT_PROMPT | llm
    out: list[Document] = []
    n = len(chunks)
    min_interval = 1.0 / max(throttle_per_sec, 0.1)
    last_call = 0.0
    failures = 0

    for i, chunk in enumerate(chunks, start=1):
        # Throttle to stay under the provider's rate limit.
        elapsed = time.perf_counter() - last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        source = chunk.metadata.get("source", "")
        document_trunc = full_docs.get(source, "")[:6000]
        ctx = ""
        try:
            ctx = _contextualise_one(chain, document_trunc, chunk.page_content)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            logger.warning(
                "Contextualisation failed for chunk %d/%d (%s): %s — using raw.",
                i, n, source, exc.__class__.__name__,
            )
        last_call = time.perf_counter()

        page_content = (
            f"{ctx}\n\n{chunk.page_content}" if ctx else chunk.page_content
        )
        new_meta = {**chunk.metadata, "raw": chunk.page_content, "context": ctx}
        out.append(Document(page_content=page_content, metadata=new_meta))

        if i % 10 == 0 or i == n:
            print(f"  ...contextualised {i} / {n} chunks", flush=True)

    if failures:
        print(
            f"  NOTE: {failures}/{n} chunks fell back to raw (rate limits "
            "or transient errors). Re-run to retry only those if needed."
        )
    return out


# ------------------------------------------------------- Index builds ----

def build_chroma(chunks: list[Document]) -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(settings.chroma_dir),
        collection_name="niletel_kb",
    )


def build_bm25(chunks: list[Document]) -> None:
    tokenised = [c.page_content.split() for c in chunks]
    bm25 = BM25Okapi(tokenised)
    payload = {"bm25": bm25, "chunks": chunks}
    settings.bm25_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.bm25_path.open("wb") as f:
        pickle.dump(payload, f)


# -------------------------------------------------------- Entrypoint ----

def main() -> None:
    print(f"Loading docs from {settings.data_dir}...")
    docs = load_documents(settings.data_dir)
    print(f"  -> {len(docs)} documents loaded")

    print(f"Chunking (size={settings.chunk_size}, overlap={settings.chunk_overlap})...")
    chunks = chunk_documents(docs)
    print(f"  -> {len(chunks)} chunks")

    if settings.contextual_retrieval:
        print(
            f"Contextualising {len(chunks)} chunks via {settings.llm_provider} "
            f"(one LLM call per chunk — be patient)..."
        )
        full_docs = {Path(d.metadata["source"]).name: d.page_content for d in docs}
        chunks = _contextualise_chunks(chunks, full_docs)
        print("  -> chunks contextualised")
    else:
        print("Contextual retrieval is OFF — using raw chunks.")

    print(f"Building ChromaDB at {settings.chroma_dir}...")
    build_chroma(chunks)
    print("  -> ChromaDB persisted")

    print(f"Building BM25 index at {settings.bm25_path}...")
    build_bm25(chunks)
    print("  -> BM25 pickled")

    print("Ingestion complete.")


if __name__ == "__main__":
    main()
