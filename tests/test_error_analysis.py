import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module(module_name):
    """Same `src/<module_name>.py` loading pattern every other test file in
    this project uses (see `tests/test_generation_eval.py`,
    `tests/test_framework_eval.py`): `src` is only on `sys.path` while the
    module's own top-level imports (`error_analysis.py` does
    `from generation_eval import ...`) resolve.
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


def _load_error_analysis_module():
    return _load_module("error_analysis")


def _real_queries_by_id(module):
    """Pull real rows out of `data/corpus_v1/example_queries.jsonl` - the
    same `_real_query` pattern `tests/test_generation_eval.py` uses. Day 13's
    cases are built from the real corpus, not hand-typed stand-ins, so the
    tests below load it for real too.
    """
    from hybrid_search import load_example_queries

    return {row["query_id"]: row for row in load_example_queries()}


# ---------------------------------------------------------------------------
# build_case_record: the taxonomy label contract
# ---------------------------------------------------------------------------


def test_build_case_record_rejects_an_unrecognized_root_cause_label():
    error_analysis = _load_error_analysis_module()
    query_row = {"query_id": "Q000", "query_type": "lookup", "query": "test?", "relevance_grades": {}}

    with pytest.raises(ValueError, match="not a recognized root-cause label"):
        error_analysis.build_case_record(
            query_row,
            sources=[],
            answer_text="answer",
            human_root_cause_label="made_up_label",
            notes="",
            recommended_repair="",
            verification_signal="",
        )


def test_build_case_record_computes_missing_primary_doc_ids():
    error_analysis = _load_error_analysis_module()
    query_row = {
        "query_id": "Q500",
        "query_type": "multi_doc",
        "query": "test?",
        "relevance_grades": {"POL-001": 2, "GUIDE-002": 2, "FAQ-001": 1},
    }
    # Only POL-001 was retrieved; GUIDE-002 (also primary) never was.
    sources = [error_analysis._source(1, "POL-001", "Policy", "Band 3 needs VP approval.")]

    case = error_analysis.build_case_record(
        query_row,
        sources,
        "VP approval is required [1].",
        human_root_cause_label="retrieval_miss",
        notes="",
        recommended_repair="",
        verification_signal="",
    )

    assert case["query_id"] == "Q500"
    assert case["context_recall_status"] == "fail"
    assert case["missing_primary_doc_ids"] == ["GUIDE-002"]
    assert case["citation_status"] == "pass"
    assert case["human_root_cause_label"] == "retrieval_miss"
    # The full Day 11 findings stay attached, not discarded.
    assert {finding["check"] for finding in case["findings"]} == {
        "citation_validity",
        "context_recall",
        "unsupported_inference",
    }


def test_build_case_record_passes_control_shape():
    error_analysis = _load_error_analysis_module()
    query_row = {
        "query_id": "Q501",
        "query_type": "threshold",
        "query": "test?",
        "relevance_grades": {"POL-001": 2},
    }
    sources = [error_analysis._source(1, "POL-001", "Policy", "Band 3 needs VP approval.")]

    case = error_analysis.build_case_record(
        query_row,
        sources,
        "VP approval is required [1].",
        human_root_cause_label="passes_control",
        notes="clean pass",
        recommended_repair="none",
        verification_signal="stays passing",
    )

    assert case["context_recall_status"] == "pass"
    assert case["citation_status"] == "pass"
    assert case["missing_primary_doc_ids"] == []


# ---------------------------------------------------------------------------
# build_cases: the real, five-case Day 13 taxonomy, against the real corpus
# ---------------------------------------------------------------------------


def test_build_cases_returns_exactly_five_cases_with_valid_labels():
    error_analysis = _load_error_analysis_module()
    queries_by_id = _real_queries_by_id(error_analysis)

    cases = error_analysis.build_cases(queries_by_id)

    assert len(cases) == 5
    assert {case["query_id"] for case in cases} == {"Q001", "Q091", "Q093", "Q016", "Q004"}
    assert all(case["human_root_cause_label"] in error_analysis.ROOT_CAUSE_LABELS for case in cases)


def test_build_cases_includes_q001_and_q004_as_passing_controls():
    # The two controls Day 13 needs so "everything is broken" isn't the only
    # story the taxonomy can tell - one multi_doc-adjacent easy case (Q001),
    # one non-multi_doc medium case (Q004), per the design doc's instruction
    # to guard against overfitting the taxonomy to only multi_doc failures.
    error_analysis = _load_error_analysis_module()
    queries_by_id = _real_queries_by_id(error_analysis)
    cases_by_id = {case["query_id"]: case for case in error_analysis.build_cases(queries_by_id)}

    for query_id in ("Q001", "Q004"):
        case = cases_by_id[query_id]
        assert case["human_root_cause_label"] == "passes_control"
        assert case["context_recall_status"] == "pass"
        assert case["citation_status"] == "pass"
        assert case["missing_primary_doc_ids"] == []


def test_build_cases_q091_is_the_known_retrieval_miss_anchor():
    # The non-negotiable Day 13 finding, reproduced automatically here
    # rather than only asserted in prose: Q091's real transcript is missing
    # exactly POL-001 and GUIDE-002 from its retrieved context.
    error_analysis = _load_error_analysis_module()
    queries_by_id = _real_queries_by_id(error_analysis)
    cases_by_id = {case["query_id"]: case for case in error_analysis.build_cases(queries_by_id)}

    q091 = cases_by_id["Q091"]
    assert q091["human_root_cause_label"] == "retrieval_miss"
    assert q091["context_recall_status"] == "fail"
    assert q091["missing_primary_doc_ids"] == ["GUIDE-002", "POL-001"]
    # Citations are still clean - the point of this case is that retrieval,
    # not generation, is what's broken.
    assert q091["citation_status"] == "pass"


def test_build_cases_q093_is_a_retrieval_miss_on_a_different_document():
    # A second, distinct retrieval_miss: CONTRACT-001 (Acme's 3% deadband)
    # never reached context, causing the answer to state Batavia's 2% figure
    # as if it were universal - see error_analysis.py's Q093 fixture comment.
    error_analysis = _load_error_analysis_module()
    queries_by_id = _real_queries_by_id(error_analysis)
    cases_by_id = {case["query_id"]: case for case in error_analysis.build_cases(queries_by_id)}

    q093 = cases_by_id["Q093"]
    assert q093["human_root_cause_label"] == "retrieval_miss"
    assert q093["context_recall_status"] == "fail"
    assert q093["missing_primary_doc_ids"] == ["CONTRACT-001"]


def test_build_cases_q016_document_level_recall_passes_but_chunk_level_does_not():
    # The contrast case that proves "multi_doc" isn't one single failure
    # mode: both primary documents WERE retrieved at the document level
    # (context_recall passes), but the specific chunk carrying the fact
    # expected_answer needs was never retrieved - a real gap, but still a
    # retrieval/context-construction one, not a generation one. This is
    # `chunk_level_retrieval_gap`, NOT `answer_completeness_gap` - the
    # latter would mean the model had the fact and failed to use it, which
    # is not what happened here (see error_analysis.py's Q016 fixture
    # comment for the full correction).
    error_analysis = _load_error_analysis_module()
    queries_by_id = _real_queries_by_id(error_analysis)
    cases_by_id = {case["query_id"]: case for case in error_analysis.build_cases(queries_by_id)}

    q016 = cases_by_id["Q016"]
    assert q016["context_recall_status"] == "pass"
    assert q016["missing_primary_doc_ids"] == []
    assert q016["human_root_cause_label"] == "chunk_level_retrieval_gap"
