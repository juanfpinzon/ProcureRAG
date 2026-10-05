"""Day 18 (Block 3A): a control plane around the Day 17 ProcureRAG graph.

**What Day 17 left uncontrolled.** `agent_graph.build_graph` decides on its
own whether to run a second retrieval pass. For Q091/Q092 that decision
changes the evidence the answer is built from (the follow-up pass appends
new chunks to the context), yet nobody can look at it before it happens,
stop it, or change the follow-up query. And once `graph.invoke` returns,
the intermediate states are gone: only the final dict is left.

This module keeps the Day 17 graph's behavior and adds three controls. Each
one is a core LangGraph feature from LangChain Academy Modules 2/3:

1. **Checkpointer + `thread_id` (short-term memory).** The graph is compiled
   with a checkpointer (`InMemorySaver`). After every super-step (here: every
   node that runs), LangGraph saves a snapshot of the FULL state under the
   `thread_id` given in the run's config. That is what lets a run stop and
   continue later, and what lets anyone inspect the state at every step
   afterwards. One thread = one review of one query. It is NOT long-term
   memory: nothing is shared between threads, and nothing survives the
   Python process (see "Honest limits" below).

2. **`interrupt()` before the recursive pass (human-in-the-loop).** Day 17's
   router is reused unchanged, but its `recursive_retrieve` route now leads
   to one new node, `approve_followup`, before reaching `recursive_retrieve`.
   That node builds an approval request (what is missing, which follow-up
   query would run, what it costs) and calls `interrupt(request)`. The run
   pauses, the checkpointer keeps the state, and `graph.invoke` returns
   with the request under the `"__interrupt__"` key. A reviewer then resumes
   the SAME run with `graph.invoke(Command(resume=decision), same_config)`,
   choosing one of three options: approve, edit the follow-up query, or reject.

3. **State history (time travel).** Because every step was checkpointed,
   `graph.get_state_history(config)` returns every saved snapshot of the
   thread. Replaying from the paused snapshot with a different decision
   answers "what if the reviewer had rejected?" without re-running the
   first retrieval pass (see `replay_with_different_decision`).

The new graph, with the one new node marked:

    START -> retrieve -> diagnose --route_after_diagnosis--> generate ------------------> END
                            ^                           |--> report_gap ----------------> END
                            |                           '--> [approve_followup] --reject--> report_gap
                            |                                        |
                            |                                 approve / edit
                            |                                        v
                            '---------------------------------- recursive_retrieve

(`python src/agent_control_plane.py` prints the real Mermaid diagram.)

**Which runs pause, and which do not.** Only runs the router sends towards
`recursive_retrieve` pause, i.e. a measured evidence gap with a known follow-up
query (on the real corpus: Q091 and Q092, 2 of 93 queries). The 76 `generate`
runs and the 15 `report_gap` runs never reach the approval node, so they
behave exactly as in Day 17. An approved run also ends exactly as in Day 17
(same routes, sources, diagnoses, stop reason), which
`tests/test_agent_control_plane.py` checks against `agent_graph.build_graph`.

**Why `interrupt()` and not a static breakpoint.** Module 3 Lesson 2's static
breakpoint, `compile(interrupt_before=["recursive_retrieve"])`, would also
pause at the same place. But a static breakpoint carries no payload (the
reviewer has to dig what to review out of the raw state) and returns no
answer: an edit means calling `graph.update_state(...)` and then
`invoke(None)`, and a reject has no clean way to change the route. With
`interrupt()` (Module 3 Lesson 4's "dynamic breakpoint"), one call sends a
structured request OUT and gets a structured decision back IN. That lets the
node validate the decision and record it in state like any other update.

**Three gotchas, all measured on the installed langgraph 1.2.11.**

1. On resume, the node that called `interrupt()` runs again FROM ITS FIRST
   LINE. This time `interrupt()` returns the reviewer's decision instead of
   pausing. So everything before `interrupt()` in `approve_followup_node` runs
   again on every resume and must be safe to repeat. It is: building the
   request only reads state.
2. To replay a past approval with a DIFFERENT decision, you cannot send
   `Command(resume=...)` to the old checkpoint. LangGraph finds the decision
   it already saved for that checkpoint and silently replays the ORIGINAL
   decision. `replay_with_different_decision` shows the pattern that works.
3. Never RAISE on a bad decision after `interrupt()` returns. The resume
   value is saved before the node finishes, so every later resume (even a
   valid one) replays the bad value and fails again: the run is stuck. So
   `approve_followup_node` calls `interrupt()` again instead (LangGraph's
   documented "validate human input" loop), and the run stays paused with
   an error message for the reviewer.

**Migration path to LangChain v1.** The decision vocabulary (`approve` /
`edit` / `reject`, with an optional reject `message`) deliberately mirrors
`langchain.agents.middleware.HumanInTheLoopMiddleware`. That middleware does
the same pause/approve/resume for TOOL CALLS inside a `create_agent` loop,
using the same `interrupt()` + checkpointer underneath. This graph has no
tool-calling model (the router is deterministic code), so it calls
`interrupt()` directly. See the Day 18 section of `docs/eval-report.md` for
the decision.

**Honest limits.**

- `InMemorySaver` keeps checkpoints in this Python process only. A real
  review queue, where the decision arrives hours later from another process,
  needs a durable checkpointer (SQLite/Postgres). The graph code would not
  change, only the `checkpointer` argument.
- The diagnosis that decides whether to ask for approval still reads gold
  labels (`relevance_grades`), the same eval-time limitation as Day 16/17.
- The pause controls a retrieval action. It says nothing about whether the
  final answer is complete. That is still measured separately.

**Observability.** As in Day 17, LangGraph traces every node to LangSmith
when the `LANGSMITH_*` tracing variables are set (`main()` loads `.env`).
On top of that, `thread_config` tags every run, and LangGraph copies the
`thread_id` into each run's metadata, so the paused run and its resume can
be found together in LangSmith. Locally, the demo prints the approval
request, the trace, and one line per saved checkpoint.
"""

import argparse
from functools import partial

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agent_graph import (
    GRAPH_RECURSION_LIMIT,
    ROUTE_GENERATE,
    ROUTE_RECURSIVE_RETRIEVE,
    ROUTE_REPORT_GAP,
    ProcureRAGState,
    diagnose_node,
    generate_node,
    make_initial_state,
    recursive_retrieve_node,
    report_gap_node,
    retrieve_node,
    route_after_diagnosis,
)
from generation_eval import context_doc_ids

# ---------------------------------------------------------------------------
# The control-plane vocabulary.
# ---------------------------------------------------------------------------

# The name of the one node this module adds to the Day 17 graph.
APPROVAL_NODE = "approve_followup"

# The three decisions a reviewer may send back. Same names, and the same
# `{"type": ...}` dict shape, as LangChain v1's HumanInTheLoopMiddleware:
#   {"type": "approve"}
#   {"type": "edit", "followup_query": "..."}   (the middleware's version edits a tool call's args)
#   {"type": "reject", "message": "why"}        (`message` is optional)
DECISION_APPROVE = "approve"
DECISION_EDIT = "edit"
DECISION_REJECT = "reject"
ALLOWED_DECISIONS = (DECISION_APPROVE, DECISION_EDIT, DECISION_REJECT)

# A new stop reason, next to Day 16's STOP_* constants. Without it, a rejected
# run would end with Day 17's "no follow-up query defined", which would be
# false: a follow-up WAS defined, and a human declined it.
STOP_FOLLOWUP_REJECTED = "followup_rejected_by_reviewer"


# ---------------------------------------------------------------------------
# State: Day 17's schema plus one field.
#
# Subclassing a TypedDict keeps every Day 17 field AND its reducer (the
# append-only `diagnoses`, `route_history`, and `trace`). So the Day 17 nodes
# below work on this state without any change.
# ---------------------------------------------------------------------------


class ControlledProcureRAGState(ProcureRAGState):
    # The reviewer's decision, written by `approve_followup` on resume:
    # {"decision", "proposed_followup_query", "approved_followup_query", "message"}.
    # Absent from the state of any run that never needed approval
    # (the controls and the no-follow-up gaps).
    approval: dict


# ---------------------------------------------------------------------------
# The approval point.
# ---------------------------------------------------------------------------


def build_approval_request(state):
    """What the reviewer sees when the run pauses: enough to decide, nothing more.

    A pure function of state. That matters because `approve_followup_node` calls
    it twice per run: once before pausing, and again when the node re-runs on
    resume (gotcha 1 in the module docstring).

    The fields answer the reviewer's three questions:

    - Why is the graph asking? `trigger_reason`, `missing_doc_ids`,
      `missing_chunk_ids` (from the latest diagnosis, i.e. the first pass).
    - What exactly would run? `proposed_action` and `proposed_followup_query`.
    - What does it cost? `first_pass_source_count`/`first_pass_doc_ids` (what
      the context holds now) and `cost_note` (what the extra pass may add).
    """
    latest = state["diagnoses"][-1]
    config = state["retrieval_config"]
    sources = state["sources"]

    return {
        "query_id": state["query_id"],
        "query": state["query"],
        "proposed_action": ROUTE_RECURSIVE_RETRIEVE,
        "proposed_followup_query": state["followup_query"],
        "trigger_reason": latest["trigger_reason"],
        "missing_doc_ids": latest["missing_doc_ids"],
        "missing_chunk_ids": latest["missing_chunk_ids"],
        "first_pass_source_count": len(sources),
        "first_pass_doc_ids": sorted(context_doc_ids(sources)),
        "cost_note": (
            f"One extra retrieval pass with the same config {config}, no LLM call. "
            f"It can append up to {config['top_k']} new chunks to the {len(sources)} sources "
            "already in context: possibly the missing evidence, but also more noise for the answer step."
        ),
        "allowed_decisions": list(ALLOWED_DECISIONS),
    }


def decision_error(decision):
    """Return why `decision` is not a usable reviewer decision, or None if it is.

    A typo like `{"type": "aprove"}` must never be treated as approval. Note
    that this function RETURNS the problem instead of raising it.
    `approve_followup_node` uses the message to ask the reviewer again (gotcha
    3 in the module docstring explains why raising would be a trap).
    """
    if not isinstance(decision, dict) or decision.get("type") not in ALLOWED_DECISIONS:
        return f"decision must be a dict whose 'type' is one of {list(ALLOWED_DECISIONS)}, got {decision!r}"

    if decision["type"] == DECISION_EDIT:
        edited_query = decision.get("followup_query")
        if not isinstance(edited_query, str) or not edited_query.strip():
            return "an 'edit' decision needs a non-empty 'followup_query' string"

    return None


def approve_followup_node(state):
    """The human approval point: pause before the second retrieval pass.

    How one run passes through this node:

    1. First time: the request is built, and `interrupt(request)` stops the
       run right there. LangGraph has already checkpointed the state, so
       `graph.invoke` returns with `result["__interrupt__"]` holding the
       request. Nothing below `interrupt()` has run yet, so no second pass
       has happened either.
    2. A reviewer calls `graph.invoke(Command(resume=decision), config)`.
       LangGraph loads the checkpoint and runs this function again from the
       top. This time `interrupt()` does not pause. It returns `decision`.
    3. If the decision is malformed, the loop calls `interrupt()` AGAIN with
       the same request plus an `"error"` field. The run stays paused, and
       `graph.invoke` returns the new request, so the reviewer sees what was
       wrong and can answer again.
    4. The valid decision is recorded. The router after this node
       (`route_after_approval`) reads that record and picks the next node.

    How the loop survives re-execution: within one node, LangGraph matches
    resume values to `interrupt()` calls by their ORDER. Each time the node
    re-runs, the first `interrupt()` returns the first answer ever given, the
    second returns the second answer, and so on. Only the first call that
    has no saved answer yet actually pauses.

    This node records the decision but does not choose the route, the same
    "measure/record vs. decide" split Day 17 used for `diagnose` vs. the
    router.
    """
    request = build_approval_request(state)

    while True:
        # The pause (step 1) and, on resume, the reviewer's answer (step 2).
        decision = interrupt(request)
        error = decision_error(decision)
        if error is None:
            break
        # Step 3: ask again, showing why the last answer was refused.
        request = {**build_approval_request(state), "error": error}

    proposed_query = state["followup_query"]
    message = decision.get("message")

    if decision["type"] == DECISION_APPROVE:
        approved_query = proposed_query
        trace_line = f"reviewer approved follow-up {proposed_query!r}"
    elif decision["type"] == DECISION_EDIT:
        approved_query = decision["followup_query"].strip()
        trace_line = f"reviewer edited follow-up {proposed_query!r} -> {approved_query!r}"
    else:  # DECISION_REJECT
        approved_query = None
        trace_line = f"reviewer rejected the follow-up pass ({message or 'no reason given'})"

    update = {
        # The audit record: what was proposed, what was decided, and why.
        "approval": {
            "decision": decision["type"],
            "proposed_followup_query": proposed_query,
            "approved_followup_query": approved_query,
            "message": message,
        },
        "trace": [f"{APPROVAL_NODE}: {trace_line}"],
    }

    if decision["type"] == DECISION_EDIT:
        # Overwrite the input field, so the UNCHANGED Day 17
        # `recursive_retrieve_node` runs the reviewer's query. The original
        # proposal is not lost: it stays in `approval` above.
        update["followup_query"] = approved_query

    return update


def route_after_approval(state):
    """Second router: approve/edit -> run the follow-up pass, reject -> report the gap.

    It returns Day 17's own route labels, so `route_history` keeps the same
    vocabulary. An approved Q091 run reads `["recursive_retrieve", "generate"]`
    exactly as in Day 17. The approval itself is recorded in `approval` and
    `trace`, not as a route.
    """
    if state["approval"]["decision"] == DECISION_REJECT:
        return ROUTE_REPORT_GAP
    return ROUTE_RECURSIVE_RETRIEVE


def controlled_report_gap_node(state):
    """Day 17's `report_gap`, plus the one stop reason it could not know about.

    Day 17's node infers its stop reason from the pass count: a gap after
    only one pass means "no follow-up query was defined". After a rejection
    that would be false. So in that one case the stop reason and the answer
    text are corrected. Every other run gets Day 17's update unchanged.
    """
    update = report_gap_node(state)

    approval = state.get("approval")
    if approval is None or approval["decision"] != DECISION_REJECT:
        return update

    reason = approval["message"] or "no reason given"
    answer = f"{update['answer']} A reviewer rejected the follow-up retrieval pass ({reason})."
    return {
        **update,
        "answer": answer,
        "stop_reason": STOP_FOLLOWUP_REJECTED,
        "trace": [f"report_gap: {STOP_FOLLOWUP_REJECTED} -> {answer}"],
    }


# ---------------------------------------------------------------------------
# Wiring: the Day 17 graph, with one gate inserted and a checkpointer.
# ---------------------------------------------------------------------------


def build_controlled_graph(retrieve_fn, client=None, checkpointer=None):
    """Assemble the Day 17 graph plus the approval node, compiled WITH a checkpointer.

    Compare with `agent_graph.build_graph`. There are three differences:

    1. One new node, `approve_followup`, and a router after it.
    2. In the router's path map, the `recursive_retrieve` label now points
       at `approve_followup` instead of at `recursive_retrieve` directly.
       The router function itself is unchanged.
    3. `compile(checkpointer=...)`. A pause is only useful with a
       checkpointer. A paused run is nothing more than "the last checkpoint,
       plus a pending interrupt", so without saved state there is nothing to
       resume. Measured on 1.2.11: without one, `interrupt()` still stops the
       run and returns `"__interrupt__"`, but the resume then fails with
       `RuntimeError: Cannot use Command(resume=...) without checkpointer`.

    `checkpointer=None` creates a fresh `InMemorySaver`, so each graph gets
    its own empty memory. Pass your own to share one between graphs, or a
    durable one in production.

    One compiled graph serves many runs: each run is told apart only by the
    `thread_id` in its config (see `thread_config`).
    """
    if checkpointer is None:
        checkpointer = InMemorySaver()

    builder = StateGraph(ControlledProcureRAGState)

    # Day 17's nodes, reused as-is. `partial` binds the injected boundaries
    # exactly as `agent_graph.build_graph` does.
    builder.add_node("retrieve", partial(retrieve_node, retrieve_fn=retrieve_fn))
    builder.add_node("diagnose", diagnose_node)
    builder.add_node("recursive_retrieve", partial(recursive_retrieve_node, retrieve_fn=retrieve_fn))
    builder.add_node("generate", partial(generate_node, client=client))
    # Same node name as Day 17, but this version also knows "rejected".
    builder.add_node("report_gap", controlled_report_gap_node)
    # The new node: the human approval point.
    builder.add_node(APPROVAL_NODE, approve_followup_node)

    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "diagnose")

    # Day 17's router, unchanged. This path map is where the gate is
    # inserted: the router still says "recursive_retrieve", but the run now
    # goes to the approval node first. The path map separates "what the
    # router decided" from "which node runs next", which is why adding a
    # gate needs no change to the router itself.
    builder.add_conditional_edges(
        "diagnose",
        route_after_diagnosis,
        {
            ROUTE_GENERATE: "generate",
            ROUTE_RECURSIVE_RETRIEVE: APPROVAL_NODE,
            ROUTE_REPORT_GAP: "report_gap",
        },
    )

    # After the reviewer's decision: run the follow-up pass, or report the gap.
    builder.add_conditional_edges(
        APPROVAL_NODE,
        route_after_approval,
        {
            ROUTE_RECURSIVE_RETRIEVE: "recursive_retrieve",
            ROUTE_REPORT_GAP: "report_gap",
        },
    )

    # Day 17's cycle and end edges, unchanged. After the second pass, the
    # router's pass budget (MAX_RETRIEVAL_PASSES) means it can never propose
    # another recursive pass, so a run asks for approval at most once.
    builder.add_edge("recursive_retrieve", "diagnose")
    builder.add_edge("generate", END)
    builder.add_edge("report_gap", END)

    # The longest run is now 6 steps (one more than Day 17, for the gate):
    # retrieve -> diagnose -> approve_followup -> recursive_retrieve -> diagnose -> generate.
    # Day 17's limit of 10 still leaves headroom.
    return builder.compile(checkpointer=checkpointer).with_config(recursion_limit=GRAPH_RECURSION_LIMIT)


def thread_config(thread_id):
    """The run config that names a thread, i.e. the key every checkpoint is saved under.

    Every call about the SAME run has to pass the same `thread_id`: the
    first `invoke`, `get_state`, and the resume. A new `thread_id` starts a
    new, empty run. That is what "short-term memory is per thread" means in
    practice.

    `tags` only matter for LangSmith: they make Day 18 control-plane runs easy
    to filter in the UI. LangGraph copies `thread_id` into every run's metadata
    on its own.
    """
    return {"configurable": {"thread_id": thread_id}, "tags": ["procurerag", "day18-control-plane"]}


# ---------------------------------------------------------------------------
# Time travel: replay the approval with a different decision.
# ---------------------------------------------------------------------------


def find_approval_checkpoint(graph, config):
    """Return the newest saved snapshot where this thread was paused at the approval node.

    `get_state_history` yields `StateSnapshot`s, newest first. Each one has
    `.values` (the full state at that point), `.next` (the node(s) that would
    run next), `.metadata` (e.g. the step number), and `.config` (which
    includes this snapshot's own `checkpoint_id`, the handle used to replay
    from it).
    """
    for snapshot in graph.get_state_history(config):
        if snapshot.next == (APPROVAL_NODE,):
            return snapshot
    raise ValueError(f"thread {config['configurable']['thread_id']!r} never paused at {APPROVAL_NODE!r}")


def replay_with_different_decision(graph, config, decision):
    """Fork the thread at its approval point and resume it with `decision`.

    The question this answers: "the reviewer approved; what would have
    happened if they had rejected (or edited) instead?" Pass-1 retrieval and
    the first diagnosis are NOT re-run. They come from the saved checkpoint,
    which is what makes the comparison cheap and fair (same first-pass
    evidence on both branches).

    Why two steps instead of `graph.invoke(Command(resume=decision), paused.config)`:
    LangGraph saves the reviewer's answer together with the paused
    checkpoint. Resuming that old checkpoint finds the saved answer and
    silently replays the ORIGINAL decision (gotcha 2, measured on 1.2.11).
    The pattern that works:

    1. `invoke(None, paused.config)`: no new input, so it re-executes from
       that checkpoint. `approve_followup` runs again, and `interrupt()` pauses
       again with a fresh request and no saved answer. That new pause is
       saved as the thread's newest checkpoint (a fork).
    2. `invoke(Command(resume=decision), config)`: resumes the thread's newest
       checkpoint, i.e. the fork, with the new decision.

    The original branch is not deleted. Its snapshots stay in
    `get_state_history`, so both outcomes remain inspectable.
    """
    paused = find_approval_checkpoint(graph, config)
    graph.invoke(None, paused.config)
    return graph.invoke(Command(resume=decision), config)


# ---------------------------------------------------------------------------
# Demo / evidence capture: Q001 (control, never pauses), Q091 and Q092
# (pause for approval). Live retrieval with local models. By default there is
# no LLM call and no API key is needed. Generation is opt-in with --generate
# (needs OPENROUTER_API_KEY), exactly as in Day 17's demo. The reviewer's
# decision comes from --decision, so the run is reproducible.
# ---------------------------------------------------------------------------

DEMO_QUERY_IDS = ["Q001", "Q091", "Q092"]


def _print_approval_request(request):
    print("  PAUSED for approval. The reviewer sees:")
    for key, value in request.items():
        print(f"    {key}: {value}")


def _print_outcome(state):
    for line in state["trace"]:
        print(f"  {line}")
    print(f"  route history: {state['route_history']}")
    print(f"  approval:      {state.get('approval', '(not needed)')}")
    print(f"  stop reason:   {state['stop_reason']}")
    print(f"  answer:        {state['answer']}")


def _print_checkpoints(graph, config):
    """One line per saved snapshot, oldest first: what the checkpointer kept for this thread."""
    snapshots = list(graph.get_state_history(config))[::-1]
    print(f"  checkpoints saved on thread {config['configurable']['thread_id']!r}: {len(snapshots)}")
    for snapshot in snapshots:
        values = snapshot.values
        print(
            f"    step {snapshot.metadata['step']:>2} | next {list(snapshot.next) or '(done)'} "
            f"| passes {values.get('retrieval_passes', '-')} "
            f"| sources {len(values.get('sources', []))} "
            f"| routes {values.get('route_history', [])}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Day 18: run queries through the ProcureRAG graph with a checkpointer and a human "
        "approval point before the recursive retrieval pass. Prints the approval request, the decision, "
        "the trace, the saved checkpoints, and a time-travel replay with the opposite decision."
    )
    parser.add_argument("--query-ids", nargs="+", default=DEMO_QUERY_IDS, help="labeled corpus query ids to run")
    parser.add_argument(
        "--decision",
        choices=ALLOWED_DECISIONS,
        default=DECISION_APPROVE,
        help="the reviewer's decision for every run that pauses (default: approve)",
    )
    parser.add_argument("--edited-followup", help="the reviewer's own follow-up query (required with --decision edit)")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Also call the live LLM (OpenRouter, needs OPENROUTER_API_KEY) whenever a run reaches 'generate'. "
        "That includes a time-travel replay that ends on 'generate' (e.g. with --decision reject, the "
        "counterfactual approve). Default: no LLM, with an explicit 'not generated' marker as the answer.",
    )
    args = parser.parse_args()
    if args.decision == DECISION_EDIT and not args.edited_followup:
        parser.error("--decision edit needs --edited-followup")

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
    # the LANGSMITH_* variables, which switch on tracing.
    load_dotenv()

    # Same live pipeline as Day 16/17's main(). Nothing retrieval-related is rebuilt.
    data = load_data()
    chunks = chunk_corpus(data)
    embedding_model = load_embedding_model()
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
    cross_encoder_model = load_cross_encoder()
    live_retrieve_fn = make_live_retrieve_fn(
        chunk_lexical_index, chunk_semantic_index, embedding_model, cross_encoder_model
    )

    # A thin wrapper that records every retrieval call. Used below to show
    # that a time-travel replay does not re-run pass 1.
    retrieval_calls = []

    def logged_retrieve_fn(query_text, config):
        retrieval_calls.append(query_text)
        return live_retrieve_fn(query_text, config)

    # The same `client(prompt) -> text` boundary Day 17 uses. None means the
    # `generate` node writes the explicit "not generated" marker instead.
    client = make_openrouter_client() if args.generate else None

    # One compiled graph and one in-memory checkpointer for every query. Runs
    # are kept apart only by their thread_id.
    graph = build_controlled_graph(logged_retrieve_fn, client=client)

    print("Graph structure (Mermaid):")
    print(graph.get_graph().draw_mermaid())

    if args.decision == DECISION_APPROVE:
        decision = {"type": DECISION_APPROVE}
    elif args.decision == DECISION_EDIT:
        decision = {"type": DECISION_EDIT, "followup_query": args.edited_followup}
    else:
        decision = {"type": DECISION_REJECT, "message": "rejected from the CLI demo"}

    queries_by_id = {query["query_id"]: query for query in load_example_queries()}
    paused_configs = []

    for query_id in args.query_ids:
        query_row = queries_by_id[query_id]
        config = thread_config(f"{query_id}-review")
        print(f"\n{query_id} ({query_row['query_type']}): {query_row['query']}")

        # First invoke: runs until the end, OR until interrupt() pauses it.
        result = graph.invoke(make_initial_state(query_row), config)

        if "__interrupt__" in result:
            # `result["__interrupt__"]` is a list of Interrupt objects. `.value`
            # is exactly the dict `build_approval_request` returned.
            _print_approval_request(result["__interrupt__"][0].value)
            print(f"  saved state says next node = {graph.get_state(config).next}")
            print(f"  reviewer decision: {decision}")
            # Second invoke: same thread_id, so it resumes the paused run.
            result = graph.invoke(Command(resume=decision), config)
            paused_configs.append(config)
        else:
            print("  no approval needed: the router never proposed a follow-up pass")

        _print_outcome(result)
        _print_checkpoints(graph, config)

    # Time travel: for every run that paused, rewind to the approval point
    # and decide the other way.
    if args.decision == DECISION_REJECT:
        counterfactual = {"type": DECISION_APPROVE}
    else:
        counterfactual = {"type": DECISION_REJECT, "message": "time-travel counterfactual"}

    for config in paused_configs:
        calls_before = len(retrieval_calls)
        forked = replay_with_different_decision(graph, config, counterfactual)
        new_calls = retrieval_calls[calls_before:]
        print(f"\nTime travel on thread {config['configurable']['thread_id']!r}: replay with {counterfactual}")
        print(f"  retrieval calls during replay: {len(new_calls)} {new_calls} (pass 1 is never re-run)")
        print(f"  forked route history: {forked['route_history']}")
        print(f"  forked stop reason:   {forked['stop_reason']}")
        print(f"  checkpoints on thread now: {len(list(graph.get_state_history(config)))} (both branches kept)")


if __name__ == "__main__":
    main()
