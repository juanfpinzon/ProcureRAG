import importlib.util
import json
import sys
from pathlib import Path

import pytest


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


def _load_graph_regression_module():
    return _load_module("graph_regression")


def _real_queries_by_id():
    from hybrid_search import load_example_queries

    return {row["query_id"]: row for row in load_example_queries()}


# ---------------------------------------------------------------------------
# A fake retrieval that reproduces the evidence MEASURED on the real pipeline
# (2026-10-20) for every query the graph cases use: which documents and
# chunks each pass returns. It answers by query text, so the real Q001...Q012
# rows and the real follow-up queries in `AGENTIC_CASE_OVERRIDES` drive it.
# No models, corpus index, or network: every test below runs in milliseconds.
# ---------------------------------------------------------------------------


def _source(source_id, doc_id, chunk_id):
    return {
        "source_id": source_id,
        "doc_id": doc_id,
        "title": f"{doc_id} title",
        "chunk_id": chunk_id,
        "text": f"{doc_id} chunk text",
        "rank": source_id,
        "score": 1.0,
    }


def _sources(*chunk_ids):
    """`generation.build_sources`-shaped list, numbered 1..n like one real pass."""
    return [_source(number, chunk_id.split("::")[0], chunk_id) for number, chunk_id in enumerate(chunk_ids, start=1)]


def _measured_sources_by_query_text(queries_by_id):
    from agentic_retrieval import AGENTIC_CASE_OVERRIDES

    q091_followup = AGENTIC_CASE_OVERRIDES["Q091"]["followup_query"]
    q092_followup = AGENTIC_CASE_OVERRIDES["Q092"]["followup_query"]
    return {
        # Q001: both labeled documents on pass 1.
        queries_by_id["Q001"]["query"]: _sources("POL-001::chunk-4", "FAQ-001::chunk-6"),
        # Q005: all three primary documents on pass 1.
        queries_by_id["Q005"]["query"]: _sources("FAQ-001::chunk-9", "POL-001::chunk-12", "SOP-008::chunk-3"),
        # Q091: every primary document, but POL-001 only through chunk-3 (not a "Band 3" chunk).
        queries_by_id["Q091"]["query"]: _sources("GUIDE-002::chunk-1", "POL-001::chunk-3", "POL-003::chunk-13"),
        q091_followup: _sources("POL-001::chunk-6", "POL-001::chunk-4"),
        # Q092: CONTRACT-005 and POL-002 missing on pass 1; the follow-up recovers both.
        queries_by_id["Q092"]["query"]: _sources("POL-006::chunk-1", "SOP-006::chunk-2"),
        q092_followup: _sources("POL-002::chunk-8", "CONTRACT-005::chunk-3"),
        # Q012: CONTRACT-002 never retrieved, and Q012 has no follow-up query.
        queries_by_id["Q012"]["query"]: _sources("POL-003::chunk-11", "CONTRACT-004::chunk-9"),
    }


def _fake_retrieve_fn(sources_by_query_text):
    """A KeyError means the graph asked for a query text the test did not expect."""
    return lambda query_text, config: sources_by_query_text[query_text]


def _structured_client(answer_by_query_fragment):
    """Fake live client: `GeneratedAnswer` JSON chosen by a fragment of the prompt's question."""

    def client(prompt):
        for fragment, answer in answer_by_query_fragment.items():
            if fragment in prompt:
                return json.dumps({"answer": answer, "answerable_from_sources": True})
        raise AssertionError("the fake client got a prompt for a question the test did not expect")

    return client


def _deterministic_run(module, sources_by_query_text, cases=None):
    """Run cases the way `main()` does in the deterministic lane, with fake retrieval."""
    llm = module.CallCounter(module.deterministic_stand_in_client)
    results = module.run_graph_regression(
        cases or module.GRAPH_CASES, _real_queries_by_id(), _fake_retrieve_fn(sources_by_query_text), llm
    )
    return results, llm


# ---------------------------------------------------------------------------
# The deterministic lane.
# ---------------------------------------------------------------------------


def test_every_committed_case_passes_when_retrieval_reproduces_the_measured_evidence():
    module = _load_graph_regression_module()

    results, llm = _deterministic_run(module, _measured_sources_by_query_text(_real_queries_by_id()))

    assert [result["category"] for result in results] == [module.CATEGORY_PASSED] * len(module.GRAPH_CASES)
    assert module.exit_code_for(results) == module.EXIT_PASSED
    # Four `generate` routes, one stand-in call each. The two `report_gap` routes add none.
    assert llm.calls == 4


def test_a_follow_up_that_stops_recovering_evidence_is_route_drift_with_exit_code_1():
    """Q091's follow-up returns only a chunk the first pass already had, so
    the "Band 3" gap stays open. The graph must now end on `report_gap`, and
    the gate must name exactly which parts of the contract moved.
    """
    module = _load_graph_regression_module()
    from agentic_retrieval import AGENTIC_CASE_OVERRIDES

    sources = _measured_sources_by_query_text(_real_queries_by_id())
    sources[AGENTIC_CASE_OVERRIDES["Q091"]["followup_query"]] = _sources("POL-001::chunk-3")

    results, _ = _deterministic_run(module, sources)
    q091 = next(result for result in results if result["case_id"] == "recursive-recovery-q091")

    assert q091["category"] == module.CATEGORY_CONTRACT
    failed_fields = {failure.split(":")[0] for failure in q091["failures"]}
    assert failed_fields == {"route", "stop_reason", "final_missing", "llm_calls"}
    assert module.exit_code_for(results) == module.EXIT_CONTRACT_FAILED
    # Every other case is untouched by the change, and still passes.
    others = [result for result in results if result["case_id"] != "recursive-recovery-q091"]
    assert {result["category"] for result in others} == {module.CATEGORY_PASSED}


def test_a_rejected_follow_up_reports_both_missing_documents_and_never_calls_the_wired_in_client():
    module = _load_graph_regression_module()
    rejected = [case for case in module.GRAPH_CASES if case["case_id"] == "bounded-abstention-q092-rejected"]

    results, llm = _deterministic_run(module, _measured_sources_by_query_text(_real_queries_by_id()), rejected)

    assert results[0]["category"] == module.CATEGORY_PASSED
    assert results[0]["actual"]["llm_calls"] == 0
    assert llm.calls == 0  # the client WAS wired in, and the graph still never called it
    assert "CONTRACT-005" in results[0]["answer_text"]
    assert "POL-002" in results[0]["answer_text"]


def test_a_gap_case_that_starts_answering_is_flagged_including_its_llm_call():
    """Sabotage Q012's retrieval so CONTRACT-002 arrives on pass 1. The graph
    then answers, and the gate must flag both the new route and the LLM call
    a `report_gap` case is never allowed to make.
    """
    module = _load_graph_regression_module()
    queries_by_id = _real_queries_by_id()
    sources = _measured_sources_by_query_text(queries_by_id)
    sources[queries_by_id["Q012"]["query"]] = _sources("POL-003::chunk-11", "CONTRACT-002::chunk-5")
    q012 = [case for case in module.GRAPH_CASES if case["case_id"] == "unrecoverable-gap-q012"]

    results, _ = _deterministic_run(module, sources, q012)

    assert results[0]["category"] == module.CATEGORY_CONTRACT
    assert "llm_calls: expected 0, got 1" in results[0]["failures"]
    assert "route: expected ['report_gap'], got ['generate']" in results[0]["failures"]


def test_a_gap_report_that_does_not_name_the_missing_evidence_is_a_failure():
    """The gap text is what a reviewer reads. Every routing field below
    matches Q012's contract, but the text never names CONTRACT-002, so the
    "name what is missing" check must still fire.

    `SimpleNamespace` stands in for the two trace attributes this check
    reads (`result.status`, `result.text`). The real graph always names the
    gap (see the passing tests above), so a stand-in is the only way to show
    the check is not decorative.
    """
    from types import SimpleNamespace

    module = _load_graph_regression_module()
    case = next(case for case in module.GRAPH_CASES if case["case_id"] == "unrecoverable-gap-q012")
    # A run that matches Q012's contract field by field.
    actual = {
        "route": case["expected_route"],
        "retrieval_calls": case["expected_retrieval_calls"],
        "approval": case["expected_approval"],
        "stop_reason": case["expected_stop_reason"],
        "first_pass_missing": case["expected_first_pass_missing"],
        "final_missing": case["expected_final_missing"],
        "llm_calls": case["expected_llm_calls"],
    }
    vague_gap_report = SimpleNamespace(
        result=SimpleNamespace(status=module.STATUS_GAP_REPORT, text="Not answered: some evidence is missing.")
    )

    failures = module.contract_failures(case, actual, vague_gap_report)

    assert failures == ["gap report does not name still-missing evidence ['CONTRACT-002']"]


# ---------------------------------------------------------------------------
# The counting wrappers and the exit-code rule.
# ---------------------------------------------------------------------------


def test_call_counter_refuses_the_call_that_would_exceed_the_budget():
    module = _load_graph_regression_module()
    calls_made = []
    counter = module.CallCounter(lambda prompt: calls_made.append(prompt) or "ok", budget=1)

    assert counter("first") == "ok"
    with pytest.raises(module.BudgetExceeded):
        counter("second")
    assert calls_made == ["first"]  # the refused call never reached the function
    assert counter.calls == 1


def test_exit_code_prefers_contract_drift_over_infrastructure_over_pass():
    module = _load_graph_regression_module()

    def results(*categories):
        return [{"category": category} for category in categories]

    assert module.exit_code_for(results(module.CATEGORY_PASSED)) == 0
    assert module.exit_code_for(results(module.CATEGORY_PASSED, module.CATEGORY_INFRASTRUCTURE)) == 2
    assert module.exit_code_for(results(module.CATEGORY_INFRASTRUCTURE, module.CATEGORY_CONTRACT)) == 1
    assert module.exit_code_for([]) == 2  # nothing was checked: never a pass


def test_every_expected_key_in_a_case_is_one_the_gate_actually_measures():
    """A typo such as `expected_stop_reasons` would otherwise be silently
    ignored: `contract_failures` only compares the fields
    `actual_contract_values` produces. This pins the two key sets together.
    """
    from types import SimpleNamespace

    module = _load_graph_regression_module()
    diagnosis = SimpleNamespace(missing_doc_ids=[], missing_chunk_ids=[])
    fake_trace = SimpleNamespace(route_history=[], approval=None, stop_reason="", diagnoses=[diagnosis])
    measured_fields = set(module.actual_contract_values(fake_trace, retrieval_calls=0, llm_calls=0))

    for case in module.GRAPH_CASES:
        expected_fields = {key.removeprefix("expected_") for key in case if key.startswith("expected_")}
        assert expected_fields == measured_fields, case["case_id"]


def test_an_llm_call_over_the_budget_is_refused_and_reported_as_a_contract_failure():
    """End to end through `run_case`: with a budget of 0, Q001's generate
    node is refused its one call. The refusal is a contract failure, and the
    stand-in client is never reached.
    """
    module = _load_graph_regression_module()
    q001 = next(case for case in module.GRAPH_CASES if case["case_id"] == "control-q001")
    llm = module.CallCounter(module.deterministic_stand_in_client, budget=0)
    sources = _measured_sources_by_query_text(_real_queries_by_id())

    results = module.run_graph_regression([q001], _real_queries_by_id(), _fake_retrieve_fn(sources), llm)

    assert results[0]["category"] == module.CATEGORY_CONTRACT
    assert results[0]["failures"][0].startswith("llm budget: call 1 refused")
    assert llm.calls == 0


# ---------------------------------------------------------------------------
# The live lane, with fake "live" clients: the quality checks and the
# infrastructure/quality split are proved here before any real provider call.
# ---------------------------------------------------------------------------


def _live_run(module, client):
    llm = module.CallCounter(module.as_provider_boundary(client), budget=module.LIVE_LLM_CALL_BUDGET)
    live_cases = [case for case in module.GRAPH_CASES if case["in_live_slice"]]
    sources = _measured_sources_by_query_text(_real_queries_by_id())
    results = module.run_graph_regression(
        live_cases, _real_queries_by_id(), _fake_retrieve_fn(sources), llm, live=True
    )
    return {result["case_id"]: result for result in results}, llm


def test_live_slice_passes_when_both_answers_carry_their_terms_and_valid_citations():
    module = _load_graph_regression_module()
    client = _structured_client(
        {
            "EUR 60,000": "VP Procurement approval with a Finance review is required [1].",
            "EUR 120,000": "This is Band 3, so VP Procurement approves [4]; pull usage data first [1].",
        }
    )

    results, llm = _live_run(module, client)

    assert {result["category"] for result in results.values()} == {module.CATEGORY_PASSED}
    assert llm.calls == module.LIVE_LLM_CALL_BUDGET  # exactly Q001 + Q091; Q092 rejected made none


def test_live_answer_missing_a_required_term_or_citing_a_missing_source_fails_quality():
    """Q091's answer drops "usage data" (the drift Day 19's stored graph-path
    answers actually show) and cites [99], which was never retrieved.
    """
    module = _load_graph_regression_module()
    client = _structured_client(
        {
            "EUR 60,000": "VP Procurement approval with a Finance review is required [1].",
            "EUR 120,000": "This is Band 3, so VP Procurement approves [99].",
        }
    )

    results, _ = _live_run(module, client)
    q091 = results["recursive-recovery-q091"]

    assert q091["category"] == module.CATEGORY_CONTRACT
    assert any("missing required term(s) ['usage data']" in failure for failure in q091["failures"])
    assert any("citations fail" in failure for failure in q091["failures"])
    assert results["control-q001"]["category"] == module.CATEGORY_PASSED
    assert module.exit_code_for(list(results.values())) == module.EXIT_CONTRACT_FAILED


def test_a_provider_failure_is_infrastructure_not_a_quality_verdict():
    """A provider outage must not be reported as "the answer was bad". The
    rejected-Q092 case needs no provider, so it is still evaluated and passes.
    """
    module = _load_graph_regression_module()

    def provider_down(prompt):
        raise ConnectionError("provider unreachable")

    results, _ = _live_run(module, provider_down)

    assert results["control-q001"]["category"] == module.CATEGORY_INFRASTRUCTURE
    assert "ConnectionError: provider unreachable" in results["control-q001"]["failures"][0]
    assert results["bounded-abstention-q092-rejected"]["category"] == module.CATEGORY_PASSED
    assert module.exit_code_for(list(results.values())) == module.EXIT_INFRASTRUCTURE


def test_a_reply_that_breaks_the_answer_schema_fails_that_case_without_stopping_the_run():
    """The provider answered, but with prose instead of `GeneratedAnswer`
    JSON (e.g. a truncated reply). That is an answer failure (exit 1), not
    infrastructure, and it must not abort the run before the Q092-rejected
    zero-call check.
    """
    module = _load_graph_regression_module()

    results, _ = _live_run(module, lambda prompt: "Sorry, here is some prose instead of JSON.")

    assert results["control-q001"]["category"] == module.CATEGORY_CONTRACT
    assert "run did not finish: ValidationError" in results["control-q001"]["failures"][0]
    assert results["bounded-abstention-q092-rejected"]["category"] == module.CATEGORY_PASSED


def test_main_live_wires_the_real_client_through_the_provider_boundary_and_the_budget(monkeypatch):
    """`main(["--live"])` end to end, with `make_openrouter_client` replaced
    by a fake: the live slice runs, both answers are scored, and a provider
    failure inside main is classified as infrastructure (so the boundary
    wrapper is really applied in main, not only in the tests' helper).
    """
    module = _load_graph_regression_module()
    import generation

    sources = _measured_sources_by_query_text(_real_queries_by_id())
    monkeypatch.setattr(module, "build_live_retrieve_fn", lambda: _fake_retrieve_fn(sources))
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key-for-tests")

    good_answers = _structured_client(
        {
            "EUR 60,000": "VP Procurement approval with a Finance review is required [1].",
            "EUR 120,000": "Band 3 applies, so VP Procurement approves [4]; pull usage data first [1].",
        }
    )
    monkeypatch.setattr(generation, "make_openrouter_client", lambda **kwargs: good_answers)
    assert module.main(["--live"]) == module.EXIT_PASSED

    def provider_down(prompt):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(generation, "make_openrouter_client", lambda **kwargs: provider_down)
    assert module.main(["--live"]) == module.EXIT_INFRASTRUCTURE


# ---------------------------------------------------------------------------
# The CLI: the exit code CI reads, with the model loader replaced by a fake.
# ---------------------------------------------------------------------------


def test_main_returns_0_on_the_measured_evidence_and_1_on_route_drift(monkeypatch):
    # Load the module FIRST: its imports put `agentic_retrieval` in
    # `sys.modules`, so the import below works even when this test runs alone.
    module = _load_graph_regression_module()
    from agentic_retrieval import AGENTIC_CASE_OVERRIDES

    sources = _measured_sources_by_query_text(_real_queries_by_id())
    monkeypatch.setattr(module, "build_live_retrieve_fn", lambda: _fake_retrieve_fn(sources))

    assert module.main([]) == module.EXIT_PASSED

    # Q092's follow-up now recovers only CONTRACT-005: still a gap after the
    # one allowed follow-up, so the approved Q092 case must turn red.
    sources[AGENTIC_CASE_OVERRIDES["Q092"]["followup_query"]] = _sources("CONTRACT-005::chunk-3")
    assert module.main([]) == module.EXIT_CONTRACT_FAILED


def test_live_without_an_api_key_exits_2_before_loading_any_model(monkeypatch):
    module = _load_graph_regression_module()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def must_not_load_models():
        raise AssertionError("the key check must run before the models are loaded")

    monkeypatch.setattr(module, "build_live_retrieve_fn", must_not_load_models)

    assert module.main(["--live"]) == module.EXIT_INFRASTRUCTURE


def test_a_model_loading_failure_is_infrastructure(monkeypatch):
    module = _load_graph_regression_module()

    def offline_with_empty_cache():
        raise OSError("Cannot find the requested files in the disk cache and outgoing traffic has been disabled")

    monkeypatch.setattr(module, "build_live_retrieve_fn", offline_with_empty_cache)

    assert module.main([]) == module.EXIT_INFRASTRUCTURE
