import importlib.util
import math
import sys
from pathlib import Path

import pytest


def _load_retrieval_module():
    project_root = Path(__file__).resolve().parents[1]
    src_path = project_root / "src"

    # retrieval.py imports the sibling preprocessing module. Add src to the
    # import path only while loading it because this project intentionally
    # keeps its learning modules as simple scripts rather than a package.
    sys.path.insert(0, str(src_path))
    try:
        module_path = src_path / "retrieval.py"
        spec = importlib.util.spec_from_file_location("retrieval", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_build_index_stores_term_counts_and_document_frequency():
    retrieval = _load_retrieval_module()

    index = retrieval.build_index(
        [
            {"id": "DOC-1", "title": "", "text": "approval approval"},
            {"id": "DOC-2", "title": "", "text": "approval review"},
        ]
    )

    assert index["document_count"] == 2
    assert index["inverted_index"]["approval"] == {"DOC-1": 2, "DOC-2": 1}
    assert index["document_frequency"]["approval"] == 2
    assert index["document_lengths"] == {"DOC-1": 2, "DOC-2": 2}
    assert index["average_document_length"] == pytest.approx(2.0)


def test_score_query_uses_query_tf_document_tf_and_idf():
    retrieval = _load_retrieval_module()
    index = retrieval.build_index(
        [
            {"id": "DOC-1", "title": "", "text": "rare rare common"},
            {"id": "DOC-2", "title": "", "text": "common"},
        ]
    )

    scores = retrieval.score_query(index, "rare rare common")

    # rare has query TF=2, document TF=2, and IDF=log(2/1).
    assert scores["DOC-1"] == pytest.approx(4 * math.log(2))
    assert "DOC-2" not in scores


def test_score_query_bm25_applies_idf_saturation_and_document_length():
    retrieval = _load_retrieval_module()
    index = retrieval.build_index(
        [
            {"id": "DOC-1", "title": "", "text": "rare rare common"},
            {"id": "DOC-2", "title": "", "text": "common"},
        ]
    )

    scores = retrieval.score_query_bm25(index, "rare")

    # N=2 and df(rare)=1, so the positive BM25 IDF is log(2). The remaining
    # terms are the standard BM25 term-frequency and length-normalization
    # factors with k1=1.5, b=0.75, tf=2, and document length 3.
    expected_score = math.log(2) * (2 * 2.5) / (2 + 1.5 * 1.375)
    assert scores["DOC-1"] == pytest.approx(expected_score)
    assert "DOC-2" not in scores


def test_search_bm25_returns_expected_documents_for_procurement_queries():
    retrieval = _load_retrieval_module()
    index = retrieval.build_index(retrieval.load_data())

    expected_results = [
        (
            "Which SaaS suppliers need SOC 2 Type II or ISO 27001 evidence?",
            "POL-003",
        ),
        ("When can we skip the three-bid requirement?", "SOP-001"),
    ]

    for query, expected_id in expected_results:
        results = retrieval.search_bm25(index, query, top_k=1)
        assert results[0]["id"] == expected_id
        assert results[0]["score"] > 0


def test_search_returns_expected_documents_for_procurement_queries():
    retrieval = _load_retrieval_module()
    index = retrieval.build_index(retrieval.load_data())

    expected_results = [
        ("What approval is required for a €60,000 purchase order?", "POL-001"),
        (
            "Which SaaS suppliers need SOC 2 Type II or ISO 27001 evidence?",
            "POL-003",
        ),
        ("When can we skip the three-bid requirement?", "SOP-001"),
    ]

    for query, expected_id in expected_results:
        results = retrieval.search(index, query, top_k=1)
        assert results[0]["id"] == expected_id
        assert results[0]["score"] > 0


def test_search_handles_empty_unknown_and_limited_queries():
    retrieval = _load_retrieval_module()
    index = retrieval.build_index(retrieval.load_data())

    assert retrieval.search(index, "") == []
    assert retrieval.search(index, "zzzz-not-in-corpus") == []
    assert retrieval.search(index, "approval", top_k=0) == []
    assert len(retrieval.search(index, "approval", top_k=2)) == 2


def test_search_bm25_handles_empty_unknown_and_limited_queries():
    retrieval = _load_retrieval_module()
    index = retrieval.build_index(retrieval.load_data())

    assert retrieval.search_bm25(index, "") == []
    assert retrieval.search_bm25(index, "zzzz-not-in-corpus") == []
    assert retrieval.search_bm25(index, "approval", top_k=0) == []
    assert len(retrieval.search_bm25(index, "approval", top_k=2)) == 2


def test_bm25_handles_an_empty_corpus():
    retrieval = _load_retrieval_module()
    index = retrieval.build_index([])

    assert index["average_document_length"] == 0.0
    assert retrieval.score_query_bm25(index, "approval") == {}
    assert retrieval.search_bm25(index, "approval") == []


def test_search_breaks_score_ties_by_document_id():
    retrieval = _load_retrieval_module()
    index = retrieval.build_index(
        [
            {"id": "DOC-B", "title": "", "text": "shared"},
            {"id": "DOC-A", "title": "", "text": "shared"},
            {"id": "DOC-C", "title": "", "text": "different"},
        ]
    )

    results = retrieval.search(index, "shared", top_k=2)

    assert [result["id"] for result in results] == ["DOC-A", "DOC-B"]


def test_search_bm25_breaks_score_ties_by_document_id():
    retrieval = _load_retrieval_module()
    index = retrieval.build_index(
        [
            {"id": "DOC-B", "title": "", "text": "shared"},
            {"id": "DOC-A", "title": "", "text": "shared"},
            {"id": "DOC-C", "title": "", "text": "different"},
        ]
    )

    results = retrieval.search_bm25(index, "shared", top_k=2)

    assert [result["id"] for result in results] == ["DOC-A", "DOC-B"]
