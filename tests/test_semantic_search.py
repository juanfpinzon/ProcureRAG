import importlib.util
import sys
from pathlib import Path

import pytest


def _load_semantic_search_module():
    project_root = Path(__file__).resolve().parents[1]
    src_path = project_root / "src"

    # The learning modules are intentionally simple scripts instead of an
    # installed package. Add src to the import path while loading the module,
    # matching the import approach used by the existing retrieval tests.
    sys.path.insert(0, str(src_path))
    try:
        module_path = src_path / "semantic_search.py"
        spec = importlib.util.spec_from_file_location("semantic_search", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class FakeEmbeddingModel:
    """Deterministic stand-in for SentenceTransformer in unit tests."""

    def __init__(self, embeddings):
        self.embeddings = embeddings

    def encode(self, texts, *, normalize_embeddings, show_progress_bar):
        # The production code explicitly requests normalized vectors and turns
        # off progress output so the command-line demo stays easy to read.
        assert normalize_embeddings is True
        assert show_progress_bar is False
        return [self.embeddings[text] for text in texts]


def test_cosine_similarity_of_identical_vectors_is_one():
    semantic_search = _load_semantic_search_module()

    assert semantic_search.cosine_similarity([3, 4], [3, 4]) == pytest.approx(1.0)


def test_cosine_similarity_of_orthogonal_vectors_is_zero():
    semantic_search = _load_semantic_search_module()

    assert semantic_search.cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)


def test_cosine_similarity_returns_zero_when_either_vector_has_no_direction():
    semantic_search = _load_semantic_search_module()

    assert semantic_search.cosine_similarity([0, 0], [1, 2]) == 0.0
    assert semantic_search.cosine_similarity([0, 0], [0, 0]) == 0.0


def test_cosine_similarity_rejects_vectors_with_different_dimensions():
    semantic_search = _load_semantic_search_module()

    with pytest.raises(ValueError, match="same dimension"):
        semantic_search.cosine_similarity([1, 0], [1, 0, 0])


def test_build_semantic_index_reuses_preprocessed_title_and_text():
    semantic_search = _load_semantic_search_module()
    model = FakeEmbeddingModel(
        {"Supplier DPA GDPR applies.": [1.0, 0.0]}
    )

    index = semantic_search.build_semantic_index(
        [{"id": "DOC-1", "title": "Supplier DPA", "text": "GDPR applies."}],
        model,
    )

    assert index["documents"]["DOC-1"]["normalized_text"] == (
        "Supplier DPA GDPR applies."
    )
    assert index["embeddings"]["DOC-1"] == [1.0, 0.0]


def test_search_semantic_ranks_by_cosine_similarity_and_returns_result_shape():
    semantic_search = _load_semantic_search_module()
    model = FakeEmbeddingModel(
        {
            "Best document": [1.0, 0.0],
            "Second document": [0.8, 0.6],
            "Worst document": [0.0, 1.0],
            "vendor vetting": [1.0, 0.0],
        }
    )
    index = semantic_search.build_semantic_index(
        [
            {"id": "DOC-B", "title": "Best", "text": "document"},
            {"id": "DOC-C", "title": "Second", "text": "document"},
            {"id": "DOC-A", "title": "Worst", "text": "document"},
        ],
        model,
    )

    results = semantic_search.search_semantic(
        index, "vendor vetting", model, top_k=2
    )

    assert [result["id"] for result in results] == ["DOC-B", "DOC-C"]
    assert results[0]["score"] == pytest.approx(1.0)
    assert set(results[0]) == {"id", "score"}


def test_search_semantic_breaks_equal_scores_by_document_id():
    semantic_search = _load_semantic_search_module()
    model = FakeEmbeddingModel(
        {
            "Document B": [1.0, 0.0],
            "Document A": [1.0, 0.0],
            "query": [1.0, 0.0],
        }
    )
    index = semantic_search.build_semantic_index(
        [
            {"id": "DOC-B", "title": "Document", "text": "B"},
            {"id": "DOC-A", "title": "Document", "text": "A"},
        ],
        model,
    )

    results = semantic_search.search_semantic(index, "query", model, top_k=2)

    assert [result["id"] for result in results] == ["DOC-A", "DOC-B"]


def test_search_semantic_handles_empty_query_empty_index_and_non_positive_top_k():
    semantic_search = _load_semantic_search_module()
    model = FakeEmbeddingModel({"Document": [1.0, 0.0], "query": [1.0, 0.0]})
    index = semantic_search.build_semantic_index(
        [{"id": "DOC-1", "title": "", "text": "Document"}], model
    )

    assert semantic_search.search_semantic(index, "", model) == []
    assert semantic_search.search_semantic(index, "query", model, top_k=0) == []
    assert semantic_search.search_semantic({}, "query", model) == []

    empty_index = semantic_search.build_semantic_index([], model)
    assert semantic_search.search_semantic(empty_index, "query", model) == []
