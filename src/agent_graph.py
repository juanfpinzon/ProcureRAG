"""Day 17 (Block 3A): ProcureRAG's recursive retrieval as a LangGraph state graph.

**What changes from Day 16, and what does not.** `agentic_retrieval.run_recursive_retrieval`
already *behaves* like a graph: it keeps a state dict, runs a retrieval step,
diagnoses missing evidence, decides whether to branch, optionally runs one more
retrieval pass, and stops with a named reason. But that control flow is hidden
inside one function's `if ...: return state` statements. This module expresses
the SAME control flow explicitly, as a LangGraph `StateGraph`:

    START -> retrieve -> diagnose --route_after_diagnosis--> generate ----------> END
                            ^                           |--> report_gap --------> END
                            |                           '--> recursive_retrieve -.
                            '----------------------------------------------------'

(`python src/agent_graph.py` prints the real Mermaid diagram LangGraph builds
from the code below, so this sketch can be checked against the real thing.)

The building blocks are NOT rewritten. Every node delegates to a function that
already exists and is already tested:

- retrieval: the injected `retrieve_fn(query_text, config) -> sources` (live
  version: `agentic_retrieval.make_live_retrieve_fn`), with the config from
  `reranking.retrieval_config_for_query_type`;
- diagnosis: `agentic_retrieval.evaluate_missing_evidence` + `decide_trigger`;
- merging a second pass into the first: `agentic_retrieval.merge_sources`;
- answering: `generation.generate_answer`;
- vocabulary: Day 16's `STOP_*` constants and `AGENTIC_CASE_OVERRIDES` table.

The only new code here is orchestration: an explicit state schema, the nodes
that read and update it, the edges between them, and one router.

**The four LangGraph ideas, mapped onto ProcureRAG.**

- *State* (`ProcureRAGState`): one shared dict that flows through the graph.
  A node never mutates it in place. It returns a small dict with only the
  keys it changed, and LangGraph merges that update into the state before
  the next node runs.
- *Node*: a plain Python function `state -> partial update`, for example
  `retrieve_node` or `diagnose_node` below.
- *Edge*: a fixed transition. `retrieve -> diagnose` always happens, no
  decision involved.
- *Conditional edge / router*: a function that READS state and returns the
  name of the next node (`route_after_diagnosis`). A router never writes
  state. It only picks the path, and the node at the end of that path does
  the work and records what happened.

**Chain vs. router vs. graph vs. agent, using this repo.**

- Chain: a fixed sequence, retrieve -> generate. That is what
  `generation.main()` still does today.
- Router: one decision point choosing between branches. Here, `diagnose`
  leads to `generate`, `recursive_retrieve`, or `report_gap`.
- Graph: state + nodes + edges, *including cycles*. `recursive_retrieve`
  loops back to `diagnose`, so the same diagnosis code re-checks the merged
  context. A chain cannot express that loop.
- Agent: a graph where a *model* chooses the next action or tool. This
  module is deliberately NOT that. The router is ordinary deterministic code
  over measured evidence (missing doc ids / chunk ids), so every route is
  reproducible and unit-testable without an LLM.

**Why the loop cannot run forever.** Two layers:

1. The real stop condition lives in state. `route_after_diagnosis` refuses
   to take the recursive route once `retrieval_passes` reaches
   `MAX_RETRIEVAL_PASSES` (2: the first pass plus Day 16's one allowed
   follow-up pass).
2. A safety net in case (1) ever has a bug: LangGraph's `recursion_limit`,
   the maximum number of steps before it raises `GraphRecursionError`.
   Careful: in this installed LangGraph version (1.2.11) the default is
   10007, not the 25 many tutorials quote (25 is an older langchain_core
   default). With a live retrieve_fn, a broken router would make ~5,000
   retrieval passes before that default stopped it. So `build_graph` sets
   `GRAPH_RECURSION_LIMIT` explicitly (measured: a deliberately broken
   router is stopped after 5 retrieval calls).

**Honest limitation: the diagnosis uses gold labels.** `evaluate_missing_evidence`
compares retrieved sources against the query row's `relevance_grades`. Only a
labeled eval query has those. So this graph is *eval-time* orchestration over
the 93 labeled corpus queries, not a production agent for arbitrary user
questions. A production router would need a label-free signal (for example an
LLM relevance grader, or a reranker-score threshold). Day 16 had the same
limitation. The graph just makes it visible, because you can see exactly which
state field the router reads.

**Testability boundary (same pattern as Day 16).** The expensive or
non-deterministic parts, retrieval (`retrieve_fn`) and the LLM (`client`), are
passed INTO `build_graph`. It binds them into the node functions with
`functools.partial`. Tests hand in small fakes, so every route can be exercised
in milliseconds with no models, corpus, or network (`tests/test_agent_graph.py`).

**Observability.** LangGraph sends every node's input/output to LangSmith
automatically when `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are set in
the environment. `main()` loads `.env`, so adding `LANGSMITH_TRACING=true`
there is enough. This module contains no tracing code of its own.
"""

import argparse
import operator
from functools import partial
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from agentic_retrieval import (
    AGENTIC_CASE_OVERRIDES,
    STOP_FIXED_AFTER_SECOND_PASS,
    STOP_NO_FOLLOWUP_QUERY_DEFINED,
    STOP_NO_MISSING_EVIDENCE,
    STOP_STILL_MISSING_AFTER_MAX_PASSES,
    decide_trigger,
    evaluate_missing_evidence,
    merge_sources,
)
from generation import generate_answer
from generation_eval import context_doc_ids
from reranking import retrieval_config_for_query_type

# ---------------------------------------------------------------------------
# Route labels: the only values `route_after_diagnosis` may return. In this
# graph each label is simply the name of the node it leads to, so the
# route history in state reads like the path the run actually took.
# ---------------------------------------------------------------------------

ROUTE_GENERATE = "generate"  # evidence complete -> safe to answer
ROUTE_RECURSIVE_RETRIEVE = "recursive_retrieve"  # gap found + a targeted follow-up is allowed
ROUTE_REPORT_GAP = "report_gap"  # gap found, but no safe way to fix it -> say so, don't guess

# The loop budget: pass 1 (the normal query) + at most one targeted follow-up
# pass. The same "exactly one extra pass" contract Day 16 enforced, now
# enforced by the router reading `retrieval_passes` from state.
MAX_RETRIEVAL_PASSES = 2

# LangGraph's step limit for one run (the safety net behind the budget
# above, see the module docstring). The longest legitimate run is 5 steps:
# retrieve -> diagnose -> recursive_retrieve -> diagnose -> generate/report_gap.
# 10 leaves 2x headroom while still failing fast if the loop ever runs away.
GRAPH_RECURSION_LIMIT = 10

# The explicit "not generated" marker. When the graph reaches `generate` but
# no LLM client was wired in (tests, or the default demo run), the answer
# field still gets a clear value. It never stays empty, and nobody has to
# guess whether an empty answer means "skipped" or "the model returned nothing".
ANSWER_NOT_GENERATED = "[not generated: evidence was complete, but no LLM client was passed to build_graph]"


# ---------------------------------------------------------------------------
# The state schema: the contract between nodes.
#
# A `TypedDict` is just a dict with declared keys and value types. LangGraph
# uses it to know which keys ("channels") the state has, and how to combine
# a node's update into each one:
#
# - Plain fields (e.g. `sources: list[dict]`) are OVERWRITTEN by an update:
#   the last node to write `sources` wins.
# - `Annotated[list[...], operator.add]` fields use a *reducer*: an update is
#   COMBINED with the existing value using `operator.add`, which for lists
#   means "append". A node returning `{"trace": ["one line"]}` adds one line
#   to the trace instead of replacing the whole list. That is what makes
#   these three fields an append-only audit log across the loop.
# ---------------------------------------------------------------------------


class ProcureRAGState(TypedDict):
    # --- Inputs: set once by make_initial_state(), never changed by a node ---
    query: str  # the buyer's question, e.g. "What approvals ... EUR 120,000 SaaS renewal?"
    query_id: str  # e.g. "Q091". Known because these are labeled corpus queries
    query_type: str  # e.g. "multi_doc". Picks the retrieval config
    relevance_grades: dict[str, int]  # gold labels {doc_id: grade}. What `diagnose` checks against
    acceptable_chunk_ids: list[str]  # chunk-level requirement (only Q091 has one). ANY ONE suffices
    followup_query: str | None  # the ONE targeted follow-up this query may run. None = none known

    # --- Retrieval: written by `retrieve` (pass 1) and `recursive_retrieve` (pass 2) ---
    retrieval_config: dict  # pool_size / top_k / max_chunks_per_document, reused on pass 2
    sources: list[dict]  # the CURRENT context (merged after pass 2), `generation.build_sources` shape
    retrieval_passes: int  # how many retrieval passes have run so far (1 or 2)

    # --- Diagnosis: `diagnose` appends one entry after every retrieval pass ---
    # Each entry: {"after_pass", "missing_doc_ids", "missing_chunk_ids", "trigger_reason"}.
    # diagnoses[0] is the "before" evidence, diagnoses[-1] the "after".
    diagnoses: Annotated[list[dict], operator.add]

    # --- Outcome: written by whichever end node the router picked ---
    answer: str  # a generated answer, the gap report, or ANSWER_NOT_GENERATED
    citations: dict | None  # `generation.validate_citations` report. None if nothing was generated
    stop_reason: str  # one of Day 16's STOP_* constants

    # --- Audit trail: appended by nodes, never overwritten ---
    route_history: Annotated[list[str], operator.add]  # routes taken, in order
    trace: Annotated[list[str], operator.add]  # one human-readable line per node that ran


def make_initial_state(query_row, case_overrides=None):
    """Build the graph's starting state from one labeled corpus query row.

    Only the INPUT fields are filled here. Everything else (sources,
    diagnoses, answer, ...) is written by the nodes as the graph runs, so
    reading the final state tells you which nodes actually ran.

    The follow-up query and chunk requirement come from Day 16's
    `AGENTIC_CASE_OVERRIDES` table, the same hand-written table
    `run_recursive_retrieval` uses. Putting them into state up front is what
    lets the router be a pure function of state. It never has to reach out
    to a global table to decide, which also makes it trivial to test with
    hand-built states. Tests pass their own `case_overrides` for synthetic
    query ids, as they did for Day 16.
    """
    if case_overrides is None:
        case_overrides = AGENTIC_CASE_OVERRIDES
    override = case_overrides.get(query_row["query_id"], {})

    return {
        "query": query_row["query"],
        "query_id": query_row["query_id"],
        "query_type": query_row["query_type"],
        "relevance_grades": query_row["relevance_grades"],
        "acceptable_chunk_ids": list(override.get("acceptable_chunk_ids", ())),
        "followup_query": override.get("followup_query"),
    }


# ---------------------------------------------------------------------------
# Nodes. Each one takes the current state and returns ONLY the keys it
# changed. Nodes that need an injected dependency (`retrieve_fn`, `client`)
# take it as an extra argument. `build_graph` binds that argument in advance
# with `functools.partial`, so LangGraph itself only ever calls `node(state)`.
# ---------------------------------------------------------------------------


def retrieve_node(state, retrieve_fn):
    """Pass 1: retrieve context for the buyer's original question.

    Uses the exact config production uses for this query type
    (`reranking.retrieval_config_for_query_type`). The graph adds routing on
    top of the current retrieval baseline and does not change the baseline.
    The config is saved in state so the follow-up pass can reuse it
    unchanged, as Day 16 did.
    """
    config = retrieval_config_for_query_type(state["query_type"])
    sources = retrieve_fn(state["query"], config)

    return {
        "retrieval_config": config,
        "sources": sources,
        "retrieval_passes": 1,
        "trace": [
            f"retrieve: pass 1 with {config} -> {len(sources)} sources "
            f"from docs {sorted(context_doc_ids(sources))}"
        ],
    }


def diagnose_node(state):
    """Measure what required evidence is still missing from `sources`.

    Runs after EVERY retrieval pass (it sits on the loop), so the same code
    checks both the first-pass context and the merged context. No injected
    dependency: evaluating evidence against labels is pure, cheap, and
    deterministic, so there is nothing to fake.

    `evaluate_missing_evidence` expects a query row, but only reads its
    `relevance_grades`, so a two-key row rebuilt from state is enough.

    The node only records the diagnosis. It does not choose the next step.
    That is the router's job (`route_after_diagnosis`, below). Keeping
    "measure" and "decide" separate is what lets each be tested on its own.
    """
    query_row = {"query_id": state["query_id"], "relevance_grades": state["relevance_grades"]}
    missing = evaluate_missing_evidence(query_row, state["sources"], state["acceptable_chunk_ids"])

    # Day 16's priority rule: a missing document outranks a missing chunk.
    # None means nothing is missing by either measure.
    trigger_reason = decide_trigger(missing["missing_doc_ids"], missing["missing_chunk_ids"])

    diagnosis = {
        "after_pass": state["retrieval_passes"],
        "missing_doc_ids": missing["missing_doc_ids"],
        "missing_chunk_ids": missing["missing_chunk_ids"],
        "trigger_reason": trigger_reason,
    }

    return {
        # A one-item list: the `operator.add` reducer APPENDS it to the
        # diagnoses already in state, so pass 1's diagnosis survives pass 2.
        "diagnoses": [diagnosis],
        "trace": [
            f"diagnose: after pass {diagnosis['after_pass']} -> "
            f"missing docs {diagnosis['missing_doc_ids'] or 'none'}, "
            f"missing chunks {diagnosis['missing_chunk_ids'] or 'none'}, "
            f"trigger {trigger_reason or 'none'}"
        ],
    }


def route_after_diagnosis(state):
    """The router (conditional edge): read the latest diagnosis, pick a route.

    Pure and deterministic: it reads state, returns one of the three
    `ROUTE_*` labels, and writes nothing. The checks run in a fixed order:

    1. Nothing missing -> `generate`. The Q001/Q005 controls take this route
       straight after pass 1. Q091/Q092 take it after pass 2 if the
       follow-up worked.
    2. Something is missing, but the pass budget is spent -> `report_gap`.
       This is the stop condition that bounds the loop, and it is checked
       BEFORE the follow-up check below, so a query that still has a
       follow-up available can never loop a third time.
    3. Something is missing and no targeted follow-up is known for this
       query -> `report_gap`. The graph does not invent a reformulation.
    4. Otherwise -> `recursive_retrieve`: a measured gap plus a known,
       targeted follow-up query (Q091's missing chunk, Q092's missing docs).
    """
    latest = state["diagnoses"][-1]

    if latest["trigger_reason"] is None:
        return ROUTE_GENERATE
    if state["retrieval_passes"] >= MAX_RETRIEVAL_PASSES:
        return ROUTE_REPORT_GAP
    if state["followup_query"] is None:
        return ROUTE_REPORT_GAP
    return ROUTE_RECURSIVE_RETRIEVE


def recursive_retrieve_node(state, retrieve_fn):
    """Pass 2: run the targeted follow-up query and merge its results in.

    Same retrieval config as pass 1, so only the query text changes. The
    merge is Day 16's additive-only `merge_sources`: every first-pass source
    stays, in order, and the second pass can only APPEND chunks it newly
    found. Because of that, everything past the first-pass length in the
    merged list is new, which is how `added_chunk_ids` is computed below.

    After this node, the fixed edge `recursive_retrieve -> diagnose` sends
    the merged context back through the SAME diagnosis code, and the router
    decides again. That edge is the cycle in this graph.
    """
    first_pass_sources = state["sources"]
    second_pass_sources = retrieve_fn(state["followup_query"], state["retrieval_config"])
    merged = merge_sources(first_pass_sources, second_pass_sources)

    # Renumber citations. Each retrieval pass numbers its own sources
    # 1, 2, 3, ... (`generation.build_sources`), so an appended second-pass
    # chunk arrives with a source_id that is already used in the first pass.
    # Day 16 never generated an answer, so it never noticed. Here, `generate`
    # would show the model two different "[1]" sources and citations would
    # become ambiguous. First-pass sources are already 1..n in order, so they
    # keep their numbers. Only the appended chunks get new ones (n+1, n+2, ...).
    renumbered = [{**source, "source_id": number} for number, source in enumerate(merged, start=1)]

    added_chunk_ids = [source["chunk_id"] for source in renumbered[len(first_pass_sources):]]
    passes = state["retrieval_passes"] + 1

    return {
        "sources": renumbered,
        "retrieval_passes": passes,
        "route_history": [ROUTE_RECURSIVE_RETRIEVE],
        "trace": [
            f"recursive_retrieve: pass {passes} with follow-up {state['followup_query']!r} "
            f"-> added {len(added_chunk_ids)} new chunk(s) {added_chunk_ids}"
        ],
    }


def generate_node(state, client):
    """End node for complete evidence: answer from `sources` (if an LLM is wired in).

    The router only sends a run here when nothing is missing, so the only
    open question for `stop_reason` is whether it took one pass or two.

    `client` is the same `client(prompt) -> text` boundary
    `generation.generate_answer` has used since Day 10. With `client=None`
    (tests, and the default demo run) the node still records an explicit
    "not generated" marker. The routing decision ("evidence is complete,
    safe to answer") does not depend on whether an LLM is available.
    """
    passes = state["retrieval_passes"]
    stop_reason = STOP_NO_MISSING_EVIDENCE if passes == 1 else STOP_FIXED_AFTER_SECOND_PASS

    if client is None:
        answer, citations = ANSWER_NOT_GENERATED, None
        outcome = "answer not generated (no LLM client)"
    else:
        result = generate_answer(state["query"], state["sources"], client)
        answer, citations = result["answer"], result["citations"]
        outcome = f"answered, citing sources {citations['valid_ids']}, orphan citations {citations['orphan_ids']}"

    return {
        "answer": answer,
        "citations": citations,
        "stop_reason": stop_reason,
        "route_history": [ROUTE_GENERATE],
        "trace": [f"generate: evidence complete after {passes} pass(es) -> {outcome}"],
    }


def report_gap_node(state):
    """End node for evidence that is still missing: report the gap, don't answer.

    No LLM call on purpose. Answering with required primary evidence
    missing is exactly what produced the incomplete multi-doc answers Day 13
    diagnosed. The gap report names what is missing, so a reviewer can see
    why the graph stopped.

    The router sends a run here for one of two reasons. The pass count
    tells them apart: at the budget means "tried a follow-up, still missing",
    below it means "never had a safe follow-up to try".
    """
    latest = state["diagnoses"][-1]
    passes = state["retrieval_passes"]

    if passes >= MAX_RETRIEVAL_PASSES:
        stop_reason = STOP_STILL_MISSING_AFTER_MAX_PASSES
    else:
        stop_reason = STOP_NO_FOLLOWUP_QUERY_DEFINED

    missing_parts = []
    if latest["missing_doc_ids"]:
        missing_parts.append(f"primary document(s) {latest['missing_doc_ids']}")
    if latest["missing_chunk_ids"]:
        missing_parts.append(f"any one of chunk(s) {latest['missing_chunk_ids']}")
    answer = (
        "Not answered: the retrieved context is still missing required evidence "
        f"({' and '.join(missing_parts)}) after {passes} retrieval pass(es)."
    )

    return {
        "answer": answer,
        "citations": None,
        "stop_reason": stop_reason,
        "route_history": [ROUTE_REPORT_GAP],
        "trace": [f"report_gap: {stop_reason} -> {answer}"],
    }


# ---------------------------------------------------------------------------
# Wiring: nodes + edges -> a compiled, runnable graph.
# ---------------------------------------------------------------------------


def build_graph(retrieve_fn, client=None):
    """Assemble and compile the ProcureRAG state graph.

    `retrieve_fn` and `client` are the two injected boundaries (see the
    module docstring). `partial(retrieve_node, retrieve_fn=retrieve_fn)`
    creates a new one-argument function, `node(state)`, with `retrieve_fn`
    already filled in. That is the shape LangGraph calls.

    `compile()` checks the wiring (for example that every edge points at a
    real node) and returns a runnable graph. `.with_config(...)` bakes the
    tight `GRAPH_RECURSION_LIMIT` into every run, so a caller cannot forget
    it. Run the graph with `graph.invoke(make_initial_state(query_row))`,
    which returns the final state dict.
    """
    builder = StateGraph(ProcureRAGState)

    # Nodes: a name and the function to run there.
    builder.add_node("retrieve", partial(retrieve_node, retrieve_fn=retrieve_fn))
    builder.add_node("diagnose", diagnose_node)
    builder.add_node("recursive_retrieve", partial(recursive_retrieve_node, retrieve_fn=retrieve_fn))
    builder.add_node("generate", partial(generate_node, client=client))
    builder.add_node("report_gap", report_gap_node)

    # Fixed edges: always taken, no decision.
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "diagnose")

    # The one conditional edge: after `diagnose`, call the router and follow
    # the route it returns. The dict maps each allowed route label to its
    # destination node. LangGraph uses it to reject an unknown label and to
    # draw every possible branch in the Mermaid diagram.
    builder.add_conditional_edges(
        "diagnose",
        route_after_diagnosis,
        {
            ROUTE_GENERATE: "generate",
            ROUTE_RECURSIVE_RETRIEVE: "recursive_retrieve",
            ROUTE_REPORT_GAP: "report_gap",
        },
    )

    # The cycle: the merged context goes back through the same diagnosis.
    builder.add_edge("recursive_retrieve", "diagnose")

    # Both end nodes finish the run.
    builder.add_edge("generate", END)
    builder.add_edge("report_gap", END)

    return builder.compile().with_config(recursion_limit=GRAPH_RECURSION_LIMIT)


# ---------------------------------------------------------------------------
# Demo / evidence capture: the same four queries as Day 16, now run through
# the graph. Retrieval is live (local models, no API key needed).
# Generation is opt-in with --generate (needs OPENROUTER_API_KEY), so the
# default run makes no network calls and costs nothing.
# ---------------------------------------------------------------------------

DEMO_QUERY_IDS = ["Q001", "Q005", "Q091", "Q092"]


def _print_case(state):
    print(f"\n{state['query_id']} ({state['query_type']}): {state['query']}")
    for line in state["trace"]:
        print(f"  {line}")
    print(f"  route history: {state['route_history']}")
    print(f"  stop reason:   {state['stop_reason']}")
    print(f"  answer:        {state['answer']}")


def _print_summary_table(states):
    print("\n" + "=" * 78)
    print("Summary table (for docs/learning-log.md / docs/eval-report.md):")
    print("=" * 78)
    print("| query_id | route_history | first_pass_missing | final_missing | stop_reason |")
    print("|---|---|---|---|---|")
    for state in states:
        first, final = state["diagnoses"][0], state["diagnoses"][-1]
        first_missing = first["missing_doc_ids"] + first["missing_chunk_ids"]
        final_missing = final["missing_doc_ids"] + final["missing_chunk_ids"]
        print(
            f"| {state['query_id']} "
            f"| {' -> '.join(state['route_history'])} "
            f"| {first_missing or '(none)'} "
            f"| {final_missing or '(none)'} "
            f"| {state['stop_reason']} |"
        )


# ---------------------------------------------------------------------------
# Whole-corpus evidence: run every labeled query through the graph (live
# retrieval, no LLM) and count which route each one took. This answers
# "how selective is the recursive branch, and how often does the graph
# refuse?" with one committed command instead of a scratch script.
# ---------------------------------------------------------------------------


def route_distribution(states):
    """Group finished graph runs by the route path they took.

    Returns `{route_path: [query_id, ...]}`, where `route_path` is the
    run's `route_history` joined with " -> " (e.g.
    "recursive_retrieve -> generate"). Pure function over final states, so
    it can be tested on fake runs without loading any model.
    """
    distribution = {}
    for state in states:
        route_path = " -> ".join(state["route_history"])
        distribution.setdefault(route_path, []).append(state["query_id"])
    return distribution


def _print_route_distribution(states):
    distribution = route_distribution(states)

    print("\n" + "=" * 78)
    print(f"Route distribution over {len(states)} queries (live retrieval, no LLM):")
    print("=" * 78)
    print("| route | queries | query_ids |")
    print("|---|---|---|")
    # Most common route first.
    for route_path, query_ids in sorted(distribution.items(), key=lambda item: -len(item[1])):
        print(f"| {route_path} | {len(query_ids)} | {', '.join(query_ids)} |")

    # Coverage of the recursive branch: of the queries whose FIRST pass
    # had an evidence gap, how many did the follow-up pass fix?
    gapped = [state for state in states if state["diagnoses"][0]["trigger_reason"] is not None]
    fixed = [state for state in gapped if state["stop_reason"] == STOP_FIXED_AFTER_SECOND_PASS]
    print(
        f"\nQueries with a first-pass evidence gap: {len(gapped)}. "
        f"Fixed by the recursive pass: {len(fixed)}. Ended in report_gap: {len(gapped) - len(fixed)}."
    )

    reported = [state for state in states if state["route_history"][-1] == ROUTE_REPORT_GAP]
    if reported:
        print("\n| query_id | query_type | stop_reason | still missing |")
        print("|---|---|---|---|")
        for state in reported:
            final = state["diagnoses"][-1]
            missing = final["missing_doc_ids"] + final["missing_chunk_ids"]
            print(f"| {state['query_id']} | {state['query_type']} | {state['stop_reason']} | {missing} |")


def main() -> None:
    """Build the live pipeline once, compile the graph once, run each demo query.

    The pipeline-building sequence is the same one `agentic_retrieval.main()`
    uses, and the live `retrieve_fn` is Day 16's own `make_live_retrieve_fn`.
    Nothing retrieval-related is rebuilt here.
    """
    parser = argparse.ArgumentParser(
        description="Day 17: run Q001/Q005/Q091/Q092 through the ProcureRAG LangGraph state graph "
        "and print each run's trace, route history, and stop reason."
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Also call the live LLM (OpenRouter, needs OPENROUTER_API_KEY) on the 'generate' route. "
        "Default: routing/retrieval only, with an explicit 'not generated' marker as the answer.",
    )
    parser.add_argument(
        "--all-queries-summary",
        action="store_true",
        help="Instead of the four demo queries, run ALL labeled corpus queries through the graph "
        "(live retrieval, no LLM) and print the route distribution plus every report_gap case.",
    )
    args = parser.parse_args()
    if args.all_queries_summary and args.generate:
        # The whole-corpus summary is routing evidence only. With a paid
        # default model, combining it with --generate would mean ~78 paid
        # LLM calls for answers this summary never prints.
        parser.error("--all-queries-summary runs without the LLM; do not combine it with --generate")

    from dotenv import load_dotenv

    from agentic_retrieval import make_live_retrieve_fn
    from chunked_search import build_chunk_lexical_index, build_chunk_semantic_index
    from chunking import chunk_corpus
    from generation import make_openrouter_client
    from hybrid_search import load_example_queries
    from preprocessing import load_data
    from reranking import load_cross_encoder
    from semantic_search import load_embedding_model

    # Loads OPENROUTER_API_KEY (only used with --generate) and, if present,
    # the LANGSMITH_* variables that switch on LangGraph's automatic tracing.
    load_dotenv()

    data = load_data()
    chunks = chunk_corpus(data)
    embedding_model = load_embedding_model()
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
    cross_encoder_model = load_cross_encoder()

    retrieve_fn = make_live_retrieve_fn(chunk_lexical_index, chunk_semantic_index, embedding_model, cross_encoder_model)
    client = make_openrouter_client() if args.generate else None

    graph = build_graph(retrieve_fn, client=client)

    if args.all_queries_summary:
        states = [graph.invoke(make_initial_state(query_row)) for query_row in load_example_queries()]
        _print_route_distribution(states)
        return

    # The diagram LangGraph derives from the wiring above: paste into any
    # Mermaid viewer (e.g. https://mermaid.live) for the whiteboard picture.
    # Dotted arrows are the conditional edges out of `diagnose`.
    print("Graph structure (Mermaid):")
    print(graph.get_graph().draw_mermaid())

    queries_by_id = {query["query_id"]: query for query in load_example_queries()}

    states = []
    for query_id in DEMO_QUERY_IDS:
        state = graph.invoke(make_initial_state(queries_by_id[query_id]))
        _print_case(state)
        states.append(state)

    _print_summary_table(states)


if __name__ == "__main__":
    main()
