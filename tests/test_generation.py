import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module(module_name):
    """Load a `src/<module_name>.py` script the same way the other test
    files do (see `tests/test_reranking.py`): the project keeps its learning
    modules as plain scripts rather than an installed package, so `src` is
    added to the import path only while the module loads.
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


def _load_generation_module():
    return _load_module("generation")


def _reranked_chunk(source_no, doc_id, title, text, score=1.0):
    """A reranked-shortlist entry shaped like `reranking.rerank` actually
    produces: `final_rank`/`reranker_score` present, plus the `chunk_id`/
    `document_id`/`title`/`text` every shortlist entry (reranked or not)
    always carries. `source_no` doubles as both the chunk index and the
    expected final rank, since every fixture list here is already sorted
    best-first, matching real reranker output.
    """
    return {
        "chunk_id": f"{doc_id}::chunk-{source_no}",
        "document_id": doc_id,
        "title": title,
        "text": text,
        "first_stage_rank": source_no,
        "first_stage_score": score,
        "bm25_score": score,
        "semantic_score": score,
        "reranker_score": score,
        "final_rank": source_no,
    }


# ---------------------------------------------------------------------------
# build_sources: the context contract
# ---------------------------------------------------------------------------


def test_build_sources_numbers_ranked_chunks_starting_at_one():
    generation = _load_generation_module()
    ranked_chunks = [
        _reranked_chunk(1, "POL-001", "Approval Policy", "Band 3 needs VP approval.", score=8.5),
        _reranked_chunk(2, "FAQ-001", "Approval FAQ", "Approvals are cumulative.", score=3.1),
    ]

    sources = generation.build_sources(ranked_chunks)

    assert [source["source_id"] for source in sources] == [1, 2]
    # Every field a citation needs to be auditable (doc_id, chunk_id, title,
    # text, rank, score) must survive the relabeling unchanged.
    assert sources[0]["doc_id"] == "POL-001"
    assert sources[0]["chunk_id"] == "POL-001::chunk-1"
    assert sources[0]["title"] == "Approval Policy"
    assert sources[0]["text"] == "Band 3 needs VP approval."
    assert sources[0]["rank"] == 1
    assert sources[0]["score"] == 8.5


def test_build_sources_falls_back_to_first_stage_rank_and_score():
    # A shortlist that was never reranked (no final_rank/reranker_score) -
    # build_sources must still work, using the first-stage fields instead.
    generation = _load_generation_module()
    chunk = {
        "chunk_id": "SOP-004::chunk-0",
        "document_id": "SOP-004",
        "title": "Renewal SOP",
        "text": "Start renewals 12 months out.",
        "first_stage_rank": 1,
        "first_stage_score": 0.05,
    }

    sources = generation.build_sources([chunk])

    assert sources[0]["rank"] == 1
    assert sources[0]["score"] == 0.05


def test_build_sources_respects_max_sources():
    generation = _load_generation_module()
    ranked_chunks = [
        _reranked_chunk(1, "A", "Title A", "Text A"),
        _reranked_chunk(2, "B", "Title B", "Text B"),
        _reranked_chunk(3, "C", "Title C", "Text C"),
    ]

    sources = generation.build_sources(ranked_chunks, max_sources=2)

    assert [source["doc_id"] for source in sources] == ["A", "B"]


def test_build_sources_handles_empty_input():
    generation = _load_generation_module()
    assert generation.build_sources([]) == []


# ---------------------------------------------------------------------------
# build_prompt: the augmentation step
# ---------------------------------------------------------------------------


def test_build_prompt_contains_every_source_id_doc_id_and_the_question():
    generation = _load_generation_module()
    sources = generation.build_sources(
        [
            _reranked_chunk(1, "POL-001", "Approval Policy", "Band 3 needs VP approval."),
            _reranked_chunk(2, "FAQ-001", "Approval FAQ", "Approvals are cumulative."),
        ]
    )

    prompt = generation.build_prompt("What approval is required for EUR 60,000?", sources)

    assert "[1]" in prompt
    assert "[2]" in prompt
    assert "POL-001" in prompt
    assert "FAQ-001" in prompt
    assert "What approval is required for EUR 60,000?" in prompt


def test_build_prompt_with_no_sources_still_names_the_question():
    generation = _load_generation_module()

    prompt = generation.build_prompt("Any question", [])

    assert "no sources retrieved" in prompt
    assert "Any question" in prompt


# ---------------------------------------------------------------------------
# extract_cited_source_ids / validate_citations: the citation contract
# ---------------------------------------------------------------------------


def test_extract_cited_source_ids_dedupes_and_sorts():
    generation = _load_generation_module()

    assert generation.extract_cited_source_ids("[2] repeats here [1] and again [2].") == [1, 2]


def test_extract_cited_source_ids_returns_empty_list_when_no_brackets():
    generation = _load_generation_module()

    assert generation.extract_cited_source_ids("No citations in this sentence.") == []


def test_validate_citations_flags_orphan_and_uncited_ids():
    generation = _load_generation_module()
    sources = generation.build_sources(
        [
            _reranked_chunk(1, "A", "Title A", "Text A"),
            _reranked_chunk(2, "B", "Title B", "Text B"),
        ]
    )

    # Cites real source 1, a real-but-unused source 2 is not cited, and [9]
    # does not correspond to any retrieved source - a hallucinated citation.
    report = generation.validate_citations("Claim backed by source one [1]. Also see [9].", sources)

    assert report["cited_ids"] == [1, 9]
    assert report["valid_ids"] == [1]
    assert report["orphan_ids"] == [9]
    assert report["uncited_ids"] == [2]


# ---------------------------------------------------------------------------
# generate_answer: the fake-client-friendly generation boundary
# ---------------------------------------------------------------------------


def test_generate_answer_with_empty_sources_refuses_without_calling_client():
    generation = _load_generation_module()

    def client_that_must_not_be_called(prompt):
        raise AssertionError("client should never be called with zero retrieved sources")

    result = generation.generate_answer("Any question", [], client_that_must_not_be_called)

    assert result["answer"] == generation.INSUFFICIENT_EVIDENCE_ANSWER
    assert result["sources"] == []
    assert result["citations"] == {
        "cited_ids": [],
        "valid_ids": [],
        "orphan_ids": [],
        "uncited_ids": [],
    }


def test_generate_answer_passes_prompt_to_client_and_returns_its_text_and_sources():
    generation = _load_generation_module()
    sources = generation.build_sources(
        [_reranked_chunk(1, "POL-001", "Approval Policy", "Band 3 needs VP approval.")]
    )
    received_prompts = []

    def fake_client(prompt):
        received_prompts.append(prompt)
        return "A EUR 60,000 purchase needs VP Procurement approval [1]."

    result = generation.generate_answer("What approval is needed?", sources, fake_client)

    # The client received the real augmented prompt (not the bare question).
    assert len(received_prompts) == 1
    assert "[1]" in received_prompts[0]
    assert "POL-001" in received_prompts[0]
    # The fake client's raw text passes straight through as the answer.
    assert result["answer"] == "A EUR 60,000 purchase needs VP Procurement approval [1]."
    assert result["sources"] == sources
    assert result["citations"]["valid_ids"] == [1]
    assert result["citations"]["orphan_ids"] == []


def test_generate_answer_multi_source_answer_can_cite_every_source():
    # The Q091-style shape: several documents, each contributing a distinct
    # fact, and the answer citing all of them rather than only the first.
    generation = _load_generation_module()
    sources = generation.build_sources(
        [
            _reranked_chunk(1, "POL-001", "Approval Policy", "Band 3 needs VP approval."),
            _reranked_chunk(2, "POL-003", "Security Policy", "Certificates refresh annually."),
            _reranked_chunk(3, "GUIDE-002", "Renewal Guide", "Start renewals 12 months out."),
        ]
    )

    def fake_client(prompt):
        return (
            "Approval: VP Procurement sign-off is required [1]. "
            "Security: certification evidence must be refreshed annually [2]. "
            "Commercially, start the renewal process 12 months out [3]."
        )

    result = generation.generate_answer("What do I need for this renewal?", sources, fake_client)

    assert result["citations"]["valid_ids"] == [1, 2, 3]
    assert result["citations"]["orphan_ids"] == []
    assert result["citations"]["uncited_ids"] == []


def test_generate_answer_flags_a_hallucinated_citation():
    generation = _load_generation_module()
    sources = generation.build_sources([_reranked_chunk(1, "A", "Title A", "Text A")])

    def fake_client_that_invents_a_source(prompt):
        return "This is backed by source [1] and also source [7]."

    result = generation.generate_answer("question", sources, fake_client_that_invents_a_source)

    assert result["citations"]["valid_ids"] == [1]
    assert result["citations"]["orphan_ids"] == [7]


# ---------------------------------------------------------------------------
# make_openrouter_client: only the deterministic, no-network guard rail
# ---------------------------------------------------------------------------


def test_make_openrouter_client_raises_without_api_key_before_any_network_call():
    generation = _load_generation_module()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            generation.make_openrouter_client(api_key=None)


def test_make_openrouter_client_raises_a_clear_error_on_blank_provider_content():
    """A live provider can hand back `None`/empty `content` - seen live on
    2026-09-14, where a harder multi-source question returned no answer
    text at all. Without a check for this, that `None` would silently
    reach `extract_cited_source_ids`'s regex and crash with an opaque
    `TypeError`, far from where the real problem (a blank live response)
    actually happened. This test fakes the `openai` SDK's response shape
    (not a real network call) to check the *client's* boundary behavior -
    it needs `openai` importable to build that fake, unlike every other
    test in this file, since it is specifically testing what happens right
    after the SDK call returns.
    """
    import types

    import openai

    generation = _load_generation_module()

    class FakeOpenAIClient:
        """Stands in for `openai.OpenAI(...)` - same `.chat.completions.create(...)`
        shape, but returns a response whose message has no content, exactly
        like the live blank-response case being tested here."""

        def __init__(self, **kwargs):
            del kwargs  # accepted (api_key, base_url, timeout), not used by the fake
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            del kwargs  # accepted (model, messages, max_tokens, ...), not used by the fake
            blank_message = types.SimpleNamespace(content=None)
            choice = types.SimpleNamespace(message=blank_message, finish_reason="content_filter")
            return types.SimpleNamespace(choices=[choice])

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(openai, "OpenAI", FakeOpenAIClient)

        client = generation.make_openrouter_client(model="fake-model", api_key="fake-key")

        with pytest.raises(RuntimeError, match="returned no answer text"):
            client("any prompt")
