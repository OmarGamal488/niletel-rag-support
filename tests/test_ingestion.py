"""Smoke tests for ingestion: loading + chunking quality."""

from __future__ import annotations

from src.config import settings
from src.ingestion import chunk_documents, load_documents


def test_load_documents_finds_kb():
    docs = load_documents(settings.data_dir)
    assert len(docs) >= 30, f"Expected 30+ KB docs, got {len(docs)}"
    assert all(d.metadata.get("source", "").endswith(".md") for d in docs)


def test_chunking_produces_reasonable_sizes():
    docs = load_documents(settings.data_dir)
    chunks = chunk_documents(docs)
    assert len(chunks) > len(docs)
    sizes = [len(c.page_content) for c in chunks]
    assert max(sizes) <= settings.chunk_size * 4
    assert min(sizes) > 0
