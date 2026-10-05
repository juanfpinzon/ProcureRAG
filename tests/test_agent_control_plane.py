import importlib.util
import sys
from pathlib import Path

from langgraph.types import Command


def _load_module(module_name):
    """Same `src/<module_name>.py` loading pattern every other test file in
    this project uses (see `tests/test_agent_graph.py`): `src` is only on
    `sys.path` while the module's own top-level imports resolve.
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


def _load_control_plane_module():
    return _load_module("agent_control_plane")


# Day 16's stop-reason vocabulary. The control plane reuses it unchanged and
# adds only one new value of its own (`STOP_FOLLOWUP_REJECTED`).
_day16 = _load_module("agentic_retrieval")
STOP_FIXED_AFTER_SECOND_PASS = _day16.STOP_FIXED_AFTER_SECOND_PASS
STOP_STILL_MISSING_AFTER_MAX_PASSES = _day16.STOP_STILL_MISSING_AFTER_MAX_PASSES


# ---------------------------------------------------------------------------
# Small local helpers, same shapes as `tests/test_agent_graph.py`: a
# synthetic query row, a `generation.build_sources`-shaped source dict, and
# a fake retrieve_fn that returns canned sources per query text and counts
# its calls. No models, corpus, or network: every run below takes
# milliseconds, including the pauses and resumes.
# ---------------------------------------------------------------------------


def _query_row(query_id, query_type, relevance_grades):
    return {
        "query_id": query_id,
        "query": f"synthetic query text for {query_id}",
        "query_type": query_type,
        "relevance_grades": relevance_grades,
    }


def _source(doc_id, chunk_id):
    return {
        "source_id": 1,
        "doc_id": doc_id,
        "title": f"{doc_id} title",
        "chunk_id": chunk_id,
        "text": f"{doc_id} chunk text",
        "rank": 1,
        "score": 1.0,
    }


class _CountingRetrieveFn:
    """Fake `retrieve_fn(query_text, config) -> sources`, keyed by query text.

    `call_count` is the key evidence in this file. It shows WHEN the second
    retrieval pass actually happens: never before the reviewer's decision,
    and never on a rejection. A `KeyError` means the graph asked for a query
    text the test did not expect.
    """

    def __init__(self, sources_by_query_text):
        self.sources_by_query_text = sources_by_query_text
        self.call_count = 0
        self.queries_received = []

    def __call__(self, query_text, config):
        self.call_count += 1
        self.queries_received.append(query_text)
        return self.sources_by_query_text[query_text]


# The Q091 shape from Day 17's tests: POL-001 is present, but only through
# chunk-3. Neither acceptable "Band 3" chunk is there, so the router proposes
# the recursive pass, which now means pausing for approval.
Q091_FOLLOWUP = "approval bands EUR 50,000 250,000 Band 3 VP Procurement"
Q091_CASE_OVERRIDES = {
    "Q091": {
        "followup_query": Q091_FOLLOWUP,
        "acceptable_chunk_ids": ("POL-001::chunk-5", "POL-001::chunk-6"),
    }
}


def _q091_shaped_case():
    query_row = _query_row("Q091", "multi_doc", {"POL-001": 2})
    retrieve_fn = _CountingRetrieveFn(
        {
            query_row["query"]: [_source("POL-001", "POL-001::chunk-3")],
            Q091_FOLLOWUP: [_source("POL-001", "POL-001::chunk-6")],
        }
    )
    return query_row, retrieve_fn


def _start_run(module, query_row, retrieve_fn, case_overrides, thread_id="test-thread"):
    """Compile a controlled graph and run it until it ends OR pauses.

    Returns the graph and the thread config too, because every later call
    about this run (get_state, resume, history) must use the same thread.
    """
    graph = module.build_controlled_graph(retrieve_fn)
    config = module.thread_config(thread_id)
    result = graph.invoke(module.make_initial_state(query_row, case_overrides), config)
    return graph, config, result


# ---------------------------------------------------------------------------
# Structure: Day 17's graph plus exactly one node.
# ---------------------------------------------------------------------------


def test_controlled_graph_is_the_day17_graph_plus_one_approval_node():
    module = _load_control_plane_module()
    day17 = _load_module("agent_graph")
    retrieve_fn = _CountingRetrieveFn({})

    day17_nodes = set(day17.build_graph(retrieve_fn).get_graph().nodes)
    controlled_nodes = set(module.build_controlled_graph(retrieve_fn).get_graph().nodes)

    assert controlled_nodes == day17_nodes | {module.APPROVAL_NODE}


# ---------------------------------------------------------------------------
# Who pauses: only runs the router sends towards recursive_retrieve.
# ---------------------------------------------------------------------------


def test_control_query_runs_to_the_end_without_pausing():
    """Complete evidence on pass 1: no follow-up is proposed, so there is
    nothing to approve. The run finishes in one invoke, exactly as Day 17,
    and the checkpointer shows no pending node.
    """
    module = _load_control_plane_module()
    query_row = _query_row("Q001", "threshold", {"POL-001": 2})
    retrieve_fn = _CountingRetrieveFn({query_row["query"]: [_source("POL-001", "POL-001::chunk-1")]})

    graph, config, result = _start_run(module, query_row, retrieve_fn, case_overrides={})

    assert "__interrupt__" not in result
    assert result["route_history"] == [module.ROUTE_GENERATE]
    assert "approval" not in result
    assert retrieve_fn.call_count == 1
    assert graph.get_state(config).next == ()  # () = nothing left to run


def test_followup_route_pauses_before_the_second_retrieval_pass():
    """The core HITL property: the run stops BEFORE the high-impact action.

    After the first invoke:
    - `result["__interrupt__"]` carries the approval request,
    - the checkpointer says the next node is the approval node,
    - only ONE retrieval call has happened (the follow-up has not run),
    - the saved state already holds the first-pass evidence the reviewer needs.
    """
    module = _load_control_plane_module()
    query_row, retrieve_fn = _q091_shaped_case()

    graph, config, result = _start_run(module, query_row, retrieve_fn, Q091_CASE_OVERRIDES)

    request = result["__interrupt__"][0].value
    assert request["query_id"] == "Q091"
    assert request["proposed_action"] == module.ROUTE_RECURSIVE_RETRIEVE
    assert request["proposed_followup_query"] == Q091_FOLLOWUP
    assert request["trigger_reason"] == "missing_chunk"
    assert request["missing_chunk_ids"] == ["POL-001::chunk-5", "POL-001::chunk-6"]
    assert request["first_pass_source_count"] == 1
    assert request["first_pass_doc_ids"] == ["POL-001"]
    assert request["allowed_decisions"] == ["approve", "edit", "reject"]

    assert retrieve_fn.call_count == 1

    snapshot = graph.get_state(config)
    assert snapshot.next == (module.APPROVAL_NODE,)
    assert snapshot.values["retrieval_passes"] == 1
    assert snapshot.values["diagnoses"][0]["trigger_reason"] == "missing_chunk"


# ---------------------------------------------------------------------------
# The three decisions.
# ---------------------------------------------------------------------------


def test_approve_resumes_the_same_run_and_ends_exactly_like_day17():
    """Approving must not change behavior: the resumed run reaches the same
    routes, sources, diagnoses, answer, and stop reason as the Day 17 graph
    on the same inputs. This is what "preserve Day 17 route outputs" means
    for the two queries that now pause.
    """
    module = _load_control_plane_module()
    day17 = _load_module("agent_graph")

    query_row, retrieve_fn = _q091_shaped_case()
    graph, config, _ = _start_run(module, query_row, retrieve_fn, Q091_CASE_OVERRIDES)
    resumed = graph.invoke(Command(resume={"type": "approve"}), config)

    _, day17_retrieve_fn = _q091_shaped_case()
    day17_state = day17.build_graph(day17_retrieve_fn).invoke(
        day17.make_initial_state(query_row, Q091_CASE_OVERRIDES)
    )

    for key in ("route_history", "sources", "diagnoses", "retrieval_passes", "answer", "citations", "stop_reason"):
        assert resumed[key] == day17_state[key], key
    assert resumed["stop_reason"] == STOP_FIXED_AFTER_SECOND_PASS
    assert retrieve_fn.call_count == day17_retrieve_fn.call_count == 2

    assert resumed["approval"] == {
        "decision": "approve",
        "proposed_followup_query": Q091_FOLLOWUP,
        "approved_followup_query": Q091_FOLLOWUP,
        "message": None,
    }
    assert graph.get_state(config).next == ()


def test_reject_reports_the_gap_without_a_second_retrieval_pass():
    """A rejection ends the run on report_gap with an HONEST stop reason.
    Day 17's would have said "no follow-up query defined", which is false
    here. The follow-up retrieval never runs, and the LLM is never called.
    """
    module = _load_control_plane_module()
    query_row, retrieve_fn = _q091_shaped_case()

    def client_that_must_not_be_called(prompt):
        raise AssertionError("the LLM client must not be called after a rejection")

    graph = module.build_controlled_graph(retrieve_fn, client=client_that_must_not_be_called)
    config = module.thread_config("reject-thread")
    graph.invoke(module.make_initial_state(query_row, Q091_CASE_OVERRIDES), config)

    resumed = graph.invoke(Command(resume={"type": "reject", "message": "Band 3 is out of scope"}), config)

    assert retrieve_fn.call_count == 1
    assert resumed["route_history"] == [module.ROUTE_REPORT_GAP]
    assert resumed["stop_reason"] == module.STOP_FOLLOWUP_REJECTED
    assert "POL-001::chunk-5" in resumed["answer"]  # still names the missing evidence
    assert "Band 3 is out of scope" in resumed["answer"]  # and the reviewer's reason
    assert resumed["approval"]["decision"] == "reject"
    assert resumed["approval"]["approved_followup_query"] is None
    assert resumed["citations"] is None


def test_edit_runs_the_reviewers_query_and_keeps_the_original_proposal():
    """An edit changes WHAT the second pass searches for, and the audit
    record shows both the proposal and the replacement.
    """
    module = _load_control_plane_module()
    query_row, retrieve_fn = _q091_shaped_case()
    edited_query = "  POL-001 Band 3 approval threshold VP Procurement  "
    retrieve_fn.sources_by_query_text[edited_query.strip()] = [_source("POL-001", "POL-001::chunk-5")]

    graph, config, _ = _start_run(module, query_row, retrieve_fn, Q091_CASE_OVERRIDES)
    resumed = graph.invoke(Command(resume={"type": "edit", "followup_query": edited_query}), config)

    assert retrieve_fn.queries_received == [query_row["query"], edited_query.strip()]
    assert resumed["followup_query"] == edited_query.strip()
    assert resumed["approval"]["decision"] == "edit"
    assert resumed["approval"]["proposed_followup_query"] == Q091_FOLLOWUP
    assert resumed["approval"]["approved_followup_query"] == edited_query.strip()
    assert any("reviewer edited follow-up" in line for line in resumed["trace"])
    assert resumed["route_history"] == [module.ROUTE_RECURSIVE_RETRIEVE, module.ROUTE_GENERATE]
    assert resumed["stop_reason"] == STOP_FIXED_AFTER_SECOND_PASS


def test_approved_followup_that_only_partly_helps_asks_for_approval_once():
    """Q092 shape: the approved follow-up recovers CONTRACT-005 but not
    POL-002. The router's pass budget sends the run to report_gap. It does
    NOT pause a second time, because a run asks for approval at most once.
    """
    module = _load_control_plane_module()
    query_row = _query_row("Q092", "multi_doc", {"CONTRACT-005": 2, "POL-002": 2})
    followup_text = "one combined follow-up for both missing docs"
    retrieve_fn = _CountingRetrieveFn(
        {
            query_row["query"]: [_source("POL-006", "POL-006::chunk-1")],
            followup_text: [_source("CONTRACT-005", "CONTRACT-005::chunk-3")],
        }
    )
    case_overrides = {"Q092": {"followup_query": followup_text, "acceptable_chunk_ids": ()}}

    graph, config, first = _start_run(module, query_row, retrieve_fn, case_overrides)
    assert first["__interrupt__"][0].value["missing_doc_ids"] == ["CONTRACT-005", "POL-002"]

    resumed = graph.invoke(Command(resume={"type": "approve"}), config)

    assert "__interrupt__" not in resumed
    assert retrieve_fn.call_count == 2
    assert resumed["route_history"] == [module.ROUTE_RECURSIVE_RETRIEVE, module.ROUTE_REPORT_GAP]
    assert resumed["diagnoses"][-1]["missing_doc_ids"] == ["POL-002"]
    assert resumed["stop_reason"] == STOP_STILL_MISSING_AFTER_MAX_PASSES


def test_invalid_decision_asks_again_instead_of_proceeding_or_getting_stuck():
    """A typo must never count as approval, and must not break the run either.

    Each malformed answer is refused with a NEW pause whose request carries
    an `"error"`. Nothing runs past the approval point (one retrieval call
    only). Then a valid answer, given to the same thread, finishes the run.
    (If the node RAISED instead, the bad answer would be saved and replayed
    on every later resume. See gotcha 3 in the module docstring.)
    """
    module = _load_control_plane_module()
    query_row, retrieve_fn = _q091_shaped_case()
    graph, config, _ = _start_run(module, query_row, retrieve_fn, Q091_CASE_OVERRIDES)

    typo = graph.invoke(Command(resume={"type": "aprove"}), config)
    assert "'type' is one of" in typo["__interrupt__"][0].value["error"]

    blank_edit = graph.invoke(Command(resume={"type": "edit", "followup_query": "   "}), config)
    assert "non-empty 'followup_query'" in blank_edit["__interrupt__"][0].value["error"]

    # Still paused, and the second pass has not run. Measured on 1.2.11:
    # after a re-ask, `snapshot.next` reads `()`, so `snapshot.interrupts`
    # (the pending request) is the reliable "is this run paused?" signal.
    assert len(graph.get_state(config).interrupts) == 1
    assert retrieve_fn.call_count == 1

    resumed = graph.invoke(Command(resume={"type": "approve"}), config)
    assert resumed["stop_reason"] == STOP_FIXED_AFTER_SECOND_PASS
    assert resumed["approval"]["decision"] == "approve"
    assert graph.get_state(config).interrupts == ()


# ---------------------------------------------------------------------------
# Checkpointer as short-term memory: state is saved per thread_id.
# ---------------------------------------------------------------------------


def test_each_thread_keeps_its_own_state_on_one_shared_graph():
    """One compiled graph, one checkpointer, two threads. Finishing Q001 on
    one thread does not touch Q091's paused run on the other, and an unknown
    thread has no state at all.
    """
    module = _load_control_plane_module()
    q091_row, retrieve_fn = _q091_shaped_case()
    q001_row = _query_row("Q001", "threshold", {"POL-001": 2})
    retrieve_fn.sources_by_query_text[q001_row["query"]] = [_source("POL-001", "POL-001::chunk-1")]

    graph = module.build_controlled_graph(retrieve_fn)
    q091_config = module.thread_config("thread-q091")
    q001_config = module.thread_config("thread-q001")

    graph.invoke(module.make_initial_state(q091_row, Q091_CASE_OVERRIDES), q091_config)
    graph.invoke(module.make_initial_state(q001_row, {}), q001_config)

    assert graph.get_state(q091_config).next == (module.APPROVAL_NODE,)
    assert graph.get_state(q001_config).next == ()
    assert graph.get_state(q001_config).values["query_id"] == "Q001"
    assert graph.get_state(module.thread_config("never-used")).values == {}

    resumed = graph.invoke(Command(resume={"type": "approve"}), q091_config)
    assert resumed["query_id"] == "Q091"
    assert resumed["stop_reason"] == STOP_FIXED_AFTER_SECOND_PASS


# ---------------------------------------------------------------------------
# Time travel: replay the approval point with a different decision.
# ---------------------------------------------------------------------------


def test_time_travel_replays_the_approval_with_a_different_decision_without_rerunning_pass_one():
    module = _load_control_plane_module()
    query_row, retrieve_fn = _q091_shaped_case()
    graph, config, _ = _start_run(module, query_row, retrieve_fn, Q091_CASE_OVERRIDES)
    graph.invoke(Command(resume={"type": "approve"}), config)
    assert retrieve_fn.call_count == 2  # pass 1 + the approved follow-up

    forked = module.replay_with_different_decision(graph, config, {"type": "reject", "message": "counterfactual"})

    # Pass 1 came from the checkpoint, and the rejection skips pass 2:
    # the replay made zero retrieval calls.
    assert retrieve_fn.call_count == 2
    assert forked["stop_reason"] == module.STOP_FOLLOWUP_REJECTED
    assert forked["route_history"] == [module.ROUTE_REPORT_GAP]
    # The thread's newest state is the fork...
    assert graph.get_state(config).values["stop_reason"] == module.STOP_FOLLOWUP_REJECTED
    # ...and the approved branch is still in the history, not overwritten.
    history_stop_reasons = {snapshot.values.get("stop_reason") for snapshot in graph.get_state_history(config)}
    assert STOP_FIXED_AFTER_SECOND_PASS in history_stop_reasons


def test_resuming_an_old_checkpoint_directly_replays_the_original_decision():
    """Characterization test for gotcha 2 in the module docstring, pinned to
    the installed LangGraph (1.2.11): `Command(resume=...)` sent straight to
    the old paused checkpoint IGNORES the new decision and replays the saved
    one. This is why `replay_with_different_decision` takes two steps. If a
    LangGraph upgrade makes this test fail, the gotcha is gone and that
    helper can be simplified.
    """
    module = _load_control_plane_module()
    query_row, retrieve_fn = _q091_shaped_case()
    graph, config, _ = _start_run(module, query_row, retrieve_fn, Q091_CASE_OVERRIDES)
    graph.invoke(Command(resume={"type": "approve"}), config)

    paused = module.find_approval_checkpoint(graph, config)
    naive = graph.invoke(Command(resume={"type": "reject"}), paused.config)

    assert naive["approval"]["decision"] == "approve"  # NOT "reject"
    assert naive["stop_reason"] == STOP_FIXED_AFTER_SECOND_PASS
