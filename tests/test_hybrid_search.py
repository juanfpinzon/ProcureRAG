import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module(module_name):
    """Load a `src/<module_name>.py` script the same way the other test
    files do: the project keeps its learning modules as plain scripts rather
    than an installed package, so `src` is added to the import path only
    while the module loads.
    """
    project_root = Path(__file__).resolve().parents[1]
    src_path = project_root / "src"

    sys.path.insert(0, str(src_path))
    try:
        module_path = src_path / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def _load_hybrid_search_module():
    return _load_module("hybrid_search")


# ---------------------------------------------------------------------------
# min_max_normalize
# ---------------------------------------------------------------------------


def test_min_max_normalize_scales_scores_to_zero_one_range():
    hybrid_search = _load_hybrid_search_module()

    normalized = hybrid_search.min_max_normalize(
        {"DOC-A": 10.0, "DOC-B": 6.0, "DOC-C": 2.0}
    )

    # The lowest raw score maps to 0.0, the highest to 1.0, and the middle
    # score sits proportionally in between - the definition of min-max
    # normalization, independent of what the original scale was.
    assert normalized["DOC-A"] == pytest.approx(1.0)
    assert normalized["DOC-B"] == pytest.approx(0.5)
    assert normalized["DOC-C"] == pytest.approx(0.0)


def test_min_max_normalize_handles_equal_scores_and_empty_input():
    hybrid_search = _load_hybrid_search_module()

    # Every score identical means there's no spread to normalize against -
    # (score - minimum) / (maximum - minimum) would divide by zero, so every
    # score maps to 0.0 instead.
    assert hybrid_search.min_max_normalize({"DOC-A": 5.0, "DOC-B": 5.0}) == {
        "DOC-A": 0.0,
        "DOC-B": 0.0,
    }
    assert hybrid_search.min_max_normalize({}) == {}


# ---------------------------------------------------------------------------
# HybridSearch.rrf / HybridSearch.weighted - formula checks
# ---------------------------------------------------------------------------


def test_rrf_combines_rank_positions_not_raw_scores():
    hybrid_search = _load_hybrid_search_module()

    # DOC-C is missing from the semantic list entirely - a realistic case
    # (dense retrieval's top-k simply didn't include it), and RRF should
    # still rank it using only its BM25 term instead of failing or dropping
    # it.
    bm25_results = [
        {"id": "DOC-A", "score": 5.0},
        {"id": "DOC-B", "score": 3.0},
        {"id": "DOC-C", "score": 1.0},
    ]
    semantic_results = [
        {"id": "DOC-C", "score": 0.9},
        {"id": "DOC-A", "score": 0.5},
    ]

    hybrid = hybrid_search.HybridSearch(bm25_results, semantic_results)
    results = hybrid.rrf(k=60, top_k=3)
    scores_by_id = {result["id"]: result["score"] for result in results}

    # rrf_score(d) = 1/(k + rank_bm25(d)) + 1/(k + rank_semantic(d)).
    # DOC-A: bm25 rank 1, semantic rank 2. DOC-C: bm25 rank 3, semantic
    # rank 1. DOC-B: bm25 rank 2, no semantic term at all.
    assert scores_by_id["DOC-A"] == pytest.approx(1 / 61 + 1 / 62)
    assert scores_by_id["DOC-C"] == pytest.approx(1 / 63 + 1 / 61)
    assert scores_by_id["DOC-B"] == pytest.approx(1 / 62)

    # DOC-A's raw BM25 score (5.0) is the highest of the three, but that
    # plays no role in RRF - only rank position does. DOC-A still wins here,
    # but for the right reason: rank 1 + rank 2 beats rank 3 + rank 1.
    assert [result["id"] for result in results] == ["DOC-A", "DOC-C", "DOC-B"]

    # Per-method raw scores are preserved for debugging, and a missing side
    # reports None rather than 0.0 - 0.0 would be indistinguishable from a
    # genuinely low score.
    doc_b = next(result for result in results if result["id"] == "DOC-B")
    assert doc_b["bm25_score"] == 3.0
    assert doc_b["semantic_score"] is None


def test_weighted_blends_normalized_scores_with_alpha():
    hybrid_search = _load_hybrid_search_module()

    bm25_results = [
        {"id": "DOC-A", "score": 10.0},
        {"id": "DOC-B", "score": 6.0},
        {"id": "DOC-C", "score": 2.0},
    ]
    semantic_results = [
        {"id": "DOC-B", "score": 0.8},
        {"id": "DOC-A", "score": 0.2},
    ]

    hybrid = hybrid_search.HybridSearch(bm25_results, semantic_results)
    results = hybrid.weighted(alpha=0.5, top_k=3)
    scores_by_id = {result["id"]: result["score"] for result in results}

    # Lexical normalized: DOC-A=1.0, DOC-B=0.5, DOC-C=0.0 (min=2, max=10).
    # Semantic normalized: DOC-B=1.0, DOC-A=0.0 (min=0.2, max=0.8); DOC-C is
    # missing from the semantic list, so it defaults to 0.0 there too.
    # hybrid_score = 0.5 * semantic_normalized + 0.5 * lexical_normalized.
    assert scores_by_id["DOC-A"] == pytest.approx(0.5 * 0.0 + 0.5 * 1.0)
    assert scores_by_id["DOC-B"] == pytest.approx(0.5 * 1.0 + 0.5 * 0.5)
    assert scores_by_id["DOC-C"] == pytest.approx(0.5 * 0.0 + 0.5 * 0.0)
    assert [result["id"] for result in results] == ["DOC-B", "DOC-A", "DOC-C"]


def test_weighted_alpha_extremes_degrade_to_single_method_rankings():
    """Acceptance criterion: alpha=1.0 degrades to semantic-only; alpha=0.0
    degrades to lexical-only.

    Min-max normalization is a strictly increasing transform of the raw
    scores (it only rescales, never reorders), so multiplying the *other*
    side's normalized score by zero should reproduce that single retriever's
    own ranking exactly.
    """
    hybrid_search = _load_hybrid_search_module()

    bm25_results = [
        {"id": "DOC-A", "score": 12.0},
        {"id": "DOC-B", "score": 8.0},
        {"id": "DOC-C", "score": 1.0},
    ]
    semantic_results = [
        {"id": "DOC-C", "score": 0.9},
        {"id": "DOC-B", "score": 0.5},
        {"id": "DOC-A", "score": 0.1},
    ]

    hybrid = hybrid_search.HybridSearch(bm25_results, semantic_results)

    lexical_only_ranking = [
        result["id"] for result in hybrid.weighted(alpha=0.0, top_k=3)
    ]
    assert lexical_only_ranking == ["DOC-A", "DOC-B", "DOC-C"]

    semantic_only_ranking = [
        result["id"] for result in hybrid.weighted(alpha=1.0, top_k=3)
    ]
    assert semantic_only_ranking == ["DOC-C", "DOC-B", "DOC-A"]


# ---------------------------------------------------------------------------
# Acceptance criteria from docs/day-06-hybrid-search-foundations.md
# ---------------------------------------------------------------------------


def test_hybrid_beats_both_single_methods_on_an_identifier_plus_paraphrase_query():
    """Hybrid beats both lexical-only and semantic-only on a procurement
    query with an exact identifier.

    Built by hand rather than pulled from a live run: on the actual 34-
    document v1 corpus, every query in `semantic_search.COMPARISON_CASES`
    already has at least one single method landing on the right top-1
    document (see the Day 6 learning log), so this corpus doesn't happen to
    produce a case where *both* methods fail on the same query. This example
    reproduces the general failure mode the Day 6 doc describes instead: a
    query that names a specific PO number *and* paraphrases what it's asking
    ("approval sign-off"). BM25 gets distracted by a different PO record that
    happens to share more boilerplate policy language; semantic search gets
    distracted by an FAQ that paraphrases the question closely but never
    mentions the PO number at all. The actually-correct record is the
    runner-up in both lists - not first in either - which is exactly the
    shape of result RRF is good at recovering.
    """
    hybrid_search = _load_hybrid_search_module()

    # query: "What approval sign-off does PO-2024-0451 need?"
    bm25_results = [
        {"id": "PO-2024-9999", "score": 12.0},  # wrong PO, shares boilerplate
        {"id": "PO-2024-0451", "score": 9.0},  # the correct record
        {"id": "FAQ-GENERAL", "score": 5.0},
        {"id": "FAQ-APPROVALS", "score": 1.0},
    ]
    semantic_results = [
        {"id": "FAQ-APPROVALS", "score": 0.90},  # closest paraphrase, wrong doc
        {"id": "PO-2024-0451", "score": 0.85},  # the correct record
        {"id": "FAQ-GENERAL", "score": 0.40},
        {"id": "PO-2024-9999", "score": 0.10},
    ]

    assert bm25_results[0]["id"] != "PO-2024-0451"
    assert semantic_results[0]["id"] != "PO-2024-0451"

    hybrid = hybrid_search.HybridSearch(bm25_results, semantic_results)

    assert hybrid.rrf(top_k=1)[0]["id"] == "PO-2024-0451"
    assert hybrid.weighted(top_k=1)[0]["id"] == "PO-2024-0451"


def test_rrf_and_weighted_agree_on_top1_on_v1_corpus():
    """RRF and weighted combination produce consistent top-1 results on the
    v1 corpus.

    BM25 is computed live against the real `data/corpus_v1` corpus - it's
    pure Python with no model to load, so there's no reason to freeze it.
    The semantic scores are frozen from an actual run of the cached
    `sentence-transformers/multi-qa-MiniLM-L6-cos-v1` model against the same
    query and corpus (see `src/hybrid_search.py`'s `main()`), so this test
    doesn't need to load a model itself.
    """
    hybrid_search = _load_hybrid_search_module()
    retrieval = _load_module("retrieval")

    query = "What happens when invoice price variance is over 3%?"
    corpus = retrieval.load_data()

    # This test's frozen semantic scores below were captured against a
    # specific snapshot of the corpus (34 documents, 2026-09-10). They don't
    # get silently re-validated by anything else in this file, so a change
    # to `data/corpus_v1` (a document added/removed/reworded) could make
    # them stale without any test failing to say so - this guard at least
    # catches a document being added or removed. It would *not* catch a
    # document's text being edited in place; re-run `src/hybrid_search.py`'s
    # `main()` and refresh the frozen scores below if that ever happens.
    assert len(corpus) == 34, (
        "data/corpus_v1 document count changed - the frozen semantic scores "
        "below may be stale. Re-run `./.venv/bin/python src/hybrid_search.py` "
        "and refresh them."
    )

    bm25_index = retrieval.build_index(corpus)
    bm25_results = retrieval.search_bm25(bm25_index, query, top_k=3)

    # BM25 alone gets this wrong: FAQ-002 mentions "variance" and "3%" too,
    # and outranks the document that actually states the rule.
    assert bm25_results[0]["id"] == "FAQ-002"

    # Captured 2026-09-10 from a real run of the cached
    # sentence-transformers/multi-qa-MiniLM-L6-cos-v1 model against the query
    # above and the full v1 corpus (see docs/learning-log.md's Day 6 entry).
    semantic_results = [
        {"id": "SOP-002", "score": 0.47533282773384916},
        {"id": "CONTRACT-003", "score": 0.27717761715340944},
        {"id": "POL-007", "score": 0.2336207053781623},
    ]

    hybrid = hybrid_search.HybridSearch(bm25_results, semantic_results)

    rrf_top1 = hybrid.rrf(top_k=1)[0]["id"]
    weighted_top1 = hybrid.weighted(top_k=1)[0]["id"]

    # Rank-only fusion (RRF) and normalized-score blending (weighted) are
    # mathematically unrelated, but both recover the correct document here
    # and agree with each other.
    assert rrf_top1 == weighted_top1 == "SOP-002"


def test_rrf_k_parameter_changes_lower_rank_order_but_not_top1_on_v1_corpus():
    """The k parameter in RRF affects tie-breaking but not top-1 on the v1
    corpus.

    Same real-BM25-live / real-semantic-frozen approach as the test above,
    for a query where two *lower-ranked* documents (not the top-1) swap
    places depending on k. A small k (1) weighs a document's best rank
    heavily; a large k (60, the default) cares more about the *sum* of a
    document's ranks across both lists. CONTRACT-006 has one great rank (2nd
    in semantic) and one poor one (6th in BM25); POL-003 is consistently
    mid-table (3rd and 4th). Small k rewards CONTRACT-006's one great rank;
    large k rewards POL-003's better total.
    """
    hybrid_search = _load_hybrid_search_module()
    retrieval = _load_module("retrieval")

    query = "Can Northstar use company data for model training?"
    corpus = retrieval.load_data()

    # Same corpus-drift guard as `test_rrf_and_weighted_agree_on_top1_on_v1_corpus`
    # above - catches the frozen semantic scores below going stale because a
    # document was added or removed, though not because one was edited in
    # place.
    assert len(corpus) == 34, (
        "data/corpus_v1 document count changed - the frozen semantic scores "
        "below may be stale. Re-run `./.venv/bin/python src/hybrid_search.py` "
        "and refresh them."
    )

    bm25_index = retrieval.build_index(corpus)
    bm25_results = retrieval.search_bm25(bm25_index, query, top_k=6)

    # Captured 2026-09-10 from a real run of the cached
    # sentence-transformers/multi-qa-MiniLM-L6-cos-v1 model against the query
    # above and the full v1 corpus (see docs/learning-log.md's Day 6 entry).
    semantic_results = [
        {"id": "CONTRACT-002", "score": 0.4968832632160464},
        {"id": "CONTRACT-006", "score": 0.3285422838019914},
        {"id": "POL-002", "score": 0.28417317091699035},
        {"id": "POL-003", "score": 0.2834470481621836},
    ]

    hybrid = hybrid_search.HybridSearch(bm25_results, semantic_results)

    # CONTRACT-002 ranks 1st with both retrievers, so it stays top-1 for any
    # k - RRF only ever adds positive terms to whatever document already
    # leads on rank in both lists.
    for k in (1, 60):
        assert hybrid.rrf(k=k, top_k=1)[0]["id"] == "CONTRACT-002"

    small_k_order = [result["id"] for result in hybrid.rrf(k=1, top_k=6)]
    large_k_order = [result["id"] for result in hybrid.rrf(k=60, top_k=6)]

    assert small_k_order.index("CONTRACT-006") < small_k_order.index("POL-003")
    assert large_k_order.index("POL-003") < large_k_order.index("CONTRACT-006")


# ---------------------------------------------------------------------------
# Chunk-level hybrid search (id_key="chunk_id")
# ---------------------------------------------------------------------------


def test_hybrid_search_supports_chunk_level_results_via_id_key():
    """`HybridSearch` is retrieval-unit-agnostic: passing `id_key="chunk_id"`
    fuses chunk-level results the same way it fuses whole-document results by
    default.

    This also regression-tests a bug caught in review: `_ranks_by_position`
    and `_scores_by_id` used to hardcode `result["id"]` instead of respecting
    `id_key`, which would have raised a `KeyError` the first time this was
    tried on chunk results (chunk results are keyed by `"chunk_id"`, not
    `"id"`).
    """
    hybrid_search = _load_hybrid_search_module()

    bm25_results = [
        {"chunk_id": "SOP-002::chunk-1", "document_id": "SOP-002", "score": 9.0},
        {"chunk_id": "SOP-002::chunk-0", "document_id": "SOP-002", "score": 3.0},
    ]
    semantic_results = [
        {"chunk_id": "SOP-002::chunk-1", "document_id": "SOP-002", "score": 0.8},
        {"chunk_id": "SOP-002::chunk-0", "document_id": "SOP-002", "score": 0.2},
    ]

    hybrid = hybrid_search.HybridSearch(
        bm25_results, semantic_results, id_key="chunk_id"
    )

    rrf_results = hybrid.rrf(top_k=2)
    assert rrf_results[0]["chunk_id"] == "SOP-002::chunk-1"
    assert "id" not in rrf_results[0]

    weighted_results = hybrid.weighted(top_k=2)
    assert weighted_results[0]["chunk_id"] == "SOP-002::chunk-1"
    assert "id" not in weighted_results[0]


def test_chunk_level_hybrid_recovers_the_right_chunk_on_v1_corpus():
    """The whole-document version of this property
    (`test_rrf_and_weighted_agree_on_top1_on_v1_corpus`) repeated at chunk
    granularity: BM25-over-chunks alone gets this query wrong (a chunk from
    the wrong document mentions the same numbers), semantic-over-chunks gets
    it right, and both fusion methods recover the right chunk.

    Chunk-level BM25 (`chunked_search.search_bm25_chunks`) is computed live -
    still pure Python, no model needed. Chunk-level semantic scores are
    frozen from a real run of the cached `multi-qa-MiniLM-L6-cos-v1` model
    (see `src/hybrid_search.py`'s `main()`, 2026-09-10).
    """
    hybrid_search = _load_hybrid_search_module()
    chunking = _load_module("chunking")
    chunked_search = _load_module("chunked_search")
    retrieval = _load_module("retrieval")

    query = "What happens when invoice price variance is over 3%?"
    corpus = retrieval.load_data()
    chunks = chunking.chunk_corpus(corpus)

    # Same purpose as the whole-document corpus-drift guards above: this
    # catches the frozen semantic scores below going stale because chunking
    # produced a different chunk set (a document added/removed/reworded, or
    # the chunking parameters changing) - not a document being edited into
    # producing the exact same chunk count by coincidence.
    assert len(chunks) == 570, (
        "data/corpus_v1 chunking output changed - the frozen semantic chunk "
        "scores below may be stale. Re-run "
        "`./.venv/bin/python src/hybrid_search.py` and refresh them."
    )

    lexical_index = chunked_search.build_chunk_lexical_index(chunks)
    bm25_results = chunked_search.search_bm25_chunks(lexical_index, query, top_k=3)

    # BM25-over-chunks alone gets this wrong, the same way whole-document
    # BM25 did: a chunk from FAQ-002 restates the same tolerances and
    # outranks the SOP-002 chunk that actually states the rule.
    assert bm25_results[0]["chunk_id"] == "FAQ-002::chunk-12"

    semantic_results = [
        {"chunk_id": "SOP-002::chunk-3", "score": 0.6965974167398016},
        {"chunk_id": "SOP-002::chunk-4", "score": 0.6172845695066638},
        {"chunk_id": "FAQ-002::chunk-12", "score": 0.4949384152337939},
    ]

    hybrid = hybrid_search.HybridSearch(
        bm25_results, semantic_results, id_key="chunk_id"
    )

    rrf_top1 = hybrid.rrf(top_k=1)[0]["chunk_id"]
    weighted_top1 = hybrid.weighted(top_k=1)[0]["chunk_id"]

    assert rrf_top1 == weighted_top1 == "SOP-002::chunk-3"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_rrf_and_weighted_handle_empty_inputs_and_non_positive_top_k():
    hybrid_search = _load_hybrid_search_module()

    empty_hybrid = hybrid_search.HybridSearch([], [])
    assert empty_hybrid.rrf() == []
    assert empty_hybrid.weighted() == []

    hybrid = hybrid_search.HybridSearch(
        [{"id": "DOC-A", "score": 1.0}], [{"id": "DOC-A", "score": 1.0}]
    )
    assert hybrid.rrf(top_k=0) == []
    assert hybrid.weighted(top_k=0) == []
