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
"""


def _ranks_by_position(results):
    """Return {id: rank}, where rank 1 is the first (best) item in the list.

    `results` is assumed to already be ranked best-first - exactly the shape
    `retrieval.search_bm25` and `semantic_search.search_semantic` return.
    Reading off rank from list position (instead of re-sorting by score) is
    what lets Reciprocal Rank Fusion below combine a BM25 list and a semantic
    list without ever looking at their raw score values.
    """
    return {result["id"]: rank for rank, result in enumerate(results, start=1)}


def _scores_by_id(results):
    """Return {id: score} for a ranked result list."""
    return {result["id"]: result["score"] for result in results}


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

    # Every score is identical (including the common case of a single
    # candidate). There is no spread to normalize against, and (0 - 0) / 0
    # would divide by zero, so every score maps to 0.0 instead.
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

    def _ranks_and_scores(self):
        """Re-key both input lists by `id_key` so the fusion methods below
        can look either one up by document id in O(1) instead of scanning."""
        bm25_by_id = {result[self.id_key]: result for result in self.bm25_results}
        semantic_by_id = {
            result[self.id_key]: result for result in self.semantic_results
        }
        return bm25_by_id, semantic_by_id

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

        bm25_ranks = _ranks_by_position(self.bm25_results)
        semantic_ranks = _ranks_by_position(self.semantic_results)
        bm25_by_id, semantic_by_id = self._ranks_and_scores()

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
                    # itself, which only reads rank position above.
                    "bm25_score": bm25_by_id.get(document_id, {}).get("score"),
                    "semantic_score": semantic_by_id.get(document_id, {}).get(
                        "score"
                    ),
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
        normalized score of 0.0 for that side (the same "worst score in this
        list" value the lowest-ranked *present* document would get) rather
        than being dropped - it can still rank via whichever side it does
        have a score on.
        """
        if top_k <= 0:
            return []

        bm25_normalized = min_max_normalize(_scores_by_id(self.bm25_results))
        semantic_normalized = min_max_normalize(_scores_by_id(self.semantic_results))
        bm25_by_id, semantic_by_id = self._ranks_and_scores()

        all_ids = set(bm25_normalized) | set(semantic_normalized)
        combined_results = []
        for document_id in all_ids:
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
                    "bm25_score": bm25_by_id.get(document_id, {}).get("score"),
                    "semantic_score": semantic_by_id.get(document_id, {}).get(
                        "score"
                    ),
                    "bm25_score_normalized": lexical_normalized_score,
                    "semantic_score_normalized": semantic_normalized_score,
                }
            )

        ranked = sorted(
            combined_results, key=lambda item: (-item["score"], item[self.id_key])
        )
        return ranked[:top_k]


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


def main() -> None:
    """Run BM25, semantic, RRF, and weighted search side by side.

    Reuses the Day 4 comparison queries (`semantic_search.COMPARISON_CASES`)
    so the same five queries that first motivated semantic search can now
    show where *hybrid* retrieval does better than either single method - in
    particular the identifier-heavy queries (SOC 2 / ISO 27001, the 3%
    variance threshold) where BM25 alone is already strong, but a paraphrase
    of the same question could easily have broken it.
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


if __name__ == "__main__":
    main()
