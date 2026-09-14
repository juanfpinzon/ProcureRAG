import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module(module_name):
    """Load a `src/<module_name>.py` script the same way the other test
    files do: the project keeps its learning modules as plain scripts rather
    than an installed package, so `src` is added to the import path only
    while the module loads.
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


def _load_eval_metrics_module():
    return _load_module("eval_metrics")


def _load_hybrid_search_module():
    return _load_module("hybrid_search")


def _load_preprocessing_module():
    return _load_module("preprocessing")


# ---------------------------------------------------------------------------
# precision_at_1
# ---------------------------------------------------------------------------


def test_precision_at_1_scores_a_relevant_top_result_as_one():
    eval_metrics = _load_eval_metrics_module()

    assert eval_metrics.precision_at_1(["DOC-A", "DOC-B"], {"DOC-A"}) == 1.0


def test_precision_at_1_scores_an_irrelevant_top_result_as_zero():
    eval_metrics = _load_eval_metrics_module()

    # DOC-A is relevant, but it isn't first - P@1 only ever looks at rank 1,
    # so this scores 0.0 even though the correct document did get retrieved.
    assert eval_metrics.precision_at_1(["DOC-B", "DOC-A"], {"DOC-A"}) == 0.0


def test_precision_at_1_handles_no_results_without_crashing():
    eval_metrics = _load_eval_metrics_module()

    assert eval_metrics.precision_at_1([], {"DOC-A"}) == 0.0


# ---------------------------------------------------------------------------
# recall_at_k
# ---------------------------------------------------------------------------


def test_recall_at_k_is_the_fraction_of_relevant_ids_found_in_the_top_k():
    eval_metrics = _load_eval_metrics_module()

    # 2 of the 3 known-relevant ids show up in the top 5 - DOC-C never does.
    retrieved = ["DOC-X", "DOC-A", "DOC-Y", "DOC-B", "DOC-Z", "DOC-C"]
    relevant = {"DOC-A", "DOC-B", "DOC-C"}

    assert eval_metrics.recall_at_k(retrieved, relevant, k=5) == pytest.approx(2 / 3)


def test_recall_at_k_returns_none_for_empty_relevant_ids():
    eval_metrics = _load_eval_metrics_module()

    # No ground truth to measure recall against - this must not report a
    # misleading 0.0, which would look identical to "every relevant document
    # was missed."
    assert eval_metrics.recall_at_k(["DOC-A"], set(), k=5) is None


# ---------------------------------------------------------------------------
# reciprocal_rank
# ---------------------------------------------------------------------------


def test_reciprocal_rank_rewards_an_earlier_relevant_result_more():
    eval_metrics = _load_eval_metrics_module()

    assert eval_metrics.reciprocal_rank(["DOC-A"], {"DOC-A"}) == pytest.approx(1.0)
    assert eval_metrics.reciprocal_rank(
        ["DOC-X", "DOC-A"], {"DOC-A"}
    ) == pytest.approx(0.5)
    assert eval_metrics.reciprocal_rank(
        ["DOC-X", "DOC-Y", "DOC-Y", "DOC-A"], {"DOC-A"}
    ) == pytest.approx(0.25)


def test_reciprocal_rank_is_zero_when_nothing_relevant_was_retrieved():
    eval_metrics = _load_eval_metrics_module()

    assert eval_metrics.reciprocal_rank(["DOC-X", "DOC-Y"], {"DOC-A"}) == 0.0


# ---------------------------------------------------------------------------
# rollup_chunks_to_documents
# ---------------------------------------------------------------------------


def test_rollup_chunks_to_documents_dedupes_and_keeps_best_rank_first():
    eval_metrics = _load_eval_metrics_module()

    # SOP-002 appears twice (chunk-1 then chunk-0) - only its first, better-
    # ranked appearance should count; the repeat contributes nothing further.
    chunk_results = [
        {"chunk_id": "SOP-002::chunk-1", "document_id": "SOP-002"},
        {"chunk_id": "FAQ-002::chunk-3", "document_id": "FAQ-002"},
        {"chunk_id": "SOP-002::chunk-0", "document_id": "SOP-002"},
    ]

    assert eval_metrics.rollup_chunks_to_documents(chunk_results) == [
        "SOP-002",
        "FAQ-002",
    ]


def test_rollup_chunks_to_documents_handles_no_chunks():
    eval_metrics = _load_eval_metrics_module()

    assert eval_metrics.rollup_chunks_to_documents([]) == []


# ---------------------------------------------------------------------------
# evaluate_method
# ---------------------------------------------------------------------------


def test_evaluate_method_averages_metrics_across_queries():
    eval_metrics = _load_eval_metrics_module()

    # A tiny synthetic query set with a hand-computed expected answer, so
    # this test does not depend on the real corpus or a model - it only
    # checks that evaluate_method wires precision_at_1/recall_at_k/
    # reciprocal_rank together and averages correctly.
    queries = [
        {"query": "q1", "expected_relevant_ids": {"DOC-A"}},
        {"query": "q2", "expected_relevant_ids": {"DOC-B"}},
    ]

    # A fake retriever: perfect on q1 (relevant doc first), wrong on q2
    # (relevant doc is never returned at all).
    def fake_retrieve(query_row):
        if query_row["query"] == "q1":
            return ["DOC-A", "DOC-X"]
        return ["DOC-X", "DOC-Y"]

    result = eval_metrics.evaluate_method(fake_retrieve, queries, k_for_recall=5)

    assert result["n_queries"] == 2
    # P@1: 1.0 for q1, 0.0 for q2 -> average 0.5.
    assert result["p_at_1"] == pytest.approx(0.5)
    # R@5: 1.0 for q1 (DOC-A found), 0.0 for q2 (DOC-B never found) -> 0.5.
    assert result["r_at_5"] == pytest.approx(0.5)
    # MRR: 1.0 for q1 (rank 1), 0.0 for q2 (not found) -> average 0.5.
    assert result["mrr"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Day 9: discounted_cumulative_gain
# ---------------------------------------------------------------------------


def test_discounted_cumulative_gain_of_empty_gains_is_zero():
    eval_metrics = _load_eval_metrics_module()

    assert eval_metrics.discounted_cumulative_gain([]) == 0.0


def test_discounted_cumulative_gain_does_not_discount_rank_one():
    eval_metrics = _load_eval_metrics_module()

    # log2(1 + 1) == 1.0, so whatever is ranked first counts in full -
    # this is the "rank 1 isn't discounted at all" property the plain-
    # English explanation of nDCG leans on.
    assert eval_metrics.discounted_cumulative_gain([2]) == pytest.approx(2.0)


def test_discounted_cumulative_gain_discounts_lower_ranks_hand_computed():
    eval_metrics = _load_eval_metrics_module()

    # gain 2 at rank 1 (discount log2(2)=1) + gain 1 at rank 2 (discount
    # log2(3)~=1.58496) = 2.0 + 1/1.58496 ~= 2.63093.
    assert eval_metrics.discounted_cumulative_gain([2, 1]) == pytest.approx(
        2.6309297535714578
    )


# ---------------------------------------------------------------------------
# Day 9: ndcg_at_k
# ---------------------------------------------------------------------------


def test_ndcg_at_k_is_one_for_the_ideal_ranking():
    eval_metrics = _load_eval_metrics_module()

    # DOC-A (primary, grade 2) ranked above DOC-B (secondary, grade 1) is
    # exactly the ideal order for this query - actual DCG == ideal DCG.
    grades = {"DOC-A": 2, "DOC-B": 1}
    assert eval_metrics.ndcg_at_k(["DOC-A", "DOC-B"], grades, k=5) == pytest.approx(1.0)


def test_ndcg_at_k_penalizes_ranking_the_secondary_document_first():
    eval_metrics = _load_eval_metrics_module()

    # Same two documents, reversed order: the secondary (grade 1) document
    # is ranked first and the primary (grade 2) document second. Hand
    # computed: dcg = 1/log2(2) + 2/log2(3) ~= 2.26186; idcg (unchanged,
    # same grades) ~= 2.63093; ndcg = 2.26186 / 2.63093 ~= 0.85972.
    grades = {"DOC-A": 2, "DOC-B": 1}
    assert eval_metrics.ndcg_at_k(["DOC-B", "DOC-A"], grades, k=5) == pytest.approx(
        0.8597186998521972
    )


def test_ndcg_at_k_scores_an_unjudged_id_as_zero_gain():
    eval_metrics = _load_eval_metrics_module()

    # DOC-X is retrieved but was never judged relevant for this query at
    # all (not a key in `grades`) - it must contribute gain 0, the same as
    # any other non-relevant document, not raise a KeyError.
    grades = {"DOC-A": 2, "DOC-B": 1}
    retrieved = ["DOC-A", "DOC-X", "DOC-B"]
    # Hand computed at k=3: dcg = 2/log2(2) + 0/log2(3) + 1/log2(4) = 2.0 +
    # 0 + 0.5 = 2.5; idcg@3 (only 2 graded documents exist, so the ideal
    # list is just [2, 1]) = 2.63093; ndcg = 2.5 / 2.63093 ~= 0.95023.
    assert eval_metrics.ndcg_at_k(retrieved, grades, k=3) == pytest.approx(
        0.9502344167898356
    )


def test_ndcg_at_k_ties_do_not_matter_for_the_ideal_ranking():
    eval_metrics = _load_eval_metrics_module()

    # Three equally-secondary (grade 1) documents - any order among them is
    # equally "ideal", so a real ranking that retrieves all three (in any
    # order) within k should still score a perfect 1.0.
    grades = {"DOC-A": 1, "DOC-B": 1, "DOC-C": 1}
    assert eval_metrics.ndcg_at_k(["DOC-C", "DOC-A", "DOC-B"], grades, k=3) == pytest.approx(
        1.0
    )


def test_ndcg_at_k_is_zero_for_an_empty_retrieved_list():
    eval_metrics = _load_eval_metrics_module()

    # Nothing was retrieved at all, but there IS a real ideal ranking to
    # compare against (grades is non-empty) - dcg is 0, idcg isn't, so
    # ndcg is 0.0, not undefined.
    grades = {"DOC-A": 2}
    assert eval_metrics.ndcg_at_k([], grades, k=5) == 0.0


def test_ndcg_at_k_is_zero_when_the_query_has_no_relevant_grades_at_all():
    eval_metrics = _load_eval_metrics_module()

    # No graded document exists for this query - there is no ideal ranking
    # to normalize against (idcg == 0), so this must return 0.0 rather than
    # dividing by zero.
    assert eval_metrics.ndcg_at_k(["DOC-A", "DOC-B"], {}, k=5) == 0.0


# ---------------------------------------------------------------------------
# Day 9: grades_for_query / evaluate_ndcg
# ---------------------------------------------------------------------------


def test_grades_for_query_returns_the_relevance_grades_field():
    eval_metrics = _load_eval_metrics_module()

    query_row = {"query": "q1", "relevance_grades": {"DOC-A": 2, "DOC-B": 1}}
    assert eval_metrics.grades_for_query(query_row) == {"DOC-A": 2, "DOC-B": 1}


def test_evaluate_ndcg_averages_ndcg_across_queries():
    eval_metrics = _load_eval_metrics_module()

    # q1: perfect ranking (ndcg 1.0). q2: reversed ranking (ndcg ~0.85972,
    # same hand-computed case as test_ndcg_at_k_penalizes... above).
    queries = [
        {"query": "q1", "relevance_grades": {"DOC-A": 2, "DOC-B": 1}},
        {"query": "q2", "relevance_grades": {"DOC-A": 2, "DOC-B": 1}},
    ]

    def fake_retrieve(query_row):
        if query_row["query"] == "q1":
            return ["DOC-A", "DOC-B"]
        return ["DOC-B", "DOC-A"]

    average_ndcg = eval_metrics.evaluate_ndcg(fake_retrieve, queries, k=5)
    assert average_ndcg == pytest.approx((1.0 + 0.8597186998521972) / 2)


def test_evaluate_ndcg_of_no_queries_is_zero():
    eval_metrics = _load_eval_metrics_module()

    assert eval_metrics.evaluate_ndcg(lambda query_row: [], [], k=5) == 0.0


# ---------------------------------------------------------------------------
# Day 9: filter_adjusted_relevant_ids / filter_adjusted_grades (synthetic)
# ---------------------------------------------------------------------------


def test_filter_adjusted_relevant_ids_drops_expected_ids_that_fail_the_filter():
    eval_metrics = _load_eval_metrics_module()

    documents_by_id = {
        "POL-001": {"doc_type": "policy"},
        "FAQ-001": {"doc_type": "faq"},
    }
    query_row = {
        "expected_relevant_ids": ["POL-001", "FAQ-001"],
        "metadata_filters": {"doc_type": "policy"},
    }

    # FAQ-001 is not a policy, so the query's own filter would exclude it -
    # it must not survive into the filter-adjusted gold set.
    assert eval_metrics.filter_adjusted_relevant_ids(query_row, documents_by_id) == [
        "POL-001"
    ]


def test_filter_adjusted_relevant_ids_with_no_filter_returns_every_expected_id():
    eval_metrics = _load_eval_metrics_module()

    documents_by_id = {"POL-001": {"doc_type": "policy"}, "FAQ-001": {"doc_type": "faq"}}
    query_row = {
        "expected_relevant_ids": ["POL-001", "FAQ-001"],
        "metadata_filters": {},
    }

    assert eval_metrics.filter_adjusted_relevant_ids(query_row, documents_by_id) == [
        "POL-001",
        "FAQ-001",
    ]


def test_filter_adjusted_grades_drops_the_same_ids_from_relevance_grades():
    eval_metrics = _load_eval_metrics_module()

    documents_by_id = {
        "POL-001": {"doc_type": "policy"},
        "FAQ-001": {"doc_type": "faq"},
    }
    query_row = {
        "relevance_grades": {"POL-001": 2, "FAQ-001": 1},
        "metadata_filters": {"doc_type": "policy"},
    }

    assert eval_metrics.filter_adjusted_grades(query_row, documents_by_id) == {
        "POL-001": 2
    }


# ---------------------------------------------------------------------------
# Day 9: filter_adjusted_relevant_ids against the real v1 corpus (Q001,
# Q007, Q019) - these three are the exact queries the Day 9 design doc
# names as evidence that excluded secondary documents are not counted
# against filtered recall.
# ---------------------------------------------------------------------------


def _real_documents_by_id():
    hybrid_search = _load_hybrid_search_module()
    preprocessing = _load_preprocessing_module()
    return hybrid_search.build_metadata_index(preprocessing.load_data())


def _real_query(query_id):
    hybrid_search = _load_hybrid_search_module()
    queries_by_id = {q["query_id"]: q for q in hybrid_search.load_example_queries()}
    return queries_by_id[query_id]


def test_filter_adjusted_relevant_ids_on_q001_drops_the_faq_secondary_answer():
    eval_metrics = _load_eval_metrics_module()

    # Q001: "What approval is required for a EUR 60,000 purchase order?"
    # filter={"doc_type": "policy"}; expected_relevant_ids=[POL-001 (primary,
    # a policy), FAQ-001 (secondary, a FAQ)]. FAQ-001 fails the filter.
    query_row = _real_query("Q001")
    assert query_row["metadata_filters"] == {"doc_type": "policy"}
    assert query_row["expected_relevant_ids"] == ["POL-001", "FAQ-001"]

    adjusted = eval_metrics.filter_adjusted_relevant_ids(query_row, _real_documents_by_id())
    assert adjusted == ["POL-001"]


def test_filter_adjusted_relevant_ids_on_q007_keeps_a_second_policy_document():
    eval_metrics = _load_eval_metrics_module()

    # Q007: "What checks are needed before onboarding a new high-risk
    # supplier?" filter={"doc_type": "policy"};
    # expected_relevant_ids=[POL-002 (primary), FAQ-002 (secondary, a FAQ -
    # excluded), POL-005 (secondary, but ALSO a policy - must survive)].
    # This is the case that shows filter-adjustment isn't just "keep the
    # primary, drop everything else" - a secondary document can survive
    # too, if it happens to also match the filter.
    query_row = _real_query("Q007")
    assert query_row["metadata_filters"] == {"doc_type": "policy"}
    assert query_row["expected_relevant_ids"] == ["POL-002", "FAQ-002", "POL-005"]

    adjusted = eval_metrics.filter_adjusted_relevant_ids(query_row, _real_documents_by_id())
    assert adjusted == ["POL-002", "POL-005"]


def test_filter_adjusted_relevant_ids_on_q019_drops_the_audit_report_secondary_answer():
    eval_metrics = _load_eval_metrics_module()

    # Q019: "What is the gift and hospitality declaration threshold?"
    # filter={"category": "compliance"}; expected_relevant_ids=[POL-005
    # (primary, category=compliance), AUDIT-001 (secondary, category=
    # procurement-operations - excluded)].
    query_row = _real_query("Q019")
    assert query_row["metadata_filters"] == {"category": "compliance"}
    assert query_row["expected_relevant_ids"] == ["POL-005", "AUDIT-001"]

    adjusted = eval_metrics.filter_adjusted_relevant_ids(query_row, _real_documents_by_id())
    assert adjusted == ["POL-005"]


# ---------------------------------------------------------------------------
# Day 9: build_filtered_queries
# ---------------------------------------------------------------------------


def test_build_filtered_queries_only_keeps_queries_with_a_metadata_filter():
    eval_metrics = _load_eval_metrics_module()
    hybrid_search = _load_hybrid_search_module()

    all_queries = hybrid_search.load_example_queries()
    filtered = eval_metrics.build_filtered_queries(all_queries, _real_documents_by_id())

    # 21 of the 93 v1 queries carry a metadata_filters value - see
    # docs/eval-report.md / docs/day-09-evaluation-harness-graded-filtered.md.
    assert len(filtered) == 21
    assert all(query_row["metadata_filters"] for query_row in filtered)


def test_build_filtered_queries_adjusts_q001s_gold_fields_in_place():
    eval_metrics = _load_eval_metrics_module()
    hybrid_search = _load_hybrid_search_module()

    all_queries = hybrid_search.load_example_queries()
    filtered = eval_metrics.build_filtered_queries(all_queries, _real_documents_by_id())
    q001_adjusted = next(q for q in filtered if q["query_id"] == "Q001")

    # FAQ-001 is gone from both the id list and the grades dict - the
    # exact adjustment filter_adjusted_relevant_ids/filter_adjusted_grades
    # make on their own, now visible end-to-end on the query row a
    # filtered evaluate_method call would actually receive.
    assert q001_adjusted["expected_relevant_ids"] == ["POL-001"]
    assert q001_adjusted["relevance_grades"] == {"POL-001": 2}


# ---------------------------------------------------------------------------
# Day 9: slice_queries / evaluate_slices / primary_count
# ---------------------------------------------------------------------------


def test_slice_queries_groups_by_key_fn_preserving_order():
    eval_metrics = _load_eval_metrics_module()

    queries = [
        {"query_id": "Q1", "query_type": "lookup"},
        {"query_id": "Q2", "query_type": "numeric"},
        {"query_id": "Q3", "query_type": "lookup"},
    ]

    slices = eval_metrics.slice_queries(queries, lambda q: q["query_type"])

    assert set(slices.keys()) == {"lookup", "numeric"}
    assert [q["query_id"] for q in slices["lookup"]] == ["Q1", "Q3"]
    assert [q["query_id"] for q in slices["numeric"]] == ["Q2"]


def test_evaluate_slices_scores_each_slice_independently():
    eval_metrics = _load_eval_metrics_module()

    # "lookup" query is answered correctly (relevant doc first); "numeric"
    # query is not (relevant doc never retrieved) - each slice's own P@1
    # must reflect only its own query, not an average across both.
    queries = [
        {"query": "q1", "query_type": "lookup", "expected_relevant_ids": {"DOC-A"}},
        {"query": "q2", "query_type": "numeric", "expected_relevant_ids": {"DOC-B"}},
    ]

    def fake_retrieve(query_row):
        if query_row["query_type"] == "lookup":
            return ["DOC-A"]
        return ["DOC-X"]

    slice_results = eval_metrics.evaluate_slices(
        fake_retrieve, queries, lambda q: q["query_type"]
    )

    assert slice_results["lookup"]["p_at_1"] == pytest.approx(1.0)
    assert slice_results["numeric"]["p_at_1"] == pytest.approx(0.0)
    assert slice_results["lookup"]["n_queries"] == 1
    assert slice_results["numeric"]["n_queries"] == 1


def test_primary_count_counts_only_grade_two_documents():
    eval_metrics = _load_eval_metrics_module()

    single_primary = {"relevance_grades": {"DOC-A": 2, "DOC-B": 1}}
    multi_primary = {"relevance_grades": {"DOC-A": 2, "DOC-B": 2, "DOC-C": 1}}

    assert eval_metrics.primary_count(single_primary) == 1
    assert eval_metrics.primary_count(multi_primary) == 2
