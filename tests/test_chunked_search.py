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


# ---------------------------------------------------------------------------
# Day 6: build_chunk_lexical_index / search_bm25_chunks - BM25 over chunks,
# the chunk-level counterpart to the semantic search above.
# ---------------------------------------------------------------------------


def test_build_chunk_lexical_index_indexes_title_plus_chunk_text():
    chunked_search = _load_chunked_search_module()
    chunks = _sample_chunks()

    index = chunked_search.build_chunk_lexical_index(chunks)

    # Both sample chunks share the title "Invoice mismatch handling", so
    # "invoice" should be indexed against both chunks - the same
    # title-inclusion behaviour `build_chunk_semantic_index` uses, applied to
    # the lexical index instead of the embedding input.
    assert index["inverted_index"]["invoice"] == {
        "SOP-002::chunk-0": 1,
        "SOP-002::chunk-1": 1,
    }
    assert index["document_frequency"]["invoice"] == 2
    # "price"/"variance" only appear in chunk-1's body text, not the shared
    # title, so they should not be indexed against chunk-0 at all.
    assert "SOP-002::chunk-0" not in index["inverted_index"]["variance"]
    assert index["chunk_count"] == 2
    assert index["chunk_lengths"]["SOP-002::chunk-0"] == 11
    assert index["average_chunk_length"] == pytest.approx(11.0)


def test_build_chunk_lexical_index_handles_no_chunks():
    chunked_search = _load_chunked_search_module()

    index = chunked_search.build_chunk_lexical_index([])

    assert index["chunk_count"] == 0
    assert index["average_chunk_length"] == 0.0


def test_search_bm25_chunks_ranks_by_bm25_score_and_traces_back_to_document():
    chunked_search = _load_chunked_search_module()
    index = chunked_search.build_chunk_lexical_index(_sample_chunks())

    # "price" and "variance" only appear in chunk-1's body - chunk-1 should
    # outrank chunk-0 even though both chunks share the query's other terms
    # via their common title.
    results = chunked_search.search_bm25_chunks(
        index, "price variance", top_k=2
    )

    assert results[0]["chunk_id"] == "SOP-002::chunk-1"
    assert results[0]["document_id"] == "SOP-002"
    assert results[0]["text"] == "A price variance over 3% requires buyer review."
    assert results[0]["score"] > 0


def test_search_bm25_chunks_handles_empty_unknown_and_limited_queries():
    chunked_search = _load_chunked_search_module()
    index = chunked_search.build_chunk_lexical_index(_sample_chunks())

    assert chunked_search.search_bm25_chunks(index, "") == []
    assert chunked_search.search_bm25_chunks(index, "zzzz-not-in-corpus") == []
    assert chunked_search.search_bm25_chunks(index, "invoice", top_k=0) == []
    assert len(chunked_search.search_bm25_chunks(index, "invoice", top_k=1)) == 1


def test_bm25_chunks_handles_an_empty_chunk_set():
    chunked_search = _load_chunked_search_module()
    index = chunked_search.build_chunk_lexical_index([])

    assert chunked_search.score_bm25_chunks(index, "invoice") == {}
    assert chunked_search.search_bm25_chunks(index, "invoice") == []
