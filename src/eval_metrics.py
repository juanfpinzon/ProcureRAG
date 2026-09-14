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

**Day 9 addition: graded relevance, filter-adjusted gold sets, and error
slices.** Everything above this note is unchanged from Day 7/8 - binary
relevance, no metadata filtering. Three new, separate sections below build
on top of it instead of replacing it:

1. `discounted_cumulative_gain` / `ndcg_at_k` / `grades_for_query` /
   `evaluate_ndcg` - a *graded* metric that finally uses `relevance_grades`
   (this docstring's "What 'relevant' means here" note above explained why
   P@1/R@5/MRR deliberately don't - that reasoning still holds for those
   three; nDCG is a different question, "did the system rank the *best*
   evidence first", that binary metrics cannot answer at all).
2. `filter_adjusted_relevant_ids` / `filter_adjusted_grades` /
   `build_filtered_queries` - a fair ground truth for the 21 v1 queries that
   carry a `metadata_filters` value, so a retriever that correctly filters
   out a secondary document the query's own filter excludes is not scored
   as if it had missed a real answer.
3. `slice_queries` / `evaluate_slices` / `primary_count` - group queries by
   a shared property (query type, difficulty, filtered/unfiltered, single-
   vs-multi-primary) and evaluate each group separately, so an aggregate
   number can't hide which class of query a method is actually weak on.

`main()` wires all three into new, clearly-labeled tables alongside the
original binary one - see that function's docstring for the full list.
"""

# `math.log2` for `discounted_cumulative_gain`'s rank discount, and
# `hybrid_search.matches_filters` for the filter-adjusted gold-set
# functions below - both cheap, dependency-free imports (no model
# download, no heavy transitive imports), unlike the retrieval/index
# builders `main()` needs, which stay as local imports inside `main()`
# itself (see that function's docstring for why: importing
# `sentence_transformers` etc. at module level would make every test in
# `tests/test_eval_metrics.py` pay for a model-capable import just to test
# a pure arithmetic function like `precision_at_1`).
import math

from hybrid_search import matches_filters


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


# ---------------------------------------------------------------------------
# Day 9: graded relevance (nDCG@k)
#
# Every metric above (precision_at_1 / recall_at_k / reciprocal_rank) treats
# "relevant" as one binary bucket - a query's grade-2 "primary" document and
# its grade-1 "secondary" document(s) all count exactly the same. That is a
# real simplification: a system that ranks the primary document first
# *should* score better than one that ranks a merely-related secondary
# document first, and no binary metric can see that difference at all.
#
# Normalized Discounted Cumulative Gain (nDCG) fixes this by scoring a
# ranked list against per-document *gains* (the corpus's own
# `relevance_grades`: 2 = primary, 1 = secondary, missing = 0 = not judged
# relevant) instead of a single relevant/not-relevant flag, and by
# discounting gains that show up lower in the ranking - a primary document
# at rank 1 counts in full, the same document at rank 5 counts for much
# less, reflecting that a user is steadily less likely to actually read
# that far down a results list.
# ---------------------------------------------------------------------------


def discounted_cumulative_gain(gains):
    """DCG = sum_i gain_i / log2(i + 1), for rank i = 1, 2, 3, ... (1-indexed).

    `gains` is already a ranked list - `gains[0]` is the gain of whatever is
    ranked first, `gains[1]` the gain of whatever is ranked second, and so
    on; it is the caller's job (`ndcg_at_k` below) to turn a ranked id list
    into a ranked gain list first. The discount `log2(i + 1)` is `1.0` at
    rank 1 (`log2(2) == 1`, so the top-ranked gain always counts in full)
    and grows slowly as rank increases - `log2(6) ~= 2.58` at rank 5,
    `log2(11) ~= 3.46` at rank 10 - so a relevant document further down the
    list still contributes something, just steadily less. `i + 1`, not
    plain `i`, is what keeps rank 1 from dividing by `log2(1) == 0`.
    """
    return sum(
        gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1)
    )


def ndcg_at_k(retrieved_ids, grades, k=5):
    """Normalized DCG@k: DCG@k of the actual ranking, divided by DCG@k of
    the *ideal* ranking for this query (every graded document, best grade
    first). A score of 1.0 means the actual ranking put the best possible
    grades into the top k slots, in the best possible order; 0.0 means
    nothing relevant showed up in the top k at all.

    `grades` is `{document_id: relevance_grade}` (see `grades_for_query`
    below). Any id in `retrieved_ids` that is *not* a key in `grades` -
    including one that was never judged for this query at all - is treated
    as gain 0, the same as a document nobody ever marked relevant; that
    lookup uses `.get(document_id, 0)` rather than requiring every corpus
    document to have an explicit zero entry.

    Ties, missing ids, an empty retrieved list, and a perfect ranking are
    all exercised in `tests/test_eval_metrics.py`.
    """
    actual_gains = [grades.get(document_id, 0) for document_id in retrieved_ids[:k]]
    dcg = discounted_cumulative_gain(actual_gains)

    # The ideal ranking for THIS query: every graded document, best grade
    # first. Ties don't matter here - two documents with the same grade
    # contribute the same DCG term regardless of which one is placed first
    # among the ties - and the list is padded implicitly by slicing to `k`,
    # exactly like the actual ranking above (a query with only 2 graded
    # documents simply has a 2-gain ideal ranking for k=5, not a padded-
    # with-zeros 5-gain one, since appending explicit zeros would not
    # change discounted_cumulative_gain's sum anyway).
    ideal_gains = sorted(grades.values(), reverse=True)[:k]
    ideal_dcg = discounted_cumulative_gain(ideal_gains)

    # No relevant document exists for this query at all (every grade is 0,
    # or `grades` is empty) - there is no ideal ranking to normalize
    # against, so nDCG is undefined, the same way recall_at_k above is
    # undefined for a query with no ground truth. 0.0 here (rather than
    # raising) keeps this usable inside evaluate_ndcg's average without
    # every caller needing a special case; every query in the v1 set has at
    # least one graded document, so this branch is defensive, not something
    # today's evaluation relies on hitting.
    if ideal_dcg == 0.0:
        return 0.0

    return dcg / ideal_dcg


def grades_for_query(query_row):
    """Return {document_id: relevance_grade} for one query.

    A direct pass-through of `query_row["relevance_grades"]` - already
    exactly the shape `ndcg_at_k` needs. Kept as its own named function
    (instead of every caller reading `query_row["relevance_grades"]`
    directly) so the *intent* - "the graded ground truth for this query" -
    reads the same way `query_row["expected_relevant_ids"]` reads for the
    binary metrics above, and so a future change to how grades are stored
    on a query row only has one call site to update.
    """
    return query_row["relevance_grades"]


def evaluate_ndcg(retrieve_fn, queries, k=5):
    """Average nDCG@k across `queries` for one retrieval method.

    Mirrors `evaluate_method` above, but for the graded metric instead of
    the three binary ones. Kept as its own small function rather than folded
    into `evaluate_method` itself: `evaluate_method`'s existing callers
    (this module's own tests, and every synthetic query used there) only
    ever carry `expected_relevant_ids`, not `relevance_grades` - changing
    `evaluate_method`'s contract to also require grades would break those
    callers for no benefit they need.
    """
    if not queries:
        return 0.0

    scores = [
        ndcg_at_k(retrieve_fn(query_row), grades_for_query(query_row), k=k)
        for query_row in queries
    ]
    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# Day 9: filter-adjusted gold sets for filtered evaluation
#
# `hybrid_search.filter_ranked_results` can filter a *retrieved* ranked list
# by metadata - but scoring that filtered ranking against the *unfiltered*
# `expected_relevant_ids` would be unfair. 17 of the 21 v1 queries that
# carry a `metadata_filters` value have at least one expected id that the
# query's OWN filter would exclude (e.g. Q001 expects `FAQ-001` as a
# secondary answer, but its filter is `doc_type: policy`, and FAQ-001 is a
# FAQ, not a policy - see `docs/eval-report.md`'s "Metadata filtering"
# section). A retriever that correctly drops FAQ-001 under that filter is
# behaving exactly as asked and should not be penalized as if it had missed
# a real answer.
#
# The fix: build a *filter-adjusted* gold set per query first - keep only
# the expected ids (and grades) whose OWN document metadata satisfies the
# query's OWN filter - and score filtered retrieval against that adjusted
# set, not the original one.
# ---------------------------------------------------------------------------


def filter_adjusted_relevant_ids(query_row, documents_by_id):
    """Return the subset of `expected_relevant_ids` whose document matches
    the query's own `metadata_filters`.

    `documents_by_id` is `hybrid_search.build_metadata_index(data)` -
    `{document_id: raw_corpus_row}` - the exact lookup `filter_ranked_results`
    already uses to check a *retrieved* document's metadata; this checks
    each *expected* (gold) document's metadata against that same
    `matches_filters` rule instead, so "does this document match the
    filter" means the identical thing on both the retrieved side and the
    gold side.

    An empty `metadata_filters` (the common no-filter case) returns every
    expected id unchanged - there is nothing to adjust for.
    """
    filters = query_row["metadata_filters"]
    if not filters:
        return list(query_row["expected_relevant_ids"])

    return [
        document_id
        for document_id in query_row["expected_relevant_ids"]
        if document_id in documents_by_id
        and matches_filters(documents_by_id[document_id], filters)
    ]


def filter_adjusted_grades(query_row, documents_by_id):
    """Same idea as `filter_adjusted_relevant_ids`, but for
    `relevance_grades` - keeps only the `{document_id: grade}` entries
    whose document matches the query's own filter. This is what a
    filter-adjusted nDCG would score against, the graded counterpart to
    `filter_adjusted_relevant_ids`'s binary gold set.
    """
    filters = query_row["metadata_filters"]
    grades = query_row["relevance_grades"]
    if not filters:
        return dict(grades)

    return {
        document_id: grade
        for document_id, grade in grades.items()
        if document_id in documents_by_id
        and matches_filters(documents_by_id[document_id], filters)
    }


def build_filtered_queries(queries, documents_by_id):
    """Return only the queries that carry a `metadata_filters` value (21 of
    the 93 in the v1 set), with `expected_relevant_ids`/`relevance_grades`
    replaced by their filter-adjusted versions.

    This is what lets the *existing* `evaluate_method`/`evaluate_ndcg`
    above score filtered retrieval correctly, completely unmodified: those
    functions only ever read `query_row["expected_relevant_ids"]` /
    `grades_for_query(query_row)`, so handing them a query row whose gold
    fields are already filter-adjusted is enough - no second, filtered code
    path needed inside either metric function.

    This only adjusts the *ground truth*. `retrieve_fn` passed to
    `evaluate_method`/`evaluate_ndcg` for these rows still has to be a
    retriever that itself actually applies the query's filter to what it
    retrieves - see `main()`'s filtered retrieval closures below - otherwise
    this would be comparing filtered gold against unfiltered retrieval,
    which answers a different, less interesting question ("did the
    retriever also happen to rank in-scope documents highly" rather than
    "how good is filtered retrieval").
    """
    filtered_queries = []
    for query_row in queries:
        if not query_row["metadata_filters"]:
            continue
        adjusted_query_row = dict(query_row)
        adjusted_query_row["expected_relevant_ids"] = filter_adjusted_relevant_ids(
            query_row, documents_by_id
        )
        adjusted_query_row["relevance_grades"] = filter_adjusted_grades(
            query_row, documents_by_id
        )
        filtered_queries.append(adjusted_query_row)
    return filtered_queries


# ---------------------------------------------------------------------------
# Day 9: error slices
#
# One aggregate P@1/R@5/MRR/nDCG number across all 93 queries can hide which
# *kind* of query a method is actually weak on. Grouping queries by a
# shared property first, then evaluating each group separately with the
# exact same `evaluate_method`/`evaluate_ndcg` functions above, turns "the
# average looks fine" into "the average looks fine because strength on
# lookup queries is masking weakness on numeric queries" - the difference
# between a score and an actual engineering roadmap.
# ---------------------------------------------------------------------------


def slice_queries(queries, key_fn):
    """Group `queries` into `{slice_key: [query_row, ...]}` via `key_fn`.

    `key_fn(query_row) -> slice_key` is the one thing each caller supplies -
    `lambda q: q["query_type"]`, `lambda q: q["difficulty"]`,
    `lambda q: bool(q["metadata_filters"])`, or anything else that reads a
    property already on the query row. This function itself knows nothing
    about what those properties mean; it only buckets by whatever key comes
    back, preserving each query's original order within its own bucket.
    """
    slices = {}
    for query_row in queries:
        slices.setdefault(key_fn(query_row), []).append(query_row)
    return slices


def evaluate_slices(retrieve_fn, queries, key_fn, k_for_recall=5):
    """Run `evaluate_method` separately per slice of `queries`.

    Returns `{slice_key: evaluate_method(...) result}` - one full
    n_queries/p_at_1/r_at_5/mrr dict per slice, so a slice with only a
    handful of queries is never silently averaged away inside one overall
    number.
    """
    return {
        slice_key: evaluate_method(retrieve_fn, slice_rows, k_for_recall=k_for_recall)
        for slice_key, slice_rows in slice_queries(queries, key_fn).items()
    }


def primary_count(query_row):
    """How many grade-2 ("primary") documents this query has.

    Used to slice queries into "single-primary" (one clear best answer) vs.
    "multi-primary" (several documents equally deserve the top spot) - a
    distinction P@1 in particular should care about, since P@1 only ever
    checks whether *a* primary document is first, never which one, and a
    multi-primary query gives a retriever more ways to be right at rank 1.
    """
    grades = grades_for_query(query_row)
    return sum(1 for grade in grades.values() if grade == 2)


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

    **Unfiltered text retrieval only, for the methods above** - none of the
    nine closures below read `query_row["metadata_filters"]`. See this
    module's docstring for why a filtered baseline isn't a simple addition
    on top of them; Day 9 adds one as its own, separate section below
    instead (`_filtered_chunk_shortlist` and its two retrieve functions).

    This prints four things, in order, each labeled precisely because they
    answer different questions and are not comparable to each other:

    1. **Binary unfiltered** - the original Day 7/8 nine-row table
       (P@1/R@5/MRR@10, binary relevance, full 93-query set).
    2. **Graded unfiltered** (Day 9) - the same nine methods, same 93
       queries, scored with nDCG@5 instead (`evaluate_ndcg`) - does each
       method rank the *best* evidence first, not just *some* relevant
       evidence.
    3. **Filtered-adjusted** (Day 9) - only the 21 queries with a
       `metadata_filters` value, scored with P@1/R@5/MRR@10 against a
       *filter-adjusted* gold set (`build_filtered_queries`), for two
       retrievers that actually apply the filter before scoring
       (`filtered_hybrid_rrf_chunk_retrieve`,
       `filtered_cross_encoder_reranked_chunk_retrieve`).
    4. **Error slices** (Day 9) - the same two methods' *unfiltered* P@1/
       R@5/MRR@10, grouped by query type, difficulty, filtered-vs-
       unfiltered, and single-vs-multi-primary, plus one "largest weak
       slice" summary line.

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
    from hybrid_search import (
        CANDIDATE_POOL_SIZE,
        HybridSearch,
        build_metadata_index,
        filter_ranked_results,
        load_example_queries,
    )
    from preprocessing import load_data
    from reranking import load_cross_encoder, rerank_with_cross_encoder, two_stage_rerank
    from retrieval import build_index, search, search_bm25
    from semantic_search import build_semantic_index, load_embedding_model, search_semantic

    data = load_data()
    queries = load_example_queries()
    # Day 9: {document_id: raw_corpus_row} - the same lookup
    # `hybrid_search.filter_ranked_results` uses to check a retrieved
    # document's metadata, reused here for the gold side too (see
    # `filter_adjusted_relevant_ids`) and for the filtered retrieval
    # closures below.
    documents_by_id = build_metadata_index(data)

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

    # Day 9: every method below gets evaluated 2-6 times over the same
    # 93-query set (the binary table, the graded table, and - for the two
    # "key methods" - four error-slice tables each). Without caching, that
    # means re-running the same retrieval for the same query up to six
    # times - for the cross-encoder reranked method specifically, six full
    # passes of ~9s of cross-encoder scoring instead of one. Wrapping every
    # retrieve_fn to cache by query_id makes every table after the first
    # one that touches a given method effectively free, with zero change
    # to what any of them compute.
    def _memoize_by_query_id(retrieve_fn):
        cache = {}

        def wrapped(query_row):
            query_id = query_row["query_id"]
            if query_id not in cache:
                cache[query_id] = retrieve_fn(query_row)
            return cache[query_id]

        return wrapped

    methods = [(name, _memoize_by_query_id(fn)) for name, fn in methods]

    print(f"v1 baseline: {len(queries)} queries, "
          f"{len(data)} documents, {len(chunks)} chunks, "
          f"retrieval depth={RETRIEVAL_DEPTH}, "
          f"candidate pool={CANDIDATE_POOL_SIZE}\n")

    print("=== Binary unfiltered (P@1 / R@5 / MRR@10, relevance_grades unused) ===")
    print(f"| {'Method':<50} | {'P@1':>5} | {'R@5':>5} | {'MRR@10':>6} |")
    print(f"|{'-'*52}|{'-'*7}|{'-'*7}|{'-'*8}|")
    binary_results = {}
    for name, retrieve_fn in methods:
        result = evaluate_method(retrieve_fn, queries)
        binary_results[name] = result
        print(
            f"| {name:<50} | {result['p_at_1']:.3f} | "
            f"{result['r_at_5']:.3f} | {result['mrr']:.3f} |"
        )

    # -----------------------------------------------------------------
    # Day 9: graded unfiltered (nDCG@5) - same 9 methods, same 93 queries,
    # a different question: not "was *a* relevant document retrieved" but
    # "was the *best* evidence ranked first". See this module's docstring
    # and `docs/eval-report.md` for what moves and what doesn't between
    # this table and the binary one above.
    # -----------------------------------------------------------------
    print("\n=== Graded unfiltered (nDCG@5, uses relevance_grades) ===")
    print(f"| {'Method':<50} | {'nDCG@5':>6} |")
    print(f"|{'-'*52}|{'-'*8}|")
    for name, retrieve_fn in methods:
        ndcg_score = evaluate_ndcg(retrieve_fn, queries, k=5)
        print(f"| {name:<50} | {ndcg_score:.3f} |")

    # -----------------------------------------------------------------
    # Day 9: filtered-adjusted - only the 21 queries with a metadata_filters
    # value, scored against a filter-adjusted gold set (build_filtered_queries)
    # rather than the raw expected_relevant_ids. See this module's docstring
    # ("filter-adjusted gold sets") for why reusing the unfiltered gold set
    # here would unfairly penalize a retriever for correctly respecting the
    # filter.
    # -----------------------------------------------------------------
    filtered_queries_raw = [q for q in queries if q["metadata_filters"]]
    filtered_queries_adjusted = build_filtered_queries(queries, documents_by_id)
    # Auditability: how many of those 21 queries actually had a gold id
    # excluded by their own filter - the number this whole methodology
    # exists to handle fairly, not hide.
    queries_losing_a_gold_id = sum(
        1
        for query_row in filtered_queries_raw
        if len(filter_adjusted_relevant_ids(query_row, documents_by_id))
        < len(query_row["expected_relevant_ids"])
    )
    print(
        f"\n=== Filtered-adjusted (P@1 / R@5 / MRR@10, "
        f"{len(filtered_queries_raw)} queries with metadata_filters) ==="
    )
    print(
        f"{queries_losing_a_gold_id}/{len(filtered_queries_raw)} of those queries have "
        "at least one expected_relevant_ids entry excluded by their own filter "
        "(dropped from the gold set below, not counted as a miss)."
    )

    total_chunk_count = chunk_lexical_index["chunk_count"]

    def _filtered_chunk_shortlist(query_row):
        """Chunk-level Hybrid RRF shortlist, filtered by the query's own
        `metadata_filters` - the filtered first stage both filtered
        retrieve functions below build on.

        Mirrors `reranking.build_chunk_shortlist`, but inserts metadata
        filtering between retrieval and fusion, the same "filter the FULL
        ranked list, then slice to the pool size" rule
        `hybrid_search.filter_ranked_results`'s own docstring requires -
        filtering only `CANDIDATE_POOL_SIZE` candidates can silently drop a
        real relevant document that ranks just outside that narrow pool
        (see that docstring for the exact Day 7 regression this caused, and
        `tests/test_hybrid_search.py`'s regression test for it). Kept as a
        local closure here rather than a `filters=` parameter added to
        `build_chunk_shortlist` itself, since only this Day 9 filtered path
        needs it.
        """
        query = query_row["query"]
        filters = query_row["metadata_filters"]

        # Every chunk in the corpus, not just CANDIDATE_POOL_SIZE - see the
        # docstring above for why filtering needs the full ranked list.
        bm25_full = search_bm25_chunks(chunk_lexical_index, query, top_k=total_chunk_count)
        semantic_full = search_semantic_chunks(
            chunk_semantic_index, query, model, top_k=total_chunk_count
        )

        # Filter each chunk by its PARENT document's metadata
        # (document_id_key="document_id" - a chunk carries no metadata of
        # its own), then cap back down to CANDIDATE_POOL_SIZE so fusion
        # below runs over the same-sized candidate set the unfiltered rows
        # use.
        bm25_filtered = filter_ranked_results(
            bm25_full,
            documents_by_id,
            filters,
            id_key="chunk_id",
            document_id_key="document_id",
            top_k=CANDIDATE_POOL_SIZE,
        )
        semantic_filtered = filter_ranked_results(
            semantic_full,
            documents_by_id,
            filters,
            id_key="chunk_id",
            document_id_key="document_id",
            top_k=CANDIDATE_POOL_SIZE,
        )

        hybrid = HybridSearch(bm25_filtered, semantic_filtered, id_key="chunk_id")
        fused = hybrid.rrf(top_k=CANDIDATE_POOL_SIZE)

        # Same shortlist shape `reranking.build_chunk_shortlist` produces,
        # so `rerank_with_cross_encoder` below can score it exactly the
        # same way as the unfiltered reranked row does.
        shortlist = []
        for first_stage_rank, result in enumerate(fused, start=1):
            chunk_id = result["chunk_id"]
            chunk = chunk_lexical_index["chunks"][chunk_id]
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

    def filtered_hybrid_rrf_chunk_retrieve(query_row):
        shortlist = _filtered_chunk_shortlist(query_row)
        return rollup_chunks_to_documents(shortlist)[:RETRIEVAL_DEPTH]

    def filtered_cross_encoder_reranked_chunk_retrieve(query_row):
        shortlist = _filtered_chunk_shortlist(query_row)
        reranked = rerank_with_cross_encoder(
            query_row["query"], shortlist, cross_encoder_model
        )
        return rollup_chunks_to_documents(reranked)[:RETRIEVAL_DEPTH]

    filtered_methods = [
        (
            "Hybrid RRF chunk->document (filtered)",
            _memoize_by_query_id(filtered_hybrid_rrf_chunk_retrieve),
        ),
        (
            "Cross-encoder reranked Hybrid RRF chunk->document (filtered)",
            _memoize_by_query_id(filtered_cross_encoder_reranked_chunk_retrieve),
        ),
    ]

    print(f"| {'Method':<62} | {'P@1':>5} | {'R@5':>5} | {'MRR@10':>6} |")
    print(f"|{'-'*64}|{'-'*7}|{'-'*7}|{'-'*8}|")
    for name, retrieve_fn in filtered_methods:
        result = evaluate_method(retrieve_fn, filtered_queries_adjusted)
        print(
            f"| {name:<62} | {result['p_at_1']:.3f} | "
            f"{result['r_at_5']:.3f} | {result['mrr']:.3f} |"
        )

    # -----------------------------------------------------------------
    # Day 9: error slices - the two most important methods in this report
    # (best first-stage row vs. best overall row), sliced by query type,
    # difficulty, filtered-vs-unfiltered, and single-vs-multi-primary, over
    # the FULL unfiltered 93-query set (these are the same memoized
    # retrieve_fn objects already scored in the binary table above, so this
    # costs no new retrieval calls at all - see _memoize_by_query_id).
    # -----------------------------------------------------------------
    key_method_names = [
        "Hybrid RRF chunk->document",
        "Cross-encoder reranked Hybrid RRF chunk->document",
    ]
    key_methods = [(name, fn) for name, fn in methods if name in key_method_names]
    slice_dimensions = [
        ("query_type", lambda q: q["query_type"]),
        ("difficulty", lambda q: q["difficulty"]),
        (
            "filtered vs. unfiltered",
            lambda q: "filtered" if q["metadata_filters"] else "unfiltered",
        ),
        (
            "single- vs. multi-primary",
            lambda q: "single-primary" if primary_count(q) == 1 else "multi-primary",
        ),
    ]

    print("\n=== Error slices (unfiltered P@1 / R@5 / MRR@10) ===")
    for method_name, retrieve_fn in key_methods:
        for dimension_name, key_fn in slice_dimensions:
            slice_results = evaluate_slices(retrieve_fn, queries, key_fn)
            print(f"\n{method_name} — by {dimension_name}")
            print(f"| {'Slice':<28} | {'n':>3} | {'P@1':>5} | {'R@5':>5} | {'MRR@10':>6} |")
            print(f"|{'-'*30}|{'-'*5}|{'-'*7}|{'-'*7}|{'-'*8}|")
            for slice_key in sorted(slice_results, key=str):
                result = slice_results[slice_key]
                print(
                    f"| {str(slice_key):<28} | {result['n_queries']:>3} | "
                    f"{result['p_at_1']:.3f} | {result['r_at_5']:.3f} | {result['mrr']:.3f} |"
                )

    # One compact summary line: of the reranked method's query_type slices,
    # which one is weakest on P@1, and how far below its own overall P@1 is
    # it - the "next fix should target this class of query" takeaway an
    # aggregate table alone can't give.
    reranked_name = "Cross-encoder reranked Hybrid RRF chunk->document"
    reranked_retrieve_fn = dict(methods)[reranked_name]
    by_query_type = evaluate_slices(reranked_retrieve_fn, queries, lambda q: q["query_type"])
    weakest_type, weakest_result = min(
        by_query_type.items(), key=lambda item: item[1]["p_at_1"]
    )
    overall_p_at_1 = binary_results[reranked_name]["p_at_1"]
    print(
        f"\nLargest weak slice ({reranked_name}, by query_type): "
        f"'{weakest_type}' — P@1 {weakest_result['p_at_1']:.3f} over "
        f"{weakest_result['n_queries']} queries, vs. {overall_p_at_1:.3f} overall. "
        "This is the query class the next retrieval/generation fix should target."
    )


if __name__ == "__main__":
    main()
