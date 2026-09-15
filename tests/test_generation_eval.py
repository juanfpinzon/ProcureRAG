import importlib.util
import sys
from pathlib import Path


def _load_module(module_name):
    """Load a `src/<module_name>.py` script the same way every other test
    file does (see `tests/test_generation.py`, `tests/test_reranking.py`):
    the project keeps its learning modules as plain scripts rather than an
    installed package, so `src` is added to the import path only while the
    module loads. `sys.path` still has `src` on it while `exec_module` runs
    `generation_eval.py`'s own top-level imports (`from generation import
    ...`, `from hybrid_search import ...`, `from eval_metrics import ...`),
    which is what lets those resolve correctly.
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


def _load_generation_eval_module():
    return _load_module("generation_eval")


def _real_query(module, query_id):
    """Pull one real row out of `data/corpus_v1/example_queries.jsonl`, the
    same `_real_query` pattern `tests/test_eval_metrics.py` already uses -
    Day 11's checks are meant to run against this project's actual query
    set, not a hand-typed stand-in, so the end-to-end tests below load it
    for real rather than re-typing `relevance_grades` by hand and risking
    it drifting out of sync with the corpus.
    """
    queries_by_id = {row["query_id"]: row for row in module.load_example_queries()}
    return queries_by_id[query_id]


def _query_row(query_id="Q000", relevance_grades=None):
    """A minimal synthetic query row - only the two fields any check here
    actually reads (`query_id` for the finding, `relevance_grades` for
    `primary_expected_doc_ids`). Used by the unit tests below that check
    one function's logic in isolation; the real Q001/Q091 fixtures are
    exercised separately, end-to-end, further down this file.
    """
    return {"query_id": query_id, "relevance_grades": relevance_grades or {}}


# ---------------------------------------------------------------------------
# primary_expected_doc_ids / context_doc_ids: the two small shared helpers
# ---------------------------------------------------------------------------


def test_primary_expected_doc_ids_keeps_only_grade_2_ids():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row(relevance_grades={"POL-001": 2, "FAQ-001": 1, "GUIDE-002": 2})

    assert generation_eval.primary_expected_doc_ids(query_row) == {"POL-001", "GUIDE-002"}


def test_context_doc_ids_collects_every_retrieved_doc_id():
    generation_eval = _load_generation_eval_module()
    sources = [
        generation_eval._source(1, "POL-001", "Title A", "text a"),
        generation_eval._source(2, "FAQ-001", "Title B", "text b"),
        generation_eval._source(3, "FAQ-001", "Title B", "text b again"),
    ]

    # FAQ-001 appears twice (two chunks, one document) - context_doc_ids
    # de-duplicates to the document level, since "was this document in
    # context at all" is the question check_context_recall asks.
    assert generation_eval.context_doc_ids(sources) == {"POL-001", "FAQ-001"}


# ---------------------------------------------------------------------------
# check_citation_validity: unchanged citation contract, re-shaped as a finding
# ---------------------------------------------------------------------------


def test_check_citation_validity_passes_with_no_orphans():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q001")
    citations = {"cited_ids": [1], "valid_ids": [1], "orphan_ids": [], "uncited_ids": []}

    finding = generation_eval.check_citation_validity(query_row, citations, cited_doc_ids=["POL-001"])

    assert finding["passed"] is True
    assert finding["severity"] == "info"
    assert finding["query_id"] == "Q001"
    assert finding["check"] == "citation_validity"
    assert finding["cited_doc_ids"] == ["POL-001"]


def test_check_citation_validity_fails_on_a_hallucinated_citation():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q999")
    citations = {"cited_ids": [1, 9], "valid_ids": [1], "orphan_ids": [9], "uncited_ids": []}

    finding = generation_eval.check_citation_validity(query_row, citations, cited_doc_ids=["A"])

    assert finding["passed"] is False
    assert finding["severity"] == "fail"
    assert finding["actual"]["orphan_ids"] == [9]


# ---------------------------------------------------------------------------
# check_context_recall: the check that catches a retrieval-side evidence gap
# ---------------------------------------------------------------------------


def test_check_context_recall_passes_when_every_primary_doc_was_retrieved():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q001", relevance_grades={"POL-001": 2, "FAQ-001": 1})
    sources = [
        generation_eval._source(1, "FAQ-001", "FAQ", "text"),
        generation_eval._source(2, "POL-001", "Policy", "text"),
    ]

    finding = generation_eval.check_context_recall(query_row, sources, cited_doc_ids=[])

    assert finding["passed"] is True
    assert finding["expected"] == ["POL-001"]
    assert finding["actual"] == ["FAQ-001", "POL-001"]


def test_check_context_recall_fails_when_a_primary_doc_was_never_retrieved():
    # The exact Q091 shape: two of the three primary documents (POL-001,
    # GUIDE-002) are simply absent from what was retrieved.
    generation_eval = _load_generation_eval_module()
    query_row = _query_row(
        "Q091", relevance_grades={"GUIDE-002": 2, "POL-001": 2, "POL-003": 2, "SOP-004": 1}
    )
    sources = [
        generation_eval._source(1, "SOP-001", "SOP", "text"),
        generation_eval._source(2, "POL-003", "Security Policy", "text"),
    ]

    finding = generation_eval.check_context_recall(query_row, sources, cited_doc_ids=[])

    assert finding["passed"] is False
    missing = sorted(set(finding["expected"]) - set(finding["actual"]))
    assert missing == ["GUIDE-002", "POL-001"]


def test_check_context_recall_passes_vacuously_with_no_primary_documents():
    # A query with only grade-1 (secondary) documents has nothing this
    # check can enforce - documented as a real limitation, not hidden.
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q500", relevance_grades={"FAQ-001": 1})

    finding = generation_eval.check_context_recall(query_row, sources=[], cited_doc_ids=[])

    assert finding["passed"] is True
    assert finding["expected"] == []


# ---------------------------------------------------------------------------
# check_expected_terms: curated-query completeness
# ---------------------------------------------------------------------------


def test_check_expected_terms_passes_when_every_term_is_present():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q001")
    answer_text = "This needs VP Procurement approval and a documented Finance review."

    finding = generation_eval.check_expected_terms(
        query_row, answer_text, required_terms=("VP Procurement", "Finance review"), cited_doc_ids=[]
    )

    assert finding["passed"] is True
    assert finding["actual"] == ["VP Procurement", "Finance review"]


def test_check_expected_terms_fails_and_names_the_missing_terms():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q091")
    answer_text = "A commitment of this significance requires VP Procurement approval."

    finding = generation_eval.check_expected_terms(
        query_row, answer_text, required_terms=("Band 3", "usage data"), cited_doc_ids=[]
    )

    assert finding["passed"] is False
    assert finding["message"] == "answer text is missing required term(s)/fact(s): ['Band 3', 'usage data']"


def test_check_expected_terms_matching_is_case_insensitive():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q001")

    finding = generation_eval.check_expected_terms(
        query_row, "vp procurement sign-off is required.", required_terms=("VP Procurement",), cited_doc_ids=[]
    )

    assert finding["passed"] is True


# ---------------------------------------------------------------------------
# check_unsupported_inference: the hand-curated hedge-phrase proxy
# ---------------------------------------------------------------------------


def test_check_unsupported_inference_passes_on_plain_sourced_text():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q001")
    answer_text = "A €60,000 purchase needs VP Procurement approval with a Finance review [1]."

    finding = generation_eval.check_unsupported_inference(query_row, answer_text, cited_doc_ids=["FAQ-001"])

    assert finding["passed"] is True
    assert finding["severity"] == "info"


def test_check_unsupported_inference_flags_a_hedge_phrase():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q091")
    # The real Day 10 Q091 sentence this check exists to catch.
    answer_text = (
        "a €120,000 commitment is of equal or greater significance, so this approval "
        "level applies at minimum."
    )

    finding = generation_eval.check_unsupported_inference(query_row, answer_text, cited_doc_ids=["FAQ-001"])

    # A flag is a WARN, not a FAIL - it names a pattern worth a human/judge
    # look, it does not itself prove the claim is wrong.
    assert finding["passed"] is False
    assert finding["severity"] == "warn"
    assert "equal or greater" in finding["actual"]
    assert "at minimum" in finding["actual"]


# ---------------------------------------------------------------------------
# evaluate_generated_answer: wiring all four checks together for one answer
# ---------------------------------------------------------------------------


def test_evaluate_generated_answer_skips_expected_terms_when_none_supplied():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q001", relevance_grades={"POL-001": 2})
    sources = [generation_eval._source(1, "POL-001", "Policy", "Band 3 needs VP approval.")]

    findings = generation_eval.evaluate_generated_answer(
        query_row, sources, "VP approval is required [1].", required_terms=None
    )

    checks_run = {finding["check"] for finding in findings}
    assert checks_run == {"citation_validity", "context_recall", "unsupported_inference"}
    assert "expected_terms" not in checks_run


def test_evaluate_generated_answer_computes_cited_doc_ids_once_for_every_finding():
    generation_eval = _load_generation_eval_module()
    query_row = _query_row("Q001", relevance_grades={"POL-001": 2, "FAQ-001": 1})
    sources = [
        generation_eval._source(1, "POL-001", "Policy", "Band 3 needs VP approval."),
        generation_eval._source(2, "FAQ-001", "FAQ", "Approvals are cumulative."),
    ]

    findings = generation_eval.evaluate_generated_answer(
        query_row, sources, "VP approval is required [1], and [1] again.", required_terms=None
    )

    # Only source 1 (POL-001) was actually cited - every finding should
    # carry that same, correctly de-duplicated doc id list.
    assert all(finding["cited_doc_ids"] == ["POL-001"] for finding in findings)


# ---------------------------------------------------------------------------
# End-to-end: the real, already-committed Q001 (pass) / Q091 (fail) fixtures
# ---------------------------------------------------------------------------


def test_curated_q001_fixture_passes_every_check():
    """The passing control: Q001's real Day 10 transcript, run through
    every Day 11 check against Q001's real `relevance_grades`."""
    generation_eval = _load_generation_eval_module()
    query_row = _real_query(generation_eval, "Q001")
    fixture = next(f for f in generation_eval.CURATED_FIXTURES if f["query_id"] == "Q001")

    findings = generation_eval.evaluate_generated_answer(
        query_row, fixture["sources"], fixture["answer_text"], required_terms=fixture["required_terms"]
    )

    assert {finding["check"] for finding in findings} == {
        "citation_validity",
        "context_recall",
        "unsupported_inference",
        "expected_terms",
    }
    assert all(finding["passed"] for finding in findings), findings


def test_curated_q091_fixture_is_caught_automatically_not_just_by_reading_it():
    """The non-negotiable Day 11 output (see the design doc's "Stop
    condition"): Q091's real, already-known-incomplete Day 10 transcript
    must fail here, in code, against Q091's real `relevance_grades` -
    without any human re-reading the prose to notice something felt off.
    """
    generation_eval = _load_generation_eval_module()
    query_row = _real_query(generation_eval, "Q091")
    fixture = next(f for f in generation_eval.CURATED_FIXTURES if f["query_id"] == "Q091")

    findings = generation_eval.evaluate_generated_answer(
        query_row, fixture["sources"], fixture["answer_text"], required_terms=fixture["required_terms"]
    )
    findings_by_check = {finding["check"]: finding for finding in findings}

    # Day 10's actual, already-documented result: citation hygiene is
    # clean - zero orphan citations.
    assert findings_by_check["citation_validity"]["passed"] is True

    # But the real gap: POL-001 and GUIDE-002 (both grade-2/primary) never
    # reached the retrieved context, so no answer built from these sources
    # could be complete - this is caught automatically here.
    context_recall = findings_by_check["context_recall"]
    assert context_recall["passed"] is False
    missing = sorted(set(context_recall["expected"]) - set(context_recall["actual"]))
    assert missing == ["GUIDE-002", "POL-001"]

    # The downstream consequence: the answer text itself never states the
    # real approval band or the renewal usage-data evidence.
    expected_terms = findings_by_check["expected_terms"]
    assert expected_terms["passed"] is False
    assert expected_terms["actual"] == []

    # And the model's own language shows the extrapolation this produced -
    # flagged, not silently passed.
    inference = findings_by_check["unsupported_inference"]
    assert inference["passed"] is False
    assert inference["severity"] == "warn"
