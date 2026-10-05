import importlib.util
import json
import sys
import uuid
from pathlib import Path

import pytest
from langchain_core.tracers.context import collect_runs
from pydantic import ValidationError


def _load_module(module_name):
    """Same `src/<module_name>.py` loading pattern every other test file in
    this project uses (see `tests/test_agent_control_plane.py`): `src` is
    only on `sys.path` while the module's own top-level imports resolve.
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


def _load_observability_module():
    return _load_module("agent_observability")


# ---------------------------------------------------------------------------
# Small local helpers, same shapes as `tests/test_agent_control_plane.py`.
# Every run below goes through the REAL Day 18 controlled graph
# (checkpointer, interrupt, resume), with only retrieval and the LLM faked.
# There are no models, corpus, network, LangSmith credentials, or LLM, and
# each run takes milliseconds.
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


def _fake_retrieve_fn(sources_by_query_text):
    """Fake `retrieve_fn(query_text, config) -> sources`. A KeyError means
    the graph asked for a query text the test did not expect."""
    return lambda query_text, config: sources_by_query_text[query_text]


# The Q091 shape: POL-001 is in context, but neither "Band 3" chunk is, so
# the run pauses for approval. Pass 2 returns chunk-3 AGAIN (already in
# context) plus chunk-6 (new). Only chunk-6 should count as "added".
Q091_FOLLOWUP = "approval bands EUR 50,000 250,000 Band 3 VP Procurement"
Q091_CASE_OVERRIDES = {
    "Q091": {
        "followup_query": Q091_FOLLOWUP,
        "acceptable_chunk_ids": ("POL-001::chunk-5", "POL-001::chunk-6"),
    }
}


def _structured_client(answer, answerable_from_sources):
    """Fake structured client: returns `GeneratedAnswer` JSON text, which is
    exactly what the live `make_openrouter_client(response_model=GeneratedAnswer)`
    returns."""
    reply = json.dumps({"answer": answer, "answerable_from_sources": answerable_from_sources})
    return lambda prompt: reply


def _q091_shaped_row(module, decision=None, client=None, langsmith_project=None):
    query_row = _query_row("Q091", "multi_doc", {"POL-001": 2})
    retrieve_fn = _fake_retrieve_fn(
        {
            query_row["query"]: [_source("POL-001", "POL-001::chunk-3"), _source("POL-004", "POL-004::chunk-1")],
            Q091_FOLLOWUP: [_source("POL-001", "POL-001::chunk-3"), _source("POL-001", "POL-001::chunk-6")],
        }
    )
    # The graph Day 19's main() runs: Day 18's controlled graph + structured generation.
    graph = module.build_observed_graph(retrieve_fn, client=client)
    return module.run_and_trace(
        graph, query_row, decision, case_overrides=Q091_CASE_OVERRIDES, langsmith_project=langsmith_project
    )


def _q014_shaped_row(module):
    """The `report_gap` shape: the primary doc (CONTRACT-004) never reaches
    context, and no follow-up query is defined, so the graph refuses after
    one pass without pausing."""
    query_row = _query_row("Q014", "numeric", {"CONTRACT-004": 2})
    retrieve_fn = _fake_retrieve_fn({query_row["query"]: [_source("CONTRACT-001", "CONTRACT-001::chunk-2")]})
    graph = module.build_observed_graph(retrieve_fn)
    return module.run_and_trace(graph, query_row, case_overrides={})


# ---------------------------------------------------------------------------
# The trace row: one finished run, with the fields the route doc asks for.
# ---------------------------------------------------------------------------


def test_q091_shaped_run_records_every_debug_field_from_the_route_doc():
    """Interview drill question 3: "What fields must be present to debug
    Q091's recursive retrieval path?" Each assertion below is one of them.
    """
    module = _load_observability_module()
    row = _q091_shaped_row(module)

    # Run metadata
    assert row.query_id == "Q091"
    assert row.query_type == "multi_doc"
    assert row.thread_id.startswith("Q091-")
    assert row.created_at.tzinfo is not None

    # Route, stop reason, and the HITL decision
    assert row.route_history == ["recursive_retrieve", "generate"]
    assert row.stop_reason == "fixed_after_second_pass"
    assert row.approval.decision == "approve"
    assert row.approval.approved_followup_query == Q091_FOLLOWUP

    # One entry per retrieval pass: the query that ran, its config, and what it ADDED
    first, second = row.retrieval_passes
    assert first.query_text == "synthetic query text for Q091"
    assert first.added_chunk_ids == ["POL-001::chunk-3", "POL-004::chunk-1"]
    assert second.query_text == Q091_FOLLOWUP
    assert second.retrieval_config == first.retrieval_config  # pass 2 reuses pass 1's config
    assert second.added_chunk_ids == ["POL-001::chunk-6"]  # the re-returned chunk-3 added nothing
    assert (first.context_size_after, second.context_size_after) == (2, 3)

    # Before/after evidence
    before, after = row.diagnoses
    assert before.trigger_reason == "missing_chunk"
    assert before.missing_chunk_ids == ["POL-001::chunk-5", "POL-001::chunk-6"]
    assert after.trigger_reason is None

    # The structured result, linked back to this row
    assert row.result.status == "not_generated"  # no LLM client was passed
    assert row.result.evidence_status == "complete"
    assert row.result.citations is None
    assert row.result.run_id == row.run_id

    # Day 18's human-readable lines are kept unchanged, and tracing was off
    assert any(line.startswith("approve_followup:") for line in row.trace_lines)
    assert row.langsmith is None


def test_report_gap_run_is_a_structured_gap_report_not_a_string_to_parse():
    """The contrast case: downstream code learns "refused, and why" from
    fields, without reading the "Not answered: ..." prose."""
    module = _load_observability_module()
    row = _q014_shaped_row(module)

    assert row.route_history == ["report_gap"]
    assert row.stop_reason == "trigger_detected_no_followup_query_defined"
    assert row.approval is None  # never paused: no follow-up to approve
    assert len(row.retrieval_passes) == 1
    assert row.retrieval_passes[0].context_doc_ids_after == ["CONTRACT-001"]  # what came back instead

    assert row.result.status == "gap_report"
    assert row.result.evidence_status == "missing_docs"
    assert row.result.missing_doc_ids == ["CONTRACT-004"]
    assert row.result.citations is None


def test_rejected_followup_is_a_gap_report_with_the_reviewers_reason_as_a_caveat():
    module = _load_observability_module()
    row = _q091_shaped_row(module, decision={"type": "reject", "message": "Band 3 is out of scope"})

    assert row.stop_reason == "followup_rejected_by_reviewer"
    assert row.approval.decision == "reject"
    assert len(row.retrieval_passes) == 1  # the follow-up never ran

    assert row.result.status == "gap_report"
    assert row.result.evidence_status == "missing_chunks"  # the evidence state, not the stop reason
    assert row.result.missing_chunk_ids == ["POL-001::chunk-5", "POL-001::chunk-6"]
    assert any("Band 3 is out of scope" in caveat for caveat in row.result.caveats)


@pytest.mark.parametrize(
    ("answer_text", "expected_passed", "expected_orphans"),
    [
        # Merged context is [1] chunk-3, [2] POL-004 chunk-1, [3] chunk-6.
        ("Band 3 needs the VP Procurement [3].", True, []),
        ("Band 3 needs the VP Procurement [3], see also [9].", False, [9]),
    ],
)
def test_answered_run_carries_a_checked_citation_report(answer_text, expected_passed, expected_orphans):
    """With an LLM client wired in that says it could answer, `status`
    becomes "answered" and the citation report travels with the result. An
    orphan citation is RECORDED (passed=False plus a caveat), not rejected:
    the trace must keep a bad answer as evidence, not throw it away."""
    module = _load_observability_module()
    row = _q091_shaped_row(module, client=_structured_client(answer_text, answerable_from_sources=True))

    assert row.result.status == "answered"
    assert row.result.text == answer_text
    assert row.result.citations.valid_ids == [3]
    assert row.result.citations.orphan_ids == expected_orphans
    assert row.result.citations.passed is expected_passed
    assert any("[9]" in caveat for caveat in row.result.caveats) is (not expected_passed)


def test_model_that_declines_on_complete_evidence_is_model_declined_not_answered():
    """Regression test for the 2026-10-05 Q092 live run. The graph found the
    evidence complete and called the LLM, and the model replied that the
    sources were not enough. v1 labeled that `answered`. Now the model's
    verdict arrives as a FIELD (`answerable_from_sources=false`), and the
    status says what really happened. No sentence is parsed anywhere."""
    module = _load_observability_module()
    decline = "The sources do not contain enough information to answer the question."
    row = _q091_shaped_row(module, client=_structured_client(decline, answerable_from_sources=False))

    # The graph's side is unchanged: complete evidence, normal route and stop reason.
    assert row.route_history == ["recursive_retrieve", "generate"]
    assert row.stop_reason == "fixed_after_second_pass"
    assert row.result.evidence_status == "complete"

    # The model's side now has its own status.
    assert row.result.status == "model_declined"
    assert row.result.text == decline
    assert row.result.citations.cited_ids == []  # the LLM wrote the text, so a citation report exists
    assert any("MODEL DECLINED" in line for line in row.trace_lines)


def test_trace_rows_round_trip_through_jsonl(tmp_path):
    """Write -> read gives back equal, re-validated rows, one JSON object per line."""
    module = _load_observability_module()
    rows = [_q091_shaped_row(module), _q014_shaped_row(module)]
    path = tmp_path / "traces.jsonl"

    module.write_trace_rows(rows, path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["result"]["status"] == "not_generated"  # plain JSON, readable without Pydantic
    assert module.read_trace_rows(path) == rows


def test_langsmith_handle_points_at_the_root_runs_langchain_actually_created():
    """The local row must name the SAME root runs LangSmith receives.

    `collect_runs()` records LangChain's run tree in memory (nothing is
    sent anywhere), so this checks the link without credentials. The Q091
    run pauses once, so there are two root runs: the first invoke and the
    resume. Both carry the row's id and thread in their metadata.
    """
    module = _load_observability_module()

    with collect_runs() as collected:
        row = _q091_shaped_row(module, langsmith_project="test-project")

    assert row.langsmith.project == "test-project"
    assert [run.id for run in collected.traced_runs] == row.langsmith.root_run_ids
    for run in collected.traced_runs:
        assert run.extra["metadata"]["trace_row_id"] == str(row.run_id)
        assert run.extra["metadata"]["thread_id"] == row.thread_id
        assert "day19-observability" in run.tags


# ---------------------------------------------------------------------------
# Validation: what the schema rejects or normalizes. Each test starts from a
# real row, dumps it to plain JSON-shaped data, breaks one thing, and
# re-validates it, which is exactly what happens when a JSONL line is read back.
# ---------------------------------------------------------------------------


def test_missing_required_fields_are_rejected_by_name():
    module = _load_observability_module()
    data = _q091_shaped_row(module).model_dump(mode="json")
    del data["stop_reason"]
    del data["result"]["status"]

    with pytest.raises(ValidationError) as excinfo:
        module.AgentRunTrace.model_validate(data)

    missing = {error["loc"] for error in excinfo.value.errors() if error["type"] == "missing"}
    assert missing == {("stop_reason",), ("result", "status")}


@pytest.mark.parametrize(
    ("break_row", "error_location"),
    [
        (lambda data: data["result"].update(status="Answered"), ("result", "status")),  # wrong case
        (lambda data: data.update(stop_reason="gave_up"), ("stop_reason",)),  # not a known stop reason
        (lambda data: data["approval"].update(decision="aprove"), ("approval", "decision")),  # typo
        (lambda data: data.update(stop_reson="fixed_after_second_pass"), ("stop_reson",)),  # unknown key
        (lambda data: data.update(created_at="2026-10-05T12:00:00"), ("created_at",)),  # no timezone
        (lambda data: data.update(schema_version=3), ("schema_version",)),  # a version this reader doesn't know
    ],
)
def test_invalid_values_and_unknown_keys_are_rejected_at_the_exact_field(break_row, error_location):
    module = _load_observability_module()
    data = _q091_shaped_row(module).model_dump(mode="json")
    break_row(data)

    with pytest.raises(ValidationError) as excinfo:
        module.AgentRunTrace.model_validate(data)

    assert [error["loc"] for error in excinfo.value.errors()] == [error_location]


def test_citation_ids_are_normalized_from_numeric_strings_but_garbage_and_false_flags_are_rejected():
    """Pydantic's default ("lax") mode NORMALIZES unambiguous input: "3"
    becomes 3. It still REJECTS input that can't be an int, and the model
    validator rejects a `passed` flag that contradicts the lists."""
    module = _load_observability_module()
    report = {"cited_ids": ["3"], "valid_ids": ["3"], "orphan_ids": [], "uncited_ids": [1, 2], "passed": True}

    assert module.CitationCheck.model_validate(report).cited_ids == [3]

    with pytest.raises(ValidationError, match="cited_ids"):
        module.CitationCheck.model_validate({**report, "cited_ids": ["three"]})

    with pytest.raises(ValidationError, match="contradicts"):
        module.CitationCheck.model_validate({**report, "orphan_ids": [9]})  # orphans, yet passed=True


def test_result_cannot_claim_an_answer_on_missing_evidence():
    """The graph's core safety rule ("never answer on incomplete evidence"),
    enforced on the output itself. Any producer, including a future LLM
    filling in this schema, is held to it."""
    module = _load_observability_module()
    gap_result = _q014_shaped_row(module).result.model_dump(mode="json")

    answered_anyway = {
        **gap_result,
        "status": "answered",
        "citations": {"cited_ids": [1], "valid_ids": [1], "orphan_ids": [], "uncited_ids": [], "passed": True},
    }
    with pytest.raises(ValidationError, match="needs complete evidence"):
        module.AgentResult.model_validate(answered_anyway)

    complete_but_missing = {**gap_result, "evidence_status": "complete"}
    with pytest.raises(ValidationError, match="contradicts missing_doc_ids"):
        module.AgentResult.model_validate(complete_but_missing)


def test_trace_row_must_point_at_its_own_result_and_describe_a_finished_run():
    module = _load_observability_module()
    data = _q091_shaped_row(module).model_dump(mode="json")

    wrong_handle = {**data, "result": {**data["result"], "run_id": str(uuid.uuid4())}}
    with pytest.raises(ValidationError, match="does not match the row's run_id"):
        module.AgentRunTrace.model_validate(wrong_handle)

    still_paused = {**data, "route_history": ["recursive_retrieve"]}
    with pytest.raises(ValidationError, match="must describe a finished run"):
        module.AgentRunTrace.model_validate(still_paused)


def test_result_json_schema_is_the_shape_provider_structured_output_consumes():
    """`model_json_schema()` is the bridge to OpenAI Structured Outputs and
    LangChain's `response_format`: the same contract, as JSON Schema. Strict
    provider modes need every field listed in `required` and
    `additionalProperties: false`. This schema has both, because the models
    have no defaults and use `extra="forbid"`. (Not yet sent to a provider:
    today the result wraps deterministic graph output.)"""
    module = _load_observability_module()
    schema = module.AgentResult.model_json_schema()

    assert schema["properties"]["status"]["enum"] == ["answered", "model_declined", "gap_report", "not_generated"]
    assert schema["properties"]["evidence_status"]["enum"] == ["complete", "missing_docs", "missing_chunks"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_schema_vocabularies_match_the_graph_constants():
    """The `Literal[...]` types are written as plain strings (the typing spec
    does not allow constants inside `Literal`), so this test is what keeps
    them tied to the Day 16-19 constants. If a constant is renamed and the
    schema is not, this fails instead of the schema silently rejecting
    every real row."""
    from typing import get_args

    module = _load_observability_module()
    graph = _load_module("agent_graph")
    day16 = _load_module("agentic_retrieval")
    control = _load_module("agent_control_plane")

    assert set(get_args(module.RouteLabel)) == {
        graph.ROUTE_GENERATE,
        graph.ROUTE_RECURSIVE_RETRIEVE,
        graph.ROUTE_REPORT_GAP,
    }
    assert set(get_args(module.StopReason)) == {
        day16.STOP_NO_MISSING_EVIDENCE,
        day16.STOP_FIXED_AFTER_SECOND_PASS,
        day16.STOP_NO_FOLLOWUP_QUERY_DEFINED,
        day16.STOP_STILL_MISSING_AFTER_MAX_PASSES,
        control.STOP_FOLLOWUP_REJECTED,
    }
    assert set(get_args(module.TriggerReason)) == {day16.TRIGGER_MISSING_DOC, day16.TRIGGER_MISSING_CHUNK}
    assert set(get_args(module.ReviewerDecision)) == set(control.ALLOWED_DECISIONS)
    assert set(get_args(module.ResultStatus)) == {
        module.STATUS_ANSWERED,
        module.STATUS_MODEL_DECLINED,
        module.STATUS_GAP_REPORT,
        module.STATUS_NOT_GENERATED,
    }
    assert set(get_args(module.EvidenceStatus)) == {
        module.EVIDENCE_COMPLETE,
        module.EVIDENCE_MISSING_DOCS,
        module.EVIDENCE_MISSING_CHUNKS,
    }


def test_new_rows_are_v2_and_v1_rows_still_read():
    """Schema evolution: v2 only ADDED a status value, so every v1 row is
    still a valid v2 row. Writers always write the current version; the
    reader accepts both, which keeps the committed v1 evidence files
    readable."""
    module = _load_observability_module()
    row = _q014_shaped_row(module)
    assert row.schema_version == module.TRACE_SCHEMA_VERSION == 2

    v1_data = {**row.model_dump(mode="json"), "schema_version": 1}
    assert module.AgentRunTrace.model_validate(v1_data).schema_version == 1
