"""Day 7: turn ranked retrieval results into P@1 / R@5 / MRR@10 numbers.

**This evaluates raw text retrieval only - metadata filtering is not
applied here.** `query_row["metadata_filters"]` is never read by `main()`'s
six retrieval closures below; every method is scored on however it ranks
the *whole* corpus for a query's text, the same as if `metadata_filters`
didn't exist. That is a deliberate scope decision, not an oversight, and it
matters because it isn't a simple thing to add: 17 of the 21 v1 queries
that carry a `metadata_filters` value have at least one id in their own
`expected_relevant_ids` that the query's *own* filter would exclude (e.g.
Q001 expects `FAQ-001` as a secondary answer, but its filter is `doc_type:
policy`, and FAQ-001 isn't a policy). A "filtered" version of this baseline
would need its own, filter-adjusted ground truth per query - scoring
`retrieved (post-filter) vs. expected_relevant_ids (unfiltered)` would
unfairly penalize every method for correctly filtering out a document the
filter was always going to exclude. `docs/eval-report.md`'s "Known
limitations" section leaves that as a real next step, not something folded
into this table.

Every module before this one (`retrieval.py`, `semantic_search.py`,
`chunked_search.py`, `hybrid_search.py`) answers "what does this method
retrieve for one query?" and Day 6's `main()` demos showed that qualitatively
- five queries, printed side by side, eyeballed for which method got the
right document first. That is a demo, not evidence: it does not say how
often each method is right, only that it was right *this time*.

This module is the other half: given a ranked list of retrieved document ids
and the *known* relevant ids for a query (`data/corpus_v1/example_queries.jsonl`'s
`expected_relevant_ids` - see `docs/corpus-v1.md`), compute the three metrics
Day 7's design doc asks for, then average them across a whole query set to
get one number per retrieval method. That is what turns "hybrid seemed to
help on this query" into "hybrid's R@5 across 93 queries is X".

**What "relevant" means here.** `expected_relevant_ids` also has a companion
field, `relevance_grades` (2 = primary, 1 = partially relevant), for graded
metrics like nDCG. This module deliberately does not use it - every id in
`expected_relevant_ids` (primary and secondary together) counts as equally
"relevant" for P@1/R@5/MRR, a *binary* relevance judgment. That is a real
simplification (a primary match and a secondary match count the same), kept
because it is what corpus_v1.md's own baseline table already used and it is
enough to compare six retrieval methods against each other. Building a
graded metric on top of `relevance_grades` is exactly the kind of thing
`docs/corpus-v1.md`'s "suggested next steps" leaves for later.

**Why these three metrics and not more.** P@1, R@5, and MRR are the three
Day 7's design doc names, and each answers a different question a
procurement stakeholder would actually ask:

- P@1 - "if I only look at the first answer, is it right?"
- R@5 - "if I'm willing to skim five results, how much of what I need is
  there?" (most queries have 1-4 relevant documents - see `docs/corpus-v1.md`
  - so R@5 is rarely saturated the way R@1 trivially would be)
- MRR - "on average, how far do I have to scroll before I hit something
  useful?" - rewards a relevant result at rank 1 fully, rank 2 half credit,
  and so on, which P@1 (all-or-nothing at rank 1) and R@5 (all-or-nothing
  membership in the top 5) cannot capture on their own.

**Why "MRR@10", not plain "MRR".** `reciprocal_rank` itself (below) will
happily search an unbounded list, but `main()` truncates every method's
ranked list to `RETRIEVAL_DEPTH=10` *before* calling it - so a relevant
document that would have been found at, say, rank 14 scores 0.0 here, the
same as if it were never found at all. That is a real, if minor, source of
score compression versus true (unbounded) MRR, and worth naming rather than
letting "MRR" imply something this table doesn't quite compute.
"""


def precision_at_1(retrieved_ids, relevant_ids):
    """1.0 if the first retrieved id is relevant, else 0.0.

    `retrieved_ids` is a ranked list, best result first - exactly the shape
    every retriever in this repo already returns (`[r["id"] for r in ...]`).
    An empty `retrieved_ids` (no results at all for the query) scores 0.0,
    same as any other wrong top-1: there was no correct answer to show.
    """
    if not retrieved_ids:
        return 0.0
    return 1.0 if retrieved_ids[0] in relevant_ids else 0.0


def recall_at_k(retrieved_ids, relevant_ids, k=5):
    """Fraction of the known relevant ids that appear anywhere in the top k.

        recall@k = |{retrieved top k} intersect {relevant}| / |relevant|

    Returns `None`, not `0.0`, when `relevant_ids` is empty - there is no
    ground truth to measure recall against, so "0% recall" would misreport a
    query that has no gold answer as a retrieval failure. Every query in the
    v1 golden set has at least one relevant id (see `docs/corpus-v1.md`'s
    verification notes), so this should not trigger in practice; it is
    defensive, not something today's evaluation relies on hitting.
    """
    if not relevant_ids:
        return None

    top_k_ids = set(retrieved_ids[:k])
    found = len(top_k_ids & set(relevant_ids))
    return found / len(relevant_ids)


def reciprocal_rank(retrieved_ids, relevant_ids):
    """1 / (rank of the first relevant id); 0.0 if none of `retrieved_ids`
    is relevant.

    Rank is 1-indexed (the first result is "rank 1"), matching how a person
    would actually count down a results list. A relevant result at rank 1
    scores 1.0, rank 2 scores 0.5, rank 10 scores 0.1, and so on - MRR
    rewards a relevant result appearing *early* far more than it punishes it
    appearing merely somewhere in a long list.
    """
    for rank, document_id in enumerate(retrieved_ids, start=1):
        if document_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def rollup_chunks_to_documents(chunk_results, document_id_key="document_id"):
    """Turn a ranked chunk-result list into a ranked, de-duplicated document-id list.

    Day 7's design note (Block 2) sets the chunk-to-document scoring rule
    deliberately simply: "a chunk hit counts for its document_id; do not
    overcomplicate." Concretely: walk the ranked chunks best-first, and the
    first time a document is seen (via its best-ranked chunk), record it -
    that becomes the document's position in the rolled-up ranking. A later,
    lower-ranked chunk from a document already recorded adds nothing further
    (no "average the chunk ranks" or "sum chunk scores" - a document either
    has already earned its place from an earlier, better chunk, or it
    hasn't yet).

    This is what lets "Dense chunk->document retrieval" be scored with the
    exact same `precision_at_1`/`recall_at_k`/`reciprocal_rank` functions
    above as the whole-document methods: those functions only know about
    ranked document ids, and this function is the adapter that produces one
    from chunk-level search output.
    """
    seen_document_ids = set()
    document_ids = []
    for chunk_result in chunk_results:
        document_id = chunk_result[document_id_key]
        if document_id not in seen_document_ids:
            seen_document_ids.add(document_id)
            document_ids.append(document_id)
    return document_ids


def evaluate_method(retrieve_fn, queries, k_for_recall=5):
    """Run `retrieve_fn` over every query and average P@1 / R@5 / MRR.

    `retrieve_fn(query_row) -> [document_id, ...]` (ranked, best first) is
    the one thing each caller adapts per method - see `main()` below for six
    small closures, one per retrieval method, all built from functions
    already defined in `retrieval.py`/`semantic_search.py`/`chunked_search.py`/
    `hybrid_search.py`. `query_row` is one row from
    `hybrid_search.load_example_queries()`, so `retrieve_fn` reads
    `query_row["query"]` and this function reads `query_row["expected_relevant_ids"]`.

    Returns one dict per method: the method scored, how many queries it was
    evaluated over, and the three averaged metrics - ready to become one row
    of `docs/eval-report.md`'s baseline table.
    """
    precision_scores = []
    recall_scores = []
    reciprocal_rank_scores = []

    for query_row in queries:
        relevant_ids = query_row["expected_relevant_ids"]
        retrieved_ids = retrieve_fn(query_row)

        precision_scores.append(precision_at_1(retrieved_ids, relevant_ids))
        reciprocal_rank_scores.append(reciprocal_rank(retrieved_ids, relevant_ids))

        recall_score = recall_at_k(retrieved_ids, relevant_ids, k=k_for_recall)
        if recall_score is not None:
            recall_scores.append(recall_score)

    return {
        "n_queries": len(queries),
        "p_at_1": sum(precision_scores) / len(precision_scores),
        "r_at_5": sum(recall_scores) / len(recall_scores) if recall_scores else 0.0,
        "mrr": sum(reciprocal_rank_scores) / len(reciprocal_rank_scores),
    }


def main() -> None:
    """Build every index once, then evaluate the six required Day 7 baseline
    rows, two chunk-level hybrid rows, and Day 8's cross-encoder reranked
    row over the full 93-query v1 golden set, and print a markdown-ready
    table.

    The two chunk-level hybrid rows (`Hybrid RRF chunk->document`, `Hybrid
    weighted chunk->document`) go past Day 7's minimum six-row table:
    `HybridSearch` already supports `id_key="chunk_id"` fusion (Day 6's
    chunk-level demo), `chunked_search.py` already has BM25-over-chunks, and
    `rollup_chunks_to_documents` already exists for the "Dense
    chunk->document" row - the missing piece was wiring BM25-over-chunks and
    dense-over-chunks *through* `HybridSearch` and rolling the fused chunk
    ranking up to documents, not any new retrieval or fusion logic.

    The last row (`Cross-encoder reranked Hybrid RRF chunk->document`) is
    Day 8's addition: `reranking.two_stage_rerank` reruns the exact same
    chunk-level Hybrid RRF shortlist as the row above it, then reranks that
    shortlist with a cross-encoder before rolling up to documents - see
    `src/reranking.py`'s module docstring for why this specific baseline
    (not whole-document hybrid) is the fair one to rerank against.

    **Unfiltered text retrieval only** - none of the closures below read
    `query_row["metadata_filters"]`. See this module's docstring for why a
    filtered baseline isn't a simple addition here.

    This is the script that produced the numbers in `docs/eval-report.md` -
    re-run it after any change to the corpus, the query set, or the
    retrieval/fusion/reranking code, and refresh that table if the numbers
    move.
    """
    from chunked_search import (
        build_chunk_lexical_index,
        build_chunk_semantic_index,
        search_bm25_chunks,
        search_semantic_chunks,
    )
    from chunking import chunk_corpus
    from hybrid_search import CANDIDATE_POOL_SIZE, HybridSearch, load_example_queries
    from preprocessing import load_data
    from reranking import load_cross_encoder, two_stage_rerank
    from retrieval import build_index, search, search_bm25
    from semantic_search import build_semantic_index, load_embedding_model, search_semantic

    data = load_data()
    queries = load_example_queries()

    # Every retriever's *index* is built exactly once and reused for all 93
    # queries - only the (cheap, corpus-independent) query encoding happens
    # per query below. `search_bm25`/`search_semantic` are called fresh
    # inside each closure rather than cached, since each method needs its
    # own `top_k`/candidate-pool shape; for 93 short queries on this small
    # corpus that repetition costs a modest amount of wall-clock time, not
    # correctness, and keeping each method's closure self-contained and
    # readable is worth more here than shaving that time off.
    bm25_index = build_index(data)
    model = load_embedding_model()
    semantic_index = build_semantic_index(data, model)
    chunks = chunk_corpus(data)
    chunk_semantic_index = build_chunk_semantic_index(chunks, model)
    # BM25-over-chunks index, the chunk-level counterpart to `bm25_index`
    # above - reused by `hybrid_search.py`'s own Day 6 chunk-level demo, and
    # the missing piece that makes a chunk-level hybrid *row* possible here.
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    # Day 8: the cross-encoder reranker, loaded once (same reason `model`
    # above is loaded once) and reused for all 93 queries' shortlists - see
    # `reranking.load_cross_encoder`'s docstring for why this is forced onto
    # CPU rather than left to auto-detect an accelerator.
    cross_encoder_model = load_cross_encoder()

    # How deep each method's *final* ranked list goes before P@1/R@5/MRR are
    # computed. 10 comfortably covers R@5 (which only looks at the top 5
    # anyway) while giving MRR room to find a relevant document that landed
    # just past rank 5 instead of silently scoring 0.0 for it.
    RETRIEVAL_DEPTH = 10

    def tfidf_retrieve(query_row):
        results = search(bm25_index, query_row["query"], top_k=RETRIEVAL_DEPTH)
        return [result["id"] for result in results]

    def bm25_retrieve(query_row):
        results = search_bm25(bm25_index, query_row["query"], top_k=RETRIEVAL_DEPTH)
        return [result["id"] for result in results]

    def dense_retrieve(query_row):
        results = search_semantic(
            semantic_index, query_row["query"], model, top_k=RETRIEVAL_DEPTH
        )
        return [result["id"] for result in results]

    def dense_chunk_retrieve(query_row):
        # Ask for more chunks than RETRIEVAL_DEPTH documents, since several
        # top-ranked chunks often come from the same document and get
        # collapsed to one entry by rollup_chunks_to_documents - requesting
        # only RETRIEVAL_DEPTH chunks could under-fill the rolled-up list.
        chunk_results = search_semantic_chunks(
            chunk_semantic_index, query_row["query"], model, top_k=CANDIDATE_POOL_SIZE
        )
        return rollup_chunks_to_documents(chunk_results)[:RETRIEVAL_DEPTH]

    def hybrid_rrf_retrieve(query_row):
        bm25_results = search_bm25(
            bm25_index, query_row["query"], top_k=CANDIDATE_POOL_SIZE
        )
        semantic_results = search_semantic(
            semantic_index, query_row["query"], model, top_k=CANDIDATE_POOL_SIZE
        )
        hybrid = HybridSearch(bm25_results, semantic_results)
        return [result["id"] for result in hybrid.rrf(top_k=RETRIEVAL_DEPTH)]

    def hybrid_weighted_retrieve(query_row):
        bm25_results = search_bm25(
            bm25_index, query_row["query"], top_k=CANDIDATE_POOL_SIZE
        )
        semantic_results = search_semantic(
            semantic_index, query_row["query"], model, top_k=CANDIDATE_POOL_SIZE
        )
        hybrid = HybridSearch(bm25_results, semantic_results)
        return [result["id"] for result in hybrid.weighted(top_k=RETRIEVAL_DEPTH)]

    def _chunk_hybrid_retrieve(query, fuse):
        """Shared retrieval step for the two chunk-level hybrid rows below.

        Mirrors `hybrid_rrf_retrieve`/`hybrid_weighted_retrieve` above, but
        over chunks (`id_key="chunk_id"`) instead of whole documents - the
        same `HybridSearch` class, same fusion math, just a different
        retrieval unit feeding it (exactly the point of `id_key` - see
        `hybrid_search.py`'s own chunk-level demo in `main()`). `fuse` is
        `lambda h: h.rrf(...)` or `lambda h: h.weighted(...)`, so this one
        function serves both rows without duplicating the chunk retrieval
        and rollup steps twice.

        `HybridSearch`'s fused output only ever carries `chunk_id` and
        per-method scores (see `hybrid_search.py`'s module docstring) - it
        never copies through `document_id`, since the fusion math has no way
        to know which extra fields are worth carrying along. `document_id`
        is looked back up via `chunk_lexical_index` before
        `rollup_chunks_to_documents` can do its job, the same pattern
        `hybrid_search.py`'s `_print_chunk_results` uses for display.
        """
        chunk_bm25_results = search_bm25_chunks(
            chunk_lexical_index, query, top_k=CANDIDATE_POOL_SIZE
        )
        chunk_semantic_results = search_semantic_chunks(
            chunk_semantic_index, query, model, top_k=CANDIDATE_POOL_SIZE
        )
        hybrid = HybridSearch(
            chunk_bm25_results, chunk_semantic_results, id_key="chunk_id"
        )
        fused_chunks = fuse(hybrid)
        chunks_with_document_id = [
            {
                **result,
                "document_id": chunk_lexical_index["chunks"][result["chunk_id"]][
                    "document_id"
                ],
            }
            for result in fused_chunks
        ]
        return rollup_chunks_to_documents(chunks_with_document_id)[:RETRIEVAL_DEPTH]

    def hybrid_rrf_chunk_retrieve(query_row):
        return _chunk_hybrid_retrieve(
            query_row["query"], lambda hybrid: hybrid.rrf(top_k=CANDIDATE_POOL_SIZE)
        )

    def hybrid_weighted_chunk_retrieve(query_row):
        return _chunk_hybrid_retrieve(
            query_row["query"],
            lambda hybrid: hybrid.weighted(top_k=CANDIDATE_POOL_SIZE),
        )

    def cross_encoder_reranked_chunk_retrieve(query_row):
        # Day 8: rerank the exact same chunk-level Hybrid RRF shortlist the
        # row above this one uses (`two_stage_rerank` calls
        # `build_chunk_shortlist`, which fuses BM25-over-chunks +
        # dense-over-chunks with the same CANDIDATE_POOL_SIZE pool), then
        # rolls the reranked chunks up to documents the same way every other
        # chunk-level row does. Unlike `_chunk_hybrid_retrieve` above, no
        # manual document_id lookup is needed here - `build_chunk_shortlist`
        # already attaches `document_id` to every candidate, and `rerank`
        # preserves it through onto the result (see `reranking.py`).
        reranked_chunks = two_stage_rerank(
            query_row["query"],
            chunk_lexical_index,
            chunk_semantic_index,
            model,
            cross_encoder_model,
        )
        return rollup_chunks_to_documents(reranked_chunks)[:RETRIEVAL_DEPTH]

    methods = [
        ("TF-IDF (document)", tfidf_retrieve),
        ("BM25 (document)", bm25_retrieve),
        ("Dense (document)", dense_retrieve),
        ("Dense chunk->document", dense_chunk_retrieve),
        ("Hybrid RRF (document)", hybrid_rrf_retrieve),
        ("Hybrid weighted (document)", hybrid_weighted_retrieve),
        ("Hybrid RRF chunk->document", hybrid_rrf_chunk_retrieve),
        ("Hybrid weighted chunk->document", hybrid_weighted_chunk_retrieve),
        (
            "Cross-encoder reranked Hybrid RRF chunk->document",
            cross_encoder_reranked_chunk_retrieve,
        ),
    ]

    print(f"v1 baseline (unfiltered text retrieval): {len(queries)} queries, "
          f"{len(data)} documents, {len(chunks)} chunks, "
          f"retrieval depth={RETRIEVAL_DEPTH}, "
          f"candidate pool={CANDIDATE_POOL_SIZE}\n")
    print(f"| {'Method':<32} | {'P@1':>5} | {'R@5':>5} | {'MRR@10':>6} |")
    print(f"|{'-'*34}|{'-'*7}|{'-'*7}|{'-'*8}|")
    for name, retrieve_fn in methods:
        result = evaluate_method(retrieve_fn, queries)
        print(
            f"| {name:<32} | {result['p_at_1']:.3f} | "
            f"{result['r_at_5']:.3f} | {result['mrr']:.3f} |"
        )


if __name__ == "__main__":
    main()
