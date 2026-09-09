import importlib.util
import sys
from pathlib import Path

import pytest


def _load_chunked_search_module():
    project_root = Path(__file__).resolve().parents[1]
    src_path = project_root / "src"

    # chunked_search.py imports its sibling modules (chunking, semantic_search)
    # by their bare names, so src must be importable while it loads - same
    # approach the other test files use.
    sys.path.insert(0, str(src_path))
    try:
        module_path = src_path / "chunked_search.py"
        spec = importlib.util.spec_from_file_location("chunked_search", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class FakeEmbeddingModel:
    """Deterministic stand-in for SentenceTransformer, same as the Day 4 tests."""

    def __init__(self, embeddings):
        self.embeddings = embeddings

    def encode(self, texts, *, normalize_embeddings, show_progress_bar):
        assert normalize_embeddings is True
        assert show_progress_bar is False
        return [self.embeddings[text] for text in texts]


def _sample_chunks():
    return [
        {
            "chunk_id": "SOP-002::chunk-0",
            "document_id": "SOP-002",
            "chunk_index": 0,
            "text": "Invoices are matched against purchase order and pricing.",
            "title": "Invoice mismatch handling",
        },
        {
            "chunk_id": "SOP-002::chunk-1",
            "document_id": "SOP-002",
            "chunk_index": 1,
            "text": "A price variance over 3% requires buyer review.",
            "title": "Invoice mismatch handling",
        },
    ]


def test_build_chunk_semantic_index_embeds_title_plus_chunk_text():
    chunked_search = _load_chunked_search_module()
    chunks = _sample_chunks()
    model = FakeEmbeddingModel(
        {
            # The embedding input is "title + chunk text", matching how whole
            # documents are embedded in semantic_search.py - not the bare
            # chunk text. That's the fix for the title-vs-no-title confound.
            "Invoice mismatch handling Invoices are matched against purchase "
            "order and pricing.": [1.0, 0.0],
            "Invoice mismatch handling A price variance over 3% requires "
            "buyer review.": [0.0, 1.0],
        }
    )

    index = chunked_search.build_chunk_semantic_index(chunks, model)

    assert index["embeddings"]["SOP-002::chunk-1"] == [0.0, 1.0]
    assert index["chunks"]["SOP-002::chunk-1"]["document_id"] == "SOP-002"
    # The stored/returned chunk text itself stays title-free - only the
    # embedding input got the title prefix.
    assert (
        index["chunks"]["SOP-002::chunk-1"]["text"]
        == "A price variance over 3% requires buyer review."
    )


def test_build_chunk_semantic_index_handles_no_chunks():
    chunked_search = _load_chunked_search_module()
    model = FakeEmbeddingModel({})

    assert chunked_search.build_chunk_semantic_index([], model) == {
        "chunks": {},
        "embeddings": {},
    }


def test_search_semantic_chunks_ranks_by_cosine_and_traces_back_to_document():
    chunked_search = _load_chunked_search_module()
    chunks = _sample_chunks()
    model = FakeEmbeddingModel(
        {
            "Invoice mismatch handling Invoices are matched against purchase "
            "order and pricing.": [1.0, 0.0],
            "Invoice mismatch handling A price variance over 3% requires "
            "buyer review.": [0.0, 1.0],
            # The query itself is embedded as-is (no title to prefix).
            "What happens when invoice price variance is over 3%?": [0.0, 1.0],
        }
    )
    index = chunked_search.build_chunk_semantic_index(chunks, model)

    results = chunked_search.search_semantic_chunks(
        index, "What happens when invoice price variance is over 3%?", model, top_k=1
    )

    assert results[0]["chunk_id"] == "SOP-002::chunk-1"
    assert results[0]["document_id"] == "SOP-002"
    assert results[0]["text"] == "A price variance over 3% requires buyer review."
    assert results[0]["score"] == pytest.approx(1.0)


def test_search_semantic_chunks_handles_empty_query_and_non_positive_top_k():
    chunked_search = _load_chunked_search_module()
    chunks = _sample_chunks()
    model = FakeEmbeddingModel(
        {
            "Invoice mismatch handling Invoices are matched against purchase "
            "order and pricing.": [1.0, 0.0],
            "Invoice mismatch handling A price variance over 3% requires "
            "buyer review.": [0.0, 1.0],
        }
    )
    index = chunked_search.build_chunk_semantic_index(chunks, model)

    assert chunked_search.search_semantic_chunks(index, "", model) == []
    assert (
        chunked_search.search_semantic_chunks(index, "query", model, top_k=0) == []
    )
    assert chunked_search.search_semantic_chunks({}, "query", model) == []
