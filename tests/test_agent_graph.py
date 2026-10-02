import importlib.util
import sys
from pathlib import Path


def _load_module(module_name):
    """Same `src/<module_name>.py` loading pattern every other test file in
    this project uses (see `tests/test_agentic_retrieval.py`): `src` is only
    on `sys.path` while the module's own top-level imports resolve.
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


def _load_agent_graph_module():
    return _load_module("agent_graph")


def _real_queries_by_id():
    from hybrid_search import load_example_queries

    return {row["query_id"]: row for row in load_example_queries()}


# ---------------------------------------------------------------------------
# Small local helpers, same shapes as `tests/test_agentic_retrieval.py`: a
# synthetic query row, a `generation.build_sources`-shaped source dict, and
# a fake retrieve_fn that returns canned sources per query text and counts
# its calls. No models, corpus, or network: every graph run below takes
# milliseconds.
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

    Records every query text and config it receives, so tests can check
    both HOW MANY retrieval passes ran and WHAT each pass asked for. A
    `KeyError` means the graph asked for retrieval on a query text the test
    did not expect, which is a more useful failure than a silent default.
    """

    def __init__(self, sources_by_query_text):
        self.sources_by_query_text = sources_by_query_text
        self.call_count = 0
        self.queries_received = []
        self.configs_received = []

    def __call__(self, query_text, config):
        self.call_count += 1
        self.queries_received.append(query_text)
        self.configs_received.append(config)
        return self.sources_by_query_text[query_text]


def _client_that_must_not_be_called(prompt):
    raise AssertionError("the LLM client must not be called on this route")


def _run_graph(module, query_row, retrieve_fn, case_overrides=None, client=None):
    """Compile the graph with the given fakes and run it on one query row.

    `case_overrides=None` means the real `AGENTIC_CASE_OVERRIDES` table
    (see `make_initial_state`). Synthetic tests pass their own small dict.
    """
    graph = module.build_graph(retrieve_fn, client=client)
    return graph.invoke(module.make_initial_state(query_row, case_overrides))


# ---------------------------------------------------------------------------
# Structure: the compiled graph has exactly the nodes the design names.
# ---------------------------------------------------------------------------


def test_compiled_graph_has_the_designed_nodes():
    module = _load_agent_graph_module()
    graph = module.build_graph(retrieve_fn=_CountingRetrieveFn({}))

    assert set(graph.get_graph().nodes) == {
        "__start__",
        "retrieve",
        "diagnose",
        "recursive_retrieve",
        "generate",
        "report_gap",
        "__end__",
    }


# ---------------------------------------------------------------------------
# The router on its own: a pure function of state, so it can be tested with
# hand-built state dicts, with no graph, retrieval, or fakes involved.
# ---------------------------------------------------------------------------


def _router_state(trigger_reason, retrieval_passes, followup_query):
    """Just the three state fields `route_after_diagnosis` reads."""
    return {
        "diagnoses": [{"trigger_reason": trigger_reason}],
        "retrieval_passes": retrieval_passes,
        "followup_query": followup_query,
    }


def test_router_sends_complete_evidence_to_generate():
    module = _load_agent_graph_module()
    state = _router_state(trigger_reason=None, retrieval_passes=1, followup_query="unused")

    assert module.route_after_diagnosis(state) == module.ROUTE_GENERATE


def test_router_sends_a_gap_with_a_known_followup_to_recursive_retrieve():
    module = _load_agent_graph_module()
    state = _router_state(trigger_reason="missing_chunk", retrieval_passes=1, followup_query="targeted follow-up")

    assert module.route_after_diagnosis(state) == module.ROUTE_RECURSIVE_RETRIEVE


def test_router_reports_the_gap_when_no_followup_is_defined():
    module = _load_agent_graph_module()
    state = _router_state(trigger_reason="missing_doc", retrieval_passes=1, followup_query=None)

    assert module.route_after_diagnosis(state) == module.ROUTE_REPORT_GAP


def test_router_reports_the_gap_once_the_pass_budget_is_spent_even_with_a_followup():
    """The loop's stop condition: after pass 2 the router must NOT send the
    run back to recursive_retrieve, even though a follow-up query exists.
    This check is what makes the graph's cycle bounded.
    """
    module = _load_agent_graph_module()
    state = _router_state(
        trigger_reason="missing_doc",
        retrieval_passes=module.MAX_RETRIEVAL_PASSES,
        followup_query="targeted follow-up",
    )

    assert module.route_after_diagnosis(state) == module.ROUTE_REPORT_GAP


def test_recursion_limit_stops_a_runaway_loop_if_the_pass_budget_is_broken():
    """The safety net behind the router's pass budget.

    Deliberately break stop condition #1 (the pass budget) on this test's
    own copy of the module, with a follow-up that never finds the missing
    doc. The loop would now run forever, so the graph's explicit
    `GRAPH_RECURSION_LIMIT` must stop it within a handful of retrieval
    calls. Without the explicit limit, LangGraph 1.2.11's default (10007
    steps) would allow ~5,000 calls first.
    """
    import pytest
    from langgraph.errors import GraphRecursionError

    module = _load_agent_graph_module()
    module.MAX_RETRIEVAL_PASSES = 10**9  # sabotage: the router never runs out of passes
    query_row = _query_row("QX", "multi_doc", {"POL-002": 2})
    followup_text = "follow-up that never finds POL-002"
    retrieve_fn = _CountingRetrieveFn(
        {
            query_row["query"]: [_source("FAQ-001", "FAQ-001::chunk-1")],
            followup_text: [_source("FAQ-001", "FAQ-001::chunk-2")],
        }
    )
    case_overrides = {"QX": {"followup_query": followup_text, "acceptable_chunk_ids": ()}}

    with pytest.raises(GraphRecursionError):
        _run_graph(module, query_row, retrieve_fn, case_overrides)

    assert retrieve_fn.call_count <= module.GRAPH_RECURSION_LIMIT


# ---------------------------------------------------------------------------
# Full graph runs with a fake retrieve_fn: one test per route through the
# graph (the Q001/Q005 control, Q091 fixed, Q092 still open, no follow-up).
# ---------------------------------------------------------------------------


def test_control_query_goes_straight_to_generate_with_one_retrieval_pass():
    """Q001-shaped control: complete evidence on pass 1 -> no recursion.

    `call_count == 1` shows the recursive branch is selective: a clean
    query never pays for a second retrieval pass.
    """
    module = _load_agent_graph_module()
    query_row = _query_row("Q001", "threshold", {"POL-001": 2, "FAQ-001": 1})
    retrieve_fn = _CountingRetrieveFn({query_row["query"]: [_source("POL-001", "POL-001::chunk-1")]})

    state = _run_graph(module, query_row, retrieve_fn, case_overrides={})

    assert retrieve_fn.call_count == 1
    assert state["route_history"] == [module.ROUTE_GENERATE]
    assert state["stop_reason"] == module.STOP_NO_MISSING_EVIDENCE
    assert len(state["diagnoses"]) == 1
    assert state["diagnoses"][0]["trigger_reason"] is None
    # No client was wired in, so the answer is the explicit marker, not "".
    assert state["answer"] == module.ANSWER_NOT_GENERATED
    assert state["citations"] is None


def test_missing_chunk_routes_through_recursive_retrieve_and_is_fixed():
    """Q091-shaped: the primary doc is present but neither acceptable chunk
    is. The graph must loop once (recursive_retrieve -> diagnose), then
    generate once the follow-up recovers one acceptable chunk.
    """
    module = _load_agent_graph_module()
    query_row = _query_row("Q091", "multi_doc", {"POL-001": 2})
    followup_text = "approval bands EUR 50,000 250,000 Band 3 VP Procurement"
    retrieve_fn = _CountingRetrieveFn(
        {
            query_row["query"]: [_source("POL-001", "POL-001::chunk-3")],
            followup_text: [_source("POL-001", "POL-001::chunk-6")],
        }
    )
    case_overrides = {
        "Q091": {
            "followup_query": followup_text,
            "acceptable_chunk_ids": ("POL-001::chunk-5", "POL-001::chunk-6"),
        }
    }

    state = _run_graph(module, query_row, retrieve_fn, case_overrides)
    agentic = _load_module("agentic_retrieval")

    assert state["route_history"] == [module.ROUTE_RECURSIVE_RETRIEVE, module.ROUTE_GENERATE]
    assert state["retrieval_passes"] == 2
    assert retrieve_fn.queries_received == [query_row["query"], followup_text]
    # Day 16's contract: the follow-up pass reuses the first pass's config.
    assert retrieve_fn.configs_received[0] == retrieve_fn.configs_received[1]
    # Before/after evidence, both kept thanks to the diagnoses reducer.
    assert state["diagnoses"][0]["trigger_reason"] == agentic.TRIGGER_MISSING_CHUNK
    assert state["diagnoses"][-1]["trigger_reason"] is None
    assert state["stop_reason"] == module.STOP_FIXED_AFTER_SECOND_PASS
    # Additive merge: the first-pass chunk is still there, the new one is appended.
    assert [source["chunk_id"] for source in state["sources"]] == ["POL-001::chunk-3", "POL-001::chunk-6"]


def test_partially_recovered_documents_route_to_report_gap_after_max_passes():
    """Q092-shaped: two primary docs are missing, and the one allowed
    follow-up recovers CONTRACT-005 but not POL-002. The graph must stop
    (no third pass), report the remaining gap without calling the LLM, and
    keep the per-document before/after visible in `diagnoses`.
    """
    module = _load_agent_graph_module()
    query_row = _query_row("Q092", "multi_doc", {"CONTRACT-005": 2, "POL-002": 2})
    followup_text = "one combined follow-up for both missing docs"
    retrieve_fn = _CountingRetrieveFn(
        {
            query_row["query"]: [_source("POL-006", "POL-006::chunk-1")],
            followup_text: [_source("CONTRACT-005", "CONTRACT-005::chunk-3")],
        }
    )
    case_overrides = {"Q092": {"followup_query": followup_text, "acceptable_chunk_ids": ()}}

    state = _run_graph(module, query_row, retrieve_fn, case_overrides, client=_client_that_must_not_be_called)

    assert retrieve_fn.call_count == 2  # exactly one extra pass, then stop
    assert state["route_history"] == [module.ROUTE_RECURSIVE_RETRIEVE, module.ROUTE_REPORT_GAP]
    assert state["diagnoses"][0]["missing_doc_ids"] == ["CONTRACT-005", "POL-002"]
    assert state["diagnoses"][-1]["missing_doc_ids"] == ["POL-002"]
    assert state["stop_reason"] == module.STOP_STILL_MISSING_AFTER_MAX_PASSES
    # The gap report names what is STILL missing, not what was recovered.
    assert "POL-002" in state["answer"]
    assert "CONTRACT-005" not in state["answer"]
    assert state["citations"] is None


def test_gap_without_a_known_followup_reports_the_gap_after_one_pass():
    """A measured gap on a query with no entry in `case_overrides`: the
    graph must not invent a follow-up query. One retrieval pass, then
    straight to report_gap, and the LLM is never called.
    """
    module = _load_agent_graph_module()
    query_row = _query_row("QZ", "multi_doc", {"POL-009": 2})
    retrieve_fn = _CountingRetrieveFn({query_row["query"]: [_source("FAQ-001", "FAQ-001::chunk-1")]})

    state = _run_graph(module, query_row, retrieve_fn, case_overrides={}, client=_client_that_must_not_be_called)

    assert retrieve_fn.call_count == 1
    assert state["route_history"] == [module.ROUTE_REPORT_GAP]
    assert state["stop_reason"] == module.STOP_NO_FOLLOWUP_QUERY_DEFINED
    assert "POL-009" in state["answer"]


def test_generate_after_recursion_uses_renumbered_sources_and_the_injected_client():
    """With a (fake) LLM client wired in, the generate node calls
    `generation.generate_answer` on the MERGED context.

    Both fake passes number their sources from 1 (as `build_sources`
    does per pass), so without renumbering the merged context would
    contain two different "[1]" sources. The graph must hand the model
    unique, sequential citation numbers.
    """
    module = _load_agent_graph_module()
    query_row = _query_row("QX", "multi_doc", {"POL-002": 2})
    followup_text = "targeted follow-up for POL-002"
    retrieve_fn = _CountingRetrieveFn(
        {
            query_row["query"]: [_source("FAQ-001", "FAQ-001::chunk-1")],
            followup_text: [_source("POL-002", "POL-002::chunk-11")],
        }
    )
    case_overrides = {"QX": {"followup_query": followup_text, "acceptable_chunk_ids": ()}}
    prompts_received = []

    def fake_client(prompt):
        prompts_received.append(prompt)
        return "High-risk suppliers need Enhanced Due Diligence [2]."

    state = _run_graph(module, query_row, retrieve_fn, case_overrides, client=fake_client)

    assert len(prompts_received) == 1
    assert [source["source_id"] for source in state["sources"]] == [1, 2]
    assert "[2] POL-002" in prompts_received[0]  # the recovered doc is citable as [2]
    assert state["answer"] == "High-risk suppliers need Enhanced Due Diligence [2]."
    assert state["citations"]["valid_ids"] == [2]
    assert state["citations"]["orphan_ids"] == []
    assert state["stop_reason"] == module.STOP_FIXED_AFTER_SECOND_PASS


# ---------------------------------------------------------------------------
# Parity with Day 16: the graph re-expresses `run_recursive_retrieval`'s
# control flow, so on the same inputs it must reach the same stop reason,
# the same final missing evidence, and the same number of retrieval calls.
# If this test fails, the graph has changed the behavior being measured,
# not just its shape.
# ---------------------------------------------------------------------------


def test_graph_matches_day16_run_recursive_retrieval_on_every_route():
    module = _load_agent_graph_module()
    agentic = _load_module("agentic_retrieval")

    followup = "targeted follow-up"
    scenarios = [
        # (name, query_row, sources_by_query_text, case_overrides)
        (
            "control, nothing missing",
            _query_row("QA", "threshold", {"POL-001": 2}),
            {"synthetic query text for QA": [_source("POL-001", "POL-001::chunk-1")]},
            {},
        ),
        (
            "missing doc, fixed by follow-up",
            _query_row("QB", "multi_doc", {"POL-002": 2}),
            {
                "synthetic query text for QB": [_source("FAQ-001", "FAQ-001::chunk-1")],
                followup: [_source("POL-002", "POL-002::chunk-11")],
            },
            {"QB": {"followup_query": followup, "acceptable_chunk_ids": ()}},
        ),
        (
            "missing doc, still missing after follow-up",
            _query_row("QC", "multi_doc", {"CONTRACT-005": 2}),
            {
                "synthetic query text for QC": [_source("FAQ-001", "FAQ-001::chunk-1")],
                followup: [_source("FAQ-001", "FAQ-001::chunk-2")],
            },
            {"QC": {"followup_query": followup, "acceptable_chunk_ids": ()}},
        ),
        (
            "missing doc, no follow-up defined",
            _query_row("QD", "multi_doc", {"POL-009": 2}),
            {"synthetic query text for QD": [_source("FAQ-001", "FAQ-001::chunk-1")]},
            {},
        ),
    ]

    for name, query_row, sources_by_query_text, case_overrides in scenarios:
        day16_retrieve_fn = _CountingRetrieveFn(sources_by_query_text)
        day16_state = agentic.run_recursive_retrieval(query_row, day16_retrieve_fn, case_overrides=case_overrides)

        graph_retrieve_fn = _CountingRetrieveFn(sources_by_query_text)
        graph_state = _run_graph(module, query_row, graph_retrieve_fn, case_overrides)
        final_diagnosis = graph_state["diagnoses"][-1]

        assert graph_state["stop_reason"] == day16_state["stop_reason"], name
        assert final_diagnosis["missing_doc_ids"] == day16_state["final_missing_doc_ids"], name
        assert final_diagnosis["missing_chunk_ids"] == day16_state["final_missing_chunk_ids"], name
        assert graph_retrieve_fn.call_count == day16_retrieve_fn.call_count, name


# ---------------------------------------------------------------------------
# Real corpus rows (Q001, Q005, Q091, Q092 from
# `data/corpus_v1/example_queries.jsonl`) with faked retrieval: checks that
# `make_initial_state` picks up the REAL `AGENTIC_CASE_OVERRIDES` wiring
# (follow-up queries, Q091's acceptable chunks) and that the real relevance
# grades drive the routes the Day 17 route table expects.
# ---------------------------------------------------------------------------


def _all_primary_doc_sources(query_row):
    """One fake chunk per grade-2 doc: complete document-level evidence."""
    return [
        _source(doc_id, f"{doc_id}::chunk-1")
        for doc_id, grade in query_row["relevance_grades"].items()
        if grade == 2
    ]


def test_real_rows_route_as_the_day17_route_table_expects():
    module = _load_agent_graph_module()
    agentic = _load_module("agentic_retrieval")
    queries_by_id = _real_queries_by_id()

    # Controls: every primary doc retrieved on pass 1 -> straight to generate.
    for query_id in ("Q001", "Q005"):
        row = queries_by_id[query_id]
        retrieve_fn = _CountingRetrieveFn({row["query"]: _all_primary_doc_sources(row)})
        state = _run_graph(module, row, retrieve_fn)
        assert state["route_history"] == [module.ROUTE_GENERATE], query_id
        assert state["stop_reason"] == module.STOP_NO_MISSING_EVIDENCE, query_id

    # Q091: all primary docs present, but POL-001 only via chunk-3 (the real
    # Day 16 first-pass shape) -> missing_chunk -> recursive -> fixed.
    q091 = queries_by_id["Q091"]
    q091_first_pass = [
        _source("POL-001", "POL-001::chunk-3"),
        _source("POL-003", "POL-003::chunk-1"),
        _source("GUIDE-002", "GUIDE-002::chunk-1"),
    ]
    q091_followup = module.AGENTIC_CASE_OVERRIDES["Q091"]["followup_query"]
    retrieve_fn = _CountingRetrieveFn(
        {q091["query"]: q091_first_pass, q091_followup: [_source("POL-001", "POL-001::chunk-6")]}
    )
    state = _run_graph(module, q091, retrieve_fn)
    assert state["diagnoses"][0]["trigger_reason"] == agentic.TRIGGER_MISSING_CHUNK
    assert state["route_history"] == [module.ROUTE_RECURSIVE_RETRIEVE, module.ROUTE_GENERATE]
    assert state["stop_reason"] == module.STOP_FIXED_AFTER_SECOND_PASS

    # Q092: CONTRACT-005 and POL-002 missing on pass 1 -> missing_doc ->
    # recursive. Here the faked follow-up recovers both (as the live Day 16
    # run did), so the graph ends on generate.
    q092 = queries_by_id["Q092"]
    q092_followup = module.AGENTIC_CASE_OVERRIDES["Q092"]["followup_query"]
    retrieve_fn = _CountingRetrieveFn(
        {
            q092["query"]: [_source("POL-006", "POL-006::chunk-1"), _source("SOP-004", "SOP-004::chunk-1")],
            q092_followup: [
                _source("CONTRACT-005", "CONTRACT-005::chunk-3"),
                _source("POL-002", "POL-002::chunk-11"),
            ],
        }
    )
    state = _run_graph(module, q092, retrieve_fn)
    assert state["diagnoses"][0]["trigger_reason"] == agentic.TRIGGER_MISSING_DOC
    assert state["diagnoses"][0]["missing_doc_ids"] == ["CONTRACT-005", "POL-002"]
    assert state["route_history"] == [module.ROUTE_RECURSIVE_RETRIEVE, module.ROUTE_GENERATE]
    assert state["stop_reason"] == module.STOP_FIXED_AFTER_SECOND_PASS


# ---------------------------------------------------------------------------
# Whole-corpus summary: `route_distribution` groups finished runs by route
# path (the logic behind `agent_graph.py --all-queries-summary`).
# ---------------------------------------------------------------------------


def test_route_distribution_groups_runs_by_route_path():
    module = _load_agent_graph_module()
    followup_text = "targeted follow-up"
    control = _query_row("QA", "threshold", {"POL-001": 2})
    fixed = _query_row("QB", "multi_doc", {"POL-002": 2})
    no_followup = _query_row("QC", "multi_doc", {"POL-009": 2})
    retrieve_fn = _CountingRetrieveFn(
        {
            control["query"]: [_source("POL-001", "POL-001::chunk-1")],
            fixed["query"]: [_source("FAQ-001", "FAQ-001::chunk-1")],
            followup_text: [_source("POL-002", "POL-002::chunk-11")],
            no_followup["query"]: [_source("FAQ-001", "FAQ-001::chunk-1")],
        }
    )
    case_overrides = {"QB": {"followup_query": followup_text, "acceptable_chunk_ids": ()}}

    states = [
        _run_graph(module, query_row, retrieve_fn, case_overrides)
        for query_row in (control, fixed, no_followup)
    ]

    assert module.route_distribution(states) == {
        "generate": ["QA"],
        "recursive_retrieve -> generate": ["QB"],
        "report_gap": ["QC"],
    }
