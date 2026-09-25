"""Day 16 (Block 3A): a bounded, measured recursive-retrieval loop.

**Why this module exists.** Days 7-15 built a strong *single-pass* retrieval
pipeline (`hybrid_search.py` + `chunked_search.py` for first-stage fusion,
`reranking.py` for cross-encoder reranking, `reranking.retrieval_config_for_query_type`
for a per-query-type pool/top_k choice). Day 15's full `multi_doc` slice
remeasurement (`docs/eval-report.md`) found that single pass still has a
ceiling, in two genuinely different ways:

- **Q091** ("...EUR 120,000 SaaS renewal...") - the missing *document*
  (`POL-001`) was already repaired in Day 14, but the answer still can't
  state the exact "Band 3" approval threshold, because the one *chunk* that
  carries it (`POL-001::chunk-4`) is not the chunk retrieval happened to
  surface (`POL-001::chunk-3`, which explains HOW total committed value is
  calculated, not the bands themselves). This is a **chunk-level** gap
  inside an already-present document.
- **Q092** ("...new cleaning contractor starts on site?") - two *documents*
  (`CONTRACT-005`, `POL-002`) never reach the generation context at all, for
  two DIFFERENT root causes measured in `docs/eval-report.md`'s Day 15
  diagnostic: `CONTRACT-005` is found by first-stage BM25 but the
  cross-encoder reranker itself scores it too low to survive into the
  top-`top_k` cut; `POL-002` barely enters the fused pool at all (weak
  first-stage + fusion signal) and, even when a much deeper diagnostic pool
  forces it in, the reranker still ranks it outside the cutoff. One generic
  "try again" cannot be expected to fix both of these the same way.

**Recursive RAG, defined the way this module implements it.** Boot.dev's
Chapter 11 framing is "use a second retrieval pass when first-pass evidence
is incomplete" - and the key word is *measured*. This is NOT "ask the model
again" or "raise `top_k` and hope": every decision below is driven by a
concrete, computed signal (a specific missing `doc_id`, or a specific
missing `chunk_id`) and every second pass is a specific, targeted
reformulated query aimed at that exact missing evidence - never a vague
retry of the same query. See `run_recursive_retrieval` below for the exact
five-step loop (first pass -> evaluate -> trigger? -> second pass -> merge
-> re-evaluate).

**Agentic, defined the way this module implements it.** "Agentic" here does
not mean an LLM decides what to do. It means *bounded control flow with an
explicit stop condition*: a plain Python function that (1) can only ever run
one extra retrieval pass today (`run_recursive_retrieval` never loops), (2)
only recurses on a concrete measured trigger, never unconditionally, and (3)
always ends in one of a small number of named `stop_reason`s a reader can
audit. No LLM is required to make the retrieve-again decision - see
`decide_trigger` below - which is also what keeps this module's tests fully
deterministic (Boot.dev's "Agentic Search" lesson calls this a *decision
loop*, not necessarily an *LLM-driven* one).

**Reuse, not reinvention.** This module does not touch the retrieval
pipeline itself. `retrieval_config_for_query_type` and `two_stage_rerank`
(`reranking.py`), `build_sources` (`generation.py`), and
`primary_expected_doc_ids`/`context_doc_ids` (`generation_eval.py`) are
called exactly as every other day's module already calls them. The only new
idea here is *when* to call retrieval a second time, with *what* query, and
how to *compare* the two results - see `run_recursive_retrieval`.

**Testability boundary.** The whole decision/merge/re-evaluate contract
(`evaluate_missing_evidence`, `decide_trigger`, `merge_sources`,
`run_recursive_retrieval`) takes retrieval as an injected
`retrieve_fn(query_text, config) -> sources` callable, exactly the same
"inject the expensive/non-deterministic part" pattern `reranking.rerank`
uses for `score_fn` and `generation.generate_answer` uses for `client`. That
is what lets `tests/test_agentic_retrieval.py` exercise the trigger/merge/
stop logic with a small fake retrieval function and canned source lists -
no embedding model, no cross-encoder, no network call, no corpus load. The
one real, model-backed `retrieve_fn` (`make_live_retrieve_fn` below) is only
ever constructed in `main()`.
"""

from generation import build_sources
from generation_eval import context_doc_ids, primary_expected_doc_ids
from reranking import retrieval_config_for_query_type

# ---------------------------------------------------------------------------
# The decision contract: named trigger reasons and stop reasons, so a reader
# (or a test) can compare against a fixed vocabulary instead of a loose
# string. This is the "trigger reason (missing_doc, missing_chunk, ...)"
# field the Day 16 route doc's target-evidence checklist asks for.
# ---------------------------------------------------------------------------

TRIGGER_MISSING_DOC = "missing_doc"
TRIGGER_MISSING_CHUNK = "missing_chunk"

STOP_NO_MISSING_EVIDENCE = "no_missing_evidence"
STOP_NO_FOLLOWUP_QUERY_DEFINED = "trigger_detected_no_followup_query_defined"
STOP_FIXED_AFTER_SECOND_PASS = "fixed_after_second_pass"
STOP_STILL_MISSING_AFTER_MAX_PASSES = "still_missing_after_max_passes"

# The merge rule, written out once as a constant string rather than only in
# a comment, so it can be printed on every case's trace (see
# `run_recursive_retrieval` and `_print_case_trace` below) instead of a
# reader having to go find this docstring to know what "merged" means.
MERGE_POLICY_DESCRIPTION = (
    "union of first-pass and second-pass sources, deduplicated by chunk_id; "
    "every first-pass source is kept unchanged and in its original order - "
    "the second pass can only ADD chunks the first pass did not already "
    "retrieve, never remove or reorder what the first pass found"
)

# ---------------------------------------------------------------------------
# Day 16's own per-query decision table: for each query this experiment
# targets, the ONE reformulated follow-up query to try, plus (for Q091 only)
# the specific chunk that has to reach context for the gap to count as
# fixed. This is the "deterministic mapping from known failure signal to
# known follow-up query" the route doc explicitly allows for Day 16 ("Keep
# the first version boring and inspectable" - Block 2). Q001 and Q005 have
# no entry here on purpose: they are the no-second-pass controls, and their
# absence is not a special case in the code below - see `decide_trigger`,
# which simply never finds anything missing for them in the first place.
#
# Q091's follow-up query is copied verbatim from the route doc's own worked
# example (see docs/day-16-recursive-rag-q091-q092-agentic-search.md,
# "Recursive RAG is a measured retry" section): it targets the exact EUR
# figures and the "Band 3" vocabulary that only live in POL-001::chunk-4.
#
# Q092's follow-up query is built directly from the Day 15 root-cause
# diagnostic (docs/eval-report.md's "Root-cause diagnostic for Q092"
# section), not guessed: "Enhanced Due Diligence" and "Legal approval" are
# POL-002's own clause language (its missing chunk quotes "High-risk
# suppliers require Enhanced Due Diligence before activation and formal
# approval from Legal"), and "recruitment fees"/"subcontracting"/"insurance"
# are CONTRACT-005's clause language. One combined query, not two - the Day
# 16 contract caps every query at exactly one extra pass, so Q092's two
# different failure owners have to share that one shot, and are reported
# separately afterward regardless of whether it worked for both, one, or
# neither (see `run_recursive_retrieval`'s `missing_doc_status` field).
AGENTIC_CASE_OVERRIDES = {
    "Q091": {
        "followup_query": "approval bands EUR 50,000 250,000 Band 3 VP Procurement",
        "required_chunk_ids": ("POL-001::chunk-4",),
    },
    "Q092": {
        "followup_query": (
            "cleaning contractor high-risk supplier Enhanced Due Diligence "
            "Legal approval recruitment fees subcontracting insurance"
        ),
        "required_chunk_ids": (),
    },
}


# ---------------------------------------------------------------------------
# Step 2 of the loop: "evaluate missing evidence using existing deterministic
# checks where possible" (Block 3A's recommended behavior). Deliberately
# reuses generation_eval's own primary/context helpers instead of
# re-deriving "what counts as primary" a second time.
# ---------------------------------------------------------------------------


def evaluate_missing_evidence(query_row, sources, required_chunk_ids=()):
    """Compare `sources` against what this query needs, at two granularities.

    Document-level: reuses `generation_eval.primary_expected_doc_ids` (the
    grade-2 "primary" documents a correct answer cannot do without) and
    `generation_eval.context_doc_ids` (every doc id actually retrieved) -
    the exact same "expected minus actual" check `check_context_recall`
    already runs per generated answer, applied here directly to a retrieval
    result. This is what catches Q092's CONTRACT-005/POL-002 gap.

    Chunk-level: `required_chunk_ids` is empty for every query except Q091
    (see `AGENTIC_CASE_OVERRIDES`) - a document can be "present" in context
    while the one chunk that actually carries the needed fact is not (Day
    14's `chunk-gap-q016` case proved this pattern first). This is what
    catches Q091's "POL-001 is there, but not chunk-4" gap - deterministically,
    from chunk ids alone, with no LLM call needed to know the fact is
    probably missing (see the module docstring's "Recursive RAG, defined"
    section for why this chunk-level check is the trigger signal instead of
    checking the generated answer's prose for the word "Band 3").
    """
    missing_doc_ids = sorted(primary_expected_doc_ids(query_row) - context_doc_ids(sources))

    actual_chunk_ids = {source["chunk_id"] for source in sources}
    missing_chunk_ids = sorted(set(required_chunk_ids) - actual_chunk_ids)

    return {"missing_doc_ids": missing_doc_ids, "missing_chunk_ids": missing_chunk_ids}


def decide_trigger(missing_doc_ids, missing_chunk_ids):
    """Pick one trigger reason from measured evidence, or None.

    A plain, deterministic priority rule - no scoring, no LLM: a missing
    *document* is the more severe gap (an entire document's worth of
    evidence is absent, as in Q092), so it is checked first. A missing
    *chunk* inside an already-present document (Q091) is checked second.
    `None` means "nothing missing by either signal" - the control case
    (Q001, Q005) falls through to this by construction, not because of a
    hardcoded query-id exception.
    """
    if missing_doc_ids:
        return TRIGGER_MISSING_DOC
    if missing_chunk_ids:
        return TRIGGER_MISSING_CHUNK
    return None


# ---------------------------------------------------------------------------
# Step 5 of the loop: "merge or compare the follow-up sources explicitly."
# ---------------------------------------------------------------------------


def merge_sources(first_pass_sources, second_pass_sources):
    """Combine first- and second-pass sources under `MERGE_POLICY_DESCRIPTION`.

    First-pass sources are copied through unchanged, in their original
    order - the second pass is additive-only. Any second-pass source whose
    `chunk_id` was not already retrieved in the first pass is appended
    afterward, in the second pass's own rank order. Because nothing is ever
    removed or reordered, any change in `evaluate_missing_evidence`'s
    output between the first-pass-only sources and this merged list is
    attributable entirely to what the second pass newly found - which is
    exactly what "print the delta" (Block 3A step 6) needs to be honest.
    """
    seen_chunk_ids = {source["chunk_id"] for source in first_pass_sources}
    merged = list(first_pass_sources)
    for source in second_pass_sources:
        if source["chunk_id"] not in seen_chunk_ids:
            merged.append(source)
            seen_chunk_ids.add(source["chunk_id"])
    return merged


# ---------------------------------------------------------------------------
# The full five/six-step loop (Block 3A's "recommended behavior"), assembled
# from the pieces above. This is the one function a caller (main(), or a
# test) actually calls per query.
# ---------------------------------------------------------------------------


def run_recursive_retrieval(query_row, retrieve_fn, case_overrides=None):
    """Run the bounded recursive-retrieval loop for one query.

    `retrieve_fn(query_text, config) -> sources` is the injected retrieval
    step (see the module docstring's "Testability boundary") - this
    function itself never imports a model or the corpus. `case_overrides`
    defaults to `AGENTIC_CASE_OVERRIDES`; tests pass their own small dict so
    they never depend on this module's specific Q091/Q092 wiring.

    The steps, matching Block 3A's recommended behavior one-to-one:

    1. Run first-pass retrieval under this query's normal config
       (`reranking.retrieval_config_for_query_type` - the same config
       `generation.py`'s real entry point already uses, so this experiment
       measures the loop's *addition* on top of current production
       behavior, not some other baseline).
    2. Evaluate missing evidence (`evaluate_missing_evidence`).
    3. Decide whether to trigger a second pass (`decide_trigger`) - if not,
       stop immediately with `STOP_NO_MISSING_EVIDENCE`. This is the
       no-second-pass control path: `retrieve_fn` is called exactly ONCE
       for a clean query, which is itself the proof the loop is selective,
       not applied globally (see `tests/test_agentic_retrieval.py`'s
       `test_no_trigger_control_only_calls_retrieve_fn_once`).
    4. If triggered but this query has no known follow-up query in
       `case_overrides`, stop honestly rather than guessing one
       (`STOP_NO_FOLLOWUP_QUERY_DEFINED`) - this is what keeps the "boring,
       inspectable, deterministic mapping" contract honest: a query this
       module was never taught a reformulation for does not silently get a
       made-up one.
    5. Otherwise run the ONE allowed second pass with the case's
       `followup_query`, under the SAME retrieval config as the first pass
       (no new tunable introduced for the second pass).
    6. Merge (`merge_sources`) and re-evaluate missing evidence on the
       merged context. The loop then stops unconditionally - there is no
       third pass, no matter what the merged result looks like - with
       either `STOP_FIXED_AFTER_SECOND_PASS` or
       `STOP_STILL_MISSING_AFTER_MAX_PASSES`.

    The returned dict is the state object the Day 16 route doc's "Key
    concepts" section describes: original query, first-pass evidence,
    trigger reason, reformulated query, second-pass evidence, merge policy,
    final evidence, and stop reason - everything needed to print a
    before/after table without re-running anything.

    `missing_doc_status` (used by Q092) answers the route doc's explicit
    requirement to report multiple missing documents SEPARATELY rather than
    as one blended claim: it is a `{doc_id: {"found_after_merge": bool}}`
    map, one entry per document that was missing after the first pass, so
    "CONTRACT-005 was recovered but POL-002 was not" (or vice versa, or
    neither) is a fact this function computes and returns, not something a
    caller has to infer from a single pass/fail flag.
    """
    if case_overrides is None:
        case_overrides = AGENTIC_CASE_OVERRIDES

    query_id = query_row["query_id"]
    case_override = case_overrides.get(query_id, {})
    required_chunk_ids = case_override.get("required_chunk_ids", ())

    # Step 1: first pass, under this query's normal production config.
    config = retrieval_config_for_query_type(query_row["query_type"])
    first_pass_query = query_row["query"]
    first_pass_sources = retrieve_fn(first_pass_query, config)

    # Step 2: evaluate.
    first_pass_missing = evaluate_missing_evidence(query_row, first_pass_sources, required_chunk_ids)

    state = {
        "query_id": query_id,
        "first_pass_query": first_pass_query,
        "first_pass_doc_ids": sorted(context_doc_ids(first_pass_sources)),
        "first_pass_chunk_ids": sorted(source["chunk_id"] for source in first_pass_sources),
        "first_pass_missing_doc_ids": first_pass_missing["missing_doc_ids"],
        "first_pass_missing_chunk_ids": first_pass_missing["missing_chunk_ids"],
        "trigger_reason": None,
        "followup_query": None,
        "second_pass_doc_ids": None,
        "second_pass_chunk_ids": None,
        "merge_policy": None,
        "final_missing_doc_ids": first_pass_missing["missing_doc_ids"],
        "final_missing_chunk_ids": first_pass_missing["missing_chunk_ids"],
        "missing_doc_status": {
            doc_id: {"found_after_merge": False} for doc_id in first_pass_missing["missing_doc_ids"]
        },
        "stop_reason": STOP_NO_MISSING_EVIDENCE,
    }

    # Step 3: decide.
    trigger_reason = decide_trigger(first_pass_missing["missing_doc_ids"], first_pass_missing["missing_chunk_ids"])
    state["trigger_reason"] = trigger_reason
    if trigger_reason is None:
        return state  # control path: exactly one retrieve_fn call total

    # Step 4: is there a known, targeted follow-up query for this trigger?
    followup_query = case_override.get("followup_query")
    if followup_query is None:
        state["stop_reason"] = STOP_NO_FOLLOWUP_QUERY_DEFINED
        return state

    # Step 5: the one allowed second pass, same retrieval config as pass 1.
    state["followup_query"] = followup_query
    second_pass_sources = retrieve_fn(followup_query, config)
    state["second_pass_doc_ids"] = sorted(context_doc_ids(second_pass_sources))
    state["second_pass_chunk_ids"] = sorted(source["chunk_id"] for source in second_pass_sources)

    # Step 6: merge, re-evaluate, and stop - no further passes regardless
    # of the outcome.
    merged_sources = merge_sources(first_pass_sources, second_pass_sources)
    state["merge_policy"] = MERGE_POLICY_DESCRIPTION

    final_missing = evaluate_missing_evidence(query_row, merged_sources, required_chunk_ids)
    state["final_missing_doc_ids"] = final_missing["missing_doc_ids"]
    state["final_missing_chunk_ids"] = final_missing["missing_chunk_ids"]

    merged_doc_ids = context_doc_ids(merged_sources)
    for doc_id in state["missing_doc_status"]:
        state["missing_doc_status"][doc_id] = {"found_after_merge": doc_id in merged_doc_ids}

    fixed = not final_missing["missing_doc_ids"] and not final_missing["missing_chunk_ids"]
    state["stop_reason"] = STOP_FIXED_AFTER_SECOND_PASS if fixed else STOP_STILL_MISSING_AFTER_MAX_PASSES

    return state


# ---------------------------------------------------------------------------
# The live retrieve_fn: the only place this module touches the real
# pipeline. Everything above this line is pure/testable without it.
# ---------------------------------------------------------------------------


def make_live_retrieve_fn(chunk_lexical_index, chunk_semantic_index, embedding_model, cross_encoder_model):
    """Build a real `retrieve_fn(query_text, config) -> sources` closure.

    Binds the (expensive-to-build) index/model objects `main()` builds once,
    and delegates to the exact same `reranking.two_stage_rerank` +
    `generation.build_sources` pair every other module's live demo already
    uses - no new retrieval code, just the standard pipeline called with
    whatever query text `run_recursive_retrieval` hands it (the original
    query on pass 1, a reformulated query on pass 2).
    """
    from reranking import two_stage_rerank

    def retrieve_fn(query_text, config):
        ranked_chunks = two_stage_rerank(
            query_text,
            chunk_lexical_index,
            chunk_semantic_index,
            embedding_model,
            cross_encoder_model,
            **config,
        )
        return build_sources(ranked_chunks)

    return retrieve_fn


# ---------------------------------------------------------------------------
# Demo / evidence-capture entry point: run the loop for two controls (Q001,
# Q005) and the two Day 16 target cases (Q091, Q092), print a full
# before/after trace for each, then a compact table for docs/eval-report.md.
# ---------------------------------------------------------------------------

# Q001 (threshold, single primary doc) and Q005 (multi_doc, already fine per
# Day 15's full-slice remeasurement) are the no-second-pass controls Block
# 3A explicitly asks for. Q091 and Q092 are the two measured Day 16 target
# cases. Order matters only for print output, not for behavior.
DEMO_QUERY_IDS = ["Q001", "Q005", "Q091", "Q092"]


def _print_case_trace(state):
    print(f"\n{state['query_id']}: {state['first_pass_query']}")
    print(f"  first-pass docs in context:   {state['first_pass_doc_ids']}")
    print(f"  first-pass missing doc(s):    {state['first_pass_missing_doc_ids'] or '(none)'}")
    print(f"  first-pass missing chunk(s):  {state['first_pass_missing_chunk_ids'] or '(none)'}")
    print(f"  trigger reason:               {state['trigger_reason'] or '(no trigger - control case)'}")

    if state["followup_query"] is None:
        print(f"  stop reason:                  {state['stop_reason']}")
        return

    print(f"  follow-up query:              {state['followup_query']!r}")
    print(f"  second-pass docs in context:  {state['second_pass_doc_ids']}")
    print(f"  merge policy:                 {state['merge_policy']}")
    print(f"  final missing doc(s):         {state['final_missing_doc_ids'] or '(none)'}")
    print(f"  final missing chunk(s):       {state['final_missing_chunk_ids'] or '(none)'}")

    if state["missing_doc_status"]:
        print("  per-document outcome (reported separately, not blended):")
        for doc_id, status in state["missing_doc_status"].items():
            verdict = "RECOVERED" if status["found_after_merge"] else "still missing"
            print(f"    {doc_id}: {verdict}")

    print(f"  stop reason:                  {state['stop_reason']}")


def _print_summary_table(states):
    print("\n" + "=" * 78)
    print("Summary table (paste into docs/eval-report.md):")
    print("=" * 78)
    header = "| query_id | trigger_reason | first_pass_missing | final_missing | stop_reason |"
    separator = "|---|---|---|---|---|"
    print(header)
    print(separator)
    for state in states:
        first_missing = state["first_pass_missing_doc_ids"] + state["first_pass_missing_chunk_ids"]
        final_missing = state["final_missing_doc_ids"] + state["final_missing_chunk_ids"]
        row = (
            f"| {state['query_id']} "
            f"| {state['trigger_reason'] or '-'} "
            f"| {first_missing or '(none)'} "
            f"| {final_missing or '(none)'} "
            f"| {state['stop_reason']} |"
        )
        print(row)


def main() -> None:
    """Build the real pipeline once, then run the loop for every demo query.

    Mirrors the exact pipeline-construction sequence `reranking.main()`,
    `generation.main()`, and `multi_doc_slice_eval.main()` already use
    (`load_data` -> `chunk_corpus` -> load embedding model -> build both
    chunk indexes -> load the cross-encoder) - nothing new is built here,
    only wired into `make_live_retrieve_fn` above.
    """
    from chunked_search import build_chunk_lexical_index, build_chunk_semantic_index
    from chunking import chunk_corpus
    from hybrid_search import load_example_queries
    from preprocessing import load_data
    from reranking import load_cross_encoder
    from semantic_search import load_embedding_model

    data = load_data()
    chunks = chunk_corpus(data)
    embedding_model = load_embedding_model()
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
    cross_encoder_model = load_cross_encoder()

    retrieve_fn = make_live_retrieve_fn(
        chunk_lexical_index, chunk_semantic_index, embedding_model, cross_encoder_model
    )

    queries_by_id = {query["query_id"]: query for query in load_example_queries()}

    states = []
    for query_id in DEMO_QUERY_IDS:
        state = run_recursive_retrieval(queries_by_id[query_id], retrieve_fn)
        _print_case_trace(state)
        states.append(state)

    _print_summary_table(states)


if __name__ == "__main__":
    main()
