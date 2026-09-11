"""Day 6: combine BM25 (lexical) and semantic (dense) retrieval into one ranking.

`retrieval.py` and `semantic_search.py` each rank documents on their own. BM25
is a lexical ranker: it rewards exact token overlap, so it excels at PO
numbers, policy codes, currency amounts, and acronyms - but it cannot see past
the exact words a query uses. Semantic search is a dense ranker: it compares
embedding directions, so it excels at paraphrases - "approval required" can
match "sign-off needed" - but it can blur exact identifiers that lexical
search preserves. Neither method alone is enough for procurement queries that
mix both (e.g. "What approval is required for a EUR 60,000 purchase order?").

This module does not re-rank anything itself. It takes the *already-ranked*
output of `retrieval.search_bm25` and `semantic_search.search_semantic` - two
plain lists of `{"id": ..., "score": ...}` - and fuses them into one ranking.
The existing lexical and semantic modules are unchanged; this module only
consumes their output.

The hard part of fusing two rankers is that their raw scores are not
comparable: BM25 scores are unbounded positive reals whose scale depends on
corpus statistics, while cosine similarity from a normalized embedding model
lives in [0, 1] (in practice; the mathematical range is [-1, 1]). Averaging
`15.37` (a BM25 score) and `0.63` (a cosine score) directly would let
whichever number is bigger dominate the ranking for no principled reason -
that has nothing to do with which document is actually more relevant.

Two ways to combine the two rankings that both avoid that trap:

1. Reciprocal Rank Fusion (`rrf` below) ignores raw scores entirely and only
   looks at *rank position* - 1st place, 2nd place, and so on - in each
   retriever's list. Because "1st place" means the same thing regardless of
   whether the underlying score was a BM25 score or a cosine similarity, RRF
   sidesteps the score-scale problem completely. There's nothing to
   normalize.
2. Weighted combination (`weighted` below) normalizes each retriever's raw
   scores onto a shared [0, 1] scale first (min-max normalization), then
   blends the two normalized scores with a tunable weight alpha. This keeps
   the scores themselves interpretable ("70% semantic, 30% lexical") at the
   cost of an extra normalization step and a weight that has to be chosen.

Day 7 adds two things on top of the Day 6 fusion math above, both driven by
`docs/day-07-hybrid-consolidation-evals.md`:

1. `CANDIDATE_POOL_SIZE` (below) - a mitigation for the exact-tie weakness
   Day 6 found: a candidate present in only one retriever's *narrow* top-k
   list can tie exactly with another candidate present in only the other
   retriever's list, and the tie then falls back to alphabetical id, which
   carries no relevance information. See the constant's docstring for what
   this does and does not fix - it is a real but partial mitigation, not a
   claim that ties are now impossible.
2. Metadata filtering (`build_metadata_index`, `matches_filters`,
   `filter_ranked_results` below) - restricting candidates to documents that
   match fields like `doc_type`, `region`, or `supplier` before they reach
   `HybridSearch`. This still fuses "already-ranked lists" exactly as
   before; filtering only decides *which* ranked lists go in.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_QUERIES_PATH = PROJECT_ROOT / "data" / "corpus_v1" / "example_queries.jsonl"

# How many results each retriever (`search_bm25`, `search_semantic`, ...)
# should be asked for *before* the caller fuses them with `HybridSearch`,
# regardless of how many fused results the caller ultimately wants back.
#
# Day 6 found a real exact-tie pathology: if both retrievers are only asked
# for their top 3, a candidate that is genuinely the *best* result for one
# retriever but happens to fall just outside the other retriever's top 3 is
# indistinguishable, score-wise, from a candidate that is completely absent
# from that retriever's ranking - RRF and weighted combination both treat
# "not in the list I was given" as "no signal from this side" either way
# (see `_ranks_by_position` and `weighted`'s docstring). Two such candidates
# - one strong-on-BM25-only, one strong-on-semantic-only - can land on the
# exact same fused score and get resolved by alphabetical document id, which
# has nothing to do with relevance.
#
# Asking each retriever for more candidates up front (15, against a
# 34-document corpus) before fusing gives a candidate that was previously
# "invisible" on one side a real chance to show up somewhere further down
# that side's list too, contributing a small but genuine term instead of
# nothing. Verified this empirically on the Day 6 "vendor vetting" case
# (`docs/eval-report.md` has the numbers): the exact tie is gone at pool=15.
# It is *not* a complete fix, though - the same investigation found that
# widening the pool does not make the fused ranking *correct* when a
# document is missing from a retriever's list for a real reason (e.g. BM25
# finds zero shared vocabulary between "vendor vetting" and the correct
# policy document's actual wording) rather than merely a too-small top_k.
# That remaining gap is a reranking problem (Day 8), not a wider-top_k one.
CANDIDATE_POOL_SIZE = 15


def load_example_queries(path=EXAMPLE_QUERIES_PATH):
    """Load the v1 golden query set - one JSON object per line.

    This is `data/corpus_v1/example_queries.jsonl`, the file Day 7's design
    note (`docs/day-07-hybrid-consolidation-evals.md`, Block 2) names as the
    canonical query source, kept as-is rather than copied into a separate
    `data/golden_queries.jsonl`. Each row carries `query_id`, `query`,
    `expected_relevant_ids`, `relevance_grades`, `metadata_filters`, and
    more - see `docs/corpus-v1.md` for the full field list.
    """
    queries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))
    return queries


def _ranks_by_position(results, id_key="id"):
    """Return {id: rank}, where rank 1 is the first (best) item in the list.

    `results` is assumed to already be ranked best-first - exactly the shape
    `retrieval.search_bm25` and `semantic_search.search_semantic` return.
    Reading off rank from list position (instead of re-sorting by score) is
    what lets Reciprocal Rank Fusion below combine a BM25 list and a semantic
    list without ever looking at their raw score values.

    `id_key` defaults to `"id"` (the whole-document result shape) but
    `HybridSearch` passes its own `id_key` through here too, so this works
    the same way for chunk results keyed by `"chunk_id"`.
    """
    return {result[id_key]: rank for rank, result in enumerate(results, start=1)}


def _scores_by_id(results, id_key="id"):
    """Return {id: score} for a ranked result list. See `_ranks_by_position`
    for what `id_key` is for."""
    return {result[id_key]: result["score"] for result in results}


def min_max_normalize(scores):
    """Scale a dict of {id: score} into the [0, 1] range.

    Min-max normalization: `normalized = (score - minimum) / (maximum -
    minimum)`. The lowest score in the set maps to 0.0, the highest maps to
    1.0, and everything else falls proportionally in between. This is what
    makes a BM25 score and a cosine score comparable enough to blend with a
    weight: after this step, both retrievers' scores live on the same [0, 1]
    scale, even though their raw scales were completely different.

    Min-max normalization is sensitive to outliers - one unusually high score
    compresses every other score toward 0 - and z-score normalization
    (subtract the mean, divide by the standard deviation) is the common
    alternative. Z-score avoids the outlier-compression problem but can
    produce negative values, which would need extra handling before blending
    with alpha below. Min-max keeps that one edge case (see the `spread == 0`
    check) instead of two, so this module only implements min-max.
    """
    if not scores:
        return {}

    values = scores.values()
    minimum = min(values)
    maximum = max(values)
    spread = maximum - minimum

    # Every score is identical, including the common case of a single
    # candidate (a list of one has no spread by definition). There is no
    # spread to normalize against, and (0 - 0) / 0 would divide by zero, so
    # every score maps to 0.0 instead.
    #
    # Practical consequence for `weighted()` below: a retriever that only
    # returned one candidate (or several candidates that happen to tie)
    # normalizes that candidate to 0.0, the same as if it were entirely
    # absent. It contributes nothing to the hybrid score on that side
    # regardless of alpha - there was nothing to discriminate on in the
    # first place, so treating it as "no information" is correct, not a
    # bug, but it is easy to misread as a broken weight.
    if spread == 0:
        return {document_id: 0.0 for document_id in scores}

    return {
        document_id: (score - minimum) / spread
        for document_id, score in scores.items()
    }


class HybridSearch:
    """Fuse one BM25 result list and one semantic result list.

    Per the Day 6 design note, this class works over whichever retrieval unit
    its two input lists already use - whole documents (`{"id", "score"}`) or
    chunks (`{"chunk_id", ...}`, in which case pass `id_key="chunk_id"`). The
    fusion math (RRF, weighted combination) doesn't care what the unit is; it
    only needs a stable id to group the two rankings by.
    """

    def __init__(self, bm25_results, semantic_results, id_key="id"):
        self.bm25_results = bm25_results
        self.semantic_results = semantic_results
        self.id_key = id_key

    def rrf(self, k=60, top_k=3):
        """Reciprocal Rank Fusion: rank by combined rank position, not score.

            rrf_score(d) = 1/(k + rank_bm25(d)) + 1/(k + rank_semantic(d))

        A document that isn't in one retriever's result list simply doesn't
        get a term for that retriever (BM25 returns nothing for a query with
        no matching tokens; dense retrieval, by contrast, scores every
        document, so it's rare but not impossible for a document to be
        missing from the semantic list too if it never made that retriever's
        top-k). Either way, that document is still rankable from whatever
        term it does have - RRF degrades gracefully instead of requiring both
        retrievers to agree on the same candidate set.

        `k` dampens how much a low rank (a bad position, e.g. 50th) hurts a
        document's score: a smaller `k` (e.g. 1) makes rank differences count
        for more, while the default `k=60` (the value most commonly cited in
        the RRF literature) makes the fused ranking fairly insensitive to
        where exactly a document sits past the first few positions.
        """
        if top_k <= 0:
            return []

        bm25_ranks = _ranks_by_position(self.bm25_results, self.id_key)
        semantic_ranks = _ranks_by_position(self.semantic_results, self.id_key)
        bm25_scores = _scores_by_id(self.bm25_results, self.id_key)
        semantic_scores = _scores_by_id(self.semantic_results, self.id_key)

        all_ids = set(bm25_ranks) | set(semantic_ranks)
        fused_results = []
        for document_id in all_ids:
            rrf_score = 0.0
            if document_id in bm25_ranks:
                rrf_score += 1.0 / (k + bm25_ranks[document_id])
            if document_id in semantic_ranks:
                rrf_score += 1.0 / (k + semantic_ranks[document_id])

            fused_results.append(
                {
                    self.id_key: document_id,
                    "score": rrf_score,
                    # Per-method raw scores are kept alongside the fused
                    # score purely for debugging/inspection - "why did this
                    # document rank where it did?" - not used in the RRF math
                    # itself, which only reads rank position above. `.get`
                    # returns None (not 0.0) for a document absent from that
                    # retriever's list, so a real low score is never
                    # confused with "no signal from this retriever".
                    "bm25_score": bm25_scores.get(document_id),
                    "semantic_score": semantic_scores.get(document_id),
                }
            )

        ranked = sorted(
            fused_results, key=lambda item: (-item["score"], item[self.id_key])
        )
        return ranked[:top_k]

    def weighted(self, alpha=0.5, top_k=3):
        """Weighted combination of min-max normalized scores.

            hybrid_score = alpha * semantic_normalized + (1 - alpha) * lexical_normalized

        `alpha` controls the balance between the two signals: `alpha=0.0` is
        pure lexical (BM25 only - the semantic term is multiplied by zero),
        `alpha=1.0` is pure semantic (BM25's term is multiplied by zero
        instead), and `alpha=0.5` (the default) weighs both equally. A
        procurement system that wants exact-identifier queries to dominate
        might use something like `alpha=0.2` to lean lexical.

        A document missing from one retriever's result list is treated as a
        normalized score of 0.0 for that side rather than being dropped - see
        the inline comment below for why 0.0 specifically, not an epsilon or
        the average.
        """
        if top_k <= 0:
            return []

        bm25_scores = _scores_by_id(self.bm25_results, self.id_key)
        semantic_scores = _scores_by_id(self.semantic_results, self.id_key)
        bm25_normalized = min_max_normalize(bm25_scores)
        semantic_normalized = min_max_normalize(semantic_scores)

        all_ids = set(bm25_normalized) | set(semantic_normalized)
        combined_results = []
        for document_id in all_ids:
            # A document absent from one retriever's list defaults to 0.0 on
            # that side - the normalized floor `min_max_normalize` already
            # gives that retriever's own worst-scored candidate (min maps to
            # 0.0), not an arbitrary placeholder like an epsilon or the
            # average would be. It can still rank via whichever side it does
            # have a score on; see `min_max_normalize`'s docstring for the
            # single-candidate-list edge case this same default covers.
            lexical_normalized_score = bm25_normalized.get(document_id, 0.0)
            semantic_normalized_score = semantic_normalized.get(document_id, 0.0)
            hybrid_score = (
                alpha * semantic_normalized_score
                + (1 - alpha) * lexical_normalized_score
            )

            combined_results.append(
                {
                    self.id_key: document_id,
                    "score": hybrid_score,
                    # Per-method scores, both raw and normalized, are kept so
                    # a result can be explained as e.g. "73% semantic match,
                    # 27% lexical match" - the interpretability weighted
                    # combination offers that RRF's rank-only score does not.
                    "bm25_score": bm25_scores.get(document_id),
                    "semantic_score": semantic_scores.get(document_id),
                    "bm25_score_normalized": lexical_normalized_score,
                    "semantic_score_normalized": semantic_normalized_score,
                }
            )

        ranked = sorted(
            combined_results, key=lambda item: (-item["score"], item[self.id_key])
        )
        return ranked[:top_k]


# ---------------------------------------------------------------------------
# Day 7: metadata filtering
#
# The v1 corpus rows carry operational metadata - `doc_type`, `category`,
# `region`, `supplier`, `risk_tags`, and more (see `docs/corpus-v1.md`) - that
# `preprocessing.preprocess_data` strips away before BM25/semantic search
# ever see a document; those functions only keep `id` plus whatever they need
# to score text (tokens, or an embedding). That is correct for scoring, but
# it means neither retriever has any way to honour "for EMEA" or "policy
# only" - a semantically perfect match in the wrong region is still wrong.
#
# Design decisions for Day 7 (see `docs/day-07-hybrid-consolidation-evals.md`,
# Block 2, for the questions these answer):
#
# - **Filter timing**: after scoring, before truncating to the caller's
#   final `top_k`. `filter_ranked_results` below expects the *full* ranked
#   list a retriever produced (call `search_bm25`/`search_semantic` with a
#   generous `top_k`, e.g. `CANDIDATE_POOL_SIZE`), drops non-matching
#   entries, and only then slices to the requested size. Filtering the
#   corpus *before* building the BM25/semantic index instead was rejected:
#   BM25's IDF and average-document-length statistics would then depend on
#   which filter was applied, so the same document could score differently
#   for the same query under different filters - confusing, and unnecessary
#   at this corpus's size (34 documents), where scoring everything and
#   filtering after is effectively free.
# - **Document level, not chunk level**: a chunk (see `chunking.py`) carries
#   only `chunk_id`, `document_id`, `text`, and `title` - none of the
#   metadata fields a filter checks. A chunk is filtered by its *parent
#   document's* metadata, looked up through `document_id`.
# - **When a filter removes the correct document**: it disappears from the
#   result list, exactly like any other non-matching candidate - a filter
#   cannot recover a document it has already excluded. `main()`'s
#   `run_edge_case_comparison` below includes a deliberately wrong filter
#   value on a real query to make this failure mode visible.
# ---------------------------------------------------------------------------


def build_metadata_index(data):
    """Return {document_id: raw_corpus_row}, for metadata lookups.

    `data` is the raw list of corpus rows from `preprocessing.load_data()` -
    the same input `retrieval.build_index` and
    `semantic_search.build_semantic_index` take. Unlike those, which reduce
    each row to tokens or an embedding, this keeps every original field
    (`doc_type`, `category`, `region`, `supplier`, `risk_tags`, ...) so
    `matches_filters` below has something to check.
    """
    return {row["id"]: row for row in data}


def matches_filters(metadata, filters):
    """Return True if one document's metadata satisfies every filter.

    `filters` is a small `{field: expected_value}` dict, e.g.
    `{"doc_type": "policy"}` or `{"region": "EMEA", "doc_type": "contract-summary"}`.
    A document must match every key present in `filters` (logical AND) -
    there is no OR or numeric-range support (e.g. "annual_value_eur over
    100000"). That is a real limitation, kept out deliberately: the v1 query
    set's `metadata_filters` field never needs more than equality-per-field
    to prove the filtering contract, so anything past that would be
    speculative complexity with no exercised test case.

    `risk_tags` is the one list-valued field in the v1 corpus (e.g.
    `["kyc", "sanctions", ...]`). For a list-valued field, "matches" means
    the expected value is a *member of* the list, not that the whole list
    equals the expected value - `{"risk_tags": "kyc"}` should match a
    document whose `risk_tags` contains `"kyc"` among other tags, not only a
    document whose entire tag list is exactly `["kyc"]`.
    """
    for field, expected_value in filters.items():
        actual_value = metadata.get(field)
        if isinstance(actual_value, list):
            if expected_value not in actual_value:
                return False
        elif actual_value != expected_value:
            return False
    return True


def filter_ranked_results(
    results, metadata_index, filters, id_key="id", document_id_key=None, top_k=3
):
    """Keep only the ranked results whose document matches `filters`, then
    slice to `top_k` - see the section docstring above for the timing and
    document-level design decisions this implements.

    `results` should be the *full* ranked list a retriever produced (e.g.
    `search_bm25(index, query, top_k=CANDIDATE_POOL_SIZE)`), not something
    already truncated to the caller's final desired size - filtering after
    truncation risks silently losing a correct document that matched the
    filter but ranked just outside a too-small pre-filter cut.

    `document_id_key=None` (the default) means `results` are whole-document
    results, so `id_key` ("id" by default) already names the document id
    directly. Pass `document_id_key="document_id"` for chunk results, whose
    own `id_key` (`"chunk_id"`) is not a document id - each chunk is then
    filtered by its parent document's metadata instead of its own (chunks
    carry no metadata of their own; see the section docstring above).

    An empty `filters` dict is the common "no filter requested" case and is
    handled first as a fast path: every result passes, so this only slices
    to `top_k` without doing per-result metadata lookups.
    """
    if not filters:
        return results[:top_k]

    filtered = []
    for result in results:
        lookup_id = result[document_id_key] if document_id_key else result[id_key]
        metadata = metadata_index.get(lookup_id)
        if metadata is not None and matches_filters(metadata, filters):
            filtered.append(result)

    return filtered[:top_k]


# ---------------------------------------------------------------------------
# Day 7: edge-case comparison on hand-picked v1 queries
# ---------------------------------------------------------------------------

# 10 queries from `data/corpus_v1/example_queries.jsonl`, chosen by
# `query_id` (not re-typed, so they can never drift from the actual golden
# file) to cover the query shapes Day 7's design doc asks for:
#
#   Q001 - exact currency threshold, + a `doc_type` metadata filter
#   Q089 - near-synonym pair ("sole source" vs "single source"), + a
#          `doc_type` filter
#   Q053 - supplier-specific, + a `supplier` filter
#   Q014 - vocabulary gap ("uptime" is the corpus's word; a paraphrase would
#          say "availability"), no filter
#   Q009 - exact numeric threshold (a shareholding percentage), no filter
#   Q005 - multi-document (answer spans 3 separate documents)
#   Q093 - multi-document and intentionally hard: three DIFFERENT numeric
#          answers depending on which contract, from the "sole confident
#          number is wrong" family docs/corpus-v1.md calls out
#   Q011 - exact standards/acronyms (SOC 2, ISO 27001), + a `category` filter
#   Q067 - vocabulary gap ("contractor" vs the corpus's "contingent worker"),
#          + a `category` filter
#   Q071 - domain-specific scenario phrasing, + a `category` filter
EDGE_CASE_QUERY_IDS = [
    "Q001", "Q089", "Q053", "Q014", "Q009",
    "Q005", "Q093", "Q011", "Q067", "Q071",
]


def run_edge_case_comparison():
    """Print BM25 vs dense vs hybrid (RRF/weighted) top-1 for 10 v1 queries.

    This is the Block 3A "comparison function" and "edge-case comparison"
    output in one: each retriever runs with `CANDIDATE_POOL_SIZE` candidates
    (the Day 7 tie mitigation - see that constant's docstring), a query's own
    `metadata_filters` are applied when present (via `filter_ranked_results`
    above), and a checkmark shows whether each method's top-1 is a known
    relevant document (`expected_relevant_ids`). The real numbers this
    produced, plus which queries landed in each of "BM25 wins" / "dense
    wins" / "hybrid wins" / "hybrid still fails", are written up in
    `docs/eval-report.md` - this function is what generated them, not a
    duplicate of them, so re-running it is how to check they are still
    accurate after any change to the corpus or the fusion code.
    """
    from preprocessing import load_data
    from retrieval import build_index, search_bm25
    from semantic_search import build_semantic_index, load_embedding_model, search_semantic

    data = load_data()
    bm25_index = build_index(data)
    model = load_embedding_model()
    semantic_index = build_semantic_index(data, model)
    metadata_index = build_metadata_index(data)
    queries_by_id = {query["query_id"]: query for query in load_example_queries()}

    def top1(results):
        return results[0]["id"] if results else "(none)"

    def mark(document_id, relevant_ids):
        return "correct" if document_id in relevant_ids else "MISS"

    for query_id in EDGE_CASE_QUERY_IDS:
        query_row = queries_by_id[query_id]
        query = query_row["query"]
        relevant_ids = set(query_row["expected_relevant_ids"])
        filters = query_row["metadata_filters"]

        bm25_results = search_bm25(bm25_index, query, top_k=CANDIDATE_POOL_SIZE)
        semantic_results = search_semantic(
            semantic_index, query, model, top_k=CANDIDATE_POOL_SIZE
        )

        # Apply the query's own metadata filter, if it has one - this is the
        # same `filter_ranked_results` a real filtered search would call,
        # exercised here on real BM25/semantic output rather than synthetic
        # data (see `tests/test_hybrid_search.py` for the synthetic-data
        # tests of `filter_ranked_results` itself).
        if filters:
            bm25_results = filter_ranked_results(
                bm25_results, metadata_index, filters, top_k=CANDIDATE_POOL_SIZE
            )
            semantic_results = filter_ranked_results(
                semantic_results, metadata_index, filters, top_k=CANDIDATE_POOL_SIZE
            )

        hybrid = HybridSearch(bm25_results, semantic_results)
        rrf_results = hybrid.rrf(top_k=3)
        weighted_results = hybrid.weighted(top_k=3)

        bm25_top1 = top1(bm25_results)
        semantic_top1 = top1(semantic_results)
        rrf_top1 = top1(rrf_results)
        weighted_top1 = top1(weighted_results)

        filter_note = f"  filter={filters}" if filters else ""
        print(f"\n{query_id}: {query}{filter_note}")
        print(f"  expected (primary+secondary): {sorted(relevant_ids)}")
        print(f"  BM25 top-1:     {bm25_top1:<15} {mark(bm25_top1, relevant_ids)}")
        print(f"  Dense top-1:    {semantic_top1:<15} {mark(semantic_top1, relevant_ids)}")
        print(f"  RRF top-1:      {rrf_top1:<15} {mark(rrf_top1, relevant_ids)}")
        print(f"  Weighted top-1: {weighted_top1:<15} {mark(weighted_top1, relevant_ids)}")

    # --- Metadata-filter failure mode -------------------------------------
    # Q001's real filter (`doc_type: policy`) keeps its correct document,
    # POL-001, since POL-001 *is* a policy - that alone doesn't show what
    # happens when a filter is wrong. Re-running the same query's BM25
    # results through a deliberately mismatched filter does: POL-001 is not
    # a contract-summary, so it is removed - not re-ranked, removed - and
    # cannot come back no matter how the remaining candidates are scored.
    print("\n--- Metadata filter failure mode (Q001, deliberately wrong filter) ---")
    query_row = queries_by_id["Q001"]
    query = query_row["query"]
    correct_filter = query_row["metadata_filters"]
    wrong_filter = {"doc_type": "contract-summary"}

    bm25_results = search_bm25(bm25_index, query, top_k=CANDIDATE_POOL_SIZE)
    correctly_filtered = filter_ranked_results(
        bm25_results, metadata_index, correct_filter, top_k=3
    )
    wrongly_filtered = filter_ranked_results(
        bm25_results, metadata_index, wrong_filter, top_k=3
    )

    print(f"Q001: {query}")
    print(f"  unfiltered BM25 top-1:                  {top1(bm25_results)}")
    print(f"  filter={correct_filter} (the query's real filter) -> top-1: {top1(correctly_filtered)}")
    print(
        f"  filter={wrong_filter} (deliberately wrong) -> "
        f"results: {[r['id'] for r in wrongly_filtered]}"
    )
    print(
        "  -> POL-001 is the correct document but is not a contract-summary, "
        "so the wrong filter removes it before scoring ever mattered."
    )


def _print_results(results, id_key="id"):
    """Print a fused result list with its per-method scores for inspection."""
    for result in results:
        bm25_score = result["bm25_score"]
        semantic_score = result["semantic_score"]
        bm25_display = f"{bm25_score:.4f}" if bm25_score is not None else "-"
        semantic_display = f"{semantic_score:.4f}" if semantic_score is not None else "-"
        print(
            f"  {result[id_key]}: hybrid={result['score']:.4f} "
            f"(bm25={bm25_display}, semantic={semantic_display})"
        )


def _print_chunk_results(results, chunks_by_id):
    """Print a fused chunk-level result list.

    `HybridSearch`'s fused output only ever carries the id and per-method
    scores (see the module docstring) - it never copies through the extra
    fields a particular retriever's result happened to have, like a chunk's
    `document_id` or `text`. That's deliberate: the fusion math is generic
    over whatever `id_key` names, so it has no way to know which extra
    fields, if any, are worth carrying along. For display, this looks
    `document_id` back up from either chunk index by `chunk_id` instead.
    """
    for result in results:
        chunk_id = result["chunk_id"]
        document_id = chunks_by_id[chunk_id]["document_id"]
        bm25_score = result["bm25_score"]
        semantic_score = result["semantic_score"]
        bm25_display = f"{bm25_score:.4f}" if bm25_score is not None else "-"
        semantic_display = f"{semantic_score:.4f}" if semantic_score is not None else "-"
        print(
            f"  {chunk_id} (doc={document_id}): hybrid={result['score']:.4f} "
            f"(bm25={bm25_display}, semantic={semantic_display})"
        )


def main() -> None:
    """Run BM25, semantic, RRF, and weighted search side by side.

    Reuses the Day 4 comparison queries (`semantic_search.COMPARISON_CASES`)
    so the same five queries that first motivated semantic search can now
    show where *hybrid* retrieval does better than either single method - in
    particular the identifier-heavy queries (SOC 2 / ISO 27001, the 3%
    variance threshold) where BM25 alone is already strong, but a paraphrase
    of the same question could easily have broken it.

    Then repeats the *same* five queries at chunk level (Day 5's
    `chunking.py` + `chunked_search.py`) instead of whole documents, to show
    that `HybridSearch` is retrieval-unit-agnostic - the only thing that
    changes is which retrievers feed it and `id_key="chunk_id"`, not the
    fusion math itself, and not the queries either.
    """
    from preprocessing import load_data
    from retrieval import build_index, search_bm25
    from semantic_search import (
        COMPARISON_CASES,
        build_semantic_index,
        load_embedding_model,
        search_semantic,
    )

    data = load_data()
    bm25_index = build_index(data)
    model = load_embedding_model()
    semantic_index = build_semantic_index(data, model)

    print("=== Whole-document hybrid search ===")
    for case in COMPARISON_CASES:
        query = case["query"]
        expected_id = case["expected_id"]
        print(f"\nQuery: {query}")
        print(f"Expected document: {expected_id}")

        bm25_results = search_bm25(bm25_index, query, top_k=3)
        semantic_results = search_semantic(semantic_index, query, model, top_k=3)
        bm25_top1 = bm25_results[0]["id"] if bm25_results else None
        semantic_top1 = semantic_results[0]["id"] if semantic_results else None

        print(f"BM25 top-1: {bm25_top1}")
        print(f"Semantic top-1: {semantic_top1}")

        hybrid = HybridSearch(bm25_results, semantic_results)

        rrf_results = hybrid.rrf(k=60, top_k=3)
        print("RRF (k=60):")
        _print_results(rrf_results)

        weighted_results = hybrid.weighted(alpha=0.5, top_k=3)
        print("Weighted (alpha=0.5):")
        _print_results(weighted_results)

        # The interesting case for a portfolio demo isn't "hybrid agrees with
        # both" (unremarkable) - it's a query where at least one single
        # method missed the expected document but fusion recovered it.
        rrf_top1 = rrf_results[0]["id"] if rrf_results else None
        if rrf_top1 == expected_id and expected_id not in (bm25_top1, semantic_top1):
            print(
                f"  -> Hybrid recovered the expected document ({expected_id}); "
                "neither single method ranked it first."
            )

    # --- Chunk-level hybrid search --------------------------------------
    # Same COMPARISON_CASES queries as the whole-document section above -
    # deliberately not chunked_search.COMPARISON_QUERIES (only 2 queries,
    # picked for Day 5's narrower whole-doc-vs-chunk comparison). Reusing
    # the same five queries here is what makes this a real side-by-side: the
    # only thing that should differ between the two sections is the
    # retrieval unit, not also which queries were asked.
    from chunking import chunk_corpus
    from chunked_search import (
        build_chunk_lexical_index,
        build_chunk_semantic_index,
        search_bm25_chunks,
        search_semantic_chunks,
    )

    print("\n\n=== Chunk-level hybrid search ===")
    chunks = chunk_corpus(data)
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, model)

    for case in COMPARISON_CASES:
        query = case["query"]
        expected_id = case["expected_id"]
        print(f"\nQuery: {query}")
        print(f"Expected document: {expected_id}")

        chunk_bm25_results = search_bm25_chunks(chunk_lexical_index, query, top_k=3)
        chunk_semantic_results = search_semantic_chunks(
            chunk_semantic_index, query, model, top_k=3
        )
        bm25_top1_document = (
            chunk_lexical_index["chunks"][chunk_bm25_results[0]["chunk_id"]][
                "document_id"
            ]
            if chunk_bm25_results
            else None
        )
        semantic_top1_document = (
            chunk_semantic_index["chunks"][chunk_semantic_results[0]["chunk_id"]][
                "document_id"
            ]
            if chunk_semantic_results
            else None
        )

        print(
            f"BM25 top-1 chunk: {chunk_bm25_results[0]['chunk_id']} "
            f"(doc={bm25_top1_document})"
        )
        print(
            f"Semantic top-1 chunk: {chunk_semantic_results[0]['chunk_id']} "
            f"(doc={semantic_top1_document})"
        )

        # `id_key="chunk_id"` is the only difference from the whole-document
        # case above - the RRF/weighted math is identical either way.
        chunk_hybrid = HybridSearch(
            chunk_bm25_results, chunk_semantic_results, id_key="chunk_id"
        )

        chunk_rrf_results = chunk_hybrid.rrf(k=60, top_k=3)
        print("RRF (k=60):")
        _print_chunk_results(chunk_rrf_results, chunk_lexical_index["chunks"])

        chunk_weighted_results = chunk_hybrid.weighted(alpha=0.5, top_k=3)
        print("Weighted (alpha=0.5):")
        _print_chunk_results(chunk_weighted_results, chunk_lexical_index["chunks"])

        rrf_top1_document = (
            chunk_lexical_index["chunks"][chunk_rrf_results[0]["chunk_id"]][
                "document_id"
            ]
            if chunk_rrf_results
            else None
        )
        if rrf_top1_document == expected_id and expected_id not in (
            bm25_top1_document,
            semantic_top1_document,
        ):
            print(
                f"  -> Hybrid recovered the expected document "
                f"({expected_id}); neither single method ranked a "
                "chunk from it first."
            )

    # --- Day 7: edge-case comparison + metadata filtering -----------------
    print("\n\n=== Day 7: edge-case comparison (metadata filtering) ===")
    run_edge_case_comparison()


if __name__ == "__main__":
    main()
