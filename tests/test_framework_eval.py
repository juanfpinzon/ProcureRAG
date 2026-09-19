import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module(module_name):
    """Load a `src/<module_name>.py` script the same way every other test
    file in this project does (see `tests/test_generation_eval.py`,
    `tests/test_generation.py`): `src` is only on `sys.path` while the
    module's own top-level imports (`from generation import
    OPENROUTER_BASE_URL`, for `framework_eval.py`) resolve.
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


def _load_framework_eval_module():
    return _load_module("framework_eval")


def _load_generation_eval_module():
    return _load_module("generation_eval")


def _real_query(module, query_id):
    """The same `_real_query` pattern `tests/test_generation_eval.py` uses:
    pull a real row out of `data/corpus_v1/example_queries.jsonl` rather
    than hand-typing `query`/`expected_answer` and risking it drifting out
    of sync with the real corpus.
    """
    queries_by_id = {row["query_id"]: row for row in module.load_example_queries()}
    return queries_by_id[query_id]


def _case(
    query_id="Q000",
    input="What color is the sky?",
    actual_output="The sky is blue.",
    expected_output="",
    retrieval_context=None,
):
    """A minimal, hand-built neutral eval case - used by the adapter-shape
    tests below, which only care about field renaming/reshaping and don't
    need a real ProcureRAG query row or real sources to prove that.
    """
    return {
        "query_id": query_id,
        "input": input,
        "actual_output": actual_output,
        "expected_output": expected_output,
        "retrieval_context": retrieval_context or ["The sky appears blue during the day due to Rayleigh scattering."],
        "source_metadata": [],
        "deterministic_findings": [],
    }


# ---------------------------------------------------------------------------
# build_framework_eval_case: the neutral case, built from real Q001/Q091 data
# ---------------------------------------------------------------------------


def test_build_framework_eval_case_maps_q001_fields_from_the_real_fixture():
    framework_eval = _load_framework_eval_module()
    generation_eval = _load_generation_eval_module()
    query_row = _real_query(generation_eval, "Q001")
    fixture = next(f for f in generation_eval.CURATED_FIXTURES if f["query_id"] == "Q001")

    case = framework_eval.build_framework_eval_case(query_row, fixture["sources"], fixture["answer_text"])

    assert case["query_id"] == "Q001"
    assert case["input"] == query_row["query"]
    assert case["actual_output"] == fixture["answer_text"]
    assert case["expected_output"] == query_row["expected_answer"]
    assert case["deterministic_findings"] == []


def test_build_framework_eval_case_preserves_source_order_for_q091():
    # Q091's real fixture has 5 sources across SOP-001, FAQ-001, FAQ-001,
    # POL-003, SOP-001, in that exact order - not sorted, not de-duplicated.
    # A faithfulness judge reads the prompt's "[1]...[5]" list in this order,
    # so the eval case has to preserve it exactly, the same way
    # `generation.build_sources` does for the real prompt.
    framework_eval = _load_framework_eval_module()
    generation_eval = _load_generation_eval_module()
    query_row = _real_query(generation_eval, "Q091")
    fixture = next(f for f in generation_eval.CURATED_FIXTURES if f["query_id"] == "Q091")

    case = framework_eval.build_framework_eval_case(query_row, fixture["sources"], fixture["answer_text"])

    expected_doc_id_order = [source["doc_id"] for source in fixture["sources"]]
    assert [entry["doc_id"] for entry in case["source_metadata"]] == expected_doc_id_order
    expected_text_order = [source["text"] for source in fixture["sources"]]
    assert case["retrieval_context"] == expected_text_order


def test_build_framework_eval_case_source_metadata_carries_the_id_fields():
    framework_eval = _load_framework_eval_module()
    generation_eval = _load_generation_eval_module()
    query_row = _real_query(generation_eval, "Q001")
    fixture = next(f for f in generation_eval.CURATED_FIXTURES if f["query_id"] == "Q001")

    case = framework_eval.build_framework_eval_case(query_row, fixture["sources"], fixture["answer_text"])

    first_entry = case["source_metadata"][0]
    assert set(first_entry.keys()) == {"source_id", "doc_id", "chunk_id", "rank"}
    assert first_entry["source_id"] == 1
    assert first_entry["doc_id"] == "FAQ-001"


def test_build_framework_eval_case_defaults_deterministic_findings_to_empty_list():
    framework_eval = _load_framework_eval_module()
    generation_eval = _load_generation_eval_module()
    query_row = _real_query(generation_eval, "Q001")
    fixture = next(f for f in generation_eval.CURATED_FIXTURES if f["query_id"] == "Q001")

    case = framework_eval.build_framework_eval_case(query_row, fixture["sources"], fixture["answer_text"])

    assert case["deterministic_findings"] == []


def test_build_framework_eval_case_carries_deterministic_findings_through_unchanged():
    # Day 11's real output shape: a list of finding dicts from
    # `evaluate_generated_answer`. This function must not recompute or
    # reshape them - only pass them through, so the Day 11 deterministic
    # verdict and the Day 12 judge verdict can be printed side by side for
    # the exact same case.
    framework_eval = _load_framework_eval_module()
    generation_eval = _load_generation_eval_module()
    query_row = _real_query(generation_eval, "Q091")
    fixture = next(f for f in generation_eval.CURATED_FIXTURES if f["query_id"] == "Q091")
    findings = generation_eval.evaluate_generated_answer(
        query_row, fixture["sources"], fixture["answer_text"], required_terms=fixture["required_terms"]
    )

    case = framework_eval.build_framework_eval_case(
        query_row, fixture["sources"], fixture["answer_text"], deterministic_findings=findings
    )

    assert case["deterministic_findings"] is findings


# ---------------------------------------------------------------------------
# to_deepeval_test_case / to_ragas_sample: same neutral case, two vocabularies
# ---------------------------------------------------------------------------


def test_to_deepeval_test_case_maps_neutral_fields_by_name():
    framework_eval = _load_framework_eval_module()
    case = _case(input="What color is the sky?", actual_output="The sky is blue.", expected_output="Blue.")

    test_case = framework_eval.to_deepeval_test_case(case)

    assert test_case.input == "What color is the sky?"
    assert test_case.actual_output == "The sky is blue."
    assert test_case.expected_output == "Blue."
    assert test_case.retrieval_context == case["retrieval_context"]


def test_to_ragas_sample_maps_the_same_fields_under_ragas_vocabulary():
    # Same neutral case as the DeepEval test above - proves the two
    # frameworks really do want the same underlying information, just under
    # different field names (input/actual_output/retrieval_context vs.
    # user_input/response/retrieved_contexts), matching the design doc's
    # "input contracts matter" point.
    framework_eval = _load_framework_eval_module()
    case = _case(input="What color is the sky?", actual_output="The sky is blue.")

    sample = framework_eval.to_ragas_sample(case)

    assert sample.user_input == "What color is the sky?"
    assert sample.response == "The sky is blue."
    assert sample.retrieved_contexts == case["retrieval_context"]


# ---------------------------------------------------------------------------
# deepeval_status / ragas_status: the dependency/key boundary, without a
# live call
# ---------------------------------------------------------------------------


def test_deepeval_status_is_blocked_without_an_api_key():
    framework_eval = _load_framework_eval_module()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        status, reason = framework_eval.deepeval_status()

    assert status == "blocked"
    assert "OPENROUTER_API_KEY" in reason


def test_deepeval_status_is_available_with_an_api_key_present():
    framework_eval = _load_framework_eval_module()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key-for-this-test-only")

        status, reason = framework_eval.deepeval_status()

    assert status == "available"
    assert reason is None


def test_deepeval_status_is_blocked_when_the_package_is_not_importable():
    # `deepeval` genuinely is installed in this project (pyproject.toml), so
    # this simulates "not installed" the standard way: a `None` entry in
    # `sys.modules` makes Python's import system raise `ImportError` for
    # that name, exactly like a real missing package would - without
    # actually uninstalling anything from the venv.
    framework_eval = _load_framework_eval_module()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key-for-this-test-only")
        monkeypatch.setitem(sys.modules, "deepeval", None)

        status, reason = framework_eval.deepeval_status()

    assert status == "blocked"
    assert "not importable" in reason


def test_ragas_status_is_blocked_without_an_api_key():
    framework_eval = _load_framework_eval_module()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        status, reason = framework_eval.ragas_status()

    assert status == "blocked"
    assert "OPENROUTER_API_KEY" in reason


def test_ragas_status_is_blocked_when_the_package_is_not_importable():
    framework_eval = _load_framework_eval_module()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key-for-this-test-only")
        monkeypatch.setitem(sys.modules, "ragas", None)

        status, reason = framework_eval.ragas_status()

    assert status == "blocked"
    assert "not importable" in reason


# ---------------------------------------------------------------------------
# run_deepeval_faithfulness / run_ragas_faithfulness: the default test suite
# must never reach the network - proved here, not just claimed in a
# docstring.
# ---------------------------------------------------------------------------


def test_run_deepeval_faithfulness_defaults_to_skipped_without_touching_deepeval():
    # `sys.modules["deepeval"] = None` makes *any* `import deepeval` raise -
    # if `run_deepeval_faithfulness(case)` (live=False, the default) tried
    # to import deepeval at all, this test would fail with ImportError
    # instead of returning a clean "skipped" result. That's the proof this
    # function makes zero contact with the framework, not just zero contact
    # with the network.
    framework_eval = _load_framework_eval_module()
    case = _case()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setitem(sys.modules, "deepeval", None)

        result = framework_eval.run_deepeval_faithfulness(case)

    assert result["status"] == "skipped"
    assert result["score"] is None
    assert result["framework"] == "deepeval"
    assert result["metric"] == "faithfulness"
    assert result["query_id"] == case["query_id"]


def test_run_deepeval_faithfulness_live_without_key_is_blocked_not_an_error():
    framework_eval = _load_framework_eval_module()
    case = _case()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        result = framework_eval.run_deepeval_faithfulness(case, live=True)

    assert result["status"] == "blocked"
    assert result["score"] is None
    assert "OPENROUTER_API_KEY" in result["error"]


def test_run_ragas_faithfulness_defaults_to_skipped_without_touching_ragas():
    framework_eval = _load_framework_eval_module()
    case = _case()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setitem(sys.modules, "ragas", None)

        result = framework_eval.run_ragas_faithfulness(case)

    assert result["status"] == "skipped"
    assert result["score"] is None
    assert result["framework"] == "ragas"
    assert result["metric"] == "faithfulness"


def test_run_ragas_faithfulness_live_without_key_is_blocked_not_an_error():
    framework_eval = _load_framework_eval_module()
    case = _case()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        result = framework_eval.run_ragas_faithfulness(case, live=True)

    assert result["status"] == "blocked"
    assert result["score"] is None
    assert "OPENROUTER_API_KEY" in result["error"]


# ---------------------------------------------------------------------------
# run_deepeval_contextual_recall (Day 13): same skip/blocked/ok/error
# contract as run_deepeval_faithfulness, different DeepEval metric class.
# ---------------------------------------------------------------------------


def test_run_deepeval_contextual_recall_defaults_to_skipped_without_touching_deepeval():
    # Same "poison sys.modules" proof as the faithfulness test above: if
    # this function tried to import deepeval at all on the live=False
    # (default) path, this would fail with ImportError instead of a clean
    # skipped result.
    framework_eval = _load_framework_eval_module()
    case = _case()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setitem(sys.modules, "deepeval", None)

        result = framework_eval.run_deepeval_contextual_recall(case)

    assert result["status"] == "skipped"
    assert result["score"] is None
    assert result["framework"] == "deepeval"
    assert result["metric"] == "contextual_recall"
    assert result["query_id"] == case["query_id"]


def test_run_deepeval_contextual_recall_live_without_key_is_blocked_not_an_error():
    framework_eval = _load_framework_eval_module()
    case = _case()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        result = framework_eval.run_deepeval_contextual_recall(case, live=True)

    assert result["status"] == "blocked"
    assert result["score"] is None
    assert "OPENROUTER_API_KEY" in result["error"]
