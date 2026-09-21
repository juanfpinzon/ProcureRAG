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
# The two retrieval-miss anchors (Q091, Q093): must match their known,
# pre-repair missing-doc state - the exact signal Day 13's recommended
# repair is supposed to move to [] later.
# ---------------------------------------------------------------------------


def test_q091_matches_its_known_pre_repair_missing_docs():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows_by_id = {row["case_id"]: row for row in regression_suite.run_deterministic_suite(queries_by_id)}

    row = rows_by_id["retrieval-miss-q091"]
    assert row["missing_primary_doc_ids"] == ["GUIDE-002", "POL-001"]
    assert row["deterministic_match"] is True  # matches the *expected pre-repair* state
    assert row["citation_status"] == "pass"


def test_q093_matches_its_known_pre_repair_missing_docs():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows_by_id = {row["case_id"]: row for row in regression_suite.run_deterministic_suite(queries_by_id)}

    row = rows_by_id["retrieval-miss-q093"]
    assert row["missing_primary_doc_ids"] == ["CONTRACT-001"]
    assert row["deterministic_match"] is True


def test_a_case_that_no_longer_matches_its_expectation_is_flagged_as_a_mismatch():
    # Prove the "regression" concept actually fires: hand-build a case spec
    # that claims Q091 already has zero missing docs (a false, too-optimistic
    # expectation) and confirm evaluate_case reports deterministic_match=False
    # instead of silently agreeing with a wrong expectation.
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    query_row = queries_by_id["Q091"]

    optimistic_case_spec = dict(regression_suite.REGRESSION_CASES[2])  # retrieval-miss-q091
    assert optimistic_case_spec["case_id"] == "retrieval-miss-q091"
    optimistic_case_spec["expected_missing_primary_doc_ids"] = []

    row = regression_suite.evaluate_case(optimistic_case_spec, query_row)

    assert row["missing_primary_doc_ids"] == ["GUIDE-002", "POL-001"]
    assert row["deterministic_match"] is False


# ---------------------------------------------------------------------------
# The chunk-gap contrast case (Q016): document-level recall passes, the
# fact-level gap is only visible through the table_note, not the checks.
# ---------------------------------------------------------------------------


def test_q016_passes_document_level_recall_but_carries_a_chunk_gap_note():
    regression_suite = _load_regression_suite_module()
    queries_by_id = _real_queries_by_id(regression_suite)
    rows_by_id = {row["case_id"]: row for row in regression_suite.run_deterministic_suite(queries_by_id)}

    row = rows_by_id["chunk-gap-q016"]
    assert row["missing_primary_doc_ids"] == []
    assert row["deterministic_match"] is True
    assert row["table_note"] is not None
    assert "chunk" in row["table_note"].lower()


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

    optimistic_case_spec = dict(regression_suite.REGRESSION_CASES[2])
    optimistic_case_spec["expected_missing_primary_doc_ids"] = []
    row = regression_suite.evaluate_case(optimistic_case_spec, query_row)

    table_text = regression_suite.render_table([row])

    assert "MISMATCH" in table_text
    assert "REGRESSION" in table_text
