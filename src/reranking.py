"""Day 8: rerank a first-stage shortlist with a cross-encoder.

`hybrid_search.py` and `chunked_search.py` build the *first stage* of
retrieval: fast, corpus-wide rankers (BM25, dense/cosine, and RRF fusion of
the two) that scale to searching the whole corpus for every query. Day 7's
baseline (`docs/eval-report.md`) found the best first-stage configuration on
this corpus is chunk-level Hybrid RRF - P@1 0.935, R@5 0.811, MRR@10 0.965 -
and also measured its structural weak spot: RRF only ever looks at *rank
position* in each retriever's list (see `hybrid_search.HybridSearch.rrf`'s
docstring), so it systematically favors a candidate that both BM25 and dense
rank "pretty good" over a candidate only one of them ranks "excellent" -
even when that second candidate is the actually correct answer. Q014 is the
clearest measured case of this (`docs/eval-report.md`'s "Hybrid still
fails" section): dense alone finds the right document, but both RRF and
weighted fusion get outvoted by a document that is merely decent on both
signals.

This module adds the *second* stage: a reranker that looks at the query and
each shortlisted candidate's actual text *together*, instead of only at
where each retriever happened to rank it, and re-scores relevance directly.

**Why this has to be two stages, not one.** The first-stage retrievers
above are *bi-encoders*: `semantic_search.py`'s embedding model encodes a
query and every document/chunk *independently*, and only compares the two
resulting vectors at the very end (`cosine_similarity`). That independence
is exactly what makes it fast enough to run over the whole corpus for every
query - a chunk's embedding is computed once, cached, and reused for every
future query compared against it. A *cross-encoder*, by contrast, feeds the
query and one candidate's text into the same model *together*, so the model
can directly notice things like "uptime" and "availability commitment"
referring to the same idea in this specific candidate - richer, but there is
no per-candidate vector to precompute and cache: every (query, candidate)
pair needs its own full forward pass. That is too expensive to run over
hundreds of chunks per query, which is exactly why a cross-encoder only ever
reranks the small shortlist the first stage already narrowed down.

**What this module does not do.** It does not replace `hybrid_search.py` or
`chunked_search.py` - `build_chunk_shortlist` below calls them unchanged, on
purpose (see that function's docstring for why reranking a *weaker* first
stage would overstate the reranker's contribution). It also does not use an
LLM as the reranker (Boot.dev Chapter 8's "LLMs for Re-Ranking" / "LLM Batch
Re-Ranking" lessons) - only a small local `sentence_transformers.CrossEncoder`
(`cross-encoder/ms-marco-TinyBERT-L2-v2`), matching today's scope.
"""

from chunked_search import search_bm25_chunks, search_semantic_chunks
from hybrid_search import CANDIDATE_POOL_SIZE, HybridSearch

# ms-marco-TinyBERT-L2-v2 is a ~4M-parameter cross-encoder trained on the
# MS MARCO passage-ranking dataset - small enough to score hundreds of
# (query, candidate) pairs per second on a laptop CPU, which matters because
# a cross-encoder has no cacheable per-candidate vector (see the module
# docstring) and must redo its full forward pass for every pair, every
# query. It is a general web/search-trained model, not procurement-specific
# - see `docs/eval-report.md`'s reranking section for whether that domain
# gap shows up in the numbers.
CROSS_ENCODER_MODEL_NAME = "cross-encoder/ms-marco-TinyBERT-L2-v2"


def load_cross_encoder(model_name=CROSS_ENCODER_MODEL_NAME, device="cpu"):
    """Load the cross-encoder reranker model once, for reuse across every query.

    The import is intentionally inside this function - the same reason
    `semantic_search.load_embedding_model` keeps its import local. It lets
    every fake-scorer test in `tests/test_reranking.py`, and every other
    function in this module, run without ever importing
    `sentence_transformers` or downloading a model just because this file
    was imported.

    `device="cpu"` is forced rather than left to auto-detect. This is a
    ~4M-parameter model scoring at most a few hundred short pairs per query
    (`CANDIDATE_POOL_SIZE`-sized shortlists) - GPU/MPS acceleration buys
    nothing at this scale, and forcing CPU keeps results reproducible on any
    machine, including one with no accelerator at all, instead of silently
    depending on whichever backend happens to be present. This is the Day 8
    design doc's "if GPU acceleration errors, force CPU" contract, applied
    unconditionally rather than only as an error-recovery branch, since
    there is no accuracy or speed reason not to at this model size.
    """
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name, device=device)


def build_candidate_text(candidate):
    """Text handed to the reranker: `title + chunk text`.

    Same "title + body" convention `chunked_search.build_chunk_semantic_index`
    and `build_chunk_lexical_index` already use for embedding/indexing (see
    that module's docstring) - reusing it here means a query phrase that
    happens to match a chunk's title gets the same treatment at both
    retrieval stages, not a different one. `candidate["text"]` itself (the
    raw chunk body - see `rerank`'s docstring for why it is kept on every
    result) stays what a downstream generator would actually cite; only this
    combined string is used as scoring input.
    """
    return f"{candidate['title']} {candidate['text']}".strip()


def score_with_cross_encoder(model, query, candidates):
    """Score every (query, candidate_text) pair with a loaded CrossEncoder.

    A thin adapter around `CrossEncoder.predict`, which expects a list of
    `(text_a, text_b)` pairs and returns one raw relevance score per pair -
    the joint query/candidate interaction that is a cross-encoder's whole
    reason to exist (see the module docstring). That score has no fixed
    scale or guaranteed range (it is the model's raw output, not a
    probability); only its *ordering* matters here - `rerank` below only
    ever sorts by it, never compares it against an absolute threshold.
    """
    if not candidates:
        return []

    pairs = [(query, build_candidate_text(candidate)) for candidate in candidates]
    raw_scores = model.predict(pairs)
    return [float(score) for score in raw_scores]


def rerank(query, candidates, score_fn, top_k=None):
    """Re-score a first-stage shortlist against `query` and re-sort it.

    This is the reusable "reranker abstraction" the Day 8 contract calls
    for: it knows nothing about cross-encoders or `sentence_transformers` -
    that is entirely `score_fn`'s job (`score_fn(query, candidates) ->
    [score, ...]`, one score per candidate, same order as `candidates`).
    Swapping `score_with_cross_encoder` (bound to a loaded model - see
    `rerank_with_cross_encoder` below) for a small fake function that
    returns hand-picked scores is what lets `tests/test_reranking.py`
    exercise the sorting/tie-break/rank-assignment logic below without ever
    downloading a model.

    Every field already on a candidate dict (`chunk_id`, `document_id`,
    `first_stage_rank`, `first_stage_score`, `bm25_score`, `semantic_score`,
    `title`, `text`, ...) is copied through unchanged onto the result -
    only `reranker_score` and `final_rank` are added. That is the
    auditability requirement from the Day 8 design doc: a reranked result
    must still be able to explain itself ("this chunk was first-stage rank
    4 with RRF score 0.031; the cross-encoder scored it 8.56; it ended up
    final rank 1") instead of only reporting the new order.

    Ties are broken by `chunk_id` (ascending) - the same deterministic
    tie-break `HybridSearch.rrf`/`weighted` already use. Without it, two
    candidates the reranker scores identically would sort in whatever order
    Python's stable sort happened to leave them in, which silently depends
    on first-stage order rather than meaning anything about relevance.
    """
    if not candidates:
        return []

    scores = score_fn(query, candidates)
    if len(scores) != len(candidates):
        raise ValueError(
            f"score_fn returned {len(scores)} scores for {len(candidates)} "
            "candidates - exactly one score per candidate is required"
        )

    scored = [
        {**candidate, "reranker_score": score}
        for candidate, score in zip(candidates, scores)
    ]
    scored.sort(key=lambda result: (-result["reranker_score"], result["chunk_id"]))

    for final_rank, result in enumerate(scored, start=1):
        result["final_rank"] = final_rank

    if top_k is not None:
        scored = scored[:top_k]

    return scored


def rerank_with_cross_encoder(query, candidates, model, top_k=None):
    """Convenience wrapper: rerank `candidates` with a loaded CrossEncoder.

    Binds `model` into a `score_fn` closure and delegates to `rerank` above,
    so a live caller (`two_stage_rerank` below, or the demo in `main()`)
    gets the `rerank(query, candidates, top_k)` shape the Day 8 design doc
    suggests, while `rerank` itself stays free of any
    `sentence_transformers`-specific code - see that function's docstring
    for why that separation is what makes reranking testable without a
    model download.
    """

    def score_fn(query, candidates):
        return score_with_cross_encoder(model, query, candidates)

    return rerank(query, candidates, score_fn, top_k=top_k)


def build_chunk_shortlist(
    query,
    chunk_lexical_index,
    chunk_semantic_index,
    embedding_model,
    pool_size=CANDIDATE_POOL_SIZE,
):
    """Produce a chunk-level Hybrid RRF shortlist for one query.

    This *is* the first stage of Day 8's two-stage pipeline: the exact Day 7
    pieces (`search_bm25_chunks`, `search_semantic_chunks`,
    `HybridSearch(id_key="chunk_id")`) that already produced the strongest
    baseline in `docs/eval-report.md` (Hybrid RRF chunk->document - P@1
    0.935, R@5 0.811, MRR@10 0.965), unchanged. Reranking on top of a
    weaker first stage (e.g. whole-document hybrid) would overstate what
    the reranker itself contributes, by comparing it against a baseline
    Day 7 already showed is not the best available - see this module's
    docstring and `docs/day-08-reranking-two-stage-retrieval.md`.

    `pool_size` sizes two things at once, matching how `eval_metrics.py`
    already uses `CANDIDATE_POOL_SIZE`: how many candidates each of BM25 and
    semantic search contribute *before* fusion (this is also the Day 7
    exact-tie mitigation - see `hybrid_search.CANDIDATE_POOL_SIZE`'s
    docstring), and how many fused chunks make it into the shortlist the
    reranker actually sees. The Day 8 design doc's suggested shortlist range
    is 10-25; this reuses the existing 15 rather than introducing a second
    tunable number with no evidence yet that a different value helps.

    Each shortlist entry carries everything `rerank` needs to score it
    (`title`, `text`) plus everything a reranked result needs to explain
    itself later (`first_stage_rank`, `first_stage_score`, `bm25_score`,
    `semantic_score`, `document_id`) - see `rerank`'s docstring for why
    those fields matter. `document_id` in particular is looked up here
    because `HybridSearch`'s fused output only ever carries `chunk_id` and
    per-method scores (see `hybrid_search.py`'s module docstring) - without
    this lookup, nothing downstream (chunk->document rollup, the demo, the
    eval row) would know which document a reranked chunk came from.
    """
    bm25_results = search_bm25_chunks(chunk_lexical_index, query, top_k=pool_size)
    semantic_results = search_semantic_chunks(
        chunk_semantic_index, query, embedding_model, top_k=pool_size
    )

    hybrid = HybridSearch(bm25_results, semantic_results, id_key="chunk_id")
    fused = hybrid.rrf(top_k=pool_size)

    chunks_by_id = chunk_lexical_index["chunks"]
    shortlist = []
    for first_stage_rank, result in enumerate(fused, start=1):
        chunk_id = result["chunk_id"]
        chunk = chunks_by_id[chunk_id]
        shortlist.append(
            {
                "chunk_id": chunk_id,
                "document_id": chunk["document_id"],
                "title": chunk["title"],
                "text": chunk["text"],
                "first_stage_rank": first_stage_rank,
                "first_stage_score": result["score"],
                "bm25_score": result["bm25_score"],
                "semantic_score": result["semantic_score"],
            }
        )
    return shortlist


def two_stage_rerank(
    query,
    chunk_lexical_index,
    chunk_semantic_index,
    embedding_model,
    cross_encoder_model,
    pool_size=CANDIDATE_POOL_SIZE,
    top_k=None,
):
    """Run the full Day 8 pipeline for one query: first-stage shortlist, then rerank.

    The one function `eval_metrics.py`'s reranked row and `main()`'s demo
    below both call - everything above this function is a building block;
    this is the assembled two-stage pipeline the design doc describes.
    """
    shortlist = build_chunk_shortlist(
        query,
        chunk_lexical_index,
        chunk_semantic_index,
        embedding_model,
        pool_size=pool_size,
    )
    return rerank_with_cross_encoder(query, shortlist, cross_encoder_model, top_k=top_k)


# Three v1 queries chosen from Day 7's own edge-case set
# (`hybrid_search.EDGE_CASE_QUERY_IDS`) to demo reranking against, covering
# the three outcomes that matter for the Day 8 objective:
#
#   Q014 - the Day 7 "hybrid still fails" case: dense alone is correct, but
#          RRF/weighted fusion both land on a document that is merely
#          decent on both signals instead (`docs/eval-report.md`). This is
#          the consensus-over-strength failure Day 8 exists to test at
#          chunk level - does the reranker recover it, or not?
#   Q009 - a case first-stage hybrid already gets right (exact numeric
#          threshold, BM25-favoring). Checks that reranking does not break
#          something that was not broken.
#   Q042 - a case where fusion itself already recovered the right document
#          over either single method (Day 7's "hybrid wins" example).
#          Checks reranking on top of an already-correct first stage.
DEMO_QUERY_IDS = ["Q014", "Q009", "Q042"]


def _document_mark(document_id, relevant_ids):
    return "correct" if document_id in relevant_ids else "MISS"


def _print_shortlist_row(result, relevant_ids):
    mark = _document_mark(result["document_id"], relevant_ids)
    print(
        f"    #{result['first_stage_rank']} {result['chunk_id']} "
        f"(doc={result['document_id']}, rrf={result['first_stage_score']:.4f}) {mark}"
    )


def _print_reranked_row(result, relevant_ids):
    mark = _document_mark(result["document_id"], relevant_ids)
    print(
        f"    #{result['final_rank']} {result['chunk_id']} "
        f"(doc={result['document_id']}, was first-stage #{result['first_stage_rank']}, "
        f"cross-encoder={result['reranker_score']:.4f}) {mark}"
    )


def main() -> None:
    """Demo: first-stage chunk shortlist vs. reranked shortlist, on the
    query Day 7 could not fix through fusion alone (Q014), plus two
    contrast cases - see `DEMO_QUERY_IDS` above for why these three.

    This is the Block 3A "targeted case study" - the aggregate 93-query
    comparison (does reranking help *on average*, not just on this one
    known failure) lives in `eval_metrics.py`'s "Cross-encoder reranked
    Hybrid RRF chunk->document" row instead; see this module's docstring
    and `docs/eval-report.md` for why both views matter.
    """
    from chunked_search import build_chunk_lexical_index, build_chunk_semantic_index
    from chunking import chunk_corpus
    from hybrid_search import load_example_queries
    from preprocessing import load_data
    from semantic_search import load_embedding_model

    data = load_data()
    chunks = chunk_corpus(data)
    embedding_model = load_embedding_model()
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
    cross_encoder_model = load_cross_encoder()

    queries_by_id = {query["query_id"]: query for query in load_example_queries()}

    for query_id in DEMO_QUERY_IDS:
        query_row = queries_by_id[query_id]
        query = query_row["query"]
        relevant_ids = set(query_row["expected_relevant_ids"])

        shortlist = build_chunk_shortlist(
            query, chunk_lexical_index, chunk_semantic_index, embedding_model
        )
        reranked = rerank_with_cross_encoder(query, shortlist, cross_encoder_model)

        print(f"\n{query_id}: {query}")
        print(f"  expected relevant documents: {sorted(relevant_ids)}")

        print("  first-stage top 3 (chunk-level Hybrid RRF):")
        for result in shortlist[:3]:
            _print_shortlist_row(result, relevant_ids)

        print("  after cross-encoder reranking, top 3:")
        for result in reranked[:3]:
            _print_reranked_row(result, relevant_ids)

        first_stage_top1_document = shortlist[0]["document_id"] if shortlist else None
        reranked_top1_document = reranked[0]["document_id"] if reranked else None
        if reranked_top1_document != first_stage_top1_document:
            print(
                f"  -> reranking changed the top document: "
                f"{first_stage_top1_document} -> {reranked_top1_document}"
            )
        else:
            print(f"  -> reranking kept the same top document: {first_stage_top1_document}")


if __name__ == "__main__":
    main()
