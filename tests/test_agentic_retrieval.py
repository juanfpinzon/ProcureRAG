import importlib.util
import sys
from pathlib import Path


def _load_module(module_name):
    """Same `src/<module_name>.py` loading pattern every other test file in
    this project uses (see `tests/test_regression_suite.py`,
    `tests/test_reranking.py`): `src` is only on `sys.path` while the
    module's own top-level imports (`agentic_retrieval.py` does
    `from generation import ...`, `from generation_eval import ...`,
    `from reranking import ...`) resolve.
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


def _load_agentic_retrieval_module():
    return _load_module("agentic_retrieval")


def _real_queries_by_id():
    from hybrid_search import load_example_queries

    return {row["query_id"]: row for row in load_example_queries()}


# ---------------------------------------------------------------------------
# Small local helpers: a synthetic query_row and a `sources`-shaped source
# dict, matching exactly what `generation.build_sources` produces
# (`doc_id`, `chunk_id`, `title`, `text`, `rank`, `score`) - the same shape
# every real `retrieve_fn` call in `agentic_retrieval.py` returns.
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
    """Wraps a dict-lookup fake retrieval function and counts calls.

    Keyed by the exact query text `run_recursive_retrieval` passes in - the
    original query on the first pass, the reformulated `followup_query` on
    the second. A `KeyError` here means the code under test asked for
    retrieval on a query text the test did not anticipate, which is a more
    useful failure than silently returning some default.
    """

    def __init__(self, sources_by_query_text):
        self.sources_by_query_text = sources_by_query_text
        self.call_count = 0
        self.queries_received = []

    def __call__(self, query_text, config):
        self.call_count += 1
        self.queries_received.append(query_text)
        return self.sources_by_query_text[query_text]


# ---------------------------------------------------------------------------
# Pure-function unit tests: evaluate_missing_evidence, decide_trigger,
# merge_sources - each tested directly, no retrieval involved at all.
# ---------------------------------------------------------------------------


def test_evaluate_missing_evidence_finds_missing_primary_doc():
    module = _load_agentic_retrieval_module()
    query_row = _query_row("QX", "multi_doc", {"POL-001": 2, "FAQ-001": 1})
    sources = [_source("FAQ-001", "FAQ-001::chunk-1")]  # POL-001 never retrieved

    missing = module.evaluate_missing_evidence(query_row, sources)

    assert missing["missing_doc_ids"] == ["POL-001"]
    assert missing["missing_chunk_ids"] == []


def test_evaluate_missing_evidence_finds_missing_required_chunk_even_if_doc_present():
    module = _load_agentic_retrieval_module()
    query_row = _query_row("QX", "multi_doc", {"POL-001": 2})
    # POL-001 IS in context, but via a different chunk than either of the
    # acceptable ones - this is exactly Q091's real shape (POL-001::chunk-3
    # present, POL-001::chunk-5/chunk-6 - the two chunks that both carry the
    # "Band 3" sentence, per the corpus's overlapping chunker - absent).
    sources = [_source("POL-001", "POL-001::chunk-3")]

    missing = module.evaluate_missing_evidence(
        query_row, sources, acceptable_chunk_ids=("POL-001::chunk-5", "POL-001::chunk-6")
    )

    assert missing["missing_doc_ids"] == []
    assert missing["missing_chunk_ids"] == ["POL-001::chunk-5", "POL-001::chunk-6"]


def test_evaluate_missing_evidence_chunk_requirement_is_satisfied_by_any_one_acceptable_chunk():
    """OR semantics, not AND: Q091's "Band 3" sentence is duplicated across
    two overlapping chunks (POL-001::chunk-5 and POL-001::chunk-6). Only one
    of them needs to reach context for the chunk-level requirement to count
    as satisfied - requiring both would be a stricter standard than the fact
    itself demands.
    """
    module = _load_agentic_retrieval_module()
    query_row = _query_row("QX", "multi_doc", {"POL-001": 2})
    # Only chunk-6 is present, chunk-5 is not - still satisfied.
    sources = [_source("POL-001", "POL-001::chunk-6")]

    missing = module.evaluate_missing_evidence(
        query_row, sources, acceptable_chunk_ids=("POL-001::chunk-5", "POL-001::chunk-6")
    )

    assert missing["missing_chunk_ids"] == []


def test_decide_trigger_prefers_missing_doc_over_missing_chunk():
    module = _load_agentic_retrieval_module()
    assert module.decide_trigger(["POL-001"], ["POL-001::chunk-4"]) == module.TRIGGER_MISSING_DOC
    assert module.decide_trigger([], ["POL-001::chunk-4"]) == module.TRIGGER_MISSING_CHUNK
    assert module.decide_trigger([], []) is None


def test_merge_sources_keeps_first_pass_order_and_appends_only_new_chunks():
    module = _load_agentic_retrieval_module()
    first_pass = [_source("POL-001", "POL-001::chunk-3"), _source("FAQ-001", "FAQ-001::chunk-1")]
    second_pass = [
        _source("POL-001", "POL-001::chunk-3"),  # duplicate - already in first pass
        _source("POL-001", "POL-001::chunk-4"),  # new
    ]

    merged = module.merge_sources(first_pass, second_pass)

    assert [source["chunk_id"] for source in merged] == [
        "POL-001::chunk-3",
        "FAQ-001::chunk-1",
        "POL-001::chunk-4",
    ]


# ---------------------------------------------------------------------------
# run_recursive_retrieval: the full loop, with a fake retrieve_fn - one test
# per required behavior from the Day 16 route doc's "Tests ... cover at
# least" checklist.
# ---------------------------------------------------------------------------


def test_no_trigger_control_only_calls_retrieve_fn_once():
    """The no-second-pass control: nothing missing on the first pass, so
    `retrieve_fn` must be called exactly once - proof the loop is selective,
    not applied globally, without needing to inspect any internal flag.
    """
    module = _load_agentic_retrieval_module()
    query_row = _query_row("Q001", "threshold", {"POL-001": 2})
    retrieve_fn = _CountingRetrieveFn(
        {query_row["query"]: [_source("POL-001", "POL-001::chunk-1")]}
    )

    state = module.run_recursive_retrieval(query_row, retrieve_fn, case_overrides={})

    assert retrieve_fn.call_count == 1
    assert state["trigger_reason"] is None
    assert state["followup_query"] is None
    assert state["stop_reason"] == module.STOP_NO_MISSING_EVIDENCE
    assert state["final_missing_doc_ids"] == []


def test_triggered_second_pass_fixes_a_missing_document():
    """The triggered-and-fixed path: a missing primary doc on pass 1 is
    recovered by the targeted follow-up query on pass 2.
    """
    module = _load_agentic_retrieval_module()
    query_row = _query_row("QX", "multi_doc", {"POL-002": 2})
    first_pass_text = query_row["query"]
    followup_text = "targeted follow-up for POL-002"
    retrieve_fn = _CountingRetrieveFn(
        {
            first_pass_text: [_source("FAQ-001", "FAQ-001::chunk-1")],  # POL-002 missing
            followup_text: [_source("POL-002", "POL-002::chunk-11")],  # now found
        }
    )
    case_overrides = {"QX": {"followup_query": followup_text, "acceptable_chunk_ids": ()}}

    state = module.run_recursive_retrieval(query_row, retrieve_fn, case_overrides=case_overrides)

    assert retrieve_fn.call_count == 2
    assert state["trigger_reason"] == module.TRIGGER_MISSING_DOC
    assert state["followup_query"] == followup_text
    assert state["stop_reason"] == module.STOP_FIXED_AFTER_SECOND_PASS
    assert state["final_missing_doc_ids"] == []
    assert state["missing_doc_status"]["POL-002"]["found_after_merge"] is True
    # merge is additive: the first-pass chunk is still present after merge
    assert "FAQ-001::chunk-1" in state["first_pass_chunk_ids"]


def test_triggered_second_pass_still_missing_is_reported_honestly():
    """The still-open-failure path: the follow-up query does not recover
    the missing document. This must NOT be hidden or reported as a
    success - `stop_reason` must say so explicitly.
    """
    module = _load_agentic_retrieval_module()
    query_row = _query_row("QY", "multi_doc", {"CONTRACT-005": 2})
    first_pass_text = query_row["query"]
    followup_text = "targeted follow-up for CONTRACT-005"
    retrieve_fn = _CountingRetrieveFn(
        {
            first_pass_text: [_source("FAQ-001", "FAQ-001::chunk-1")],
            followup_text: [_source("FAQ-001", "FAQ-001::chunk-2")],  # still no CONTRACT-005
        }
    )
    case_overrides = {"QY": {"followup_query": followup_text, "acceptable_chunk_ids": ()}}

    state = module.run_recursive_retrieval(query_row, retrieve_fn, case_overrides=case_overrides)

    assert retrieve_fn.call_count == 2
    assert state["stop_reason"] == module.STOP_STILL_MISSING_AFTER_MAX_PASSES
    assert state["final_missing_doc_ids"] == ["CONTRACT-005"]
    assert state["missing_doc_status"]["CONTRACT-005"]["found_after_merge"] is False


def test_two_missing_documents_are_reported_separately_not_blended():
    """Q092's real shape: two missing primary docs with different owners.
    One second pass may recover one but not the other - the route doc
    requires that outcome be visible per-document, not folded into a
    single blended pass/fail.
    """
    module = _load_agentic_retrieval_module()
    query_row = _query_row("Q092", "multi_doc", {"CONTRACT-005": 2, "POL-002": 2})
    first_pass_text = query_row["query"]
    followup_text = "one combined follow-up for both missing docs"
    retrieve_fn = _CountingRetrieveFn(
        {
            first_pass_text: [_source("POL-006", "POL-006::chunk-1")],
            # the combined second pass recovers CONTRACT-005 but not POL-002
            followup_text: [_source("CONTRACT-005", "CONTRACT-005::chunk-3")],
        }
    )
    case_overrides = {"Q092": {"followup_query": followup_text, "acceptable_chunk_ids": ()}}

    state = module.run_recursive_retrieval(query_row, retrieve_fn, case_overrides=case_overrides)

    assert retrieve_fn.call_count == 2  # exactly one extra pass, for BOTH docs combined
    assert state["missing_doc_status"] == {
        "CONTRACT-005": {"found_after_merge": True},
        "POL-002": {"found_after_merge": False},
    }
    assert state["final_missing_doc_ids"] == ["POL-002"]
    assert state["stop_reason"] == module.STOP_STILL_MISSING_AFTER_MAX_PASSES


def test_missing_chunk_trigger_fixed_after_second_pass():
    """Q091's real shape: the primary document is already present, but
    neither acceptable chunk is - the trigger must fire on the chunk-level
    signal even though `missing_doc_ids` is empty. The second pass recovers
    only ONE of the two acceptable chunks (chunk-6, not chunk-5) - that is
    still enough under the OR semantics `evaluate_missing_evidence` uses.
    """
    module = _load_agentic_retrieval_module()
    query_row = _query_row("Q091", "multi_doc", {"POL-001": 2})
    first_pass_text = query_row["query"]
    followup_text = "approval bands EUR 50,000 250,000 Band 3 VP Procurement"
    retrieve_fn = _CountingRetrieveFn(
        {
            first_pass_text: [_source("POL-001", "POL-001::chunk-3")],
            followup_text: [_source("POL-001", "POL-001::chunk-6")],
        }
    )
    case_overrides = {
        "Q091": {
            "followup_query": followup_text,
            "acceptable_chunk_ids": ("POL-001::chunk-5", "POL-001::chunk-6"),
        }
    }

    state = module.run_recursive_retrieval(query_row, retrieve_fn, case_overrides=case_overrides)

    assert state["trigger_reason"] == module.TRIGGER_MISSING_CHUNK
    assert state["stop_reason"] == module.STOP_FIXED_AFTER_SECOND_PASS
    assert state["final_missing_chunk_ids"] == []


def test_trigger_without_known_followup_query_stops_honestly_without_second_pass():
    """A query with missing evidence but no entry in `case_overrides` must
    stop rather than guess a reformulation - and must NOT call `retrieve_fn`
    a second time, since there is no follow-up query to run.
    """
    module = _load_agentic_retrieval_module()
    query_row = _query_row("QZ", "multi_doc", {"POL-009": 2})
    retrieve_fn = _CountingRetrieveFn({query_row["query"]: [_source("FAQ-001", "FAQ-001::chunk-1")]})

    state = module.run_recursive_retrieval(query_row, retrieve_fn, case_overrides={})

    assert retrieve_fn.call_count == 1
    assert state["trigger_reason"] == module.TRIGGER_MISSING_DOC
    assert state["followup_query"] is None
    assert state["stop_reason"] == module.STOP_NO_FOLLOWUP_QUERY_DEFINED


# ---------------------------------------------------------------------------
# One test grounded in the real corpus rows (Q001, Q091, Q092 from
# `data/corpus_v1/example_queries.jsonl`), with a faked retrieve_fn so it
# stays fast and deterministic - proves the module's own
# `AGENTIC_CASE_OVERRIDES` wiring (the real follow-up queries and acceptable
# chunk ids this project actually ships) behaves as designed against the
# real `relevance_grades` for these queries, not just synthetic ones.
# ---------------------------------------------------------------------------


def test_real_q091_and_q092_rows_with_faked_retrieval():
    module = _load_agentic_retrieval_module()
    queries_by_id = _real_queries_by_id()

    q091 = queries_by_id["Q091"]
    q091_followup = module.AGENTIC_CASE_OVERRIDES["Q091"]["followup_query"]
    retrieve_fn_q091 = _CountingRetrieveFn(
        {
            q091["query"]: [
                _source("POL-001", "POL-001::chunk-3"),
                _source("POL-003", "POL-003::chunk-1"),
                _source("GUIDE-002", "GUIDE-002::chunk-1"),
            ],
            # only chunk-6 comes back (not chunk-5) - the real live run
            # confirmed either one alone satisfies the OR-semantics
            # acceptable_chunk_ids check, so this is an honest fake, not a
            # convenient one.
            q091_followup: [_source("POL-001", "POL-001::chunk-6")],
        }
    )
    state_q091 = module.run_recursive_retrieval(q091, retrieve_fn_q091)
    assert state_q091["trigger_reason"] == module.TRIGGER_MISSING_CHUNK
    assert state_q091["stop_reason"] == module.STOP_FIXED_AFTER_SECOND_PASS

    q092 = queries_by_id["Q092"]
    q092_followup = module.AGENTIC_CASE_OVERRIDES["Q092"]["followup_query"]
    retrieve_fn_q092 = _CountingRetrieveFn(
        {
            q092["query"]: [
                _source("POL-006", "POL-006::chunk-1"),
                _source("POL-008", "POL-008::chunk-1"),
                _source("SOP-004", "SOP-004::chunk-1"),
            ],
            # matches the real Day 15 diagnostic: the follow-up recovers
            # neither document in this faked run, exercising the still-open
            # path against the real query row/relevance grades.
            q092_followup: [_source("POL-006", "POL-006::chunk-2")],
        }
    )
    state_q092 = module.run_recursive_retrieval(q092, retrieve_fn_q092)
    assert state_q092["trigger_reason"] == module.TRIGGER_MISSING_DOC
    assert set(state_q092["first_pass_missing_doc_ids"]) == {"CONTRACT-005", "POL-002"}
    assert state_q092["stop_reason"] == module.STOP_STILL_MISSING_AFTER_MAX_PASSES
    assert state_q092["missing_doc_status"]["CONTRACT-005"]["found_after_merge"] is False
    assert state_q092["missing_doc_status"]["POL-002"]["found_after_merge"] is False
