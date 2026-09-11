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
