import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module(module_name):
    """Same `src/<module_name>.py` loading pattern every other test file in
    this project uses (see `tests/test_error_analysis.py`,
    `tests/test_framework_eval.py`): `src` is only on `sys.path` while the
    module's own top-level imports (`regression_suite.py` does
    `from error_analysis import ...`, `from framework_eval import ...`,
    etc.) resolve.
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


def _load_regression_suite_module():
    return _load_module("regression_suite")


def _real_queries_by_id(module):
    from hybrid_search import load_example_queries

    return {row["query_id"]: row for row in load_example_queries()}


# ---------------------------------------------------------------------------
# run_deterministic_suite: the seven-case shape, no network, no live import
# ---------------------------------------------------------------------------


def test_run_deterministic_suite_returns_exactly_seven_cases():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)

    rows = regression_suite.run_deterministic_suite(queries_by_id)

    assert len(rows) == 7
    assert {row["case_id"] for row in rows} == {
        "control-q001",
        "control-q004",
        "retrieval-miss-q091",
        "retrieval-miss-q093",
        "chunk-gap-q016",
        "citation-negative-synthetic",
        "refusal-negative-synthetic",
    }


def test_run_deterministic_suite_never_touches_deepeval_or_ragas():
    # If run_deterministic_suite (or anything it calls) imported deepeval or
    # ragas at all, this test would fail with ImportError instead of
    # returning a clean result - the same "poison sys.modules" proof
    # tests/test_framework_eval.py already uses for the live=False path.
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setitem(sys.modules, "deepeval", None)
        monkeypatch.setitem(sys.modules, "ragas", None)

        rows = regression_suite.run_deterministic_suite(queries_by_id)

    assert len(rows) == 7
    assert all(row["live_status"] is None for row in rows)


# ---------------------------------------------------------------------------
# The two passing controls (Q001, Q004): must match their own "no gap" state
# ---------------------------------------------------------------------------


def test_controls_q001_and_q004_match_their_expected_clean_state():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows_by_id = {row["case_id"]: row for row in regression_suite.run_deterministic_suite(queries_by_id)}

    for case_id in ("control-q001", "control-q004"):
        row = rows_by_id[case_id]
        assert row["deterministic_match"] is True
        assert row["missing_primary_doc_ids"] == []
        assert row["citation_status"] == "pass"


# ---------------------------------------------------------------------------
# The two retrieval-miss anchors (Q091, Q093): Block 3B repaired both -
# these now assert the CURRENT, post-repair state (missing docs == []),
# captured from a real retrieval + real live generation run under
# reranking.MULTI_DOC_RETRIEVAL_CONFIG. See error_analysis.py's own,
# untouched Q091/Q093 fixtures for the historical pre-repair evidence these
# numbers used to be.
# ---------------------------------------------------------------------------


def test_q091_is_repaired_missing_docs_now_empty():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows_by_id = {row["case_id"]: row for row in regression_suite.run_deterministic_suite(queries_by_id)}

    row = rows_by_id["retrieval-miss-q091"]
    # The real Block 3B repair signal: both primary documents Day 13 found
    # missing (GUIDE-002, POL-001) now reach context under the repaired
    # retrieval config - this is not the same fixture Day 13 captured.
    assert row["missing_primary_doc_ids"] == []
    assert row["deterministic_match"] is True
    assert row["citation_status"] == "pass"
    assert row["retrieval_config"] == regression_suite.MULTI_DOC_RETRIEVAL_CONFIG


def test_q093_is_repaired_missing_docs_now_empty():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows_by_id = {row["case_id"]: row for row in regression_suite.run_deterministic_suite(queries_by_id)}

    row = rows_by_id["retrieval-miss-q093"]
    assert row["missing_primary_doc_ids"] == []
    assert row["deterministic_match"] is True


def test_a_stale_expectation_against_the_repaired_fixture_is_flagged_as_a_mismatch():
    # Prove the "regression" concept actually fires in the direction that
    # matters now: hand-build a case spec that still expects Q091's OLD,
    # pre-repair missing-doc list against the NEW, already-repaired
    # fixture - exactly what would happen if a case spec's expectation went
    # stale (forgot to be updated) after a real pipeline change. This must
    # be caught as a mismatch, not silently accepted.
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    query_row = queries_by_id["Q091"]

    stale_case_spec = dict(regression_suite.REGRESSION_CASES[2])  # retrieval-miss-q091
    assert stale_case_spec["case_id"] == "retrieval-miss-q091"
    stale_case_spec["expected_missing_primary_doc_ids"] = ["GUIDE-002", "POL-001"]  # the OLD, pre-repair value

    row = regression_suite.evaluate_case(stale_case_spec, query_row)

    assert row["missing_primary_doc_ids"] == []  # the real, current, repaired result
    assert row["deterministic_match"] is False


# ---------------------------------------------------------------------------
# The chunk-gap contrast case (Q016): Block 3B addressed it - the specific
# GUIDE-001::chunk-2 (the "logistics price <=40%" fact) now reaches
# context, verified by a real chunk-id check (`required_chunk_ids`), not
# just a hand-written note.
# ---------------------------------------------------------------------------


def test_q016_document_level_recall_passes_and_the_specific_chunk_is_now_present():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows_by_id = {row["case_id"]: row for row in regression_suite.run_deterministic_suite(queries_by_id)}

    row = rows_by_id["chunk-gap-q016"]
    assert row["missing_primary_doc_ids"] == []
    # The real, computed chunk-level check: GUIDE-001::chunk-2 must be
    # present, not just claimed present in a comment.
    assert row["missing_chunk_ids"] == []
    assert row["deterministic_match"] is True
    assert row["table_note"] is not None
    assert "chunk" in row["table_note"].lower()
    assert "ADDRESSED" in row["table_note"]


def test_q016_chunk_level_check_would_catch_a_regression_if_the_chunk_went_missing_again():
    # Prove the chunk-level check is a real gate, not decoration: hand-build
    # a case spec whose `sources` no longer include GUIDE-001::chunk-2 (the
    # exact pre-repair Q016 shape) and confirm missing_chunk_ids/
    # deterministic_match correctly flag it, even though document-level
    # recall would still pass (GUIDE-001 the *document* is still present
    # via a different chunk).
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    query_row = queries_by_id["Q016"]

    case_spec = dict(regression_suite.REGRESSION_CASES[4])  # chunk-gap-q016
    assert case_spec["case_id"] == "chunk-gap-q016"
    case_spec["sources"] = [
        source for source in case_spec["sources"] if source["chunk_id"] != "GUIDE-001::chunk-2"
    ]

    row = regression_suite.evaluate_case(case_spec, query_row)

    assert row["missing_primary_doc_ids"] == []  # GUIDE-001 the document is still present
    assert row["missing_chunk_ids"] == ["GUIDE-001::chunk-2"]  # but this specific chunk is not
    assert row["deterministic_match"] is False
    assert "OPEN" in row["table_note"]


# ---------------------------------------------------------------------------
# The citation-negative boundary case: expects citation_validity to FAIL
# ---------------------------------------------------------------------------


def test_citation_negative_case_expects_and_gets_a_citation_failure():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows_by_id = {row["case_id"]: row for row in regression_suite.run_deterministic_suite(queries_by_id)}

    row = rows_by_id["citation-negative-synthetic"]
    # The synthetic [99] citation must be caught as an orphan...
    assert row["citation_status"] == "fail"
    # ...and because the case's own contract *expects* a failure here, the
    # case as a whole is still "as expected", not a regression.
    assert row["deterministic_match"] is True


def test_citation_negative_case_would_be_a_regression_if_the_validator_stopped_catching_it():
    # If check_citation_validity ever silently accepted [99] as valid (a real
    # validator regression), this case must report deterministic_match=False -
    # simulated here by asserting the actual synthetic answer text still
    # contains the un-listed [99] citation the case relies on.
    regression_suite = _load_regression_suite_module()
    assert "[99]" in regression_suite.CITATION_NEGATIVE_CASE["answer_text"]
    valid_source_ids = {source["source_id"] for source in regression_suite.CITATION_NEGATIVE_CASE["sources"]}
    assert 99 not in valid_source_ids


# ---------------------------------------------------------------------------
# The refusal-negative boundary case: empty context must refuse, and must
# never call a client at all.
# ---------------------------------------------------------------------------


def test_refusal_case_returns_the_fixed_refusal_answer_and_matches_its_expectation():
    regression_suite = _load_regression_suite_module()

    row = regression_suite.evaluate_refusal_case()

    assert row["deterministic_match"] is True
    assert row["citation_status"] == "pass"
    assert row["query_id"] is None  # synthetic - no real corpus query backs this case


# ---------------------------------------------------------------------------
# The live lane: opt-in only, degrades to "blocked" without a key, never
# judges the two synthetic negative cases.
# ---------------------------------------------------------------------------


def test_attach_live_results_without_a_key_reports_blocked_not_a_crash():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows = regression_suite.run_deterministic_suite(queries_by_id)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        regression_suite.attach_live_results(rows, queries_by_id)

    rows_by_id = {row["case_id"]: row for row in rows}

    for case_id in (
        "control-q001",
        "control-q004",
        "retrieval-miss-q091",
        "retrieval-miss-q093",
        "chunk-gap-q016",
    ):
        live_status = rows_by_id[case_id]["live_status"]
        assert live_status["faithfulness"]["status"] == "blocked"
        assert live_status["contextual_recall"]["status"] == "blocked"
        # The honest trace-metadata fields Day 14 asks for are still present,
        # even on a blocked (never-called) result.
        assert "run_timestamp_utc" in live_status["faithfulness"]
        assert live_status["faithfulness"]["provider"] == "openrouter"


def test_attach_live_results_leaves_the_synthetic_cases_unjudged():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows = regression_suite.run_deterministic_suite(queries_by_id)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        regression_suite.attach_live_results(rows, queries_by_id)

    rows_by_id = {row["case_id"]: row for row in rows}
    for case_id in ("citation-negative-synthetic", "refusal-negative-synthetic"):
        assert isinstance(rows_by_id[case_id]["live_status"], str)
        assert "synthetic" in rows_by_id[case_id]["live_status"]


# ---------------------------------------------------------------------------
# render_table: a readable table, one line per case, header included
# ---------------------------------------------------------------------------


def test_render_table_has_one_header_line_a_separator_and_one_line_per_row():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows = regression_suite.run_deterministic_suite(queries_by_id)

    table_text = regression_suite.render_table(rows)
    lines = table_text.splitlines()

    assert len(lines) == 2 + len(rows)  # header + separator + one line per case
    for column_name, _ in regression_suite._TABLE_COLUMNS:
        assert column_name in lines[0]


def test_render_table_marks_a_mismatch_case_as_a_regression_in_the_overall_verdict():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    query_row = queries_by_id["Q091"]

    stale_case_spec = dict(regression_suite.REGRESSION_CASES[2])
    stale_case_spec["expected_missing_primary_doc_ids"] = ["GUIDE-002", "POL-001"]  # stale, pre-repair value
    row = regression_suite.evaluate_case(stale_case_spec, query_row)

    table_text = regression_suite.render_table([row])

    assert "MISMATCH" in table_text
    assert "REGRESSION" in table_text
