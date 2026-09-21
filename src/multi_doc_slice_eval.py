"""Day 15: measure the FULL multi_doc query slice under both retrieval configs.

**Why this script exists.** Day 14's Block 3B repair (`reranking.py`'s
`MULTI_DOC_RETRIEVAL_CONFIG`) was verified on exactly three queries: Q091,
Q093, Q016 — the three Day 13 happened to pick as fixtures for
`regression_suite.py`. But the corpus's `multi_doc` query type has FIVE
members: Q005, Q016, Q091, Q092, Q093 (see `docs/corpus-v1.md` /
`data/corpus_v1/example_queries.jsonl`). Day 14's own "Next step" flagged
this directly: before calling the repaired config broadly safe for every
`multi_doc` query, Q005 and Q092 — the two NOT checked yet — need to be
measured too, not just assumed to behave the same as the three that were
checked.

This script is the smallest honest way to answer that: for each of the five
`multi_doc` queries, run retrieval under `DEFAULT_RETRIEVAL_CONFIG` (the old
`pool_size=15` behavior every non-multi_doc query still uses) and under
`MULTI_DOC_RETRIEVAL_CONFIG` (`pool_size=80, max_chunks_per_document=2`,
Day 14's repair), then report the same signals Day 13/14 already used to
diagnose Q091/Q093/Q016: which documents actually reach the generation
context, whether any *primary* (grade-2) document is missing from that
context, and the standard P@1/R@5/MRR@10/nDCG@5 retrieval-quality numbers.

**Two different questions, kept separate on purpose** (the same distinction
`generation_eval.check_context_recall` draws for a single query, now applied
across the whole slice):

1. "Did retrieval quality change?" — P@1/R@5/MRR@10/nDCG@5, computed the
   exact same way `eval_metrics.py`'s own baseline table already computes
   them for every other row: rerank the query's FULL candidate pool (no
   `top_k` cutoff), roll the reranked chunks up to a ranked document list,
   then truncate that list to `RETRIEVAL_DEPTH=10` before scoring. This
   makes the numbers here directly comparable to `eval_metrics.py`'s
   existing "Cross-encoder reranked Hybrid RRF chunk->document" row and its
   "multi_doc" error slice (which used exactly `DEFAULT_RETRIEVAL_CONFIG`'s
   `pool_size=15`, so the "default" column below should reproduce that
   row's multi_doc-slice numbers as a sanity check — see `main()`'s closing
   printout).
2. "Did the documents that actually reach generation change?" — this is a
   DIFFERENT cut than #1, because `top_k` (5 for default, 10 for repaired)
   truncates the reranked list BEFORE it becomes `generation.build_sources`
   input. A document ranked #7 counts toward R@5/nDCG@5 only partially (or
   not at all past #5/#10), but for the "does the generator ever see this
   document" question, the only thing that matters is: was it inside the
   first `top_k` chunks or not? That is what `missing_primary_doc_ids`
   below reports, and it is the exact same "primary document missing from
   context" idea `generation_eval.check_context_recall` checks per-answer,
   just applied here directly to retrieval output instead of to a captured
   generation transcript.

Both views are built from ONE reranked call per (query, config) pair, not
two — `reranking.rerank` always sorts its full candidate list and only
slices to `top_k` at the very end (see that function's docstring), so
calling with `top_k=None` and then slicing the result in Python two
different ways (`[:RETRIEVAL_DEPTH]` for view #1, `[:config["top_k"]]` for
view #2) gives identical results to calling `two_stage_rerank` twice with
two different `top_k` values — just without the wasted second rerank pass.

**What this script deliberately does not do.** It does not change
`reranking.py`, `generation.py`, or `regression_suite.py` — it is read-only
measurement over the existing, already-shipped repair. It does not average
metrics across an aggregate "multi_doc slice score" as the final verdict;
Day 14's own experience with Q091 (missing docs fixed, but a narrower
`Band 3` term-level gap remained) is exactly why this script prints a
per-query table instead of one blended number that could hide a query
that got worse while others got better.
"""

from chunked_search import build_chunk_lexical_index, build_chunk_semantic_index
from chunking import chunk_corpus
from eval_metrics import (
    grades_for_query,
    ndcg_at_k,
    precision_at_1,
    reciprocal_rank,
    recall_at_k,
    rollup_chunks_to_documents,
)
from hybrid_search import load_example_queries
from preprocessing import load_data
from reranking import (
    DEFAULT_RETRIEVAL_CONFIG,
    MULTI_DOC_RETRIEVAL_CONFIG,
    load_cross_encoder,
    two_stage_rerank,
)
from semantic_search import load_embedding_model

# The full multi_doc slice — every query in the v1 corpus whose
# `query_type == "multi_doc"`, not just the three Day 13/14 already fixed.
# Verified against `data/corpus_v1/example_queries.jsonl` directly (5 rows
# carry `"query_type": "multi_doc"`), not assumed.
MULTI_DOC_QUERY_IDS = ["Q005", "Q016", "Q091", "Q092", "Q093"]

# Same convention `eval_metrics.main()` already uses for every other row in
# its baseline table: truncate the rolled-up document ranking to the top 10
# before scoring P@1/R@5/MRR (this is what makes "MRR" in this report really
# "MRR@10" — see `eval_metrics.py`'s module docstring for why).
RETRIEVAL_DEPTH = 10

# The two configs under comparison, named for the table. `retrieval_config_for_query_type`
# itself is NOT called here — this script deliberately builds both configs
# for every query (instead of only the one that config function would pick),
# because the whole point is to compare them side by side.
CONFIGS = [
    ("default", DEFAULT_RETRIEVAL_CONFIG),
    ("repaired", MULTI_DOC_RETRIEVAL_CONFIG),
]


def primary_doc_ids(query_row):
    """Grade-2 ("primary") expected document ids for one query.

    Same "primary = grade 2" definition `eval_metrics.primary_count` and
    `generation_eval.primary_expected_doc_ids` already use — repeated here
    (not imported) because it is a one-line dict comprehension and this
    script already imports enough from both modules.
    """
    return {doc_id for doc_id, grade in query_row["relevance_grades"].items() if grade == 2}


def measure_one_config(query_row, config, chunk_lexical_index, chunk_semantic_index, embedding_model, cross_encoder_model):
    """Run one (query, config) pair and return every signal the Day 15 table needs.

    `top_k=None` below is the key choice this whole script hinges on (see
    the module docstring's "Both views are built from ONE reranked call"
    section): it returns the reranker's FULL scored candidate list, sorted
    best-first, so this function can slice it two different ways below
    without a second, redundant rerank pass.
    """
    reranked_full = two_stage_rerank(
        query_row["query"],
        chunk_lexical_index,
        chunk_semantic_index,
        embedding_model,
        cross_encoder_model,
        pool_size=config["pool_size"],
        max_chunks_per_document=config["max_chunks_per_document"],
        top_k=None,
    )

    # View #1: retrieval-quality metrics, at the standard RETRIEVAL_DEPTH=10
    # cutoff every other eval_metrics.py row already uses.
    rolled_up_full = rollup_chunks_to_documents(reranked_full)
    retrieved_ids_for_metrics = rolled_up_full[:RETRIEVAL_DEPTH]
    relevant_ids = query_row["expected_relevant_ids"]

    metrics = {
        "p_at_1": precision_at_1(retrieved_ids_for_metrics, relevant_ids),
        "r_at_5": recall_at_k(retrieved_ids_for_metrics, relevant_ids, k=5),
        "mrr_at_10": reciprocal_rank(retrieved_ids_for_metrics, relevant_ids),
        "ndcg_at_5": ndcg_at_k(rolled_up_full, grades_for_query(query_row), k=5),
    }

    # View #2: what actually reaches generation context under THIS config's
    # own top_k — the same cutoff `generation.py`'s real entry point applies
    # via `build_sources(two_stage_rerank(..., **retrieval_config))`.
    context_chunks = reranked_full[: config["top_k"]]
    context_doc_ids = rollup_chunks_to_documents(context_chunks)
    missing_primary_doc_ids = sorted(primary_doc_ids(query_row) - set(context_doc_ids))

    return {
        "metrics": metrics,
        "context_doc_ids": context_doc_ids,
        "context_chunk_ids": [chunk["chunk_id"] for chunk in context_chunks],
        "missing_primary_doc_ids": missing_primary_doc_ids,
        "top5_doc_ids": rolled_up_full[:5],
    }


def format_metrics(metrics):
    return (
        f"P@1={metrics['p_at_1']:.3f} R@5={metrics['r_at_5']:.3f} "
        f"MRR@10={metrics['mrr_at_10']:.3f} nDCG@5={metrics['ndcg_at_5']:.3f}"
    )


def main() -> None:
    data = load_data()
    chunks = chunk_corpus(data)
    embedding_model = load_embedding_model()
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
    cross_encoder_model = load_cross_encoder()

    queries_by_id = {query["query_id"]: query for query in load_example_queries()}

    # Every result, keyed by (query_id, config_name), so the closing sanity
    # check below can re-use them without re-running retrieval.
    results = {}

    for query_id in MULTI_DOC_QUERY_IDS:
        query_row = queries_by_id[query_id]
        print(f"\n{query_id} ({query_row['difficulty']}): {query_row['query']}")
        print(f"  primary (grade-2) expected docs: {sorted(primary_doc_ids(query_row))}")
        print(f"  all expected docs: {sorted(query_row['expected_relevant_ids'])}")

        for config_name, config in CONFIGS:
            result = measure_one_config(
                query_row, config, chunk_lexical_index, chunk_semantic_index,
                embedding_model, cross_encoder_model,
            )
            results[(query_id, config_name)] = result

            print(f"  [{config_name}] pool_size={config['pool_size']} top_k={config['top_k']} "
                  f"max_chunks_per_document={config['max_chunks_per_document']}")
            print(f"    top-5 retrieved docs (full ranking): {result['top5_doc_ids']}")
            print(f"    docs reaching generation context (top_k={config['top_k']}): "
                  f"{sorted(set(result['context_doc_ids']))}")
            print(f"    chunk ids reaching context: {result['context_chunk_ids']}")
            if result["missing_primary_doc_ids"]:
                print(f"    MISSING primary doc(s) from context: {result['missing_primary_doc_ids']}")
            else:
                print("    all primary docs reach context")
            print(f"    {format_metrics(result['metrics'])}")

    # ------------------------------------------------------------------
    # Sanity check: eval_metrics.py's own "Day 9 error slices" section
    # already reports one aggregate number for the multi_doc slice under
    # the OLD default config (pool_size=15, cross-encoder reranked row):
    # "Largest weak slice: reranked multi_doc P@1 0.600 over 5 queries"
    # (see docs/eval-report.md). This script's "default" column re-derives
    # the same P@1 the same way (rerank full pool, roll up, truncate to
    # RETRIEVAL_DEPTH=10) - if these two numbers disagree, something in
    # this script's measurement setup is wrong, not just "the numbers
    # moved". Printed as an explicit check rather than trusted silently.
    # ------------------------------------------------------------------
    default_p_at_1_values = [
        results[(query_id, "default")]["metrics"]["p_at_1"] for query_id in MULTI_DOC_QUERY_IDS
    ]
    default_p_at_1_mean = sum(default_p_at_1_values) / len(default_p_at_1_values)
    print(f"\nSanity check - default-config P@1 across the 5-query multi_doc slice: "
          f"{default_p_at_1_mean:.3f} (eval_metrics.py's Day 9 error slice reported 0.600 "
          f"for the reranked method's multi_doc slice under this same pool_size=15 config)")


if __name__ == "__main__":
    main()
