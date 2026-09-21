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


def _load_reranking_module():
    return _load_module("reranking")


class FakeCrossEncoder:
    """Deterministic stand-in for `sentence_transformers.CrossEncoder`.

    Mirrors the `FakeEmbeddingModel` pattern `tests/test_chunked_search.py`
    already uses for the embedding model: a dict lookup keyed by the exact
    pair the real model would receive, so a test fails loudly (`KeyError`)
    if the code under test ever builds a different pair than expected,
    instead of silently returning some default score.
    """

    def __init__(self, scores_by_pair):
        self.scores_by_pair = scores_by_pair
        self.received_pairs = None

    def predict(self, pairs):
        self.received_pairs = pairs
        return [self.scores_by_pair[pair] for pair in pairs]


def _candidate(chunk_id, document_id, title, text, first_stage_rank, first_stage_score):
    """A shortlist entry shaped exactly like `build_chunk_shortlist` produces
    - every field a reranked result is expected to preserve for
    auditability (see `rerank`'s docstring), plus the `title`/`text` a
    reranker actually scores.
    """
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "title": title,
        "text": text,
        "first_stage_rank": first_stage_rank,
        "first_stage_score": first_stage_score,
        "bm25_score": first_stage_score,
        "semantic_score": first_stage_score,
    }


# ---------------------------------------------------------------------------
# build_candidate_text
# ---------------------------------------------------------------------------


def test_build_candidate_text_joins_title_and_chunk_text():
    reranking = _load_reranking_module()
    candidate = _candidate("SOP-002::chunk-1", "SOP-002", "Invoice mismatch handling",
                            "A price variance over 3% requires buyer review.", 1, 0.05)

    assert (
        reranking.build_candidate_text(candidate)
        == "Invoice mismatch handling A price variance over 3% requires buyer review."
    )


# ---------------------------------------------------------------------------
# score_with_cross_encoder
# ---------------------------------------------------------------------------


def test_score_with_cross_encoder_builds_query_title_text_pairs():
    reranking = _load_reranking_module()
    candidates = [
        _candidate("A::chunk-0", "A", "Title A", "Body A", 1, 0.02),
        _candidate("B::chunk-0", "B", "Title B", "Body B", 2, 0.01),
    ]
    model = FakeCrossEncoder(
        {
            ("what happened?", "Title A Body A"): 3.5,
            ("what happened?", "Title B Body B"): -1.2,
        }
    )

    scores = reranking.score_with_cross_encoder(model, "what happened?", candidates)

    # The exact pairs handed to CrossEncoder.predict are (query, title+text),
    # not (query, text) alone - if `build_candidate_text` were bypassed this
    # would raise KeyError against the fake's dict instead of returning these.
    assert model.received_pairs == [
        ("what happened?", "Title A Body A"),
        ("what happened?", "Title B Body B"),
    ]
    assert scores == [3.5, -1.2]


def test_score_with_cross_encoder_handles_no_candidates():
    reranking = _load_reranking_module()
    model = FakeCrossEncoder({})

    assert reranking.score_with_cross_encoder(model, "query", []) == []


# ---------------------------------------------------------------------------
# rerank
# ---------------------------------------------------------------------------


def test_rerank_sorts_by_reranker_score_and_preserves_first_stage_fields():
    reranking = _load_reranking_module()

    # First-stage order deliberately disagrees with the fake reranker's
    # order - this is the whole point of reranking (see the module
    # docstring's Q014 discussion): a candidate that was first-stage rank 2
    # can end up final rank 1 once the reranker looks at its actual text.
    candidates = [
        _candidate("A::chunk-0", "A", "Title A", "Body A", 1, 0.05),
        _candidate("B::chunk-0", "B", "Title B", "Body B", 2, 0.04),
    ]

    def fake_score_fn(query, candidates):
        return [1.0, 9.0]  # candidate B scores far higher than candidate A

    results = reranking.rerank("query", candidates, fake_score_fn)

    assert [r["chunk_id"] for r in results] == ["B::chunk-0", "A::chunk-0"]
    assert results[0]["reranker_score"] == 9.0
    assert results[0]["final_rank"] == 1
    # Original first-stage fields survive unchanged onto the reranked result
    # - this is the auditability requirement, not incidental.
    assert results[0]["first_stage_rank"] == 2
    assert results[0]["first_stage_score"] == 0.04
    assert results[0]["document_id"] == "B"
    assert results[1]["final_rank"] == 2


def test_rerank_breaks_score_ties_by_chunk_id_ascending():
    reranking = _load_reranking_module()
    candidates = [
        _candidate("Z::chunk-0", "Z", "Title Z", "Body Z", 1, 0.05),
        _candidate("A::chunk-0", "A", "Title A", "Body A", 2, 0.04),
    ]

    def fake_score_fn(query, candidates):
        return [5.0, 5.0]  # exact tie

    results = reranking.rerank("query", candidates, fake_score_fn)

    # Same deterministic tie-break HybridSearch.rrf/weighted already use:
    # lower chunk_id first, not whatever order the candidates happened to
    # arrive in.
    assert [r["chunk_id"] for r in results] == ["A::chunk-0", "Z::chunk-0"]


def test_rerank_truncates_to_top_k_after_sorting():
    reranking = _load_reranking_module()
    candidates = [
        _candidate("A::chunk-0", "A", "Title A", "Body A", 1, 0.03),
        _candidate("B::chunk-0", "B", "Title B", "Body B", 2, 0.02),
        _candidate("C::chunk-0", "C", "Title C", "Body C", 3, 0.01),
    ]

    def fake_score_fn(query, candidates):
        return [1.0, 3.0, 2.0]

    results = reranking.rerank("query", candidates, fake_score_fn, top_k=2)

    assert [r["chunk_id"] for r in results] == ["B::chunk-0", "C::chunk-0"]
    assert len(results) == 2


def test_rerank_handles_empty_candidates_without_calling_score_fn():
    reranking = _load_reranking_module()

    def score_fn_that_must_not_be_called(query, candidates):
        raise AssertionError("score_fn should not be called for an empty shortlist")

    assert reranking.rerank("query", [], score_fn_that_must_not_be_called) == []


def test_rerank_raises_if_score_fn_returns_the_wrong_number_of_scores():
    reranking = _load_reranking_module()
    candidates = [_candidate("A::chunk-0", "A", "Title A", "Body A", 1, 0.03)]

    def broken_score_fn(query, candidates):
        return [1.0, 2.0]  # two scores for one candidate

    with pytest.raises(ValueError):
        reranking.rerank("query", candidates, broken_score_fn)


# ---------------------------------------------------------------------------
# rerank_with_cross_encoder
# ---------------------------------------------------------------------------


def test_rerank_with_cross_encoder_wires_score_with_cross_encoder_into_rerank():
    reranking = _load_reranking_module()
    candidates = [
        _candidate("A::chunk-0", "A", "Title A", "Body A", 1, 0.03),
        _candidate("B::chunk-0", "B", "Title B", "Body B", 2, 0.02),
    ]
    model = FakeCrossEncoder(
        {
            ("query", "Title A Body A"): 0.1,
            ("query", "Title B Body B"): 9.9,
        }
    )

    results = reranking.rerank_with_cross_encoder("query", candidates, model)

    assert [r["chunk_id"] for r in results] == ["B::chunk-0", "A::chunk-0"]
    assert results[0]["reranker_score"] == 9.9


# ---------------------------------------------------------------------------
# build_chunk_shortlist - the first stage, over a small synthetic chunk set
# ---------------------------------------------------------------------------


class FakeEmbeddingModel:
    """Deterministic stand-in for SentenceTransformer, same pattern
    `tests/test_chunked_search.py` uses."""

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
        {
            "chunk_id": "FAQ-002::chunk-0",
            "document_id": "FAQ-002",
            "chunk_index": 0,
            "text": "Purchase order tolerances allow small pricing differences.",
            "title": "Invoice FAQ",
        },
    ]


def test_build_chunk_shortlist_fuses_bm25_and_semantic_and_attaches_first_stage_fields():
    reranking = _load_reranking_module()
    chunked_search = _load_module("chunked_search")

    chunks = _sample_chunks()
    chunk_lexical_index = chunked_search.build_chunk_lexical_index(chunks)

    query = "What happens when invoice price variance is over 3%?"
    embedding_model = FakeEmbeddingModel(
        {
            "Invoice mismatch handling Invoices are matched against purchase "
            "order and pricing.": [1.0, 0.0],
            "Invoice mismatch handling A price variance over 3% requires "
            "buyer review.": [0.0, 1.0],
            "Invoice FAQ Purchase order tolerances allow small pricing "
            "differences.": [0.5, 0.5],
            query: [0.0, 1.0],
        }
    )
    chunk_semantic_index = chunked_search.build_chunk_semantic_index(
        chunks, embedding_model
    )

    shortlist = reranking.build_chunk_shortlist(
        query, chunk_lexical_index, chunk_semantic_index, embedding_model, pool_size=3
    )

    # "price"/"variance" (BM25) and cosine direction (semantic) both single
    # out SOP-002::chunk-1 - it should come out on top of the fused
    # shortlist, at first_stage_rank 1.
    assert shortlist[0]["chunk_id"] == "SOP-002::chunk-1"
    assert shortlist[0]["document_id"] == "SOP-002"
    assert shortlist[0]["first_stage_rank"] == 1
    assert shortlist[0]["text"] == "A price variance over 3% requires buyer review."
    assert shortlist[0]["title"] == "Invoice mismatch handling"
    # Per-method scores are preserved too, the same auditability contract
    # `rerank` relies on downstream.
    assert shortlist[0]["bm25_score"] is not None
    assert shortlist[0]["semantic_score"] is not None
    assert len(shortlist) == 3


def test_build_chunk_shortlist_handles_a_query_with_no_lexical_matches():
    reranking = _load_reranking_module()
    chunked_search = _load_module("chunked_search")

    chunks = _sample_chunks()
    chunk_lexical_index = chunked_search.build_chunk_lexical_index(chunks)

    # A query sharing no vocabulary with any chunk - BM25 contributes
    # nothing, so the shortlist should still be produced from semantic
    # scores alone (RRF degrades gracefully - see HybridSearch.rrf).
    query = "zzzzz-not-in-corpus"
    embedding_model = FakeEmbeddingModel(
        {
            "Invoice mismatch handling Invoices are matched against purchase "
            "order and pricing.": [1.0, 0.0],
            "Invoice mismatch handling A price variance over 3% requires "
            "buyer review.": [0.0, 1.0],
            "Invoice FAQ Purchase order tolerances allow small pricing "
            "differences.": [0.0, 1.0],
            query: [0.0, 1.0],
        }
    )
    chunk_semantic_index = chunked_search.build_chunk_semantic_index(
        chunks, embedding_model
    )

    shortlist = reranking.build_chunk_shortlist(
        query, chunk_lexical_index, chunk_semantic_index, embedding_model, pool_size=3
    )

    assert len(shortlist) == 3
    assert all(result["bm25_score"] is None for result in shortlist)


# ---------------------------------------------------------------------------
# build_chunk_shortlist's max_chunks_per_document (Day 14 Block 3B): the
# per-document diversity cap on the fused, pre-rerank shortlist.
# ---------------------------------------------------------------------------


def _diverse_chunks():
    """Four chunks across three documents, deliberately unrelated in
    vocabulary to the query - the same "no lexical matches" trick
    `test_build_chunk_shortlist_handles_a_query_with_no_lexical_matches`
    already uses, so BM25 contributes nothing and the fused order is driven
    entirely by the hand-picked semantic vectors below, making the expected
    order fully predictable rather than dependent on real BM25 tokenization.
    """
    return [
        {"chunk_id": "DOC-A::chunk-0", "document_id": "DOC-A", "chunk_index": 0, "text": "zzzzz-a0", "title": "A"},
        {"chunk_id": "DOC-A::chunk-1", "document_id": "DOC-A", "chunk_index": 1, "text": "zzzzz-a1", "title": "A"},
        {"chunk_id": "DOC-B::chunk-0", "document_id": "DOC-B", "chunk_index": 0, "text": "zzzzz-b0", "title": "B"},
        {"chunk_id": "DOC-C::chunk-0", "document_id": "DOC-C", "chunk_index": 0, "text": "zzzzz-c0", "title": "C"},
    ]


def _diverse_embedding_model(query):
    # All vectors are unit-length, so cosine similarity equals their dot
    # product with the query vector [1.0, 0.0] - strictly decreasing here
    # (1.0, 0.8, 0.6, 0.4), giving a fully deterministic semantic rank
    # order: DOC-A::chunk-0, DOC-A::chunk-1, DOC-B::chunk-0, DOC-C::chunk-0.
    # DOC-A deliberately takes the top TWO fused positions, so the test
    # below can prove the cap skips DOC-A's *second* chunk specifically
    # (not just "some" chunk), while leaving DOC-B/DOC-C untouched.
    return FakeEmbeddingModel(
        {
            "A zzzzz-a0": [1.0, 0.0],
            "A zzzzz-a1": [0.8, 0.6],
            "B zzzzz-b0": [0.6, 0.8],
            "C zzzzz-c0": [0.4, 0.9165],
            query: [1.0, 0.0],
        }
    )


def test_build_chunk_shortlist_with_no_cap_lets_one_document_take_two_slots():
    # The baseline this test's capped counterpart below is contrasted
    # against: with no cap (the default), DOC-A legitimately occupies both
    # of the top two fused positions.
    reranking = _load_reranking_module()
    chunked_search = _load_module("chunked_search")

    chunks = _diverse_chunks()
    chunk_lexical_index = chunked_search.build_chunk_lexical_index(chunks)
    query = "no-shared-vocabulary-query"
    embedding_model = _diverse_embedding_model(query)
    chunk_semantic_index = chunked_search.build_chunk_semantic_index(chunks, embedding_model)

    shortlist = reranking.build_chunk_shortlist(
        query, chunk_lexical_index, chunk_semantic_index, embedding_model, pool_size=4
    )

    assert [result["chunk_id"] for result in shortlist] == [
        "DOC-A::chunk-0",
        "DOC-A::chunk-1",
        "DOC-B::chunk-0",
        "DOC-C::chunk-0",
    ]


def test_build_chunk_shortlist_diversity_cap_skips_a_documents_extra_chunks():
    # Day 14's actual repair mechanism: with max_chunks_per_document=1,
    # DOC-A's weaker second chunk (fused rank 2) is skipped so the
    # shortlist stays diverse, while DOC-A's stronger first chunk, DOC-B,
    # and DOC-C are all kept - proving the cap keeps a document's *best*
    # chunk(s), not an arbitrary one, and never removes a different
    # document's chunk to enforce the cap.
    reranking = _load_reranking_module()
    chunked_search = _load_module("chunked_search")

    chunks = _diverse_chunks()
    chunk_lexical_index = chunked_search.build_chunk_lexical_index(chunks)
    query = "no-shared-vocabulary-query"
    embedding_model = _diverse_embedding_model(query)
    chunk_semantic_index = chunked_search.build_chunk_semantic_index(chunks, embedding_model)

    shortlist = reranking.build_chunk_shortlist(
        query,
        chunk_lexical_index,
        chunk_semantic_index,
        embedding_model,
        pool_size=4,
        max_chunks_per_document=1,
    )

    assert [result["chunk_id"] for result in shortlist] == [
        "DOC-A::chunk-0",
        "DOC-B::chunk-0",
        "DOC-C::chunk-0",
    ]
    # Skipped candidates are dropped, not backfilled - the capped shortlist
    # is genuinely shorter than pool_size, not re-padded to 4 with a
    # candidate that was never fetched.
    assert len(shortlist) == 3
    # first_stage_rank values are preserved from the ORIGINAL fused order,
    # not renumbered after the skip - DOC-B::chunk-0 keeps its true rank 3
    # (not compacted down to rank 2), so a reader can still see exactly
    # which original position the cap skipped over (rank 2, DOC-A's second
    # chunk).
    assert [result["first_stage_rank"] for result in shortlist] == [1, 3, 4]


def test_build_chunk_shortlist_cap_of_two_keeps_both_of_a_documents_top_chunks():
    # A cap higher than how many chunks any one document actually has in
    # the pool is a no-op - proving the cap only ever removes what's
    # actually in excess of the limit, never truncates below it.
    reranking = _load_reranking_module()
    chunked_search = _load_module("chunked_search")

    chunks = _diverse_chunks()
    chunk_lexical_index = chunked_search.build_chunk_lexical_index(chunks)
    query = "no-shared-vocabulary-query"
    embedding_model = _diverse_embedding_model(query)
    chunk_semantic_index = chunked_search.build_chunk_semantic_index(chunks, embedding_model)

    shortlist = reranking.build_chunk_shortlist(
        query,
        chunk_lexical_index,
        chunk_semantic_index,
        embedding_model,
        pool_size=4,
        max_chunks_per_document=2,
    )

    assert [result["chunk_id"] for result in shortlist] == [
        "DOC-A::chunk-0",
        "DOC-A::chunk-1",
        "DOC-B::chunk-0",
        "DOC-C::chunk-0",
    ]


# ---------------------------------------------------------------------------
# retrieval_config_for_query_type (Day 14 Block 3B): the multi_doc vs
# default retrieval-config decision, as plain data.
# ---------------------------------------------------------------------------


def test_retrieval_config_for_multi_doc_uses_the_deeper_diversity_capped_config():
    reranking = _load_reranking_module()

    config = reranking.retrieval_config_for_query_type("multi_doc")

    assert config == reranking.MULTI_DOC_RETRIEVAL_CONFIG
    # Returns a copy, not the module's own dict - a caller mutating its
    # result must not corrupt the shared constant for the next query.
    config["top_k"] = 999
    assert reranking.MULTI_DOC_RETRIEVAL_CONFIG["top_k"] != 999


def test_retrieval_config_for_non_multi_doc_query_types_uses_the_default_config():
    reranking = _load_reranking_module()

    for query_type in ("threshold", "lookup", "comparison", None):
        assert reranking.retrieval_config_for_query_type(query_type) == reranking.DEFAULT_RETRIEVAL_CONFIG


# ---------------------------------------------------------------------------
# two_stage_rerank - the full pipeline, first stage + rerank in one call
# ---------------------------------------------------------------------------


def test_two_stage_rerank_runs_first_stage_then_reranks_with_the_given_model():
    reranking = _load_reranking_module()
    chunked_search = _load_module("chunked_search")

    chunks = _sample_chunks()
    chunk_lexical_index = chunked_search.build_chunk_lexical_index(chunks)

    query = "What happens when invoice price variance is over 3%?"
    embedding_model = FakeEmbeddingModel(
        {
            "Invoice mismatch handling Invoices are matched against purchase "
            "order and pricing.": [1.0, 0.0],
            "Invoice mismatch handling A price variance over 3% requires "
            "buyer review.": [0.0, 1.0],
            "Invoice FAQ Purchase order tolerances allow small pricing "
            "differences.": [0.5, 0.5],
            query: [0.0, 1.0],
        }
    )
    chunk_semantic_index = chunked_search.build_chunk_semantic_index(
        chunks, embedding_model
    )

    # The cross-encoder deliberately disagrees with the first stage: it
    # scores the FAQ chunk highest even though first-stage RRF should not
    # rank it first. This is only here to prove two_stage_rerank actually
    # calls the reranker (and reflects its order), not the first stage's.
    cross_encoder_model = FakeCrossEncoder(
        {
            (query, "Invoice mismatch handling Invoices are matched against "
             "purchase order and pricing."): 0.1,
            (query, "Invoice mismatch handling A price variance over 3% "
             "requires buyer review."): 0.2,
            (query, "Invoice FAQ Purchase order tolerances allow small "
             "pricing differences."): 9.0,
        }
    )

    results = reranking.two_stage_rerank(
        query,
        chunk_lexical_index,
        chunk_semantic_index,
        embedding_model,
        cross_encoder_model,
        pool_size=3,
    )

    assert results[0]["chunk_id"] == "FAQ-002::chunk-0"
    assert results[0]["reranker_score"] == 9.0
    assert results[0]["final_rank"] == 1
    # first_stage_rank is still present and unchanged - reranking replaced
    # the *order*, not the record of where the candidate started.
    assert "first_stage_rank" in results[0]


def test_two_stage_rerank_passes_max_chunks_per_document_through_to_the_shortlist():
    # Proves the parameter is actually threaded end to end, not just
    # accepted and ignored: DOC-A::chunk-1 must never reach the reranker at
    # all once capped out of the shortlist. Using a FakeCrossEncoder whose
    # score dict has NO entry for DOC-A::chunk-1's pair means that if the
    # cap were silently skipped, `score_with_cross_encoder` would raise
    # KeyError instead of this test just checking the final order - the
    # same "fail loudly on an unexpected pair" property
    # `test_score_with_cross_encoder_builds_query_title_text_pairs` relies
    # on above.
    reranking = _load_reranking_module()
    chunked_search = _load_module("chunked_search")

    chunks = _diverse_chunks()
    chunk_lexical_index = chunked_search.build_chunk_lexical_index(chunks)
    query = "no-shared-vocabulary-query"
    embedding_model = _diverse_embedding_model(query)
    chunk_semantic_index = chunked_search.build_chunk_semantic_index(chunks, embedding_model)

    cross_encoder_model = FakeCrossEncoder(
        {
            (query, "A zzzzz-a0"): 3.0,
            (query, "B zzzzz-b0"): 2.0,
            (query, "C zzzzz-c0"): 1.0,
            # deliberately no entry for ("A zzzzz-a1") - it must never be scored
        }
    )

    results = reranking.two_stage_rerank(
        query,
        chunk_lexical_index,
        chunk_semantic_index,
        embedding_model,
        cross_encoder_model,
        pool_size=4,
        max_chunks_per_document=1,
    )

    assert [r["chunk_id"] for r in results] == ["DOC-A::chunk-0", "DOC-B::chunk-0", "DOC-C::chunk-0"]


# ---------------------------------------------------------------------------
# Edge cases: a single-candidate shortlist, and reranking's interaction with
# eval_metrics.rollup_chunks_to_documents when two candidates share a
# document_id.
# ---------------------------------------------------------------------------


def test_rerank_handles_a_single_candidate_shortlist():
    reranking = _load_reranking_module()
    candidates = [_candidate("A::chunk-0", "A", "Title A", "Body A", 1, 0.05)]

    def fake_score_fn(query, candidates):
        return [4.2]

    results = reranking.rerank("query", candidates, fake_score_fn)

    # A shortlist of one has nothing to sort against and no tie to break -
    # it should still get a reranker_score and a final_rank of 1, the same
    # shape a multi-candidate shortlist produces.
    assert len(results) == 1
    assert results[0]["reranker_score"] == 4.2
    assert results[0]["final_rank"] == 1
    assert results[0]["chunk_id"] == "A::chunk-0"


def test_reranked_chunks_rolling_up_to_documents_uses_the_reranked_order_not_first_stage_order():
    """`eval_metrics.rollup_chunks_to_documents` keeps a document's *first*
    appearance in whatever ranked list it is given - Day 8's eval row feeds
    it the *reranked* chunk list, not the first-stage shortlist, so a
    document whose best chunk changes after reranking should roll up at
    the position of its new best chunk, not its old one.

    This is the "duplicate-document rollup" case the same class of chunks
    can hit: SOP-002 contributes two chunks to the shortlist, and the
    reranker prefers the *second* first-stage chunk over the first - the
    rolled-up document order must follow the reranker, not first-stage
    order, and must still de-duplicate SOP-002 down to one entry.
    """
    reranking = _load_reranking_module()
    eval_metrics = _load_module("eval_metrics")

    # First-stage order: SOP-002::chunk-0, SOP-002::chunk-1, FAQ-002::chunk-0
    # - two chunks from the same document, one from another.
    candidates = [
        _candidate("SOP-002::chunk-0", "SOP-002", "T", "first SOP-002 chunk", 1, 0.05),
        _candidate("SOP-002::chunk-1", "SOP-002", "T", "second SOP-002 chunk", 2, 0.04),
        _candidate("FAQ-002::chunk-0", "FAQ-002", "T", "FAQ chunk", 3, 0.03),
    ]

    # The reranker inverts SOP-002's two chunks and puts FAQ-002 in between:
    # chunk-1 (was first-stage #2) now scores highest, FAQ-002 second,
    # chunk-0 (was first-stage #1) last.
    def fake_score_fn(query, candidates):
        scores_by_chunk_id = {
            "SOP-002::chunk-0": 1.0,
            "SOP-002::chunk-1": 9.0,
            "FAQ-002::chunk-0": 5.0,
        }
        return [scores_by_chunk_id[c["chunk_id"]] for c in candidates]

    reranked = reranking.rerank("query", candidates, fake_score_fn)
    assert [r["chunk_id"] for r in reranked] == [
        "SOP-002::chunk-1",
        "FAQ-002::chunk-0",
        "SOP-002::chunk-0",
    ]

    document_ids = eval_metrics.rollup_chunks_to_documents(reranked)

    # SOP-002 de-duplicates to one entry, at the position of its *reranked*
    # best chunk (SOP-002::chunk-1, now rank 1) - not its first-stage best
    # chunk (SOP-002::chunk-0, which the reranker actually ranked last).
    assert document_ids == ["SOP-002", "FAQ-002"]
